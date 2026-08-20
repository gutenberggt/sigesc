"""Testes puros da série efetiva usada pelo Policy Resolver."""

import pytest

from assessment_policy.exceptions import (
    AssessmentPolicyError,
    STUDENT_SERIES_AMBIGUOUS,
    STUDENT_SERIES_REQUIRED,
)
from assessment_policy.series_resolver import (
    is_multi_grade_class,
    normalize_series,
    resolve_effective_student_series,
)


def _class(**updates):
    base = {
        "id": "class-1",
        "grade_level": "1º ANO",
        "is_multi_grade": False,
        "series": ["1º ANO"],
    }
    base.update(updates)
    return base


def test_normalize_series_tolerates_case_spaces_accents_and_ordinal_symbols():
    assert normalize_series(" 1º ANO ") == normalize_series("1° ano")
    assert normalize_series("Educação Infantil") == normalize_series("educacao infantil")


def test_enrollment_series_has_highest_precedence():
    resolved = resolve_effective_student_series(
        enrollment_rows=[{"id": "e1", "student_series": "2º ANO"}],
        student={"id": "s1", "class_id": "class-1", "student_series": "1º ANO"},
        class_info=_class(),
        academic_year=2026,
        current_year=2026,
    )

    assert resolved.value == "2º ANO"
    assert resolved.source == "enrollment.student_series"
    assert resolved.evidence_id == "e1"


def test_equivalent_enrollment_series_are_not_ambiguous():
    resolved = resolve_effective_student_series(
        enrollment_rows=[
            {"id": "e1", "student_series": "2º ANO"},
            {"id": "e2", "student_series": " 2° ano "},
        ],
        student=None,
        class_info=_class(is_multi_grade=True, series=["1º ANO", "2º ANO"]),
        academic_year=2026,
        current_year=2026,
    )
    assert normalize_series(resolved.value) == normalize_series("2º ANO")


def test_conflicting_enrollment_series_fail_closed():
    with pytest.raises(AssessmentPolicyError) as exc:
        resolve_effective_student_series(
            enrollment_rows=[
                {"id": "e1", "student_series": "1º ANO"},
                {"id": "e2", "student_series": "2º ANO"},
            ],
            student=None,
            class_info=_class(is_multi_grade=True, series=["1º ANO", "2º ANO"]),
            academic_year=2026,
            current_year=2026,
        )

    assert exc.value.code == STUDENT_SERIES_AMBIGUOUS


def test_current_student_series_is_safe_fallback_only_same_class_current_year():
    resolved = resolve_effective_student_series(
        enrollment_rows=[],
        student={"id": "s1", "class_id": "class-1", "student_series": "2º ANO"},
        class_info=_class(is_multi_grade=True, series=["1º ANO", "2º ANO"]),
        academic_year=2026,
        current_year=2026,
    )
    assert resolved.value == "2º ANO"
    assert resolved.source == "student.student_series"


def test_historical_context_does_not_reuse_current_student_series():
    resolved = resolve_effective_student_series(
        enrollment_rows=[],
        student={"id": "s1", "class_id": "class-1", "student_series": "5º ANO"},
        class_info=_class(grade_level="4º ANO"),
        academic_year=2025,
        current_year=2026,
    )
    assert resolved.value == "4º ANO"
    assert resolved.source == "class.grade_level"


def test_multigrade_never_uses_class_grade_level_as_individual_series():
    class_info = _class(
        grade_level="1º ANO",
        is_multi_grade=True,
        series=["1º ANO", "2º ANO", "3º ANO"],
    )
    with pytest.raises(AssessmentPolicyError) as exc:
        resolve_effective_student_series(
            enrollment_rows=[],
            student=None,
            class_info=class_info,
            academic_year=2026,
            current_year=2026,
        )

    assert exc.value.code == STUDENT_SERIES_REQUIRED


def test_multiple_class_series_also_marks_multigrade_even_without_flag():
    assert is_multi_grade_class(
        _class(is_multi_grade=False, series=["1º ANO", "2º ANO"])
    ) is True


def test_single_grade_class_can_use_class_grade_level_fallback():
    resolved = resolve_effective_student_series(
        enrollment_rows=[],
        student=None,
        class_info=_class(grade_level="3º ANO"),
        academic_year=2026,
        current_year=2026,
    )
    assert resolved.value == "3º ANO"
    assert resolved.source == "class.grade_level"


def test_no_safe_series_anywhere_fails_closed():
    with pytest.raises(AssessmentPolicyError) as exc:
        resolve_effective_student_series(
            enrollment_rows=[],
            student=None,
            class_info=_class(grade_level=None, series=[]),
            academic_year=2026,
            current_year=2026,
        )

    assert exc.value.code == STUDENT_SERIES_REQUIRED
