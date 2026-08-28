"""P0-F4 — dossiê READ-ONLY de proveniência dos conflitos de courses duplicados.

Parte exclusivamente dos conflitos semânticos identificados pelo P0-F3 e reúne
metadados técnicos seguros para apoiar uma futura decisão humana. Não escolhe
qual valor pedagógico vence, não remapeia, não mescla e não altera documentos.

Valores de notas, status individuais de frequência e textos pedagógicos jamais
são incluídos no manifesto P0-F4. Apenas hashes de chave, IDs técnicos, nomes de
campos conflitantes e metadados de proveniência/auditoria são preservados.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
P0F3_PATH = SCRIPT_DIR / "audit_duplicate_course_semantic_collision_p0f3.py"
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0F4-DUPLICATE-COURSE-CONFLICT-PROVENANCE-READ-ONLY-2026"
MANIFEST_VERSION = 1

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)

SAFE_METADATA_FIELDS = (
    "id", "course_id", "component_id", "class_id", "school_id", "student_id",
    "academic_year", "date", "period", "aula_numero", "staff_id", "teacher_id",
    "created_at", "updated_at", "created_by", "updated_by", "recorded_by",
    "version", "assignment_id", "source", "migration_run_id",
    "migrated_from_class_id", "migrated_from_grade_id", "migration_event_id",
    "copied_from_id", "copied_at",
)

PROVENANCE_SIGNAL_FIELDS = (
    "created_at", "updated_at", "created_by", "updated_by", "recorded_by",
    "version", "assignment_id", "source", "migration_run_id",
    "migrated_from_class_id", "migrated_from_grade_id", "migration_event_id",
    "copied_from_id", "copied_at",
)

HARD_CLASSIFICATIONS = {
    "grades": {"VALUE_CONFLICT", "MULTIPLICITY_CONFLICT"},
    "attendance": {"DATA_CONFLICT", "MULTIPLICITY_CONFLICT"},
    "learning_objects": {"PEDAGOGICAL_CONTENT_CONFLICT", "MULTIPLICITY_CONFLICT"},
    "class_schedules": {"SAME_DAY_SLOT_COLLISION", "MULTIPLICITY_CONFLICT"},
}

RESOLUTION_REQUIREMENTS = {
    "grades": "PEDAGOGICAL_GRADE_DECISION_REQUIRED",
    "attendance": "ATTENDANCE_DECISION_REQUIRED",
    "learning_objects": "PEDAGOGICAL_CONTENT_DECISION_REQUIRED",
    "class_schedules": "SCHEDULE_DECISION_REQUIRED",
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


def _canonical_sha(payload: Any) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_p0f3_module():
    spec = importlib.util.spec_from_file_location("p0f3_semantic_collision", P0F3_PATH)
    if not spec or not spec.loader:
        raise RuntimeError("P0F3_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def safe_metadata(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Retorna somente metadados explicitamente permitidos.

    A lista é allow-list proposital. Campos de payload pedagógico como b1..b4,
    records, content, observations e methodology não podem vazar para o P0-F4.
    """
    return {
        field: doc.get(field)
        for field in SAFE_METADATA_FIELDS
        if field in doc and _present(doc.get(field))
    }


def provenance_signal_count(metadata: Mapping[str, Any]) -> int:
    return sum(1 for field in PROVENANCE_SIGNAL_FIELDS if _present(metadata.get(field)))


def classify_provenance(
    source_metadata: list[Mapping[str, Any]],
    target_metadata: list[Mapping[str, Any]],
    source_audit_events: int,
    target_audit_events: int,
) -> str:
    source_signal = any(provenance_signal_count(row) > 0 for row in source_metadata)
    target_signal = any(provenance_signal_count(row) > 0 for row in target_metadata)
    if source_signal and target_signal and source_audit_events > 0 and target_audit_events > 0:
        return "BILATERAL_PROVENANCE_WITH_AUDIT"
    if source_signal and target_signal:
        return "BILATERAL_PROVENANCE_NO_COMPLETE_AUDIT"
    if source_signal or target_signal:
        return "PARTIAL_PROVENANCE"
    return "SPARSE_PROVENANCE"


