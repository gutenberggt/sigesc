#!/usr/bin/env python3
"""ANA-LUCIA-F2.2 — rastreamento read-only de origem/orfandade.

Objetivo: investigar os oito pares de Língua Inglesa dos 6º/9º anos que a
F2.1 encontrou sem learning_objects no par esperado e, dentro deles, os cinco
pares também sem frequência oficial no par esperado.

A auditoria procura somente metadados estruturais para distinguir:
- registro no mesmo par fora do escopo de ano;
- registro na mesma turma sob outro course_id de Língua Inglesa;
- registro na mesma turma sob outro componente;
- registro canônico em content_entries;
- frequência class-daily/sem course_id;
- frequência documental;
- registros atribuíveis à mesma professora em outra turma;
- evidência de create/update/delete em audit_logs, sem ler old/new/description.

Boundary obrigatório:
- MongoDB somente leitura;
- nenhum HTTP/login;
- nenhuma leitura de attendance.records;
- nenhuma coleção de estudantes/matrículas;
- nenhum texto pedagógico de learning_objects/content_entries;
- nenhum ID técnico bruto emitido; somente fingerprints SHA-256 truncados;
- nenhuma mutação, backfill, reconciliação, migração ou saneamento.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import os
import re
import unicodedata
from typing import Any, Iterable, Mapping

from pymongo import MongoClient

ACADEMIC_YEAR = 2026
TEACHER_NAME = "Ana Lucia Faria Pinto"
ACTIVE_STATUSES = ("ativo", "active")
TARGET_CLASSES: tuple[str, ...] = (
    "6º ANO A",
    "6º ANO B",
    "6º ANO C",
    "6º ANO D",
    "9º ANO A",
    "9º ANO B",
    "9º ANO C",
    "9º ANO D",
)
EXPECTED_ATTENDANCE_MISSING: frozenset[str] = frozenset(
    {"6º ANO A", "6º ANO D", "9º ANO A", "9º ANO B", "9º ANO C"}
)
COMPONENT_NAME = "Língua Inglesa"

CONTENT_PROJECTION = {
    "_id": 0,
    "id": 1,
    "date": 1,
    "academic_year": 1,
    "class_id": 1,
    "course_id": 1,
    "component_id": 1,
    "assignment_id": 1,
    "teacher_id": 1,
    "recorded_by": 1,
    "created_by": 1,
    "updated_by": 1,
    "mantenedora_id": 1,
    "deleted": 1,
    "status": 1,
    "copied_from_id": 1,
    "migration_source": 1,
}

ATTENDANCE_PROJECTION = {
    "_id": 0,
    "id": 1,
    "date": 1,
    "academic_year": 1,
    "class_id": 1,
    "course_id": 1,
    "assignment_id": 1,
    "teacher_id": 1,
    "created_by": 1,
    "updated_by": 1,
    "school_id": 1,
    "mantenedora_id": 1,
    "attendance_mode": 1,
    "attendance_purpose": 1,
    "deleted": 1,
    "status": 1,
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


def _day(value: Any) -> str:
    return _sid(value)[:10]


def _year_scope() -> dict[str, Any]:
    return {
        "$or": [
            {"academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
            {"date": {"$gte": f"{ACADEMIC_YEAR}-01-01", "$lte": f"{ACADEMIC_YEAR}-12-31"}},
        ]
    }


def _year_bucket(row: Mapping[str, Any]) -> str:
    ay = _sid(row.get("academic_year"))
    day = _day(row.get("date"))
    ay_target = ay == str(ACADEMIC_YEAR)
    day_year = day[:4] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) else ""
    day_target = day_year == str(ACADEMIC_YEAR)
    if ay and day_year and ay != day_year:
        return "conflict"
    if ay_target or day_target:
        return "target"
    if not ay and not day_year:
        return "missing"
    return "other"


def _course_key(row: Mapping[str, Any]) -> str:
    return _sid(row.get("course_id") or row.get("component_id"))


def _is_teacher_actor(row: Mapping[str, Any], actor_ids: set[str]) -> bool:
    for key in ("recorded_by", "created_by", "updated_by", "teacher_id"):
        if _sid(row.get(key)) in actor_ids:
            return True
    return False


def _safe_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    buckets = Counter(_year_bucket(row) for row in materialized)
    return {
        "documents": len(materialized),
        "year_buckets": dict(sorted(buckets.items())),
        "distinct_dates_2026": len({_day(r.get("date")) for r in materialized if _year_bucket(r) == "target" and _day(r.get("date"))}),
    }


def classify_content_origin(
    *,
    exact_2026: int,
    alt_english_same_class_teacher: int,
    canonical_same_class_teacher: int,
    exact_other_year: int,
    other_component_same_class_teacher: int,
    copied_lineage_same_class: int,
    school_delete_audit_count: int,
) -> list[str]:
    codes: list[str] = []
    if exact_2026:
        codes.append("CONTENT_EXACT_PAIR_NOW_PRESENT")
    if alt_english_same_class_teacher:
        codes.append("CONTENT_ALT_ENGLISH_COURSE_ID_SAME_CLASS")
    if canonical_same_class_teacher:
        codes.append("CONTENT_CANONICAL_SAME_CLASS_ENGLISH")
    if exact_other_year:
        codes.append("CONTENT_EXACT_PAIR_OUTSIDE_2026")
    if other_component_same_class_teacher:
        codes.append("CONTENT_OTHER_COMPONENT_SAME_CLASS_TEACHER_ATTRIBUTED")
    if copied_lineage_same_class:
        codes.append("CONTENT_COPY_LINEAGE_PRESENT_SAME_CLASS")
    if school_delete_audit_count:
        codes.append("CONTENT_DELETE_AUDIT_EXISTS_SAME_SCHOOL_UNATTRIBUTED")
    if not codes:
        codes.append("CONTENT_ORIGIN_NOT_FOUND_IN_SCANNED_METADATA")
    return codes


def classify_attendance_origin(
    *,
    exact_2026: int,
    alt_english_same_class_teacher: int,
    class_daily_teacher: int,
    documentary_english_teacher: int,
    exact_other_year: int,
    other_component_same_class_teacher: int,
    school_delete_audit_count: int,
) -> list[str]:
    codes: list[str] = []
    if exact_2026:
        codes.append("ATTENDANCE_EXACT_PAIR_NOW_PRESENT")
    if alt_english_same_class_teacher:
        codes.append("ATTENDANCE_ALT_ENGLISH_COURSE_ID_SAME_CLASS")
    if class_daily_teacher:
        codes.append("ATTENDANCE_CLASS_DAILY_UNATTRIBUTED_TO_COMPONENT")
    if documentary_english_teacher:
        codes.append("ATTENDANCE_DOCUMENTARY_ENGLISH_SAME_CLASS")
    if exact_other_year:
        codes.append("ATTENDANCE_EXACT_PAIR_OUTSIDE_2026")
    if other_component_same_class_teacher:
        codes.append("ATTENDANCE_OTHER_COMPONENT_SAME_CLASS_TEACHER_ATTRIBUTED")
    if school_delete_audit_count:
        codes.append("ATTENDANCE_DELETE_AUDIT_EXISTS_SAME_SCHOOL_UNATTRIBUTED")
    if not codes:
        codes.append("ATTENDANCE_ORIGIN_NOT_FOUND_IN_SCANNED_METADATA")
    return codes


def _unique_teacher_identity(db) -> tuple[dict[str, Any], dict[str, Any]]:
    users = list(
        db.users.find(
            {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
            {"_id": 0, "id": 1, "email": 1, "full_name": 1, "name": 1, "role": 1, "mantenedora_id": 1},
        ).limit(5)
    )
    users = [row for row in users if _norm(row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)]
    if len(users) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_2_TEACHER_USER_MATCHES:{len(users)}")
    user = users[0]
    if user.get("role") != "professor":
        raise RuntimeError(f"ANA_LUCIA_F2_2_TEACHER_ROLE:{user.get('role')}")

    clauses = [{"user_id": user["id"]}]
    if user.get("email"):
        clauses.append({"email": user["email"]})
    staff_rows = list(
        db.staff.find(
            {"$or": clauses},
            {"_id": 0, "id": 1, "user_id": 1, "email": 1, "mantenedora_id": 1},
        ).limit(5)
    )
    dedup = {_sid(row.get("id")): row for row in staff_rows if _sid(row.get("id"))}
    if len(dedup) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_2_STAFF_MATCHES:{len(dedup)}")
    return user, next(iter(dedup.values()))


def _resolve_targets(db, staff: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    assignments = list(
        db.teacher_assignments.find(
            {
                "staff_id": staff["id"],
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
                "status": {"$in": list(ACTIVE_STATUSES)},
            },
            {"_id": 0, "id": 1, "class_id": 1, "course_id": 1, "school_id": 1, "mantenedora_id": 1},
        )
    )
    class_ids = sorted({_sid(row.get("class_id")) for row in assignments if _sid(row.get("class_id"))})
    course_ids = sorted({_sid(row.get("course_id")) for row in assignments if _sid(row.get("course_id"))})
    classes = list(
        db.classes.find(
            {"id": {"$in": class_ids}},
            {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1, "academic_year": 1},
        )
    )
    class_by_id = {_sid(row.get("id")): row for row in classes if _sid(row.get("id"))}
    course_rows = list(
        db.courses.find(
            {"id": {"$in": course_ids}},
            {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
        )
    )
    course_names = {_sid(row.get("id")): _sid(row.get("name")) for row in course_rows if _sid(row.get("id"))}
    school_ids = sorted({_sid(row.get("school_id")) for row in classes if _sid(row.get("school_id"))})
    schools = list(
        db.schools.find(
            {"id": {"$in": school_ids}},
            {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
        )
    )
    school_by_id = {_sid(row.get("id")): row for row in schools if _sid(row.get("id"))}

    targets: list[dict[str, Any]] = []
    for class_name in TARGET_CLASSES:
        candidates: list[dict[str, Any]] = []
        for row in assignments:
            class_doc = class_by_id.get(_sid(row.get("class_id"))) or {}
            if _norm(class_doc.get("name")) != _norm(class_name):
                continue
            if _norm(course_names.get(_sid(row.get("course_id")))) != _norm(COMPONENT_NAME):
                continue
            candidates.append(row)
        if len(candidates) != 1:
            raise RuntimeError(f"ANA_LUCIA_F2_2_TARGET_NOT_EXACT:{class_name}:{len(candidates)}")
        assignment = candidates[0]
        class_doc = class_by_id[_sid(assignment.get("class_id"))]
        school = school_by_id.get(_sid(class_doc.get("school_id"))) or {}
        tenant_id = _sid(class_doc.get("mantenedora_id") or school.get("mantenedora_id"))
        if not tenant_id:
            raise RuntimeError(f"ANA_LUCIA_F2_2_TENANT_MISSING:{class_name}")
        targets.append(
            {
                "class": class_name,
                "class_id": _sid(assignment.get("class_id")),
                "course_id": _sid(assignment.get("course_id")),
                "school_id": _sid(class_doc.get("school_id")),
                "school": _sid(school.get("name")),
                "tenant_id": tenant_id,
            }
        )
    return targets, {cid: _sid(class_by_id[cid].get("name")) for cid in class_by_id}, course_names


def _load_name_maps(db) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    classes = list(db.classes.find({}, {"_id": 0, "id": 1, "name": 1, "school_id": 1}))
    courses = list(db.courses.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}))
    schools = list(db.schools.find({}, {"_id": 0, "id": 1, "name": 1}))
    return (
        {_sid(row.get("id")): _sid(row.get("name")) for row in classes if _sid(row.get("id"))},
        {_sid(row.get("id")): _sid(row.get("name")) for row in courses if _sid(row.get("id"))},
        {_sid(row.get("id")): _sid(row.get("name")) for row in schools if _sid(row.get("id"))},
    )


def _english_course_ids(db, tenant_ids: set[str]) -> set[str]:
    rows = list(
        db.courses.find(
            {"$or": [{"mantenedora_id": {"$in": sorted(tenant_ids)}}, {"mantenedora_id": {"$exists": False}}, {"mantenedora_id": None}, {"mantenedora_id": ""}]},
            {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
        )
    )
    return {_sid(row.get("id")) for row in rows if _sid(row.get("id")) and _norm(row.get("name")) == _norm(COMPONENT_NAME)}


def _assignment_owners(db, teacher_id: str) -> tuple[set[str], dict[str, str]]:
    rows = list(
        db.teacher_class_assignments.find(
            {},
            {"_id": 0, "id": 1, "teacher_id": 1, "class_id": 1, "component_id": 1, "deleted": 1},
        )
    )
    owner = {_sid(row.get("id")): _sid(row.get("teacher_id")) for row in rows if _sid(row.get("id"))}
    teacher_ids = {_sid(row.get("id")) for row in rows if _sid(row.get("id")) and _sid(row.get("teacher_id")) == teacher_id}
    return teacher_ids, owner


def _teacher_attributed(row: Mapping[str, Any], *, actor_ids: set[str], teacher_assignment_ids: set[str], assignment_owner: Mapping[str, str], teacher_id: str) -> bool:
    if _is_teacher_actor(row, actor_ids):
        return True
    aid = _sid(row.get("assignment_id"))
    if aid and (aid in teacher_assignment_ids or assignment_owner.get(aid) == teacher_id):
        return True
    return False


def _summarize_pair_collection(
    rows: list[dict[str, Any]],
    *,
    target: Mapping[str, Any],
    english_ids: set[str],
    actor_ids: set[str],
    teacher_assignment_ids: set[str],
    assignment_owner: Mapping[str, str],
    teacher_id: str,
) -> dict[str, Any]:
    class_id = target["class_id"]
    course_id = target["course_id"]
    in_class = [row for row in rows if _sid(row.get("class_id")) == class_id]
    target_year = [row for row in in_class if _year_bucket(row) == "target"]
    exact = [row for row in in_class if _course_key(row) == course_id]
    exact_target = [row for row in exact if _year_bucket(row) == "target"]
    exact_other = [row for row in exact if _year_bucket(row) != "target"]
    alt_english = [
        row for row in target_year
        if _course_key(row) in english_ids and _course_key(row) != course_id
    ]
    blank_course = [row for row in target_year if not _course_key(row)]
    other_component = [
        row for row in target_year
        if _course_key(row) and _course_key(row) not in english_ids
    ]

    def attributed(seq: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        return [
            row for row in seq
            if _teacher_attributed(
                row,
                actor_ids=actor_ids,
                teacher_assignment_ids=teacher_assignment_ids,
                assignment_owner=assignment_owner,
                teacher_id=teacher_id,
            )
        ]

    copied = [row for row in target_year if _sid(row.get("copied_from_id"))]
    alt_course_fps = sorted({_fp(_course_key(row)) for row in alt_english if _fp(_course_key(row))})
    other_course_fps = sorted({_fp(_course_key(row)) for row in other_component if _fp(_course_key(row))})
    return {
        "same_class": _safe_counts(in_class),
        "exact_expected_course": _safe_counts(exact),
        "exact_2026": len(exact_target),
        "exact_outside_2026": len(exact_other),
        "alt_english_same_class_2026": len(alt_english),
        "alt_english_teacher_attributed_2026": len(attributed(alt_english)),
        "alt_english_course_fingerprints": alt_course_fps,
        "blank_course_same_class_2026": len(blank_course),
        "blank_course_teacher_attributed_2026": len(attributed(blank_course)),
        "other_component_same_class_2026": len(other_component),
        "other_component_teacher_attributed_2026": len(attributed(other_component)),
        "other_component_course_fingerprints": other_course_fps,
        "copy_lineage_same_class_2026": len(copied),
        "copy_lineage_teacher_attributed_2026": len(attributed(copied)),
    }


def _teacher_english_locations(
    rows: Iterable[Mapping[str, Any]],
    *,
    english_ids: set[str],
    actor_ids: set[str],
    teacher_assignment_ids: set[str],
    assignment_owner: Mapping[str, str],
    teacher_id: str,
    class_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        if _year_bucket(row) != "target" or _course_key(row) not in english_ids:
            continue
        if not _teacher_attributed(
            row,
            actor_ids=actor_ids,
            teacher_assignment_ids=teacher_assignment_ids,
            assignment_owner=assignment_owner,
            teacher_id=teacher_id,
        ):
            continue
        class_id = _sid(row.get("class_id"))
        counts[class_id] += 1
    out = []
    for class_id, count in sorted(counts.items(), key=lambda item: (_norm(class_names.get(item[0])), item[0])):
        out.append({
            "class": class_names.get(class_id) or "<turma não resolvida>",
            "class_fingerprint": _fp(class_id),
            "documents": count,
        })
    return out


def _audit_log_summary(db, *, teacher_id: str, target_school_ids: set[str]) -> dict[str, Any]:
    rows = list(
        db.audit_logs.find(
            {
                "user_id": teacher_id,
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
                "collection": {"$in": ["learning_objects", "content_entries", "attendance", "attendance_documentary"]},
                "action": {"$in": ["create", "update", "delete"]},
            },
            {"_id": 0, "collection": 1, "action": 1, "school_id": 1, "document_id": 1, "timestamp": 1},
        )
    )
    total = Counter((row.get("collection") or "<missing>", row.get("action") or "<missing>") for row in rows)
    by_school: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        school_id = _sid(row.get("school_id"))
        if school_id not in target_school_ids:
            continue
        by_school[school_id][f"{row.get('collection') or '<missing>'}:{row.get('action') or '<missing>'}"] += 1
    return {
        "teacher_events_total": len(rows),
        "counts": {f"{collection}:{action}": count for (collection, action), count in sorted(total.items())},
        "target_school_counts": {school: dict(sorted(counter.items())) for school, counter in by_school.items()},
    }


def _delete_count(audit_summary: Mapping[str, Any], school_id: str, collection: str) -> int:
    return int(((audit_summary.get("target_school_counts") or {}).get(school_id) or {}).get(f"{collection}:delete", 0))


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("ANA_LUCIA_F2_2_MONGO_URL_MISSING")

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
    db = client[db_name]
    try:
        user, staff = _unique_teacher_identity(db)
        targets, _, _ = _resolve_targets(db, staff)
        teacher_id = _sid(user.get("id"))
        staff_id = _sid(staff.get("id"))
        actor_ids = {value for value in (teacher_id, staff_id) if value}
        tenant_ids = {_sid(row.get("tenant_id")) for row in targets if _sid(row.get("tenant_id"))}
        english_ids = _english_course_ids(db, tenant_ids)
        if not english_ids:
            raise RuntimeError("ANA_LUCIA_F2_2_ENGLISH_COURSE_IDS_MISSING")
        teacher_assignment_ids, assignment_owner = _assignment_owners(db, teacher_id)
        class_names, course_names, school_names = _load_name_maps(db)
        target_class_ids = {_sid(row.get("class_id")) for row in targets}
        target_school_ids = {_sid(row.get("school_id")) for row in targets}

        learning_all = list(
            db.learning_objects.find(
                {"$or": [
                    {"class_id": {"$in": sorted(target_class_ids)}},
                    {"recorded_by": {"$in": sorted(actor_ids)}},
                    {"created_by": {"$in": sorted(actor_ids)}},
                    {"teacher_id": {"$in": sorted(actor_ids)}},
                ]},
                CONTENT_PROJECTION,
            )
        )
        content_entries_all = list(
            db.content_entries.find(
                {"$or": [
                    {"class_id": {"$in": sorted(target_class_ids)}},
                    {"teacher_id": teacher_id},
                    {"created_by": {"$in": sorted(actor_ids)}},
                    {"assignment_id": {"$in": sorted(teacher_assignment_ids)}},
                ]},
                CONTENT_PROJECTION,
            )
        )
        content_entries_all = [row for row in content_entries_all if row.get("deleted") is not True]

        attendance_query = {"$or": [
            {"class_id": {"$in": sorted(target_class_ids)}},
            {"teacher_id": teacher_id},
            {"created_by": {"$in": sorted(actor_ids)}},
            {"updated_by": {"$in": sorted(actor_ids)}},
            {"assignment_id": {"$in": sorted(teacher_assignment_ids)}},
        ]}
        attendance_all = list(db.attendance.find(attendance_query, ATTENDANCE_PROJECTION))
        documentary_all = list(db.attendance_documentary.find(attendance_query, ATTENDANCE_PROJECTION))

        audit_summary = _audit_log_summary(db, teacher_id=teacher_id, target_school_ids=target_school_ids)

        pair_results: list[dict[str, Any]] = []
        content_codes: Counter[str] = Counter()
        attendance_codes: Counter[str] = Counter()
        for target in targets:
            learning = _summarize_pair_collection(
                learning_all,
                target=target,
                english_ids=english_ids,
                actor_ids=actor_ids,
                teacher_assignment_ids=teacher_assignment_ids,
                assignment_owner=assignment_owner,
                teacher_id=teacher_id,
            )
            canonical = _summarize_pair_collection(
                content_entries_all,
                target=target,
                english_ids=english_ids,
                actor_ids=actor_ids,
                teacher_assignment_ids=teacher_assignment_ids,
                assignment_owner=assignment_owner,
                teacher_id=teacher_id,
            )
            attendance = _summarize_pair_collection(
                attendance_all,
                target=target,
                english_ids=english_ids,
                actor_ids=actor_ids,
                teacher_assignment_ids=teacher_assignment_ids,
                assignment_owner=assignment_owner,
                teacher_id=teacher_id,
            )
            documentary = _summarize_pair_collection(
                documentary_all,
                target=target,
                english_ids=english_ids,
                actor_ids=actor_ids,
                teacher_assignment_ids=teacher_assignment_ids,
                assignment_owner=assignment_owner,
                teacher_id=teacher_id,
            )
            c_codes = classify_content_origin(
                exact_2026=int(learning["exact_2026"]),
                alt_english_same_class_teacher=int(learning["alt_english_teacher_attributed_2026"]),
                canonical_same_class_teacher=(
                    int(canonical["exact_2026"]) + int(canonical["alt_english_teacher_attributed_2026"])
                ),
                exact_other_year=int(learning["exact_outside_2026"]),
                other_component_same_class_teacher=int(learning["other_component_teacher_attributed_2026"]),
                copied_lineage_same_class=int(learning["copy_lineage_teacher_attributed_2026"]),
                school_delete_audit_count=_delete_count(audit_summary, target["school_id"], "learning_objects"),
            )
            a_codes = classify_attendance_origin(
                exact_2026=int(attendance["exact_2026"]),
                alt_english_same_class_teacher=int(attendance["alt_english_teacher_attributed_2026"]),
                class_daily_teacher=int(attendance["blank_course_teacher_attributed_2026"]),
                documentary_english_teacher=(
                    int(documentary["exact_2026"]) + int(documentary["alt_english_teacher_attributed_2026"])
                ),
                exact_other_year=int(attendance["exact_outside_2026"]),
                other_component_same_class_teacher=int(attendance["other_component_teacher_attributed_2026"]),
                school_delete_audit_count=_delete_count(audit_summary, target["school_id"], "attendance"),
            )
            content_codes.update(c_codes)
            attendance_codes.update(a_codes)
            pair_results.append(
                {
                    "class": target["class"],
                    "component": COMPONENT_NAME,
                    "school": target["school"],
                    "expected_course_fingerprint": _fp(target["course_id"]),
                    "expected_content_missing_from_f2_1": True,
                    "expected_attendance_missing_from_f2_1": target["class"] in EXPECTED_ATTENDANCE_MISSING,
                    "learning_objects": learning,
                    "content_entries": canonical,
                    "attendance": attendance,
                    "attendance_documentary": documentary,
                    "content_origin_codes": c_codes,
                    "attendance_origin_codes": a_codes,
                }
            )

        english_course_catalog = [
            {
                "course_fingerprint": _fp(course_id),
                "name": course_names.get(course_id) or COMPONENT_NAME,
                "is_expected_by_any_target": any(_sid(t.get("course_id")) == course_id for t in targets),
            }
            for course_id in sorted(english_ids)
        ]

        return {
            "schema": "ANA_LUCIA_F2_2_ORPHAN_TRACE_READ_ONLY_V1",
            "status": "PASS",
            "database_mutation": False,
            "production_writes": False,
            "mongo_reads_only": True,
            "http_methods": [],
            "login_endpoint_used": False,
            "attendance_records_read": False,
            "student_data_read": False,
            "student_pii_emitted": False,
            "pedagogical_text_read": False,
            "technical_ids_emitted": False,
            "technical_id_fingerprints_emitted": True,
            "audit_old_new_values_read": False,
            "target": {
                "teacher": TEACHER_NAME,
                "academic_year": ACADEMIC_YEAR,
                "component": COMPONENT_NAME,
                "target_pair_count": len(TARGET_CLASSES),
                "content_missing_pair_count_from_f2_1": len(TARGET_CLASSES),
                "attendance_missing_pair_count_from_f2_1": len(EXPECTED_ATTENDANCE_MISSING),
            },
            "catalog": {
                "english_course_identity_count": len(english_ids),
                "english_courses": english_course_catalog,
            },
            "teacher_english_locations": {
                "learning_objects": _teacher_english_locations(
                    learning_all,
                    english_ids=english_ids,
                    actor_ids=actor_ids,
                    teacher_assignment_ids=teacher_assignment_ids,
                    assignment_owner=assignment_owner,
                    teacher_id=teacher_id,
                    class_names=class_names,
                ),
                "content_entries": _teacher_english_locations(
                    content_entries_all,
                    english_ids=english_ids,
                    actor_ids=actor_ids,
                    teacher_assignment_ids=teacher_assignment_ids,
                    assignment_owner=assignment_owner,
                    teacher_id=teacher_id,
                    class_names=class_names,
                ),
                "attendance": _teacher_english_locations(
                    attendance_all,
                    english_ids=english_ids,
                    actor_ids=actor_ids,
                    teacher_assignment_ids=teacher_assignment_ids,
                    assignment_owner=assignment_owner,
                    teacher_id=teacher_id,
                    class_names=class_names,
                ),
                "attendance_documentary": _teacher_english_locations(
                    documentary_all,
                    english_ids=english_ids,
                    actor_ids=actor_ids,
                    teacher_assignment_ids=teacher_assignment_ids,
                    assignment_owner=assignment_owner,
                    teacher_id=teacher_id,
                    class_names=class_names,
                ),
            },
            "audit_logs_metadata_only": {
                "teacher_events_total": audit_summary["teacher_events_total"],
                "counts": audit_summary["counts"],
                "target_school_counts": {
                    school_names.get(school_id) or _fp(school_id) or "<unknown>": counts
                    for school_id, counts in sorted((audit_summary.get("target_school_counts") or {}).items())
                },
            },
            "summary": {
                "content_origin_code_counts": dict(sorted(content_codes.items())),
                "attendance_origin_code_counts": dict(sorted(attendance_codes.items())),
            },
            "pairs": pair_results,
        }
    finally:
        client.close()


def main() -> None:
    print(
        "ANA_LUCIA_F2_2_JSON="
        + json.dumps(run_live_audit(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )


if __name__ == "__main__":
    main()
