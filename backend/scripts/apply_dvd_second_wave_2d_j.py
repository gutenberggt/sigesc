"""Segunda Onda DVD 2D-J — apply/rollback controlado e selado.

Default: DRY-RUN, sem escrita no MongoDB.
Apply: exige --apply + --confirm APPLY-DVD-SECOND-WAVE-2D-J-2.
Rollback: exige --rollback + --confirm ROLLBACK-DVD-SECOND-WAVE-2D-J-2.

Fonte autorizativa imutável:
- preflight dual-profile homologado em produção;
- manifesto de exatamente 2 vínculos;
- MANIFEST_SHA256 aprovado;
- bundle persistente V2 e BACKUP_SHA256 aprovado;
- profile=regular, student_scope=all, valid_from=2026-08-18;
- evidência dual: mesmo componente/mesma escola + irmãos da professora/turma.

Qualquer drift de backup, baseline, manifesto vivo, perfil, horário, escopo ou
proveniência falha fechado antes do caminho de escrita.
"""
from __future__ import annotations

import argparse
import asyncio
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

from scripts import apply_dvd_second_wave_2a as apply_base  # noqa: E402
from scripts import prepare_dvd_second_wave_2d_j as preflight_base  # noqa: E402
from scripts import prepare_dvd_second_wave_2d_j_dual_profile_persistent as dual  # noqa: E402
from scripts import prepare_dvd_second_wave_2d_j_migration_aware as migration_aware  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

ACADEMIC_YEAR = 2026
REFERENCE_DATE = "2026-08-18"
TEACHER_USER_ID = preflight_base.TEACHER_USER_ID
STAFF_ID = preflight_base.STAFF_ID
CLASS_ID = preflight_base.CLASS_ID
SCHOOL_ID = preflight_base.SCHOOL_ID
APPROVED_READY_COUNT = 2
APPROVED_MANIFEST_SHA256 = "d55cf98685e6025f2ef988cc7df1cdfb2c307a5565a1a612b996614e026889c9"
APPROVED_BACKUP_BUNDLE_SHA256 = "8961e226b44dc760754c03a9ee41c545821249cc918a69b68dd2e6d9dbe094bd"
PERSISTENT_BACKUP_DIR = Path("/data/sigesc-dvd-backups/dvd-second-wave-2d-j-preflight-v2")
PERSISTENT_RECEIPT_DIR = Path("/data/sigesc-dvd-backups/receipts/second-wave-2d-j")
APPLY_PHASE = "SECOND_WAVE_2D_J"
APPLY_CONFIRMATION = "APPLY-DVD-SECOND-WAVE-2D-J-2"
ROLLBACK_CONFIRMATION = "ROLLBACK-DVD-SECOND-WAVE-2D-J-2"
ACTOR = "dvd-second-wave-2d-j"
EXPECTED_PROFILE = "regular"
EXPECTED_SCOPE = "all"
EXPECTED_VALID_FROM = "2026-08-18"
EXPECTED_SIBLING_COUNT = 7
EXPECTED_LEGACY_MIGRATION_ARTIFACTS = 2

EXPECTED_SIBLING_IDS = {
    "28477804-96b6-5e18-b5f8-d4022784022d",
    "2cb1fd7b-3eb9-59ff-b699-1ba7529112ed",
    "43db72dc-c1a5-51da-85e0-bf42f3feefa1",
    "92dd69ff-c9c4-5a7c-8cdb-2e519b623e38",
    "b1ed1194-3118-5d32-9fce-cd4ef9cb4093",
    "d3645603-7051-57c8-bcb2-f7326767e8e0",
    "ff7125fc-7753-5559-b816-8f6c125be93d",
}

EXPECTED_TARGETS = {
    "bd8273ec-2dfd-563a-80c7-38b7c32088f9": {
        "legacy_id": "1f08bfe3-b486-4266-81bc-2f03fe72a3a4",
        "component_id": "e90107dc-3276-4480-852b-91f617eefc67",
        "component_name": "Contação de Histórias e Iniciação Musical",
        "peer_id": "b7282075-118d-5a21-9639-5d71ec73f4c1",
        "workload": 5,
    },
    "332d4421-cb57-5a4b-bf2c-eb8878904373": {
        "legacy_id": "7d62a0df-c601-4288-b4ef-18093d3c37cf",
        "component_id": "7cce8ff9-9cd1-4737-a4ed-a61554a711dc",
        "component_name": "Higiene e Saúde",
        "peer_id": "9a7683a4-1801-5bc5-ac1e-713891251960",
        "workload": 3,
    },
}

