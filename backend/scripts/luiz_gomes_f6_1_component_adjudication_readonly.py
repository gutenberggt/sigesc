#!/usr/bin/env python3
"""LUIZ-GOMES-F6.1 — adjudicação read-only do componente histórico.

Escopo fixo:
- Luiz Gomes dos Santos;
- E M E I E F Jose Pereira Barbosa;
- 8º ANO A e 9º ANO A;
- 2026-02-01 <= date < 2026-05-01.

A F6 confirmou que há 111/98 learning_objects nas turmas atuais, porém sob
componentes catalogados diferentes de Matemática. Esta etapa identifica os
componentes candidatos e cruza somente metadados com:
- teacher_assignments do Luiz em 2026, inclusive inativos;
- teacher_class_assignments históricos/atuais;
- datas de frequência de Matemática atribuíveis ao Luiz, sem attendance.records.

Nenhum texto pedagógico, estudante, matrícula, nota ou ID técnico bruto é lido
ou emitido. MongoDB é estritamente read-only.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
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
ACTIVE_STATUSES = {"ativo", "active"}

LEARNING_PROJECTION = {
    "_id": 0,
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
}
ATTENDANCE_PROJECTION = {
    "_id": 0,
    "class_id": 1,
    "course_id": 1,
    "date": 1,
    "academic_year": 1,
    "recorded_by": 1,
    "created_by": 1,
    "updated_by": 1,
    "teacher_id": 1,
    "staff_id": 1,
    "assignment_id": 1,
}
FORBIDDEN_FIELDS = {
    "records", "content", "description", "object", "objects", "objectives",
    "skills", "habilidades", "conteudo", "conteúdo", "observations", "notes",
    "old_value", "new_value",
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


def _date(value: Any) -> str | None:
    raw = _sid(value)[:10]
    return raw if re.fullmatch(r"2026-(0[2-4])-\d{2}", raw) else None


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


def _summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(rows)
    dates = sorted({_date(row.get("date")) for row in values if _date(row.get("date"))})
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
        "months": {month: months.get(month, 0) for month in ("02", "03", "04")},
    }


def _safe_dateish(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    raw = _sid(value)
    return raw[:32] if raw else None


def _resolve_teacher(db) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    users = list(db.users.find(
        {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
        {"_id": 0, "id": 1, "name": 1, "full_name": 1, "mantenedora_id": 1},
    ).limit(20))
    users = [
        row for row in users
        if _norm(row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)
    ]
    if len(users) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_1_TEACHER_USER_MATCHES:{len(users)}")
    user = users[0]
    user_id = _sid(user.get("id"))
    staff_rows = list(db.staff.find(
        {"user_id": user_id},
        {"_id": 0, "id": 1, "user_id": 1, "mantenedora_id": 1, "school_id": 1},
    ).limit(50))
    if not staff_rows:
        raise RuntimeError("LUIZ_GOMES_F6_1_STAFF_NOT_FOUND")
    return user, staff_rows


def _resolve_school(db, *, user: Mapping[str, Any], staff_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    matches = [
        row for row in db.schools.find(
            {}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}
        )
        if _norm(row.get("name")) == _norm(TARGET_SCHOOL)
    ]
    tenant_hints = {_sid(user.get("mantenedora_id"))}
    tenant_hints.update(_sid(row.get("mantenedora_id")) for row in staff_rows)
    tenant_hints.discard("")
    if len(matches) > 1 and tenant_hints:
        scoped = [row for row in matches if _sid(row.get("mantenedora_id")) in tenant_hints]
        if scoped:
            matches = scoped
    if len(matches) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_1_SCHOOL_MATCHES:{len(matches)}")
    school = matches[0]
    if not _sid(school.get("id")) or not _sid(school.get("mantenedora_id")):
        raise RuntimeError("LUIZ_GOMES_F6_1_SCHOOL_SCOPE_MISSING")
    return school


def _catalog(db, *, school_id: str, tenant_id: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    classes = list(db.classes.find(
        {"school_id": school_id},
        {"_id": 0, "id": 1, "name": 1, "academic_year": 1, "mantenedora_id": 1},
    ))
    classes = [row for row in classes if _sid(row.get("mantenedora_id")) in {"", tenant_id}]
    class_by_id = {_sid(row.get("id")): row for row in classes if _sid(row.get("id"))}

    courses = list(db.courses.find(
        {},
        {
            "_id": 0, "id": 1, "name": 1, "nivel_ensino": 1,
            "mantenedora_id": 1, "created_at": 1, "updated_at": 1,
        },
    ))
    courses = [row for row in courses if _sid(row.get("mantenedora_id")) in {"", tenant_id}]
    course_by_id = {_sid(row.get("id")): row for row in courses if _sid(row.get("id"))}
    return class_by_id, course_by_id


def _teacher_history(
    db,
    *,
    teacher_id: str,
    staff_ids: set[str],
    school_id: str,
    tenant_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    legacy = list(db.teacher_assignments.find(
        {
            "staff_id": {"$in": sorted(staff_ids)},
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        },
        {
            "_id": 0, "id": 1, "staff_id": 1, "school_id": 1, "class_id": 1,
            "course_id": 1, "academic_year": 1, "status": 1, "mantenedora_id": 1,
            "created_at": 1, "updated_at": 1,
        },
    ))
    legacy = [
        row for row in legacy
        if _sid(row.get("school_id")) in {"", school_id}
        and _sid(row.get("mantenedora_id")) in {"", tenant_id}
    ]

    dvd = list(db.teacher_class_assignments.find(
        {"teacher_id": teacher_id},
        {
            "_id": 0, "id": 1, "teacher_id": 1, "class_id": 1,
            "component_id": 1, "course_id": 1, "school_id": 1,
            "mantenedora_id": 1, "valid_from": 1, "valid_until": 1,
            "deleted": 1, "created_at": 1, "updated_at": 1,
        },
    ))
    dvd = [
        row for row in dvd
        if _sid(row.get("school_id")) in {"", school_id}
        and _sid(row.get("mantenedora_id")) in {"", tenant_id}
    ]
    assignment_ids = {
        _sid(row.get("id")) for row in legacy + dvd if _sid(row.get("id"))
    }
    return legacy, dvd, assignment_ids


def _resolve_target_classes(
    *, class_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, str]:
    out: dict[str, str] = {}
    for target_name in TARGET_CLASSES:
        matches = [
            cid for cid, row in class_by_id.items()
            if _norm(row.get("name")) == _norm(target_name)
            and _sid(row.get("academic_year")) in {"", str(ACADEMIC_YEAR)}
        ]
        if len(matches) != 1:
            raise RuntimeError(f"LUIZ_GOMES_F6_1_CLASS_NOT_EXACT:{target_name}:{len(matches)}")
        out[target_name] = matches[0]
    return out


def _resolve_current_math_course(
    *,
    class_id: str,
    legacy: list[Mapping[str, Any]],
    course_by_id: Mapping[str, Mapping[str, Any]],
) -> str:
    active = []
    for row in legacy:
        if _sid(row.get("class_id")) != class_id:
            continue
        course_id = _sid(row.get("course_id"))
        course = course_by_id.get(course_id)
        if not course or _norm(course.get("name")) != _norm(TARGET_COMPONENT):
            continue
        if _norm(row.get("status")) not in ACTIVE_STATUSES:
            continue
        active.append(course_id)
    unique = sorted(set(active))
    if len(unique) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_1_CURRENT_MATH_NOT_EXACT:{_fp(class_id)}:{len(unique)}")
    return unique[0]


def _history_for_course(
    rows: Iterable[Mapping[str, Any]], *, class_id: str, course_id: str, component_field: str
) -> dict[str, Any]:
    matches = [
        row for row in rows
        if _sid(row.get("class_id")) == class_id
        and _sid(row.get(component_field) or row.get("course_id")) == course_id
    ]
    statuses = sorted({_sid(row.get("status")) or "missing" for row in matches})
    return {
        "count": len(matches),
        "statuses": statuses,
        "deleted_values": sorted({str(bool(row.get("deleted"))) for row in matches}) if matches else [],
        "valid_from_values": sorted({value for row in matches if (value := _safe_dateish(row.get("valid_from")))}),
        "valid_until_values": sorted({value for row in matches if (value := _safe_dateish(row.get("valid_until")))}),
        "created_at_values": sorted({value for row in matches if (value := _safe_dateish(row.get("created_at")))}),
        "updated_at_values": sorted({value for row in matches if (value := _safe_dateish(row.get("updated_at")))}),
    }


def adjudicate_class(
    *,
    class_name: str,
    class_id: str,
    current_math_course_id: str,
    learning_rows: list[Mapping[str, Any]],
    math_attendance_rows: list[Mapping[str, Any]],
    legacy_history: list[Mapping[str, Any]],
    dvd_history: list[Mapping[str, Any]],
    course_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    by_course: dict[str, list[Mapping[str, Any]]] = {}
    for row in learning_rows:
        course_id = _record_course_id(row)
        if not course_id:
            course_id = "<missing>"
        by_course.setdefault(course_id, []).append(row)

    math_dates = {
        date for row in math_attendance_rows if (date := _date(row.get("date")))
    }
    candidates: list[dict[str, Any]] = []
    for course_id, rows in by_course.items():
        if course_id == current_math_course_id:
            continue
        course = course_by_id.get(course_id) if course_id != "<missing>" else None
        dates = {date for row in rows if (date := _date(row.get("date")))}
        overlap = sorted(dates & math_dates)
        legacy = _history_for_course(
            legacy_history, class_id=class_id, course_id=course_id, component_field="course_id"
        ) if course_id != "<missing>" else {"count": 0, "statuses": [], "deleted_values": [], "valid_from_values": [], "valid_until_values": [], "created_at_values": [], "updated_at_values": []}
        dvd = _history_for_course(
            dvd_history, class_id=class_id, course_id=course_id, component_field="component_id"
        ) if course_id != "<missing>" else {"count": 0, "statuses": [], "deleted_values": [], "valid_from_values": [], "valid_until_values": [], "created_at_values": [], "updated_at_values": []}
        candidates.append({
            "course_fingerprint": _fp(course_id) if course_id != "<missing>" else None,
            "catalog_resolved": course is not None,
            "catalog_name": _sid(course.get("name")) if course else None,
            "catalog_level": _sid(course.get("nivel_ensino")) if course else None,
            "catalog_created_at": _safe_dateish(course.get("created_at")) if course else None,
            "catalog_updated_at": _safe_dateish(course.get("updated_at")) if course else None,
            "content": _summary(rows),
            "math_attendance_distinct_dates": len(math_dates),
            "date_overlap_with_math_attendance": len(overlap),
            "date_overlap_ratio": round(len(overlap) / len(dates), 4) if dates else 0.0,
            "legacy_teacher_assignment_history": legacy,
            "dvd_assignment_history": dvd,
        })

    candidates.sort(
        key=lambda row: (
            -(row["legacy_teacher_assignment_history"]["count"] > 0),
            -(row["dvd_assignment_history"]["count"] > 0),
            -row["date_overlap_with_math_attendance"],
            -(row["content"]["documents"]),
            row["catalog_name"] or "",
        )
    )

    codes: list[str] = []
    assigned_candidates = [
        row for row in candidates
        if row["legacy_teacher_assignment_history"]["count"] > 0
        or row["dvd_assignment_history"]["count"] > 0
    ]
    if len(assigned_candidates) == 1:
        codes.append("UNIQUE_OTHER_COMPONENT_WITH_LUIZ_ASSIGNMENT_HISTORY")
    elif len(assigned_candidates) > 1:
        codes.append("MULTIPLE_OTHER_COMPONENTS_WITH_LUIZ_ASSIGNMENT_HISTORY")
    if any(row["legacy_teacher_assignment_history"]["count"] > 0 for row in candidates):
        codes.append("LEGACY_TEACHER_ASSIGNMENT_TO_OTHER_COMPONENT_CONFIRMED")
    if any(row["dvd_assignment_history"]["count"] > 0 for row in candidates):
        codes.append("DVD_ASSIGNMENT_TO_OTHER_COMPONENT_CONFIRMED")

    overlap_candidates = [
        row for row in candidates
        if row["date_overlap_with_math_attendance"] > 0
    ]
    if overlap_candidates:
        best_overlap = max(row["date_overlap_with_math_attendance"] for row in overlap_candidates)
        best = [row for row in overlap_candidates if row["date_overlap_with_math_attendance"] == best_overlap]
        if len(best) == 1:
            codes.append("UNIQUE_MAX_DATE_OVERLAP_CANDIDATE")
        else:
            codes.append("TIED_DATE_OVERLAP_CANDIDATES")
    if not candidates:
        codes.append("NO_OTHER_COMPONENT_CONTENT_IN_PERIOD")
    if candidates and not assigned_candidates:
        codes.append("NO_DIRECT_LUIZ_ASSIGNMENT_HISTORY_ON_CANDIDATES")

    return {
        "class": class_name,
        "current_math_course_fingerprint": _fp(current_math_course_id),
        "math_attendance": _summary(math_attendance_rows),
        "candidate_count": len(candidates),
        "classification": codes,
        "candidates": candidates,
    }


def run_live_audit() -> dict[str, Any]:
    if FORBIDDEN_FIELDS.intersection(LEARNING_PROJECTION) or FORBIDDEN_FIELDS.intersection(ATTENDANCE_PROJECTION):
        raise RuntimeError("LUIZ_GOMES_F6_1_UNSAFE_PROJECTION")

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("LUIZ_GOMES_F6_1_MONGO_URL_MISSING")
    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]

    user, staff_rows = _resolve_teacher(db)
    teacher_id = _sid(user.get("id"))
    staff_ids = {_sid(row.get("id")) for row in staff_rows if _sid(row.get("id"))}
    actor_ids = {teacher_id, *staff_ids}
    actor_ids.discard("")

    school = _resolve_school(db, user=user, staff_rows=staff_rows)
    school_id = _sid(school.get("id"))
    tenant_id = _sid(school.get("mantenedora_id"))
    class_by_id, course_by_id = _catalog(db, school_id=school_id, tenant_id=tenant_id)
    target_classes = _resolve_target_classes(class_by_id=class_by_id)
    legacy, dvd, assignment_ids = _teacher_history(
        db,
        teacher_id=teacher_id,
        staff_ids=staff_ids,
        school_id=school_id,
        tenant_id=tenant_id,
    )

    targets: list[dict[str, Any]] = []
    for class_name, class_id in target_classes.items():
        current_math_course_id = _resolve_current_math_course(
            class_id=class_id,
            legacy=legacy,
            course_by_id=course_by_id,
        )
        learning_rows = list(db.learning_objects.find(
            {
                "class_id": class_id,
                "date": {"$gte": START_DATE, "$lt": END_DATE},
            },
            LEARNING_PROJECTION,
        ))
        attendance_rows = list(db.attendance.find(
            {
                "class_id": class_id,
                "course_id": current_math_course_id,
                "date": {"$gte": START_DATE, "$lt": END_DATE},
            },
            ATTENDANCE_PROJECTION,
        ))
        math_attendance_rows = [
            row for row in attendance_rows
            if _teacher_attributed(row, actor_ids=actor_ids, assignment_ids=assignment_ids)
        ]
        targets.append(adjudicate_class(
            class_name=class_name,
            class_id=class_id,
            current_math_course_id=current_math_course_id,
            learning_rows=learning_rows,
            math_attendance_rows=math_attendance_rows,
            legacy_history=legacy,
            dvd_history=dvd,
            course_by_id=course_by_id,
        ))

    counts: Counter[str] = Counter(
        code for target in targets for code in target["classification"]
    )
    return {
        "schema": "LUIZ_GOMES_F6_1_COMPONENT_ADJUDICATION_READ_ONLY_V1",
        "status": "PASS",
        "academic_year": ACADEMIC_YEAR,
        "period": {"start": START_DATE, "end_exclusive": END_DATE},
        "teacher": TEACHER_NAME,
        "school": TARGET_SCHOOL,
        "target_pair_count": len(TARGET_CLASSES),
        "targets": targets,
        "summary": {"classification_counts": dict(sorted(counts.items()))},
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
    print("LUIZ_GOMES_F6_1_JSON=" + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True))
