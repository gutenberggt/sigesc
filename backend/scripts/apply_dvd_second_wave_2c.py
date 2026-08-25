"""Segunda Onda DVD 2C — apply/rollback controlado e selado.

Default: DRY-RUN, sem escrita no MongoDB.
Apply: exige --apply + --confirm APPLY-DVD-SECOND-WAVE-2C-2.
Rollback: exige --rollback + --confirm ROLLBACK-DVD-SECOND-WAVE-2C-2.

Fonte autorizativa:
- manifesto 2C de 2 vínculos da professora/turma seladas;
- evidência declared_grid_plus_exact_workload;
- resíduos estritamente acima de slots_per_day=7;
- manifesto SHA-256 aprovado em produção;
- backup persistente selado pelo preflight 2C e SHA-256 aprovado.

Os dois casos no_out_of_range_residue permanecem fora desta onda.
Qualquer drift no backup, baseline, manifesto vivo ou escopo falha fechado.
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
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from scripts import apply_dvd_second_wave_2a as base  # noqa: E402
from scripts import prepare_dvd_second_wave_2c as preflight  # noqa: E402
from scripts.remediate_dvd_out_of_range_schedule_p0 import (  # noqa: E402
    collect_manifest,
    manifest_digest,
)

load_dotenv(BACKEND_DIR / ".env")

ACADEMIC_YEAR = 2026
TEACHER_USER_ID = preflight.TEACHER_USER_ID
CLASS_ID = preflight.CLASS_ID
SCHOOL_ID = preflight.SCHOOL_ID
APPROVED_READY_COUNT = 2
APPROVED_MANIFEST_SHA256 = "09aa29dd9c535c1b83de8390a14c24d6cf44d77e7eb811530c87dc8222cc0223"
APPROVED_BACKUP_BUNDLE_SHA256 = "02b0b0e64fa1d208dfd9a22a56c69c6028df9e3157b61beeb77e93bdb6430975"
PERSISTENT_BACKUP_DIR = Path("/data/sigesc-dvd-backups/dvd-second-wave-2c-preflight-v1")
PERSISTENT_RECEIPT_DIR = Path("/data/sigesc-dvd-backups/receipts/second-wave-2c")
APPLY_PHASE = "SECOND_WAVE_2C"
APPLY_CONFIRMATION = "APPLY-DVD-SECOND-WAVE-2C-2"
ROLLBACK_CONFIRMATION = "ROLLBACK-DVD-SECOND-WAVE-2C-2"
ACTOR = "dvd-second-wave-2c"
EXPECTED_SOURCE_MISSING_TOTAL = 4
EXPECTED_SOURCE_BLOCKED = 2
EXPECTED_EXCLUDED_BLOCKERS = {"no_out_of_range_residue": 2}
EXPECTED_WEEKLY_SLOTS_COUNTS = {"3": 1, "4": 1}
EXPECTED_RESIDUE_COUNTS = {"5": 2}

SecondWaveGateError = base.SecondWaveGateError


def _configure_base() -> None:
    """Configura helpers compartilhados para proveniência exclusiva da 2C."""
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


def _validated_report_from_backup(
    manifest: list[dict[str, Any]],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Reaplica ao manifesto selado as mesmas invariantes estruturais do preflight."""
    report = {
        "summary": {
            "ready": metadata.get("second_wave_2c_ready"),
            "manifest_sha256": metadata.get("manifest_sha256"),
            "missing_total": metadata.get("source_missing_total"),
            "blocked": metadata.get("source_blocked"),
        },
        "manifest": manifest,
        "details": [],
    }
    return preflight.validate_2c_report(report)