SecondWaveGateError = apply_base.SecondWaveGateError


def _configure_base() -> None:
    apply_base.APPLY_PHASE = APPLY_PHASE
    apply_base.ACTOR = ACTOR


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _target_key(doc: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(doc.get("teacher_id") or ""),
        str(doc.get("class_id") or ""),
        str(doc.get("component_id") or ""),
    )


def _assert_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise SecondWaveGateError(f"{label} expected={expected!r} actual={actual!r}")


def validate_manifest_semantics(manifest: list[Mapping[str, Any]]) -> None:
    if len(manifest) != APPROVED_READY_COUNT:
        raise SecondWaveGateError(
            f"SEALED_MANIFEST_COUNT_MISMATCH expected={APPROVED_READY_COUNT} actual={len(manifest)}"
        )

    by_id = {str(row.get("id") or ""): row for row in manifest if row.get("id")}
    if set(by_id) != set(EXPECTED_TARGETS):
        raise SecondWaveGateError(
            "SEALED_MANIFEST_ID_SET_MISMATCH "
            f"expected={sorted(EXPECTED_TARGETS)} actual={sorted(by_id)}"
        )

    target_keys: list[tuple[str, str, str]] = []
    for assignment_id in sorted(EXPECTED_TARGETS):
        row = by_id[assignment_id]
        spec = EXPECTED_TARGETS[assignment_id]
        legacy_id = str(spec["legacy_id"])
        source_spec = preflight_base.APPROVED_TARGETS[legacy_id]
        settings = row.get("diary_settings") or {}
        provenance = row.get("cutover_provenance") or {}

        _assert_equal("MANIFEST_TEACHER_ID", str(row.get("teacher_id") or ""), TEACHER_USER_ID)
        _assert_equal("MANIFEST_CLASS_ID", str(row.get("class_id") or ""), CLASS_ID)
        _assert_equal("MANIFEST_SCHOOL_ID", str(row.get("school_id") or ""), SCHOOL_ID)
        _assert_equal("MANIFEST_COMPONENT_ID", str(row.get("component_id") or ""), spec["component_id"])
        _assert_equal("MANIFEST_COMPONENT_NAME", str(row.get("component_name") or ""), spec["component_name"])
        _assert_equal("MANIFEST_WEEKLY_SLOTS", row.get("weekly_slots") or [], source_spec["weekly_slots"])
        _assert_equal("MANIFEST_VALID_FROM", str(row.get("valid_from") or "")[:10], EXPECTED_VALID_FROM)
        _assert_equal("MANIFEST_VALID_UNTIL", row.get("valid_until"), None)
        _assert_equal("MANIFEST_SUBSTITUTE", row.get("is_substitute"), False)
        _assert_equal("MANIFEST_SOURCE", row.get("source"), "import")

        _assert_equal("MANIFEST_DIARY_ENABLED", settings.get("enabled"), True)
        _assert_equal("MANIFEST_DIARY_PROFILE", settings.get("profile"), EXPECTED_PROFILE)
        _assert_equal("MANIFEST_DIARY_SCOPE", settings.get("student_scope"), EXPECTED_SCOPE)
        _assert_equal("MANIFEST_DIARY_SCHEMA", settings.get("schema_version"), 1)

        _assert_equal("MANIFEST_PROVENANCE_PHASE", provenance.get("phase"), preflight_base.PROVENANCE_PHASE)
        _assert_equal("MANIFEST_PROVENANCE_STATE", provenance.get("state"), "DRY_RUN_ONLY")
        _assert_equal("MANIFEST_SOURCE_LEGACY", provenance.get("source_legacy_assignment_id"), legacy_id)
        _assert_equal("MANIFEST_EVIDENCE", provenance.get("evidence"), dual.REQUIRED_EVIDENCE)
        _assert_equal("MANIFEST_PROFILE_EVIDENCE", provenance.get("profile_evidence"), dual.DUAL_PROFILE_EVIDENCE)
        _assert_equal("MANIFEST_SCHEDULE_STATE", provenance.get("schedule_state"), "schedule_ready")
        _assert_equal("MANIFEST_SLOTS_PER_DAY", int(provenance.get("slots_per_day") or 0), preflight_base.REQUIRED_SLOTS_PER_DAY)
        _assert_equal("MANIFEST_WORKLOAD", int(provenance.get("workload") or 0), int(spec["workload"]))
        _assert_equal("MANIFEST_PEER_PROFILE", provenance.get("peer_profile"), EXPECTED_PROFILE)
        _assert_equal("MANIFEST_PEER_PROFILE_COUNT", int(provenance.get("peer_profile_count") or 0), 1)
        _assert_equal("MANIFEST_SAME_COMPONENT_COUNT", int(provenance.get("same_component_peer_count") or 0), 1)
        _assert_equal("MANIFEST_SIBLING_PROFILE_COUNT", int(provenance.get("sibling_profile_count") or 0), EXPECTED_SIBLING_COUNT)

        target_keys.append(_target_key(row))

    if len(target_keys) != len(set(target_keys)) or any(not all(key) for key in target_keys):
        raise SecondWaveGateError("SEALED_MANIFEST_TARGET_KEYS_INVALID")


