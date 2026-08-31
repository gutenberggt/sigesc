#!/usr/bin/env python3
"""P0 #250 F2.9B — sela os 48 targets seguros da F2.9A, sem backfill.

A F2.9B não recalcula regras próprias de reconciliação: ela executa o planner
F2.9A aprovado, captura o manifesto interno produzido pela mesma SSoT e exige
paridade exata com os seals da execução read-only homologada.

Somente depois disso a fase cria um bundle privado e imutável com os 48 inserts
planejados, precondições de ausência e contrato de rollback. Nenhuma escrita em
MongoDB é realizada nesta fase.
"""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from typing import Any, Mapping

from pymongo import MongoClient

PHASE_ID = "P0-250-F2.9B-SEALED-48-DVD-TARGETS-2026"
SCHEMA = "P0_250_F2_9B_SEALED_BACKFILL_TARGETS_V1"
ACADEMIC_YEAR = 2026
REFERENCE_DATE = "2026-08-31"

SOURCE_F2_9A_MAIN_SHA = "794cf799a8f4091d35401d45d8203109b4e5dd0d"
SOURCE_F2_9A_PLANNER_BLOB_SHA = "42178d99c479ab43d4345c4a5346cac6735eefd3"
SOURCE_F2_9A_RUN_ID = 33350397799
SOURCE_F2_9A_PLAN_SHA256 = (
    "fbfe46dd455e45ad65c510d75022d52918c8993c21cc76593f1915d5324fb177"
)
SOURCE_F2_9A_DECISION_MANIFEST_SHA256 = (
    "8dec6b3544ac01ecda5c4f84fba382816c51248e63a04704c8a79ee674877c27"
)
SOURCE_F2_9A_INPUT_STATE_SHA256 = (
    "c080d9deb83ce3d08fa2aa2ffc5b88f11f85f19570fcf4c77771db79d6c67cca"
)
SOURCE_F2_9A_PLAN_NAMESPACE_SHA256 = (
    "af2532ee57419a8c8b51e4750997de5a9943404e7097492313200d85b41e6143"
)
SOURCE_F2_9A_CLASSIFICATION = (
    "GLOBAL_DVD_RECONCILIATION_PLAN_PARTIAL_REVIEW_REQUIRED"
)

APPROVED_TARGET_COUNT = 48
APPROVED_REVIEW_COUNT = 883
APPROVED_ACTIVE_LEGACY_PAIRS = 2218
APPROVED_DECISION_COUNTS = {
    "NOOP_ALREADY_CANONICAL": 275,
    "PLAN_CREATE_CANONICAL_ASSIGNMENT": 48,
    "NOOP_OUT_OF_DVD_SCOPE": 1012,
    "REQUIRES_REVIEW": 883,
}

