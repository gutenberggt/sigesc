"""Etapa 38C — diagnóstico READ-ONLY dos bloqueios de horário do DVD.

Explica por que vínculos elegíveis não conseguem reconstruir `weekly_slots` a
partir de `class_schedules`. Não corrige, cria, atualiza ou remove dados.

Princípios:
- somente `class_schedule` do ano letivo exato é elegível para cutover automático;
- documento de outro ano ou sem ano é evidência para revisão, nunca fallback automático;
- múltiplos documentos do mesmo ano são ambíguos e bloqueiam;
- divergência de `course_id` pode ser sinalizada por nome, mas nunca reparada aqui;
- horários alternativos em `slot_times.start_time/end_time` são diagnosticados
  como gap de parser, sem reescrever o banco.

Uso:
    cd /app/backend
    python scripts/audit_dvd_schedule_blockers.py \
      --academic-year 2026 --json /tmp/dvd-schedule-blockers-2026.json
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

WEEKDAY_MAP = {
    "segunda": 1,
    "segunda-feira": 1,
    "seg": 1,
    "terca": 2,
    "terça": 2,
    "terca-feira": 2,
    "terça-feira": 2,
    "ter": 2,
    "quarta": 3,
    "quarta-feira": 3,
    "qua": 3,
    "quinta": 4,
    "quinta-feira": 4,
    "qui": 4,
    "sexta": 5,
    "sexta-feira": 5,
    "sex": 5,
    "sabado": 6,
    "sábado": 6,
    "sab": 6,
    "domingo": 7,
    "dom": 7,
}

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def normalize_text(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    return " ".join("".join(ch for ch in raw if not unicodedata.combining(ch)).split())


def normalize_day(value: Any) -> Optional[int]:
    if isinstance(value, int) and 1 <= value <= 7:
        return value
    raw = str(value or "").strip().casefold()
    return WEEKDAY_MAP.get(raw)


def parse_slot_number(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 1 <= parsed <= 12 else None


def valid_time(value: Any) -> bool:
    return bool(TIME_RE.fullmatch(str(value or "").strip()))


def choose_schedule_document(
    documents: list[Mapping[str, Any]], academic_year: int
) -> tuple[str, Optional[Mapping[str, Any]]]:
    """Seleciona somente documento inequivocamente pertencente ao ano alvo."""
    exact = [d for d in documents if str(d.get("academic_year") or "") == str(academic_year)]
    missing_year = [d for d in documents if str(d.get("academic_year") or "").strip() == ""]
    other_year = [
        d
        for d in documents
        if str(d.get("academic_year") or "").strip()
        and str(d.get("academic_year")) != str(academic_year)
    ]

    if len(exact) > 1:
        return "schedule_duplicate_current_year", None
    if len(exact) == 1:
        return "schedule_exact_year", exact[0]
    if len(missing_year) > 1:
        return "schedule_multiple_without_year", None
    if len(missing_year) == 1:
        return "schedule_year_missing", missing_year[0]
    if other_year:
        return "schedule_other_year_only", None
    return "schedule_document_missing", None


def _time_sources(
    slot: Mapping[str, Any], slot_times: Mapping[str, Any], aula_numero: Optional[int]
) -> tuple[Any, Any, str]:
    inline_start = slot.get("start_time")
    inline_end = slot.get("end_time")
    if inline_start or inline_end:
        return inline_start, inline_end, "inline"

    if aula_numero is None:
        return None, None, "none"
    time_def = slot_times.get(str(aula_numero)) or slot_times.get(aula_numero) or {}
    canonical_start = time_def.get("start")
    canonical_end = time_def.get("end")
    if canonical_start or canonical_end:
        return canonical_start, canonical_end, "slot_times_canonical"

    alt_start = time_def.get("start_time")
    alt_end = time_def.get("end_time")
    if alt_start or alt_end:
        return alt_start, alt_end, "slot_times_alternate_keys"
    return None, None, "none"


def diagnose_component_schedule(
    schedule: Optional[Mapping[str, Any]],
    *,
    course_id: Optional[str],
    course_name: Optional[str] = None,
) -> dict[str, Any]:
    """Diagnostica um componente sem inferir nem alterar dados."""
    if schedule is None:
        return {"code": "schedule_unusable", "issues": [], "slot_count": 0}

    slots = list(schedule.get("schedule_slots") or [])
    if not slots:
        return {"code": "schedule_slots_empty", "issues": [], "slot_count": 0}

    target_id = str(course_id or "")
    component_slots = [s for s in slots if str(s.get("course_id") or "") == target_id]
    if not component_slots:
        target_name = normalize_text(course_name)
        name_matches = [
            s
            for s in slots
            if target_name and normalize_text(s.get("course_name")) == target_name
        ]
        if name_matches:
            return {
                "code": "component_id_mismatch_name_match",
                "issues": ["course_id_differs_but_name_matches"],
                "slot_count": len(name_matches),
                "schedule_course_ids": sorted(
                    {str(s.get("course_id") or "") for s in name_matches if s.get("course_id")}
                ),
            }
        return {"code": "component_absent_in_schedule", "issues": [], "slot_count": 0}

    slot_times = schedule.get("slot_times") or {}
    issues: Counter[str] = Counter()
    parser_gap_only = True
    complete_slots = 0

    for slot in component_slots:
        weekday = normalize_day(slot.get("day") or slot.get("weekday"))
        aula_numero = parse_slot_number(slot.get("slot_number") or slot.get("aula_numero"))
        if weekday is None:
            issues["weekday_missing_or_invalid"] += 1
            parser_gap_only = False
        if aula_numero is None:
            issues["slot_number_missing_or_invalid"] += 1
            parser_gap_only = False

        start_time, end_time, source = _time_sources(slot, slot_times, aula_numero)
        if source == "slot_times_alternate_keys":
            issues["alternate_time_keys"] += 1
        if not start_time:
            issues["start_time_missing"] += 1
            parser_gap_only = False
        if not end_time:
            issues["end_time_missing"] += 1
            parser_gap_only = False

        if start_time and not valid_time(start_time):
            issues["start_time_invalid"] += 1
            parser_gap_only = False
        if end_time and not valid_time(end_time):
            issues["end_time_invalid"] += 1
            parser_gap_only = False
        if valid_time(start_time) and valid_time(end_time) and str(end_time) <= str(start_time):
            issues["end_not_after_start"] += 1
            parser_gap_only = False

        if (
            weekday is not None
            and aula_numero is not None
            and valid_time(start_time)
            and valid_time(end_time)
            and str(end_time) > str(start_time)
        ):
            complete_slots += 1

    if not issues:
        code = "schedule_ready"
    elif parser_gap_only and set(issues) == {"alternate_time_keys"} and complete_slots == len(component_slots):
        code = "parser_gap_alt_time_keys"
    elif "weekday_missing_or_invalid" in issues:
        code = "slot_weekday_invalid"
    elif "slot_number_missing_or_invalid" in issues:
        code = "slot_number_invalid"
    elif any(k in issues for k in ("start_time_missing", "end_time_missing")):
        code = "slot_time_missing"
    elif any(k in issues for k in ("start_time_invalid", "end_time_invalid", "end_not_after_start")):
        code = "slot_time_invalid"
    else:
        code = "schedule_incomplete_mixed"

    return {
        "code": code,
        "issues": dict(sorted(issues.items())),
        "slot_count": len(component_slots),
        "complete_slots": complete_slots,
    }


def recovery_bucket(document_state: str, component_code: str) -> str:
    if document_state == "schedule_exact_year" and component_code == "schedule_ready":
        return "ready_now"
    if document_state == "schedule_exact_year" and component_code == "parser_gap_alt_time_keys":
        return "code_only"
    if document_state in {"schedule_year_missing", "schedule_other_year_only"}:
        return "year_mapping_review"
    if document_state in {"schedule_duplicate_current_year", "schedule_multiple_without_year"}:
        return "schedule_ambiguity_review"
    if component_code == "component_id_mismatch_name_match":
        return "component_mapping_review"
    if document_state == "schedule_document_missing" or component_code == "schedule_slots_empty":
        return "schedule_creation_needed"
    return "schedule_data_fix_needed"


async def collect_schedule_blockers(
    db,
    *,
    academic_year: int,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    legacy = await db.teacher_assignments.find(
        {
            "academic_year": {"$in": [academic_year, str(academic_year)]},
            "status": "ativo",
        },
        {
            "_id": 0,
            "id": 1,
            "staff_id": 1,
            "school_id": 1,
            "class_id": 1,
            "course_id": 1,
            "academic_year": 1,
            "is_substituicao": 1,
        },
    ).to_list(30000)

    class_ids = sorted({a.get("class_id") for a in legacy if a.get("class_id")})
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
            "grade": 1,
            "atendimento_programa": 1,
        },
    ).to_list(20000) if class_ids else []
    classes_by_id = {c.get("id"): c for c in classes if c.get("id")}

    legacy = [
        a
        for a in legacy
        if (classes_by_id.get(a.get("class_id")) is not None)
        and is_class_in_scope(classes_by_id[a.get("class_id")])
        and (
            not tenant_id
            or classes_by_id[a.get("class_id")].get("mantenedora_id") == tenant_id
        )
    ]
    in_scope_class_ids = sorted({a.get("class_id") for a in legacy if a.get("class_id")})

    schools_ids = sorted(
        {
            classes_by_id[cid].get("school_id")
            for cid in in_scope_class_ids
            if classes_by_id.get(cid) and classes_by_id[cid].get("school_id")
        }
    )
    schools = await db.schools.find(
        {"id": {"$in": schools_ids}}, {"_id": 0, "id": 1, "name": 1}
    ).to_list(10000) if schools_ids else []
    schools_by_id = {s.get("id"): s for s in schools if s.get("id")}

    course_ids = sorted({a.get("course_id") for a in legacy if a.get("course_id")})
    courses = await db.courses.find(
        {"id": {"$in": course_ids}}, {"_id": 0, "id": 1, "name": 1}
    ).to_list(10000) if course_ids else []
    courses_by_id = {c.get("id"): c for c in courses if c.get("id")}

    schedules = await db.class_schedules.find(
        {"class_id": {"$in": in_scope_class_ids}},
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
    ).to_list(20000) if in_scope_class_ids else []
    schedules_by_class: dict[str, list[dict]] = defaultdict(list)
    for schedule in schedules:
        if schedule.get("class_id"):
            schedules_by_class[str(schedule["class_id"])].append(schedule)

    document_counts: Counter[str] = Counter()
    cause_binding_counts: Counter[str] = Counter()
    cause_class_sets: dict[str, set[str]] = defaultdict(set)
    recovery_counts: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    school_blocked_counts: Counter[str] = Counter()

    for assignment in legacy:
        cid = str(assignment.get("class_id") or "")
        course_id = str(assignment.get("course_id") or "")
        klass = classes_by_id.get(cid) or {}
        school = schools_by_id.get(klass.get("school_id")) or {}
        course = courses_by_id.get(course_id) or {}

        document_state, selected = choose_schedule_document(
            schedules_by_class.get(cid, []), academic_year
        )
        document_counts[document_state] += 1

        # Documento sem ano pode ser analisado para diagnóstico, mas nunca vira
        # `ready_now`; outros anos e duplicidades permanecem fail-closed.
        diagnostic_doc = selected if document_state in {"schedule_exact_year", "schedule_year_missing"} else None
        component = diagnose_component_schedule(
            diagnostic_doc,
            course_id=course_id,
            course_name=course.get("name"),
        )
        code = component["code"]
        if diagnostic_doc is None and document_state != "schedule_exact_year":
            code = document_state

        cause_binding_counts[code] += 1
        cause_class_sets[code].add(cid)
        bucket = recovery_bucket(document_state, component["code"])
        recovery_counts[bucket] += 1
        if bucket != "ready_now":
            school_blocked_counts[str(school.get("name") or klass.get("school_id") or "-")] += 1

        rows.append(
            {
                "legacy_assignment_id": assignment.get("id"),
                "class_id": cid,
                "class_name": klass.get("name"),
                "school_id": klass.get("school_id"),
                "school_name": school.get("name"),
                "course_id": course_id or None,
                "course_name": course.get("name"),
                "document_state": document_state,
                "schedule_documents_count": len(schedules_by_class.get(cid, [])),
                "schedule_document_years": sorted(
                    {str(d.get("academic_year") or "SEM_ANO") for d in schedules_by_class.get(cid, [])}
                ),
                "component_diagnosis": component,
                "recovery_bucket": bucket,
            }
        )

    blocked_total = sum(v for k, v in recovery_counts.items() if k != "ready_now")
    unique_blocked_classes = {
        row["class_id"] for row in rows if row["recovery_bucket"] != "ready_now"
    }
    top_schools = [
        {"school_name": name, "blocked_bindings": count}
        for name, count in school_blocked_counts.most_common(15)
    ]

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "READ_ONLY_SCHEDULE_DIAGNOSTIC",
            "academic_year": academic_year,
            "tenant_id": tenant_id,
            "mutates_database": False,
        },
        "summary": {
            "bindings_analyzed": len(rows),
            "schedule_document_state": dict(sorted(document_counts.items())),
            "root_causes_bindings": dict(sorted(cause_binding_counts.items())),
            "root_causes_classes": {
                key: len(value) for key, value in sorted(cause_class_sets.items())
            },
            "recovery": dict(sorted(recovery_counts.items())),
            "blocked_bindings": blocked_total,
            "blocked_unique_classes": len(unique_blocked_classes),
            "top_schools_by_blocked_bindings": top_schools,
        },
        "details": sorted(
            rows,
            key=lambda row: (
                row["recovery_bucket"],
                str(row.get("school_name") or "").casefold(),
                str(row.get("class_name") or "").casefold(),
                str(row.get("course_name") or "").casefold(),
            ),
        ),
    }


def print_compact(report: Mapping[str, Any]) -> None:
    summary = report["summary"]
    print("=== DVD 38C — HORÁRIOS READ-ONLY ===")
    print("DOCUMENTOS:", summary["schedule_document_state"])
    print("CAUSAS_VINCULOS:", summary["root_causes_bindings"])
    print("RECUPERABILIDADE:", summary["recovery"])
    print(
        "IMPACTO:",
        {
            "bloqueados": summary["blocked_bindings"],
            "turmas_bloqueadas": summary["blocked_unique_classes"],
        },
    )
    print("TOP_ESCOLAS:", summary["top_schools_by_blocked_bindings"][:5])


async def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico read-only de horários do cutover DVD")
    parser.add_argument("--academic-year", type=int, default=datetime.now().year)
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]
        report = await collect_schedule_blockers(
            db,
            academic_year=args.academic_year,
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
