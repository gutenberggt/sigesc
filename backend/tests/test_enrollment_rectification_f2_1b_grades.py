from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

from routers.grades import _frozen_fields_of_migrated_grade, _strip_frozen_grade_fields
from services.enrollment_rectification import _grade_manifest
from services.enrollment_rectification_grade_contract import grade_academic_fingerprint
from services.enrollment_rectification_grades import GradeRectificationError, apply_grade_rectification_item

TENANT = "TENANT-F21B"
STUDENT = "STUDENT-F21B"
SOURCE = "CLASS-6A-F21B"
DEST = "CLASS-7A-F21B"
SRC_COURSE = "COURSE-PT6-F21B"
DST_COURSE = "COURSE-PT7-F21B"
YEAR = 2026
PROTOCOL = "RET-F21B-0001"
ACTOR = {"id": "ADMIN-F21B", "role": "admin", "full_name": "Admin F2.1B"}
OWN_B1 = {"assignment_id": "A1", "teacher_id": "T1", "component_id": SRC_COURSE, "class_id": SOURCE}


@pytest.fixture
def db():
    return AsyncMongoMockClient()["sigesc_rectification_f21b"]


def source_grade(**overrides):
    doc = {
        "id": "GRADE-SRC",
        "mantenedora_id": TENANT,
        "student_id": STUDENT,
        "class_id": SOURCE,
        "course_id": SRC_COURSE,
        "academic_year": YEAR,
        "dependency_id": None,
        "b1": 8.0,
        "b2": 6.0,
        "b3": None,
        "b4": None,
        "rec_s1": None,
        "rec_s2": None,
        "recovery": None,
        "grade_ownership": {"b1": deepcopy(OWN_B1)},
        "rectified_fields": {},
    }
    doc.update(overrides)
    return doc


def destination_grade(**overrides):
    doc = {
        "id": "GRADE-DST",
        "mantenedora_id": TENANT,
        "student_id": STUDENT,
        "class_id": DEST,
        "course_id": DST_COURSE,
        "academic_year": YEAR,
        "dependency_id": None,
        "b1": None,
        "b2": None,
        "b3": 9.0,
        "b4": None,
        "rec_s1": None,
        "rec_s2": None,
        "recovery": None,
        "grade_ownership": {"b3": {"assignment_id": "DEST-A3"}},
        "rectified_fields": {},
    }
    doc.update(overrides)
    return doc


def manifest(src, dst=None, **overrides):
    item = {
        "grade_id": src["id"],
        "source_grade_id": src["id"],
        "source_course_id": SRC_COURSE,
        "target_course_id": DST_COURSE,
        "source_values": {field: src.get(field) for field in ("b1", "b2", "rec_s1", "b3", "b4", "rec_s2", "recovery")},
        "migratable_fields": [field for field in ("b1", "b2", "rec_s1", "b3", "b4", "rec_s2", "recovery") if src.get(field) not in (None, "", [], {})],
        "source_grade_fingerprint": grade_academic_fingerprint(src),
        "destination_grade_id": (dst or {}).get("id"),
        "destination_grade_fingerprint": grade_academic_fingerprint(dst),
        "destination_expected_absent": dst is None,
        "destination_cardinality": 0 if dst is None else 1,
        "overlapping_fields": [],
        "destination_metadata_conflicts": [],
    }
    item.update(overrides)
    return item


