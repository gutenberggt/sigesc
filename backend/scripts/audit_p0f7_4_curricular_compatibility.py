"""P0-F7.4 — compatibilidade curricular READ-ONLY dos 3 casos de Geografia.

Consome o relatório privado P0-F7.3 e verifica se os componentes source/target são
compatíveis com o nível explícito da turma. Também inventaria candidatos de mesmo
nome no mesmo tenant para detectar alternativas EJA/EJA Final sem expor estudantes.

NÃO decide carga horária, NÃO remapeia componente e NÃO altera o banco.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
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

PHASE_ID = "P0F7.4-CURRICULAR-COMPATIBILITY-READ-ONLY-2026"
P0F73_PHASE = "P0F7.3-TEACHER-WORKLOAD-TRIANGULATION-READ-ONLY-2026"
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


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_level(value: Any) -> str:
    return _norm(value).casefold().replace("-", "_").replace(" ", "_")


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
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
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
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


def validate_p0f73(report: Mapping[str, Any]) -> dict[str, Any]:
    sha = _verify_embedded_sha(report, "manifest_sha256", "P0F7_3")
    if report.get("phase") != P0F73_PHASE:
        raise ValueError("P0F7_3_PHASE_MISMATCH")
    if report.get("mode") != "READ_ONLY_TEACHER_WORKLOAD_TRIANGULATION":
        raise ValueError("P0F7_3_MODE_MISMATCH")
    if report.get("status") != "PASS":
        raise ValueError("P0F7_3_STATUS_NOT_PASS")
    if report.get("group_name") != "Geografia":
        raise ValueError("P0F7_3_GROUP_MISMATCH")
    summary = report.get("summary") or {}
    safety = report.get("safety") or {}
    cases = report.get("cases") or []
    if summary.get("documented_cases") != 3 or len(cases) != 3:
        raise ValueError("P0F7_3_CASE_COUNT_MISMATCH")
    if summary.get("snapshot_drift_cases") != 0:
        raise ValueError("P0F7_3_SNAPSHOT_DRIFT")
    if safety.get("read_only") is not True:
        raise ValueError("P0F7_3_NOT_READ_ONLY")
    if safety.get("production_writes_executed") is not False:
        raise ValueError("P0F7_3_WRITES_FLAG_INVALID")
    if safety.get("not_authorization_for_executor") is not True:
        raise ValueError("P0F7_3_EXECUTOR_FLAG_INVALID")
    return {"manifest_sha256": sha, "cases": cases}


def classify_level_compatibility(class_level: Any, course_level: Any) -> str:
    c = _norm_level(class_level)
    k = _norm_level(course_level)
    if not c:
        return "UNKNOWN_CLASS_LEVEL"
    if not k:
        return "UNKNOWN_COURSE_LEVEL"
    if c == k:
        return "EXACT_LEVEL_MATCH"
    if c == "eja_final" and k == "eja":
        return "BROAD_EJA_MATCH_REQUIRES_REVIEW"
    if c == "eja" and k == "eja_final":
        return "SPECIALIZED_EJA_MATCH_REQUIRES_REVIEW"
    return "LEVEL_MISMATCH"


def _explicit_class_level(class_doc: Mapping[str, Any]) -> str:
    return _norm(class_doc.get("education_level") or class_doc.get("nivel_ensino"))


def _safe_course(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "course_id": row.get("id"),
        "name": row.get("name"),
        "nivel_ensino": row.get("nivel_ensino"),
        "grade_levels": row.get("grade_levels") or [],
        "workload": row.get("workload"),
        "carga_horaria_por_serie": row.get("carga_horaria_por_serie"),
        "active": row.get("active"),
        "created_at": row.get("created_at"),
    }


async def collect_report(db: Any, *, p0f73_path: Path) -> dict[str, Any]:
    assert_read_only()
    p0f73 = _load_json(p0f73_path)
    validated = validate_p0f73(p0f73)

    results: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()
    explicit_levels: Counter[str] = Counter()

    for raw_case in sorted(validated["cases"], key=lambda row: int(row.get("case_number") or 0)):
        number = int(raw_case.get("case_number") or 0)
        class_meta = raw_case.get("class") or {}
        class_id = _norm(class_meta.get("class_id") or class_meta.get("id"))
        if not class_id:
            raise ValueError(f"CASE_{number}_CLASS_ID_MISSING")

        class_doc = await db.classes.find_one(
            {"id": class_id},
            {
                "_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1,
                "mantenedora_id": 1, "education_level": 1, "nivel_ensino": 1,
                "grade_level": 1, "series": 1, "course_ids": 1,
            },
        ) or {}
        if not class_doc:
            raise RuntimeError(f"CASE_{number}_CLASS_NOT_FOUND")
        tenant_id = _norm(class_doc.get("mantenedora_id"))
        if not tenant_id:
            raise RuntimeError(f"CASE_{number}_TENANT_MISSING_FAIL_CLOSED")

        source_master = (raw_case.get("course_master_evidence") or {}).get("source") or {}
        target_master = (raw_case.get("course_master_evidence") or {}).get("target") or {}
        source_id = _norm(source_master.get("course_id"))
        target_id = _norm(target_master.get("course_id"))
        if not source_id or not target_id:
            raise ValueError(f"CASE_{number}_COURSE_PAIR_MISSING")

        pair = await db.courses.find(
            {"id": {"$in": [source_id, target_id]}, "mantenedora_id": tenant_id},
            {
                "_id": 0, "id": 1, "name": 1, "nivel_ensino": 1,
                "grade_levels": 1, "workload": 1, "carga_horaria_por_serie": 1,
                "active": 1, "created_at": 1,
            },
        ).to_list(10)
        pair_map = {_norm(row.get("id")): row for row in pair}
        if source_id not in pair_map or target_id not in pair_map:
            raise RuntimeError(f"CASE_{number}_COURSE_PAIR_NOT_TENANT_SCOPED")

        source_course = pair_map[source_id]
        target_course = pair_map[target_id]
        class_level = _explicit_class_level(class_doc)
        explicit_levels[_norm_level(class_level) or "<missing>"] += 1

        source_compat = classify_level_compatibility(class_level, source_course.get("nivel_ensino"))
        target_compat = classify_level_compatibility(class_level, target_course.get("nivel_ensino"))
        source_counts[source_compat] += 1
        target_counts[target_compat] += 1

        same_name = await db.courses.find(
            {"mantenedora_id": tenant_id},
            {
                "_id": 0, "id": 1, "name": 1, "nivel_ensino": 1,
                "grade_levels": 1, "workload": 1, "carga_horaria_por_serie": 1,
                "active": 1, "created_at": 1,
            },
        ).to_list(5000)
        target_name = _norm(target_course.get("name")).casefold()
        same_name = [row for row in same_name if _norm(row.get("name")).casefold() == target_name]
        exact_level_candidates = [
            _safe_course(row) for row in same_name
            if classify_level_compatibility(class_level, row.get("nivel_ensino")) == "EXACT_LEVEL_MATCH"
        ]

        results.append({
            "case_number": number,
            "teacher": raw_case.get("teacher"),
            "school": raw_case.get("school"),
            "class": {
                "class_id": class_id,
                "name": class_doc.get("name"),
                "academic_year": class_doc.get("academic_year"),
                "education_level": class_doc.get("education_level"),
                "nivel_ensino": class_doc.get("nivel_ensino"),
                "grade_level": class_doc.get("grade_level"),
                "series": class_doc.get("series") or [],
                "explicit_level_used": class_level or None,
            },
            "source_course": _safe_course(source_course),
            "target_course": _safe_course(target_course),
            "source_level_compatibility": source_compat,
            "target_level_compatibility": target_compat,
            "same_name_course_candidates": [_safe_course(row) for row in same_name],
            "exact_level_same_name_candidates": exact_level_candidates,
            "identity_evidence_from_p0f7_3": raw_case.get("identity_evidence"),
            "weekly_workload_conflict": raw_case.get("weekly_workload_conflict"),
            "automatic_course_decision": False,
            "automatic_workload_decision": False,
            "human_or_policy_decision_required": True,
        })

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_CURRICULAR_COMPATIBILITY",
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "group_name": "Geografia",
        "source_p0f7_3_manifest_sha256": validated["manifest_sha256"],
        "summary": {
            "expected_cases": 3,
            "documented_cases": len(results),
            "class_explicit_level_counts": dict(sorted(explicit_levels.items())),
            "source_level_compatibility_counts": dict(sorted(source_counts.items())),
            "target_level_compatibility_counts": dict(sorted(target_counts.items())),
            "automatic_course_decisions": 0,
            "automatic_workload_decisions": 0,
            "human_or_policy_decisions_required": len(results),
            "database_mutation": False,
        },
        "safety": {
            "read_only": True,
            "contains_student_identifiers": False,
            "contains_grade_values": False,
            "contains_attendance_values": False,
            "automatic_recommendation": False,
            "automatic_resolution": False,
            "database_mutation": False,
            "production_writes_executed": False,
            "not_authorization_for_executor": True,
        },
        "cases": results,
    }
    report["manifest_sha256"] = _canonical_sha256(report)
    return report


def compact_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    cases = []
    for row in report.get("cases") or []:
        cases.append({
            "case_number": row.get("case_number"),
            "teacher_name": (row.get("teacher") or {}).get("name"),
            "school_name": (row.get("school") or {}).get("name"),
            "class": row.get("class"),
            "weekly_workload_conflict": row.get("weekly_workload_conflict"),
            "source_course": row.get("source_course"),
            "target_course": row.get("target_course"),
            "source_level_compatibility": row.get("source_level_compatibility"),
            "target_level_compatibility": row.get("target_level_compatibility"),
            "exact_level_same_name_candidates": row.get("exact_level_same_name_candidates"),
            "identity_evidence_from_p0f7_3": row.get("identity_evidence_from_p0f7_3"),
            "automatic_course_decision": False,
            "automatic_workload_decision": False,
        })
    return {
        "phase": report.get("phase"),
        "mode": report.get("mode"),
        "status": report.get("status"),
        "group_name": report.get("group_name"),
        "summary": report.get("summary"),
        "cases": cases,
        "manifest_sha256": report.get("manifest_sha256"),
        "student_identifiers_printed": False,
        "automatic_course_decision": False,
        "automatic_workload_decision": False,
        "database_mutation": False,
        "executor_authorized": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F7.4 curricular compatibility read-only")
    parser.add_argument("--triangulation", required=True, type=Path)
    parser.add_argument("--json", dest="json_path", required=True, type=Path)
    return parser.parse_args()


async def async_main() -> int:
    assert_read_only()
    args = parse_args()
    mongo_url, db_name = os.getenv("MONGO_URL"), os.getenv("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError("MONGO_URL and DB_NAME are required")
    client = AsyncIOMotorClient(mongo_url)
    try:
        report = await collect_report(client[db_name], p0f73_path=args.triangulation)
    finally:
        client.close()
    _private_write_json(args.json_path, report)
    print(json.dumps(compact_summary(report), ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
