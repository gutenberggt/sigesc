"""P0-F7.5 — aplicabilidade por série READ-ONLY dos 3 casos de Geografia.

Consome o relatório privado P0-F7.4 e avalia, sem acessar MongoDB, a cobertura
das séries/etapas por ``grade_levels`` e ``carga_horaria_por_serie``.
Não escolhe componente, não decide carga e não altera dados.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata
from typing import Any, Mapping

PHASE_ID = "P0F7.5-SERIES-APPLICABILITY-READ-ONLY-2026"
P0F74_PHASE = "P0F7.4-CURRICULAR-COMPATIBILITY-READ-ONLY-2026"
MANIFEST_VERSION = 1
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


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_series(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _norm(value).casefold())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.replace("º", " ").replace("ª", " ")
    raw = re.sub(r"[^0-9a-z]+", " ", raw)
    return " ".join(raw.split())


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
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
    if _canonical_sha256(canonical) != stored:
        raise ValueError(f"{label}_SHA_MISMATCH")
    return stored


def validate_p0f74(report: Mapping[str, Any]) -> dict[str, Any]:
    sha = _verify_embedded_sha(report, "manifest_sha256", "P0F7_4")
    if report.get("phase") != P0F74_PHASE:
        raise ValueError("P0F7_4_PHASE_MISMATCH")
    if report.get("mode") != "READ_ONLY_CURRICULAR_COMPATIBILITY":
        raise ValueError("P0F7_4_MODE_MISMATCH")
    if report.get("status") != "PASS" or report.get("group_name") != "Geografia":
        raise ValueError("P0F7_4_STATUS_OR_GROUP_MISMATCH")
    summary, safety = report.get("summary") or {}, report.get("safety") or {}
    cases = report.get("cases") or []
    if summary.get("documented_cases") != 3 or len(cases) != 3:
        raise ValueError("P0F7_4_CASE_COUNT_MISMATCH")
    if summary.get("automatic_course_decisions") != 0 or summary.get("automatic_workload_decisions") != 0:
        raise ValueError("P0F7_4_AUTOMATIC_DECISION_PRESENT")
    if safety.get("read_only") is not True or safety.get("production_writes_executed") is not False:
        raise ValueError("P0F7_4_SAFETY_INVALID")
    if safety.get("not_authorization_for_executor") is not True:
        raise ValueError("P0F7_4_EXECUTOR_FLAG_INVALID")
    return {"manifest_sha256": sha, "cases": cases}


def _class_series(class_meta: Mapping[str, Any]) -> list[str]:
    values = [v for v in (class_meta.get("series") or []) if _norm(v)]
    if not values and _norm(class_meta.get("grade_level")):
        values = [class_meta.get("grade_level")]
    out, seen = [], set()
    for value in values:
        key = _norm_series(value)
        if key and key not in seen:
            seen.add(key)
            out.append(_norm(value))
    return out


def analyze_course_series(course: Mapping[str, Any], class_series: list[str], *, level_compatibility: str) -> dict[str, Any]:
    class_norm = {_norm_series(v) for v in class_series if _norm_series(v)}
    explicit_raw = [v for v in (course.get("grade_levels") or []) if _norm(v)]
    explicit_norm = {_norm_series(v) for v in explicit_raw if _norm_series(v)}
    matrix = course.get("carga_horaria_por_serie") or {}
    matrix_norm = {_norm_series(k) for k in matrix if _norm_series(k)} if isinstance(matrix, dict) else set()

    if level_compatibility not in {"EXACT_LEVEL_MATCH", "BROAD_EJA_MATCH_REQUIRES_REVIEW", "SPECIALIZED_EJA_MATCH_REQUIRES_REVIEW"}:
        classification = "LEVEL_MISMATCH_PRECEDES_SERIES"
    elif not class_norm:
        classification = "UNKNOWN_CLASS_SERIES"
    elif explicit_norm and class_norm <= explicit_norm:
        classification = "EXPLICIT_FULL_MATRIX_INCOMPLETE_REQUIRES_REVIEW" if matrix_norm and not class_norm <= matrix_norm else "EXPLICIT_SERIES_FULL_MATCH"
    elif matrix_norm and class_norm <= matrix_norm:
        classification = "MATRIX_FULL_BUT_EXPLICIT_SCOPE_CONFLICT_REQUIRES_REVIEW" if explicit_norm else "PER_SERIES_MATRIX_FULL_MATCH"
    elif explicit_norm or matrix_norm:
        classification = "PARTIAL_SERIES_MATCH_REQUIRES_REVIEW" if (class_norm & explicit_norm) or (class_norm & matrix_norm) else "NO_SERIES_MATCH"
    else:
        classification = "LEVEL_ONLY_NO_SERIES_SCOPE"

    return {
        "classification": classification,
        "class_series": class_series,
        "grade_levels": explicit_raw,
        "matrix_series": list(matrix) if isinstance(matrix, dict) else [],
        "explicit_covered_normalized": sorted(class_norm & explicit_norm),
        "matrix_covered_normalized": sorted(class_norm & matrix_norm),
        "missing_from_explicit_normalized": sorted(class_norm - explicit_norm),
        "missing_from_matrix_normalized": sorted(class_norm - matrix_norm),
        "automatic_course_decision": False,
        "automatic_workload_decision": False,
    }


def collect_report(p0f74_path: Path) -> dict[str, Any]:
    assert_read_only()
    validated = validate_p0f74(_load_json(p0f74_path))
    results = []
    source_counts, target_counts, candidate_counts = Counter(), Counter(), Counter()

    for raw_case in sorted(validated["cases"], key=lambda row: int(row.get("case_number") or 0)):
        number = int(raw_case.get("case_number") or 0)
        class_meta = raw_case.get("class") or {}
        series = _class_series(class_meta)
        if not series:
            raise ValueError(f"CASE_{number}_SERIES_MISSING")
        source, target = raw_case.get("source_course") or {}, raw_case.get("target_course") or {}
        source_level, target_level = _norm(raw_case.get("source_level_compatibility")), _norm(raw_case.get("target_level_compatibility"))
        source_analysis = analyze_course_series(source, series, level_compatibility=source_level)
        target_analysis = analyze_course_series(target, series, level_compatibility=target_level)
        source_counts[source_analysis["classification"]] += 1
        target_counts[target_analysis["classification"]] += 1
        source_id, target_id = _norm(source.get("course_id")), _norm(target.get("course_id"))
        candidate_rows = []
        for candidate in raw_case.get("exact_level_same_name_candidates") or []:
            cid = _norm(candidate.get("course_id"))
            analysis = analyze_course_series(candidate, series, level_compatibility="EXACT_LEVEL_MATCH")
            candidate_counts[analysis["classification"]] += 1
            candidate_rows.append({"course": candidate, "is_source": bool(cid and cid == source_id), "is_target": bool(cid and cid == target_id), "series_applicability": analysis})
        results.append({
            "case_number": number,
            "teacher": raw_case.get("teacher"), "school": raw_case.get("school"), "class": class_meta,
            "class_series": series, "weekly_workload_conflict": raw_case.get("weekly_workload_conflict"),
            "source_course": source, "target_course": target,
            "source_level_compatibility": source_level, "target_level_compatibility": target_level,
            "source_series_applicability": source_analysis, "target_series_applicability": target_analysis,
            "exact_level_same_name_candidates": candidate_rows,
            "identity_evidence_from_p0f7_3": raw_case.get("identity_evidence_from_p0f7_3"),
            "automatic_course_decision": False, "automatic_workload_decision": False,
            "human_or_policy_decision_required": True,
        })

    report = {
        "phase": PHASE_ID, "manifest_version": MANIFEST_VERSION, "mode": "READ_ONLY_SERIES_APPLICABILITY",
        "status": "PASS", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "group_name": "Geografia",
        "source_p0f7_4_manifest_sha256": validated["manifest_sha256"],
        "summary": {
            "expected_cases": 3, "documented_cases": len(results),
            "source_series_applicability_counts": dict(sorted(source_counts.items())),
            "target_series_applicability_counts": dict(sorted(target_counts.items())),
            "candidate_series_applicability_counts": dict(sorted(candidate_counts.items())),
            "automatic_course_decisions": 0, "automatic_workload_decisions": 0,
            "human_or_policy_decisions_required": len(results), "database_access": False, "database_mutation": False,
        },
        "safety": {
            "read_only": True, "database_access": False, "contains_student_identifiers": False,
            "contains_grade_values": False, "contains_attendance_values": False,
            "automatic_recommendation": False, "automatic_resolution": False,
            "database_mutation": False, "production_writes_executed": False,
            "not_authorization_for_executor": True,
        },
        "cases": results,
    }
    report["manifest_sha256"] = _canonical_sha256(report)
    return report


def compact_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    cases = []
    for row in report.get("cases") or []:
        candidates = []
        for candidate in row.get("exact_level_same_name_candidates") or []:
            course = candidate.get("course") or {}
            candidates.append({
                "course_id": course.get("course_id"), "nivel_ensino": course.get("nivel_ensino"), "workload": course.get("workload"),
                "is_source": candidate.get("is_source"), "is_target": candidate.get("is_target"),
                "series_classification": (candidate.get("series_applicability") or {}).get("classification"),
            })
        cases.append({
            "case_number": row.get("case_number"), "teacher_name": (row.get("teacher") or {}).get("name"),
            "school_name": (row.get("school") or {}).get("name"), "class_name": (row.get("class") or {}).get("name"),
            "class_level": (row.get("class") or {}).get("explicit_level_used"), "class_series": row.get("class_series"),
            "weekly_workload_conflict": row.get("weekly_workload_conflict"),
            "source_level_compatibility": row.get("source_level_compatibility"), "target_level_compatibility": row.get("target_level_compatibility"),
            "source_series_classification": (row.get("source_series_applicability") or {}).get("classification"),
            "target_series_classification": (row.get("target_series_applicability") or {}).get("classification"),
            "exact_level_candidates": candidates,
            "identity_classification": (row.get("identity_evidence_from_p0f7_3") or {}).get("classification"),
            "automatic_course_decision": False, "automatic_workload_decision": False,
        })
    return {
        "phase": report.get("phase"), "mode": report.get("mode"), "status": report.get("status"), "group_name": report.get("group_name"),
        "summary": report.get("summary"), "cases": cases, "manifest_sha256": report.get("manifest_sha256"),
        "student_identifiers_printed": False, "database_access": False, "database_mutation": False, "executor_authorized": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F7.5 series applicability read-only")
    parser.add_argument("--curricular", required=True, type=Path)
    parser.add_argument("--json", dest="json_path", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    assert_read_only()
    args = parse_args()
    report = collect_report(args.curricular)
    _private_write_json(args.json_path, report)
    print(json.dumps(compact_summary(report), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
