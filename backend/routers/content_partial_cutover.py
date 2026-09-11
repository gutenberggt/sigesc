"""Cutover progressivo do contrato legado ``/learning-objects``.

F2.7 introduziu a projeção class-wide do professor. A F4 mantém a mesma URL e
UI, mas faz o formulário docente gravar em ``content_entries`` e projeta o
histórico legado apenas como fallback. Perfis não docentes preservam o writer
legado nesta fase; registros canônicos continuam visíveis para gestão.
"""
from __future__ import annotations

from functools import wraps
from typing import Any

from fastapi import HTTPException, Request

from auth_middleware import AuthMiddleware
from services.content_form_canonical_cutover import (
    create_from_learning_object_form,
    delete_from_learning_object_form,
    get_canonical_learning_object,
    list_learning_objects_cutover,
    update_from_learning_object_form,
)
from services.content_pdf_partial_cutover import generate_professor_classwide_pdf


READ_ROLES = {
    "admin", "secretario", "diretor", "coordenador", "auxiliar_secretaria",
    "professor", "semed", "semed1", "semed2", "semed3",
}
WRITE_ROLES = {
    "admin", "secretario", "diretor", "coordenador", "auxiliar_secretaria", "professor",
}


def _find_route(router: Any, path: str, method: str):
    for route in getattr(router, "routes", []):
        if getattr(route, "path", None) != path:
            continue
        if method in (getattr(route, "methods", set()) or set()):
            return route
    return None


def _request_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Request | None:
    request = kwargs.get("request")
    if isinstance(request, Request):
        return request
    return next((arg for arg in args if isinstance(arg, Request)), None)


def _value_from_call(
    args: tuple[Any, ...], kwargs: dict[str, Any], name: str, *, position: int | None = None
):
    if name in kwargs:
        return kwargs[name]
    if position is not None and len(args) > position:
        return args[position]
    return None


def _replace_call(route: Any, call: Any) -> None:
    route.endpoint = call
    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        dependant.call = call


async def _user(request: Request) -> dict:
    return await AuthMiddleware.get_current_user(request)