def validate_peer_evidence(peer_evidence: Mapping[str, Any]) -> None:
    expected_legacy_ids = {str(spec["legacy_id"]) for spec in EXPECTED_TARGETS.values()}
    if set(peer_evidence) != expected_legacy_ids:
        raise SecondWaveGateError(
            "PEER_EVIDENCE_SET_MISMATCH "
            f"expected={sorted(expected_legacy_ids)} actual={sorted(peer_evidence)}"
        )

    by_legacy = {
        str(spec["legacy_id"]): spec
        for spec in EXPECTED_TARGETS.values()
    }
    for legacy_id in sorted(expected_legacy_ids):
        evidence = peer_evidence.get(legacy_id) or {}
        spec = by_legacy[legacy_id]
        _assert_equal("PEER_EVIDENCE_MODEL", evidence.get("evidence_model"), dual.DUAL_PROFILE_EVIDENCE)
        _assert_equal("PEER_EVIDENCE_PROFILE", evidence.get("profile"), EXPECTED_PROFILE)
        _assert_equal("PEER_EVIDENCE_SCOPE", evidence.get("student_scope"), EXPECTED_SCOPE)
        _assert_equal("PEER_EVIDENCE_PEER_COUNT", int(evidence.get("peer_count") or 0), 1)
        _assert_equal("PEER_EVIDENCE_SIBLING_COUNT", int(evidence.get("sibling_count") or 0), EXPECTED_SIBLING_COUNT)
        _assert_equal("PEER_EVIDENCE_PROFILE_COUNTS", evidence.get("profile_counts") or {}, {EXPECTED_PROFILE: 1})
        _assert_equal(
            "PEER_EVIDENCE_SIBLING_PROFILE_COUNTS",
            evidence.get("sibling_profile_counts") or {},
            {EXPECTED_PROFILE: EXPECTED_SIBLING_COUNT},
        )
        _assert_equal("PEER_EVIDENCE_SAME_COMPONENT_IDS", set(evidence.get("same_component_ids") or []), {spec["peer_id"]})
        _assert_equal("PEER_EVIDENCE_SIBLING_IDS", set(evidence.get("sibling_ids") or []), EXPECTED_SIBLING_IDS)


