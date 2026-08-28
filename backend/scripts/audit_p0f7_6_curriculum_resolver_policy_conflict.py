"""P0-F7.6 — conflito de política do Curriculum Resolver (READ-ONLY/OFFLINE).

Consome exclusivamente o relatório privado P0-F7.5 e inspeciona estaticamente
``backend/utils/curriculum_resolver.py`` para verificar se a precedência atual do
resolver pode favorecer evidência operacional antes de compatibilidade
curricular por nível/série.

A fase NÃO escolhe componente, NÃO decide carga horária, NÃO acessa MongoDB e
NÃO autoriza executor.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

PHASE_ID = "P0F7.6-CURRICULUM-RESOLVER-POLICY-CONFLICT-READ-ONLY-2026"
P0F75_PHASE = "P0F7.5-SERIES-APPLICABILITY-READ-ONLY-2026"
MANIFEST_VERSION = 1

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)
DB_CLIENT_TOKENS = ("AsyncIOMotorClient", "MongoClient", "motor.motor_asyncio", "pymongo")

STRONG_SERIES_MATCH = {
    "EXPLICIT_SERIES_FULL_MATCH",
    "PER_SERIES_MATRIX_FULL_MATCH",
}
REVIEW_SERIES_SCOPE = {
    "MATRIX_FULL_BUT_EXPLICIT_SCOPE_CONFLICT_REQUIRES_REVIEW",
    "PARTIAL_SERIES_MATCH_REQUIRES_REVIEW",
    "EXPLICIT_FULL_MATRIX_INCOMPLETE_REQUIRES_REVIEW",
    "LEVEL_ONLY_NO_SERIES_SCOPE",
    "UNKNOWN_CLASS_SERIES",
}
INCOMPATIBLE_SERIES_SCOPE = {
    "LEVEL_MISMATCH_PRECEDES_SERIES",
    "NO_SERIES_MATCH",
}


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden_mutators = [token for token in MUTATOR_TOKENS if token in source]
    forbidden_clients = [token for token in DB_CLIENT_TOKENS if token in source]
    apply_token = "--" + "apply"
    if forbidden_mutators:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED mutators={forbidden_mutators}")
    if forbidden_clients:
        raise RuntimeError(f"OFFLINE_GUARD_FAILED db_clients={forbidden_clients}")
    if apply_token in source:
        raise RuntimeError("READ_ONLY_GUARD_FAILED apply_surface")


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

    if summary.get("documented_cases") != 3 or len(cases) != 3:
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

    return {"manifest_sha256": sha, "cases": cases}


def _function_source(source: str, tree: ast.AST, name: str) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(source, node)
            if segment:
                return segment
    raise ValueError(f"RESOLVER_FUNCTION_MISSING:{name}")


def inspect_resolver_policy(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    pick_winner = _function_source(source, tree, "_pick_winner")
    load_courses = _function_source(source, tree, "_load_courses")
    resolve_curriculum = _function_source(source, tree, "resolve_curriculum")

    precedence_markers = {
        "evidence_before_class_matrix": (
            "evidence_course_ids" in resolve_curriculum
            and "class_course_ids" in resolve_curriculum
            and resolve_curriculum.find("evidence_course_ids") < resolve_curriculum.find("class_course_ids")
        ),
        "class_matrix_before_teacher_assignment": (
            "class_course_ids" in resolve_curriculum
            and "ta_course_ids" in resolve_curriculum
            and resolve_curriculum.find("class_course_ids") < resolve_curriculum.find("ta_course_ids")
        ),
        "teacher_assignment_before_fallback": (
            "ta_course_ids" in resolve_curriculum
            and "fallback_course_ids" in resolve_curriculum
            and resolve_curriculum.find("ta_course_ids") < resolve_curriculum.find("fallback_course_ids")
        ),
    }

    winner_signals = {
        "evidence_score": "evidence_score" in pick_winner,
        "active": "active" in pick_winner,
        "created_at": "created_at" in pick_winner,
        "course_id": "course_id" in pick_winner,
    }
    winner_curricular_gates = {
        "nivel_ensino": "nivel_ensino" in pick_winner,
        "grade_levels": "grade_levels" in pick_winner,
        "carga_horaria_por_serie": "carga_horaria_por_serie" in pick_winner,
        "series": "series" in pick_winner,
    }
    loaded_curricular_fields = {
        "nivel_ensino": "nivel_ensino" in load_courses,
        "grade_levels": "grade_levels" in load_courses,
        "carga_horaria_por_serie": "carga_horaria_por_serie" in load_courses,
    }

    expected_precedence_confirmed = all(precedence_markers.values())
    winner_uses_operational_signals = all(winner_signals.values())
    winner_has_level_or_series_gate = any(winner_curricular_gates.values())

    return {
        "resolver_path": str(path),
        "resolver_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "precedence_markers": precedence_markers,
        "winner_signals": winner_signals,
        "winner_curricular_gates": winner_curricular_gates,
        "loaded_curricular_fields": loaded_curricular_fields,
        "expected_precedence_confirmed": expected_precedence_confirmed,
        "winner_uses_operational_signals": winner_uses_operational_signals,
        "winner_has_level_or_series_gate": winner_has_level_or_series_gate,
        "policy_gap_candidate": bool(
            expected_precedence_confirmed
            and winner_uses_operational_signals
            and not winner_has_level_or_series_gate
        ),
    }


def classify_case(case: Mapping[str, Any]) -> dict[str, Any]:
    number = int(case.get("case_number") or 0)
    identity = _norm((case.get("identity_evidence_from_p0f7_3") or {}).get("classification"))
    source_classification = _norm((case.get("source_series_applicability") or {}).get("classification"))
    target_classification = _norm((case.get("target_series_applicability") or {}).get("classification"))

    candidate_classes: list[str] = []
    alternate_candidates: list[dict[str, Any]] = []
    for candidate in case.get("exact_level_same_name_candidates") or []:
        applicability = candidate.get("series_applicability") or {}
        classification = _norm(applicability.get("classification"))
        candidate_classes.append(classification)
        if not candidate.get("is_source") and not candidate.get("is_target"):
            course = candidate.get("course") or {}
            alternate_candidates.append({
                "course_id": course.get("course_id"),
                "nivel_ensino": course.get("nivel_ensino"),
                "workload": course.get("workload"),
                "series_classification": classification,
            })

    conflict_codes: list[str] = []
    if identity == "IDENTITY_EVIDENCE_LEANS_TARGET":
        if target_classification in INCOMPATIBLE_SERIES_SCOPE:
            conflict_codes.append("EVIDENCE_LEANS_TARGET_BUT_TARGET_CURRICULARLY_INCOMPATIBLE")
        elif target_classification in REVIEW_SERIES_SCOPE and source_classification in STRONG_SERIES_MATCH:
            conflict_codes.append("EVIDENCE_LEANS_TARGET_BUT_SOURCE_HAS_STRONGER_SERIES_SCOPE")
        elif target_classification in REVIEW_SERIES_SCOPE:
            conflict_codes.append("EVIDENCE_LEANS_TARGET_WITH_UNRESOLVED_TARGET_SERIES_SCOPE")

    if source_classification in INCOMPATIBLE_SERIES_SCOPE and target_classification in INCOMPATIBLE_SERIES_SCOPE:
        if alternate_candidates:
            conflict_codes.append("SOURCE_AND_TARGET_INCOMPATIBLE_ALTERNATE_LEVEL_CANDIDATE_EXISTS")
        else:
            conflict_codes.append("SOURCE_AND_TARGET_CURRICULARLY_INCOMPATIBLE")

    if not conflict_codes:
        conflict_codes.append("NO_POLICY_CONFLICT_DETECTED_FROM_AVAILABLE_EVIDENCE")

    return {
        "case_number": number,
        "teacher_name": (case.get("teacher") or {}).get("name"),
        "school_name": (case.get("school") or {}).get("name"),
        "class_name": (case.get("class") or {}).get("name"),
        "class_level": (case.get("class") or {}).get("explicit_level_used"),
        "class_series": case.get("class_series") or [],
        "identity_classification": identity,
        "source_series_classification": source_classification,
        "target_series_classification": target_classification,
        "alternate_candidates": alternate_candidates,
        "conflict_codes": conflict_codes,
        "automatic_course_decision": False,
        "automatic_workload_decision": False,
        "human_or_policy_decision_required": True,
    }


def collect_report(series_path: Path, resolver_path: Path) -> dict[str, Any]:
    assert_read_only()
    validated = validate_p0f75(_load_json(series_path))
    resolver = inspect_resolver_policy(resolver_path)
    cases = [classify_case(case) for case in validated["cases"]]

    counts = Counter(code for case in cases for code in case["conflict_codes"])
    meaningful_conflict_count = sum(
        count for code, count in counts.items()
        if code != "NO_POLICY_CONFLICT_DETECTED_FROM_AVAILABLE_EVIDENCE"
    )

    report = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_OFFLINE_POLICY_CONFLICT_AUDIT",
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "group_name": "Geografia",
        "source_p0f7_5_manifest_sha256": validated["manifest_sha256"],
        "resolver_policy": resolver,
        "summary": {
            "expected_cases": 3,
            "documented_cases": len(cases),
            "policy_conflict_counts": dict(sorted(counts.items())),
            "meaningful_policy_conflicts": meaningful_conflict_count,
            "resolver_policy_gap_candidate": resolver["policy_gap_candidate"],
            "requires_resolver_hardening_before_executor": bool(
                resolver["policy_gap_candidate"] and meaningful_conflict_count > 0
            ),
            "automatic_course_decisions": 0,
            "automatic_workload_decisions": 0,
            "human_or_policy_decisions_required": len(cases),
            "database_access": False,
            "database_mutation": False,
        },
        "safety": {
            "read_only": True,
            "offline": True,
            "database_access": False,
            "contains_student_identifiers": False,
            "contains_grade_values": False,
            "contains_attendance_values": False,
            "automatic_recommendation": False,
            "automatic_resolution": False,
            "database_mutation": False,
            "production_writes_executed": False,
            "not_authorization_for_executor": True,
        },
        "cases": cases,
    }
    report["manifest_sha256"] = _canonical_sha256(report)
    return report


def compact_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phase": report.get("phase"),
        "mode": report.get("mode"),
        "status": report.get("status"),
        "group_name": report.get("group_name"),
        "resolver_policy": report.get("resolver_policy"),
        "summary": report.get("summary"),
        "cases": report.get("cases"),
        "manifest_sha256": report.get("manifest_sha256"),
        "student_identifiers_printed": False,
        "database_access": False,
        "database_mutation": False,
        "executor_authorized": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F7.6 curriculum resolver policy conflict audit")
    parser.add_argument("--series", required=True, type=Path)
    parser.add_argument("--resolver", required=True, type=Path)
    parser.add_argument("--json", dest="json_path", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    assert_read_only()
    args = parse_args()
    report = collect_report(args.series, args.resolver)
    _private_write_json(args.json_path, report)
    print(json.dumps(compact_summary(report), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
