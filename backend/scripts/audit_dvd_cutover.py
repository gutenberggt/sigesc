"""Auditoria READ-ONLY do cutover do Diário por Vínculo Docente (DVD).

Objetivo
--------
Medir, sem alterar o MongoDB, quanto do fluxo de professor ainda depende do
legado (`teacher_assignments`, `attendance`, `learning_objects`) e quanto já está
coberto pelo DVD (`teacher_class_assignments`, `content_entries`).

A auditoria usa o mesmo escopo canônico do DVD v1 (`is_class_in_scope`) e
classifica cada alocação legada ativa do ano letivo em relação aos vínculos DVD.
Nenhum dado é migrado, corrigido, inferido ou reatribuído.

Uso no backend de produção:
    cd /app/backend
    python scripts/audit_dvd_cutover.py \
      --academic-year 2026 \
      --reference-date 2026-08-18 \
      --json /tmp/dvd-cutover-audit-2026.json

Opções:
    --tenant-id ID        restringe a uma mantenedora;
    --academic-year ANO   default = ano atual;
    --reference-date DATA default = hoje, formato YYYY-MM-DD;
    --json CAMINHO        salva cópia JSON local (não grava no banco);
    --details-limit N     linhas detalhadas exibidas no stdout (default 50).

Segurança
---------
Este arquivo só usa operações de leitura do MongoDB (`find`, `find_one` e
`to_list`). O teste `test_dvd_cutover_audit_read_only.py` impede a introdução
de mutadores Mongo nesta auditoria.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from services.diary_assignment_contract import is_class_in_scope  # noqa: E402

ACTIVE_LEGACY_STATUS = "ativo"
DVD_PROFILES = {"regular", "integrator", "shared"}


@dataclass(frozen=True)
class BindingClassification:
    code: str
    matching_dvd_ids: tuple[str, ...] = ()
    active_enabled_dvd_ids: tuple[str, ...] = ()


def _db_client():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


def _iso_day(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value).strip()
    return raw[:10] if raw else None


def _is_current_assignment(assignment: Mapping[str, Any], reference_date: str) -> bool:
    if assignment.get("deleted") is True:
        return False
    valid_from = _iso_day(assignment.get("valid_from"))
    valid_until = _iso_day(assignment.get("valid_until"))
    if not valid_from or valid_from > reference_date:
        return False
    return valid_until is None or valid_until >= reference_date


def _component_compatible(
    dvd_component_id: Optional[str], legacy_course_id: Optional[str]
) -> bool:
    """Assignment class-wide (component_id=None) é compatível com o componente."""
    return dvd_component_id is None or dvd_component_id == legacy_course_id


def _resolve_teacher_user_id(
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


def _classify_legacy_binding(
    *,
    teacher_user_id: Optional[str],
    class_id: Optional[str],
    course_id: Optional[str],
    reference_date: str,
    dvd_assignments: Iterable[Mapping[str, Any]],
) -> BindingClassification:
    if not teacher_user_id:
        return BindingClassification("teacher_identity_unresolved")
    if not class_id:
        return BindingClassification("class_unresolved")

    matching = [
        item
        for item in dvd_assignments
        if item.get("teacher_id") == teacher_user_id
        and item.get("class_id") == class_id
        and _component_compatible(item.get("component_id"), course_id)
        and item.get("deleted") is not True
    ]
    matching_ids = tuple(sorted(str(item.get("id")) for item in matching if item.get("id")))
    if not matching:
        return BindingClassification("dvd_missing")

    current = [item for item in matching if _is_current_assignment(item, reference_date)]
    if not current:
        return BindingClassification("dvd_present_not_current", matching_ids)

    enabled = [item for item in current if (item.get("diary_settings") or {}).get("enabled") is True]
    enabled_ids = tuple(sorted(str(item.get("id")) for item in enabled if item.get("id")))
    if not enabled:
        return BindingClassification("dvd_present_disabled", matching_ids)
    if len(enabled) > 1:
        return BindingClassification("dvd_active_ambiguous", matching_ids, enabled_ids)

    settings = enabled[0].get("diary_settings") or {}
    profile = settings.get("profile")
    if profile not in DVD_PROFILES:
        return BindingClassification("dvd_enabled_invalid_profile", matching_ids, enabled_ids)
    if settings.get("student_scope") == "group" and profile == "shared":
        return BindingClassification("dvd_active_group_unresolved", matching_ids, enabled_ids)
    return BindingClassification("dvd_active_exact", matching_ids, enabled_ids)


def _assignment_id_present(doc: Mapping[str, Any]) -> bool:
    return bool(doc.get("assignment_id"))


def _content_key(doc: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(doc.get("class_id") or ""),
        str(doc.get("component_id") or doc.get("course_id") or ""),
        str(_iso_day(doc.get("date")) or ""),
    )


def _attendance_key(doc: Mapping[str, Any]) -> tuple[str, str]:
    return (str(doc.get("class_id") or ""), str(_iso_day(doc.get("date")) or ""))


def _scope_reason(class_info: Mapping[str, Any]) -> str:
    program = str(class_info.get("atendimento_programa") or "").strip().casefold()
    if program == "aee":
        return "aee"
    return "dvd_v1_out_of_scope"


def _safe_name(value: Any) -> str:
    return str(value or "").strip()


async def collect_audit(
    db,
    *,
    academic_year: int,
    reference_date: str,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Coleta o relatório usando somente leituras do MongoDB."""

    class_query: dict[str, Any] = {"academic_year": academic_year}
    if tenant_id:
        class_query["mantenedora_id"] = tenant_id
    classes = await db.classes.find(
        class_query,
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
    ).to_list(10000)
    classes_by_id = {item.get("id"): item for item in classes if item.get("id")}
    in_scope_classes = {cid: item for cid, item in classes_by_id.items() if is_class_in_scope(item)}
    out_scope_classes = {cid: item for cid, item in classes_by_id.items() if cid not in in_scope_classes}
    in_scope_ids = sorted(in_scope_classes)

    school_ids = sorted({item.get("school_id") for item in classes if item.get("school_id")})
    schools = await db.schools.find(
        {"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}
    ).to_list(10000)
    schools_by_id = {item.get("id"): item for item in schools if item.get("id")}

    legacy_query: dict[str, Any] = {
        "academic_year": academic_year,
        "status": ACTIVE_LEGACY_STATUS,
    }
    if tenant_id:
        legacy_query["mantenedora_id"] = tenant_id
    legacy_assignments = await db.teacher_assignments.find(
        legacy_query,
        {
            "_id": 0,
            "id": 1,
            "staff_id": 1,
            "school_id": 1,
            "class_id": 1,
            "course_id": 1,
            "academic_year": 1,
            "status": 1,
            "is_substituicao": 1,
            "substituted_staff_id": 1,
            "data_inicio_substituicao": 1,
            "data_fim_substituicao": 1,
            "mantenedora_id": 1,
        },
    ).to_list(20000)

    staff_ids = sorted({item.get("staff_id") for item in legacy_assignments if item.get("staff_id")})
    staff_docs = await db.staff.find(
        {"id": {"$in": staff_ids}},
        {"_id": 0, "id": 1, "user_id": 1, "email": 1, "nome": 1, "full_name": 1},
    ).to_list(20000)
    staff_by_id = {item.get("id"): item for item in staff_docs if item.get("id")}
    emails = sorted(
        {
            str(item.get("email")).strip().casefold()
            for item in staff_docs
            if str(item.get("email") or "").strip()
        }
    )
    user_docs = await db.users.find(
        {"email": {"$in": emails}},
        {"_id": 0, "id": 1, "email": 1, "role": 1, "name": 1, "full_name": 1},
    ).to_list(20000) if emails else []
    users_by_email = {
        str(item.get("email") or "").strip().casefold(): item
        for item in user_docs
        if item.get("email")
    }

    dvd_query: dict[str, Any] = {"deleted": {"$ne": True}}
    if tenant_id:
        # Registros antigos podem ter tenant apenas na turma. O filtro definitivo
        # é feito abaixo pela classe em escopo; não ampliar aqui evita falso negativo.
        pass
    dvd_assignments = await db.teacher_class_assignments.find(
        dvd_query,
        {
            "_id": 0,
            "id": 1,
            "teacher_id": 1,
            "teacher_name": 1,
            "class_id": 1,
            "component_id": 1,
            "valid_from": 1,
            "valid_until": 1,
            "deleted": 1,
            "is_substitute": 1,
            "diary_settings": 1,
            "grades_official_owner": 1,
        },
    ).to_list(30000)
    if tenant_id:
        dvd_assignments = [
            item
            for item in dvd_assignments
            if (classes_by_id.get(item.get("class_id")) or {}).get("mantenedora_id") == tenant_id
        ]

    dvd_by_teacher_class: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in dvd_assignments:
        if item.get("teacher_id") and item.get("class_id"):
            dvd_by_teacher_class[(str(item["teacher_id"]), str(item["class_id"]))].append(item)

    binding_counts: Counter[str] = Counter()
    detail_rows: list[dict[str, Any]] = []
    class_binding_states: dict[str, list[str]] = defaultdict(list)
    unique_legacy_keys: set[tuple[str, str, str]] = set()
    in_scope_legacy_total = 0
    out_scope_legacy_total = 0
    orphan_class_total = 0

    for legacy in legacy_assignments:
        class_id = legacy.get("class_id")
        class_info = classes_by_id.get(class_id)
        if not class_info:
            orphan_class_total += 1
            binding_counts["class_unresolved"] += 1
            continue
        if not is_class_in_scope(class_info):
            out_scope_legacy_total += 1
            continue

        in_scope_legacy_total += 1
        staff = staff_by_id.get(legacy.get("staff_id"))
        teacher_user_id = _resolve_teacher_user_id(staff, users_by_email)
        candidates = dvd_by_teacher_class.get((str(teacher_user_id), str(class_id)), []) if teacher_user_id else []
        classification = _classify_legacy_binding(
            teacher_user_id=teacher_user_id,
            class_id=class_id,
            course_id=legacy.get("course_id"),
            reference_date=reference_date,
            dvd_assignments=candidates,
        )
        binding_counts[classification.code] += 1
        class_binding_states[str(class_id)].append(classification.code)
        unique_legacy_keys.add(
            (str(legacy.get("staff_id") or ""), str(class_id or ""), str(legacy.get("course_id") or ""))
        )

        school = schools_by_id.get(class_info.get("school_id")) or {}
        detail_rows.append(
            {
                "legacy_assignment_id": legacy.get("id"),
                "staff_id": legacy.get("staff_id"),
                "teacher_user_id": teacher_user_id,
                "teacher_name": _safe_name((staff or {}).get("nome") or (staff or {}).get("full_name")),
                "school_id": class_info.get("school_id"),
                "school_name": _safe_name(school.get("name")),
                "class_id": class_id,
                "class_name": _safe_name(class_info.get("name")),
                "course_id": legacy.get("course_id"),
                "is_substitution": bool(legacy.get("is_substituicao")),
                "classification": classification.code,
                "matching_dvd_ids": list(classification.matching_dvd_ids),
                "active_enabled_dvd_ids": list(classification.active_enabled_dvd_ids),
            }
        )

    class_cutover_counts: Counter[str] = Counter()
    class_cutover_details: list[dict[str, Any]] = []
    for class_id in in_scope_ids:
        states = class_binding_states.get(str(class_id), [])
        current_enabled = [
            item
            for item in dvd_assignments
            if item.get("class_id") == class_id
            and _is_current_assignment(item, reference_date)
            and (item.get("diary_settings") or {}).get("enabled") is True
        ]
        if states:
            exact = sum(1 for state in states if state == "dvd_active_exact")
            if exact == len(states):
                state = "fully_cutover"
            elif exact > 0 or current_enabled:
                state = "partially_cutover"
            else:
                state = "legacy_only"
        elif current_enabled:
            state = "dvd_only"
        else:
            state = "no_teacher_binding"
        class_cutover_counts[state] += 1
        if state in {"partially_cutover", "legacy_only"}:
            class_info = in_scope_classes[class_id]
            school = schools_by_id.get(class_info.get("school_id")) or {}
            class_cutover_details.append(
                {
                    "class_id": class_id,
                    "class_name": class_info.get("name"),
                    "school_id": class_info.get("school_id"),
                    "school_name": school.get("name"),
                    "cutover_state": state,
                    "legacy_binding_states": dict(Counter(states)),
                    "current_enabled_dvd_ids": sorted(
                        str(item.get("id")) for item in current_enabled if item.get("id")
                    ),
                }
            )

    current_enabled_dvd = [
        item
        for item in dvd_assignments
        if item.get("class_id") in in_scope_classes
        and _is_current_assignment(item, reference_date)
        and (item.get("diary_settings") or {}).get("enabled") is True
    ]
    dvd_profile_counts = Counter(
        str((item.get("diary_settings") or {}).get("profile") or "missing")
        for item in current_enabled_dvd
    )
    dvd_group_unresolved = sum(
        1
        for item in current_enabled_dvd
        if (item.get("diary_settings") or {}).get("profile") == "shared"
        and (item.get("diary_settings") or {}).get("student_scope") == "group"
    )

    attendance_docs = await db.attendance.find(
        {"academic_year": academic_year, "class_id": {"$in": in_scope_ids}},
        {
            "_id": 0,
            "id": 1,
            "class_id": 1,
            "date": 1,
            "assignment_id": 1,
            "attendance_mode": 1,
            "attendance_purpose": 1,
            "records": 1,
        },
    ).to_list(50000) if in_scope_ids else []
    attendance_documentary = await db.attendance_documentary.find(
        {"academic_year": academic_year, "class_id": {"$in": in_scope_ids}},
        {
            "_id": 0,
            "id": 1,
            "class_id": 1,
            "date": 1,
            "assignment_id": 1,
            "records": 1,
        },
    ).to_list(50000) if in_scope_ids else []

    attendance_legacy = [item for item in attendance_docs if not _assignment_id_present(item)]
    attendance_dvd = [item for item in attendance_docs if _assignment_id_present(item)]
    current_dvd_class_ids = {item.get("class_id") for item in current_enabled_dvd}
    legacy_attendance_on_current_dvd_classes = [
        item for item in attendance_legacy if item.get("class_id") in current_dvd_class_ids
    ]

    learning_objects = await db.learning_objects.find(
        {"academic_year": academic_year, "class_id": {"$in": in_scope_ids}},
        {
            "_id": 0,
            "id": 1,
            "class_id": 1,
            "course_id": 1,
            "date": 1,
            "recorded_by": 1,
        },
    ).to_list(50000) if in_scope_ids else []
    content_entries = await db.content_entries.find(
        {"academic_year": academic_year, "class_id": {"$in": in_scope_ids}},
        {
            "_id": 0,
            "id": 1,
            "class_id": 1,
            "course_id": 1,
            "component_id": 1,
            "date": 1,
            "assignment_id": 1,
            "teacher_id": 1,
            "deleted": 1,
            "status": 1,
        },
    ).to_list(50000) if in_scope_ids else []
    content_entries = [item for item in content_entries if item.get("deleted") is not True]
    content_dvd = [item for item in content_entries if _assignment_id_present(item)]
    content_entries_legacy = [item for item in content_entries if not _assignment_id_present(item)]

    learning_keys = {_content_key(item) for item in learning_objects}
    content_dvd_keys = {_content_key(item) for item in content_dvd}
    overlap_keys = sorted(learning_keys & content_dvd_keys)
    legacy_content_on_current_dvd_classes = [
        item for item in learning_objects if item.get("class_id") in current_dvd_class_ids
    ]

    out_scope_reasons = Counter(_scope_reason(item) for item in out_scope_classes.values())
    safe_exact = binding_counts.get("dvd_active_exact", 0)
    remaining_legacy = max(0, in_scope_legacy_total - safe_exact)

    report = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "READ_ONLY",
            "academic_year": academic_year,
            "reference_date": reference_date,
            "tenant_id": tenant_id,
            "database_name": os.environ.get("DB_NAME"),
        },
        "scope": {
            "classes_year_total": len(classes),
            "classes_dvd_v1_in_scope": len(in_scope_classes),
            "classes_out_of_scope": len(out_scope_classes),
            "out_of_scope_reasons": dict(out_scope_reasons),
        },
        "bindings": {
            "legacy_teacher_assignments_active_year_total": len(legacy_assignments),
            "legacy_bindings_in_dvd_scope": in_scope_legacy_total,
            "legacy_bindings_out_of_dvd_scope": out_scope_legacy_total,
            "legacy_bindings_orphan_class": orphan_class_total,
            "legacy_unique_staff_class_course_keys_in_scope": len(unique_legacy_keys),
            "dvd_current_enabled_in_scope": len(current_enabled_dvd),
            "dvd_current_profiles": dict(dvd_profile_counts),
            "dvd_shared_group_unresolved": dvd_group_unresolved,
            "classification": dict(sorted(binding_counts.items())),
            "safe_exact_cutover_bindings": safe_exact,
            "remaining_legacy_or_unsafe_bindings": remaining_legacy,
        },
        "classes_cutover": {
            "classification": dict(sorted(class_cutover_counts.items())),
            "attention": sorted(
                class_cutover_details,
                key=lambda item: (
                    str(item.get("school_name") or "").casefold(),
                    str(item.get("class_name") or "").casefold(),
                ),
            ),
        },
        "attendance": {
            "official_collection_docs_in_scope_year": len(attendance_docs),
            "dvd_docs_with_assignment_id": len(attendance_dvd),
            "legacy_docs_without_assignment_id": len(attendance_legacy),
            "legacy_distinct_class_dates": len({_attendance_key(item) for item in attendance_legacy}),
            "legacy_student_rows": sum(len(item.get("records") or []) for item in attendance_legacy),
            "legacy_docs_on_classes_with_current_dvd": len(legacy_attendance_on_current_dvd_classes),
            "documentary_pdf_only_docs": len(attendance_documentary),
        },
        "content": {
            "legacy_learning_objects_docs": len(learning_objects),
            "legacy_learning_objects_unique_keys": len(learning_keys),
            "content_entries_total_non_deleted": len(content_entries),
            "content_entries_dvd_with_assignment_id": len(content_dvd),
            "content_entries_legacy_without_assignment_id": len(content_entries_legacy),
            "legacy_learning_objects_on_classes_with_current_dvd": len(legacy_content_on_current_dvd_classes),
            "legacy_vs_dvd_overlap_keys": len(overlap_keys),
            "overlap_keys_sample": [list(key) for key in overlap_keys[:100]],
        },
        "legacy_binding_details": sorted(
            detail_rows,
            key=lambda item: (
                item["classification"],
                item["school_name"].casefold(),
                item["class_name"].casefold(),
                item["teacher_name"].casefold(),
                str(item.get("course_id") or ""),
            ),
        ),
    }
    return report


