"""Validate a P0-F7.9D7.6 production execution receipt offline.

The validator never connects to production. It verifies the exact D7.5
manifest, D7.6 executor metadata and executor file hash, then classifies the
captured mongosh receipt as APPLIED, SAFE_ROLLBACK or unsafe/incomplete.

D7.6.2 deliberately loads the D7.6.1 compatibility builder so validation uses
the same exact sealed retire-status contract used to materialize the authorized
executor. This changes no writer bytes and performs no production access.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Mapping

COMPAT_BUILDER_PATH = Path(__file__).with_name(
    "build_p0f7_9d761_authorized_revised_executor_js.py"
)
_spec = importlib.util.spec_from_file_location("p0f7_9d761_builder_for_receipt", COMPAT_BUILDER_PATH)
if not _spec or not _spec.loader:
    raise RuntimeError("P0F7_9D762_COMPAT_BUILDER_IMPORT_FAILED")
compat_builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compat_builder)
# The D7.6.1 module patches only the retire-status operation validator on the
# reviewed D7.6 builder and exposes that patched builder as ``d76``.
builder = compat_builder.d76

OUTPUT_PHASE = "P0F7.9D7.6-OFFLINE-EXECUTION-RECEIPT-VALIDATION-2026"


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


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _validate_metadata(metadata: Mapping[str, Any], executor_path: Path) -> str:
    if metadata.get("phase") != builder.OUTPUT_PHASE or metadata.get("status") != "PASS":
        raise ValueError("P0F7_9D76_METADATA_INVALID")
    metadata_sha = _norm(metadata.get("metadata_sha256"))
    unsigned = dict(metadata)
    unsigned.pop("metadata_sha256", None)
    if not metadata_sha or metadata_sha != _canonical_sha256(unsigned):
        raise ValueError("P0F7_9D76_METADATA_SHA_INVALID")
    if _norm(metadata.get("manifest_sha256")) != builder.EXPECTED_MANIFEST_SHA256:
        raise ValueError("P0F7_9D76_METADATA_MANIFEST_CHAIN_INVALID")
    if _norm(metadata.get("source_revised_plan_sha256")) != builder.EXPECTED_REVISED_PLAN_SHA256:
        raise ValueError("P0F7_9D76_METADATA_PLAN_CHAIN_INVALID")
    if _norm(metadata.get("source_d74_report_sha256")) != builder.EXPECTED_D74_REPORT_SHA256:
        raise ValueError("P0F7_9D76_METADATA_D74_CHAIN_INVALID")
    if metadata.get("authorization_marker") != builder.AUTHORIZATION_MARKER:
        raise ValueError("P0F7_9D76_METADATA_AUTHORIZATION_INVALID")
    if metadata.get("strategy") != builder.EXPECTED_STRATEGY:
        raise ValueError("P0F7_9D76_METADATA_STRATEGY_INVALID")
    if int(metadata.get("expected_operations") or 0) != builder.EXPECTED_OPERATIONS:
        raise ValueError("P0F7_9D76_METADATA_OPERATION_COUNT_INVALID")
    if (
        metadata.get("executor_materialized") is not True
        or metadata.get("production_write_authorized") is not True
        or metadata.get("executor_authorized") is not True
        or metadata.get("execution_performed") is not False
        or metadata.get("database_mutation") is not False
        or metadata.get("production_writes") is not False
        or metadata.get("hard_delete_allowed") is not False
    ):
        raise ValueError("P0F7_9D76_METADATA_STATE_INVALID")

    executor_sha = hashlib.sha256(executor_path.read_bytes()).hexdigest()
    if executor_sha != _norm(metadata.get("executor_sha256")):
        raise ValueError("P0F7_9D76_EXECUTOR_FILE_SHA_INVALID")
    return executor_sha


def build_report(
    manifest: Mapping[str, Any],
    metadata: Mapping[str, Any],
    receipt: Mapping[str, Any],
    executor_path: Path,
) -> dict[str, Any]:
    ctx = builder.validate_manifest(manifest)
    executor_sha = _validate_metadata(metadata, executor_path)

    if receipt.get("phase") != builder.OUTPUT_PHASE:
        raise ValueError("P0F7_9D76_RECEIPT_PHASE_INVALID")
    if _norm(receipt.get("manifest_sha256")) != ctx["manifest_sha256"]:
        raise ValueError("P0F7_9D76_RECEIPT_MANIFEST_CHAIN_INVALID")
    if _norm(receipt.get("source_revised_plan_sha256")) != builder.EXPECTED_REVISED_PLAN_SHA256:
        raise ValueError("P0F7_9D76_RECEIPT_PLAN_CHAIN_INVALID")
    if _norm(receipt.get("source_d74_report_sha256")) != builder.EXPECTED_D74_REPORT_SHA256:
        raise ValueError("P0F7_9D76_RECEIPT_D74_CHAIN_INVALID")
    if receipt.get("strategy") != builder.EXPECTED_STRATEGY:
        raise ValueError("P0F7_9D76_RECEIPT_STRATEGY_INVALID")
    if int(receipt.get("expected_operations") or 0) != builder.EXPECTED_OPERATIONS:
        raise ValueError("P0F7_9D76_RECEIPT_OPERATION_COUNT_INVALID")
    if receipt.get("hard_delete") is not False:
        raise ValueError("P0F7_9D76_RECEIPT_HARD_DELETE_INVALID")

    status = _norm(receipt.get("status"))
    forward = int(receipt.get("forward_writes") or 0)
    rollback = int(receipt.get("rollback_writes") or 0)
    mutations = int(receipt.get("mutation_operations") or 0)
    if mutations != forward + rollback:
        raise ValueError("P0F7_9D76_RECEIPT_MUTATION_COUNT_INVALID")

    if status == "APPLIED":
        if (
            forward != builder.EXPECTED_OPERATIONS
            or rollback != 0
            or mutations != builder.EXPECTED_OPERATIONS
            or receipt.get("remediation_executed") is not True
            or receipt.get("production_writes") is not True
            or receipt.get("rollback_complete") is not True
        ):
            raise ValueError("P0F7_9D76_APPLIED_RECEIPT_INVALID")
        operation_results = list(receipt.get("operation_results") or [])
        if len(operation_results) != builder.EXPECTED_OPERATIONS:
            raise ValueError("P0F7_9D76_APPLIED_RESULTS_COUNT_INVALID")
        for op, result in zip(ctx["operations"], operation_results, strict=True):
            if (
                int(result.get("operation_index") or 0) != op["operation_index"]
                or result.get("operation_type") != op["operation_type"]
                or _norm(result.get("assignment_id")) != op["scope"]["assignment_id"]
                or result.get("state") != "APPLIED"
            ):
                raise ValueError("P0F7_9D76_APPLIED_RESULT_CHAIN_INVALID")
        classification = "REMEDIATION_APPLIED"
        safe = True
    elif status == "SAFE_ROLLBACK":
        if (
            forward < 0
            or forward > builder.EXPECTED_OPERATIONS
            or rollback != forward
            or receipt.get("remediation_executed") is not False
            or receipt.get("rollback_complete") is not True
            or list(receipt.get("rollback_failures") or [])
        ):
            raise ValueError("P0F7_9D76_SAFE_ROLLBACK_RECEIPT_INVALID")
        classification = "SAFE_ROLLBACK_NO_REMEDIATION_APPLIED"
        safe = True
    elif status == "ROLLBACK_INCOMPLETE":
        classification = "UNSAFE_ROLLBACK_INCOMPLETE_MANUAL_INTERVENTION_REQUIRED"
        safe = False
    else:
        raise ValueError("P0F7_9D76_RECEIPT_STATUS_INVALID")

    report: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS" if safe else "BLOCKED",
        "classification": classification,
        "manifest_sha256": ctx["manifest_sha256"],
        "executor_sha256": executor_sha,
        "metadata_sha256": metadata["metadata_sha256"],
        "execution_receipt_status": status,
        "forward_writes": forward,
        "rollback_writes": rollback,
        "mutation_operations": mutations,
        "remediation_executed": receipt.get("remediation_executed") is True,
        "rollback_complete": receipt.get("rollback_complete") is True,
        "database_access_by_validator": False,
        "database_mutation_by_validator": False,
        "production_writes_by_validator": False,
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate P0-F7.9D7.6 execution receipt offline")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--executor", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        _load(args.manifest),
        _load(args.metadata),
        _load(args.receipt),
        args.executor,
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("P0F7_9D76_EXECUTION_RECEIPT_VALIDATION=" + report["status"])
    print(f"REPORT_SHA256={report['report_sha256']}")
    print(f"REPORT={args.json}")
    print("VALIDATOR_PRODUCTION_ACCESS=NO")
    print("VALIDATOR_DATABASE_MUTATION=NO")
    print("VALIDATOR_PRODUCTION_WRITES=NO")


if __name__ == "__main__":
    main()
