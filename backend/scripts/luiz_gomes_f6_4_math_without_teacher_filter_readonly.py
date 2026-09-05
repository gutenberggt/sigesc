#!/usr/bin/env python3
"""LUIZ-GOMES-F6.4 — Matemática por turma/data sem filtro docente, read-only.

Hipótese: os conteúdos de Matemática de fevereiro a abril/2026 podem continuar
armazenados em 8º ANO A e/ou 9º ANO A, mas com autoria ausente, assignment
inconsistente ou ator diferente. A seleção primária NÃO usa professor.

Estratégia:
1. resolver escola e as duas turmas de 2026;
2. resolver TODAS as identidades de `courses` cujo nome normalizado é Matemática
   no tenant da escola;
3. ler somente metadados de `learning_objects` e `content_entries` das duas turmas;
4. restringir em memória ao período 2026-02-01 <= date < 2026-05-01 e às identidades
   de Matemática;
5. somente após a seleção, particionar a autoria/vínculo em Luiz, outro ator,
   assignment-only ou ausência completa de metadados de autoria.

Nenhum texto pedagógico, estudante, frequência, nota ou ID técnico é emitido.
Nenhuma mutação é executada.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
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
ACTOR_FIELDS = ("recorded_by", "created_by", "updated_by", "teacher_id", "staff_id")

ROW_PROJECTION = {
    "_id": 0,
    "id": 1,
    "class_id": 1,
    "course_id": 1,
    "component_id": 1,
    "date": 1,
    "academic_year": 1,
    "recorded_by": 1,
    "created_by": 1,
    "updated_by": 1,
    "teacher_id": 1,
    "staff_id": 1,
    "assignment_id": 1,
    "deleted": 1,
    "status": 1,
    "source": 1,
    "migration_source": 1,
    "legacy_id": 1,
    "aula_numero": 1,
    "version": 1,
    "mantenedora_id": 1,
}


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _sid(value))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.casefold().replace("º", "o").replace("ª", "a")
    return re.sub(r"\s+", " ", raw).strip()


def _iso_day(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = _sid(value)
    if len(raw) >= 10 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw[:10]):
        return raw[:10]
    return None


def _in_period(row: Mapping[str, Any]) -> bool:
    day = _iso_day(row.get("date"))
    return bool(day and START_DATE <= day < END_DATE)


def _component_id(row: Mapping[str, Any]) -> str:
    return _sid(row.get("course_id") or row.get("component_id"))


def _resolve_school(db) -> dict[str, Any]:
    rows = list(db.schools.find(
        {}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}
    ))
    matches = [r for r in rows if _norm(r.get("name")) == _norm(TARGET_SCHOOL)]
    if len(matches) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_4_SCHOOL_MATCHES:{len(matches)}")
    return matches[0]


def _resolve_classes(db, school_id: str, tenant_id: str) -> dict[str, str]:
    rows = list(db.classes.find(
        {"school_id": school_id},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1, "mantenedora_id": 1},
    ))
    rows = [r for r in rows if _sid(r.get("mantenedora_id")) in {"", tenant_id}]
    out: dict[str, str] = {}
    for class_name in TARGET_CLASSES:
        matches = [
            _sid(r.get("id")) for r in rows
            if _norm(r.get("name")) == _norm(class_name)
            and _sid(r.get("academic_year")) in {str(ACADEMIC_YEAR), ""}
            and _sid(r.get("id"))
        ]
        matches = sorted(set(matches))
        if len(matches) != 1:
            raise RuntimeError(f"LUIZ_GOMES_F6_4_CLASS_NOT_EXACT:{class_name}:{len(matches)}")
        out[class_name] = matches[0]
    return out


def _resolve_math_catalog(db, tenant_id: str) -> tuple[set[str], dict[str, str]]:
    rows = list(db.courses.find(
        {}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1, "nivel_ensino": 1}
    ))
    rows = [r for r in rows if _sid(r.get("mantenedora_id")) in {"", tenant_id}]
    by_id = {_sid(r.get("id")): _sid(r.get("name")) for r in rows if _sid(r.get("id"))}
    math_ids = {cid for cid, name in by_id.items() if _norm(name) == _norm(TARGET_COMPONENT)}
    if not math_ids:
        raise RuntimeError("LUIZ_GOMES_F6_4_NO_MATH_IDENTITIES")
    return math_ids, by_id


def _resolve_luiz_post_selection(db, school_id: str, tenant_id: str) -> tuple[set[str], set[str]]:
    """Resolve Luiz somente para classificar linhas já selecionadas, nunca para buscá-las."""
    users = list(db.users.find(
        {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
        {"_id": 0, "id": 1, "name": 1, "full_name": 1, "mantenedora_id": 1},
    ).limit(20))
    users = [u for u in users if _norm(u.get("full_name") or u.get("name")) == _norm(TEACHER_NAME)]
    if len(users) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_4_TEACHER_MATCHES:{len(users)}")
    teacher_id = _sid(users[0].get("id"))
    staff_rows = list(db.staff.find(
        {"user_id": teacher_id},
        {"_id": 0, "id": 1, "user_id": 1, "school_id": 1, "mantenedora_id": 1},
    ))
    staff_rows = [
        r for r in staff_rows
        if _sid(r.get("school_id")) in {"", school_id}
        and _sid(r.get("mantenedora_id")) in {"", tenant_id}
    ]
    actor_ids = {teacher_id, *(_sid(r.get("id")) for r in staff_rows)}
    actor_ids.discard("")

    staff_ids = sorted({_sid(r.get("id")) for r in staff_rows if _sid(r.get("id"))})
    legacy = list(db.teacher_assignments.find(
        {
            "staff_id": {"$in": staff_ids},
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        },
        {"_id": 0, "id": 1, "school_id": 1, "mantenedora_id": 1},
    )) if staff_ids else []
    legacy = [
        r for r in legacy
        if _sid(r.get("school_id")) in {"", school_id}
        and _sid(r.get("mantenedora_id")) in {"", tenant_id}
    ]
    dvd = list(db.teacher_class_assignments.find(
        {"teacher_id": teacher_id},
        {"_id": 0, "id": 1, "school_id": 1, "mantenedora_id": 1},
    ))
    dvd = [
        r for r in dvd
        if _sid(r.get("school_id")) in {"", school_id}
        and _sid(r.get("mantenedora_id")) in {"", tenant_id}
    ]
    assignment_ids = {_sid(r.get("id")) for r in legacy + dvd if _sid(r.get("id"))}
    return actor_ids, assignment_ids


def _actor_category(row: Mapping[str, Any], luiz_actor_ids: set[str], luiz_assignment_ids: set[str]) -> str:
    explicit = {_sid(row.get(field)) for field in ACTOR_FIELDS if _sid(row.get(field))}
    assignment = _sid(row.get("assignment_id"))
    has_luiz_explicit = bool(explicit & luiz_actor_ids)
    assignment_is_luiz = bool(assignment and assignment in luiz_assignment_ids)

    if has_luiz_explicit:
        return "LUIZ_EXPLICIT_ACTOR"
    if explicit and assignment_is_luiz:
        return "FOREIGN_EXPLICIT_ACTOR_WITH_LUIZ_ASSIGNMENT"
    if explicit:
        return "OTHER_EXPLICIT_ACTOR"
    if assignment_is_luiz:
        return "LUIZ_ASSIGNMENT_ONLY"
    if assignment:
        return "OTHER_OR_UNKNOWN_ASSIGNMENT_ONLY"
    return "NO_ACTOR_OR_ASSIGNMENT_METADATA"


def _status_category(row: Mapping[str, Any]) -> str:
    if row.get("deleted") is True:
        return "DELETED_TRUE"
    status = _norm(row.get("status"))
    return f"STATUS_{status.upper().replace(' ', '_')}" if status else "NO_STATUS"


def _summarize_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    luiz_actor_ids: set[str],
    luiz_assignment_ids: set[str],
    course_names: Mapping[str, str],
) -> dict[str, Any]:
    values = list(rows)
    actor = Counter(_actor_category(r, luiz_actor_ids, luiz_assignment_ids) for r in values)
    status = Counter(_status_category(r) for r in values)
    days = sorted({_iso_day(r.get("date")) for r in values if _iso_day(r.get("date"))})
    months = Counter(day[5:7] for day in (_iso_day(r.get("date")) for r in values) if day)
    course_names_used = Counter(course_names.get(_component_id(r), "<unresolved>") for r in values)
    return {
        "documents": len(values),
        "distinct_dates": len(days),
        "first_date": days[0] if days else None,
        "last_date": days[-1] if days else None,
        "months": {m: months.get(m, 0) for m in ("02", "03", "04")},
        "actor_partition": dict(sorted(actor.items())),
        "status_partition": dict(sorted(status.items())),
        "course_name_partition": dict(sorted(course_names_used.items())),
        "rows_without_any_actor_or_assignment": actor.get("NO_ACTOR_OR_ASSIGNMENT_METADATA", 0),
        "rows_with_luiz_explicit_actor": actor.get("LUIZ_EXPLICIT_ACTOR", 0),
        "rows_with_luiz_assignment_only": actor.get("LUIZ_ASSIGNMENT_ONLY", 0),
        "rows_with_other_explicit_actor": actor.get("OTHER_EXPLICIT_ACTOR", 0),
        "rows_deleted_true": status.get("DELETED_TRUE", 0),
    }


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("LUIZ_GOMES_F6_4_MONGO_URL_MISSING")
    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]

    school = _resolve_school(db)
    school_id = _sid(school.get("id"))
    tenant_id = _sid(school.get("mantenedora_id"))
    class_ids = _resolve_classes(db, school_id, tenant_id)
    math_ids, course_names = _resolve_math_catalog(db, tenant_id)

    # CRÍTICO: seleção por turma, data e identidade Matemática; nenhum filtro docente.
    selected: dict[str, dict[str, list[dict[str, Any]]]] = {}
    unresolved_component_counts: dict[str, dict[str, int]] = {}
    for class_name, class_id in class_ids.items():
        selected[class_name] = {}
        unresolved_component_counts[class_name] = {}
        for collection_name in ("learning_objects", "content_entries"):
            collection = db[collection_name]
            class_rows = list(collection.find({"class_id": class_id}, ROW_PROJECTION))
            period_rows = [r for r in class_rows if _in_period(r)]
            selected[class_name][collection_name] = [
                r for r in period_rows if _component_id(r) in math_ids
            ]
            unresolved_component_counts[class_name][collection_name] = sum(
                1 for r in period_rows
                if _component_id(r) and _component_id(r) not in course_names
            )

    # Autoria é resolvida somente DEPOIS da seleção acima.
    luiz_actor_ids, luiz_assignment_ids = _resolve_luiz_post_selection(db, school_id, tenant_id)

    targets = []
    overall = Counter()
    for class_name in TARGET_CLASSES:
        lo_rows = selected[class_name]["learning_objects"]
        ce_rows = selected[class_name]["content_entries"]
        lo = _summarize_rows(
            lo_rows,
            luiz_actor_ids=luiz_actor_ids,
            luiz_assignment_ids=luiz_assignment_ids,
            course_names=course_names,
        )
        ce = _summarize_rows(
            ce_rows,
            luiz_actor_ids=luiz_actor_ids,
            luiz_assignment_ids=luiz_assignment_ids,
            course_names=course_names,
        )
        total = lo["documents"] + ce["documents"]
        unbound = lo["rows_without_any_actor_or_assignment"] + ce["rows_without_any_actor_or_assignment"]
        deleted = lo["rows_deleted_true"] + ce["rows_deleted_true"]
        luiz = (
            lo["rows_with_luiz_explicit_actor"] + lo["rows_with_luiz_assignment_only"]
            + ce["rows_with_luiz_explicit_actor"] + ce["rows_with_luiz_assignment_only"]
        )
        codes: list[str] = []
        if total == 0:
            codes.append("NO_MATH_RECORDS_FOUND_WITHOUT_TEACHER_FILTER")
        else:
            codes.append("MATH_RECORDS_FOUND_WITHOUT_TEACHER_FILTER")
        if unbound:
            codes.append("MATH_RECORDS_WITHOUT_ACTOR_OR_ASSIGNMENT_CONFIRMED")
        if deleted:
            codes.append("MATH_RECORDS_SOFT_DELETED_PRESENT")
        if luiz:
            codes.append("MATH_RECORDS_POSTSELECT_ATTRIBUTABLE_TO_LUIZ")
        if total and not unbound and not luiz:
            codes.append("MATH_RECORDS_PRESENT_BUT_NOT_POSTSELECT_ATTRIBUTABLE_TO_LUIZ")
        unresolved = unresolved_component_counts[class_name]
        if unresolved.get("learning_objects", 0) or unresolved.get("content_entries", 0):
            codes.append("UNRESOLVED_COMPONENT_ROWS_EXIST_IN_PERIOD")
        for code in codes:
            overall[code] += 1
        targets.append({
            "class": class_name,
            "classification": codes,
            "learning_objects": lo,
            "content_entries": ce,
            "unresolved_component_rows_in_period": unresolved,
        })

    return {
        "schema": "LUIZ_GOMES_F6_4_MATH_WITHOUT_TEACHER_FILTER_READ_ONLY_V1",
        "status": "PASS",
        "academic_year": ACADEMIC_YEAR,
        "period": {"start": START_DATE, "end_exclusive": END_DATE},
        "school": TARGET_SCHOOL,
        "component": TARGET_COMPONENT,
        "selection_teacher_filter_used": False,
        "post_selection_actor_resolution_used": True,
        "math_catalog_identity_count": len(math_ids),
        "targets": targets,
        "summary": {"classification_counts": dict(sorted(overall.items()))},
        "mongo_reads_only": True,
        "database_mutation": False,
        "production_writes": False,
        "pedagogical_plaintext_read": False,
        "pedagogical_plaintext_emitted": False,
        "attendance_read": False,
        "attendance_records_read": False,
        "student_data_read": False,
        "grades_read": False,
        "technical_ids_emitted": False,
    }


if __name__ == "__main__":
    print("LUIZ_GOMES_F6_4_JSON=" + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True))
