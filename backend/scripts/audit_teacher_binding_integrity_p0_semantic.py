#!/usr/bin/env python3
"""P0-C.1D — auditor global semantic-aware, estritamente READ-ONLY.

Corrige a leitura forense do P0-B sem alterar o artefato histórico original:
- referências curriculares continuam auditadas em TODA a collection;
- somente vínculos DVD operacionais entram na resolução ``users.id -> staff.id``;
- ``source=legacy_migration`` só é separado quando os marcadores sintéticos
  oficiais permanecem íntegros;
- materializações sem professor são um bucket sintético explícito, não drift;
- qualquer drift real desses marcadores bloqueia remediação automática.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import date
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
from scripts import audit_teacher_binding_integrity_p0 as base  # noqa: E402
from services.teacher_class_assignment_semantics import (  # noqa: E402
    LEGACY_MIGRATION_DRIFT,
    LEGACY_MIGRATION_SOURCE,
    LEGACY_MIGRATION_SYNTHETIC,
    LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED,
    OPERATIONAL_DVD,
    classify_teacher_class_assignment,
    semantic_projection,
)

load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0C-1D-TEACHER-BINDING-SEMANTIC-AUDIT-2026-V3"
MUTATOR_TOKENS = base.MUTATOR_TOKENS


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")
    base.assert_read_only()


def _binding_identity_scan(
    query: Mapping[str, Any] | None,
    projection: Mapping[str, Any] | None,
) -> bool:
    """Reconhece apenas o scan de identidade/vínculo dos auditores P0.

    A auditoria de referências curriculares não pede ``valid_from`` e
    ``valid_until`` ao mesmo tempo; portanto permanece intocada e continua vendo
    inclusive os artefatos sintéticos.
    """
    projection = projection or {}
    return all(
        field in projection
        for field in ("teacher_id", "component_id", "valid_from", "valid_until")
    )


class _SemanticCollectionProxy:
    def __init__(self, collection):
        self._collection = collection

    def find(self, query=None, projection=None, *args, **kwargs):
        effective = dict(query or {})
        if _binding_identity_scan(effective, projection):
            effective = {
                "$and": [
                    effective,
                    {"source": {"$ne": LEGACY_MIGRATION_SOURCE}},
                ]
            }
        return self._collection.find(effective, projection, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._collection, name)


class _SemanticDatabaseProxy:
    def __init__(self, db):
        self._db = db
        self.teacher_class_assignments = _SemanticCollectionProxy(
            db.teacher_class_assignments
        )

    def __getattr__(self, name):
        return getattr(self._db, name)

    def __getitem__(self, name):
        if name == "teacher_class_assignments":
            return self.teacher_class_assignments
        return self._db[name]


async def _scope_class_ids(
    db: Any,
    *,
    academic_year: int,
    mantenedora_id: Optional[str],
) -> set[str]:
    if not mantenedora_id:
        rows = await db.classes.find(
            {"academic_year": {"$in": [academic_year, str(academic_year)]}},
            {"_id": 0, "id": 1},
        ).to_list(20000)
        return {str(row.get("id")) for row in rows if row.get("id")}

    schools = await db.schools.find(
        {"mantenedora_id": mantenedora_id}, {"_id": 0, "id": 1}
    ).to_list(10000)
    school_ids = [row.get("id") for row in schools if row.get("id")]
    rows = await db.classes.find(
        {
            "academic_year": {"$in": [academic_year, str(academic_year)]},
            "school_id": {"$in": school_ids},
        },
        {"_id": 0, "id": 1},
    ).to_list(20000)
    return {str(row.get("id")) for row in rows if row.get("id")}


async def collect_semantic_partition(
    db: Any,
    *,
    academic_year: int,
    reference_date: str,
    mantenedora_id: Optional[str],
    examples_limit: int,
) -> dict[str, Any]:
    class_ids = await _scope_class_ids(
        db,
        academic_year=academic_year,
        mantenedora_id=mantenedora_id,
    )
    rows = await db.teacher_class_assignments.find(
        {"deleted": {"$ne": True}, "class_id": {"$in": sorted(class_ids)}},
        semantic_projection(),
    ).to_list(50000)
    active = [row for row in rows if base._active_temporal(row, reference_date)]

    counts = Counter()
    row_counts = Counter()
    distinct_teacher_ids: dict[str, set[str]] = {
        OPERATIONAL_DVD: set(),
        LEGACY_MIGRATION_SYNTHETIC: set(),
        LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED: set(),
        LEGACY_MIGRATION_DRIFT: set(),
    }
    migration_runs = Counter()
    drift_reasons = Counter()
    drift_examples: list[dict[str, Any]] = []

    migration_kinds = {
        LEGACY_MIGRATION_SYNTHETIC,
        LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED,
        LEGACY_MIGRATION_DRIFT,
    }

    for row in active:
        semantic = classify_teacher_class_assignment(row)
        counts[semantic.kind] += 1
        teacher_id = str(row.get("teacher_id") or "").strip()
        if teacher_id:
            distinct_teacher_ids[semantic.kind].add(teacher_id)
        if semantic.kind in migration_kinds:
            run_id = str(row.get("migration_run_id") or "").strip() or "(missing)"
            migration_runs[run_id] += 1
        if semantic.kind == LEGACY_MIGRATION_DRIFT:
            for reason in semantic.drift_reasons:
                drift_reasons[reason] += 1
            if len(drift_examples) < examples_limit:
                drift_examples.append({
                    "id": row.get("id"),
                    "teacher_id": row.get("teacher_id"),
                    "class_id": row.get("class_id"),
                    "component_id": row.get("component_id"),
                    "drift_reasons": list(semantic.drift_reasons),
                })

    for kind, values in distinct_teacher_ids.items():
        row_counts[f"{kind}_DISTINCT_TEACHER_IDS"] = len(values)

    drift = counts[LEGACY_MIGRATION_DRIFT]
    return {
        "raw_active_rows": len(active),
        "counts": dict(sorted(counts.items())),
        "distinct_teacher_ids": dict(sorted(row_counts.items())),
        "migration_run_counts": dict(sorted(migration_runs.items())),
        "drift_reason_counts": dict(sorted(drift_reasons.items())),
        "drift_examples": drift_examples,
        "remediation_gate": "PASS" if drift == 0 else "BLOCKED_LEGACY_MIGRATION_DRIFT",
    }


async def collect_report(
    db: Any,
    *,
    academic_year: int,
    reference_date: str,
    mantenedora_id: Optional[str] = None,
    examples_limit: int = 50,
) -> dict[str, Any]:
    assert_read_only()
    semantic = await collect_semantic_partition(
        db,
        academic_year=academic_year,
        reference_date=reference_date,
        mantenedora_id=mantenedora_id,
        examples_limit=examples_limit,
    )

    report = await base.collect_report(
        _SemanticDatabaseProxy(db),
        academic_year=academic_year,
        reference_date=reference_date,
        mantenedora_id=mantenedora_id,
        examples_limit=examples_limit,
    )
    report["kind"] = "P0_GLOBAL_TEACHER_BINDING_INTEGRITY_SEMANTIC_V3"
    report["phase"] = PHASE_ID
    report["semantic_partition"] = semantic
    report["summary"] = {
        **report["summary"],
        "teacher_class_assignments_raw_active": semantic["raw_active_rows"],
        "teacher_class_assignments_operational": semantic["counts"].get(OPERATIONAL_DVD, 0),
        "legacy_migration_synthetic": semantic["counts"].get(LEGACY_MIGRATION_SYNTHETIC, 0),
        "legacy_migration_synthetic_unassigned": semantic["counts"].get(
            LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED, 0
        ),
        "legacy_migration_drift": semantic["counts"].get(LEGACY_MIGRATION_DRIFT, 0),
    }
    report["remediation_gate"] = semantic["remediation_gate"]
    return report


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="P0-C.1D READ-ONLY — auditoria semantic-aware de vínculos docentes"
    )
    parser.add_argument("--academic-year", type=int, default=date.today().year)
    parser.add_argument("--reference-date", default=date.today().isoformat())
    parser.add_argument("--mantenedora-id", default=None)
    parser.add_argument("--examples-limit", type=int, default=50)
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        report = await collect_report(
            client[os.environ["DB_NAME"]],
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            mantenedora_id=args.mantenedora_id,
            examples_limit=max(1, min(args.examples_limit, 500)),
        )
    finally:
        client.close()

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
