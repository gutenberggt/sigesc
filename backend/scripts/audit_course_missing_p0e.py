"""P0-E — auditoria forense READ-ONLY de referências a courses.id ausentes.

Objetivo: explicar cada ocorrência COURSE_MISSING sem corrigir, remapear ou
inferir automaticamente componente curricular. O relatório cruza o registry
canônico de referências, contexto escola/turma/tenant e trilhas históricas de
auditoria/consolidação.
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

PHASE_ID = "P0E-COURSE-MISSING-FORENSIC-READ-ONLY-2026"
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


def _same_year(value: Any, year: int) -> bool:
    if value in (None, ""):
        return True
    try:
        return int(value) == int(year)
    except (TypeError, ValueError):
        return False


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _course_identity(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _norm(row.get("mantenedora_id")),
        _norm(row.get("name")).casefold(),
        _norm(row.get("nivel_ensino")).casefold(),
    )


def exact_identity_candidates(
    historical_course: Mapping[str, Any],
    current_courses: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Retorna apenas candidatos de identidade exata; nunca escolhe um vencedor."""
    key = _course_identity(historical_course)
    if not all(key):
        return []
    result = []
    for row in current_courses:
        if _course_identity(row) == key:
            result.append({
                "id": row.get("id"),
                "name": row.get("name"),
                "nivel_ensino": row.get("nivel_ensino"),
                "mantenedora_id": row.get("mantenedora_id"),
                "status": row.get("status"),
            })
    return sorted(result, key=lambda x: _norm(x.get("id")))


def _safe_reference_context(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "id", "mantenedora_id", "school_id", "class_id", "academic_year",
        "staff_id", "teacher_id", "student_id", "status", "deleted",
        "source", "created_by", "migration_run_id", "created_at", "updated_at",
    )
    return {key: row.get(key) for key in keys if key in row}


async def _load_audit_history(db: Any, missing_course_id: str, limit: int) -> list[dict[str, Any]]:
    """Procura evidência histórica explícita para um courses.id ausente."""
    query = {
        "$and": [
            {"collection": "courses"},
            {"$or": [
                {"document_id": missing_course_id},
                {"old_value.id": missing_course_id},
                {"new_value.id": missing_course_id},
                {"extra_data.consolidated.removed_ids": missing_course_id},
                {"extra_data.consolidated.kept_id": missing_course_id},
            ]},
        ]
    }
    projection = {
        "_id": 0,
        "action": 1,
        "collection": 1,
        "document_id": 1,
        "description": 1,
        "timestamp": 1,
        "timestamp_utc": 1,
        "user_id": 1,
        "user_email": 1,
        "old_value": 1,
        "new_value": 1,
        "extra_data.consolidated": 1,
    }
    rows = await db.audit_logs.find(query, projection).sort("timestamp", 1).to_list(limit)
    return rows


