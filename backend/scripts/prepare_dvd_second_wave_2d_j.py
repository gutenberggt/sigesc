"""Segunda Onda DVD 2D-J — preflight read-only dos 2 vínculos restantes de Juliana.

Escopo fixo:
- Juliana da Silva Leao;
- CMEI Professora Nivalda Maria de Godoy / Berçario II A / 2026;
- Contação de Histórias e Iniciação Musical;
- Higiene e Saúde.

Esta etapa NÃO aplica vínculos e NÃO altera class_schedules. O MongoDB é somente
lido. O preflight pode gravar um bundle de backup/manifesto no volume persistente
apenas depois de todos os gates passarem.

A 2D-J é diferente da 2C: os horários desses dois componentes estão integralmente
dentro da grade declarada e a carga semanal coincide exatamente com os slots.
O antigo P0 os bloqueia apenas porque foi desenhado para exigir resíduo fora da
grade. Além disso, como não há nota real, o perfil regular/integrator não pode ser
inferido. Por isso a 2D-J exige consenso de perfil entre vínculos DVD ativos do
mesmo componente, na mesma escola e no mesmo ano, com pelo menos dois pares.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional
import uuid

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
    build_in_range_weekly_slots,
)

load_dotenv(BACKEND_DIR / ".env")

ACADEMIC_YEAR = 2026
REFERENCE_DATE = "2026-08-18"
TEACHER_USER_ID = "2e5004ac-dad2-4d07-a6aa-372ff49bb54a"
STAFF_ID = "a2dfe7d1-b135-46f8-b347-0b21b8bc906c"
CLASS_ID = "a76ccc2c-317c-4bd6-8b39-ed5fa806d67c"
SCHOOL_ID = "1279c538-94c9-4c6b-a0de-994ed73c9f6f"
APPROVED_READY_COUNT = 2
REQUIRED_SLOTS_PER_DAY = 7
REQUIRED_PEER_PROFILE_MIN_COUNT = 2
PERSISTENT_BACKUP_ROOT = Path("/data/sigesc-dvd-backups")
BACKUP_MODE = "SECOND_WAVE_2D_J_PREFLIGHT_READ_ONLY"
PROVENANCE_PHASE = "SECOND_WAVE_2D_J_PREFLIGHT"
REQUIRED_EVIDENCE = "exact_schedule_exact_workload_peer_profile_consensus"

APPROVED_TARGETS = {
    "1f08bfe3-b486-4266-81bc-2f03fe72a3a4": {
        "component_id": "e90107dc-3276-4480-852b-91f617eefc67",
        "component_name": "Contação de Histórias e Iniciação Musical",
        "workload": 5,
        "weekly_slots": [
            {"weekday": 1, "aula_numero": 5, "start_time": "13:00", "end_time": "13:40"},
            {"weekday": 2, "aula_numero": 7, "start_time": "14:50", "end_time": "15:55"},
            {"weekday": 3, "aula_numero": 5, "start_time": "13:00", "end_time": "13:40"},
            {"weekday": 4, "aula_numero": 6, "start_time": "13:40", "end_time": "14:30"},
            {"weekday": 5, "aula_numero": 5, "start_time": "13:00", "end_time": "13:40"},
        ],
    },
    "7d62a0df-c601-4288-b4ef-18093d3c37cf": {
        "component_id": "7cce8ff9-9cd1-4737-a4ed-a61554a711dc",
        "component_name": "Higiene e Saúde",
        "workload": 3,
        "weekly_slots": [
            {"weekday": 1, "aula_numero": 7, "start_time": "14:50", "end_time": "15:55"},
            {"weekday": 3, "aula_numero": 7, "start_time": "14:50", "end_time": "15:55"},
            {"weekday": 4, "aula_numero": 7, "start_time": "14:50", "end_time": "15:55"},
        ],
    },
}

MONGO_MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


class PreflightGateError(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def manifest_digest(items: list[Mapping[str, Any]]) -> str:
    return hashlib.sha256(_canonical(items).encode("utf-8")).hexdigest()


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


def _is_active_on_reference(row: Mapping[str, Any]) -> bool:
    valid_from = str(row.get("valid_from") or "")[:10]
    valid_until = str(row.get("valid_until") or "")[:10]
    if valid_from and valid_from > REFERENCE_DATE:
        return False
    if valid_until and valid_until < REFERENCE_DATE:
        return False
    return True


def validate_exact_schedule_result(
    legacy_id: str,
    result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if legacy_id not in APPROVED_TARGETS:
        raise PreflightGateError(f"TARGET_NOT_APPROVED legacy={legacy_id}")
    expected = APPROVED_TARGETS[legacy_id]
    blockers = set(str(x) for x in (result.get("blockers") or []))
    if blockers != {"no_out_of_range_residue"}:
        raise PreflightGateError(
            f"SCHEDULE_GATE_MISMATCH legacy={legacy_id} blockers={sorted(blockers)}"
        )
    if int(result.get("slots_per_day") or 0) != REQUIRED_SLOTS_PER_DAY:
        raise PreflightGateError(f"SLOTS_PER_DAY_MISMATCH legacy={legacy_id}")
    if result.get("stale_slots"):
        raise PreflightGateError(f"STALE_SLOTS_UNEXPECTED legacy={legacy_id}")
    weekly_slots = list(result.get("weekly_slots") or [])
    if weekly_slots != expected["weekly_slots"]:
        raise PreflightGateError(
            f"WEEKLY_SLOTS_DRIFT legacy={legacy_id} expected={expected['weekly_slots']} actual={weekly_slots}"
        )
    if len(weekly_slots) != int(expected["workload"]):
        raise PreflightGateError(f"WORKLOAD_SLOT_COUNT_MISMATCH legacy={legacy_id}")
    return weekly_slots


def resolve_peer_profile(
    component_id: str,
    peers: list[Mapping[str, Any]],
) -> dict[str, Any]:
    active = [
        row for row in peers
        if str(row.get("component_id") or "") == component_id
        and (row.get("diary_settings") or {}).get("enabled") is True
        and not row.get("is_substitute")
        and row.get("deleted") is not True
        and _is_active_on_reference(row)
    ]
    if len(active) < REQUIRED_PEER_PROFILE_MIN_COUNT:
        raise PreflightGateError(
            f"PEER_PROFILE_EVIDENCE_INSUFFICIENT component={component_id} "
            f"required={REQUIRED_PEER_PROFILE_MIN_COUNT} actual={len(active)}"
        )

    profiles = Counter(str((row.get("diary_settings") or {}).get("profile") or "") for row in active)
    scopes = Counter(str((row.get("diary_settings") or {}).get("student_scope") or "") for row in active)

    if len(profiles) != 1:
        raise PreflightGateError(
            f"PEER_PROFILE_AMBIGUOUS component={component_id} profiles={dict(sorted(profiles.items()))}"
        )
    profile = next(iter(profiles))
    if profile not in {"regular", "integrator"}:
        raise PreflightGateError(f"PEER_PROFILE_NOT_ALLOWED component={component_id} profile={profile}")
    if set(scopes) != {"all"}:
        raise PreflightGateError(
            f"PEER_STUDENT_SCOPE_AMBIGUOUS component={component_id} scopes={dict(sorted(scopes.items()))}"
        )
    return {
        "profile": profile,
        "student_scope": "all",
        "peer_count": len(active),
        "profile_counts": dict(sorted(profiles.items())),
    }


def deterministic_assignment_id(
    *,
    source_legacy_assignment_id: str,
    component_id: str,
    valid_from: str,
) -> str:
    seed = "|".join(
        [
            "sigesc-dvd-second-wave-2d-j-v1",
            source_legacy_assignment_id,
            TEACHER_USER_ID,
            CLASS_ID,
            component_id,
            valid_from,
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


async def collect_2d_j_manifest(db) -> dict[str, Any]:
    teacher = await db.users.find_one(
        {"id": TEACHER_USER_ID},
        {"_id": 0, "id": 1, "full_name": 1, "name": 1, "email": 1},
    )
    if not teacher:
        raise PreflightGateError("TEACHER_USER_NOT_FOUND")

    staff = await db.staff.find_one(
        {"id": STAFF_ID},
        {"_id": 0, "id": 1, "user_id": 1, "nome": 1, "full_name": 1, "email": 1},
    )
    if not staff:
        raise PreflightGateError("STAFF_NOT_FOUND")
    if staff.get("user_id") and str(staff.get("user_id")) != TEACHER_USER_ID:
        raise PreflightGateError("STAFF_USER_ID_MISMATCH")
    if not staff.get("user_id") and teacher.get("email") and str(staff.get("email") or "").casefold() != str(teacher.get("email") or "").casefold():
        raise PreflightGateError("STAFF_EMAIL_IDENTITY_MISMATCH")

    klass = await db.classes.find_one({"id": CLASS_ID}, {"_id": 0})
    if not klass:
        raise PreflightGateError("CLASS_NOT_FOUND")
    if str(klass.get("school_id") or "") != SCHOOL_ID:
        raise PreflightGateError("CLASS_SCHOOL_MISMATCH")
    if str(klass.get("academic_year") or "") not in {"", str(ACADEMIC_YEAR)}:
        raise PreflightGateError("CLASS_ACADEMIC_YEAR_MISMATCH")

    schedules = await db.class_schedules.find(
        {"class_id": CLASS_ID, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
        {"_id": 0},
    ).to_list(10)
    if len(schedules) != 1:
        raise PreflightGateError(f"SCHEDULE_DOCUMENT_NOT_UNIQUE count={len(schedules)}")
    schedule = schedules[0]
    if int(schedule.get("slots_per_day") or 0) != REQUIRED_SLOTS_PER_DAY:
        raise PreflightGateError("SCHEDULE_SLOTS_PER_DAY_DRIFT")

    target_legacy_ids = sorted(APPROVED_TARGETS)
    legacy = await db.teacher_assignments.find(
        {
            "id": {"$in": target_legacy_ids},
            "staff_id": STAFF_ID,
            "class_id": CLASS_ID,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "status": "ativo",
        },
        {"_id": 0},
    ).to_list(10)
    legacy_by_id = {str(row.get("id") or ""): row for row in legacy if row.get("id")}
    if set(legacy_by_id) != set(target_legacy_ids):
        raise PreflightGateError(
            f"TARGET_LEGACY_SET_MISMATCH expected={target_legacy_ids} actual={sorted(legacy_by_id)}"
        )

    component_ids = sorted({str(v["component_id"]) for v in APPROVED_TARGETS.values()})
    courses = await db.courses.find(
        {"id": {"$in": component_ids}}, {"_id": 0, "id": 1, "name": 1}
    ).to_list(10)
    course_names = {str(row.get("id")): str(row.get("name") or "") for row in courses if row.get("id")}

    class_year_docs = await db.classes.find(
        {"school_id": SCHOOL_ID, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
        {"_id": 0, "id": 1},
    ).to_list(1000)
    school_class_ids = sorted({str(row.get("id")) for row in class_year_docs if row.get("id")})

    peer_rows = await db.teacher_class_assignments.find(
        {
            "class_id": {"$in": school_class_ids},
            "component_id": {"$in": component_ids},
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
    ).to_list(10000)

    current_class_assignments = await db.teacher_class_assignments.find(
        {"class_id": CLASS_ID, "deleted": {"$ne": True}}, {"_id": 0}
    ).to_list(1000)

    target_keys = {(TEACHER_USER_ID, CLASS_ID, cid) for cid in component_ids}
    existing_target = [
        row for row in current_class_assignments
        if (str(row.get("teacher_id") or ""), str(row.get("class_id") or ""), str(row.get("component_id") or "")) in target_keys
        and _is_active_on_reference(row)
    ]
    if existing_target:
        raise PreflightGateError(
            f"TARGET_ALREADY_HAS_DVD ids={sorted(str(row.get('id') or '') for row in existing_target)}"
        )

    current_component_conflicts = [
        row for row in current_class_assignments
        if str(row.get("component_id") or "") in component_ids and _is_active_on_reference(row)
    ]
    if current_component_conflicts:
        raise PreflightGateError(
            "CLASS_COMPONENT_DVD_CONFLICT "
            f"ids={sorted(str(row.get('id') or '') for row in current_component_conflicts)}"
        )

    sibling_rows = [
        row for row in current_class_assignments
        if str(row.get("teacher_id") or "") == TEACHER_USER_ID
        and (row.get("diary_settings") or {}).get("enabled") is True
        and not row.get("is_substitute")
        and _is_active_on_reference(row)
    ]
    sibling_valid_from = sorted({str(row.get("valid_from") or "")[:10] for row in sibling_rows if row.get("valid_from")})
    if not sibling_rows:
        raise PreflightGateError("CURRENT_DVD_SIBLING_EVIDENCE_MISSING")
    if len(sibling_valid_from) != 1:
        raise PreflightGateError(f"CURRENT_DVD_VALID_FROM_AMBIGUOUS values={sibling_valid_from}")
    valid_from = sibling_valid_from[0]

    manifest: list[dict[str, Any]] = []
    peer_evidence: dict[str, Any] = {}

    for legacy_id in target_legacy_ids:
        expected = APPROVED_TARGETS[legacy_id]
        source = legacy_by_id[legacy_id]
        component_id = str(source.get("course_id") or "")
        if component_id != expected["component_id"]:
            raise PreflightGateError(f"COMPONENT_ID_DRIFT legacy={legacy_id}")
        if course_names.get(component_id) != expected["component_name"]:
            raise PreflightGateError(
                f"COMPONENT_NAME_DRIFT legacy={legacy_id} actual={course_names.get(component_id)!r}"
            )
        if source.get("is_substituicao") or source.get("substituto_staff_id") or source.get("data_substituicao"):
            raise PreflightGateError(f"SUBSTITUTION_REVIEW legacy={legacy_id}")
        try:
            workload = int(source.get("carga_horaria_semanal"))
        except (TypeError, ValueError) as exc:
            raise PreflightGateError(f"WORKLOAD_INVALID legacy={legacy_id}") from exc
        if workload != int(expected["workload"]):
            raise PreflightGateError(
                f"WORKLOAD_DRIFT legacy={legacy_id} expected={expected['workload']} actual={workload}"
            )

        competing_legacy = await db.teacher_assignments.find(
            {
                "class_id": CLASS_ID,
                "course_id": component_id,
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
                "status": "ativo",
            },
            {"_id": 0, "id": 1, "staff_id": 1, "is_substituicao": 1, "substituto_staff_id": 1},
        ).to_list(100)
        non_substitute_staff = {
            str(row.get("staff_id") or "")
            for row in competing_legacy
            if not row.get("is_substituicao") and not row.get("substituto_staff_id") and row.get("staff_id")
        }
        if non_substitute_staff != {STAFF_ID}:
            raise PreflightGateError(
                f"LEGACY_TEACHER_OWNERSHIP_NOT_UNIQUE legacy={legacy_id} staff={sorted(non_substitute_staff)}"
            )

        schedule_result = build_in_range_weekly_slots(
            schedule,
            course_id=component_id,
            expected_workload=workload,
        )
        weekly_slots = validate_exact_schedule_result(legacy_id, schedule_result)

        profile_evidence = resolve_peer_profile(component_id, peer_rows)
        peer_evidence[legacy_id] = profile_evidence

        manifest.append(
            {
                "id": deterministic_assignment_id(
                    source_legacy_assignment_id=legacy_id,
                    component_id=component_id,
                    valid_from=valid_from,
                ),
                "teacher_id": TEACHER_USER_ID,
                "teacher_name": teacher.get("full_name") or teacher.get("name") or staff.get("nome"),
                "class_id": CLASS_ID,
                "class_name": klass.get("name"),
                "school_id": SCHOOL_ID,
                "mantenedora_id": klass.get("mantenedora_id") or source.get("mantenedora_id"),
                "component_id": component_id,
                "component_name": expected["component_name"],
                "weekly_slots": weekly_slots,
                "valid_from": valid_from,
                "valid_until": None,
                "is_substitute": False,
                "source": "import",
                "diary_settings": {
                    "enabled": True,
                    "schema_version": 1,
                    "profile": profile_evidence["profile"],
                    "student_scope": "all",
                },
                "cutover_provenance": {
                    "phase": PROVENANCE_PHASE,
                    "state": "DRY_RUN_ONLY",
                    "source_legacy_assignment_id": legacy_id,
                    "evidence": REQUIRED_EVIDENCE,
                    "schedule_state": "schedule_ready",
                    "slots_per_day": REQUIRED_SLOTS_PER_DAY,
                    "workload": workload,
                    "peer_profile": profile_evidence["profile"],
                    "peer_profile_count": profile_evidence["peer_count"],
                },
            }
        )

    manifest.sort(key=lambda row: (str(row.get("component_name") or "").casefold(), str(row.get("id") or "")))
    if len(manifest) != APPROVED_READY_COUNT:
        raise PreflightGateError(
            f"READY_COUNT_MISMATCH expected={APPROVED_READY_COUNT} actual={len(manifest)}"
        )

    return {
        "manifest": manifest,
        "manifest_sha256": manifest_digest(manifest),
        "peer_evidence": peer_evidence,
        "valid_from": valid_from,
        "school_class_count": len(school_class_ids),
        "current_sibling_count": len(sibling_rows),
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
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        checksums[filename] = sha256_file(path)
        if isinstance(payload, list):
            counts[filename] = len(payload)

    metadata = {
        "mode": BACKUP_MODE,
        "mutates_database": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "academic_year": ACADEMIC_YEAR,
        "reference_date": REFERENCE_DATE,
        "teacher_user_id": TEACHER_USER_ID,
        "staff_id": STAFF_ID,
        "class_id": CLASS_ID,
        "school_id": SCHOOL_ID,
        "second_wave_2d_j_ready": len(validated.get("manifest") or []),
        "manifest_sha256": validated["manifest_sha256"],
        "valid_from": validated["valid_from"],
        "peer_evidence": validated["peer_evidence"],
        "school_class_count": validated["school_class_count"],
        "current_sibling_count": validated["current_sibling_count"],
        "file_counts": counts,
        "file_sha256": checksums,
    }
    metadata_path = backup_dir / "backup-metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    checksums[metadata_path.name] = sha256_file(metadata_path)

    bundle_digest = sha256_value({"file_sha256": checksums})
    seal = {"backup_bundle_sha256": bundle_digest, "files": checksums}
    (backup_dir / "BACKUP-SEAL.json").write_text(
        json.dumps(seal, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {**metadata, **seal}


async def run_preflight(db, *, backup_dir: Path) -> dict[str, Any]:
    assert_script_read_only()
    validate_persistent_backup_path(backup_dir)
    validated = await collect_2d_j_manifest(db)
    bundle = await collect_backup_bundle(
        db,
        validated["manifest"],
        academic_year=ACADEMIC_YEAR,
    )
    backup = write_backup_directory(backup_dir, validated=validated, bundle=bundle)
    return {"validated": validated, "backup": backup, "backup_dir": str(backup_dir)}


def print_compact(result: Mapping[str, Any]) -> None:
    v = result["validated"]
    b = result["backup"]
    print("=== DVD SEGUNDA ONDA 2D-J — PREFLIGHT READ-ONLY ===")
    print("READY_2D_J:", len(v["manifest"]))
    print("ESPERADO:", APPROVED_READY_COUNT)
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
    backup_dir = Path(args.backup_dir)

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc")]
        result = await run_preflight(db, backup_dir=backup_dir)
        print_compact(result)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