def print_report(report: Mapping[str, Any], details_limit: int = 50) -> None:
    meta = report["meta"]
    bindings = report["bindings"]
    classes_cutover = report["classes_cutover"]
    attendance = report["attendance"]
    content = report["content"]

    print("=" * 88)
    print("AUDITORIA READ-ONLY — CUTOVER DVD: FREQUÊNCIA + CONTEÚDOS")
    print("=" * 88)
    print(
        f"ano={meta['academic_year']} | referência={meta['reference_date']} | "
        f"tenant={meta.get('tenant_id') or 'TODOS'} | db={meta.get('database_name') or '-'}"
    )
    print()
    print("VÍNCULOS")
    print(json.dumps(bindings, ensure_ascii=False, indent=2, default=str))
    print()
    print("TURMAS — ESTADO DO CUTOVER")
    print(json.dumps(classes_cutover["classification"], ensure_ascii=False, indent=2))
    print()
    print("FREQUÊNCIA")
    print(json.dumps(attendance, ensure_ascii=False, indent=2))
    print()
    print("CONTEÚDOS")
    print(json.dumps(content, ensure_ascii=False, indent=2))

    attention = [
        row
        for row in report["legacy_binding_details"]
        if row.get("classification") != "dvd_active_exact"
    ]
    print()
    print(f"VÍNCULOS QUE EXIGEM AÇÃO — exibindo até {details_limit} de {len(attention)}")
    print("-" * 88)
    for row in attention[: max(0, details_limit)]:
        print(
            f"{row['classification']:<30} | {row['school_name'][:24]:<24} | "
            f"{row['class_name'][:18]:<18} | {row['teacher_name'][:24]:<24} | "
            f"course={str(row.get('course_id') or '-')[:12]}"
        )


async def _main(args) -> int:
    # Validação antecipada: não inicia consulta com data ambígua.
    try:
        date.fromisoformat(args.reference_date)
    except ValueError as exc:
        raise SystemExit("--reference-date deve usar YYYY-MM-DD") from exc

    client, db = _db_client()
    try:
        report = await collect_audit(
            db,
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            tenant_id=args.tenant_id,
        )
        print_report(report, details_limit=args.details_limit)
        if args.json:
            out_path = Path(args.json)
            out_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"\nJSON local salvo em: {out_path}")
        return 0
    finally:
        client.close()


def _parse_args():
    parser = argparse.ArgumentParser(description="Auditoria read-only do cutover DVD")
    parser.add_argument("--academic-year", type=int, default=date.today().year)
    parser.add_argument("--reference-date", default=date.today().isoformat())
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--json", default=None)
    parser.add_argument("--details-limit", type=int, default=50)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(_parse_args())))
