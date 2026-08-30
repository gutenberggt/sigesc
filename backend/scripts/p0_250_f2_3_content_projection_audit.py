#!/usr/bin/env python3
"""P0 #250 F2.3 — read-only parity audit for Objetos de Conhecimento.

The collector compares the two effective read models involved in the reported
5º ANO A case without changing production data:

- management legacy view: ``learning_objects`` for the target class/month;
- professor DVD view: the same history composition used by
  ``list_assignment_content_history`` for the professor's content-enabled
  assignments, aggregated like the frontend ``contentDvdBridge``;
- when no content-enabled DVD diary exists, the professor frontend falls back to
  the same legacy class/month reader. That fallback is modeled explicitly rather
  than treated as an audit failure.

Only structural metadata is emitted. Record ids, content text, teacher ids,
student data and authentication material are never included in the result.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

ACADEMIC_YEAR = 2026
TARGET_MONTH = 6
TEACHER_NAME = "Abadia Alves Martins"
SCHOOL_NAME = "E M E I E F Jose Pereira Barbosa"
CLASS_NAME = "5º ANO A"
EXPECTED_COMPONENTS = 9


def _sid(value: Any) -> str:
    return "" if value is None else str(value)


def _date(value: Any) -> str:
    return _sid(value)[:10]


def _component_id(row: dict[str, Any]) -> str:
    return _sid(row.get("component_id") or row.get("course_id"))


def _slot(row: dict[str, Any]) -> tuple[str, str]:
    return (_date(row.get("date")), _component_id(row))


def _dedupe_professor_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror the frontend bridge's source/id/component defensive dedupe."""
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    fallback_index = 0
    for row in rows:
        source = _sid(row.get("source") or "content_entries")
        record_id = _sid(row.get("id"))
        component_id = _component_id(row)
        if record_id:
            key = (source, record_id, component_id)
        else:
            fallback_index += 1
            key = (source, f"missing-id-{fallback_index}", component_id)
        unique[key] = row
    return list(unique.values())


def _matching_scopes(
    assignment_scopes: list[dict[str, Any]], component_id: str
) -> list[dict[str, Any]]:
    return [
        scope
        for scope in assignment_scopes
        if not _sid(scope.get("component_id"))
        or _sid(scope.get("component_id")) == component_id
    ]


def _legacy_visibility_reason(
    row: dict[str, Any], assignment_scopes: list[dict[str, Any]]
) -> str:
    """Classify whether a legacy slot should be in professor DVD history."""
    component_id = _component_id(row)
    on_date = _date(row.get("date"))
    scopes = _matching_scopes(assignment_scopes, component_id)
    if not scopes:
        return "OUTSIDE_PROFESSOR_COMPONENT_SCOPE"

    valid_from_values = [
        _date(scope.get("valid_from")) for scope in scopes if _date(scope.get("valid_from"))
    ]
    if not valid_from_values:
        return "ASSIGNMENT_VALID_FROM_MISSING"

    # The history bridge admits legacy rows up to and including each assignment's
    # cutover date. The frontend aggregates all authorized sibling assignments.
    if any(on_date and on_date <= valid_from for valid_from in valid_from_values):
        return "EXPECTED_IN_PROFESSOR_HISTORY"
    return "LEGACY_AFTER_COMPONENT_CUTOVER"


