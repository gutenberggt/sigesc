#!/usr/bin/env python3
"""P0 #250 F2.9B — sela os 48 targets seguros da F2.9A, sem backfill.

A fase reutiliza o planner F2.9A como SSoT: captura o manifesto interno que ele
acabou de produzir, exige paridade integral com os seals da execução homologada
e só então gera um bundle privado dos 48 inserts planejados.

Nenhuma escrita em MongoDB é realizada nesta fase.
"""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from typing import Any, Mapping

from pymongo import MongoClient

PHASE_ID = "P0-250-F2.9B-SEALED-48-DVD-TARGETS-2026"
PRIVATE_SCHEMA = "P0_250_F2_9B_SEALED_BACKFILL_TARGETS_V1"
PUBLIC_SCHEMA = "P0_250_F2_9B_PUBLIC_SEAL_RECEIPT_V1"
ACADEMIC_YEAR = 2026
REFERENCE_DATE = "2026-08-31"

SOURCE_F2_9A_MAIN_SHA = "794cf799a8f4091d35401d45d8203109b4e5dd0d"
SOURCE_F2_9A_PLANNER_BLOB_SHA = "42178d99c479ab43d4345c4a5346cac6735eefd3"
SOURCE_F2_9A_RUN_ID = 33350397799
SOURCE_PLAN_SHA256 = "fbfe46dd455e45ad65c510d75022d52918c8993c21cc76593f1915d5324fb177"
SOURCE_DECISION_SHA256 = "8dec6b3544ac01ecda5c4f84fba382816c51248e63a04704c8a79ee674877c27"
SOURCE_INPUT_SHA256 = "c080d9deb83ce3d08fa2aa2ffc5b88f11f85f19570fcf4c77771db79d6c67cca"
SOURCE_NAMESPACE_SHA256 = "af2532ee57419a8c8b51e4750997de5a9943404e7097492313200d85b41e6143"
SOURCE_CLASSIFICATION = "GLOBAL_DVD_RECONCILIATION_PLAN_PARTIAL_REVIEW_REQUIRED"

APPROVED_TARGET_COUNT = 48
APPROVED_REVIEW_COUNT = 883
APPROVED_ACTIVE_PAIRS = 2218
APPROVED_DECISIONS = {
    "NOOP_ALREADY_CANONICAL": 275,
    "PLAN_CREATE_CANONICAL_ASSIGNMENT": 48,
    "NOOP_OUT_OF_DVD_SCOPE": 1012,
    "REQUIRES_REVIEW": 883,
}

TARGET_REQUIRED = frozenset(
    {
        "id", "teacher_id", "class_id", "component_id", "school_id",
        "mantenedora_id", "deleted", "valid_from", "valid_until",
        "diary_settings", "is_substitute", "grades_official_owner",
    }
)
TARGET_OPTIONAL = frozenset({"shift"})
DIARY_KEYS = frozenset({"enabled", "schema_version", "profile", "student_scope"})


class F29BSealError(RuntimeError):
    """Violação fail-closed do contrato F2.9B."""


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
    if namespace_hash != SOURCE_NAMESPACE_SHA256:
        raise F29BSealError("F2_9A_PLAN_NAMESPACE_DRIFT")


