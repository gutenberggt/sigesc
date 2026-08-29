"""P0-F7.9D3 — offline collision preflight for UNIQUE_SAFE_TARGET proposals.

Consumes the sealed D2 report and one bounded structural snapshot. It never
accesses production. The analyzer detects source drift and whether the same
staff/class/target/year tuple already has an active teacher_assignment.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

D2_PHASE = "P0F7.9D2-SAFE-TARGET-RESOLUTION-2026"
SNAPSHOT_PHASE = "P0F7.9D3-COLLISION-PREFLIGHT-SNAPSHOT-2026"
SNAPSHOT_MODE = "READ_ONLY_BOUNDED_TARGET_COLLISION_PREFLIGHT"
OUTPUT_PHASE = "P0F7.9D3-OFFLINE-COLLISION-PREFLIGHT-2026"
ACTIVE_STATUS = {"active", "ativo"}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _is_active(row: Mapping[str, Any]) -> bool:
    return _norm(row.get("status")).casefold() in ACTIVE_STATUS


def _proposal_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    if report.get("phase") != D2_PHASE or report.get("status") != "PASS":
        raise ValueError("P0F7_9D2_REPORT_INVALID")
    if report.get("summary", {}).get("proposal_only") is not True:
        raise ValueError("P0F7_9D2_NOT_PROPOSAL_ONLY")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in report.get("resolutions") or []:
        if _norm(row.get("resolution")) != "UNIQUE_SAFE_TARGET":
            continue
        assignment_id = _norm(row.get("assignment_id"))
        targets = list(row.get("validated_targets") or [])
        if not assignment_id or assignment_id in seen or len(targets) != 1:
            raise ValueError("P0F7_9D3_D2_PROPOSAL_INVALID")
        seen.add(assignment_id)
        out.append({
            "assignment_id": assignment_id,
            "school_id": _norm(row.get("school_id")),
            "class_id": _norm(row.get("class_id")),
            "class_name": row.get("class_name"),
            "source_course_id": _norm(row.get("source_course_id")),
            "source_course_name": row.get("source_course_name"),
            "source_course_level": row.get("source_course_level"),
            "target": targets[0],
        })
    expected = int(report.get("summary", {}).get("unique_safe_target") or 0)
    if len(out) != expected:
        raise ValueError("P0F7_9D3_D2_PROPOSAL_COUNT_DRIFT")
    return out


def build_report(d2: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    proposals = _proposal_rows(d2)
    tenant = _norm(d2.get("mantenedora_id"))
    year = int(d2.get("academic_year") or 0)
    if not tenant or year <= 0:
        raise ValueError("P0F7_9D3_D2_CONTEXT_INVALID")
    if snapshot.get("phase") != SNAPSHOT_PHASE or snapshot.get("mode") != SNAPSHOT_MODE:
        raise ValueError("P0F7_9D3_SNAPSHOT_INVALID")
    if _norm(snapshot.get("mantenedora_id")) != tenant or int(snapshot.get("academic_year") or 0) != year:
        raise ValueError("P0F7_9D3_SNAPSHOT_CONTEXT_DRIFT")
    if _norm(snapshot.get("source_p0f7_9d2_report_sha256")) != _canonical_sha256(d2):
        raise ValueError("P0F7_9D3_SOURCE_CHAIN_MISMATCH")
    if int(snapshot.get("query_budget") or 0) != 2 or int(snapshot.get("query_calls") or 0) != 2:
        raise ValueError("P0F7_9D3_QUERY_BUDGET_INVALID")
    if int(snapshot.get("source_proposals") or 0) != len(proposals):
        raise ValueError("P0F7_9D3_SOURCE_PROPOSAL_COUNT_DRIFT")
    records = list(snapshot.get("teacher_assignments") or [])
    if len(records) != int((snapshot.get("counts") or {}).get("matching_assignments") or 0):
        raise ValueError("P0F7_9D3_SNAPSHOT_RECORD_COUNT_DRIFT")

    by_id: dict[str, Mapping[str, Any]] = {}
    for row in records:
        row_id = _norm((row or {}).get("id"))
        if not row_id or row_id in by_id:
            raise ValueError("P0F7_9D3_ASSIGNMENT_ID_INVALID_OR_DUPLICATE")
        if _norm((row or {}).get("mantenedora_id")) != tenant:
            raise ValueError("P0F7_9D3_ASSIGNMENT_TENANT_DRIFT")
        if int((row or {}).get("academic_year") or 0) != year:
            raise ValueError("P0F7_9D3_ASSIGNMENT_YEAR_DRIFT")
        by_id[row_id] = row

    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for proposal in proposals:
        source = by_id.get(proposal["assignment_id"])
        status = "CLEAR_FOR_REMEDIATION_PLANNING"
        reasons: list[str] = []
        staff_id = ""
        active_collisions: list[str] = []
        inactive_collisions: list[str] = []

        if not source:
            status = "SOURCE_DRIFT_REVIEW_REQUIRED"
            reasons.append("SOURCE_ASSIGNMENT_MISSING")
        else:
            staff_id = _norm(source.get("staff_id"))
            source_checks = {
                "school_id": proposal["school_id"],
                "class_id": proposal["class_id"],
                "course_id": proposal["source_course_id"],
            }
            if not staff_id:
                reasons.append("SOURCE_STAFF_ID_REQUIRED")
            for field, expected in source_checks.items():
                if _norm(source.get(field)) != expected:
                    reasons.append(f"SOURCE_{field.upper()}_DRIFT")
            if not _is_active(source):
                reasons.append("SOURCE_NOT_ACTIVE")
            if reasons:
                status = "SOURCE_DRIFT_REVIEW_REQUIRED"

        target_course_id = _norm((proposal.get("target") or {}).get("course_id"))
        if status == "CLEAR_FOR_REMEDIATION_PLANNING":
            for row in records:
                if _norm(row.get("id")) == proposal["assignment_id"]:
                    continue
                if (
                    _norm(row.get("staff_id")) == staff_id
                    and _norm(row.get("school_id")) == proposal["school_id"]
                    and _norm(row.get("class_id")) == proposal["class_id"]
                    and _norm(row.get("course_id")) == target_course_id
                ):
                    if _is_active(row):
                        active_collisions.append(_norm(row.get("id")))
                    else:
                        inactive_collisions.append(_norm(row.get("id")))
            if active_collisions:
                status = "ACTIVE_TARGET_ALREADY_EXISTS"
                reasons.append("ACTIVE_DUPLICATE_TUPLE_WOULD_RESULT")

        counts[status] += 1
        results.append({
            "assignment_id": proposal["assignment_id"],
            "school_id": proposal["school_id"],
            "class_id": proposal["class_id"],
            "class_name": proposal["class_name"],
            "source_course_id": proposal["source_course_id"],
            "source_course_name": proposal["source_course_name"],
            "source_course_level": proposal["source_course_level"],
            "target_course_id": target_course_id,
            "target_course_name": (proposal.get("target") or {}).get("course_name"),
            "target_course_level": (proposal.get("target") or {}).get("course_level"),
            "target_write_policy": (proposal.get("target") or {}).get("write_policy"),
            "preflight": status,
            "reasons": reasons,
            "active_collision_assignment_ids": sorted(active_collisions),
            "inactive_collision_assignment_ids": sorted(inactive_collisions),
            "staff_id_present": bool(staff_id),
        })

    results.sort(key=lambda row: (_norm(row.get("school_id")), _norm(row.get("assignment_id"))))
    output: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "mantenedora_id": tenant,
        "academic_year": year,
        "source_p0f7_9d2_report_sha256": _canonical_sha256(d2),
        "source_snapshot_sha256": _canonical_sha256(snapshot),
        "summary": {
            "unique_safe_target_source": len(proposals),
            "clear_for_remediation_planning": counts["CLEAR_FOR_REMEDIATION_PLANNING"],
            "active_target_already_exists": counts["ACTIVE_TARGET_ALREADY_EXISTS"],
            "source_drift_review_required": counts["SOURCE_DRIFT_REVIEW_REQUIRED"],
            "proposal_only": True,
        },
        "results": results,
        "safety": {
            "production_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "student_records_read": 0,
            "teacher_names_read": 0,
            "staff_identifier_used_for_collision_check": True,
        },
    }
    output["report_sha256"] = _canonical_sha256(output)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze P0-F7.9D3 collision preflight offline")
    parser.add_argument("--d2-report", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(_load(args.d2_report), _load(args.snapshot))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("P0F7_9D3_COLLISION_PREFLIGHT=PASS")
    print(f"REPORT={args.json}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("REMEDIATION_EXECUTED=NO")


if __name__ == "__main__":
    main()
