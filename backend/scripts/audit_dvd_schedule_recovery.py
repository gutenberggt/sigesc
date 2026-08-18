"""Etapa 38D — recuperabilidade READ-ONLY dos horários bloqueados do DVD.

Procura evidências determinísticas já existentes no SIGESC para explicar quais
bloqueios de horário poderiam ser corrigidos futuramente sem inventar dados.
Nenhuma escrita é feita no MongoDB.

Prioridade de evidência para horários ausentes/inválidos:
1. consenso no próprio class_schedule para o mesmo número de aula;
2. padrão único e completo entre class_schedules do mesmo ano/escola/turno;
3. caso contrário, permanece revisão/bloqueio.

Divergência de course_id por nome é apenas sinalizada para revisão humana.
Grade ausente ou vazia nunca é reconstruída automaticamente nesta etapa.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from services.diary_assignment_contract import is_class_in_scope  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def normalize_text(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    return " ".join("".join(ch for ch in raw if not unicodedata.combining(ch)).split())


def valid_pair(start: Any, end: Any) -> bool:
    s = str(start or "").strip()
    e = str(end or "").strip()
    return bool(TIME_RE.fullmatch(s) and TIME_RE.fullmatch(e) and e > s)


def slot_number(value: Any) -> Optional[int]:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 12 else None


def _pair_from_definition(value: Any) -> Optional[tuple[str, str]]:
    if not isinstance(value, Mapping):
        return None
    start = value.get("start") or value.get("start_time")
    end = value.get("end") or value.get("end_time")
    if valid_pair(start, end):
        return str(start).strip(), str(end).strip()
    return None


def schedule_time_consensus(schedule: Mapping[str, Any]) -> dict[int, tuple[str, str]]:
    """Retorna apenas horários sem conflito dentro do próprio documento."""
    candidates: dict[int, set[tuple[str, str]]] = defaultdict(set)
    for raw_n, definition in (schedule.get("slot_times") or {}).items():
        n = slot_number(raw_n)
        pair = _pair_from_definition(definition)
        if n and pair:
            candidates[n].add(pair)

    for slot in schedule.get("schedule_slots") or []:
        n = slot_number(slot.get("slot_number") or slot.get("aula_numero"))
        if not n:
            continue
        start = slot.get("start_time")
        end = slot.get("end_time")
        if valid_pair(start, end):
            candidates[n].add((str(start).strip(), str(end).strip()))

    return {n: next(iter(pairs)) for n, pairs in candidates.items() if len(pairs) == 1}


def required_slot_numbers(schedule: Mapping[str, Any], course_id: str) -> set[int]:
    numbers = set()
    for slot in schedule.get("schedule_slots") or []:
        if str(slot.get("course_id") or "") != str(course_id or ""):
            continue
        n = slot_number(slot.get("slot_number") or slot.get("aula_numero"))
        if n:
            numbers.add(n)
    return numbers


def pattern_signature(pattern: Mapping[int, tuple[str, str]], required: set[int]) -> Optional[tuple]:
    if not required or not required.issubset(set(pattern)):
        return None
    return tuple((n, pattern[n][0], pattern[n][1]) for n in sorted(required))


def classify_time_recovery(
    *,
    target_schedule: Mapping[str, Any],
    course_id: str,
    donor_schedules: list[Mapping[str, Any]],
) -> tuple[str, Optional[dict[str, Any]]]:
    required = required_slot_numbers(target_schedule, course_id)
    if not required:
        return "time_recovery_not_applicable", None

    own = schedule_time_consensus(target_schedule)
    own_sig = pattern_signature(own, required)
    if own_sig is not None:
        return "time_recoverable_same_schedule", {
            "required_slots": sorted(required),
            "pattern": {str(n): {"start": own[n][0], "end": own[n][1]} for n in sorted(required)},
        }

    signatures: dict[tuple, dict[str, Any]] = {}
    for donor in donor_schedules:
        pattern = schedule_time_consensus(donor)
        sig = pattern_signature(pattern, required)
        if sig is None:
            continue
        signatures.setdefault(
            sig,
            {
                "required_slots": sorted(required),
                "pattern": {str(n): {"start": pattern[n][0], "end": pattern[n][1]} for n in sorted(required)},
                "donor_classes": [],
            },
        )["donor_classes"].append(str(donor.get("class_id") or ""))

    if len(signatures) == 1:
        evidence = next(iter(signatures.values()))
        evidence["donor_classes"] = sorted(set(evidence["donor_classes"]))
        return "time_recoverable_unique_school_shift", evidence
    if len(signatures) > 1:
        return "time_pattern_ambiguous_school_shift", {"pattern_count": len(signatures)}
    return "time_pattern_no_safe_evidence", None


def _component_state(schedule: Optional[Mapping[str, Any]], course_id: str, course_name: str) -> str:
    if not schedule:
        return "schedule_document_missing"
    slots = schedule.get("schedule_slots") or []
    if not slots:
        return "schedule_slots_empty"
    exact = [s for s in slots if str(s.get("course_id") or "") == str(course_id or "")]
    if not exact:
        target = normalize_text(course_name)
        name_ids = {
            str(s.get("course_id") or "")
            for s in slots
            if target and normalize_text(s.get("course_name")) == target and s.get("course_id")
        }
        if len(name_ids) == 1:
            return "component_mapping_unique_name_review"
        if len(name_ids) > 1:
            return "component_mapping_ambiguous_name"
        return "component_absent_no_name_match"

    required = required_slot_numbers(schedule, course_id)
    if not required:
        return "slot_number_missing_or_invalid"
    own = schedule_time_consensus(schedule)
    if required.issubset(set(own)):
        return "schedule_ready"
    return "slot_time_needs_recovery"


async def collect_recovery(db, *, academic_year: int, tenant_id: Optional[str] = None) -> dict[str, Any]:
    assignments = await db.teacher_assignments.find(
        {"academic_year": {"$in": [academic_year, str(academic_year)]}, "status": "ativo"},
        {"_id": 0, "id": 1, "class_id": 1, "course_id": 1, "staff_id": 1},
    ).to_list(30000)

    class_ids = sorted({a.get("class_id") for a in assignments if a.get("class_id")})
    classes = await db.classes.find(
        {"id": {"$in": class_ids}},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1, "shift": 1,
         "academic_year": 1, "education_level": 1, "nivel_ensino": 1, "grade_level": 1,
         "grade": 1, "atendimento_programa": 1},
    ).to_list(20000) if class_ids else []
    classes_by_id = {c.get("id"): c for c in classes if c.get("id")}

    assignments = [
        a for a in assignments
        if a.get("class_id") in classes_by_id
        and is_class_in_scope(classes_by_id[a.get("class_id")])
        and (not tenant_id or classes_by_id[a.get("class_id")].get("mantenedora_id") == tenant_id)
    ]
    class_ids = sorted({a.get("class_id") for a in assignments if a.get("class_id")})
    school_ids = sorted({classes_by_id[cid].get("school_id") for cid in class_ids if classes_by_id[cid].get("school_id")})

    # Donors: todos os horários do mesmo ano nas escolas envolvidas, não apenas classes DVD.
    schedules = await db.class_schedules.find(
        {"school_id": {"$in": school_ids}, "academic_year": {"$in": [academic_year, str(academic_year)]}},
        {"_id": 0, "id": 1, "class_id": 1, "school_id": 1, "academic_year": 1, "shift": 1,
         "schedule_slots": 1, "slot_times": 1},
    ).to_list(30000) if school_ids else []
    exact_by_class: dict[str, list[dict]] = defaultdict(list)
    for s in schedules:
        if str(s.get("academic_year") or "") == str(academic_year) and s.get("class_id"):
            exact_by_class[str(s["class_id"])].append(s)

    course_ids = sorted({a.get("course_id") for a in assignments if a.get("course_id")})
    courses = await db.courses.find(
        {"id": {"$in": course_ids}}, {"_id": 0, "id": 1, "name": 1}
    ).to_list(10000) if course_ids else []
    course_names = {str(c.get("id")): str(c.get("name") or "") for c in courses if c.get("id")}

    donors_by_school_shift: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for s in schedules:
        cid = str(s.get("class_id") or "")
        klass = classes_by_id.get(cid) or {}
        shift = str(s.get("shift") or klass.get("shift") or "").strip()
        key = (str(s.get("school_id") or klass.get("school_id") or ""), shift)
        donors_by_school_shift[key].append(s)

    counts: Counter[str] = Counter()
    school_counts: dict[str, Counter[str]] = defaultdict(Counter)
    rows = []

    for a in assignments:
        cid = str(a.get("class_id") or "")
        course_id = str(a.get("course_id") or "")
        klass = classes_by_id.get(cid) or {}
        docs = exact_by_class.get(cid, [])
        schedule = docs[0] if len(docs) == 1 else None
        if len(docs) > 1:
            state = "schedule_duplicate_current_year"
            evidence = None
        else:
            state = _component_state(schedule, course_id, course_names.get(course_id, ""))
            evidence = None
            if state == "slot_time_needs_recovery" and schedule:
                key = (str(klass.get("school_id") or schedule.get("school_id") or ""),
                       str(schedule.get("shift") or klass.get("shift") or "").strip())
                donors = [d for d in donors_by_school_shift.get(key, []) if str(d.get("class_id") or "") != cid]
                state, evidence = classify_time_recovery(
                    target_schedule=schedule, course_id=course_id, donor_schedules=donors
                )

        counts[state] += 1
        school_name = str(klass.get("school_id") or "-")
        school_counts[school_name][state] += 1
        rows.append({
            "legacy_assignment_id": a.get("id"),
            "class_id": cid,
            "class_name": klass.get("name"),
            "school_id": klass.get("school_id"),
            "course_id": course_id,
            "course_name": course_names.get(course_id),
            "recovery_state": state,
            "evidence": evidence,
        })

    deterministic = counts["time_recoverable_same_schedule"] + counts["time_recoverable_unique_school_shift"]
    component_review = counts["component_mapping_unique_name_review"]
    hard_rebuild = counts["schedule_document_missing"] + counts["schedule_slots_empty"]
    unresolved = len(rows) - counts["schedule_ready"] - deterministic - component_review

    top = []
    for school_id, sc in school_counts.items():
        recoverable = sc["time_recoverable_same_schedule"] + sc["time_recoverable_unique_school_shift"]
        if recoverable:
            top.append({"school_id": school_id, "recoverable_time_bindings": recoverable})
    top.sort(key=lambda x: (-x["recoverable_time_bindings"], x["school_id"]))

    return {
        "meta": {
            "mode": "READ_ONLY_RECOVERY_ANALYSIS",
            "mutates_database": False,
            "academic_year": academic_year,
            "tenant_id": tenant_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "summary": {
            "states": dict(sorted(counts.items())),
            "deterministic_time_candidates": deterministic,
            "component_mapping_review_candidates": component_review,
            "schedule_rebuild_needed": hard_rebuild,
            "still_unresolved_or_ambiguous": unresolved,
        },
        "top_recoverable_schools": top[:10],
        "details": rows,
    }


def print_compact(report: Mapping[str, Any]) -> None:
    s = report["summary"]
    print("=== DVD 38D — RECUPERABILIDADE READ-ONLY ===")
    print("ESTADOS:", s["states"])
    print("DETERMINISTICOS_HORARIO:", s["deterministic_time_candidates"])
    print("MAPEAMENTO_COMPONENTE_REVISAO:", s["component_mapping_review_candidates"])
    print("RECONSTRUCAO_GRADE:", s["schedule_rebuild_needed"])
    print("AINDA_AMBIGUOS_OU_BLOQUEADOS:", s["still_unresolved_or_ambiguous"])
    print("TOP_RECUPERAVEIS:", report["top_recoverable_schools"][:5])


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--academic-year", type=int, default=datetime.now().year)
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        report = await collect_recovery(
            client[os.environ["DB_NAME"]], academic_year=args.academic_year, tenant_id=args.tenant_id
        )
        print_compact(report)
        if args.json_path:
            path = Path(args.json_path)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print(f"JSON_LOCAL={path}")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
