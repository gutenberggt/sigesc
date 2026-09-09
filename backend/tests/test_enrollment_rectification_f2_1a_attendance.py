from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.attendance_validation import (
    AttendanceValidationError,
    unvalidate_attendance_institutional,
    validate_attendance_institutional,
)
from services.enrollment_rectification_attendance import (
    AttendanceRectificationError,
    apply_attendance_rectification_item,
    project_effective_attendance_rectification,
)

TENANT = "TENANT-F21A"
SOURCE = "CLASS-6A-F21A"
DEST = "CLASS-7A-F21A"
STUDENT = "STUDENT-F21A"
OTHER = "OTHER-F21A"
ATT = "ATT-F21A"
COURSE_SRC = "COURSE-PT6-F21A"
COURSE_DST = "COURSE-PT7-F21A"
PROTOCOL = "RET-F21A-0001"
YEAR = 2026
ACTOR = {"id": "ADMIN-F21A", "role": "admin", "full_name": "Admin F2.1A"}


class AuditSpy:
    def __init__(self):
        self.events = []

    async def log(self, **kwargs):
        self.events.append(kwargs)


@pytest.fixture
def db():
    return AsyncMongoMockClient()["sigesc_rectification_f21a"]


async def seed(db, *, validated=False, version=4):
    await db.classes.insert_many([
        {"id": SOURCE, "name": "6º A", "school_id": "SCHOOL", "mantenedora_id": TENANT},
        {"id": DEST, "name": "7º A", "school_id": "SCHOOL", "mantenedora_id": TENANT},
    ])
    doc = {
        "id": ATT,
        "mantenedora_id": TENANT,
        "class_id": SOURCE,
        "course_id": COURSE_SRC,
        "academic_year": YEAR,
        "date": "2026-03-12",
        "aula_numero": 2,
        "assignment_id": "ASSIGN-SOURCE",
        "version": version,
        "created_by": "TEACHER",
        "records": [
            {"student_id": STUDENT, "status": "P"},
            {"student_id": OTHER, "status": "F", "note": "preserve"},
        ],
    }
    if validated:
        doc.update({
            "validated_by": "COORD",
            "validated_by_name": "Coordenação",
            "validated_by_role": "coordenador",
            "validated_at": "2026-03-13T10:00:00+00:00",
        })
    snapshot = deepcopy(doc)
    await db.attendance.insert_one(doc)
    return snapshot


def manifest(*, version=4, status="P"):
    return {
        "source_attendance_id": ATT,
        "source_date": "2026-03-12",
        "source_course_id": COURSE_SRC,
        "target_course_id": COURSE_DST,
        "source_aula_numero": 2,
        "source_assignment_id": "ASSIGN-SOURCE",
        "status": status,
        "validated": False,
        "version": version,
    }


