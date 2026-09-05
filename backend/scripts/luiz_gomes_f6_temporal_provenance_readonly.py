#!/usr/bin/env python3
"""LUIZ-GOMES-F6 — proveniência temporal read-only de conteúdos históricos.

Escopo fixo:
- Luiz Gomes dos Santos;
- E M E I E F Jose Pereira Barbosa;
- Matemática / 8º ANO A e 9º ANO A;
- 2026-02-01 <= date < 2026-05-01.

Objetivo: localizar metadados de conteúdos históricos que não aparecem na
consulta corrente, sem ler qualquer texto pedagógico ou dado de estudante.

A auditoria considera:
- identidade corrente de turma/componente;
- identidades alternativas de turma com o mesmo nome na mesma escola/tenant;
- identidades catalogadas de mesmo nome do componente;
- course_id/component_id ausente, não catalogado ou divergente;
- learning_objects e content_entries;
- registros atribuíveis ao professor fora das identidades de turma conhecidas.

Boundary: MongoDB somente leitura; nenhuma chamada HTTP; nenhuma leitura de
attendance.records; nenhum texto pedagógico; nenhum ID técnico bruto emitido.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
import re
import unicodedata
from typing import Any, Iterable, Mapping

from pymongo import MongoClient

ACADEMIC_YEAR = 2026
TEACHER_NAME = "Luiz Gomes dos Santos"
TARGET_SCHOOL = "E M E I E F Jose Pereira Barbosa"
TARGET_COMPONENT = "Matemática"
TARGET_CLASSES = ("8º ANO A", "9º ANO A")
START_DATE = "2026-02-01"
END_DATE = "2026-05-01"
ACTIVE_STATUSES = ("ativo", "active")

SAFE_CONTENT_PROJECTION = {
    "_id": 0,
    "id": 1,
    "class_id": 1,
    "course_id": 1,
    "component_id": 1,
    "assignment_id": 1,
    "date": 1,
    "academic_year": 1,
    "mantenedora_id": 1,
    "recorded_by": 1,
    "created_by": 1,
    "updated_by": 1,
    "teacher_id": 1,
    "staff_id": 1,
    "copied_from_id": 1,
    "deleted": 1,
    "created_at": 1,
    "updated_at": 1,
}
FORBIDDEN_CONTENT_FIELDS = {
    "content", "description", "object", "objects", "objectives", "skills",
    "habilidades", "conteudo", "conteúdo", "observations", "notes",
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


def _month(value: Any) -> str | None:
    raw = _sid(value)[:10]
    match = re.fullmatch(r"2026-(0[2-4])-\d{2}", raw)
    return match.group(1) if match else None


def _record_course_id(row: Mapping[str, Any]) -> str:
    return _sid(row.get("course_id") or row.get("component_id"))


def _teacher_attributed(
    row: Mapping[str, Any],
    *,
    actor_ids: set[str],
    assignment_ids: set[str],
) -> bool:
    for field in ("recorded_by", "created_by", "updated_by", "teacher_id", "staff_id"):
        value = _sid(row.get(field))
        if value and value in actor_ids:
            return True
    assignment_id = _sid(row.get("assignment_id"))
    return bool(assignment_id and assignment_id in assignment_ids)


def _date_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(rows)
    dates = sorted({_sid(row.get("date"))[:10] for row in values if _sid(row.get("date"))})
    months: Counter[str] = Counter()
    for row in values:
        month = _month(row.get("date"))
        if month:
            months[month] += 1
    return {
        "documents": len(values),
        "distinct_dates": len(dates),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "months": {key: months.get(key, 0) for key in ("02", "03", "04")},
    }


def _resolve_teacher(db) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    users = list(db.users.find(
        {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
        {"_id": 0, "id": 1, "name": 1, "full_name": 1, "role": 1, "mantenedora_id": 1},
    ).limit(10))
    users = [
        row for row in users
        if _norm(row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)
    ]
    if len(users) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_TEACHER_USER_MATCHES:{len(users)}")
    user = users[0]
    user_id = _sid(user.get("id"))
    staff_rows = list(db.staff.find(
        {"user_id": user_id},
        {"_id": 0, "id": 1, "user_id": 1, "mantenedora_id": 1},
    ).limit(20))
    if not staff_rows:
        raise RuntimeError("LUIZ_GOMES_F6_STAFF_NOT_FOUND")
    return user, staff_rows


def _resolve_school(db, *, user: Mapping[str, Any], staff_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    schools = list(db.schools.find(
        {},
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    ))
    matches = [row for row in schools if _norm(row.get("name")) == _norm(TARGET_SCHOOL)]
    tenant_hints = {_sid(user.get("mantenedora_id"))}
    tenant_hints.update(_sid(row.get("mantenedora_id")) for row in staff_rows)
    tenant_hints.discard("")
    if len(matches) > 1 and tenant_hints:
        scoped = [row for row in matches if _sid(row.get("mantenedora_id")) in tenant_hints]
        if scoped:
            matches = scoped
    if len(matches) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_SCHOOL_MATCHES:{len(matches)}")
    school = matches[0]
    if not _sid(school.get("id")) or not _sid(school.get("mantenedora_id")):
        raise RuntimeError("LUIZ_GOMES_F6_SCHOOL_SCOPE_MISSING")
    return school


def _assignment_inventory(db, *, staff_ids: set[str], school_id: str, tenant_id: str) -> dict[str, Any]:
    legacy = list(db.teacher_assignments.find(
        {
            "staff_id": {"$in": sorted(staff_ids)},
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "status": {"$in": list(ACTIVE_STATUSES)},
        },
        {
            "_id": 0, "id": 1, "staff_id": 1, "class_id": 1, "course_id": 1,
            "school_id": 1, "mantenedora_id": 1, "academic_year": 1, "status": 1,
        },
    ))
    legacy = [
        row for row in legacy
        if _sid(row.get("school_id")) in {"", school_id}
        and _sid(row.get("mantenedora_id")) in {"", tenant_id}
    ]
    canonical = list(db.teacher_class_assignments.find(
        {
            "staff_id": {"$in": sorted(staff_ids)},
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        },
        {
            "_id": 0, "id": 1, "staff_id": 1, "class_id": 1, "component_id": 1,
            "course_id": 1, "school_id": 1, "mantenedora_id": 1,
            "academic_year": 1, "deleted": 1,
        },
    ))
    canonical = [
        row for row in canonical
        if row.get("deleted") is not True
        and _sid(row.get("school_id")) in {"", school_id}
        and _sid(row.get("mantenedora_id")) in {"", tenant_id}
    ]
    assignment_ids = {
        _sid(row.get("id")) for row in legacy + canonical if _sid(row.get("id"))
    }
    return {"legacy": legacy, "canonical": canonical, "assignment_ids": assignment_ids}


def _catalog_inventory(db, *, school_id: str, tenant_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    classes = list(db.classes.find(
        {"school_id": school_id},
        {
            "_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1,
            "academic_year": 1, "education_level": 1, "nivel_ensino": 1, "grade_level": 1,
        },
    ))
    classes = [
        row for row in classes
        if _sid(row.get("mantenedora_id")) in {"", tenant_id}
    ]
    courses = list(db.courses.find(
        {},
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1, "nivel_ensino": 1},
    ))
    courses = [
        row for row in courses
        if _sid(row.get("mantenedora_id")) in {"", tenant_id}
        and _norm(row.get("name")) == _norm(TARGET_COMPONENT)
    ]
    return classes, courses


def _resolve_current_targets(
    *,
    legacy_assignments: list[Mapping[str, Any]],
    classes: list[Mapping[str, Any]],
    courses: list[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    class_by_id = {_sid(row.get("id")): row for row in classes if _sid(row.get("id"))}
    course_by_id = {_sid(row.get("id")): row for row in courses if _sid(row.get("id"))}
    out: dict[str, dict[str, Any]] = {}
    for target_name in TARGET_CLASSES:
        candidates = []
        for row in legacy_assignments:
            class_doc = class_by_id.get(_sid(row.get("class_id")))
            course_doc = course_by_id.get(_sid(row.get("course_id")))
            if not class_doc or not course_doc:
                continue
            if _norm(class_doc.get("name")) != _norm(target_name):
                continue
            if _norm(course_doc.get("name")) != _norm(TARGET_COMPONENT):
                continue
            candidates.append((row, class_doc, course_doc))
        if len(candidates) != 1:
            raise RuntimeError(f"LUIZ_GOMES_F6_CURRENT_TARGET_NOT_EXACT:{target_name}:{len(candidates)}")
        assignment, class_doc, course_doc = candidates[0]
        out[target_name] = {
            "class_id": _sid(class_doc.get("id")),
            "course_id": _sid(course_doc.get("id")),
            "assignment_id": _sid(assignment.get("id")),
        }
    return out


def _read_store_rows(
    db,
    *,
    store: str,
    relevant_class_ids: set[str],
    actor_ids: set[str],
    assignment_ids: set[str],
) -> list[dict[str, Any]]:
    selectors: list[dict[str, Any]] = []
    if relevant_class_ids:
        selectors.append({"class_id": {"$in": sorted(relevant_class_ids)}})
    for field in ("recorded_by", "created_by", "updated_by", "teacher_id", "staff_id"):
        if actor_ids:
            selectors.append({field: {"$in": sorted(actor_ids)}})
    if assignment_ids:
        selectors.append({"assignment_id": {"$in": sorted(assignment_ids)}})
    if not selectors:
        return []
    return list(db[store].find(
        {
            "$and": [
                {"date": {"$gte": START_DATE, "$lt": END_DATE}},
                {"$or": selectors},
            ]
        },
        SAFE_CONTENT_PROJECTION,
    ))


def _course_role(course_id: str, *, current_course_id: str, same_name_course_ids: set[str], all_course_ids: set[str]) -> str:
    if not course_id:
        return "MISSING_COURSE_ID"
    if course_id == current_course_id:
        return "CURRENT_COURSE"
    if course_id in same_name_course_ids:
        return "ALTERNATE_SAME_NAME_COURSE"
    if course_id in all_course_ids:
        return "OTHER_CATALOG_COURSE"
    return "UNRESOLVED_COURSE_ID"


def _class_role(class_id: str, *, current_class_id: str, same_name_class_ids: set[str], all_class_ids: set[str]) -> str:
    if not class_id:
        return "MISSING_CLASS_ID"
    if class_id == current_class_id:
        return "CURRENT_CLASS"
    if class_id in same_name_class_ids:
        return "ALTERNATE_SAME_NAME_CLASS"
    if class_id in all_class_ids:
        return "OTHER_CATALOG_CLASS"
    return "UNRESOLVED_CLASS_ID"


def classify_target(
    *,
    target_name: str,
    current_class_id: str,
    current_course_id: str,
    same_name_class_ids: set[str],
    same_name_course_ids: set[str],
    all_class_ids: set[str],
    all_course_ids: set[str],
    actor_ids: set[str],
    assignment_ids: set[str],
    store_rows: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    categories: dict[str, Counter[str]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    teacher_unresolved_class_rows: list[Mapping[str, Any]] = []

    for store, rows in store_rows.items():
        counter: Counter[str] = Counter()
        target_rows: list[Mapping[str, Any]] = []
        for row in rows:
            class_id = _sid(row.get("class_id"))
            course_id = _record_course_id(row)
            class_role = _class_role(
                class_id,
                current_class_id=current_class_id,
                same_name_class_ids=same_name_class_ids,
                all_class_ids=all_class_ids,
            )
            course_role = _course_role(
                course_id,
                current_course_id=current_course_id,
                same_name_course_ids=same_name_course_ids,
                all_course_ids=all_course_ids,
            )
            attributed = _teacher_attributed(row, actor_ids=actor_ids, assignment_ids=assignment_ids)
            if class_id in same_name_class_ids:
                key = f"{class_role}/{course_role}/{'TEACHER' if attributed else 'UNATTRIBUTED'}"
                counter[key] += 1
                target_rows.append(row)
            elif attributed and class_role in {"UNRESOLVED_CLASS_ID", "MISSING_CLASS_ID"}:
                teacher_unresolved_class_rows.append(row)
        categories[store] = counter
        summaries[store] = _date_summary(target_rows)

    learning_categories = categories.get("learning_objects", Counter())
    canonical_categories = categories.get("content_entries", Counter())

    def _has(counter: Counter[str], *tokens: str) -> bool:
        return any(count > 0 and all(token in key for token in tokens) for key, count in counter.items())

    codes: list[str] = []
    if _has(learning_categories, "CURRENT_CLASS", "CURRENT_COURSE"):
        codes.append("CURRENT_PATH_HAS_HISTORICAL_CONTENT")
    if (
        _has(learning_categories, "CURRENT_CLASS", "ALTERNATE_SAME_NAME_COURSE")
        or _has(learning_categories, "CURRENT_CLASS", "UNRESOLVED_COURSE_ID")
        or _has(learning_categories, "CURRENT_CLASS", "MISSING_COURSE_ID")
        or _has(learning_categories, "CURRENT_CLASS", "OTHER_CATALOG_COURSE")
    ):
        codes.append("HISTORICAL_CONTENT_COURSE_BINDING_ANOMALY_CONFIRMED")
    if _has(learning_categories, "ALTERNATE_SAME_NAME_CLASS"):
        codes.append("HISTORICAL_CONTENT_CLASS_IDENTITY_SPLIT_CONFIRMED")
    if sum(canonical_categories.values()) > 0:
        codes.append("HISTORICAL_CONTENT_IN_CANONICAL_STORE_CONFIRMED")
    if teacher_unresolved_class_rows:
        codes.append("HISTORICAL_CONTENT_POSSIBLE_UNRESOLVED_CLASS_BINDING")
    if not codes:
        codes.append("HISTORICAL_CONTENT_NOT_FOUND_LIVE_STORES")

    return {
        "class": target_name,
        "classification": codes,
        "stores": {
            store: {
                "summary": summaries[store],
                "categories": dict(sorted(categories[store].items())),
            }
            for store in sorted(store_rows)
        },
        "teacher_attributed_unresolved_class_rows": _date_summary(teacher_unresolved_class_rows),
    }


def run_live_audit() -> dict[str, Any]:
    if FORBIDDEN_CONTENT_FIELDS.intersection(SAFE_CONTENT_PROJECTION):
        raise RuntimeError("LUIZ_GOMES_F6_UNSAFE_PROJECTION")

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("LUIZ_GOMES_F6_MONGO_URL_MISSING")
    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]

    user, staff_rows = _resolve_teacher(db)
    school = _resolve_school(db, user=user, staff_rows=staff_rows)
    school_id = _sid(school.get("id"))
    tenant_id = _sid(school.get("mantenedora_id"))
    staff_ids = {_sid(row.get("id")) for row in staff_rows if _sid(row.get("id"))}
    actor_ids = set(staff_ids)
    actor_ids.add(_sid(user.get("id")))
    actor_ids.discard("")

    assignments = _assignment_inventory(
        db, staff_ids=staff_ids, school_id=school_id, tenant_id=tenant_id
    )
    classes, same_name_courses = _catalog_inventory(
        db, school_id=school_id, tenant_id=tenant_id
    )
    current_targets = _resolve_current_targets(
        legacy_assignments=assignments["legacy"],
        classes=classes,
        courses=same_name_courses,
    )

    all_course_docs = list(db.courses.find(
        {},
        {"_id": 0, "id": 1, "mantenedora_id": 1},
    ))
    all_course_ids = {
        _sid(row.get("id")) for row in all_course_docs
        if _sid(row.get("id"))
        and _sid(row.get("mantenedora_id")) in {"", tenant_id}
    }
    same_name_course_ids = {_sid(row.get("id")) for row in same_name_courses if _sid(row.get("id"))}
    all_class_ids = {_sid(row.get("id")) for row in classes if _sid(row.get("id"))}

    same_name_classes: dict[str, list[dict[str, Any]]] = {}
    relevant_class_ids: set[str] = set()
    for target_name in TARGET_CLASSES:
        matches = [row for row in classes if _norm(row.get("name")) == _norm(target_name)]
        same_name_classes[target_name] = matches
        relevant_class_ids.update(_sid(row.get("id")) for row in matches if _sid(row.get("id")))

    store_rows = {
        store: _read_store_rows(
            db,
            store=store,
            relevant_class_ids=relevant_class_ids,
            actor_ids=actor_ids,
            assignment_ids=assignments["assignment_ids"],
        )
        for store in ("learning_objects", "content_entries")
    }

    targets_out = []
    for target_name in TARGET_CLASSES:
        current = current_targets[target_name]
        same_class_ids = {
            _sid(row.get("id")) for row in same_name_classes[target_name] if _sid(row.get("id"))
        }
        classified = classify_target(
            target_name=target_name,
            current_class_id=current["class_id"],
            current_course_id=current["course_id"],
            same_name_class_ids=same_class_ids,
            same_name_course_ids=same_name_course_ids,
            all_class_ids=all_class_ids,
            all_course_ids=all_course_ids,
            actor_ids=actor_ids,
            assignment_ids=assignments["assignment_ids"],
            store_rows=store_rows,
        )
        classified["class_identity_inventory"] = {
            "same_name_in_school": len(same_class_ids),
            "current_class_fingerprint": _fp(current["class_id"]),
            "same_name_class_fingerprints": sorted(
                _fp(value) for value in same_class_ids if _fp(value)
            ),
            "academic_year_values": sorted({
                _sid(row.get("academic_year")) or "missing"
                for row in same_name_classes[target_name]
            }),
        }
        classified["course_identity_inventory"] = {
            "same_name_in_tenant": len(same_name_course_ids),
            "current_course_fingerprint": _fp(current["course_id"]),
            "same_name_course_fingerprints": sorted(
                _fp(value) for value in same_name_course_ids if _fp(value)
            ),
        }
        targets_out.append(classified)

    classification_counts: Counter[str] = Counter(
        code for target in targets_out for code in target["classification"]
    )
    return {
        "schema": "LUIZ_GOMES_F6_TEMPORAL_PROVENANCE_READ_ONLY_V1",
        "status": "PASS",
        "academic_year": ACADEMIC_YEAR,
        "period": {"start": START_DATE, "end_exclusive": END_DATE},
        "teacher": TEACHER_NAME,
        "school": TARGET_SCHOOL,
        "component": TARGET_COMPONENT,
        "target_pair_count": len(TARGET_CLASSES),
        "targets": targets_out,
        "summary": {
            "classification_counts": dict(sorted(classification_counts.items())),
            "same_name_math_identities_in_tenant": len(same_name_course_ids),
            "learning_objects_metadata_rows_scanned": len(store_rows["learning_objects"]),
            "content_entries_metadata_rows_scanned": len(store_rows["content_entries"]),
        },
        "mongo_reads_only": True,
        "http_methods": [],
        "database_mutation": False,
        "production_writes": False,
        "attendance_records_read": False,
        "student_data_read": False,
        "student_pii_emitted": False,
        "pedagogical_text_read": False,
        "technical_ids_emitted": False,
    }


if __name__ == "__main__":
    print("LUIZ_GOMES_F6_JSON=" + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True))
