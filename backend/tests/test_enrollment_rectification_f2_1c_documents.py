from __future__ import annotations

import pytest
from mongomock_motor import AsyncMongoMockClient

from services.enrollment_rectification_documents import (
    DOCUMENT_ACKNOWLEDGEMENT,
    DocumentRectificationError,
    build_rectification_document_inventory,
    check_rectification_rollback_eligibility,
    detect_rectification_origin_residues,
    resolve_rectification_documents,
)

TENANT = "TENANT-A"
OTHER_TENANT = "TENANT-B"
STUDENT = "STUDENT-1"
SOURCE = "CLASS-6A"
YEAR = 2026


@pytest.fixture
def db():
    return AsyncMongoMockClient()["sigesc_rectification_f21c"]


def vdoc(code: str = "SIGESC-ABCD-2345", *, tenant: str = TENANT):
    return {
        "code": code,
        "verification_token": "a" * 32,
        "mantenedora_id": tenant,
        "student_id": STUDENT,
        "entity_id": STUDENT,
        "revoked": False,
        "revoked_at": None,
        "superseded_at": None,
        "created_at": "2026-03-01T10:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_inventory_empty_is_resolvable_but_requires_historical_ack(db):
    inv = await build_rectification_document_inventory(
        db,
        student_id=STUDENT,
        source_class_id=SOURCE,
        academic_year=YEAR,
        tenant_id=TENANT,
    )
    assert inv["can_resolve_for_execution"] is True
    assert inv["coverage_complete"] is False
    assert inv["can_prove_no_prior_issuance"] is False
    assert inv["requires_untracked_acknowledgement"] is True
    assert inv["blockers"] == []
    assert len(inv["inventory_digest"]) == 64


@pytest.mark.asyncio
async def test_school_log_without_verifiable_code_blocks_fail_closed(db):
    await db.school_documents_log.insert_one({
        "id": "LOG-1", "student_id": STUDENT, "class_id": SOURCE,
        "mantenedora_id": TENANT, "emitted_at": "2026-03-01T10:00:00+00:00",
    })
    inv = await build_rectification_document_inventory(
        db, student_id=STUDENT, source_class_id=SOURCE, academic_year=YEAR, tenant_id=TENANT
    )
    assert inv["can_resolve_for_execution"] is False
    assert "DOCUMENT_RESOLUTION_REQUIRED_F1_3" in {b["code"] for b in inv["blockers"]}


@pytest.mark.asyncio
async def test_manual_ficha_and_diary_snapshot_block(db):
    await db.manual_document_issuances.insert_one({
        "id": "MANUAL-1", "student_id": STUDENT, "mantenedora_id": TENANT,
        "class_id": SOURCE, "academic_year": YEAR,
    })
    await db.diary_snapshots.insert_one({
        "id": "DIARY-1", "class_id": SOURCE, "academic_year": YEAR, "mantenedora_id": TENANT,
    })
    inv = await build_rectification_document_inventory(
        db, student_id=STUDENT, source_class_id=SOURCE, academic_year=YEAR, tenant_id=TENANT
    )
    codes = {b["code"] for b in inv["blockers"]}
    assert "BLOCKED_DOCUMENT_REVIEW_REQUIRED" in codes
    assert "DIARY_SNAPSHOT_SUPERSESSION_REQUIRED" in codes


@pytest.mark.asyncio
async def test_revocable_documents_are_invalidated_with_protocol_and_tenant_scope(db):
    await db.verifiable_documents.insert_one(vdoc())
    await db.school_documents_log.insert_one({
        "id": "LOG-1", "student_id": STUDENT, "class_id": SOURCE,
        "mantenedora_id": TENANT, "code": "SIGESC-ABCD-2345",
        "emitted_at": "2026-03-01T10:00:00+00:00",
    })
    await db.bulletin_verifications.insert_one({
        "id": "BUL-1", "student_id": STUDENT, "academic_year": YEAR,
        "mantenedora_id": TENANT, "revoked_at": None, "created_at": "2026-03-02T10:00:00+00:00",
    })
    await db.history_verifications.insert_one({
        "id": "HIS-1", "student_id": STUDENT, "mantenedora_id": TENANT,
        "revoked_at": None, "created_at": "2026-03-03T10:00:00+00:00",
    })
    await db.verifiable_documents.insert_one(vdoc("SIGESC-WXYZ-6789", tenant=OTHER_TENANT))

    inv = await build_rectification_document_inventory(
        db, student_id=STUDENT, source_class_id=SOURCE, academic_year=YEAR, tenant_id=TENANT
    )
    assert inv["can_resolve_for_execution"] is True
    assert {x["kind"] for x in inv["revocable"]} == {
        "verifiable_document", "bulletin_verification", "history_verification"
    }

    out = await resolve_rectification_documents(
        db,
        protocol="RET-2026-001",
        student_id=STUDENT,
        source_class_id=SOURCE,
        academic_year=YEAR,
        tenant_id=TENANT,
        actor={"id": "ADMIN-1", "role": "super_admin"},
        acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
    )
    assert out["revoked_count"] == 3
    saved = await db.verifiable_documents.find_one({"code": "SIGESC-ABCD-2345"}, {"_id": 0})
    assert saved["revoked"] is True
    bulletin = await db.bulletin_verifications.find_one({"id": "BUL-1"}, {"_id": 0})
    history = await db.history_verifications.find_one({"id": "HIS-1"}, {"_id": 0})
    assert bulletin["revoked_at"] and bulletin["rectification_protocol"] == "RET-2026-001"
    assert history["revoked_at"] and history["rectification_protocol"] == "RET-2026-001"
    other = await db.verifiable_documents.find_one({"code": "SIGESC-WXYZ-6789"}, {"_id": 0})
    assert other["revoked"] is False
    assert await db.document_rectifications.count_documents({"protocol": "RET-2026-001"}) == 3


@pytest.mark.asyncio
async def test_document_acknowledgement_is_exact_and_mandatory(db):
    with pytest.raises(DocumentRectificationError) as exc:
        await resolve_rectification_documents(
            db,
            protocol="RET-1",
            student_id=STUDENT,
            source_class_id=SOURCE,
            academic_year=YEAR,
            tenant_id=TENANT,
            actor={"id": "ADMIN-1", "role": "admin"},
            acknowledgement="estou ciente",
        )
    assert exc.value.code == "DOCUMENT_UNTRACKED_ACKNOWLEDGEMENT_REQUIRED"


@pytest.mark.asyncio
async def test_rollback_blocks_irreversible_document_revocation(db):
    await db.document_rectifications.insert_one({
        "id": "DR-1", "mantenedora_id": TENANT, "protocol": "RET-1",
        "artifact_kind": "verifiable_document", "artifact_key": "x", "state": "APPLIED",
    })
    result = await check_rectification_rollback_eligibility(
        db,
        protocol="RET-1",
        student_id=STUDENT,
        source_class_id=SOURCE,
        academic_year=YEAR,
        tenant_id=TENANT,
        executed_at="2026-03-10T10:00:00+00:00",
    )
    assert result["eligible"] is False
    assert "ROLLBACK_DOCUMENT_REVOCATION_IRREVERSIBLE" in {b["code"] for b in result["blockers"]}


@pytest.mark.asyncio
async def test_rollback_blocks_new_document_after_execution(db):
    await db.school_documents_log.insert_one({
        "id": "NEW-LOG", "student_id": STUDENT, "mantenedora_id": TENANT,
        "class_id": SOURCE, "code": "SIGESC-ABCD-2345",
        "emitted_at": "2026-03-12T10:00:00+00:00",
    })
    await db.verifiable_documents.insert_one(vdoc())
    result = await check_rectification_rollback_eligibility(
        db,
        protocol="RET-2",
        student_id=STUDENT,
        source_class_id=SOURCE,
        academic_year=YEAR,
        tenant_id=TENANT,
        executed_at="2026-03-10T10:00:00+00:00",
    )
    assert result["eligible"] is False
    assert "ROLLBACK_NEW_DOCUMENT_ISSUANCE" in {b["code"] for b in result["blockers"]}


@pytest.mark.asyncio
async def test_origin_residue_detector_requires_academic_zero(db):
    await db.students.insert_one({"id": STUDENT, "mantenedora_id": TENANT, "class_id": SOURCE})
    await db.enrollments.insert_one({
        "id": "ENR-1", "student_id": STUDENT, "class_id": SOURCE, "status": "active",
        "academic_year": YEAR, "mantenedora_id": TENANT,
    })
    await db.attendance.insert_one({
        "id": "ATT-1", "class_id": SOURCE, "academic_year": YEAR, "mantenedora_id": TENANT,
        "records": [{"student_id": STUDENT, "status": "P"}],
    })
    await db.grades.insert_one({
        "id": "G-1", "student_id": STUDENT, "class_id": SOURCE,
        "academic_year": YEAR, "mantenedora_id": TENANT,
    })
    before = await detect_rectification_origin_residues(
        db, student_id=STUDENT, source_enrollment_id="ENR-1", source_class_id=SOURCE,
        academic_year=YEAR, tenant_id=TENANT,
    )
    assert before["ok"] is False
    assert all(v == 1 for v in before["residues"].values())

    await db.enrollments.update_one({"id": "ENR-1"}, {"$set": {"class_id": "DEST"}})
    await db.attendance.update_one({"id": "ATT-1"}, {"$set": {"records": []}})
    await db.grades.delete_one({"id": "G-1"})
    await db.students.update_one({"id": STUDENT}, {"$set": {"class_id": "DEST"}})
    after = await detect_rectification_origin_residues(
        db, student_id=STUDENT, source_enrollment_id="ENR-1", source_class_id=SOURCE,
        academic_year=YEAR, tenant_id=TENANT,
    )
    assert after["ok"] is True