def load_and_verify_backup(
    backup_dir: Path,
    *,
    expected_manifest_sha256: str = APPROVED_MANIFEST_SHA256,
    expected_count: int = APPROVED_READY_COUNT,
    expected_backup_sha256: str = APPROVED_BACKUP_BUNDLE_SHA256,
) -> dict[str, Any]:
    """Valida integralmente o bundle 2C antes de qualquer caminho de escrita."""
    preflight.validate_persistent_backup_path(backup_dir)

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
    if metadata.get("mode") != preflight.BACKUP_MODE:
        raise SecondWaveGateError(
            f"BACKUP_METADATA_MODE_INVALID mode={metadata.get('mode')}"
        )
    if metadata.get("mutates_database") is not False:
        raise SecondWaveGateError("BACKUP_METADATA_MUTATION_FLAG_INVALID")
    if int(metadata.get("academic_year") or 0) != ACADEMIC_YEAR:
        raise SecondWaveGateError("BACKUP_METADATA_ACADEMIC_YEAR_INVALID")
    if str(metadata.get("teacher_user_id") or "") != TEACHER_USER_ID:
        raise SecondWaveGateError("BACKUP_METADATA_TEACHER_SCOPE_INVALID")
    if str(metadata.get("class_id") or "") != CLASS_ID:
        raise SecondWaveGateError("BACKUP_METADATA_CLASS_SCOPE_INVALID")
    if str(metadata.get("school_id") or "") != SCHOOL_ID:
        raise SecondWaveGateError("BACKUP_METADATA_SCHOOL_SCOPE_INVALID")
    if str(metadata.get("manifest_sha256") or "") != expected_manifest_sha256:
        raise SecondWaveGateError("BACKUP_METADATA_MANIFEST_HASH_MISMATCH")
    if int(metadata.get("second_wave_2c_ready") or 0) != expected_count:
        raise SecondWaveGateError(
            f"BACKUP_METADATA_COUNT_MISMATCH expected={expected_count} "
            f"actual={metadata.get('second_wave_2c_ready')}"
        )
    if int(metadata.get("source_missing_total") or 0) != EXPECTED_SOURCE_MISSING_TOTAL:
        raise SecondWaveGateError("BACKUP_METADATA_SOURCE_MISSING_TOTAL_INVALID")
    if int(metadata.get("source_blocked") or 0) != EXPECTED_SOURCE_BLOCKED:
        raise SecondWaveGateError("BACKUP_METADATA_SOURCE_BLOCKED_INVALID")
    if (metadata.get("excluded_blockers") or {}) != EXPECTED_EXCLUDED_BLOCKERS:
        raise SecondWaveGateError("BACKUP_METADATA_EXCLUDED_BLOCKERS_INVALID")
    if (metadata.get("weekly_slots_counts") or {}) != EXPECTED_WEEKLY_SLOTS_COUNTS:
        raise SecondWaveGateError("BACKUP_METADATA_WEEKLY_SLOTS_COUNTS_INVALID")
    if (metadata.get("residue_counts") or {}) != EXPECTED_RESIDUE_COUNTS:
        raise SecondWaveGateError("BACKUP_METADATA_RESIDUE_COUNTS_INVALID")

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

    validated = _validated_report_from_backup(manifest, metadata)
    if validated["manifest_sha256"] != expected_manifest_sha256:
        raise SecondWaveGateError("SEALED_MANIFEST_PREFLIGHT_VALIDATION_HASH_MISMATCH")

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
    expected_manifest_sha256: str = APPROVED_MANIFEST_SHA256,
    expected_count: int = APPROVED_READY_COUNT,
    expected_backup_sha256: str = APPROVED_BACKUP_BUNDLE_SHA256,
) -> dict[str, Any]:
    """Confirma baseline, manifesto vivo 2C e ausência de conflito lógico."""
    _configure_base()
    manifest = list(backup["manifest"])
    expected_ids = [str(row["id"]) for row in manifest]
    class_ids = [CLASS_ID]

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

    source = await collect_manifest(
        db,
        teacher_user_id=TEACHER_USER_ID,
        class_id=CLASS_ID,
        academic_year=ACADEMIC_YEAR,
    )
    live = preflight.validate_2c_report(source)
    live_manifest = live["manifest"]
    live_sha = str(live.get("manifest_sha256") or "")
    live_count = int(live.get("ready") or 0)

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
    if live["source_missing_total"] != EXPECTED_SOURCE_MISSING_TOTAL:
        raise SecondWaveGateError("LIVE_SOURCE_MISSING_TOTAL_DRIFT")
    if live["source_blocked"] != EXPECTED_SOURCE_BLOCKED:
        raise SecondWaveGateError("LIVE_SOURCE_BLOCKED_DRIFT")
    if live["excluded_blockers"] != EXPECTED_EXCLUDED_BLOCKERS:
        raise SecondWaveGateError("LIVE_EXCLUDED_BLOCKERS_DRIFT")
    if live["weekly_slots_counts"] != EXPECTED_WEEKLY_SLOTS_COUNTS:
        raise SecondWaveGateError("LIVE_WEEKLY_SLOTS_COUNTS_DRIFT")
    if live["residue_counts"] != EXPECTED_RESIDUE_COUNTS:
        raise SecondWaveGateError("LIVE_RESIDUE_COUNTS_DRIFT")

    all_active = await db.teacher_class_assignments.find(
        {"class_id": CLASS_ID, "deleted": {"$ne": True}},
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
) -> dict[str, Any]:
    _configure_base()
    return await base.apply_second_wave(
        db,
        backup,
        inspection,
        expected_manifest_sha256=APPROVED_MANIFEST_SHA256,
        expected_backup_sha256=APPROVED_BACKUP_BUNDLE_SHA256,
    )


