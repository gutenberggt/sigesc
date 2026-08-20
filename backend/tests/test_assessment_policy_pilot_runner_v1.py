"""Testes da Sprint 007 — dry-run piloto de policy candidata."""

from datetime import date
import ast
from pathlib import Path

import pytest

from assessment_policy.exceptions import AssessmentPolicyError
from assessment_policy.models import (
    AcademicOutcomeRule,
    AssessmentMode,
    AssessmentPolicy,
    AssessmentRule,
    AttendanceBasis,
    CalculationRule,
    CalculationStrategy,
    NormativeSource,
    NumericScale,
    PeriodRule,
    PolicyScope,
    PolicyStatus,
    RecoveryRule,
)
from assessment_policy.pilot_runner import (
    PILOT_GRADE_TENANT_MISMATCH,
    PILOT_NOT_READY,
    PILOT_TENANT_MISMATCH,
    run_candidate_dry_run,
)
from assessment_policy.shadow import LegacyGradeFieldMapping


class FakeCursor:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        if length is None:
            return [dict(row) for row in self.rows]
        return [dict(row) for row in self.rows[:length]]


def _matches(row, query):
    for key, expected in query.items():
        value = row.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and value not in expected["$in"]:
                return False
            if "$lte" in expected and not (value <= expected["$lte"]):
                return False
            if "$gte" in expected and not (value >= expected["$gte"]):
                return False
        elif value != expected:
            return False
    return True


def _project(row, projection):
    if not projection:
        return dict(row)
    included = {key for key, value in projection.items() if value and key != "_id"}
    if not included:
        return {key: value for key, value in row.items() if key != "_id"}
    return {key: row[key] for key in included if key in row}


class FakeCollection:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def find(self, query, projection=None):
        return FakeCursor(
            [_project(row, projection) for row in self.rows if _matches(row, query)]
        )

    async def find_one(self, query, projection=None):
        for row in self.rows:
            if _matches(row, query):
                return _project(row, projection)
        return None


