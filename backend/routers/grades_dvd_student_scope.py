"""Paridade segura da aba ``Por Estudante`` para professor DVD.

A tela histórica de Notas agregava estudantes em escopo amplo e o endpoint
``/grades/by-student/{id}`` não resolvia autorização por componente. Este
adaptador mantém o comportamento legado para demais perfis e, para professor:

- expõe um roster derivado somente dos vínculos avaliativos autorizados;
- exige que o estudante pertença a uma turma do professor;
- resolve um ``assignment_id`` próprio por turma/componente;
- aplica a mesma projeção histórica read-only do PR #53;
- nunca grava ``grades`` e não cria ownership.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Optional

from fastapi import HTTPException, Request

from auth_middleware import AuthMiddleware
from routers.grades_dvd_parity import (
    _decorate_context_with_legacy_history,
    _project_grade_for_assignment,
)
from services.grade_assignment_scope import (
    GradeAssignmentContext,
    GradeAssignmentScopeError,
    resolve_grade_assignment,
)
from services.teacher_grade_access import (
    TeacherGradeAccessError,
    TeacherGradeScope,
    ensure_teacher_student_grade_access,
    list_teacher_grade_roster,
)
from tenant_scope import get_mantenedora_scope


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


def _db_for_user(db, sandbox_db, user: Mapping[str, Any]):
    if user.get("is_sandbox"):
        return sandbox_db if sandbox_db is not None else db
    return db


def _http_teacher_scope_error(exc: TeacherGradeAccessError) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"code": exc.code, "message": exc.message},
    )


async def _resolve_unique_grade_context(
    current_db,
    user: Mapping[str, Any],
    scopes: list[TeacherGradeScope],
    *,
    class_id: str,
    course_id: str,
    academic_year: int,
    active_mantenedora_id: Optional[str],
) -> Optional[GradeAssignmentContext]:
    """Resolve o único vínculo autorizado para uma linha da aba Por Estudante."""
    on_date = date.today().isoformat()
    candidates = [
        scope
        for scope in scopes
        if scope.class_id == class_id
        and scope.component_id in (None, course_id)
    ]

    contexts: list[GradeAssignmentContext] = []
    for scope in candidates:
        try:
            context = await resolve_grade_assignment(
                current_db,
                user,
                scope.assignment_id,
                class_id=class_id,
                course_id=course_id,
                on_date=on_date,
                active_mantenedora_id=active_mantenedora_id,
            )
        except GradeAssignmentScopeError:
            continue
        context = await _decorate_context_with_legacy_history(
            current_db,
            context,
            academic_year,
        )
        contexts.append(context)

    if len(contexts) > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "GRADE_STUDENT_SCOPE_AMBIGUOUS",
                "message": (
                    "Há mais de um vínculo avaliativo autorizado para este "
                    "estudante/componente; a gestão deve reconciliar a responsabilidade."
                ),
            },
        )
    return contexts[0] if contexts else None


async def _student_series_by_class(
    current_db,
    *,
    student_id: str,
    class_ids: set[str],
) -> dict[str, str]:
    rows = await current_db.enrollments.find(
        {
            "student_id": student_id,
            "class_id": {"$in": list(class_ids)},
            "status": "active",
        },
        {"_id": 0, "class_id": 1, "student_series": 1},
    ).to_list(100)
    return {
        str(row.get("class_id")): str(row.get("student_series") or "")
        for row in rows
        if row.get("class_id")
    }


def install_grades_dvd_student_scope(base_router, db, *, sandbox_db=None):
    if getattr(base_router, "_dvd_grades_student_scope_installed", False):
        return base_router

    original_by_student = _remove_route(
        base_router,
        "/grades/by-student/{student_id}",
        "GET",
    )
    if original_by_student is None:
        raise RuntimeError("Rota /grades/by-student não encontrada para hardening DVD")

    @base_router.get("/dvd/teacher-students")
    async def dvd_teacher_students(
        request: Request,
        academic_year: Optional[int] = None,
    ):
        user = await AuthMiddleware.require_roles(["professor"])(request)
        current_db = _db_for_user(db, sandbox_db, user)
        year = int(academic_year or datetime.now().year)
        roster = await list_teacher_grade_roster(
            current_db,
            user,
            academic_year=year,
            active_mantenedora_id=get_mantenedora_scope(user, request),
        )
        # Shape compatível com studentsAPI.getAll usado pela busca atual.
        return {
            "items": roster,
            "total": len(roster),
            "page": 1,
            "page_size": len(roster),
            "academic_year": year,
            "scope": "teacher_grade_roster",
        }

    @base_router.get("/by-student/{student_id}")
    async def dvd_scoped_by_student(
        student_id: str,
        request: Request,
        academic_year: Optional[int] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") != "professor":
            return await original_by_student(student_id, request, academic_year)

        current_db = _db_for_user(db, sandbox_db, user)
        year = int(academic_year or datetime.now().year)
        tenant_id = get_mantenedora_scope(user, request)

        try:
            scopes, memberships = await ensure_teacher_student_grade_access(
                current_db,
                user,
                student_id=student_id,
                academic_year=year,
                active_mantenedora_id=tenant_id,
            )
        except TeacherGradeAccessError as exc:
            raise _http_teacher_scope_error(exc) from exc

        student = await current_db.students.find_one(
            {"id": student_id},
            {
                "_id": 0,
                "id": 1,
                "full_name": 1,
                "cpf": 1,
                "enrollment_number": 1,
                "student_series": 1,
                "class_id": 1,
                "status": 1,
            },
        )
        if not student:
            raise HTTPException(status_code=404, detail="Estudante não encontrado")

        series_by_class = await _student_series_by_class(
            current_db,
            student_id=student_id,
            class_ids=memberships,
        )

        raw_grades = await current_db.grades.find(
            {
                "student_id": student_id,
                "academic_year": {"$in": [year, str(year)]},
                "class_id": {"$in": list(memberships)},
            },
            {"_id": 0},
        ).to_list(1000)

        class_cache: dict[str, dict[str, Any]] = {}
        course_cache: dict[str, dict[str, Any]] = {}
        visible: list[dict[str, Any]] = []

        for grade in raw_grades:
            class_id = str(grade.get("class_id") or "")
            course_id = str(grade.get("course_id") or "")
            if not class_id or not course_id:
                continue

            context = await _resolve_unique_grade_context(
                current_db,
                user,
                scopes,
                class_id=class_id,
                course_id=course_id,
                academic_year=year,
                active_mantenedora_id=tenant_id,
            )
            if context is None:
                # Campo de componente não lecionado não aparece na visão docente.
                continue

            projected = _project_grade_for_assignment(grade, context)

            if class_id not in class_cache:
                class_cache[class_id] = await current_db.classes.find_one(
                    {"id": class_id},
                    {
                        "_id": 0,
                        "id": 1,
                        "name": 1,
                        "grade_level": 1,
                        "education_level": 1,
                        "nivel_ensino": 1,
                        "is_multi_grade": 1,
                    },
                ) or {}
            if course_id not in course_cache:
                course_cache[course_id] = await current_db.courses.find_one(
                    {"id": course_id},
                    {"_id": 0, "id": 1, "name": 1},
                ) or {}

            class_info = class_cache[class_id]
            student_series = series_by_class.get(class_id) or student.get("student_series")
            projected.update(
                {
                    "course_name": course_cache[course_id].get("name", "N/A"),
                    "class_name": class_info.get("name", ""),
                    "grade_level": student_series or class_info.get("grade_level", ""),
                    "education_level": (
                        class_info.get("education_level")
                        or class_info.get("nivel_ensino")
                        or ""
                    ),
                    "student_series": student_series,
                    "is_multi_grade": bool(class_info.get("is_multi_grade")),
                }
            )
            visible.append(projected)

        visible.sort(
            key=lambda item: (
                (item.get("class_name") or "").casefold(),
                (item.get("course_name") or "").casefold(),
                item.get("course_id") or "",
            )
        )

        return {
            "student": {
                **student,
                "authorized_class_ids": sorted(memberships),
            },
            "grades": visible,
            "academic_year": year,
            "scope": "teacher_grade_assignments",
        }

    base_router._dvd_grades_student_scope_installed = True
    return base_router
