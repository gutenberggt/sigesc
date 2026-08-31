#!/usr/bin/env python3
"""P0 #250 F2.9A — planner/dry-run global de reconciliação docente/DVD.

Esta fase transforma o inventário F2.8 em um plano determinístico, porém NÃO
executa backfill. O planner:
- lê somente metadados estruturais;
- nunca remapeia componente por nome;
- usa turma/tenant/escola como âncoras;
- só propõe criação quando identidade, cobertura e template canônico são
  unívocos;
- envia qualquer ambiguidade para REQUIRES_REVIEW;
- emite somente contagens e hashes do plano, nunca IDs/PII.

O executor de escrita é deliberadamente inexistente nesta fase.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date
from typing import Any, Iterable, Mapping

from pymongo import MongoClient

from services.diary_assignment_access import (
    DiaryAssignmentAccessError,
    effective_diary_settings,
    is_assignment_active_on,
)
from services.diary_assignment_contract import is_class_in_scope
from services.teacher_class_assignment_semantics import (
    LEGACY_MIGRATION_DRIFT,
    OPERATIONAL_DVD,
    classify_teacher_class_assignment,
)

ACADEMIC_YEAR = int(os.environ.get("P0_250_F2_9A_ACADEMIC_YEAR", "2026"))
REFERENCE_DATE = os.environ.get(
    "P0_250_F2_9A_REFERENCE_DATE", date.today().isoformat()
)[:10]
ACTIVE_STATUSES = ("ativo", "active")
PLAN_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://sigesc.aprenderdigital.top/p0/250/f2.9a/dvd-reconciliation",
)
ALLOWED_DIARY_SETTING_KEYS = frozenset(
    {"enabled", "schema_version", "profile", "student_scope"}
)

DECISIONS = (
    "NOOP_ALREADY_CANONICAL",
    "PLAN_CREATE_CANONICAL_ASSIGNMENT",
    "NOOP_OUT_OF_DVD_SCOPE",
    "REQUIRES_REVIEW",
)

REVIEW_REASONS = (
    "CLASS_NOT_FOUND",
    "CLASS_YEAR_MISMATCH",
    "LEGACY_DUPLICATE",
    "IDENTITY_UNRESOLVED",
    "USER_ROLE_NOT_PROFESSOR",
    "TENANT_SCOPE_UNRESOLVED",
    "SCHOOL_SCOPE_MISSING",
    "LEGACY_SCHOOL_MISMATCH",
    "LEGACY_TENANT_MISMATCH",
    "COURSE_UNRESOLVED",
    "COURSE_AMBIGUOUS",
    "LEGACY_MIGRATION_DRIFT",
    "DVD_DUPLICATE_COVERAGE",
    "DVD_PRESENT_INVALID",
    "NO_CANONICAL_TEMPLATE",
    "AMBIGUOUS_CANONICAL_TEMPLATE",
    "UNSUPPORTED_TEMPLATE_FIELDS",
    "TARGET_ID_COLLISION",
)

GROUP_STATES = (
    "ALREADY_CANONICAL",
    "PLAN_READY",
    "REQUIRES_REVIEW",
    "OUT_OF_DVD_SCOPE",
)


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _role_is_professor(user: Mapping[str, Any]) -> bool:
    return _sid(user.get("role")) == "professor"


def _school_ids_for_staff(
    db,
    staff: Mapping[str, Any],
    user: Mapping[str, Any],
) -> set[str]:
    school_ids = {
        _sid(value)
        for value in (user.get("school_ids") or [])
        if _sid(value)
    }
    for link in user.get("school_links") or []:
        if not isinstance(link, Mapping):
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


def _resolve_user_for_staff(
    db,
    staff: Mapping[str, Any],
) -> dict[str, Any] | None:
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
            user_id = _sid(user.get("id"))
            if user_id:
                seen[user_id] = user

    if len(seen) != 1:
        return None
    return next(iter(seen.values()))


def _candidate_invalid_reason(
    row: Mapping[str, Any],
    *,
    class_doc: Mapping[str, Any],
    user: Mapping[str, Any],
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


def _normalized_diary_settings(
    row: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    raw = row.get("diary_settings")
    if not isinstance(raw, Mapping):
        return None, "UNSUPPORTED_TEMPLATE_FIELDS"
    if set(raw.keys()) - ALLOWED_DIARY_SETTING_KEYS:
        return None, "UNSUPPORTED_TEMPLATE_FIELDS"

    try:
        settings = effective_diary_settings(row)
    except DiaryAssignmentAccessError:
        return None, "UNSUPPORTED_TEMPLATE_FIELDS"
    if not settings.enabled:
        return None, "UNSUPPORTED_TEMPLATE_FIELDS"

    return {
        "enabled": True,
        "schema_version": settings.schema_version,
        "profile": settings.profile.value,
        "student_scope": settings.student_scope.value,
    }, None


def _template_envelope(
    row: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    diary_settings, error = _normalized_diary_settings(row)
    if error:
        return None, error

    valid_from = _sid(row.get("valid_from"))
    if not valid_from:
        return None, "UNSUPPORTED_TEMPLATE_FIELDS"

    valid_until_raw = row.get("valid_until")
    valid_until = _sid(valid_until_raw) or None
    if valid_until is not None and valid_until < valid_from:
        return None, "UNSUPPORTED_TEMPLATE_FIELDS"

    shift = _sid(row.get("shift")) or None

    return {
        "valid_from": valid_from,
        "valid_until": valid_until,
        "diary_settings": diary_settings,
        "is_substitute": bool(row.get("is_substitute")),
        "grades_official_owner": bool(row.get("grades_official_owner")),
        "shift": shift,
    }, None


def derive_unique_template(
    valid_class_rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    rows = list(valid_class_rows)
    if not rows:
        return None, "NO_CANONICAL_TEMPLATE"

    envelopes: dict[str, dict[str, Any]] = {}
    for row in rows:
        envelope, error = _template_envelope(row)
        if error:
            return None, error
        assert envelope is not None
        envelopes[_sha256_value(envelope)] = envelope

    if len(envelopes) != 1:
        return None, "AMBIGUOUS_CANONICAL_TEMPLATE"
    return deepcopy(next(iter(envelopes.values()))), None


def deterministic_assignment_id(
    *,
    tenant_id: str,
    school_id: str,
    teacher_id: str,
    class_id: str,
    component_id: str,
    academic_year: int,
) -> str:
    natural_key = "|".join(
        [
            str(academic_year),
            tenant_id,
            school_id,
            teacher_id,
            class_id,
            component_id,
        ]
    )
    return str(uuid.uuid5(PLAN_NAMESPACE, natural_key))


def build_target_assignment(
    *,
    tenant_id: str,
    school_id: str,
    teacher_id: str,
    class_id: str,
    component_id: str,
    academic_year: int,
    template: Mapping[str, Any],
) -> dict[str, Any]:
    target = {
        "id": deterministic_assignment_id(
            tenant_id=tenant_id,
            school_id=school_id,
            teacher_id=teacher_id,
            class_id=class_id,
            component_id=component_id,
            academic_year=academic_year,
        ),
        "teacher_id": teacher_id,
        "class_id": class_id,
        "component_id": component_id,
        "school_id": school_id,
        "mantenedora_id": tenant_id,
        "deleted": False,
        "valid_from": template.get("valid_from"),
        "valid_until": template.get("valid_until"),
        "diary_settings": deepcopy(template.get("diary_settings")),
        "is_substitute": bool(template.get("is_substitute")),
        "grades_official_owner": bool(template.get("grades_official_owner")),
    }
    if template.get("shift"):
        target["shift"] = template.get("shift")
    return target


def group_state(rows: Iterable[Mapping[str, Any]]) -> str:
    decisions = [row.get("decision") for row in rows]
    if not decisions:
        return "REQUIRES_REVIEW"
    if "REQUIRES_REVIEW" in decisions:
        return "REQUIRES_REVIEW"
    if "PLAN_CREATE_CANONICAL_ASSIGNMENT" in decisions:
        return "PLAN_READY"
    if all(decision == "NOOP_OUT_OF_DVD_SCOPE" for decision in decisions):
        return "OUT_OF_DVD_SCOPE"
    return "ALREADY_CANONICAL"


def summarize_decisions(
    decision_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    decision_counts = Counter(row["decision"] for row in decision_rows)
    review_reason_counts: Counter[str] = Counter()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in decision_rows:
        grouped[(row["teacher_key"], row["class_key"])].append(row)
        review_reason_counts.update(row.get("review_reasons") or [])

    group_counts = Counter(group_state(rows) for rows in grouped.values())

    plan_count = decision_counts.get("PLAN_CREATE_CANONICAL_ASSIGNMENT", 0)
    review_count = decision_counts.get("REQUIRES_REVIEW", 0)

    if plan_count and review_count:
        classification = "GLOBAL_DVD_RECONCILIATION_PLAN_PARTIAL_REVIEW_REQUIRED"
    elif plan_count:
        classification = "GLOBAL_DVD_RECONCILIATION_PLAN_READY"
    elif review_count:
        classification = "GLOBAL_DVD_RECONCILIATION_PLAN_REVIEW_ONLY"
    else:
        classification = "GLOBAL_DVD_RECONCILIATION_PLAN_CLEAN"

    return {
        "classification": classification,
        "decision_counts": {
            key: int(decision_counts.get(key, 0)) for key in DECISIONS
        },
        "review_reason_counts": {
            key: int(review_reason_counts.get(key, 0)) for key in REVIEW_REASONS
        },
        "teacher_class_state_counts": {
            key: int(group_counts.get(key, 0)) for key in GROUP_STATES
        },
        "active_legacy_component_pairs": len(decision_rows),
        "plan_create_count": int(plan_count),
        "review_count": int(review_count),
        "teacher_class_groups": len(grouped),
        "plan_complete_without_review": review_count == 0,
    }


def _decision_manifest_rows(
    decision_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for row in decision_rows:
        item = {
            "teacher_key": row["teacher_key"],
            "class_key": row["class_key"],
            "component_key": row["component_key"],
            "decision": row["decision"],
            "review_reasons": sorted(row.get("review_reasons") or []),
        }
        if row.get("target_assignment"):
            item["target_assignment"] = row["target_assignment"]
        result.append(item)
    result.sort(
        key=lambda item: (
            item["teacher_key"],
            item["class_key"],
            item["component_key"],
            item["decision"],
        )
    )
    return result


def _input_state_rows(
    *,
    legacy_rows: Iterable[Mapping[str, Any]],
    dvd_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in legacy_rows:
        rows.append(
            {
                "kind": "legacy",
                "staff_id": _sid(row.get("staff_id")),
                "class_id": _sid(row.get("class_id")),
                "course_id": _sid(row.get("course_id")),
                "school_id": _sid(row.get("school_id")) or None,
                "mantenedora_id": _sid(row.get("mantenedora_id")) or None,
                "academic_year": row.get("academic_year"),
                "status": _sid(row.get("status")),
            }
        )
    for row in dvd_rows:
        rows.append(
            {
                "kind": "dvd",
                "id": _sid(row.get("id")),
                "teacher_id": _sid(row.get("teacher_id")) or None,
                "class_id": _sid(row.get("class_id")),
                "component_id": _sid(row.get("component_id")) or None,
                "school_id": _sid(row.get("school_id")) or None,
                "mantenedora_id": _sid(row.get("mantenedora_id")) or None,
                "deleted": bool(row.get("deleted")),
                "valid_from": row.get("valid_from"),
                "valid_until": row.get("valid_until"),
                "diary_settings": row.get("diary_settings"),
                "is_substitute": bool(row.get("is_substitute")),
                "grades_official_owner": bool(row.get("grades_official_owner")),
                "shift": _sid(row.get("shift")) or None,
                "source": _sid(row.get("source")) or None,
                "migrated_from_legacy": row.get("migrated_from_legacy"),
                "synthetic_validity": row.get("synthetic_validity"),
                "created_by": _sid(row.get("created_by")) or None,
            }
        )
    rows.sort(key=_canonical_json_bytes)
    return rows


def run_live_plan() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("P0_250_F2_9A_MONGO_URL_MISSING")

    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]

    legacy_rows = list(
        db.teacher_assignments.find(
            {
                "academic_year": ACADEMIC_YEAR,
                "status": {"$in": list(ACTIVE_STATUSES)},
            },
            {
                "_id": 0,
                "staff_id": 1,
                "class_id": 1,
                "course_id": 1,
                "school_id": 1,
                "mantenedora_id": 1,
                "academic_year": 1,
                "status": 1,
            },
        )
    )

    legacy_pair_rows: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in legacy_rows:
        key = (
            _sid(row.get("staff_id")),
            _sid(row.get("class_id")),
            _sid(row.get("course_id")),
        )
        if all(key):
            legacy_pair_rows[key].append(row)

    staff_ids = sorted({key[0] for key in legacy_pair_rows})
    class_ids = sorted({key[1] for key in legacy_pair_rows})
    course_ids = sorted({key[2] for key in legacy_pair_rows})

    staff_by_id = {
        _sid(row.get("id")): row
        for row in db.staff.find(
            {"id": {"$in": staff_ids}},
            {
                "_id": 0,
                "id": 1,
                "user_id": 1,
                "email": 1,
                "mantenedora_id": 1,
                "cargo": 1,
                "status": 1,
            },
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
                "academic_year": 1,
                "education_level": 1,
                "nivel_ensino": 1,
                "grade_level": 1,
                "grade": 1,
                "atendimento_programa": 1,
            },
        )
    }

    courses_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in db.courses.find(
        {"id": {"$in": course_ids}},
        {"_id": 0, "id": 1, "mantenedora_id": 1},
    ):
        courses_by_id[_sid(row.get("id"))].append(row)

    resolved_user_by_staff: dict[str, dict[str, Any] | None] = {}
    school_scope_by_staff: dict[str, set[str]] = {}
    resolved_teacher_ids: set[str] = set()

    for staff_id in staff_ids:
        staff = staff_by_id.get(staff_id)
        if not staff:
            resolved_user_by_staff[staff_id] = None
            continue
        user = _resolve_user_for_staff(db, staff)
        resolved_user_by_staff[staff_id] = user
        if user:
            teacher_id = _sid(user.get("id"))
            if teacher_id:
                resolved_teacher_ids.add(teacher_id)
            school_scope_by_staff[staff_id] = _school_ids_for_staff(db, staff, user)

    # Busca todos os rows das turmas-alvo para poder separar DVD operacional
    # de artefatos legacy_migration e detectar drift sem confundir staff.id com user.id.
    dvd_rows = list(
        db.teacher_class_assignments.find(
            {"class_id": {"$in": class_ids}},
            {
                "_id": 0,
                "id": 1,
                "teacher_id": 1,
                "class_id": 1,
                "component_id": 1,
                "school_id": 1,
                "mantenedora_id": 1,
                "deleted": 1,
                "valid_from": 1,
                "valid_until": 1,
                "diary_settings": 1,
                "is_substitute": 1,
                "grades_official_owner": 1,
                "shift": 1,
                "source": 1,
                "migrated_from_legacy": 1,
                "synthetic_validity": 1,
                "created_by": 1,
            },
        )
    )

    operational_by_teacher_class: dict[
        tuple[str, str], list[dict[str, Any]]
    ] = defaultdict(list)
    drift_by_class_component: dict[
        tuple[str, str], list[dict[str, Any]]
    ] = defaultdict(list)

    for row in dvd_rows:
        semantic = classify_teacher_class_assignment(row)
        if semantic.kind == OPERATIONAL_DVD:
            teacher_id = _sid(row.get("teacher_id"))
            class_id = _sid(row.get("class_id"))
            if teacher_id in resolved_teacher_ids and class_id:
                operational_by_teacher_class[(teacher_id, class_id)].append(row)
        elif semantic.kind == LEGACY_MIGRATION_DRIFT and row.get("deleted") is not True:
            class_id = _sid(row.get("class_id"))
            component_id = _sid(row.get("component_id"))
            if class_id:
                drift_by_class_component[(class_id, component_id)].append(row)

    decision_rows: list[dict[str, Any]] = []
    planned_target_ids: dict[str, tuple[str, str, str]] = {}
    dvd_by_id = {
        _sid(row.get("id")): row
        for row in dvd_rows
        if _sid(row.get("id"))
    }

    for (staff_id, class_id, course_id), pair_docs in sorted(legacy_pair_rows.items()):
        base_row: dict[str, Any] = {
            "teacher_key": staff_id,
            "class_key": class_id,
            "component_key": course_id,
            "decision": None,
            "review_reasons": [],
            "target_assignment": None,
        }
        class_doc = class_by_id.get(class_id)
        staff = staff_by_id.get(staff_id)
        user = resolved_user_by_staff.get(staff_id)

        def review(*reasons: str) -> None:
            base_row["decision"] = "REQUIRES_REVIEW"
            base_row["review_reasons"] = sorted(set(reasons))

        if len(pair_docs) != 1:
            review("LEGACY_DUPLICATE")
            decision_rows.append(base_row)
            continue

        legacy = pair_docs[0]
        if not class_doc:
            review("CLASS_NOT_FOUND")
            decision_rows.append(base_row)
            continue

        class_year = class_doc.get("academic_year")
        if class_year is not None and str(class_year) != str(ACADEMIC_YEAR):
            review("CLASS_YEAR_MISMATCH")
            decision_rows.append(base_row)
            continue

        if not is_class_in_scope(class_doc):
            base_row["decision"] = "NOOP_OUT_OF_DVD_SCOPE"
            decision_rows.append(base_row)
            continue

        if not staff or not user:
            review("IDENTITY_UNRESOLVED")
            decision_rows.append(base_row)
            continue

        if not _role_is_professor(user):
            review("USER_ROLE_NOT_PROFESSOR")
            decision_rows.append(base_row)
            continue

        class_tenant = _sid(class_doc.get("mantenedora_id"))
        class_school = _sid(class_doc.get("school_id"))
        user_tenant = _sid(user.get("mantenedora_id"))
        if not class_tenant or not user_tenant or class_tenant != user_tenant:
            review("TENANT_SCOPE_UNRESOLVED")
            decision_rows.append(base_row)
            continue

        if not class_school or class_school not in school_scope_by_staff.get(staff_id, set()):
            review("SCHOOL_SCOPE_MISSING")
            decision_rows.append(base_row)
            continue

        legacy_school = _sid(legacy.get("school_id"))
        if legacy_school and legacy_school != class_school:
            review("LEGACY_SCHOOL_MISMATCH")
            decision_rows.append(base_row)
            continue

        legacy_tenant = _sid(legacy.get("mantenedora_id"))
        if legacy_tenant and legacy_tenant != class_tenant:
            review("LEGACY_TENANT_MISMATCH")
            decision_rows.append(base_row)
            continue

        compatible_courses = [
            course
            for course in courses_by_id.get(course_id, [])
            if not _sid(course.get("mantenedora_id"))
            or _sid(course.get("mantenedora_id")) == class_tenant
        ]
        if not compatible_courses:
            review("COURSE_UNRESOLVED")
            decision_rows.append(base_row)
            continue
        if len(compatible_courses) != 1:
            review("COURSE_AMBIGUOUS")
            decision_rows.append(base_row)
            continue

        # Drift de legacy_migration no mesmo componente (ou class-wide) bloqueia
        # criação automática: não reinterpretamos artefato sintético como DVD.
        if drift_by_class_component.get((class_id, "")) or drift_by_class_component.get(
            (class_id, course_id)
        ):
            review("LEGACY_MIGRATION_DRIFT")
            decision_rows.append(base_row)
            continue

        teacher_id = _sid(user.get("id"))
        class_dvd_rows = [
            row
            for row in operational_by_teacher_class.get((teacher_id, class_id), [])
            if row.get("deleted") is not True
        ]

        covering = [
            row
            for row in class_dvd_rows
            if not _sid(row.get("component_id"))
            or _sid(row.get("component_id")) == course_id
        ]

        valid_covering: list[dict[str, Any]] = []
        for row in covering:
            if (
                _candidate_invalid_reason(
                    row,
                    class_doc=class_doc,
                    user=user,
                    school_ids=school_scope_by_staff.get(staff_id, set()),
                )
                is None
            ):
                valid_covering.append(row)

        if len(valid_covering) == 1:
            base_row["decision"] = "NOOP_ALREADY_CANONICAL"
            decision_rows.append(base_row)
            continue
        if len(valid_covering) > 1:
            review("DVD_DUPLICATE_COVERAGE")
            decision_rows.append(base_row)
            continue
        if covering:
            review("DVD_PRESENT_INVALID")
            decision_rows.append(base_row)
            continue

        valid_class_rows: list[dict[str, Any]] = []
        for row in class_dvd_rows:
            if (
                _candidate_invalid_reason(
                    row,
                    class_doc=class_doc,
                    user=user,
                    school_ids=school_scope_by_staff.get(staff_id, set()),
                )
                is None
            ):
                valid_class_rows.append(row)

        template, template_error = derive_unique_template(valid_class_rows)
        if template_error:
            review(template_error)
            decision_rows.append(base_row)
            continue
        assert template is not None

        target = build_target_assignment(
            tenant_id=class_tenant,
            school_id=class_school,
            teacher_id=teacher_id,
            class_id=class_id,
            component_id=course_id,
            academic_year=ACADEMIC_YEAR,
            template=template,
        )
        target_id = target["id"]
        natural = (teacher_id, class_id, course_id)
        previous = planned_target_ids.get(target_id)
        if previous and previous != natural:
            review("TARGET_ID_COLLISION")
            decision_rows.append(base_row)
            continue

        if target_id in dvd_by_id:
            # Se a mesma natural key existisse, ela já teria entrado em covering.
            review("TARGET_ID_COLLISION")
            decision_rows.append(base_row)
            continue

        planned_target_ids[target_id] = natural
        base_row["decision"] = "PLAN_CREATE_CANONICAL_ASSIGNMENT"
        base_row["target_assignment"] = target
        decision_rows.append(base_row)

    analysis = summarize_decisions(decision_rows)
    decision_manifest = _decision_manifest_rows(decision_rows)
    planned_payloads = [
        row["target_assignment"]
        for row in decision_manifest
        if row.get("target_assignment")
    ]

    analysis["plan_sha256"] = _sha256_value(planned_payloads)
    analysis["decision_manifest_sha256"] = _sha256_value(decision_manifest)
    analysis["input_state_sha256"] = _sha256_value(
        _input_state_rows(legacy_rows=legacy_rows, dvd_rows=dvd_rows)
    )
    analysis["academic_year"] = ACADEMIC_YEAR
    analysis["reference_date"] = REFERENCE_DATE
    analysis["plan_namespace_sha256"] = hashlib.sha256(
        str(PLAN_NAMESPACE).encode("ascii")
    ).hexdigest()
    analysis["automatic_apply_authorized"] = False

    return {
        "schema": "P0_250_F2_9A_GLOBAL_DVD_RECONCILIATION_PLAN_V1",
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
        "plan_payload_emitted": False,
        "plan_digest_emitted": True,
        "analysis": analysis,
    }


if __name__ == "__main__":
    print(json.dumps(run_live_plan(), ensure_ascii=False, indent=2, sort_keys=True))
