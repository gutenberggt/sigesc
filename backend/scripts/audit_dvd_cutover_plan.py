"""Etapa 38B — plano READ-ONLY de cutover do Diário por Vínculo Docente.

Não altera MongoDB. Classifica os vínculos legados em categorias de decisão e
monta um dry-run do que poderia virar `teacher_class_assignments` a partir da
data de corte, sem atribuir autoria retroativa.

Critérios conservadores:
- identidade professor↔usuário não resolvida => bloqueado;
- substituição => revisão específica;
- >1 professor não substituto no mesmo turma+componente => candidato `shared`,
  nunca autoativado;
- professor único + evidência de nota real no ano => `regular_ready`;
- professor único sem evidência de nota => `regular_or_integrator_review`;
- vínculo só fica tecnicamente pronto se a grade da turma fornecer slots
  completos (dia, aula, início e fim).

Uso:
    cd /app/backend
    python scripts/audit_dvd_cutover_plan.py --academic-year 2026 \
      --reference-date 2026-08-18 --json /tmp/dvd-cutover-plan-2026.json

Por padrão imprime apenas um resumo compacto. `--json` salva os detalhes em
arquivo local; nenhuma escrita é feita no banco.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
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

GRADE_FIELDS = ("b1", "b2", "b3", "b4", "rec_s1", "rec_s2", "recovery")


def iso_day(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value).strip()
    return raw[:10] if raw else None


def normalize_day(value: Any) -> Optional[int]:
    if isinstance(value, int) and 1 <= value <= 7:
        return value
    raw = str(value or "").strip().casefold()
    return WEEKDAY_MAP.get(raw)


def resolve_teacher_user_id(
    staff: Optional[Mapping[str, Any]],
    users_by_email: Mapping[str, Mapping[str, Any]],
) -> Optional[str]:
    if not staff:
        return None
    if staff.get("user_id"):
        return str(staff["user_id"])
    email = str(staff.get("email") or "").strip().casefold()
    user = users_by_email.get(email) if email else None
    return str(user.get("id")) if user and user.get("id") else None


def grade_has_real_evidence(doc: Mapping[str, Any]) -> bool:
    """Documento vazio não é evidência de que o componente seja avaliativo."""
    for field in GRADE_FIELDS:
        value = doc.get(field)
        if value is not None and str(value).strip() != "":
            return True
    return False


def classify_plan_binding(
    *,
    teacher_user_id: Optional[str],
    is_substitution: bool,
    non_substitute_teacher_count: int,
    has_grade_evidence: bool,
    schedule_state: str,
) -> str:
    """Classificação fail-closed para o dry-run 38B."""
    if not teacher_user_id:
        return "teacher_identity_unresolved"
    if is_substitution:
        return "substitution_review"
    if non_substitute_teacher_count > 1:
        return "shared_review"
    if schedule_state != "schedule_ready":
        return schedule_state
    if has_grade_evidence:
        return "regular_ready"
    return "regular_or_integrator_review"


def extract_weekly_slots(schedule: Optional[Mapping[str, Any]], course_id: Optional[str]) -> tuple[str, list[dict]]:
    """Extrai slots completos do componente sem inferir horários faltantes."""
    if not schedule:
        return "schedule_missing", []
    slots = schedule.get("schedule_slots") or []
    slot_times = schedule.get("slot_times") or {}
    selected = []
    had_component_slot = False

    for slot in slots:
        if str(slot.get("course_id") or "") != str(course_id or ""):
            continue
        had_component_slot = True
        aula_numero = slot.get("slot_number") or slot.get("aula_numero")
        weekday = normalize_day(slot.get("day") or slot.get("weekday"))
        times = slot_times.get(str(aula_numero)) or slot_times.get(aula_numero) or {}
        start_time = slot.get("start_time") or times.get("start")
        end_time = slot.get("end_time") or times.get("end")
        try:
            aula_numero = int(aula_numero) if aula_numero is not None else None
        except (TypeError, ValueError):
            aula_numero = None
        if not weekday or not aula_numero or not start_time or not end_time:
            return "schedule_incomplete", []
        selected.append(
            {
                "weekday": weekday,
                "aula_numero": aula_numero,
                "start_time": str(start_time),
                "end_time": str(end_time),
            }
        )

    if not had_component_slot or not selected:
        return "schedule_component_missing", []
    selected.sort(key=lambda item: (item["weekday"], item["aula_numero"]))
    return "schedule_ready", selected


def _safe_name(value: Any) -> str:
    return str(value or "").strip()


async def collect_cutover_plan(
    db,
    *,
    academic_year: int,
    reference_date: str,
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
            "data_inicio_substituicao": 1,
            "data_fim_substituicao": 1,
        },
    ).to_list(30000)

    class_ids = sorted({item.get("class_id") for item in legacy if item.get("class_id")})
    classes = await db.classes.find(
        {
            "$or": [
                {"id": {"$in": class_ids}},
                {"academic_year": {"$in": [academic_year, str(academic_year)]}},
            ]
        },
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
            "shift": 1,
        },
    ).to_list(20000)
    classes_by_id = {item.get("id"): item for item in classes if item.get("id")}

    if tenant_id:
        legacy = [
            item
            for item in legacy
            if (classes_by_id.get(item.get("class_id")) or {}).get("mantenedora_id") == tenant_id
        ]

    in_scope_classes = {
        cid: item
        for cid, item in classes_by_id.items()
        if is_class_in_scope(item)
        and (not tenant_id or item.get("mantenedora_id") == tenant_id)
        and (
            str(item.get("academic_year") or "") == str(academic_year)
            or cid in {a.get("class_id") for a in legacy}
        )
    }
    in_scope_ids = sorted(in_scope_classes)
    legacy = [item for item in legacy if item.get("class_id") in in_scope_classes]

    school_ids = sorted({item.get("school_id") for item in in_scope_classes.values() if item.get("school_id")})
    schools = await db.schools.find(
        {"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1}
    ).to_list(10000) if school_ids else []
    schools_by_id = {item.get("id"): item for item in schools if item.get("id")}

    staff_ids = sorted({item.get("staff_id") for item in legacy if item.get("staff_id")})
    staff_docs = await db.staff.find(
        {"id": {"$in": staff_ids}},
        {"_id": 0, "id": 1, "user_id": 1, "email": 1, "nome": 1, "full_name": 1},
    ).to_list(30000) if staff_ids else []
    staff_by_id = {item.get("id"): item for item in staff_docs if item.get("id")}

    users = await db.users.find(
        {}, {"_id": 0, "id": 1, "email": 1, "role": 1, "name": 1, "full_name": 1}
    ).to_list(30000)
    users_by_email = {
        str(item.get("email") or "").strip().casefold(): item
        for item in users
        if str(item.get("email") or "").strip()
    }

    course_ids = sorted({item.get("course_id") for item in legacy if item.get("course_id")})
    courses = await db.courses.find(
        {"id": {"$in": course_ids}}, {"_id": 0, "id": 1, "name": 1}
    ).to_list(10000) if course_ids else []
    courses_by_id = {item.get("id"): item for item in courses if item.get("id")}

    schedules = await db.class_schedules.find(
        {"class_id": {"$in": in_scope_ids}},
        {"_id": 0, "class_id": 1, "academic_year": 1, "schedule_slots": 1, "slot_times": 1},
    ).to_list(10000) if in_scope_ids else []
    schedules_by_class = {}
    for item in schedules:
        cid = item.get("class_id")
        if not cid:
            continue
        # Prefere documento do próprio ano; não adivinha entre múltiplos do mesmo ano.
        if str(item.get("academic_year") or "") == str(academic_year):
            schedules_by_class[cid] = item
        elif cid not in schedules_by_class:
            schedules_by_class[cid] = item

    grade_docs = await db.grades.find(
        {
            "class_id": {"$in": in_scope_ids},
            "academic_year": {"$in": [academic_year, str(academic_year)]},
        },
        {
            "_id": 0,
            "class_id": 1,
            "course_id": 1,
            "component_id": 1,
            "b1": 1,
            "b2": 1,
            "b3": 1,
            "b4": 1,
            "rec_s1": 1,
            "rec_s2": 1,
            "recovery": 1,
        },
    ).to_list(100000) if in_scope_ids else []
    grade_evidence_keys = {
        (str(item.get("class_id") or ""), str(item.get("course_id") or item.get("component_id") or ""))
        for item in grade_docs
        if grade_has_real_evidence(item)
    }

    # Grupos simultâneos turma+componente. Substituições não transformam um grupo em shared.
    group_staff: dict[tuple[str, str], set[str]] = defaultdict(set)
    class_staff: dict[str, set[str]] = defaultdict(set)
    for item in legacy:
        if item.get("is_substituicao"):
            continue
        cid = str(item.get("class_id") or "")
        course_id = str(item.get("course_id") or "")
        staff_id = str(item.get("staff_id") or "")
        if cid and staff_id:
            class_staff[cid].add(staff_id)
        if cid and course_id and staff_id:
            group_staff[(cid, course_id)].add(staff_id)

    classification_counts: Counter[str] = Counter()
    schedule_counts: Counter[str] = Counter()
    rows = []
    ready_creates = []
    identities = []

    for item in legacy:
        cid = str(item.get("class_id") or "")
        course_id = str(item.get("course_id") or "")
        staff = staff_by_id.get(item.get("staff_id")) or {}
        teacher_user_id = resolve_teacher_user_id(staff, users_by_email)
        schedule_state, weekly_slots = extract_weekly_slots(schedules_by_class.get(cid), course_id)
        schedule_counts[schedule_state] += 1
        group_count = len(group_staff.get((cid, course_id), set()))
        has_grades = (cid, course_id) in grade_evidence_keys
        classification = classify_plan_binding(
            teacher_user_id=teacher_user_id,
            is_substitution=bool(item.get("is_substituicao")),
            non_substitute_teacher_count=group_count,
            has_grade_evidence=has_grades,
            schedule_state=schedule_state,
        )
        classification_counts[classification] += 1

        klass = in_scope_classes.get(cid) or {}
        school = schools_by_id.get(klass.get("school_id")) or {}
        course = courses_by_id.get(course_id) or {}
        teacher_name = _safe_name(staff.get("nome") or staff.get("full_name"))
        row = {
            "legacy_assignment_id": item.get("id"),
            "staff_id": item.get("staff_id"),
            "teacher_user_id": teacher_user_id,
            "teacher_name": teacher_name,
            "school_id": klass.get("school_id"),
            "school_name": _safe_name(school.get("name")),
            "class_id": cid,
            "class_name": _safe_name(klass.get("name")),
            "course_id": course_id or None,
            "course_name": _safe_name(course.get("name")),
            "is_substitution": bool(item.get("is_substituicao")),
            "non_substitute_teachers_same_class_course": group_count,
            "has_grade_evidence": has_grades,
            "schedule_state": schedule_state,
            "weekly_slots_count": len(weekly_slots),
            "classification": classification,
        }
        rows.append(row)
        if classification == "teacher_identity_unresolved":
            identities.append(row)

        if classification == "regular_ready":
            ready_creates.append(
                {
                    "state": "DRY_RUN_ONLY",
                    "source_legacy_assignment_id": item.get("id"),
                    "teacher_id": teacher_user_id,
                    "teacher_name": teacher_name,
                    "class_id": cid,
                    "class_name": klass.get("name"),
                    "school_id": klass.get("school_id"),
                    "component_id": course_id or None,
                    "component_name": course.get("name"),
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
                }
            )

    no_teacher_classes = []
    legacy_class_ids = {str(item.get("class_id") or "") for item in legacy}
    for cid, klass in in_scope_classes.items():
        if str(cid) in legacy_class_ids:
            continue
        school = schools_by_id.get(klass.get("school_id")) or {}
        no_teacher_classes.append(
            {
                "class_id": cid,
                "class_name": klass.get("name"),
                "school_id": klass.get("school_id"),
                "school_name": school.get("name"),
            }
        )

    shared_groups = []
    for (cid, course_id), teachers in sorted(group_staff.items()):
        if len(teachers) <= 1:
            continue
        klass = in_scope_classes.get(cid) or {}
        school = schools_by_id.get(klass.get("school_id")) or {}
        teacher_items = []
        for sid in sorted(teachers):
            staff = staff_by_id.get(sid) or {}
            teacher_items.append(
                {
                    "staff_id": sid,
                    "teacher_user_id": resolve_teacher_user_id(staff, users_by_email),
                    "teacher_name": _safe_name(staff.get("nome") or staff.get("full_name")),
                }
            )
        shared_groups.append(
            {
                "class_id": cid,
                "class_name": klass.get("name"),
                "school_id": klass.get("school_id"),
                "school_name": school.get("name"),
                "course_id": course_id,
                "course_name": (courses_by_id.get(course_id) or {}).get("name"),
                "teacher_count": len(teachers),
                "teachers": teacher_items,
                "decision_required": ["confirm_shared", "student_scope", "grades_official_owner"],
            }
        )

    multi_teacher_classes = []
    for cid, teachers in sorted(class_staff.items()):
        if len(teachers) <= 1:
            continue
        klass = in_scope_classes.get(cid) or {}
        school = schools_by_id.get(klass.get("school_id")) or {}
        multi_teacher_classes.append(
            {
                "class_id": cid,
                "class_name": klass.get("name"),
                "school_id": klass.get("school_id"),
                "school_name": school.get("name"),
                "teacher_count": len(teachers),
            }
        )

    auto_ready = classification_counts.get("regular_ready", 0)
    review_required = sum(
        classification_counts.get(code, 0)
        for code in ("shared_review", "regular_or_integrator_review", "substitution_review")
    )
    blocked = len(rows) - auto_ready - review_required

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "READ_ONLY_DRY_RUN",
            "academic_year": academic_year,
            "reference_date": reference_date,
            "tenant_id": tenant_id,
            "historical_ownership_migration": False,
        },
        "summary": {
            "legacy_bindings_in_scope": len(rows),
            "classification": dict(sorted(classification_counts.items())),
            "schedule": dict(sorted(schedule_counts.items())),
            "regular_auto_ready": auto_ready,
            "review_required": review_required,
            "blocked": blocked,
            "confirmed_profile_counts": {"regular": auto_ready, "integrator": 0, "shared": 0},
            "shared_candidate_bindings": classification_counts.get("shared_review", 0),
            "regular_or_integrator_review": classification_counts.get("regular_or_integrator_review", 0),
            "teacher_identity_unresolved": classification_counts.get("teacher_identity_unresolved", 0),
            "substitution_review": classification_counts.get("substitution_review", 0),
            "no_teacher_binding_classes": len(no_teacher_classes),
            "multi_teacher_classes": len(multi_teacher_classes),
            "shared_candidate_class_course_groups": len(shared_groups),
            "dry_run_teacher_class_assignments_ready": len(ready_creates),
        },
        "teacher_identity_unresolved": identities,
        "no_teacher_binding_classes": no_teacher_classes,
        "multi_teacher_classes": multi_teacher_classes,
        "shared_candidate_groups": shared_groups,
        "dry_run_ready_creates": ready_creates,
        "binding_details": sorted(
            rows,
            key=lambda row: (
                row["classification"],
                row["school_name"].casefold(),
                row["class_name"].casefold(),
                row["teacher_name"].casefold(),
                str(row.get("course_name") or "").casefold(),
            ),
        ),
    }


def print_compact(report: Mapping[str, Any]) -> None:
    s = report["summary"]
    print("=== PLANO DVD 38B — READ-ONLY ===")
    print("CLASSIFICACAO:", s["classification"])
    print("HORARIOS:", s["schedule"])
    print(
        "DRY-RUN:",
        {
            "regular_auto_ready": s["regular_auto_ready"],
            "review_required": s["review_required"],
            "blocked": s["blocked"],
            "creates_ready": s["dry_run_teacher_class_assignments_ready"],
        },
    )
    print(
        "CASOS:",
        {
            "identity_unresolved": s["teacher_identity_unresolved"],
            "no_teacher_classes": s["no_teacher_binding_classes"],
            "multi_teacher_classes": s["multi_teacher_classes"],
            "shared_candidate_groups": s["shared_candidate_class_course_groups"],
        },
    )
    print("HISTORICO: preservado; nenhuma autoria retroativa será criada.")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--academic-year", type=int, default=datetime.now().year)
    parser.add_argument("--reference-date", default=date.today().isoformat())
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]
        report = await collect_cutover_plan(
            db,
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            tenant_id=args.tenant_id,
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
