"""Segunda Onda DVD 2C — preflight selado e estritamente READ-ONLY.

Escopo auditado em produção em 2026-08-25:
- professora Juliana da Silva Leao;
- turma Berçario II A / CMEI Professora Nivalda Maria de Godoy;
- 2 vínculos prontos pelo padrão P0 de slots residuais fora de slots_per_day;
- manifesto SHA-256 fixo;
- nenhum apply/rollback;
- nenhuma escrita no MongoDB.

Importante: ``missing_total`` do diagnóstico P0 inclui também ausências que não
pertencem à 2C. Este preflight sela somente ``report['manifest']`` (os ``ready``)
e valida que são exatamente os dois candidatos aprovados. Casos ``blocked``
sem resíduo fora da grade permanecem fora desta onda.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
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

from scripts.prepare_dvd_cutover_phase38g import (  # noqa: E402
    collect_backup_bundle,
    sha256_file,
    sha256_value,
)
from scripts.remediate_dvd_out_of_range_schedule_p0 import (  # noqa: E402
    PROVENANCE_PHASE,
    collect_manifest,
    manifest_digest,
)

load_dotenv(BACKEND_DIR / ".env")

ACADEMIC_YEAR = 2026
TEACHER_USER_ID = "2e5004ac-dad2-4d07-a6aa-372ff49bb54a"
CLASS_ID = "a76ccc2c-317c-4bd6-8b39-ed5fa806d67c"
SCHOOL_ID = "1279c538-94c9-4c6b-a0de-994ed73c9f6f"
APPROVED_READY_COUNT = 2
APPROVED_MANIFEST_SHA256 = "09aa29dd9c535c1b83de8390a14c24d6cf44d77e7eb811530c87dc8222cc0223"
PERSISTENT_BACKUP_ROOT = Path("/data/sigesc-dvd-backups")
BACKUP_MODE = "SECOND_WAVE_2C_PREFLIGHT_READ_ONLY"
REQUIRED_EVIDENCE = "declared_grid_plus_exact_workload"
REQUIRED_SLOTS_PER_DAY = 7

APPROVED_TARGETS = {
    "8d48d5bd-418c-414a-88ce-015a8bd20fa6": {
        "component_name": "Arte e Cultura",
        "proposed_id": "d3645603-7051-57c8-bcb2-f7326767e8e0",
        "weekly_slots": 4,
        "residue_slots": {9},
        "residue_count": 5,
    },
    "0f96bcb8-33e9-47ca-add4-e9d9f9b4635d": {
        "component_name": "Linguagem Recreativa Com Práticas de Esporte e Lazer",
        "proposed_id": "b1ed1194-3118-5d32-9fce-cd4ef9cb4093",
        "weekly_slots": 3,
        "residue_slots": {8},
        "residue_count": 5,
    },
}

MONGO_MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


class PreflightGateError(RuntimeError):
    pass


def assert_script_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable_lines = [
        line for line in source.splitlines()
        if not line.lstrip().startswith('"') and "MONGO_MUTATOR_TOKENS" not in line
    ]
    executable = "\n".join(executable_lines)
    forbidden = [token for token in MONGO_MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise PreflightGateError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def validate_persistent_backup_path(path: Path) -> None:
    if not path.is_absolute():
        raise PreflightGateError(f"BACKUP_PATH_NOT_ABSOLUTE path={path}")
    try:
        path.relative_to(PERSISTENT_BACKUP_ROOT)
    except ValueError as exc:
        raise PreflightGateError(
            f"BACKUP_PATH_NOT_PERSISTENT root={PERSISTENT_BACKUP_ROOT} path={path}"
        ) from exc
    if path == PERSISTENT_BACKUP_ROOT:
        raise PreflightGateError("BACKUP_PATH_MUST_BE_CHILD_DIRECTORY")


def _legacy_id(row: Mapping[str, Any]) -> str:
    return str((row.get("cutover_provenance") or {}).get("source_legacy_assignment_id") or "")


def _target_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("teacher_id") or ""),
        str(row.get("class_id") or ""),
        str(row.get("component_id") or ""),
    )


def validate_2c_report(report: Mapping[str, Any]) -> dict[str, Any]:
    manifest = list(report.get("manifest") or [])
    summary = report.get("summary") or {}

    actual_count = len(manifest)
    if actual_count != APPROVED_READY_COUNT:
        raise PreflightGateError(
            f"READY_COUNT_MISMATCH expected={APPROVED_READY_COUNT} actual={actual_count}"
        )

    summary_ready = int(summary.get("ready") or 0)
    if summary_ready != APPROVED_READY_COUNT:
        raise PreflightGateError(
            f"SUMMARY_READY_MISMATCH expected={APPROVED_READY_COUNT} actual={summary_ready}"
        )

    actual_sha = manifest_digest(manifest)
    if actual_sha != APPROVED_MANIFEST_SHA256:
        raise PreflightGateError(
            f"MANIFEST_SHA256_MISMATCH expected={APPROVED_MANIFEST_SHA256} actual={actual_sha}"
        )
    if str(summary.get("manifest_sha256") or "") != APPROVED_MANIFEST_SHA256:
        raise PreflightGateError("SUMMARY_MANIFEST_SHA256_MISMATCH")

    legacy_ids = [_legacy_id(row) for row in manifest]
    if set(legacy_ids) != set(APPROVED_TARGETS):
        raise PreflightGateError(
            f"APPROVED_TARGET_SET_MISMATCH expected={sorted(APPROVED_TARGETS)} actual={sorted(legacy_ids)}"
        )
    if len(legacy_ids) != len(set(legacy_ids)):
        raise PreflightGateError("DUPLICATE_SOURCE_LEGACY_ID")

    ids = [str(row.get("id") or "") for row in manifest]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise PreflightGateError("MANIFEST_IDS_INVALID missing_or_duplicate")

    targets = [_target_key(row) for row in manifest]
    if any(not all(key) for key in targets) or len(targets) != len(set(targets)):
        raise PreflightGateError("MANIFEST_TARGET_KEYS_INVALID missing_or_duplicate")

    weekly_counts: Counter[int] = Counter()
    residue_counts: Counter[int] = Counter()

    for row in manifest:
        legacy_id = _legacy_id(row)
        expected = APPROVED_TARGETS[legacy_id]
        provenance = row.get("cutover_provenance") or {}
        settings = row.get("diary_settings") or {}
        weekly_slots = row.get("weekly_slots") or []
        residues = provenance.get("ignored_out_of_range_slots") or []

        if str(row.get("teacher_id") or "") != TEACHER_USER_ID:
            raise PreflightGateError(f"TEACHER_SCOPE_MISMATCH legacy={legacy_id}")
        if str(row.get("class_id") or "") != CLASS_ID:
            raise PreflightGateError(f"CLASS_SCOPE_MISMATCH legacy={legacy_id}")
        if str(row.get("school_id") or "") != SCHOOL_ID:
            raise PreflightGateError(f"SCHOOL_SCOPE_MISMATCH legacy={legacy_id}")
        if str(row.get("id") or "") != expected["proposed_id"]:
            raise PreflightGateError(f"PROPOSED_ID_MISMATCH legacy={legacy_id}")
        if str(row.get("component_name") or "") != expected["component_name"]:
            raise PreflightGateError(f"COMPONENT_NAME_MISMATCH legacy={legacy_id}")
        if provenance.get("phase") != PROVENANCE_PHASE:
            raise PreflightGateError(f"PROVENANCE_PHASE_MISMATCH legacy={legacy_id}")
        if provenance.get("state") != "DRY_RUN_ONLY":
            raise PreflightGateError(f"PROVENANCE_STATE_MISMATCH legacy={legacy_id}")
        if provenance.get("evidence") != REQUIRED_EVIDENCE:
            raise PreflightGateError(f"EVIDENCE_MISMATCH legacy={legacy_id}")
        if int(provenance.get("slots_per_day") or 0) != REQUIRED_SLOTS_PER_DAY:
            raise PreflightGateError(f"SLOTS_PER_DAY_MISMATCH legacy={legacy_id}")
        if len(weekly_slots) != expected["weekly_slots"]:
            raise PreflightGateError(
                f"WEEKLY_SLOTS_COUNT_MISMATCH legacy={legacy_id} expected={expected['weekly_slots']} actual={len(weekly_slots)}"
            )
        if len(residues) != expected["residue_count"]:
            raise PreflightGateError(
                f"RESIDUE_COUNT_MISMATCH legacy={legacy_id} expected={expected['residue_count']} actual={len(residues)}"
            )

        residue_slots: set[int] = set()
        for residue in residues:
            try:
                slot_number = int(residue.get("slot_number"))
            except (TypeError, ValueError) as exc:
                raise PreflightGateError(f"RESIDUE_SLOT_INVALID legacy={legacy_id}") from exc
            if slot_number <= REQUIRED_SLOTS_PER_DAY:
                raise PreflightGateError(
                    f"RESIDUE_NOT_OUT_OF_RANGE legacy={legacy_id} slot={slot_number} limit={REQUIRED_SLOTS_PER_DAY}"
                )
            residue_slots.add(slot_number)
        if residue_slots != expected["residue_slots"]:
            raise PreflightGateError(
                f"RESIDUE_SLOT_SET_MISMATCH legacy={legacy_id} expected={sorted(expected['residue_slots'])} actual={sorted(residue_slots)}"
            )

        if settings.get("enabled") is not True or settings.get("profile") != "regular":
            raise PreflightGateError(f"DIARY_PROFILE_INVALID legacy={legacy_id}")

        weekly_counts[len(weekly_slots)] += 1
        residue_counts[len(residues)] += 1

    excluded = [
        row for row in (report.get("details") or [])
        if row.get("state") == "blocked"
    ]
    blocker_counts: Counter[str] = Counter()
    for row in excluded:
        for blocker in row.get("blockers") or []:
            blocker_counts[str(blocker)] += 1

    return {
        "manifest": manifest,
        "manifest_sha256": actual_sha,
        "ready": actual_count,
        "source_missing_total": int(summary.get("missing_total") or 0),
        "source_blocked": int(summary.get("blocked") or 0),
        "excluded_blockers": dict(sorted(blocker_counts.items())),
        "weekly_slots_counts": {str(k): v for k, v in sorted(weekly_counts.items())},
        "residue_counts": {str(k): v for k, v in sorted(residue_counts.items())},
    }


def write_backup_directory(
    backup_dir: Path,
    *,
    validated: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=False)

    files: dict[str, Any] = {
        "manifest.json": validated.get("manifest") or [],
        "scope.json": bundle.get("scope") or {},
    }
    for name, docs in (bundle.get("collections") or {}).items():
        files[f"{name}.json"] = docs

    checksums: dict[str, str] = {}
    counts: dict[str, int] = {}
    for filename, payload in files.items():
        path = backup_dir / filename
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        checksums[filename] = sha256_file(path)
        if isinstance(payload, list):
            counts[filename] = len(payload)

    metadata = {
        "mode": BACKUP_MODE,
        "mutates_database": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "academic_year": ACADEMIC_YEAR,
        "teacher_user_id": TEACHER_USER_ID,
        "class_id": CLASS_ID,
        "school_id": SCHOOL_ID,
        "manifest_sha256": validated["manifest_sha256"],
        "second_wave_2c_ready": validated["ready"],
        "source_missing_total": validated["source_missing_total"],
        "source_blocked": validated["source_blocked"],
        "excluded_blockers": validated["excluded_blockers"],
        "weekly_slots_counts": validated["weekly_slots_counts"],
        "residue_counts": validated["residue_counts"],
        "file_counts": counts,
        "file_sha256": checksums,
    }
    metadata_path = backup_dir / "backup-metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    checksums[metadata_path.name] = sha256_file(metadata_path)

    bundle_digest = sha256_value({"file_sha256": checksums})
    seal = {
        "backup_bundle_sha256": bundle_digest,
        "files": checksums,
    }
    (backup_dir / "BACKUP-SEAL.json").write_text(
        json.dumps(seal, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {**metadata, **seal}


async def run_preflight(db, *, backup_dir: Path) -> dict[str, Any]:
    assert_script_read_only()
    validate_persistent_backup_path(backup_dir)

    source = await collect_manifest(
        db,
        teacher_user_id=TEACHER_USER_ID,
        class_id=CLASS_ID,
        academic_year=ACADEMIC_YEAR,
    )
    validated = validate_2c_report(source)

    bundle = await collect_backup_bundle(
        db,
        validated["manifest"],
        academic_year=ACADEMIC_YEAR,
    )
    backup = write_backup_directory(
        backup_dir,
        validated=validated,
        bundle=bundle,
    )

    return {
        "validated": validated,
        "backup": backup,
        "backup_dir": str(backup_dir),
    }


def print_compact(result: Mapping[str, Any]) -> None:
    v = result["validated"]
    backup = result["backup"]
    print("=== DVD SEGUNDA ONDA 2C — PREFLIGHT READ-ONLY ===")
    print("READY_2C:", v["ready"])
    print("ESPERADO:", APPROVED_READY_COUNT)
    print("MANIFEST_SHA256:", v["manifest_sha256"])
    print("SHA_ESPERADO:", APPROVED_MANIFEST_SHA256)
    print("HASH_MATCH: SIM")
    print("SOURCE_MISSING_TOTAL:", v["source_missing_total"])
    print("SOURCE_BLOCKED_EXCLUDED:", v["source_blocked"])
    print("EXCLUDED_BLOCKERS:", v["excluded_blockers"])
    print("WEEKLY_SLOTS_COUNTS:", v["weekly_slots_counts"])
    print("RESIDUE_COUNTS:", v["residue_counts"])
    print("BACKUP_DIR:", result["backup_dir"])
    print("BACKUP_SHA256:", backup["backup_bundle_sha256"])
    print("MONGO_WRITES: 0")
    print("ATIVACAO_EXECUTADA: NAO")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", required=True)
    args = parser.parse_args()

    backup_dir = Path(args.backup_dir)
    validate_persistent_backup_path(backup_dir)

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc")]
        result = await run_preflight(db, backup_dir=backup_dir)
        print_compact(result)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
