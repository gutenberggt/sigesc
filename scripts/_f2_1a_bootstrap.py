from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

attendance_validation = r'''"""Canonical institutional validation/unvalidation for attendance documents.

F2.1A extracts the state transition from the HTTP router so normal attendance
routes and the future enrollment-rectification saga share one CAS-protected
implementation. RBAC remains the responsibility of each caller/route.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


MIN_RATIONALE_LENGTH = 30


class AttendanceValidationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.detail}


async def validate_attendance_institutional(
    db,
    attendance_id: str,
    *,
    user: dict[str, Any],
    request,
    audit_service,
    batch_marker: str | None = None,
) -> dict[str, Any]:
    att = await db.attendance.find_one({"id": attendance_id}, {"_id": 0})
    if not att:
        raise AttendanceValidationError("NOT_FOUND", "Frequência não encontrada", status_code=404)
    if att.get("validated_by"):
        raise AttendanceValidationError(
            "ALREADY_VALIDATED", "Frequência já validada institucionalmente."
        )
    if not (att.get("records") or []):
        raise AttendanceValidationError(
            "EMPTY_RECORDS", "Não é possível validar frequência sem registros.", status_code=422
        )

    previous_version = att.get("version") or 0
    new_version = previous_version + 1
    now = datetime.now(timezone.utc).isoformat()
    result = await db.attendance.update_one(
        {"id": attendance_id, "version": previous_version},
        {
            "$set": {
                "validated_by": user["id"],
                "validated_by_name": user.get("full_name") or user.get("email"),
                "validated_by_role": user.get("role"),
                "validated_at": now,
                "version": new_version,
                "updated_at": now,
                "updated_by": user["id"],
            }
        },
    )
    if result.matched_count != 1:
        raise AttendanceValidationError(
            "VERSION_CONFLICT",
            "A frequência mudou durante a validação institucional. Recarregue e tente novamente.",
            detail={"attendance_id": attendance_id, "expected_version": previous_version},
        )

    klass = await db.classes.find_one(
        {"id": att.get("class_id")}, {"_id": 0, "name": 1, "school_id": 1}
    )
    await audit_service.log(
        action="validate_attendance",
        collection="attendance",
        user=user,
        request=request,
        document_id=attendance_id,
        description=(
            f"Validou frequência institucional da turma "
            f"{(klass or {}).get('name', '—')} em {att.get('date')}"
        ),
        school_id=(klass or {}).get("school_id"),
        academic_year=att.get("academic_year"),
        extra_data={
            "entity_type": "attendance",
            "change_kind": "validation",
            "class_id": att.get("class_id"),
            "date": att.get("date"),
            "previous_version": previous_version,
            "new_version": new_version,
            "batch_marker": batch_marker,
        },
    )
    return await db.attendance.find_one({"id": attendance_id}, {"_id": 0})


async def unvalidate_attendance_institutional(
    db,
    attendance_id: str,
    *,
    user: dict[str, Any],
    request,
    audit_service,
    rationale: str,
    allow_management_override: bool = False,
) -> dict[str, Any]:
    normalized = (rationale or "").strip()
    if len(normalized) < MIN_RATIONALE_LENGTH:
        raise AttendanceValidationError(
            "RATIONALE_TOO_SHORT",
            "Justificativa deve ter ao menos 30 caracteres.",
            status_code=422,
        )

    att = await db.attendance.find_one({"id": attendance_id}, {"_id": 0})
    if not att:
        raise AttendanceValidationError("NOT_FOUND", "Frequência não encontrada", status_code=404)
    if not att.get("validated_by"):
        raise AttendanceValidationError(
            "NOT_VALIDATED", "Frequência não está validada — nada a reverter."
        )

    role = user.get("role")
    normal_admin = role in ("admin", "admin_teste", "super_admin")
    rectification_manager = allow_management_override and role in ("admin", "super_admin", "gerente")
    if att.get("validated_by") != user.get("id") and not normal_admin and not rectification_manager:
        raise AttendanceValidationError(
            "FORBIDDEN_UNVALIDATE",
            "Apenas o autor da validação ou admin/super_admin podem reverter.",
            status_code=403,
        )

    previous_version = att.get("version") or 0
    new_version = previous_version + 1
    now = datetime.now(timezone.utc).isoformat()
    previous_validation = {
        "validated_by": att.get("validated_by"),
        "validated_by_name": att.get("validated_by_name"),
        "validated_by_role": att.get("validated_by_role"),
        "validated_at": att.get("validated_at"),
    }
    result = await db.attendance.update_one(
        {"id": attendance_id, "version": previous_version},
        {
            "$set": {
                "validated_by": None,
                "validated_by_name": None,
                "validated_by_role": None,
                "validated_at": None,
                "version": new_version,
                "updated_at": now,
                "updated_by": user["id"],
            },
            "$push": {
                "validation_history": {
                    **previous_validation,
                    "unvalidated_by": user["id"],
                    "unvalidated_by_name": user.get("full_name"),
                    "unvalidated_at": now,
                    "rationale": normalized,
                }
            },
        },
    )
    if result.matched_count != 1:
        raise AttendanceValidationError(
            "VERSION_CONFLICT",
            "A frequência mudou durante a reversão da validação. Recarregue e tente novamente.",
            detail={"attendance_id": attendance_id, "expected_version": previous_version},
        )

    klass = await db.classes.find_one(
        {"id": att.get("class_id")}, {"_id": 0, "name": 1, "school_id": 1}
    )
    await audit_service.log(
        action="unvalidate_attendance",
        collection="attendance",
        user=user,
        request=request,
        document_id=attendance_id,
        description=(
            f"REVERTEU validação institucional da turma "
            f"{(klass or {}).get('name', '—')} em {att.get('date')}: {normalized[:80]}"
        ),
        school_id=(klass or {}).get("school_id"),
        academic_year=att.get("academic_year"),
        old_value=previous_validation,
        extra_data={
            "entity_type": "attendance",
            "change_kind": "unvalidation",
            "class_id": att.get("class_id"),
            "date": att.get("date"),
            "rationale": normalized,
            "previous_version": previous_version,
            "new_version": new_version,
        },
    )
    return await db.attendance.find_one({"id": attendance_id}, {"_id": 0})
'''

