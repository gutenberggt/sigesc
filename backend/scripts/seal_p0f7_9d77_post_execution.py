"""P0-F7.9D7.7 — seal verified post-execution state.

Consumes the aggregate read-only production verification snapshot and emits an
immutable final remediation seal. No production/network access is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SNAPSHOT_PHASE = "P0F7.9D7.7-POST-EXECUTION-VERIFICATION-2026"
SEAL_PHASE = "P0F7.9D7.7-FINAL-REMEDIATION-SEAL-2026"
EXPECTED_MANIFEST_SHA256 = "89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc"
EXPECTED_REVISED_PLAN_SHA256 = "b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb"
EXPECTED_D74_REPORT_SHA256 = "b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e"
EXPECTED_EXECUTOR_SHA256 = "aa61676f8e3841436b34d8f345d235304380eda866984319b815ceec638e4e5b"


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("phase") != SNAPSHOT_PHASE or snapshot.get("status") != "PASS":
        raise ValueError("P0F7_9D77_SNAPSHOT_STATUS_INVALID")
    exact = {
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "source_revised_plan_sha256": EXPECTED_REVISED_PLAN_SHA256,
        "source_d74_report_sha256": EXPECTED_D74_REPORT_SHA256,
        "operations_verified": 23,
        "documents_verified": 23,
        "active_final_assignments": 22,
        "active_unique_tuples_verified": 22,
        "survivor_canonical_weekly_workload": 2,
        "query_budget": 2,
        "query_calls": 2,
        "student_records_read": 0,
        "teacher_names_read": 0,
        "production_writes": 0,
    }
    for field, expected in exact.items():
        if snapshot.get(field) != expected:
            raise ValueError(f"P0F7_9D77_SNAPSHOT_FIELD_INVALID:{field}")
    for field in (
        "retired_duplicate_verified",
        "survivor_verified",
        "remediation_final_state_verified",
    ):
        if snapshot.get(field) is not True:
            raise ValueError(f"P0F7_9D77_SNAPSHOT_GATE_CLOSED:{field}")
    if snapshot.get("database_mutation") is not False or snapshot.get("hard_delete") is not False:
        raise ValueError("P0F7_9D77_SNAPSHOT_SAFETY_INVALID")


def build_seal(snapshot: Mapping[str, Any], *, run_id: str, code_sha: str) -> dict[str, Any]:
    validate_snapshot(snapshot)
    seal: dict[str, Any] = {
        "phase": SEAL_PHASE,
        "status": "PASS",
        "source_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "source_revised_plan_sha256": EXPECTED_REVISED_PLAN_SHA256,
        "source_d74_report_sha256": EXPECTED_D74_REPORT_SHA256,
        "source_authorized_executor_sha256": EXPECTED_EXECUTOR_SHA256,
        "source_post_execution_snapshot_sha256": _canonical_sha256(snapshot),
        "github_actions_run_id": str(run_id),
        "github_code_sha": str(code_sha),
        "production_execution_status": "APPLIED_CONFIRMED_BY_POST_STATE",
        "operations_verified": 23,
        "active_unique_tuples_verified": 22,
        "duplicate_retirement_verified": True,
        "survivor_canonical_workload_verified": True,
        "survivor_canonical_weekly_workload": 2,
        "remediation_final_state_verified": True,
        "verification_production_access": "READ_ONLY",
        "verification_database_mutation": False,
        "verification_production_writes": 0,
        "student_records_read": 0,
        "teacher_names_read": 0,
        "hard_delete": False,
        "final_classification": "REMEDIATION_APPLIED_AND_POST_STATE_VERIFIED",
    }
    seal["seal_sha256"] = _canonical_sha256(seal)
    return seal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seal P0-F7.9D7.7 final remediation state")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seal = build_seal(_load(args.snapshot), run_id=args.run_id, code_sha=args.code_sha)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(seal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("P0F7_9D77_FINAL_REMEDIATION_SEAL=PASS")
    print(f"SEAL_SHA256={seal['seal_sha256']}")
    print("FINAL_CLASSIFICATION=REMEDIATION_APPLIED_AND_POST_STATE_VERIFIED")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")
    print(f"SEAL={args.json}")


if __name__ == "__main__":
    main()