TARGET_REQUIRED_KEYS = frozenset(
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
TARGET_OPTIONAL_KEYS = frozenset({"shift"})
DIARY_SETTING_KEYS = frozenset(
    {"enabled", "schema_version", "profile", "student_scope"}
)


class F29BSealError(RuntimeError):
    """Violação fail-closed do contrato selado F2.9B."""


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def load_planner():
    override = globals().get("_PLANNER_OVERRIDE")
    if override is not None:
        return override
    from scripts import p0_250_f2_9a_global_dvd_reconciliation_plan as planner

    return planner


def assert_planner_contract(planner: Any) -> None:
    if int(getattr(planner, "ACADEMIC_YEAR", 0)) != ACADEMIC_YEAR:
        raise F29BSealError("F2_9A_ACADEMIC_YEAR_DRIFT")
    if str(getattr(planner, "REFERENCE_DATE", "")) != REFERENCE_DATE:
        raise F29BSealError("F2_9A_REFERENCE_DATE_DRIFT")

    namespace_hash = hashlib.sha256(
        str(getattr(planner, "PLAN_NAMESPACE", "")).encode("ascii")
    ).hexdigest()
    if namespace_hash != SOURCE_F2_9A_PLAN_NAMESPACE_SHA256:
        raise F29BSealError("F2_9A_PLAN_NAMESPACE_DRIFT")


def capture_planner_material(planner: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Captura o manifesto interno sem duplicar a lógica de decisão F2.9A."""
    original = planner._decision_manifest_rows
    captured: dict[str, Any] = {}

    def capture(rows):
        manifest = original(rows)
        captured["decision_manifest"] = deepcopy(manifest)
        return manifest

    planner._decision_manifest_rows = capture
    try:
        snapshot = planner.run_live_plan()
    finally:
        planner._decision_manifest_rows = original

    manifest = captured.get("decision_manifest")
    if not isinstance(manifest, list):
        raise F29BSealError("F2_9A_DECISION_MANIFEST_NOT_CAPTURED")
    return snapshot, manifest


def assert_source_snapshot_approved(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("status") != "PASS":
        raise F29BSealError("F2_9A_STATUS_NOT_PASS")
    if snapshot.get("classification") != SOURCE_F2_9A_CLASSIFICATION:
        raise F29BSealError("F2_9A_CLASSIFICATION_DRIFT")

    for key in (
        "database_mutation",
        "production_writes",
        "academic_data_read",
        "record_content_emitted",
        "record_ids_emitted",
        "assignment_ids_emitted",
        "teacher_ids_emitted",
        "staff_ids_emitted",
        "student_data_read",
        "student_pii_emitted",
        "user_pii_emitted",
        "plan_payload_emitted",
    ):
        if snapshot.get(key) is not False:
            raise F29BSealError(f"F2_9A_BOUNDARY_DRIFT_{key}")
    if snapshot.get("mongo_reads_only") is not True or snapshot.get("http_methods") != []:
        raise F29BSealError("F2_9A_READ_BOUNDARY_DRIFT")

    analysis = snapshot.get("analysis") or {}
    expected_scalars = {
        "plan_sha256": SOURCE_F2_9A_PLAN_SHA256,
        "decision_manifest_sha256": SOURCE_F2_9A_DECISION_MANIFEST_SHA256,
        "input_state_sha256": SOURCE_F2_9A_INPUT_STATE_SHA256,
        "plan_namespace_sha256": SOURCE_F2_9A_PLAN_NAMESPACE_SHA256,
        "academic_year": ACADEMIC_YEAR,
        "reference_date": REFERENCE_DATE,
        "plan_create_count": APPROVED_TARGET_COUNT,
        "review_count": APPROVED_REVIEW_COUNT,
        "active_legacy_component_pairs": APPROVED_ACTIVE_LEGACY_PAIRS,
    }
    for key, expected in expected_scalars.items():
        if analysis.get(key) != expected:
            raise F29BSealError(f"F2_9A_APPROVED_SEAL_DRIFT_{key}")
    if analysis.get("decision_counts") != APPROVED_DECISION_COUNTS:
        raise F29BSealError("F2_9A_DECISION_COUNTS_DRIFT")
    if analysis.get("automatic_apply_authorized") is not False:
        raise F29BSealError("F2_9A_APPLY_FLAG_DRIFT")


def validate_target_assignment(target: Mapping[str, Any]) -> None:
    keys = set(target.keys())
    missing = TARGET_REQUIRED_KEYS - keys
    unknown = keys - TARGET_REQUIRED_KEYS - TARGET_OPTIONAL_KEYS
    if missing:
        raise F29BSealError("TARGET_REQUIRED_FIELDS_MISSING")
    if unknown:
        raise F29BSealError("TARGET_UNAPPROVED_FIELDS_PRESENT")

    for key in (
        "id",
        "teacher_id",
        "class_id",
        "component_id",
        "school_id",
        "mantenedora_id",
        "valid_from",
    ):
        if not _sid(target.get(key)):
            raise F29BSealError(f"TARGET_EMPTY_{key}")

    if target.get("deleted") is not False:
        raise F29BSealError("TARGET_DELETED_FLAG_INVALID")
    if target.get("valid_until") not in (None, ""):
        if str(target.get("valid_until")) < str(target.get("valid_from")):
            raise F29BSealError("TARGET_VALIDITY_INVALID")

    settings = target.get("diary_settings")
    if not isinstance(settings, Mapping) or set(settings.keys()) != DIARY_SETTING_KEYS:
        raise F29BSealError("TARGET_DIARY_SETTINGS_SHAPE_INVALID")
    if settings.get("enabled") is not True or settings.get("schema_version") != 1:
        raise F29BSealError("TARGET_DIARY_SETTINGS_NOT_ENABLED_V1")
    if settings.get("profile") not in {"regular", "integrator", "shared"}:
        raise F29BSealError("TARGET_PROFILE_INVALID")
    if settings.get("student_scope") not in {"all", "group"}:
        raise F29BSealError("TARGET_STUDENT_SCOPE_INVALID")
    if settings.get("student_scope") == "group" and settings.get("profile") != "shared":
        raise F29BSealError("TARGET_GROUP_SCOPE_PROFILE_INVALID")


def extract_approved_target_rows(
    planner: Any,
    decision_manifest: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if planner._sha256_value(decision_manifest) != SOURCE_F2_9A_DECISION_MANIFEST_SHA256:
        raise F29BSealError("CAPTURED_DECISION_MANIFEST_SHA_DRIFT")

    rows = [
        deepcopy(row)
        for row in decision_manifest
        if row.get("decision") == "PLAN_CREATE_CANONICAL_ASSIGNMENT"
    ]
    if len(rows) != APPROVED_TARGET_COUNT:
        raise F29BSealError("SEALED_TARGET_COUNT_NOT_48")

    targets = []
    target_ids: set[str] = set()
    natural_keys: set[tuple[str, str, str]] = set()
    source_keys: set[tuple[str, str, str]] = set()

    for row in rows:
        if row.get("review_reasons"):
            raise F29BSealError("TARGET_ROW_HAS_REVIEW_REASON")
        target = row.get("target_assignment")
        if not isinstance(target, Mapping):
            raise F29BSealError("TARGET_ASSIGNMENT_MISSING")
        validate_target_assignment(target)

        target_id = _sid(target.get("id"))
        natural = (
            _sid(target.get("teacher_id")),
            _sid(target.get("class_id")),
            _sid(target.get("component_id")),
        )
        source = (
            _sid(row.get("teacher_key")),
            _sid(row.get("class_key")),
            _sid(row.get("component_key")),
        )
        if not all(natural) or not all(source):
            raise F29BSealError("TARGET_NATURAL_OR_SOURCE_KEY_EMPTY")
        if target_id in target_ids:
            raise F29BSealError("TARGET_ID_DUPLICATED")
        if natural in natural_keys:
            raise F29BSealError("TARGET_NATURAL_KEY_DUPLICATED")
        if source in source_keys:
            raise F29BSealError("TARGET_SOURCE_KEY_DUPLICATED")

        target_ids.add(target_id)
        natural_keys.add(natural)
        source_keys.add(source)
        targets.append(dict(target))

    if planner._sha256_value(targets) != SOURCE_F2_9A_PLAN_SHA256:
        raise F29BSealError("CAPTURED_TARGET_PLAN_SHA_DRIFT")
    return rows


def _active_date_query() -> dict[str, Any]:
    return {
        "deleted": {"$ne": True},
        "diary_settings.enabled": True,
        "valid_from": {"$lte": REFERENCE_DATE},
        "$or": [{"valid_until": None}, {"valid_until": {"$gte": REFERENCE_DATE}}],
    }


def collect_live_preconditions(
    db: Any,
    target_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    preconditions: list[dict[str, Any]] = []

    for index, row in enumerate(target_rows, start=1):
        target = row["target_assignment"]
        source_key = {
            "staff_id": row["teacher_key"],
            "class_id": row["class_key"],
            "course_id": row["component_key"],
            "academic_year": ACADEMIC_YEAR,
            "status": {"$in": ["ativo", "active"]},
        }
        source_count = db.teacher_assignments.count_documents(source_key)
        if source_count != 1:
            raise F29BSealError(f"SOURCE_LEGACY_COUNT_DRIFT_AT_{index}")

        target_id_count = db.teacher_class_assignments.count_documents(
            {"id": target["id"]}
        )
        if target_id_count != 0:
            raise F29BSealError(f"TARGET_ID_ALREADY_PRESENT_AT_{index}")

        active_base = _active_date_query()
        same_teacher_exact = {
            **active_base,
            "teacher_id": target["teacher_id"],
            "class_id": target["class_id"],
            "component_id": target["component_id"],
        }
        same_teacher_exact_count = db.teacher_class_assignments.count_documents(
            same_teacher_exact
        )
        if same_teacher_exact_count != 0:
            raise F29BSealError(f"TARGET_NATURAL_KEY_ALREADY_ACTIVE_AT_{index}")

        same_teacher_classwide = {
            **active_base,
            "teacher_id": target["teacher_id"],
            "class_id": target["class_id"],
            "$and": [
                active_base["$or"],
                {"$or": [{"component_id": None}, {"component_id": ""}]},
            ],
        }
        same_teacher_classwide.pop("$or", None)
        classwide_count = db.teacher_class_assignments.count_documents(
            same_teacher_classwide
        )
        if classwide_count != 0:
            raise F29BSealError(f"CLASSWIDE_COVERAGE_DRIFT_AT_{index}")

        official_owner_conflict_count = 0
        if target.get("grades_official_owner") is True:
            owner_query = {
                **active_base,
                "class_id": target["class_id"],
                "component_id": target["component_id"],
                "teacher_id": {"$ne": target["teacher_id"]},
                "grades_official_owner": True,
            }
            official_owner_conflict_count = (
                db.teacher_class_assignments.count_documents(owner_query)
            )
            if official_owner_conflict_count != 0:
                raise F29BSealError(f"GRADES_OFFICIAL_OWNER_CONFLICT_AT_{index}")

        preconditions.append(
            {
                "ordinal": index,
                "source_legacy_count": source_count,
                "target_id_count": target_id_count,
                "same_teacher_active_exact_count": same_teacher_exact_count,
                "same_teacher_active_classwide_count": classwide_count,
                "other_teacher_official_grade_owner_count": official_owner_conflict_count,
            }
        )

    return preconditions


def build_sealed_bundle(
    planner: Any,
    snapshot: Mapping[str, Any],
    target_rows: list[dict[str, Any]],
    preconditions: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(target_rows) != APPROVED_TARGET_COUNT or len(preconditions) != APPROVED_TARGET_COUNT:
        raise F29BSealError("SEAL_INPUT_COUNT_MISMATCH")

    operations: list[dict[str, Any]] = []
    for index, (row, live) in enumerate(zip(target_rows, preconditions), start=1):
        if live.get("ordinal") != index:
            raise F29BSealError("PRECONDITION_ORDINAL_DRIFT")
        target = deepcopy(row["target_assignment"])
        target_sha = _sha256_value(target)
        operation = {
            "ordinal": index,
            "operation": "INSERT_TEACHER_CLASS_ASSIGNMENT",
            "source_legacy_key": {
                "staff_id": row["teacher_key"],
                "class_id": row["class_key"],
                "course_id": row["component_key"],
                "academic_year": ACADEMIC_YEAR,
                "active_statuses": ["ativo", "active"],
            },
            "target_assignment": target,
            "target_assignment_sha256": target_sha,
            "sealed_preconditions": {
                "source_legacy_count": 1,
                "target_id_count": 0,
                "same_teacher_active_exact_count": 0,
                "same_teacher_active_classwide_count": 0,
                "other_teacher_official_grade_owner_count": 0,
                "reference_date": REFERENCE_DATE,
            },
            "rollback_contract": {
                "mode": "DELETE_INSERTED_IF_EXACT_PROJECTED_MATCH",
                "target_assignment_id": target["id"],
                "target_assignment_sha256": target_sha,
            },
        }
        operations.append(operation)

    targets = [op["target_assignment"] for op in operations]
    targets_sha = _sha256_value(targets)
    if targets_sha != SOURCE_F2_9A_PLAN_SHA256:
        raise F29BSealError("SEALED_TARGETS_SHA_NOT_APPROVED")

    source_analysis = snapshot.get("analysis") or {}
    core = {
        "schema": SCHEMA,
        "phase": PHASE_ID,
        "mode": "READ_ONLY_SEAL",
        "status": "PASS",
        "database_mutation": False,
        "production_database_writes": False,
        "automatic_apply_authorized": False,
        "source": {
            "f2_9a_main_sha": SOURCE_F2_9A_MAIN_SHA,
            "f2_9a_planner_blob_sha": SOURCE_F2_9A_PLANNER_BLOB_SHA,
            "f2_9a_run_id": SOURCE_F2_9A_RUN_ID,
            "academic_year": ACADEMIC_YEAR,
            "reference_date": REFERENCE_DATE,
            "classification": SOURCE_F2_9A_CLASSIFICATION,
            "plan_sha256": source_analysis.get("plan_sha256"),
            "decision_manifest_sha256": source_analysis.get("decision_manifest_sha256"),
            "input_state_sha256": source_analysis.get("input_state_sha256"),
            "plan_namespace_sha256": source_analysis.get("plan_namespace_sha256"),
        },
        "expected_target_count": APPROVED_TARGET_COUNT,
        "operations": operations,
        "sealed_targets_sha256": targets_sha,
        "sealed_operations_sha256": _sha256_value(operations),
    }
    return {**core, "sealed_bundle_sha256": _sha256_value(core)}


def build_public_receipt(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "P0_250_F2_9B_PUBLIC_SEAL_RECEIPT_V1",
        "phase": PHASE_ID,
        "status": "PASS",
        "classification": "F2_9B_48_TARGETS_SEALED_READY_FOR_EXPLICIT_BACKFILL_AUTHORIZATION",
        "database_mutation": False,
        "production_writes": False,
        "mongo_reads_only": True,
        "http_methods": [],
        "target_ids_emitted": False,
        "teacher_ids_emitted": False,
        "staff_ids_emitted": False,
        "user_pii_emitted": False,
        "private_manifest_emitted_to_logs": False,
        "apply_authorized": False,
        "target_count": bundle["expected_target_count"],
        "source_f2_9a_main_sha": SOURCE_F2_9A_MAIN_SHA,
        "source_f2_9a_run_id": SOURCE_F2_9A_RUN_ID,
        "source_plan_sha256": SOURCE_F2_9A_PLAN_SHA256,
        "source_decision_manifest_sha256": SOURCE_F2_9A_DECISION_MANIFEST_SHA256,
        "source_input_state_sha256": SOURCE_F2_9A_INPUT_STATE_SHA256,
        "sealed_targets_sha256": bundle["sealed_targets_sha256"],
        "sealed_operations_sha256": bundle["sealed_operations_sha256"],
        "sealed_bundle_sha256": bundle["sealed_bundle_sha256"],
        "academic_year": ACADEMIC_YEAR,
        "reference_date": REFERENCE_DATE,
    }


def run_live_seal() -> dict[str, Any]:
    planner = load_planner()
    assert_planner_contract(planner)
    snapshot, decision_manifest = capture_planner_material(planner)
    assert_source_snapshot_approved(snapshot)
    target_rows = extract_approved_target_rows(planner, decision_manifest)

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise F29BSealError("MONGO_URL_MISSING")
    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]
    preconditions = collect_live_preconditions(db, target_rows)

    bundle = build_sealed_bundle(planner, snapshot, target_rows, preconditions)
    public = build_public_receipt(bundle)
    return {"public": public, "private": bundle}


if __name__ == "__main__":
    result = run_live_seal()
    # Execução manual nunca despeja o bundle privado por padrão.
    print(json.dumps(result["public"], ensure_ascii=False, indent=2, sort_keys=True))