async def apply(db, audit, item=None, **kwargs):
    return await apply_attendance_rectification_item(
        db,
        manifest_item=item or manifest(),
        protocol=PROTOCOL,
        tenant_id=kwargs.pop("tenant_id", TENANT),
        student_id=STUDENT,
        source_class_id=kwargs.pop("source_class_id", SOURCE),
        target_enrollment_id="ENR-F21A",
        target_class_id=DEST,
        academic_year=YEAR,
        actor=kwargs.pop("actor", ACTOR),
        request=object(),
        audit_service=audit,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_validation_service_uses_cas_and_audits(db):
    await seed(db, version=4)
    audit = AuditSpy()
    out = await validate_attendance_institutional(db, ATT, user=ACTOR, request=object(), audit_service=audit)
    assert out["version"] == 5
    assert out["validated_by"] == ACTOR["id"]
    assert audit.events[-1]["action"] == "validate_attendance"


@pytest.mark.asyncio
async def test_unvalidation_service_appends_history_and_increments_version(db):
    await seed(db, validated=True, version=7)
    audit = AuditSpy()
    out = await unvalidate_attendance_institutional(
        db, ATT, user=ACTOR, request=object(), audit_service=audit,
        rationale="Reversão administrativa devidamente justificada para teste F2.1A.",
    )
    assert out["version"] == 8
    assert out["validated_by"] is None
    assert len(out["validation_history"]) == 1
    assert out["validation_history"][0]["validated_by"] == "COORD"
    assert audit.events[-1]["action"] == "unvalidate_attendance"


@pytest.mark.asyncio
async def test_unvalidation_preserves_normal_route_authorization(db):
    await seed(db, validated=True)
    with pytest.raises(AttendanceValidationError) as exc:
        await unvalidate_attendance_institutional(
            db, ATT,
            user={"id": "GER", "role": "gerente"},
            request=object(), audit_service=AuditSpy(),
            rationale="Justificativa longa o suficiente para a reversão institucional.",
        )
    assert exc.value.code == "FORBIDDEN_UNVALIDATE"


@pytest.mark.asyncio
async def test_unvalidated_rectification_removes_only_student_and_applies_ledger(db):
    before = await seed(db)
    audit = AuditSpy()
    out = await apply(db, audit)
    post = await db.attendance.find_one({"id": ATT}, {"_id": 0})
    assert out["state"] == "APPLIED"
    assert post["records"] == [before["records"][1]]
    assert post["version"] == 5
    for field in ("class_id", "date", "course_id", "aula_numero", "assignment_id", "academic_year"):
        assert post[field] == before[field]


@pytest.mark.asyncio
async def test_validated_rectification_unvalidates_append_only_and_marks_pending_revalidation(db):
    await seed(db, validated=True)
    audit = AuditSpy()
    out = await apply(db, audit)
    post = await db.attendance.find_one({"id": ATT}, {"_id": 0})
    assert out["requires_revalidation"] is True
    assert out["attendance_revalidation_pending"] is True
    assert post["validated_by"] is None
    assert len(post["validation_history"]) == 1
    assert PROTOCOL in post["validation_history"][0]["rationale"]
    assert post["version"] == 6


@pytest.mark.asyncio
async def test_retry_after_success_is_idempotent(db):
    await seed(db)
    audit = AuditSpy()
    first = await apply(db, audit)
    version = (await db.attendance.find_one({"id": ATT}))["version"]
    second = await apply(db, audit)
    assert first["id"] == second["id"]
    assert second["idempotent_replay"] is True
    assert (await db.attendance.find_one({"id": ATT}))["version"] == version
    assert await db.attendance_rectifications.count_documents({}) == 1


@pytest.mark.asyncio
async def test_stale_version_fails_before_ledger_or_academic_write(db):
    before = await seed(db, version=9)
    with pytest.raises(AttendanceRectificationError) as exc:
        await apply(db, AuditSpy(), item=manifest(version=4))
    assert exc.value.code == "RECTIFICATION_ATTENDANCE_VERSION_CONFLICT"
    assert await db.attendance_rectifications.count_documents({}) == 0
    post = await db.attendance.find_one({"id": ATT}, {"_id": 0})
    assert post == before


@pytest.mark.asyncio
async def test_tenant_mismatch_is_fail_closed(db):
    await seed(db)
    with pytest.raises(AttendanceRectificationError) as exc:
        await apply(db, AuditSpy(), tenant_id="OTHER-TENANT")
    assert exc.value.code == "RECTIFICATION_ATTENDANCE_TENANT_MISMATCH"


@pytest.mark.asyncio
async def test_source_class_mismatch_is_fail_closed(db):
    await seed(db)
    with pytest.raises(AttendanceRectificationError) as exc:
        await apply(db, AuditSpy(), source_class_id="OTHER-CLASS")
    assert exc.value.code == "RECTIFICATION_ATTENDANCE_SOURCE_CLASS_MISMATCH"


@pytest.mark.asyncio
async def test_student_status_change_blocks(db):
    await seed(db)
    with pytest.raises(AttendanceRectificationError) as exc:
        await apply(db, AuditSpy(), item=manifest(status="F"))
    assert exc.value.code == "RECTIFICATION_ATTENDANCE_STATUS_CHANGED"


@pytest.mark.asyncio
async def test_destination_attendance_is_never_created(db):
    await seed(db)
    await apply(db, AuditSpy())
    assert await db.attendance.count_documents({"class_id": DEST}) == 0
    assert await db.attendance.count_documents({"class_id": SOURCE}) == 1


@pytest.mark.asyncio
async def test_admin_teste_cannot_invoke_internal_rectification_primitive(db):
    await seed(db)
    with pytest.raises(AttendanceRectificationError) as exc:
        await apply(db, AuditSpy(), actor={"id": "TEST", "role": "admin_teste"})
    assert exc.value.code == "RECTIFICATION_ATTENDANCE_ACTOR_FORBIDDEN"


@pytest.mark.asyncio
async def test_shadow_projection_only_consumes_applied_ledger(db):
    await seed(db)
    out = await apply(db, AuditSpy())
    shadow = project_effective_attendance_rectification(out)
    assert shadow["student_id"] == STUDENT
    assert shadow["attendance_status"] == "P"
    assert shadow["anti_double_count_key"].startswith(TENANT + ":" + STUDENT)
    assert project_effective_attendance_rectification({"state": "PENDING"}) is None


def test_no_execute_or_rollback_route_is_exposed_by_rectification_f2_1a():
    root = Path(__file__).resolve().parents[1]
    for rel in ("routers/enrollment_rectification.py", "routers/enrollment_rectification_execution.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert '@router.post("/execute")' not in src
        assert '@router.post("/rollback")' not in src
    service_src = (root / "services/enrollment_rectification_attendance.py").read_text(encoding="utf-8")
    assert "APIRouter" not in service_src
