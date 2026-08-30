"""P0-F7.9D7.4 — offline revised last-mile preflight and CAS/rollback simulation.

Consumes the exact sealed D7.3.1 report plus one bounded production snapshot.
The analyzer itself has no database/network client and never writes production.
It validates all 23 CAS preconditions, rechecks current curriculum, simulates the
ordered forward batch, detects active tuple collisions, and simulates rollback in
reverse order.
"""
from __future__ import annotations

from collections import Counter
import argparse
import copy
import hashlib
import importlib.util
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

BUILDER_PATH = Path(__file__).with_name("build_p0f7_9d74_revised_preflight_snapshot_js.py")
_spec = importlib.util.spec_from_file_location("p0f7_9d74_builder", BUILDER_PATH)
if not _spec or not _spec.loader:
    raise RuntimeError("P0F7_9D74_BUILDER_IMPORT_FAILED")
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)

OUTPUT_PHASE = "P0F7.9D7.4-OFFLINE-REVISED-LAST-MILE-PREFLIGHT-2026"
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
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _active(row: Mapping[str, Any]) -> bool:
    return _norm(row.get("status")).casefold() in ACTIVE_STATUSES


def _year(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("P0F7_9D74_YEAR_INVALID") from exc


def _value_equal(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        try:
            return float(left) == float(right)
        except (TypeError, ValueError):
            pass
    return _norm(left) == _norm(right)


def _topology(topology: Mapping[str, Any]) -> tuple[str, str, bool]:
    set_name = _norm(topology.get("set_name"))
    msg = _norm(topology.get("msg")).casefold()
    sessions = topology.get("logical_session_timeout_minutes")
    try:
        max_wire = int(topology.get("max_wire_version"))
    except (TypeError, ValueError):
        max_wire = -1
    if msg == "isdbgrid" and sessions is not None and max_wire >= 8:
        return "SHARDED_TRANSACTION_CAPABLE", "MONGODB_MULTI_DOCUMENT_TRANSACTION_REQUIRED", True
    if set_name and sessions is not None and max_wire >= 7:
        return "REPLICA_SET_TRANSACTION_CAPABLE", "MONGODB_MULTI_DOCUMENT_TRANSACTION_REQUIRED", True
    return "STANDALONE_OR_TRANSACTION_UNAVAILABLE", "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED", False


def _tuple_key(row: Mapping[str, Any]) -> tuple[str, int, str, str, str, str]:
    return (
        _norm(row.get("mantenedora_id")),
        _year(row.get("academic_year")),
        _norm(row.get("school_id")),
        _norm(row.get("class_id")),
        _norm(row.get("staff_id")),
        _norm(row.get("course_id")),
    )


def _check_cas(row: Mapping[str, Any], expected: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field, value in expected.items():
        if field == "status" and _norm(value) == "ativo_or_active":
            if not _active(row):
                reasons.append("CAS_STATUS_NOT_ACTIVE")
        elif field == "status":
            if _norm(row.get(field)).casefold() != _norm(value).casefold():
                reasons.append("CAS_STATUS_DRIFT")
        elif not _value_equal(row.get(field), value):
            reasons.append(f"CAS_{field.upper()}_DRIFT")
    return reasons


def build_report(sealed_report: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    ctx = builder.validate_sealed_report(sealed_report)
    tenant = ctx["mantenedora_id"]
    year = ctx["academic_year"]
    operations = ctx["operations"]

    if snapshot.get("phase") != builder.OUTPUT_PHASE or snapshot.get("mode") != builder.OUTPUT_MODE:
        raise ValueError("P0F7_9D74_SNAPSHOT_INVALID")
    if _norm(snapshot.get("sealed_report_sha256")) != ctx["sealed_report_sha256"]:
        raise ValueError("P0F7_9D74_SNAPSHOT_CHAIN_MISMATCH")
    if _norm(snapshot.get("mantenedora_id")) != tenant or _year(snapshot.get("academic_year")) != year:
        raise ValueError("P0F7_9D74_SNAPSHOT_CONTEXT_DRIFT")
    if int(snapshot.get("source_operations") or 0) != builder.EXPECTED_OPERATIONS:
        raise ValueError("P0F7_9D74_SNAPSHOT_OPERATION_COUNT_DRIFT")
    if int(snapshot.get("query_budget") or 0) != builder.QUERY_BUDGET or int(snapshot.get("query_calls") or 0) != builder.QUERY_BUDGET:
        raise ValueError("P0F7_9D74_QUERY_BUDGET_INVALID")

    assignments = list(snapshot.get("teacher_assignments") or [])
    if len(assignments) != int((snapshot.get("counts") or {}).get("matching_assignments") or 0):
        raise ValueError("P0F7_9D74_ASSIGNMENT_COUNT_DRIFT")
    state: dict[str, dict[str, Any]] = {}
    for raw in assignments:
        row = dict(raw or {})
        aid = _norm(row.get("id"))
        if not aid or aid in state:
            raise ValueError("P0F7_9D74_ASSIGNMENT_ID_INVALID_OR_DUPLICATE")
        if _norm(row.get("mantenedora_id")) != tenant or _year(row.get("academic_year")) != year:
            raise ValueError("P0F7_9D74_ASSIGNMENT_CONTEXT_DRIFT")
        state[aid] = row

    by_class: dict[str, Mapping[str, Any]] = {}
    for raw in snapshot.get("classes") or []:
        row = dict(raw or {})
        cid = _norm(row.get("id"))
        if not cid or cid in by_class or _norm(row.get("mantenedora_id")) != tenant:
            raise ValueError("P0F7_9D74_CLASS_INVALID_OR_DUPLICATE")
        by_class[cid] = row

    by_course: dict[str, Mapping[str, Any]] = {}
    for raw in snapshot.get("target_courses") or []:
        row = dict(raw or {})
        cid = _norm(row.get("id"))
        if not cid or cid in by_course or _norm(row.get("mantenedora_id")) != tenant:
            raise ValueError("P0F7_9D74_COURSE_INVALID_OR_DUPLICATE")
        by_course[cid] = row

    topology_mode, strategy, transaction_capable = _topology(snapshot.get("topology") or {})
    source_ids = [_norm(op["scope"]["assignment_id"]) for op in operations]
    original = {aid: copy.deepcopy(state.get(aid)) for aid in source_ids}
    counts: Counter[str] = Counter()
    results: list[dict[str, Any]] = []
    forward_clear = True
    curricular_checks = 0

    for op in operations:
        idx = int(op["operation_index"])
        op_type = op["operation_type"]
        scope = op["scope"]
        aid = _norm(scope["assignment_id"])
        reasons: list[str] = []
        collision_ids: list[str] = []
        row = state.get(aid)
        current_write_policy = ""

        if row is None:
            reasons.append("SOURCE_ASSIGNMENT_MISSING")
        else:
            if not _norm(row.get("staff_id")):
                reasons.append("SOURCE_STAFF_ID_REQUIRED")
            for field in ("school_id", "class_id"):
                if _norm(row.get(field)) != _norm(scope.get(field)):
                    reasons.append(f"SOURCE_{field.upper()}_DRIFT")
            reasons.extend(_check_cas(row, op.get("cas_expected") or {}))

        class_info = by_class.get(_norm(scope.get("class_id")))
        if class_info is None:
            reasons.append("CURRENT_CLASS_RECORD_MISSING")
        else:
            if _norm(class_info.get("school_id")) != _norm(scope.get("school_id")):
                reasons.append("CURRENT_CLASS_SCHOOL_DRIFT")
            if _year(class_info.get("academic_year")) != year:
                reasons.append("CURRENT_CLASS_YEAR_DRIFT")

        target_course_id = _norm((op.get("set_fields") or {}).get("course_id"))
        if target_course_id:
            target_course = by_course.get(target_course_id)
            if target_course is None:
                reasons.append("CURRENT_TARGET_COURSE_RECORD_MISSING")
            elif class_info is not None:
                try:
                    validation = validate_teacher_assignment_curriculum(
                        class_info=class_info,
                        course=target_course,
                        school_id=_norm(scope.get("school_id")),
                        academic_year=year,
                    )
                    current_write_policy = _norm(validation.get("write_policy"))
                    curricular_checks += 1
                except TeacherAssignmentIntegrityError as exc:
                    reasons.append(exc.code)

        after = copy.deepcopy(row) if row is not None else None
        if after is not None and not reasons:
            after.update(op.get("set_fields") or {})
            if _active(after):
                key = _tuple_key(after)
                for other_id, other in state.items():
                    if other_id == aid or not _active(other):
                        continue
                    if _tuple_key(other) == key:
                        collision_ids.append(other_id)
                if collision_ids:
                    reasons.append("ACTIVE_DUPLICATE_TUPLE_WOULD_RESULT")

        status = "CAS_DRY_RUN_CLEAR" if not reasons else "CAS_DRY_RUN_BLOCKED"
        counts[status] += 1
        if reasons:
            forward_clear = False
        else:
            state[aid] = after  # type: ignore[assignment]

        results.append({
            "operation_index": idx,
            "operation_type": op_type,
            "assignment_id": aid,
            "preflight": status,
            "reasons": reasons,
            "active_collision_assignment_ids": sorted(collision_ids),
            "staff_id_present": bool(_norm((row or {}).get("staff_id"))),
            "current_write_policy": current_write_policy,
        })

    retire_id = _norm((sealed_report.get("pair_resolution") or {}).get("retired_assignment_id"))
    survivor_id = _norm((sealed_report.get("pair_resolution") or {}).get("survivor_assignment_id"))
    survivor_target = _norm((sealed_report.get("pair_resolution") or {}).get("shared_target_course_id"))
    postconditions_clear = False
    if forward_clear:
        retired = state.get(retire_id) or {}
        survivor = state.get(survivor_id) or {}
        postconditions_clear = (
            _norm(retired.get("status")).casefold() == "inativo"
            and _active(survivor)
            and _norm(survivor.get("course_id")) == survivor_target
            and _value_equal(survivor.get("carga_horaria_semanal"), 2)
        )

    rollback_clear = False
    if forward_clear and postconditions_clear:
        rollback_state = copy.deepcopy(state)
        rollback_clear = True
        for op in reversed(operations):
            aid = _norm(op["scope"]["assignment_id"])
            row = rollback_state.get(aid)
            if row is None:
                rollback_clear = False
                break
            for field, expected_after in (op.get("set_fields") or {}).items():
                if not _value_equal(row.get(field), expected_after):
                    rollback_clear = False
                    break
            if not rollback_clear:
                break
            row.update(op.get("rollback_set_fields") or {})
        if rollback_clear:
            for aid in source_ids:
                before = original.get(aid)
                after = rollback_state.get(aid)
                if before is None or after is None:
                    rollback_clear = False
                    break
                for field in ("status", "course_id", "carga_horaria_semanal"):
                    if not _value_equal(before.get(field), after.get(field)):
                        rollback_clear = False
                        break
                if not rollback_clear:
                    break

    all_clear = (
        counts["CAS_DRY_RUN_CLEAR"] == builder.EXPECTED_OPERATIONS
        and forward_clear
        and postconditions_clear
        and rollback_clear
    )
    report: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "mode": "LOCAL_OFFLINE_REVISED_CAS_DRY_RUN",
        "sealed_report_sha256": ctx["sealed_report_sha256"],
        "source_snapshot_sha256": _canonical_sha256(snapshot),
        "mantenedora_id": tenant,
        "academic_year": year,
        "summary": {
            "operations": builder.EXPECTED_OPERATIONS,
            "cas_dry_run_clear": counts["CAS_DRY_RUN_CLEAR"],
            "cas_dry_run_blocked": counts["CAS_DRY_RUN_BLOCKED"],
            "curricular_checks_passed": curricular_checks,
            "forward_simulation_clear": forward_clear,
            "pair_postconditions_clear": postconditions_clear,
            "rollback_simulation_clear": rollback_clear,
            "clear_for_executor_sealing": all_clear,
            "production_write_authorized": False,
            "executor_authorized": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "topology": {
            "classification": topology_mode,
            "multi_document_transactions_available": transaction_capable,
            "required_future_execution_strategy": strategy,
        },
        "results": results,
        "execution_contract": {
            "executable": False,
            "writer_implementation_present": False,
            "requires_separate_explicit_production_write_authorization": True,
            "old_23_write_authorization_reusable": False,
            "failure_policy": "FAIL_CLOSED_NO_PARTIAL_GUESSING",
            "required_future_execution_strategy": strategy,
            "required_operation_order": "SEALED_OPERATION_INDEX_ASC",
            "required_rollback_order": "REVERSE_OPERATION_ORDER",
        },
        "safety": {
            "analyzer_production_access": False,
            "snapshot_origin_read_only": True,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "student_records_read": 0,
            "teacher_names_read": 0,
            "staff_id_exposed_in_report": False,
            "hard_delete_allowed": False,
        },
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze P0-F7.9D7.4 revised last-mile snapshot offline")
    parser.add_argument("--sealed-report", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(_load(args.sealed_report), _load(args.snapshot))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "topology": report["topology"]}, ensure_ascii=False, indent=2))
    print("P0F7_9D74_REVISED_LAST_MILE_PREFLIGHT=PASS")
    print(f"REPORT_SHA256={report['report_sha256']}")
    print(f"REPORT={args.json}")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")
    print("EXECUTOR_AUTHORIZED=NO")


if __name__ == "__main__":
    main()