async def apply(db, item, **kwargs):
    return await apply_grade_rectification_item(
        db,
        manifest_item=item,
        protocol=kwargs.pop("protocol", PROTOCOL),
        tenant_id=kwargs.pop("tenant_id", TENANT),
        student_id=kwargs.pop("student_id", STUDENT),
        source_class_id=kwargs.pop("source_class_id", SOURCE),
        target_enrollment_id=kwargs.pop("target_enrollment_id", "ENR-F21B"),
        target_class_id=kwargs.pop("target_class_id", DEST),
        academic_year=kwargs.pop("academic_year", YEAR),
        actor=kwargs.pop("actor", ACTOR),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_f1_manifest_contains_fingerprints_and_fields(db):
    src = source_grade()
    dst = destination_grade()
    await db.grades.insert_many([deepcopy(src), deepcopy(dst)])
    out, blockers = await _grade_manifest(
        db,
        student_id=STUDENT,
        source_class_id=SOURCE,
        destination_class_id=DEST,
        academic_year=YEAR,
        tenant_id=TENANT,
        course_map=[{"source_course_id": SRC_COURSE, "target_course_id": DST_COURSE, "ok": True}],
    )
    assert blockers == []
    assert out[0]["source_grade_id"] == src["id"]
    assert out[0]["source_grade_fingerprint"] == grade_academic_fingerprint(src)
    assert out[0]["destination_grade_fingerprint"] == grade_academic_fingerprint(dst)
    assert out[0]["migratable_fields"] == ["b1", "b2"]


@pytest.mark.asyncio
async def test_destination_absent_creates_grade_preserves_ownership_and_removes_source(db):
    src = source_grade()
    await db.grades.insert_one(deepcopy(src))
    out = await apply(db, manifest(src))
    assert out["state"] == "APPLIED"
    assert await db.grades.find_one({"id": src["id"]}) is None
    dst = await db.grades.find_one({"class_id": DEST}, {"_id": 0})
    assert dst["b1"] == 8.0 and dst["b2"] == 6.0
    assert dst["grade_ownership"]["b1"] == OWN_B1
    assert "b2" not in dst["grade_ownership"]
    assert set(dst["rectified_fields"]) == {"b1", "b2"}
    assert dst["final_average"] == 7.0


@pytest.mark.asyncio
async def test_existing_destination_merges_only_empty_fields(db):
    src = source_grade()
    dst = destination_grade()
    await db.grades.insert_many([deepcopy(src), deepcopy(dst)])
    await apply(db, manifest(src, dst))
    updated = await db.grades.find_one({"id": dst["id"]}, {"_id": 0})
    assert updated["b1"] == 8.0 and updated["b2"] == 6.0
    assert updated["b3"] == 9.0
    assert updated["grade_ownership"]["b3"] == {"assignment_id": "DEST-A3"}


@pytest.mark.asyncio
async def test_overlap_non_null_is_zero_mutation(db):
    src = source_grade()
    dst = destination_grade(b1=5.0)
    await db.grades.insert_many([deepcopy(src), deepcopy(dst)])
    before = await db.grades.find_one({"id": dst["id"]}, {"_id": 0})
    with pytest.raises(GradeRectificationError) as exc:
        await apply(db, manifest(src, dst))
    assert exc.value.code == "RECTIFICATION_GRADE_DESTINATION_VALUE_PRESENT"
    assert await db.grade_rectifications.count_documents({}) == 0
    assert await db.grades.find_one({"id": dst["id"]}, {"_id": 0}) == before


@pytest.mark.asyncio
async def test_destination_ownership_metadata_conflict_is_zero_mutation(db):
    src = source_grade()
    dst = destination_grade(grade_ownership={"b1": {"assignment_id": "OLD"}, "b3": {"assignment_id": "DEST-A3"}})
    await db.grades.insert_many([deepcopy(src), deepcopy(dst)])
    with pytest.raises(GradeRectificationError) as exc:
        await apply(db, manifest(src, dst))
    assert exc.value.code == "RECTIFICATION_GRADE_DESTINATION_FIELD_METADATA_PRESENT"
    assert await db.grade_rectifications.count_documents({}) == 0


@pytest.mark.asyncio
async def test_dependency_is_blocked_before_ledger(db):
    src = source_grade(dependency_id="DEP-1")
    await db.grades.insert_one(deepcopy(src))
    with pytest.raises(GradeRectificationError) as exc:
        await apply(db, manifest(src))
    assert exc.value.code == "RECTIFICATION_GRADE_DEPENDENCY_REVIEW_REQUIRED"
    assert await db.grade_rectifications.count_documents({}) == 0


@pytest.mark.asyncio
async def test_missing_course_map_is_blocked(db):
    src = source_grade()
    await db.grades.insert_one(deepcopy(src))
    bad = manifest(src, target_course_id="")
    with pytest.raises(GradeRectificationError) as exc:
        await apply(db, bad)
    assert exc.value.code == "RECTIFICATION_GRADE_MANIFEST_UNHARDENED"


@pytest.mark.asyncio
async def test_source_fingerprint_stale_is_zero_mutation(db):
    src = source_grade()
    await db.grades.insert_one(deepcopy(src))
    item = manifest(src)
    await db.grades.update_one({"id": src["id"]}, {"$set": {"b1": 4.0}})
    with pytest.raises(GradeRectificationError) as exc:
        await apply(db, item)
    assert exc.value.code == "RECTIFICATION_GRADE_SOURCE_FINGERPRINT_CHANGED"
    assert await db.grade_rectifications.count_documents({}) == 0
    assert await db.grades.count_documents({"class_id": DEST}) == 0


@pytest.mark.asyncio
async def test_destination_fingerprint_stale_is_zero_mutation(db):
    src = source_grade()
    dst = destination_grade()
    await db.grades.insert_many([deepcopy(src), deepcopy(dst)])
    item = manifest(src, dst)
    await db.grades.update_one({"id": dst["id"]}, {"$set": {"b4": 10.0}})
    with pytest.raises(GradeRectificationError) as exc:
        await apply(db, item)
    assert exc.value.code == "RECTIFICATION_GRADE_DESTINATION_FINGERPRINT_CHANGED"
    assert await db.grade_rectifications.count_documents({}) == 0


@pytest.mark.asyncio
async def test_destination_appears_after_dry_run_is_blocked(db):
    src = source_grade()
    await db.grades.insert_one(deepcopy(src))
    item = manifest(src)
    await db.grades.insert_one(deepcopy(destination_grade()))
    with pytest.raises(GradeRectificationError) as exc:
        await apply(db, item)
    assert exc.value.code == "RECTIFICATION_GRADE_DESTINATION_FINGERPRINT_CHANGED"


@pytest.mark.asyncio
async def test_legacy_documents_without_metadata_maps_are_supported_by_cas(db):
    src = source_grade()
    src.pop("grade_ownership", None)
    src.pop("rectified_fields", None)
    dst = destination_grade()
    dst.pop("rectified_fields", None)
    await db.grades.insert_many([deepcopy(src), deepcopy(dst)])
    out = await apply(db, manifest(src, dst))
    assert out["state"] == "APPLIED"
    updated = await db.grades.find_one({"id": dst["id"]}, {"_id": 0})
    assert updated["b1"] == 8.0 and updated["b2"] == 6.0
    assert "b1" not in (updated.get("grade_ownership") or {})
    assert await db.grades.find_one({"id": src["id"]}) is None


@pytest.mark.asyncio
async def test_replay_after_applied_is_idempotent(db):
    src = source_grade()
    await db.grades.insert_one(deepcopy(src))
    item = manifest(src)
    first = await apply(db, item)
    second = await apply(db, item)
    assert second["idempotent_replay"] is True
    assert first["id"] == second["id"]
    assert await db.grade_rectifications.count_documents({}) == 1
    assert await db.grades.count_documents({"class_id": DEST}) == 1


@pytest.mark.asyncio
async def test_tenant_mismatch_fail_closed(db):
    src = source_grade()
    await db.grades.insert_one(deepcopy(src))
    with pytest.raises(GradeRectificationError) as exc:
        await apply(db, manifest(src), tenant_id="OTHER-TENANT")
    assert exc.value.code == "RECTIFICATION_GRADE_TENANT_MISMATCH"


@pytest.mark.asyncio
async def test_source_class_mismatch_fail_closed(db):
    src = source_grade()
    await db.grades.insert_one(deepcopy(src))
    with pytest.raises(GradeRectificationError) as exc:
        await apply(db, manifest(src), source_class_id="OTHER-CLASS")
    assert exc.value.code == "RECTIFICATION_GRADE_SOURCE_IDENTITY_CHANGED"


@pytest.mark.asyncio
async def test_admin_teste_forbidden(db):
    src = source_grade()
    await db.grades.insert_one(deepcopy(src))
    with pytest.raises(GradeRectificationError) as exc:
        await apply(db, manifest(src), actor={"id": "TEST", "role": "admin_teste"})
    assert exc.value.code == "RECTIFICATION_GRADE_ACTOR_FORBIDDEN"


def test_rectified_fields_freeze_is_granular_and_legacy_compatible():
    explicit = {"b1": 8, "b2": 7, "rectified_fields": {"b1": {"protocol": PROTOCOL}}}
    assert _frozen_fields_of_migrated_grade(explicit) == {"b1"}
    stripped = _strip_frozen_grade_fields({"b1": 1, "b2": 9}, explicit, "professor")
    assert "b1" not in stripped and stripped["b2"] == 9

    legacy = {"b1": 8, "b2": None, "migrated_from_class_id": SOURCE}
    assert _frozen_fields_of_migrated_grade(legacy) == {"b1"}


def test_structural_guard_keeps_saga_publicly_closed():
    root = Path(__file__).resolve().parents[1]
    f2_router = (root / "routers/enrollment_rectification_execution.py").read_text(encoding="utf-8")
    f2_kernel = (root / "services/enrollment_rectification_execution.py").read_text(encoding="utf-8")
    grade_service = (root / "services/enrollment_rectification_grades.py").read_text(encoding="utf-8")
    assert '@router.post("/execute")' not in f2_router
    assert '@router.post("/rollback")' not in f2_router
    assert "ACADEMIC_MUTATION_IMPLEMENTED = False" in f2_kernel
    assert "APIRouter" not in grade_service
