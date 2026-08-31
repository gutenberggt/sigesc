#!/usr/bin/env python3
"""P0 #250 F2.9C — executor autorizado dos 48 targets selados na F2.9B.

Este executor só aceita o manifesto privado exato produzido pela F2.9B. Antes
de qualquer escrita ele valida a cadeia criptográfica, exige autorização
explícita e revalida as precondições. A escrita normal é insert_one em
teacher_class_assignments. Em falha, o rollback compensatório usa delete_one
somente quando o documento continua exatamente igual ao target selado.
"""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from typing import Any, Callable, Mapping

from pymongo import MongoClient

PHASE_ID = "P0-250-F2.9C-AUTHORIZED-48-DVD-BACKFILL-2026"
PRIVATE_RECEIPT_SCHEMA = "P0_250_F2_9C_PRIVATE_EXECUTION_RECEIPT_V1"
PUBLIC_RECEIPT_SCHEMA = "P0_250_F2_9C_PUBLIC_EXECUTION_RECEIPT_V1"

SEALED_PHASE_ID = "P0-250-F2.9B-SEALED-48-DVD-TARGETS-2026"
SEALED_PRIVATE_SCHEMA = "P0_250_F2_9B_SEALED_BACKFILL_TARGETS_V1"
SEALED_MODE = "READ_ONLY_SEAL"

ACADEMIC_YEAR = 2026
REFERENCE_DATE = "2026-08-31"
EXPECTED_TARGET_COUNT = 48

SOURCE_F2_9A_MAIN_SHA = "794cf799a8f4091d35401d45d8203109b4e5dd0d"
SOURCE_F2_9A_PLAN_SHA256 = (
    "fbfe46dd455e45ad65c510d75022d52918c8993c21cc76593f1915d5324fb177"
)
SOURCE_F2_9B_TARGET_SHA = "eea0ee3b9905b65e82e440243566b6f44926f7af"
SOURCE_F2_9B_ARTIFACT_ID = 9745250820
SOURCE_F2_9B_ARTIFACT_DIGEST = (
    "26d0904d231a7ed23f41487a57a8e2fd08b0e0b6ac96b14ef7897d130123ddfd"
)
EXPECTED_TARGETS_SHA256 = (
    "fbfe46dd455e45ad65c510d75022d52918c8993c21cc76593f1915d5324fb177"
)
EXPECTED_OPERATIONS_SHA256 = (
    "f3fb8c4b7d8d3a9e51939b8cf2d40e756759744e431471d073afd038295b47e5"
)
EXPECTED_BUNDLE_SHA256 = (
    "ddca5bb662a5670b96459ad5f5748f123ed65e52bdd2fe739e933b18d4d164d4"
)

AUTHORIZATION_MARKER = (
    "P0-250-F2.9C-BUNDLE-"
    "ddca5bb662a5670b96459ad5f5748f123ed65e52bdd2fe739e933b18d4d164d4-"
    "EXPLICIT-AUTHORIZED-2026-08-31"
)

TARGET_REQUIRED = frozenset(
    {
        "id",
        "teacher_id",
        "class_id",
        "component_id",
        "school_id",
        "mantenedora_id",
        "deleted",
        "valid_from",
        "valid_until",
        "diary_settings",
        "is_substitute",
        "grades_official_owner",
    }
)
TARGET_OPTIONAL = frozenset({"shift"})
DIARY_KEYS = frozenset({"enabled", "schema_version", "profile", "student_scope"})


