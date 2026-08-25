"""P0 — remedia vínculos DVD omitidos por slots residuais fora da grade declarada.

O script é fail-closed e NÃO altera ``class_schedules`` nem conteúdo pedagógico.
Ele cria somente ``teacher_class_assignments`` ausentes quando toda a evidência
necessária já existe no SIGESC:

- professor↔staff resolvido;
- alocação legada ativa e não substituta;
- existe exatamente um horário da turma/ano;
- ``slots_per_day`` define a grade efetiva;
- o componente possui pelo menos um slot residual acima de ``slots_per_day``;
- todos os slots dentro da grade possuem dia e horário completos;
- a quantidade de slots válidos coincide exatamente com
  ``carga_horaria_semanal`` da alocação;
- há vínculo DVD ``regular`` já vigente do mesmo professor e mesma turma,
  fornecendo evidência de perfil e ``valid_from``;
- não existe DVD atual para professor+turma+componente.

Default: dry-run.
Apply:    --apply --confirm APPLY-P0-DVD-OUT-OF-RANGE
Rollback: --rollback --confirm ROLLBACK-P0-DVD-OUT-OF-RANGE
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
import re
import sys
from typing import Any, Mapping, Optional
import uuid

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from scripts.audit_dvd_cutover_plan import normalize_day  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

APPLY_CONFIRMATION = "APPLY-P0-DVD-OUT-OF-RANGE"
ROLLBACK_CONFIRMATION = "ROLLBACK-P0-DVD-OUT-OF-RANGE"
PROVENANCE_PHASE = "P0_DVD_OUT_OF_RANGE_SCHEDULE_REMEDIATION"
ACTOR = "dvd-out-of-range-schedule-p0"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class RemediationGateError(RuntimeError):
    pass


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _valid_pair(start: Any, end: Any) -> bool:
    s = str(start or "").strip()
    e = str(end or "").strip()
    return bool(TIME_RE.fullmatch(s) and TIME_RE.fullmatch(e) and e > s)


def _slot_pair(schedule: Mapping[str, Any], raw: Mapping[str, Any], n: int) -> Optional[tuple[str, str]]:
    start = raw.get("start_time")
    end = raw.get("end_time")
    if _valid_pair(start, end):
        return str(start).strip(), str(end).strip()
    definition = (schedule.get("slot_times") or {}).get(str(n))
    if definition is None:
        definition = (schedule.get("slot_times") or {}).get(n)
    if isinstance(definition, Mapping):
        start = definition.get("start") or definition.get("start_time")
        end = definition.get("end") or definition.get("end_time")
        if _valid_pair(start, end):
            return str(start).strip(), str(end).strip()
    return None


def build_in_range_weekly_slots(
    schedule: Mapping[str, Any],
    *,
    course_id: str,
    expected_workload: int,
) -> dict[str, Any]:
    """Deriva weekly_slots ignorando apenas resíduos acima de slots_per_day.

    Não inventa horários. Qualquer inconsistência dentro da grade declarada
    bloqueia o componente.
    """
    slots_per_day = _int(schedule.get("slots_per_day"))
    if slots_per_day is None or not 1 <= slots_per_day <= 12:
        return {"ready": False, "blockers": ["slots_per_day_invalid"], "weekly_slots": [], "stale_slots": []}
    if expected_workload <= 0:
        return {"ready": False, "blockers": ["workload_invalid"], "weekly_slots": [], "stale_slots": []}

    weekly_slots: list[dict[str, Any]] = []
    stale_slots: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen: set[tuple[int, int]] = set()

    component_rows = [
        raw for raw in (schedule.get("schedule_slots") or [])
        if str(raw.get("course_id") or "") == str(course_id or "")
    ]
    if not component_rows:
        return {"ready": False, "blockers": ["component_absent_from_schedule"], "weekly_slots": [], "stale_slots": []}

    for raw in component_rows:
        n = _int(raw.get("slot_number") or raw.get("aula_numero"))
        if n is None or n < 1:
            blockers.append("slot_number_invalid")
            continue
        if n > slots_per_day:
            stale_slots.append(dict(raw))
            continue

        weekday = normalize_day(raw.get("day") or raw.get("weekday"))
        if weekday is None:
            blockers.append("weekday_invalid_in_range")
            continue
        pair = _slot_pair(schedule, raw, n)
        if pair is None:
            blockers.append("slot_time_invalid_in_range")
            continue

        key = (weekday, n)
        if key in seen:
            blockers.append("duplicate_in_range_slot")
            continue
        seen.add(key)
        weekly_slots.append({
            "weekday": weekday,
            "aula_numero": n,
            "start_time": pair[0],
            "end_time": pair[1],
        })

    if not stale_slots:
        blockers.append("no_out_of_range_residue")
    if len(weekly_slots) != expected_workload:
        blockers.append(
            f"workload_mismatch:expected={expected_workload}:valid_slots={len(weekly_slots)}"
        )

    weekly_slots.sort(key=lambda item: (item["weekday"], item["aula_numero"]))
    return {
        "ready": not blockers,
        "blockers": sorted(set(blockers)),
        "weekly_slots": weekly_slots,
        "stale_slots": stale_slots,
        "slots_per_day": slots_per_day,
    }


def deterministic_assignment_id(
    *,
    source_legacy_assignment_id: str,
    teacher_id: str,
    class_id: str,
    component_id: str,
    valid_from: str,
) -> str:
    seed = "|".join([
        "sigesc-p0-dvd-out-of-range-v1",
        source_legacy_assignment_id,
        teacher_id,
        class_id,
        component_id,
        valid_from,
    ])
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def manifest_digest(items: list[Mapping[str, Any]]) -> str:
    raw = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def collect_manifest(
    db,
    *,
    teacher_user_id: str,
    class_id: str,
    academic_year: int,
) -> dict[str, Any]:
    teacher = await db.users.find_one({"id": teacher_user_id}, {"_id": 0, "id": 1, "full_name": 1, "name": 1, "email": 1})
    if not teacher:
        raise RemediationGateError("TEACHER_USER_NOT_FOUND")

    staff = await db.staff.find_one({"user_id": teacher_user_id}, {"_id": 0, "id": 1, "user_id": 1, "nome": 1, "full_name": 1, "email": 1})
    if not staff and teacher.get("email"):
        staff = await db.staff.find_one({"email": teacher.get("email")}, {"_id": 0, "id": 1, "user_id": 1, "nome": 1, "full_name": 1, "email": 1})
    if not staff:
        raise RemediationGateError("TEACHER_STAFF_NOT_FOUND")

    klass = await db.classes.find_one(
        {"id": class_id},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1, "academic_year": 1, "shift": 1},
    )
    if not klass:
        raise RemediationGateError("CLASS_NOT_FOUND")
    if klass.get("academic_year") is not None and str(klass.get("academic_year")) != str(academic_year):
        raise RemediationGateError("CLASS_ACADEMIC_YEAR_MISMATCH")

    schedules = await db.class_schedules.find(
        {"class_id": class_id, "academic_year": {"$in": [academic_year, str(academic_year)]}},
        {"_id": 0},
    ).to_list(10)
    if len(schedules) != 1:
        raise RemediationGateError(f"SCHEDULE_DOCUMENT_NOT_UNIQUE count={len(schedules)}")
    schedule = schedules[0]

    legacy = await db.teacher_assignments.find(
        {
            "staff_id": staff["id"],
            "class_id": class_id,
            "academic_year": {"$in": [academic_year, str(academic_year)]},
            "status": "ativo",
        },
        {"_id": 0},
    ).to_list(1000)

    dvd = await db.teacher_class_assignments.find(
        {"teacher_id": teacher_user_id, "class_id": class_id, "deleted": {"$ne": True}},
        {"_id": 0},
    ).to_list(1000)
    existing_components = {str(row.get("component_id") or "") for row in dvd if row.get("component_id")}

    regular_siblings = [
        row for row in dvd
        if (row.get("diary_settings") or {}).get("enabled") is True
        and (row.get("diary_settings") or {}).get("profile") == "regular"
        and not row.get("is_substitute")
    ]
    sibling_valid_from = sorted({str(row.get("valid_from") or "") for row in regular_siblings if row.get("valid_from")})
    if not regular_siblings:
        raise RemediationGateError("REGULAR_SIBLING_EVIDENCE_MISSING")
    if len(sibling_valid_from) != 1:
        raise RemediationGateError(f"REGULAR_SIBLING_VALID_FROM_AMBIGUOUS values={sibling_valid_from}")
    valid_from = sibling_valid_from[0]

    course_ids = sorted({str(row.get("course_id") or "") for row in legacy if row.get("course_id")})
    courses = await db.courses.find(
        {"id": {"$in": course_ids}}, {"_id": 0, "id": 1, "name": 1}
    ).to_list(5000) if course_ids else []
    course_names = {str(row.get("id")): row.get("name") for row in courses if row.get("id")}

    manifest: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    states: Counter[str] = Counter()

    for source in sorted(legacy, key=lambda row: str(row.get("id") or "")):
        component_id = str(source.get("course_id") or "")
        if not component_id:
            states["blocked"] += 1
            details.append({"legacy_assignment_id": source.get("id"), "state": "blocked", "blockers": ["component_id_missing"]})
            continue
        if component_id in existing_components:
            states["already_has_dvd"] += 1
            details.append({
                "legacy_assignment_id": source.get("id"),
                "component_id": component_id,
                "component_name": course_names.get(component_id),
                "state": "already_has_dvd",
            })
            continue
        if source.get("substituto_staff_id") or source.get("data_substituicao"):
            result = {"ready": False, "blockers": ["substitution_review"], "weekly_slots": [], "stale_slots": []}
        else:
            workload = _int(source.get("carga_horaria_semanal"))
            if workload is None:
                result = {"ready": False, "blockers": ["workload_invalid"], "weekly_slots": [], "stale_slots": []}
            else:
                result = build_in_range_weekly_slots(
                    schedule,
                    course_id=component_id,
                    expected_workload=workload,
                )

        if not result.get("ready"):
            states["blocked"] += 1
            details.append({
                "legacy_assignment_id": source.get("id"),
                "component_id": component_id,
                "component_name": course_names.get(component_id),
                "state": "blocked",
                "blockers": result.get("blockers") or [],
                "stale_slots_count": len(result.get("stale_slots") or []),
            })
            continue

        assignment_id = deterministic_assignment_id(
            source_legacy_assignment_id=str(source["id"]),
            teacher_id=teacher_user_id,
            class_id=class_id,
            component_id=component_id,
            valid_from=valid_from,
        )
        proposed = {
            "id": assignment_id,
            "teacher_id": teacher_user_id,
            "teacher_name": teacher.get("full_name") or teacher.get("name") or staff.get("nome"),
            "class_id": class_id,
            "class_name": klass.get("name"),
            "school_id": klass.get("school_id") or source.get("school_id"),
            "mantenedora_id": klass.get("mantenedora_id") or source.get("mantenedora_id"),
            "component_id": component_id,
            "component_name": course_names.get(component_id),
            "weekly_slots": result["weekly_slots"],
            "valid_from": valid_from,
            "valid_until": None,
            "is_substitute": False,
            "source": "import",
            "diary_settings": {
                "enabled": True,
                "schema_version": 1,
                "profile": "regular",
                "student_scope": "all",
            },
            "cutover_provenance": {
                "phase": PROVENANCE_PHASE,
                "state": "DRY_RUN_ONLY",
                "source_legacy_assignment_id": source.get("id"),
                "evidence": "declared_grid_plus_exact_workload",
                "slots_per_day": result.get("slots_per_day"),
                "ignored_out_of_range_slots": [
                    {
                        "day": row.get("day") or row.get("weekday"),
                        "slot_number": row.get("slot_number") or row.get("aula_numero"),
                        "course_id": row.get("course_id"),
                    }
                    for row in result.get("stale_slots") or []
                ],
            },
        }
        manifest.append(proposed)
        states["ready"] += 1
        details.append({
            "legacy_assignment_id": source.get("id"),
            "component_id": component_id,
            "component_name": course_names.get(component_id),
            "state": "ready",
            "proposed_assignment_id": assignment_id,
            "weekly_slots_count": len(result["weekly_slots"]),
            "stale_slots_count": len(result.get("stale_slots") or []),
        })

    missing_total = sum(1 for row in details if row.get("state") != "already_has_dvd")
    blocked_total = sum(1 for row in details if row.get("state") == "blocked")
    manifest.sort(key=lambda row: (str(row.get("component_name") or "").casefold(), row["id"]))
    return {
        "meta": {
            "mode": "DRY_RUN_P0_DVD_OUT_OF_RANGE_SCHEDULE_REMEDIATION",
            "mutates_database": False,
            "teacher_user_id": teacher_user_id,
            "class_id": class_id,
            "academic_year": academic_year,
            "valid_from": valid_from,
            "schedule_id": schedule.get("id"),
            "slots_per_day": schedule.get("slots_per_day"),
        },
        "summary": {
            "legacy_bindings": len(legacy),
            "existing_dvd_bindings": len(dvd),
            "missing_total": missing_total,
            "ready": len(manifest),
            "blocked": blocked_total,
            "states": dict(sorted(states.items())),
            "manifest_sha256": manifest_digest(manifest),
        },
        "manifest": manifest,
        "details": details,
    }


async def apply_manifest(db, report: Mapping[str, Any]) -> dict[str, Any]:
    if int(report["summary"].get("blocked") or 0) != 0:
        raise RemediationGateError("APPLY_BLOCKED: existem vínculos ausentes não remediáveis")
    manifest = [dict(row) for row in (report.get("manifest") or [])]
    if not manifest:
        return {"state": "nothing_to_apply", "inserted": 0}

    ids = [str(row["id"]) for row in manifest]
    existing = await db.teacher_class_assignments.find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1}
    ).to_list(len(ids) + 10)
    if existing:
        if len(existing) == len(ids):
            return {"state": "already_applied", "inserted": 0, "postcheck": len(existing)}
        raise RemediationGateError("PARTIAL_APPLY_DETECTED")

    logical_conflicts = []
    for row in manifest:
        conflict = await db.teacher_class_assignments.find_one(
            {
                "teacher_id": row["teacher_id"],
                "class_id": row["class_id"],
                "component_id": row["component_id"],
                "deleted": {"$ne": True},
            },
            {"_id": 0, "id": 1},
        )
        if conflict:
            logical_conflicts.append(conflict)
    if logical_conflicts:
        raise RemediationGateError(f"LOGICAL_TARGET_CONFLICT count={len(logical_conflicts)}")

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    digest = str(report["summary"].get("manifest_sha256") or "")
    docs = []
    for row in manifest:
        doc = dict(row)
        provenance = dict(doc.get("cutover_provenance") or {})
        provenance.update({
            "state": "ACTIVATED",
            "apply_run_id": run_id,
            "manifest_sha256": digest,
            "activated_at": now,
        })
        doc["cutover_provenance"] = provenance
        doc["deleted"] = False
        doc["created_at"] = now
        doc["created_by"] = ACTOR
        doc["updated_at"] = now
        doc["updated_by"] = ACTOR
        docs.append(doc)

    try:
        result = await db.teacher_class_assignments.insert_many(docs, ordered=True)
        if len(result.inserted_ids) != len(docs):
            raise RemediationGateError("INSERT_COUNT_MISMATCH")
        post = await db.teacher_class_assignments.find(
            {"id": {"$in": ids}, "cutover_provenance.apply_run_id": run_id},
            {"_id": 0, "id": 1},
        ).to_list(len(ids) + 10)
        if len(post) != len(ids):
            raise RemediationGateError("POSTCHECK_COUNT_MISMATCH")
        return {"state": "applied", "inserted": len(ids), "postcheck": len(post), "run_id": run_id}
    except Exception:
        await db.teacher_class_assignments.delete_many({
            "id": {"$in": ids},
            "cutover_provenance.phase": PROVENANCE_PHASE,
            "cutover_provenance.apply_run_id": run_id,
        })
        raise


async def rollback_manifest(db, report: Mapping[str, Any]) -> dict[str, Any]:
    ids = [str(row["id"]) for row in (report.get("manifest") or [])]
    if not ids:
        return {"state": "nothing_to_rollback", "removed": 0}
    result = await db.teacher_class_assignments.delete_many({
        "id": {"$in": ids},
        "cutover_provenance.phase": PROVENANCE_PHASE,
    })
    return {"state": "rolled_back", "removed": result.deleted_count}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--teacher-user-id", required=True)
    parser.add_argument("--class-id", required=True)
    parser.add_argument("--academic-year", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    if args.apply and args.rollback:
        raise SystemExit("Escolha apenas --apply ou --rollback")
    if args.apply and args.confirm != APPLY_CONFIRMATION:
        raise SystemExit(f"Apply exige --confirm {APPLY_CONFIRMATION}")
    if args.rollback and args.confirm != ROLLBACK_CONFIRMATION:
        raise SystemExit(f"Rollback exige --confirm {ROLLBACK_CONFIRMATION}")

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc_db")]
        report = await collect_manifest(
            db,
            teacher_user_id=args.teacher_user_id,
            class_id=args.class_id,
            academic_year=args.academic_year,
        )
        if args.apply:
            report["apply"] = await apply_manifest(db, report)
        elif args.rollback:
            report["rollback"] = await rollback_manifest(db, report)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
