"""Escopo canônico de acesso avaliativo do professor.

Esta camada é deliberadamente read-only. Ela deriva, a partir dos
``teacher_class_assignments`` e do autorizador do Diário por Vínculo, quais
turmas/estudantes podem compor Notas e Boletim de um professor em determinado
ano letivo.

Invariantes:
- nunca aceita ``teacher_id`` arbitrário; usa somente ``current_user.id``;
- somente vínculos com capability GRADES são considerados;
- o vínculo precisa intersectar o ano letivo solicitado;
- shared/group permanece fail-closed;
- shared/all exige ``grades_official_owner=true``;
- roster atual usa matrícula/dependência ativa; histórico exige evidência do
  próprio ano (matrícula com academic_year ou documento canônico em ``grades``);
- nenhuma coleção é alterada por este módulo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional

from services.diary_assignment_access import (
    DiaryAction,
    DiaryAssignmentAccessError,
    authorize_assignment_access,
)
from services.diary_assignment_contract import DiaryProfile, StudentScope


class TeacherGradeAccessError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TeacherGradeScope:
    assignment_id: str
    class_id: str
    component_id: Optional[str]
    school_id: str
    mantenedora_id: str
    profile: str
    student_scope: str
    valid_from: Optional[str]
    valid_until: Optional[str]


def _year_bounds(academic_year: int) -> tuple[str, str]:
    return f"{int(academic_year):04d}-01-01", f"{int(academic_year):04d}-12-31"


def _assignment_authorization_date(
    assignment: Mapping[str, Any],
    academic_year: int,
    reference_date: Optional[str] = None,
) -> Optional[str]:
    """Escolhe uma data que prove a interseção vínculo × ano solicitado."""
    year_start, year_end = _year_bounds(academic_year)
    valid_from = str(assignment.get("valid_from") or "")[:10]
    valid_until = str(assignment.get("valid_until") or "")[:10] or None
    if not valid_from:
        return None

    if reference_date:
        ref = str(reference_date)[:10]
        if not (year_start <= ref <= year_end):
            return None
        if valid_from <= ref and (valid_until is None or ref <= valid_until):
            return ref
        return None

    overlap_start = max(valid_from, year_start)
    overlap_end = min(valid_until or year_end, year_end)
    return overlap_start if overlap_start <= overlap_end else None


def _year_or_current_operational_filter(academic_year: int) -> list[dict[str, Any]]:
    """Evidência histórica explícita; fallback ativo somente no ano corrente."""
    options: list[dict[str, Any]] = [
        {"academic_year": {"$in": [int(academic_year), str(int(academic_year))]}},
    ]
    if int(academic_year) == date.today().year:
        options.append({"status": "active"})
    return options


async def list_teacher_grade_scopes(
    db,
    current_user: Mapping[str, Any],
    *,
    academic_year: int,
    active_mantenedora_id: Optional[str] = None,
    reference_date: Optional[str] = None,
) -> list[TeacherGradeScope]:
    """Lista vínculos avaliativos do professor que intersectam o ano solicitado."""
    teacher_id = str(current_user.get("id") or "")
    if not teacher_id:
        return []

    year_start, year_end = _year_bounds(academic_year)
    candidates = await db.teacher_class_assignments.find(
        {
            "teacher_id": teacher_id,
            "deleted": {"$ne": True},
            "diary_settings.enabled": True,
            "valid_from": {"$lte": year_end},
            "$or": [
                {"valid_until": None},
                {"valid_until": {"$gte": year_start}},
            ],
        },
        {
            "_id": 0,
            "id": 1,
            "class_id": 1,
            "component_id": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "valid_from": 1,
            "valid_until": 1,
            "grades_official_owner": 1,
            "diary_settings": 1,
        },
    ).to_list(1000)

    scopes: list[TeacherGradeScope] = []
    for assignment in candidates:
        assignment_id = assignment.get("id")
        class_id = assignment.get("class_id")
        if not assignment_id or not class_id:
            continue

        authorization_date = _assignment_authorization_date(
            assignment,
            academic_year,
            reference_date,
        )
        if not authorization_date:
            continue

        try:
            access = await authorize_assignment_access(
                db,
                current_user,
                assignment_id,
                action=DiaryAction.GRADES,
                on_date=authorization_date,
                expected_class_id=class_id,
                active_mantenedora_id=active_mantenedora_id,
            )
        except DiaryAssignmentAccessError:
            # Candidato inconsistente ou sem capability não amplia escopo.
            continue

        profile = access.settings.profile
        student_scope = access.settings.student_scope
        if profile is DiaryProfile.SHARED:
            if student_scope is StudentScope.GROUP:
                continue
            if assignment.get("grades_official_owner") is not True:
                continue

        class_info = access.class_info
        tenant_id = (
            class_info.get("mantenedora_id")
            or assignment.get("mantenedora_id")
        )
        school_id = class_info.get("school_id") or assignment.get("school_id")
        if not tenant_id or not school_id:
            continue

        scopes.append(
            TeacherGradeScope(
                assignment_id=str(assignment_id),
                class_id=str(class_id),
                component_id=(
                    str(assignment.get("component_id"))
                    if assignment.get("component_id") is not None
                    else None
                ),
                school_id=str(school_id),
                mantenedora_id=str(tenant_id),
                profile=profile.value,
                student_scope=student_scope.value,
                valid_from=(str(assignment.get("valid_from"))[:10] if assignment.get("valid_from") else None),
                valid_until=(str(assignment.get("valid_until"))[:10] if assignment.get("valid_until") else None),
            )
        )

    scopes.sort(
        key=lambda item: (
            item.school_id,
            item.class_id,
            item.component_id or "",
            item.assignment_id,
        )
    )
    return scopes


async def _student_membership(
    db,
    *,
    student_id: str,
    class_ids: set[str],
    academic_year: int,
) -> set[str]:
    """Turmas autorizadas comprovadas por operação atual ou histórico do ano."""
    if not class_ids:
        return set()

    memberships: set[str] = set()
    class_values = list(class_ids)

    enrollments = await db.enrollments.find(
        {
            "student_id": student_id,
            "class_id": {"$in": class_values},
            "$or": _year_or_current_operational_filter(academic_year),
        },
        {"_id": 0, "class_id": 1},
    ).to_list(500)
    memberships.update(
        str(item.get("class_id"))
        for item in enrollments
        if item.get("class_id")
    )

    # Documento avaliativo no próprio ano é evidência histórica forte da turma,
    # inclusive após transferência/remanejamento, sem depender do status atual.
    grade_rows = await db.grades.find(
        {
            "student_id": student_id,
            "class_id": {"$in": class_values},
            "academic_year": {"$in": [int(academic_year), str(int(academic_year))]},
        },
        {"_id": 0, "class_id": 1},
    ).to_list(500)
    memberships.update(
        str(item.get("class_id"))
        for item in grade_rows
        if item.get("class_id")
    )

    dependencies = await db.student_dependencies.find(
        {
            "student_id": student_id,
            "class_id": {"$in": class_values},
            "$or": _year_or_current_operational_filter(academic_year),
        },
        {"_id": 0, "class_id": 1},
    ).to_list(500)
    memberships.update(
        str(item.get("class_id"))
        for item in dependencies
        if item.get("class_id")
    )

    # Compatibilidade com cadastros correntes antigos sem enrollment operacional.
    # Nunca é usado para anos históricos/futuros.
    if int(academic_year) == date.today().year:
        student = await db.students.find_one(
            {
                "id": student_id,
                "class_id": {"$in": class_values},
                "status": {"$in": ["active", "Ativo"]},
            },
            {"_id": 0, "class_id": 1},
        )
        if student and student.get("class_id"):
            memberships.add(str(student.get("class_id")))

    return memberships


async def ensure_teacher_student_grade_access(
    db,
    current_user: Mapping[str, Any],
    *,
    student_id: str,
    academic_year: int,
    active_mantenedora_id: Optional[str] = None,
    reference_date: Optional[str] = None,
) -> tuple[list[TeacherGradeScope], set[str]]:
    """Falha fechado se o estudante não pertence ao escopo avaliativo docente."""
    scopes = await list_teacher_grade_scopes(
        db,
        current_user,
        academic_year=academic_year,
        active_mantenedora_id=active_mantenedora_id,
        reference_date=reference_date,
    )
    class_ids = {scope.class_id for scope in scopes}
    memberships = await _student_membership(
        db,
        student_id=student_id,
        class_ids=class_ids,
        academic_year=academic_year,
    )
    if not memberships:
        raise TeacherGradeAccessError(
            "TEACHER_STUDENT_GRADE_SCOPE_DENIED",
            "O estudante não pertence às turmas avaliativas autorizadas deste professor neste ano letivo.",
        )

    scoped = [scope for scope in scopes if scope.class_id in memberships]
    if not scoped:
        raise TeacherGradeAccessError(
            "TEACHER_STUDENT_GRADE_SCOPE_DENIED",
            "Não existe vínculo avaliativo autorizado para este estudante neste ano letivo.",
        )
    return scoped, memberships


def _add_roster_row(
    by_student: dict[str, dict[str, Any]],
    *,
    student_id: Any,
    class_id: Any,
    enrollment_number: Any = None,
    student_series: Any = None,
) -> None:
    if not student_id or not class_id:
        return
    item = by_student.setdefault(
        str(student_id),
        {
            "authorized_class_ids": set(),
            "enrollment_number": enrollment_number,
            "student_series": student_series,
        },
    )
    item["authorized_class_ids"].add(str(class_id))
    if not item.get("enrollment_number") and enrollment_number:
        item["enrollment_number"] = enrollment_number
    if not item.get("student_series") and student_series:
        item["student_series"] = student_series


async def list_teacher_grade_roster(
    db,
    current_user: Mapping[str, Any],
    *,
    academic_year: int,
    active_mantenedora_id: Optional[str] = None,
    reference_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Roster do professor limitado ao ano e às turmas de seus vínculos."""
    scopes = await list_teacher_grade_scopes(
        db,
        current_user,
        academic_year=academic_year,
        active_mantenedora_id=active_mantenedora_id,
        reference_date=reference_date,
    )
    class_ids = {scope.class_id for scope in scopes}
    if not class_ids:
        return []
    class_values = list(class_ids)

    enrollment_rows = await db.enrollments.find(
        {
            "class_id": {"$in": class_values},
            "$or": _year_or_current_operational_filter(academic_year),
        },
        {
            "_id": 0,
            "student_id": 1,
            "class_id": 1,
            "enrollment_number": 1,
            "student_series": 1,
        },
    ).to_list(10000)

    dependency_rows = await db.student_dependencies.find(
        {
            "class_id": {"$in": class_values},
            "$or": _year_or_current_operational_filter(academic_year),
        },
        {"_id": 0, "student_id": 1, "class_id": 1},
    ).to_list(5000)

    grade_rows = await db.grades.find(
        {
            "class_id": {"$in": class_values},
            "academic_year": {"$in": [int(academic_year), str(int(academic_year))]},
        },
        {"_id": 0, "student_id": 1, "class_id": 1},
    ).to_list(20000)

    by_student: dict[str, dict[str, Any]] = {}
    for row in enrollment_rows:
        _add_roster_row(
            by_student,
            student_id=row.get("student_id"),
            class_id=row.get("class_id"),
            enrollment_number=row.get("enrollment_number"),
            student_series=row.get("student_series"),
        )
    for row in dependency_rows:
        _add_roster_row(
            by_student,
            student_id=row.get("student_id"),
            class_id=row.get("class_id"),
        )
    for row in grade_rows:
        _add_roster_row(
            by_student,
            student_id=row.get("student_id"),
            class_id=row.get("class_id"),
        )

    # Fallback corrente para registros legados que guardam turma no estudante.
    if int(academic_year) == date.today().year:
        direct_students = await db.students.find(
            {
                "class_id": {"$in": class_values},
                "status": {"$in": ["active", "Ativo"]},
            },
            {
                "_id": 0,
                "id": 1,
                "class_id": 1,
                "enrollment_number": 1,
                "student_series": 1,
            },
        ).to_list(10000)
        for row in direct_students:
            _add_roster_row(
                by_student,
                student_id=row.get("id"),
                class_id=row.get("class_id"),
                enrollment_number=row.get("enrollment_number"),
                student_series=row.get("student_series"),
            )

    student_ids = list(by_student)
    if not student_ids:
        return []

    students = await db.students.find(
        {"id": {"$in": student_ids}},
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
    ).to_list(10000)

    result: list[dict[str, Any]] = []
    for student in students:
        sid = str(student.get("id") or "")
        meta = by_student.get(sid)
        if not sid or not meta:
            continue
        authorized = sorted(meta["authorized_class_ids"])
        result.append(
            {
                "id": sid,
                "full_name": student.get("full_name") or "",
                "cpf": student.get("cpf"),
                "enrollment_number": (
                    meta.get("enrollment_number")
                    or student.get("enrollment_number")
                ),
                "student_series": (
                    meta.get("student_series")
                    or student.get("student_series")
                ),
                # Compatibilidade com a UI antiga quando há uma única turma.
                "class_id": authorized[0] if len(authorized) == 1 else None,
                "authorized_class_ids": authorized,
                "status": student.get("status"),
            }
        )

    result.sort(key=lambda item: (item.get("full_name") or "").casefold())
    return result
