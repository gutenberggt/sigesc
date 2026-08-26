"""Preflight da normalização global de horários do 1º ao 5º ano — Fase 1.

Escopo desta fase:
- somente as 69 turmas regulares classificadas READY_NORMALIZE pela V2;
- 36 turmas sem class_schedule: planeja criação;
- 33 turmas com class_schedule: planeja atualização apenas da grade temporal;
- 15 turmas bloqueadas pela V2 ficam explicitamente fora desta fase;
- AEE e EJA/ETAPA permanecem excluídas;
- MongoDB é estritamente READ-ONLY.

O preflight escreve somente artefatos de backup/manifesta no filesystem persistente.
Nenhuma criação/atualização de class_schedules é executada aqui.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
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

ACADEMIC_YEAR = 2026
EXPECTED_SOURCE_INVENTORY_SHA256 = "891e6f8bc29929ba0a4d9ca59eb7d034f0ad1617f2758b3db9a00b4d3bdcc01a"
EXPECTED_SCOPE_V2_SHA256 = "1815d025770d24f2bb109cb5598bc990f2f0ca4ce361095dc1446cbbb2de9b7d"
EXPECTED_REGULAR_TARGETS = 84
EXPECTED_EXCLUDED_NON_REGULAR = 10
EXPECTED_READY_TARGETS = 69
EXPECTED_BLOCKED_TARGETS = 15
EXPECTED_CREATE_TARGETS = 36
EXPECTED_EXISTING_TARGETS = 33
PHASE_ID = "INITIAL-YEARS-SCHEDULE-NORMALIZATION-2026-PHASE1"
CREATE_ID_NAMESPACE = uuid.UUID("b6c7e82c-2a4d-4f17-9f4f-91e73caa1206")

MONGO_MUTATOR_TOKENS = tuple(
    "." + name + "("
    for name in (
        "insert_one", "insert_many", "update_one", "update_many",
        "replace_one", "delete_one", "delete_many", "bulk_write",
        "find_one_and_update", "find_one_and_delete", "find_one_and_replace",
    )
)


class Phase1PreflightError(RuntimeError):
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
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _without_mongo_id(row: Mapping[str, Any]) -> dict[str, Any]:
    clean = deepcopy(dict(row))
    clean.pop("_id", None)
    return clean


def assert_script_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MONGO_MUTATOR_TOKENS" not in line
    )
    forbidden = [token for token in MONGO_MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise Phase1PreflightError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def validate_persistent_backup_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    text = str(resolved)
    if not resolved.is_absolute():
        raise Phase1PreflightError("BACKUP_PATH_MUST_BE_ABSOLUTE")
    if text == "/data" or not text.startswith("/data/"):
        raise Phase1PreflightError(
            f"BACKUP_PATH_MUST_BE_UNDER_DATA actual={resolved}"
        )
    return resolved


def deterministic_schedule_id(class_id: str) -> str:
    key = f"{PHASE_ID}:{ACADEMIC_YEAR}:{class_id}"
    return str(uuid.uuid5(CREATE_ID_NAMESPACE, key))


def _policy_for_shift(shift: str) -> dict[str, dict[str, str]]:
    proposed = inventory_v1.proposed_slot_times(shift)
    if proposed is None:
        raise Phase1PreflightError(f"SHIFT_POLICY_MISSING shift={shift}")
    return proposed


def validate_scope_v2(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    if (report.get("meta") or {}).get("mutates_database") is not False:
        raise Phase1PreflightError("SCOPE_V2_NOT_READ_ONLY")

    actual_scope_hash = str(report.get("scope_v2_sha256") or "")
    if actual_scope_hash != EXPECTED_SCOPE_V2_SHA256:
        raise Phase1PreflightError(
            "SCOPE_V2_SHA256_DRIFT "
            f"expected={EXPECTED_SCOPE_V2_SHA256} actual={actual_scope_hash}"
        )

    scope = report.get("scope") or {}
    source_hash = str(scope.get("source_inventory_sha256") or "")
    if source_hash != EXPECTED_SOURCE_INVENTORY_SHA256:
        raise Phase1PreflightError(
            "SOURCE_INVENTORY_SHA256_DRIFT "
            f"expected={EXPECTED_SOURCE_INVENTORY_SHA256} actual={source_hash}"
        )

    if int(scope.get("regular_target_count") or 0) != EXPECTED_REGULAR_TARGETS:
        raise Phase1PreflightError("REGULAR_TARGET_COUNT_DRIFT")
    if int(scope.get("excluded_non_regular_count") or 0) != EXPECTED_EXCLUDED_NON_REGULAR:
        raise Phase1PreflightError("EXCLUDED_NON_REGULAR_COUNT_DRIFT")

    summary = scope.get("summary") or {}
    statuses = summary.get("status") or {}
    ready_count = int(statuses.get("READY_NORMALIZE") or 0)
    blocked_count = int(statuses.get("BLOCKED_REQUIRES_REVIEW") or 0)
    if ready_count != EXPECTED_READY_TARGETS:
        raise Phase1PreflightError(
            f"READY_COUNT_DRIFT expected={EXPECTED_READY_TARGETS} actual={ready_count}"
        )
    if blocked_count != EXPECTED_BLOCKED_TARGETS:
        raise Phase1PreflightError(
            f"BLOCKED_COUNT_DRIFT expected={EXPECTED_BLOCKED_TARGETS} actual={blocked_count}"
        )

    ready_rows = [
        deepcopy(row)
        for row in (scope.get("regular_rows") or [])
        if row.get("status") == "READY_NORMALIZE"
    ]
    if len(ready_rows) != EXPECTED_READY_TARGETS:
        raise Phase1PreflightError(
            f"READY_ROWS_DRIFT expected={EXPECTED_READY_TARGETS} actual={len(ready_rows)}"
        )

    ids = [str(row.get("class_id") or "") for row in ready_rows]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise Phase1PreflightError("READY_CLASS_IDS_INVALID_OR_DUPLICATE")

    return ready_rows


def build_manifest(
    ready_rows: list[Mapping[str, Any]],
    schedule_docs: list[Mapping[str, Any]],
    id_collisions: list[Mapping[str, Any]],
) -> dict[str, Any]:
    schedules_by_class: dict[str, list[dict[str, Any]]] = {}
    for raw in schedule_docs:
        row = _without_mongo_id(raw)
        class_id = str(row.get("class_id") or "")
        schedules_by_class.setdefault(class_id, []).append(row)

    collisions_by_id = {
        str(row.get("id") or ""): _without_mongo_id(row)
        for row in id_collisions
        if row.get("id")
    }

    targets: list[dict[str, Any]] = []
    create_count = 0
    existing_count = 0
    existing_write_required = 0
    existing_already_compliant = 0

    for source_row in sorted(
        ready_rows,
        key=lambda row: (
            str(row.get("school_name") or "").casefold(),
            str(row.get("class_name") or "").casefold(),
            str(row.get("class_id") or ""),
        ),
    ):
        row = dict(source_row)
        class_id = str(row.get("class_id") or "")
        shift = str(row.get("shift") or "")
        policy = _policy_for_shift(shift)
        if row.get("proposed_slot_times") != policy:
            raise Phase1PreflightError(
                f"PROPOSED_POLICY_DRIFT class_id={class_id} shift={shift}"
            )

        expected_schedule_count = int(row.get("schedule_count") or 0)
        current_docs = schedules_by_class.get(class_id, [])
        if len(current_docs) != expected_schedule_count:
            raise Phase1PreflightError(
                "SCHEDULE_COUNT_DRIFT "
                f"class_id={class_id} source={expected_schedule_count} db={len(current_docs)}"
            )
        if expected_schedule_count not in {0, 1}:
            raise Phase1PreflightError(
                f"READY_ROW_WITH_NON_UNIQUE_SCHEDULE class_id={class_id} count={expected_schedule_count}"
            )

        common = {
            "class_id": class_id,
            "class_name": row.get("class_name"),
            "school_id": row.get("school_id"),
            "school_name": row.get("school_name"),
            "academic_year": ACADEMIC_YEAR,
            "shift": shift,
            "series": (row.get("grade_evidence") or {}).get("combined_numbers"),
            "is_multi_grade": bool((row.get("grade_evidence") or {}).get("is_multi_grade")),
            "proposed_slots_per_day": 4,
            "proposed_slot_times": policy,
        }

        if expected_schedule_count == 0:
            create_count += 1
            proposed_id = deterministic_schedule_id(class_id)
            collision = collisions_by_id.get(proposed_id)
            if collision:
                raise Phase1PreflightError(
                    "DETERMINISTIC_ID_COLLISION "
                    f"class_id={class_id} proposed_id={proposed_id} "
                    f"existing_class_id={collision.get('class_id')}"
                )
            targets.append(
                {
                    **common,
                    "mode": "CREATE_TIME_GRID",
                    "schedule_id": proposed_id,
                    "current_document_sha256": None,
                    "current_schedule_slots_sha256": None,
                    "current_slots_per_day": None,
                    "current_slot_times": None,
                    "preserve_schedule_slots": False,
                    "proposed_schedule_slots": [],
                    "write_required": True,
                }
            )
            continue

        existing_count += 1
        current = current_docs[0]
        current_id = str(current.get("id") or "")
        source_shape = row.get("schedule_shape") or {}
        source_schedule_id = str(source_shape.get("schedule_id") or "")
        if not current_id or current_id != source_schedule_id:
            raise Phase1PreflightError(
                "SCHEDULE_ID_DRIFT "
                f"class_id={class_id} source={source_schedule_id} db={current_id}"
            )
        if str(current.get("school_id") or "") != str(row.get("school_id") or ""):
            raise Phase1PreflightError(f"SCHEDULE_SCHOOL_DRIFT class_id={class_id}")
        if str(current.get("shift") or "") != shift:
            raise Phase1PreflightError(
                f"SCHEDULE_SHIFT_DRIFT class_id={class_id} class_shift={shift} schedule_shift={current.get('shift')}"
            )

        current_slot_times = deepcopy(current.get("slot_times") or {})
        current_slots_per_day = current.get("slots_per_day")
        schedule_slots = deepcopy(current.get("schedule_slots") or [])
        write_required = not (
            current_slots_per_day == 4
            and current_slot_times == policy
        )
        if write_required:
            existing_write_required += 1
        else:
            existing_already_compliant += 1

        targets.append(
            {
                **common,
                "mode": "UPDATE_TIME_GRID",
                "schedule_id": current_id,
                "current_document_sha256": _sha256(current),
                "current_schedule_slots_sha256": _sha256(schedule_slots),
                "current_slots_per_day": current_slots_per_day,
                "current_slot_times": current_slot_times,
                "current_updated_at": current.get("updated_at"),
                "preserve_schedule_slots": True,
                "schedule_slots_count": len(schedule_slots) if isinstance(schedule_slots, list) else None,
                "write_required": write_required,
            }
        )

    core = {
        "phase_id": PHASE_ID,
        "academic_year": ACADEMIC_YEAR,
        "source_inventory_sha256": EXPECTED_SOURCE_INVENTORY_SHA256,
        "scope_v2_sha256": EXPECTED_SCOPE_V2_SHA256,
        "policy": {
            shift: inventory_v1.proposed_slot_times(shift)
            for shift in ("morning", "afternoon")
        },
        "target_count": len(targets),
        "create_target_count": create_count,
        "existing_target_count": existing_count,
        "existing_write_required_count": existing_write_required,
        "existing_already_compliant_count": existing_already_compliant,
        "blocked_outside_phase1_count": EXPECTED_BLOCKED_TARGETS,
        "targets": targets,
    }
    return {
        "manifest": core,
        "manifest_sha256": _sha256(core),
    }


def validate_production_manifest_counts(manifest: Mapping[str, Any]) -> None:
    if int(manifest.get("target_count") or 0) != EXPECTED_READY_TARGETS:
        raise Phase1PreflightError("MANIFEST_TARGET_COUNT_DRIFT")
    if int(manifest.get("create_target_count") or 0) != EXPECTED_CREATE_TARGETS:
        raise Phase1PreflightError(
            "CREATE_TARGET_COUNT_DRIFT "
            f"expected={EXPECTED_CREATE_TARGETS} actual={manifest.get('create_target_count')}"
        )
    if int(manifest.get("existing_target_count") or 0) != EXPECTED_EXISTING_TARGETS:
        raise Phase1PreflightError(
            "EXISTING_TARGET_COUNT_DRIFT "
            f"expected={EXPECTED_EXISTING_TARGETS} actual={manifest.get('existing_target_count')}"
        )
    if (
        int(manifest.get("existing_write_required_count") or 0)
        + int(manifest.get("existing_already_compliant_count") or 0)
        != EXPECTED_EXISTING_TARGETS
    ):
        raise Phase1PreflightError("EXISTING_COMPLIANCE_COUNTS_INVALID")


def _write_json(path: Path, value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
    path.write_text(text, encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if _sha256(loaded) != _sha256(value):
        raise Phase1PreflightError(f"BACKUP_WRITE_VERIFY_FAILED path={path}")
    return _sha256(value)


def write_backup_directory(
    backup_dir: Path,
    *,
    scope_report: Mapping[str, Any],
    manifest_result: Mapping[str, Any],
    existing_schedules: list[Mapping[str, Any]],
) -> dict[str, Any]:
    resolved = validate_persistent_backup_path(backup_dir)
    if resolved.exists() and any(resolved.iterdir()):
        raise Phase1PreflightError(f"BACKUP_DIR_NOT_EMPTY path={resolved}")
    resolved.mkdir(parents=True, exist_ok=True)

    existing_clean = sorted(
        [_without_mongo_id(row) for row in existing_schedules],
        key=lambda row: (str(row.get("class_id") or ""), str(row.get("id") or "")),
    )
    if len(existing_clean) != EXPECTED_EXISTING_TARGETS:
        raise Phase1PreflightError(
            f"BACKUP_EXISTING_COUNT_DRIFT expected={EXPECTED_EXISTING_TARGETS} actual={len(existing_clean)}"
        )

    scope_payload = {
        "meta": scope_report.get("meta"),
        "scope_v2_sha256": scope_report.get("scope_v2_sha256"),
        "scope": scope_report.get("scope"),
    }
    manifest_payload = manifest_result.get("manifest")
    hashes = {
        "scope_v2_snapshot_sha256": _write_json(resolved / "scope_v2_snapshot.json", scope_payload),
        "manifest_sha256": _write_json(resolved / "manifest.json", manifest_payload),
        "existing_class_schedules_sha256": _write_json(
            resolved / "existing_class_schedules.json", existing_clean
        ),
    }
    if hashes["manifest_sha256"] != manifest_result.get("manifest_sha256"):
        raise Phase1PreflightError("MANIFEST_HASH_CHANGED_DURING_BACKUP")

    metadata_core = {
        "phase_id": PHASE_ID,
        "academic_year": ACADEMIC_YEAR,
        "source_inventory_sha256": EXPECTED_SOURCE_INVENTORY_SHA256,
        "scope_v2_sha256": EXPECTED_SCOPE_V2_SHA256,
        "manifest_sha256": manifest_result.get("manifest_sha256"),
        "existing_schedule_count": len(existing_clean),
        "file_hashes": hashes,
    }
    bundle_sha = _sha256(metadata_core)
    metadata = {
        **metadata_core,
        "backup_bundle_sha256": bundle_sha,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mongo_writes": 0,
        "apply_executed": False,
    }
    _write_json(resolved / "metadata.json", metadata)

    return {
        "backup_dir": str(resolved),
        "backup_bundle_sha256": bundle_sha,
        "file_hashes": hashes,
    }


async def run_preflight(db, *, backup_dir: Path) -> dict[str, Any]:
    assert_script_read_only()
    inventory_v1.assert_script_read_only()
    inventory_v2.assert_script_read_only()
    validate_persistent_backup_path(backup_dir)

    scope_report = await inventory_v2.collect_inventory_v2(db)
    ready_rows = validate_scope_v2(scope_report)
    ready_ids = [str(row.get("class_id")) for row in ready_rows]

    schedule_docs = await db.class_schedules.find(
        {
            "class_id": {"$in": ready_ids},
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        }
    ).to_list(1000)

    create_rows = [row for row in ready_rows if int(row.get("schedule_count") or 0) == 0]
    proposed_ids = [deterministic_schedule_id(str(row.get("class_id"))) for row in create_rows]
    id_collisions = []
    if proposed_ids:
        id_collisions = await db.class_schedules.find(
            {"id": {"$in": proposed_ids}},
            {"_id": 0, "id": 1, "class_id": 1, "school_id": 1, "academic_year": 1},
        ).to_list(1000)

    manifest_result = build_manifest(ready_rows, schedule_docs, id_collisions)
    validate_production_manifest_counts(manifest_result["manifest"])

    existing_schedules = [
        row for row in schedule_docs
        if str(row.get("class_id") or "") in set(ready_ids)
    ]
    backup = write_backup_directory(
        backup_dir,
        scope_report=scope_report,
        manifest_result=manifest_result,
        existing_schedules=existing_schedules,
    )

    return {
        "scope_report": scope_report,
        "manifest_result": manifest_result,
        "backup": backup,
    }


def print_compact(result: Mapping[str, Any]) -> None:
    manifest_result = result["manifest_result"]
    manifest = manifest_result["manifest"]
    backup = result["backup"]
    print("=== HORARIOS 1º AO 5º ANO — FASE 1 PREFLIGHT READ-ONLY ===")
    print("PHASE_ID:", PHASE_ID)
    print("SOURCE_INVENTORY_SHA256:", EXPECTED_SOURCE_INVENTORY_SHA256)
    print("SCOPE_V2_SHA256:", EXPECTED_SCOPE_V2_SHA256)
    print("READY_TARGETS:", manifest["target_count"])
    print("CREATE_TARGETS:", manifest["create_target_count"])
    print("EXISTING_TARGETS:", manifest["existing_target_count"])
    print("EXISTING_WRITE_REQUIRED:", manifest["existing_write_required_count"])
    print("EXISTING_ALREADY_COMPLIANT:", manifest["existing_already_compliant_count"])
    print("BLOCKED_OUTSIDE_PHASE1:", manifest["blocked_outside_phase1_count"])
    print("MANIFEST_SHA256:", manifest_result["manifest_sha256"])
    print("BACKUP_DIR:", backup["backup_dir"])
    print("BACKUP_BUNDLE_SHA256:", backup["backup_bundle_sha256"])
    print("BACKUP_EXISTING_SCHEDULES:", EXPECTED_EXISTING_TARGETS)
    print("MONGO_WRITES: 0")
    print("APPLY_EXECUTED: NAO")


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
