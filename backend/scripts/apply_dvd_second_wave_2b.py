"""Segunda Onda DVD 2B — apply/rollback controlado com gates fail-closed.

Default: DRY-RUN, sem escrita no MongoDB.
Apply: exige --apply + --confirm APPLY-DVD-SECOND-WAVE-2B-13.
Rollback: exige --rollback + --confirm ROLLBACK-DVD-SECOND-WAVE-2B-13.

Fonte autorizativa:
- manifesto 2B de 13 vínculos com recuperação determinística;
- todos com recovery_state=time_recoverable_unique_school_shift;
- SHA-256 do manifesto aprovado em produção;
- backup persistente selado pelo preflight 2B e SHA-256 aprovado.

Qualquer drift no backup, baseline, recovery state ou manifesto vivo falha fechado.
"""
from __future__ import annotations

import argparse
import asyncio
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

from scripts import apply_dvd_second_wave_2a as base  # noqa: E402
from scripts.audit_dvd_first_wave_manifest import (  # noqa: E402
    collect_first_wave_manifest,
    manifest_digest,
)
from scripts.prepare_dvd_second_wave_2b import (  # noqa: E402
    ALLOWED_RECOVERY_STATES,
    BACKUP_MODE,
    PERSISTENT_BACKUP_ROOT,
    select_second_wave_2b,
    validate_persistent_backup_path,
)

load_dotenv(BACKEND_DIR / ".env")

APPROVED_MANIFEST_SHA256 = "4d84e76b7236d2e6c5e0b8199165aa1e034d6d2529ceed05d248226ff9af72fc"
APPROVED_READY_COUNT = 13
APPROVED_BACKUP_BUNDLE_SHA256 = "b481670bb416429254d1efb066ef614a50c2bf053957bd078fe5eba3ea8f81f6"
DEFAULT_REFERENCE_DATE = "2026-08-18"
PERSISTENT_BACKUP_DIR = Path("/data/sigesc-dvd-backups/dvd-second-wave-2b-preflight-v1")
PERSISTENT_RECEIPT_DIR = Path("/data/sigesc-dvd-backups/receipts/second-wave-2b")
SCHEDULE_SOURCE = "deterministic_recovery"
REQUIRED_RECOVERY_STATE = "time_recoverable_unique_school_shift"
REQUIRED_WEEKLY_SLOTS = 5
APPLY_PHASE = "SECOND_WAVE_2B"
APPLY_CONFIRMATION = "APPLY-DVD-SECOND-WAVE-2B-13"
ROLLBACK_CONFIRMATION = "ROLLBACK-DVD-SECOND-WAVE-2B-13"
ACTOR = "dvd-second-wave-2b"

SecondWaveGateError = base.SecondWaveGateError


def _configure_base() -> None:
    """Configura os helpers compartilhados para proveniência exclusiva da 2B."""
    base.APPLY_PHASE = APPLY_PHASE
    base.ACTOR = ACTOR


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _target_key(doc: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(doc.get("teacher_id") or ""),
        str(doc.get("class_id") or ""),
        str(doc.get("component_id") or ""),
    )


