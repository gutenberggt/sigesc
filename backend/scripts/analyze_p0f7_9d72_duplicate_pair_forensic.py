"""P0-F7.9D7.2 — offline forensic analysis of the one blocked duplicate pair.

Consumes only the D4 plan, D7.1 collision report and a bounded D7.2 snapshot.
It never connects to MongoDB and never writes production. The report deliberately
keeps survivor selection and the 2h-vs-3h workload choice as separate human
adjudication decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

PLAN_PHASE = "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026"
D71_PHASE = "P0F7.9D7.1-INTRA-BATCH-COLLISION-PREFLIGHT-2026"
SNAPSHOT_PHASE = "P0F7.9D7.2-DUPLICATE-PAIR-FORENSIC-SNAPSHOT-2026"
SNAPSHOT_MODE = "READ_ONLY_BOUNDED_DUPLICATE_PAIR_FORENSIC"
OUTPUT_PHASE = "P0F7.9D7.2-OFFLINE-DUPLICATE-PAIR-FORENSIC-2026"
EXPECTED_PLAN_SHA = "6d39d8425c0555b36b69c8f5d00832fc8f93e1c4f38c35c0f29ea8e72fcf1312"
ACTIVE_STATUSES = {"active", "ativo"}
EXPECTED_QUERY_BUDGET = 5


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
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path}")
    return payload


def _active(value: Any) -> bool:
    return _norm(value).casefold() in ACTIVE_STATUSES


def analyze(plan: Mapping[str, Any], d71: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("phase") != PLAN_PHASE or plan.get("status") != "PASS":
        raise ValueError("P0F7_9D72_PLAN_INVALID")
    plan_sha = _norm(plan.get("plan_sha256"))
    if plan_sha != EXPECTED_PLAN_SHA or plan_sha != _unsigned_hash(plan, "plan_sha256"):
        raise ValueError("P0F7_9D72_PLAN_SHA_INVALID")

    if d71.get("phase") != D71_PHASE or d71.get("status") != "PASS":
        raise ValueError("P0F7_9D72_D71_INVALID")
    d71_sha = _norm(d71.get("report_sha256"))
    if not d71_sha or d71_sha != _unsigned_hash(d71, "report_sha256"):
        raise ValueError("P0F7_9D72_D71_SHA_INVALID")
    summary71 = d71.get("summary") or {}
    if (
        int(summary71.get("blocked_intra_batch") or 0) != 2
        or int(summary71.get("collision_groups") or 0) != 1
        or summary71.get("execution_gate_open") is not False
    ):
        raise ValueError("P0F7_9D72_D71_EXPECTED_BLOCK_NOT_PRESENT")

    if snapshot.get("phase") != SNAPSHOT_PHASE or snapshot.get("mode") != SNAPSHOT_MODE:
        raise ValueError("P0F7_9D72_SNAPSHOT_INVALID")
    if _norm(snapshot.get("sealed_plan_sha256")) != plan_sha:
        raise ValueError("P0F7_9D72_SNAPSHOT_PLAN_CHAIN_MISMATCH")
    if _norm(snapshot.get("source_d71_report_sha256")) != d71_sha:
        raise ValueError("P0F7_9D72_SNAPSHOT_D71_CHAIN_MISMATCH")
    if int(snapshot.get("query_budget") or 0) != EXPECTED_QUERY_BUDGET or int(snapshot.get("query_calls") or 0) != EXPECTED_QUERY_BUDGET:
        raise ValueError("P0F7_9D72_QUERY_BUDGET_INVALID")

    tenant = _norm(plan.get("mantenedora_id"))
    year = int(plan.get("academic_year") or 0)
    if _norm(snapshot.get("mantenedora_id")) != tenant or int(snapshot.get("academic_year") or 0) != year:
        raise ValueError("P0F7_9D72_SNAPSHOT_CONTEXT_DRIFT")

    blocked = list(d71.get("blocked_entries") or [])
    if len(blocked) != 2:
        raise ValueError("P0F7_9D72_BLOCKED_COUNT_INVALID")
    blocked_by_id = {_norm(row.get("assignment_id")): row for row in blocked}
    if len(blocked_by_id) != 2:
        raise ValueError("P0F7_9D72_BLOCKED_ID_INVALID")

    assignments = list(snapshot.get("teacher_assignments") or [])
    if len(assignments) != 2:
        raise ValueError("P0F7_9D72_ASSIGNMENT_COUNT_INVALID")
    by_id: dict[str, Mapping[str, Any]] = {}
    for row in assignments:
        assignment_id = _norm(row.get("id"))
        if not assignment_id or assignment_id in by_id or assignment_id not in blocked_by_id:
            raise ValueError("P0F7_9D72_ASSIGNMENT_ID_INVALID")
        by_id[assignment_id] = row

    staff_ids = {_norm(row.get("staff_id")) for row in assignments}
    class_ids = {_norm(row.get("class_id")) for row in assignments}
    school_ids = {_norm(row.get("school_id")) for row in assignments}
    years = {str(row.get("academic_year") or "").strip() for row in assignments}
    if "" in staff_ids or len(staff_ids) != 1:
        raise ValueError("P0F7_9D72_PAIR_STAFF_MISMATCH")
    if len(class_ids) != 1 or len(school_ids) != 1 or years != {str(year)}:
        raise ValueError("P0F7_9D72_PAIR_SCOPE_MISMATCH")
    if any(not _active(row.get("status")) for row in assignments):
        raise ValueError("P0F7_9D72_PAIR_NOT_BOTH_ACTIVE")
    if any(row.get("is_substituicao") is True for row in assignments):
        raise ValueError("P0F7_9D72_SUBSTITUTION_PAIR_REQUIRES_SEPARATE_REVIEW")

    class_id = next(iter(class_ids))
    school_id = next(iter(school_ids))
    class_record = snapshot.get("class_record") or {}
    if _norm(class_record.get("id")) != class_id or _norm(class_record.get("school_id")) != school_id:
        raise ValueError("P0F7_9D72_CLASS_DRIFT")

    courses = list(snapshot.get("courses") or [])
    course_by_id = {_norm(row.get("id")): row for row in courses if _norm(row.get("id"))}
    expected_course_ids = {
        _norm(row.get("source_course_id")) for row in blocked
    } | {
        _norm(row.get("target_course_id")) for row in blocked
    }
    if len(expected_course_ids) != 3 or set(course_by_id) != expected_course_ids:
        raise ValueError("P0F7_9D72_COURSE_SET_INVALID")

    target_ids = {_norm(row.get("target_course_id")) for row in blocked}
    if len(target_ids) != 1:
        raise ValueError("P0F7_9D72_SHARED_TARGET_NOT_UNIQUE")
    shared_target_id = next(iter(target_ids))

    audit = snapshot.get("audit_summaries") or {}
    slots = snapshot.get("schedule_slot_counts_by_course") or {}

    public_rows: list[dict[str, Any]] = []
    workloads: list[Any] = []
    for assignment_id, blocked_row in sorted(blocked_by_id.items(), key=lambda item: int(item[1].get("ordinal") or 0)):
        live = by_id[assignment_id]
        source_course_id = _norm(blocked_row.get("source_course_id"))
        if _norm(live.get("course_id")) != source_course_id:
            raise ValueError(f"P0F7_9D72_SOURCE_COURSE_DRIFT:{assignment_id}")
        workload = live.get("carga_horaria_semanal")
        workloads.append(workload)
        source_course = course_by_id[source_course_id]
        public_rows.append(
            {
                "ordinal": int(blocked_row.get("ordinal") or 0),
                "assignment_id": assignment_id,
                "source_course_id": source_course_id,
                "source_course_name": source_course.get("name"),
                "source_course_level": source_course.get("nivel_ensino"),
                "weekly_workload": workload,
                "status": live.get("status"),
                "created_at": live.get("created_at"),
                "updated_at": live.get("updated_at"),
                "created_by_present": bool(_norm(live.get("created_by"))),
                "updated_by_present": bool(_norm(live.get("updated_by"))),
                "audit": audit.get(assignment_id) or {"event_count": 0, "first_event_at": None, "last_event_at": None, "action_counts": {}},
                "schedule_slots_for_source_course": int(slots.get(source_course_id) or 0),
            }
        )

    normalized_workloads = {_norm(value) for value in workloads}
    workload_conflict = len(normalized_workloads) > 1
    if not workload_conflict:
        raise ValueError("P0F7_9D72_EXPECTED_WORKLOAD_CONFLICT_NOT_PRESENT")

    target_course = course_by_id[shared_target_id]
    target_view = {
        "course_id": shared_target_id,
        "course_name": target_course.get("name"),
        "course_level": target_course.get("nivel_ensino"),
        "grade_levels": target_course.get("grade_levels") or [],
        "workload": target_course.get("workload"),
        "carga_horaria_por_serie": target_course.get("carga_horaria_por_serie"),
        "active": target_course.get("active"),
        "status": target_course.get("status"),
        "schedule_slots": int(slots.get(shared_target_id) or 0),
    }

    report: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "mode": "LOCAL_OFFLINE_READ_ONLY_FORENSIC",
        "sealed_plan_sha256": plan_sha,
        "source_d71_report_sha256": d71_sha,
        "source_snapshot_sha256": _canonical_sha256(snapshot),
        "class": {
            "class_id": class_id,
            "class_name": class_record.get("name"),
            "class_level": class_record.get("nivel_ensino") or class_record.get("education_level"),
            "grade_level": class_record.get("grade_level"),
            "series": class_record.get("series"),
        },
        "pair": {
            "classification": "ACTIVE_DUPLICATE_SEMANTIC_PAIR_REQUIRES_CONSOLIDATION",
            "same_staff": True,
            "same_school": True,
            "same_class": True,
            "same_academic_year": True,
            "both_active": True,
            "substitution_present": False,
            "weekly_workload_conflict": True,
            "assignments": public_rows,
            "shared_target": target_view,
        },
        "adjudication_contract": {
            "automatic_survivor_selection": False,
            "survivor_decision_required": True,
            "automatic_workload_decision": False,
            "workload_decision_required": True,
            "allowed_structural_outcome": "EXACTLY_ONE_ACTIVE_ASSIGNMENT_MAY_SURVIVE_FOR_THE_SHARED_TARGET_TUPLE",
            "duplicate_retirement_requires_separate_explicit_write_plan": True,
            "revised_course_remap_requires_new_explicit_write_authorization": True,
            "current_23_write_authorization_reusable": False,
        },
        "summary": {
            "blocked_assignments": 2,
            "collision_groups": 1,
            "semantic_pair_confirmed": True,
            "weekly_workload_conflict": True,
            "survivor_decision_required": True,
            "workload_decision_required": True,
            "production_write_authorized": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "safety": {
            "production_access": False,
            "database_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "staff_id_used_only_for_same-person_check": True,
            "staff_id_exposed_in_report": False,
            "teacher_names_read": 0,
            "student_records_read": 0,
            "grades_read": 0,
            "attendance_read": 0,
        },
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze P0-F7.9D7.2 duplicate-pair forensic snapshot offline")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--d71-report", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = analyze(_load(args.plan), _load(args.d71_report), _load(args.snapshot))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("P0F7_9D72_DUPLICATE_PAIR_FORENSIC=PASS")
    print(f"REPORT={args.json}")
    print(f"REPORT_SHA256={report['report_sha256']}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")
    print("REMEDIATION_EXECUTED=NO")


if __name__ == "__main__":
    main()
