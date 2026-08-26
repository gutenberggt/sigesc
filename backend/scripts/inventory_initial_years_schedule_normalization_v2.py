"""Inventário V2 READ-ONLY para normalização de horários do 1º ao 5º ano.

Preserva o inventário V1 como evidência e aplica uma camada explícita de escopo:
- exclui turmas AEE da normalização regular;
- exclui EJA / turmas por ETAPA;
- mantém turmas regulares de 1º ao 5º ano, inclusive multisseriadas;
- mantém casos full_time, slots > 4 e divergências de turno como bloqueios visíveis;
- não altera MongoDB.
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
from typing import Any, Mapping

from motor.motor_asyncio import AsyncIOMotorClient

from scripts import inventory_initial_years_schedule_normalization as base


MODE = "INITIAL_YEARS_SCHEDULE_NORMALIZATION_INVENTORY_V2_READ_ONLY"
EXCLUSION_AEE = "EXCLUDED_AEE"
EXCLUSION_EJA = "EXCLUDED_EJA_OR_ETAPA"

MONGO_MUTATOR_TOKENS = tuple(
    "." + name + "("
    for name in (
        "insert_one", "insert_many", "update_one", "update_many",
        "replace_one", "delete_one", "delete_many", "bulk_write",
        "find_one_and_update", "find_one_and_delete", "find_one_and_replace",
    )
)


class ScopeV2GateError(RuntimeError):
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


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("°", "º")
    text = re.sub(r"\s+", " ", text)
    return text


def assert_script_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    hits = [token for token in MONGO_MUTATOR_TOKENS if token in source]
    if hits:
        raise ScopeV2GateError(f"READ_ONLY_GUARD_FAILED forbidden={hits}")


def exclusion_reason(row: Mapping[str, Any]) -> str | None:
    """Retorna exclusão de modalidade; None significa turma regular no escopo."""
    name = _norm(row.get("class_name"))
    program = _norm(row.get("atendimento_programa"))
    grade = row.get("grade_evidence") or {}
    level = _norm(grade.get("education_level"))

    if program == "aee" or re.search(r"(^|\W)aee($|\W)", name):
        return EXCLUSION_AEE

    if (
        level in {"eja", "eja_final"}
        or re.search(r"(^|\W)eja($|\W)", name)
        or re.search(r"(^|\W)etapa($|\W)", name)
    ):
        return EXCLUSION_EJA

    return None


def review_group(row: Mapping[str, Any]) -> str | None:
    blockers = [str(x) for x in (row.get("blockers") or [])]
    if not blockers:
        return None
    if any(x == "SHIFT_WITHOUT_POLICY:full_time" for x in blockers):
        return "FULL_TIME_POLICY_REQUIRED"
    if any(x.startswith("EXTRA_SLOTS_ABOVE_4:") for x in blockers):
        return "EXTRA_SLOTS_REVIEW"
    if any(x.startswith("CLASS_SCHEDULE_SHIFT_MISMATCH:") for x in blockers):
        return "SHIFT_MISMATCH_REVIEW"
    if any(x.startswith("MULTIPLE_CLASS_SCHEDULES:") for x in blockers):
        return "MULTIPLE_SCHEDULES_REVIEW"
    if any(x.startswith("MULTI_GRADE_CROSSES_1_TO_5_BOUNDARY") for x in blockers):
        return "CROSS_BOUNDARY_REVIEW"
    if any(x.startswith("SHIFT_WITHOUT_POLICY:") for x in blockers):
        return "SHIFT_POLICY_REQUIRED"
    return "OTHER_REVIEW"


def _recount(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status: Counter[str] = Counter()
    shifts: Counter[str] = Counter()
    schedules: Counter[str] = Counter()
    multigrade: Counter[str] = Counter()
    review_groups: Counter[str] = Counter()

    for row in rows:
        status[str(row.get("status") or "missing")] += 1
        shifts[str(row.get("shift") or "missing")] += 1
        count = int(row.get("schedule_count") or 0)
        schedules["missing" if count == 0 else "single" if count == 1 else "multiple"] += 1
        grade = row.get("grade_evidence") or {}
        multigrade["multi" if grade.get("is_multi_grade") else "regular"] += 1
        group = row.get("review_group")
        if group:
            review_groups[str(group)] += 1

    return {
        "status": dict(sorted(status.items())),
        "shifts": dict(sorted(shifts.items())),
        "schedules": dict(sorted(schedules.items())),
        "multigrade": dict(sorted(multigrade.items())),
        "review_groups": dict(sorted(review_groups.items())),
    }


def build_scope_v2(source_report: Mapping[str, Any]) -> dict[str, Any]:
    assert_script_read_only()

    meta = source_report.get("meta") or {}
    if meta.get("mutates_database") is not False:
        raise ScopeV2GateError("SOURCE_INVENTORY_NOT_READ_ONLY")

    source_rows = list((source_report.get("inventory") or {}).get("rows") or [])
    if not source_rows:
        raise ScopeV2GateError("SOURCE_INVENTORY_EMPTY")

    regular_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    excluded_counter: Counter[str] = Counter()

    for raw in source_rows:
        row = dict(raw)
        reason = exclusion_reason(row)
        if reason:
            excluded_counter[reason] += 1
            excluded_rows.append(
                {
                    "class_id": row.get("class_id"),
                    "class_name": row.get("class_name"),
                    "school_id": row.get("school_id"),
                    "school_name": row.get("school_name"),
                    "shift": row.get("shift"),
                    "education_level": (row.get("grade_evidence") or {}).get("education_level"),
                    "atendimento_programa": row.get("atendimento_programa"),
                    "series": (row.get("grade_evidence") or {}).get("combined_numbers"),
                    "source_status": row.get("status"),
                    "exclusion_reason": reason,
                }
            )
            continue

        row["review_group"] = review_group(row)
        regular_rows.append(row)

    regular_rows.sort(
        key=lambda row: (
            str(row.get("school_name") or "").casefold(),
            str(row.get("class_name") or "").casefold(),
            str(row.get("class_id") or ""),
        )
    )
    excluded_rows.sort(
        key=lambda row: (
            str(row.get("school_name") or "").casefold(),
            str(row.get("class_name") or "").casefold(),
            str(row.get("class_id") or ""),
        )
    )

    counts = _recount(regular_rows)
    core = {
        "academic_year": base.ACADEMIC_YEAR,
        "source_inventory_sha256": source_report.get("inventory_sha256"),
        "policy": (source_report.get("inventory") or {}).get("policy"),
        "regular_target_count": len(regular_rows),
        "excluded_non_regular_count": len(excluded_rows),
        "excluded_counts": dict(sorted(excluded_counter.items())),
        "summary": counts,
        "regular_rows": regular_rows,
        "excluded_non_regular_rows": excluded_rows,
    }

    return {
        "meta": {
            "mode": MODE,
            "mutates_database": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "scope_v2_sha256": _sha256(core),
        "scope": core,
    }


async def collect_inventory_v2(db) -> dict[str, Any]:
    source = await base.collect_inventory(db)
    return build_scope_v2(source)


def print_compact(report: Mapping[str, Any]) -> None:
    scope = report["scope"]
    summary = scope["summary"]
    print("=== HORARIOS 1º AO 5º ANO — INVENTARIO V2 DE ESCOPO READ-ONLY ===")
    print("ACADEMIC_YEAR:", scope["academic_year"])
    print("SOURCE_INVENTORY_SHA256:", scope["source_inventory_sha256"])
    print("SCOPE_V2_SHA256:", report["scope_v2_sha256"])
    print("REGULAR_TARGET_CLASSES:", scope["regular_target_count"])
    print("EXCLUDED_NON_REGULAR:", scope["excluded_non_regular_count"])
    print("EXCLUDED_COUNTS:", json.dumps(scope["excluded_counts"], ensure_ascii=False, sort_keys=True))
    print("STATUS_COUNTS:", json.dumps(summary["status"], ensure_ascii=False, sort_keys=True))
    print("SHIFT_COUNTS:", json.dumps(summary["shifts"], ensure_ascii=False, sort_keys=True))
    print("SCHEDULE_COUNTS:", json.dumps(summary["schedules"], ensure_ascii=False, sort_keys=True))
    print("MULTIGRADE_COUNTS:", json.dumps(summary["multigrade"], ensure_ascii=False, sort_keys=True))
    print("REVIEW_GROUPS:", json.dumps(summary["review_groups"], ensure_ascii=False, sort_keys=True))

    print("=== EXCLUIDAS DO ESCOPO REGULAR ===")
    for row in scope["excluded_non_regular_rows"]:
        print("---")
        print("SCHOOL:", row.get("school_name"))
        print("CLASS:", row.get("class_name"))
        print("CLASS_ID:", row.get("class_id"))
        print("SHIFT:", row.get("shift"))
        print("EDUCATION_LEVEL:", row.get("education_level"))
        print("ATENDIMENTO_PROGRAMA:", row.get("atendimento_programa"))
        print("SERIES:", row.get("series"))
        print("EXCLUSION_REASON:", row.get("exclusion_reason"))

    print("=== BLOQUEIOS REAIS DO ESCOPO REGULAR ===")
    for row in scope["regular_rows"]:
        if row.get("status") != "BLOCKED_REQUIRES_REVIEW":
            continue
        print("---")
        print("SCHOOL:", row.get("school_name"))
        print("CLASS:", row.get("class_name"))
        print("CLASS_ID:", row.get("class_id"))
        print("SHIFT:", row.get("shift"))
        print("SERIES:", (row.get("grade_evidence") or {}).get("combined_numbers"))
        print("SCHEDULE_COUNT:", row.get("schedule_count"))
        print("EXTRA_SLOTS:", (row.get("schedule_shape") or {}).get("extra_slot_numbers") or [])
        print("REVIEW_GROUP:", row.get("review_group"))
        print("BLOCKERS:", row.get("blockers") or [])

    print("MONGO_WRITES: 0")
    print("AUTOMATIC_ACTION: NAO")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc")]
        report = await collect_inventory_v2(db)
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
