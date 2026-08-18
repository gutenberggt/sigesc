"""Adaptador da Frequência por Vínculo Docente — DVD Fase 4.

Mantém `Attendance.js` e o router histórico como superfícies canônicas. O modo
DVD é ativado apenas quando há `assignment_id`; sem ele o comportamento legado
permanece, exceto pelo guard anti-bypass do professor em turma DVD habilitada.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Optional
import logging
import uuid

from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth_middleware import AuthMiddleware
from services.attendance_assignment_roster import build_attendance_roster
from services.attendance_assignment_scope import (
    ASSIGNMENT_SESSION_KEY_SCOPE,
    DOCUMENTARY_ATTENDANCE_COLLECTION,
    OFFICIAL_ATTENDANCE_COLLECTION,
    AttendanceAssignmentContext,
    AttendanceAssignmentScopeError,
    attendance_provenance_fields,
    authorize_historical_attendance,
    ensure_attendance_assignment_indexes,
    logical_attendance_query,
    professor_has_active_dvd_for_class,
    resolve_attendance_assignment,
    resolve_session_aula_numero,
)
from services.diary_assignment_contract import AttendanceMode, AttendancePurpose
from tenant_scope import get_mantenedora_scope
from utils.academic_event_lens import record_lock_audit, resolve_student_ownership
from utils.dependency_validator import validate_dependency_link

logger = logging.getLogger(__name__)


class DvdAttendanceRecord(BaseModel):
    student_id: str
    status: str
    dependency_id: Optional[str] = None


class DvdAttendanceCreate(BaseModel):
    assignment_id: str
    date: str
    records: list[DvdAttendanceRecord]
    period: str = "regular"
    observations: Optional[str] = None
    aula_numero: Optional[int] = None
    expected_version: Optional[int] = None
    force_overwrite: bool = False
    change_note: Optional[str] = None


def _http_scope_error(exc: AttendanceAssignmentScopeError) -> HTTPException:
    status_code = 409 if exc.code in {
        "ATTENDANCE_GROUP_SCOPE_UNRESOLVED",
        "ASSIGNMENT_SESSION_SLOT_REQUIRED",
        "ATTENDANCE_LEGACY_CONFLICT_REQUIRES_REVIEW",
        "CLASS_DAILY_ALREADY_OWNED",
        "DVD_ASSIGNMENT_REQUIRED",
    } else 403
    if exc.code.startswith("INVALID_") or exc.code.endswith("_INVALID"):
        status_code = 422
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def _db_for_user(db, sandbox_db, user: dict):
    if user.get("is_sandbox"):
        return sandbox_db if sandbox_db is not None else db
    return db


def _collection_for_context(db, context: AttendanceAssignmentContext):
    return db[context.storage_collection]


async def _validate_records_for_context(
    db,
    user: dict,
    request: Request,
    context: AttendanceAssignmentContext,
    payload: DvdAttendanceCreate,
) -> list[dict[str, Any]]:
    tenant_id = context.snapshot.get("mantenedora_id")
    class_id = context.assignment.get("class_id")
    course_id = context.effective_course_id
    out = []
    for record in payload.records:
        if record.dependency_id:
            await validate_dependency_link(
                db=db,
                dependency_id=record.dependency_id,
                student_id=record.student_id,
                class_id=class_id,
                course_id=course_id,
                tenant_id=tenant_id,
            )

        ownership = await resolve_student_ownership(
            db,
            student_id=record.student_id,
            class_id=class_id,
            course_id=course_id,
            target_date=payload.date,
            mantenedora_id=tenant_id,
        )
        if not ownership["editable"]:
            await record_lock_audit(
                db,
                event_id=ownership.get("governing_event_id"),
                action="attendance_dvd_create_blocked",
                user_id=user.get("id"),
                role=user.get("role"),
                student_id=record.student_id,
                class_id=class_id,
                target_date=payload.date,
                target_resource="attendance",
                reason_code=ownership["blocked_reason"],
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ACADEMIC_EVENT_LOCK",
                    "reason_code": ownership["blocked_reason"],
                    "event_id": ownership.get("governing_event_id"),
                    "student_id": record.student_id,
                    "effective_date": ownership.get("governing_effective_date"),
                    "message": "Frequência bloqueada por evento acadêmico para este estudante.",
                },
            )
        out.append({
            "student_id": record.student_id,
            "status": record.status,
            **({"dependency_id": record.dependency_id} if record.dependency_id else {}),
        })
    return out


async def _save_dvd_attendance(
    db,
    user: dict,
    request: Request,
    payload: DvdAttendanceCreate,
    audit_service,
) -> dict:
    try:
        context = await resolve_attendance_assignment(
            db,
            user,
            payload.assignment_id,
            on_date=payload.date,
            active_mantenedora_id=get_mantenedora_scope(user, request),
        )
        aula_numero = resolve_session_aula_numero(context, payload.aula_numero)
    except AttendanceAssignmentScopeError as exc:
        raise _http_scope_error(exc) from exc

    collection = _collection_for_context(db, context)
    query = logical_attendance_query(
        context,
        on_date=payload.date,
        aula_numero=aula_numero,
        period=payload.period,
    )
    existing = await collection.find_one(query, {"_id": 0})

    # class_daily preserva a chave única da turma/data. Nunca transforma um
    # registro legado ou de outro vínculo em propriedade do professor atual.
    if context.attendance_mode is AttendanceMode.CLASS_DAILY and existing:
        existing_assignment = existing.get("assignment_id")
        if not existing_assignment:
            raise _http_scope_error(AttendanceAssignmentScopeError(
                "ATTENDANCE_LEGACY_CONFLICT_REQUIRES_REVIEW",
                "Já existe frequência legada nesta turma/data. O registro não será atribuído automaticamente ao vínculo; a gestão deve reconciliar o histórico.",
            ))
        if existing_assignment != payload.assignment_id:
            raise _http_scope_error(AttendanceAssignmentScopeError(
                "CLASS_DAILY_ALREADY_OWNED",
                "A frequência canônica desta turma/data já pertence a outro vínculo docente.",
            ))

    records_data = await _validate_records_for_context(db, user, request, context, payload)

    if existing:
        try:
            await authorize_historical_attendance(
                db,
                user,
                existing,
                action="attendance",
                active_mantenedora_id=get_mantenedora_scope(user, request),
            )
        except AttendanceAssignmentScopeError as exc:
            raise _http_scope_error(exc) from exc

        current_version = existing.get("version") or 1
        if payload.expected_version is not None and payload.expected_version != current_version:
            if not payload.force_overwrite:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "ATTENDANCE_VERSION_CONFLICT",
                        "message": "Esta frequência foi alterada desde o carregamento. Recarregue ou sobrescreva com justificativa.",
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

        # Preserva metadados de frequência migrada por estudante, igual ao motor
        # histórico, sem alterar a autoria pedagógica do assignment.
        from routers.attendance import _block_if_changing_migrated_attendance
        records_data, _ = _block_if_changing_migrated_attendance(
            existing.get("records") or [], records_data, user
        )

        new_version = current_version + 1
        now = datetime.now(timezone.utc).isoformat()
        await collection.update_one(
            {"id": existing["id"]},
            {"$set": {
                "records": records_data,
                "observations": payload.observations,
                "updated_by": user["id"],
                "updated_at": now,
                "version": new_version,
            }},
        )
        updated = await collection.find_one({"id": existing["id"]}, {"_id": 0})
        change_kind = (
            "overwrite_after_conflict"
            if payload.expected_version is not None
            and payload.expected_version != current_version
            else "update"
        )
        from services.attendance_audit_diary import build_diary_audit_extra, diff_records
        per_student = diff_records(existing.get("records") or [], records_data)
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
            change_note=payload.change_note if change_kind == "overwrite_after_conflict" else None,
        )
        extra.update({
            "assignment_id": payload.assignment_id,
            "attendance_mode": context.attendance_mode.value,
            "attendance_purpose": context.attendance_purpose.value,
        })
        await audit_service.log(
            action="update",
            collection=context.storage_collection,
            user=user,
            request=request,
            document_id=existing["id"],
            description=(
                f"Atualizou frequência DVD do vínculo {payload.assignment_id} "
                f"em {payload.date} ({len(per_student)} estudante(s) alterado(s))"
            ),
            old_value={"records": existing.get("records") or [], "version": current_version},
            new_value={"records": records_data, "version": new_version},
            school_id=context.snapshot.get("school_id"),
            academic_year=updated.get("academic_year") if updated else None,
            extra_data=extra,
        )
        return updated

    now = datetime.now(timezone.utc).isoformat()
    provenance = attendance_provenance_fields(context, aula_numero=aula_numero)
    new_doc = {
        "id": str(uuid.uuid4()),
        **provenance,
        "date": payload.date,
        "period": payload.period,
        "attendance_type": (
            "daily" if context.attendance_mode is AttendanceMode.CLASS_DAILY else "by_course"
        ),
        "records": records_data,
        "observations": payload.observations,
        "number_of_classes": 1,
        "academic_year": context.class_info.get("academic_year") or int(payload.date[:4]),
        "created_by": user["id"],
        "created_at": now,
        "version": 1,
    }
    await collection.insert_one(new_doc)

    from services.attendance_audit_diary import build_diary_audit_extra
    extra = await build_diary_audit_extra(
        db=db,
        attendance_doc=new_doc,
        class_info={
            "name": context.class_info.get("name") or context.assignment.get("class_name"),
            "school_id": context.snapshot.get("school_id"),
        },
        per_student_changes=[
            {"student_id": row["student_id"], "previous_status": None, "new_status": row.get("status")}
            for row in records_data
        ],
        change_kind="create",
        expected_version=None,
        final_version=1,
    )
    extra.update({
        "assignment_id": payload.assignment_id,
        "attendance_mode": context.attendance_mode.value,
        "attendance_purpose": context.attendance_purpose.value,
    })
    await audit_service.log(
        action="create",
        collection=context.storage_collection,
        user=user,
        request=request,
        document_id=new_doc["id"],
        description=f"Lançou frequência DVD do vínculo {payload.assignment_id} em {payload.date}",
        school_id=context.snapshot.get("school_id"),
        academic_year=new_doc.get("academic_year"),
        extra_data=extra,
    )
    return await collection.find_one({"id": new_doc["id"]}, {"_id": 0})


async def _dvd_context_payload(db, user, request, assignment_id: str, on_date: str) -> tuple[AttendanceAssignmentContext, dict]:
    try:
        context = await resolve_attendance_assignment(
            db,
            user,
            assignment_id,
            on_date=on_date,
            active_mantenedora_id=get_mantenedora_scope(user, request),
        )
    except AttendanceAssignmentScopeError as exc:
        raise _http_scope_error(exc) from exc
    return context, {
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
        "documentary_only": context.attendance_purpose is AttendancePurpose.PDF_ONLY,
        "session_slots": list(context.session_slots),
        "academic_year": context.class_info.get("academic_year"),
    }


async def _get_dvd_attendance(
    db,
    user,
    request,
    *,
    assignment_id: str,
    on_date: str,
    aula_numero: Optional[int],
    period: str,
) -> dict:
    context, meta = await _dvd_context_payload(db, user, request, assignment_id, on_date)
    try:
        resolved_aula = resolve_session_aula_numero(context, aula_numero)
    except AttendanceAssignmentScopeError as exc:
        if exc.code == "ASSIGNMENT_SESSION_SLOT_REQUIRED":
            return {
                **meta,
                "date": on_date,
                "session_selection_required": True,
                "attendance_id": None,
                "students": [],
                "sessions": [],
            }
        raise _http_scope_error(exc) from exc

    collection = _collection_for_context(db, context)
    query = logical_attendance_query(
        context,
        on_date=on_date,
        aula_numero=resolved_aula,
        period=period,
    )
    attendance = await collection.find_one(query, {"_id": 0})
    if attendance:
        try:
            await authorize_historical_attendance(
                db,
                user,
                attendance,
                action="attendance",
                active_mantenedora_id=get_mantenedora_scope(user, request),
            )
        except AttendanceAssignmentScopeError as exc:
            raise _http_scope_error(exc) from exc

    roster = await build_attendance_roster(
        db,
        class_id=context.assignment.get("class_id"),
        academic_year=context.class_info.get("academic_year") or int(on_date[:4]),
        course_id=context.effective_course_id,
        tenant_id=context.snapshot.get("mantenedora_id"),
    )
    records_map = {
        row.get("student_id"): row.get("status")
        for row in (attendance or {}).get("records", [])
    }
    dependency_map = {
        row.get("student_id"): row.get("dependency_id")
        for row in (attendance or {}).get("records", [])
        if row.get("dependency_id")
    }
    for student in roster:
        student["status"] = records_map.get(student.get("id"))
        if dependency_map.get(student.get("id")):
            student["dependency_id"] = dependency_map[student.get("id")]
            student["is_dependency"] = True

    return {
        **meta,
        "date": on_date,
        "period": period,
        "aula_numero": resolved_aula,
        "session_selection_required": False,
        "attendance_id": (attendance or {}).get("id"),
        "observations": (attendance or {}).get("observations"),
        "version": (attendance or {}).get("version"),
        "number_of_classes": 1,
        "total_sessions": 1 if attendance else 0,
        "sessions": ([{
            "id": attendance.get("id"),
            "aula_numero": resolved_aula,
            "number_of_classes": 1,
            "observations": attendance.get("observations"),
            "records": records_map,
        }] if attendance else []),
        "students": roster,
    }


async def _assignment_docs(db, context: AttendanceAssignmentContext, academic_year: int, *, start: str = None, end: str = None) -> list[dict]:
    collection = _collection_for_context(db, context)
    query: dict[str, Any] = {
        "assignment_id": context.assignment.get("id"),
        "academic_year": academic_year,
    }
    if start and end:
        query["date"] = {"$gte": start, "$lte": end}
    return await collection.find(query, {"_id": 0}).sort([("date", 1), ("aula_numero", 1)]).to_list(5000)


async def _calendar_periods(db, academic_year: int) -> list[tuple[int, str, str]]:
    calendar = await db.calendario_letivo.find_one(
        {"ano_letivo": academic_year, "school_id": None}, {"_id": 0}
    ) or await db.calendario_letivo.find_one({"ano_letivo": academic_year}, {"_id": 0})
    fallback = {
        1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
        2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
        3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
        4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
    }
    out = []
    for bim in range(1, 5):
        start = str((calendar or {}).get(f"bimestre_{bim}_inicio") or fallback[bim][0])[:10]
        end = str((calendar or {}).get(f"bimestre_{bim}_fim") or fallback[bim][1])[:10]
        out.append((bim, start, end))
    return out


async def _calendar_day_sets(db, academic_year: int, tenant_id: Optional[str]) -> tuple[set[str], dict[str, int]]:
    event_query: dict[str, Any] = {"academic_year": academic_year}
    if tenant_id:
        # Coleções legadas podem não possuir mantenedora_id; não força o campo.
        pass
    events = await db.calendar_events.find(event_query, {"_id": 0}).to_list(2000)
    blocked: set[str] = set()
    saturday_school: set[str] = set()
    for event in events:
        start = str(event.get("start_date") or "")[:10]
        end = str(event.get("end_date") or start)[:10]
        if not start:
            continue
        try:
            cursor = datetime.strptime(start, "%Y-%m-%d").date()
            final = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            continue
        while cursor <= final:
            ds = cursor.isoformat()
            event_type = event.get("event_type", "")
            if event_type == "sabado_letivo" or (event.get("is_school_day") and cursor.weekday() == 5):
                saturday_school.add(ds)
            if (
                "feriado" in event_type
                or event_type == "recesso_escolar"
                or event.get("is_school_day") is False
            ):
                blocked.add(ds)
            cursor += timedelta(days=1)

    from services.school_calendar_helper import get_saturday_weekday_map
    saturday_map = await get_saturday_weekday_map(
        db, academic_year=academic_year, mantenedora_id=tenant_id
    )
    # O mapa oficial é a fonte de verdade para rotação de sábado; eventos são
    # mantidos como fallback de identificação de sábado letivo.
    for ds in saturday_school:
        saturday_map.setdefault(ds, 1)
    return blocked, saturday_map


async def _expected_sessions(
    db,
    context: AttendanceAssignmentContext,
    *,
    start: str,
    end: str,
    academic_year: int,
) -> int:
    blocked, saturday_map = await _calendar_day_sets(
        db, academic_year, context.snapshot.get("mantenedora_id")
    )
    valid_from = context.assignment.get("valid_from") or start
    valid_until = context.assignment.get("valid_until") or end
    effective_start = max(start, valid_from)
    effective_end = min(end, valid_until)
    try:
        cursor = datetime.strptime(effective_start, "%Y-%m-%d").date()
        final = datetime.strptime(effective_end, "%Y-%m-%d").date()
    except ValueError:
        return 0
    if cursor > final:
        return 0

    total = 0
    slots = context.assignment.get("weekly_slots") or []
    while cursor <= final:
        ds = cursor.isoformat()
        dow = cursor.weekday()  # 0=seg ... 6=dom
        effective_weekday = None
        if dow < 5 and ds not in blocked:
            effective_weekday = dow + 1
        elif dow == 5 and ds in saturday_map and ds not in blocked:
            effective_weekday = saturday_map[ds]

        if effective_weekday is not None:
            if context.attendance_mode is AttendanceMode.CLASS_DAILY:
                total += 1
            else:
                total += sum(1 for slot in slots if slot.get("weekday") == effective_weekday)
        cursor += timedelta(days=1)
    return total


async def _dvd_bimestre_summary(db, user, request, assignment_id: str, academic_year: int) -> list[dict]:
    # Usa uma data dentro da vigência para revalidar o vínculo. Para dashboard
    # corrente, today normalmente basta; se o vínculo é do próprio ano, usa o
    # ponto de interseção com sua validade.
    assignment = await db.teacher_class_assignments.find_one({"id": assignment_id}, {"_id": 0})
    if not assignment:
        raise HTTPException(status_code=404, detail="Vínculo docente não encontrado")
    ref = max(str(assignment.get("valid_from") or f"{academic_year}-01-01")[:10], f"{academic_year}-01-01")
    context, _ = await _dvd_context_payload(db, user, request, assignment_id, ref)
    periods = await _calendar_periods(db, academic_year)
    result = []
    for bim, start, end in periods:
        docs = await _assignment_docs(db, context, academic_year, start=start, end=end)
        previstos = await _expected_sessions(
            db, context, start=start, end=end, academic_year=academic_year
        )
        registrados = len({
            (doc.get("date", "")[:10], doc.get("aula_numero"))
            for doc in docs if doc.get("date")
        })
        optional = context.attendance_purpose is AttendancePurpose.PDF_ONLY
        result.append({
            "bimestre": bim,
            "previstos": previstos,
            "registrados": registrados,
            "restantes": None if optional else max(0, previstos - registrados),
            "optional": optional,
            "documentary_only": optional,
            "label_prev": "SESSÕES PREVISTAS" if context.attendance_mode is AttendanceMode.ASSIGNMENT_SESSION else "DIAS PREVISTOS",
            "label_reg": "SESSÕES REGISTRADAS" if context.attendance_mode is AttendanceMode.ASSIGNMENT_SESSION else "DIAS REGISTRADOS",
            "period_start": start,
            "period_end": end,
        })
    return result


async def _dvd_report(db, user, request, assignment_id: str, academic_year: int, bimestre: Optional[int]) -> dict:
    assignment = await db.teacher_class_assignments.find_one({"id": assignment_id}, {"_id": 0})
    if not assignment:
        raise HTTPException(status_code=404, detail="Vínculo docente não encontrado")
    ref = max(str(assignment.get("valid_from") or f"{academic_year}-01-01")[:10], f"{academic_year}-01-01")
    context, meta = await _dvd_context_payload(db, user, request, assignment_id, ref)
    start = end = None
    if bimestre:
        for bim, p_start, p_end in await _calendar_periods(db, academic_year):
            if bim == bimestre:
                start, end = p_start, p_end
                break
    docs = await _assignment_docs(db, context, academic_year, start=start, end=end)
    roster = await build_attendance_roster(
        db,
        class_id=context.assignment.get("class_id"),
        academic_year=academic_year,
        course_id=context.effective_course_id,
        tenant_id=context.snapshot.get("mantenedora_id"),
    )
    stats = {
        s["id"]: {"present": 0, "absent": 0, "justified": 0, "late": 0, "total": 0}
        for s in roster
    }
    dates = {doc.get("date", "")[:10] for doc in docs if doc.get("date")}
    certs = []
    if stats and dates:
        certs = await db.medical_certificates.find(
            {
                "student_id": {"$in": list(stats)},
                "start_date": {"$lte": max(dates)},
                "end_date": {"$gte": min(dates)},
            },
            {"_id": 0, "student_id": 1, "start_date": 1, "end_date": 1},
        ).to_list(None)
    medical_by_sid: dict[str, set[str]] = {}
    for cert in certs:
        sid = cert.get("student_id")
        medical_by_sid.setdefault(sid, set())
        for ds in dates:
            if str(cert.get("start_date") or "")[:10] <= ds <= str(cert.get("end_date") or "")[:10]:
                medical_by_sid[sid].add(ds)

    for doc in docs:
        ds = doc.get("date", "")[:10]
        for row in doc.get("records") or []:
            sid = row.get("student_id")
            if sid not in stats or row.get("dependency_id"):
                continue
            item = stats[sid]
            item["total"] += 1
            if ds in medical_by_sid.get(sid, set()):
                item["medical"] = item.get("medical", 0) + 1
                continue
            status_value = row.get("status")
            if status_value in ("present", "P"):
                item["present"] += 1
            elif status_value in ("absent", "F", "A"):
                item["absent"] += 1
            elif status_value in ("justified", "J"):
                item["justified"] += 1
            elif status_value in ("late", "L"):
                item["late"] += 1

    report = []
    for student in roster:
        item = stats[student["id"]]
        total = item["total"]
        medical = item.get("medical", 0)
        rate = round((item["present"] + item["justified"] + medical) / total * 100, 1) if total else 0
        report.append({
            "student_id": student["id"],
            "student_name": student.get("full_name"),
            "enrollment_number": student.get("enrollment_number"),
            **item,
            "medical": medical,
            "attendance_percentage": rate,
            "status": "documental" if meta["documentary_only"] else ("regular" if rate >= 75 else "infrequente"),
        })

    return {
        "class": {
            **context.class_info,
            "name": context.class_info.get("name") or context.assignment.get("class_name"),
        },
        **meta,
        "academic_year": academic_year,
        "total_records": len(docs),
        "total_school_days_recorded": len(docs),
        "total_students": len(roster),
        "report_type": "sessoes" if context.attendance_mode is AttendanceMode.ASSIGNMENT_SESSION else "dias",
        "students": report,
    }


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


def _install_sync_adapter(db, audit_service, sandbox_db=None):
    """Torna o sync offline assignment-aware sem duplicar o motor de gravação."""
    import routers.sync as sync_mod

    if getattr(sync_mod, "_dvd_phase4_installed", False):
        return
    original_sync = sync_mod._sync_attendance_canonical
    original_fetch = sync_mod.fetch_collection_data_paginated

    async def dvd_sync(db_arg, user, request, record_id: str, data: dict):
        assignment_id = data.get("assignment_id")
        if not assignment_id:
            return await original_sync(db_arg, user, request, record_id, data)
        try:
            payload = DvdAttendanceCreate(
                assignment_id=assignment_id,
                date=data.get("date"),
                records=[DvdAttendanceRecord(**row) for row in (data.get("records") or [])],
                period=data.get("period") or "regular",
                observations=data.get("observations"),
                aula_numero=data.get("aula_numero"),
                expected_version=data.get("base_version"),
                force_overwrite=True,
                change_note=(
                    f"[Sincronização offline DVD] registrada no dispositivo em "
                    f"{data.get('updated_at') or data.get('timestamp') or ''}"
                ),
            )
            doc = await _save_dvd_attendance(db_arg, user, request, payload, audit_service)
            return sync_mod.SyncPushResult(
                recordId=record_id, success=True, serverId=(doc or {}).get("id")
            )
        except HTTPException as exc:
            detail = exc.detail
            if isinstance(detail, dict):
                detail = detail.get("message") or detail.get("code") or str(detail)
            return sync_mod.SyncPushResult(
                recordId=record_id, success=False, error=f"{exc.status_code}: {detail}"
            )
        except Exception as exc:  # pragma: no cover - defesa de transporte
            logger.exception("Falha no sync DVD de frequência")
            return sync_mod.SyncPushResult(recordId=record_id, success=False, error=str(exc))

    async def dvd_fetch(
        db_arg,
        user,
        collection,
        class_id,
        academic_year,
        last_sync,
        page=1,
        page_size=100,
        request=None,
    ):
        if collection != "attendance" or user.get("role") != "professor" or not class_id:
            return await original_fetch(
                db_arg, user, collection, class_id, academic_year, last_sync,
                page, page_size, request
            )
        year = int(academic_year) if academic_year else datetime.now().year
        assignments = await db_arg.teacher_class_assignments.find(
            {
                "teacher_id": user.get("id"),
                "class_id": class_id,
                "diary_settings.enabled": True,
                "valid_from": {"$lte": f"{year}-12-31"},
                "$or": [{"valid_until": None}, {"valid_until": {"$gte": f"{year}-01-01"}}],
            },
            {"_id": 0, "id": 1},
        ).to_list(500)
        assignment_ids = [a.get("id") for a in assignments if a.get("id")]
        if not assignment_ids:
            return await original_fetch(
                db_arg, user, collection, class_id, academic_year, last_sync,
                page, page_size, request
            )

        base_q: dict[str, Any] = {
            "class_id": class_id,
            "assignment_id": {"$in": assignment_ids},
            "academic_year": year,
        }
        tenant_id = user.get("mantenedora_id")
        if tenant_id:
            base_q["mantenedora_id"] = tenant_id
        if last_sync:
            base_q["$or"] = [
                {"created_at": {"$gte": last_sync}},
                {"updated_at": {"$gte": last_sync}},
            ]
        official = await db_arg.attendance.find(base_q, {"_id": 0}).to_list(10000)
        documentary = await db_arg[DOCUMENTARY_ATTENDANCE_COLLECTION].find(base_q, {"_id": 0}).to_list(10000)
        combined = official + documentary
        combined.sort(key=lambda doc: (
            doc.get("updated_at") or doc.get("created_at") or "",
            doc.get("id") or "",
        ))
        total = len(combined)
        start = max(0, (page - 1) * page_size)
        return combined[start:start + page_size], total

    sync_mod._sync_attendance_canonical = dvd_sync
    sync_mod.fetch_collection_data_paginated = dvd_fetch
    sync_mod._dvd_phase4_installed = True


def install_attendance_dvd_adapter(base_router, db, audit_service, sandbox_db=None):
    """Instala as extensões DVD no mesmo APIRouter de Frequência."""
    if getattr(base_router, "_dvd_phase4_installed", False):
        return base_router

    # Índices são criados no startup, antes de aceitar tráfego.
    @base_router.on_event("startup")
    async def _ensure_dvd_attendance_indexes():
        await ensure_attendance_assignment_indexes(db)
        if sandbox_db is not None:
            await ensure_attendance_assignment_indexes(sandbox_db)

    # Guard anti-bypass também cobre `/sync/push`, pois sync importa esta função
    # canônica em runtime.
    import routers.attendance as attendance_mod
    if not hasattr(attendance_mod, "_dvd_original_save_attendance_canonical"):
        attendance_mod._dvd_original_save_attendance_canonical = attendance_mod.save_attendance_canonical
        original_canonical = attendance_mod.save_attendance_canonical

        async def guarded_legacy_canonical(current_db, current_user, request, attendance, audit):
            if await professor_has_active_dvd_for_class(
                current_db,
                current_user,
                class_id=attendance.class_id,
                on_date=attendance.date,
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "DVD_ASSIGNMENT_REQUIRED",
                        "message": "Esta turma usa Diário por Vínculo. Abra a frequência a partir de Meus Diários para registrar com o vínculo correto.",
                    },
                )
            return await original_canonical(current_db, current_user, request, attendance, audit)

        attendance_mod.save_attendance_canonical = guarded_legacy_canonical

    _install_sync_adapter(db, audit_service, sandbox_db)

    legacy_get = _remove_route(base_router, "/attendance/by-class/{class_id}/{date}", "GET")
    legacy_delete = _remove_route(base_router, "/attendance/{attendance_id}", "DELETE")
    legacy_report = _remove_route(base_router, "/attendance/report/class/{class_id}", "GET")
    legacy_summary = _remove_route(base_router, "/attendance/attendance-summary/{class_id}", "GET")
    legacy_dates = _remove_route(base_router, "/attendance/dates-with-records", "GET")
    legacy_bim = _remove_route(base_router, "/attendance/bimestre-summary", "GET")

    @base_router.get("/dvd/context/{assignment_id}")
    async def dvd_context(
        assignment_id: str,
        request: Request,
        date_value: str = Query(None, alias="date"),
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, user)
        ref = date_value or date.today().isoformat()
        _, meta = await _dvd_context_payload(current_db, user, request, assignment_id, ref)
        return meta

    @base_router.get("/by-class/{class_id}/{date}")
    async def dvd_aware_get_by_class(
        class_id: str,
        date: str,
        request: Request,
        course_id: Optional[str] = None,
        period: str = "regular",
        assignment_id: Optional[str] = None,
        aula_numero: Optional[int] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, user)
        if assignment_id:
            result = await _get_dvd_attendance(
                current_db,
                user,
                request,
                assignment_id=assignment_id,
                on_date=date,
                aula_numero=aula_numero,
                period=period,
            )
            if result.get("class_id") != class_id:
                raise HTTPException(status_code=403, detail={
                    "code": "CLASS_MISMATCH",
                    "message": "O vínculo não pertence à turma informada.",
                })
            return result
        if await professor_has_active_dvd_for_class(
            current_db, user, class_id=class_id, on_date=date
        ):
            raise HTTPException(status_code=409, detail={
                "code": "DVD_ASSIGNMENT_REQUIRED",
                "message": "Esta turma usa Diário por Vínculo. Abra a frequência a partir de Meus Diários.",
            })
        if legacy_get is None:
            raise HTTPException(status_code=500, detail="Rota legada de frequência indisponível")
        return await legacy_get(class_id, date, request, course_id, period)

    @base_router.post("/dvd")
    async def save_dvd(payload: DvdAttendanceCreate, request: Request):
        user = await AuthMiddleware.require_roles([
            "admin", "admin_teste", "super_admin", "gerente",
            "professor", "coordenador", "apoio_pedagogico",
        ])(request)
        current_db = _db_for_user(db, sandbox_db, user)
        return await _save_dvd_attendance(current_db, user, request, payload, audit_service)

    @base_router.delete("/dvd/{attendance_id}")
    async def delete_dvd(attendance_id: str, request: Request):
        user = await AuthMiddleware.require_roles([
            "admin", "admin_teste", "super_admin", "gerente", "professor", "coordenador", "apoio_pedagogico"
        ])(request)
        current_db = _db_for_user(db, sandbox_db, user)
        existing = await current_db.attendance.find_one({"id": attendance_id}, {"_id": 0})
        collection_name = OFFICIAL_ATTENDANCE_COLLECTION
        if not existing:
            existing = await current_db[DOCUMENTARY_ATTENDANCE_COLLECTION].find_one({"id": attendance_id}, {"_id": 0})
            collection_name = DOCUMENTARY_ATTENDANCE_COLLECTION
        if not existing:
            raise HTTPException(status_code=404, detail="Registro de frequência não encontrado")
        if not existing.get("assignment_id"):
            raise HTTPException(status_code=409, detail={
                "code": "NOT_DVD_ATTENDANCE",
                "message": "Registro não pertence ao Diário por Vínculo.",
            })
        try:
            await authorize_historical_attendance(
                current_db,
                user,
                existing,
                action="attendance",
                allow_management_override=user.get("role") != "professor",
                active_mantenedora_id=get_mantenedora_scope(user, request),
            )
        except AttendanceAssignmentScopeError as exc:
            raise _http_scope_error(exc) from exc
        await current_db[collection_name].delete_one({"id": attendance_id})
        await audit_service.log(
            action="delete",
            collection=collection_name,
            user=user,
            request=request,
            document_id=attendance_id,
            description=f"EXCLUIU frequência DVD do vínculo {existing.get('assignment_id')} em {existing.get('date')}",
            school_id=existing.get("school_id"),
            academic_year=existing.get("academic_year"),
            old_value={
                "assignment_id": existing.get("assignment_id"),
                "date": existing.get("date"),
                "records_count": len(existing.get("records") or []),
                "attendance_purpose": existing.get("attendance_purpose"),
            },
        )
        return {"message": "Frequência removida com sucesso"}

    @base_router.delete("/{attendance_id}")
    async def dvd_aware_delete(attendance_id: str, request: Request):
        user = await AuthMiddleware.require_roles([
            "admin", "admin_teste", "secretario", "professor", "super_admin", "gerente", "coordenador"
        ])(request)
        current_db = _db_for_user(db, sandbox_db, user)
        existing = await current_db.attendance.find_one({"id": attendance_id}, {"_id": 0})
        if existing and existing.get("assignment_id"):
            return await delete_dvd(attendance_id, request)
        if legacy_delete is None:
            raise HTTPException(status_code=500, detail="Rota legada de exclusão indisponível")
        return await legacy_delete(attendance_id, request)

    async def _has_dvd_year(current_db, user, class_id: str, academic_year: int) -> bool:
        if user.get("role") != "professor":
            return False
        return bool(await current_db.teacher_class_assignments.find_one(
            {
                "teacher_id": user.get("id"),
                "class_id": class_id,
                "diary_settings.enabled": True,
                "valid_from": {"$lte": f"{academic_year}-12-31"},
                "$or": [{"valid_until": None}, {"valid_until": {"$gte": f"{academic_year}-01-01"}}],
            },
            {"_id": 0, "id": 1},
        ))

    @base_router.get("/report/class/{class_id}")
    async def dvd_aware_report(
        class_id: str,
        request: Request,
        academic_year: Optional[int] = None,
        course_id: Optional[str] = None,
        bimestre: Optional[int] = None,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, user)
        year = academic_year or datetime.now().year
        if assignment_id:
            report = await _dvd_report(current_db, user, request, assignment_id, year, bimestre)
            if report.get("class_id") != class_id:
                raise HTTPException(status_code=403, detail="Vínculo não pertence à turma")
            return report
        if await _has_dvd_year(current_db, user, class_id, year):
            raise HTTPException(status_code=409, detail={
                "code": "DVD_ASSIGNMENT_REQUIRED",
                "message": "Relatório de professor em turma DVD deve ser aberto pelo vínculo docente.",
            })
        return await legacy_report(class_id, request, academic_year, course_id, bimestre)

    @base_router.get("/attendance-summary/{class_id}")
    async def dvd_aware_summary(
        class_id: str,
        request: Request,
        academic_year: Optional[int] = None,
        course_id: Optional[str] = None,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, user)
        year = academic_year or datetime.now().year
        if assignment_id:
            summaries = await _dvd_bimestre_summary(current_db, user, request, assignment_id, year)
            registrados = sum(item["registrados"] for item in summaries)
            previstos = sum(item["previstos"] for item in summaries)
            optional = any(item.get("optional") for item in summaries)
            return {
                "type": "sessoes" if any("SESSÕES" in item["label_reg"] for item in summaries) else "dias",
                "previstos": previstos,
                "registrados": registrados,
                "restantes": None if optional else max(0, previstos - registrados),
                "optional": optional,
                "documentary_only": optional,
            }
        if await _has_dvd_year(current_db, user, class_id, year):
            raise HTTPException(status_code=409, detail={
                "code": "DVD_ASSIGNMENT_REQUIRED",
                "message": "Resumo de frequência em turma DVD deve usar o vínculo docente.",
            })
        return await legacy_summary(class_id, request, academic_year, course_id)

    @base_router.get("/dates-with-records")
    async def dvd_aware_dates(
        request: Request,
        class_id: str,
        academic_year: int,
        course_id: Optional[str] = None,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, user)
        if assignment_id:
            assignment = await current_db.teacher_class_assignments.find_one({"id": assignment_id}, {"_id": 0})
            if not assignment or assignment.get("class_id") != class_id:
                raise HTTPException(status_code=403, detail="Vínculo não pertence à turma")
            ref = max(str(assignment.get("valid_from") or f"{academic_year}-01-01")[:10], f"{academic_year}-01-01")
            context, _ = await _dvd_context_payload(current_db, user, request, assignment_id, ref)
            docs = await _assignment_docs(current_db, context, academic_year)
            dates = sorted({doc.get("date", "")[:10] for doc in docs if doc.get("date")})
            return {"dates": dates}
        if await _has_dvd_year(current_db, user, class_id, academic_year):
            raise HTTPException(status_code=409, detail={"code": "DVD_ASSIGNMENT_REQUIRED", "message": "Use o vínculo docente."})
        return await legacy_dates(request, class_id, academic_year, course_id)

    @base_router.get("/bimestre-summary")
    async def dvd_aware_bimestre_summary(
        request: Request,
        class_id: str,
        academic_year: int,
        course_id: Optional[str] = None,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, user)
        if assignment_id:
            assignment = await current_db.teacher_class_assignments.find_one({"id": assignment_id}, {"_id": 0})
            if not assignment or assignment.get("class_id") != class_id:
                raise HTTPException(status_code=403, detail="Vínculo não pertence à turma")
            return await _dvd_bimestre_summary(current_db, user, request, assignment_id, academic_year)
        if await _has_dvd_year(current_db, user, class_id, academic_year):
            raise HTTPException(status_code=409, detail={"code": "DVD_ASSIGNMENT_REQUIRED", "message": "Use o vínculo docente."})
        return await legacy_bim(request, class_id, academic_year, course_id)

    @base_router.get("/dvd/pdf/bimestre/{assignment_id}")
    async def dvd_bimestre_pdf(
        assignment_id: str,
        request: Request,
        bimestre: int = Query(..., ge=1, le=4),
        academic_year: Optional[int] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, user)
        year = academic_year or datetime.now().year
        assignment = await current_db.teacher_class_assignments.find_one({"id": assignment_id}, {"_id": 0})
        if not assignment:
            raise HTTPException(status_code=404, detail="Vínculo docente não encontrado")
        ref = max(str(assignment.get("valid_from") or f"{year}-01-01")[:10], f"{year}-01-01")
        context, meta = await _dvd_context_payload(current_db, user, request, assignment_id, ref)
        periods = await _calendar_periods(current_db, year)
        _, start, end = next((item for item in periods if item[0] == bimestre), (bimestre, None, None))
        docs = await _assignment_docs(current_db, context, year, start=start, end=end)
        attendance_days = []
        for doc in docs:
            ds = doc.get("date", "")[:10]
            if context.attendance_mode is AttendanceMode.ASSIGNMENT_SESSION and doc.get("aula_numero") is not None:
                attendance_days.append(f"{ds}#{doc.get('aula_numero')}")
            else:
                attendance_days.append(ds)
        attendance_days = sorted(set(attendance_days))

        roster = await build_attendance_roster(
            current_db,
            class_id=context.assignment.get("class_id"),
            academic_year=year,
            course_id=context.effective_course_id,
            tenant_id=context.snapshot.get("mantenedora_id"),
        )
        by_student = {s["id"]: {
            "name": s.get("full_name"),
            "attendance_by_date": {},
            "attendance_classes_by_date": {},
            "medical_days": [],
        } for s in roster}
        for doc in docs:
            ds = doc.get("date", "")[:10]
            key = f"{ds}#{doc.get('aula_numero')}" if (
                context.attendance_mode is AttendanceMode.ASSIGNMENT_SESSION
                and doc.get("aula_numero") is not None
            ) else ds
            for row in doc.get("records") or []:
                if row.get("student_id") in by_student:
                    by_student[row["student_id"]]["attendance_by_date"][key] = row.get("status")
                    by_student[row["student_id"]]["attendance_classes_by_date"][key] = 1

        dates_only = {key.split("#")[0] for key in attendance_days}
        if dates_only and by_student:
            certs = await current_db.medical_certificates.find(
                {
                    "student_id": {"$in": list(by_student)},
                    "start_date": {"$lte": max(dates_only)},
                    "end_date": {"$gte": min(dates_only)},
                },
                {"_id": 0, "student_id": 1, "start_date": 1, "end_date": 1},
            ).to_list(None)
            for cert in certs:
                sid = cert.get("student_id")
                if sid not in by_student:
                    continue
                for ds in dates_only:
                    if str(cert.get("start_date") or "")[:10] <= ds <= str(cert.get("end_date") or "")[:10]:
                        by_student[sid]["medical_days"].append(ds)

        school = await current_db.schools.find_one(
            {"id": context.snapshot.get("school_id"), "mantenedora_id": context.snapshot.get("mantenedora_id")},
            {"_id": 0},
        )
        if not school:
            raise HTTPException(status_code=404, detail="Escola do vínculo não encontrada")
        course = None
        if context.effective_course_id:
            course = await current_db.courses.find_one(
                {"id": context.effective_course_id, "mantenedora_id": context.snapshot.get("mantenedora_id")},
                {"_id": 0},
            )
        mantenedora = await current_db.mantenedoras.find_one(
            {"id": context.snapshot.get("mantenedora_id")}, {"_id": 0}
        ) or {}
        previstos = await _expected_sessions(
            current_db, context, start=start, end=end, academic_year=year
        )

        from pdf_generator import generate_relatorio_frequencia_bimestre_pdf
        teacher_name = context.snapshot.get("teacher_name") or ""
        if meta["documentary_only"]:
            teacher_name = f"{teacher_name} - REGISTRO DOCUMENTAL (NÃO OFICIAL)"
        pdf_buffer: BytesIO = generate_relatorio_frequencia_bimestre_pdf(
            school=school,
            class_info={
                **context.class_info,
                "name": context.class_info.get("name") or context.assignment.get("class_name"),
            },
            course_info=course or {},
            students_attendance=list(by_student.values()),
            bimestre=bimestre,
            academic_year=year,
            period_start=start,
            period_end=end,
            attendance_days=attendance_days,
            aulas_previstas=previstos,
            aulas_ministradas=len(attendance_days),
            teacher_name=teacher_name,
            mantenedora=mantenedora,
            teacher_names=None,
        )
        filename = f"frequencia_{assignment_id}_{bimestre}bim_{year}.pdf"
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    base_router._dvd_phase4_installed = True
    return base_router
