#!/usr/bin/env python3
"""P0 #250 F2.4 — read-only runtime contract audit for Objetos de Conhecimento.

This collector does not call the production HTTP API. It evaluates, against the
same production MongoDB state, the two code paths that decide the professor
screen's read route:

1. frontend ``contentDvdBridge``: if /professor/diarios exposes no
   ``content_enabled`` diary for the target class, the GET /learning-objects
   request is left untouched (legacy fallback);
2. backend ``legacy_content_dvd_guard``: the legacy endpoint returns 409 whenever
   an enabled/vigente ``teacher_class_assignment`` matches the professor/class,
   even when that assignment is not present in /professor/diarios after canonical
   authorization.

Only structural counters and non-sensitive class metadata are emitted. No
content text, record ids, teacher ids, student ids, student data, auth material,
or grade values are emitted. MongoDB access is read-only.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from typing import Any

ACADEMIC_YEAR = 2026
TARGET_MONTH = 6
TEACHER_NAME = "Abadia Alves Martins"
SCHOOL_NAME = "E M E I E F Jose Pereira Barbosa"
CLASS_NAME = "5º ANO A"
EXPECTED_COMPONENTS = 9
REPORTED_DATES = ("2026-06-30", "2026-06-29", "2026-06-27", "2026-06-26")


def _sid(value: Any) -> str:
    return "" if value is None else str(value)


def analyze_runtime_contract(
    *,
    content_enabled_diary_count: int,
    legacy_guard_match_count: int,
    legacy_record_count: int,
    teacher_assignment_component_count: int,
    blocked_diary_count: int = 0,
) -> dict[str, Any]:
    """Classify the professor runtime route without reproducing business rules.

    The inputs are produced by the canonical services/queries themselves. This
    function only states the observable contract implied by those results.
    """
    frontend_route = "CONTENT_ENTRIES_DVD" if content_enabled_diary_count > 0 else "LEARNING_OBJECTS_LEGACY"
    legacy_status = 409 if legacy_guard_match_count > 0 else 200

    if content_enabled_diary_count == 0 and legacy_guard_match_count > 0:
        classification = "CONTENT_RUNTIME_LEGACY_FALLBACK_BLOCKED"
        parity = False
        stale_ui_risk = True
    elif content_enabled_diary_count == 0:
        classification = "CONTENT_RUNTIME_LEGACY_FALLBACK_AVAILABLE"
        parity = True
        stale_ui_risk = False
    elif legacy_guard_match_count > 0:
        classification = "CONTENT_RUNTIME_DVD_REWRITE_EXPECTED"
        parity = True
        stale_ui_risk = False
    else:
        classification = "CONTENT_RUNTIME_DVD_GUARD_DRIFT"
        parity = False
        stale_ui_risk = False

    if teacher_assignment_component_count != EXPECTED_COMPONENTS:
        classification = "PROFESSOR_CONTENT_ENTITLEMENT_DRIFT"
        parity = False

    return {
        "classification": classification,
        "runtime_contract_parity": parity,
        "frontend_expected_route": frontend_route,
        "backend_legacy_expected_status": legacy_status,
        "content_enabled_diary_count": content_enabled_diary_count,
        "legacy_guard_match_count": legacy_guard_match_count,
        "legacy_record_count": legacy_record_count,
        "teacher_assignment_component_count": teacher_assignment_component_count,
        "blocked_diary_count": blocked_diary_count,
        "stale_ui_risk_if_previous_records_exist": stale_ui_risk,
    }


async def _unique_one(collection, query: dict[str, Any], projection: dict[str, int], label: str) -> dict[str, Any]:
    docs = await collection.find(query, projection).limit(3).to_list(3)
    if len(docs) != 1:
        raise RuntimeError(f"P0_250_F2_4_IDENTITY_{label}_MATCHES:{len(docs)}")
    return docs[0]


async def _run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("P0_250_F2_4_MONGO_URL_MISSING")

    from motor.motor_asyncio import AsyncIOMotorClient  # pylint: disable=import-outside-toplevel
    from services.legacy_content_dvd_guard import build_professor_dvd_query  # pylint: disable=import-outside-toplevel
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
            raise RuntimeError(f"P0_250_F2_4_PRIMARY_ROLE_NOT_PROFESSOR:{user.get('role')}")

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
                "education_level": 1,
                "nivel_ensino": 1,
                "grade_level": 1,
                "grade": 1,
            },
            "CLASS",
        )

        reference_date = date.today().isoformat()
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
        ]
        content_enabled_diaries = [
            item
            for item in target_diaries
            if (item.get("capabilities") or {}).get("content_enabled") is True
        ]

        guard_query = build_professor_dvd_query(
            user,
            class_id=class_doc["id"],
            course_id=None,
            on_date=reference_date,
        )
        legacy_guard_match_count = 0
        if guard_query:
            legacy_guard_match_count = await db.teacher_class_assignments.count_documents(guard_query)

        legacy_assignments = await db.teacher_assignments.find(
            {
                "staff_id": staff["id"],
                "class_id": class_doc["id"],
                "academic_year": ACADEMIC_YEAR,
                "status": {"$in": ["ativo", "active"]},
            },
            {"_id": 0, "course_id": 1},
        ).to_list(500)
        teacher_assignment_component_count = len(
            {_sid(row.get("course_id")) for row in legacy_assignments if _sid(row.get("course_id"))}
        )

        month_start = f"{ACADEMIC_YEAR}-{TARGET_MONTH:02d}-01"
        month_end = (
            f"{ACADEMIC_YEAR + 1}-01-01"
            if TARGET_MONTH == 12
            else f"{ACADEMIC_YEAR}-{TARGET_MONTH + 1:02d}-01"
        )
        legacy_query: dict[str, Any] = {
            "class_id": class_doc["id"],
            "academic_year": ACADEMIC_YEAR,
            "date": {"$gte": month_start, "$lt": month_end},
        }
        if class_doc.get("mantenedora_id"):
            legacy_query["mantenedora_id"] = class_doc["mantenedora_id"]
        legacy_rows = await db.learning_objects.find(
            legacy_query,
            {"_id": 0, "date": 1, "course_id": 1},
        ).sort("date", -1).to_list(1000)

        reported_date_counts = {
            target_date: sum(1 for row in legacy_rows if _sid(row.get("date"))[:10] == target_date)
            for target_date in REPORTED_DATES
        }

        analysis = analyze_runtime_contract(
            content_enabled_diary_count=len(content_enabled_diaries),
            legacy_guard_match_count=legacy_guard_match_count,
            legacy_record_count=len(legacy_rows),
            teacher_assignment_component_count=teacher_assignment_component_count,
            blocked_diary_count=int(diaries_payload.get("blocked_total") or 0),
        )
        analysis["target_diary_count"] = len(target_diaries)
        analysis["reported_date_record_counts"] = reported_date_counts
        analysis["class_metadata"] = {
            "education_level": class_doc.get("education_level") or class_doc.get("nivel_ensino"),
            "grade_level": class_doc.get("grade_level") or class_doc.get("grade"),
        }
        analysis["reference_date"] = reference_date

        return {
            "schema": "P0_250_F2_4_CONTENT_RUNTIME_CONTRACT_AUDIT_V1",
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


if __name__ == "__main__":
    print(json.dumps(run_live_audit(), ensure_ascii=False))
