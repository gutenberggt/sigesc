"""Etapa 38E — manifesto READ-ONLY da primeira onda de cutover DVD.

Cruza o plano pedagógico/identidade da 38B com a recuperabilidade de horários da
38D e produz um manifesto dry-run de `teacher_class_assignments` que poderiam
ser criados em uma futura etapa escrita.

Nenhuma escrita é feita no MongoDB.

Elegibilidade automática desta primeira onda (fail-closed):
- identidade professor↔usuário resolvida;
- não é substituição;
- apenas um professor não substituto no mesmo turma+componente;
- existe evidência real de avaliação, portanto perfil `regular` é confirmado;
- horário já íntegro OU recuperável deterministicamente pela 38D;
- `weekly_slots` completos podem ser reconstruídos sem inventar dia/aula/horário;
- não existe DVD atual para a mesma combinação professor+turma+componente.

Casos `integrator`, `shared`, substituição, identidade não resolvida e grades sem
evidência suficiente ficam fora da primeira onda e permanecem em revisão.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
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

from scripts.audit_dvd_cutover_plan import collect_cutover_plan, normalize_day  # noqa: E402
from scripts.audit_dvd_schedule_recovery import (  # noqa: E402
    collect_recovery,
    schedule_time_consensus,
    slot_number,
)

load_dotenv(BACKEND_DIR / ".env")

RECOVERABLE_STATES = {
    "schedule_ready",
    "time_recoverable_same_schedule",
    "time_recoverable_unique_school_shift",
}


def first_wave_blocker(plan_row: Mapping[str, Any], recovery_row: Mapping[str, Any]) -> Optional[str]:
    """Retorna o primeiro bloqueio objetivo; `None` significa candidato."""
    if not plan_row.get("teacher_user_id"):
        return "teacher_identity_unresolved"
    if plan_row.get("is_substitution"):
        return "substitution_review"
    if int(plan_row.get("non_substitute_teachers_same_class_course") or 0) != 1:
        return "shared_or_multi_teacher_review"
    if not plan_row.get("has_grade_evidence"):
        return "regular_or_integrator_review"

    recovery_state = str(recovery_row.get("recovery_state") or "")
    if recovery_state not in RECOVERABLE_STATES:
        return f"schedule:{recovery_state or 'unknown'}"
    return None


def _pattern_for_recovery(
    schedule: Mapping[str, Any],
    recovery_row: Mapping[str, Any],
) -> dict[int, tuple[str, str]]:
    state = str(recovery_row.get("recovery_state") or "")
    if state == "schedule_ready":
        return schedule_time_consensus(schedule)

    evidence = recovery_row.get("evidence") or {}
    pattern = evidence.get("pattern") or {}
    resolved: dict[int, tuple[str, str]] = {}
    for raw_n, pair in pattern.items():
        n = slot_number(raw_n)
        if not n or not isinstance(pair, Mapping):
            continue
        start = str(pair.get("start") or "").strip()
        end = str(pair.get("end") or "").strip()
        if start and end and end > start:
            resolved[n] = (start, end)
    return resolved


def build_manifest_weekly_slots(
    schedule: Optional[Mapping[str, Any]],
    *,
    course_id: str,
    recovery_row: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Reconstrói slots apenas quando dia/aula e horário estão integralmente provados."""
    if not schedule:
        return []
    pattern = _pattern_for_recovery(schedule, recovery_row)
    if not pattern:
        return []

    slots: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for raw in schedule.get("schedule_slots") or []:
        if str(raw.get("course_id") or "") != str(course_id or ""):
            continue
        weekday = normalize_day(raw.get("day") or raw.get("weekday"))
        aula = slot_number(raw.get("slot_number") or raw.get("aula_numero"))
        if weekday is None or aula is None or aula not in pattern:
            return []
        start, end = pattern[aula]
        key = (weekday, aula)
        if key in seen:
            continue
        seen.add(key)
        slots.append(
            {
                "weekday": weekday,
                "aula_numero": aula,
                "start_time": start,
                "end_time": end,
            }
        )

    if not slots:
        return []
    slots.sort(key=lambda item: (item["weekday"], item["aula_numero"]))
    return slots


