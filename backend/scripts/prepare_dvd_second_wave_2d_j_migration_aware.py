"""Segunda Onda DVD 2D-J — preflight migration-aware, estritamente READ-ONLY.

Corrige exclusivamente a distinção entre:
- artefatos persistidos da migração de grade legada (`source=legacy_migration`),
  que NÃO são DVD habilitado; e
- vínculos DVD reais, que continuam bloqueando qualquer conflito de turma/componente.

A lógica pedagógica/horária/perfil permanece delegada ao preflight 2D-J original.
Nenhum mutador Mongo existe neste script.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from scripts import prepare_dvd_second_wave_2d_j as base
from scripts.prepare_dvd_cutover_phase38g import collect_backup_bundle

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

MIGRATION_SOURCE = "legacy_migration"
EXPECTED_MIGRATION_RUN_ID = "c6bf982e-3114-4aeb-b276-79afb2af71b7"
EXPECTED_MIGRATION_VALID_FROM = "2026-02-01"
EXPECTED_MIGRATION_VALID_UNTIL = "2026-12-31"

EXPECTED_ARTIFACTS = {
    f"legacy::{base.CLASS_ID}::7cce8ff9-9cd1-4737-a4ed-a61554a711dc::{base.STAFF_ID}": {
        "component_id": "7cce8ff9-9cd1-4737-a4ed-a61554a711dc",
        "component_name": "HIGIENE E SAÚDE",
    },
    f"legacy::{base.CLASS_ID}::e90107dc-3276-4480-852b-91f617eefc67::{base.STAFF_ID}": {
        "component_id": "e90107dc-3276-4480-852b-91f617eefc67",
        "component_name": "CONTAÇÃO DE HISTÓRIAS E INICIAÇÃO MUSICAL",
    },
}

MONGO_MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


class MigrationAwarePreflightError(base.PreflightGateError):
    pass


def assert_script_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith('"') and "MONGO_MUTATOR_TOKENS" not in line
    )
    forbidden = [token for token in MONGO_MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise MigrationAwarePreflightError(
            f"READ_ONLY_GUARD_FAILED forbidden={forbidden}"
        )


def _artifact_id(row: Mapping[str, Any]) -> str:
    return str(row.get("id") or "")


def validate_legacy_migration_artifacts(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Aceita somente as duas materializações legadas comprovadas em produção.

    Qualquer drift converte o artefato em conflito e aborta o preflight.
    """
    by_id = {_artifact_id(row): row for row in rows if _artifact_id(row)}
    if set(by_id) != set(EXPECTED_ARTIFACTS):
        raise MigrationAwarePreflightError(
            "LEGACY_MIGRATION_ARTIFACT_SET_MISMATCH "
            f"expected={sorted(EXPECTED_ARTIFACTS)} actual={sorted(by_id)}"
        )

    evidence: list[dict[str, Any]] = []
    for artifact_id in sorted(EXPECTED_ARTIFACTS):
        row = by_id[artifact_id]
        expected = EXPECTED_ARTIFACTS[artifact_id]
        settings = row.get("diary_settings") or {}

        checks = {
            "source": row.get("source") == MIGRATION_SOURCE,
            "migrated_from_legacy": row.get("migrated_from_legacy") is True,
            "synthetic_validity": row.get("synthetic_validity") is True,
            "created_by": row.get("created_by") == MIGRATION_SOURCE,
            "migration_run_id": str(row.get("migration_run_id") or "") == EXPECTED_MIGRATION_RUN_ID,
            "class_id": str(row.get("class_id") or "") == base.CLASS_ID,
            "school_id": str(row.get("school_id") or "") == base.SCHOOL_ID,
            "academic_year": str(row.get("academic_year") or "") == str(base.ACADEMIC_YEAR),
            "component_id": str(row.get("component_id") or "") == expected["component_id"],
            "teacher_is_staff_id": str(row.get("teacher_id") or "") == base.STAFF_ID,
            "deleted_false": row.get("deleted") is False,
            "not_substitute": row.get("is_substitute") is False,
            "dvd_not_enabled": settings.get("enabled") is not True,
            "valid_from": str(row.get("valid_from") or "")[:10] == EXPECTED_MIGRATION_VALID_FROM,
            "valid_until": str(row.get("valid_until") or "")[:10] == EXPECTED_MIGRATION_VALID_UNTIL,
        }
        failed = sorted(name for name, ok in checks.items() if not ok)
        if failed:
            raise MigrationAwarePreflightError(
                f"LEGACY_MIGRATION_ARTIFACT_INVALID id={artifact_id} failed={failed}"
            )

        evidence.append({
            "id": artifact_id,
            "component_id": expected["component_id"],
            "source": MIGRATION_SOURCE,
            "migration_run_id": EXPECTED_MIGRATION_RUN_ID,
            "synthetic_validity": True,
            "migrated_from_legacy": True,
            "dvd_enabled": False,
        })
    return evidence


