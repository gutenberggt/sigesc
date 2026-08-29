"""P0-F7.8.2 — offline snapshot reevaluation.

Consumes a sealed P0-F7.5 report plus a minimal MongoDB snapshot collected by
PowerShell. This program is intentionally database-free and MUST run outside
production. It never opens MongoDB, SSH, Docker, students, enrollments, grades
or attendance.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from utils.curriculum_resolver import (  # noqa: E402
    _curricular_fit,
    _norm_name,
    _pick_winner,
    _resolve_class_curricular_context,
    _series_tokens,
)
import utils.curriculum_resolver as curriculum_resolver_module  # noqa: E402

PHASE_ID = "P0F7.8.2-OFFLINE-SNAPSHOT-REEVALUATION-2026"
SNAPSHOT_PHASE = "P0F7.8.2-MINIMAL-MONGOSH-SNAPSHOT-2026"
P0F75_PHASE = "P0F7.5-SERIES-APPLICABILITY-READ-ONLY-2026"
MANIFEST_VERSION = 3
MAX_CASES = 3
EXPECTED_PRODUCTION_QUERY_CALLS = 9
FORBIDDEN_SNAPSHOT_KEYS = {
    "student_id", "student_name", "student_ids", "student_names",
    "students", "enrollments", "grades", "attendance",
}
MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _private_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(rendered)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


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


def validate_p0f75(report: Mapping[str, Any]) -> dict[str, Any]:
    sha = _verify_embedded_sha(report, "manifest_sha256", "P0F7_5")
    if report.get("phase") != P0F75_PHASE:
        raise ValueError("P0F7_5_PHASE_MISMATCH")
    if report.get("mode") != "READ_ONLY_SERIES_APPLICABILITY":
        raise ValueError("P0F7_5_MODE_MISMATCH")
    if report.get("status") != "PASS" or report.get("group_name") != "Geografia":
        raise ValueError("P0F7_5_STATUS_OR_GROUP_MISMATCH")

    summary = report.get("summary") or {}
    safety = report.get("safety") or {}
    cases = report.get("cases") or []
    if summary.get("documented_cases") != MAX_CASES or len(cases) != MAX_CASES:
        raise ValueError("P0F7_5_CASE_COUNT_MISMATCH")
    if summary.get("automatic_course_decisions") != 0:
        raise ValueError("P0F7_5_AUTOMATIC_COURSE_DECISION_PRESENT")
    if summary.get("automatic_workload_decisions") != 0:
        raise ValueError("P0F7_5_AUTOMATIC_WORKLOAD_DECISION_PRESENT")
    if summary.get("database_access") is not False:
        raise ValueError("P0F7_5_DATABASE_ACCESS_INVALID")
    if safety.get("read_only") is not True:
        raise ValueError("P0F7_5_READ_ONLY_INVALID")
    if safety.get("production_writes_executed") is not False:
        raise ValueError("P0F7_5_PRODUCTION_WRITES_INVALID")
    if safety.get("not_authorization_for_executor") is not True:
        raise ValueError("P0F7_5_EXECUTOR_FLAG_INVALID")

    numbers = [int(row.get("case_number") or 0) for row in cases]
    if sorted(numbers) != [1, 2, 3]:
        raise ValueError("P0F7_5_CASE_NUMBERS_INVALID")
    return {"manifest_sha256": sha, "cases": cases}


def _walk_keys(value: Any):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def validate_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if snapshot.get("phase") != SNAPSHOT_PHASE:
        raise ValueError("SNAPSHOT_PHASE_MISMATCH")
    if snapshot.get("mode") != "READ_ONLY_MINIMAL_MONGOSH":
        raise ValueError("SNAPSHOT_MODE_MISMATCH")
    if int(snapshot.get("query_budget") or 0) != EXPECTED_PRODUCTION_QUERY_CALLS:
        raise ValueError("SNAPSHOT_QUERY_BUDGET_MISMATCH")
    if int(snapshot.get("query_calls") or 0) != EXPECTED_PRODUCTION_QUERY_CALLS:
        raise ValueError("SNAPSHOT_QUERY_CALL_COUNT_MISMATCH")
    cases = snapshot.get("cases") or []
    if len(cases) != MAX_CASES:
        raise ValueError("SNAPSHOT_CASE_COUNT_MISMATCH")
    numbers = [int(row.get("case_number") or 0) for row in cases]
    if sorted(numbers) != [1, 2, 3]:
        raise ValueError("SNAPSHOT_CASE_NUMBERS_INVALID")

    forbidden = sorted(FORBIDDEN_SNAPSHOT_KEYS.intersection(set(_walk_keys(snapshot))))
    if forbidden:
        raise ValueError(f"SNAPSHOT_PRIVACY_GUARD_FAILED:{','.join(forbidden)}")

    return {
        "snapshot_sha256": _canonical_sha256(snapshot),
        "cases": {int(row["case_number"]): row for row in cases},
    }


def validate_resolver_hardening_contract() -> dict[str, Any]:
    path = Path(curriculum_resolver_module.__file__).resolve()
    source = path.read_text(encoding="utf-8")
    pick = inspect.getsource(_pick_winner)
    if "curricular_rank" not in pick or "evidence_score" not in pick:
        raise RuntimeError("P0F7_7_HARDENING_MARKERS_MISSING")
    if pick.find("curricular_rank") >= pick.find("evidence_score"):
        raise RuntimeError("P0F7_7_CURRICULAR_PRECEDENCE_NOT_CONFIRMED")

    unknown_course = _curricular_fit(
        {"grade_levels": ["8º ANO"]},
        class_level="fundamental_anos_finais",
        class_series={"ano:8"},
    )
    if unknown_course.get("rank") != 2:
        raise RuntimeError("P0F7_7_UNKNOWN_COURSE_LEVEL_NOT_REVIEW")
    if unknown_course.get("classification") != "COURSE_LEVEL_UNKNOWN_REQUIRES_REVIEW":
        raise RuntimeError("P0F7_7_UNKNOWN_COURSE_LEVEL_CLASSIFICATION_INVALID")

    mutators = [token for token in MUTATOR_TOKENS if token in source]
    if mutators:
        raise RuntimeError(f"RESOLVER_READ_ONLY_GUARD_FAILED forbidden={mutators}")

    this_source = Path(__file__).read_text(encoding="utf-8")
    forbidden_runtime = (
        "motor.", "pymongo", "AsyncIOMotorClient", "MongoClient(",
        "subprocess.", "docker exec",
    )
    found = [token for token in forbidden_runtime if token in this_source]
    if found:
        raise RuntimeError(f"OFFLINE_ANALYZER_BOUNDARY_FAILED:{found}")

    return {
        "resolver_path": str(path),
        "resolver_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "curricular_rank_precedes_evidence_score": True,
        "unknown_course_level_is_review": True,
        "resolver_mutator_surface_detected": False,
        "database_client_available_in_analyzer": False,
    }


def _expected_rank_from_p0f75(classification: str) -> int:
    if classification in {"EXPLICIT_SERIES_FULL_MATCH", "PER_SERIES_MATRIX_FULL_MATCH"}:
        return 3
    if classification in {"LEVEL_MISMATCH_PRECEDES_SERIES", "NO_SERIES_MATCH"}:
        return 1
    return 2


def classify_pair_policy(
    source_fit: Mapping[str, Any], target_fit: Mapping[str, Any]
) -> dict[str, Any]:
    source_rank = int(source_fit.get("rank") or 0)
    target_rank = int(target_fit.get("rank") or 0)
    if source_rank == 3 and target_rank < 3:
        state, preference, review = "STRONG_CURRICULAR_PREFERENCE_SOURCE", "source", False
    elif target_rank == 3 and source_rank < 3:
        state, preference, review = "STRONG_CURRICULAR_PREFERENCE_TARGET", "target", False
    elif source_rank == target_rank == 1:
        state, preference, review = (
            "BOTH_CURRICULARLY_INCOMPATIBLE_REQUIRES_ADJUDICATION", None, True
        )
    elif source_rank == target_rank == 2:
        state, preference, review = "BOTH_REVIEW_TIER_REQUIRES_ADJUDICATION", None, True
    elif source_rank == target_rank == 3:
        state, preference, review = "BOTH_STRONG_OPERATIONAL_TIEBREAK_REMAINS_POSSIBLE", None, True
    elif source_rank > target_rank:
        state, preference, review = "SOURCE_RANKS_HIGHER_BUT_NOT_STRONG_REQUIRES_ADJUDICATION", None, True
    elif target_rank > source_rank:
        state, preference, review = "TARGET_RANKS_HIGHER_BUT_NOT_STRONG_REQUIRES_ADJUDICATION", None, True
    else:
        state, preference, review = "UNCLASSIFIED_POLICY_STATE_REQUIRES_ADJUDICATION", None, True
    return {
        "state": state,
        "source_rank": source_rank,
        "target_rank": target_rank,
        "curricular_preference": preference,
        "component_adjudication_required": review,
        "automatic_database_action": False,
    }


def _course_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "course_id": _norm(row.get("id") or row.get("course_id")),
        "name": row.get("name"),
        "nivel_ensino": row.get("nivel_ensino"),
        "grade_levels": sorted(_series_tokens(row.get("grade_levels"))),
        "matrix_series": sorted(_series_tokens(row.get("carga_horaria_por_serie"))),
        "workload": row.get("workload"),
        "active": bool(row.get("active", True)),
    }


def _assert_course_snapshot(
    number: int, label: str, expected: Mapping[str, Any], live: Mapping[str, Any]
) -> None:
    expected_snap = _course_snapshot(expected)
    live_snap = _course_snapshot(live)
    drift: list[str] = []
    for field in (
        "course_id", "name", "nivel_ensino", "grade_levels",
        "matrix_series", "workload", "active",
    ):
        left, right = expected_snap.get(field), live_snap.get(field)
        if field in {"name", "nivel_ensino"}:
            left, right = _norm_name(_norm(left)), _norm_name(_norm(right))
        if left != right:
            drift.append(field)
    if drift:
        raise RuntimeError(
            f"CASE_{number}_{label.upper()}_COURSE_SNAPSHOT_DRIFT:"
            f"{','.join(sorted(drift))}"
        )


def _validate_assignment_pair(
    *, number: int, rows: list[Mapping[str, Any]], source_course_id: str,
    target_course_id: str, expected_workload: Mapping[str, Any],
) -> dict[str, Any]:
    by_course: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_course.setdefault(_norm(row.get("course_id")), []).append(row)
    for label, cid in (("source", source_course_id), ("target", target_course_id)):
        matches = by_course.get(cid) or []
        if len(matches) != 1:
            raise RuntimeError(
                f"CASE_{number}_{label.upper()}_ACTIVE_ASSIGNMENT_COUNT_DRIFT:{len(matches)}"
            )
        expected = expected_workload.get(label)
        live = matches[0].get("carga_horaria_semanal")
        if expected != live:
            raise RuntimeError(
                f"CASE_{number}_{label.upper()}_WEEKLY_WORKLOAD_DRIFT:{expected!r}!={live!r}"
            )
    return {
        "source_active_assignments": 1,
        "target_active_assignments": 1,
        "source_weekly_workload": expected_workload.get("source"),
        "target_weekly_workload": expected_workload.get("target"),
        "workload_decision_performed": False,
    }


def build_report(p0f75: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    source = validate_p0f75(p0f75)
    snap = validate_snapshot(snapshot)
    hardening = validate_resolver_hardening_contract()
    results: list[dict[str, Any]] = []
    policy_counts: Counter[str] = Counter()
    unresolved_cases = 0
    strong_preferences = 0

    for raw_case in sorted(source["cases"], key=lambda row: int(row.get("case_number") or 0)):
        number = int(raw_case.get("case_number") or 0)
        captured = snap["cases"].get(number)
        if not captured:
            raise RuntimeError(f"CASE_{number}_SNAPSHOT_MISSING")

        class_meta = raw_case.get("class") or {}
        teacher_meta = raw_case.get("teacher") or {}
        school_meta = raw_case.get("school") or {}
        live_class = captured.get("class") or {}
        class_id = _norm(class_meta.get("class_id") or class_meta.get("id"))
        staff_id = _norm(teacher_meta.get("staff_id") or teacher_meta.get("id"))
        school_id = _norm(school_meta.get("school_id") or school_meta.get("id"))
        year = int(class_meta.get("academic_year") or 0)
        if not class_id or not staff_id or not school_id or year <= 0:
            raise ValueError(f"CASE_{number}_NATURAL_KEY_INCOMPLETE")
        if _norm(live_class.get("id")) != class_id:
            raise RuntimeError(f"CASE_{number}_CLASS_ID_DRIFT")
        tenant_id = _norm(live_class.get("mantenedora_id"))
        if not tenant_id:
            raise RuntimeError(f"CASE_{number}_TENANT_MISSING_FAIL_CLOSED")
        if _norm(live_class.get("school_id")) != school_id:
            raise RuntimeError(f"CASE_{number}_SCHOOL_DRIFT")
        if int(live_class.get("academic_year") or 0) != year:
            raise RuntimeError(f"CASE_{number}_ACADEMIC_YEAR_DRIFT")

        live_level, live_series = _resolve_class_curricular_context(live_class, {})
        expected_level = _norm(class_meta.get("explicit_level_used"))
        expected_series = _series_tokens(raw_case.get("class_series") or [])
        if _norm_name(_norm(live_level)) != _norm_name(expected_level):
            raise RuntimeError(f"CASE_{number}_CLASS_LEVEL_DRIFT")
        if live_series != expected_series:
            raise RuntimeError(f"CASE_{number}_CLASS_SERIES_DRIFT")

        source_expected = raw_case.get("source_course") or {}
        target_expected = raw_case.get("target_course") or {}
        source_id = _norm(source_expected.get("course_id"))
        target_id = _norm(target_expected.get("course_id"))
        if not source_id or not target_id:
            raise ValueError(f"CASE_{number}_COURSE_PAIR_MISSING")

        alternatives_expected: dict[str, dict[str, Any]] = {}
        for candidate in raw_case.get("exact_level_same_name_candidates") or []:
            if candidate.get("is_source") or candidate.get("is_target"):
                continue
            course = candidate.get("course") or {}
            cid = _norm(course.get("course_id"))
            if cid:
                alternatives_expected[cid] = course

        live_courses = {
            _norm(row.get("id")): row for row in (captured.get("courses") or []) if _norm(row.get("id"))
        }
        tracked_ids = sorted({source_id, target_id, *alternatives_expected.keys()})
        missing = [cid for cid in tracked_ids if cid not in live_courses]
        extra = [cid for cid in live_courses if cid not in tracked_ids]
        if missing:
            raise RuntimeError(f"CASE_{number}_TRACKED_COURSE_MISSING:{','.join(missing)}")
        if extra:
            raise RuntimeError(f"CASE_{number}_UNREQUESTED_COURSE_PRESENT:{','.join(sorted(extra))}")

        _assert_course_snapshot(number, "source", source_expected, live_courses[source_id])
        _assert_course_snapshot(number, "target", target_expected, live_courses[target_id])
        for cid, expected_course in alternatives_expected.items():
            _assert_course_snapshot(number, "alternative", expected_course, live_courses[cid])

        assignment_state = _validate_assignment_pair(
            number=number,
            rows=captured.get("assignments") or [],
            source_course_id=source_id,
            target_course_id=target_id,
            expected_workload=raw_case.get("weekly_workload_conflict") or {},
        )

        source_fit = _curricular_fit(live_courses[source_id], class_level=live_level, class_series=live_series)
        target_fit = _curricular_fit(live_courses[target_id], class_level=live_level, class_series=live_series)
        expected_source_rank = _expected_rank_from_p0f75(
            _norm((raw_case.get("source_series_applicability") or {}).get("classification"))
        )
        expected_target_rank = _expected_rank_from_p0f75(
            _norm((raw_case.get("target_series_applicability") or {}).get("classification"))
        )
        if int(source_fit.get("rank") or 0) != expected_source_rank:
            raise RuntimeError(f"CASE_{number}_SOURCE_RANK_CHAIN_DRIFT")
        if int(target_fit.get("rank") or 0) != expected_target_rank:
            raise RuntimeError(f"CASE_{number}_TARGET_RANK_CHAIN_DRIFT")

        policy = classify_pair_policy(source_fit, target_fit)
        policy_counts[policy["state"]] += 1
        unresolved_cases += int(bool(policy["component_adjudication_required"]))
        strong_preferences += int(bool(policy["curricular_preference"]))

        alternatives = []
        for cid in sorted(alternatives_expected):
            fit = _curricular_fit(live_courses[cid], class_level=live_level, class_series=live_series)
            alternatives.append({
                "course_id": cid,
                "curricular_rank": fit.get("rank"),
                "curricular_classification": fit.get("classification"),
                "automatically_injected_into_resolver": False,
            })

        results.append({
            "case_number": number,
            "teacher_name": teacher_meta.get("name"),
            "school_name": school_meta.get("name"),
            "class_name": class_meta.get("name"),
            "class_level": live_level,
            "class_series": sorted(live_series),
            "snapshot_drift": False,
            "source": {
                "course_id": source_id,
                "curricular_rank": source_fit.get("rank"),
                "curricular_classification": source_fit.get("classification"),
            },
            "target": {
                "course_id": target_id,
                "curricular_rank": target_fit.get("rank"),
                "curricular_classification": target_fit.get("classification"),
            },
            "alternative_exact_level_candidates": alternatives,
            "pair_policy": policy,
            "assignment_snapshot": assignment_state,
            "automatic_course_mutation": False,
            "automatic_workload_decision": False,
            "executor_authorized": False,
        })

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "OFFLINE_ANALYSIS_OF_MINIMAL_PRODUCTION_SNAPSHOT",
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "group_name": "Geografia",
        "source_p0f7_5_manifest_sha256": source["manifest_sha256"],
        "snapshot_sha256": snap["snapshot_sha256"],
        "resolver_hardening_contract": hardening,
        "summary": {
            "expected_cases": MAX_CASES,
            "documented_cases": len(results),
            "snapshot_drift_cases": 0,
            "pair_policy_state_counts": dict(sorted(policy_counts.items())),
            "strong_curricular_preferences": strong_preferences,
            "component_policy_cases_requiring_adjudication": unresolved_cases,
            "production_snapshot_query_calls": EXPECTED_PRODUCTION_QUERY_CALLS,
            "production_python_executions": 0,
            "production_backend_exec_calls": 0,
            "student_records_read": 0,
            "enrollment_records_read": 0,
            "grade_records_read": 0,
            "attendance_records_read": 0,
            "automatic_course_mutations": 0,
            "automatic_workload_decisions": 0,
            "database_access_by_offline_analyzer": False,
            "database_mutation": False,
        },
        "safety": {
            "read_only": True,
            "offline_analysis": True,
            "production_collector": "mongosh_only",
            "production_backend_python_execution": False,
            "production_backend_container_exec": False,
            "allowed_production_collections": ["classes", "courses", "teacher_assignments"],
            "student_identifiers_used": False,
            "student_identifiers_exposed": False,
            "contains_grade_values": False,
            "contains_attendance_values": False,
            "automatic_database_action": False,
            "automatic_workload_resolution": False,
            "database_mutation": False,
            "production_writes_executed": False,
            "not_authorization_for_executor": True,
        },
        "cases": results,
    }
    report["manifest_sha256"] = _canonical_sha256(report)
    return report


def compact_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phase": report.get("phase"),
        "mode": report.get("mode"),
        "status": report.get("status"),
        "group_name": report.get("group_name"),
        "summary": report.get("summary"),
        "cases": report.get("cases"),
        "manifest_sha256": report.get("manifest_sha256"),
        "database_mutation": False,
        "executor_authorized": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F7.8.2 offline snapshot reevaluation")
    parser.add_argument("--series", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--json", dest="json_path", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(_load_json(args.series), _load_json(args.snapshot))
    _private_write_json(args.json_path, report)
    print(json.dumps(compact_summary(report), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
