"""Apply controlado da normalização de horários do 1º ao 5º ano — Fase 2.

Default: DRY-RUN, sem escrita no MongoDB.
Apply: exige --apply e três confirmações exatas.

Fonte autorizativa selada em produção:
- SOURCE_INVENTORY_SHA256 = 891e6f8b...;
- SCOPE_V2_SHA256 = 1815d025...;
- MANIFEST_SHA256 = 550812a8...;
- BACKUP_BUNDLE_SHA256 = 7fbb0bce...;
- exatamente 69 alvos: 36 criações e 33 atualizações.

Invariantes do apply:
- recalcula o escopo V2 antes de qualquer escrita e falha em qualquer drift;
- verifica integralmente os quatro artefatos persistentes do preflight;
- CREATE usa ID determinístico e schedule_slots=[];
- UPDATE preserva schedule_slots e só altera slots_per_day, slot_times e updated_at;
- cada UPDATE usa filtro otimista sobre o snapshot atual para não sobrescrever edição concorrente;
- pós-check exige exatamente 69 grades normalizadas;
- receipt persistente é gravado em /data.

Este script NÃO deve ser executado com --apply sem autorização humana explícita.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping
import uuid

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from scripts import inventory_initial_years_schedule_normalization as inventory_v1  # noqa: E402
from scripts import inventory_initial_years_schedule_normalization_v2 as inventory_v2  # noqa: E402
from scripts import prepare_initial_years_schedule_normalization_phase1 as preflight  # noqa: E402

ACADEMIC_YEAR = 2026
APPROVED_SOURCE_INVENTORY_SHA256 = "891e6f8bc29929ba0a4d9ca59eb7d034f0ad1617f2758b3db9a00b4d3bdcc01a"
APPROVED_SCOPE_V2_SHA256 = "1815d025770d24f2bb109cb5598bc990f2f0ca4ce361095dc1446cbbb2de9b7d"
APPROVED_MANIFEST_SHA256 = "550812a8358a587f1dbbf56ae1ebe1999889d66fd0829de66d69b72062a4e554"
APPROVED_BACKUP_BUNDLE_SHA256 = "7fbb0bcee57d7b81e67a5aaf35f0e75aec86ca6f44e2d96a8d96ef53ebfc512f"
APPROVED_BACKUP_DIR = Path("/data/sigesc-schedule-backups/initial-years-phase1-preflight-v1")
RECEIPT_DIR = Path("/data/sigesc-schedule-backups/receipts/initial-years-phase2")
APPLY_CONFIRMATION = "APPLY-INITIAL-YEARS-SCHEDULE-2026-PHASE2-69"
PHASE_ID = "INITIAL-YEARS-SCHEDULE-NORMALIZATION-2026-PHASE2"
EXPECTED_TARGETS = 69
EXPECTED_CREATES = 36
EXPECTED_UPDATES = 33
EXPECTED_UPDATE_WRITES = 33
EXPECTED_BLOCKED_OUTSIDE = 15


class Phase2ApplyError(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256(value: Any) -> str:
    return preflight._sha256(value)


def _without_mongo_id(row: Mapping[str, Any]) -> dict[str, Any]:
    clean = deepcopy(dict(row))
    clean.pop("_id", None)
    return clean


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise Phase2ApplyError(f"BACKUP_FILE_MISSING path={path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise Phase2ApplyError(f"BACKUP_FILE_INVALID_JSON path={path}") from exc


def validate_confirmation(
    *,
    apply: bool,
    confirm: str | None,
    confirm_manifest: str | None,
    confirm_backup: str | None,
) -> None:
    if not apply:
        return
    if confirm != APPLY_CONFIRMATION:
        raise Phase2ApplyError(
            f"APPLY_CONFIRMATION_INVALID expected={APPLY_CONFIRMATION!r} actual={confirm!r}"
        )
    if confirm_manifest != APPROVED_MANIFEST_SHA256:
        raise Phase2ApplyError(
            "MANIFEST_CONFIRMATION_INVALID "
            f"expected={APPROVED_MANIFEST_SHA256} actual={confirm_manifest}"
        )
    if confirm_backup != APPROVED_BACKUP_BUNDLE_SHA256:
        raise Phase2ApplyError(
            "BACKUP_CONFIRMATION_INVALID "
            f"expected={APPROVED_BACKUP_BUNDLE_SHA256} actual={confirm_backup}"
        )


def validate_backup_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    approved = APPROVED_BACKUP_DIR.resolve()
    if resolved != approved:
        raise Phase2ApplyError(
            f"BACKUP_DIR_NOT_APPROVED expected={approved} actual={resolved}"
        )
    return resolved


def validate_manifest_semantics(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected_policy = {
        shift: inventory_v1.proposed_slot_times(shift)
        for shift in ("morning", "afternoon")
    }
    checks = {
        "phase_id": preflight.PHASE_ID,
        "academic_year": ACADEMIC_YEAR,
        "source_inventory_sha256": APPROVED_SOURCE_INVENTORY_SHA256,
        "scope_v2_sha256": APPROVED_SCOPE_V2_SHA256,
        "target_count": EXPECTED_TARGETS,
        "create_target_count": EXPECTED_CREATES,
        "existing_target_count": EXPECTED_UPDATES,
        "existing_write_required_count": EXPECTED_UPDATE_WRITES,
        "existing_already_compliant_count": 0,
        "blocked_outside_phase1_count": EXPECTED_BLOCKED_OUTSIDE,
        "policy": expected_policy,
    }
    for key, expected in checks.items():
        actual = manifest.get(key)
        if actual != expected:
            raise Phase2ApplyError(
                f"SEALED_MANIFEST_FIELD_MISMATCH field={key} expected={expected!r} actual={actual!r}"
            )

    targets = [dict(row) for row in (manifest.get("targets") or [])]
    if len(targets) != EXPECTED_TARGETS:
        raise Phase2ApplyError(
            f"SEALED_TARGET_COUNT_MISMATCH expected={EXPECTED_TARGETS} actual={len(targets)}"
        )

    class_ids: list[str] = []
    schedule_ids: list[str] = []
    create_count = 0
    update_count = 0

    for row in targets:
        class_id = str(row.get("class_id") or "")
        schedule_id = str(row.get("schedule_id") or "")
        shift = str(row.get("shift") or "")
        mode = str(row.get("mode") or "")
        if not class_id or not schedule_id:
            raise Phase2ApplyError("SEALED_TARGET_ID_MISSING")
        if shift not in {"morning", "afternoon"}:
            raise Phase2ApplyError(f"SEALED_TARGET_SHIFT_INVALID class_id={class_id} shift={shift}")
        if int(row.get("academic_year") or 0) != ACADEMIC_YEAR:
            raise Phase2ApplyError(f"SEALED_TARGET_YEAR_INVALID class_id={class_id}")
        if int(row.get("proposed_slots_per_day") or 0) != 4:
            raise Phase2ApplyError(f"SEALED_TARGET_SLOTS_PER_DAY_INVALID class_id={class_id}")
        if row.get("proposed_slot_times") != expected_policy[shift]:
            raise Phase2ApplyError(f"SEALED_TARGET_POLICY_INVALID class_id={class_id}")
        if row.get("write_required") is not True:
            raise Phase2ApplyError(f"SEALED_TARGET_NOT_WRITE_REQUIRED class_id={class_id}")

        if mode == "CREATE_TIME_GRID":
            create_count += 1
            if schedule_id != preflight.deterministic_schedule_id(class_id):
                raise Phase2ApplyError(f"SEALED_CREATE_ID_NOT_DETERMINISTIC class_id={class_id}")
            if row.get("preserve_schedule_slots") is not False:
                raise Phase2ApplyError(f"SEALED_CREATE_PRESERVE_FLAG_INVALID class_id={class_id}")
            if row.get("proposed_schedule_slots") != []:
                raise Phase2ApplyError(f"SEALED_CREATE_SCHEDULE_SLOTS_NOT_EMPTY class_id={class_id}")
            if row.get("current_document_sha256") is not None:
                raise Phase2ApplyError(f"SEALED_CREATE_CURRENT_HASH_PRESENT class_id={class_id}")
        elif mode == "UPDATE_TIME_GRID":
            update_count += 1
            if row.get("preserve_schedule_slots") is not True:
                raise Phase2ApplyError(f"SEALED_UPDATE_PRESERVE_FLAG_INVALID class_id={class_id}")
            if not row.get("current_document_sha256"):
                raise Phase2ApplyError(f"SEALED_UPDATE_CURRENT_HASH_MISSING class_id={class_id}")
            if not row.get("current_schedule_slots_sha256"):
                raise Phase2ApplyError(f"SEALED_UPDATE_SLOTS_HASH_MISSING class_id={class_id}")
        else:
            raise Phase2ApplyError(f"SEALED_TARGET_MODE_INVALID class_id={class_id} mode={mode}")

        class_ids.append(class_id)
        schedule_ids.append(schedule_id)

    if create_count != EXPECTED_CREATES or update_count != EXPECTED_UPDATES:
        raise Phase2ApplyError(
            f"SEALED_MODE_COUNTS_INVALID create={create_count} update={update_count}"
        )
    if len(set(class_ids)) != EXPECTED_TARGETS:
        raise Phase2ApplyError("SEALED_CLASS_IDS_DUPLICATE")
    if len(set(schedule_ids)) != EXPECTED_TARGETS:
        raise Phase2ApplyError("SEALED_SCHEDULE_IDS_DUPLICATE")

    return targets


def load_and_verify_backup(backup_dir: Path) -> dict[str, Any]:
    resolved = validate_backup_dir(backup_dir)
    scope_path = resolved / "scope_v2_snapshot.json"
    manifest_path = resolved / "manifest.json"
    existing_path = resolved / "existing_class_schedules.json"
    metadata_path = resolved / "metadata.json"

    scope = _read_json(scope_path)
    manifest = _read_json(manifest_path)
    existing = _read_json(existing_path)
    metadata = _read_json(metadata_path)

    actual_manifest_hash = _sha256(manifest)
    if actual_manifest_hash != APPROVED_MANIFEST_SHA256:
        raise Phase2ApplyError(
            f"MANIFEST_NOT_APPROVED expected={APPROVED_MANIFEST_SHA256} actual={actual_manifest_hash}"
        )

    if not isinstance(existing, list) or len(existing) != EXPECTED_UPDATES:
        raise Phase2ApplyError(
            f"BACKUP_EXISTING_COUNT_INVALID expected={EXPECTED_UPDATES} actual={len(existing) if isinstance(existing, list) else 'non-list'}"
        )

    file_hashes = metadata.get("file_hashes") or {}
    calculated_file_hashes = {
        "scope_v2_snapshot_sha256": _sha256(scope),
        "manifest_sha256": actual_manifest_hash,
        "existing_class_schedules_sha256": _sha256(existing),
    }
    if file_hashes != calculated_file_hashes:
        raise Phase2ApplyError(
            f"BACKUP_FILE_HASHES_MISMATCH expected={file_hashes} actual={calculated_file_hashes}"
        )

    metadata_core = {
        "phase_id": metadata.get("phase_id"),
        "academic_year": metadata.get("academic_year"),
        "source_inventory_sha256": metadata.get("source_inventory_sha256"),
        "scope_v2_sha256": metadata.get("scope_v2_sha256"),
        "manifest_sha256": metadata.get("manifest_sha256"),
        "existing_schedule_count": metadata.get("existing_schedule_count"),
        "file_hashes": file_hashes,
    }
    calculated_bundle = _sha256(metadata_core)
    sealed_bundle = str(metadata.get("backup_bundle_sha256") or "")
    if calculated_bundle != sealed_bundle:
        raise Phase2ApplyError(
            f"BACKUP_BUNDLE_METADATA_MISMATCH sealed={sealed_bundle} calculated={calculated_bundle}"
        )
    if calculated_bundle != APPROVED_BACKUP_BUNDLE_SHA256:
        raise Phase2ApplyError(
            f"BACKUP_BUNDLE_NOT_APPROVED expected={APPROVED_BACKUP_BUNDLE_SHA256} actual={calculated_bundle}"
        )

    expected_metadata = {
        "phase_id": preflight.PHASE_ID,
        "academic_year": ACADEMIC_YEAR,
        "source_inventory_sha256": APPROVED_SOURCE_INVENTORY_SHA256,
        "scope_v2_sha256": APPROVED_SCOPE_V2_SHA256,
        "manifest_sha256": APPROVED_MANIFEST_SHA256,
        "existing_schedule_count": EXPECTED_UPDATES,
        "mongo_writes": 0,
        "apply_executed": False,
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            raise Phase2ApplyError(
                f"BACKUP_METADATA_MISMATCH field={key} expected={expected!r} actual={metadata.get(key)!r}"
            )

    if str(scope.get("scope_v2_sha256") or "") != APPROVED_SCOPE_V2_SHA256:
        raise Phase2ApplyError("BACKUP_SCOPE_HASH_MISMATCH")
    scope_core = scope.get("scope") or {}
    if str(scope_core.get("source_inventory_sha256") or "") != APPROVED_SOURCE_INVENTORY_SHA256:
        raise Phase2ApplyError("BACKUP_SOURCE_HASH_MISMATCH")

    targets = validate_manifest_semantics(manifest)
    existing_by_id = {
        str(row.get("id") or ""): _without_mongo_id(row)
        for row in existing
        if row.get("id")
    }
    update_ids = {
        str(row["schedule_id"])
        for row in targets
        if row.get("mode") == "UPDATE_TIME_GRID"
    }
    if set(existing_by_id) != update_ids:
        raise Phase2ApplyError("BACKUP_EXISTING_ID_SET_MISMATCH")

    for target in targets:
        if target.get("mode") != "UPDATE_TIME_GRID":
            continue
        schedule_id = str(target["schedule_id"])
        backed = existing_by_id[schedule_id]
        if _sha256(backed) != target.get("current_document_sha256"):
            raise Phase2ApplyError(f"BACKUP_CURRENT_DOCUMENT_HASH_MISMATCH schedule_id={schedule_id}")
        if _sha256(backed.get("schedule_slots") or []) != target.get("current_schedule_slots_sha256"):
            raise Phase2ApplyError(f"BACKUP_SCHEDULE_SLOTS_HASH_MISMATCH schedule_id={schedule_id}")

    return {
        "backup_dir": str(resolved),
        "scope": scope,
        "manifest": manifest,
        "targets": targets,
        "existing_by_id": existing_by_id,
        "metadata": metadata,
    }


async def validate_live_preconditions(db, sealed: Mapping[str, Any]) -> dict[str, Any]:
    live_scope = await inventory_v2.collect_inventory_v2(db)
    preflight.validate_scope_v2(live_scope)

    targets = list(sealed["targets"])
    class_ids = [str(row["class_id"]) for row in targets]
    live_docs = await db.class_schedules.find(
        {
            "class_id": {"$in": class_ids},
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        }
    ).to_list(1000)

    by_class: dict[str, list[dict[str, Any]]] = {}
    for raw in live_docs:
        clean = _without_mongo_id(raw)
        by_class.setdefault(str(clean.get("class_id") or ""), []).append(clean)

    create_ids = [
        str(row["schedule_id"])
        for row in targets
        if row.get("mode") == "CREATE_TIME_GRID"
    ]
    collisions = []
    if create_ids:
        collisions = await db.class_schedules.find(
            {"id": {"$in": create_ids}},
            {"_id": 0, "id": 1, "class_id": 1, "academic_year": 1},
        ).to_list(1000)
    if collisions:
        raise Phase2ApplyError(f"LIVE_CREATE_ID_COLLISION count={len(collisions)}")

    create_ready = 0
    update_ready = 0
    current_by_schedule_id: dict[str, dict[str, Any]] = {}

    for target in targets:
        class_id = str(target["class_id"])
        schedule_id = str(target["schedule_id"])
        docs = by_class.get(class_id, [])
        mode = target.get("mode")

        if mode == "CREATE_TIME_GRID":
            if docs:
                raise Phase2ApplyError(
                    f"LIVE_CREATE_CLASS_NOW_HAS_SCHEDULE class_id={class_id} count={len(docs)}"
                )
            create_ready += 1
            continue

        if len(docs) != 1:
            raise Phase2ApplyError(
                f"LIVE_UPDATE_SCHEDULE_COUNT_DRIFT class_id={class_id} expected=1 actual={len(docs)}"
            )
        current = docs[0]
        if str(current.get("id") or "") != schedule_id:
            raise Phase2ApplyError(f"LIVE_UPDATE_ID_DRIFT class_id={class_id}")
        if _sha256(current) != target.get("current_document_sha256"):
            raise Phase2ApplyError(f"LIVE_UPDATE_DOCUMENT_DRIFT schedule_id={schedule_id}")
        if _sha256(current.get("schedule_slots") or []) != target.get("current_schedule_slots_sha256"):
            raise Phase2ApplyError(f"LIVE_UPDATE_SCHEDULE_SLOTS_DRIFT schedule_id={schedule_id}")
        if str(current.get("school_id") or "") != str(target.get("school_id") or ""):
            raise Phase2ApplyError(f"LIVE_UPDATE_SCHOOL_DRIFT schedule_id={schedule_id}")
        if str(current.get("shift") or "") != str(target.get("shift") or ""):
            raise Phase2ApplyError(f"LIVE_UPDATE_SHIFT_DRIFT schedule_id={schedule_id}")
        current_by_schedule_id[schedule_id] = current
        update_ready += 1

    if create_ready != EXPECTED_CREATES or update_ready != EXPECTED_UPDATES:
        raise Phase2ApplyError(
            f"LIVE_PRECONDITION_COUNTS_INVALID create={create_ready} update={update_ready}"
        )

    return {
        "create_ready": create_ready,
        "update_ready": update_ready,
        "current_by_schedule_id": current_by_schedule_id,
    }


def build_create_document(target: Mapping[str, Any], *, timestamp: str) -> dict[str, Any]:
    return {
        "id": str(target["schedule_id"]),
        "school_id": str(target["school_id"]),
        "class_id": str(target["class_id"]),
        "academic_year": ACADEMIC_YEAR,
        "shift": str(target["shift"]),
        "slots_per_day": 4,
        "slot_times": deepcopy(target["proposed_slot_times"]),
        "schedule_slots": [],
        "created_at": timestamp,
    }


def build_update_filter_and_patch(
    target: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    timestamp: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    filter_doc = {
        "id": str(target["schedule_id"]),
        "class_id": str(target["class_id"]),
        "school_id": str(target["school_id"]),
        "shift": str(target["shift"]),
        "academic_year": current.get("academic_year"),
        "slots_per_day": current.get("slots_per_day"),
        "slot_times": deepcopy(current.get("slot_times") or {}),
        "schedule_slots": deepcopy(current.get("schedule_slots") or []),
        "updated_at": current.get("updated_at"),
    }
    patch = {
        "$set": {
            "slots_per_day": 4,
            "slot_times": deepcopy(target["proposed_slot_times"]),
            "updated_at": timestamp,
        }
    }
    return filter_doc, patch


async def postcheck(db, sealed: Mapping[str, Any]) -> dict[str, Any]:
    targets = list(sealed["targets"])
    class_ids = [str(row["class_id"]) for row in targets]
    docs = await db.class_schedules.find(
        {
            "class_id": {"$in": class_ids},
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        }
    ).to_list(1000)

    by_class: dict[str, list[dict[str, Any]]] = {}
    for raw in docs:
        clean = _without_mongo_id(raw)
        by_class.setdefault(str(clean.get("class_id") or ""), []).append(clean)

    checked = 0
    preserved_update_slots = 0
    empty_create_slots = 0
    for target in targets:
        class_id = str(target["class_id"])
        schedule_id = str(target["schedule_id"])
        rows = by_class.get(class_id, [])
        if len(rows) != 1:
            raise Phase2ApplyError(
                f"POSTCHECK_SCHEDULE_COUNT_INVALID class_id={class_id} actual={len(rows)}"
            )
        row = rows[0]
        if str(row.get("id") or "") != schedule_id:
            raise Phase2ApplyError(f"POSTCHECK_ID_MISMATCH class_id={class_id}")
        if str(row.get("school_id") or "") != str(target.get("school_id") or ""):
            raise Phase2ApplyError(f"POSTCHECK_SCHOOL_MISMATCH schedule_id={schedule_id}")
        if str(row.get("shift") or "") != str(target.get("shift") or ""):
            raise Phase2ApplyError(f"POSTCHECK_SHIFT_MISMATCH schedule_id={schedule_id}")
        if int(row.get("slots_per_day") or 0) != 4:
            raise Phase2ApplyError(f"POSTCHECK_SLOTS_PER_DAY_MISMATCH schedule_id={schedule_id}")
        if row.get("slot_times") != target.get("proposed_slot_times"):
            raise Phase2ApplyError(f"POSTCHECK_SLOT_TIMES_MISMATCH schedule_id={schedule_id}")

        if target.get("mode") == "UPDATE_TIME_GRID":
            if _sha256(row.get("schedule_slots") or []) != target.get("current_schedule_slots_sha256"):
                raise Phase2ApplyError(f"POSTCHECK_SCHEDULE_SLOTS_CHANGED schedule_id={schedule_id}")
            preserved_update_slots += 1
        else:
            if (row.get("schedule_slots") or []) != []:
                raise Phase2ApplyError(f"POSTCHECK_CREATE_SCHEDULE_SLOTS_NOT_EMPTY schedule_id={schedule_id}")
            empty_create_slots += 1
        checked += 1

    if checked != EXPECTED_TARGETS:
        raise Phase2ApplyError(f"POSTCHECK_COUNT_INVALID expected={EXPECTED_TARGETS} actual={checked}")
    if preserved_update_slots != EXPECTED_UPDATES:
        raise Phase2ApplyError("POSTCHECK_UPDATE_PRESERVATION_COUNT_INVALID")
    if empty_create_slots != EXPECTED_CREATES:
        raise Phase2ApplyError("POSTCHECK_CREATE_EMPTY_COUNT_INVALID")

    return {
        "checked": checked,
        "update_schedule_slots_preserved": preserved_update_slots,
        "create_schedule_slots_empty": empty_create_slots,
    }


def write_receipt(payload: Mapping[str, Any]) -> Path:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = str(payload.get("run_id") or "run")
    path = RECEIPT_DIR / f"initial-years-phase2-{stamp}-{run_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


async def execute_apply(db, sealed: Mapping[str, Any]) -> dict[str, Any]:
    preconditions = await validate_live_preconditions(db, sealed)
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    created = 0
    updated = 0
    touched: list[dict[str, str]] = []

    try:
        # Atualiza primeiro os 33 documentos existentes com filtro otimista completo.
        for target in sealed["targets"]:
            if target.get("mode") != "UPDATE_TIME_GRID":
                continue
            schedule_id = str(target["schedule_id"])
            current = preconditions["current_by_schedule_id"][schedule_id]
            filter_doc, patch = build_update_filter_and_patch(target, current, timestamp=timestamp)
            result = await db.class_schedules.update_one(filter_doc, patch)
            if int(result.matched_count or 0) != 1 or int(result.modified_count or 0) != 1:
                raise Phase2ApplyError(
                    "UPDATE_OPTIMISTIC_CONCURRENCY_FAILED "
                    f"schedule_id={schedule_id} matched={result.matched_count} modified={result.modified_count}"
                )
            updated += 1
            touched.append({"mode": "UPDATE_TIME_GRID", "schedule_id": schedule_id, "class_id": str(target["class_id"])})

        # Criações são upserts somente por classe/ano. Se surgir concorrente, nada é sobrescrito.
        for target in sealed["targets"]:
            if target.get("mode") != "CREATE_TIME_GRID":
                continue
            doc = build_create_document(target, timestamp=timestamp)
            result = await db.class_schedules.update_one(
                {
                    "class_id": str(target["class_id"]),
                    "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
                },
                {"$setOnInsert": doc},
                upsert=True,
            )
            if result.upserted_id is None or int(result.matched_count or 0) != 0:
                raise Phase2ApplyError(
                    "CREATE_OPTIMISTIC_CONCURRENCY_FAILED "
                    f"class_id={target['class_id']} matched={result.matched_count} upserted={result.upserted_id}"
                )
            created += 1
            touched.append({"mode": "CREATE_TIME_GRID", "schedule_id": str(target["schedule_id"]), "class_id": str(target["class_id"])})

        if updated != EXPECTED_UPDATES or created != EXPECTED_CREATES:
            raise Phase2ApplyError(
                f"APPLY_COUNTS_INVALID updated={updated} created={created}"
            )

        checked = await postcheck(db, sealed)
        receipt = {
            "phase_id": PHASE_ID,
            "run_id": run_id,
            "status": "SUCCESS",
            "applied_at": timestamp,
            "approved_source_inventory_sha256": APPROVED_SOURCE_INVENTORY_SHA256,
            "approved_scope_v2_sha256": APPROVED_SCOPE_V2_SHA256,
            "approved_manifest_sha256": APPROVED_MANIFEST_SHA256,
            "approved_backup_bundle_sha256": APPROVED_BACKUP_BUNDLE_SHA256,
            "backup_dir": sealed["backup_dir"],
            "updated": updated,
            "created": created,
            "mongo_writes": updated + created,
            "postcheck": checked,
            "touched": touched,
        }
        receipt_path = write_receipt(receipt)
        return {**receipt, "receipt_path": str(receipt_path)}
    except Exception as exc:
        failure = {
            "phase_id": PHASE_ID,
            "run_id": run_id,
            "status": "FAILED_PARTIAL_OR_BLOCKED",
            "started_at": timestamp,
            "error": f"{type(exc).__name__}: {exc}",
            "approved_manifest_sha256": APPROVED_MANIFEST_SHA256,
            "approved_backup_bundle_sha256": APPROVED_BACKUP_BUNDLE_SHA256,
            "updated_before_failure": updated,
            "created_before_failure": created,
            "mongo_writes_before_failure": updated + created,
            "touched": touched,
        }
        receipt_path = write_receipt(failure)
        raise Phase2ApplyError(
            f"APPLY_FAILED receipt={receipt_path} cause={type(exc).__name__}: {exc}"
        ) from exc


async def run(db, *, backup_dir: Path, apply: bool) -> dict[str, Any]:
    sealed = load_and_verify_backup(backup_dir)
    if apply:
        return await execute_apply(db, sealed)

    preconditions = await validate_live_preconditions(db, sealed)
    return {
        "phase_id": PHASE_ID,
        "mode": "DRY_RUN",
        "approved_manifest_sha256": APPROVED_MANIFEST_SHA256,
        "approved_backup_bundle_sha256": APPROVED_BACKUP_BUNDLE_SHA256,
        "ready_targets": EXPECTED_TARGETS,
        "create_ready": preconditions["create_ready"],
        "update_ready": preconditions["update_ready"],
        "mongo_writes": 0,
        "apply_executed": False,
    }


def print_compact(result: Mapping[str, Any]) -> None:
    print("=== HORARIOS 1º AO 5º ANO — FASE 2 APPLY CONTROLADO ===")
    print("PHASE_ID:", PHASE_ID)
    print("MANIFEST_SHA256:", APPROVED_MANIFEST_SHA256)
    print("BACKUP_BUNDLE_SHA256:", APPROVED_BACKUP_BUNDLE_SHA256)
    print("MODE:", result.get("mode") or result.get("status"))
    if result.get("mode") == "DRY_RUN":
        print("READY_TARGETS:", result.get("ready_targets"))
        print("CREATE_READY:", result.get("create_ready"))
        print("UPDATE_READY:", result.get("update_ready"))
        print("MONGO_WRITES: 0")
        print("APPLY_EXECUTED: NAO")
        return
    print("UPDATED:", result.get("updated"))
    print("CREATED:", result.get("created"))
    print("MONGO_WRITES:", result.get("mongo_writes"))
    print("POSTCHECK:", json.dumps(result.get("postcheck") or {}, ensure_ascii=False, sort_keys=True))
    print("RECEIPT:", result.get("receipt_path"))
    print("APPLY_EXECUTED: SIM")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", default=str(APPROVED_BACKUP_DIR))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default=None)
    parser.add_argument("--confirm-manifest", default=None)
    parser.add_argument("--confirm-backup", default=None)
    args = parser.parse_args()

    validate_confirmation(
        apply=args.apply,
        confirm=args.confirm,
        confirm_manifest=args.confirm_manifest,
        confirm_backup=args.confirm_backup,
    )

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc")]
        result = await run(db, backup_dir=Path(args.backup_dir), apply=args.apply)
        print_compact(result)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
