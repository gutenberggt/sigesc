"""F2.1A — compensable attendance primitive for enrollment rectification.

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