def install_professor_content_partial_cutover_setup(learning_objects_mod: Any) -> None:
    """Instala F2.7 + F4 sobre o setup legado, sem criar rotas concorrentes."""
    if getattr(learning_objects_mod, "_p0_250_f4_canonical_form_installed", False):
        return

    original_setup = learning_objects_mod.setup_router

    @wraps(original_setup)
    def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
        configured = original_setup(
            db,
            audit_service=audit_service,
            sandbox_db=sandbox_db,
            **kwargs,
        )
        scoped_default = lambda current_user: (
            sandbox_db if current_user.get("is_sandbox") and sandbox_db else db
        )

        # GET lista — professor usa projeção efetiva; gestão recebe legado + canônico.
        list_route = _find_route(configured, "/learning-objects", "GET")
        if list_route is None:
            raise RuntimeError("GET /learning-objects não encontrado para F4")
        legacy_list = getattr(getattr(list_route, "dependant", None), "call", None) or list_route.endpoint

        @wraps(legacy_list)
        async def cutover_list(*args, **call_kwargs):
            request = _request_from_call(args, call_kwargs)
            if request is None:
                return await legacy_list(*args, **call_kwargs)
            current_user = await _user(request)
            class_id = call_kwargs.get("class_id")
            course_id = call_kwargs.get("course_id")
            if current_user.get("role") == "professor" and not class_id:
                return await legacy_list(*args, **call_kwargs)

            scoped_db = scoped_default(current_user)
            if current_user.get("role") == "professor":
                legacy_items = []
            else:
                legacy_items = await legacy_list(*args, **call_kwargs)
            return await list_learning_objects_cutover(
                scoped_db,
                current_user,
                request,
                legacy_items=legacy_items,
                class_id=class_id,
                course_id=course_id,
                date=call_kwargs.get("date"),
                academic_year=call_kwargs.get("academic_year"),
                month=call_kwargs.get("month"),
            )

        _replace_call(list_route, cutover_list)

        # PDF class-wide — sem assignment_id explícito, o professor deve receber
        # exatamente a mesma projeção mista da tela (legado + canônico F4).
        # PDFs DVD com assignment_id e perfis de gestão preservam o adaptador
        # anterior sem alteração.
        pdf_route = _find_route(configured, "/learning-objects/pdf/bimestre/{class_id}", "GET")
        if pdf_route is None:
            raise RuntimeError("PDF de learning-objects não encontrado para F4")
        previous_pdf = getattr(getattr(pdf_route, "dependant", None), "call", None) or pdf_route.endpoint

        @wraps(previous_pdf)
        async def cutover_pdf(*args, **call_kwargs):
            request = _request_from_call(args, call_kwargs)
            if request is None:
                return await previous_pdf(*args, **call_kwargs)
            current_user = await _user(request)
            assignment_id = _value_from_call(
                args, call_kwargs, "assignment_id", position=5
            )
            if current_user.get("role") != "professor" or assignment_id:
                return await previous_pdf(*args, **call_kwargs)

            return await generate_professor_classwide_pdf(
                learning_objects_mod,
                scoped_default(current_user),
                current_user,
                request,
                class_id=_value_from_call(args, call_kwargs, "class_id", position=0),
                bimestre=int(_value_from_call(args, call_kwargs, "bimestre", position=2)),
                academic_year=_value_from_call(
                    args, call_kwargs, "academic_year", position=3
                ),
                course_id=_value_from_call(args, call_kwargs, "course_id", position=4),
            )

        _replace_call(pdf_route, cutover_pdf)

        # GET individual — primeiro reconhece id canônico; legado segue intacto.
        get_route = _find_route(configured, "/learning-objects/{object_id}", "GET")
        if get_route is None:
            raise RuntimeError("GET individual de learning-objects não encontrado para F4")
        legacy_get = getattr(getattr(get_route, "dependant", None), "call", None) or get_route.endpoint

        @wraps(legacy_get)
        async def cutover_get(*args, **call_kwargs):
            request = _request_from_call(args, call_kwargs)
            if request is None:
                return await legacy_get(*args, **call_kwargs)
            current_user = await _user(request)
            if current_user.get("role") not in READ_ROLES:
                return await legacy_get(*args, **call_kwargs)
            entry_id = _value_from_call(args, call_kwargs, "object_id", position=0)
            canonical = await get_canonical_learning_object(
                scoped_default(current_user), current_user, request, entry_id
            )
            if canonical is not None:
                return canonical
            return await legacy_get(*args, **call_kwargs)

        _replace_call(get_route, cutover_get)

        # POST — somente o professor muda de writer nesta fase.
        post_route = _find_route(configured, "/learning-objects", "POST")
        if post_route is None:
            raise RuntimeError("POST /learning-objects não encontrado para F4")
        legacy_create = getattr(getattr(post_route, "dependant", None), "call", None) or post_route.endpoint

        @wraps(legacy_create)
        async def cutover_create(*args, **call_kwargs):
            request = _request_from_call(args, call_kwargs)
            if request is None:
                return await legacy_create(*args, **call_kwargs)
            current_user = await _user(request)
            if current_user.get("role") != "professor":
                return await legacy_create(*args, **call_kwargs)
            data = _value_from_call(args, call_kwargs, "data", position=0)
            return await create_from_learning_object_form(
                scoped_default(current_user), audit_service, current_user, request, data
            )

        _replace_call(post_route, cutover_create)

        # PUT — ids canônicos usam o writer canônico; ids históricos continuam legados.
        put_route = _find_route(configured, "/learning-objects/{object_id}", "PUT")
        if put_route is None:
            raise RuntimeError("PUT /learning-objects/{object_id} não encontrado para F4")
        legacy_update = getattr(getattr(put_route, "dependant", None), "call", None) or put_route.endpoint

        @wraps(legacy_update)
        async def cutover_update(*args, **call_kwargs):
            request = _request_from_call(args, call_kwargs)
            if request is None:
                return await legacy_update(*args, **call_kwargs)
            current_user = await _user(request)
            if current_user.get("role") not in WRITE_ROLES:
                return await legacy_update(*args, **call_kwargs)
            entry_id = _value_from_call(args, call_kwargs, "object_id", position=0)
            scoped_db = scoped_default(current_user)
            canonical = await scoped_db.content_entries.find_one(
                {"id": entry_id, "deleted": False}, {"_id": 0, "id": 1}
            )
            if not canonical:
                return await legacy_update(*args, **call_kwargs)
            data = _value_from_call(args, call_kwargs, "data", position=1)
            return await update_from_learning_object_form(
                scoped_db, audit_service, current_user, request, entry_id, data
            )

        _replace_call(put_route, cutover_update)

        # DELETE — canônico é soft-delete auditado; histórico mantém contrato antigo.
        delete_route = _find_route(configured, "/learning-objects/{object_id}", "DELETE")
        if delete_route is None:
            raise RuntimeError("DELETE /learning-objects/{object_id} não encontrado para F4")
        legacy_delete = getattr(getattr(delete_route, "dependant", None), "call", None) or delete_route.endpoint

        @wraps(legacy_delete)
        async def cutover_delete(*args, **call_kwargs):
            request = _request_from_call(args, call_kwargs)
            if request is None:
                return await legacy_delete(*args, **call_kwargs)
            current_user = await _user(request)
            if current_user.get("role") not in WRITE_ROLES:
                return await legacy_delete(*args, **call_kwargs)
            entry_id = _value_from_call(args, call_kwargs, "object_id", position=0)
            scoped_db = scoped_default(current_user)
            canonical = await scoped_db.content_entries.find_one(
                {"id": entry_id, "deleted": False}, {"_id": 0, "id": 1}
            )
            if not canonical:
                return await legacy_delete(*args, **call_kwargs)
            return await delete_from_learning_object_form(
                scoped_db, audit_service, current_user, request, entry_id
            )

        _replace_call(delete_route, cutover_delete)

        # Cópia — conteúdo canônico pode continuar usando o modal legado. O destino
        # é novamente resolvido pelo writer canônico; nenhuma cópia vai a learning_objects.
        copy_route = _find_route(configured, "/learning-objects/{object_id}/copy-to-class", "POST")
        if copy_route is None:
            raise RuntimeError("copy-to-class legado não encontrado para F4")
        legacy_copy = getattr(getattr(copy_route, "dependant", None), "call", None) or copy_route.endpoint

        @wraps(legacy_copy)
        async def cutover_copy(*args, **call_kwargs):
            request = _request_from_call(args, call_kwargs)
            if request is None:
                return await legacy_copy(*args, **call_kwargs)
            current_user = await _user(request)
            if current_user.get("role") != "professor":
                return await legacy_copy(*args, **call_kwargs)
            source_id = _value_from_call(args, call_kwargs, "object_id", position=0)
            scoped_db = scoped_default(current_user)
            source = await scoped_db.content_entries.find_one(
                {"id": source_id, "deleted": False}, {"_id": 0}
            )
            if not source:
                return await legacy_copy(*args, **call_kwargs)
            visible = await get_canonical_learning_object(
                scoped_db, current_user, request, source_id
            )
            if visible is None:
                raise HTTPException(status_code=404, detail="Conteúdo de origem não encontrado")
            try:
                body = await request.json()
            except Exception:
                body = {}
            target_class_id = (body or {}).get("target_class_id")
            target_course_id = (body or {}).get("target_course_id")
            target_date = (body or {}).get("target_date") or source.get("date")
            if not target_class_id or not target_course_id:
                raise HTTPException(
                    status_code=400,
                    detail="target_class_id e target_course_id são obrigatórios",
                )
            conflict = await scoped_db.content_entries.find_one(
                {
                    "class_id": target_class_id,
                    "component_id": target_course_id,
                    "date": target_date,
                    "deleted": False,
                },
                {"_id": 0, "id": 1},
            )
            if conflict:
                raise HTTPException(status_code=409, detail=f"Já existe conteúdo no destino em {target_date}.")
            created = await create_from_learning_object_form(
                scoped_db,
                audit_service,
                current_user,
                request,
                {
                    "class_id": target_class_id,
                    "course_id": target_course_id,
                    "date": target_date,
                    "academic_year": source.get("academic_year"),
                    "number_of_classes": source.get("number_of_classes") or 1,
                    "content": source.get("content") or "",
                    "methodology": source.get("methodology"),
                    "observations": source.get("observations"),
                    "resources": source.get("resources"),
                    "skill_codigos": source.get("skill_codigos") or [],
                    "adaptation_ids": source.get("adaptation_ids") or [],
                },
            )
            await scoped_db.content_entries.update_one(
                {"id": created["id"]},
                {"$set": {
                    "copied_from_id": source_id,
                    "copied_from_source": "content_entries",
                }},
            )
            return await get_canonical_learning_object(
                scoped_db, current_user, request, created["id"]
            )

        _replace_call(copy_route, cutover_copy)

        configured._p0_250_f4_canonical_form = True
        return configured

    learning_objects_mod.setup_router = setup_router
    learning_objects_mod._p0_250_f2_7_partial_cutover_installed = True
    learning_objects_mod._p0_250_f4_canonical_form_installed = True
