#!/usr/bin/env python3
"""P0-C.1E — preflight de identidade semantic-aware, READ-ONLY.

Executa o P0-C original somente sobre vínculos DVD operacionais. Artefatos
``source=legacy_migration`` são separados porque usam ``teacher_id=staff.id`` e
não representam propriedade pedagógica DVD. Qualquer drift dos marcadores
sintéticos bloqueia o preflight fail-closed.
"""
from __future__ import annotations

import argparse
import asyncio
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
from scripts import preflight_teacher_identity_remediation_p0c as base  # noqa: E402
from scripts.audit_teacher_binding_integrity_p0_semantic import (  # noqa: E402
    _SemanticDatabaseProxy,
    collect_semantic_partition,
)
from services.teacher_class_assignment_semantics import (  # noqa: E402
    LEGACY_MIGRATION_DRIFT,
    LEGACY_MIGRATION_SYNTHETIC,
    OPERATIONAL_DVD,
)

load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0C-TEACHER-IDENTITY-PREFLIGHT-2026-SEMANTIC-V2"
MANIFEST_VERSION = 2
DEFAULT_MANIFEST = "/tmp/sigesc_p0c_teacher_identity_semantic_v2.json"
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


async def collect_manifest(
    db: Any,
    *,
    academic_year: int,
    reference_date: str,
    mantenedora_id: Optional[str] = None,
    source_evidence_sha256: Optional[str] = None,
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

    if semantic["remediation_gate"] != "PASS":
        return {
            "phase": PHASE_ID,
            "manifest_version": MANIFEST_VERSION,
            "mode": "READ_ONLY_PREFLIGHT",
            "status": "BLOCKED_LEGACY_MIGRATION_DRIFT",
            "academic_year": academic_year,
            "reference_date": reference_date,
            "mantenedora_id": mantenedora_id,
            "source_p0b_evidence_sha256": source_evidence_sha256,
            "semantic_partition": semantic,
            "summary": {
                "decision_counts": {},
                "proposed_staff_user_id_backfills": 0,
                "operational_dvd_rows": semantic["counts"].get(OPERATIONAL_DVD, 0),
                "legacy_migration_synthetic": semantic["counts"].get(LEGACY_MIGRATION_SYNTHETIC, 0),
                "legacy_migration_drift": semantic["counts"].get(LEGACY_MIGRATION_DRIFT, 0),
            },
            "proposals": [],
            "cases": [],
            "safety_contract": {
                "database_mutation": False,
                "legacy_migration_drift_blocks_preflight": True,
            },
        }

    payload = await base.collect_manifest(
        _SemanticDatabaseProxy(db),
        academic_year=academic_year,
        reference_date=reference_date,
        mantenedora_id=mantenedora_id,
        source_evidence_sha256=source_evidence_sha256,
    )
    payload["phase"] = PHASE_ID
    payload["manifest_version"] = MANIFEST_VERSION
    payload["status"] = "PASS"
    payload["semantic_partition"] = semantic
    payload["scope"] = {
        **payload["scope"],
        "teacher_class_assignments_raw_active": semantic["raw_active_rows"],
        "operational_dvd_rows": semantic["counts"].get(OPERATIONAL_DVD, 0),
        "legacy_migration_synthetic": semantic["counts"].get(LEGACY_MIGRATION_SYNTHETIC, 0),
        "legacy_migration_drift": semantic["counts"].get(LEGACY_MIGRATION_DRIFT, 0),
    }
    payload["safety_contract"] = {
        **payload["safety_contract"],
        "legacy_migration_semantically_separated": True,
        "legacy_migration_teacher_id_semantics": "staff.id",
        "operational_dvd_teacher_id_semantics": "users.id",
        "legacy_migration_drift_blocks_preflight": True,
    }
    return payload


async def run(args: argparse.Namespace) -> int:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise SystemExit("ERRO: MONGO_URL ou DB_NAME ausente.")

    client = AsyncIOMotorClient(mongo_url)
    try:
        payload = await collect_manifest(
            client[db_name],
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            mantenedora_id=args.mantenedora_id,
            source_evidence_sha256=args.source_evidence_sha256,
            examples_limit=max(1, min(args.examples_limit, 500)),
        )
    finally:
        client.close()

    digest = base.manifest_sha256(payload)
    output = Path(args.manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "phase": PHASE_ID,
        "mode": "READ_ONLY_PREFLIGHT",
        "status": payload.get("status"),
        "manifest": str(output),
        "manifest_sha256": digest,
        "source_p0b_evidence_sha256": args.source_evidence_sha256,
        "scope": payload.get("scope"),
        "semantic_partition": payload.get("semantic_partition"),
        "summary": payload.get("summary"),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="P0-C.1E READ-ONLY — preflight semantic-aware da identidade docente"
    )
    parser.add_argument("--academic-year", type=int, default=date.today().year)
    parser.add_argument("--reference-date", default=date.today().isoformat())
    parser.add_argument("--mantenedora-id", default=None)
    parser.add_argument("--source-evidence-sha256", default=None)
    parser.add_argument("--examples-limit", type=int, default=50)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