def resolution_requirement(collection: str) -> str:
    return RESOLUTION_REQUIREMENTS.get(collection, "UNSUPPORTED_CONFLICT_TYPE_BLOCKED")


def _actor_id(row: Mapping[str, Any]) -> str | None:
    if row.get("user_id"):
        return str(row.get("user_id"))
    user = row.get("user") or {}
    if isinstance(user, Mapping) and user.get("id"):
        return str(user.get("id"))
    return None


def summarize_audit(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    actions = Counter(str(row.get("action") or "<unknown>") for row in rows)
    actors = {_actor_id(row) for row in rows}
    actors.discard(None)
    timestamps = [
        row.get("timestamp_utc") or row.get("timestamp")
        for row in rows
        if row.get("timestamp_utc") or row.get("timestamp")
    ]
    return {
        "event_count": len(rows),
        "action_counts": dict(sorted(actions.items())),
        "actor_count": len(actors),
        "first_event_at": min((str(v) for v in timestamps), default=None),
        "last_event_at": max((str(v) for v in timestamps), default=None),
    }


async def _load_documents(db: Any, collection: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    projection = {"_id": 0, **{field: 1 for field in SAFE_METADATA_FIELDS}}
    rows = await db[collection].find({"id": {"$in": ids}}, projection).to_list(len(ids) + 10)
    return {str(row.get("id")): row for row in rows if row.get("id")}


async def _load_audit_by_document(
    db: Any,
    collection: str,
    ids: list[str],
    per_document_limit: int,
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {doc_id: [] for doc_id in ids}
    if not ids:
        return result
    projection = {
        "_id": 0, "document_id": 1, "action": 1, "timestamp": 1,
        "timestamp_utc": 1, "user_id": 1, "user.id": 1,
    }
    rows = await db.audit_logs.find(
        {"collection": collection, "document_id": {"$in": ids}}, projection
    ).sort("timestamp", -1).to_list(max(len(ids) * per_document_limit, per_document_limit))
    for row in rows:
        doc_id = str(row.get("document_id") or "")
        if doc_id in result and len(result[doc_id]) < per_document_limit:
            result[doc_id].append(row)
    return result


def _hard_examples(analysis: Mapping[str, Any], collection: str) -> list[dict[str, Any]]:
    allowed = HARD_CLASSIFICATIONS.get(collection, set())
    return [
        dict(example)
        for example in analysis.get("examples") or []
        if example.get("classification") in allowed
    ]


async def collect_report(
    db: Any,
    *,
    academic_year: int,
    mantenedora_id: str | None,
    audit_history_limit: int,
    audit_events_per_doc: int,
) -> dict[str, Any]:
    p0f3 = _load_p0f3_module()
    p0f3_report = await p0f3.collect_report(
        db,
        academic_year=academic_year,
        mantenedora_id=mantenedora_id,
        audit_history_limit=audit_history_limit,
        example_limit=10000,
    )

    cases: list[dict[str, Any]] = []
    total_hard_from_p0f3 = int((p0f3_report.get("summary") or {}).get("hard_conflicts") or 0)
    conflict_items_total = 0
    provenance_counts: Counter[str] = Counter()
    requirement_counts: Counter[str] = Counter()

    for p0f3_case in p0f3_report.get("cases") or []:
        conflict_items: list[dict[str, Any]] = []
        analyses = p0f3_case.get("analyses") or {}
        for collection, analysis in analyses.items():
            examples = _hard_examples(analysis, collection)
            for example in examples:
                source_ids = [str(v) for v in example.get("source_document_ids") or [] if v]
                target_ids = [str(v) for v in example.get("target_document_ids") or [] if v]
                all_ids = list(dict.fromkeys(source_ids + target_ids))

                documents = await _load_documents(db, collection, all_ids)
                audits = await _load_audit_by_document(
                    db, collection, all_ids, audit_events_per_doc
                )

                source_meta = [safe_metadata(documents[i]) for i in source_ids if i in documents]
                target_meta = [safe_metadata(documents[i]) for i in target_ids if i in documents]
                source_audit_count = sum(len(audits.get(i) or []) for i in source_ids)
                target_audit_count = sum(len(audits.get(i) or []) for i in target_ids)
                provenance_state = classify_provenance(
                    source_meta, target_meta, source_audit_count, target_audit_count
                )
                requirement = resolution_requirement(collection)
                provenance_counts[provenance_state] += 1
                requirement_counts[requirement] += 1

                conflict_items.append({
                    "collection": collection,
                    "key_sha256": example.get("key_sha256"),
                    "p0f3_classification": example.get("classification"),
                    "field_names": list(example.get("field_names") or []),
                    "conflicting_student_count": example.get("conflicting_student_count"),
                    "source_document_ids": source_ids,
                    "target_document_ids": target_ids,
                    "source_metadata": source_meta,
                    "target_metadata": target_meta,
                    "source_audit": summarize_audit([
                        row for doc_id in source_ids for row in (audits.get(doc_id) or [])
                    ]),
                    "target_audit": summarize_audit([
                        row for doc_id in target_ids for row in (audits.get(doc_id) or [])
                    ]),
                    "provenance_state": provenance_state,
                    "resolution_requirement": requirement,
                    "automatic_resolution": False,
                })

        conflict_items_total += len(conflict_items)
        cases.append({
            "group_number": p0f3_case.get("group_number"),
            "identity": p0f3_case.get("identity"),
            "source_id": p0f3_case.get("source_id"),
            "target_id": p0f3_case.get("target_id"),
            "p0f3_hard_conflicts": p0f3_case.get("hard_conflicts"),
            "conflicts_documented": len(conflict_items),
            "conflicts_by_collection": dict(sorted(Counter(
                item["collection"] for item in conflict_items
            ).items())),
            "resolution_requirements": dict(sorted(Counter(
                item["resolution_requirement"] for item in conflict_items
            ).items())),
            "provenance_states": dict(sorted(Counter(
                item["provenance_state"] for item in conflict_items
            ).items())),
            "conflicts": conflict_items,
            "automatic_resolution": False,
            "database_mutation": False,
        })

    complete_coverage = conflict_items_total == total_hard_from_p0f3
    status = "PASS" if complete_coverage else "BLOCKED_INCOMPLETE_CONFLICT_COVERAGE"

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_CONFLICT_PROVENANCE_DOSSIER",
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "academic_year": academic_year,
        "mantenedora_id": mantenedora_id,
        "source_p0f3_manifest_sha256": p0f3_report.get("manifest_sha256"),
        "summary": {
            "duplicate_identity_groups": len(cases),
            "p0f3_hard_conflicts": total_hard_from_p0f3,
            "conflicts_documented": conflict_items_total,
            "complete_conflict_coverage": complete_coverage,
            "provenance_state_counts": dict(sorted(provenance_counts.items())),
            "resolution_requirement_counts": dict(sorted(requirement_counts.items())),
            "automatic_resolution": False,
            "database_mutation": False,
        },
        "safety": {
            "payload_values_in_manifest": False,
            "grade_values_redacted": True,
            "attendance_status_values_redacted": True,
            "pedagogical_text_redacted": True,
            "historical_kept_is_evidence_not_authorization": True,
            "timestamps_do_not_define_authority": True,
            "automatic_resolution": False,
            "automatic_remap": False,
            "automatic_merge": False,
            "automatic_delete": False,
        },
        "cases": cases,
    }
    report["manifest_sha256"] = _canonical_sha(report)
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
                "source_id": case.get("source_id"),
                "target_id": case.get("target_id"),
                "p0f3_hard_conflicts": case.get("p0f3_hard_conflicts"),
                "conflicts_documented": case.get("conflicts_documented"),
                "conflicts_by_collection": case.get("conflicts_by_collection"),
                "resolution_requirements": case.get("resolution_requirements"),
                "provenance_states": case.get("provenance_states"),
                "automatic_resolution": False,
            }
            for case in report.get("cases") or []
        ],
        "manifest_sha256": report.get("manifest_sha256"),
        "database_mutation": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F4 conflict provenance read-only dossier")
    parser.add_argument("--academic-year", required=True, type=int)
    parser.add_argument("--mantenedora-id")
    parser.add_argument("--audit-history-limit", type=int, default=200)
    parser.add_argument("--audit-events-per-doc", type=int, default=50)
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
            audit_events_per_doc=args.audit_events_per_doc,
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
    return 0 if report.get("status") == "PASS" else 2


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
