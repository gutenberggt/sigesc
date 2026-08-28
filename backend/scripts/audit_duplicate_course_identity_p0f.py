"""P0-F — auditoria forense READ-ONLY de identidades duplicadas em courses.

Reproduz exatamente a identidade nominal usada pelo P0 Global:
``(mantenedora_id, name.casefold(), nivel_ensino.casefold())``.

O auditor não escolhe curso canônico, não remapeia referências, não exclui,
não arquiva e não cria componentes. Para cada grupo duplicado, descreve os
``course_ids`` atuais, referências registradas na SSoT de integridade, contexto
de turma/escola e histórico de auditoria disponível.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from services.course_reference_integrity import (  # noqa: E402
    COURSE_REFERENCE_SPECS,
    extract_reference_ids,
    reference_projection,
)

load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0F-DUPLICATE-COURSE-IDENTITY-FORENSIC-READ-ONLY-2026"
MANIFEST_VERSION = 1

MUTATOR_TOKENS = (
    ".insert_one(",
    ".insert_many(",
    ".update_one(",
    ".update_many(",
    ".replace_one(",
    ".delete_one(",
    ".delete_many(",
    ".bulk_write(",
    ".find_one_and_update(",
    ".find_one_and_delete(",
    ".find_one_and_replace(",
)

SAFE_CONTEXT_FIELDS = (
    "id",
    "mantenedora_id",
    "school_id",
    "class_id",
    "academic_year",
    "staff_id",
    "teacher_id",
    "student_id",
    "status",
    "deleted",
    "source",
    "created_by",
    "migration_run_id",
    "created_at",
    "updated_at",
)

COURSE_SAFE_FIELDS = (
    "id",
    "name",
    "nivel_ensino",
    "mantenedora_id",
    "status",
    "active",
    "created_at",
    "updated_at",
    "created_by",
)


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line
        for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _same_year(value: Any, year: int) -> bool:
    if value in (None, ""):
        return True
    try:
        return int(value) == int(year)
    except (TypeError, ValueError):
        return False


def course_identity_key(course: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _norm(course.get("mantenedora_id")),
        _norm(course.get("name")).casefold(),
        _norm(course.get("nivel_ensino")).casefold(),
    )


def build_duplicate_groups(courses: list[Mapping[str, Any]]) -> list[tuple[tuple[str, str, str], list[Mapping[str, Any]]]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for course in courses:
        grouped[course_identity_key(course)].append(course)
    return sorted(
        (
            (key, rows)
            for key, rows in grouped.items()
            if key[1] and len(rows) > 1
        ),
        key=lambda item: item[0],
    )


def safe_context(row: Mapping[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in SAFE_CONTEXT_FIELDS if field in row}


def safe_course(course: Mapping[str, Any]) -> dict[str, Any]:
    return {field: course.get(field) for field in COURSE_SAFE_FIELDS if field in course}


def _canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def classify_reference_distribution(counts: Mapping[str, int], *, history_found: bool) -> str:
    referenced = sum(1 for value in counts.values() if int(value or 0) > 0)
    total_refs = sum(int(value or 0) for value in counts.values())
    if history_found:
        return "AUDIT_HISTORY_FOUND_REQUIRES_REVIEW"
    if total_refs == 0:
        return "NO_REGISTERED_REFERENCES_REQUIRES_REVIEW"
    if referenced == 1:
        return "ONE_REFERENCED_ID_OTHERS_UNUSED_REQUIRES_REVIEW"
    return "MULTIPLE_REFERENCED_IDS_REQUIRES_REVIEW"


async def _load_course_audit_history(db: Any, course_ids: list[str], limit: int) -> list[dict[str, Any]]:
    if not course_ids:
        return []
    query = {
        "collection": "courses",
        "$or": [
            {"document_id": {"$in": course_ids}},
            {"old_value.id": {"$in": course_ids}},
            {"new_value.id": {"$in": course_ids}},
            {"extra_data.consolidated.removed_ids": {"$in": course_ids}},
            {"extra_data.consolidated.kept_id": {"$in": course_ids}},
        ],
    }
    projection = {
        "_id": 0,
        "action": 1,
        "collection": 1,
        "document_id": 1,
        "description": 1,
        "user_id": 1,
        "user_email": 1,
        "timestamp": 1,
        "timestamp_utc": 1,
        "old_value": 1,
        "new_value": 1,
        "extra_data.consolidated": 1,
    }
    rows = await db.audit_logs.find(query, projection).sort("timestamp", -1).to_list(limit)
    return rows


def _extract_merge_edges(history: list[Mapping[str, Any]], group_ids: set[str]) -> list[dict[str, Any]]:
    edges: set[tuple[str, str]] = set()
    for row in history:
        consolidated = ((row.get("extra_data") or {}).get("consolidated") or [])
        for entry in consolidated:
            if not isinstance(entry, Mapping):
                continue
            kept = _norm(entry.get("kept_id"))
            for removed in entry.get("removed_ids") or []:
                removed_id = _norm(removed)
                if removed_id in group_ids or kept in group_ids:
                    if removed_id and kept:
                        edges.add((removed_id, kept))
    return [
        {"removed_id": removed, "kept_id": kept}
        for removed, kept in sorted(edges)
    ]


async def collect_report(
    db: Any,
    *,
    academic_year: int,
    mantenedora_id: Optional[str] = None,
    audit_history_limit: int = 200,
    examples_per_course: int = 20,
) -> dict[str, Any]:
    course_query: dict[str, Any] = {}
    if mantenedora_id:
        course_query["mantenedora_id"] = mantenedora_id

    projection = {"_id": 0, **{field: 1 for field in COURSE_SAFE_FIELDS}}
    courses = await db.courses.find(course_query, projection).to_list(50000)
    duplicate_groups = build_duplicate_groups(courses)

    schools_query: dict[str, Any] = {}
    if mantenedora_id:
        schools_query["mantenedora_id"] = mantenedora_id
    schools = await db.schools.find(
        schools_query,
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    ).to_list(10000)
    school_by_id = {_norm(row.get("id")): row for row in schools if _norm(row.get("id"))}

    classes_query: dict[str, Any] = {"academic_year": {"$in": [academic_year, str(academic_year)]}}
    classes = await db.classes.find(
        classes_query,
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1, "mantenedora_id": 1},
    ).to_list(30000)
    class_by_id = {_norm(row.get("id")): row for row in classes if _norm(row.get("id"))}

    duplicate_ids = {
        _norm(course.get("id"))
        for _key, rows in duplicate_groups
        for course in rows
        if _norm(course.get("id"))
    }

    references_by_course: dict[str, list[dict[str, Any]]] = defaultdict(list)
    references_audited = 0

    for spec in COURSE_REFERENCE_SPECS:
        root = spec.field.split(".", 1)[0]
        ref_projection = reference_projection(spec)
        for field in SAFE_CONTEXT_FIELDS:
            ref_projection[field] = 1

        cursor = db[spec.collection].find({root: {"$exists": True}}, ref_projection)
        async for row in cursor:
            if not _same_year(row.get("academic_year"), academic_year):
                continue

            class_id = _norm(row.get("class_id"))
            klass = class_by_id.get(class_id) if class_id else None
            if class_id and not klass and row.get("academic_year") in (None, ""):
                continue

            if mantenedora_id:
                doc_tenant = _norm(row.get("mantenedora_id"))
                if not doc_tenant and klass:
                    doc_tenant = _norm(klass.get("mantenedora_id"))
                    if not doc_tenant:
                        school = school_by_id.get(_norm(klass.get("school_id")))
                        doc_tenant = _norm((school or {}).get("mantenedora_id"))
                if doc_tenant and doc_tenant != mantenedora_id:
                    continue

            for course_id in extract_reference_ids(row, spec.field):
                references_audited += 1
                if course_id not in duplicate_ids:
                    continue

                school = None
                if klass:
                    school = school_by_id.get(_norm(klass.get("school_id")))
                if not school and _norm(row.get("school_id")):
                    school = school_by_id.get(_norm(row.get("school_id")))

                references_by_course[course_id].append(
                    {
                        "collection": spec.collection,
                        "field": spec.field,
                        "label": spec.label,
                        "document": safe_context(row),
                        "class": {
                            "id": klass.get("id"),
                            "name": klass.get("name"),
                            "school_id": klass.get("school_id"),
                            "academic_year": klass.get("academic_year"),
                            "mantenedora_id": klass.get("mantenedora_id"),
                        }
                        if klass
                        else None,
                        "school": {
                            "id": school.get("id"),
                            "name": school.get("name"),
                            "mantenedora_id": school.get("mantenedora_id"),
                        }
                        if school
                        else None,
                    }
                )

    cases: list[dict[str, Any]] = []
    classification_counts = Counter()

    for index, (key, rows) in enumerate(duplicate_groups, 1):
        ids = sorted(_norm(row.get("id")) for row in rows if _norm(row.get("id")))
        per_course: list[dict[str, Any]] = []
        ref_count_by_id: dict[str, int] = {}

        for course in sorted(rows, key=lambda row: _norm(row.get("id"))):
            course_id = _norm(course.get("id"))
            refs = references_by_course.get(course_id, [])
            ref_count_by_id[course_id] = len(refs)
            by_collection = Counter(ref["collection"] for ref in refs)
            per_course.append(
                {
                    "course": safe_course(course),
                    "reference_count": len(refs),
                    "reference_counts_by_collection": dict(sorted(by_collection.items())),
                    "reference_examples": refs[:examples_per_course],
                }
            )

        history = await _load_course_audit_history(db, ids, audit_history_limit)
        merge_edges = _extract_merge_edges(history, set(ids))
        classification = classify_reference_distribution(
            ref_count_by_id,
            history_found=bool(history),
        )
        classification_counts[classification] += 1

        cases.append(
            {
                "group_number": index,
                "identity": {
                    "mantenedora_id": key[0] or None,
                    "name_casefold": key[1],
                    "nivel_ensino_casefold": key[2],
                    "display_name": rows[0].get("name"),
                    "display_nivel_ensino": rows[0].get("nivel_ensino"),
                },
                "course_count": len(ids),
                "course_ids": ids,
                "courses": per_course,
                "total_registered_references": sum(ref_count_by_id.values()),
                "referenced_course_ids": sorted(
                    course_id for course_id, count in ref_count_by_id.items() if count > 0
                ),
                "unreferenced_course_ids": sorted(
                    course_id for course_id, count in ref_count_by_id.items() if count == 0
                ),
                "audit_history_count": len(history),
                "merge_history_edges": merge_edges,
                "audit_history": history,
                "forensic_classification": classification,
                "automatic_canonical_choice": False,
                "automatic_remap": False,
                "automatic_delete": False,
            }
        )

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_FORENSIC",
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "academic_year": academic_year,
        "mantenedora_id": mantenedora_id,
        "identity_semantics": {
            "fields": ["mantenedora_id", "name.casefold()", "nivel_ensino.casefold()"],
            "duplicate_counter_unit": "GROUP",
        },
        "summary": {
            "courses_audited": len(courses),
            "course_references_audited": references_audited,
            "duplicate_identity_groups": len(cases),
            "duplicate_course_records": sum(case["course_count"] for case in cases),
            "classification_counts": dict(sorted(classification_counts.items())),
            "database_mutation": False,
        },
        "cases": cases,
        "safety": {
            "automatic_canonical_choice": False,
            "automatic_remap": False,
            "automatic_course_creation": False,
            "automatic_delete": False,
            "classification_semantics": "forensic classification is evidence only; it is not authorization to consolidate",
        },
    }
    report["manifest_sha256"] = _canonical_json_sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F duplicate course identity forensic auditor")
    parser.add_argument("--academic-year", required=True, type=int)
    parser.add_argument("--mantenedora-id")
    parser.add_argument("--audit-history-limit", type=int, default=200)
    parser.add_argument("--examples-per-course", type=int, default=20)
    parser.add_argument("--json", dest="json_path")
    return parser.parse_args()


async def async_main() -> int:
    assert_read_only()
    args = parse_args()
    mongo_url = os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError("MONGO_URL and DB_NAME are required")

    client = AsyncIOMotorClient(mongo_url)
    try:
        report = await collect_report(
            client[db_name],
            academic_year=args.academic_year,
            mantenedora_id=args.mantenedora_id,
            audit_history_limit=args.audit_history_limit,
            examples_per_course=args.examples_per_course,
        )
    finally:
        client.close()

    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(rendered)
    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
