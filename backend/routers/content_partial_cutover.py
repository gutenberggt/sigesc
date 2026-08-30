"""F2.7 — adaptador class-wide para cutover parcial de Conteúdo.

Substitui apenas a leitura ``GET /learning-objects`` quando o chamador é
professor, existe ``class_id`` e não existe ``course_id``. Gestão e leituras
component-scoped preservam integralmente o contrato anterior.
"""
from __future__ import annotations

from functools import wraps
from typing import Any

from fastapi import HTTPException, Request

from auth_middleware import AuthMiddleware
from services.professor_content_projection import (
    ProfessorContentProjectionError,
    list_professor_content_projection,
)
from tenant_scope import get_mantenedora_scope


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


def _projection_http_error(exc: ProfessorContentProjectionError) -> HTTPException:
    if exc.code == "CLASS_NOT_FOUND_IN_TENANT":
        status = 404
    elif exc.code == "CANONICAL_CONTENT_HISTORY_UNAVAILABLE":
        status = 409
    else:
        status = 403
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": exc.message},
    )


def install_professor_content_partial_cutover_setup(learning_objects_mod: Any) -> None:
    """Instala a projeção mista após os demais adapters do learning_objects."""
    if getattr(learning_objects_mod, "_p0_250_f2_7_partial_cutover_installed", False):
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
        route = _find_route(configured, "/learning-objects", "GET")
        if route is None:
            raise RuntimeError("GET /learning-objects não encontrado para F2.7")

        dependant = getattr(route, "dependant", None)
        legacy_list = getattr(dependant, "call", None) or getattr(route, "endpoint", None)
        if legacy_list is None:
            raise RuntimeError("Endpoint GET /learning-objects sem callable para F2.7")
        if getattr(legacy_list, "_p0_250_f2_7_mixed_reader", False):
            return configured

        @wraps(legacy_list)
        async def mixed_list(*args, **call_kwargs):
            request = _request_from_call(args, call_kwargs)
            if request is None:
                return await legacy_list(*args, **call_kwargs)

            current_user = await AuthMiddleware.get_current_user(request)
            class_id = call_kwargs.get("class_id")
            course_id = call_kwargs.get("course_id")

            # Somente o caso class-wide do professor muda. O reader legado de
            # gestão e o contrato component-scoped F2.5 permanecem intactos.
            if current_user.get("role") != "professor" or not class_id or course_id:
                return await legacy_list(*args, **call_kwargs)

            scoped_db = sandbox_db if current_user.get("is_sandbox") and sandbox_db else db
            try:
                return await list_professor_content_projection(
                    scoped_db,
                    current_user,
                    class_id=class_id,
                    academic_year=call_kwargs.get("academic_year"),
                    month=call_kwargs.get("month"),
                    date=call_kwargs.get("date"),
                    active_mantenedora_id=get_mantenedora_scope(current_user, request),
                )
            except ProfessorContentProjectionError as exc:
                raise _projection_http_error(exc) from exc

        mixed_list._p0_250_f2_7_mixed_reader = True  # type: ignore[attr-defined]
        route.endpoint = mixed_list
        if dependant is not None:
            dependant.call = mixed_list
        return configured

    learning_objects_mod.setup_router = setup_router
    learning_objects_mod._p0_250_f2_7_partial_cutover_installed = True
