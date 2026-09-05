#!/usr/bin/env python3
"""Preflight reutilizável para reconstrução administrativa por turma-espelho.

O motor é deliberadamente read-only. Ele recebe uma especificação declarativa
de caso, resolve o contexto institucional, lê conteúdo pedagógico somente para
computar fingerprints privados e constrói um manifesto SANITIZADO por mês.

Nenhum ID técnico bruto e nenhum plaintext pedagógico são emitidos.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import base64
import hashlib
import json
import os
import re
import unicodedata
from typing import Any, Iterable, Mapping

from pymongo import MongoClient

SCHEMA = "SIBLING_CLASS_RECONSTRUCTION_PREFLIGHT_V1"
CASE_SCHEMA = "SIBLING_CLASS_RECONSTRUCTION_CASE_V1"
SUPPORTED_STRATEGY = "MONTHLY_ORDINAL_EXACT_COUNT"
ACTIVE_STATUSES = {"ativo", "active"}
ACTOR_FIELDS = (
    "recorded_by", "created_by", "updated_by", "teacher_id", "staff_id",
    "actor_id", "user_id",
)

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

CONTENT_PROJECTION = {
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
    # Payload lido APENAS dentro do processo para fingerprint; nunca emitido.
    "content": 1,
    "methodology": 1,
    "observations": 1,
    "number_of_classes": 1,
}

ASSIGNMENT_PROJECTION = {
    "_id": 0,
    "id": 1,
    "teacher_id": 1,
    "staff_id": 1,
    "school_id": 1,
    "class_id": 1,
    "course_id": 1,
    "component_id": 1,
    "academic_year": 1,
    "status": 1,
    "deleted": 1,
    "mantenedora_id": 1,
    "valid_from": 1,
    "valid_until": 1,
    "diary_settings.enabled": 1,
}


class PreflightError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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
    raw = _sid(value)[:10]
    return raw if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) else None


def _fp(value: Any, length: int = 16) -> str:
    raw = _sid(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _payload_fingerprint(row: Mapping[str, Any]) -> str:
    payload = {
        "content": row.get("content") or "",
        "methodology": row.get("methodology"),
        "observations": row.get("observations"),
        "number_of_classes": row.get("number_of_classes") or 1,
    }
    return _canonical_hash(payload)


def _component_id(row: Mapping[str, Any]) -> str:
    return _sid(row.get("component_id") or row.get("course_id"))


def _teacher_attributed(
    row: Mapping[str, Any], actor_ids: set[str], assignment_ids: set[str]
) -> bool:
    for field in ACTOR_FIELDS:
        value = _sid(row.get(field))
        if value and value in actor_ids:
            return True
    assignment_id = _sid(row.get("assignment_id"))
    return bool(assignment_id and assignment_id in assignment_ids)


def _validate_case(case: Mapping[str, Any]) -> None:
    if case.get("schema") != CASE_SCHEMA:
        raise PreflightError("CASE_SCHEMA_INVALID")
    required = (
        "case_id", "teacher_name", "school_name", "component_name",
        "academic_year", "start_date", "end_date", "strategy", "pairs",
    )
    if any(not case.get(key) for key in required):
        raise PreflightError("CASE_REQUIRED_FIELD_MISSING")
    if case.get("strategy") != SUPPORTED_STRATEGY:
        raise PreflightError("CASE_STRATEGY_UNSUPPORTED")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _sid(case.get("start_date"))):
        raise PreflightError("CASE_START_DATE_INVALID")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _sid(case.get("end_date"))):
        raise PreflightError("CASE_END_DATE_INVALID")
    if _sid(case.get("start_date")) >= _sid(case.get("end_date")):
        raise PreflightError("CASE_PERIOD_INVALID")
    pairs = case.get("pairs") or []
    if not isinstance(pairs, list) or not pairs:
        raise PreflightError("CASE_PAIRS_INVALID")
    seen = set()
    for pair in pairs:
        source = _sid((pair or {}).get("source_class"))
        target = _sid((pair or {}).get("target_class"))
        if not source or not target or source == target:
            raise PreflightError("CASE_PAIR_INVALID")
        key = (_norm(source), _norm(target))
        if key in seen:
            raise PreflightError("CASE_PAIR_DUPLICATE")
        seen.add(key)


def _months_between(start_date: str, end_date: str) -> list[str]:
    y, m = map(int, start_date[:7].split("-"))
    out = []
    while f"{y:04d}-{m:02d}-01" < end_date:
        month = f"{y:04d}-{m:02d}"
        if month >= start_date[:7] and month <= end_date[:7]:
            out.append(month)
        m += 1
        if m == 13:
            y += 1
            m = 1
    return [month for month in out if month + "-01" < end_date]


def _in_period(day: str | None, start_date: str, end_date: str) -> bool:
    return bool(day and start_date <= day < end_date)


def _resolve_context(db, case: Mapping[str, Any]) -> dict[str, Any]:
    teacher_name = _sid(case["teacher_name"])
    school_name = _sid(case["school_name"])
    component_name = _sid(case["component_name"])
    academic_year = int(case["academic_year"])

    users = list(db.users.find(
        {"$or": [{"full_name": teacher_name}, {"name": teacher_name}]},
        {"_id": 0, "id": 1, "name": 1, "full_name": 1, "mantenedora_id": 1},
    ).limit(20))
    users = [u for u in users if _norm(u.get("full_name") or u.get("name")) == _norm(teacher_name)]
    if len(users) != 1:
        raise PreflightError(f"TEACHER_MATCH_COUNT_{len(users)}")
    user = users[0]
    teacher_id = _sid(user.get("id"))
    if not teacher_id:
        raise PreflightError("TEACHER_ID_MISSING")

    staff_rows = list(db.staff.find(
        {"user_id": teacher_id},
        {"_id": 0, "id": 1, "user_id": 1, "school_id": 1, "mantenedora_id": 1},
    ))
    if not staff_rows:
        raise PreflightError("STAFF_NOT_FOUND")

    schools = [
        row for row in db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1})
        if _norm(row.get("name")) == _norm(school_name)
    ]
    tenant_hints = {_sid(user.get("mantenedora_id")), *(_sid(r.get("mantenedora_id")) for r in staff_rows)}
    tenant_hints.discard("")
    if len(schools) > 1 and tenant_hints:
        schools = [s for s in schools if _sid(s.get("mantenedora_id")) in tenant_hints]
    if len(schools) != 1:
        raise PreflightError(f"SCHOOL_MATCH_COUNT_{len(schools)}")
    school = schools[0]
    school_id = _sid(school.get("id"))
    tenant_id = _sid(school.get("mantenedora_id"))

    staff_rows = [
        r for r in staff_rows
        if _sid(r.get("school_id")) in {"", school_id}
        and _sid(r.get("mantenedora_id")) in {"", tenant_id}
    ]
    staff_ids = {_sid(r.get("id")) for r in staff_rows if _sid(r.get("id"))}
    if not staff_ids:
        raise PreflightError("STAFF_NOT_IN_SCHOOL_SCOPE")
    actor_ids = {teacher_id, *staff_ids}

    wanted_names = []
    for pair in case["pairs"]:
        wanted_names += [_sid(pair["source_class"]), _sid(pair["target_class"])]
    classes = list(db.classes.find(
        {"school_id": school_id},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1, "mantenedora_id": 1},
    ))
    classes = [c for c in classes if _sid(c.get("mantenedora_id")) in {"", tenant_id}]
    class_ids: dict[str, str] = {}
    for name in sorted(set(wanted_names)):
        matches = sorted({
            _sid(c.get("id")) for c in classes
            if _norm(c.get("name")) == _norm(name)
            and _sid(c.get("academic_year")) in {"", str(academic_year)}
            and _sid(c.get("id"))
        })
        if len(matches) != 1:
            raise PreflightError(f"CLASS_MATCH_COUNT_{_fp(name, 8)}_{len(matches)}")
        class_ids[name] = matches[0]

    courses = list(db.courses.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}))
    math_ids = {
        _sid(c.get("id")) for c in courses
        if _sid(c.get("id"))
        and _sid(c.get("mantenedora_id")) in {"", tenant_id}
        and _norm(c.get("name")) == _norm(component_name)
    }
    if not math_ids:
        raise PreflightError("COMPONENT_IDENTITY_NOT_FOUND")

    legacy = list(db.teacher_assignments.find(
        {
            "staff_id": {"$in": sorted(staff_ids)},
            "academic_year": {"$in": [academic_year, str(academic_year)]},
        },
        ASSIGNMENT_PROJECTION,
    ))
    legacy = [
        r for r in legacy
        if _sid(r.get("school_id")) in {"", school_id}
        and _sid(r.get("mantenedora_id")) in {"", tenant_id}
    ]

    dvd = list(db.teacher_class_assignments.find(
        {"teacher_id": teacher_id}, ASSIGNMENT_PROJECTION
    ))
    dvd = [
        r for r in dvd
        if _sid(r.get("school_id")) in {"", school_id}
        and _sid(r.get("mantenedora_id")) in {"", tenant_id}
        and r.get("deleted") is not True
    ]

    assignment_ids = {_sid(r.get("id")) for r in legacy + dvd if _sid(r.get("id"))}

    target_component: dict[str, str] = {}
    target_names = {_sid(pair["target_class"]) for pair in case["pairs"]}
    for name in target_names:
        class_id = class_ids[name]
        dvd_exact = sorted({
            _component_id(r) for r in dvd
            if _sid(r.get("class_id")) == class_id
            and _component_id(r) in math_ids
            and ((r.get("diary_settings") or {}).get("enabled") is True)
        })
        legacy_active = sorted({
            _sid(r.get("course_id")) for r in legacy
            if _sid(r.get("class_id")) == class_id
            and _sid(r.get("course_id")) in math_ids
            and _norm(r.get("status")) in ACTIVE_STATUSES
        })
        candidates = dvd_exact or legacy_active
        if len(candidates) != 1:
            raise PreflightError(f"TARGET_COMPONENT_AMBIGUOUS_{_fp(name, 8)}_{len(candidates)}")
        target_component[name] = candidates[0]

    return {
        "teacher_id": teacher_id,
        "school_id": school_id,
        "tenant_id": tenant_id,
        "staff_ids": staff_ids,
        "actor_ids": actor_ids,
        "class_ids": class_ids,
        "math_ids": math_ids,
        "legacy_assignments": legacy,
        "dvd_assignments": dvd,
        "assignment_ids": assignment_ids,
        "target_component": target_component,
    }


def _find_rows_for_class(
    db,
    *,
    class_id: str,
    math_ids: set[str],
    start_date: str,
    end_date: str,
) -> tuple[list[dict], list[dict]]:
    canonical = list(db.content_entries.find(
        {
            "class_id": class_id,
            "$or": [
                {"component_id": {"$in": sorted(math_ids)}},
                {"course_id": {"$in": sorted(math_ids)}},
            ],
        },
        CONTENT_PROJECTION,
    ))
    canonical = [
        r for r in canonical
        if r.get("deleted") is not True
        and _in_period(_iso_day(r.get("date")), start_date, end_date)
    ]

    legacy = list(db.learning_objects.find(
        {"class_id": class_id, "course_id": {"$in": sorted(math_ids)}},
        CONTENT_PROJECTION,
    ))
    legacy = [
        r for r in legacy
        if _in_period(_iso_day(r.get("date")), start_date, end_date)
    ]
    return canonical, legacy


def _source_items_by_month(
    canonical: list[dict],
    legacy: list[dict],
    *,
    actor_ids: set[str],
    assignment_ids: set[str],
    months: list[str],
) -> dict[str, dict[str, Any]]:
    result = {}
    for month in months:
        c_rows = [r for r in canonical if (_iso_day(r.get("date")) or "").startswith(month)]
        l_rows = [r for r in legacy if (_iso_day(r.get("date")) or "").startswith(month)]
        c_own = [r for r in c_rows if _teacher_attributed(r, actor_ids, assignment_ids)]
        l_own = [r for r in l_rows if _teacher_attributed(r, actor_ids, assignment_ids)]
        c_foreign = [r for r in c_rows if not _teacher_attributed(r, actor_ids, assignment_ids)]
        l_foreign = [r for r in l_rows if not _teacher_attributed(r, actor_ids, assignment_ids)]

        blockers = []
        if c_own and l_own:
            blockers.append("SOURCE_STORAGE_MIXED_CANONICAL_AND_LEGACY")
        selected = c_own if c_own else l_own
        selected_kind = "content_entries" if c_own else "learning_objects" if l_own else None

        by_day: dict[str, list[dict]] = defaultdict(list)
        for row in selected:
            day = _iso_day(row.get("date"))
            if day:
                by_day[day].append(row)
        duplicate_days = sorted(day for day, rows in by_day.items() if len(rows) != 1)
        if duplicate_days:
            blockers.append("SOURCE_MULTIPLE_ROWS_SAME_DATE")

        foreign_days = {
            _iso_day(r.get("date")) for r in c_foreign + l_foreign if _iso_day(r.get("date"))
        }
        conflict_days = sorted(set(by_day) & foreign_days)
        if conflict_days:
            blockers.append("SOURCE_ACTOR_CONFLICT_ON_DATE")

        items = []
        for day in sorted(by_day):
            if len(by_day[day]) != 1:
                continue
            row = by_day[day][0]
            content = row.get("content") or ""
            if not str(content).strip():
                blockers.append("SOURCE_CONTENT_EMPTY")
                continue
            items.append({
                "source_date": day,
                "source_kind": selected_kind,
                "payload_fingerprint": _payload_fingerprint(row),
                "number_of_classes": int(row.get("number_of_classes") or 1),
            })

        result[month] = {
            "items": items,
            "blockers": sorted(set(blockers)),
            "foreign_row_count": len(c_foreign) + len(l_foreign),
            "canonical_row_count": len(c_own),
            "legacy_row_count": len(l_own),
        }
    return result


def _attendance_by_month(
    db,
    *,
    class_id: str,
    math_ids: set[str],
    actor_ids: set[str],
    assignment_ids: set[str],
    start_date: str,
    end_date: str,
    months: list[str],
) -> dict[str, dict[str, Any]]:
    rows = list(db.attendance.find(
        {"class_id": class_id, "course_id": {"$in": sorted(math_ids)}},
        ATTENDANCE_PROJECTION,
    ))
    rows = [r for r in rows if _in_period(_iso_day(r.get("date")), start_date, end_date)]
    out = {}
    for month in months:
        month_rows = [r for r in rows if (_iso_day(r.get("date")) or "").startswith(month)]
        own = [r for r in month_rows if _teacher_attributed(r, actor_ids, assignment_ids)]
        foreign = [r for r in month_rows if not _teacher_attributed(r, actor_ids, assignment_ids)]
        own_dates = sorted({_iso_day(r.get("date")) for r in own if _iso_day(r.get("date"))})
        foreign_dates = {_iso_day(r.get("date")) for r in foreign if _iso_day(r.get("date"))}
        conflict_dates = sorted(set(own_dates) & foreign_dates)
        out[month] = {
            "dates": own_dates,
            "document_count": len(own),
            "foreign_document_count": len(foreign),
            "actor_conflict_dates": conflict_dates,
        }
    return out


def _assignment_for_date(
    dvd_rows: Iterable[Mapping[str, Any]],
    *,
    class_id: str,
    component_id: str,
    teacher_id: str,
    target_date: str,
) -> dict[str, Any]:
    rows = [
        r for r in dvd_rows
        if _sid(r.get("class_id")) == class_id
        and _sid(r.get("teacher_id")) == teacher_id
        and r.get("deleted") is not True
        and ((r.get("diary_settings") or {}).get("enabled") is True)
        and (_component_id(r) in {"", component_id})
    ]

    def active(r: Mapping[str, Any]) -> bool:
        valid_from = _sid(r.get("valid_from"))
        valid_until = _sid(r.get("valid_until"))
        return bool(valid_from and valid_from <= target_date and (not valid_until or valid_until >= target_date))

    def choose(candidates: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        exact = [r for r in candidates if _component_id(r) == component_id]
        return exact or [r for r in candidates if not _component_id(r)]

    active_rows = choose([r for r in rows if active(r)])
    if len(active_rows) == 1:
        return {
            "status": "RESOLVED",
            "assignment_fingerprint": _fp(active_rows[0].get("id")),
            "historical_backfill": False,
        }
    if len(active_rows) > 1:
        return {"status": "AMBIGUOUS_ACTIVE", "assignment_fingerprint": None, "historical_backfill": False}

    historical = choose([
        r for r in rows
        if _sid(r.get("valid_from")) and target_date < _sid(r.get("valid_from"))
    ])
    if len(historical) == 1:
        return {
            "status": "RESOLVED",
            "assignment_fingerprint": _fp(historical[0].get("id")),
            "historical_backfill": True,
        }
    if len(historical) > 1:
        return {"status": "AMBIGUOUS_HISTORICAL", "assignment_fingerprint": None, "historical_backfill": True}
    return {"status": "NOT_FOUND", "assignment_fingerprint": None, "historical_backfill": False}


def _occupied_dates(
    canonical: list[dict], legacy: list[dict]
) -> set[str]:
    return {
        day
        for row in canonical + legacy
        for day in [_iso_day(row.get("date"))]
        if day
    }


def _build_month_plan(
    *,
    month: str,
    source: Mapping[str, Any],
    target_attendance: Mapping[str, Any],
    occupied_dates: set[str],
    assignment_by_date: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    blockers = list(source.get("blockers") or [])
    source_items = list(source.get("items") or [])
    target_dates = list(target_attendance.get("dates") or [])

    if target_attendance.get("actor_conflict_dates"):
        blockers.append("TARGET_ATTENDANCE_ACTOR_CONFLICT")
    if len(source_items) != len(target_dates):
        blockers.append("MONTHLY_COUNT_MISMATCH")
    occupied_targets = sorted(set(target_dates) & occupied_dates)
    if occupied_targets:
        blockers.append("TARGET_DATE_ALREADY_HAS_CONTENT")

    unresolved = [
        day for day in target_dates
        if (assignment_by_date.get(day) or {}).get("status") != "RESOLVED"
    ]
    if unresolved:
        blockers.append("TARGET_ASSIGNMENT_NOT_UNIQUE")

    items = []
    if not blockers:
        for ordinal, (src, target_date) in enumerate(zip(source_items, target_dates), 1):
            assignment = assignment_by_date[target_date]
            items.append({
                "ordinal": ordinal,
                "source_date": src["source_date"],
                "target_date": target_date,
                "source_kind": src["source_kind"],
                "payload_fingerprint": src["payload_fingerprint"],
                "number_of_classes": src["number_of_classes"],
                "target_assignment_fingerprint": assignment["assignment_fingerprint"],
                "historical_backfill": bool(assignment.get("historical_backfill")),
            })

    return {
        "month": month,
        "status": "READY_TO_APPLY" if not blockers else "BLOCKED_REVIEW_REQUIRED",
        "blockers": sorted(set(blockers)),
        "source_content_count": len(source_items),
        "source_canonical_count": int(source.get("canonical_row_count") or 0),
        "source_legacy_count": int(source.get("legacy_row_count") or 0),
        "source_foreign_row_count": int(source.get("foreign_row_count") or 0),
        "target_attendance_date_count": len(target_dates),
        "target_attendance_document_count": int(target_attendance.get("document_count") or 0),
        "target_existing_content_on_anchor_dates": len(occupied_targets),
        "target_unresolved_assignment_date_count": len(unresolved),
        "items": items,
    }


def run_live_preflight(case: Mapping[str, Any]) -> dict[str, Any]:
    _validate_case(case)
    uri = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "sigesc")
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    try:
        client.admin.command("ping")
        db = client[db_name]
        context = _resolve_context(db, case)
        start_date = _sid(case["start_date"])
        end_date = _sid(case["end_date"])
        months = _months_between(start_date, end_date)

        pair_results = []
        for pair in case["pairs"]:
            source_name = _sid(pair["source_class"])
            target_name = _sid(pair["target_class"])
            source_id = context["class_ids"][source_name]
            target_id = context["class_ids"][target_name]
            target_component = context["target_component"][target_name]

            source_canonical, source_legacy = _find_rows_for_class(
                db,
                class_id=source_id,
                math_ids=context["math_ids"],
                start_date=start_date,
                end_date=end_date,
            )
            source_months = _source_items_by_month(
                source_canonical,
                source_legacy,
                actor_ids=context["actor_ids"],
                assignment_ids=context["assignment_ids"],
                months=months,
            )

            target_attendance = _attendance_by_month(
                db,
                class_id=target_id,
                math_ids=context["math_ids"],
                actor_ids=context["actor_ids"],
                assignment_ids=context["assignment_ids"],
                start_date=start_date,
                end_date=end_date,
                months=months,
            )

            target_canonical, target_legacy = _find_rows_for_class(
                db,
                class_id=target_id,
                math_ids=context["math_ids"],
                start_date=start_date,
                end_date=end_date,
            )
            occupied = _occupied_dates(target_canonical, target_legacy)

            month_results = []
            for month in months:
                assignment_by_date = {
                    day: _assignment_for_date(
                        context["dvd_assignments"],
                        class_id=target_id,
                        component_id=target_component,
                        teacher_id=context["teacher_id"],
                        target_date=day,
                    )
                    for day in target_attendance[month]["dates"]
                }
                month_results.append(_build_month_plan(
                    month=month,
                    source=source_months[month],
                    target_attendance=target_attendance[month],
                    occupied_dates=occupied,
                    assignment_by_date=assignment_by_date,
                ))

            pair_results.append({
                "source_class": source_name,
                "target_class": target_name,
                "months": month_results,
            })

        all_months = [month for pair in pair_results for month in pair["months"]]
        ready_count = sum(1 for month in all_months if month["status"] == "READY_TO_APPLY")
        blocked_count = len(all_months) - ready_count
        manifest = {
            "schema": SCHEMA,
            "case_id": _sid(case["case_id"]),
            "strategy": _sid(case["strategy"]),
            "teacher_name": _sid(case["teacher_name"]),
            "school_name": _sid(case["school_name"]),
            "component_name": _sid(case["component_name"]),
            "academic_year": int(case["academic_year"]),
            "start_date": start_date,
            "end_date": end_date,
            "pairs": pair_results,
            "summary": {
                "month_total": len(all_months),
                "ready_to_apply": ready_count,
                "blocked_review_required": blocked_count,
                "overall_status": "READY_TO_APPLY" if blocked_count == 0 else "BLOCKED_REVIEW_REQUIRED",
            },
            "boundaries": {
                "mongo_reads_only": True,
                "production_writes": False,
                "attendance_records_read": False,
                "student_data_read": False,
                "enrollment_data_read": False,
                "grades_read": False,
                "source_payload_plaintext_read_for_fingerprint": True,
                "source_payload_plaintext_emitted": False,
                "technical_ids_emitted": False,
                "learning_objects_written": False,
                "content_entries_written": False,
                "attendance_written": False,
            },
        }
        manifest["manifest_hash"] = _canonical_hash(manifest)
        return manifest
    finally:
        client.close()


def load_case_from_env() -> dict[str, Any]:
    raw = os.getenv("SIBLING_RECONSTRUCTION_CASE_B64", "")
    if not raw:
        raise PreflightError("CASE_ENV_MISSING")
    try:
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise PreflightError("CASE_ENV_INVALID") from exc


if __name__ == "__main__":
    print(json.dumps(run_live_preflight(load_case_from_env()), ensure_ascii=False, sort_keys=True))
