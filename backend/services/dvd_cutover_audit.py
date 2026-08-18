"""Serviço READ-ONLY para auditoria do cutover DVD.

Não executa mutações. A finalidade é medir o estado atual antes de qualquer
migração de `teacher_assignments`, frequência ou conteúdos.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from services.diary_assignment_contract import is_class_in_scope

ACTIVE_LEGACY_STATUS = "ativo"
DVD_PROFILES = {"regular", "integrator", "shared"}


@dataclass(frozen=True)
class BindingClassification:
    code: str
    matching_dvd_ids: tuple[str, ...] = ()
    active_enabled_dvd_ids: tuple[str, ...] = ()


def iso_day(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value).strip()
    return raw[:10] if raw else None


def is_current_assignment(assignment: Mapping[str, Any], reference_date: str) -> bool:
    if assignment.get("deleted") is True:
        return False
    valid_from = iso_day(assignment.get("valid_from"))
    valid_until = iso_day(assignment.get("valid_until"))
    if not valid_from or valid_from > reference_date:
        return False
    return valid_until is None or valid_until >= reference_date


def component_compatible(
    dvd_component_id: Optional[str], legacy_course_id: Optional[str]
) -> bool:
    """Assignment class-wide (`component_id=None`) é compatível com o componente."""
    return dvd_component_id is None or dvd_component_id == legacy_course_id


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


def classify_legacy_binding(
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
        and component_compatible(item.get("component_id"), course_id)
        and item.get("deleted") is not True
    ]
    matching_ids = tuple(sorted(str(item.get("id")) for item in matching if item.get("id")))
    if not matching:
        return BindingClassification("dvd_missing")

    current = [item for item in matching if is_current_assignment(item, reference_date)]
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


def assignment_id_present(doc: Mapping[str, Any]) -> bool:
    return bool(doc.get("assignment_id"))


def content_key(doc: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(doc.get("class_id") or ""),
        str(doc.get("component_id") or doc.get("course_id") or ""),
        str(iso_day(doc.get("date")) or ""),
    )


def attendance_key(doc: Mapping[str, Any]) -> tuple[str, str]:
    return (str(doc.get("class_id") or ""), str(iso_day(doc.get("date")) or ""))


def scope_reason(class_info: Mapping[str, Any]) -> str:
    program = str(class_info.get("atendimento_programa") or "").strip().casefold()
    if program == "aee":
        return "aee"
    return "dvd_v1_out_of_scope"


def year_or_date_query(academic_year: int) -> dict[str, Any]:
    """Captura dados do ano mesmo quando `academic_year` legado está ausente."""
    return {
        "$or": [
            {"academic_year": {"$in": [academic_year, str(academic_year)]}},
            {"date": {"$gte": f"{academic_year}-01-01", "$lte": f"{academic_year}-12-31"}},
        ]
    }


def _safe_name(value: Any) -> str:
    return str(value or "").strip()


async def collect_dvd_cutover_audit(
    db,
    *,
    academic_year: int,
    reference_date: str,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Coleta métricas e detalhes sem alterar qualquer coleção."""

    legacy_assignments = await db.teacher_assignments.find(
        {
            "academic_year": {"$in": [academic_year, str(academic_year)]},
            "status": ACTIVE_LEGACY_STATUS,
        },
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
    ).to_list(30000)

    dvd_assignments = await db.teacher_class_assignments.find(
        {"deleted": {"$ne": True}},
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
            "mantenedora_id": 1,
        },
    ).to_list(30000)

    # Carrega turmas de uma vez. Além das turmas marcadas com o ano, considera
    # as referenciadas pelos dois motores de vínculo, evitando perder legado com
    # academic_year ausente/inconsistente no documento da turma.
    all_classes = await db.classes.find(
        {},
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
    ).to_list(20000)
    all_classes_by_id = {item.get("id"): item for item in all_classes if item.get("id")}

    if tenant_id:
        legacy_assignments = [
            item
            for item in legacy_assignments
            if (all_classes_by_id.get(item.get("class_id")) or {}).get("mantenedora_id") == tenant_id
        ]
        dvd_assignments = [
            item
            for item in dvd_assignments
            if (all_classes_by_id.get(item.get("class_id")) or {}).get("mantenedora_id") == tenant_id
        ]

    legacy_class_ids = {item.get("class_id") for item in legacy_assignments if item.get("class_id")}
    current_dvd_all = [item for item in dvd_assignments if is_current_assignment(item, reference_date)]
    current_dvd_class_ids_all = {
        item.get("class_id") for item in current_dvd_all if item.get("class_id")
    }
    year_class_ids = {
        item.get("id")
        for item in all_classes
        if str(item.get("academic_year") or "") == str(academic_year)
        and (not tenant_id or item.get("mantenedora_id") == tenant_id)
    }
    relevant_class_ids = year_class_ids | legacy_class_ids | current_dvd_class_ids_all
    classes_by_id = {
        cid: all_classes_by_id[cid]
        for cid in relevant_class_ids
        if cid in all_classes_by_id
    }
    in_scope_classes = {cid: item for cid, item in classes_by_id.items() if is_class_in_scope(item)}
    out_scope_classes = {cid: item for cid, item in classes_by_id.items() if cid not in in_scope_classes}
    in_scope_ids = sorted(in_scope_classes)

    school_ids = sorted({item.get("school_id") for item in classes_by_id.values() if item.get("school_id")})
    schools = await db.schools.find(
        {"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}
    ).to_list(10000) if school_ids else []
    schools_by_id = {item.get("id"): item for item in schools if item.get("id")}

    staff_ids = sorted({item.get("staff_id") for item in legacy_assignments if item.get("staff_id")})
    staff_docs = await db.staff.find(
        {"id": {"$in": staff_ids}},
        {"_id": 0, "id": 1, "user_id": 1, "email": 1, "nome": 1, "full_name": 1},
    ).to_list(30000) if staff_ids else []
    staff_by_id = {item.get("id"): item for item in staff_docs if item.get("id")}

    # O fallback por email deve ser case-insensitive. Como o universo de usuários
    # é pequeno frente aos registros pedagógicos, lê apenas a projeção necessária
    # e normaliza em memória, sem regex nem inferência de identidade.
    user_docs = await db.users.find(
        {}, {"_id": 0, "id": 1, "email": 1, "role": 1, "name": 1, "full_name": 1}
    ).to_list(30000)
    users_by_email = {
        str(item.get("email") or "").strip().casefold(): item
        for item in user_docs
        if str(item.get("email") or "").strip()
    }

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
        teacher_user_id = resolve_teacher_user_id(staff, users_by_email)
        candidates = dvd_by_teacher_class.get((str(teacher_user_id), str(class_id)), []) if teacher_user_id else []
        classification = classify_legacy_binding(
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
            and is_current_assignment(item, reference_date)
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
        and is_current_assignment(item, reference_date)
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

    if in_scope_ids:
        record_scope = {"class_id": {"$in": in_scope_ids}, **year_or_date_query(academic_year)}
        attendance_docs = await db.attendance.find(
            record_scope,
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
        ).to_list(100000)
        attendance_documentary = await db.attendance_documentary.find(
            record_scope,
            {"_id": 0, "id": 1, "class_id": 1, "date": 1, "assignment_id": 1, "records": 1},
        ).to_list(100000)
        learning_objects = await db.learning_objects.find(
            record_scope,
            {"_id": 0, "id": 1, "class_id": 1, "course_id": 1, "date": 1, "recorded_by": 1},
        ).to_list(100000)
        content_entries = await db.content_entries.find(
            record_scope,
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
        ).to_list(100000)
    else:
        attendance_docs = []
        attendance_documentary = []
        learning_objects = []
        content_entries = []

    attendance_legacy = [item for item in attendance_docs if not assignment_id_present(item)]
    attendance_dvd = [item for item in attendance_docs if assignment_id_present(item)]
    current_dvd_class_ids = {item.get("class_id") for item in current_enabled_dvd}
    legacy_attendance_on_current_dvd_classes = [
        item for item in attendance_legacy if item.get("class_id") in current_dvd_class_ids
    ]

    content_entries = [item for item in content_entries if item.get("deleted") is not True]
    content_dvd = [item for item in content_entries if assignment_id_present(item)]
    content_entries_legacy = [item for item in content_entries if not assignment_id_present(item)]
    learning_keys = {content_key(item) for item in learning_objects}
    content_dvd_keys = {content_key(item) for item in content_dvd}
    overlap_keys = sorted(learning_keys & content_dvd_keys)
    legacy_content_on_current_dvd_classes = [
        item for item in learning_objects if item.get("class_id") in current_dvd_class_ids
    ]

    out_scope_reasons = Counter(scope_reason(item) for item in out_scope_classes.values())
    safe_exact = binding_counts.get("dvd_active_exact", 0)
    remaining_legacy = max(0, in_scope_legacy_total - safe_exact)

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "READ_ONLY",
            "academic_year": academic_year,
            "reference_date": reference_date,
            "tenant_id": tenant_id,
        },
        "scope": {
            "classes_relevant_total": len(classes_by_id),
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
            "legacy_distinct_class_dates": len({attendance_key(item) for item in attendance_legacy}),
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
