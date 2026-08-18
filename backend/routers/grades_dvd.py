"""Adaptador de Notas/Conceitos por Vínculo Docente — DVD Fase 5.

Mantém ``Grades.js``, ``/grades`` e o gerador PDF existentes. O backend deriva o
assignment do professor quando ele é unívoco; ``assignment_id`` explícito é
sempre revalidado e nunca confiado como autoria.

Invariantes adicionais:
- autoria pedagógica é por campo em ``grade_ownership``;
- professor comum não recebe valores/metadados pertencentes a outro vínculo;
- sync offline usa o mesmo motor DVD e não grava ``grades`` diretamente;
- calendário de autoria lê ``calendario_letivo`` com a mesma prioridade
  escola → calendário geral utilizada pelo SIGESC;
- PDF reutiliza o gerador/layout existente e recebe somente dados do vínculo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional
import logging
import uuid

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from auth_middleware import AuthMiddleware
from models import GradeCreate, GradeUpdate
from pdf_cache import get_mantenedora_cached
from services.diary_assignment_access import (
    DiaryAction,
    DiaryAssignmentAccessError,
    authorize_assignment_access,
)
from services.diary_assignment_contract import DiaryProfile
from services.grade_assignment_scope import (
    GRADE_OWNERSHIP_FIELDS,
    GRADE_VALUE_FIELDS,
    GradeAssignmentContext,
    GradeAssignmentScopeError,
    apply_grade_field_ownership,
    changed_grade_fields,
    owned_fields_for_assignment,
    resolve_grade_assignment,
    resolve_own_grade_assignment,
)
from tenant_scope import get_mantenedora_scope
from utils.academic_event_lens import record_lock_audit, resolve_student_ownership
from utils.dependency_validator import validate_dependency_link

logger = logging.getLogger(__name__)

PEDAGOGICAL_ROLES = {"professor", "coordenador", "apoio_pedagogico"}
MANAGEMENT_WRITE_ROLES = {
    "super_admin", "admin", "admin_teste", "gerente", "semed3", "coordenador", "apoio_pedagogico"
}


def _db_for_user(db, sandbox_db, user: Mapping[str, Any]):
    if user.get("is_sandbox"):
        return sandbox_db if sandbox_db is not None else db
    return db


def _http_scope_error(exc: GradeAssignmentScopeError) -> HTTPException:
    conflict_codes = {
        "GRADE_ASSIGNMENT_AMBIGUOUS",
        "GRADE_GROUP_SCOPE_UNRESOLVED",
        "SHARED_GRADE_OWNER_REQUIRED",
        "SHARED_GRADE_OWNER_AMBIGUOUS",
        "GRADE_FIELD_OWNED_BY_OTHER_ASSIGNMENT",
        "GRADE_LEGACY_FIELD_REQUIRES_REVIEW",
        "GRADE_PERIOD_OUTSIDE_ASSIGNMENT",
        "DVD_ASSIGNMENT_REQUIRED",
        "GRADE_BATCH_SCOPE_MISMATCH",
    }
    status_code = 409 if exc.code in conflict_codes else 403
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def _remove_route(base_router, path: str, method: str):
    for route in list(base_router.routes):
        if (
            getattr(route, "path", None) == path
            and method.upper() in (getattr(route, "methods", set()) or set())
        ):
            endpoint = route.endpoint
            base_router.routes.remove(route)
            return endpoint
    return None


async def _calendar_periods(
    current_db,
    academic_year: int,
    *,
    school_id: Optional[str] = None,
) -> dict[int, tuple[str, str]]:
    """Resolve os 4 bimestres pela fonte institucional ``calendario_letivo``.

    Mantém a mesma prioridade de ``school_calendar_helper``: calendário da escola
    quando existente, depois calendário geral (`school_id=None`). O fallback só é
    usado quando não há datas institucionais configuradas.
    """
    calendario = None
    if school_id:
        calendario = await current_db.calendario_letivo.find_one(
            {"ano_letivo": academic_year, "school_id": school_id},
            {"_id": 0},
        )
    if not calendario:
        calendario = await current_db.calendario_letivo.find_one(
            {"ano_letivo": academic_year, "school_id": None},
            {"_id": 0},
        )

    fallback = {
        1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
        2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
        3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
        4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
    }
    result: dict[int, tuple[str, str]] = {}
    for bimestre in (1, 2, 3, 4):
        ini = (calendario or {}).get(f"bimestre_{bimestre}_inicio")
        fim = (calendario or {}).get(f"bimestre_{bimestre}_fim")
        result[bimestre] = (
            str(ini)[:10] if ini else fallback[bimestre][0],
            str(fim)[:10] if fim else fallback[bimestre][1],
        )
    return result


async def _class_has_dvd_grades(
    current_db,
    class_id: str,
    course_id: str,
    academic_year: int,
) -> bool:
    docs = await current_db.teacher_class_assignments.find(
        {
            "class_id": class_id,
            "deleted": False,
            "diary_settings.enabled": True,
            "diary_settings.profile": {
                "$in": [DiaryProfile.REGULAR.value, DiaryProfile.SHARED.value]
            },
            "valid_from": {"$lte": f"{academic_year}-12-31"},
            "$or": [
                {"valid_until": None},
                {"valid_until": {"$gte": f"{academic_year}-01-01"}},
            ],
        },
        {"_id": 0, "id": 1, "component_id": 1},
    ).to_list(500)
    return any(item.get("component_id") in (None, course_id) for item in docs)


async def _context_or_legacy(
    current_db,
    user: Mapping[str, Any],
    request: Request,
    *,
    class_id: str,
    course_id: str,
    academic_year: int,
    assignment_id: Optional[str] = None,
) -> Optional[GradeAssignmentContext]:
    active_tenant = get_mantenedora_scope(user, request)
    today = datetime.now(timezone.utc).date().isoformat()
    if assignment_id:
        try:
            return await resolve_grade_assignment(
                current_db,
                user,
                assignment_id,
                class_id=class_id,
                course_id=course_id,
                on_date=today,
                allow_management_override=user.get("role") in MANAGEMENT_WRITE_ROLES,
                active_mantenedora_id=active_tenant,
            )
        except GradeAssignmentScopeError as exc:
            raise _http_scope_error(exc) from exc

    if user.get("role") in PEDAGOGICAL_ROLES:
        try:
            context = await resolve_own_grade_assignment(
                current_db,
                user,
                class_id=class_id,
                course_id=course_id,
                on_date=today,
                active_mantenedora_id=active_tenant,
            )
        except GradeAssignmentScopeError as exc:
            raise _http_scope_error(exc) from exc
        if context is not None:
            return context
        if await _class_has_dvd_grades(current_db, class_id, course_id, academic_year):
            raise _http_scope_error(
                GradeAssignmentScopeError(
                    "DVD_ASSIGNMENT_REQUIRED",
                    "Esta avaliação usa Diário por Vínculo e não existe um vínculo próprio unívoco para o usuário.",
                )
            )
    return None


async def _validate_dependency(current_db, user, request, payload: Mapping[str, Any]):
    dependency_id = payload.get("dependency_id")
    if not dependency_id:
        return
    await validate_dependency_link(
        db=current_db,
        dependency_id=dependency_id,
        student_id=payload["student_id"],
        class_id=payload["class_id"],
        course_id=payload["course_id"],
        tenant_id=get_mantenedora_scope(user, request),
    )


async def _validate_academic_event(current_db, user, request, payload: Mapping[str, Any]):
    ownership = await resolve_student_ownership(
        current_db,
        student_id=payload["student_id"],
        class_id=payload["class_id"],
        course_id=payload["course_id"],
        target_date=None,
        mantenedora_id=get_mantenedora_scope(user, request),
    )
    if ownership["editable"]:
        return
    await record_lock_audit(
        current_db,
        event_id=ownership.get("governing_event_id"),
        action="grade_dvd_write_blocked",
        user_id=user.get("id"),
        role=user.get("role"),
        student_id=payload["student_id"],
        class_id=payload["class_id"],
        target_date=ownership.get("governing_effective_date"),
        target_resource="grade",
        reason_code=ownership["blocked_reason"],
        ip=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    raise HTTPException(
        status_code=409,
        detail={
            "code": "ACADEMIC_EVENT_LOCK",
            "reason_code": ownership["blocked_reason"],
            "event_id": ownership.get("governing_event_id"),
            "message": "Edição de avaliação bloqueada por evento acadêmico.",
        },
    )


def _filter_masked_null_noops(
    existing: Mapping[str, Any],
    update_fields: Mapping[str, Any],
    context: GradeAssignmentContext,
) -> dict[str, Any]:
    """Ignora ``null`` enviado por uma UI que recebeu o campo mascarado.

    ``Grades.js`` envia todos os campos no batch. Quando um campo de outro
    vínculo/legado é ocultado como ``null``, esse ``null`` não pode ser tratado
    como tentativa de apagar o valor real. Valor não-nulo divergente continua
    sendo validado e bloqueado pelo motor de ownership.
    """
    ownership = existing.get("grade_ownership") or {}
    filtered = dict(update_fields)
    for field in list(filtered):
        if filtered[field] is not None or existing.get(field) is None:
            continue
        owner = ownership.get(field)
        if not owner or owner.get("assignment_id") != context.assignment_id:
            filtered.pop(field, None)
    return filtered


async def _save_one_dvd_grade(
    current_db,
    user: Mapping[str, Any],
    request: Request,
    context: GradeAssignmentContext,
    payload: Mapping[str, Any],
) -> tuple[dict, Optional[dict]]:
    """Salva um estudante e retorna ``(grade atualizada, mudança auditável)``."""
    if payload.get("class_id") != context.class_id or payload.get("course_id") != context.course_id:
        raise _http_scope_error(
            GradeAssignmentScopeError(
                "GRADE_BATCH_SCOPE_MISMATCH",
                "Todos os dados do lote devem pertencer à turma/componente do vínculo.",
            )
        )
    await _validate_dependency(current_db, user, request, payload)
    await _validate_academic_event(current_db, user, request, payload)

    from routers.grades import _strip_frozen_grade_fields, calculate_and_update_grade

    key = {
        "student_id": payload["student_id"],
        "class_id": payload["class_id"],
        "course_id": payload["course_id"],
        "academic_year": payload["academic_year"],
    }
    existing = await current_db.grades.find_one(key, {"_id": 0})
    update_fields = {
        field: payload.get(field)
        for field in GRADE_OWNERSHIP_FIELDS
        if field in payload
    }
    if existing:
        update_fields = _strip_frozen_grade_fields(
            update_fields,
            existing,
            str(user.get("role") or ""),
        )
        if context.access.is_owner:
            update_fields = _filter_masked_null_noops(existing, update_fields, context)

    changes = changed_grade_fields(existing, update_fields)
    if existing and not changes:
        return existing, None

    periods = await _calendar_periods(
        current_db,
        int(payload["academic_year"]),
        school_id=context.snapshot.get("school_id"),
    )
    try:
        grade_ownership = await apply_grade_field_ownership(
            current_db,
            user,
            existing,
            changes,
            context,
            periods=periods,
            allow_management_override=(
                user.get("role") in MANAGEMENT_WRITE_ROLES and not context.access.is_owner
            ),
            active_mantenedora_id=get_mantenedora_scope(user, request),
        )
    except GradeAssignmentScopeError as exc:
        raise _http_scope_error(exc) from exc

    now = datetime.now(timezone.utc).isoformat()
    if existing:
        set_data = dict(changes)
        set_data.update(
            {
                "grade_ownership": grade_ownership,
                "updated_at": now,
                "updated_by": user.get("id"),
                "last_updated_by": user.get("id"),
            }
        )
        old_values = {field: existing.get(field) for field in changes}
        await current_db.grades.update_one({"id": existing["id"]}, {"$set": set_data})
        updated = await calculate_and_update_grade(current_db, existing["id"])
        return updated, {
            "student_id": payload["student_id"],
            "grade_id": existing["id"],
            "old": old_values,
            "new": dict(changes),
            "assignment_id": context.assignment_id,
        }

    new_grade = {
        "id": str(uuid.uuid4()),
        **key,
        "dependency_id": payload.get("dependency_id"),
        "b1": payload.get("b1"),
        "b2": payload.get("b2"),
        "b3": payload.get("b3"),
        "b4": payload.get("b4"),
        "rec_s1": payload.get("rec_s1"),
        "rec_s2": payload.get("rec_s2"),
        "recovery": payload.get("recovery"),
        "observations": payload.get("observations"),
        "final_average": None,
        "status": "cursando",
        "grade_ownership": grade_ownership,
        "mantenedora_id": context.snapshot.get("mantenedora_id"),
        "created_at": now,
        "created_by": user.get("id"),
        "updated_at": now,
        "updated_by": user.get("id"),
        "last_updated_by": user.get("id"),
    }
    await current_db.grades.insert_one(new_grade)
    updated = await calculate_and_update_grade(current_db, new_grade["id"])
    return updated, {
        "student_id": payload["student_id"],
        "grade_id": new_grade["id"],
        "action": "create",
        "new": dict(changes),
        "assignment_id": context.assignment_id,
    }


def _mask_grade_for_assignment(
    grade: Mapping[str, Any],
    context: GradeAssignmentContext,
    *,
    mask_foreign: bool,
) -> dict[str, Any]:
    out = dict(grade)
    ownership = grade.get("grade_ownership") or {}
    owned = sorted(owned_fields_for_assignment(grade, context.assignment_id))
    locked = sorted(
        field
        for field in GRADE_OWNERSHIP_FIELDS
        if grade.get(field) is not None and field not in owned
    )
    if mask_foreign:
        for field in GRADE_OWNERSHIP_FIELDS:
            if field not in owned:
                out[field] = None
        # Snapshot de outro professor também é dado de autoria e não deve vazar.
        out["grade_ownership"] = {
            field: dict(snapshot)
            for field, snapshot in ownership.items()
            if field in owned and isinstance(snapshot, Mapping)
        }
        foreign_value = any(
            grade.get(field) is not None and field not in owned
            for field in GRADE_VALUE_FIELDS
        )
        if foreign_value:
            out["final_average"] = None
            out["status"] = "cursando"
    out["dvd_assignment_id"] = context.assignment_id
    out["dvd_owned_fields"] = owned
    out["dvd_locked_fields"] = locked
    return out


def _mask_grade_for_teacher(grade: Mapping[str, Any], teacher_id: str) -> Optional[dict[str, Any]]:
    """Visão histórica/offline: somente campos cujo snapshot pertence ao professor."""
    ownership = grade.get("grade_ownership") or {}
    owned = {
        field
        for field, snapshot in ownership.items()
        if isinstance(snapshot, Mapping) and snapshot.get("teacher_id") == teacher_id
    }
    if not owned:
        return None
    out = dict(grade)
    for field in GRADE_OWNERSHIP_FIELDS:
        if field not in owned:
            out[field] = None
    out["grade_ownership"] = {
        field: dict(snapshot)
        for field, snapshot in ownership.items()
        if field in owned and isinstance(snapshot, Mapping)
    }
    foreign_value = any(
        grade.get(field) is not None and field not in owned
        for field in GRADE_VALUE_FIELDS
    )
    if foreign_value:
        out["final_average"] = None
        out["status"] = "cursando"
    out["dvd_owned_fields"] = sorted(owned)
    out["dvd_locked_fields"] = []
    return out


async def _dvd_pdf(
    current_db,
    context: GradeAssignmentContext,
    *,
    class_id: str,
    course_id: str,
    bimestres: str,
    academic_year: int,
    student_series: Optional[str],
):
    from pdf_generator import generate_grades_report_pdf

    tenant_id = context.snapshot.get("mantenedora_id")
    class_info = await current_db.classes.find_one(
        {"id": class_id, "mantenedora_id": tenant_id},
        {"_id": 0},
    )
    course = await current_db.courses.find_one(
        {"id": course_id, "mantenedora_id": tenant_id},
        {"_id": 0},
    )
    if not class_info:
        raise HTTPException(status_code=404, detail="Turma do vínculo não encontrada")
    if not course:
        raise HTTPException(status_code=404, detail="Componente do vínculo não encontrado")
    school = await current_db.schools.find_one(
        {
            "id": context.snapshot.get("school_id"),
            "mantenedora_id": tenant_id,
        },
        {"_id": 0},
    ) or {"name": ""}
    mantenedora = await current_db.mantenedoras.find_one(
        {"id": tenant_id},
        {"_id": 0},
    ) or await get_mantenedora_cached(current_db) or {}

    enrollments = await current_db.enrollments.find(
        {"class_id": class_id, "status": "active"},
        {"_id": 0, "student_id": 1, "enrollment_number": 1, "student_series": 1},
    ).to_list(1000)
    direct_students = await current_db.students.find(
        {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
        {"_id": 0, "id": 1, "enrollment_number": 1, "student_series": 1},
    ).to_list(1000)
    enrollment_map = {
        item.get("student_id"): {
            "enrollment_number": item.get("enrollment_number"),
            "student_series": item.get("student_series", ""),
        }
        for item in enrollments
        if item.get("student_id")
    }
    for student in direct_students:
        sid = student.get("id")
        if sid and sid not in enrollment_map:
            enrollment_map[sid] = {
                "enrollment_number": student.get("enrollment_number"),
                "student_series": student.get("student_series", ""),
            }

    student_ids = list(enrollment_map)
    students = []
    if student_ids:
        students = await current_db.students.find(
            {"id": {"$in": student_ids}},
            {
                "_id": 0,
                "id": 1,
                "full_name": 1,
                "enrollment_number": 1,
                "student_series": 1,
            },
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)

    if student_series:
        from utils.serie_canonical import canonicalize_serie

        def _series_match(a, b):
            ca = canonicalize_serie(a or "")
            cb = canonicalize_serie(b or "")
            if ca and cb:
                return ca == cb
            return (a or "").strip().lower() == (b or "").strip().lower()

        students = [
            student
            for student in students
            if _series_match(
                enrollment_map.get(student["id"], {}).get("student_series")
                or student.get("student_series"),
                student_series,
            )
        ]

    grades = await current_db.grades.find(
        {
            "class_id": class_id,
            "course_id": course_id,
            "academic_year": academic_year,
        },
        {"_id": 0},
    ).to_list(1000)
    grades_map = {grade.get("student_id"): grade for grade in grades}
    students_data = []
    for student in students:
        grade = grades_map.get(student["id"], {})
        owned = owned_fields_for_assignment(grade, context.assignment_id)
        foreign_value = any(
            grade.get(field) is not None and field not in owned
            for field in GRADE_VALUE_FIELDS
        )
        students_data.append(
            {
                "full_name": student.get("full_name", ""),
                "enrollment_number": (
                    enrollment_map.get(student["id"], {}).get("enrollment_number")
                    or student.get("enrollment_number", "")
                ),
                **{
                    field: grade.get(field) if field in owned else None
                    for field in GRADE_VALUE_FIELDS
                },
                # Média/situação agregadas só podem aparecer quando não dependem
                # de um valor pertencente a outro vínculo.
                "final_average": None if foreign_value else grade.get("final_average"),
                "status": "cursando" if foreign_value else grade.get("status", "cursando"),
            }
        )

    bims = [
        int(value.strip())
        for value in bimestres.split(",")
        if value.strip().isdigit()
    ]
    buffer = generate_grades_report_pdf(
        school=school,
        class_info=class_info,
        course=course,
        students_data=students_data,
        bimestres=bims,
        academic_year=academic_year,
        grade_level=student_series or class_info.get("grade_level", ""),
        mantenedora=mantenedora,
        teacher_names=[context.snapshot.get("teacher_name") or ""],
    )
    class_name = (class_info.get("name") or "turma").replace(" ", "_")
    course_name = (course.get("name") or "comp").replace(" ", "_")
    filename = f"notas_{class_name}_{course_name}_{academic_year}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _install_sync_adapter(db, audit_service, sandbox_db=None):
    """Fecha o bypass de ``/sync/push``/``pull`` para notas DVD do professor."""
    import routers.sync as sync_mod

    if getattr(sync_mod, "_dvd_phase5_grades_installed", False):
        return

    original_process = sync_mod.process_sync_operation
    original_fetch = sync_mod.fetch_collection_data_paginated

    async def dvd_process(db_arg, user, op, request=None):
        if op.collection != "grades" or user.get("role") != "professor":
            return await original_process(db_arg, user, op, request)

        data = op.data or {}
        class_id = data.get("class_id")
        course_id = data.get("course_id")
        academic_year = data.get("academic_year")
        if not class_id or not course_id or not academic_year:
            return sync_mod.SyncPushResult(
                recordId=op.recordId,
                success=False,
                error="Nota offline sem turma, componente ou ano letivo.",
            )

        try:
            context = await resolve_own_grade_assignment(
                db_arg,
                user,
                class_id=class_id,
                course_id=course_id,
                on_date=datetime.now(timezone.utc).date().isoformat(),
                active_mantenedora_id=get_mantenedora_scope(user, request),
            )
            if context is None:
                if await _class_has_dvd_grades(
                    db_arg,
                    class_id,
                    course_id,
                    int(academic_year),
                ):
                    return sync_mod.SyncPushResult(
                        recordId=op.recordId,
                        success=False,
                        error="409: DVD_ASSIGNMENT_REQUIRED",
                    )
                return await original_process(db_arg, user, op, request)

            if op.operation == "delete":
                return sync_mod.SyncPushResult(
                    recordId=op.recordId,
                    success=False,
                    error="Exclusão offline de avaliação DVD não é permitida.",
                )
            if op.operation not in {"create", "update"}:
                return sync_mod.SyncPushResult(
                    recordId=op.recordId,
                    success=False,
                    error=f"Operação desconhecida: {op.operation}",
                )

            current_db = _db_for_user(db_arg, sandbox_db, user)
            updated, change = await _save_one_dvd_grade(
                current_db,
                user,
                request,
                context,
                data,
            )
            if change:
                await audit_service.log(
                    action="create" if change.get("action") == "create" else "update",
                    collection="grades",
                    user=user,
                    request=request,
                    document_id=updated.get("id"),
                    description=(
                        f"Sincronizou avaliação DVD offline do vínculo {context.assignment_id}"
                    ),
                    school_id=context.snapshot.get("school_id"),
                    academic_year=int(academic_year),
                    extra_data={
                        "assignment_id": context.assignment_id,
                        "change": change,
                        "source": "offline_sync",
                    },
                )
            return sync_mod.SyncPushResult(
                recordId=op.recordId,
                success=True,
                serverId=updated.get("id"),
            )
        except (GradeAssignmentScopeError, HTTPException) as exc:
            if isinstance(exc, HTTPException):
                detail = exc.detail
                if isinstance(detail, dict):
                    detail = detail.get("message") or detail.get("code") or str(detail)
                return sync_mod.SyncPushResult(
                    recordId=op.recordId,
                    success=False,
                    error=f"{exc.status_code}: {detail}",
                )
            return sync_mod.SyncPushResult(
                recordId=op.recordId,
                success=False,
                error=f"409: {exc.code}: {exc.message}",
            )
        except Exception as exc:  # pragma: no cover - defesa de transporte
            logger.exception("Falha no sync DVD de notas")
            return sync_mod.SyncPushResult(
                recordId=op.recordId,
                success=False,
                error=str(exc),
            )

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
        data, total = await original_fetch(
            db_arg,
            user,
            collection,
            class_id,
            academic_year,
            last_sync,
            page,
            page_size,
            request,
        )
        if collection != "grades" or user.get("role") != "professor":
            return data, total
        masked = []
        for grade in data:
            own = _mask_grade_for_teacher(grade, user.get("id"))
            if own is not None:
                masked.append(own)
        # O total exposto ao professor corresponde apenas aos registros que
        # possuem pelo menos um campo de autoria dele nesta página. O sync é
        # cache auxiliar; não deve revelar a contagem consolidada de terceiros.
        return masked, len(masked)

    sync_mod.process_sync_operation = dvd_process
    sync_mod.fetch_collection_data_paginated = dvd_fetch
    sync_mod._dvd_phase5_grades_installed = True


def install_grades_dvd_adapter(
    base_router,
    db,
    audit_service,
    *,
    verify_academic_year_open_or_raise=None,
    verify_bimestre_edit_deadline_or_raise=None,
    sandbox_db=None,
):
    if getattr(base_router, "_dvd_phase5_installed", False):
        return base_router

    _install_sync_adapter(db, audit_service, sandbox_db)

    legacy_list = _remove_route(base_router, "/grades", "GET")
    legacy_by_class = _remove_route(
        base_router,
        "/grades/by-class/{class_id}/{course_id}",
        "GET",
    )
    legacy_by_student = _remove_route(
        base_router,
        "/grades/by-student/{student_id}",
        "GET",
    )
    legacy_create = _remove_route(base_router, "/grades", "POST")
    legacy_update = _remove_route(base_router, "/grades/{grade_id}", "PUT")
    legacy_batch = _remove_route(base_router, "/grades/batch", "POST")
    legacy_pdf = _remove_route(
        base_router,
        "/grades/pdf/{class_id}/{course_id}",
        "GET",
    )

    @base_router.put("/dvd/shared-owner/{assignment_id}")
    async def set_shared_grade_owner(assignment_id: str, request: Request):
        user = await AuthMiddleware.require_roles(list(MANAGEMENT_WRITE_ROLES))(request)
        current_db = _db_for_user(db, sandbox_db, user)
        try:
            access = await authorize_assignment_access(
                current_db,
                user,
                assignment_id,
                action=DiaryAction.VIEW,
                active_mantenedora_id=get_mantenedora_scope(user, request),
            )
        except DiaryAssignmentAccessError as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        if access.settings.profile is not DiaryProfile.SHARED:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "GRADE_OWNER_REQUIRES_SHARED",
                    "message": (
                        "Responsável oficial explícito é configurável apenas para profile=shared."
                    ),
                },
            )

        component_id = access.assignment.get("component_id")
        peer_filter: dict[str, Any] = {
            "class_id": access.assignment.get("class_id"),
            "deleted": False,
            "diary_settings.enabled": True,
            "diary_settings.profile": DiaryProfile.SHARED.value,
        }
        if component_id is not None:
            peer_filter["$or"] = [
                {"component_id": component_id},
                {"component_id": None},
            ]
        await current_db.teacher_class_assignments.update_many(
            peer_filter,
            {"$set": {"grades_official_owner": False}},
        )
        await current_db.teacher_class_assignments.update_one(
            {"id": assignment_id},
            {
                "$set": {
                    "grades_official_owner": True,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "updated_by": user.get("id"),
                }
            },
        )
        await audit_service.log(
            action="update",
            collection="teacher_class_assignments",
            user=user,
            request=request,
            document_id=assignment_id,
            description="Definiu vínculo shared como responsável oficial pela avaliação",
            school_id=access.class_info.get("school_id"),
            extra_data={
                "grades_official_owner": True,
                "component_id": component_id,
            },
        )
        return {"assignment_id": assignment_id, "grades_official_owner": True}

    @base_router.get("")
    async def dvd_aware_list(
        request: Request,
        student_id: Optional[str] = None,
        class_id: Optional[str] = None,
        course_id: Optional[str] = None,
        academic_year: Optional[int] = None,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, user)
        year = academic_year or datetime.now().year
        result = await legacy_list(
            request,
            student_id,
            class_id,
            course_id,
            academic_year,
        )
        if class_id and course_id:
            context = await _context_or_legacy(
                current_db,
                user,
                request,
                class_id=class_id,
                course_id=course_id,
                academic_year=year,
                assignment_id=assignment_id,
            )
            if context:
                mask = user.get("role") == "professor"
                return [
                    _mask_grade_for_assignment(grade, context, mask_foreign=mask)
                    for grade in result
                ]
        return result

    @base_router.get("/by-class/{class_id}/{course_id}")
    async def dvd_aware_by_class(
        class_id: str,
        course_id: str,
        request: Request,
        academic_year: Optional[int] = None,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, user)
        year = academic_year or datetime.now().year
        context = await _context_or_legacy(
            current_db,
            user,
            request,
            class_id=class_id,
            course_id=course_id,
            academic_year=year,
            assignment_id=assignment_id,
        )
        result = await legacy_by_class(
            class_id,
            course_id,
            request,
            academic_year,
        )
        if not context:
            return result
        mask = user.get("role") == "professor"
        for item in result:
            if item.get("grade"):
                item["grade"] = _mask_grade_for_assignment(
                    item["grade"],
                    context,
                    mask_foreign=mask,
                )
        return result

    @base_router.get("/by-student/{student_id}")
    async def dvd_aware_by_student(
        student_id: str,
        request: Request,
        academic_year: Optional[int] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        result = await legacy_by_student(student_id, request, academic_year)
        if user.get("role") != "professor":
            return result
        visible = []
        for grade in result.get("grades") or []:
            own = _mask_grade_for_teacher(grade, user.get("id"))
            if own is not None:
                visible.append(own)
        return {
            **result,
            "grades": visible,
        }

    @base_router.post("")
    async def dvd_aware_create(
        grade_data: GradeCreate,
        request: Request,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.require_roles(
            [
                "admin",
                "admin_teste",
                "secretario",
                "professor",
                "coordenador",
                "auxiliar_secretaria",
                "apoio_pedagogico",
            ]
        )(request)
        current_db = _db_for_user(db, sandbox_db, user)
        payload = grade_data.model_dump()
        context = await _context_or_legacy(
            current_db,
            user,
            request,
            class_id=payload["class_id"],
            course_id=payload["course_id"],
            academic_year=payload["academic_year"],
            assignment_id=assignment_id,
        )
        if not context:
            return await legacy_create(grade_data, request)
        updated, change = await _save_one_dvd_grade(
            current_db,
            user,
            request,
            context,
            payload,
        )
        if change:
            await audit_service.log(
                action="create" if change.get("action") == "create" else "update",
                collection="grades",
                user=user,
                request=request,
                document_id=updated.get("id"),
                description=f"Lançou/atualizou avaliação DVD do vínculo {context.assignment_id}",
                school_id=context.snapshot.get("school_id"),
                academic_year=payload["academic_year"],
                extra_data={
                    "assignment_id": context.assignment_id,
                    "change": change,
                    "ownership_model": "field_snapshot_v1",
                },
            )
        return _mask_grade_for_assignment(
            updated,
            context,
            mask_foreign=user.get("role") == "professor",
        )

    @base_router.put("/{grade_id}")
    async def dvd_aware_update(
        grade_id: str,
        grade_update: GradeUpdate,
        request: Request,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.require_roles(
            [
                "admin",
                "admin_teste",
                "secretario",
                "professor",
                "coordenador",
                "auxiliar_secretaria",
                "apoio_pedagogico",
            ]
        )(request)
        current_db = _db_for_user(db, sandbox_db, user)
        existing = await current_db.grades.find_one({"id": grade_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Nota não encontrada")
        context = await _context_or_legacy(
            current_db,
            user,
            request,
            class_id=existing["class_id"],
            course_id=existing["course_id"],
            academic_year=existing["academic_year"],
            assignment_id=assignment_id,
        )
        if not context:
            return await legacy_update(grade_id, grade_update, request)
        payload = {
            "student_id": existing["student_id"],
            "class_id": existing["class_id"],
            "course_id": existing["course_id"],
            "academic_year": existing["academic_year"],
            "dependency_id": existing.get("dependency_id"),
            **grade_update.model_dump(exclude_unset=True),
        }
        updated, change = await _save_one_dvd_grade(
            current_db,
            user,
            request,
            context,
            payload,
        )
        if change:
            await audit_service.log(
                action="update",
                collection="grades",
                user=user,
                request=request,
                document_id=grade_id,
                description=f"Atualizou avaliação DVD do vínculo {context.assignment_id}",
                school_id=context.snapshot.get("school_id"),
                academic_year=existing["academic_year"],
                extra_data={
                    "assignment_id": context.assignment_id,
                    "change": change,
                    "ownership_model": "field_snapshot_v1",
                },
            )
        return _mask_grade_for_assignment(
            updated,
            context,
            mask_foreign=user.get("role") == "professor",
        )

    @base_router.post("/batch")
    async def dvd_aware_batch(
        request: Request,
        grades: list[dict],
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.require_roles(
            [
                "admin",
                "admin_teste",
                "secretario",
                "professor",
                "coordenador",
                "auxiliar_secretaria",
                "apoio_pedagogico",
            ]
        )(request)
        current_db = _db_for_user(db, sandbox_db, user)
        if not grades:
            return await legacy_batch(request, grades)
        first = grades[0]
        context = await _context_or_legacy(
            current_db,
            user,
            request,
            class_id=first["class_id"],
            course_id=first["course_id"],
            academic_year=first["academic_year"],
            assignment_id=assignment_id,
        )
        if not context:
            return await legacy_batch(request, grades)

        for row in grades:
            if (
                row.get("class_id") != context.class_id
                or row.get("course_id") != context.course_id
                or row.get("academic_year") != first.get("academic_year")
            ):
                raise _http_scope_error(
                    GradeAssignmentScopeError(
                        "GRADE_BATCH_SCOPE_MISMATCH",
                        "Lote DVD deve conter uma única turma, componente e ano letivo.",
                    )
                )

        role = str(user.get("role") or "")
        if (
            role not in {"admin", "admin_teste", "super_admin", "gerente"}
            and verify_academic_year_open_or_raise
        ):
            await verify_academic_year_open_or_raise(
                context.snapshot.get("school_id"),
                first["academic_year"],
            )
        if (
            role
            not in {"admin", "admin_teste", "super_admin", "gerente", "secretario"}
            and verify_bimestre_edit_deadline_or_raise
        ):
            bimestres = set()
            for row in grades:
                for field in ("b1", "b2", "b3", "b4"):
                    if row.get(field) is not None:
                        bimestres.add(int(field[1]))
            for bimestre in bimestres:
                await verify_bimestre_edit_deadline_or_raise(
                    first["academic_year"],
                    bimestre,
                    role,
                )

        results = []
        changes = []
        for row in grades:
            updated, change = await _save_one_dvd_grade(
                current_db,
                user,
                request,
                context,
                row,
            )
            results.append(
                _mask_grade_for_assignment(
                    updated,
                    context,
                    mask_foreign=user.get("role") == "professor",
                )
            )
            if change:
                changes.append(change)

        if changes:
            await audit_service.log(
                action="update",
                collection="grades",
                user=user,
                request=request,
                description=(
                    f"Atualizou avaliação DVD de {len(changes)} estudante(s) "
                    f"no vínculo {context.assignment_id}"
                ),
                school_id=context.snapshot.get("school_id"),
                academic_year=first["academic_year"],
                extra_data={
                    "assignment_id": context.assignment_id,
                    "changes": changes[:10],
                    "ownership_model": "field_snapshot_v1",
                },
            )
        return {"updated": len(results), "grades": results, "skipped": []}

    @base_router.get("/pdf/{class_id}/{course_id}")
    async def dvd_aware_pdf(
        class_id: str,
        course_id: str,
        request: Request,
        bimestres: str = "1,2,3,4",
        academic_year: Optional[int] = None,
        student_series: Optional[str] = None,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, user)
        year = academic_year or datetime.now().year
        context = await _context_or_legacy(
            current_db,
            user,
            request,
            class_id=class_id,
            course_id=course_id,
            academic_year=year,
            assignment_id=assignment_id,
        )
        if not context:
            return await legacy_pdf(
                class_id,
                course_id,
                request,
                bimestres,
                academic_year,
                student_series,
            )
        return await _dvd_pdf(
            current_db,
            context,
            class_id=class_id,
            course_id=course_id,
            bimestres=bimestres,
            academic_year=year,
            student_series=student_series,
        )

    base_router._dvd_phase5_installed = True
    return base_router
