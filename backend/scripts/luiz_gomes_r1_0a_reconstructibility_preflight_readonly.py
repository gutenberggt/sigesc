#!/usr/bin/env python3
"""LUIZ-GOMES-R1.0A — preflight read-only de reconstruibilidade por data.

Escopo:
- Luiz Gomes dos Santos;
- E M E I E F Jose Pereira Barbosa;
- Matemática;
- 8º ANO A e 9º ANO A;
- 2026-02-01 <= date < 2026-05-01.

Esta subfase NÃO reconstrói dados. Ela produz uma matriz data a data usando
somente evidências atuais metadata-only:
1) frequência de Matemática atribuível ao Luiz (sem attendance.records);
2) learning_objects/content_entries de Matemática, sem payload pedagógico;
3) audit_logs de identidade/data, sem valores pedagógicos;
4) diary_snapshots apenas metadados top-level.

Classificação fail-closed:
- RECOVERABLE_EXACT: reservado; R1.0A nunca o emite porque não lê payload histórico.
- RECOVERABLE_METADATA_ONLY: evidência histórica metadata-only atribuível ao Luiz.
- ATTENDANCE_ANCHOR_ONLY: frequência atribuível ao Luiz sem evidência de conteúdo.
- CONFLICTING_EVIDENCE: conteúdo/evidência existe, mas autoria conflita.
- NO_EVIDENCE: nenhuma evidência utilizável.

Nenhuma mutação é executada e nenhum ID técnico bruto é emitido.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
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
ACTOR_FIELDS = ("recorded_by", "created_by", "updated_by", "teacher_id", "staff_id", "actor_id", "user_id")

ATTENDANCE_PROJECTION = {
    "_id": 0, "class_id": 1, "course_id": 1, "date": 1, "academic_year": 1,
    "recorded_by": 1, "created_by": 1, "updated_by": 1,
    "teacher_id": 1, "staff_id": 1, "assignment_id": 1,
}
CONTENT_PROJECTION = {
    "_id": 0, "id": 1, "class_id": 1, "course_id": 1, "component_id": 1,
    "date": 1, "academic_year": 1, "recorded_by": 1, "created_by": 1,
    "updated_by": 1, "teacher_id": 1, "staff_id": 1, "assignment_id": 1,
    "deleted": 1, "status": 1,
}
AUDIT_PROJECTION = {
    "_id": 0, "collection": 1, "document_id": 1, "action": 1,
    "timestamp": 1, "timestamp_utc": 1, "actor_id": 1, "user_id": 1,
    "recorded_by": 1, "created_by": 1, "updated_by": 1, "teacher_id": 1, "staff_id": 1,
    "changes.class_id": 1, "changes.course_id": 1, "changes.component_id": 1, "changes.date": 1,
    "old_value.class_id": 1, "new_value.class_id": 1,
    "old_value.course_id": 1, "new_value.course_id": 1,
    "old_value.component_id": 1, "new_value.component_id": 1,
    "old_value.date": 1, "new_value.date": 1,
}
SNAPSHOT_PROJECTION = {
    "_id": 0, "class_id": 1, "course_id": 1, "component_id": 1,
    "date": 1, "snapshot_date": 1, "period_start": 1, "period_end": 1,
    "academic_year": 1, "status": 1, "published_at": 1,
    "recorded_by": 1, "created_by": 1, "updated_by": 1,
    "teacher_id": 1, "staff_id": 1, "assignment_id": 1,
}


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _sid(value))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.casefold().replace("º", "o").replace("ª", "a")
    return re.sub(r"\s+", " ", raw).strip()


def _day(value: Any) -> str | None:
    if isinstance(value, datetime):
        raw = value.date().isoformat()
    elif isinstance(value, date):
        raw = value.isoformat()
    else:
        raw = _sid(value)[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) and START_DATE <= raw < END_DATE:
        return raw
    return None


def _fingerprint(value: Any) -> str | None:
    raw = _sid(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12] if raw else None


def _component_id(row: Mapping[str, Any]) -> str:
    return _sid(row.get("course_id") or row.get("component_id"))


def _teacher_attributed(row: Mapping[str, Any], actor_ids: set[str], assignment_ids: set[str]) -> bool:
    for field in ACTOR_FIELDS:
        value = _sid(row.get(field))
        if value and value in actor_ids:
            return True
    assignment_id = _sid(row.get("assignment_id"))
    return bool(assignment_id and assignment_id in assignment_ids)


def _actor_state(row: Mapping[str, Any], actor_ids: set[str], assignment_ids: set[str]) -> str:
    explicit = {_sid(row.get(field)) for field in ACTOR_FIELDS if _sid(row.get(field))}
    assignment_id = _sid(row.get("assignment_id"))
    if explicit & actor_ids:
        return "LUIZ"
    if assignment_id and assignment_id in assignment_ids:
        return "LUIZ_ASSIGNMENT"
    if explicit:
        return "FOREIGN"
    if assignment_id:
        return "UNKNOWN_ASSIGNMENT"
    return "UNATTRIBUTED"


def _resolve_context(db):
    users = list(db.users.find(
        {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
        {"_id": 0, "id": 1, "name": 1, "full_name": 1, "mantenedora_id": 1},
    ).limit(20))
    users = [u for u in users if _norm(u.get("full_name") or u.get("name")) == _norm(TEACHER_NAME)]
    if len(users) != 1:
        raise RuntimeError(f"LUIZ_GOMES_R1_0A_TEACHER_MATCHES:{len(users)}")
    user = users[0]
    teacher_id = _sid(user.get("id"))

    staff_rows = list(db.staff.find(
        {"user_id": teacher_id},
        {"_id": 0, "id": 1, "user_id": 1, "school_id": 1, "mantenedora_id": 1},
    ))
    if not staff_rows:
        raise RuntimeError("LUIZ_GOMES_R1_0A_STAFF_NOT_FOUND")

    schools = [
        row for row in db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1})
        if _norm(row.get("name")) == _norm(TARGET_SCHOOL)
    ]
    tenant_hints = {_sid(user.get("mantenedora_id")), *(_sid(r.get("mantenedora_id")) for r in staff_rows)}
    tenant_hints.discard("")
    if len(schools) > 1 and tenant_hints:
        schools = [s for s in schools if _sid(s.get("mantenedora_id")) in tenant_hints]
    if len(schools) != 1:
        raise RuntimeError(f"LUIZ_GOMES_R1_0A_SCHOOL_MATCHES:{len(schools)}")
    school = schools[0]
    school_id = _sid(school.get("id"))
    tenant_id = _sid(school.get("mantenedora_id"))

    staff_rows = [
        r for r in staff_rows
        if _sid(r.get("school_id")) in {"", school_id}
        and _sid(r.get("mantenedora_id")) in {"", tenant_id}
    ]
    staff_ids = {_sid(r.get("id")) for r in staff_rows if _sid(r.get("id"))}
    actor_ids = {teacher_id, *staff_ids}
    actor_ids.discard("")

    classes = list(db.classes.find(
        {"school_id": school_id},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1, "mantenedora_id": 1},
    ))
    classes = [c for c in classes if _sid(c.get("mantenedora_id")) in {"", tenant_id}]
    class_ids: dict[str, str] = {}
    for name in TARGET_CLASSES:
        matches = [
            _sid(c.get("id")) for c in classes
            if _norm(c.get("name")) == _norm(name)
            and _sid(c.get("academic_year")) in {"", str(ACADEMIC_YEAR)}
            and _sid(c.get("id"))
        ]
        matches = sorted(set(matches))
        if len(matches) != 1:
            raise RuntimeError(f"LUIZ_GOMES_R1_0A_CLASS_NOT_EXACT:{name}:{len(matches)}")
        class_ids[name] = matches[0]

    courses = list(db.courses.find(
        {}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}
    ))
    courses = [c for c in courses if _sid(c.get("mantenedora_id")) in {"", tenant_id}]
    course_by_id = {_sid(c.get("id")): c for c in courses if _sid(c.get("id"))}
    math_ids = {
        cid for cid, row in course_by_id.items()
        if _norm(row.get("name")) == _norm(TARGET_COMPONENT)
    }
    if not math_ids:
        raise RuntimeError("LUIZ_GOMES_R1_0A_NO_MATH_IDENTITIES")

    legacy = list(db.teacher_assignments.find(
        {"staff_id": {"$in": sorted(staff_ids)}, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
        {"_id": 0, "id": 1, "staff_id": 1, "school_id": 1, "class_id": 1,
         "course_id": 1, "academic_year": 1, "status": 1, "mantenedora_id": 1},
    )) if staff_ids else []
    legacy = [
        r for r in legacy
        if _sid(r.get("school_id")) in {"", school_id}
        and _sid(r.get("mantenedora_id")) in {"", tenant_id}
    ]
    dvd = list(db.teacher_class_assignments.find(
        {"teacher_id": teacher_id},
        {"_id": 0, "id": 1, "teacher_id": 1, "class_id": 1, "component_id": 1,
         "course_id": 1, "school_id": 1, "mantenedora_id": 1, "deleted": 1},
    ))
    dvd = [
        r for r in dvd
        if _sid(r.get("school_id")) in {"", school_id}
        and _sid(r.get("mantenedora_id")) in {"", tenant_id}
    ]
    assignment_ids = {_sid(r.get("id")) for r in legacy + dvd if _sid(r.get("id"))}

    current_math: dict[str, str] = {}
    for name, class_id in class_ids.items():
        candidates = sorted({
            _sid(r.get("course_id")) for r in legacy
            if _sid(r.get("class_id")) == class_id
            and _norm(r.get("status")) in ACTIVE_STATUSES
            and _sid(r.get("course_id")) in math_ids
        })
        if len(candidates) != 1:
            raise RuntimeError(f"LUIZ_GOMES_R1_0A_CURRENT_MATH_NOT_EXACT:{name}:{len(candidates)}")
        current_math[name] = candidates[0]

    return {
        "teacher_id": teacher_id, "school_id": school_id, "tenant_id": tenant_id,
        "actor_ids": actor_ids, "assignment_ids": assignment_ids,
        "class_ids": class_ids, "math_ids": math_ids, "current_math": current_math,
    }


def _audit_candidates_for_target(rows: Iterable[Mapping[str, Any]], class_id: str, math_ids: set[str]):
    """Extract only identity/date evidence from projected audit rows."""
    out = []
    for row in rows:
        changes = row.get("changes") if isinstance(row.get("changes"), Mapping) else {}
        oldv = row.get("old_value") if isinstance(row.get("old_value"), Mapping) else {}
        newv = row.get("new_value") if isinstance(row.get("new_value"), Mapping) else {}
        class_values = {
            _sid(changes.get("class_id")), _sid(oldv.get("class_id")), _sid(newv.get("class_id"))
        }
        course_values = {
            _sid(changes.get("course_id")), _sid(changes.get("component_id")),
            _sid(oldv.get("course_id")), _sid(newv.get("course_id")),
            _sid(oldv.get("component_id")), _sid(newv.get("component_id")),
        }
        class_values.discard("")
        course_values.discard("")
        if class_id not in class_values or not (course_values & math_ids):
            continue
        day = (
            _day(changes.get("date")) or _day(oldv.get("date")) or _day(newv.get("date"))
            or _day(row.get("timestamp")) or _day(row.get("timestamp_utc"))
        )
        if day:
            out.append((day, row))
    return out


def _snapshot_rows_by_day(
    rows: Iterable[Mapping[str, Any]], class_id: str, math_ids: set[str]
) -> dict[str, list[Mapping[str, Any]]]:
    out: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if _sid(row.get("class_id")) != class_id or _component_id(row) not in math_ids:
            continue
        exact = _day(row.get("date")) or _day(row.get("snapshot_date"))
        if exact:
            out[exact].append(row)
        # period_start/period_end are deliberately not expanded: a period-level
        # snapshot does not prove that a Luiz/Matemática entry existed on each day.
    return out


def _classify_day(
    *,
    attendance_anchor: bool,
    content_states: Counter,
    audit_states: Counter,
    snapshot_states: Counter,
) -> tuple[str, str]:
    if (
        content_states.get("FOREIGN", 0)
        or audit_states.get("FOREIGN", 0)
        or snapshot_states.get("FOREIGN", 0)
    ):
        return "CONFLICTING_EVIDENCE", "foreign_actor_metadata_present"
    metadata_luiz = (
        content_states.get("LUIZ", 0)
        + content_states.get("LUIZ_ASSIGNMENT", 0)
        + audit_states.get("LUIZ", 0)
        + audit_states.get("LUIZ_ASSIGNMENT", 0)
        + snapshot_states.get("LUIZ", 0)
        + snapshot_states.get("LUIZ_ASSIGNMENT", 0)
    )
    if metadata_luiz:
        return "RECOVERABLE_METADATA_ONLY", "luiz_metadata_evidence_without_preserved_payload"
    if attendance_anchor:
        return "ATTENDANCE_ANCHOR_ONLY", "math_attendance_attributable_to_luiz_without_content_evidence"
    return "NO_EVIDENCE", "no_reconstructible_evidence"


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("LUIZ_GOMES_R1_0A_MONGO_URL_MISSING")
    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]
    ctx = _resolve_context(db)

    class_ids = ctx["class_ids"]
    math_ids = ctx["math_ids"]
    actor_ids = ctx["actor_ids"]
    assignment_ids = ctx["assignment_ids"]
    current_math = ctx["current_math"]

    audit_rows = list(db.audit_logs.find(
        {"collection": {"$in": ["learning_objects", "content_entries"]}},
        AUDIT_PROJECTION,
    ))
    snapshot_rows = list(db.diary_snapshots.find(
        {"academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
        SNAPSHOT_PROJECTION,
    ))

    targets = []
    overall = Counter()
    for class_name in TARGET_CLASSES:
        class_id = class_ids[class_name]
        attendance_rows = list(db.attendance.find(
            {"class_id": class_id, "course_id": current_math[class_name],
             "date": {"$gte": START_DATE, "$lt": END_DATE}},
            ATTENDANCE_PROJECTION,
        ))
        attendance_rows = [
            r for r in attendance_rows if _teacher_attributed(r, actor_ids, assignment_ids)
        ]
        attendance_dates = {_day(r.get("date")) for r in attendance_rows if _day(r.get("date"))}

        content_by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        collection_counts = {}
        for collection_name in ("learning_objects", "content_entries"):
            rows = list(db[collection_name].find(
                {"class_id": class_id, "date": {"$gte": START_DATE, "$lt": END_DATE}},
                CONTENT_PROJECTION,
            ))
            rows = [r for r in rows if _component_id(r) in math_ids]
            collection_counts[collection_name] = len(rows)
            for row in rows:
                day = _day(row.get("date"))
                if day:
                    content_by_date[day].append(row)

        audit_for_target = _audit_candidates_for_target(audit_rows, class_id, math_ids)
        audit_by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for day, row in audit_for_target:
            audit_by_date[day].append(row)

        snapshot_by_date = _snapshot_rows_by_day(snapshot_rows, class_id, math_ids)
        snapshot_dates = set(snapshot_by_date)

        day_universe = sorted(attendance_dates | set(content_by_date) | set(audit_by_date) | snapshot_dates)
        matrix = []
        for day in day_universe:
            content_states = Counter(
                _actor_state(r, actor_ids, assignment_ids) for r in content_by_date.get(day, [])
            )
            audit_states = Counter(
                _actor_state(r, actor_ids, assignment_ids) for r in audit_by_date.get(day, [])
            )
            snapshot_states = Counter(
                _actor_state(r, actor_ids, assignment_ids) for r in snapshot_by_date.get(day, [])
            )
            classification, reason = _classify_day(
                attendance_anchor=day in attendance_dates,
                content_states=content_states,
                audit_states=audit_states,
                snapshot_states=snapshot_states,
            )
            overall[classification] += 1
            matrix.append({
                "date": day,
                "attendance_anchor": day in attendance_dates,
                "content_metadata_rows": len(content_by_date.get(day, [])),
                "content_actor_partition": dict(sorted(content_states.items())),
                "audit_identity_events": len(audit_by_date.get(day, [])),
                "audit_actor_partition": dict(sorted(audit_states.items())),
                "snapshot_top_level_metadata": day in snapshot_dates,
                "snapshot_actor_partition": dict(sorted(snapshot_states.items())),
                "classification": classification,
                "reason": reason,
            })

        per_class = Counter(row["classification"] for row in matrix)
        targets.append({
            "class": class_name,
            "class_fingerprint": _fingerprint(class_id),
            "attendance_anchor_dates": len(attendance_dates),
            "current_math_content_counts": collection_counts,
            "audit_identity_events": len(audit_for_target),
            "snapshot_top_level_dates": len(snapshot_dates),
            "classification_counts": {
                key: per_class.get(key, 0) for key in (
                    "RECOVERABLE_EXACT", "RECOVERABLE_METADATA_ONLY",
                    "ATTENDANCE_ANCHOR_ONLY", "CONFLICTING_EVIDENCE", "NO_EVIDENCE",
                )
            },
            "matrix": matrix,
        })

    return {
        "schema": "LUIZ_GOMES_R1_0A_RECONSTRUCTIBILITY_PREFLIGHT_READ_ONLY_V1",
        "status": "PASS",
        "scope": {
            "teacher": TEACHER_NAME,
            "school": TARGET_SCHOOL,
            "component": TARGET_COMPONENT,
            "classes": list(TARGET_CLASSES),
            "academic_year": ACADEMIC_YEAR,
            "start_date": START_DATE,
            "end_date_exclusive": END_DATE,
        },
        "classification_counts": {
            key: overall.get(key, 0) for key in (
                "RECOVERABLE_EXACT", "RECOVERABLE_METADATA_ONLY",
                "ATTENDANCE_ANCHOR_ONLY", "CONFLICTING_EVIDENCE", "NO_EVIDENCE",
            )
        },
        "targets": targets,
        "r1_1_gate_openable": overall.get("RECOVERABLE_EXACT", 0) > 0,
        "exact_payload_recovery_attempted": False,
        "historical_backup_restore_attempted": False,
        "mongo_reads_only": True,
        "database_mutation": False,
        "production_writes": False,
        "attendance_records_read": False,
        "student_data_read": False,
        "enrollment_data_read": False,
        "grades_read": False,
        "pedagogical_plaintext_read": False,
        "pedagogical_plaintext_emitted": False,
        "technical_ids_emitted": False,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True))
