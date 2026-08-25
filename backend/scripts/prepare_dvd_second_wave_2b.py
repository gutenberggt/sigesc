"""Segunda Onda DVD 2B — preflight selado e estritamente READ-ONLY.

Escopo auditado em produção em 2026-08-25:
- 13 vínculos atuais da 38E;
- somente ``schedule_source=deterministic_recovery``;
- todos com ``recovery_state=time_recoverable_unique_school_shift``;
- manifesto SHA-256 fixo;
- nenhuma escrita no MongoDB.

O preflight recalcula a 38E no banco atual, extrai somente o subconjunto 2B,
exige quantidade + hash aprovados, valida invariantes e gera backup selado do
pre-state. O CLI de produção exige que o backup seja gravado no volume
persistente ``/data/sigesc-dvd-backups``. Qualquer drift falha fechado.

Esta etapa NÃO contém apply nem rollback.
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
from typing import Any, Iterable, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from scripts.audit_dvd_first_wave_manifest import (  # noqa: E402
    collect_first_wave_manifest,
    manifest_digest,
)
from scripts.prepare_dvd_cutover_phase38g import (  # noqa: E402
    collect_backup_bundle,
    sha256_file,
    sha256_value,
)

load_dotenv(BACKEND_DIR / ".env")

APPROVED_MANIFEST_SHA256 = "4d84e76b7236d2e6c5e0b8199165aa1e034d6d2529ceed05d248226ff9af72fc"
APPROVED_READY_COUNT = 13
DEFAULT_REFERENCE_DATE = "2026-08-18"
SCHEDULE_SOURCE = "deterministic_recovery"
ALLOWED_RECOVERY_STATES = frozenset({"time_recoverable_unique_school_shift"})
PERSISTENT_BACKUP_ROOT = Path("/data/sigesc-dvd-backups")
BACKUP_MODE = "SECOND_WAVE_2B_PREFLIGHT_READ_ONLY"

MONGO_MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


class PreflightGateError(RuntimeError):
    pass


def assert_script_read_only() -> None:
    """Falha se este arquivo ganhar qualquer chamada de mutação Mongo."""
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
    """Impede repetir o erro operacional de selar backup em /tmp/overlay."""
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


def _target_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("teacher_id") or ""),
        str(row.get("class_id") or ""),
        str(row.get("component_id") or ""),
    )


def _source_legacy_id(row: Mapping[str, Any]) -> str:
    return str(
        (row.get("cutover_provenance") or {}).get("source_legacy_assignment_id")
        or ""
    )


def _sort_manifest(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    manifest = [dict(item) for item in items]
    manifest.sort(
        key=lambda row: (
            str(row.get("school_id") or ""),
            str(row.get("class_name") or "").casefold(),
            str(row.get("component_name") or "").casefold(),
            str(row.get("teacher_name") or "").casefold(),
        )
    )
    return manifest


def select_second_wave_2b(source_report: Mapping[str, Any]) -> dict[str, Any]:
    """Extrai deterministicamente somente os ready por recuperação 2B aprovada."""
    details = source_report.get("details") or []
    source_manifest = source_report.get("manifest") or []

    deterministic_ready = [
        row
        for row in details
        if row.get("first_wave_state") == "ready"
        and row.get("schedule_source") == SCHEDULE_SOURCE
    ]

    disallowed = [
        row
        for row in deterministic_ready
        if str(row.get("recovery_state") or "") not in ALLOWED_RECOVERY_STATES
    ]
    if disallowed:
        first = disallowed[0]
        raise PreflightGateError(
            "READY_RECOVERY_STATE_NOT_ALLOWED "
            f"count={len(disallowed)} first_legacy={first.get('legacy_assignment_id')} "
            f"state={first.get('recovery_state')}"
        )

    ready_ids = {
        str(row.get("legacy_assignment_id") or "")
        for row in deterministic_ready
        if row.get("legacy_assignment_id")
    }

    manifest = _sort_manifest(
        row
        for row in source_manifest
        if _source_legacy_id(row) in ready_ids
        and (row.get("cutover_provenance") or {}).get("schedule_source")
        == SCHEDULE_SOURCE
        and str((row.get("cutover_provenance") or {}).get("recovery_state") or "")
        in ALLOWED_RECOVERY_STATES
    )

    manifest_source_ids = [_source_legacy_id(row) for row in manifest]
    if set(manifest_source_ids) != ready_ids:
        raise PreflightGateError(
            "READY_DETAIL_MANIFEST_MISMATCH "
            f"details={len(ready_ids)} manifest={len(set(manifest_source_ids))}"
        )

    ids = [str(row.get("id") or "") for row in manifest]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise PreflightGateError("MANIFEST_IDS_INVALID missing_or_duplicate")

    if (
        any(not value for value in manifest_source_ids)
        or len(manifest_source_ids) != len(set(manifest_source_ids))
    ):
        raise PreflightGateError("MANIFEST_SOURCE_IDS_INVALID missing_or_duplicate")

    target_keys = [_target_key(row) for row in manifest]
    if any(not all(key) for key in target_keys) or len(target_keys) != len(set(target_keys)):
        raise PreflightGateError("MANIFEST_TARGET_KEYS_INVALID missing_or_duplicate")

    recovery_counts: Counter[str] = Counter()
    weekly_slots_counts: Counter[int] = Counter()

    for row in manifest:
        provenance = row.get("cutover_provenance") or {}
        settings = row.get("diary_settings") or {}
        recovery_state = str(provenance.get("recovery_state") or "")
        weekly_slots = row.get("weekly_slots") or []

        if provenance.get("schedule_source") != SCHEDULE_SOURCE:
            raise PreflightGateError("MANIFEST_NON_DETERMINISTIC_SCHEDULE_SOURCE")
        if recovery_state not in ALLOWED_RECOVERY_STATES:
            raise PreflightGateError(
                f"MANIFEST_RECOVERY_STATE_NOT_ALLOWED state={recovery_state}"
            )
        if not weekly_slots:
            raise PreflightGateError(
                f"MANIFEST_WEEKLY_SLOTS_EMPTY id={row.get('id')}"
            )
        if settings.get("enabled") is not True or settings.get("profile") != "regular":
            raise PreflightGateError("MANIFEST_DIARY_PROFILE_INVALID")

        recovery_counts[recovery_state] += 1
        weekly_slots_counts[len(weekly_slots)] += 1

    return {
        "meta": {
            "mode": "READ_ONLY_SECOND_WAVE_2B_MANIFEST",
            "mutates_database": False,
            "source_mode": (source_report.get("meta") or {}).get("mode"),
            "academic_year": (source_report.get("meta") or {}).get("academic_year"),
            "reference_date": (source_report.get("meta") or {}).get("reference_date"),
            "schedule_source": SCHEDULE_SOURCE,
            "allowed_recovery_states": sorted(ALLOWED_RECOVERY_STATES),
        },
        "summary": {
            "source_38e_ready": int(
                (source_report.get("summary") or {}).get("first_wave_ready") or 0
            ),
            "source_38e_manifest_sha256": (
                source_report.get("summary") or {}
            ).get("manifest_sha256"),
            "second_wave_2b_ready": len(manifest),
            "recovery_states": dict(sorted(recovery_counts.items())),
            "weekly_slots_counts": {
                str(key): value for key, value in sorted(weekly_slots_counts.items())
            },
            "manifest_sha256": manifest_digest(manifest),
        },
        "manifest": manifest,
    }


def validate_manifest_gate(
    summary: Mapping[str, Any],
    *,
    expected_sha256: str,
    expected_count: int,
) -> None:
    actual_sha = str(summary.get("manifest_sha256") or "")
    actual_count = int(summary.get("second_wave_2b_ready") or 0)
    if actual_sha != expected_sha256:
        raise PreflightGateError(
            f"MANIFEST_SHA256_MISMATCH expected={expected_sha256} actual={actual_sha}"
        )
    if actual_count != expected_count:
        raise PreflightGateError(
            f"MANIFEST_COUNT_MISMATCH expected={expected_count} actual={actual_count}"
        )


def write_backup_directory(
    backup_dir: Path,
    *,
    manifest_report: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Grava apenas arquivos e sela o pre-state; nunca toca no Mongo."""
    backup_dir.mkdir(parents=True, exist_ok=False)

    files: dict[str, Any] = {
        "manifest.json": manifest_report.get("manifest") or [],
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

    summary = manifest_report.get("summary") or {}
    metadata = {
        "mode": BACKUP_MODE,
        "mutates_database": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": summary.get("manifest_sha256"),
        "second_wave_2b_ready": summary.get("second_wave_2b_ready"),
        "source_38e_manifest_sha256": summary.get("source_38e_manifest_sha256"),
        "recovery_states": summary.get("recovery_states") or {},
        "weekly_slots_counts": summary.get("weekly_slots_counts") or {},
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


async def run_preflight(
    db,
    *,
    academic_year: int,
    reference_date: str,
    expected_sha256: str,
    expected_count: int,
    backup_dir: Path,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    assert_script_read_only()

    source = await collect_first_wave_manifest(
        db,
        academic_year=academic_year,
        reference_date=reference_date,
        tenant_id=tenant_id,
    )
    report = select_second_wave_2b(source)
    validate_manifest_gate(
        report["summary"],
        expected_sha256=expected_sha256,
        expected_count=expected_count,
    )

    bundle = await collect_backup_bundle(
        db,
        report["manifest"],
        academic_year=academic_year,
    )
    backup = write_backup_directory(
        backup_dir,
        manifest_report=report,
        bundle=bundle,
    )

    return {
        "meta": {
            "mode": BACKUP_MODE,
            "mutates_database": False,
            "academic_year": academic_year,
            "reference_date": reference_date,
            "tenant_id": tenant_id,
        },
        "summary": report["summary"],
        "backup": backup,
        "backup_dir": str(backup_dir),
    }


def print_compact(
    result: Mapping[str, Any],
    *,
    expected_sha256: str,
    expected_count: int,
) -> None:
    summary = result["summary"]
    backup = result["backup"]
    print("=== DVD SEGUNDA ONDA 2B — PREFLIGHT READ-ONLY ===")
    print("READY_2B:", summary["second_wave_2b_ready"])
    print("ESPERADO:", expected_count)
    print("MANIFEST_SHA256:", summary["manifest_sha256"])
    print("SHA_ESPERADO:", expected_sha256)
    print("HASH_MATCH: SIM")
    print("SOURCE_38E_READY:", summary["source_38e_ready"])
    print("SOURCE_38E_SHA256:", summary["source_38e_manifest_sha256"])
    print("RECOVERY_STATES:", summary["recovery_states"])
    print("WEEKLY_SLOTS_COUNTS:", summary["weekly_slots_counts"])
    print("BACKUP_DIR:", result["backup_dir"])
    print("BACKUP_SHA256:", backup["backup_bundle_sha256"])
    print("MONGO_WRITES: 0")
    print("ATIVACAO_EXECUTADA: NAO")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--academic-year", type=int, default=2026)
    parser.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE)
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--expected-manifest-sha256", default=APPROVED_MANIFEST_SHA256)
    parser.add_argument("--expected-count", type=int, default=APPROVED_READY_COUNT)
    parser.add_argument("--backup-dir", required=True)
    args = parser.parse_args()

    backup_dir = Path(args.backup_dir)
    validate_persistent_backup_path(backup_dir)

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        result = await run_preflight(
            client[os.environ.get("DB_NAME", "sigesc")],
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            expected_sha256=args.expected_manifest_sha256,
            expected_count=args.expected_count,
            backup_dir=backup_dir,
            tenant_id=args.tenant_id,
        )
        print_compact(
            result,
            expected_sha256=args.expected_manifest_sha256,
            expected_count=args.expected_count,
        )
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
