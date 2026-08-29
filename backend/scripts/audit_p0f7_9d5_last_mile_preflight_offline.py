"""P0-F7.9D5 — offline topology and last-mile remediation preflight.

Consumes the sealed P0-F7.9D4 plan and one bounded read-only snapshot. The
analyzer never accesses production. It rechecks source CAS preconditions,
active-target collisions and the current teacher-assignment curriculum SSoT.
It also classifies MongoDB topology so a later explicitly authorized writer can
choose real multi-document transactions when supported, or CAS plus
compensating rollback otherwise.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.teacher_assignment_integrity import (  # noqa: E402
    TeacherAssignmentIntegrityError,
    validate_teacher_assignment_curriculum,
)

PLAN_PHASE = "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026"
PLAN_MODE = "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE"
SNAPSHOT_PHASE = "P0F7.9D5-LAST-MILE-PREFLIGHT-SNAPSHOT-2026"
SNAPSHOT_MODE = "READ_ONLY_BOUNDED_LAST_MILE_EXECUTION_PREFLIGHT"
OUTPUT_PHASE = "P0F7.9D5-OFFLINE-LAST-MILE-PREFLIGHT-2026"
ACTIVE_STATUSES = {"active", "ativo"}
EXPECTED_ENTRIES = 23
QUERY_BUDGET = 5


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


def _plan_sha256(plan: Mapping[str, Any]) -> str:
    unsigned = dict(plan)
    unsigned.pop("plan_sha256", None)
    return _canonical_sha256(unsigned)


def _is_active(row: Mapping[str, Any]) -> bool:
    return _norm(row.get("status")).casefold() in ACTIVE_STATUSES


def _topology(topology: Mapping[str, Any]) -> tuple[str, str, bool]:
    set_name = _norm(topology.get("set_name"))
    msg = _norm(topology.get("msg")).casefold()
    session_timeout = topology.get("logical_session_timeout_minutes")
    try:
        max_wire = int(topology.get("max_wire_version"))
    except (TypeError, ValueError):
        max_wire = -1

    if msg == "isdbgrid" and session_timeout is not None and max_wire >= 8:
        return (
            "SHARDED_TRANSACTION_CAPABLE",
            "MONGODB_MULTI_DOCUMENT_TRANSACTION_REQUIRED",
            True,
        )
    if set_name and session_timeout is not None and max_wire >= 7:
        return (
            "REPLICA_SET_TRANSACTION_CAPABLE",
            "MONGODB_MULTI_DOCUMENT_TRANSACTION_REQUIRED",
            True,
        )
    return (
        "STANDALONE_OR_TRANSACTION_UNAVAILABLE",
        "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED",
        False,
    )


def build_report(plan: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("phase") != PLAN_PHASE or plan.get("status") != "PASS" or plan.get("mode") != PLAN_MODE:
        raise ValueError("P0F7_9D4_PLAN_INVALID")
    stored_plan_sha = _norm(plan.get("plan_sha256"))
    if not stored_plan_sha or stored_plan_sha != _plan_sha256(plan):
        raise ValueError("P0F7_9D4_PLAN_SHA256_INVALID")
    if (plan.get("execution_contract") or {}).get("executable") is not False:
        raise ValueError("P0F7_9D4_PLAN_MUST_BE_NON_EXECUTABLE")

    tenant = _norm(plan.get("mantenedora_id"))
    year = int(plan.get("academic_year") or 0)
    entries = list(plan.get("entries") or [])
    if not tenant or year <= 0 or len(entries) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D5_PLAN_CONTEXT_INVALID")

    if snapshot.get("phase") != SNAPSHOT_PHASE or snapshot.get("mode") != SNAPSHOT_MODE:
        raise ValueError("P0F7_9D5_SNAPSHOT_INVALID")
    if _norm(snapshot.get("mantenedora_id")) != tenant or int(snapshot.get("academic_year") or 0) != year:
        raise ValueError("P0F7_9D5_SNAPSHOT_CONTEXT_DRIFT")
    if _norm(snapshot.get("sealed_plan_sha256")) != stored_plan_sha:
        raise ValueError("P0F7_9D5_PLAN_CHAIN_MISMATCH")
    if int(snapshot.get("query_budget") or 0) != QUERY_BUDGET or int(snapshot.get("query_calls") or 0) != QUERY_BUDGET:
        raise ValueError("P0F7_9D5_QUERY_BUDGET_INVALID")
    if int(snapshot.get("source_entries") or 0) != len(entries):
        raise ValueError("P0F7_9D5_SOURCE_ENTRY_COUNT_DRIFT")

    assignments = list(snapshot.get("teacher_assignments") or [])
    if len(assignments) != int((snapshot.get("counts") or {}).get("matching_assignments") or 0):
        raise ValueError("P0F7_9D5_ASSIGNMENT_COUNT_DRIFT")

    by_assignment: dict[str, Mapping[str, Any]] = {}
    for row in assignments:
        row_id = _norm((row or {}).get("id"))
        if not row_id or row_id in by_assignment:
            raise ValueError("P0F7_9D5_ASSIGNMENT_ID_INVALID_OR_DUPLICATE")
        if _norm((row or {}).get("mantenedora_id")) != tenant:
            raise ValueError("P0F7_9D5_ASSIGNMENT_TENANT_DRIFT")
        try:
            row_year = int((row or {}).get("academic_year") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("P0F7_9D5_ASSIGNMENT_YEAR_INVALID") from exc
        if row_year != year:
            raise ValueError("P0F7_9D5_ASSIGNMENT_YEAR_DRIFT")
        by_assignment[row_id] = row

    classes = list(snapshot.get("classes") or [])
    by_class: dict[str, Mapping[str, Any]] = {}
    for row in classes:
        row_id = _norm((row or {}).get("id"))
        if not row_id or row_id in by_class:
            raise ValueError("P0F7_9D5_CLASS_ID_INVALID_OR_DUPLICATE")
        if _norm((row or {}).get("mantenedora_id")) != tenant:
            raise ValueError("P0F7_9D5_CLASS_TENANT_DRIFT")
        by_class[row_id] = row

    courses = list(snapshot.get("target_courses") or [])
    by_course: dict[str, Mapping[str, Any]] = {}
    for row in courses:
        row_id = _norm((row or {}).get("id"))
        if not row_id or row_id in by_course:
            raise ValueError("P0F7_9D5_COURSE_ID_INVALID_OR_DUPLICATE")
        if _norm((row or {}).get("mantenedora_id")) != tenant:
            raise ValueError("P0F7_9D5_COURSE_TENANT_DRIFT")
        by_course[row_id] = row

    topology_mode, transaction_strategy, transaction_capable = _topology(snapshot.get("topology") or {})

    counts: Counter[str] = Counter()
    results: list[dict[str, Any]] = []
    seen_entries: set[str] = set()
    for entry in entries:
        assignment_id = _norm(entry.get("assignment_id"))
        if not assignment_id or assignment_id in seen_entries:
            raise ValueError("P0F7_9D5_PLAN_ENTRY_ID_INVALID_OR_DUPLICATE")
        seen_entries.add(assignment_id)
        school_id = _norm(entry.get("school_id"))
        class_id = _norm(entry.get("class_id"))
        source_course_id = _norm((entry.get("source") or {}).get("course_id"))
        target_course_id = _norm((entry.get("target") or {}).get("course_id"))
        sealed_write_policy = _norm((entry.get("target") or {}).get("write_policy"))

        status = "CLEAR_FOR_EXECUTION_AUTHORIZATION"
        reasons: list[str] = []
        active_collision_ids: list[str] = []
        staff_id = ""
        current_write_policy = ""

        source = by_assignment.get(assignment_id)
        if not source:
            reasons.append("SOURCE_ASSIGNMENT_MISSING")
        else:
            staff_id = _norm(source.get("staff_id"))
            if not staff_id:
                reasons.append("SOURCE_STAFF_ID_REQUIRED")
            for field, expected in {
                "school_id": school_id,
                "class_id": class_id,
                "course_id": source_course_id,
            }.items():
                if _norm(source.get(field)) != expected:
                    reasons.append(f"SOURCE_{field.upper()}_DRIFT")
            if not _is_active(source):
                reasons.append("SOURCE_NOT_ACTIVE")
        if reasons:
            status = "SOURCE_DRIFT_REVIEW_REQUIRED"

        if status == "CLEAR_FOR_EXECUTION_AUTHORIZATION":
            for row in assignments:
                if _norm(row.get("id")) == assignment_id:
                    continue
                if (
                    _norm(row.get("staff_id")) == staff_id
                    and _norm(row.get("school_id")) == school_id
                    and _norm(row.get("class_id")) == class_id
                    and _norm(row.get("course_id")) == target_course_id
                    and _is_active(row)
                ):
                    active_collision_ids.append(_norm(row.get("id")))
            if active_collision_ids:
                status = "ACTIVE_TARGET_ALREADY_EXISTS"
                reasons.append("ACTIVE_DUPLICATE_TUPLE_WOULD_RESULT")

        if status == "CLEAR_FOR_EXECUTION_AUTHORIZATION":
            class_info = by_class.get(class_id)
            target_course = by_course.get(target_course_id)
            if not class_info:
                status = "SOURCE_DRIFT_REVIEW_REQUIRED"
                reasons.append("CURRENT_CLASS_RECORD_MISSING")
            elif _norm(class_info.get("school_id")) != school_id:
                status = "SOURCE_DRIFT_REVIEW_REQUIRED"
                reasons.append("CURRENT_CLASS_SCHOOL_DRIFT")
            else:
                try:
                    if int(class_info.get("academic_year") or 0) != year:
                        status = "SOURCE_DRIFT_REVIEW_REQUIRED"
                        reasons.append("CURRENT_CLASS_YEAR_DRIFT")
                except (TypeError, ValueError):
                    status = "SOURCE_DRIFT_REVIEW_REQUIRED"
                    reasons.append("CURRENT_CLASS_YEAR_INVALID")
            if not target_course:
                status = "TARGET_CURRICULUM_REJECTED"
                reasons.append("CURRENT_TARGET_COURSE_RECORD_MISSING")

            if status == "CLEAR_FOR_EXECUTION_AUTHORIZATION":
                try:
                    validation = validate_teacher_assignment_curriculum(
                        class_info=class_info,
                        course=target_course,
                        school_id=school_id,
                        academic_year=year,
                    )
                    current_write_policy = _norm(validation.get("write_policy"))
                    if sealed_write_policy and current_write_policy != sealed_write_policy:
                        status = "TARGET_CURRICULUM_REJECTED"
                        reasons.append("TARGET_WRITE_POLICY_DRIFT")
                except TeacherAssignmentIntegrityError as exc:
                    status = "TARGET_CURRICULUM_REJECTED"
                    reasons.append(exc.code)

        counts[status] += 1
        results.append(
            {
                "ordinal": int(entry.get("ordinal") or 0),
                "assignment_id": assignment_id,
                "school_id": school_id,
                "class_id": class_id,
                "source_course_id": source_course_id,
                "target_course_id": target_course_id,
                "sealed_write_policy": sealed_write_policy,
                "current_write_policy": current_write_policy,
                "preflight": status,
                "reasons": reasons,
                "active_collision_assignment_ids": sorted(active_collision_ids),
                "staff_id_present": bool(staff_id),
            }
        )

    results.sort(key=lambda row: int(row.get("ordinal") or 0))
    total = sum(counts.values())
    if total != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D5_RESULT_TOTAL_DRIFT")

    output: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "mantenedora_id": tenant,
        "academic_year": year,
        "sealed_plan_sha256": stored_plan_sha,
        "source_snapshot_sha256": _canonical_sha256(snapshot),
        "summary": {
            "sealed_entries": EXPECTED_ENTRIES,
            "clear_for_execution_authorization": counts["CLEAR_FOR_EXECUTION_AUTHORIZATION"],
            "active_target_already_exists": counts["ACTIVE_TARGET_ALREADY_EXISTS"],
            "source_drift_review_required": counts["SOURCE_DRIFT_REVIEW_REQUIRED"],
            "target_curriculum_rejected": counts["TARGET_CURRICULUM_REJECTED"],
            "preflight_total": total,
            "proposal_only": True,
            "production_write_authorized": False,
        },
        "topology": {
            "classification": topology_mode,
            "multi_document_transactions_available": transaction_capable,
            "required_future_execution_strategy": transaction_strategy,
            "set_name_present": bool(_norm((snapshot.get("topology") or {}).get("set_name"))),
            "logical_sessions_present": (snapshot.get("topology") or {}).get("logical_session_timeout_minutes") is not None,
            "max_wire_version": (snapshot.get("topology") or {}).get("max_wire_version"),
        },
        "results": results,
        "execution_contract": {
            "executable": False,
            "requires_separate_explicit_production_write_authorization": True,
            "failure_policy": "FAIL_CLOSED_NO_PARTIAL_GUESSING",
            "future_writer_must_recheck_this_preflight_immediately_before_write": True,
            "future_writer_strategy": transaction_strategy,
        },
        "safety": {
            "production_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "student_records_read": 0,
            "teacher_names_read": 0,
        },
    }
    output["report_sha256"] = _canonical_sha256(output)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze P0-F7.9D5 last-mile preflight offline")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(_load(args.plan), _load(args.snapshot))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "topology": report["topology"]}, ensure_ascii=False, indent=2))
    print("P0F7_9D5_LAST_MILE_PREFLIGHT=PASS")
    print(f"REPORT={args.json}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")
    print("REMEDIATION_EXECUTED=NO")


if __name__ == "__main__":
    main()