async def rollback_second_wave(db, backup: Mapping[str, Any]) -> dict[str, Any]:
    _configure_base()
    return await base.rollback_second_wave(
        db,
        backup,
        expected_manifest_sha256=APPROVED_MANIFEST_SHA256,
        expected_backup_sha256=APPROVED_BACKUP_BUNDLE_SHA256,
    )


def write_receipt(receipt_dir: Path, payload: Mapping[str, Any]) -> Path:
    preflight.validate_persistent_backup_path(receipt_dir)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = receipt_dir / f"dvd-second-wave-2c-{payload.get('mode', 'unknown').lower()}-{stamp}.json"
    doc = dict(payload)
    doc["receipt_sha256"] = _sha256_value(payload)
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def print_dry_run(backup: Mapping[str, Any], inspection: Mapping[str, Any]) -> None:
    print("=== DVD SEGUNDA ONDA 2C — DRY-RUN CONTROLADO ===")
    print("MODE: DRY_RUN")
    print("BACKUP_INTEGRITY: APROVADA")
    print("BACKUP_BUNDLE_SHA256:", backup["backup_bundle_sha256"])
    print("SEALED_MANIFEST_SHA256:", inspection["sealed_manifest_sha256"])
    print(
        "LIVE_MANIFEST_SHA256:",
        inspection["live_manifest_sha256"] or "SKIPPED_ALREADY_APPLIED",
    )
    print("MANIFEST_MATCH: SIM")
    print("ESPERADO:", APPROVED_READY_COUNT)
    print("SOURCE_MISSING_TOTAL_SELADO:", EXPECTED_SOURCE_MISSING_TOTAL)
    print("SOURCE_BLOCKED_EXCLUDED:", EXPECTED_SOURCE_BLOCKED)
    print("EXCLUDED_BLOCKERS:", EXPECTED_EXCLUDED_BLOCKERS)
    print("ALREADY_PRESENT:", inspection["already_present"])
    print("TO_INSERT:", inspection["to_insert"])
    print("LOGICAL_CONFLICTS:", inspection["logical_conflicts"])
    print("MONGO_WRITES: 0")
    print("ATIVACAO_EXECUTADA: NAO")


async def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args()

    backup = load_and_verify_backup(PERSISTENT_BACKUP_DIR)
    preflight.validate_persistent_backup_path(PERSISTENT_RECEIPT_DIR)

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc")]

        if args.rollback:
            if args.confirm != ROLLBACK_CONFIRMATION:
                raise SecondWaveGateError(
                    f"ROLLBACK_CONFIRMATION_REQUIRED expected={ROLLBACK_CONFIRMATION}"
                )
            result = await rollback_second_wave(db, backup)
            payload = {
                "mode": "ROLLBACK",
                "result": result,
                "manifest_sha256": APPROVED_MANIFEST_SHA256,
                "backup_bundle_sha256": APPROVED_BACKUP_BUNDLE_SHA256,
                "expected_count": APPROVED_READY_COUNT,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            receipt = write_receipt(PERSISTENT_RECEIPT_DIR, payload)
            print("=== DVD SEGUNDA ONDA 2C — ROLLBACK ===")
            print("STATE:", result["state"])
            print("REMOVED:", result["removed"])
            print("BASELINE_RESTORED: SIM")
            print("RECEIPT:", receipt)
            return

        inspection = await inspect_state(db, backup)

        if not args.apply:
            print_dry_run(backup, inspection)
            return

        if args.confirm != APPLY_CONFIRMATION:
            raise SecondWaveGateError(
                f"APPLY_CONFIRMATION_REQUIRED expected={APPLY_CONFIRMATION}"
            )

        result = await apply_second_wave(db, backup, inspection)
        payload = {
            "mode": "APPLY",
            "result": result,
            "manifest_sha256": APPROVED_MANIFEST_SHA256,
            "backup_bundle_sha256": APPROVED_BACKUP_BUNDLE_SHA256,
            "expected_count": APPROVED_READY_COUNT,
            "source_missing_total": EXPECTED_SOURCE_MISSING_TOTAL,
            "excluded_blockers": EXPECTED_EXCLUDED_BLOCKERS,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        receipt = write_receipt(PERSISTENT_RECEIPT_DIR, payload)

        print("=== DVD SEGUNDA ONDA 2C — APPLY CONTROLADO ===")
        print("STATE:", result["state"])
        print("INSERTED:", result["inserted"])
        print("POSTCHECK:", f"{result['postcheck']}/{APPROVED_READY_COUNT}")
        print("MANIFEST_SHA256:", APPROVED_MANIFEST_SHA256)
        print("BACKUP_BUNDLE_SHA256:", APPROVED_BACKUP_BUNDLE_SHA256)
        print("ACTIVATION_EXECUTED:", "SIM" if result["state"] == "applied" else "JA_ESTAVA_APLICADO")
        print("RECEIPT:", receipt)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