class _TeacherClassAssignmentsProxy:
    """Oculta legacy_migration somente da leitura de conflitos da turma-alvo."""

    def __init__(self, collection):
        self._collection = collection

    def find(self, query=None, projection=None):
        query = dict(query or {})
        if (
            query.get("class_id") == base.CLASS_ID
            and query.get("deleted") == {"$ne": True}
            and "component_id" not in query
        ):
            query["source"] = {"$ne": MIGRATION_SOURCE}
        return self._collection.find(query, projection)

    def __getattr__(self, name):
        return getattr(self._collection, name)


class _DatabaseProxy:
    def __init__(self, db):
        self._db = db
        self.teacher_class_assignments = _TeacherClassAssignmentsProxy(
            db.teacher_class_assignments
        )

    def __getattr__(self, name):
        return getattr(self._db, name)

    def __getitem__(self, name):
        return self._db[name]


async def collect_migration_artifacts(db) -> list[dict[str, Any]]:
    component_ids = sorted(
        expected["component_id"] for expected in EXPECTED_ARTIFACTS.values()
    )
    rows = await db.teacher_class_assignments.find(
        {
            "class_id": base.CLASS_ID,
            "component_id": {"$in": component_ids},
            "source": MIGRATION_SOURCE,
            "deleted": {"$ne": True},
        },
        {"_id": 0},
    ).to_list(20)
    return validate_legacy_migration_artifacts(rows)


async def run_preflight(db, *, backup_dir: Path) -> dict[str, Any]:
    assert_script_read_only()
    base.assert_script_read_only()
    base.validate_persistent_backup_path(backup_dir)

    migration_evidence = await collect_migration_artifacts(db)

    # Mantém toda a lógica original. O proxy remove somente os artefatos
    # legacy_migration do snapshot usado pelo gate CLASS_COMPONENT_DVD_CONFLICT.
    # Qualquer vínculo real (source != legacy_migration) permanece visível.
    validated = await base.collect_2d_j_manifest(_DatabaseProxy(db))

    bundle = await collect_backup_bundle(
        db,
        validated["manifest"],
        academic_year=base.ACADEMIC_YEAR,
    )
    scope = dict(bundle.get("scope") or {})
    scope["second_wave_2d_j_legacy_migration_artifacts"] = migration_evidence
    bundle = {**bundle, "scope": scope}

    backup = base.write_backup_directory(
        backup_dir,
        validated=validated,
        bundle=bundle,
    )
    return {
        "validated": validated,
        "backup": backup,
        "backup_dir": str(backup_dir),
        "migration_evidence": migration_evidence,
    }


def print_compact(result: Mapping[str, Any]) -> None:
    v = result["validated"]
    b = result["backup"]
    evidence = result["migration_evidence"]
    print("=== DVD SEGUNDA ONDA 2D-J — PREFLIGHT MIGRATION-AWARE READ-ONLY ===")
    print("READY_2D_J:", len(v["manifest"]))
    print("ESPERADO:", base.APPROVED_READY_COUNT)
    print("LEGACY_MIGRATION_ARTIFACTS:", len(evidence))
    print("LEGACY_MIGRATION_RUN_ID:", EXPECTED_MIGRATION_RUN_ID)
    print("MANIFEST_SHA256:", v["manifest_sha256"])
    print("VALID_FROM:", v["valid_from"])
    print("PEER_EVIDENCE:", v["peer_evidence"])
    print("CURRENT_DVD_SIBLINGS:", v["current_sibling_count"])
    print("BACKUP_DIR:", result["backup_dir"])
    print("BACKUP_SHA256:", b["backup_bundle_sha256"])
    print("MONGO_WRITES: 0")
    print("ATIVACAO_EXECUTADA: NAO")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", required=True)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc")]
        result = await run_preflight(db, backup_dir=Path(args.backup_dir))
        print_compact(result)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
