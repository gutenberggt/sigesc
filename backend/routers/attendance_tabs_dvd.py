"""Paridade segura das abas de Frequência no Diário por Vínculo (DVD).

Esta camada é instalada *depois* do adaptador Fase 4 e corrige lacunas de
compatibilidade sem alterar/migrar registros históricos:

- histórico oficial `class_daily` anterior ao cutover volta a alimentar
  Registros, Resumo, Relatórios, Alertas e PDF em modo somente leitura;
- vínculos `regular` do mesmo professor/turma compartilham a frequência diária
  oficial sem reatribuir a autoria/proveniência do documento já existente;
- Informações dos Estudantes passa a exigir o `assignment_id` no modo DVD e
  usa o roster autorizado do vínculo;
- professor no fluxo legado só consulta Informações de turmas às quais está
  realmente alocado.

Nenhuma função deste arquivo faz migração retroativa ou adiciona assignment_id
em documentos legados.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Any, Mapping, Optional

from fastapi import HTTPException, Request

from auth_middleware import AuthMiddleware
from services.attendance_assignment_roster import build_attendance_roster
from services.attendance_assignment_scope import (
    AttendanceAssignmentContext,
    AttendanceAssignmentScopeError,
    resolve_attendance_assignment,
)
from services.diary_assignment_contract import AttendanceMode, AttendancePurpose
from tenant_scope import get_mantenedora_scope


def _remove_route(router, path: str, method: str):
    for route in list(router.routes):
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set()):
            router.routes.remove(route)
            return route.endpoint
    return None


def _db_for_user(db, sandbox_db, user: Mapping[str, Any]):
    if user.get("is_sandbox") and sandbox_db is not None:
        return sandbox_db
    return db


def _scope_http_error(exc: AttendanceAssignmentScopeError) -> HTTPException:
    status_code = 403
    if exc.code.startswith("INVALID_") or exc.code.endswith("_INVALID"):
        status_code = 422
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )


async def _legacy_staff_matches_teacher(db, legacy: Mapping[str, Any], teacher_id: str) -> bool:
    staff_id = legacy.get("staff_id")
    if not staff_id:
        return False
    staff = await db.staff.find_one(
        {"id": staff_id},
        {"_id": 0, "user_id": 1, "email": 1},
    )
    if not staff:
        return False
    if staff.get("user_id"):
        return str(staff.get("user_id")) == str(teacher_id)

    email = str(staff.get("email") or "").strip()
    if not email:
        return False
    user = await db.users.find_one(
        {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
        {"_id": 0, "id": 1},
    )
    return bool(user and str(user.get("id")) == str(teacher_id))


async def _safe_cutover_legacy_assignment(
    db,
    context: AttendanceAssignmentContext,
    academic_year: int,
) -> Optional[dict]:
    """Resolve a origem legada somente para vínculos realmente ativados na 38G-B.

    O vínculo legado é revalidado contra professor, turma, componente, ano e
    status. Qualquer divergência desliga silenciosamente a ponte histórica.
    """
    if context.attendance_mode is not AttendanceMode.CLASS_DAILY:
        return None
    if context.attendance_purpose is not AttendancePurpose.OFFICIAL:
        return None

    assignment = context.assignment
    provenance = assignment.get("cutover_provenance") or {}
    source_id = provenance.get("source_legacy_assignment_id")
    if (
        not source_id
        or provenance.get("apply_phase") != "38G-B"
        or provenance.get("apply_state") != "ACTIVATED"
    ):
        return None

    legacy = await db.teacher_assignments.find_one(
        {
            "id": source_id,
            "class_id": assignment.get("class_id"),
            "course_id": assignment.get("component_id"),
            "status": "ativo",
            "academic_year": {"$in": [academic_year, str(academic_year)]},
        },
        {"_id": 0},
    )
    if not legacy:
        return None
    if not await _legacy_staff_matches_teacher(db, legacy, str(assignment.get("teacher_id") or "")):
        return None
    return legacy


def _date_bounds(academic_year: int, start: Optional[str], end: Optional[str], valid_until: Optional[str]):
    lower = max(str(start or f"{academic_year}-01-01")[:10], f"{academic_year}-01-01")
    upper = min(str(end or f"{academic_year}-12-31")[:10], f"{academic_year}-12-31")
    if valid_until:
        upper = min(upper, str(valid_until)[:10])
    return lower, upper


async def _combined_class_daily_docs(
    db,
    context: AttendanceAssignmentContext,
    academic_year: int,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Optional[list[dict]]:
    """Combina histórico legado + DVD sem reatribuir documentos legados.

    Retorna None quando o assignment não é um cutover 38G-B validado; o chamador
    deve então usar exatamente o comportamento original da Fase 4.
    """
    legacy_assignment = await _safe_cutover_legacy_assignment(db, context, academic_year)
    if not legacy_assignment:
        return None

    lower, upper = _date_bounds(
        academic_year,
        start,
        end,
        context.assignment.get("valid_until"),
    )
    if lower > upper:
        return []

    class_id = context.assignment.get("class_id")
    teacher_id = context.assignment.get("teacher_id")
    date_query = {"$gte": lower, "$lte": upper}

    # Documentos DVD class_daily de qualquer componente REGULAR do mesmo
    # professor são a mesma frequência oficial da turma. A autoria/proveniência
    # armazenada permanece intocada; aqui ocorre apenas leitura consolidada.
    canonical = await db.attendance.find(
        {
            "class_id": class_id,
            "date": date_query,
            "course_id": None,
            "teacher_id": teacher_id,
            "attendance_mode": AttendanceMode.CLASS_DAILY.value,
            "attendance_purpose": AttendancePurpose.OFFICIAL.value,
        },
        {"_id": 0},
    ).to_list(5000)

    # Histórico anterior à Fase 4 não possui assignment_id. Ele continua físico
    # e imutável em `attendance`; a ponte apenas o apresenta na leitura anual.
    legacy = await db.attendance.find(
        {
            "class_id": class_id,
            "date": date_query,
            "course_id": None,
            "$or": [
                {"assignment_id": None},
                {"assignment_id": {"$exists": False}},
            ],
        },
        {"_id": 0},
    ).to_list(5000)

    # Para class_daily a chave oficial é turma+data(+period). Se existir versão
    # DVD e legado na mesma data, a versão DVD prevalece apenas na LEITURA para
    # evitar dupla contagem; nenhum documento é removido ou atualizado.
    merged: dict[tuple[str, str], dict] = {}
    for doc in legacy:
        item = dict(doc)
        item["legacy_history"] = True
        item["read_only"] = True
        item["history_source"] = "attendance_legacy"
        key = (str(item.get("date") or "")[:10], str(item.get("period") or "regular"))
        merged[key] = item
    for doc in canonical:
        item = dict(doc)
        item["legacy_history"] = False
        item["read_only"] = False
        item["history_source"] = "attendance_dvd"
        key = (str(item.get("date") or "")[:10], str(item.get("period") or "regular"))
        merged[key] = item

    out = list(merged.values())
    out.sort(key=lambda doc: (str(doc.get("date") or ""), int(doc.get("aula_numero") or 0)))
    return out


async def _legacy_professor_has_class(db, user: Mapping[str, Any], class_id: str, academic_year: int) -> bool:
    staff = await db.staff.find_one(
        {"user_id": user.get("id")},
        {"_id": 0, "id": 1},
    )
    if not staff and user.get("email"):
        staff = await db.staff.find_one(
            {"email": {"$regex": f"^{re.escape(str(user.get('email')))}$", "$options": "i"}},
            {"_id": 0, "id": 1},
        )
    if not staff:
        return False
    return bool(await db.teacher_assignments.find_one(
        {
            "staff_id": staff.get("id"),
            "class_id": class_id,
            "status": "ativo",
            "academic_year": {"$in": [academic_year, str(academic_year)]},
        },
        {"_id": 0, "id": 1},
    ))


async def _professor_has_dvd_year(db, user: Mapping[str, Any], class_id: str, academic_year: int) -> bool:
    if user.get("role") != "professor" or not user.get("id"):
        return False
    return bool(await db.teacher_class_assignments.find_one(
        {
            "teacher_id": user.get("id"),
            "class_id": class_id,
            "deleted": {"$ne": True},
            "diary_settings.enabled": True,
            "valid_from": {"$lte": f"{academic_year}-12-31"},
            "$or": [
                {"valid_until": None},
                {"valid_until": {"$gte": f"{academic_year}-01-01"}},
            ],
        },
        {"_id": 0, "id": 1},
    ))


def install_attendance_tabs_dvd_adapter(base_router, db, audit_service=None, sandbox_db=None):
    """Instala paridade das abas após o adaptador DVD Fase 4."""
    if getattr(base_router, "_dvd_tabs_parity_installed", False):
        return base_router

    from routers import attendance_dvd as dvd_mod

    # ------------------------------------------------------------
    # 1. Fonte consolidada de histórico para Registros/Relatório/PDF/Alertas.
    # ------------------------------------------------------------
    if not hasattr(dvd_mod, "_tabs_parity_original_assignment_docs"):
        dvd_mod._tabs_parity_original_assignment_docs = dvd_mod._assignment_docs
        original_assignment_docs = dvd_mod._assignment_docs

        async def assignment_docs_with_cutover_history(
            db_arg,
            context: AttendanceAssignmentContext,
            academic_year: int,
            *,
            start: str = None,
            end: str = None,
        ) -> list[dict]:
            combined = await _combined_class_daily_docs(
                db_arg,
                context,
                academic_year,
                start=start,
                end=end,
            )
            if combined is not None:
                return combined
            return await original_assignment_docs(
                db_arg,
                context,
                academic_year,
                start=start,
                end=end,
            )

        dvd_mod._assignment_docs = assignment_docs_with_cutover_history

    if not hasattr(dvd_mod, "_tabs_parity_original_expected_sessions"):
        dvd_mod._tabs_parity_original_expected_sessions = dvd_mod._expected_sessions
        original_expected_sessions = dvd_mod._expected_sessions

        async def expected_sessions_with_cutover_history(
            db_arg,
            context: AttendanceAssignmentContext,
            *,
            start: str,
            end: str,
            academic_year: int,
        ) -> int:
            legacy_assignment = await _safe_cutover_legacy_assignment(db_arg, context, academic_year)
            if not legacy_assignment:
                return await original_expected_sessions(
                    db_arg,
                    context,
                    start=start,
                    end=end,
                    academic_year=academic_year,
                )

            # O `valid_from=18/08` do lote 38G-B é a fronteira técnica do novo
            # armazenamento, não o início da lotação docente legada. Para o
            # calendário anual, a origem validada autoriza contabilizar o ano.
            assignment = dict(context.assignment)
            assignment["valid_from"] = f"{academic_year}-01-01"
            historical_context = replace(context, assignment=assignment)
            return await original_expected_sessions(
                db_arg,
                historical_context,
                start=start,
                end=end,
                academic_year=academic_year,
            )

        dvd_mod._expected_sessions = expected_sessions_with_cutover_history

    # ------------------------------------------------------------
    # 2. Mesmo professor, vários componentes regular: a frequência class_daily
    #    é única. Se outro assignment do MESMO professor já é o proprietário,
    #    reutiliza esse owner sem reatribuir o documento.
    # ------------------------------------------------------------
    original_save_dvd = _remove_route(base_router, "/attendance/dvd", "POST")
    if original_save_dvd is not None:
        @base_router.post("/dvd")
        async def save_dvd_with_same_teacher_owner(payload: dvd_mod.DvdAttendanceCreate, request: Request):
            try:
                return await original_save_dvd(payload, request)
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                if detail.get("code") != "CLASS_DAILY_ALREADY_OWNED":
                    raise

                user = await AuthMiddleware.get_current_user(request)
                current_db = _db_for_user(db, sandbox_db, user)
                try:
                    context = await resolve_attendance_assignment(
                        current_db,
                        user,
                        payload.assignment_id,
                        on_date=payload.date,
                        active_mantenedora_id=get_mantenedora_scope(user, request),
                    )
                except AttendanceAssignmentScopeError as scope_exc:
                    raise _scope_http_error(scope_exc) from scope_exc

                if (
                    context.attendance_mode is not AttendanceMode.CLASS_DAILY
                    or context.attendance_purpose is not AttendancePurpose.OFFICIAL
                ):
                    raise

                query: dict[str, Any] = {
                    "class_id": context.assignment.get("class_id"),
                    "date": payload.date,
                    "course_id": None,
                }
                if payload.period != "regular":
                    query["period"] = payload.period
                existing = await current_db.attendance.find_one(query, {"_id": 0})
                owner_assignment_id = (existing or {}).get("assignment_id")
                if (
                    not existing
                    or not owner_assignment_id
                    or str(existing.get("teacher_id") or "") != str(context.assignment.get("teacher_id") or "")
                ):
                    raise

                owner = await current_db.teacher_class_assignments.find_one(
                    {
                        "id": owner_assignment_id,
                        "teacher_id": context.assignment.get("teacher_id"),
                        "class_id": context.assignment.get("class_id"),
                        "deleted": {"$ne": True},
                        "diary_settings.enabled": True,
                        "diary_settings.profile": "regular",
                    },
                    {"_id": 0, "id": 1},
                )
                if not owner:
                    raise

                raw = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
                raw["assignment_id"] = owner_assignment_id
                owner_payload = dvd_mod.DvdAttendanceCreate(**raw)
                return await original_save_dvd(owner_payload, request)

    # ------------------------------------------------------------
    # 3. Informações dos Estudantes: assignment-aware e fail-closed.
    # ------------------------------------------------------------
    legacy_info = _remove_route(base_router, "/attendance/class-students-info/{class_id}", "GET")
    if legacy_info is not None:
        @base_router.get("/class-students-info/{class_id}")
        async def dvd_aware_class_students_info(
            class_id: str,
            request: Request,
            academic_year: Optional[int] = None,
            assignment_id: Optional[str] = None,
        ):
            user = await AuthMiddleware.get_current_user(request)
            current_db = _db_for_user(db, sandbox_db, user)
            year = academic_year or __import__("datetime").datetime.now().year

            if assignment_id:
                assignment = await current_db.teacher_class_assignments.find_one(
                    {"id": assignment_id},
                    {"_id": 0, "valid_from": 1},
                )
                if not assignment:
                    raise HTTPException(status_code=404, detail="Vínculo docente não encontrado")
                ref = max(str(assignment.get("valid_from") or f"{year}-01-01")[:10], f"{year}-01-01")
                try:
                    context = await resolve_attendance_assignment(
                        current_db,
                        user,
                        assignment_id,
                        class_id=class_id,
                        on_date=ref,
                        active_mantenedora_id=get_mantenedora_scope(user, request),
                    )
                except AttendanceAssignmentScopeError as exc:
                    raise _scope_http_error(exc) from exc

                roster = await build_attendance_roster(
                    current_db,
                    class_id=context.assignment.get("class_id"),
                    academic_year=context.class_info.get("academic_year") or year,
                    course_id=context.effective_course_id,
                    tenant_id=context.snapshot.get("mantenedora_id"),
                )
                roster_ids = [row.get("id") for row in roster if row.get("id")]
                student_docs = await current_db.students.find(
                    {"id": {"$in": roster_ids}},
                    {
                        "_id": 0,
                        "id": 1,
                        "full_name": 1,
                        "birth_date": 1,
                        "mother_name": 1,
                        "mother_phone": 1,
                    },
                ).to_list(1000) if roster_ids else []
                by_id = {row.get("id"): row for row in student_docs if row.get("id")}
                students = [by_id[sid] for sid in roster_ids if sid in by_id]
                return {
                    "assignment_id": assignment_id,
                    "class_id": class_id,
                    "students": students,
                    "total": len(students),
                }

            if user.get("role") == "professor":
                if await _professor_has_dvd_year(current_db, user, class_id, year):
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "DVD_ASSIGNMENT_REQUIRED",
                            "message": "Informações da turma DVD devem ser abertas pelo vínculo docente.",
                        },
                    )
                if not await _legacy_professor_has_class(current_db, user, class_id, year):
                    raise HTTPException(status_code=403, detail="Você não tem acesso a esta turma")

            return await legacy_info(class_id, request, academic_year)

    base_router._dvd_tabs_parity_installed = True
    return base_router
