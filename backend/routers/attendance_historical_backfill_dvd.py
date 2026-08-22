"""P0 — paridade histórica da Frequência após o cutover DVD.

Problema observado em produção:
- vínculo DVD regular criado/ativado no cutover em 18/08/2026;
- professor precisa lançar frequência em uma data pedagógica anterior, por
  exemplo 01/06/2026;
- o autorizador vivo rejeita corretamente a data como anterior ao ``valid_from``.

Esta camada NÃO retrodata o vínculo e NÃO abre uma exceção genérica de vigência.
O backfill só é liberado quando o próprio vínculo possui proveniência 38G-B
selada e a ``teacher_assignment`` legada de origem continua validando professor,
turma, componente, ano e status pelo guard existente da paridade das abas.

Para ``class_daily`` oficial:
- registro novo anterior ao cutover continua sendo criado pelo motor DVD normal,
  com snapshot e ``assignment_id``;
- registro legado já existente pode ser atualizado pelo professor autorizado,
  mas NÃO recebe ``assignment_id`` retroativamente e preserva sua proveniência;
- exclusão de legado continua bloqueada pelo contrato atual.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any, Mapping, Optional

from fastapi import HTTPException

from services.attendance_assignment_roster import build_attendance_roster
from services.attendance_assignment_scope import (
    AttendanceAssignmentContext,
    AttendanceAssignmentScopeError,
)
from services.diary_assignment_contract import AttendanceMode, AttendancePurpose
from tenant_scope import get_mantenedora_scope


HISTORICAL_BACKFILL_FLAG = "historical_backfill"
HISTORICAL_BACKFILL_SOURCE = "cutover_38g_b_legacy_assignment"


def _is_historical_class_daily(context: AttendanceAssignmentContext) -> bool:
    return bool(
        context.snapshot.get(HISTORICAL_BACKFILL_FLAG) is True
        and context.attendance_mode is AttendanceMode.CLASS_DAILY
        and context.attendance_purpose is AttendancePurpose.OFFICIAL
    )


def _reference_date(raw: Optional[str]) -> str:
    value = str(raw or date.today().isoformat())[:10]
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise AttendanceAssignmentScopeError(
            "INVALID_ATTENDANCE_DATE",
            "Data da frequência deve usar YYYY-MM-DD.",
        ) from exc


def _build_historical_resolver(base_resolver, tabs_mod):
    async def resolve_attendance_assignment_with_historical_backfill(
        db,
        current_user: Mapping[str, Any],
        assignment_id: str,
        *,
        class_id: Optional[str] = None,
        on_date: Optional[str] = None,
        active_mantenedora_id: Optional[str] = None,
    ) -> AttendanceAssignmentContext:
        reference_date = _reference_date(on_date)
        try:
            return await base_resolver(
                db,
                current_user,
                assignment_id,
                class_id=class_id,
                on_date=reference_date,
                active_mantenedora_id=active_mantenedora_id,
            )
        except AttendanceAssignmentScopeError as exc:
            if exc.code != "ASSIGNMENT_NOT_ACTIVE":
                raise
            inactive_error = exc

        assignment = await db.teacher_class_assignments.find_one(
            {"id": assignment_id, "deleted": False},
            {"_id": 0},
        )
        if not assignment:
            raise inactive_error

        valid_from = str(assignment.get("valid_from") or "")[:10]
        # A exceção é estritamente retroativa. Vínculo expirado depois de
        # valid_until continua falhando fechado no autorizador original.
        if not valid_from or reference_date >= valid_from:
            raise inactive_error

        try:
            live_context = await base_resolver(
                db,
                current_user,
                assignment_id,
                class_id=class_id,
                on_date=valid_from,
                active_mantenedora_id=active_mantenedora_id,
            )
        except AttendanceAssignmentScopeError:
            # Se nem na data inicial o vínculo é autorizável, não há base para
            # backfill. Preserve o erro específico de segurança/capability.
            raise

        academic_year = date.fromisoformat(reference_date).year
        legacy_assignment = await tabs_mod._safe_cutover_legacy_assignment(
            db,
            live_context,
            academic_year,
        )
        if not legacy_assignment:
            raise inactive_error

        snapshot = dict(live_context.snapshot)
        snapshot.update({
            HISTORICAL_BACKFILL_FLAG: True,
            "historical_backfill_date": reference_date,
            "historical_backfill_authorized_from": valid_from,
            "historical_backfill_source": HISTORICAL_BACKFILL_SOURCE,
            "historical_backfill_source_legacy_assignment_id": legacy_assignment.get("id"),
        })
        return replace(live_context, snapshot=snapshot)

    return resolve_attendance_assignment_with_historical_backfill


async def _read_legacy_historical_day(
    dvd_mod,
    db,
    user,
    request,
    *,
    context: AttendanceAssignmentContext,
    assignment_id: str,
    on_date: str,
    period: str,
    attendance: Mapping[str, Any],
) -> dict:
    """Projeta um attendance legado no lançamento DVD sem reatribuir autoria."""
    roster = await build_attendance_roster(
        db,
        class_id=context.assignment.get("class_id"),
        academic_year=context.class_info.get("academic_year") or int(on_date[:4]),
        course_id=context.effective_course_id,
        tenant_id=context.snapshot.get("mantenedora_id"),
    )
    records_map = {
        row.get("student_id"): row.get("status")
        for row in attendance.get("records", [])
    }
    dependency_map = {
        row.get("student_id"): row.get("dependency_id")
        for row in attendance.get("records", [])
        if row.get("dependency_id")
    }
    for student in roster:
        student["status"] = records_map.get(student.get("id"))
        if dependency_map.get(student.get("id")):
            student["dependency_id"] = dependency_map[student.get("id")]
            student["is_dependency"] = True

    return {
        "assignment_id": assignment_id,
        "class_id": context.assignment.get("class_id"),
        "class_name": context.class_info.get("name") or context.assignment.get("class_name"),
        "school_id": context.snapshot.get("school_id"),
        "component_id": context.effective_course_id,
        "teacher_id": context.snapshot.get("teacher_id"),
        "teacher_name": context.snapshot.get("teacher_name"),
        "profile": context.profile.value,
        "student_scope": context.student_scope.value,
        "attendance_mode": context.attendance_mode.value,
        "attendance_purpose": context.attendance_purpose.value,
        "attendance_required": context.profile.value != "integrator",
        "documentary_only": False,
        "session_slots": [],
        "academic_year": context.class_info.get("academic_year"),
        HISTORICAL_BACKFILL_FLAG: True,
        "legacy_historical_record": True,
        "date": on_date,
        "period": period,
        "aula_numero": None,
        "session_selection_required": False,
        "attendance_id": attendance.get("id"),
        "observations": attendance.get("observations"),
        "version": attendance.get("version") or 1,
        "number_of_classes": attendance.get("number_of_classes", 1),
        "total_sessions": 1,
        "sessions": [{
            "id": attendance.get("id"),
            "aula_numero": None,
            "number_of_classes": attendance.get("number_of_classes", 1),
            "observations": attendance.get("observations"),
            "records": records_map,
        }],
        "students": roster,
    }


async def _update_legacy_historical_day(
    dvd_mod,
    db,
    user: dict,
    request,
    payload,
    audit_service,
    *,
    context: AttendanceAssignmentContext,
    existing: Mapping[str, Any],
) -> dict:
    """Atualiza legado autorizado sem escrever ``assignment_id`` no documento."""
    records_data = await dvd_mod._validate_records_for_context(
        db,
        user,
        request,
        context,
        payload,
    )

    current_version = existing.get("version") or 1
    if payload.expected_version is not None and payload.expected_version != current_version:
        if not payload.force_overwrite:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ATTENDANCE_VERSION_CONFLICT",
                    "message": (
                        "Esta frequência foi alterada desde o carregamento. "
                        "Recarregue ou sobrescreva com justificativa."
                    ),
                    "expected_version": payload.expected_version,
                    "current_version": current_version,
                    "attendance_id": existing.get("id"),
                },
            )
        if not (payload.change_note and payload.change_note.strip()):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "OVERWRITE_REQUIRES_NOTE",
                    "message": "Sobrescrita após conflito requer change_note obrigatório.",
                },
            )

    from routers.attendance import _block_if_changing_migrated_attendance

    records_data, _ = _block_if_changing_migrated_attendance(
        existing.get("records") or [],
        records_data,
        user,
    )

    new_version = current_version + 1
    now = datetime.now(timezone.utc).isoformat()
    # Deliberadamente NÃO adiciona assignment_id, teacher_id, attendance_mode ou
    # outros snapshots ao documento legado. A prova do vínculo fica na auditoria.
    update_data = {
        "records": records_data,
        "observations": payload.observations,
        "updated_by": user["id"],
        "updated_at": now,
        "version": new_version,
        "historical_backfill_last_authorized_assignment_id": payload.assignment_id,
        "historical_backfill_last_authorized_at": now,
    }
    await db.attendance.update_one(
        {"id": existing["id"]},
        {"$set": update_data},
    )
    updated = await db.attendance.find_one({"id": existing["id"]}, {"_id": 0})

    from services.attendance_audit_diary import build_diary_audit_extra, diff_records

    per_student = diff_records(existing.get("records") or [], records_data)
    change_kind = (
        "overwrite_after_conflict"
        if payload.expected_version is not None
        and payload.expected_version != current_version
        else "historical_backfill_update"
    )
    extra = await build_diary_audit_extra(
        db=db,
        attendance_doc=updated,
        class_info={
            "name": context.class_info.get("name") or context.assignment.get("class_name"),
            "school_id": context.snapshot.get("school_id"),
        },
        per_student_changes=per_student,
        change_kind=change_kind,
        expected_version=payload.expected_version,
        final_version=new_version,
        change_note=(
            payload.change_note
            if change_kind == "overwrite_after_conflict"
            else None
        ),
    )
    extra.update({
        "assignment_id": payload.assignment_id,
        HISTORICAL_BACKFILL_FLAG: True,
        "historical_backfill_source": HISTORICAL_BACKFILL_SOURCE,
        "historical_backfill_source_legacy_assignment_id": context.snapshot.get(
            "historical_backfill_source_legacy_assignment_id"
        ),
        "legacy_document_preserved_without_assignment_id": True,
    })
    await audit_service.log(
        action="update",
        collection="attendance",
        user=user,
        request=request,
        document_id=existing["id"],
        description=(
            f"Atualizou frequência histórica pré-cutover via vínculo "
            f"{payload.assignment_id} em {payload.date} "
            f"({len(per_student)} estudante(s) alterado(s))"
        ),
        old_value={"records": existing.get("records") or [], "version": current_version},
        new_value={"records": records_data, "version": new_version},
        school_id=context.snapshot.get("school_id"),
        academic_year=updated.get("academic_year") if updated else None,
        extra_data=extra,
    )
    return updated


def install_attendance_historical_backfill_dvd(
    base_router,
    db,
    audit_service,
    sandbox_db=None,
):
    """Instala a exceção histórica somente após Fase 4 + paridade das abas."""
    from routers import attendance_dvd as dvd_mod
    from routers import attendance_tabs_dvd as tabs_mod

    if getattr(dvd_mod, "_historical_backfill_p0_installed", False):
        return base_router

    base_resolver = dvd_mod.resolve_attendance_assignment
    historical_resolver = _build_historical_resolver(base_resolver, tabs_mod)
    dvd_mod.resolve_attendance_assignment = historical_resolver
    # attendance_tabs_dvd importou a função por nome durante import; atualiza o
    # alias local para que Informações/owner fallback usem a mesma política.
    tabs_mod.resolve_attendance_assignment = historical_resolver

    original_context_payload = dvd_mod._dvd_context_payload

    async def context_payload_with_history(db_arg, user, request, assignment_id: str, on_date: str):
        context, meta = await original_context_payload(
            db_arg,
            user,
            request,
            assignment_id,
            on_date,
        )
        if context.snapshot.get(HISTORICAL_BACKFILL_FLAG) is True:
            meta = {
                **meta,
                HISTORICAL_BACKFILL_FLAG: True,
                "assignment_valid_from": context.assignment.get("valid_from"),
                "historical_backfill_source": context.snapshot.get("historical_backfill_source"),
            }
        return context, meta

    dvd_mod._dvd_context_payload = context_payload_with_history

    original_get = dvd_mod._get_dvd_attendance

    async def get_with_historical_backfill(
        db_arg,
        user,
        request,
        *,
        assignment_id: str,
        on_date: str,
        aula_numero: Optional[int],
        period: str,
    ) -> dict:
        try:
            context = await historical_resolver(
                db_arg,
                user,
                assignment_id,
                on_date=on_date,
                active_mantenedora_id=get_mantenedora_scope(user, request),
            )
        except AttendanceAssignmentScopeError as exc:
            raise dvd_mod._http_scope_error(exc) from exc

        if not _is_historical_class_daily(context):
            return await original_get(
                db_arg,
                user,
                request,
                assignment_id=assignment_id,
                on_date=on_date,
                aula_numero=aula_numero,
                period=period,
            )

        query = dvd_mod.logical_attendance_query(
            context,
            on_date=on_date,
            aula_numero=None,
            period=period,
        )
        attendance = await db_arg.attendance.find_one(query, {"_id": 0})
        if not attendance or attendance.get("assignment_id"):
            return await original_get(
                db_arg,
                user,
                request,
                assignment_id=assignment_id,
                on_date=on_date,
                aula_numero=aula_numero,
                period=period,
            )

        return await _read_legacy_historical_day(
            dvd_mod,
            db_arg,
            user,
            request,
            context=context,
            assignment_id=assignment_id,
            on_date=on_date,
            period=period,
            attendance=attendance,
        )

    dvd_mod._get_dvd_attendance = get_with_historical_backfill

    original_save = dvd_mod._save_dvd_attendance

    async def save_with_historical_backfill(db_arg, user, request, payload, audit_service_arg):
        try:
            context = await historical_resolver(
                db_arg,
                user,
                payload.assignment_id,
                on_date=payload.date,
                active_mantenedora_id=get_mantenedora_scope(user, request),
            )
        except AttendanceAssignmentScopeError as exc:
            raise dvd_mod._http_scope_error(exc) from exc

        if _is_historical_class_daily(context):
            query = dvd_mod.logical_attendance_query(
                context,
                on_date=payload.date,
                aula_numero=None,
                period=payload.period,
            )
            existing = await db_arg.attendance.find_one(query, {"_id": 0})
            if existing and not existing.get("assignment_id"):
                return await _update_legacy_historical_day(
                    dvd_mod,
                    db_arg,
                    user,
                    request,
                    payload,
                    audit_service_arg,
                    context=context,
                    existing=existing,
                )

        # Registro novo ou já canônico continua no motor original. Como o
        # resolver global foi substituído, o novo documento recebe snapshot do
        # backfill sem qualquer alteração em valid_from do assignment.
        return await original_save(db_arg, user, request, payload, audit_service_arg)

    dvd_mod._save_dvd_attendance = save_with_historical_backfill
    dvd_mod._historical_backfill_p0_installed = True
    return base_router
