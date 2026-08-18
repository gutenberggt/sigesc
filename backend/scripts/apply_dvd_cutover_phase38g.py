"""38G-B — apply controlado do cutover DVD com gates fail-closed.

Default: dry-run, sem escrita.
Apply: exige --apply + --confirm APPLY-38G-B-228.
Rollback: exige --rollback + --confirm ROLLBACK-38G-B-228.

O manifesto e o backup selados pela 38G-A são a fonte autorizativa.
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
import uuid
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

load_dotenv(BACKEND_DIR / ".env")

APPROVED_MANIFEST_SHA256 = "6f40a48e1eb686412ead3342e2cdf7304ebf234d4a0f597eeb817300295743e2"
APPROVED_READY_COUNT = 228
APPROVED_BACKUP_BUNDLE_SHA256 = "a1c126bfc36ff71a5ed4cdd8d3245a44cfa94c09fa35d7716862b6e7421b29ac"
DEFAULT_REFERENCE_DATE = "2026-08-18"
APPLY_CONFIRMATION = "APPLY-38G-B-228"
ROLLBACK_CONFIRMATION = "ROLLBACK-38G-B-228"
ACTOR = "dvd-cutover-phase38g-b"

CORE_FIELDS = (
    "id",
    "teacher_id",
    "teacher_name",
    "class_id",
    "class_name",
    "school_id",
    "mantenedora_id",
    "component_id",
    "component_name",
    "weekly_slots",
    "valid_from",
    "valid_until",
    "is_substitute",
    "source",
    "diary_settings",
)


class CutoverGateError(RuntimeError):
    pass


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


def _sorted_docs(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    docs = [dict(item) for item in items]
    for doc in docs:
        doc.pop("_id", None)
    docs.sort(
        key=lambda row: (
            str(row.get("school_id") or ""),
            str(row.get("class_id") or row.get("id") or ""),
            str(row.get("component_id") or row.get("course_id") or ""),
            str(row.get("teacher_id") or row.get("staff_id") or ""),
            str(row.get("id") or ""),
        )
    )
    return docs


def _core(doc: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: doc.get(field)
        for field in CORE_FIELDS
        if field in doc or field in {"valid_until"}
    }


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
    seal_path = backup_dir / "BACKUP-SEAL.json"
    metadata_path = backup_dir / "backup-metadata.json"
    manifest_path = backup_dir / "manifest.json"
    before_path = backup_dir / "teacher_class_assignments_before.json"

    for path in (seal_path, metadata_path, manifest_path, before_path):
        if not path.is_file():
            raise CutoverGateError(f"BACKUP_FILE_MISSING path={path}")

    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    sealed_files = seal.get("files")
    if not isinstance(sealed_files, dict) or not sealed_files:
        raise CutoverGateError("BACKUP_SEAL_INVALID files ausente/vazio")

    for name, expected_hash in sorted(sealed_files.items()):
        path = backup_dir / name
        if not path.is_file():
            raise CutoverGateError(f"BACKUP_FILE_MISSING path={path}")
        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
            raise CutoverGateError(
                f"BACKUP_FILE_HASH_MISMATCH file={name} "
                f"expected={expected_hash} actual={actual_hash}"
            )

    calculated_bundle = _sha256_value({"file_sha256": sealed_files})
    sealed_bundle = str(seal.get("backup_bundle_sha256") or "")
    if calculated_bundle != sealed_bundle:
        raise CutoverGateError(
            f"BACKUP_BUNDLE_SEAL_MISMATCH sealed={sealed_bundle} "
            f"calculated={calculated_bundle}"
        )
    if calculated_bundle != expected_backup_sha256:
        raise CutoverGateError(
            f"BACKUP_BUNDLE_NOT_APPROVED expected={expected_backup_sha256} "
            f"actual={calculated_bundle}"
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("mode") != "38G_A_PREFLIGHT_READ_ONLY":
        raise CutoverGateError(
            f"BACKUP_METADATA_MODE_INVALID mode={metadata.get('mode')}"
        )
    if metadata.get("mutates_database") is not False:
        raise CutoverGateError("BACKUP_METADATA_MUTATION_FLAG_INVALID")
    if str(metadata.get("manifest_sha256") or "") != expected_manifest_sha256:
        raise CutoverGateError(
            "BACKUP_METADATA_MANIFEST_HASH_MISMATCH "
            f"expected={expected_manifest_sha256} "
            f"actual={metadata.get('manifest_sha256')}"
        )
    if int(metadata.get("first_wave_ready") or 0) != expected_count:
        raise CutoverGateError(
            f"BACKUP_METADATA_COUNT_MISMATCH expected={expected_count} "
            f"actual={metadata.get('first_wave_ready')}"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise CutoverGateError("BACKUP_MANIFEST_INVALID expected=list")
    if len(manifest) != expected_count:
        raise CutoverGateError(
            f"SEALED_MANIFEST_COUNT_MISMATCH expected={expected_count} "
            f"actual={len(manifest)}"
        )
    sealed_manifest_sha = manifest_digest(manifest)
    if sealed_manifest_sha != expected_manifest_sha256:
        raise CutoverGateError(
            f"SEALED_MANIFEST_HASH_MISMATCH expected={expected_manifest_sha256} "
            f"actual={sealed_manifest_sha}"
        )

    ids = [str(row.get("id") or "") for row in manifest]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        raise CutoverGateError("SEALED_MANIFEST_IDS_INVALID missing_or_duplicate_id")

    target_keys = [_target_key(row) for row in manifest]
    if any(not all(key) for key in target_keys) or len(target_keys) != len(set(target_keys)):
        raise CutoverGateError(
            "SEALED_MANIFEST_TARGET_KEYS_INVALID missing_or_duplicate_target"
        )

    before = json.loads(before_path.read_text(encoding="utf-8"))
    if not isinstance(before, list):
        raise CutoverGateError("BACKUP_BEFORE_INVALID expected=list")

    return {
        "seal": seal,
        "metadata": metadata,
        "manifest": manifest,
        "before": before,
        "manifest_sha256": sealed_manifest_sha,
        "backup_bundle_sha256": calculated_bundle,
    }


async def _current_scope_assignments(
    db,
    class_ids: list[str],
) -> list[dict[str, Any]]:
    if not class_ids:
        return []
    rows = await db.teacher_class_assignments.find(
        {"class_id": {"$in": class_ids}},
        {"_id": 0},
    ).to_list(50000)
    return _sorted_docs(rows)


def _assert_baseline_unchanged(
    current: list[dict[str, Any]],
    before: list[dict[str, Any]],
) -> None:
    current_sorted = _sorted_docs(current)
    before_sorted = _sorted_docs(before)
    if _canonical_json(current_sorted) != _canonical_json(before_sorted):
        raise CutoverGateError(
            "PRE_CUTOVER_BASELINE_DRIFT "
            f"backup_count={len(before_sorted)} current_count={len(current_sorted)}"
        )


def _verify_applied_docs(
    existing_by_id: Mapping[str, Mapping[str, Any]],
    manifest: list[Mapping[str, Any]],
    *,
    expected_manifest_sha256: str,
    expected_backup_sha256: str,
) -> None:
    for proposed in manifest:
        assignment_id = str(proposed["id"])
        actual = existing_by_id.get(assignment_id)
        if actual is None:
            raise CutoverGateError(f"APPLIED_DOC_MISSING id={assignment_id}")
        if _canonical_json(_core(actual)) != _canonical_json(_core(proposed)):
            raise CutoverGateError(f"APPLIED_DOC_CORE_MISMATCH id={assignment_id}")
        provenance = actual.get("cutover_provenance") or {}
        source_provenance = proposed.get("cutover_provenance") or {}
        for key, value in source_provenance.items():
            if provenance.get(key) != value:
                raise CutoverGateError(
                    f"APPLIED_DOC_PROVENANCE_SOURCE_MISMATCH "
                    f"id={assignment_id} key={key}"
                )
        if provenance.get("apply_phase") != "38G-B":
            raise CutoverGateError(
                f"APPLIED_DOC_PHASE_MISMATCH id={assignment_id}"
            )
        if provenance.get("apply_state") != "ACTIVATED":
            raise CutoverGateError(
                f"APPLIED_DOC_STATE_MISMATCH id={assignment_id}"
            )
        if provenance.get("manifest_sha256") != expected_manifest_sha256:
            raise CutoverGateError(
                f"APPLIED_DOC_MANIFEST_HASH_MISMATCH id={assignment_id}"
            )
        if provenance.get("backup_bundle_sha256") != expected_backup_sha256:
            raise CutoverGateError(
                f"APPLIED_DOC_BACKUP_HASH_MISMATCH id={assignment_id}"
            )


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
        str(row.get("id")): row
        for row in existing_expected
        if row.get("id")
    }

    if existing_expected:
        if len(existing_expected) != expected_count or len(existing_by_id) != expected_count:
            raise CutoverGateError(
                "PARTIAL_OR_DUPLICATE_APPLY_DETECTED "
                f"expected={expected_count} rows={len(existing_expected)} "
                f"unique_ids={len(existing_by_id)}"
            )
        _verify_applied_docs(
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

    current_scope = await _current_scope_assignments(db, class_ids)
    _assert_baseline_unchanged(current_scope, list(backup["before"]))

    live = await collect_first_wave_manifest(
        db,
        academic_year=academic_year,
        reference_date=reference_date,
        tenant_id=tenant_id,
    )
    live_summary = live["summary"]
    live_manifest = live["manifest"]
    live_sha = str(live_summary.get("manifest_sha256") or "")
    live_count = int(live_summary.get("first_wave_ready") or 0)

    if live_count != expected_count:
        raise CutoverGateError(
            f"LIVE_MANIFEST_COUNT_MISMATCH expected={expected_count} "
            f"actual={live_count}"
        )
    if live_sha != expected_manifest_sha256:
        raise CutoverGateError(
            f"LIVE_MANIFEST_HASH_MISMATCH expected={expected_manifest_sha256} "
            f"actual={live_sha}"
        )
    if _canonical_json(live_manifest) != _canonical_json(manifest):
        raise CutoverGateError(
            "LIVE_MANIFEST_CONTENT_MISMATCH sealed_vs_recalculated"
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
        raise CutoverGateError(
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


def build_apply_documents(
    manifest: list[Mapping[str, Any]],
    *,
    manifest_sha256: str,
    backup_bundle_sha256: str,
    run_id: str,
    activated_at: str,
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for proposed in manifest:
        doc = dict(proposed)
        source_provenance = dict(doc.get("cutover_provenance") or {})
        source_provenance.update(
            {
                "apply_phase": "38G-B",
                "apply_state": "ACTIVATED",
                "manifest_sha256": manifest_sha256,
                "backup_bundle_sha256": backup_bundle_sha256,
                "apply_run_id": run_id,
                "activated_at": activated_at,
            }
        )
        doc["cutover_provenance"] = source_provenance
        doc["deleted"] = False
        doc["created_at"] = activated_at
        doc["created_by"] = ACTOR
        doc["updated_at"] = activated_at
        doc["updated_by"] = ACTOR
        docs.append(doc)
    return docs


async def apply_cutover(
    db,
    backup: Mapping[str, Any],
    inspection: Mapping[str, Any],
    *,
    expected_manifest_sha256: str,
    expected_backup_sha256: str,
) -> dict[str, Any]:
    if inspection["state"] == "already_applied":
        return {
            "state": "already_applied",
            "inserted": 0,
            "postcheck": len(inspection["expected_ids"]),
            "run_id": None,
        }
    if inspection["state"] != "ready":
        raise CutoverGateError(
            f"APPLY_STATE_INVALID state={inspection['state']}"
        )

    run_id = str(uuid.uuid4())
    activated_at = datetime.now(timezone.utc).isoformat()
    docs = build_apply_documents(
        list(backup["manifest"]),
        manifest_sha256=expected_manifest_sha256,
        backup_bundle_sha256=expected_backup_sha256,
        run_id=run_id,
        activated_at=activated_at,
    )
    ids = [str(row["id"]) for row in docs]

    try:
        result = await db.teacher_class_assignments.insert_many(docs, ordered=True)
        inserted = len(result.inserted_ids)
        if inserted != len(docs):
            raise CutoverGateError(
                f"INSERT_COUNT_MISMATCH expected={len(docs)} actual={inserted}"
            )

        post = await db.teacher_class_assignments.find(
            {"id": {"$in": ids}},
            {"_id": 0},
        ).to_list(len(ids) + 10)
        post_by_id = {
            str(row.get("id")): row
            for row in post
            if row.get("id")
        }
        if len(post) != len(ids) or len(post_by_id) != len(ids):
            raise CutoverGateError(
                "POSTCHECK_COUNT_MISMATCH "
                f"expected={len(ids)} rows={len(post)} "
                f"unique_ids={len(post_by_id)}"
            )
        _verify_applied_docs(
            post_by_id,
            list(backup["manifest"]),
            expected_manifest_sha256=expected_manifest_sha256,
            expected_backup_sha256=expected_backup_sha256,
        )
        return {
            "state": "applied",
            "inserted": inserted,
            "postcheck": len(post_by_id),
            "run_id": run_id,
            "activated_at": activated_at,
        }
    except Exception:
        await db.teacher_class_assignments.delete_many(
            {
                "id": {"$in": ids},
                "cutover_provenance.apply_phase": "38G-B",
                "cutover_provenance.apply_run_id": run_id,
            }
        )
        raise


async def rollback_cutover(
    db,
    backup: Mapping[str, Any],
    *,
    expected_manifest_sha256: str,
    expected_backup_sha256: str,
) -> dict[str, Any]:
    manifest = list(backup["manifest"])
    ids = [str(row["id"]) for row in manifest]
    class_ids = sorted(
        {
            str(row.get("class_id") or "")
            for row in manifest
            if row.get("class_id")
        }
    )

    existing = await db.teacher_class_assignments.find(
        {"id": {"$in": ids}},
        {"_id": 0},
    ).to_list(len(ids) + 10)
    existing_by_id = {
        str(row.get("id")): row
        for row in existing
        if row.get("id")
    }

    if not existing:
        current_scope = await _current_scope_assignments(db, class_ids)
        _assert_baseline_unchanged(current_scope, list(backup["before"]))
        return {
            "state": "already_rolled_back",
            "removed": 0,
            "postcheck_baseline": True,
        }

    if len(existing) != len(ids) or len(existing_by_id) != len(ids):
        raise CutoverGateError(
            "ROLLBACK_PARTIAL_OR_DUPLICATE_STATE "
            f"expected={len(ids)} rows={len(existing)} "
            f"unique_ids={len(existing_by_id)}"
        )
    _verify_applied_docs(
        existing_by_id,
        manifest,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_backup_sha256=expected_backup_sha256,
    )

    current_scope = await _current_scope_assignments(db, class_ids)
    expected_id_set = set(ids)
    without_cutover = [
        row
        for row in current_scope
        if str(row.get("id") or "") not in expected_id_set
    ]
    _assert_baseline_unchanged(without_cutover, list(backup["before"]))

    result = await db.teacher_class_assignments.delete_many(
        {
            "id": {"$in": ids},
            "cutover_provenance.apply_phase": "38G-B",
            "cutover_provenance.manifest_sha256": expected_manifest_sha256,
            "cutover_provenance.backup_bundle_sha256": expected_backup_sha256,
        }
    )
    if result.deleted_count != len(ids):
        raise CutoverGateError(
            f"ROLLBACK_DELETE_COUNT_MISMATCH expected={len(ids)} "
            f"actual={result.deleted_count}"
        )

    current_scope = await _current_scope_assignments(db, class_ids)
    _assert_baseline_unchanged(current_scope, list(backup["before"]))
    return {
        "state": "rolled_back",
        "removed": result.deleted_count,
        "postcheck_baseline": True,
    }


def write_receipt(receipt_dir: Path, payload: Mapping[str, Any]) -> Path:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = receipt_dir / (
        f"dvd38g-b-{payload.get('mode', 'unknown').lower()}-{stamp}.json"
    )
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
    print("=== DVD 38G-B — DRY-RUN CONTROLADO ===")
    print("MODE: DRY_RUN")
    print("BACKUP_INTEGRITY: APROVADA")
    print("BACKUP_BUNDLE_SHA256:", backup["backup_bundle_sha256"])
    print("SEALED_MANIFEST_SHA256:", inspection["sealed_manifest_sha256"])
    print(
        "LIVE_MANIFEST_SHA256:",
        inspection["live_manifest_sha256"] or "SKIPPED_ALREADY_APPLIED",
    )
    print("MANIFEST_MATCH: SIM")
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
    parser.add_argument(
        "--expected-manifest-sha256",
        default=APPROVED_MANIFEST_SHA256,
    )
    parser.add_argument("--expected-count", type=int, default=APPROVED_READY_COUNT)
    parser.add_argument(
        "--expected-backup-sha256",
        default=APPROVED_BACKUP_BUNDLE_SHA256,
    )
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--receipt-dir", default="/tmp/dvd38g-receipts")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args()

    backup = load_and_verify_backup(
        Path(args.backup_dir),
        expected_manifest_sha256=args.expected_manifest_sha256,
        expected_count=args.expected_count,
        expected_backup_sha256=args.expected_backup_sha256,
    )

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]

        if args.rollback:
            if args.confirm != ROLLBACK_CONFIRMATION:
                raise CutoverGateError(
                    f"ROLLBACK_CONFIRMATION_REQUIRED expected={ROLLBACK_CONFIRMATION}"
                )
            result = await rollback_cutover(
                db,
                backup,
                expected_manifest_sha256=args.expected_manifest_sha256,
                expected_backup_sha256=args.expected_backup_sha256,
            )
            receipt_payload = {
                "mode": "ROLLBACK",
                "result": result,
                "manifest_sha256": args.expected_manifest_sha256,
                "backup_bundle_sha256": args.expected_backup_sha256,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            receipt = write_receipt(Path(args.receipt_dir), receipt_payload)
            print("=== DVD 38G-B — ROLLBACK ===")
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
            print_dry_run(
                backup,
                inspection,
                expected_count=args.expected_count,
            )
            return

        if args.confirm != APPLY_CONFIRMATION:
            raise CutoverGateError(
                f"APPLY_CONFIRMATION_REQUIRED expected={APPLY_CONFIRMATION}"
            )

        result = await apply_cutover(
            db,
            backup,
            inspection,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_backup_sha256=args.expected_backup_sha256,
        )
        receipt_payload = {
            "mode": "APPLY",
            "result": result,
            "manifest_sha256": args.expected_manifest_sha256,
            "backup_bundle_sha256": args.expected_backup_sha256,
            "expected_count": args.expected_count,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        receipt = write_receipt(Path(args.receipt_dir), receipt_payload)

        print("=== DVD 38G-B — APPLY CONTROLADO ===")
        print("STATE:", result["state"])
        print("INSERTED:", result["inserted"])
        print("POSTCHECK:", f"{result['postcheck']}/{args.expected_count}")
        print("MANIFEST_SHA256:", args.expected_manifest_sha256)
        print("BACKUP_BUNDLE_SHA256:", args.expected_backup_sha256)
        print(
            "ACTIVATION_EXECUTED:",
            "SIM" if result["state"] == "applied" else "JA_ESTAVA_APLICADO",
        )
        print("RECEIPT:", receipt)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