def _historical_course_from_logs(missing_id: str, logs: list[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """Extrai snapshot histórico somente se o próprio audit log o contém."""
    for log in reversed(logs):
        for key in ("old_value", "new_value"):
            value = log.get(key)
            if not isinstance(value, Mapping):
                continue
            value_id = _norm(value.get("id"))
            if value_id and value_id != missing_id:
                continue
            name = _norm(value.get("name"))
            level = _norm(value.get("nivel_ensino"))
            tenant = _norm(value.get("mantenedora_id"))
            if name or level or tenant:
                return {
                    "id": missing_id,
                    "name": value.get("name"),
                    "nivel_ensino": value.get("nivel_ensino"),
                    "mantenedora_id": value.get("mantenedora_id"),
                    "source": f"audit_logs.{key}",
                }
    return None


def _merge_candidates(missing_id: str, logs: list[Mapping[str, Any]]) -> list[str]:
    candidates: set[str] = set()
    for log in logs:
        consolidated = ((log.get("extra_data") or {}).get("consolidated") or [])
        for entry in consolidated:
            if not isinstance(entry, Mapping):
                continue
            removed = {_norm(x) for x in (entry.get("removed_ids") or [])}
            kept = _norm(entry.get("kept_id"))
            if missing_id in removed and kept:
                candidates.add(kept)
    return sorted(candidates)


async def collect_report(
    db: Any,
    *,
    academic_year: int,
    mantenedora_id: Optional[str] = None,
    audit_history_limit: int = 100,
) -> dict[str, Any]:
    schools_query: dict[str, Any] = {}
    if mantenedora_id:
        schools_query["mantenedora_id"] = mantenedora_id
    schools = await db.schools.find(
        schools_query,
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    ).to_list(10000)
    school_by_id = {_norm(x.get("id")): x for x in schools if x.get("id")}
    school_ids = set(school_by_id)

    class_query: dict[str, Any] = {
        "academic_year": {"$in": [academic_year, str(academic_year)]}
    }
    if mantenedora_id:
        class_query["school_id"] = {"$in": sorted(school_ids)}
    classes = await db.classes.find(
        class_query,
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1, "mantenedora_id": 1},
    ).to_list(20000)
    class_by_id = {_norm(x.get("id")): x for x in classes if x.get("id")}

    current_courses = await db.courses.find(
        {},
        {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1, "status": 1},
    ).to_list(20000)
    course_ids = {_norm(x.get("id")) for x in current_courses if x.get("id")}

    references: list[dict[str, Any]] = []
    counters = Counter()

    for spec in COURSE_REFERENCE_SPECS:
        root = spec.field.split(".", 1)[0]
        projection = reference_projection(spec)
        for key in (
            "student_id", "source", "created_by", "migration_run_id",
            "created_at", "updated_at",
        ):
            projection[key] = 1

        cursor = db[spec.collection].find({root: {"$exists": True}}, projection)
        async for row in cursor:
            if not _same_year(row.get("academic_year"), academic_year):
                continue

            class_id = _norm(row.get("class_id"))
            klass = class_by_id.get(class_id) if class_id else None
            school = school_by_id.get(_norm((klass or {}).get("school_id"))) if klass else None

            if mantenedora_id:
                resolved_tenant = (
                    _norm(row.get("mantenedora_id"))
                    or _norm((klass or {}).get("mantenedora_id"))
                    or _norm((school or {}).get("mantenedora_id"))
                )
                if resolved_tenant and resolved_tenant != mantenedora_id:
                    continue
                if class_id and class_id not in class_by_id and not resolved_tenant:
                    continue

            for course_id in extract_reference_ids(row, spec.field):
                counters["COURSE_REFERENCES_AUDITED"] += 1
                if course_id in course_ids:
                    continue
                counters["COURSE_MISSING_REFERENCES"] += 1
                references.append({
                    "missing_course_id": course_id,
                    "collection": spec.collection,
                    "field": spec.field,
                    "label": spec.label,
                    "document": _safe_reference_context(row),
                    "class": None if not klass else {
                        "id": klass.get("id"),
                        "name": klass.get("name"),
                        "school_id": klass.get("school_id"),
                        "academic_year": klass.get("academic_year"),
                        "mantenedora_id": klass.get("mantenedora_id"),
                    },
                    "school": None if not school else {
                        "id": school.get("id"),
                        "name": school.get("name"),
                        "mantenedora_id": school.get("mantenedora_id"),
                    },
                })

    by_missing_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ref in references:
        by_missing_id[ref["missing_course_id"]].append(ref)

    cases: list[dict[str, Any]] = []
    origin_counts = Counter()

    for missing_id in sorted(by_missing_id):
        refs = by_missing_id[missing_id]
        history = await _load_audit_history(db, missing_id, audit_history_limit)
        merge_candidates = _merge_candidates(missing_id, history)
        historical_course = _historical_course_from_logs(missing_id, history)
        identity_candidates = (
            exact_identity_candidates(historical_course, current_courses)
            if historical_course else []
        )

        if merge_candidates:
            origin_state = "MERGE_PROVENANCE_FOUND"
        elif history:
            origin_state = "COURSE_AUDIT_HISTORY_FOUND"
        else:
            origin_state = "NO_COURSE_AUDIT_HISTORY"
        origin_counts[origin_state] += 1

        cases.append({
            "missing_course_id": missing_id,
            "reference_count": len(refs),
            "collections": dict(sorted(Counter(r["collection"] for r in refs).items())),
            "references": refs,
            "origin_state": origin_state,
            "merge_canonical_candidates": merge_candidates,
            "historical_course_snapshot": historical_course,
            "exact_identity_current_candidates": identity_candidates,
            "audit_history": history,
        })

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_FORENSIC",
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "academic_year": academic_year,
        "mantenedora_id": mantenedora_id,
        "summary": {
            "course_references_audited": counters["COURSE_REFERENCES_AUDITED"],
            "course_missing_references": counters["COURSE_MISSING_REFERENCES"],
            "distinct_missing_course_ids": len(by_missing_id),
            "origin_state_counts": dict(sorted(origin_counts.items())),
            "database_mutation": False,
        },
        "cases": cases,
        "safety": {
            "automatic_remap": False,
            "automatic_course_creation": False,
            "automatic_delete": False,
            "candidate_semantics": (
                "candidatos de merge/identidade são evidência forense; não são autorização de remapeamento"
            ),
        },
    }
    report["manifest_sha256"] = canonical_sha256(report)
    return report


async def async_main(args: argparse.Namespace) -> dict[str, Any]:
    assert_read_only()
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError("MONGO_URL e DB_NAME são obrigatórios")

    client = AsyncIOMotorClient(mongo_url)
    try:
        report = await collect_report(
            client[db_name],
            academic_year=args.academic_year,
            mantenedora_id=args.mantenedora_id,
            audit_history_limit=args.audit_history_limit,
        )
    finally:
        client.close()

    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--academic-year", type=int, required=True)
    parser.add_argument("--mantenedora-id")
    parser.add_argument("--audit-history-limit", type=int, default=100)
    parser.add_argument("--json")
    return parser.parse_args()


def main() -> None:
    report = asyncio.run(async_main(parse_args()))
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
