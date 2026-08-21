"""P0 pós-cutover — preflight READ-ONLY para vínculos DVD ausentes.

Objetivo: explicar, sem qualquer escrita no MongoDB, por que uma alocação ativa
em `teacher_assignments` não possui correspondente em
`teacher_class_assignments` e se existe evidência suficiente para uma futura
remediação controlada.

Este script NÃO corrige dados. Ele somente lê, cruza e classifica.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
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

from scripts.audit_dvd_cutover_plan import collect_cutover_plan  # noqa: E402
from scripts.audit_dvd_schedule_recovery import collect_recovery  # noqa: E402
from scripts.audit_dvd_first_wave_manifest import (  # noqa: E402
    RECOVERABLE_STATES,
    build_manifest_weekly_slots,
    first_wave_blocker,
)

load_dotenv(BACKEND_DIR / ".env")

DEFAULT_ACADEMIC_YEAR = 2026
DEFAULT_REFERENCE_DATE = "2026-08-21"


def _iso_day(value: Any) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip()
    return raw[:10] if raw else None


def _is_current(doc: Mapping[str, Any], reference_date: str) -> bool:
    if doc.get("deleted") is True:
        return False
    valid_from = _iso_day(doc.get("valid_from"))
    valid_until = _iso_day(doc.get("valid_until"))
    if not valid_from or valid_from > reference_date:
        return False
    return valid_until is None or valid_until >= reference_date


def _level(row: Mapping[str, Any]) -> str:
    return str(
        row.get("education_level")
        or row.get("nivel_ensino")
        or ""
    ).strip().casefold()


def _target_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("teacher_id") or row.get("teacher_user_id") or ""),
        str(row.get("class_id") or ""),
        str(row.get("component_id") or row.get("course_id") or ""),
    )


def _regular_sibling_evidence(
    *,
    teacher_user_id: str,
    education_level: str,
    reference_date: str,
    dvd_rows: list[Mapping[str, Any]],
    classes_by_id: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    ids: list[str] = []
    for dvd in dvd_rows:
        if str(dvd.get("teacher_id") or "") != teacher_user_id:
            continue
        if not _is_current(dvd, reference_date):
            continue
        settings = dvd.get("diary_settings") or {}
        if settings.get("enabled") is not True or settings.get("profile") != "regular":
            continue
        klass = classes_by_id.get(str(dvd.get("class_id") or "")) or {}
        if _level(klass) != education_level:
            continue
        if dvd.get("id"):
            ids.append(str(dvd["id"]))
    return sorted(set(ids))


def _schedule_diagnostics(
    *,
    schedule_docs: list[Mapping[str, Any]],
    recovery_row: Mapping[str, Any],
    course_id: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    blockers: list[str] = []
    if len(schedule_docs) != 1:
        blockers.append("schedule_document_not_unique")
        return blockers, []

    recovery_state = str(recovery_row.get("recovery_state") or "")
    if recovery_state not in RECOVERABLE_STATES:
        blockers.append(f"schedule:{recovery_state or 'unknown'}")
        return blockers, []

    weekly_slots = build_manifest_weekly_slots(
        schedule_docs[0],
        course_id=course_id,
        recovery_row=recovery_row,
    )
    if not weekly_slots:
        blockers.append("weekly_slots_reconstruction_failed")
    return blockers, weekly_slots


async def collect_missing_bindings_preflight(
    db,
    *,
    teacher_user_id: str,
    academic_year: int,
    reference_date: str,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    plan = await collect_cutover_plan(
        db,
        academic_year=academic_year,
        reference_date=reference_date,
        tenant_id=tenant_id,
    )
    recovery = await collect_recovery(
        db,
        academic_year=academic_year,
        tenant_id=tenant_id,
    )

    plan_rows = [
        row for row in (plan.get("binding_details") or [])
        if str(row.get("teacher_user_id") or "") == teacher_user_id
    ]
    recovery_by_legacy = {
        str(row.get("legacy_assignment_id")): row
        for row in (recovery.get("details") or [])
        if row.get("legacy_assignment_id")
    }

    class_ids = sorted({
        str(row.get("class_id") or "")
        for row in plan_rows
        if row.get("class_id")
    })

    classes = await db.classes.find(
        {"id": {"$in": class_ids}},
        {
            "_id": 0,
            "id": 1,
            "name": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "academic_year": 1,
            "education_level": 1,
            "nivel_ensino": 1,
            "grade_level": 1,
        },
    ).to_list(20000) if class_ids else []
    classes_by_id = {
        str(row.get("id")): row for row in classes if row.get("id")
    }

    school_ids = sorted({
        str(row.get("school_id") or "")
        for row in classes
        if row.get("school_id")
    })
    schools = await db.schools.find(
        {"id": {"$in": school_ids}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(5000) if school_ids else []
    schools_by_id = {
        str(row.get("id")): row for row in schools if row.get("id")
    }

    schedules = await db.class_schedules.find(
        {
            "class_id": {"$in": class_ids},
            "academic_year": {"$in": [academic_year, str(academic_year)]},
        },
        {
            "_id": 0,
            "id": 1,
            "class_id": 1,
            "academic_year": 1,
            "schedule_slots": 1,
            "slot_times": 1,
            "shift": 1,
        },
    ).to_list(20000) if class_ids else []
    schedules_by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in schedules:
        if str(row.get("academic_year") or "") == str(academic_year) and row.get("class_id"):
            schedules_by_class[str(row["class_id"])].append(row)

    dvd_rows = await db.teacher_class_assignments.find(
        {"teacher_id": teacher_user_id, "deleted": {"$ne": True}},
        {
            "_id": 0,
            "id": 1,
            "teacher_id": 1,
            "class_id": 1,
            "school_id": 1,
            "component_id": 1,
            "valid_from": 1,
            "valid_until": 1,
            "deleted": 1,
            "diary_settings": 1,
        },
    ).to_list(30000)
    existing_keys = {
        _target_key(row) for row in dvd_rows if all(_target_key(row))
    }

    legacy_key_counts: Counter[tuple[str, str, str]] = Counter()
    for row in plan_rows:
        key = _target_key(row)
        if all(key):
            legacy_key_counts[key] += 1

    states: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    details: list[dict[str, Any]] = []

    for p in plan_rows:
        legacy_id = str(p.get("legacy_assignment_id") or "")
        key = _target_key(p)
        class_id = str(p.get("class_id") or "")
        course_id = str(p.get("course_id") or "")
        klass = classes_by_id.get(class_id) or {}
        school_id = str(klass.get("school_id") or p.get("school_id") or "")
        school_name = (schools_by_id.get(school_id) or {}).get("name")

        if key in existing_keys:
            states["already_has_dvd"] += 1
            details.append({
                "state": "already_has_dvd",
                "legacy_assignment_id": legacy_id,
                "school_name": school_name,
                "class_name": p.get("class_name"),
                "course_name": p.get("course_name"),
            })
            continue

        r = recovery_by_legacy.get(legacy_id) or {}
        first_wave_reason = first_wave_blocker(p, r)
        diagnostic_blockers: list[str] = []

        if legacy_key_counts.get(key, 0) != 1:
            diagnostic_blockers.append("duplicate_legacy_binding_review")

        schedule_blockers, weekly_slots = _schedule_diagnostics(
            schedule_docs=schedules_by_class.get(class_id, []),
            recovery_row=r,
            course_id=course_id,
        )
        diagnostic_blockers.extend(schedule_blockers)

        level = _level(klass)
        sibling_regular_ids = _regular_sibling_evidence(
            teacher_user_id=teacher_user_id,
            education_level=level,
            reference_date=reference_date,
            dvd_rows=dvd_rows,
            classes_by_id=classes_by_id,
        ) if level else []

        non_profile_first_wave_blocker = (
            first_wave_reason
            if first_wave_reason not in {None, "regular_or_integrator_review"}
            else None
        )
        if non_profile_first_wave_blocker:
            diagnostic_blockers.append(non_profile_first_wave_blocker)

        diagnostic_blockers = sorted(set(diagnostic_blockers))
        state = "missing_blocked"
        remediation_hint = None

        if first_wave_reason is None and not diagnostic_blockers:
            state = "missing_first_wave_ready_now"
            remediation_hint = "candidato automático pelos mesmos gates da 38E"
        elif (
            first_wave_reason == "regular_or_integrator_review"
            and sibling_regular_ids
            and not diagnostic_blockers
            and weekly_slots
        ):
            state = "missing_regular_sibling_evidence"
            remediation_hint = (
                "único bloqueio original era evidência de perfil; há DVD regular "
                "vigente do mesmo professor e nível e horário reconstruível"
            )

        states[state] += 1
        for blocker in diagnostic_blockers:
            blocker_counts[blocker] += 1
        if first_wave_reason:
            blocker_counts[f"first_wave:{first_wave_reason}"] += 1

        details.append({
            "state": state,
            "legacy_assignment_id": legacy_id,
            "school_id": school_id or None,
            "school_name": school_name,
            "class_id": class_id,
            "class_name": p.get("class_name"),
            "course_id": course_id,
            "course_name": p.get("course_name"),
            "first_wave_blocker": first_wave_reason,
            "diagnostic_blockers": diagnostic_blockers,
            "recovery_state": r.get("recovery_state"),
            "schedule_documents": len(schedules_by_class.get(class_id, [])),
            "weekly_slots_reconstructable": bool(weekly_slots),
            "weekly_slots_count": len(weekly_slots),
            "regular_sibling_evidence_ids": sibling_regular_ids,
            "remediation_hint": remediation_hint,
        })

    details.sort(key=lambda row: (
        str(row.get("state") or ""),
        str(row.get("school_name") or "").casefold(),
        str(row.get("class_name") or "").casefold(),
        str(row.get("course_name") or "").casefold(),
    ))

    return {
        "meta": {
            "mode": "READ_ONLY_P0_MISSING_BINDINGS_PREFLIGHT",
            "mutates_database": False,
            "teacher_user_id": teacher_user_id,
            "academic_year": academic_year,
            "reference_date": reference_date,
            "tenant_id": tenant_id,
        },
        "summary": {
            "legacy_bindings_for_teacher": len(plan_rows),
            "states": dict(sorted(states.items())),
            "blockers": dict(sorted(blocker_counts.items())),
            "missing_total": sum(
                count for state, count in states.items()
                if state != "already_has_dvd"
            ),
        },
        "details": details,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--teacher-user-id", required=True)
    parser.add_argument("--academic-year", type=int, default=DEFAULT_ACADEMIC_YEAR)
    parser.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE)
    parser.add_argument("--tenant-id", default=None)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc")]
        report = await collect_missing_bindings_preflight(
            db,
            teacher_user_id=args.teacher_user_id,
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            tenant_id=args.tenant_id,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
