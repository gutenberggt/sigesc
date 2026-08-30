"""P0-F7.9D7.5 — seal the revised execution manifest after a clear D7.4.

This stage is deliberately non-executable. It consumes the exact D7.3.1 sealed
revised plan and the exact real D7.4 preflight report, then emits an immutable
execution specification. It does not materialize a writer, does not connect to
MongoDB/network, and does not authorize production writes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Mapping

BUILDER_PATH = Path(__file__).with_name("build_p0f7_9d74_revised_preflight_snapshot_js.py")
_spec = importlib.util.spec_from_file_location("p0f7_9d74_builder", BUILDER_PATH)
if not _spec or not _spec.loader:
    raise RuntimeError("P0F7_9D75_D74_BUILDER_IMPORT_FAILED")
d74_builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d74_builder)

D74_PHASE = "P0F7.9D7.4-OFFLINE-REVISED-LAST-MILE-PREFLIGHT-2026"
D74_MODE = "LOCAL_OFFLINE_REVISED_CAS_DRY_RUN"
OUTPUT_PHASE = "P0F7.9D7.5-SEALED-REVISED-EXECUTOR-MANIFEST-2026"
OUTPUT_MODE = "LOCAL_OFFLINE_EXECUTOR_SPECIFICATION_NON_EXECUTABLE"
EXPECTED_REVISED_PLAN_SHA256 = "b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb"
EXPECTED_D74_REPORT_SHA256 = "b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e"
EXPECTED_OPERATIONS = 23
EXPECTED_CURRICULAR_CHECKS = 22
EXPECTED_STRATEGY = "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED"
EXPECTED_TOPOLOGY = "STANDALONE_OR_TRANSACTION_UNAVAILABLE"


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _unsigned_hash(payload: Mapping[str, Any], field: str) -> str:
    unsigned = dict(payload)
    unsigned.pop(field, None)
    return _canonical_sha256(unsigned)


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def validate_d74_report(report: Mapping[str, Any], *, expected_sha: str = EXPECTED_D74_REPORT_SHA256) -> str:
    if report.get("phase") != D74_PHASE or report.get("status") != "PASS" or report.get("mode") != D74_MODE:
        raise ValueError("P0F7_9D75_D74_REPORT_INVALID")

    report_sha = _norm(report.get("report_sha256"))
    if not report_sha or report_sha != _unsigned_hash(report, "report_sha256"):
        raise ValueError("P0F7_9D75_D74_REPORT_SHA_INVALID")
    if report_sha != expected_sha:
        raise ValueError("P0F7_9D75_D74_REPORT_NOT_AUTHORIZED_INPUT")
    if _norm(report.get("sealed_report_sha256")) != EXPECTED_REVISED_PLAN_SHA256:
        raise ValueError("P0F7_9D75_D74_REVISED_PLAN_CHAIN_MISMATCH")

    summary = report.get("summary") or {}
    expected_summary = {
        "operations": EXPECTED_OPERATIONS,
        "cas_dry_run_clear": EXPECTED_OPERATIONS,
        "cas_dry_run_blocked": 0,
        "curricular_checks_passed": EXPECTED_CURRICULAR_CHECKS,
    }
    for field, expected in expected_summary.items():
        if int(summary.get(field) or 0) != expected:
            raise ValueError(f"P0F7_9D75_D74_SUMMARY_INVALID:{field}")
    for field in (
        "forward_simulation_clear",
        "pair_postconditions_clear",
        "rollback_simulation_clear",
        "clear_for_executor_sealing",
    ):
        if summary.get(field) is not True:
            raise ValueError(f"P0F7_9D75_D74_GATE_CLOSED:{field}")
    for field in (
        "production_write_authorized",
        "executor_authorized",
        "database_mutation",
        "production_writes",
        "remediation_executed",
    ):
        if summary.get(field) is not False:
            raise ValueError(f"P0F7_9D75_D74_UNSAFE_STATE:{field}")

    topology = report.get("topology") or {}
    if (
        topology.get("classification") != EXPECTED_TOPOLOGY
        or topology.get("multi_document_transactions_available") is not False
        or topology.get("required_future_execution_strategy") != EXPECTED_STRATEGY
    ):
        raise ValueError("P0F7_9D75_D74_TOPOLOGY_OR_STRATEGY_DRIFT")

    execution = report.get("execution_contract") or {}
    if (
        execution.get("executable") is not False
        or execution.get("writer_implementation_present") is not False
        or execution.get("requires_separate_explicit_production_write_authorization") is not True
        or execution.get("old_23_write_authorization_reusable") is not False
        or execution.get("failure_policy") != "FAIL_CLOSED_NO_PARTIAL_GUESSING"
        or execution.get("required_future_execution_strategy") != EXPECTED_STRATEGY
        or execution.get("required_operation_order") != "SEALED_OPERATION_INDEX_ASC"
        or execution.get("required_rollback_order") != "REVERSE_OPERATION_ORDER"
    ):
        raise ValueError("P0F7_9D75_D74_EXECUTION_CONTRACT_INVALID")

    safety = report.get("safety") or {}
    if (
        safety.get("analyzer_production_access") is not False
        or safety.get("snapshot_origin_read_only") is not True
        or safety.get("database_mutation") is not False
        or safety.get("production_writes") is not False
        or safety.get("remediation_executed") is not False
        or int(safety.get("student_records_read") or 0) != 0
        or int(safety.get("teacher_names_read") or 0) != 0
        or safety.get("staff_id_exposed_in_report") is not False
        or safety.get("hard_delete_allowed") is not False
    ):
        raise ValueError("P0F7_9D75_D74_SAFETY_CONTRACT_INVALID")

    results = list(report.get("results") or [])
    if len(results) != EXPECTED_OPERATIONS:
        raise ValueError("P0F7_9D75_D74_RESULTS_COUNT_INVALID")
    indexes = [int((row or {}).get("operation_index") or 0) for row in results]
    if indexes != list(range(1, EXPECTED_OPERATIONS + 1)):
        raise ValueError("P0F7_9D75_D74_RESULTS_SEQUENCE_INVALID")
    for row in results:
        if row.get("preflight") != "CAS_DRY_RUN_CLEAR" or list(row.get("reasons") or []):
            raise ValueError("P0F7_9D75_D74_RESULT_NOT_CLEAR")
        if list(row.get("active_collision_assignment_ids") or []):
            raise ValueError("P0F7_9D75_D74_RESULT_COLLISION")
        if row.get("staff_id_present") is not True:
            raise ValueError("P0F7_9D75_D74_STAFF_ID_PRECONDITION_MISSING")

    return report_sha


def build_manifest(sealed_report: Mapping[str, Any], d74_report: Mapping[str, Any]) -> dict[str, Any]:
    ctx = d74_builder.validate_sealed_report(sealed_report)
    if ctx["sealed_report_sha256"] != EXPECTED_REVISED_PLAN_SHA256:
        raise ValueError("P0F7_9D75_REVISED_PLAN_NOT_AUTHORIZED_INPUT")
    d74_sha = validate_d74_report(d74_report)

    operations = list(ctx["operations"])
    if len(operations) != EXPECTED_OPERATIONS:
        raise ValueError("P0F7_9D75_OPERATION_COUNT_INVALID")

    result_by_index = {
        int((row or {}).get("operation_index") or 0): row
        for row in (d74_report.get("results") or [])
    }
    sealed_operations: list[dict[str, Any]] = []
    for op in operations:
        index = int(op["operation_index"])
        result = result_by_index.get(index) or {}
        if _norm(result.get("assignment_id")) != _norm(op["scope"]["assignment_id"]):
            raise ValueError("P0F7_9D75_D74_RESULT_ASSIGNMENT_CHAIN_MISMATCH")
        sealed_operations.append(
            {
                "operation_index": index,
                "operation_type": op["operation_type"],
                "scope": dict(op["scope"]),
                "cas_expected": dict(op.get("cas_expected") or {}),
                "set_fields": dict(op.get("set_fields") or {}),
                "rollback_set_fields": dict(op.get("rollback_set_fields") or {}),
                "d74_preflight": "CAS_DRY_RUN_CLEAR",
                "d74_current_write_policy": _norm(result.get("current_write_policy")),
            }
        )

    types = [op["operation_type"] for op in sealed_operations]
    if types.count("REMAP_COURSE") != 21:
        raise ValueError("P0F7_9D75_REMAP_COUNT_INVALID")
    if types[-2:] != ["RETIRE_DUPLICATE_ASSIGNMENT", "CONSOLIDATE_SURVIVOR"]:
        raise ValueError("P0F7_9D75_PAIR_ORDER_INVALID")

    manifest: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "mode": OUTPUT_MODE,
        "source_revised_plan_sha256": ctx["sealed_report_sha256"],
        "source_d74_report_sha256": d74_sha,
        "mantenedora_id": ctx["mantenedora_id"],
        "academic_year": ctx["academic_year"],
        "strategy": EXPECTED_STRATEGY,
        "summary": {
            "operations": EXPECTED_OPERATIONS,
            "remap_course": 21,
            "retire_duplicate_assignment": 1,
            "consolidate_survivor": 1,
            "cas_preflight_clear": EXPECTED_OPERATIONS,
            "forward_simulation_clear": True,
            "pair_postconditions_clear": True,
            "rollback_simulation_clear": True,
            "manifest_ready_for_explicit_authorization": True,
            "production_write_authorized": False,
            "executor_authorized": False,
            "executor_materialized": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "operations": sealed_operations,
        "execution_contract": {
            "executable": False,
            "writer_implementation_present": False,
            "executor_materialized": False,
            "requires_separate_explicit_production_write_authorization": True,
            "authorization_must_pin_manifest_sha256": True,
            "authorization_must_pin_revised_plan_sha256": True,
            "authorization_must_pin_d74_report_sha256": True,
            "old_23_write_authorization_reusable": False,
            "failure_policy": "FAIL_CLOSED_NO_PARTIAL_GUESSING",
            "required_execution_strategy": EXPECTED_STRATEGY,
            "required_operation_order": "SEALED_OPERATION_INDEX_ASC",
            "required_pair_order": "RETIRE_DUPLICATE_BEFORE_CONSOLIDATE_SURVIVOR",
            "required_rollback_order": "REVERSE_OPERATION_ORDER",
            "hard_delete_allowed": False,
        },
        "safety": {
            "production_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "student_records_read": 0,
            "teacher_names_read": 0,
            "staff_id_exposed": False,
            "hard_delete_allowed": False,
        },
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seal P0-F7.9D7.5 non-executable revised executor manifest")
    parser.add_argument("--sealed-report", required=True, type=Path)
    parser.add_argument("--d74-report", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_manifest(_load(args.sealed_report), _load(args.d74_report))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": manifest["summary"], "strategy": manifest["strategy"]}, ensure_ascii=False, indent=2))
    print("P0F7_9D75_REVISED_EXECUTOR_MANIFEST_SEAL=PASS")
    print(f"MANIFEST_SHA256={manifest['manifest_sha256']}")
    print(f"MANIFEST={args.json}")
    print("EXECUTABLE=NO")
    print("WRITER_IMPLEMENTATION_PRESENT=NO")
    print("PRODUCTION_WRITE_AUTHORIZED=NO")
    print("EXECUTOR_AUTHORIZED=NO")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")


if __name__ == "__main__":
    main()
