"""Validate a P0-F7.9D7 production execution receipt offline.

The validator performs no network or database access. It seals either a fully
successful 23-entry remediation or a fail-closed rollback outcome, while
flagging incomplete rollback as critical.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

RECEIPT_PHASE = "P0F7.9D7-AUTHORIZED-PRODUCTION-EXECUTOR-2026"
AUTHORIZATION_MARKER = "P0-F7.9D7-EXPLICIT-23-WRITES-AUTHORIZED-2026-08-29"
EXPECTED_ENTRIES = 23


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def validate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if receipt.get("phase") != RECEIPT_PHASE:
        raise ValueError("P0F7_9D7_RECEIPT_PHASE_INVALID")
    if str(receipt.get("authorization_marker") or "") != AUTHORIZATION_MARKER:
        raise ValueError("P0F7_9D7_RECEIPT_AUTHORIZATION_INVALID")
    if int(receipt.get("expected_entries") or 0) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D7_RECEIPT_ENTRY_COUNT_INVALID")
    if receipt.get("production_writes_authorized") is not True:
        raise ValueError("P0F7_9D7_RECEIPT_AUTHORIZATION_STATE_INVALID")

    hashes = receipt.get("hashes") or {}
    for field in ("plan_sha256", "d5_report_sha256", "d6_package_sha256", "d6_report_sha256"):
        value = str(hashes.get(field) or "").strip()
        if len(value) != 64:
            raise ValueError(f"P0F7_9D7_RECEIPT_HASH_INVALID:{field}")

    status = str(receipt.get("status") or "")
    forward = int(receipt.get("forward_writes") or 0)
    rollback = int(receipt.get("rollback_writes") or 0)
    mutations = int(receipt.get("mutation_operations") or 0)
    post = int(receipt.get("postconditions_verified") or 0)
    final = int(receipt.get("final_verifications") or 0)
    rollback_errors = list(receipt.get("rollback_errors") or [])

    if mutations != forward + rollback:
        raise ValueError("P0F7_9D7_MUTATION_COUNT_INCONSISTENT")
    if forward < 0 or forward > EXPECTED_ENTRIES or rollback < 0 or rollback > EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D7_MUTATION_COUNT_OUT_OF_RANGE")

    if status == "PASS":
        if (
            forward != EXPECTED_ENTRIES
            or rollback != 0
            or mutations != EXPECTED_ENTRIES
            or post != EXPECTED_ENTRIES
            or final != EXPECTED_ENTRIES
            or receipt.get("rollback_attempted") is not False
            or receipt.get("remediation_executed") is not True
            or rollback_errors
        ):
            raise ValueError("P0F7_9D7_SUCCESS_RECEIPT_INVALID")
        entries = list(receipt.get("entries") or [])
        if len(entries) != EXPECTED_ENTRIES:
            raise ValueError("P0F7_9D7_SUCCESS_ENTRY_RECEIPTS_INVALID")
        if any(str(row.get("status") or "") != "APPLIED_AND_VERIFIED" for row in entries):
            raise ValueError("P0F7_9D7_SUCCESS_ENTRY_STATUS_INVALID")
        classification = "REMEDIATION_APPLIED_AND_VERIFIED"
        seal_status = "PASS"
    elif status == "FAILED_BEFORE_FIRST_WRITE":
        if forward != 0 or rollback != 0 or mutations != 0 or receipt.get("remediation_executed") is not False:
            raise ValueError("P0F7_9D7_PREWRITE_FAILURE_RECEIPT_INVALID")
        classification = "NO_MUTATION_FAILURE"
        seal_status = "SAFE_ABORT"
    elif status == "FAILED_ROLLED_BACK":
        if (
            forward <= 0
            or rollback != forward
            or receipt.get("rollback_attempted") is not True
            or receipt.get("rollback_complete") is not True
            or receipt.get("remediation_executed") is not False
            or rollback_errors
        ):
            raise ValueError("P0F7_9D7_ROLLED_BACK_RECEIPT_INVALID")
        classification = "FORWARD_FAILED_FULL_COMPENSATION_VERIFIED"
        seal_status = "SAFE_ROLLBACK"
    elif status == "CRITICAL_ROLLBACK_INCOMPLETE":
        classification = "MANUAL_RECOVERY_REQUIRED"
        seal_status = "CRITICAL"
    else:
        raise ValueError(f"P0F7_9D7_RECEIPT_STATUS_UNKNOWN:{status}")

    report: dict[str, Any] = {
        "phase": "P0F7.9D7-OFFLINE-EXECUTION-SEAL-2026",
        "status": seal_status,
        "classification": classification,
        "execution_status": status,
        "forward_writes": forward,
        "rollback_writes": rollback,
        "mutation_operations": mutations,
        "postconditions_verified": post,
        "final_verifications": final,
        "remediation_executed": bool(receipt.get("remediation_executed")),
        "source_receipt_sha256": _canonical_sha256(receipt),
        "hashes": dict(hashes),
        "requires_manual_recovery": seal_status == "CRITICAL",
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate P0-F7.9D7 production execution receipt offline")
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = validate_receipt(_load(args.receipt))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"P0F7_9D7_EXECUTION_SEAL={report['status']}")
    print(f"REPORT={args.json}")


if __name__ == "__main__":
    main()
