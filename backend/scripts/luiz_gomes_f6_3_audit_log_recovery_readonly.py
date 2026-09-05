#!/usr/bin/env python3
"""LUIZ-GOMES-F6.3 — recuperação forense por audit_logs, read-only.

Objetivo:
- verificar se os logs canônicos preservam evidência histórica de que Luiz Gomes
  registrou conteúdo para Matemática no 8º ANO A e 9º ANO A em fev-abr/2026;
- usar somente metadados de auditoria (ator, turma, componente, data, ação);
- não ler nem emitir conteúdo pedagógico, alunos, frequência detalhada, notas ou PII.

Esta fase NÃO restaura dados. Ela apenas classifica a força probatória dos logs.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
import re
import unicodedata
from typing import Any, Mapping

from pymongo import MongoClient

ACADEMIC_YEAR = 2026
TEACHER_NAME = "Luiz Gomes dos Santos"
TARGET_SCHOOL = "E M E I E F Jose Pereira Barbosa"
TARGET_COMPONENT = "Matemática"
TARGET_CLASSES = ("8º ANO A", "9º ANO A")
START_DATE = "2026-02-01"
END_DATE = "2026-05-01"
ACTIVE_STATUSES = {"ativo", "active"}
CONTENT_COLLECTIONS = ("content_entries", "learning_objects")

AUDIT_PROJECTION = {
    "_id": 0,
    "action": 1,
    "collection": 1,
    "document_id": 1,
    "user_id": 1,
    "school_id": 1,
    "academic_year": 1,
    "timestamp": 1,
    "timestamp_utc": 1,
    "description": 1,
    "extra_data.entity_type": 1,
    "extra_data.entity_scope": 1,
    "extra_data.class_id": 1,
    "extra_data.class_name": 1,
    "extra_data.date": 1,
    "extra_data.course_id": 1,
    "extra_data.component_id": 1,
    "extra_data.assignment_id": 1,
    "extra_data.teacher_id": 1,
    "extra_data.teacher_name": 1,
    "extra_data.aula_numero": 1,
    "extra_data.change_kind": 1,
    "extra_data.final_version": 1,
    "extra_data.status_at_change": 1,
    "new_value.date": 1,
    "new_value.class_id": 1,
    "new_value.course_id": 1,
    "new_value.component_id": 1,
    "old_value.date": 1,
    "old_value.class_id": 1,
    "old_value.course_id": 1,
    "old_value.component_id": 1,
}

FORBIDDEN_AUDIT_FIELDS = {
    "content",
    "previous_content",
    "new_content",
    "methodology",
    "observations",
    "resources",
}


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _sid(value))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.casefold().replace("º", "o").replace("ª", "a")
    return re.sub(r"\s+", " ", raw).strip()


def _fp(value: Any) -> str | None:
    raw = _sid(value)
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _valid_lesson_date(value: Any) -> str | None:
    raw = _sid(value)[:10]
    if re.fullmatch(r"2026-(02|03|04)-\d{2}", raw):
        return raw
    return None


def _lesson_date_from_log(log: Mapping[str, Any]) -> tuple[str | None, str | None]:
    extra = log.get("extra_data") or {}
    new_value = log.get("new_value") or {}
    old_value = log.get("old_value") or {}
    candidates = (
        ("extra_data.date", extra.get("date")),
        ("new_value.date", new_value.get("date")),
        ("old_value.date", old_value.get("date")),
    )
    for source, value in candidates:
        parsed = _valid_lesson_date(value)
        if parsed:
            return parsed, source

    description = _sid(log.get("description"))
    match = re.search(r"\b(2026-(?:02|03|04)-\d{2})\b", description)
    if match:
        return match.group(1), "description"
    return None, None


def _month_counts(events: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(
        _sid(event.get("lesson_date"))[5:7]
        for event in events
        if _sid(event.get("lesson_date"))
    )
    return {month: counts.get(month, 0) for month in ("02", "03", "04")}


def _resolve_teacher(db) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    users = list(
        db.users.find(
            {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
            {"_id": 0, "id": 1, "name": 1, "full_name": 1, "mantenedora_id": 1},
        ).limit(20)
    )
    users = [
        user for user in users
        if _norm(user.get("full_name") or user.get("name")) == _norm(TEACHER_NAME)
    ]
    if len(users) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_3_TEACHER_USER_MATCHES:{len(users)}")
    user = users[0]
    staff_rows = list(
        db.staff.find(
            {"user_id": _sid(user.get("id"))},
            {"_id": 0, "id": 1, "user_id": 1, "school_id": 1, "mantenedora_id": 1},
        ).limit(50)
    )
    if not staff_rows:
        raise RuntimeError("LUIZ_GOMES_F6_3_STAFF_NOT_FOUND")
    return user, staff_rows


def _resolve_school(db, user: Mapping[str, Any], staff_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    matches = [
        row
        for row in db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1})
        if _norm(row.get("name")) == _norm(TARGET_SCHOOL)
    ]
    tenant_hints = {
        _sid(user.get("mantenedora_id")),
        *(_sid(row.get("mantenedora_id")) for row in staff_rows),
    }
    tenant_hints.discard("")
    if len(matches) > 1 and tenant_hints:
        matches = [row for row in matches if _sid(row.get("mantenedora_id")) in tenant_hints]
    if len(matches) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_3_SCHOOL_MATCHES:{len(matches)}")
    return matches[0]


def _catalog(db, school_id: str, tenant_id: str):
    classes = list(
        db.classes.find(
            {"school_id": school_id},
            {"_id": 0, "id": 1, "name": 1, "academic_year": 1, "mantenedora_id": 1},
        )
    )
    classes = [row for row in classes if _sid(row.get("mantenedora_id")) in {"", tenant_id}]
    class_by_id = {_sid(row.get("id")): row for row in classes if _sid(row.get("id"))}

    courses = list(
        db.courses.find(
            {},
            {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1},
        )
    )
    courses = [row for row in courses if _sid(row.get("mantenedora_id")) in {"", tenant_id}]
    course_by_id = {_sid(row.get("id")): row for row in courses if _sid(row.get("id"))}
    return class_by_id, course_by_id


def _resolve_target_classes(class_by_id: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    result = {}
    for class_name in TARGET_CLASSES:
        matches = [
            class_id
            for class_id, row in class_by_id.items()
            if _norm(row.get("name")) == _norm(class_name)
            and _sid(row.get("academic_year")) in {"", str(ACADEMIC_YEAR)}
        ]
        if len(matches) != 1:
            raise RuntimeError(f"LUIZ_GOMES_F6_3_CLASS_NOT_EXACT:{class_name}:{len(matches)}")
        result[class_name] = matches[0]
    return result


def _current_math_by_class(
    db,
    staff_ids: set[str],
    target_classes: Mapping[str, str],
    course_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, set[str]]:
    rows = list(
        db.teacher_assignments.find(
            {
                "staff_id": {"$in": sorted(staff_ids)},
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            },
            {"_id": 0, "class_id": 1, "course_id": 1, "status": 1},
        )
    )
    result = {name: set() for name in TARGET_CLASSES}
    reverse = {class_id: name for name, class_id in target_classes.items()}
    for row in rows:
        if _norm(row.get("status")) not in ACTIVE_STATUSES:
            continue
        class_name = reverse.get(_sid(row.get("class_id")))
        if not class_name:
            continue
        course_id = _sid(row.get("course_id"))
        if course_id and _norm((course_by_id.get(course_id) or {}).get("name")) == _norm(TARGET_COMPONENT):
            result[class_name].add(course_id)
    for class_name, course_ids in result.items():
        if len(course_ids) != 1:
            raise RuntimeError(
                f"LUIZ_GOMES_F6_3_CURRENT_MATH_NOT_EXACT:{class_name}:{len(course_ids)}"
            )
    return result


def _event_context(
    log: Mapping[str, Any],
    *,
    target_classes: Mapping[str, str],
    course_by_id: Mapping[str, Mapping[str, Any]],
    math_by_class: Mapping[str, set[str]],
    teacher_user_id: str,
) -> dict[str, Any] | None:
    lesson_date, date_source = _lesson_date_from_log(log)
    if not lesson_date:
        return None

    extra = log.get("extra_data") or {}
    new_value = log.get("new_value") or {}
    old_value = log.get("old_value") or {}

    class_id = _sid(extra.get("class_id") or new_value.get("class_id") or old_value.get("class_id"))
    class_name_hint = _sid(extra.get("class_name"))
    class_name = None
    for name, expected_class_id in target_classes.items():
        if class_id and class_id == expected_class_id:
            class_name = name
            break
        if class_name_hint and _norm(class_name_hint) == _norm(name):
            class_name = name
            break
    if not class_name:
        normalized_description = _norm(log.get("description"))
        for name in TARGET_CLASSES:
            if _norm(name) in normalized_description:
                class_name = name
                break
    if not class_name:
        return None

    course_id = _sid(
        extra.get("component_id")
        or extra.get("course_id")
        or new_value.get("component_id")
        or new_value.get("course_id")
        or old_value.get("component_id")
        or old_value.get("course_id")
    )
    course_name = _sid((course_by_id.get(course_id) or {}).get("name")) if course_id else None
    math_match = bool(course_id and course_id in math_by_class[class_name])

    teacher_id = _sid(extra.get("teacher_id"))
    teacher_name = _sid(extra.get("teacher_name"))
    teacher_context_match = (
        (not teacher_id and not teacher_name)
        or (teacher_id and teacher_id == teacher_user_id)
        or (_norm(teacher_name) == _norm(TEACHER_NAME))
    )

    change_kind = _sid(extra.get("change_kind"))
    action = _sid(log.get("action"))
    if math_match and teacher_context_match:
        evidence_strength = "STRONG_MATH_CONTEXT"
    elif teacher_context_match:
        evidence_strength = "TARGET_CLASS_CONTENT_BY_LUIZ"
    else:
        evidence_strength = "CONFLICTING_TEACHER_CONTEXT"

    return {
        "class": class_name,
        "lesson_date": lesson_date,
        "lesson_date_source": date_source,
        "month": lesson_date[5:7],
        "action": action,
        "collection": _sid(log.get("collection")),
        "change_kind": change_kind or None,
        "course_name": course_name or None,
        "course_fingerprint": _fp(course_id),
        "math_component_match": math_match,
        "teacher_context_match": teacher_context_match,
        "evidence_strength": evidence_strength,
        "logged_at_date": _sid(log.get("timestamp_utc") or log.get("timestamp"))[:10] or None,
        "aula_numero": extra.get("aula_numero"),
        "final_version": extra.get("final_version"),
        "status_at_change": extra.get("status_at_change"),
    }


def _classify(events: list[Mapping[str, Any]]) -> list[str]:
    strong = [event for event in events if event.get("evidence_strength") == "STRONG_MATH_CONTEXT"]
    creates = [
        event
        for event in strong
        if event.get("action") == "create" or event.get("change_kind") == "content_created"
    ]
    if creates:
        return ["AUDIT_LOG_MATH_REGISTRATION_CONFIRMED"]
    if strong:
        return ["AUDIT_LOG_MATH_CONTENT_ACTIVITY_CONFIRMED_WITHOUT_CREATE"]
    if events:
        return ["AUDIT_LOG_TARGET_CLASS_CONTENT_ACTIVITY_ONLY"]
    return ["NO_AUDIT_LOG_EVIDENCE_FOR_TARGET_PERIOD"]


def run_live_audit() -> dict[str, Any]:
    uri = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "sigesc")
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    db = client[db_name]

    user, staff_rows = _resolve_teacher(db)
    school = _resolve_school(db, user, staff_rows)
    tenant_id = _sid(school.get("mantenedora_id") or user.get("mantenedora_id"))
    if not tenant_id:
        raise RuntimeError("LUIZ_GOMES_F6_3_TENANT_NOT_FOUND")

    class_by_id, course_by_id = _catalog(db, _sid(school.get("id")), tenant_id)
    target_classes = _resolve_target_classes(class_by_id)
    staff_ids = {_sid(row.get("id")) for row in staff_rows if _sid(row.get("id"))}
    math_by_class = _current_math_by_class(db, staff_ids, target_classes, course_by_id)

    teacher_id = _sid(user.get("id"))
    audit_rows = list(
        db.audit_logs.find(
            {
                "user_id": teacher_id,
                "collection": {"$in": list(CONTENT_COLLECTIONS)},
            },
            AUDIT_PROJECTION,
        ).sort("timestamp", 1)
    )

    contexts = []
    for log in audit_rows:
        context = _event_context(
            log,
            target_classes=target_classes,
            course_by_id=course_by_id,
            math_by_class=math_by_class,
            teacher_user_id=teacher_id,
        )
        if context:
            contexts.append(context)

    targets = []
    for class_name in TARGET_CLASSES:
        events = [event for event in contexts if event.get("class") == class_name]
        strong = [event for event in events if event.get("evidence_strength") == "STRONG_MATH_CONTEXT"]
        distinct_dates = sorted({event["lesson_date"] for event in strong})
        targets.append(
            {
                "class": class_name,
                "classification": _classify(events),
                "audit_events_in_target_period": len(events),
                "strong_math_events": len(strong),
                "strong_math_distinct_dates": len(distinct_dates),
                "strong_math_months": _month_counts(strong),
                "strong_math_dates": distinct_dates,
                "event_action_counts": dict(Counter(event.get("action") for event in events)),
                "change_kind_counts": dict(
                    Counter(event.get("change_kind") or "<none>" for event in events)
                ),
                "events": events,
            }
        )

    result = {
        "schema": "LUIZ_GOMES_F6_3_AUDIT_LOG_RECOVERY_READ_ONLY_V1",
        "academic_year": ACADEMIC_YEAR,
        "period": {"from": START_DATE, "to_exclusive": END_DATE},
        "teacher": TEACHER_NAME,
        "school": TARGET_SCHOOL,
        "component": TARGET_COMPONENT,
        "audit_rows_for_luiz_content_collections": len(audit_rows),
        "targets": targets,
        "summary": {
            "classification_counts": dict(
                Counter(code for target in targets for code in target["classification"])
            ),
            "strong_math_events_total": sum(target["strong_math_events"] for target in targets),
            "strong_math_distinct_dates_total": sum(
                target["strong_math_distinct_dates"] for target in targets
            ),
        },
        "database_mutation": False,
        "production_writes": False,
        "mongo_reads_only": True,
        "http_methods": [],
        "attendance_records_read": False,
        "student_data_read": False,
        "student_pii_emitted": False,
        "pedagogical_plaintext_read": False,
        "pedagogical_plaintext_emitted": False,
        "technical_ids_emitted": False,
        "audit_descriptions_read": True,
    }
    client.close()
    return result


if __name__ == "__main__":
    print(
        "LUIZ_GOMES_F6_3_JSON="
        + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True)
    )
