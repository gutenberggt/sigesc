from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.teacher_assignment_integrity import (  # noqa: E402
    TeacherAssignmentIntegrityError,
    is_active_teacher_assignment_status,
    validate_teacher_assignment_workload,
)


def _class(**overrides) -> dict:
    row = {
        "school_id": "school-1",
        "academic_year": 2026,
        "education_level": "eja_final",
        "grade_level": "EJA 3ª ETAPA",
        "series": ["EJA 3ª ETAPA", "EJA 4ª ETAPA"],
    }
    row.update(overrides)
    return row


def _course(name: str = "Geografia", **overrides) -> dict:
    row = {
        "id": "course-1",
        "name": name,
        "nivel_ensino": "eja_final",
        "grade_levels": [],
        "carga_horaria_por_serie": {},
    }
    row.update(overrides)
    return row


def test_eja_final_geografia_requires_canonical_two_weekly_hours() -> None:
    result = validate_teacher_assignment_workload(
        class_info=_class(),
        course=_course("Geografia"),
        weekly_workload=2,
    )
    assert result["allowed"] is True
    assert result["workload_policy"] == "CANONICAL_WEEKLY_WORKLOAD_MATCH"
    assert result["canonical_weekly_workload"] == 2
    assert result["workload"]["canonical_annual_workload"] == 80


def test_eja_final_geografia_rejects_three_weekly_hours() -> None:
    with pytest.raises(TeacherAssignmentIntegrityError) as exc:
        validate_teacher_assignment_workload(
            class_info=_class(),
            course=_course("Geografia"),
            weekly_workload=3,
        )
    assert exc.value.code == "TEACHER_ASSIGNMENT_WEEKLY_WORKLOAD_MISMATCH"
    assert exc.value.fit["actual_weekly_workload"] == 3
    assert exc.value.fit["expected_weekly_workload"] == 2


def test_supported_component_requires_weekly_workload() -> None:
    with pytest.raises(TeacherAssignmentIntegrityError) as exc:
        validate_teacher_assignment_workload(
            class_info=_class(),
            course=_course("História"),
            weekly_workload=None,
        )
    assert exc.value.code == "TEACHER_ASSIGNMENT_WEEKLY_WORKLOAD_REQUIRED"


def test_multigrade_fundamental_uses_max_annual_workload() -> None:
    class_info = _class(
        education_level="fundamental_anos_finais",
        grade_level="6º ANO",
        series=["6º ANO", "7º ANO"],
    )
    course = _course("Geografia", nivel_ensino="fundamental_anos_finais")

    result = validate_teacher_assignment_workload(
        class_info=class_info,
        course=course,
        weekly_workload="3",
    )
    assert result["canonical_weekly_workload"] == 3
    assert result["workload"]["canonical_annual_workload"] == 120
    assert result["workload"]["multigrade"] is True
    assert result["workload"]["multigrade_rule"] == "MAX_ANNUAL_WORKLOAD"


def test_component_outside_workload_policy_preserves_existing_behavior() -> None:
    result = validate_teacher_assignment_workload(
        class_info=_class(),
        course=_course("Língua Portuguesa"),
        weekly_workload=None,
    )
    assert result["allowed"] is True
    assert result["workload_policy"] == "NOT_APPLICABLE"
    assert result["workload"]["applies"] is False


def test_policy_resolution_failure_is_translated_to_integrity_error() -> None:
    with pytest.raises(TeacherAssignmentIntegrityError) as exc:
        validate_teacher_assignment_workload(
            class_info=_class(education_level="educacao_infantil", series=[]),
            course=_course("Ciências", nivel_ensino="educacao_infantil"),
            weekly_workload=3,
        )
    assert exc.value.code == "TEACHER_ASSIGNMENT_WORKLOAD_POLICY_UNRESOLVED"
    assert exc.value.fit["workload_policy_error"] == "CURRICULAR_WORKLOAD_LEVEL_UNSUPPORTED"


@pytest.mark.parametrize("status", ["ativo", "active", " ATIVO ", "Active"])
def test_historical_active_status_tokens_are_recognized(status: str) -> None:
    assert is_active_teacher_assignment_status(status) is True


@pytest.mark.parametrize("status", ["inativo", "inactive", "encerrado", None, ""])
def test_non_active_statuses_are_not_treated_as_active(status) -> None:
    assert is_active_teacher_assignment_status(status) is False


def test_router_wires_workload_ssot_into_all_active_writer_paths() -> None:
    text = (BACKEND / "routers" / "assignments.py").read_text(encoding="utf-8")

    # Titular create, substitution and active update all use the domain guard.
    assert text.count("validate_teacher_assignment_workload(") >= 3
    assert "is_active_teacher_assignment_status(" in text

    # The router must not own or duplicate the curricular workload matrix.
    assert "curricular_workload_policy" not in text
    assert "MAX_ANNUAL_WORKLOAD" not in text
    assert "ha / 40" not in text

    # Both historical active tokens participate in duplicate/titular lookup.
    assert text.count('{"$in": ["ativo", "active"]}') >= 2

    # Substitution validates workload only after possible titular inheritance.
    inherit = text.index("payload['carga_horaria_semanal'] = titular_assign.get('carga_horaria_semanal')")
    workload = text.index("validate_teacher_assignment_workload(", inherit)
    assert workload > inherit

    # Historical inactivation remains available; hard delete remains blocked.
    assert "INACTIVE_REMEDIATION_ALLOWED" in text
    assert "TEACHER_ASSIGNMENT_HARD_DELETE_DISABLED_P0" in text