rectification_attendance = r'''"""F2.1A — compensable attendance primitive for enrollment rectification.

Internal-only module: there is intentionally no HTTP route that invokes it.
It removes only the student's record from the erroneous source-class lesson,
creates an individual administrative ledger entry, and never fabricates a
lesson in the destination class.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from services.attendance_validation import (
    AttendanceValidationError,
    unvalidate_attendance_institutional,
)

LEDGER_COLLECTION = "attendance_rectifications"
LEDGER_INDEX_NAME = "uq_attendance_rectification_protocol_source_student"
ALLOWED_ACTOR_ROLES = frozenset({"admin", "super_admin", "gerente"})
IDENTITY_FIELDS = (
    "class_id",
    "date",
    "course_id",
    "aula_numero",
    "assignment_id",
    "academic_year",
)


class AttendanceRectificationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.detail}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _ledger_key(*, tenant_id: str, protocol: str, attendance_id: str, student_id: str) -> dict[str, str]:
    return {
        "mantenedora_id": tenant_id,
        "protocol": protocol,
        "source_attendance_id": attendance_id,
        "student_id": student_id,
    }


async def ensure_attendance_rectification_indexes(db) -> None:
    await db[LEDGER_COLLECTION].create_index(
        [
            ("mantenedora_id", 1),
            ("protocol", 1),
            ("source_attendance_id", 1),
            ("student_id", 1),
        ],
        unique=True,
        name=LEDGER_INDEX_NAME,
    )


def project_effective_attendance_rectification(ledger: Mapping[str, Any]) -> dict[str, Any] | None:
    """Read-side shadow only; not connected to official frequency calculations."""
    if ledger.get("state") != "APPLIED":
        return None
    anti_double_count_key = ":".join(
        str(ledger.get(field) or "")
        for field in (
            "mantenedora_id",
            "student_id",
            "target_enrollment_id",
            "source_attendance_id",
            "source_aula_numero",
        )
    )
    return {
        "anti_double_count_key": anti_double_count_key,
        "student_id": ledger.get("student_id"),
        "target_enrollment_id": ledger.get("target_enrollment_id"),
        "target_class_id": ledger.get("target_class_id"),
        "academic_year": ledger.get("academic_year"),
        "source_date": ledger.get("source_date"),
        "source_course_id": ledger.get("source_course_id"),
        "target_course_id": ledger.get("target_course_id"),
        "source_aula_numero": ledger.get("source_aula_numero"),
        "attendance_status": ledger.get("attendance_status"),
        "requires_revalidation": bool(ledger.get("requires_revalidation")),
    }


async def _mark_failed(db, key: Mapping[str, Any], *, code: str, message: str) -> None:
    await db[LEDGER_COLLECTION].update_one(
        dict(key),
        {"$set": {"state": "FAILED_RECOVERABLE", "failure_code": code, "failure_message": message, "failed_at": _now()}},
    )


async def apply_attendance_rectification_item(
    db,
    *,
    manifest_item: Mapping[str, Any],
    protocol: str,
    tenant_id: str,
    student_id: str,
    source_class_id: str,
    target_enrollment_id: str,
    target_class_id: str,
    academic_year: int,
    actor: Mapping[str, Any],
    request,
    audit_service,
) -> dict[str, Any]:
    """Apply exactly one attendance-manifest item under the future saga lock."""
    if actor.get("role") not in ALLOWED_ACTOR_ROLES:
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_ACTOR_FORBIDDEN",
            "O perfil não pode executar o primitivo interno de retificação de frequência.",
            status_code=403,
        )
    attendance_id = str(manifest_item.get("source_attendance_id") or "")
    if not attendance_id or not protocol or not tenant_id or not student_id or not source_class_id:
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_INPUT_INVALID",
            "Protocolo, tenant, estudante, turma de origem e attendance são obrigatórios.",
            status_code=422,
        )

    await ensure_attendance_rectification_indexes(db)
    key = _ledger_key(
        tenant_id=tenant_id,
        protocol=protocol,
        attendance_id=attendance_id,
        student_id=student_id,
    )
    prior = await db[LEDGER_COLLECTION].find_one(key, {"_id": 0})
    if prior and prior.get("state") == "APPLIED":
        return {**prior, "idempotent_replay": True}
    if prior and prior.get("state") == "FAILED_RECOVERABLE":
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_RECOVERY_REQUIRED",
            "A etapa anterior falhou após iniciar a cadeia institucional e exige recuperação explícita.",
            detail={"source_attendance_id": attendance_id},
        )

    att = await db.attendance.find_one({"id": attendance_id}, {"_id": 0})
    if not att:
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_NOT_FOUND", "Frequência de origem não encontrada.", status_code=404
        )
    if str(att.get("mantenedora_id") or "") != str(tenant_id):
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_TENANT_MISMATCH",
            "A frequência não pertence ao tenant operacional.",
            status_code=403,
        )
    if str(att.get("class_id") or "") != str(source_class_id):
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_SOURCE_CLASS_MISMATCH",
            "A frequência não pertence à turma de origem revalidada.",
        )
    if str(att.get("academic_year")) != str(academic_year):
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_YEAR_MISMATCH", "Ano letivo da frequência divergiu do dry-run."
        )

    for manifest_field, doc_field in (
        ("source_date", "date"),
        ("source_course_id", "course_id"),
        ("source_aula_numero", "aula_numero"),
        ("source_assignment_id", "assignment_id"),
    ):
        expected = manifest_item.get(manifest_field)
        if expected is not None and att.get(doc_field) != expected:
            raise AttendanceRectificationError(
                "RECTIFICATION_ATTENDANCE_IDENTITY_CHANGED",
                "A identidade da aula mudou após o dry-run.",
                detail={"field": doc_field, "expected": expected, "current": att.get(doc_field)},
            )

    current_version = att.get("version") or 0
    expected_version = manifest_item.get("version")
    if expected_version is not None and int(expected_version) != int(current_version):
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_VERSION_CONFLICT",
            "A frequência mudou após o dry-run.",
            detail={"expected_version": expected_version, "current_version": current_version},
        )
    if expected_version is None and att.get("version") not in (None, 0):
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_VERSION_CONFLICT",
            "O dry-run não possui a versão atual da frequência.",
            detail={"current_version": current_version},
        )

    matching = [r for r in (att.get("records") or []) if str(r.get("student_id")) == str(student_id)]
    if len(matching) != 1:
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_STUDENT_RECORD_MISMATCH",
            "O student-record esperado não existe de forma única na frequência de origem.",
            detail={"matches": len(matching)},
        )
    source_record = matching[0]
    if manifest_item.get("status") is not None and source_record.get("status") != manifest_item.get("status"):
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_STATUS_CHANGED",
            "O status individual de frequência mudou após o dry-run.",
        )
    manifest_hash = manifest_item.get("student_record_hash") or manifest_item.get("record_hash")
    if manifest_hash and manifest_hash != _digest(source_record):
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_RECORD_HASH_CHANGED",
            "O hash do student-record divergiu do dry-run.",
        )

    identity_before = {field: att.get(field) for field in IDENTITY_FIELDS}
    remaining_records = [r for r in (att.get("records") or []) if str(r.get("student_id")) != str(student_id)]
    requires_revalidation = bool(att.get("validated_by") or att.get("validated_at"))
    created_at = _now()
    pending = {
        "id": str(uuid.uuid4()),
        **key,
        "rectification_protocol": protocol,
        "target_enrollment_id": target_enrollment_id,
        "target_class_id": target_class_id,
        "academic_year": academic_year,
        "source_class_id": source_class_id,
        "source_date": att.get("date"),
        "source_course_id": att.get("course_id"),
        "target_course_id": manifest_item.get("target_course_id"),
        "source_aula_numero": att.get("aula_numero"),
        "source_assignment_id": att.get("assignment_id"),
        "attendance_status": source_record.get("status"),
        "source_record": source_record,
        "source_record_hash": _digest(source_record),
        "source_document_hash_before": _digest(att),
        "requires_revalidation": requires_revalidation,
        "state": "PENDING",
        "created_at": created_at,
        "created_by": actor.get("id"),
        "actor_role": actor.get("role"),
        "version_before": current_version,
    }
    await db[LEDGER_COLLECTION].update_one(key, {"$setOnInsert": pending}, upsert=True)
    ledger = await db[LEDGER_COLLECTION].find_one(key, {"_id": 0})
    if ledger and ledger.get("state") == "APPLIED":
        return {**ledger, "idempotent_replay": True}

    version_for_pull = current_version
    if requires_revalidation:
        rationale = f"Retificação de matrícula/turma — protocolo {protocol}; desvalidação institucional auditada."
        try:
            unvalidated = await unvalidate_attendance_institutional(
                db,
                attendance_id,
                user=dict(actor),
                request=request,
                audit_service=audit_service,
                rationale=rationale,
                allow_management_override=True,
            )
        except AttendanceValidationError as exc:
            await _mark_failed(db, key, code=exc.code, message=exc.message)
            raise AttendanceRectificationError(
                "RECTIFICATION_ATTENDANCE_UNVALIDATION_FAILED",
                "Falha ao desvalidar a frequência antes da retificação.",
                detail={"cause": exc.code},
            ) from exc
        version_for_pull = unvalidated.get("version") or (current_version + 1)

    now = _now()
    result = await db.attendance.update_one(
        {
            "id": attendance_id,
            "mantenedora_id": tenant_id,
            "class_id": source_class_id,
            "version": version_for_pull,
            "records.student_id": student_id,
        },
        {
            "$set": {
                "records": remaining_records,
                "version": version_for_pull + 1,
                "updated_at": now,
                "updated_by": actor.get("id"),
            }
        },
    )
    if result.matched_count != 1:
        await _mark_failed(
            db,
            key,
            code="RECTIFICATION_ATTENDANCE_PULL_CAS_CONFLICT",
            message="CAS falhou após a preparação da etapa; a validação antiga não foi recriada.",
        )
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_PULL_CAS_CONFLICT",
            "A frequência mudou durante a retirada individual; recuperação explícita é necessária.",
        )

    post = await db.attendance.find_one({"id": attendance_id}, {"_id": 0})
    if any(str(r.get("student_id")) == str(student_id) for r in (post.get("records") or [])):
        await _mark_failed(db, key, code="RECTIFICATION_ATTENDANCE_POSTCONDITION_FAILED", message="Student-record permaneceu na origem.")
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_POSTCONDITION_FAILED", "O student-record permaneceu na frequência de origem."
        )
    if (post.get("records") or []) != remaining_records:
        await _mark_failed(db, key, code="RECTIFICATION_ATTENDANCE_PEERS_CHANGED", message="Records de outros estudantes divergiram.")
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_PEERS_CHANGED", "Registros de outros estudantes foram alterados."
        )
    identity_after = {field: post.get(field) for field in IDENTITY_FIELDS}
    if identity_after != identity_before:
        await _mark_failed(db, key, code="RECTIFICATION_ATTENDANCE_IDENTITY_MUTATED", message="Identidade da aula foi alterada.")
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_IDENTITY_MUTATED", "A identidade da aula foi alterada indevidamente."
        )
    if requires_revalidation and any(post.get(k) is not None for k in ("validated_by", "validated_by_name", "validated_by_role", "validated_at")):
        await _mark_failed(db, key, code="RECTIFICATION_ATTENDANCE_VALIDATION_SURVIVED", message="Selo antigo sobreviveu à mudança de payload.")
        raise AttendanceRectificationError(
            "RECTIFICATION_ATTENDANCE_VALIDATION_SURVIVED", "A validação anterior não foi removida corretamente."
        )

    applied_at = _now()
    await db[LEDGER_COLLECTION].update_one(
        key,
        {
            "$set": {
                "state": "APPLIED",
                "applied_at": applied_at,
                "version_after": post.get("version"),
                "source_document_hash_after": _digest(post),
                "attendance_revalidation_pending": requires_revalidation,
            },
            "$unset": {"failure_code": "", "failure_message": "", "failed_at": ""},
        },
    )
    final = await db[LEDGER_COLLECTION].find_one(key, {"_id": 0})
    return {**final, "idempotent_replay": False}
'''

