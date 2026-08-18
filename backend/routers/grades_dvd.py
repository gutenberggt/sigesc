"""Adaptador de Notas/Conceitos por Vínculo Docente — DVD Fase 5.

Mantém ``Grades.js``, ``/grades`` e o gerador PDF existentes. O backend deriva o
assignment do professor quando ele é unívoco; ``assignment_id`` explícito é
sempre revalidado e nunca confiado como autoria.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional
import uuid

from fastapi import HTTPException, Query, Request
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
    }
    status_code = 409 if exc.code in conflict_codes else 403
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def _remove_route(base_router, path: str, method: str):
    for route in list(base_router.routes):
        if getattr(route, "path", None) == path and method.upper() in (getattr(route, "methods", set()) or set()):
            endpoint = route.endpoint
            base_router.routes.remove(route)
            return endpoint
    return None


async def _calendar_periods(current_db, academic_year: int) -> dict[int, tuple[str, str]]:
    """Mesmos períodos/fallback já usados pelo router histórico de notas."""
    calendario = await get_mantenedora_cached(current_db)
    fallback = {
        1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
        2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
        3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
        4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
    }
    result = {}
    for b in (1, 2, 3, 4):
        ini = (calendario or {}).get(f"bimestre_{b}_inicio")
        fim = (calendario or {}).get(f"bimestre_{b}_fim")
        result[b] = (
            str(ini)[:10] if ini else fallback[b][0],
            str(fim)[:10] if fim else fallback[b][1],
        )
    return result


async def _class_has_dvd_grades(current_db, class_id: str, course_id: str, academic_year: int) -> bool:
    docs = await current_db.teacher_class_assignments.find(
        {
            "class_id": class_id,
            "deleted": False,
            "diary_settings.enabled": True,
            "diary_settings.profile": {"$in": [DiaryProfile.REGULAR.value, DiaryProfile.SHARED.value]},
            "valid_from": {"$lte": f"{academic_year}-12-31"},
            "$or": [{"valid_until": None}, {"valid_until": {"$gte": f"{academic_year}-01-01"}}],
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
            raise _http_scope_error(GradeAssignmentScopeError(
                "DVD_ASSIGNMENT_REQUIRED",
                "Esta avaliação usa Diário por Vínculo e não existe um vínculo próprio unívoco para o usuário.",
            ))
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
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
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


async def _save_one_dvd_grade(
    current_db,
    user: Mapping[str, Any],
    request: Request,
    context: GradeAssignmentContext,
    payload: Mapping[str, Any],
) -> tuple[dict, Optional[dict]]:
    """Salva um estudante e retorna (grade atualizada, mudança auditável)."""
    if payload.get("class_id") != context.class_id or payload.get("course_id") != context.course_id:
        raise _http_scope_error(GradeAssignmentScopeError(
            "GRADE_BATCH_SCOPE_MISMATCH",
            "Todos os dados do lote devem pertencer à turma/componente do vínculo.",
        ))
    await _validate_dependency(current_db, user, request, payload)
    await _validate_academic_event(current_db, user, request, payload)

    from routers.grades import (
        _strip_frozen_grade_fields,
        calculate_and_update_grade,
    )

    key = {
        "student_id": payload["student_id"],
        "class_id": payload["class_id"],
        "course_id": payload["course_id"],
        "academic_year": payload["academic_year"],
    }
    existing = await current_db.grades.find_one(key, {"_id": 0})
    grade_keys = list(GRADE_OWNERSHIP_FIELDS)
    update_fields = {k: payload.get(k) for k in grade_keys if k in payload}
    if existing:
        update_fields = _strip_frozen_grade_fields(
            update_fields, existing, str(user.get("role") or "")
        )
    changes = changed_grade_fields(existing, update_fields)
    if existing and not changes:
        return existing, None

    periods = await _calendar_periods(current_db, int(payload["academic_year"]))
    try:
        grade_ownership = await apply_grade_field_ownership(
            current_db,
            user,
            existing,
            changes,
            context,
            periods=periods,
            allow_management_override=user.get("role") in MANAGEMENT_WRITE_ROLES and not context.access.is_owner,
            active_mantenedora_id=get_mantenedora_scope(user, request),
        )
    except GradeAssignmentScopeError as exc:
        raise _http_scope_error(exc) from exc

    now = datetime.now(timezone.utc).isoformat()
    if existing:
        set_data = dict(changes)
        set_data.update({
            "grade_ownership": grade_ownership,
            "updated_at": now,
            "updated_by": user.get("id"),
            "last_updated_by": user.get("id"),
        })
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


def _annotate_grade(grade: Mapping[str, Any], context: GradeAssignmentContext) -> dict:
    out = dict(grade)
    owned = sorted(owned_fields_for_assignment(out, context.assignment_id))
    locked = sorted(
        field for field in GRADE_OWNERSHIP_FIELDS
        if out.get(field) is not None and field not in owned
    )
    out["dvd_assignment_id"] = context.assignment_id
    out["dvd_owned_fields"] = owned
    out["dvd_locked_fields"] = locked
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
        {"id": class_id, "mantenedora_id": tenant_id}, {"_id": 0}
    )
    course = await current_db.courses.find_one(
        {"id": course_id, "mantenedora_id": tenant_id}, {"_id": 0}
    )
    if not class_info:
        raise HTTPException(status_code=404, detail="Turma do vínculo não encontrada")
    if not course:
        raise HTTPException(status_code=404, detail="Componente do vínculo não encontrado")
    school = await current_db.schools.find_one(
        {"id": context.snapshot.get("school_id"), "mantenedora_id": tenant_id}, {"_id": 0}
    ) or {"name": ""}
    mantenedora = await current_db.mantenedoras.find_one(
        {"id": tenant_id}, {"_id": 0}
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
        for item in enrollments if item.get("student_id")
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
            {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1, "student_series": 1},
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)

    if student_series:
        from utils.serie_canonical import canonicalize_serie

        def _series_match(a, b):
            ca, cb = canonicalize_serie(a or ""), canonicalize_serie(b or "")
            if ca and cb:
                return ca == cb
            return (a or "").strip().lower() == (b or "").strip().lower()

        students = [
            student for student in students
            if _series_match(
                enrollment_map.get(student["id"], {}).get("student_series") or student.get("student_series"),
                student_series,
            )
        ]

    grades = await current_db.grades.find(
        {"class_id": class_id, "course_id": course_id, "academic_year": academic_year},
        {"_id": 0},
    ).to_list(1000)
    grades_map = {grade.get("student_id"): grade for grade in grades}
    students_data = []
    for student in students:
        grade = grades_map.get(student["id"], {})
        owned = owned_fields_for_assignment(grade, context.assignment_id)
        students_data.append({
            "full_name": student.get("full_name", ""),
            "enrollment_number": enrollment_map.get(student["id"], {}).get("enrollment_number") or student.get("enrollment_number", ""),
            **{field: grade.get(field) if field in owned else None for field in GRADE_VALUE_FIELDS},
            # Média/status são derivados pelo sistema; não recebem autoria manual.
            "final_average": grade.get("final_average"),
            "status": grade.get("status", "cursando"),
        })

    bims = [int(value.strip()) for value in bimestres.split(",") if value.strip().isdigit()]
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

    legacy_list = _remove_route(base_router, "/grades", "GET")
    legacy_by_class = _remove_route(base_router, "/grades/by-class/{class_id}/{course_id}", "GET")
    legacy_by_student = _remove_route(base_router, "/grades/by-student/{student_id}", "GET")
    legacy_create = _remove_route(base_router, "/grades", "POST")
    legacy_update = _remove_route(base_router, "/grades/{grade_id}", "PUT")
    legacy_batch = _remove_route(base_router, "/grades/batch", "POST")
    legacy_pdf = _remove_route(base_router, "/grades/pdf/{class_id}/{course_id}", "GET")

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
            raise HTTPException(status_code=403, detail={"code": exc.code, "message": exc.message}) from exc
        if access.settings.profile is not DiaryProfile.SHARED:
            raise HTTPException(status_code=422, detail={
                "code": "GRADE_OWNER_REQUIRES_SHARED",
                "message": "Responsável oficial explícito é configurável apenas para profile=shared.",
            })
        component_id = access.assignment.get("component_id")
        peer_filter: dict[str, Any] = {
            "class_id": access.assignment.get("class_id"),
            "deleted": False,
            "diary_settings.enabled": True,
            "diary_settings.profile": DiaryProfile.SHARED.value,
        }
        if component_id is None:
            pass
        else:
            peer_filter["$or"] = [{"component_id": component_id}, {"component_id": None}]
        await current_db.teacher_class_assignments.update_many(
            peer_filter,
            {"$set": {"grades_official_owner": False}},
        )
        await current_db.teacher_class_assignments.update_one(
            {"id": assignment_id},
            {"$set": {
                "grades_official_owner": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": user.get("id"),
            }},
        )
        await audit_service.log(
            action="update",
            collection="teacher_class_assignments",
            user=user,
            request=request,
            document_id=assignment_id,
            description="Definiu vínculo shared como responsável oficial pela avaliação",
            school_id=access.class_info.get("school_id"),
            extra_data={"grades_official_owner": True, "component_id": component_id},
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
        if class_id and course_id:
            context = await _context_or_legacy(
                current_db, user, request,
                class_id=class_id, course_id=course_id, academic_year=year,
                assignment_id=assignment_id,
            )
            result = await legacy_list(request, student_id, class_id, course_id, academic_year)
            if context:
                return [_annotate_grade(grade, context) for grade in result]
            return result
        return await legacy_list(request, student_id, class_id, course_id, academic_year)

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
            current_db, user, request,
            class_id=class_id, course_id=course_id, academic_year=year,
            assignment_id=assignment_id,
        )
        result = await legacy_by_class(class_id, course_id, request, academic_year)
        if not context:
            return result
        for item in result:
            if item.get("grade"):
                item["grade"] = _annotate_grade(item["grade"], context)
        return result

    @base_router.get("/by-student/{student_id}")
    async def dvd_aware_by_student(
        student_id: str,
        request: Request,
        academic_year: Optional[int] = None,
    ):
        # Mantém a consulta consolidada para continuidade pedagógica. Escritas
        # subsequentes continuam protegidas por campo no PUT/POST.
        return await legacy_by_student(student_id, request, academic_year)

    @base_router.post("")
    async def dvd_aware_create(
        grade_data: GradeCreate,
        request: Request,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.require_roles([
            "admin", "admin_teste", "secretario", "professor", "coordenador", "auxiliar_secretaria", "apoio_pedagogico"
        ])(request)
        current_db = _db_for_user(db, sandbox_db, user)
        payload = grade_data.model_dump()
        context = await _context_or_legacy(
            current_db, user, request,
            class_id=payload["class_id"], course_id=payload["course_id"],
            academic_year=payload["academic_year"], assignment_id=assignment_id,
        )
        if not context:
            return await legacy_create(grade_data, request)
        updated, change = await _save_one_dvd_grade(current_db, user, request, context, payload)
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
                extra_data={"assignment_id": context.assignment_id, "change": change},
            )
        return updated

    @base_router.put("/{grade_id}")
    async def dvd_aware_update(
        grade_id: str,
        grade_update: GradeUpdate,
        request: Request,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.require_roles([
            "admin", "admin_teste", "secretario", "professor", "coordenador", "auxiliar_secretaria", "apoio_pedagogico"
        ])(request)
        current_db = _db_for_user(db, sandbox_db, user)
        existing = await current_db.grades.find_one({"id": grade_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Nota não encontrada")
        context = await _context_or_legacy(
            current_db, user, request,
            class_id=existing["class_id"], course_id=existing["course_id"],
            academic_year=existing["academic_year"], assignment_id=assignment_id,
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
        updated, change = await _save_one_dvd_grade(current_db, user, request, context, payload)
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
                extra_data={"assignment_id": context.assignment_id, "change": change},
            )
        return updated

    @base_router.post("/batch")
    async def dvd_aware_batch(
        request: Request,
        grades: list[dict],
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.require_roles([
            "admin", "admin_teste", "secretario", "professor", "coordenador", "auxiliar_secretaria", "apoio_pedagogico"
        ])(request)
        current_db = _db_for_user(db, sandbox_db, user)
        if not grades:
            return await legacy_batch(request, grades)
        first = grades[0]
        context = await _context_or_legacy(
            current_db, user, request,
            class_id=first["class_id"], course_id=first["course_id"],
            academic_year=first["academic_year"], assignment_id=assignment_id,
        )
        if not context:
            return await legacy_batch(request, grades)

        for row in grades:
            if (
                row.get("class_id") != context.class_id
                or row.get("course_id") != context.course_id
                or row.get("academic_year") != first.get("academic_year")
            ):
                raise _http_scope_error(GradeAssignmentScopeError(
                    "GRADE_BATCH_SCOPE_MISMATCH",
                    "Lote DVD deve conter uma única turma, componente e ano letivo.",
                ))

        role = str(user.get("role") or "")
        if role not in {"admin", "admin_teste", "super_admin", "gerente"} and verify_academic_year_open_or_raise:
            await verify_academic_year_open_or_raise(
                context.snapshot.get("school_id"), first["academic_year"]
            )
        if role not in {"admin", "admin_teste", "super_admin", "gerente", "secretario"} and verify_bimestre_edit_deadline_or_raise:
            bimestres = set()
            for row in grades:
                for field in ("b1", "b2", "b3", "b4"):
                    if row.get(field) is not None:
                        bimestres.add(int(field[1]))
            for bimestre in bimestres:
                await verify_bimestre_edit_deadline_or_raise(first["academic_year"], bimestre, role)

        results = []
        changes = []
        for row in grades:
            updated, change = await _save_one_dvd_grade(current_db, user, request, context, row)
            results.append(updated)
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
            current_db, user, request,
            class_id=class_id, course_id=course_id, academic_year=year,
            assignment_id=assignment_id,
        )
        if not context:
            return await legacy_pdf(
                class_id, course_id, request, bimestres, academic_year, student_series
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
