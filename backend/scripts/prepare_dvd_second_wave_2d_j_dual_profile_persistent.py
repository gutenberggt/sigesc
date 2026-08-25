"""Segunda Onda DVD 2D-J — preflight com evidência de perfil em duas fontes.

READ-ONLY no MongoDB. Não aplica vínculo e não altera class_schedules.

O perfil só é aceito quando duas fontes independentes concordam:
1. ao menos um DVD ativo do MESMO componente, na mesma escola/ano;
2. ao menos dois DVDs irmãos da mesma professora/turma.

Ambas as fontes precisam ser unânimes em profile (regular/integrator),
student_scope=all e concordar entre si. Qualquer divergência falha fechado.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from scripts import prepare_dvd_second_wave_2d_j as base  # noqa: E402
from scripts import prepare_dvd_second_wave_2d_j_migration_aware as migration_aware  # noqa: E402
from scripts.prepare_dvd_cutover_phase38g import collect_backup_bundle  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

SAME_COMPONENT_MIN_COUNT = 1
SIBLING_MIN_COUNT = 2
DUAL_PROFILE_EVIDENCE = "same_component_same_school_plus_teacher_class_siblings"
REQUIRED_EVIDENCE = "exact_schedule_exact_workload_dual_profile_consensus"

MONGO_MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


class DualProfilePreflightError(base.PreflightGateError):
    pass


def assert_script_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith('"') and "MONGO_MUTATOR_TOKENS" not in line
    )
    forbidden = [token for token in MONGO_MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise DualProfilePreflightError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def _active_enabled(row: Mapping[str, Any]) -> bool:
    return (
        row.get("deleted") is not True
        and not row.get("is_substitute")
        and (row.get("diary_settings") or {}).get("enabled") is True
        and base._is_active_on_reference(row)
    )


def _source_consensus(label: str, rows: list[Mapping[str, Any]], *, minimum: int) -> dict[str, Any]:
    active = [row for row in rows if _active_enabled(row)]
    if len(active) < minimum:
        raise DualProfilePreflightError(
            f"{label}_EVIDENCE_INSUFFICIENT required={minimum} actual={len(active)}"
        )

    profiles = Counter(str((row.get("diary_settings") or {}).get("profile") or "") for row in active)
    scopes = Counter(str((row.get("diary_settings") or {}).get("student_scope") or "") for row in active)

    if len(profiles) != 1:
        raise DualProfilePreflightError(
            f"{label}_PROFILE_AMBIGUOUS profiles={dict(sorted(profiles.items()))}"
        )
    profile = next(iter(profiles))
    if profile not in {"regular", "integrator"}:
        raise DualProfilePreflightError(f"{label}_PROFILE_NOT_ALLOWED profile={profile}")
    if set(scopes) != {"all"}:
        raise DualProfilePreflightError(
            f"{label}_STUDENT_SCOPE_AMBIGUOUS scopes={dict(sorted(scopes.items()))}"
        )

    return {
        "profile": profile,
        "student_scope": "all",
        "count": len(active),
        "profile_counts": dict(sorted(profiles.items())),
        "scope_counts": dict(sorted(scopes.items())),
        "ids": sorted(str(row.get("id") or "") for row in active),
    }


def resolve_dual_source_profile(
    component_id: str,
    peers: list[Mapping[str, Any]],
    siblings: list[Mapping[str, Any]],
) -> dict[str, Any]:
    same_component = [
        row for row in peers
        if str(row.get("component_id") or "") == component_id
    ]
    peer = _source_consensus(
        "SAME_COMPONENT",
        same_component,
        minimum=SAME_COMPONENT_MIN_COUNT,
    )
    sibling = _source_consensus(
        "TEACHER_CLASS_SIBLING",
        siblings,
        minimum=SIBLING_MIN_COUNT,
    )

    if peer["profile"] != sibling["profile"]:
        raise DualProfilePreflightError(
            "DUAL_PROFILE_DISAGREEMENT "
            f"component={component_id} same_component={peer['profile']} sibling={sibling['profile']}"
        )

    return {
        "profile": peer["profile"],
        "student_scope": "all",
        "peer_count": peer["count"],
        "sibling_count": sibling["count"],
        "profile_counts": peer["profile_counts"],
        "sibling_profile_counts": sibling["profile_counts"],
        "same_component_ids": peer["ids"],
        "sibling_ids": sibling["ids"],
        "evidence_model": DUAL_PROFILE_EVIDENCE,
    }


async def collect_sibling_rows(db) -> list[dict[str, Any]]:
    rows = await db.teacher_class_assignments.find(
        {
            "class_id": base.CLASS_ID,
            "teacher_id": base.TEACHER_USER_ID,
            "deleted": {"$ne": True},
        },
        {
            "_id": 0,
            "id": 1,
            "teacher_id": 1,
            "class_id": 1,
            "component_id": 1,
            "valid_from": 1,
            "valid_until": 1,
            "is_substitute": 1,
            "deleted": 1,
            "diary_settings": 1,
        },
    ).to_list(1000)
    return [row for row in rows if _active_enabled(row)]


def _enrich_manifest_profile_provenance(validated: dict[str, Any]) -> None:
    evidence_by_legacy = validated.get("peer_evidence") or {}
    for row in validated.get("manifest") or []:
        provenance = row.get("cutover_provenance") or {}
        legacy_id = str(provenance.get("source_legacy_assignment_id") or "")
        evidence = evidence_by_legacy.get(legacy_id) or {}
        provenance["evidence"] = REQUIRED_EVIDENCE
        provenance["profile_evidence"] = DUAL_PROFILE_EVIDENCE
        provenance["same_component_peer_count"] = int(evidence.get("peer_count") or 0)
        provenance["sibling_profile_count"] = int(evidence.get("sibling_count") or 0)
        row["cutover_provenance"] = provenance
    validated["manifest_sha256"] = base.manifest_digest(validated.get("manifest") or [])


async def run_preflight(db, *, backup_dir: Path) -> dict[str, Any]:
    assert_script_read_only()
    base.assert_script_read_only()
    migration_aware.assert_script_read_only()
    base.validate_persistent_backup_path(backup_dir)

    migration_evidence = await migration_aware.collect_migration_artifacts(db)
    sibling_rows = await collect_sibling_rows(db)

    original_resolver = base.resolve_peer_profile
    try:
        base.resolve_peer_profile = lambda component_id, peers: resolve_dual_source_profile(
            component_id,
            peers,
            sibling_rows,
        )
        validated = await base.collect_2d_j_manifest(migration_aware._DatabaseProxy(db))
    finally:
        base.resolve_peer_profile = original_resolver

    _enrich_manifest_profile_provenance(validated)

    bundle = await collect_backup_bundle(
        db,
        validated["manifest"],
        academic_year=base.ACADEMIC_YEAR,
    )
    scope = dict(bundle.get("scope") or {})
    scope["second_wave_2d_j_legacy_migration_artifacts"] = migration_evidence
    scope["second_wave_2d_j_profile_evidence"] = validated.get("peer_evidence") or {}
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
        "sibling_count": len(sibling_rows),
    }


def print_compact(result: Mapping[str, Any]) -> None:
    v = result["validated"]
    b = result["backup"]
    print("=== DVD SEGUNDA ONDA 2D-J — PREFLIGHT DUAL-PROFILE READ-ONLY ===")
    print("READY_2D_J:", len(v["manifest"]))
    print("ESPERADO:", base.APPROVED_READY_COUNT)
    print("MANIFEST_SHA256:", v["manifest_sha256"])
    print("VALID_FROM:", v["valid_from"])
    print("PROFILE_EVIDENCE_MODEL:", DUAL_PROFILE_EVIDENCE)
    print("PROFILE_EVIDENCE:", json.dumps(v["peer_evidence"], ensure_ascii=False, sort_keys=True))
    print("CURRENT_DVD_SIBLINGS:", result["sibling_count"])
    print("LEGACY_MIGRATION_ARTIFACTS:", len(result["migration_evidence"]))
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
