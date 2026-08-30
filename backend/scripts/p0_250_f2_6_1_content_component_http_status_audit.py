#!/usr/bin/env python3
"""P0 #250 F2.6.1 — read-only HTTP-status audit for Objetos de Conhecimento.

Purpose
=======
The first F2.6 production run proved that the professor class-wide
``GET /learning-objects`` can still return HTTP 409 after F2.5, but the collector
incorrectly treated that expected diagnostic state as fatal. This collector
makes HTTP status itself part of the evidence.

For E M E I E F Jose Pereira Barbosa / 5º ANO A / 2026 it compares April,
May and June, per legacy teacher component:
- MongoDB legacy record counts in the target tenant;
- professor class-wide GET status/count;
- professor component-scoped GET status/count;
- tenant-scoped super-admin GET status/count;
- raw/current teacher_class_assignments counts by component.

Privacy / mutation boundary
===========================
- MongoDB reads only;
- application HTTP GET only;
- no login endpoint;
- ephemeral tokens stay only in process memory;
- no record content, record ids, assignment ids, teacher ids or student data is
  emitted.
"""

from __future__ import annotations

import json
import os
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from typing import Any

from pymongo import MongoClient

ACADEMIC_YEAR = 2026
TARGET_MONTHS = (4, 5, 6)
TEACHER_NAME = "Abadia Alves Martins"
SUPERADMIN_NAME = "Gutenberg Barroso"
SCHOOL_NAME = "E M E I E F Jose Pereira Barbosa"
CLASS_NAME = "5º ANO A"
EXPECTED_COMPONENTS = 9
API_BASE = os.environ.get("P0_250_F2_6_1_API_BASE", "http://127.0.0.1:8001/api").rstrip("/")

MONGO_MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
    ".drop(", ".drop_database(",
)
HTTP_WRITE_MARKERS = (
    "method=\"POST\"", "method='POST'", "method=\"PUT\"", "method='PUT'",
    "method=\"PATCH\"", "method='PATCH'", "method=\"DELETE\"", "method='DELETE'",
)


def _sid(value: Any) -> str:
    return "" if value is None else str(value)


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).casefold().strip()


def _focus_component(name: str) -> str | None:
    normalized = _norm(name)
    if "portugues" in normalized or "lingua portuguesa" in normalized:
        return "PORTUGUES"
    if "matemat" in normalized:
        return "MATEMATICA"
    return None


def _month_bounds(month: int) -> tuple[str, str]:
    start = f"{ACADEMIC_YEAR}-{month:02d}-01"
    end = f"{ACADEMIC_YEAR + 1}-01-01" if month == 12 else f"{ACADEMIC_YEAR}-{month + 1:02d}-01"
    return start, end


def _counts_by_component(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(
        _sid(row.get("course_id") or row.get("component_id"))
        for row in rows
        if row.get("course_id") or row.get("component_id")
    )


def _api_get_result(token: str, path: str, params=None, extra_headers=None) -> dict[str, Any]:
    """Return only status plus JSON data for successful GETs.

    HTTP errors such as the DVD legacy 409 are evidence, not collector failures.
    Error bodies are deliberately not read or emitted.
    """
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{API_BASE}{path}" + (f"?{query}" if query else "")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "sigesc-p0-250-f2-6-1-http-status-readonly-audit",
    }
    headers.update(extra_headers or {})
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response) if response.status == 200 else None
            return {"status": int(response.status), "data": payload}
    except urllib.error.HTTPError as exc:
        return {"status": int(exc.code), "data": None}


def _api_get_200(token: str, path: str, params=None, extra_headers=None) -> Any:
    result = _api_get_result(token, path, params, extra_headers)
    if result["status"] != 200:
        raise RuntimeError(f"P0_250_F2_6_1_HTTP_STATUS:{result['status']}:{path}")
    return result["data"]


def _unique_one(collection, query, projection, label):
    docs = list(collection.find(query, projection).limit(3))
    if len(docs) != 1:
        raise RuntimeError(f"P0_250_F2_6_1_IDENTITY_{label}_MATCHES:{len(docs)}")
    return docs[0]


