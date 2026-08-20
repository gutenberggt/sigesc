"""Testes read-only do context builder da Assessment Policy v1."""

from datetime import date

import pytest

from assessment_policy.context_builder import build_assessment_policy_context
from assessment_policy.exceptions import (
    AssessmentPolicyError,
    POLICY_CONTEXT_MISMATCH,
    STUDENT_SERIES_REQUIRED,
)


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)

    async def to_list(self, length=None):
        return list(self.rows)


class FakeCollection:
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
        return FakeCursor(self.rows)


class FakeDB:
    def __init__(self, *, class_info, enrollments=None, student=None):
        self.classes = FakeCollection(one=class_info)
        self.enrollments = FakeCollection(rows=enrollments or [])
        self.students = FakeCollection(one=student)


def _class(**updates):
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
async def test_context_uses_annual_enrollment_series_and_class_dimensions():
    db = FakeDB(
        class_info=_class(),
        enrollments=[
            {
                "id": "enr-1",
                "student_id": "student-1",
                "class_id": "class-1",
                "academic_year": 2026,
                "student_series": "2º ANO",
            }
        ],
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
    assert context.component_id == "math"

    class_query = db.classes.find_one_calls[0][0]
    assert class_query == {"id": "class-1", "mantenedora_id": "tenant-a"}
    enrollment_query = db.enrollments.find_calls[0][0]
    assert enrollment_query["student_id"] == "student-1"
    assert enrollment_query["class_id"] == "class-1"
    assert enrollment_query["academic_year"] == {"$in": [2026, "2026"]}


@pytest.mark.asyncio
async def test_missing_tenant_scoped_class_fails_closed():
    db = FakeDB(class_info=None)

    with pytest.raises(AssessmentPolicyError) as exc:
        await build_assessment_policy_context(
            db,
            mantenedora_id="tenant-a",
            school_id="school-1",
            class_id="class-x",
            student_id="student-1",
            academic_year=2026,
            reference_date=date(2026, 8, 19),
            current_year=2026,
        )

    assert exc.value.code == POLICY_CONTEXT_MISMATCH


@pytest.mark.asyncio
async def test_school_mismatch_fails_closed():
    db = FakeDB(class_info=_class(school_id="school-2"))

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
async def test_historical_context_requires_annual_membership_evidence():
    db = FakeDB(
        class_info=_class(
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
async def test_multigrade_membership_without_individual_series_fails_closed():
    db = FakeDB(
        class_info=_class(),
        enrollments=[
            {
                "id": "enr-1",
                "student_id": "student-1",
                "class_id": "class-1",
                "academic_year": 2026,
            }
        ],
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


@pytest.mark.asyncio
async def test_current_direct_membership_can_support_legacy_student_fallback():
    db = FakeDB(
        class_info=_class(),
        enrollments=[],
        student={
            "id": "student-1",
            "class_id": "class-1",
            "school_id": "school-1",
            "mantenedora_id": "tenant-a",
            "student_series": "2º ANO",
        },
    )

    context = await build_assessment_policy_context(
        db,
        mantenedora_id="tenant-a",
        school_id="school-1",
        class_id="class-1",
        student_id="student-1",
        academic_year=2026,
        reference_date=date(2026, 8, 19),
        current_year=2026,
    )

    assert context.student_series == "2º ANO"