def load_and_verify_backup(
    backup_dir: Path,
    *,
    expected_manifest_sha256: str = APPROVED_MANIFEST_SHA256,
    expected_count: int = APPROVED_READY_COUNT,
    expected_backup_sha256: str = APPROVED_BACKUP_BUNDLE_SHA256,
) -> dict[str, Any]:
    preflight_base.validate_persistent_backup_path(backup_dir)

    seal_path = backup_dir / "BACKUP-SEAL.json"
    metadata_path = backup_dir / "backup-metadata.json"
    manifest_path = backup_dir / "manifest.json"
    before_path = backup_dir / "teacher_class_assignments_before.json"
    scope_path = backup_dir / "scope.json"

    for path in (seal_path, metadata_path, manifest_path, before_path, scope_path):
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
        actual_hash = apply_base._sha256_file(path)
        if actual_hash != expected_hash:
            raise SecondWaveGateError(
                f"BACKUP_FILE_HASH_MISMATCH file={name} expected={expected_hash} actual={actual_hash}"
            )

    calculated_bundle = apply_base._sha256_value({"file_sha256": sealed_files})
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
    _assert_equal("BACKUP_METADATA_MODE", metadata.get("mode"), preflight_base.BACKUP_MODE)
    _assert_equal("BACKUP_METADATA_MUTATION_FLAG", metadata.get("mutates_database"), False)
    _assert_equal("BACKUP_METADATA_YEAR", int(metadata.get("academic_year") or 0), ACADEMIC_YEAR)
    _assert_equal("BACKUP_METADATA_REFERENCE_DATE", str(metadata.get("reference_date") or "")[:10], REFERENCE_DATE)
    _assert_equal("BACKUP_METADATA_TEACHER", str(metadata.get("teacher_user_id") or ""), TEACHER_USER_ID)
    _assert_equal("BACKUP_METADATA_STAFF", str(metadata.get("staff_id") or ""), STAFF_ID)
    _assert_equal("BACKUP_METADATA_CLASS", str(metadata.get("class_id") or ""), CLASS_ID)
    _assert_equal("BACKUP_METADATA_SCHOOL", str(metadata.get("school_id") or ""), SCHOOL_ID)
    _assert_equal("BACKUP_METADATA_COUNT", int(metadata.get("second_wave_2d_j_ready") or 0), expected_count)
    _assert_equal("BACKUP_METADATA_MANIFEST_HASH", str(metadata.get("manifest_sha256") or ""), expected_manifest_sha256)
    _assert_equal("BACKUP_METADATA_VALID_FROM", str(metadata.get("valid_from") or "")[:10], EXPECTED_VALID_FROM)
    _assert_equal("BACKUP_METADATA_SIBLING_COUNT", int(metadata.get("current_sibling_count") or 0), EXPECTED_SIBLING_COUNT)
    validate_peer_evidence(metadata.get("peer_evidence") or {})

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise SecondWaveGateError("BACKUP_MANIFEST_INVALID expected=list")
    sealed_manifest_sha = preflight_base.manifest_digest(manifest)
    if sealed_manifest_sha != expected_manifest_sha256:
        raise SecondWaveGateError(
            f"SEALED_MANIFEST_HASH_MISMATCH expected={expected_manifest_sha256} actual={sealed_manifest_sha}"
        )
    validate_manifest_semantics(manifest)

    before = json.loads(before_path.read_text(encoding="utf-8"))
    if not isinstance(before, list):
        raise SecondWaveGateError("BACKUP_BEFORE_INVALID expected=list")

    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    migration_evidence = scope.get("second_wave_2d_j_legacy_migration_artifacts") or []
    if len(migration_evidence) != EXPECTED_LEGACY_MIGRATION_ARTIFACTS:
        raise SecondWaveGateError(
            "BACKUP_SCOPE_LEGACY_ARTIFACT_COUNT_MISMATCH "
            f"expected={EXPECTED_LEGACY_MIGRATION_ARTIFACTS} actual={len(migration_evidence)}"
        )
    validate_peer_evidence(scope.get("second_wave_2d_j_profile_evidence") or {})

    return {
        "seal": seal,
        "metadata": metadata,
        "manifest": manifest,
        "before": before,
        "scope": scope,
        "manifest_sha256": sealed_manifest_sha,
        "backup_bundle_sha256": calculated_bundle,
    }


async def collect_live_validated(db) -> dict[str, Any]:
    migration_evidence = await migration_aware.collect_migration_artifacts(db)
    if len(migration_evidence) != EXPECTED_LEGACY_MIGRATION_ARTIFACTS:
        raise SecondWaveGateError(
            "LIVE_LEGACY_MIGRATION_ARTIFACT_COUNT_MISMATCH "
            f"expected={EXPECTED_LEGACY_MIGRATION_ARTIFACTS} actual={len(migration_evidence)}"
        )

    sibling_rows = await dual.collect_sibling_rows(db)
    if len(sibling_rows) != EXPECTED_SIBLING_COUNT:
        raise SecondWaveGateError(
            f"LIVE_SIBLING_COUNT_MISMATCH expected={EXPECTED_SIBLING_COUNT} actual={len(sibling_rows)}"
        )

    original_resolver = preflight_base.resolve_peer_profile
    try:
        preflight_base.resolve_peer_profile = lambda component_id, peers: dual.resolve_dual_source_profile(
            component_id,
            peers,
            sibling_rows,
        )
        validated = await preflight_base.collect_2d_j_manifest(
            migration_aware._DatabaseProxy(db)
        )
    finally:
        preflight_base.resolve_peer_profile = original_resolver

    dual._enrich_manifest_profile_provenance(validated)
    validate_manifest_semantics(validated.get("manifest") or [])
    validate_peer_evidence(validated.get("peer_evidence") or {})
    return validated