tests = r'''from __future__ import annotations

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
    await db.attendance.insert_one(doc)
    return doc


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
'''

workflow = r'''name: Enrollment Rectification F2.1A - Attendance Guard

on:
  pull_request:
    paths:
      - 'backend/services/attendance_validation.py'
      - 'backend/services/enrollment_rectification_attendance.py'
      - 'backend/routers/attendance.py'
      - 'backend/services/enrollment_rectification.py'
      - 'backend/services/enrollment_rectification_execution.py'
      - 'backend/routers/enrollment_rectification.py'
      - 'backend/routers/enrollment_rectification_execution.py'
      - 'backend/tests/test_enrollment_rectification_f1_dry_run.py'
      - 'backend/tests/test_enrollment_rectification_f2_safety_kernel.py'
      - 'backend/tests/test_enrollment_rectification_f2_1a_attendance.py'
      - 'docs/governance/RETIFICACAO_MATRICULA_TURMA_F2_1A.md'
      - '.github/workflows/enrollment-rectification-f2-1a-attendance-guard.yml'
  workflow_dispatch:

permissions:
  contents: read

jobs:
  f2-1a-attendance:
    name: F2.1A - Attendance ledger and CAS
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
          cache-dependency-path: backend/requirements.txt
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r backend/requirements.txt
          pip install pytest pytest-asyncio mongomock mongomock-motor
      - name: Compile F1/F2/F2.1A contracts
        working-directory: backend
        run: |
          python -m py_compile \
            services/attendance_validation.py \
            services/enrollment_rectification_attendance.py \
            services/enrollment_rectification.py \
            services/enrollment_rectification_execution.py \
            routers/attendance.py \
            routers/enrollment_rectification.py \
            routers/enrollment_rectification_execution.py
      - name: Run rectification regression
        working-directory: backend
        env:
          MONGO_URL: 'mongodb://127.0.0.1:27017'
          DB_NAME: 'sigesc_rectification_f21a_conftest_unused'
          JWT_SECRET_KEY: 'ci-only-jwt-secret-0123456789abcdef0123456789abcdef'
          ENROLLMENT_RECTIFICATION_DRY_RUN_SECRET: 'ci-only-rectification-secret-0123456789abcdef0123456789abcdef'
          ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED: 'false'
        run: |
          python -m pytest \
            tests/test_enrollment_rectification_f1_dry_run.py \
            tests/test_enrollment_rectification_f2_safety_kernel.py \
            tests/test_enrollment_rectification_f2_1a_attendance.py \
            -q --asyncio-mode=auto
      - name: Structural fail-closed guard
        working-directory: backend
        run: |
          python - <<'PY'
          from pathlib import Path
          service = Path('services/enrollment_rectification_attendance.py').read_text(encoding='utf-8')
          if 'APIRouter' in service or '@router.' in service:
              raise SystemExit('F2.1A attendance primitive must remain internal-only')
          for rel in ('routers/enrollment_rectification.py', 'routers/enrollment_rectification_execution.py'):
              src = Path(rel).read_text(encoding='utf-8')
              for route in ('/execute', '/rollback'):
                  if f'@router.post("{route}")' in src:
                      raise SystemExit(f'Forbidden rectification route exposed: {route}')
          if 'ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED' in service:
              raise SystemExit('F2.1A must not enable global academic execution')
          if 'db.students.' in service or 'db.enrollments.' in service or 'db.grades.' in service:
              raise SystemExit('F2.1A attendance module touched out-of-scope academic collections')
          print('F2.1A structural guard: PASS')
          PY
'''

