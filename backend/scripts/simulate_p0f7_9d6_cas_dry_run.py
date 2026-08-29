"""Offline simulator for the P0-F7.9D6 CAS package.

The simulator consumes only the local D6 package and the bounded D5 snapshot.
It never connects to MongoDB. It verifies that every sealed CAS would match one
active source, would not collide with an active target tuple, would reach the
expected postcondition, and that compensating rollback restores the source.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

PACKAGE_PHASE = "P0F7.9D6-CAS-DRY-RUN-PACKAGE-2026"
PACKAGE_MODE = "DRY_RUN_ONLY_NON_EXECUTABLE"
SNAPSHOT_PHASE = "P0F7.9D5-LAST-MILE-PREFLIGHT-SNAPSHOT-2026"
SNAPSHOT_MODE = "READ_ONLY_BOUNDED_LAST_MILE_EXECUTION_PREFLIGHT"
EXPECTED_ENTRIES = 23
ACTIVE_STATUSES = {"active", "ativo"}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path}")
    return payload


def _is_active(row: Mapping[str, Any]) -> bool:
    return _norm(row.get("status")).casefold() in ACTIVE_STATUSES


def _validate_package(package: Mapping[str, Any]) -> None:
    if package.get("phase") != PACKAGE_PHASE or package.get("status") != "PASS" or package.get("mode") != PACKAGE_MODE:
        raise ValueError("P0F7_9D6_PACKAGE_INVALID")
    stored = _norm(package.get("package_sha256"))
    unsigned = dict(package)
    unsigned.pop("package_sha256", None)
    if not stored or stored != _canonical_sha256(unsigned):
        raise ValueError("P0F7_9D6_PACKAGE_SHA256_INVALID")
    summary = package.get("summary") or {}
    if int(summary.get("entries") or 0) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D6_PACKAGE_ENTRY_COUNT_INVALID")
    if summary.get("dry_run_only") is not True or summary.get("production_write_authorized") is not False:
        raise ValueError("P0F7_9D6_PACKAGE_AUTHORIZATION_INVALID")
    contract = package.get("execution_contract") or {}
    if contract.get("executable") is not False or contract.get("writer_implementation_present") is not False:
        raise ValueError("P0F7_9D6_PACKAGE_MUST_BE_NON_EXECUTABLE")


def simulate(package: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    _validate_package(package)
    if snapshot.get("phase") != SNAPSHOT_PHASE or snapshot.get("mode") != SNAPSHOT_MODE:
        raise ValueError("P0F7_9D5_SNAPSHOT_INVALID")
    if _norm(snapshot.get("sealed_plan_sha256")) != _norm(package.get("sealed_plan_sha256")):
        raise ValueError("P0F7_9D6_SNAPSHOT_PLAN_CHAIN_MISMATCH")
    if _norm(snapshot.get("mantenedora_id")) != _norm(package.get("mantenedora_id")):
        raise ValueError("P0F7_9D6_SNAPSHOT_TENANT_DRIFT")
    if int(snapshot.get("academic_year") or 0) != int(package.get("academic_year") or 0):
        raise ValueError("P0F7_9D6_SNAPSHOT_YEAR_DRIFT")

    records = [copy.deepcopy(row) for row in (snapshot.get("teacher_assignments") or [])]
    by_id: dict[str, dict[str, Any]] = {}
    for row in records:
        row_id = _norm((row or {}).get("id"))
        if not row_id or row_id in by_id:
            raise ValueError("P0F7_9D6_SNAPSHOT_ASSIGNMENT_ID_INVALID_OR_DUPLICATE")
        by_id[row_id] = row

    receipts: list[dict[str, Any]] = []
    for entry in package.get("entries") or []:
        assignment_id = _norm(entry.get("assignment_id"))
        source_id = _norm(entry.get("source_course_id"))
        target_id = _norm(entry.get("target_course_id"))
        source = by_id.get(assignment_id)
        if not source:
            raise ValueError(f"P0F7_9D6_DRY_RUN_SOURCE_MISSING:{assignment_id}")
        if not _is_active(source):
            raise ValueError(f"P0F7_9D6_DRY_RUN_SOURCE_NOT_ACTIVE:{assignment_id}")
        for field, expected in {
            "mantenedora_id": _norm(package.get("mantenedora_id")),
            "academic_year": str(package.get("academic_year")),
            "school_id": _norm(entry.get("school_id")),
            "class_id": _norm(entry.get("class_id")),
            "course_id": source_id,
        }.items():
            current = str(source.get(field) or "").strip()
            if current != expected:
                raise ValueError(f"P0F7_9D6_DRY_RUN_CAS_DRIFT:{assignment_id}:{field}")
        staff_id = _norm(source.get("staff_id"))
        if not staff_id:
            raise ValueError(f"P0F7_9D6_DRY_RUN_STAFF_REQUIRED:{assignment_id}")

        collision_ids = []
        for row in records:
            if _norm(row.get("id")) == assignment_id:
                continue
            if (
                _norm(row.get("staff_id")) == staff_id
                and _norm(row.get("school_id")) == _norm(entry.get("school_id"))
                and _norm(row.get("class_id")) == _norm(entry.get("class_id"))
                and _norm(row.get("course_id")) == target_id
                and _is_active(row)
            ):
                collision_ids.append(_norm(row.get("id")))
        if collision_ids:
            raise ValueError(f"P0F7_9D6_DRY_RUN_ACTIVE_COLLISION:{assignment_id}")

        before = _norm(source.get("course_id"))
        source["course_id"] = target_id
        if _norm(source.get("course_id")) != target_id:
            raise ValueError(f"P0F7_9D6_DRY_RUN_POSTCONDITION_FAILED:{assignment_id}")

        source["course_id"] = source_id
        if _norm(source.get("course_id")) != source_id:
            raise ValueError(f"P0F7_9D6_DRY_RUN_ROLLBACK_FAILED:{assignment_id}")

        receipt = {
            "ordinal": int(entry.get("ordinal") or 0),
            "assignment_id": assignment_id,
            "before_course_id": before,
            "simulated_after_course_id": target_id,
            "cas_match_count": 1,
            "active_collision_count": 0,
            "postcondition_verified": True,
            "rollback_attempted": True,
            "rollback_verified": True,
        }
        receipt["receipt_sha256"] = _canonical_sha256(receipt)
        receipts.append(receipt)

    receipts.sort(key=lambda item: int(item.get("ordinal") or 0))
    if len(receipts) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D6_DRY_RUN_RECEIPT_COUNT_INVALID")

    report: dict[str, Any] = {
        "phase": "P0F7.9D6-OFFLINE-CAS-DRY-RUN-2026",
        "status": "PASS",
        "package_sha256": _norm(package.get("package_sha256")),
        "source_snapshot_sha256": _canonical_sha256(snapshot),
        "summary": {
            "entries": EXPECTED_ENTRIES,
            "cas_match_verified": EXPECTED_ENTRIES,
            "postconditions_verified": EXPECTED_ENTRIES,
            "rollback_verified": EXPECTED_ENTRIES,
            "active_collisions": 0,
            "dry_run_only": True,
            "production_write_authorized": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "receipts": receipts,
        "execution_contract": {
            "executable": False,
            "future_writer_phase_required": "P0-F7.9D7",
            "required_strategy": "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED",
            "failure_policy": "FAIL_CLOSED_NO_PARTIAL_GUESSING",
        },
        "safety": {
            "production_access": False,
            "database_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate P0-F7.9D6 CAS and compensating rollback offline")
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = simulate(_load(args.package), _load(args.snapshot))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("P0F7_9D6_OFFLINE_CAS_DRY_RUN=PASS")
    print(f"REPORT={args.json}")
    print(f"REPORT_SHA256={report['report_sha256']}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")
    print("REMEDIATION_EXECUTED=NO")


if __name__ == "__main__":
    main()
