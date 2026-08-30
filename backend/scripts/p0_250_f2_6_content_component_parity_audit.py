#!/usr/bin/env python3
"""P0 #250 F2.6 — component-level read-only audit for Objetos de Conhecimento.

Compares, for the same class and Apr/May/Jun 2026:
- direct Mongo legacy records by component and tenant state;
- authenticated professor GET /learning-objects, class-wide and per component;
- authenticated super-admin GET /learning-objects, unscoped and tenant-scoped;
- legacy teacher_assignments versus raw teacher_class_assignments mapping.

No content text, record/assignment/teacher/student/user ids, student data or auth
material is emitted. MongoDB is read-only and application HTTP is GET-only.
"""

from __future__ import annotations

import json
import os
import unicodedata
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
API_BASE = os.environ.get("P0_250_F2_6_API_BASE", "http://127.0.0.1:8001/api").rstrip("/")

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


def analyze_component_parity(
    *, component_rows: list[dict[str, Any]], expected_components: int = EXPECTED_COMPONENTS
) -> dict[str, Any]:
    if len(component_rows) != expected_components:
        classification = "PROFESSOR_CONTENT_ENTITLEMENT_DRIFT"
    else:
        professor_http_gap = any(
            row["months"][str(month)]["professor_classwide_http"]
            != row["months"][str(month)]["mongo_target_tenant"]
            for row in component_rows for month in TARGET_MONTHS
        )
        classwide_projection_gap = any(
            row["months"][str(month)]["professor_classwide_http"]
            != row["months"][str(month)]["professor_component_http"]
            for row in component_rows for month in TARGET_MONTHS
        )
        tenant_scope_gap = any(
            row["months"][str(month)]["mongo_all_tenants"]
            > row["months"][str(month)]["mongo_target_tenant"]
            for row in component_rows for month in TARGET_MONTHS
        )
        superadmin_scope_gap = any(
            row["months"][str(month)]["superadmin_unscoped_http"]
            != row["months"][str(month)]["superadmin_scoped_http"]
            for row in component_rows for month in TARGET_MONTHS
        )
        if professor_http_gap:
            classification = "CONTENT_COMPONENT_HTTP_PROFESSOR_GAP"
        elif classwide_projection_gap:
            classification = "CONTENT_COMPONENT_CLASSWIDE_PROJECTION_GAP"
        elif tenant_scope_gap or superadmin_scope_gap:
            classification = "CONTENT_COMPONENT_TENANT_SCOPE_GAP"
        else:
            classification = "CONTENT_COMPONENT_HTTP_DB_PARITY"

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
        "focus_components": focus,
        "component_rows": component_rows,
    }


def _api_get(token: str, path: str, params=None, extra_headers=None) -> Any:
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{API_BASE}{path}" + (f"?{query}" if query else "")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "sigesc-p0-250-f2-6-content-component-readonly-audit",
    }
    headers.update(extra_headers or {})
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"P0_250_F2_6_HTTP_STATUS:{response.status}:{path}")
        return json.load(response)