# Write new files.
(ROOT / "backend/services/attendance_validation.py").write_text(attendance_validation, encoding="utf-8")
(ROOT / "backend/services/enrollment_rectification_attendance.py").write_text(rectification_attendance, encoding="utf-8")
(ROOT / "backend/tests/test_enrollment_rectification_f2_1a_attendance.py").write_text(tests, encoding="utf-8")
(ROOT / ".github/workflows/enrollment-rectification-f2-1a-attendance-guard.yml").write_text(workflow, encoding="utf-8")

# Patch attendance router without rewriting unrelated code.
router_path = ROOT / "backend/routers/attendance.py"
text = router_path.read_text(encoding="utf-8")
import_anchor = "from utils.academic_event_lens import resolve_student_ownership, record_lock_audit\n"
service_import = '''from services.attendance_validation import (\n    AttendanceValidationError,\n    unvalidate_attendance_institutional,\n    validate_attendance_institutional,\n)\n'''
if service_import not in text:
    if import_anchor not in text:
        raise SystemExit("attendance import anchor not found")
    text = text.replace(import_anchor, import_anchor + service_import, 1)

start = text.index("    async def _validate_single(current_db, attendance_id: str")
end = text.index('    @router.post("/{attendance_id}/validate")', start)
wrapper = '''    async def _validate_single(current_db, attendance_id: str, *, user, request, batch_marker: str = None):\n        """Delegates institutional validation to the canonical CAS service."""\n        try:\n            return await validate_attendance_institutional(\n                current_db, attendance_id, user=user, request=request,\n                audit_service=audit_service, batch_marker=batch_marker,\n            )\n        except AttendanceValidationError as exc:\n            # Preserve the legacy batch contract (reason string per item).\n            raise ValueError(exc.code) from exc\n\n'''
text = text[:start] + wrapper + text[end:]

