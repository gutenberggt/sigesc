"""P0-F7.8.1 — reavaliação pós-hardening bounded e READ-ONLY.

Substitui a implementação inicial da P0-F7.8, que fazia replay do resolver por
matrícula e podia gerar carga N+1 incompatível com produção. Esta versão lê
somente os três casos selados e consulta, por caso, apenas turma, cursos e
vínculos docentes. Não acessa estudantes, matrículas, notas ou frequência.

A fase NÃO remapeia componente, NÃO escolhe 2h/3h, NÃO altera vínculos e NÃO
autoriza executor.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from utils.curriculum_resolver import (  # noqa: E402
    _curricular_fit,
    _norm_name,
    _pick_winner,
    _resolve_class_curricular_context,
    _series_tokens,
)
import utils.curriculum_resolver as curriculum_resolver_module  # noqa: E402

PHASE_ID = "P0F7.8.1-BOUNDED-POST-HARDENING-REEVALUATION-READ-ONLY-2026"
P0F75_PHASE = "P0F7.5-SERIES-APPLICABILITY-READ-ONLY-2026"
MANIFEST_VERSION = 2
ACTIVE_STATUSES = ["active", "Ativo", "ativo"]
MAX_CASES = 3
MAX_TRACKED_COURSES_PER_CASE = 4
MAX_ASSIGNMENT_ROWS_PER_CASE = 10
MAX_DATABASE_QUERY_CALLS = 9

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")
    apply_token = "--" + "apply"
    if apply_token in source:
        raise RuntimeError("READ_ONLY_GUARD_FAILED apply_surface")


def assert_resource_safety() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden_surfaces = (
        "db." + "students",
        "db." + "enrollments",
        "db." + "grades",
        "db." + "attendance",
        "resolve_" + "curriculum(",
        ".to_list(5000)",
        ".to_list(10000)",
    )
    found = [token for token in forbidden_surfaces if token in source]
    if found:
        raise RuntimeError(f"RESOURCE_SAFETY_GUARD_FAILED forbidden={found}")


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
    with path.open(encoding="utf-8") as handle:
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
    os.chmod(path, 0o600)


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

    forbidden = [token for token in MUTATOR_TOKENS if token in source]
    if forbidden:
        raise RuntimeError(f"RESOLVER_READ_ONLY_GUARD_FAILED forbidden={forbidden}")

    return {
        "resolver_path": str(path),
        "resolver_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "curricular_rank_precedes_evidence_score": True,
        "unknown_course_level_is_review": True,
        "resolver_mutator_surface_detected": False,
        "full_resolver_replay_per_student_performed": False,
    }


def _expected_rank_from_p0f75(classification: str) -> int:
    strong = {
        "EXPLICIT_SERIES_FULL_MATCH",
        "PER_SERIES_MATRIX_FULL_MATCH",
    }
    incompatible = {
        "LEVEL_MISMATCH_PRECEDES_SERIES",
        "NO_SERIES_MATCH",
    }
    if classification in strong:
        return 3
    if classification in incompatible:
        return 1
    return 2


def classify_pair_policy(
    source_fit: Mapping[str, Any], target_fit: Mapping[str, Any]
) -> dict[str, Any]:
    source_rank = int(source_fit.get("rank") or 0)
    target_rank = int(target_fit.get("rank") or 0)

    if source_rank == 3 and target_rank < 3:
        state = "STRONG_CURRICULAR_PREFERENCE_SOURCE"
        preference = "source"
        adjudication_required = False
    elif target_rank == 3 and source_rank < 3:
        state = "STRONG_CURRICULAR_PREFERENCE_TARGET"
        preference = "target"
        adjudication_required = False
    elif source_rank == target_rank == 1:
        state = "BOTH_CURRICULARLY_INCOMPATIBLE_REQUIRES_ADJUDICATION"
        preference = None
        adjudication_required = True
    elif source_rank == target_rank == 2:
        state = "BOTH_REVIEW_TIER_REQUIRES_ADJUDICATION"
        preference = None
        adjudication_required = True
    elif source_rank == target_rank == 3:
        state = "BOTH_STRONG_OPERATIONAL_TIEBREAK_REMAINS_POSSIBLE"
        preference = None
        adjudication_required = True
    elif source_rank > target_rank:
        state = "SOURCE_RANKS_HIGHER_BUT_NOT_STRONG_REQUIRES_ADJUDICATION"
        preference = None
        adjudication_required = True
    elif target_rank > source_rank:
        state = "TARGET_RANKS_HIGHER_BUT_NOT_STRONG_REQUIRES_ADJUDICATION"
        preference = None
        adjudication_required = True
    else:
        state = "UNCLASSIFIED_POLICY_STATE_REQUIRES_ADJUDICATION"
        preference = None
        adjudication_required = True

    return {
        "state": state,
        "source_rank": source_rank,
        "target_rank": target_rank,
        "curricular_preference": preference,
        "component_adjudication_required": adjudication_required,
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
    number: int,
    label: str,
    expected: Mapping[str, Any],
    live: Mapping[str, Any],
) -> None:
    expected_snap = _course_snapshot(expected)
    live_snap = _course_snapshot(live)
    drift = []
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


async def _fetch_live_courses(
    db: Any, tenant_id: str, course_ids: list[str]
) -> dict[str, dict[str, Any]]:
    if len(course_ids) > MAX_TRACKED_COURSES_PER_CASE:
        raise RuntimeError("TRACKED_COURSE_BUDGET_EXCEEDED")
    docs = await db.courses.find(
        {"id": {"$in": course_ids}, "mantenedora_id": tenant_id},
        {
            "_id": 0, "id": 1, "name": 1, "nivel_ensino": 1,
            "grade_levels": 1, "carga_horaria_por_serie": 1,
            "workload": 1, "active": 1, "created_at": 1,
            "mantenedora_id": 1,
        },
    ).to_list(MAX_TRACKED_COURSES_PER_CASE)
    return {_norm(row.get("id")): row for row in docs}


async def _validate_assignment_pair(
    db: Any,
    *,
    number: int,
    tenant_id: str,
    class_id: str,
    staff_id: str,
    school_id: str,
    academic_year: int,
    source_course_id: str,
    target_course_id: str,
    expected_workload: Mapping[str, Any],
) -> dict[str, Any]:
    rows = await db.teacher_assignments.find(
        {
            "mantenedora_id": tenant_id,
            "class_id": class_id,
            "staff_id": staff_id,
            "school_id": school_id,
            "academic_year": {"$in": [academic_year, str(academic_year)]},
            "course_id": {"$in": [source_course_id, target_course_id]},
            "status": {"$in": ACTIVE_STATUSES},
        },
        {
            "_id": 0, "id": 1, "course_id": 1,
            "carga_horaria_semanal": 1,
        },
    ).to_list(MAX_ASSIGNMENT_ROWS_PER_CASE)

    by_course: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_course.setdefault(_norm(row.get("course_id")), []).append(row)

    for label, cid in (("source", source_course_id), ("target", target_course_id)):
        matches = by_course.get(cid) or []
        if len(matches) != 1:
            raise RuntimeError(
                f"CASE_{number}_{label.upper()}_ACTIVE_ASSIGNMENT_COUNT_DRIFT:"
                f"{len(matches)}"
            )
        expected = expected_workload.get(label)
        live = matches[0].get("carga_horaria_semanal")
        if expected != live:
            raise RuntimeError(
                f"CASE_{number}_{label.upper()}_WEEKLY_WORKLOAD_DRIFT:"
                f"{expected!r}!={live!r}"
            )

    return {
        "source_active_assignments": 1,
        "target_active_assignments": 1,
        "source_weekly_workload": expected_workload.get("source"),
        "target_weekly_workload": expected_workload.get("target"),
        "workload_decision_performed": False,
    }


async def collect_report(db: Any, *, p0f75_path: Path) -> dict[str, Any]:
    assert_read_only()
    assert_resource_safety()
    validated = validate_p0f75(_load_json(p0f75_path))
    hardening = validate_resolver_hardening_contract()

    results: list[dict[str, Any]] = []
    policy_counts: Counter[str] = Counter()
    unresolved_cases = 0
    strong_preferences = 0
    query_calls = 0

    for raw_case in sorted(
        validated["cases"], key=lambda row: int(row.get("case_number") or 0)
    ):
        number = int(raw_case.get("case_number") or 0)
        class_meta = raw_case.get("class") or {}
        teacher_meta = raw_case.get("teacher") or {}
        school_meta = raw_case.get("school") or {}

        class_id = _norm(class_meta.get("class_id") or class_meta.get("id"))
        staff_id = _norm(teacher_meta.get("staff_id") or teacher_meta.get("id"))
        school_id = _norm(school_meta.get("school_id") or school_meta.get("id"))
        year = int(class_meta.get("academic_year") or 0)
        if not class_id or not staff_id or not school_id or year <= 0:
            raise ValueError(f"CASE_{number}_NATURAL_KEY_INCOMPLETE")

        live_class = await db.classes.find_one(
            {"id": class_id},
            {
                "_id": 0, "id": 1, "name": 1, "school_id": 1,
                "academic_year": 1, "mantenedora_id": 1,
                "nivel_ensino": 1, "education_level": 1,
                "grade_level": 1, "series": 1,
            },
        ) or {}
        query_calls += 1

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
        source_course_id = _norm(source_expected.get("course_id"))
        target_course_id = _norm(target_expected.get("course_id"))
        if not source_course_id or not target_course_id:
            raise ValueError(f"CASE_{number}_COURSE_PAIR_MISSING")

        expected_candidates = raw_case.get("exact_level_same_name_candidates") or []
        alternative_expected: dict[str, dict[str, Any]] = {}
        for candidate in expected_candidates:
            if candidate.get("is_source") or candidate.get("is_target"):
                continue
            course = candidate.get("course") or {}
            cid = _norm(course.get("course_id"))
            if cid:
                alternative_expected[cid] = course

        tracked_ids = sorted(
            {source_course_id, target_course_id, *alternative_expected.keys()}
        )
        live_courses = await _fetch_live_courses(db, tenant_id, tracked_ids)
        query_calls += 1
        missing = [cid for cid in tracked_ids if cid not in live_courses]
        if missing:
            raise RuntimeError(
                f"CASE_{number}_TRACKED_COURSE_MISSING:{','.join(missing)}"
            )

        _assert_course_snapshot(
            number, "source", source_expected, live_courses[source_course_id]
        )
        _assert_course_snapshot(
            number, "target", target_expected, live_courses[target_course_id]
        )
        for cid, expected_course in alternative_expected.items():
            _assert_course_snapshot(
                number, "alternative", expected_course, live_courses[cid]
            )

        assignment_state = await _validate_assignment_pair(
            db,
            number=number,
            tenant_id=tenant_id,
            class_id=class_id,
            staff_id=staff_id,
            school_id=school_id,
            academic_year=year,
            source_course_id=source_course_id,
            target_course_id=target_course_id,
            expected_workload=raw_case.get("weekly_workload_conflict") or {},
        )
        query_calls += 1

        source_fit = _curricular_fit(
            live_courses[source_course_id],
            class_level=live_level,
            class_series=live_series,
        )
        target_fit = _curricular_fit(
            live_courses[target_course_id],
            class_level=live_level,
            class_series=live_series,
        )

        expected_source_rank = _expected_rank_from_p0f75(
            _norm(
                (raw_case.get("source_series_applicability") or {}).get(
                    "classification"
                )
            )
        )
        expected_target_rank = _expected_rank_from_p0f75(
            _norm(
                (raw_case.get("target_series_applicability") or {}).get(
                    "classification"
                )
            )
        )
        if int(source_fit.get("rank") or 0) != expected_source_rank:
            raise RuntimeError(f"CASE_{number}_SOURCE_RANK_CHAIN_DRIFT")
        if int(target_fit.get("rank") or 0) != expected_target_rank:
            raise RuntimeError(f"CASE_{number}_TARGET_RANK_CHAIN_DRIFT")

        policy = classify_pair_policy(source_fit, target_fit)
        policy_counts[policy["state"]] += 1
        if policy["component_adjudication_required"]:
            unresolved_cases += 1
        if policy["curricular_preference"]:
            strong_preferences += 1

        alternatives = []
        for cid in sorted(alternative_expected):
            alt_fit = _curricular_fit(
                live_courses[cid],
                class_level=live_level,
                class_series=live_series,
            )
            alternatives.append({
                "course_id": cid,
                "curricular_rank": alt_fit.get("rank"),
                "curricular_classification": alt_fit.get("classification"),
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
                "course_id": source_course_id,
                "curricular_rank": source_fit.get("rank"),
                "curricular_classification": source_fit.get("classification"),
                "p0f7_5_series_classification": (
                    raw_case.get("source_series_applicability") or {}
                ).get("classification"),
            },
            "target": {
                "course_id": target_course_id,
                "curricular_rank": target_fit.get("rank"),
                "curricular_classification": target_fit.get("classification"),
                "p0f7_5_series_classification": (
                    raw_case.get("target_series_applicability") or {}
                ).get("classification"),
            },
            "alternative_exact_level_candidates": alternatives,
            "pair_policy": policy,
            "assignment_snapshot": assignment_state,
            "resource_safety": {
                "student_records_read": 0,
                "enrollment_records_read": 0,
                "grade_records_read": 0,
                "attendance_records_read": 0,
                "full_resolver_replays": 0,
                "database_query_calls_for_case": 3,
            },
            "automatic_course_mutation": False,
            "automatic_workload_decision": False,
            "executor_authorized": False,
        })

    if query_calls > MAX_DATABASE_QUERY_CALLS:
        raise RuntimeError(
            f"RESOURCE_QUERY_BUDGET_EXCEEDED:{query_calls}>{MAX_DATABASE_QUERY_CALLS}"
        )

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_BOUNDED_POST_HARDENING_REEVALUATION",
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "group_name": "Geografia",
        "source_p0f7_5_manifest_sha256": validated["manifest_sha256"],
        "resolver_hardening_contract": hardening,
        "summary": {
            "expected_cases": MAX_CASES,
            "documented_cases": len(results),
            "snapshot_drift_cases": 0,
            "pair_policy_state_counts": dict(sorted(policy_counts.items())),
            "strong_curricular_preferences": strong_preferences,
            "component_policy_cases_requiring_adjudication": unresolved_cases,
            "database_query_calls": query_calls,
            "database_query_call_budget": MAX_DATABASE_QUERY_CALLS,
            "full_resolver_replays": 0,
            "student_records_read": 0,
            "enrollment_records_read": 0,
            "grade_records_read": 0,
            "attendance_records_read": 0,
            "automatic_course_mutations": 0,
            "automatic_workload_decisions": 0,
            "database_access": True,
            "database_mutation": False,
        },
        "safety": {
            "read_only": True,
            "bounded_read_only": True,
            "database_access": True,
            "allowed_collections": ["classes", "courses", "teacher_assignments"],
            "student_identifiers_used": False,
            "student_identifiers_exposed": False,
            "contains_grade_values": False,
            "contains_attendance_values": False,
            "full_resolver_replay_per_student_performed": False,
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
        "source_p0f7_5_manifest_sha256": report.get(
            "source_p0f7_5_manifest_sha256"
        ),
        "resolver_hardening_contract": report.get("resolver_hardening_contract"),
        "summary": report.get("summary"),
        "cases": report.get("cases"),
        "manifest_sha256": report.get("manifest_sha256"),
        "student_identifiers_printed": False,
        "grade_values_printed": False,
        "attendance_values_printed": False,
        "database_mutation": False,
        "executor_authorized": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="P0-F7.8.1 bounded post-hardening reevaluation read-only"
    )
    parser.add_argument("--series", required=True, type=Path)
    parser.add_argument("--json", dest="json_path", required=True, type=Path)
    return parser.parse_args()


async def async_main() -> int:
    assert_read_only()
    assert_resource_safety()
    args = parse_args()
    mongo_url, db_name = os.getenv("MONGO_URL"), os.getenv("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError("MONGO_URL and DB_NAME are required")
    client = AsyncIOMotorClient(
        mongo_url,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=15000,
        maxPoolSize=2,
        minPoolSize=0,
    )
    try:
        report = await collect_report(client[db_name], p0f75_path=args.series)
    finally:
        client.close()
    _private_write_json(args.json_path, report)
    print(json.dumps(compact_summary(report), ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