def _unique_one(collection, query, projection, label):
    docs = list(collection.find(query, projection).limit(3))
    if len(docs) != 1:
        raise RuntimeError(f"P0_250_F2_6_IDENTITY_{label}_MATCHES:{len(docs)}")
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


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("P0_250_F2_6_MONGO_URL_MISSING")
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
        {"_id": 0, "id": 1, "email": 1, "role": 1, "roles": 1, "mantenedora_id": 1},
        "SUPERADMIN_USER",
    )
    if teacher.get("role") != "professor":
        raise RuntimeError(f"P0_250_F2_6_PRIMARY_ROLE_NOT_PROFESSOR:{teacher.get('role')}")

    staff_query = {"$or": [{"user_id": teacher["id"]}]}
    if teacher.get("email"):
        staff_query["$or"].append({"email": teacher["email"]})
    staff = _unique_one(db.staff, staff_query, {"_id": 0, "id": 1}, "STAFF")
    class_doc = _unique_one(
        db.classes,
        {"school_id": school["id"], "name": CLASS_NAME, "academic_year": ACADEMIC_YEAR},
        {"_id": 0, "id": 1, "school_id": 1, "mantenedora_id": 1},
        "CLASS",
    )
    target_tenant = class_doc.get("mantenedora_id") or school.get("mantenedora_id")
    if not target_tenant:
        raise RuntimeError("P0_250_F2_6_TARGET_TENANT_MISSING")

    legacy_assignments = list(db.teacher_assignments.find(
        {
            "staff_id": staff["id"], "class_id": class_doc["id"],
            "academic_year": ACADEMIC_YEAR, "status": {"$in": ["ativo", "active"]},
        },
        {"_id": 0, "course_id": 1},
    ))
    legacy_assignment_counts = Counter(_sid(row.get("course_id")) for row in legacy_assignments if row.get("course_id"))
    legacy_course_ids = sorted(legacy_assignment_counts)
    course_docs = list(db.courses.find(
        {"id": {"$in": legacy_course_ids}}, {"_id": 0, "id": 1, "name": 1}
    ))
    course_name_by_id = {_sid(row.get("id")): str(row.get("name") or "") for row in course_docs}
    unresolved = [cid for cid in legacy_course_ids if cid not in course_name_by_id]
    if unresolved:
        raise RuntimeError(f"P0_250_F2_6_UNRESOLVED_COURSES:{len(unresolved)}")

    today = date.today().isoformat()
    dvd_rows = list(db.teacher_class_assignments.find(
        {"teacher_id": teacher["id"], "class_id": class_doc["id"], "deleted": False},
        {"_id": 0, "component_id": 1, "valid_from": 1, "valid_until": 1, "diary_settings.enabled": 1},
    ))
    dvd_raw_counts = Counter(_sid(row.get("component_id")) for row in dvd_rows if row.get("component_id"))
    dvd_class_wide_rows = sum(1 for row in dvd_rows if not row.get("component_id"))
    dvd_enabled_current_counts: Counter[str] = Counter()
    dvd_enabled_current_class_wide = 0
    for row in dvd_rows:
        enabled = bool((row.get("diary_settings") or {}).get("enabled"))
        start = _sid(row.get("valid_from"))[:10]
        end = _sid(row.get("valid_until"))[:10]
        if not (enabled and (not start or start <= today) and (not end or today <= end)):
            continue
        component_id = _sid(row.get("component_id"))
        if component_id:
            dvd_enabled_current_counts[component_id] += 1
        else:
            dvd_enabled_current_class_wide += 1

    from auth_utils import create_access_token  # pylint: disable=import-outside-toplevel

    school_ids = _school_ids_for_professor(db, teacher, staff)
    if _sid(school["id"]) not in {_sid(value) for value in school_ids}:
        raise RuntimeError("P0_250_F2_6_TARGET_SCHOOL_OUTSIDE_PROFESSOR_SCOPE")
    teacher_token = create_access_token({
        "sub": teacher["id"], "email": teacher.get("email"), "role": "professor",
        "school_ids": school_ids, "mantenedora_id": teacher.get("mantenedora_id"),
    })
    superadmin_token = create_access_token({
        "sub": superadmin["id"], "email": superadmin.get("email"), "role": "super_admin",
        "mantenedora_id": superadmin.get("mantenedora_id"),
    })

    turmas = _api_get(teacher_token, "/professor/turmas", {"academic_year": ACADEMIC_YEAR}) or []
    target_turmas = [row for row in turmas if _sid(row.get("id")) == _sid(class_doc["id"])]
    if len(target_turmas) != 1:
        raise RuntimeError(f"P0_250_F2_6_HTTP_TARGET_CLASS_MATCHES:{len(target_turmas)}")
    professor_http_course_ids = {
        _sid(component.get("id")) for component in (target_turmas[0].get("componentes") or [])
        if component.get("id") is not None
    }

    per_month_http: dict[int, dict[str, Counter[str]]] = {}
    scoped_headers = {"X-Mantenedora-Id": _sid(target_tenant)}
    for month in TARGET_MONTHS:
        params = {"class_id": class_doc["id"], "academic_year": ACADEMIC_YEAR, "month": month}
        professor_rows = _api_get(teacher_token, "/learning-objects", params) or []
        superadmin_unscoped_rows = _api_get(superadmin_token, "/learning-objects", params) or []
        superadmin_scoped_rows = _api_get(superadmin_token, "/learning-objects", params, scoped_headers) or []
        per_month_http[month] = {
            "professor_classwide": _counts_by_component(professor_rows),
            "superadmin_unscoped": _counts_by_component(superadmin_unscoped_rows),
            "superadmin_scoped": _counts_by_component(superadmin_scoped_rows),
        }

    component_rows = []
    for course_id in sorted(legacy_course_ids, key=lambda cid: _norm(course_name_by_id[cid])):
        component_name = course_name_by_id[course_id]
        months = {}
        for month in TARGET_MONTHS:
            start, end = _month_bounds(month)
            base = {
                "class_id": class_doc["id"], "course_id": course_id,
                "academic_year": ACADEMIC_YEAR, "date": {"$gte": start, "$lt": end},
            }
            mongo_all = db.learning_objects.count_documents(base)
            mongo_target = db.learning_objects.count_documents({**base, "mantenedora_id": target_tenant})
            # Mongo equality with None matches both explicit null and field absence,
            # which is exactly the diagnostic bucket required here.
            mongo_missing_or_null = db.learning_objects.count_documents({**base, "mantenedora_id": None})
            mongo_other = max(0, mongo_all - mongo_target - mongo_missing_or_null)
            component_http = _api_get(
                teacher_token, "/learning-objects",
                {"class_id": class_doc["id"], "course_id": course_id, "academic_year": ACADEMIC_YEAR, "month": month},
            ) or []
            months[str(month)] = {
                "mongo_all_tenants": mongo_all,
                "mongo_target_tenant": mongo_target,
                "mongo_missing_or_null_tenant": mongo_missing_or_null,
                "mongo_other_tenant": mongo_other,
                "professor_classwide_http": per_month_http[month]["professor_classwide"].get(course_id, 0),
                "professor_component_http": len(component_http),
                "superadmin_unscoped_http": per_month_http[month]["superadmin_unscoped"].get(course_id, 0),
                "superadmin_scoped_http": per_month_http[month]["superadmin_scoped"].get(course_id, 0),
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

    analysis = analyze_component_parity(component_rows=component_rows)
    analysis.update({
        "professor_turmas_component_count": len(professor_http_course_ids),
        "dvd_raw_total_rows": len(dvd_rows),
        "dvd_raw_class_wide_rows": dvd_class_wide_rows,
        "dvd_enabled_current_class_wide_rows": dvd_enabled_current_class_wide,
        "reference_date": today,
    })
    return {
        "schema": "P0_250_F2_6_CONTENT_COMPONENT_PARITY_AUDIT_V1",
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
        "target": {"academic_year": ACADEMIC_YEAR, "months": list(TARGET_MONTHS), "school": SCHOOL_NAME, "class": CLASS_NAME},
        "analysis": analysis,
    }


def assert_source_read_only() -> None:
    source = open(__file__, encoding="utf-8").read()
    for token in MONGO_MUTATOR_TOKENS:
        if token in source:
            raise RuntimeError(f"P0_250_F2_6_MONGO_MUTATOR_TOKEN_FOUND:{token}")
    for marker in HTTP_WRITE_MARKERS:
        if marker in source:
            raise RuntimeError(f"P0_250_F2_6_HTTP_WRITE_MARKER_FOUND:{marker}")


def main() -> None:
    assert_source_read_only()
    print("P0_250_F2_6_AUDIT_JSON=" + json.dumps(run_live_audit(), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
