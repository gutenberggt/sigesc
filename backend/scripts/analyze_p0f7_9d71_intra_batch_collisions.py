"""P0-F7.9D7.1 — offline intra-batch target collision preflight.

This analyzer exists because individually valid target transitions can collide
with each other after earlier entries in the same batch are applied. It consumes
only the sealed D4 plan and a bounded D5 snapshot already collected locally.
It never connects to MongoDB and never mutates data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

PLAN_PHASE = "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026"
PLAN_MODE = "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE"
SNAPSHOT_PHASE = "P0F7.9D5-LAST-MILE-PREFLIGHT-SNAPSHOT-2026"
SNAPSHOT_MODE = "READ_ONLY_BOUNDED_LAST_MILE_EXECUTION_PREFLIGHT"
OUTPUT_PHASE = "P0F7.9D7.1-INTRA-BATCH-COLLISION-PREFLIGHT-2026"
OUTPUT_MODE = "LOCAL_OFFLINE_READ_ONLY"
EXPECTED_ENTRIES = 23
ACTIVE_STATUSES = {"active", "ativo"}


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


def _unsigned_hash(payload: Mapping[str, Any], signature_field: str) -> str:
    unsigned = dict(payload)
    unsigned.pop(signature_field, None)
    return _canonical_sha256(unsigned)


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path}")
    return payload


def _is_active(row: Mapping[str, Any]) -> bool:
    return _norm(row.get("status")).casefold() in ACTIVE_STATUSES


def analyze(plan: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("phase") != PLAN_PHASE or plan.get("status") != "PASS" or plan.get("mode") != PLAN_MODE:
        raise ValueError("P0F79D71_PLAN_INVALID")
    plan_sha = _norm(plan.get("plan_sha256"))
    if not plan_sha or plan_sha != _unsigned_hash(plan, "plan_sha256"):
        raise ValueError("P0F79D71_PLAN_SHA256_INVALID")
    if (plan.get("execution_contract") or {}).get("executable") is not False:
        raise ValueError("P0F79D71_PLAN_MUST_BE_NON_EXECUTABLE")

    entries = list(plan.get("entries") or [])
    tenant = _norm(plan.get("mantenedora_id"))
    year = int(plan.get("academic_year") or 0)
    if len(entries) != EXPECTED_ENTRIES or not tenant or year <= 0:
        raise ValueError("P0F79D71_PLAN_CONTEXT_INVALID")

    if snapshot.get("phase") != SNAPSHOT_PHASE or snapshot.get("mode") != SNAPSHOT_MODE:
        raise ValueError("P0F79D71_SNAPSHOT_INVALID")
    if _norm(snapshot.get("sealed_plan_sha256")) != plan_sha:
        raise ValueError("P0F79D71_PLAN_SNAPSHOT_CHAIN_MISMATCH")
    if _norm(snapshot.get("mantenedora_id")) != tenant or int(snapshot.get("academic_year") or 0) != year:
        raise ValueError("P0F79D71_SNAPSHOT_CONTEXT_DRIFT")
    if int(snapshot.get("source_entries") or 0) != EXPECTED_ENTRIES:
        raise ValueError("P0F79D71_SNAPSHOT_SOURCE_COUNT_INVALID")

    assignment_by_id: dict[str, Mapping[str, Any]] = {}
    for row in snapshot.get("teacher_assignments") or []:
        row_id = _norm((row or {}).get("id"))
        if not row_id or row_id in assignment_by_id:
            raise ValueError("P0F79D71_SNAPSHOT_ASSIGNMENT_ID_INVALID_OR_DUPLICATE")
        assignment_by_id[row_id] = row

    proposals: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()

    for entry in entries:
        assignment_id = _norm(entry.get("assignment_id"))
        school_id = _norm(entry.get("school_id"))
        class_id = _norm(entry.get("class_id"))
        source_course_id = _norm((entry.get("source") or {}).get("course_id"))
        target_course_id = _norm((entry.get("target") or {}).get("course_id"))
        ordinal = int(entry.get("ordinal") or 0)
        if (
            not assignment_id
            or assignment_id in seen
            or not school_id
            or not class_id
            or not source_course_id
            or not target_course_id
            or source_course_id == target_course_id
            or ordinal <= 0
        ):
            raise ValueError("P0F79D71_PLAN_ENTRY_INVALID")
        seen.add(assignment_id)

        source_row = assignment_by_id.get(assignment_id)
        if not source_row:
            raise ValueError(f"P0F79D71_SOURCE_NOT_IN_SNAPSHOT:{assignment_id}")
        staff_id = _norm(source_row.get("staff_id"))
        if not staff_id:
            raise ValueError(f"P0F79D71_STAFF_ID_REQUIRED:{assignment_id}")
        if not _is_active(source_row):
            raise ValueError(f"P0F79D71_SOURCE_NOT_ACTIVE:{assignment_id}")
        for field, expected in {
            "mantenedora_id": tenant,
            "school_id": school_id,
            "class_id": class_id,
            "course_id": source_course_id,
        }.items():
            if _norm(source_row.get(field)) != expected:
                raise ValueError(f"P0F79D71_SOURCE_DRIFT:{assignment_id}:{field}")
        if str(source_row.get("academic_year") or "").strip() != str(year):
            raise ValueError(f"P0F79D71_SOURCE_DRIFT:{assignment_id}:academic_year")

        tuple_key = (staff_id, school_id, class_id, target_course_id, year)
        fingerprint = _canonical_sha256(
            {
                "staff_id": staff_id,
                "school_id": school_id,
                "class_id": class_id,
                "target_course_id": target_course_id,
                "academic_year": year,
            }
        )
        proposal = {
            "ordinal": ordinal,
            "assignment_id": assignment_id,
            "school_id": school_id,
            "class_id": class_id,
            "class_name": entry.get("class_name"),
            "source_course_id": source_course_id,
            "source_course_name": (entry.get("source") or {}).get("course_name"),
            "source_course_level": (entry.get("source") or {}).get("course_level"),
            "target_course_id": target_course_id,
            "target_course_name": (entry.get("target") or {}).get("course_name"),
            "target_course_level": (entry.get("target") or {}).get("course_level"),
            "write_policy": (entry.get("target") or {}).get("write_policy"),
            "target_tuple_fingerprint_sha256": fingerprint,
        }
        proposals.append(proposal)
        grouped[tuple_key].append(proposal)

    collision_groups: list[dict[str, Any]] = []
    blocked_ids: set[str] = set()
    for members in grouped.values():
        if len(members) <= 1:
            continue
        ordered = sorted(members, key=lambda row: int(row["ordinal"]))
        blocked_ids.update(_norm(row.get("assignment_id")) for row in ordered)
        collision_groups.append(
            {
                "target_tuple_fingerprint_sha256": ordered[0]["target_tuple_fingerprint_sha256"],
                "proposal_count": len(ordered),
                "assignment_ids": [_norm(row.get("assignment_id")) for row in ordered],
                "ordinals": [int(row.get("ordinal") or 0) for row in ordered],
                "class_id": ordered[0]["class_id"],
                "class_name": ordered[0].get("class_name"),
                "target_course_id": ordered[0]["target_course_id"],
                "target_course_name": ordered[0].get("target_course_name"),
                "members": ordered,
                "required_resolution": "HUMAN_ADJUDICATION_BEFORE_ANY_REVISED_WRITE_PLAN",
            }
        )

    collision_groups.sort(key=lambda group: min(group.get("ordinals") or [999999]))
    safe_entries = [row for row in proposals if _norm(row.get("assignment_id")) not in blocked_ids]
    safe_entries.sort(key=lambda row: int(row["ordinal"]))
    blocked_entries = [row for row in proposals if _norm(row.get("assignment_id")) in blocked_ids]
    blocked_entries.sort(key=lambda row: int(row["ordinal"]))

    gate_open = len(collision_groups) == 0
    report: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "mode": OUTPUT_MODE,
        "sealed_plan_sha256": plan_sha,
        "source_snapshot_sha256": _canonical_sha256(snapshot),
        "mantenedora_id": tenant,
        "academic_year": year,
        "summary": {
            "entries": EXPECTED_ENTRIES,
            "safe_noncolliding": len(safe_entries),
            "blocked_intra_batch": len(blocked_entries),
            "collision_groups": len(collision_groups),
            "execution_gate_open": gate_open,
            "production_write_authorized": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "safe_entries": safe_entries,
        "blocked_entries": blocked_entries,
        "collision_groups": collision_groups,
        "execution_contract": {
            "executable": False,
            "full_23_entry_executor_may_be_armed": gate_open,
            "if_blocked": "do not retry P0-F7.9D7; create a separately authorized revised plan",
        },
        "safety": {
            "production_access": False,
            "database_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "staff_ids_exposed_in_report": False,
            "teacher_names_read": 0,
            "student_records_read": 0,
        },
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze P0-F7.9D7.1 intra-batch target collisions offline")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--d5-snapshot", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = analyze(_load(args.plan), _load(args.d5_snapshot))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("P0F7_9D71_INTRA_BATCH_PREFLIGHT=PASS")
    print(f"REPORT={args.json}")
    print(f"REPORT_SHA256={report['report_sha256']}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")
    print("REMEDIATION_EXECUTED=NO")


if __name__ == "__main__":
    main()