empty_records_map = '''            if code == "EMPTY_RECORDS":\n                raise HTTPException(status_code=422, detail={"code": "EMPTY_RECORDS",\n                                                              "message": "Não é possível validar frequência sem registros."})\n            raise\n'''
empty_records_new = '''            if code == "EMPTY_RECORDS":\n                raise HTTPException(status_code=422, detail={"code": "EMPTY_RECORDS",\n                                                              "message": "Não é possível validar frequência sem registros."})\n            if code == "VERSION_CONFLICT":\n                raise HTTPException(status_code=409, detail={\n                    "code": "VERSION_CONFLICT",\n                    "message": "A frequência mudou durante a validação institucional. Recarregue e tente novamente.",\n                })\n            raise\n'''
if empty_records_map not in text:
    raise SystemExit("validate endpoint mapping anchor not found")
text = text.replace(empty_records_map, empty_records_new, 1)

unval_start = text.index('    @router.post("/{attendance_id}/unvalidate")')
unval_end = text.index('    @router.delete("/{attendance_id}")', unval_start)
unval_block = '''    @router.post("/{attendance_id}/unvalidate")\n    async def unvalidate_attendance(attendance_id: str, payload: UnvalidateRequest, request: Request):\n        """Reverte validação usando o serviço canônico CAS, preservando a API atual."""\n        current_user = await AuthMiddleware.require_roles(VALIDATE_ROLES)(request)\n        current_db = get_db_for_user(current_user)\n        try:\n            return await unvalidate_attendance_institutional(\n                current_db, attendance_id, user=current_user, request=request,\n                audit_service=audit_service, rationale=payload.rationale,\n                allow_management_override=False,\n            )\n        except AttendanceValidationError as exc:\n            if exc.code == "NOT_FOUND":\n                raise HTTPException(status_code=404, detail="Frequência não encontrada")\n            if exc.code == "RATIONALE_TOO_SHORT":\n                raise HTTPException(status_code=422, detail=exc.as_detail())\n            if exc.code == "FORBIDDEN_UNVALIDATE":\n                raise HTTPException(status_code=403, detail=exc.as_detail())\n            if exc.code in ("NOT_VALIDATED", "VERSION_CONFLICT"):\n                raise HTTPException(status_code=409, detail=exc.as_detail())\n            raise\n\n'''
text = text[:unval_start] + unval_block + text[unval_end:]
router_path.write_text(text, encoding="utf-8")

print("F2.1A bootstrap patch applied")
