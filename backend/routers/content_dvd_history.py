"""Adaptador P0 de histórico de Conteúdos no Diário por Vínculo.

Segue o mesmo padrão dos adaptadores DVD de Frequência/Notas: preserva os
routers existentes e substitui somente as superfícies de leitura que precisam
compor ``learning_objects`` histórico com ``content_entries`` canônico.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from auth_middleware import AuthMiddleware
from services.content_assignment_scope import filter_visible_content_entries
from services.content_history_bridge import (
    ContentHistoryBridgeError,
    list_assignment_content_history,
)
from services.teacher_diaries import list_teacher_diaries
from tenant_scope import get_mantenedora_scope


VIEW_ROLES = [
    'professor', 'coordenador', 'admin', 'admin_teste', 'super_admin',
    'secretario', 'gerente', 'auxiliar_secretaria', 'diretor',
    'ass_social_2', 'semed3',
]


def _http_bridge_error(exc: ContentHistoryBridgeError) -> HTTPException:
    not_found = {"ASSIGNMENT_NOT_FOUND", "CLASS_NOT_FOUND"}
    conflicts = {
        "ASSIGNMENT_NOT_ACTIVE",
        "DVD_NOT_ENABLED",
        "ASSIGNMENT_VALID_FROM_REQUIRED",
    }
    status = 404 if exc.code in not_found else 409 if exc.code in conflicts else 403
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": exc.message},
    )


def _find_route(router, path: str, method: str):
    for route in list(router.routes):
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set()):
            return route
    return None


def _remove_route(router, path: str, method: str):
    route = _find_route(router, path, method)
    if route is None:
        return None
    router.routes.remove(route)
    return route.endpoint


def _is_multi_component_day_level(class_info: dict) -> bool:
    """Níveis cuja UI registra o dia da turma com vários componentes/campos."""
    level = str(
        class_info.get("education_level")
        or class_info.get("nivel_ensino")
        or ""
    ).lower()
    return level in {
        "educacao_infantil",
        "fundamental_anos_iniciais",
        "eja_inicial",
        "eja",
    }


async def _pdf_assignment_ids(
    db,
    current_user,
    request,
    *,
    primary_assignment: dict,
    class_info: dict,
    academic_year: int,
    course_id: Optional[str],
) -> list[str]:
    """Resolve vínculos de conteúdo do próprio professor que compõem o PDF.

    Anos Finais/EJA final e PDFs com componente explícito continuam estritamente
    no assignment selecionado. Infantil/Anos Iniciais sem componente explícito
    reúnem os assignments irmãos do mesmo professor/turma, conforme a UI diária.
    """
    primary_id = primary_assignment.get("id")
    if not primary_id:
        return []
    if course_id or not _is_multi_component_day_level(class_info):
        return [primary_id]

    reference_date = str(
        primary_assignment.get("valid_from") or datetime.now().date().isoformat()
    )[:10]
    diaries = await list_teacher_diaries(
        db,
        current_user,
        academic_year=academic_year,
        reference_date=reference_date,
        active_mantenedora_id=get_mantenedora_scope(current_user, request),
    )
    sibling_ids = [
        item.get("assignment_id")
        for item in diaries.get("items", [])
        if item.get("class_id") == primary_assignment.get("class_id")
        and item.get("capabilities", {}).get("content_enabled") is True
        and item.get("assignment_id")
    ]
    if primary_id not in sibling_ids:
        sibling_ids.append(primary_id)
    return list(dict.fromkeys(sibling_ids))


async def _merged_pdf_history(
    db,
    current_user,
    request,
    *,
    assignment_ids: list[str],
    class_id: str,
    course_id: Optional[str],
) -> list[dict]:
    """Compõe histórias autorizadas sem cruzar autoria entre professores."""
    merged_items: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for current_assignment_id in assignment_ids:
        try:
            history = await list_assignment_content_history(
                db,
                current_user,
                assignment_id=current_assignment_id,
                class_id=class_id,
                component_id=course_id,
                active_mantenedora_id=get_mantenedora_scope(current_user, request),
            )
        except ContentHistoryBridgeError as exc:
            if current_assignment_id == assignment_ids[0]:
                raise
            # Um vínculo irmão que deixou de ser válido não pode derrubar o
            # vínculo principal já autorizado nem ampliar acesso por fallback.
            continue
        for item in history.get("items", []):
            key = (str(item.get("source") or ""), str(item.get("id") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged_items.append(dict(item))
    return merged_items


def install_content_entries_history_adapter(base_router, db, sandbox_db=None):
    """Substitui somente GET /content-entries; escritas permanecem intactas."""
    if getattr(base_router, "_dvd_content_history_installed", False):
        return base_router

    legacy_list = _remove_route(base_router, "/content-entries", "GET")

    @base_router.get("")
    async def dvd_history_list(
        request: Request,
        class_id: Optional[str] = Query(None),
        date: Optional[str] = Query(None),
        teacher_id: Optional[str] = Query(None),
        component_id: Optional[str] = Query(None),
        assignment_id: Optional[str] = Query(None),
        include_deleted: bool = Query(False),
    ):
        current_user = await AuthMiddleware.require_roles(VIEW_ROLES)(request)

        if assignment_id:
            try:
                return await list_assignment_content_history(
                    db,
                    current_user,
                    assignment_id=assignment_id,
                    class_id=class_id,
                    date=date,
                    teacher_id=teacher_id,
                    component_id=component_id,
                    include_deleted=include_deleted,
                    active_mantenedora_id=get_mantenedora_scope(current_user, request),
                )
            except ContentHistoryBridgeError as exc:
                raise _http_bridge_error(exc) from exc

        # Sem assignment_id, replica estritamente o contrato anterior.
        q: dict = {}
        if not include_deleted:
            q["deleted"] = False
        if class_id:
            q["class_id"] = class_id
        if date:
            q["date"] = date
        if teacher_id:
            q["teacher_id"] = teacher_id
        if component_id:
            q["component_id"] = component_id
        cursor = db.content_entries.find(q, {"_id": 0}).sort([("date", -1), ("aula_numero", 1)])
        items = await cursor.to_list(2000)
        visible = await filter_visible_content_entries(
            db,
            current_user,
            items,
            active_mantenedora_id=get_mantenedora_scope(current_user, request),
        )
        return {"items": visible, "total": len(visible)}

    if legacy_list is None:
        raise RuntimeError("GET /content-entries não encontrado para instalação do bridge histórico")

    base_router._dvd_content_history_installed = True
    return base_router


def install_content_entries_history_setup(content_entries_mod):
    """Envolve setup_content_entries_router sem alterar o router canônico."""
    if getattr(content_entries_mod, "_dvd_history_setup_installed", False):
        return
    original_setup = content_entries_mod.setup_content_entries_router

    def setup_content_entries_router(db, audit_service, sandbox_db=None):
        configured = original_setup(db, audit_service, sandbox_db)
        return install_content_entries_history_adapter(configured, db, sandbox_db)

    content_entries_mod.setup_content_entries_router = setup_content_entries_router
    content_entries_mod._dvd_history_setup_installed = True


def install_learning_objects_history_setup(learning_objects_mod):
    """Envolve setup_router para substituir somente o PDF DVD por visão consolidada."""
    if getattr(learning_objects_mod, "_dvd_history_setup_installed", False):
        return
    original_setup = learning_objects_mod.setup_router

    def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
        configured = original_setup(db, audit_service, sandbox_db, **kwargs)
        router = learning_objects_mod.router
        legacy_pdf = _remove_route(
            router, "/learning-objects/pdf/bimestre/{class_id}", "GET"
        )
        if legacy_pdf is None:
            raise RuntimeError("PDF legado de conteúdos não encontrado para instalação do bridge histórico")

        @router.get("/learning-objects/pdf/bimestre/{class_id}")
        async def dvd_history_pdf(
            class_id: str,
            request: Request,
            bimestre: int = Query(..., ge=1, le=4),
            academic_year: Optional[int] = None,
            course_id: Optional[str] = None,
            assignment_id: Optional[str] = None,
        ):
            # Sem assignment_id, preserva integralmente o endpoint anterior.
            if not assignment_id:
                return await legacy_pdf(
                    class_id,
                    request,
                    bimestre,
                    academic_year,
                    course_id,
                    assignment_id,
                )

            current_user = await AuthMiddleware.get_current_user(request)
            academic_year = academic_year or datetime.now().year

            import asyncio
            turma_task = db.classes.find_one({"id": class_id}, {"_id": 0})
            mantenedora_task = learning_objects_mod.get_mantenedora_cached(db)
            calendario_task = learning_objects_mod.get_calendario_cached(db, academic_year, None)
            turma, mantenedora, calendario = await asyncio.gather(
                turma_task, mantenedora_task, calendario_task
            )
            if not turma:
                raise HTTPException(status_code=404, detail="Turma não encontrada")
            school = await learning_objects_mod.get_school_cached(db, turma.get("school_id"))
            if not school:
                raise HTTPException(status_code=404, detail="Escola não encontrada")

            bk_inicio = f"bimestre_{bimestre}_inicio"
            bk_fim = f"bimestre_{bimestre}_fim"
            if calendario and calendario.get(bk_inicio) and calendario.get(bk_fim):
                period_start = str(calendario[bk_inicio])[:10]
                period_end = str(calendario[bk_fim])[:10]
            else:
                periodos = {
                    1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
                    2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
                    3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
                    4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
                }
                period_start, period_end = periodos[bimestre]

            assignment = await db.teacher_class_assignments.find_one(
                {"id": assignment_id, "deleted": False},
                {
                    "_id": 0,
                    "id": 1,
                    "teacher_id": 1,
                    "teacher_name": 1,
                    "class_id": 1,
                    "component_id": 1,
                    "valid_from": 1,
                },
            )
            if not assignment:
                raise HTTPException(status_code=404, detail="Vínculo docente não encontrado")

            assignment_ids = await _pdf_assignment_ids(
                db,
                current_user,
                request,
                primary_assignment=assignment,
                class_info=turma,
                academic_year=academic_year,
                course_id=course_id,
            )
            try:
                merged_items = await _merged_pdf_history(
                    db,
                    current_user,
                    request,
                    assignment_ids=assignment_ids,
                    class_id=class_id,
                    course_id=course_id,
                )
            except ContentHistoryBridgeError as exc:
                raise _http_bridge_error(exc) from exc

            records = [
                dict(item)
                for item in merged_items
                if period_start <= str(item.get("date") or "")[:10] <= period_end
                and (
                    item.get("academic_year") in (None, academic_year, str(academic_year))
                )
            ]
            records.sort(key=lambda item: (str(item.get("date") or ""), item.get("aula_numero") or 0))

            course_ids = list({r.get("course_id") for r in records if r.get("course_id")})
            course_names = {}
            if course_ids:
                cursor = db.courses.find(
                    {"id": {"$in": course_ids}},
                    {"_id": 0, "id": 1, "name": 1},
                )
                async for course in cursor:
                    course_names[course["id"]] = course.get("name", "")
            for record in records:
                record["course_name"] = course_names.get(record.get("course_id"), "")

            teacher_name = (assignment or {}).get("teacher_name") or ""
            if not teacher_name and (assignment or {}).get("teacher_id"):
                teacher = await db.users.find_one(
                    {"id": assignment.get("teacher_id")},
                    {"_id": 0, "full_name": 1, "name": 1},
                )
                if teacher:
                    teacher_name = teacher.get("full_name") or teacher.get("name") or ""

            # Mesma regra de dias previstos usada pelo endpoint legado.
            dias_previstos = 0
            if period_start and period_end:
                from datetime import datetime as dt_calc, timedelta
                events = await db.calendar_events.find(
                    {"academic_year": {"$in": [academic_year, str(academic_year)]}},
                    {"_id": 0, "event_type": 1, "start_date": 1, "end_date": 1, "is_school_day": 1},
                ).to_list(1000)
                non_school_dates = set()
                saturday_letivo_dates = set()
                for event in events:
                    event_type = event.get("event_type", "")
                    ev_start = str(event.get("start_date") or "")[:10]
                    ev_end = str(event.get("end_date") or ev_start)[:10]
                    if not ev_start:
                        continue
                    try:
                        cursor_date = dt_calc.strptime(ev_start, "%Y-%m-%d")
                        final_date = dt_calc.strptime(ev_end, "%Y-%m-%d")
                    except ValueError:
                        continue
                    while cursor_date <= final_date:
                        ds = cursor_date.strftime("%Y-%m-%d")
                        if (
                            "feriado" in event_type
                            or event_type == "recesso_escolar"
                            or event.get("is_school_day") is False
                        ):
                            non_school_dates.add(ds)
                        if event_type == "sabado_letivo" or event.get("is_school_day") is True:
                            if cursor_date.weekday() == 5:
                                saturday_letivo_dates.add(ds)
                        cursor_date += timedelta(days=1)
                try:
                    cursor_date = dt_calc.strptime(period_start, "%Y-%m-%d")
                    final_date = dt_calc.strptime(period_end, "%Y-%m-%d")
                    while cursor_date <= final_date:
                        ds = cursor_date.strftime("%Y-%m-%d")
                        dow = cursor_date.weekday()
                        blocked = (
                            dow == 6
                            or ds in non_school_dates
                            or (dow == 5 and ds not in saturday_letivo_dates)
                        )
                        if not blocked:
                            dias_previstos += 1
                        cursor_date += timedelta(days=1)
                except ValueError:
                    pass

            try:
                teacher_names = [teacher_name] if teacher_name else None
                pdf_buffer = learning_objects_mod.generate_learning_objects_pdf(
                    school=school,
                    class_info=turma,
                    records=records,
                    bimestre=bimestre,
                    academic_year=academic_year,
                    period_start=period_start,
                    period_end=period_end,
                    teacher_name=teacher_name,
                    mantenedora=mantenedora,
                    dias_previstos=dias_previstos,
                    teacher_names=teacher_names,
                )
                course_name_part = ""
                if course_id and records:
                    course_name_part = f"_{records[0].get('course_name', '')}"
                filename = (
                    f"objetos_conhecimento_{turma.get('name', 'turma')}"
                    f"{course_name_part}_{bimestre}bim_{academic_year}.pdf"
                )
                filename = filename.replace(" ", "_").replace("/", "-")
                return StreamingResponse(
                    pdf_buffer,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={filename}"},
                )
            except HTTPException:
                raise
            except Exception as exc:
                learning_objects_mod.logger.exception(
                    "Erro ao gerar PDF consolidado de objetos de conhecimento"
                )
                raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {exc}") from exc

        learning_objects_mod.router = router
        return configured

    learning_objects_mod.setup_router = setup_router
    learning_objects_mod._dvd_history_setup_installed = True


def install_content_history_setups(content_entries_mod, learning_objects_mod):
    install_content_entries_history_setup(content_entries_mod)
    install_learning_objects_history_setup(learning_objects_mod)
