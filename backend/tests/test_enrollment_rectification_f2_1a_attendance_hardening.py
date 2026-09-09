from __future__ import annotations

from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.enrollment_rectification_attendance import (
    AttendanceRectificationError,
    LEDGER_INDEX_NAME,
    apply_attendance_rectification_item,
)

TENANT = "TENANT-F21A-HARDENING"
SOURCE = "CLASS-SOURCE-F21A-HARDENING"
DEST = "CLASS-TARGET-F21A-HARDENING"
STUDENT = "STUDENT-F21A-HARDENING"
OTHER = "OTHER-F21A-HARDENING"
ATT = "ATT-F21A-HARDENING"
COURSE_SRC = "COURSE-SOURCE-F21A-HARDENING"
COURSE_DST = "COURSE-TARGET-F21A-HARDENING"
PROTOCOL = "RET-F21A-HARDENING-0001"
YEAR = 2026
ACTOR = {"id": "ADMIN-F21A-HARDENING", "role": "admin", "full_name": "Admin F2.1A Hardening"}


class AuditSpy:
    def __init__(self):
        self.events = []

    async def log(self, **kwargs):
        self.events.append(kwargs)


class RacingAttendanceCollection:
    """Injects one concurrent version bump exactly before the records CAS write."""

    def __init__(self, inner):
        self._inner = inner
        self.injected = False

    async def update_one(self, filter_doc, update_doc, *args, **kwargs):
        set_doc = (update_doc or {}).get("$set") or {}
        if not self.injected and "records" in set_doc:
            self.injected = True
            await self._inner.update_one(
                {"id": ATT},
                {"$inc": {"version": 1}, "$set": {"concurrent_touch": True}},
            )
        return await self._inner.update_one(filter_doc, update_doc, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class RacingDb:
    def __init__(self, inner):
        self._inner = inner
        self.attendance = RacingAttendanceCollection(inner.attendance)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __getitem__(self, name):
        return self._inner[name]


@pytest.fixture
def db():
    return AsyncMongoMockClient()["sigesc_rectification_f21a_hardening"]


async def seed(db, *, validated: bool = True, version: int = 4):
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
        "assignment_id": "ASSIGN-SOURCE-HARDENING",
        "version": version,
        "created_by": "TEACHER-HARDENING",
        "records": [
            {"student_id": STUDENT, "status": "P"},
            {"student_id": OTHER, "status": "F", "note": "preserve"},
        ],
    }
    if validated:
        doc.update({
            "validated_by": "COORD-HARDENING",
            "validated_by_name": "Coordenação",
            "validated_by_role": "coordenador",
            "validated_at": "2026-03-13T10:00:00+00:00",
        })
    await db.attendance.insert_one(doc)


def manifest(*, version: int = 4):
    return {
        "source_attendance_id": ATT,
        "source_date": "2026-03-12",
        "source_course_id": COURSE_SRC,
        "target_course_id": COURSE_DST,
        "source_aula_numero": 2,
        "source_assignment_id": "ASSIGN-SOURCE-HARDENING",
        "status": "P",
        "validated": True,
        "version": version,
    }


async def apply(db, audit):
    return await apply_attendance_rectification_item(
        db,
        manifest_item=manifest(),
        protocol=PROTOCOL,
        tenant_id=TENANT,
        student_id=STUDENT,
        source_class_id=SOURCE,
        target_enrollment_id="ENR-F21A-HARDENING",
        target_class_id=DEST,
        academic_year=YEAR,
        actor=ACTOR,
        request=object(),
        audit_service=audit,
    )


@pytest.mark.asyncio
async def test_cas_conflict_after_unvalidation_is_explicit_recoverable(db):
    await seed(db, validated=True, version=4)
    audit = AuditSpy()
    racing_db = RacingDb(db)

    with pytest.raises(AttendanceRectificationError) as exc:
        await apply(racing_db, audit)

    assert exc.value.code == "RECTIFICATION_ATTENDANCE_PULL_CAS_CONFLICT"
    assert racing_db.attendance.injected is True

    ledger = await db.attendance_rectifications.find_one(
        {
            "mantenedora_id": TENANT,
            "protocol": PROTOCOL,
            "source_attendance_id": ATT,
            "student_id": STUDENT,
        },
        {"_id": 0},
    )
    assert ledger["state"] == "FAILED_RECOVERABLE"
    assert ledger["failure_code"] == "RECTIFICATION_ATTENDANCE_PULL_CAS_CONFLICT"

    post = await db.attendance.find_one({"id": ATT}, {"_id": 0})
    assert post["validated_by"] is None
    assert len(post.get("validation_history") or []) == 1
    assert any(r.get("student_id") == STUDENT for r in post["records"])
    assert any(r.get("student_id") == OTHER for r in post["records"])
    assert post["version"] == 6


@pytest.mark.asyncio
async def test_rectification_unvalidation_audit_contains_protocol_without_credentials(db):
    await seed(db, validated=True, version=4)
    audit = AuditSpy()

    await apply(db, audit)

    event = next(e for e in audit.events if e.get("action") == "unvalidate_attendance")
    assert PROTOCOL in event["description"]
    assert PROTOCOL in event["extra_data"]["rationale"]
    serialized = repr(event).lower()
    assert "password" not in serialized
    assert "jwt_secret" not in serialized
    assert "access_token" not in serialized


@pytest.mark.asyncio
async def test_ledger_unique_index_matches_tenant_protocol_attendance_student(db):
    await seed(db, validated=False, version=4)
    await apply(db, AuditSpy())

    indexes = await db.attendance_rectifications.index_information()
    index = indexes[LEDGER_INDEX_NAME]
    assert index.get("unique") is True
    assert index["key"] == [
        ("mantenedora_id", 1),
        ("protocol", 1),
        ("source_attendance_id", 1),
        ("student_id", 1),
    ]


def test_attendance_http_contract_is_preserved_and_delegates_to_canonical_service():
    root = Path(__file__).resolve().parents[1]
    src = (root / "routers/attendance.py").read_text(encoding="utf-8")

    assert '@router.post("/{attendance_id}/validate")' in src
    assert '@router.post("/validate-batch")' in src
    assert '@router.post("/{attendance_id}/unvalidate")' in src
    assert "validate_attendance_institutional(" in src
    assert "unvalidate_attendance_institutional(" in src
    for code in (
        "NOT_FOUND",
        "ALREADY_VALIDATED",
        "EMPTY_RECORDS",
        "VERSION_CONFLICT",
        "RATIONALE_TOO_SHORT",
        "FORBIDDEN_UNVALIDATE",
        "NOT_VALIDATED",
    ):
        assert code in src