def analyze_content_projection(
    *,
    management_rows: list[dict[str, Any]],
    professor_rows: list[dict[str, Any]],
    assignment_scopes: list[dict[str, Any]],
    target_teacher_id: str,
    course_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compare management legacy slots with professor DVD history slots.

    Comparison is intentionally structural. A slot is ``date + component``;
    content text and record ids never leave this function.
    """
    course_names = course_names or {}
    professor_rows = _dedupe_professor_rows(professor_rows)

    management_by_slot: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    professor_by_slot: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in management_rows:
        if _date(row.get("date")) and _component_id(row):
            management_by_slot[_slot(row)].append(row)
    for row in professor_rows:
        if _date(row.get("date")) and _component_id(row):
            professor_by_slot[_slot(row)].append(row)

    management_slots = set(management_by_slot)
    professor_slots = set(professor_by_slot)
    common_slots = management_slots & professor_slots
    management_only_slots = sorted(management_slots - professor_slots)
    professor_only_slots = sorted(professor_slots - management_slots)

    management_only_details: list[dict[str, Any]] = []
    unexpected_management_only = 0
    scope_explained_management_only = 0
    cutover_explained_management_only = 0
    missing_valid_from_management_only = 0

    for date_value, component_id in management_only_slots:
        rows = management_by_slot[(date_value, component_id)]
        reasons = {_legacy_visibility_reason(row, assignment_scopes) for row in rows}
        if "EXPECTED_IN_PROFESSOR_HISTORY" in reasons:
            reason = "EXPECTED_IN_PROFESSOR_HISTORY"
            unexpected_management_only += 1
        elif "ASSIGNMENT_VALID_FROM_MISSING" in reasons:
            reason = "ASSIGNMENT_VALID_FROM_MISSING"
            missing_valid_from_management_only += 1
        elif "LEGACY_AFTER_COMPONENT_CUTOVER" in reasons:
            reason = "LEGACY_AFTER_COMPONENT_CUTOVER"
            cutover_explained_management_only += 1
        else:
            reason = "OUTSIDE_PROFESSOR_COMPONENT_SCOPE"
            scope_explained_management_only += 1

        management_only_details.append({
            "date": date_value,
            "course_id": component_id,
            "course_name": course_names.get(component_id) or "",
            "reason": reason,
            "management_record_count": len(rows),
            "recorded_by_target_professor_count": sum(
                1 for row in rows if _sid(row.get("recorded_by")) == _sid(target_teacher_id)
            ),
            "recorded_by_other_or_unknown_count": sum(
                1 for row in rows if _sid(row.get("recorded_by")) != _sid(target_teacher_id)
            ),
        })

    professor_only_details: list[dict[str, Any]] = []
    for date_value, component_id in professor_only_slots:
        rows = professor_by_slot[(date_value, component_id)]
        sources = sorted({_sid(row.get("source") or "content_entries") for row in rows})
        professor_only_details.append({
            "date": date_value,
            "course_id": component_id,
            "course_name": course_names.get(component_id) or "",
            "sources": sources,
            "professor_record_count": len(rows),
        })

    date_summaries: list[dict[str, Any]] = []
    all_dates = sorted(
        {date_value for date_value, _ in management_slots | professor_slots},
        reverse=True,
    )
    for date_value in all_dates:
        mgmt = {component for date_key, component in management_slots if date_key == date_value}
        prof = {component for date_key, component in professor_slots if date_key == date_value}
        date_summaries.append({
            "date": date_value,
            "management_component_count": len(mgmt),
            "professor_component_count": len(prof),
            "common_component_count": len(mgmt & prof),
            "management_only_component_count": len(mgmt - prof),
            "professor_only_component_count": len(prof - mgmt),
        })

    canonical_professor_rows = sum(
        1 for row in professor_rows if _sid(row.get("source")) == "content_entries"
    )
    legacy_professor_rows = sum(
        1 for row in professor_rows if _sid(row.get("source")) == "learning_objects"
    )

    assignment_component_ids = sorted({
        _sid(scope.get("component_id"))
        for scope in assignment_scopes
        if _sid(scope.get("component_id"))
    })
    class_wide_assignment_count = sum(
        1 for scope in assignment_scopes if not _sid(scope.get("component_id"))
    )

    classification = "CONTENT_PROJECTION_PARITY"
    if len(assignment_component_ids) != EXPECTED_COMPONENTS and not class_wide_assignment_count:
        classification = "PROFESSOR_CONTENT_ENTITLEMENT_DRIFT"
    elif unexpected_management_only or missing_valid_from_management_only:
        classification = "CONTENT_PROJECTION_GAP_WITHIN_AUTHORIZED_SCOPE"
    elif management_only_slots:
        classification = "CONTENT_VIEW_DIFFERENCE_EXPLAINED_BY_SCOPE_OR_CUTOVER"
    elif professor_only_slots:
        classification = "CONTENT_CANONICAL_ONLY_ROWS_PRESENT"

    return {
        "classification": classification,
        "assignment_scope_count": len(assignment_scopes),
        "assignment_component_count": len(assignment_component_ids),
        "class_wide_assignment_count": class_wide_assignment_count,
        "management_legacy_record_count": len(management_rows),
        "management_slot_count": len(management_slots),
        "professor_projection_record_count": len(professor_rows),
        "professor_slot_count": len(professor_slots),
        "professor_legacy_record_count": legacy_professor_rows,
        "professor_canonical_record_count": canonical_professor_rows,
        "common_slot_count": len(common_slots),
        "management_only_slot_count": len(management_only_slots),
        "professor_only_slot_count": len(professor_only_slots),
        "unexpected_management_only_slot_count": unexpected_management_only,
        "scope_explained_management_only_slot_count": scope_explained_management_only,
        "cutover_explained_management_only_slot_count": cutover_explained_management_only,
        "missing_valid_from_management_only_slot_count": missing_valid_from_management_only,
        "management_only_slots": management_only_details,
        "professor_only_slots": professor_only_details,
        "date_summaries": date_summaries,
    }


def analyze_legacy_fallback_projection(
    *,
    management_rows: list[dict[str, Any]],
    legacy_assignment_course_ids: list[str],
    target_teacher_id: str,
    course_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Model the effective professor read when the DVD bridge has no candidates.

    In Anos Iniciais, LearningObjects.js requests class + academic_year + month
    without a component filter. When contentDvdBridge resolves zero content
    diaries, it leaves that GET untouched, so professor and management consume the
    same legacy dataset for the same tenant/class/month. This helper records that
    expected parity and adds provenance counters without emitting identities.
    """
    course_names = course_names or {}
    course_ids = sorted({_sid(value) for value in legacy_assignment_course_ids if _sid(value)})
    assignment_scopes = [
        {"component_id": course_id, "valid_from": None, "valid_until": None}
        for course_id in course_ids
    ]
    professor_rows = [dict(row, source="learning_objects") for row in management_rows]
    analysis = analyze_content_projection(
        management_rows=management_rows,
        professor_rows=professor_rows,
        assignment_scopes=assignment_scopes,
        target_teacher_id=target_teacher_id,
        course_names=course_names,
    )
    analysis["projection_mode"] = "LEGACY_FALLBACK"
    analysis["legacy_teacher_assignment_component_count"] = len(course_ids)

    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in management_rows:
        date_value = _date(row.get("date"))
        if date_value:
            by_date[date_value].append(row)
    analysis["legacy_date_provenance"] = [
        {
            "date": date_value,
            "record_count": len(rows),
            "component_count": len({_component_id(row) for row in rows if _component_id(row)}),
            "recorded_by_target_professor_count": sum(
                1 for row in rows if _sid(row.get("recorded_by")) == _sid(target_teacher_id)
            ),
            "recorded_by_other_or_unknown_count": sum(
                1 for row in rows if _sid(row.get("recorded_by")) != _sid(target_teacher_id)
            ),
        }
        for date_value, rows in sorted(by_date.items(), reverse=True)
    ]

    if len(course_ids) == EXPECTED_COMPONENTS:
        analysis["classification"] = "CONTENT_LEGACY_FALLBACK_PARITY_EXPECTED"
    else:
        analysis["classification"] = "PROFESSOR_CONTENT_ENTITLEMENT_DRIFT"
    return analysis


async def _unique_one(collection, query: dict[str, Any], projection: dict[str, int], label: str) -> dict[str, Any]:
    docs = await collection.find(query, projection).limit(3).to_list(3)
    if len(docs) != 1:
        raise RuntimeError(f"P0_250_F2_3_IDENTITY_{label}_MATCHES:{len(docs)}")
    return docs[0]


async def _run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("P0_250_F2_3_MONGO_URL_MISSING")

    from motor.motor_asyncio import AsyncIOMotorClient  # pylint: disable=import-outside-toplevel
    from services.content_history_bridge import list_assignment_content_history  # pylint: disable=import-outside-toplevel
    from services.teacher_diaries import list_teacher_diaries  # pylint: disable=import-outside-toplevel

    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=10000)
    db = client[db_name]

    try:
        school = await _unique_one(
            db.schools,
            {"name": SCHOOL_NAME},
            {"_id": 0, "id": 1, "mantenedora_id": 1},
            "SCHOOL",
        )
        user = await _unique_one(
            db.users,
            {"full_name": TEACHER_NAME},
            {
                "_id": 0,
                "id": 1,
                "email": 1,
                "role": 1,
                "roles": 1,
                "mantenedora_id": 1,
                "school_links": 1,
            },
            "USER",
        )
        if user.get("role") != "professor":
            raise RuntimeError(f"P0_250_F2_3_PRIMARY_ROLE_NOT_PROFESSOR:{user.get('role')}")

        staff_query: dict[str, Any] = {"$or": [{"user_id": user["id"]}]}
        if user.get("email"):
            staff_query["$or"].append({"email": user["email"]})
        staff = await _unique_one(
            db.staff,
            staff_query,
            {"_id": 0, "id": 1},
            "STAFF",
        )
        class_doc = await _unique_one(
            db.classes,
            {
                "school_id": school["id"],
                "name": CLASS_NAME,
                "academic_year": ACADEMIC_YEAR,
            },
            {
                "_id": 0,
                "id": 1,
                "school_id": 1,
                "mantenedora_id": 1,
                "academic_year": 1,
            },
            "CLASS",
        )

        month_start = f"{ACADEMIC_YEAR}-{TARGET_MONTH:02d}-01"
        month_end = (
            f"{ACADEMIC_YEAR + 1}-01-01"
            if TARGET_MONTH == 12
            else f"{ACADEMIC_YEAR}-{TARGET_MONTH + 1:02d}-01"
        )
        management_rows = await db.learning_objects.find(
            {
                "class_id": class_doc["id"],
                "academic_year": ACADEMIC_YEAR,
                "date": {"$gte": month_start, "$lt": month_end},
            },
            {
                "_id": 0,
                "id": 1,
                "class_id": 1,
                "course_id": 1,
                "date": 1,
                "academic_year": 1,
                "recorded_by": 1,
            },
        ).to_list(5000)

        legacy_assignments = await db.teacher_assignments.find(
            {
                "staff_id": staff["id"],
                "class_id": class_doc["id"],
                "academic_year": ACADEMIC_YEAR,
                "status": {"$in": ["ativo", "active"]},
            },
            {"_id": 0, "course_id": 1},
        ).to_list(500)
        legacy_assignment_course_ids = [
            _sid(row.get("course_id")) for row in legacy_assignments if _sid(row.get("course_id"))
        ]

        reference_date = datetime.now(timezone.utc).date().isoformat()
        diaries_payload = await list_teacher_diaries(
            db,
            user,
            academic_year=ACADEMIC_YEAR,
            reference_date=reference_date,
            active_mantenedora_id=user.get("mantenedora_id") or class_doc.get("mantenedora_id"),
        )
        target_diaries = [
            item
            for item in diaries_payload.get("items", [])
            if _sid(item.get("class_id")) == _sid(class_doc["id"])
            and (item.get("capabilities") or {}).get("content_enabled") is True
        ]

        professor_history_rows: list[dict[str, Any]] = []
        assignment_scopes: list[dict[str, Any]] = []
        for diary in target_diaries:
            assignment_scopes.append({
                "component_id": diary.get("component_id"),
                "valid_from": diary.get("valid_from"),
                "valid_until": diary.get("valid_until"),
            })
            history = await list_assignment_content_history(
                db,
                user,
                assignment_id=diary["assignment_id"],
                class_id=class_doc["id"],
                active_mantenedora_id=user.get("mantenedora_id") or class_doc.get("mantenedora_id"),
            )
            for row in history.get("items", []):
                row_date = _date(row.get("date"))
                row_year = row.get("academic_year")
                if month_start <= row_date < month_end and (
                    row_year in (None, ACADEMIC_YEAR, str(ACADEMIC_YEAR))
                ):
                    professor_history_rows.append(row)

        component_ids = {
            _component_id(row) for row in management_rows + professor_history_rows if _component_id(row)
        }
        component_ids.update(legacy_assignment_course_ids)
        component_ids.update(
            _sid(scope.get("component_id"))
            for scope in assignment_scopes
            if _sid(scope.get("component_id"))
        )
        courses = await db.courses.find(
            {"id": {"$in": sorted(component_ids)}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(max(1, len(component_ids)))
        course_names = {_sid(row.get("id")): _sid(row.get("name")) for row in courses}

        if target_diaries:
            analysis = analyze_content_projection(
                management_rows=management_rows,
                professor_rows=professor_history_rows,
                assignment_scopes=assignment_scopes,
                target_teacher_id=_sid(user["id"]),
                course_names=course_names,
            )
            analysis["projection_mode"] = "DVD_HISTORY"
            analysis["legacy_teacher_assignment_component_count"] = len(set(legacy_assignment_course_ids))
        else:
            analysis = analyze_legacy_fallback_projection(
                management_rows=management_rows,
                legacy_assignment_course_ids=legacy_assignment_course_ids,
                target_teacher_id=_sid(user["id"]),
                course_names=course_names,
            )

        analysis["dvd_content_diary_count"] = len(target_diaries)
        analysis["dvd_blocked_diary_count"] = int(diaries_payload.get("blocked_total") or 0)

        return {
            "schema": "P0_250_F2_3_CONTENT_PROJECTION_AUDIT_V2",
            "status": "PASS",
            "classification": analysis["classification"],
            "database_mutation": False,
            "production_writes": False,
            "http_methods": [],
            "mongo_reads_only": True,
            "record_content_emitted": False,
            "record_ids_emitted": False,
            "teacher_ids_emitted": False,
            "student_ids_emitted": False,
            "student_pii_emitted": False,
            "access_token_used": False,
            "target": {
                "academic_year": ACADEMIC_YEAR,
                "month": TARGET_MONTH,
                "school": SCHOOL_NAME,
                "class": CLASS_NAME,
            },
            "analysis": analysis,
        }
    finally:
        client.close()


def run_live_audit() -> dict[str, Any]:
    return asyncio.run(_run_live_audit())


def main() -> None:
    payload = run_live_audit()
    print(
        "P0_250_F2_3_AUDIT_JSON="
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