class FakeDB:
    def __init__(self, **collections):
        self.collections = {
            name: FakeCollection(rows)
            for name, rows in collections.items()
        }

    def __getattr__(self, name):
        try:
            return self.collections[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __getitem__(self, name):
        return self.collections[name]


def _candidate_policy(*, status=PolicyStatus.DRAFT, normative=True):
    return AssessmentPolicy(
        id="candidate-3ano-2026",
        policy_key="EF_3_NUMERICO_2026",
        version=1,
        revision=1,
        mantenedora_id="tenant-a",
        name="3º Ano — Numérico — 2026",
        status=status,
        academic_year=2026,
        effective_from=date(2026, 1, 1),
        effective_until=date(2026, 12, 31),
        scope=PolicyScope(series=["3º Ano"]),
        assessment=AssessmentRule(
            mode=AssessmentMode.NUMERIC,
            numeric_scale=NumericScale(minimum=0, maximum=10, decimal_places=1),
            periods=[
                PeriodRule(code="b1", label="1º Bimestre", weight=2),
                PeriodRule(code="b2", label="2º Bimestre", weight=3),
                PeriodRule(code="b3", label="3º Bimestre", weight=2),
                PeriodRule(code="b4", label="4º Bimestre", weight=3),
            ],
            calculation=CalculationRule(strategy=CalculationStrategy.WEIGHTED_AVERAGE),
        ),
        recovery=RecoveryRule(enabled=False),
        academic_outcome=AcademicOutcomeRule(
            minimum_component_average=5.0,
            minimum_attendance_percentage=75.0,
            attendance_basis=AttendanceBasis.GLOBAL,
        ),
        normative_sources=(
            [
                NormativeSource(
                    type="documento_semed",
                    title="Documento oficial SEMED — política avaliativa 2026",
                )
            ]
            if normative
            else []
        ),
    )


def _mapping():
    return LegacyGradeFieldMapping(
        period_field_map={"b1": "b1", "b2": "b2", "b3": "b3", "b4": "b4"},
        recovery_field_map={},
    )


def _multigrade_db(*, first_grade_tenant="tenant-a"):
    return FakeDB(
        classes=[
            {
                "id": "class-multi",
                "school_id": "school-1",
                "mantenedora_id": "tenant-a",
                "academic_year": 2026,
                "grade_level": "3º e 4º Ano",
                "education_level": "fundamental_anos_iniciais",
                "modality": "regular",
                "is_multi_grade": True,
                "series": ["3º Ano", "4º Ano"],
            }
        ],
        grades=[
            {
                "id": "grade-3",
                "student_id": "student-3",
                "class_id": "class-multi",
                "course_id": "course-mat",
                "academic_year": 2026,
                "mantenedora_id": first_grade_tenant,
                "b1": 5.0,
                "b2": 7.5,
                "b3": 5.0,
                "b4": 7.5,
                "final_average": 6.5,
                "status": "aprovado",
            },
            {
                "id": "grade-4",
                "student_id": "student-4",
                "class_id": "class-multi",
                "course_id": "course-mat",
                "academic_year": 2026,
                "mantenedora_id": "tenant-a",
                "b1": 6.0,
                "b2": 6.0,
                "b3": 6.0,
                "b4": 6.0,
                "final_average": 6.0,
                "status": "aprovado",
            },
        ],
        enrollments=[
            {
                "id": "enrollment-3",
                "student_id": "student-3",
                "class_id": "class-multi",
                "student_series": "3º Ano",
                "academic_year": 2026,
                "status": "active",
            },
            {
                "id": "enrollment-4",
                "student_id": "student-4",
                "class_id": "class-multi",
                "student_series": "4º Ano",
                "academic_year": 2026,
                "status": "active",
            },
        ],
        students=[
            {
                "id": "student-3",
                "class_id": "class-multi",
                "school_id": "school-1",
                "mantenedora_id": "tenant-a",
                "student_series": "3º Ano",
                "status": "active",
            },
            {
                "id": "student-4",
                "class_id": "class-multi",
                "school_id": "school-1",
                "mantenedora_id": "tenant-a",
                "student_series": "4º Ano",
                "status": "active",
            },
        ],
        courses=[
            {
                "id": "course-mat",
                "mantenedora_id": "tenant-a",
                "school_id": "",
                "nivel_ensino": "fundamental_anos_iniciais",
                "grade_levels": ["3º Ano", "4º Ano"],
                "name": "Matemática",
            }
        ],
    )


@pytest.mark.asyncio
async def test_candidate_pilot_uses_student_series_in_multigrade_class():
    report = await run_candidate_dry_run(
        _multigrade_db(),
        policy=_candidate_policy(),
        mapping=_mapping(),
        reference_date=date(2026, 12, 31),
        class_ids=["class-multi"],
        current_year=2026,
    )

    assert report.scanned == 2
    assert report.in_scope == 1
    assert report.skipped_out_of_scope == 1
    assert report.compared == 1
    assert report.unresolved == 0
    assert report.comparable == 1
    assert report.matches == 1
    assert report.differences == 0
    assert report.match_rate == 1.0
    assert report.report.comparisons[0].student_id == "student-3"


@pytest.mark.asyncio
async def test_candidate_pilot_reports_explicit_grade_tenant_mismatch():
    report = await run_candidate_dry_run(
        _multigrade_db(first_grade_tenant="tenant-b"),
        policy=_candidate_policy(),
        mapping=_mapping(),
        reference_date=date(2026, 12, 31),
        class_ids=["class-multi"],
        current_year=2026,
    )

    assert report.scanned == 2
    assert report.in_scope == 0
    assert report.skipped_out_of_scope == 1
    assert report.compared == 0
    assert report.unresolved == 1
    assert report.issues[0].error_code == PILOT_GRADE_TENANT_MISMATCH


@pytest.mark.asyncio
async def test_candidate_pilot_rejects_class_outside_tenant_scope():
    with pytest.raises(AssessmentPolicyError) as exc:
        await run_candidate_dry_run(
            _multigrade_db(),
            policy=_candidate_policy(),
            mapping=_mapping(),
            reference_date=date(2026, 12, 31),
            class_ids=["class-other"],
            current_year=2026,
        )

    assert exc.value.code == PILOT_TENANT_MISMATCH


@pytest.mark.asyncio
async def test_candidate_pilot_rejects_semantically_incomplete_draft():
    with pytest.raises(AssessmentPolicyError) as exc:
        await run_candidate_dry_run(
            _multigrade_db(),
            policy=_candidate_policy(normative=False),
            mapping=_mapping(),
            reference_date=date(2026, 12, 31),
            current_year=2026,
        )

    assert exc.value.code == PILOT_NOT_READY
    issue_codes = {
        item["code"]
        for item in exc.value.details["issues"]
    }
    assert "ASSESSMENT_POLICY_NORMATIVE_SOURCE_REQUIRED" in issue_codes


def test_assisted_and_pilot_sources_have_no_grade_write_or_legacy_recalculation():
    paths = [
        Path("backend/assessment_policy/assisted_config.py"),
        Path("backend/assessment_policy/pilot_runner.py"),
    ]
    forbidden_attributes = {
        "insert_one",
        "insert_many",
        "update_one",
        "update_many",
        "replace_one",
        "delete_one",
        "delete_many",
        "bulk_write",
        "find_one_and_update",
        "find_one_and_replace",
        "find_one_and_delete",
    }

    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        used_attributes = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        assert forbidden_attributes.isdisjoint(used_attributes), path
        assert "calculate_and_update_grade" not in source, path
        assert "grade_calculator" not in source, path
