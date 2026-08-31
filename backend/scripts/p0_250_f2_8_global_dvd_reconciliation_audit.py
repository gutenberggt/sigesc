#!/usr/bin/env python3
"""P0 #250 F2.8 — inventário global read-only de reconciliação docente/DVD.

Objetivo
========
Medir em produção, sem qualquer escrita, o tamanho real do passivo entre as duas
representações de vínculo docente atualmente coexistentes no SIGESC:

- ``teacher_assignments``: entitlement legado usado por ``/professor/turmas`` e
  por módulos pedagógicos históricos;
- ``teacher_class_assignments``: vínculo canônico do Diário por Vínculo (DVD),
  com validade, tenant/escola e ``diary_settings`` explícitos.

A auditoria é global para o ano letivo alvo. Ela NÃO é codificada por nome de
professor, escola ou componente e usa o caso 7 DVD + 2 legados apenas como uma
classe de estado possível: ``PARTIAL_CUTOVER``.

Privacidade / segurança
=======================
- MongoDB somente leitura;
- nenhum HTTP de aplicação;
- nenhum ID, nome, e-mail ou PII é emitido;
- nenhuma nota, frequência ou conteúdo pedagógico é lido;
- saída contém apenas contagens e classificações estruturais.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import date
from typing import Any, Iterable

from pymongo import MongoClient

from services.diary_assignment_access import (
    DiaryAssignmentAccessError,
    effective_diary_settings,
    is_assignment_active_on,
)
from services.diary_assignment_contract import is_class_in_scope

ACADEMIC_YEAR = int(os.environ.get("P0_250_F2_8_ACADEMIC_YEAR", "2026"))
REFERENCE_DATE = os.environ.get("P0_250_F2_8_REFERENCE_DATE", date.today().isoformat())[:10]
ACTIVE_STATUSES = ("ativo", "active")

COMPONENT_CLASSIFICATIONS = (
    "CANONICAL_COVERED",
    "PARTIAL_CUTOVER_COMPONENT_MISSING",
    "LEGACY_ONLY_CLASS",
    "DVD_PRESENT_INVALID",
    "DVD_DUPLICATE_COVERAGE",
    "LEGACY_DUPLICATE",
    "IDENTITY_UNRESOLVED",
    "USER_ROLE_NOT_PROFESSOR",
    "TENANT_SCOPE_UNRESOLVED",
    "SCHOOL_SCOPE_MISSING",
    "COURSE_UNRESOLVED",
    "OUT_OF_DVD_SCOPE",
)

GROUP_CLASSIFICATIONS = (
    "FULL_CANONICAL",
    "PARTIAL_CUTOVER",
    "LEGACY_ONLY",
    "REQUIRES_REVIEW",
    "OUT_OF_DVD_SCOPE",
)

MONGO_MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
    ".drop(", ".drop_database(",
)


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _role_is_professor(user: dict[str, Any]) -> bool:
    # O endpoint /professor/turmas exige hoje role primária professor. A auditoria
    # mede o contrato real em produção, não amplia papel por roles secundárias.
    return _sid(user.get("role")) == "professor"


def _school_ids_for_staff(db, staff: dict[str, Any], user: dict[str, Any]) -> set[str]:
    school_ids = {_sid(value) for value in (user.get("school_ids") or []) if _sid(value)}
    for link in user.get("school_links") or []:
        if not isinstance(link, dict):
            continue
        school_id = _sid(link.get("school_id"))
        roles = link.get("roles") or ([link.get("role")] if link.get("role") else [])
        if school_id and (not roles or "professor" in roles):
            school_ids.add(school_id)
    for row in db.school_assignments.find(
        {
            "staff_id": staff.get("id"),
            "academic_year": ACADEMIC_YEAR,
            "status": {"$in": list(ACTIVE_STATUSES)},
        },
        {"_id": 0, "school_id": 1},
    ):
        school_id = _sid(row.get("school_id"))
        if school_id:
            school_ids.add(school_id)
    return school_ids


def _resolve_user_for_staff(db, staff: dict[str, Any]) -> dict[str, Any] | None:
    queries: list[dict[str, Any]] = []
    if _sid(staff.get("user_id")):
        queries.append({"id": staff.get("user_id")})
    if _sid(staff.get("email")):
        queries.append({"email": staff.get("email")})
    seen: dict[str, dict[str, Any]] = {}
    for query in queries:
        for user in db.users.find(
            query,
            {
                "_id": 0,
                "id": 1,
                "email": 1,
                "role": 1,
                "mantenedora_id": 1,
                "school_ids": 1,
                "school_links": 1,
            },
        ).limit(3):
            if _sid(user.get("id")):
                seen[_sid(user.get("id"))] = user
    if len(seen) != 1:
        return None
    return next(iter(seen.values()))


def _candidate_invalid_reason(
    row: dict[str, Any],
    *,
    class_doc: dict[str, Any],
    user: dict[str, Any],
    school_ids: set[str],
) -> str | None:
    if row.get("deleted") is True:
        return "DELETED"
    try:
        settings = effective_diary_settings(row)
    except DiaryAssignmentAccessError:
        return "INVALID_DIARY_SETTINGS"
    if not settings.enabled:
        return "DVD_NOT_ENABLED"
    if not is_assignment_active_on(row, REFERENCE_DATE):
        return "ASSIGNMENT_NOT_ACTIVE"

    class_tenant = _sid(class_doc.get("mantenedora_id"))
    user_tenant = _sid(user.get("mantenedora_id"))
    row_tenant = _sid(row.get("mantenedora_id"))
    if not class_tenant or not user_tenant or user_tenant != class_tenant:
        return "TENANT_ACCESS_DENIED"
    if row_tenant and row_tenant != class_tenant:
        return "ASSIGNMENT_TENANT_MISMATCH"

    class_school = _sid(class_doc.get("school_id"))
    row_school = _sid(row.get("school_id"))
    if not class_school:
        return "CLASS_SCHOOL_MISSING"
    if row_school and row_school != class_school:
        return "ASSIGNMENT_SCHOOL_MISMATCH"
    if class_school not in school_ids:
        return "SCHOOL_ACCESS_DENIED"
    return None


def classify_group(component_rows: Iterable[dict[str, Any]]) -> str:
    rows = list(component_rows)
    if not rows:
        return "REQUIRES_REVIEW"
    statuses = [row["classification"] for row in rows]
    if all(status == "OUT_OF_DVD_SCOPE" for status in statuses):
        return "OUT_OF_DVD_SCOPE"
    eligible = [status for status in statuses if status != "OUT_OF_DVD_SCOPE"]
    if eligible and all(status == "CANONICAL_COVERED" for status in eligible):
        return "FULL_CANONICAL"
    covered = sum(status == "CANONICAL_COVERED" for status in eligible)
    missing = sum(
        status in {"PARTIAL_CUTOVER_COMPONENT_MISSING", "LEGACY_ONLY_CLASS"}
        for status in eligible
    )
    if covered > 0 and missing > 0:
        return "PARTIAL_CUTOVER"
    if covered == 0 and eligible and all(status == "LEGACY_ONLY_CLASS" for status in eligible):
        return "LEGACY_ONLY"
    return "REQUIRES_REVIEW"


def summarize(component_rows: list[dict[str, Any]]) -> dict[str, Any]:
    component_counts = Counter(row["classification"] for row in component_rows)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in component_rows:
        grouped[(row["teacher_key"], row["class_key"])].append(row)
    group_counts = Counter(classify_group(rows) for rows in grouped.values())

    eligible_components = sum(
        count for status, count in component_counts.items() if status != "OUT_OF_DVD_SCOPE"
    )
    canonical_components = component_counts.get("CANONICAL_COVERED", 0)
    unresolved_components = eligible_components - canonical_components

    if unresolved_components == 0 and group_counts.get("REQUIRES_REVIEW", 0) == 0:
        classification = "GLOBAL_DVD_RECONCILIATION_CLEAN"
    elif group_counts.get("PARTIAL_CUTOVER", 0) > 0:
        classification = "GLOBAL_DVD_PARTIAL_CUTOVER_PRESENT"
    else:
        classification = "GLOBAL_DVD_RECONCILIATION_REQUIRED"

    return {
        "classification": classification,
        "component_classification_counts": {
            key: int(component_counts.get(key, 0)) for key in COMPONENT_CLASSIFICATIONS
        },
        "teacher_class_classification_counts": {
            key: int(group_counts.get(key, 0)) for key in GROUP_CLASSIFICATIONS
        },
        "active_legacy_component_pairs": len(component_rows),
        "dvd_eligible_component_pairs": eligible_components,
        "canonical_component_pairs": canonical_components,
        "unresolved_eligible_component_pairs": unresolved_components,
        "teacher_class_groups": len(grouped),
    }


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("P0_250_F2_8_MONGO_URL_MISSING")
    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]

    legacy_rows = list(db.teacher_assignments.find(
        {
            "academic_year": ACADEMIC_YEAR,
            "status": {"$in": list(ACTIVE_STATUSES)},
        },
        {"_id": 0, "staff_id": 1, "class_id": 1, "course_id": 1},
    ))

    legacy_pair_counts = Counter(
        (_sid(row.get("staff_id")), _sid(row.get("class_id")), _sid(row.get("course_id")))
        for row in legacy_rows
        if _sid(row.get("staff_id")) and _sid(row.get("class_id")) and _sid(row.get("course_id"))
    )

    staff_ids = sorted({key[0] for key in legacy_pair_counts})
    class_ids = sorted({key[1] for key in legacy_pair_counts})
    course_ids = sorted({key[2] for key in legacy_pair_counts})

    staff_by_id = {
        _sid(row.get("id")): row
        for row in db.staff.find(
            {"id": {"$in": staff_ids}},
            {"_id": 0, "id": 1, "user_id": 1, "email": 1, "mantenedora_id": 1},
        )
    }
    class_by_id = {
        _sid(row.get("id")): row
        for row in db.classes.find(
            {"id": {"$in": class_ids}},
            {
                "_id": 0,
                "id": 1,
                "school_id": 1,
                "mantenedora_id": 1,
                "education_level": 1,
                "nivel_ensino": 1,
                "grade_level": 1,
                "grade": 1,
                "atendimento_programa": 1,
            },
        )
    }

    # Course ids podem existir em mais de um tenant; indexamos por id e depois
    # exigimos match de tenant quando o documento o declarar.
    courses_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in db.courses.find(
        {"id": {"$in": course_ids}}, {"_id": 0, "id": 1, "mantenedora_id": 1}
    ):
        courses_by_id[_sid(row.get("id"))].append(row)

    resolved_user_by_staff: dict[str, dict[str, Any] | None] = {}
    school_scope_by_staff: dict[str, set[str]] = {}
    teacher_ids: set[str] = set()
    for staff_id in staff_ids:
        staff = staff_by_id.get(staff_id)
        if not staff:
            resolved_user_by_staff[staff_id] = None
            continue
        user = _resolve_user_for_staff(db, staff)
        resolved_user_by_staff[staff_id] = user
        if user:
            teacher_ids.add(_sid(user.get("id")))
            school_scope_by_staff[staff_id] = _school_ids_for_staff(db, staff, user)

    dvd_by_teacher_class: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    if teacher_ids:
        for row in db.teacher_class_assignments.find(
            {"teacher_id": {"$in": sorted(teacher_ids)}, "deleted": False},
            {
                "_id": 0,
                "teacher_id": 1,
                "class_id": 1,
                "component_id": 1,
                "school_id": 1,
                "mantenedora_id": 1,
                "deleted": 1,
                "valid_from": 1,
                "valid_until": 1,
                "diary_settings": 1,
            },
        ):
            dvd_by_teacher_class[(_sid(row.get("teacher_id")), _sid(row.get("class_id")))].append(row)

    component_rows: list[dict[str, Any]] = []
    tenant_keys: set[str] = set()

    for (staff_id, class_id, course_id), duplicate_count in sorted(legacy_pair_counts.items()):
        class_doc = class_by_id.get(class_id)
        staff = staff_by_id.get(staff_id)
        user = resolved_user_by_staff.get(staff_id)
        teacher_key = staff_id  # somente interno; não é emitido no snapshot final.
        class_key = class_id

        if not class_doc:
            classification = "TENANT_SCOPE_UNRESOLVED"
            invalid_reasons: Counter[str] = Counter({"CLASS_NOT_FOUND": 1})
        elif not is_class_in_scope(class_doc):
            classification = "OUT_OF_DVD_SCOPE"
            invalid_reasons = Counter()
        elif duplicate_count > 1:
            classification = "LEGACY_DUPLICATE"
            invalid_reasons = Counter()
        elif not staff or not user:
            classification = "IDENTITY_UNRESOLVED"
            invalid_reasons = Counter()
        elif not _role_is_professor(user):
            classification = "USER_ROLE_NOT_PROFESSOR"
            invalid_reasons = Counter()
        else:
            class_tenant = _sid(class_doc.get("mantenedora_id"))
            user_tenant = _sid(user.get("mantenedora_id"))
            class_school = _sid(class_doc.get("school_id"))
            if not class_tenant or not user_tenant or class_tenant != user_tenant:
                classification = "TENANT_SCOPE_UNRESOLVED"
                invalid_reasons = Counter()
            elif class_school not in school_scope_by_staff.get(staff_id, set()):
                classification = "SCHOOL_SCOPE_MISSING"
                invalid_reasons = Counter()
            else:
                course_docs = courses_by_id.get(course_id, [])
                tenant_courses = [
                    course for course in course_docs
                    if not _sid(course.get("mantenedora_id"))
                    or _sid(course.get("mantenedora_id")) == class_tenant
                ]
                if not tenant_courses:
                    classification = "COURSE_UNRESOLVED"
                    invalid_reasons = Counter()
                else:
                    tenant_keys.add(class_tenant)
                    teacher_id = _sid(user.get("id"))
                    class_dvd_rows = dvd_by_teacher_class.get((teacher_id, class_id), [])
                    covering = [
                        row for row in class_dvd_rows
                        if not _sid(row.get("component_id")) or _sid(row.get("component_id")) == course_id
                    ]
                    invalid_reasons = Counter()
                    valid_covering = []
                    for dvd_row in covering:
                        reason = _candidate_invalid_reason(
                            dvd_row,
                            class_doc=class_doc,
                            user=user,
                            school_ids=school_scope_by_staff.get(staff_id, set()),
                        )
                        if reason:
                            invalid_reasons[reason] += 1
                        else:
                            valid_covering.append(dvd_row)

                    valid_class_any = []
                    for dvd_row in class_dvd_rows:
                        reason = _candidate_invalid_reason(
                            dvd_row,
                            class_doc=class_doc,
                            user=user,
                            school_ids=school_scope_by_staff.get(staff_id, set()),
                        )
                        if reason is None:
                            valid_class_any.append(dvd_row)

                    if len(valid_covering) == 1:
                        classification = "CANONICAL_COVERED"
                    elif len(valid_covering) > 1:
                        classification = "DVD_DUPLICATE_COVERAGE"
                    elif covering:
                        classification = "DVD_PRESENT_INVALID"
                    elif valid_class_any:
                        classification = "PARTIAL_CUTOVER_COMPONENT_MISSING"
                    else:
                        classification = "LEGACY_ONLY_CLASS"

        component_rows.append({
            "teacher_key": teacher_key,
            "class_key": class_key,
            "classification": classification,
            "invalid_reason_counts": dict(invalid_reasons),
        })

    analysis = summarize(component_rows)
    invalid_reason_counts: Counter[str] = Counter()
    for row in component_rows:
        invalid_reason_counts.update(row.get("invalid_reason_counts") or {})
    analysis["invalid_dvd_reason_counts"] = dict(sorted(invalid_reason_counts.items()))
    analysis["tenant_count_with_eligible_active_allocations"] = len(tenant_keys)
    analysis["academic_year"] = ACADEMIC_YEAR
    analysis["reference_date"] = REFERENCE_DATE

    return {
        "schema": "P0_250_F2_8_GLOBAL_DVD_RECONCILIATION_AUDIT_V1",
        "status": "PASS",
        "classification": analysis["classification"],
        "database_mutation": False,
        "production_writes": False,
        "http_methods": [],
        "mongo_reads_only": True,
        "academic_data_read": False,
        "record_content_emitted": False,
        "record_ids_emitted": False,
        "assignment_ids_emitted": False,
        "teacher_ids_emitted": False,
        "staff_ids_emitted": False,
        "student_data_read": False,
        "student_pii_emitted": False,
        "user_pii_emitted": False,
        "analysis": analysis,
    }


if __name__ == "__main__":
    print(json.dumps(run_live_audit(), ensure_ascii=False, indent=2, sort_keys=True))