def capture_planner_material(planner: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Captura o manifesto interno sem copiar a lógica de classificação F2.9A."""
    original = planner._decision_manifest_rows
    captured: dict[str, Any] = {}

    def capture(rows):
        manifest = original(rows)
        captured["manifest"] = deepcopy(manifest)
        return manifest

    planner._decision_manifest_rows = capture
    try:
        snapshot = planner.run_live_plan()
    finally:
        planner._decision_manifest_rows = original

    manifest = captured.get("manifest")
    if not isinstance(manifest, list):
        raise F29BSealError("F2_9A_DECISION_MANIFEST_NOT_CAPTURED")
    return snapshot, manifest


def assert_source_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("status") != "PASS":
        raise F29BSealError("F2_9A_STATUS_NOT_PASS")
    if snapshot.get("classification") != SOURCE_CLASSIFICATION:
        raise F29BSealError("F2_9A_CLASSIFICATION_DRIFT")
    if snapshot.get("mongo_reads_only") is not True or snapshot.get("http_methods") != []:
        raise F29BSealError("F2_9A_READ_BOUNDARY_DRIFT")
    for key in (
        "database_mutation", "production_writes", "academic_data_read",
        "record_content_emitted", "record_ids_emitted", "assignment_ids_emitted",
        "teacher_ids_emitted", "staff_ids_emitted", "student_data_read",
        "student_pii_emitted", "user_pii_emitted", "plan_payload_emitted",
    ):
        if snapshot.get(key) is not False:
            raise F29BSealError(f"F2_9A_BOUNDARY_DRIFT_{key}")

    analysis = snapshot.get("analysis") or {}
    expected = {
        "plan_sha256": SOURCE_PLAN_SHA256,
        "decision_manifest_sha256": SOURCE_DECISION_SHA256,
        "input_state_sha256": SOURCE_INPUT_SHA256,
        "plan_namespace_sha256": SOURCE_NAMESPACE_SHA256,
        "academic_year": ACADEMIC_YEAR,
        "reference_date": REFERENCE_DATE,
        "plan_create_count": APPROVED_TARGET_COUNT,
        "review_count": APPROVED_REVIEW_COUNT,
        "active_legacy_component_pairs": APPROVED_ACTIVE_PAIRS,
    }
    for key, value in expected.items():
        if analysis.get(key) != value:
            raise F29BSealError(f"F2_9A_SEAL_DRIFT_{key}")
    if analysis.get("decision_counts") != APPROVED_DECISIONS:
        raise F29BSealError("F2_9A_DECISION_COUNTS_DRIFT")
    if analysis.get("automatic_apply_authorized") is not False:
        raise F29BSealError("F2_9A_APPLY_FLAG_DRIFT")


def validate_target(target: Mapping[str, Any]) -> None:
    keys = set(target.keys())
    if TARGET_REQUIRED - keys:
        raise F29BSealError("TARGET_REQUIRED_FIELDS_MISSING")
    if keys - TARGET_REQUIRED - TARGET_OPTIONAL:
        raise F29BSealError("TARGET_UNAPPROVED_FIELDS_PRESENT")
    for key in (
        "id", "teacher_id", "class_id", "component_id", "school_id",
        "mantenedora_id", "valid_from",
    ):
        if not sid(target.get(key)):
            raise F29BSealError(f"TARGET_EMPTY_{key}")
    if target.get("deleted") is not False:
        raise F29BSealError("TARGET_DELETED_FLAG_INVALID")

    settings = target.get("diary_settings")
    if not isinstance(settings, Mapping) or set(settings.keys()) != DIARY_KEYS:
        raise F29BSealError("TARGET_DIARY_SETTINGS_SHAPE_INVALID")
    if settings.get("enabled") is not True or settings.get("schema_version") != 1:
        raise F29BSealError("TARGET_DIARY_SETTINGS_NOT_ENABLED_V1")
    if settings.get("profile") not in {"regular", "integrator", "shared"}:
        raise F29BSealError("TARGET_PROFILE_INVALID")
    if settings.get("student_scope") not in {"all", "group"}:
        raise F29BSealError("TARGET_STUDENT_SCOPE_INVALID")
    if settings.get("student_scope") == "group" and settings.get("profile") != "shared":
        raise F29BSealError("TARGET_GROUP_SCOPE_PROFILE_INVALID")


def extract_targets(planner: Any, manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if planner._sha256_value(manifest) != SOURCE_DECISION_SHA256:
        raise F29BSealError("CAPTURED_DECISION_MANIFEST_SHA_DRIFT")

    rows = [
        deepcopy(row)
        for row in manifest
        if row.get("decision") == "PLAN_CREATE_CANONICAL_ASSIGNMENT"
    ]
    if len(rows) != APPROVED_TARGET_COUNT:
        raise F29BSealError("TARGET_COUNT_NOT_48")

    ids: set[str] = set()
    natural: set[tuple[str, str, str]] = set()
    source: set[tuple[str, str, str]] = set()
    payloads: list[dict[str, Any]] = []

    for row in rows:
        if row.get("review_reasons"):
            raise F29BSealError("TARGET_ROW_HAS_REVIEW_REASON")
        target = row.get("target_assignment")
        if not isinstance(target, Mapping):
            raise F29BSealError("TARGET_ASSIGNMENT_MISSING")
        validate_target(target)

        target_id = sid(target.get("id"))
        natural_key = (
            sid(target.get("teacher_id")), sid(target.get("class_id")),
            sid(target.get("component_id")),
        )
        source_key = (
            sid(row.get("teacher_key")), sid(row.get("class_key")),
            sid(row.get("component_key")),
        )
        if not all(natural_key) or not all(source_key):
            raise F29BSealError("TARGET_KEY_EMPTY")
        if target_id in ids or natural_key in natural or source_key in source:
            raise F29BSealError("TARGET_DUPLICATE_KEY")
        ids.add(target_id)
        natural.add(natural_key)
        source.add(source_key)
        payloads.append(dict(target))

    if planner._sha256_value(payloads) != SOURCE_PLAN_SHA256:
        raise F29BSealError("CAPTURED_PLAN_SHA_DRIFT")
    return rows


def active_on_reference(extra: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **dict(extra),
        "deleted": {"$ne": True},
        "diary_settings.enabled": True,
        "valid_from": {"$lte": REFERENCE_DATE},
        "$or": [{"valid_until": None}, {"valid_until": {"$gte": REFERENCE_DATE}}],
    }


def collect_preconditions(db: Any, rows: list[dict[str, Any]]) -> list[dict[str, int]]:
    checks: list[dict[str, int]] = []
    for index, row in enumerate(rows, start=1):
        target = row["target_assignment"]
        source_count = db.teacher_assignments.count_documents(
            {
                "staff_id": row["teacher_key"],
                "class_id": row["class_key"],
                "course_id": row["component_key"],
                "academic_year": ACADEMIC_YEAR,
                "status": {"$in": ["ativo", "active"]},
            }
        )
        if source_count != 1:
            raise F29BSealError(f"SOURCE_COUNT_DRIFT_AT_{index}")

        target_id_count = db.teacher_class_assignments.count_documents(
            {"id": target["id"]}
        )
        if target_id_count != 0:
            raise F29BSealError(f"TARGET_ID_PRESENT_AT_{index}")

        owner_conflicts = 0
        if target.get("grades_official_owner") is True:
            owner_conflicts = db.teacher_class_assignments.count_documents(
                active_on_reference(
                    {
                        "class_id": target["class_id"],
                        "component_id": target["component_id"],
                        "teacher_id": {"$ne": target["teacher_id"]},
                        "grades_official_owner": True,
                    }
                )
            )
            if owner_conflicts != 0:
                raise F29BSealError(f"OFFICIAL_GRADE_OWNER_CONFLICT_AT_{index}")

        checks.append(
            {
                "ordinal": index,
                "source_legacy_count": source_count,
                "target_id_count": target_id_count,
                "other_teacher_official_grade_owner_count": owner_conflicts,
            }
        )
    return checks


def build_private_bundle(
    snapshot: Mapping[str, Any],
    rows: list[dict[str, Any]],
    checks: list[dict[str, int]],
) -> dict[str, Any]:
    if len(rows) != APPROVED_TARGET_COUNT or len(checks) != APPROVED_TARGET_COUNT:
        raise F29BSealError("SEAL_INPUT_COUNT_MISMATCH")

    operations: list[dict[str, Any]] = []
    for index, (row, check) in enumerate(zip(rows, checks), start=1):
        if check.get("ordinal") != index:
            raise F29BSealError("PRECONDITION_ORDINAL_DRIFT")
        target = deepcopy(row["target_assignment"])
        target_sha = sha256_value(target)
        operations.append(
            {
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
                    "other_teacher_official_grade_owner_count": 0,
                    "reference_date": REFERENCE_DATE,
                    "must_reappear_identically_in_f2_9a_plan_before_apply": True,
                },
                "rollback_contract": {
                    "mode": "DELETE_INSERTED_IF_EXACT_PROJECTED_MATCH",
                    "target_assignment_id": target["id"],
                    "target_assignment_sha256": target_sha,
                },
            }
        )

    targets = [op["target_assignment"] for op in operations]
    targets_sha = sha256_value(targets)
    if targets_sha != SOURCE_PLAN_SHA256:
        raise F29BSealError("SEALED_TARGETS_SHA_DRIFT")

    analysis = snapshot.get("analysis") or {}
    core = {
        "schema": PRIVATE_SCHEMA,
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
            "classification": SOURCE_CLASSIFICATION,
            "plan_sha256": analysis.get("plan_sha256"),
            "decision_manifest_sha256": analysis.get("decision_manifest_sha256"),
            "input_state_sha256": analysis.get("input_state_sha256"),
            "plan_namespace_sha256": analysis.get("plan_namespace_sha256"),
        },
        "expected_target_count": APPROVED_TARGET_COUNT,
        "operations": operations,
        "sealed_targets_sha256": targets_sha,
        "sealed_operations_sha256": sha256_value(operations),
    }
    return {**core, "sealed_bundle_sha256": sha256_value(core)}


def build_public_receipt(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": PUBLIC_SCHEMA,
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
        "source_plan_sha256": SOURCE_PLAN_SHA256,
        "source_decision_manifest_sha256": SOURCE_DECISION_SHA256,
        "source_input_state_sha256": SOURCE_INPUT_SHA256,
        "sealed_targets_sha256": bundle["sealed_targets_sha256"],
        "sealed_operations_sha256": bundle["sealed_operations_sha256"],
        "sealed_bundle_sha256": bundle["sealed_bundle_sha256"],
        "academic_year": ACADEMIC_YEAR,
        "reference_date": REFERENCE_DATE,
    }


def run_live_seal() -> dict[str, Any]:
    planner = load_planner()
    assert_planner_contract(planner)
    snapshot, manifest = capture_planner_material(planner)
    assert_source_snapshot(snapshot)
    rows = extract_targets(planner, manifest)

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise F29BSealError("MONGO_URL_MISSING")
    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]
    checks = collect_preconditions(db, rows)

    private = build_private_bundle(snapshot, rows, checks)
    return {"public": build_public_receipt(private), "private": private}


if __name__ == "__main__":
    result = run_live_seal()
    # Execução manual nunca despeja o manifesto privado por padrão.
    print(json.dumps(result["public"], ensure_ascii=False, indent=2, sort_keys=True))
