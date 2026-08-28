"""P0-F2 — preflight READ-ONLY de consolidação de pares de courses duplicados.

Parte dos grupos nominais do P0-F e mede, sem mutação:
- candidato histórico mantido por consolidações anteriores;
- distribuição das referências entre os IDs atuais;
- sobreposição de escopos lógicos por coleção;
- documentos que já contêm ambos os IDs;
- direção hipotética source→target apenas para análise.

Nenhum curso canônico é escolhido automaticamente. Mesmo quando existe um único
``kept_id`` histórico, o resultado permanece ``REQUIRES_REVIEW`` até existir um
plano de migração com manifesto, backup, rollback, CAS e autorização humana.
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
)

load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0F2-DUPLICATE-COURSE-PAIR-PREFLIGHT-READ-ONLY-2026"
MANIFEST_VERSION = 1

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)

COURSE_FIELDS = (
    "id", "name", "nivel_ensino", "mantenedora_id", "status", "active",
    "created_at", "updated_at", "created_by",
)

REFERENCE_FIELDS = (
    "id", "mantenedora_id", "school_id", "class_id", "academic_year",
    "staff_id", "teacher_id", "student_id", "status", "deleted", "source",
    "created_by", "migration_run_id", "created_at", "updated_at",
    "date", "attendance_date", "recorded_by", "bimestre", "bimester",
    "term", "period", "assessment_id", "evaluation_id", "valid_from",
    "valid_until", "schedule_slots",
)

# Chaves de escopo conservadoras. Elas sinalizam coexistência lógica; não são
# prova de duplicata material e nunca autorizam deleção/merge automático.
SCOPE_FIELDS: dict[str, tuple[str, ...]] = {
    "teacher_assignments": ("staff_id", "class_id", "academic_year"),
    "teacher_allocations": ("staff_id", "class_id", "academic_year"),
    "teacher_class_assignments": ("teacher_id", "class_id", "school_id", "valid_from", "valid_until"),
    "class_schedules": ("class_id", "academic_year"),
    "grades": (
        "student_id", "class_id", "academic_year", "bimestre", "bimester",
        "term", "period", "assessment_id", "evaluation_id",
    ),
    "attendance": ("class_id", "academic_year", "date", "attendance_date"),
    "content_entries": ("teacher_id", "class_id", "academic_year", "date"),
    "learning_objects": ("recorded_by", "class_id", "academic_year", "date"),
    "student_dependencies": ("student_id", "class_id", "academic_year"),
}


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


def build_duplicate_groups(
    courses: list[Mapping[str, Any]],
) -> list[tuple[tuple[str, str, str], list[Mapping[str, Any]]]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for course in courses:
        grouped[course_identity_key(course)].append(course)
    return sorted(
        ((key, rows) for key, rows in grouped.items() if key[1] and len(rows) > 1),
        key=lambda item: item[0],
    )


def safe_course(course: Mapping[str, Any]) -> dict[str, Any]:
    return {field: course.get(field) for field in COURSE_FIELDS if field in course}


def _canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def scope_key(collection: str, row: Mapping[str, Any]) -> Optional[tuple[tuple[str, str], ...]]:
    fields = SCOPE_FIELDS.get(collection, ())
    items: list[tuple[str, str]] = []
    for field in fields:
        value = _norm(row.get(field))
        if value:
            items.append((field, value))
    # Exige pelo menos um identificador estrutural além de ano/período solto.
    strong = {"staff_id", "teacher_id", "student_id", "class_id"}
    if not any(field in strong for field, _value in items):
        return None
    return tuple(items)


def historical_kept_candidates(
    history: list[Mapping[str, Any]],
    group_ids: set[str],
) -> tuple[list[str], list[dict[str, str]]]:
    candidates: set[str] = set()
    edges: set[tuple[str, str]] = set()
    for row in history:
        consolidated = ((row.get("extra_data") or {}).get("consolidated") or [])
        for entry in consolidated:
            if not isinstance(entry, Mapping):
                continue
            kept = _norm(entry.get("kept_id"))
            removed_ids = [_norm(x) for x in (entry.get("removed_ids") or [])]
            if kept in group_ids:
                candidates.add(kept)
            for removed in removed_ids:
                if removed and kept and (removed in group_ids or kept in group_ids):
                    edges.add((removed, kept))
    return sorted(candidates), [
        {"removed_id": removed, "kept_id": kept}
        for removed, kept in sorted(edges)
    ]


def classify_pair(*, kept_candidates: list[str], scope_overlap_signals: int) -> str:
    if len(kept_candidates) != 1:
        return "NO_UNIQUE_HISTORICAL_KEPT_BLOCKED"
    if scope_overlap_signals > 0:
        return "HISTORICAL_KEPT_WITH_SCOPE_OVERLAP_REQUIRES_REVIEW"
    return "HISTORICAL_KEPT_NO_SCOPE_OVERLAP_REQUIRES_REVIEW"


async def _load_course_audit_history(
    db: Any,
    course_ids: list[str],
    limit: int,
) -> list[dict[str, Any]]:
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
        "timestamp": 1,
        "timestamp_utc": 1,
        "old_value": 1,
        "new_value": 1,
        "extra_data.consolidated": 1,
    }
    return await db.audit_logs.find(query, projection).sort("timestamp", -1).to_list(limit)


async def collect_report(
    db: Any,
    *,
    academic_year: int,
    mantenedora_id: Optional[str] = None,
    audit_history_limit: int = 200,
    overlap_examples_limit: int = 20,
) -> dict[str, Any]:
    course_query: dict[str, Any] = {}
    if mantenedora_id:
        course_query["mantenedora_id"] = mantenedora_id

    projection = {"_id": 0, **{field: 1 for field in COURSE_FIELDS}}
    courses = await db.courses.find(course_query, projection).to_list(50000)
    duplicate_groups = build_duplicate_groups(courses)

    all_duplicate_ids = {
        _norm(course.get("id"))
        for _key, rows in duplicate_groups
        for course in rows
        if _norm(course.get("id"))
    }

    refs_by_id_collection: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    references_audited = 0

    for spec in COURSE_REFERENCE_SPECS:
        root = spec.field.split(".", 1)[0]
        ref_projection = {"_id": 0, root: 1}
        for field in REFERENCE_FIELDS:
            ref_projection[field] = 1

        cursor = db[spec.collection].find({root: {"$exists": True}}, ref_projection)
        async for row in cursor:
            if not _same_year(row.get("academic_year"), academic_year):
                continue
            if mantenedora_id:
                doc_tenant = _norm(row.get("mantenedora_id"))
                if doc_tenant and doc_tenant != mantenedora_id:
                    continue

            ids = extract_reference_ids(row, spec.field)
            references_audited += len(ids)
            for course_id in ids:
                if course_id in all_duplicate_ids:
                    refs_by_id_collection[course_id][spec.collection].append(dict(row))

    cases: list[dict[str, Any]] = []
    classifications = Counter()

    for group_number, (identity, rows) in enumerate(duplicate_groups, 1):
        ids = sorted(_norm(row.get("id")) for row in rows if _norm(row.get("id")))
        group_set = set(ids)
        history = await _load_course_audit_history(db, ids, audit_history_limit)
        kept_candidates, merge_edges = historical_kept_candidates(history, group_set)

        canonical_candidate = kept_candidates[0] if len(kept_candidates) == 1 else None
        hypothetical_directions = [
            {"source_id": course_id, "target_id": canonical_candidate}
            for course_id in ids
            if canonical_candidate and course_id != canonical_candidate
        ]

        collection_analysis: list[dict[str, Any]] = []
        scope_overlap_total = 0
        shared_document_total = 0

        for spec in COURSE_REFERENCE_SPECS:
            collection = spec.collection
            per_id_rows = {
                course_id: refs_by_id_collection[course_id].get(collection, [])
                for course_id in ids
            }
            if not any(per_id_rows.values()):
                continue

            scopes_by_id: dict[str, set[tuple[tuple[str, str], ...]]] = {}
            doc_ids_by_id: dict[str, set[str]] = {}
            for course_id, ref_rows in per_id_rows.items():
                scopes_by_id[course_id] = {
                    key
                    for row in ref_rows
                    if (key := scope_key(collection, row)) is not None
                }
                doc_ids_by_id[course_id] = {
                    _norm(row.get("id")) for row in ref_rows if _norm(row.get("id"))
                }

            shared_scopes: set[tuple[tuple[str, str], ...]] = set()
            shared_docs: set[str] = set()
            if len(ids) == 2:
                shared_scopes = scopes_by_id[ids[0]] & scopes_by_id[ids[1]]
                shared_docs = doc_ids_by_id[ids[0]] & doc_ids_by_id[ids[1]]
            else:
                nonempty_scope_sets = [value for value in scopes_by_id.values() if value]
                nonempty_doc_sets = [value for value in doc_ids_by_id.values() if value]
                if len(nonempty_scope_sets) >= 2:
                    shared_scopes = set.intersection(*nonempty_scope_sets)
                if len(nonempty_doc_sets) >= 2:
                    shared_docs = set.intersection(*nonempty_doc_sets)

            scope_overlap_total += len(shared_scopes)
            shared_document_total += len(shared_docs)

            collection_analysis.append(
                {
                    "collection": collection,
                    "reference_counts": {
                        course_id: len(per_id_rows[course_id]) for course_id in ids
                    },
                    "scope_fields": list(SCOPE_FIELDS.get(collection, ())),
                    "scope_counts": {
                        course_id: len(scopes_by_id[course_id]) for course_id in ids
                    },
                    "shared_scope_count": len(shared_scopes),
                    "shared_scope_examples": [
                        dict(scope) for scope in sorted(shared_scopes)[:overlap_examples_limit]
                    ],
                    "shared_document_count": len(shared_docs),
                    "shared_document_examples": sorted(shared_docs)[:overlap_examples_limit],
                    "signal_semantics": (
                        "shared scope/document is a collision-risk signal only; "
                        "it is not proof that records are semantically identical"
                    ),
                }
            )

        classification = classify_pair(
            kept_candidates=kept_candidates,
            scope_overlap_signals=scope_overlap_total + shared_document_total,
        )
        classifications[classification] += 1

        cases.append(
            {
                "group_number": group_number,
                "identity": {
                    "mantenedora_id": identity[0] or None,
                    "name_casefold": identity[1],
                    "nivel_ensino_casefold": identity[2],
                    "display_name": rows[0].get("name"),
                    "display_nivel_ensino": rows[0].get("nivel_ensino"),
                },
                "course_ids": ids,
                "courses": [safe_course(row) for row in sorted(rows, key=lambda x: _norm(x.get("id")))],
                "audit_history_count": len(history),
                "merge_history_edges": merge_edges,
                "historical_kept_candidates": kept_candidates,
                "historical_canonical_candidate": canonical_candidate,
                "hypothetical_directions": hypothetical_directions,
                "collection_analysis": collection_analysis,
                "scope_overlap_signals": scope_overlap_total,
                "shared_document_signals": shared_document_total,
                "forensic_classification": classification,
                "automatic_canonical_choice": False,
                "automatic_remap": False,
                "database_mutation": False,
            }
        )

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_PREFLIGHT",
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
            "unique_historical_kept_groups": sum(
                1 for case in cases if len(case["historical_kept_candidates"]) == 1
            ),
            "scope_overlap_signals": sum(case["scope_overlap_signals"] for case in cases),
            "shared_document_signals": sum(case["shared_document_signals"] for case in cases),
            "classification_counts": dict(sorted(classifications.items())),
            "database_mutation": False,
        },
        "cases": cases,
        "safety": {
            "historical_kept_is_evidence_not_authorization": True,
            "scope_overlap_is_risk_signal_not_duplicate_proof": True,
            "automatic_canonical_choice": False,
            "automatic_remap": False,
            "automatic_course_creation": False,
            "automatic_delete": False,
        },
    }
    report["manifest_sha256"] = _canonical_json_sha256(report)
    return report


def compact_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phase": report.get("phase"),
        "mode": report.get("mode"),
        "status": report.get("status"),
        "summary": report.get("summary"),
        "cases": [
            {
                "group_number": case.get("group_number"),
                "name": (case.get("identity") or {}).get("display_name"),
                "course_ids": case.get("course_ids"),
                "historical_canonical_candidate": case.get("historical_canonical_candidate"),
                "hypothetical_directions": case.get("hypothetical_directions"),
                "scope_overlap_signals": case.get("scope_overlap_signals"),
                "shared_document_signals": case.get("shared_document_signals"),
                "forensic_classification": case.get("forensic_classification"),
                "collections": [
                    {
                        "collection": item.get("collection"),
                        "reference_counts": item.get("reference_counts"),
                        "shared_scope_count": item.get("shared_scope_count"),
                        "shared_document_count": item.get("shared_document_count"),
                    }
                    for item in case.get("collection_analysis") or []
                ],
            }
            for case in report.get("cases") or []
        ],
        "manifest_sha256": report.get("manifest_sha256"),
        "database_mutation": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F2 duplicate course pair read-only preflight")
    parser.add_argument("--academic-year", required=True, type=int)
    parser.add_argument("--mantenedora-id")
    parser.add_argument("--audit-history-limit", type=int, default=200)
    parser.add_argument("--overlap-examples-limit", type=int, default=20)
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
            overlap_examples_limit=args.overlap_examples_limit,
        )
    finally:
        client.close()

    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
        print(json.dumps(compact_summary(report), ensure_ascii=False, indent=2, default=str))
    else:
        print(rendered)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