def deterministic_proposed_id(
    *,
    source_legacy_assignment_id: str,
    teacher_id: str,
    class_id: str,
    component_id: str,
    valid_from: str,
) -> str:
    seed = "|".join(
        [
            "sigesc-dvd-first-wave-v1",
            source_legacy_assignment_id,
            teacher_id,
            class_id,
            component_id,
            valid_from,
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def manifest_digest(documents: list[Mapping[str, Any]]) -> str:
    canonical = json.dumps(documents, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def collect_first_wave_manifest(
    db,
    *,
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

    plan_by_id = {
        str(row.get("legacy_assignment_id")): row
        for row in plan.get("binding_details") or []
        if row.get("legacy_assignment_id")
    }
    recovery_by_id = {
        str(row.get("legacy_assignment_id")): row
        for row in recovery.get("details") or []
        if row.get("legacy_assignment_id")
    }

    candidate_ids = sorted(set(plan_by_id) & set(recovery_by_id))
    class_ids = sorted(
        {
            str(plan_by_id[aid].get("class_id") or "")
            for aid in candidate_ids
            if plan_by_id[aid].get("class_id")
        }
    )

    classes = await db.classes.find(
        {"id": {"$in": class_ids}},
        {
            "_id": 0,
            "id": 1,
            "name": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "shift": 1,
        },
    ).to_list(20000) if class_ids else []
    classes_by_id = {str(row.get("id")): row for row in classes if row.get("id")}

    schedules = await db.class_schedules.find(
        {
            "class_id": {"$in": class_ids},
            "academic_year": {"$in": [academic_year, str(academic_year)]},
        },
        {
            "_id": 0,
            "id": 1,
            "class_id": 1,
            "school_id": 1,
            "academic_year": 1,
            "schedule_slots": 1,
            "slot_times": 1,
            "shift": 1,
        },
    ).to_list(20000) if class_ids else []
    schedules_by_class: dict[str, list[dict]] = defaultdict(list)
    for row in schedules:
        if str(row.get("academic_year") or "") != str(academic_year):
            continue
        if row.get("class_id"):
            schedules_by_class[str(row["class_id"])].append(row)

    existing = await db.teacher_class_assignments.find(
        {"class_id": {"$in": class_ids}, "deleted": {"$ne": True}},
        {
            "_id": 0,
            "id": 1,
            "teacher_id": 1,
            "class_id": 1,
            "component_id": 1,
            "valid_from": 1,
            "valid_until": 1,
            "deleted": 1,
        },
    ).to_list(30000) if class_ids else []
    existing_keys = {
        (
            str(row.get("teacher_id") or ""),
            str(row.get("class_id") or ""),
            str(row.get("component_id") or ""),
        )
        for row in existing
    }

    # Duplicidades do próprio legado são bloqueadas, mesmo que os demais critérios passem.
    legacy_target_counts: Counter[tuple[str, str, str]] = Counter()
    for aid in candidate_ids:
        row = plan_by_id[aid]
        key = (
            str(row.get("teacher_user_id") or ""),
            str(row.get("class_id") or ""),
            str(row.get("course_id") or ""),
        )
        if all(key):
            legacy_target_counts[key] += 1

    blockers: Counter[str] = Counter()
    schedule_source_counts: Counter[str] = Counter()
    manifest: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for aid in candidate_ids:
        p = plan_by_id[aid]
        r = recovery_by_id[aid]
        blocker = first_wave_blocker(p, r)
        teacher_id = str(p.get("teacher_user_id") or "")
        class_id = str(p.get("class_id") or "")
        component_id = str(p.get("course_id") or "")
        target_key = (teacher_id, class_id, component_id)

        if blocker is None and legacy_target_counts.get(target_key, 0) > 1:
            blocker = "duplicate_legacy_binding_review"
        if blocker is None and target_key in existing_keys:
            blocker = "existing_dvd_assignment_review"

        schedule_docs = schedules_by_class.get(class_id, [])
        schedule = schedule_docs[0] if len(schedule_docs) == 1 else None
        if blocker is None and len(schedule_docs) != 1:
            blocker = "schedule_document_not_unique"

        weekly_slots: list[dict[str, Any]] = []
        if blocker is None:
            weekly_slots = build_manifest_weekly_slots(
                schedule,
                course_id=component_id,
                recovery_row=r,
            )
            if not weekly_slots:
                blocker = "weekly_slots_reconstruction_failed"

        if blocker is not None:
            blockers[blocker] += 1
            details.append(
                {
                    "legacy_assignment_id": aid,
                    "class_id": class_id,
                    "class_name": p.get("class_name"),
                    "course_id": component_id,
                    "course_name": p.get("course_name"),
                    "teacher_user_id": teacher_id or None,
                    "teacher_name": p.get("teacher_name"),
                    "recovery_state": r.get("recovery_state"),
                    "first_wave_state": "blocked",
                    "blocker": blocker,
                }
            )
            continue

        klass = classes_by_id.get(class_id) or {}
        source_state = str(r.get("recovery_state"))
        schedule_source = (
            "existing_exact_schedule"
            if source_state == "schedule_ready"
            else "deterministic_recovery"
        )
        schedule_source_counts[schedule_source] += 1

        proposed = {
            "id": deterministic_proposed_id(
                source_legacy_assignment_id=aid,
                teacher_id=teacher_id,
                class_id=class_id,
                component_id=component_id,
                valid_from=reference_date,
            ),
            "teacher_id": teacher_id,
            "teacher_name": p.get("teacher_name"),
            "class_id": class_id,
            "class_name": p.get("class_name"),
            "school_id": klass.get("school_id") or p.get("school_id"),
            "mantenedora_id": klass.get("mantenedora_id"),
            "component_id": component_id,
            "component_name": p.get("course_name"),
            "weekly_slots": weekly_slots,
            "valid_from": reference_date,
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
                "phase": "38E",
                "state": "DRY_RUN_ONLY",
                "source_legacy_assignment_id": aid,
                "schedule_source": schedule_source,
                "recovery_state": source_state,
            },
        }
        manifest.append(proposed)
        details.append(
            {
                "legacy_assignment_id": aid,
                "class_id": class_id,
                "class_name": p.get("class_name"),
                "course_id": component_id,
                "course_name": p.get("course_name"),
                "teacher_user_id": teacher_id,
                "teacher_name": p.get("teacher_name"),
                "recovery_state": source_state,
                "first_wave_state": "ready",
                "schedule_source": schedule_source,
                "proposed_assignment_id": proposed["id"],
                "weekly_slots_count": len(weekly_slots),
            }
        )

    manifest.sort(
        key=lambda row: (
            str(row.get("school_id") or ""),
            str(row.get("class_name") or "").casefold(),
            str(row.get("component_name") or "").casefold(),
            str(row.get("teacher_name") or "").casefold(),
        )
    )

    return {
        "meta": {
            "mode": "READ_ONLY_FIRST_WAVE_MANIFEST",
            "mutates_database": False,
            "academic_year": academic_year,
            "reference_date": reference_date,
            "tenant_id": tenant_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "historical_ownership_migration": False,
        },
        "summary": {
            "bindings_crossed": len(candidate_ids),
            "first_wave_ready": len(manifest),
            "first_wave_blocked": len(candidate_ids) - len(manifest),
            "schedule_source": dict(sorted(schedule_source_counts.items())),
            "blockers": dict(sorted(blockers.items())),
            "manifest_sha256": manifest_digest(manifest),
        },
        "manifest": manifest,
        "details": details,
    }


def print_compact(report: Mapping[str, Any]) -> None:
    s = report["summary"]
    print("=== DVD 38E — PRIMEIRA ONDA READ-ONLY ===")
    print("CRUZADOS:", s["bindings_crossed"])
    print("PRIMEIRA_ONDA_PRONTOS:", s["first_wave_ready"])
    print("FONTES_HORARIO:", s["schedule_source"])
    print("BLOQUEADOS:", s["first_wave_blocked"])
    print("MOTIVOS_BLOQUEIO:", s["blockers"])
    print("MANIFEST_SHA256:", s["manifest_sha256"])
    print("HISTORICO: preservado; nenhuma autoria retroativa e nenhuma escrita no MongoDB.")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--academic-year", type=int, default=datetime.now().year)
    parser.add_argument("--reference-date", required=True)
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        report = await collect_first_wave_manifest(
            client[os.environ["DB_NAME"]],
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            tenant_id=args.tenant_id,
        )
        print_compact(report)
        if args.json_path:
            path = Path(args.json_path)
            path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"JSON_LOCAL={path}")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
