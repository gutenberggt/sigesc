"""Canonical institutional validation/unvalidation for attendance documents.

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
