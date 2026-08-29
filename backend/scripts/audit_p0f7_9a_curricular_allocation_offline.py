"""P0-F7.9A — offline forensic analysis of teacher curricular allocations.

Consumes only a sealed P0-F7.5 report and the bounded P0-F7.9A snapshot already
copied to the workstation. No database, network, Docker or remote execution is
available from this module.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from utils.curriculum_resolver import (  # noqa: E402
    _curricular_fit,
    _resolve_class_curricular_context,
)

P0F75_PHASE = "P0F7.5-SERIES-APPLICABILITY-READ-ONLY-2026"
SNAPSHOT_PHASE = "P0F7.9A-CURRICULAR-ALLOCATION-FORENSIC-SNAPSHOT-2026"
SNAPSHOT_MODE = "READ_ONLY_BOUNDED_MONGOSH_CLASS_FORENSICS"
REPORT_PHASE = "P0F7.9A-OFFLINE-CURRICULAR-ALLOCATION-FORENSICS-2026"
EXPECTED_QUERY_BUDGET = 8
TARGET_CASE = 2
ACTIVE_STATUS = {"active", "ativo"}


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


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _verify_embedded_sha(payload: Mapping[str, Any], field: str, label: str) -> str:
    stored = _norm(payload.get(field))
    if not stored:
        raise ValueError(f"{label}_SHA_MISSING")
    canonical = dict(payload)
    canonical.pop(field, None)
    actual = _canonical_sha256(canonical)
    if actual != stored:
        raise ValueError(f"{label}_SHA_MISMATCH")
    return stored


def _case2(report: Mapping[str, Any]) -> Mapping[str, Any]:
    if report.get("phase") != P0F75_PHASE or report.get("status") != "PASS":
        raise ValueError("P0F7_5_INVALID")
    cases = report.get("cases") or []
    case = next(
        (row for row in cases if int(row.get("case_number") or 0) == TARGET_CASE),
        None,
    )
    if not isinstance(case, Mapping):
        raise ValueError("P0F7_5_CASE_2_MISSING")
    return case


def _matrix_course_ids(value: Any) -> set[str]:
    out: set[str] = set()
    if value is None:
        return out
    if isinstance(value, str):
        if value.strip():
            out.add(value.strip())
        return out
    if isinstance(value, Mapping):
        for key in ("course_id", "component_id", "id"):
            candidate = _norm(value.get(key))
            if candidate:
                out.add(candidate)
        return out
    if isinstance(value, (list, tuple, set)):
        for item in value:
            out.update(_matrix_course_ids(item))
    return out


def _nested_course_ids(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"course_id", "component_id"}:
                candidate = _norm(item)
                if candidate:
                    out.add(candidate)
            else:
                out.update(_nested_course_ids(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            out.update(_nested_course_ids(item))
    return out


def _is_active(row: Mapping[str, Any]) -> bool:
    return _norm(row.get("status")).casefold() in ACTIVE_STATUS


def _fit_bucket(fit: Mapping[str, Any]) -> str:
    rank = int(fit.get("rank") or 0)
    classification = _norm(fit.get("classification"))
    if rank >= 3:
        return "COMPATIBLE"
    if rank == 2:
        return "REQUIRES_REVIEW"
    if classification == "LEVEL_MISMATCH":
        return "LEVEL_MISMATCH"
    return "INCOMPATIBLE"


def _validate_inputs(
    p0f75: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> tuple[Mapping[str, Any], str]:
    sha75 = _verify_embedded_sha(p0f75, "manifest_sha256", "P0F7_5")
    case = _case2(p0f75)

    if snapshot.get("phase") != SNAPSHOT_PHASE or snapshot.get("mode") != SNAPSHOT_MODE:
        raise ValueError("P0F7_9A_SNAPSHOT_PHASE_OR_MODE_INVALID")
    if snapshot.get("query_budget") != EXPECTED_QUERY_BUDGET:
        raise ValueError("P0F7_9A_QUERY_BUDGET_INVALID")
    if snapshot.get("query_calls") != EXPECTED_QUERY_BUDGET:
        raise ValueError("P0F7_9A_QUERY_CALLS_INVALID")
    if _norm(snapshot.get("source_p0f7_5_manifest_sha256")) != sha75:
        raise ValueError("P0F7_9A_SOURCE_CHAIN_MISMATCH")

    class_expected = case.get("class") or {}
    school_expected = case.get("school") or {}
    cls = snapshot.get("class") or {}
    expected_class_id = _norm(class_expected.get("class_id") or class_expected.get("id"))
    expected_school_id = _norm(school_expected.get("school_id") or school_expected.get("id"))
    expected_year = int(class_expected.get("academic_year") or 0)

    if _norm(cls.get("id")) != expected_class_id:
        raise ValueError("P0F7_9A_CLASS_ID_DRIFT")
    if _norm(cls.get("school_id")) != expected_school_id:
        raise ValueError("P0F7_9A_SCHOOL_ID_DRIFT")
    if int(cls.get("academic_year") or 0) != expected_year:
        raise ValueError("P0F7_9A_ACADEMIC_YEAR_DRIFT")
    if not _norm(cls.get("mantenedora_id")):
        raise ValueError("P0F7_9A_TENANT_MISSING_FAIL_CLOSED")

    for row in snapshot.get("teacher_assignments") or []:
        if _norm(row.get("mantenedora_id")) != _norm(cls.get("mantenedora_id")):
            raise ValueError("P0F7_9A_ASSIGNMENT_TENANT_DRIFT")
        if _norm(row.get("class_id")) != expected_class_id:
            raise ValueError("P0F7_9A_ASSIGNMENT_CLASS_DRIFT")
        if _norm(row.get("school_id")) != expected_school_id:
            raise ValueError("P0F7_9A_ASSIGNMENT_SCHOOL_DRIFT")

    return case, sha75


def build_report(p0f75: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    _, sha75 = _validate_inputs(p0f75, snapshot)
    cls = snapshot.get("class") or {}
    assignments = list(snapshot.get("teacher_assignments") or [])
    courses = list(snapshot.get("courses") or [])
    staff_rows = list(snapshot.get("staff") or [])
    allocations = list(snapshot.get("teacher_allocations") or [])
    dvd_rows = list(snapshot.get("teacher_class_assignments") or [])
    schedules = list(snapshot.get("class_schedules") or [])
    audit_logs = list(snapshot.get("assignment_audit_logs") or [])

    course_by_id = {_norm(row.get("id")): row for row in courses if _norm(row.get("id"))}
    staff_by_id = {_norm(row.get("id")): row for row in staff_rows if _norm(row.get("id"))}
    staff_by_user_id = {
        _norm(row.get("user_id")): _norm(row.get("id"))
        for row in staff_rows
        if _norm(row.get("user_id")) and _norm(row.get("id"))
    }

    class_level, class_series = _resolve_class_curricular_context(dict(cls), {})
    class_matrix_ids = _matrix_course_ids(cls.get("course_ids"))

    allocation_keys = {
        (_norm(row.get("staff_id")), _norm(row.get("class_id")), _norm(row.get("course_id")))
        for row in allocations
        if _norm(row.get("staff_id")) and _norm(row.get("class_id")) and _norm(row.get("course_id"))
    }
    dvd_keys: set[tuple[str, str, str]] = set()
    for row in dvd_rows:
        staff_id = staff_by_user_id.get(_norm(row.get("teacher_id")), "")
        component_id = _norm(row.get("component_id"))
        class_id = _norm(row.get("class_id"))
        if staff_id and component_id and class_id:
            dvd_keys.add((staff_id, class_id, component_id))

    schedule_course_ids: set[str] = set()
    for row in schedules:
        schedule_course_ids.update(_nested_course_ids(row))

    logs_by_document: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in audit_logs:
        doc_id = _norm(row.get("document_id"))
        if doc_id:
            logs_by_document[doc_id].append(row)

    counters: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    mismatch_staff: set[str] = set()

    for assignment in assignments:
        assignment_id = _norm(assignment.get("id"))
        staff_id = _norm(assignment.get("staff_id"))
        course_id = _norm(assignment.get("course_id"))
        course = course_by_id.get(course_id)
        staff = staff_by_id.get(staff_id) or {}
        active = _is_active(assignment)
        if active:
            counters["ACTIVE_ASSIGNMENTS"] += 1
        else:
            counters["NON_ACTIVE_ASSIGNMENTS"] += 1

        if not course:
            counters["COURSE_RECORD_MISSING_IN_TENANT_SNAPSHOT"] += 1
            bucket = "COURSE_RECORD_MISSING_IN_TENANT_SNAPSHOT"
            fit: dict[str, Any] = {}
        else:
            fit = _curricular_fit(
                dict(course),
                class_level=class_level,
                class_series=set(class_series),
            )
            bucket = _fit_bucket(fit)
            if active:
                counters[f"ACTIVE_{bucket}"] += 1
            else:
                counters[f"NON_ACTIVE_{bucket}"] += 1

        if active and bucket in {"LEVEL_MISMATCH", "INCOMPATIBLE"}:
            mismatch_staff.add(staff_id)
            if _norm((course or {}).get("nivel_ensino")).casefold() == "educacao_infantil" and _norm(class_level).casefold() == "eja_final":
                counters["ACTIVE_EDUCACAO_INFANTIL_TO_EJA_FINAL"] += 1

        key = (staff_id, _norm(assignment.get("class_id")), course_id)
        events = logs_by_document.get(assignment_id, [])
        create_events = [
            row for row in events
            if _norm(row.get("action")).casefold() in {"create", "created", "criar", "criacao", "criação"}
        ]
        in_matrix = course_id in class_matrix_ids
        if bucket in {"LEVEL_MISMATCH", "INCOMPATIBLE"}:
            if in_matrix:
                origin_signal = "MISMATCH_PRESENT_IN_CLASS_MATRIX"
            elif create_events:
                origin_signal = "MISMATCH_ASSIGNMENT_WITH_CREATE_AUDIT_EVENT"
            else:
                origin_signal = "MISMATCH_ASSIGNMENT_WITHOUT_CREATE_AUDIT_EVIDENCE"
        else:
            origin_signal = "NO_INCOMPATIBLE_ORIGIN_SIGNAL"

        records.append({
            "assignment_id": assignment_id,
            "status": assignment.get("status"),
            "is_active": active,
            "staff_id": staff_id,
            "staff_name": staff.get("nome") or staff.get("full_name") or None,
            "course_id": course_id,
            "course_name": (course or {}).get("name"),
            "course_level": (course or {}).get("nivel_ensino"),
            "class_level": class_level,
            "class_series": sorted(class_series),
            "curricular_bucket": bucket,
            "curricular_rank": fit.get("rank") if fit else None,
            "curricular_classification": fit.get("classification") if fit else None,
            "in_class_course_matrix": in_matrix,
            "same_binding_in_teacher_allocations": key in allocation_keys,
            "same_binding_in_dvd": key in dvd_keys,
            "course_present_in_class_schedule": course_id in schedule_course_ids,
            "assignment_created_at": assignment.get("created_at"),
            "assignment_updated_at": assignment.get("updated_at"),
            "assignment_audit_event_count": len(events),
            "assignment_create_audit_event_count": len(create_events),
            "origin_signal": origin_signal,
        })

    active_mismatches = [
        row for row in records
        if row["is_active"] and row["curricular_bucket"] in {"LEVEL_MISMATCH", "INCOMPATIBLE"}
    ]
    affected_names = sorted({
        row["staff_name"] or row["staff_id"]
        for row in active_mismatches
        if row["staff_name"] or row["staff_id"]
    })

    report: dict[str, Any] = {
        "phase": REPORT_PHASE,
        "mode": "OFFLINE_ANALYSIS_OF_BOUNDED_CLASS_SNAPSHOT",
        "status": "PASS",
        "investigation_state": "FINDINGS_PRESENT" if active_mismatches else "NO_ACTIVE_INCOMPATIBILITY_FOUND",
        "source_p0f7_5_manifest_sha256": sha75,
        "source_snapshot_sha256": _canonical_sha256(snapshot),
        "class": {
            "id": cls.get("id"),
            "name": cls.get("name"),
            "school_id": cls.get("school_id"),
            "academic_year": cls.get("academic_year"),
            "mantenedora_id": cls.get("mantenedora_id"),
            "class_level": class_level,
            "class_series": sorted(class_series),
            "class_course_matrix_ids": sorted(class_matrix_ids),
        },
        "summary": {
            "snapshot_query_budget": snapshot.get("query_budget"),
            "snapshot_query_calls": snapshot.get("query_calls"),
            "teacher_assignments_total": len(assignments),
            "active_assignments": counters["ACTIVE_ASSIGNMENTS"],
            "non_active_assignments": counters["NON_ACTIVE_ASSIGNMENTS"],
            "active_compatible": counters["ACTIVE_COMPATIBLE"],
            "active_requires_review": counters["ACTIVE_REQUIRES_REVIEW"],
            "active_level_mismatch": counters["ACTIVE_LEVEL_MISMATCH"],
            "active_incompatible_other": counters["ACTIVE_INCOMPATIBLE"],
            "active_educacao_infantil_to_eja_final": counters["ACTIVE_EDUCACAO_INFANTIL_TO_EJA_FINAL"],
            "affected_staff_count": len(mismatch_staff),
            "affected_staff_names": affected_names,
            "course_records_missing": counters["COURSE_RECORD_MISSING_IN_TENANT_SNAPSHOT"],
            "teacher_allocations_rows": len(allocations),
            "dvd_rows": len(dvd_rows),
            "class_schedule_rows": len(schedules),
            "assignment_audit_logs": len(audit_logs),
            "database_access_by_offline_analyzer": False,
            "database_mutation": False,
            "student_records_read": 0,
            "enrollment_records_read": 0,
            "grade_records_read": 0,
            "attendance_records_read": 0,
        },
        "active_incompatible_assignments": active_mismatches,
        "all_assignments": records,
        "safety": {
            "production_python_executions": 0,
            "production_backend_exec_calls": 0,
            "database_mutation": False,
            "production_writes_executed": False,
            "executor_authorized": False,
            "not_authorization_for_executor": True,
        },
    }
    report["manifest_sha256"] = _canonical_sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F7.9A offline curricular-allocation forensics")
    parser.add_argument("--series", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--json", dest="output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(_load_json(args.series), _load_json(args.snapshot))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("P0F7_9A_OFFLINE_ANALYSIS_DONE=YES")
    print(f"REPORT={args.output}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")


if __name__ == "__main__":
    main()
