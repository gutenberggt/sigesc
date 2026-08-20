"""Testes da série efetiva e do context builder do Policy Resolver."""

from datetime import date

import pytest

from assessment_policy.context_builder import build_assessment_policy_context
from assessment_policy.exceptions import (
    AssessmentPolicyError,
    POLICY_CONTEXT_MISMATCH,
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


class _FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)

    async def to_list(self, length=None):
        return list(self.rows)


class _FakeCollection:
    def __init__(self, *, one=None, rows=None):
        self.one = one
        self.rows = list(rows or [])
        self.find_one_calls = []
        self.find_calls = []

    async def find_one(self, query, projection):
        self.find_one_calls.append((query, projection))
        return self.one

    def find(self, query, projection):
        self.find_calls.append((query, projection))
        return _FakeCursor(self.rows)


class _FakeDB:
    def __init__(self, *, class_info, enrollments=None, student=None):
        self.classes = _FakeCollection(one=class_info)
        self.enrollments = _FakeCollection(rows=enrollments or [])
        self.students = _FakeCollection(one=student)


def _context_class(**updates):
    base = {
        "id": "class-1",
        "school_id": "school-1",
        "mantenedora_id": "tenant-a",
        "academic_year": 2026,
        "grade_level": "1º ANO",
        "education_level": "fundamental_anos_iniciais",
        "modality": "regular",
        "is_multi_grade": True,
        "series": ["1º ANO", "2º ANO"],
    }
    base.update(updates)
    return base


@pytest.mark.asyncio
async def test_context_builder_uses_annual_enrollment_and_tenant_scoped_class():
    db = _FakeDB(
        class_info=_context_class(),
        enrollments=[{"id": "e1", "student_series": "2º ANO"}],
        student={
            "id": "student-1",
            "class_id": "class-1",
            "school_id": "school-1",
            "mantenedora_id": "tenant-a",
            "student_series": "1º ANO",
        },
    )

    context = await build_assessment_policy_context(
        db,
        mantenedora_id="tenant-a",
        school_id="school-1",
        class_id="class-1",
        student_id="student-1",
        component_id="math",
        academic_year=2026,
        reference_date=date(2026, 8, 19),
        current_year=2026,
    )

    assert context.student_series == "2º ANO"
    assert context.education_stage == "fundamental_anos_iniciais"
    assert context.modality == "regular"
    assert db.classes.find_one_calls[0][0] == {
        "id": "class-1",
        "mantenedora_id": "tenant-a",
    }
    assert db.enrollments.find_calls[0][0]["academic_year"] == {
        "$in": [2026, "2026"]
    }


@pytest.mark.asyncio
async def test_context_builder_rejects_school_mismatch():
    db = _FakeDB(class_info=_context_class(school_id="school-2"))

    with pytest.raises(AssessmentPolicyError) as exc:
        await build_assessment_policy_context(
            db,
            mantenedora_id="tenant-a",
            school_id="school-1",
            class_id="class-1",
            student_id="student-1",
            academic_year=2026,
            reference_date=date(2026, 8, 19),
            current_year=2026,
        )

    assert exc.value.code == POLICY_CONTEXT_MISMATCH


@pytest.mark.asyncio
async def test_context_builder_historical_context_requires_annual_membership():
    db = _FakeDB(
        class_info=_context_class(
            academic_year=2025,
            is_multi_grade=False,
            series=["4º ANO"],
            grade_level="4º ANO",
        ),
        enrollments=[],
        student={
            "id": "student-1",
            "class_id": "class-1",
            "school_id": "school-1",
            "mantenedora_id": "tenant-a",
            "student_series": "5º ANO",
        },
    )

    with pytest.raises(AssessmentPolicyError) as exc:
        await build_assessment_policy_context(
            db,
            mantenedora_id="tenant-a",
            school_id="school-1",
            class_id="class-1",
            student_id="student-1",
            academic_year=2025,
            reference_date=date(2025, 8, 19),
            current_year=2026,
        )

    assert exc.value.code == POLICY_CONTEXT_MISMATCH


@pytest.mark.asyncio
async def test_context_builder_multigrade_without_individual_series_fails_closed():
    db = _FakeDB(
        class_info=_context_class(),
        enrollments=[{"id": "e1", "student_series": None}],
        student={
            "id": "student-1",
            "class_id": "class-1",
            "school_id": "school-1",
            "mantenedora_id": "tenant-a",
            "student_series": None,
        },
    )

    with pytest.raises(AssessmentPolicyError) as exc:
        await build_assessment_policy_context(
            db,
            mantenedora_id="tenant-a",
            school_id="school-1",
            class_id="class-1",
            student_id="student-1",
            academic_year=2026,
            reference_date=date(2026, 8, 19),
            current_year=2026,
        )

    assert exc.value.code == STUDENT_SERIES_REQUIRED