def _school_ids_for_professor(db, user, staff) -> list[str]:
    rows = list(db.school_assignments.find(
        {"staff_id": staff["id"], "status": "ativo", "academic_year": ACADEMIC_YEAR},
        {"_id": 0, "school_id": 1},
    ))
    ids: list[str] = []
    for row in rows:
        value = row.get("school_id")
        if value and value not in ids:
            ids.append(value)
    if ids:
        return ids

    for link in user.get("school_links") or []:
        if not isinstance(link, dict):
            continue
        value = link.get("school_id")
        roles = link.get("roles") or ([link.get("role")] if link.get("role") else [])
        if value and (not roles or "professor" in roles) and value not in ids:
            ids.append(value)
    return ids


def analyze_http_status_parity(*, component_rows: list[dict[str, Any]], classwide_statuses: dict[str, int]) -> dict[str, Any]:
    if len(component_rows) != EXPECTED_COMPONENTS:
        classification = "PROFESSOR_CONTENT_ENTITLEMENT_DRIFT"
    else:
        component_blocked = any(
            row["months"][str(month)]["professor_component_status"] == 409
            for row in component_rows for month in TARGET_MONTHS
        )
        classwide_blocked = any(classwide_statuses.get(str(month)) == 409 for month in TARGET_MONTHS)
        professor_count_gap = any(
            row["months"][str(month)]["professor_component_status"] == 200
            and row["months"][str(month)]["professor_component_http"]
            != row["months"][str(month)]["mongo_target_tenant"]
            for row in component_rows for month in TARGET_MONTHS
        )
        management_gap = any(
            row["months"][str(month)]["superadmin_scoped_status"] == 200
            and row["months"][str(month)]["superadmin_scoped_http"]
            != row["months"][str(month)]["mongo_target_tenant"]
            for row in component_rows for month in TARGET_MONTHS
        )
        if component_blocked:
            classification = "CONTENT_COMPONENT_PROFESSOR_COMPONENT_BLOCKED"
        elif classwide_blocked:
            classification = "CONTENT_COMPONENT_PROFESSOR_CLASSWIDE_BLOCKED"
        elif professor_count_gap:
            classification = "CONTENT_COMPONENT_HTTP_PROFESSOR_GAP"
        elif management_gap:
            classification = "CONTENT_COMPONENT_HTTP_MANAGEMENT_GAP"
        else:
            classification = "CONTENT_COMPONENT_HTTP_DB_PARITY"

    blocked_components = []
    for row in component_rows:
        blocked_months = [
            month for month in TARGET_MONTHS
            if row["months"][str(month)]["professor_component_status"] == 409
        ]
        if blocked_months:
            blocked_components.append({
                "component_name": row["component_name"],
                "focus": row.get("focus"),
                "months": blocked_months,
            })

    focus = {}
    for row in component_rows:
        if row.get("focus"):
            focus[row["focus"]] = {
                "component_name": row["component_name"],
                "legacy_assignment_count": row["legacy_assignment_count"],
                "dvd_raw_component_rows": row["dvd_raw_component_rows"],
                "dvd_enabled_current_component_rows": row["dvd_enabled_current_component_rows"],
                "months": row["months"],
            }

    return {
        "classification": classification,
        "component_count": len(component_rows),
        "professor_classwide_statuses": classwide_statuses,
        "blocked_components": blocked_components,
        "focus_components": focus,
        "component_rows": component_rows,
    }


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("P0_250_F2_6_1_MONGO_URL_MISSING")
    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]

    school = _unique_one(
        db.schools, {"name": SCHOOL_NAME}, {"_id": 0, "id": 1, "mantenedora_id": 1}, "SCHOOL"
    )
    teacher = _unique_one(
        db.users, {"full_name": TEACHER_NAME},
        {"_id": 0, "id": 1, "email": 1, "role": 1, "roles": 1, "mantenedora_id": 1, "school_links": 1},
        "TEACHER_USER",
    )
    superadmin = _unique_one(
        db.users, {"full_name": SUPERADMIN_NAME, "role": "super_admin"},
        {"_id": 0, "id": 1, "email": 1, "role": 1, "mantenedora_id": 1},
        "SUPERADMIN_USER",
    )
    if teacher.get("role") != "professor":
        raise RuntimeError(f"P0_250_F2_6_1_PRIMARY_ROLE_NOT_PROFESSOR:{teacher.get('role')}")

    staff_query = {"$or": [{"user_id": teacher["id"]}]}
    if teacher.get("email"):
        staff_query["$or"].append({"email": teacher["email"]})
    staff = _unique_one(db.staff, staff_query, {"_id": 0, "id": 1}, "STAFF")
    class_doc = _unique_one(
        db.classes,
        {"school_id": school["id"], "name": CLASS_NAME, "academic_year": ACADEMIC_YEAR},
        {"_id": 0, "id": 1, "mantenedora_id": 1},
        "CLASS",
    )
    target_tenant = class_doc.get("mantenedora_id") or school.get("mantenedora_id")
    if not target_tenant:
        raise RuntimeError("P0_250_F2_6_1_TARGET_TENANT_MISSING")

    legacy_assignments = list(db.teacher_assignments.find(
        {
            "staff_id": staff["id"], "class_id": class_doc["id"],
            "academic_year": ACADEMIC_YEAR, "status": {"$in": ["ativo", "active"]},
        },
        {"_id": 0, "course_id": 1},
    ))
    legacy_assignment_counts = Counter(
        _sid(row.get("course_id")) for row in legacy_assignments if row.get("course_id")
    )
    legacy_course_ids = sorted(legacy_assignment_counts)
    course_docs = list(db.courses.find(
        {"id": {"$in": legacy_course_ids}}, {"_id": 0, "id": 1, "name": 1}
    ))
    course_name_by_id = {_sid(row.get("id")): str(row.get("name") or "") for row in course_docs}
    unresolved = [course_id for course_id in legacy_course_ids if course_id not in course_name_by_id]
    if unresolved:
        raise RuntimeError(f"P0_250_F2_6_1_UNRESOLVED_COURSES:{len(unresolved)}")

    today = date.today().isoformat()
    dvd_rows = list(db.teacher_class_assignments.find(
        {"teacher_id": teacher["id"], "class_id": class_doc["id"], "deleted": False},
        {"_id": 0, "component_id": 1, "valid_from": 1, "valid_until": 1, "diary_settings.enabled": 1},
    ))
    dvd_raw_counts = Counter(_sid(row.get("component_id")) for row in dvd_rows if row.get("component_id"))
    dvd_enabled_current_counts: Counter[str] = Counter()
    for row in dvd_rows:
        enabled = bool((row.get("diary_settings") or {}).get("enabled"))
        start = _sid(row.get("valid_from"))[:10]
        end = _sid(row.get("valid_until"))[:10]
        if not (enabled and (not start or start <= today) and (not end or today <= end)):
            continue
        component_id = _sid(row.get("component_id"))
        if component_id:
            dvd_enabled_current_counts[component_id] += 1

    from auth_utils import create_access_token  # pylint: disable=import-outside-toplevel

    school_ids = _school_ids_for_professor(db, teacher, staff)
    if _sid(school["id"]) not in {_sid(value) for value in school_ids}:
        raise RuntimeError("P0_250_F2_6_1_TARGET_SCHOOL_OUTSIDE_PROFESSOR_SCOPE")

    teacher_token = create_access_token({
        "sub": teacher["id"], "email": teacher.get("email"), "role": "professor",
        "school_ids": school_ids, "mantenedora_id": teacher.get("mantenedora_id"),
    })
    superadmin_token = create_access_token({
        "sub": superadmin["id"], "email": superadmin.get("email"), "role": "super_admin",
        "mantenedora_id": superadmin.get("mantenedora_id"),
    })

    turmas = _api_get_200(teacher_token, "/professor/turmas", {"academic_year": ACADEMIC_YEAR}) or []
    target_turmas = [row for row in turmas if _sid(row.get("id")) == _sid(class_doc["id"])]
    if len(target_turmas) != 1:
        raise RuntimeError(f"P0_250_F2_6_1_HTTP_TARGET_CLASS_MATCHES:{len(target_turmas)}")
    professor_http_course_ids = {
        _sid(component.get("id")) for component in (target_turmas[0].get("componentes") or [])
        if component.get("id") is not None
    }

    scoped_headers = {"X-Mantenedora-Id": _sid(target_tenant)}
    classwide_statuses: dict[str, int] = {}
    classwide_counts: dict[int, Counter[str]] = {}
    management_counts: dict[int, Counter[str]] = {}
    management_statuses: dict[str, int] = {}

    for month in TARGET_MONTHS:
        params = {"class_id": class_doc["id"], "academic_year": ACADEMIC_YEAR, "month": month}
        professor_result = _api_get_result(teacher_token, "/learning-objects", params)
        classwide_statuses[str(month)] = professor_result["status"]
        classwide_counts[month] = _counts_by_component(professor_result["data"] or []) if professor_result["status"] == 200 else Counter()

        management_result = _api_get_result(
            superadmin_token, "/learning-objects", params, scoped_headers
        )
        management_statuses[str(month)] = management_result["status"]
        management_counts[month] = _counts_by_component(management_result["data"] or []) if management_result["status"] == 200 else Counter()

    component_rows = []
    for course_id in sorted(legacy_course_ids, key=lambda cid: _norm(course_name_by_id[cid])):
        component_name = course_name_by_id[course_id]
        months = {}
        for month in TARGET_MONTHS:
            start, end = _month_bounds(month)
            base = {
                "class_id": class_doc["id"], "course_id": course_id,
                "academic_year": ACADEMIC_YEAR, "date": {"$gte": start, "$lt": end},
                "mantenedora_id": target_tenant,
            }
            mongo_target = db.learning_objects.count_documents(base)
            component_result = _api_get_result(
                teacher_token,
                "/learning-objects",
                {
                    "class_id": class_doc["id"], "course_id": course_id,
                    "academic_year": ACADEMIC_YEAR, "month": month,
                },
            )
            months[str(month)] = {
                "mongo_target_tenant": mongo_target,
                "professor_classwide_status": classwide_statuses[str(month)],
                "professor_classwide_http": classwide_counts[month].get(course_id, 0),
                "professor_component_status": component_result["status"],
                "professor_component_http": len(component_result["data"] or []) if component_result["status"] == 200 else 0,
                "superadmin_scoped_status": management_statuses[str(month)],
                "superadmin_scoped_http": management_counts[month].get(course_id, 0),
            }

        component_rows.append({
            "component_name": component_name,
            "focus": _focus_component(component_name),
            "legacy_assignment_count": legacy_assignment_counts.get(course_id, 0),
            "present_in_professor_turmas_http": course_id in professor_http_course_ids,
            "dvd_raw_component_rows": dvd_raw_counts.get(course_id, 0),
            "dvd_enabled_current_component_rows": dvd_enabled_current_counts.get(course_id, 0),
            "months": months,
        })

    analysis = analyze_http_status_parity(
        component_rows=component_rows,
        classwide_statuses=classwide_statuses,
    )
    analysis.update({
        "professor_turmas_component_count": len(professor_http_course_ids),
        "dvd_raw_total_rows": len(dvd_rows),
        "reference_date": today,
        "superadmin_scoped_statuses": management_statuses,
    })

    return {
        "schema": "P0_250_F2_6_1_CONTENT_COMPONENT_HTTP_STATUS_AUDIT_V1",
        "status": "PASS",
        "classification": analysis["classification"],
        "database_mutation": False,
        "production_writes": False,
        "http_methods": ["GET"],
        "mongo_reads_only": True,
        "record_content_emitted": False,
        "record_ids_emitted": False,
        "assignment_ids_emitted": False,
        "teacher_ids_emitted": False,
        "student_data_read": False,
        "student_pii_emitted": False,
        "access_token_emitted": False,
        "access_token_persisted": False,
        "component_names_emitted": True,
        "target": {
            "academic_year": ACADEMIC_YEAR,
            "months": list(TARGET_MONTHS),
            "school": SCHOOL_NAME,
            "class": CLASS_NAME,
        },
        "analysis": analysis,
    }


def assert_source_read_only() -> None:
    source = open(__file__, encoding="utf-8").read()
    for token in MONGO_MUTATOR_TOKENS:
        if token in source:
            raise RuntimeError(f"P0_250_F2_6_1_MONGO_MUTATOR_TOKEN_FOUND:{token}")
    for marker in HTTP_WRITE_MARKERS:
        if marker in source:
            raise RuntimeError(f"P0_250_F2_6_1_HTTP_WRITE_MARKER_FOUND:{marker}")


def main() -> None:
    assert_source_read_only()
    print(
        "P0_250_F2_6_1_AUDIT_JSON="
        + json.dumps(run_live_audit(), ensure_ascii=False, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