async def inspect_state(
    db,
    backup: Mapping[str, Any],
    *,
    expected_manifest_sha256: str = APPROVED_MANIFEST_SHA256,
    expected_count: int = APPROVED_READY_COUNT,
    expected_backup_sha256: str = APPROVED_BACKUP_BUNDLE_SHA256,
) -> dict[str, Any]:
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
                f"expected={expected_count} rows={len(existing_expected)} unique_ids={len(existing_by_id)}"
            )
        apply_base._verify_applied_docs(
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

    current_scope = await apply_base._current_scope_assignments(db, class_ids)
    apply_base._assert_baseline_unchanged(current_scope, list(backup["before"]))

    live = await collect_live_validated(db)
    live_manifest = list(live.get("manifest") or [])
    live_sha = str(live.get("manifest_sha256") or "")
    if len(live_manifest) != expected_count:
        raise SecondWaveGateError(
            f"LIVE_MANIFEST_COUNT_MISMATCH expected={expected_count} actual={len(live_manifest)}"
        )
    if live_sha != expected_manifest_sha256:
        raise SecondWaveGateError(
            f"LIVE_MANIFEST_HASH_MISMATCH expected={expected_manifest_sha256} actual={live_sha}"
        )
    if _canonical(live_manifest) != _canonical(manifest):
        raise SecondWaveGateError("LIVE_MANIFEST_CONTENT_MISMATCH sealed_vs_recalculated")
    if str(live.get("valid_from") or "")[:10] != EXPECTED_VALID_FROM:
        raise SecondWaveGateError("LIVE_VALID_FROM_DRIFT")

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
    return await apply_base.apply_second_wave(
        db,
        backup,
        inspection,
        expected_manifest_sha256=APPROVED_MANIFEST_SHA256,
        expected_backup_sha256=APPROVED_BACKUP_BUNDLE_SHA256,
    )


async def rollback_second_wave(db, backup: Mapping[str, Any]) -> dict[str, Any]:
    _configure_base()
    return await apply_base.rollback_second_wave(
        db,
        backup,
        expected_manifest_sha256=APPROVED_MANIFEST_SHA256,
        expected_backup_sha256=APPROVED_BACKUP_BUNDLE_SHA256,
    )


def write_receipt(receipt_dir: Path, payload: Mapping[str, Any]) -> Path:
    preflight_base.validate_persistent_backup_path(receipt_dir)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = receipt_dir / f"dvd-second-wave-2d-j-{payload.get('mode', 'unknown').lower()}-{stamp}.json"
    doc = dict(payload)
    doc["receipt_sha256"] = apply_base._sha256_value(payload)
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def print_dry_run(backup: Mapping[str, Any], inspection: Mapping[str, Any]) -> None:
    print("=== DVD SEGUNDA ONDA 2D-J — DRY-RUN CONTROLADO ===")
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
    print("PROFILE:", EXPECTED_PROFILE)
    print("STUDENT_SCOPE:", EXPECTED_SCOPE)
    print("VALID_FROM:", EXPECTED_VALID_FROM)
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
    preflight_base.validate_persistent_backup_path(PERSISTENT_RECEIPT_DIR)

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
            print("=== DVD SEGUNDA ONDA 2D-J — ROLLBACK ===")
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
            "profile": EXPECTED_PROFILE,
            "student_scope": EXPECTED_SCOPE,
            "valid_from": EXPECTED_VALID_FROM,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        receipt = write_receipt(PERSISTENT_RECEIPT_DIR, payload)

        print("=== DVD SEGUNDA ONDA 2D-J — APPLY CONTROLADO ===")
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
