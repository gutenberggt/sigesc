"""Testes da Sprint 006 — Shadow Runner read-only."""

from datetime import date
import ast
from pathlib import Path

import pytest

from assessment_policy.canonical import calculate_rule_hash
from assessment_policy.exceptions import AssessmentPolicyError, POLICY_CONTEXT_MISMATCH
from assessment_policy.models import (
    AcademicOutcomeRule,
    AssessmentMode,
    AssessmentPolicy,
    AssessmentRule,
    AttendanceBasis,
    CalculationRule,
    CalculationStrategy,
    NumericScale,
    PeriodRule,
    PolicyScope,
    PolicyStatus,
    RecoveryRule,
)
from assessment_policy.shadow import LegacyGradeFieldMapping
from assessment_policy.shadow_runner import (
    SHADOW_RUNNER_GRADE_TENANT_MISMATCH,
    SHADOW_RUNNER_MAPPING_REQUIRED,
    run_shadow_dry_run,
)


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
        self.last_find_query = None
        self.last_find_projection = None

    def find(self, query, projection=None):
        self.last_find_query = query
        self.last_find_projection = projection
        rows = [_project(row, projection) for row in self.rows if _matches(row, query)]
        return FakeCursor(rows)

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


def _published_policy():
    policy = AssessmentPolicy(
        id="policy-3ano-2026",
        policy_key="EF_3_NUMERICO",
        version=1,
        revision=1,
        mantenedora_id="tenant-a",
        name="3º Ano — Numérico — 2026",
        status=PolicyStatus.PUBLISHED,
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
            minimum_component_average=5,
            minimum_attendance_percentage=75,
            attendance_basis=AttendanceBasis.GLOBAL,
        ),
        rule_hash=None,
    )
    return policy.model_copy(update={"rule_hash": calculate_rule_hash(policy)})


def _mapping():
    return LegacyGradeFieldMapping(
        period_field_map={"b1": "b1", "b2": "b2", "b3": "b3", "b4": "b4"},
        recovery_field_map={},
    )


def _db(*, grade_tenant="tenant-a"):
    policy = _published_policy()
    return FakeDB(
        classes=[
            {
                "id": "class-3a",
                "school_id": "school-1",
                "mantenedora_id": "tenant-a",
                "academic_year": 2026,
                "grade_level": "3º Ano",
                "education_level": "fundamental_anos_iniciais",
                "modality": "regular",
                "is_multi_grade": False,
            }
        ],
        grades=[
            {
                "id": "grade-1",
                "student_id": "student-1",
                "class_id": "class-3a",
                "course_id": "course-mat",
                "academic_year": 2026,
                "mantenedora_id": grade_tenant,
                "b1": 5.0,
                "b2": 7.5,
                "b3": 5.0,
                "b4": 7.5,
                "final_average": 6.5,
                "status": "aprovado",
            }
        ],
        enrollments=[
            {
                "id": "enrollment-1",
                "student_id": "student-1",
                "class_id": "class-3a",
                "student_series": "3º Ano",
                "academic_year": 2026,
                "status": "active",
            }
        ],
        students=[
            {
                "id": "student-1",
                "class_id": "class-3a",
                "school_id": "school-1",
                "mantenedora_id": "tenant-a",
                "student_series": "3º Ano",
                "status": "active",
            }
        ],
        courses=[
            {
                "id": "course-mat",
                "mantenedora_id": "tenant-a",
                "school_id": "",
                "nivel_ensino": "fundamental_anos_iniciais",
                "grade_levels": ["3º Ano"],
                "name": "Matemática",
            }
        ],
        assessment_policies=[policy.model_dump(mode="json")],
    )


@pytest.mark.asyncio
async def test_runner_resolves_policy_and_matches_persisted_legacy_average():
    db = _db()
    report = await run_shadow_dry_run(
        db,
        mantenedora_id="tenant-a",
        academic_year=2026,
        reference_date=date(2026, 12, 31),
        mappings_by_policy_id={"policy-3ano-2026": _mapping()},
        current_year=2026,
    )

    assert report.scanned == 1
    assert report.compared == 1
    assert report.unresolved == 0
    assert report.comparable == 1
    assert report.matches == 1
    assert report.differences == 0
    assert report.match_rate == 1.0
    assert len(report.groups) == 1
    assert report.groups[0].policy_id == "policy-3ano-2026"
    assert report.groups[0].report.comparisons[0].legacy_final_average == 6.5
    assert report.groups[0].report.comparisons[0].new_final_average == 6.5


@pytest.mark.asyncio
async def test_runner_never_infers_missing_policy_mapping():
    report = await run_shadow_dry_run(
        _db(),
        mantenedora_id="tenant-a",
        academic_year=2026,
        reference_date=date(2026, 12, 31),
        mappings_by_policy_id={},
        current_year=2026,
    )

    assert report.scanned == 1
    assert report.compared == 0
    assert report.unresolved == 1
    assert report.issues[0].error_code == SHADOW_RUNNER_MAPPING_REQUIRED


@pytest.mark.asyncio
async def test_runner_rejects_explicit_grade_tenant_mismatch_as_issue():
    report = await run_shadow_dry_run(
        _db(grade_tenant="tenant-b"),
        mantenedora_id="tenant-a",
        academic_year=2026,
        reference_date=date(2026, 12, 31),
        mappings_by_policy_id={"policy-3ano-2026": _mapping()},
        current_year=2026,
    )

    assert report.scanned == 1
    assert report.compared == 0
    assert report.unresolved == 1
    assert report.issues[0].error_code == SHADOW_RUNNER_GRADE_TENANT_MISMATCH


@pytest.mark.asyncio
async def test_runner_class_filter_cannot_escape_tenant_year_scope():
    with pytest.raises(AssessmentPolicyError) as exc:
        await run_shadow_dry_run(
            _db(),
            mantenedora_id="tenant-a",
            academic_year=2026,
            reference_date=date(2026, 12, 31),
            mappings_by_policy_id={"policy-3ano-2026": _mapping()},
            class_ids=["class-other-tenant"],
            current_year=2026,
        )

    assert exc.value.code == POLICY_CONTEXT_MISMATCH


@pytest.mark.asyncio
async def test_runner_reference_date_must_belong_to_year():
    with pytest.raises(AssessmentPolicyError) as exc:
        await run_shadow_dry_run(
            _db(),
            mantenedora_id="tenant-a",
            academic_year=2026,
            reference_date=date(2025, 12, 31),
            mappings_by_policy_id={"policy-3ano-2026": _mapping()},
            current_year=2026,
        )

    assert exc.value.code == POLICY_CONTEXT_MISMATCH


@pytest.mark.asyncio
async def test_reader_scopes_classes_by_tenant_and_year_before_grades():
    db = _db()
    await run_shadow_dry_run(
        db,
        mantenedora_id="tenant-a",
        academic_year=2026,
        reference_date=date(2026, 12, 31),
        mappings_by_policy_id={"policy-3ano-2026": _mapping()},
        current_year=2026,
    )

    assert db.classes.last_find_query == {
        "mantenedora_id": "tenant-a",
        "academic_year": {"$in": [2026, "2026"]},
    }
    assert db.grades.last_find_query["class_id"] == {"$in": ["class-3a"]}
    assert db.grades.last_find_query["academic_year"] == {"$in": [2026, "2026"]}


def test_shadow_runner_source_has_no_mongo_write_primitives_or_legacy_recalculation():
    source = Path("assessment_policy/shadow_runner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

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
    used_attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }

    assert forbidden_attributes.isdisjoint(used_attributes)
    assert "calculate_and_update_grade" not in source
    assert "grade_calculator" not in source
