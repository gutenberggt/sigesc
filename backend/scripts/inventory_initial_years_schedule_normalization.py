"""Inventário READ-ONLY para normalização global de horários do 1º ao 5º ano.

Política informada para 2026:
- Matutino: 07:00-07:55, 07:55-08:50, 09:10-10:05, 10:05-11:00.
- Vespertino: 13:00-13:55, 13:55-14:50, 15:10-16:05, 16:05-17:00.

Escopo:
- todas as turmas de 1º a 5º ano;
- inclui multisseriadas;
- inclui turmas com ou sem class_schedule existente;
- não altera MongoDB.

Casos estruturalmente ambíguos ficam explicitamente bloqueados no inventário:
- turno sem política (integral/noturno/desconhecido);
- multisseriada que cruza o limite dos Anos Iniciais (ex.: 5º + 6º);
- mais de um class_schedule para a mesma turma/ano;
- horário atual com slots > 4, pois a política fornecida define somente 4 aulas.
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
import re
import sys
from typing import Any, Iterable, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

ACADEMIC_YEAR = 2026
TARGET_GRADES = {1, 2, 3, 4, 5}
INITIAL_YEARS_LEVEL = "fundamental_anos_iniciais"

SCHEDULE_POLICY = {
    "morning": {
        1: {"start": "07:00", "end": "07:55"},
        2: {"start": "07:55", "end": "08:50"},
        3: {"start": "09:10", "end": "10:05"},
        4: {"start": "10:05", "end": "11:00"},
    },
    "afternoon": {
        1: {"start": "13:00", "end": "13:55"},
        2: {"start": "13:55", "end": "14:50"},
        3: {"start": "15:10", "end": "16:05"},
        4: {"start": "16:05", "end": "17:00"},
    },
}

MONGO_MUTATOR_TOKENS = tuple(
    "." + name + "("
    for name in (
        "insert_one", "insert_many", "update_one", "update_many",
        "replace_one", "delete_one", "delete_many", "bulk_write",
        "find_one_and_update", "find_one_and_delete", "find_one_and_replace",
    )
)


class InventoryGateError(RuntimeError):
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


def assert_script_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    hits = [token for token in MONGO_MUTATOR_TOKENS if token in source]
    if hits:
        raise InventoryGateError(f"READ_ONLY_GUARD_FAILED forbidden={hits}")


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("°", "º")
    text = re.sub(r"\s+", " ", text)
    return text


def grade_numbers_from_value(value: Any) -> set[int]:
    """Extrai anos do EF de representações legadas/comuns do SIGESC."""
    text = _norm(value)
    if not text:
        return set()

    aliases = {
        "1ano": 1, "2ano": 2, "3ano": 3, "4ano": 4, "5ano": 5,
        "6ano": 6, "7ano": 7, "8ano": 8, "9ano": 9,
    }
    compact = re.sub(r"[^a-z0-9]", "", text)
    if compact in aliases:
        return {aliases[compact]}

    found: set[int] = set()
    # 1º ANO, 1 ANO, 1º/2º ANO, etc.
    for match in re.finditer(r"(?<!\d)([1-9])\s*º?\s*(?:ano)?\b", text):
        n = int(match.group(1))
        # Evita capturar números isolados sem nenhum indício de série/ano.
        fragment = match.group(0)
        if "ano" in fragment or "º" in fragment:
            found.add(n)

    # Formatos com barra em que apenas o último número carrega "ANO": 1º/2º ANO.
    if "ano" in text:
        for match in re.finditer(r"(?<!\d)([1-9])\s*º?", text):
            found.add(int(match.group(1)))
    return found


def class_grade_evidence(cls: Mapping[str, Any]) -> dict[str, Any]:
    grade_level = grade_numbers_from_value(cls.get("grade_level"))
    series_values = cls.get("series") or []
    if not isinstance(series_values, list):
        series_values = [series_values]
    series: set[int] = set()
    for value in series_values:
        series |= grade_numbers_from_value(value)
    name = grade_numbers_from_value(cls.get("name"))

    level = _norm(
        cls.get("education_level")
        or cls.get("nivel_ensino")
        or cls.get("level")
    )
    explicit_initial_level = level == INITIAL_YEARS_LEVEL
    is_multi = bool(cls.get("is_multi_grade"))

    combined = grade_level | series | name
    target_grades = combined & TARGET_GRADES
    outside_grades = {n for n in combined if n not in TARGET_GRADES}

    # Nível explícito de Anos Iniciais conta como alvo mesmo em cadastros antigos
    # sem grade_level, mas o inventário deixa isso visível como evidência incompleta.
    is_target = bool(target_grades) or explicit_initial_level

    cross_boundary_multi = bool(
        is_multi and target_grades and outside_grades
    )
    multi_without_series = bool(is_multi and not series)

    return {
        "education_level": level or None,
        "explicit_initial_years_level": explicit_initial_level,
        "grade_level_numbers": sorted(grade_level),
        "series_numbers": sorted(series),
        "name_numbers": sorted(name),
        "combined_numbers": sorted(combined),
        "target_grades": sorted(target_grades),
        "outside_grades": sorted(outside_grades),
        "is_multi_grade": is_multi,
        "multi_without_series": multi_without_series,
        "cross_boundary_multi": cross_boundary_multi,
        "is_target": is_target,
    }


def _slot_number(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def schedule_shape(schedule: Mapping[str, Any] | None) -> dict[str, Any]:
    if not schedule:
        return {
            "exists": False,
            "schedule_id": None,
            "slots_per_day": None,
            "slot_time_numbers": [],
            "schedule_slot_numbers": [],
            "extra_slot_numbers": [],
            "schedule_slots_count": 0,
        }

    slot_times = schedule.get("slot_times") or {}
    time_numbers: set[int] = set()
    if isinstance(slot_times, Mapping):
        for key in slot_times:
            n = _slot_number(key)
            if n:
                time_numbers.add(n)

    schedule_numbers: set[int] = set()
    schedule_slots = schedule.get("schedule_slots") or []
    if isinstance(schedule_slots, list):
        for row in schedule_slots:
            if isinstance(row, Mapping):
                n = _slot_number(row.get("slot_number"))
                if n:
                    schedule_numbers.add(n)

    slots_per_day = _slot_number(schedule.get("slots_per_day"))
    all_numbers = time_numbers | schedule_numbers
    if slots_per_day:
        all_numbers |= set(range(1, slots_per_day + 1))
    extras = sorted(n for n in all_numbers if n > 4)

    return {
        "exists": True,
        "schedule_id": schedule.get("id"),
        "schedule_shift": schedule.get("shift"),
        "slots_per_day": slots_per_day,
        "slot_time_numbers": sorted(time_numbers),
        "schedule_slot_numbers": sorted(schedule_numbers),
        "extra_slot_numbers": extras,
        "schedule_slots_count": len(schedule_slots) if isinstance(schedule_slots, list) else 0,
        "created_at": schedule.get("created_at"),
        "updated_at": schedule.get("updated_at"),
    }


def classify_target(
    cls: Mapping[str, Any],
    grade: Mapping[str, Any],
    schedules: list[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    shift = _norm(cls.get("shift"))

    if grade.get("cross_boundary_multi"):
        reasons.append("MULTI_GRADE_CROSSES_1_TO_5_BOUNDARY")
    if shift not in SCHEDULE_POLICY:
        reasons.append(f"SHIFT_WITHOUT_POLICY:{shift or 'missing'}")
    if len(schedules) > 1:
        reasons.append(f"MULTIPLE_CLASS_SCHEDULES:{len(schedules)}")
    if len(schedules) == 1:
        shape = schedule_shape(schedules[0])
        if shape["extra_slot_numbers"]:
            reasons.append(
                "EXTRA_SLOTS_ABOVE_4:" + ",".join(map(str, shape["extra_slot_numbers"]))
            )
        schedule_shift = _norm(schedules[0].get("shift"))
        if schedule_shift and shift and schedule_shift != shift:
            reasons.append(
                f"CLASS_SCHEDULE_SHIFT_MISMATCH:{shift}!={schedule_shift}"
            )

    if reasons:
        return "BLOCKED_REQUIRES_REVIEW", reasons
    return "READY_NORMALIZE", []


def proposed_slot_times(shift: str) -> dict[str, dict[str, str]] | None:
    policy = SCHEDULE_POLICY.get(_norm(shift))
    if not policy:
        return None
    return {
        str(slot): {"start": pair["start"], "end": pair["end"]}
        for slot, pair in sorted(policy.items())
    }


async def collect_inventory(db) -> dict[str, Any]:
    assert_script_read_only()

    classes = await db.classes.find(
        {"academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
        {"_id": 0},
    ).to_list(10000)

    target_classes: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for cls in classes:
        evidence = class_grade_evidence(cls)
        if evidence["is_target"]:
            target_classes.append((cls, evidence))

    target_ids = [str(cls.get("id")) for cls, _ in target_classes if cls.get("id")]
    schedules = []
    if target_ids:
        schedules = await db.class_schedules.find(
            {
                "class_id": {"$in": target_ids},
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            },
            {"_id": 0},
        ).to_list(20000)

    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for schedule in schedules:
        by_class[str(schedule.get("class_id") or "")].append(schedule)

    school_ids = sorted(
        {str(cls.get("school_id")) for cls, _ in target_classes if cls.get("school_id")}
    )
    schools = []
    if school_ids:
        schools = await db.schools.find(
            {"id": {"$in": school_ids}},
            {"_id": 0, "id": 1, "name": 1, "zona_localizacao": 1, "status": 1},
        ).to_list(1000)
    school_by_id = {str(row.get("id")): row for row in schools if row.get("id")}

    rows: list[dict[str, Any]] = []
    status_counter: Counter[str] = Counter()
    shift_counter: Counter[str] = Counter()
    schedule_counter: Counter[str] = Counter()
    multigrade_counter: Counter[str] = Counter()

    for cls, grade in target_classes:
        class_id = str(cls.get("id") or "")
        class_schedules = by_class.get(class_id, [])
        status, blockers = classify_target(cls, grade, class_schedules)
        shift = _norm(cls.get("shift")) or "missing"
        shape = (
            schedule_shape(class_schedules[0])
            if len(class_schedules) == 1
            else {
                "exists": bool(class_schedules),
                "schedule_id": None,
                "schedule_count": len(class_schedules),
            }
        )
        school = school_by_id.get(str(cls.get("school_id") or "")) or {}

        row = {
            "class_id": class_id,
            "class_name": cls.get("name"),
            "school_id": cls.get("school_id"),
            "school_name": school.get("name"),
            "academic_year": cls.get("academic_year"),
            "shift": shift,
            "atendimento_programa": cls.get("atendimento_programa") or cls.get("programa"),
            "grade_evidence": grade,
            "schedule_count": len(class_schedules),
            "schedule_shape": shape,
            "status": status,
            "blockers": blockers,
            "proposed_slots_per_day": 4 if shift in SCHEDULE_POLICY else None,
            "proposed_slot_times": proposed_slot_times(shift),
            "normalization_mode": (
                "OVERWRITE_EXISTING_TIME_GRID"
                if len(class_schedules) == 1
                else "CREATE_TIME_GRID"
                if len(class_schedules) == 0
                else None
            ),
        }
        rows.append(row)
        status_counter[status] += 1
        shift_counter[shift] += 1
        schedule_counter[
            "missing" if len(class_schedules) == 0 else "single" if len(class_schedules) == 1 else "multiple"
        ] += 1
        multigrade_counter["multi" if grade["is_multi_grade"] else "regular"] += 1

    rows.sort(
        key=lambda row: (
            str(row.get("school_name") or "").casefold(),
            str(row.get("class_name") or "").casefold(),
            str(row.get("class_id") or ""),
        )
    )

    inventory_core = {
        "academic_year": ACADEMIC_YEAR,
        "policy": {
            shift: {
                str(slot): pair
                for slot, pair in sorted(policy.items())
            }
            for shift, policy in sorted(SCHEDULE_POLICY.items())
        },
        "target_count": len(rows),
        "rows": rows,
    }

    return {
        "meta": {
            "mode": "INITIAL_YEARS_SCHEDULE_NORMALIZATION_INVENTORY_READ_ONLY",
            "mutates_database": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "inventory_sha256": _sha256(inventory_core),
        "summary": {
            "all_2026_classes": len(classes),
            "target_classes": len(rows),
            "status": dict(sorted(status_counter.items())),
            "shifts": dict(sorted(shift_counter.items())),
            "schedules": dict(sorted(schedule_counter.items())),
            "multigrade": dict(sorted(multigrade_counter.items())),
        },
        "inventory": inventory_core,
    }


def print_compact(report: Mapping[str, Any]) -> None:
    summary = report["summary"]
    print("=== HORARIOS 1º AO 5º ANO — INVENTARIO GLOBAL READ-ONLY ===")
    print("ACADEMIC_YEAR:", ACADEMIC_YEAR)
    print("INVENTORY_SHA256:", report["inventory_sha256"])
    print("POLICY_MORNING: 1=07:00-07:55 2=07:55-08:50 3=09:10-10:05 4=10:05-11:00")
    print("POLICY_AFTERNOON: 1=13:00-13:55 2=13:55-14:50 3=15:10-16:05 4=16:05-17:00")
    print("ALL_2026_CLASSES:", summary["all_2026_classes"])
    print("TARGET_CLASSES:", summary["target_classes"])
    print("STATUS_COUNTS:", json.dumps(summary["status"], ensure_ascii=False, sort_keys=True))
    print("SHIFT_COUNTS:", json.dumps(summary["shifts"], ensure_ascii=False, sort_keys=True))
    print("SCHEDULE_COUNTS:", json.dumps(summary["schedules"], ensure_ascii=False, sort_keys=True))
    print("MULTIGRADE_COUNTS:", json.dumps(summary["multigrade"], ensure_ascii=False, sort_keys=True))

    for row in report["inventory"]["rows"]:
        print("---")
        print("SCHOOL:", row.get("school_name"))
        print("CLASS:", row.get("class_name"))
        print("CLASS_ID:", row.get("class_id"))
        print("SHIFT:", row.get("shift"))
        print("IS_MULTI_GRADE:", "SIM" if row["grade_evidence"]["is_multi_grade"] else "NAO")
        print("SERIES:", row["grade_evidence"].get("combined_numbers"))
        print("SCHEDULE_COUNT:", row.get("schedule_count"))
        shape = row.get("schedule_shape") or {}
        print("CURRENT_SLOTS_PER_DAY:", shape.get("slots_per_day"))
        print("EXTRA_SLOT_NUMBERS:", shape.get("extra_slot_numbers") or [])
        print("STATUS:", row.get("status"))
        print("BLOCKERS:", row.get("blockers") or [])
        if row.get("proposed_slot_times"):
            print(
                "PROPOSED_SLOT_TIMES:",
                json.dumps(row["proposed_slot_times"], ensure_ascii=False, sort_keys=True),
            )

    print("MONGO_WRITES: 0")
    print("AUTOMATIC_ACTION: NAO")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc")]
        report = await collect_inventory(db)
        print_compact(report)
        if args.json_path:
            path = Path(args.json_path)
            path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print("JSON_LOCAL:", path)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
