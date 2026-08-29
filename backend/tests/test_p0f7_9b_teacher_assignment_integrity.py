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
    validate_teacher_assignment_curriculum,
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


def _course(**overrides) -> dict:
    row = {
        "id": "course-1",
        "name": "Língua Portuguesa",
        "nivel_ensino": "eja_final",
        "grade_levels": [],
        "carga_horaria_por_serie": {},
    }
    row.update(overrides)
    return row


def _validate(class_info: dict | None = None, course: dict | None = None):
    return validate_teacher_assignment_curriculum(
        class_info=class_info or _class(),
        course=course or _course(),
        school_id="school-1",
        academic_year=2026,
    )


def test_eja_level_course_without_series_scope_is_allowed() -> None:
    result = _validate()
    assert result["allowed"] is True
    assert result["write_policy"] == "LEVEL_MATCH_NO_SERIES_SCOPE"


def test_educacao_infantil_course_is_rejected_for_eja_final() -> None:
    with pytest.raises(TeacherAssignmentIntegrityError) as exc:
        _validate(course=_course(
            name="O Eu, O Outro e Nós",
            nivel_ensino="educacao_infantil",
        ))
    assert exc.value.code == "TEACHER_ASSIGNMENT_LEVEL_MISMATCH"
    assert exc.value.fit["classification"] == "LEVEL_MISMATCH"


def test_missing_explicit_class_level_is_fail_closed_even_when_grade_name_is_eja() -> None:
    class_info = _class(education_level=None, nivel_ensino=None)
    with pytest.raises(TeacherAssignmentIntegrityError) as exc:
        _validate(class_info=class_info)
    assert exc.value.code == "TEACHER_ASSIGNMENT_CLASS_LEVEL_REQUIRED"


def test_missing_course_level_is_fail_closed() -> None:
    with pytest.raises(TeacherAssignmentIntegrityError) as exc:
        _validate(course=_course(nivel_ensino=None))
    assert exc.value.code == "TEACHER_ASSIGNMENT_COURSE_LEVEL_REQUIRED"


def test_full_series_scope_is_allowed() -> None:
    result = _validate(course=_course(
        grade_levels=["EJA 3ª ETAPA", "EJA 4ª ETAPA"],
    ))
    assert result["allowed"] is True
    assert result["write_policy"] == "EXPLICIT_SERIES_FULL_MATCH"


def test_partial_multigrade_series_scope_is_rejected_for_review() -> None:
    with pytest.raises(TeacherAssignmentIntegrityError) as exc:
        _validate(course=_course(grade_levels=["EJA 3ª ETAPA"]))
    assert exc.value.code == "TEACHER_ASSIGNMENT_SERIES_SCOPE_REVIEW_REQUIRED"
    assert exc.value.fit["classification"] == "PARTIAL_EXPLICIT_SERIES_MATCH_REQUIRES_REVIEW"


def test_no_matching_series_is_rejected() -> None:
    with pytest.raises(TeacherAssignmentIntegrityError) as exc:
        _validate(course=_course(grade_levels=["EJA 2ª ETAPA"]))
    assert exc.value.code == "TEACHER_ASSIGNMENT_SERIES_MISMATCH"
    assert exc.value.fit["classification"] == "NO_SERIES_MATCH"


def test_school_mismatch_is_rejected_before_curricular_evaluation() -> None:
    with pytest.raises(TeacherAssignmentIntegrityError) as exc:
        validate_teacher_assignment_curriculum(
            class_info=_class(),
            course=_course(),
            school_id="school-other",
            academic_year=2026,
        )
    assert exc.value.code == "TEACHER_ASSIGNMENT_CLASS_SCHOOL_MISMATCH"


def test_academic_year_mismatch_is_rejected() -> None:
    with pytest.raises(TeacherAssignmentIntegrityError) as exc:
        validate_teacher_assignment_curriculum(
            class_info=_class(),
            course=_course(),
            school_id="school-1",
            academic_year=2025,
        )
    assert exc.value.code == "TEACHER_ASSIGNMENT_CLASS_YEAR_MISMATCH"


def test_router_wires_integrity_into_all_active_write_paths_and_audits_mutations() -> None:
    router_text = (BACKEND / "routers" / "assignments.py").read_text(encoding="utf-8")

    # Criação titular, substituição e atualização ativa devem passar pelo mesmo SSoT.
    assert router_text.count("validate_teacher_assignment_curriculum(") >= 3
    assert "from services.teacher_assignment_integrity import" in router_text

    # As três superfícies mutáveis deixam trilha; hard delete continua bloqueado.
    assert "collection='teacher_assignments'" in router_text
    assert "action='create'" in router_text
    assert "action='update'" in router_text
    assert "action='delete_blocked'" in router_text
    assert "TEACHER_ASSIGNMENT_HARD_DELETE_DISABLED_P0" in router_text

    # Encerramento do passivo histórico continua possível sem reativar vínculo inválido.
    assert "INACTIVE_REMEDIATION_ALLOWED" in router_text
