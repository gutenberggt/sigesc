"""P0-F7.9C — validate counts-only network inventory offline.

No database, network, Docker or remote execution is used. The script validates
that the production inventory is chained to the local P0-F7.9A snapshot and
selects the safest next collection strategy from conservative size thresholds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SOURCE_PHASE = "P0F7.9A-CURRICULAR-ALLOCATION-FORENSIC-SNAPSHOT-2026"
INVENTORY_PHASE = "P0F7.9C-NETWORK-CURRICULAR-INVENTORY-2026"
INVENTORY_MODE = "READ_ONLY_COUNTS_ONLY_TENANT_SCOPED"
EXPECTED_QUERY_BUDGET = 6
MAX_SINGLE_CLASSES = 300
MAX_SINGLE_ASSIGNMENTS = 1000
MAX_SINGLE_COURSES = 500
REPORT_PHASE = "P0F7.9C-INVENTORY-OFFLINE-VALIDATION-2026"


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


def validate(source: Mapping[str, Any], inventory: Mapping[str, Any]) -> dict[str, Any]:
    if source.get("phase") != SOURCE_PHASE:
        raise ValueError("P0F7_9A_SOURCE_PHASE_INVALID")
    cls = source.get("class") or {}
    tenant = _norm(cls.get("mantenedora_id"))
    year = int(cls.get("academic_year") or 0)
    if not tenant or year <= 0:
        raise ValueError("P0F7_9A_SOURCE_CONTEXT_INVALID")

    if inventory.get("phase") != INVENTORY_PHASE or inventory.get("mode") != INVENTORY_MODE:
        raise ValueError("P0F7_9C_INVENTORY_PHASE_OR_MODE_INVALID")
    if inventory.get("query_budget") != EXPECTED_QUERY_BUDGET or inventory.get("query_calls") != EXPECTED_QUERY_BUDGET:
        raise ValueError("P0F7_9C_INVENTORY_QUERY_BUDGET_INVALID")
    if _norm(inventory.get("mantenedora_id")) != tenant:
        raise ValueError("P0F7_9C_INVENTORY_TENANT_DRIFT")
    if int(inventory.get("academic_year") or 0) != year:
        raise ValueError("P0F7_9C_INVENTORY_YEAR_DRIFT")
    if _norm(inventory.get("source_p0f7_9a_snapshot_sha256")) != _canonical_sha256(source):
        raise ValueError("P0F7_9C_INVENTORY_SOURCE_CHAIN_MISMATCH")

    counts = inventory.get("counts") or {}
    required = (
        "schools",
        "classes",
        "classes_without_explicit_level",
        "teacher_assignments",
        "active_teacher_assignments",
        "courses",
    )
    normalized: dict[str, int] = {}
    for key in required:
        try:
            value = int(counts.get(key))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"P0F7_9C_COUNT_INVALID_{key.upper()}") from exc
        if value < 0:
            raise ValueError(f"P0F7_9C_COUNT_NEGATIVE_{key.upper()}")
        normalized[key] = value

    if normalized["active_teacher_assignments"] > normalized["teacher_assignments"]:
        raise ValueError("P0F7_9C_ACTIVE_ASSIGNMENTS_EXCEED_TOTAL")
    if normalized["classes_without_explicit_level"] > normalized["classes"]:
        raise ValueError("P0F7_9C_CLASSES_WITHOUT_LEVEL_EXCEED_TOTAL")

    single_ok = (
        normalized["classes"] <= MAX_SINGLE_CLASSES
        and normalized["teacher_assignments"] <= MAX_SINGLE_ASSIGNMENTS
        and normalized["courses"] <= MAX_SINGLE_COURSES
    )
    strategy = "SINGLE_BOUNDED_TENANT_SNAPSHOT" if single_ok else "PAGED_BY_SCHOOL_SNAPSHOT"

    return {
        "phase": REPORT_PHASE,
        "status": "PASS",
        "mantenedora_id": tenant,
        "academic_year": year,
        "source_snapshot_sha256": _canonical_sha256(source),
        "inventory_sha256": _canonical_sha256(inventory),
        "counts": normalized,
        "collection_strategy": strategy,
        "thresholds": {
            "max_single_classes": MAX_SINGLE_CLASSES,
            "max_single_teacher_assignments": MAX_SINGLE_ASSIGNMENTS,
            "max_single_courses": MAX_SINGLE_COURSES,
        },
        "safety": {
            "production_python_executions": 0,
            "production_backend_exec_calls": 0,
            "database_mutation": False,
            "production_writes": False,
            "student_records_read": 0,
            "enrollment_records_read": 0,
            "grade_records_read": 0,
            "attendance_records_read": 0,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate P0-F7.9C network inventory offline")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--json", dest="output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = validate(_load(args.source), _load(args.inventory))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("P0F7_9C_INVENTORY_VALIDATION=PASS")
    print(f"COLLECTION_STRATEGY={report['collection_strategy']}")
    print(f"REPORT={args.output}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")


if __name__ == "__main__":
    main()