class F29CExecutionError(RuntimeError):
    """Violação fail-closed do contrato F2.9C."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _without_mongo_id(document: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if document is None:
        return None
    clean = dict(document)
    clean.pop("_id", None)
    return clean


def _validate_target_shape(target: Mapping[str, Any]) -> None:
    keys = set(target)
    if TARGET_REQUIRED - keys:
        raise F29CExecutionError("SEALED_TARGET_REQUIRED_FIELDS_MISSING")
    if keys - TARGET_REQUIRED - TARGET_OPTIONAL:
        raise F29CExecutionError("SEALED_TARGET_UNAPPROVED_FIELDS_PRESENT")
    for key in (
        "id",
        "teacher_id",
        "class_id",
        "component_id",
        "school_id",
        "mantenedora_id",
        "valid_from",
    ):
        if not sid(target.get(key)):
            raise F29CExecutionError(f"SEALED_TARGET_EMPTY_{key}")
    if target.get("deleted") is not False:
        raise F29CExecutionError("SEALED_TARGET_DELETED_FLAG_INVALID")

    settings = target.get("diary_settings")
    if not isinstance(settings, Mapping) or set(settings) != DIARY_KEYS:
        raise F29CExecutionError("SEALED_TARGET_DIARY_SETTINGS_SHAPE_INVALID")
    if settings.get("enabled") is not True or settings.get("schema_version") != 1:
        raise F29CExecutionError("SEALED_TARGET_DIARY_SETTINGS_NOT_ENABLED_V1")
    if settings.get("profile") not in {"regular", "integrator", "shared"}:
        raise F29CExecutionError("SEALED_TARGET_PROFILE_INVALID")
    if settings.get("student_scope") not in {"all", "group"}:
        raise F29CExecutionError("SEALED_TARGET_STUDENT_SCOPE_INVALID")
    if settings.get("student_scope") == "group" and settings.get("profile") != "shared":
        raise F29CExecutionError("SEALED_TARGET_GROUP_SCOPE_PROFILE_INVALID")


def validate_sealed_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_target_count: int | None = None,
    expected_targets_sha256: str | None = None,
    expected_operations_sha256: str | None = None,
    expected_bundle_sha256: str | None = None,
) -> list[dict[str, Any]]:
    expected_target_count = (
        EXPECTED_TARGET_COUNT
        if expected_target_count is None
        else expected_target_count
    )
    expected_targets_sha256 = (
        EXPECTED_TARGETS_SHA256
        if expected_targets_sha256 is None
        else expected_targets_sha256
    )
    expected_operations_sha256 = (
        EXPECTED_OPERATIONS_SHA256
        if expected_operations_sha256 is None
        else expected_operations_sha256
    )
    expected_bundle_sha256 = (
        EXPECTED_BUNDLE_SHA256
        if expected_bundle_sha256 is None
        else expected_bundle_sha256
    )
    if (
        manifest.get("schema") != SEALED_PRIVATE_SCHEMA
        or manifest.get("phase") != SEALED_PHASE_ID
        or manifest.get("mode") != SEALED_MODE
        or manifest.get("status") != "PASS"
    ):
        raise F29CExecutionError("SEALED_MANIFEST_IDENTITY_INVALID")
    if manifest.get("database_mutation") is not False:
        raise F29CExecutionError("SEALED_MANIFEST_MUTATION_FLAG_INVALID")
    if manifest.get("production_database_writes") is not False:
        raise F29CExecutionError("SEALED_MANIFEST_WRITE_FLAG_INVALID")
    if manifest.get("automatic_apply_authorized") is not False:
        raise F29CExecutionError("SEALED_MANIFEST_AUTO_APPLY_FLAG_INVALID")
    if int(manifest.get("expected_target_count") or 0) != expected_target_count:
        raise F29CExecutionError("SEALED_MANIFEST_TARGET_COUNT_INVALID")

    source = manifest.get("source") or {}
    if source.get("f2_9a_main_sha") != SOURCE_F2_9A_MAIN_SHA:
        raise F29CExecutionError("SEALED_SOURCE_F2_9A_SHA_INVALID")
    if source.get("plan_sha256") != SOURCE_F2_9A_PLAN_SHA256:
        raise F29CExecutionError("SEALED_SOURCE_PLAN_SHA_INVALID")
    if int(source.get("academic_year") or 0) != ACADEMIC_YEAR:
        raise F29CExecutionError("SEALED_SOURCE_YEAR_INVALID")
    if source.get("reference_date") != REFERENCE_DATE:
        raise F29CExecutionError("SEALED_SOURCE_REFERENCE_DATE_INVALID")

    operations = deepcopy(list(manifest.get("operations") or []))
    if len(operations) != expected_target_count:
        raise F29CExecutionError("SEALED_OPERATION_COUNT_INVALID")

    targets: list[dict[str, Any]] = []
    target_ids: set[str] = set()
    natural_keys: set[tuple[str, str, str]] = set()
    source_keys: set[tuple[str, str, str]] = set()

    for expected_ordinal, operation in enumerate(operations, start=1):
        if int(operation.get("ordinal") or 0) != expected_ordinal:
            raise F29CExecutionError(
                f"SEALED_OPERATION_SEQUENCE_INVALID_AT_{expected_ordinal}"
            )
        if operation.get("operation") != "INSERT_TEACHER_CLASS_ASSIGNMENT":
            raise F29CExecutionError(
                f"SEALED_OPERATION_TYPE_INVALID_AT_{expected_ordinal}"
            )

        target = operation.get("target_assignment")
        if not isinstance(target, Mapping):
            raise F29CExecutionError(f"SEALED_TARGET_MISSING_AT_{expected_ordinal}")
        _validate_target_shape(target)
        target = dict(target)
        target_hash = sha256_value(target)
        if operation.get("target_assignment_sha256") != target_hash:
            raise F29CExecutionError(
                f"SEALED_TARGET_HASH_INVALID_AT_{expected_ordinal}"
            )

        target_id = sid(target.get("id"))
        natural_key = (
            sid(target.get("teacher_id")),
            sid(target.get("class_id")),
            sid(target.get("component_id")),
        )

        source_key = operation.get("source_legacy_key") or {}
        source_tuple = (
            sid(source_key.get("staff_id")),
            sid(source_key.get("class_id")),
            sid(source_key.get("course_id")),
        )
        if (
            int(source_key.get("academic_year") or 0) != ACADEMIC_YEAR
            or source_key.get("active_statuses") != ["ativo", "active"]
            or not all(source_tuple)
        ):
            raise F29CExecutionError(
                f"SEALED_SOURCE_KEY_INVALID_AT_{expected_ordinal}"
            )

        preconditions = operation.get("sealed_preconditions") or {}
        expected_preconditions = {
            "source_legacy_count": 1,
            "target_id_count": 0,
            "other_teacher_official_grade_owner_count": 0,
            "reference_date": REFERENCE_DATE,
            "must_reappear_identically_in_f2_9a_plan_before_apply": True,
        }
        if preconditions != expected_preconditions:
            raise F29CExecutionError(
                f"SEALED_PRECONDITIONS_INVALID_AT_{expected_ordinal}"
            )

        rollback = operation.get("rollback_contract") or {}
        if (
            rollback.get("mode") != "DELETE_INSERTED_IF_EXACT_PROJECTED_MATCH"
            or sid(rollback.get("target_assignment_id")) != target_id
            or rollback.get("target_assignment_sha256") != target_hash
        ):
            raise F29CExecutionError(
                f"SEALED_ROLLBACK_CONTRACT_INVALID_AT_{expected_ordinal}"
            )

        if (
            target_id in target_ids
            or natural_key in natural_keys
            or source_tuple in source_keys
        ):
            raise F29CExecutionError(f"SEALED_DUPLICATE_KEY_AT_{expected_ordinal}")
        target_ids.add(target_id)
        natural_keys.add(natural_key)
        source_keys.add(source_tuple)
        targets.append(target)

    if sha256_value(targets) != expected_targets_sha256:
        raise F29CExecutionError("SEALED_TARGETS_SHA_INVALID")
    if sha256_value(operations) != expected_operations_sha256:
        raise F29CExecutionError("SEALED_OPERATIONS_SHA_INVALID")
    if manifest.get("sealed_targets_sha256") != expected_targets_sha256:
        raise F29CExecutionError("SEALED_TARGETS_DECLARED_SHA_INVALID")
    if manifest.get("sealed_operations_sha256") != expected_operations_sha256:
        raise F29CExecutionError("SEALED_OPERATIONS_DECLARED_SHA_INVALID")

    core = dict(manifest)
    declared_bundle_hash = core.pop("sealed_bundle_sha256", None)
    if declared_bundle_hash != sha256_value(core):
        raise F29CExecutionError("SEALED_BUNDLE_SELF_HASH_INVALID")
    if declared_bundle_hash != expected_bundle_sha256:
        raise F29CExecutionError("SEALED_BUNDLE_NOT_EXPLICITLY_AUTHORIZED")

    return operations


def validate_live_reseal(
    sealed_manifest: Mapping[str, Any],
    live_reseal: Mapping[str, Any],
) -> None:
    if live_reseal.get("sealed_bundle_sha256") != EXPECTED_BUNDLE_SHA256:
        raise F29CExecutionError("LIVE_RESEAL_BUNDLE_SHA_DRIFT")
    if sha256_value(live_reseal) != sha256_value(sealed_manifest):
        raise F29CExecutionError("LIVE_RESEAL_NOT_IDENTICAL_TO_SEALED_MANIFEST")


def _active_on_reference(extra: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **dict(extra),
        "deleted": {"$ne": True},
        "diary_settings.enabled": True,
        "valid_from": {"$lte": REFERENCE_DATE},
        "$or": [{"valid_until": None}, {"valid_until": {"$gte": REFERENCE_DATE}}],
    }


def _source_filter(operation: Mapping[str, Any]) -> dict[str, Any]:
    source = operation["source_legacy_key"]
    return {
        "staff_id": source["staff_id"],
        "class_id": source["class_id"],
        "course_id": source["course_id"],
        "academic_year": ACADEMIC_YEAR,
        "status": {"$in": ["ativo", "active"]},
    }


def _natural_active_filter(target: Mapping[str, Any]) -> dict[str, Any]:
    return _active_on_reference(
        {
            "teacher_id": target["teacher_id"],
            "class_id": target["class_id"],
            "component_id": target["component_id"],
        }
    )


def _owner_conflict_filter(target: Mapping[str, Any]) -> dict[str, Any]:
    return _active_on_reference(
        {
            "class_id": target["class_id"],
            "component_id": target["component_id"],
            "teacher_id": {"$ne": target["teacher_id"]},
            "grades_official_owner": True,
        }
    )


def inspect_execution_state(
    db: Any,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    exact_ordinals: list[int] = []
    missing_ordinals: list[int] = []
    mismatch_ordinals: list[int] = []
    source_drift_ordinals: list[int] = []
    natural_drift_ordinals: list[int] = []
    owner_conflict_ordinals: list[int] = []

    for operation in operations:
        ordinal = int(operation["ordinal"])
        target = operation["target_assignment"]
        current = db.teacher_class_assignments.find_one({"id": target["id"]})
        clean = _without_mongo_id(current)

        if clean is None:
            missing_ordinals.append(ordinal)
            expected_natural_count = 0
        elif sha256_value(clean) == operation["target_assignment_sha256"]:
            exact_ordinals.append(ordinal)
            expected_natural_count = 1
        else:
            mismatch_ordinals.append(ordinal)
            expected_natural_count = -1

        if db.teacher_assignments.count_documents(_source_filter(operation)) != 1:
            source_drift_ordinals.append(ordinal)

        natural_count = db.teacher_class_assignments.count_documents(
            _natural_active_filter(target)
        )
        if expected_natural_count < 0 or natural_count != expected_natural_count:
            natural_drift_ordinals.append(ordinal)

        if target.get("grades_official_owner") is True:
            conflict_count = db.teacher_class_assignments.count_documents(
                _owner_conflict_filter(target)
            )
            if conflict_count != 0:
                owner_conflict_ordinals.append(ordinal)

    return {
        "exact_ordinals": exact_ordinals,
        "missing_ordinals": missing_ordinals,
        "mismatch_ordinals": mismatch_ordinals,
        "source_drift_ordinals": source_drift_ordinals,
        "natural_drift_ordinals": natural_drift_ordinals,
        "owner_conflict_ordinals": owner_conflict_ordinals,
    }


def _assert_state_clear(
    state: Mapping[str, Any],
    *,
    allow_all_exact: bool,
    expected_target_count: int | None = None,
) -> str:
    expected_target_count = (
        EXPECTED_TARGET_COUNT
        if expected_target_count is None
        else expected_target_count
    )
    exact = len(state["exact_ordinals"])
    missing = len(state["missing_ordinals"])

    if state["mismatch_ordinals"]:
        raise F29CExecutionError("TARGET_DOCUMENT_MISMATCH_PRESENT")
    if state["source_drift_ordinals"]:
        raise F29CExecutionError("SOURCE_LEGACY_PRECONDITION_DRIFT")
    if state["natural_drift_ordinals"]:
        raise F29CExecutionError("NATURAL_KEY_PRECONDITION_DRIFT")
    if state["owner_conflict_ordinals"]:
        raise F29CExecutionError("OFFICIAL_GRADE_OWNER_CONFLICT")

    if exact == 0 and missing == expected_target_count:
        return "ALL_MISSING"
    if allow_all_exact and exact == expected_target_count and missing == 0:
        return "ALL_EXACT"
    raise F29CExecutionError("PARTIAL_TARGET_STATE_FAIL_CLOSED")


def _exact_rollback_filter(
    mongo_id: Any,
    target: Mapping[str, Any],
) -> dict[str, Any]:
    return {"_id": mongo_id, **dict(target)}


def rollback_inserted(
    db: Any,
    applied: list[dict[str, Any]],
) -> dict[str, Any]:
    rolled_back = 0
    rollback_failed_ordinals: list[int] = []

    for entry in reversed(applied):
        ordinal = int(entry["ordinal"])
        target = entry["target_assignment"]
        current = db.teacher_class_assignments.find_one({"id": target["id"]})
        if current is None:
            rolled_back += 1
            continue
        clean = _without_mongo_id(current)
        if sha256_value(clean) != entry["target_assignment_sha256"]:
            rollback_failed_ordinals.append(ordinal)
            continue

        result = db.teacher_class_assignments.delete_one(
            _exact_rollback_filter(current["_id"], target)
        )
        if int(result.deleted_count) != 1:
            rollback_failed_ordinals.append(ordinal)
        else:
            rolled_back += 1

    remaining = 0
    for entry in applied:
        target_id = entry["target_assignment"]["id"]
        remaining += db.teacher_class_assignments.count_documents({"id": target_id})

    return {
        "attempted": len(applied),
        "rolled_back": rolled_back,
        "remaining_target_documents": remaining,
        "rollback_failed_ordinals": rollback_failed_ordinals,
        "complete": not rollback_failed_ordinals and remaining == 0,
    }


def apply_validated_operations(
    db: Any,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    applied: list[dict[str, Any]] = []

    try:
        for operation in operations:
            ordinal = int(operation["ordinal"])
            target = operation["target_assignment"]

            if db.teacher_assignments.count_documents(_source_filter(operation)) != 1:
                raise F29CExecutionError(f"PER_OPERATION_SOURCE_DRIFT_AT_{ordinal}")
            if db.teacher_class_assignments.count_documents({"id": target["id"]}) != 0:
                raise F29CExecutionError(
                    f"PER_OPERATION_TARGET_ID_PRESENT_AT_{ordinal}"
                )
            if (
                db.teacher_class_assignments.count_documents(
                    _natural_active_filter(target)
                )
                != 0
            ):
                raise F29CExecutionError(
                    f"PER_OPERATION_NATURAL_KEY_PRESENT_AT_{ordinal}"
                )
            if (
                target.get("grades_official_owner") is True
                and db.teacher_class_assignments.count_documents(
                    _owner_conflict_filter(target)
                )
                != 0
            ):
                raise F29CExecutionError(
                    f"PER_OPERATION_OWNER_CONFLICT_AT_{ordinal}"
                )

            candidate = deepcopy(target)
            result = db.teacher_class_assignments.insert_one(candidate)
            if result.inserted_id is None:
                raise F29CExecutionError(f"INSERT_NOT_ACKNOWLEDGED_AT_{ordinal}")

            applied_entry = {
                "ordinal": ordinal,
                "target_assignment": deepcopy(target),
                "target_assignment_sha256": operation["target_assignment_sha256"],
            }
            applied.append(applied_entry)

            current = db.teacher_class_assignments.find_one({"id": target["id"]})
            clean = _without_mongo_id(current)
            if clean is None or sha256_value(clean) != operation["target_assignment_sha256"]:
                raise F29CExecutionError(
                    f"POST_INSERT_EXACT_MATCH_FAILED_AT_{ordinal}"
                )
            if (
                db.teacher_class_assignments.count_documents(
                    _natural_active_filter(target)
                )
                != 1
            ):
                raise F29CExecutionError(
                    f"POST_INSERT_NATURAL_CARDINALITY_FAILED_AT_{ordinal}"
                )

        final_state = inspect_execution_state(db, operations)
        state_kind = _assert_state_clear(
            final_state,
            allow_all_exact=True,
            expected_target_count=len(operations),
        )
        if state_kind != "ALL_EXACT":
            raise F29CExecutionError("FINAL_STATE_NOT_ALL_EXACT")

    except Exception as exc:
        rollback = rollback_inserted(db, applied)
        if not rollback["complete"]:
            raise F29CExecutionError("CRITICAL_ROLLBACK_INCOMPLETE") from exc
        safe_reason = (
            str(exc)
            if isinstance(exc, F29CExecutionError)
            else type(exc).__name__
        )
        raise F29CExecutionError(
            f"EXECUTION_FAILED_ROLLED_BACK:{safe_reason}"
        ) from exc

    return {
        "inserted_count": len(applied),
        "verified_count": len(applied),
        "rollback_performed": False,
        "rollback_complete": True,
        "operations": [
            {
                "ordinal": entry["ordinal"],
                "outcome": "INSERTED_AND_EXACTLY_VERIFIED",
                "target_assignment_id": entry["target_assignment"]["id"],
                "target_assignment_sha256": entry["target_assignment_sha256"],
            }
            for entry in applied
        ],
    }


def _connect_database() -> Any:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise F29CExecutionError("MONGO_URL_MISSING")
    return MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]


def _build_receipts(
    *,
    classification: str,
    new_writes: int,
    verified_count: int,
    execution_operations: list[dict[str, Any]],
    idempotent: bool,
) -> dict[str, Any]:
    private_core = {
        "schema": PRIVATE_RECEIPT_SCHEMA,
        "phase": PHASE_ID,
        "status": "PASS",
        "classification": classification,
        "authorization_marker_sha256": hashlib.sha256(
            AUTHORIZATION_MARKER.encode("utf-8")
        ).hexdigest(),
        "sealed_source": {
            "f2_9b_target_sha": SOURCE_F2_9B_TARGET_SHA,
            "artifact_id": SOURCE_F2_9B_ARTIFACT_ID,
            "artifact_digest": SOURCE_F2_9B_ARTIFACT_DIGEST,
            "sealed_targets_sha256": EXPECTED_TARGETS_SHA256,
            "sealed_operations_sha256": EXPECTED_OPERATIONS_SHA256,
            "sealed_bundle_sha256": EXPECTED_BUNDLE_SHA256,
        },
        "expected_target_count": EXPECTED_TARGET_COUNT,
        "new_writes": new_writes,
        "verified_count": verified_count,
        "idempotent_replay": idempotent,
        "rollback_performed": False,
        "rollback_complete": True,
        "operations": execution_operations,
    }
    private = {
        **private_core,
        "execution_receipt_sha256": sha256_value(private_core),
    }
    public = {
        "schema": PUBLIC_RECEIPT_SCHEMA,
        "phase": PHASE_ID,
        "status": "PASS",
        "classification": classification,
        "database_mutation": new_writes > 0,
        "production_writes": new_writes > 0,
        "collection": "teacher_class_assignments",
        "mutation_primitive": "insert_one",
        "rollback_contract": "DELETE_INSERTED_IF_EXACT_PROJECTED_MATCH",
        "rollback_performed": False,
        "rollback_complete": True,
        "target_count": EXPECTED_TARGET_COUNT,
        "new_writes": new_writes,
        "verified_count": verified_count,
        "idempotent_replay": idempotent,
        "source_f2_9b_artifact_id": SOURCE_F2_9B_ARTIFACT_ID,
        "source_f2_9b_artifact_digest": SOURCE_F2_9B_ARTIFACT_DIGEST,
        "sealed_targets_sha256": EXPECTED_TARGETS_SHA256,
        "sealed_operations_sha256": EXPECTED_OPERATIONS_SHA256,
        "sealed_bundle_sha256": EXPECTED_BUNDLE_SHA256,
        "execution_receipt_sha256": private["execution_receipt_sha256"],
        "target_ids_emitted": False,
        "teacher_ids_emitted": False,
        "staff_ids_emitted": False,
        "student_data_read": False,
        "academic_data_read": False,
        "user_pii_emitted": False,
        "private_receipt_emitted_to_logs": False,
    }
    return {"public": public, "private": private}


def run_authorized_backfill(
    sealed_manifest: Mapping[str, Any],
    *,
    explicit_authorization: bool,
    authorization_marker: str,
    live_reseal_factory: Callable[[], Mapping[str, Any]] | None,
    db: Any | None = None,
) -> dict[str, Any]:
    if explicit_authorization is not True:
        raise F29CExecutionError("EXPLICIT_PRODUCTION_WRITE_AUTHORIZATION_REQUIRED")
    if authorization_marker != AUTHORIZATION_MARKER:
        raise F29CExecutionError("EXPLICIT_AUTHORIZATION_MARKER_INVALID")

    operations = validate_sealed_manifest(sealed_manifest)
    target_db = db if db is not None else _connect_database()

    initial_state = inspect_execution_state(target_db, operations)
    state_kind = _assert_state_clear(initial_state, allow_all_exact=True)
    if state_kind == "ALL_EXACT":
        exact_operations = [
            {
                "ordinal": operation["ordinal"],
                "outcome": "ALREADY_PRESENT_EXACT_IDEMPOTENT",
                "target_assignment_id": operation["target_assignment"]["id"],
                "target_assignment_sha256": operation["target_assignment_sha256"],
            }
            for operation in operations
        ]
        return _build_receipts(
            classification="F2_9C_48_TARGETS_ALREADY_APPLIED_EXACT",
            new_writes=0,
            verified_count=EXPECTED_TARGET_COUNT,
            execution_operations=exact_operations,
            idempotent=True,
        )

    if live_reseal_factory is None:
        raise F29CExecutionError("LIVE_RESEAL_FACTORY_REQUIRED_BEFORE_WRITE")
    live_reseal = live_reseal_factory()
    validate_live_reseal(sealed_manifest, live_reseal)

    second_state = inspect_execution_state(target_db, operations)
    if _assert_state_clear(second_state, allow_all_exact=False) != "ALL_MISSING":
        raise F29CExecutionError("PREWRITE_STATE_CHANGED_AFTER_RESEAL")

    execution = apply_validated_operations(target_db, operations)
    if execution["inserted_count"] != EXPECTED_TARGET_COUNT:
        raise F29CExecutionError("EXECUTION_INSERT_COUNT_NOT_48")
    if execution["verified_count"] != EXPECTED_TARGET_COUNT:
        raise F29CExecutionError("EXECUTION_VERIFY_COUNT_NOT_48")

    return _build_receipts(
        classification="F2_9C_48_TARGETS_APPLIED_AND_VERIFIED",
        new_writes=execution["inserted_count"],
        verified_count=execution["verified_count"],
        execution_operations=execution["operations"],
        idempotent=False,
    )


if __name__ == "__main__":
    raise SystemExit(
        "F2.9C is intentionally not executable as a standalone script. "
        "Use the exact-SHA GitHub production gate."
    )