def load_and_verify_backup(
    backup_dir: Path,
    *,
    expected_manifest_sha256: str,
    expected_count: int,
    expected_backup_sha256: str,
) -> dict[str, Any]:
    """Valida integralmente o bundle 2B antes de qualquer acesso de escrita."""
    validate_persistent_backup_path(backup_dir)

    seal_path = backup_dir / "BACKUP-SEAL.json"
    metadata_path = backup_dir / "backup-metadata.json"
    manifest_path = backup_dir / "manifest.json"
    before_path = backup_dir / "teacher_class_assignments_before.json"

    for path in (seal_path, metadata_path, manifest_path, before_path):
        if not path.is_file():
            raise SecondWaveGateError(f"BACKUP_FILE_MISSING path={path}")

    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    sealed_files = seal.get("files")
    if not isinstance(sealed_files, dict) or not sealed_files:
        raise SecondWaveGateError("BACKUP_SEAL_INVALID files ausente/vazio")

    for name, expected_hash in sorted(sealed_files.items()):
        path = backup_dir / name
        if not path.is_file():
            raise SecondWaveGateError(f"BACKUP_FILE_MISSING path={path}")
        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
            raise SecondWaveGateError(
                f"BACKUP_FILE_HASH_MISMATCH file={name} "
                f"expected={expected_hash} actual={actual_hash}"
            )

    calculated_bundle = _sha256_value({"file_sha256": sealed_files})
    sealed_bundle = str(seal.get("backup_bundle_sha256") or "")
    if calculated_bundle != sealed_bundle:
        raise SecondWaveGateError(
            f"BACKUP_BUNDLE_SEAL_MISMATCH sealed={sealed_bundle} calculated={calculated_bundle}"
        )
    if calculated_bundle != expected_backup_sha256:
        raise SecondWaveGateError(
            f"BACKUP_BUNDLE_NOT_APPROVED expected={expected_backup_sha256} actual={calculated_bundle}"
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("mode") != BACKUP_MODE:
        raise SecondWaveGateError(
            f"BACKUP_METADATA_MODE_INVALID mode={metadata.get('mode')}"
        )
    if metadata.get("mutates_database") is not False:
        raise SecondWaveGateError("BACKUP_METADATA_MUTATION_FLAG_INVALID")
    if str(metadata.get("manifest_sha256") or "") != expected_manifest_sha256:
        raise SecondWaveGateError(
            "BACKUP_METADATA_MANIFEST_HASH_MISMATCH "
            f"expected={expected_manifest_sha256} actual={metadata.get('manifest_sha256')}"
        )
    if int(metadata.get("second_wave_2b_ready") or 0) != expected_count:
        raise SecondWaveGateError(
            f"BACKUP_METADATA_COUNT_MISMATCH expected={expected_count} "
            f"actual={metadata.get('second_wave_2b_ready')}"
        )

    recovery_states = metadata.get("recovery_states") or {}
    if recovery_states != {REQUIRED_RECOVERY_STATE: expected_count}:
        raise SecondWaveGateError(
            "BACKUP_METADATA_RECOVERY_STATES_INVALID "
            f"actual={recovery_states}"
        )
    weekly_slots_counts = metadata.get("weekly_slots_counts") or {}
    if weekly_slots_counts != {str(REQUIRED_WEEKLY_SLOTS): expected_count}:
        raise SecondWaveGateError(
            "BACKUP_METADATA_WEEKLY_SLOTS_INVALID "
            f"actual={weekly_slots_counts}"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise SecondWaveGateError("BACKUP_MANIFEST_INVALID expected=list")
    if len(manifest) != expected_count:
        raise SecondWaveGateError(
            f"SEALED_MANIFEST_COUNT_MISMATCH expected={expected_count} actual={len(manifest)}"
        )

    sealed_manifest_sha = manifest_digest(manifest)
    if sealed_manifest_sha != expected_manifest_sha256:
        raise SecondWaveGateError(
            f"SEALED_MANIFEST_HASH_MISMATCH expected={expected_manifest_sha256} "
            f"actual={sealed_manifest_sha}"
        )

    ids = [str(row.get("id") or "") for row in manifest]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise SecondWaveGateError("SEALED_MANIFEST_IDS_INVALID missing_or_duplicate_id")

    target_keys = [_target_key(row) for row in manifest]
    if any(not all(key) for key in target_keys) or len(target_keys) != len(set(target_keys)):
        raise SecondWaveGateError(
            "SEALED_MANIFEST_TARGET_KEYS_INVALID missing_or_duplicate_target"
        )

    for row in manifest:
        provenance = row.get("cutover_provenance") or {}
        settings = row.get("diary_settings") or {}
        weekly_slots = row.get("weekly_slots") or []

        if provenance.get("schedule_source") != SCHEDULE_SOURCE:
            raise SecondWaveGateError("SEALED_MANIFEST_NON_DETERMINISTIC_SOURCE")
        if provenance.get("recovery_state") != REQUIRED_RECOVERY_STATE:
            raise SecondWaveGateError(
                "SEALED_MANIFEST_RECOVERY_STATE_INVALID "
                f"id={row.get('id')} state={provenance.get('recovery_state')}"
            )
        if len(weekly_slots) != REQUIRED_WEEKLY_SLOTS:
            raise SecondWaveGateError(
                "SEALED_MANIFEST_WEEKLY_SLOTS_COUNT_INVALID "
                f"id={row.get('id')} count={len(weekly_slots)}"
            )
        if settings.get("enabled") is not True or settings.get("profile") != "regular":
            raise SecondWaveGateError("SEALED_MANIFEST_DIARY_PROFILE_INVALID")

    before = json.loads(before_path.read_text(encoding="utf-8"))
    if not isinstance(before, list):
        raise SecondWaveGateError("BACKUP_BEFORE_INVALID expected=list")

    return {
        "seal": seal,
        "metadata": metadata,
        "manifest": manifest,
        "before": before,
        "manifest_sha256": sealed_manifest_sha,
        "backup_bundle_sha256": calculated_bundle,
    }


async def inspect_state(
    db,
    backup: Mapping[str, Any],
    *,
    academic_year: int,
    reference_date: str,
    tenant_id: Optional[str],
    expected_manifest_sha256: str,
    expected_count: int,
    expected_backup_sha256: str,
) -> dict[str, Any]:
    """Confirma baseline, manifesto vivo e ausência de conflito lógico."""
    _configure_base()
    manifest = list(backup["manifest"])
    expected_ids = [str(row["id"]) for row in manifest]
    class_ids = sorted(
        {
            str(row.get("class_id") or "")
            for row in manifest
            if row.get("class_id")
        }
    )

    existing_expected = await db.teacher_class_assignments.find(
        {"id": {"$in": expected_ids}},
        {"_id": 0},
    ).to_list(expected_count + 10)
    existing_by_id = {
        str(row.get("id")): row for row in existing_expected if row.get("id")
    }

    if existing_expected:
        if len(existing_expected) != expected_count or len(existing_by_id) != expected_count:
            raise SecondWaveGateError(
                "PARTIAL_OR_DUPLICATE_APPLY_DETECTED "
                f"expected={expected_count} rows={len(existing_expected)} "
                f"unique_ids={len(existing_by_id)}"
            )
        base._verify_applied_docs(
            existing_by_id,
            manifest,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_backup_sha256=expected_backup_sha256,
        )
        return {
            "state": "already_applied",
            "sealed_manifest_sha256": backup["manifest_sha256"],
            "live_manifest_sha256": None,
            "manifest_match": True,
            "already_present": expected_count,
            "to_insert": 0,
            "logical_conflicts": 0,
            "expected_ids": expected_ids,
            "class_ids": class_ids,
        }

    current_scope = await base._current_scope_assignments(db, class_ids)
    base._assert_baseline_unchanged(current_scope, list(backup["before"]))

    source = await collect_first_wave_manifest(
        db,
        academic_year=academic_year,
        reference_date=reference_date,
        tenant_id=tenant_id,
    )
    live = select_second_wave_2b(source)
    live_summary = live["summary"]
    live_manifest = live["manifest"]
    live_sha = str(live_summary.get("manifest_sha256") or "")
    live_count = int(live_summary.get("second_wave_2b_ready") or 0)

    if live_count != expected_count:
        raise SecondWaveGateError(
            f"LIVE_MANIFEST_COUNT_MISMATCH expected={expected_count} actual={live_count}"
        )
    if live_sha != expected_manifest_sha256:
        raise SecondWaveGateError(
            f"LIVE_MANIFEST_HASH_MISMATCH expected={expected_manifest_sha256} actual={live_sha}"
        )
    if _canonical_json(live_manifest) != _canonical_json(manifest):
        raise SecondWaveGateError("LIVE_MANIFEST_CONTENT_MISMATCH sealed_vs_recalculated")

    recovery_states = live_summary.get("recovery_states") or {}
    if recovery_states != {REQUIRED_RECOVERY_STATE: expected_count}:
        raise SecondWaveGateError(
            f"LIVE_RECOVERY_STATES_MISMATCH actual={recovery_states}"
        )
    weekly_slots_counts = live_summary.get("weekly_slots_counts") or {}
    if weekly_slots_counts != {str(REQUIRED_WEEKLY_SLOTS): expected_count}:
        raise SecondWaveGateError(
            f"LIVE_WEEKLY_SLOTS_MISMATCH actual={weekly_slots_counts}"
        )

    all_active = await db.teacher_class_assignments.find(
        {"class_id": {"$in": class_ids}, "deleted": {"$ne": True}},
        {
            "_id": 0,
            "id": 1,
            "teacher_id": 1,
            "class_id": 1,
            "component_id": 1,
        },
    ).to_list(50000)
    active_keys: dict[tuple[str, str, str], list[str]] = {}
    for row in all_active:
        key = _target_key(row)
        if all(key):
            active_keys.setdefault(key, []).append(str(row.get("id") or ""))

    conflicts = []
    for proposed in manifest:
        key = _target_key(proposed)
        if key in active_keys:
            conflicts.append({"key": key, "existing_ids": active_keys[key]})
    if conflicts:
        raise SecondWaveGateError(
            f"LOGICAL_TARGET_CONFLICTS count={len(conflicts)} first={conflicts[0]}"
        )

    return {
        "state": "ready",
        "sealed_manifest_sha256": backup["manifest_sha256"],
        "live_manifest_sha256": live_sha,
        "manifest_match": True,
        "already_present": 0,
        "to_insert": expected_count,
        "logical_conflicts": 0,
        "expected_ids": expected_ids,
        "class_ids": class_ids,
    }


async def apply_second_wave(
    db,
    backup: Mapping[str, Any],
    inspection: Mapping[str, Any],
    *,
    expected_manifest_sha256: str,
    expected_backup_sha256: str,
) -> dict[str, Any]:
    _configure_base()
    return await base.apply_second_wave(
        db,
        backup,
        inspection,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_backup_sha256=expected_backup_sha256,
    )


async def rollback_second_wave(
    db,
    backup: Mapping[str, Any],
    *,
    expected_manifest_sha256: str,
    expected_backup_sha256: str,
) -> dict[str, Any]:
    _configure_base()
    return await base.rollback_second_wave(
        db,
        backup,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_backup_sha256=expected_backup_sha256,
    )


def write_receipt(receipt_dir: Path, payload: Mapping[str, Any]) -> Path:
    validate_persistent_backup_path(receipt_dir)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = receipt_dir / f"dvd-second-wave-2b-{payload.get('mode', 'unknown').lower()}-{stamp}.json"
    doc = dict(payload)
    doc["receipt_sha256"] = _sha256_value(payload)
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def print_dry_run(
    backup: Mapping[str, Any],
    inspection: Mapping[str, Any],
    *,
    expected_count: int,
) -> None:
    print("=== DVD SEGUNDA ONDA 2B — DRY-RUN CONTROLADO ===")
    print("MODE: DRY_RUN")
    print("BACKUP_INTEGRITY: APROVADA")
    print("BACKUP_BUNDLE_SHA256:", backup["backup_bundle_sha256"])
    print("SEALED_MANIFEST_SHA256:", inspection["sealed_manifest_sha256"])
    print(
        "LIVE_MANIFEST_SHA256:",
        inspection["live_manifest_sha256"] or "SKIPPED_ALREADY_APPLIED",
    )
    print("MANIFEST_MATCH: SIM")
    print("RECOVERY_STATE:", REQUIRED_RECOVERY_STATE)
    print("WEEKLY_SLOTS_POR_VINCULO:", REQUIRED_WEEKLY_SLOTS)
    print("ESPERADO:", expected_count)
    print("ALREADY_PRESENT:", inspection["already_present"])
    print("TO_INSERT:", inspection["to_insert"])
    print("LOGICAL_CONFLICTS:", inspection["logical_conflicts"])
    print("MONGO_WRITES: 0")
    print("ATIVACAO_EXECUTADA: NAO")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--academic-year", type=int, default=2026)
    parser.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE)
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--expected-manifest-sha256", default=APPROVED_MANIFEST_SHA256)
    parser.add_argument("--expected-count", type=int, default=APPROVED_READY_COUNT)
    parser.add_argument("--expected-backup-sha256", default=APPROVED_BACKUP_BUNDLE_SHA256)
    parser.add_argument("--backup-dir", default=str(PERSISTENT_BACKUP_DIR))
    parser.add_argument("--receipt-dir", default=str(PERSISTENT_RECEIPT_DIR))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args()

    backup_dir = Path(args.backup_dir)
    receipt_dir = Path(args.receipt_dir)
    validate_persistent_backup_path(backup_dir)
    validate_persistent_backup_path(receipt_dir)

    backup = load_and_verify_backup(
        backup_dir,
        expected_manifest_sha256=args.expected_manifest_sha256,
        expected_count=args.expected_count,
        expected_backup_sha256=args.expected_backup_sha256,
    )

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc")]

        if args.rollback:
            if args.confirm != ROLLBACK_CONFIRMATION:
                raise SecondWaveGateError(
                    f"ROLLBACK_CONFIRMATION_REQUIRED expected={ROLLBACK_CONFIRMATION}"
                )
            result = await rollback_second_wave(
                db,
                backup,
                expected_manifest_sha256=args.expected_manifest_sha256,
                expected_backup_sha256=args.expected_backup_sha256,
            )
            payload = {
                "mode": "ROLLBACK",
                "result": result,
                "manifest_sha256": args.expected_manifest_sha256,
                "backup_bundle_sha256": args.expected_backup_sha256,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            receipt = write_receipt(receipt_dir, payload)
            print("=== DVD SEGUNDA ONDA 2B — ROLLBACK ===")
            print("STATE:", result["state"])
            print("REMOVED:", result["removed"])
            print("BASELINE_RESTORED: SIM")
            print("RECEIPT:", receipt)
            return

        inspection = await inspect_state(
            db,
            backup,
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            tenant_id=args.tenant_id,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_count=args.expected_count,
            expected_backup_sha256=args.expected_backup_sha256,
        )

        if not args.apply:
            print_dry_run(backup, inspection, expected_count=args.expected_count)
            return

        if args.confirm != APPLY_CONFIRMATION:
            raise SecondWaveGateError(
                f"APPLY_CONFIRMATION_REQUIRED expected={APPLY_CONFIRMATION}"
            )

        result = await apply_second_wave(
            db,
            backup,
            inspection,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_backup_sha256=args.expected_backup_sha256,
        )
        payload = {
            "mode": "APPLY",
            "result": result,
            "manifest_sha256": args.expected_manifest_sha256,
            "backup_bundle_sha256": args.expected_backup_sha256,
            "expected_count": args.expected_count,
            "recovery_state": REQUIRED_RECOVERY_STATE,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        receipt = write_receipt(receipt_dir, payload)

        print("=== DVD SEGUNDA ONDA 2B — APPLY CONTROLADO ===")
        print("STATE:", result["state"])
        print("INSERTED:", result["inserted"])
        print("POSTCHECK:", f"{result['postcheck']}/{args.expected_count}")
        print("MANIFEST_SHA256:", args.expected_manifest_sha256)
        print("BACKUP_BUNDLE_SHA256:", args.expected_backup_sha256)
        print("RECOVERY_STATE:", REQUIRED_RECOVERY_STATE)
        print(
            "ACTIVATION_EXECUTED:",
            "SIM" if result["state"] == "applied" else "JA_ESTAVA_APLICADO",
        )
        print("RECEIPT:", receipt)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
