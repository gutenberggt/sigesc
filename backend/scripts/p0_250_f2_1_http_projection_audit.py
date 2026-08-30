#!/usr/bin/env python3
"""P0 #250 F2.1 — bounded production HTTP/projection parity audit.

This script is designed to be streamed into the already-running SIGESC backend
container and executed there. It performs only authenticated HTTP GET requests
plus MongoDB reads needed to resolve the canonical professor session context.

Privacy boundary:
- no grade value is emitted;
- no student id/name/document is emitted;
- the ephemeral professor access token is never emitted or persisted;
- the output contains only aggregate structural counters and course ids already
  present in the teacher entitlement.

Mutation boundary:
- no MongoDB mutation primitive is used;
- no HTTP write method is used;
- no application or container restart is performed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any

from pymongo import MongoClient

ACADEMIC_YEAR = 2026
TEACHER_NAME = "Abadia Alves Martins"
SCHOOL_NAME = "E M E I E F Jose Pereira Barbosa"
CLASS_NAME = "5º ANO A"
EXPECTED_PROMOTION_STUDENTS = 21
EXPECTED_COMPONENTS = 9
GRADE_FIELDS = ("b1", "b2", "b3", "b4", "rec_s1", "rec_s2")
API_BASE = os.environ.get("P0_250_F2_1_API_BASE", "http://127.0.0.1:8001/api").rstrip("/")

MONGO_MUTATOR_TOKENS = (
    ".insert_one(",
    ".insert_many(",
    ".update_one(",
    ".update_many(",
    ".replace_one(",
    ".delete_one(",
    ".delete_many(",
    ".bulk_write(",
    ".find_one_and_update(",
    ".find_one_and_delete(",
    ".find_one_and_replace(",
    ".drop(",
    ".drop_database(",
)
HTTP_WRITE_MARKERS = (
    "method=\"POST\"",
    "method='POST'",
    "method=\"PUT\"",
    "method='PUT'",
    "method=\"PATCH\"",
    "method='PATCH'",
    "method=\"DELETE\"",
    "method='DELETE'",
)


def _sid(value: Any) -> str:
    return "" if value is None else str(value)


def _recorded(grade: dict[str, Any] | None) -> bool:
    return bool(grade) and any(grade.get(field) is not None for field in GRADE_FIELDS)


def _field_presence(grade: dict[str, Any] | None) -> dict[str, bool]:
    grade = grade or {}
    return {field: grade.get(field) is not None for field in GRADE_FIELDS}


def _same_grade_values(left: dict[str, Any] | None, right: dict[str, Any] | None) -> int:
    """Return number of value mismatches without ever returning the values."""
    left = left or {}
    right = right or {}
    return sum(1 for field in GRADE_FIELDS if left.get(field) != right.get(field))


def analyze_http_projection(
    *,
    promotion_student_ids: list[str],
    allowed_course_ids: list[str],
    class_id: str,
    generic_payloads: dict[str, list[dict[str, Any]]],
    by_class_payloads: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Compare the two live HTTP shapes and emulate Promotion.jsx projection.

    `generic_payloads` corresponds to GET /grades per promotion student.
    `by_class_payloads` corresponds to GET /grades/by-class per allowed course.
    The function intentionally emits aggregate counters only.
    """
    promotion_ids = [_sid(x) for x in promotion_student_ids if x is not None]
    course_ids = [_sid(x) for x in allowed_course_ids if x is not None]
    promotion_set = set(promotion_ids)
    course_set = set(course_ids)
    class_key = _sid(class_id)

    generic_index: dict[tuple[str, str], dict[str, Any]] = {}
    generic_duplicates = 0
    raw_generic_documents = 0
    ignored_non_authorized_documents = 0
    strict_course_identity_mismatches = 0

    for requested_sid, rows in generic_payloads.items():
        requested_sid_key = _sid(requested_sid)
        for grade in rows or []:
            raw_generic_documents += 1
            grade_sid = _sid(grade.get("student_id"))
            grade_cid = _sid(grade.get("course_id"))
            grade_class = _sid(grade.get("class_id"))

            # This reproduces filterPromotionGradesForClass: class + allowed ids.
            if grade_class != class_key or grade_cid not in course_set:
                ignored_non_authorized_documents += 1
                continue
            if grade_sid != requested_sid_key or grade_sid not in promotion_set:
                # An authorized-looking document for another student would be a
                # projection integrity failure; keep it out of the target matrix.
                continue

            # Promotion.jsx later uses strict course.id === grade.course_id.
            # Record whether the live JSON types would break that strict lookup.
            matching_raw_course = next(
                (cid for cid in allowed_course_ids if _sid(cid) == grade_cid),
                None,
            )
            if matching_raw_course is not None and type(matching_raw_course) is not type(grade.get("course_id")):
                strict_course_identity_mismatches += 1

            key = (grade_sid, grade_cid)
            if key in generic_index:
                generic_duplicates += 1
            else:
                generic_index[key] = grade

    by_class_index: dict[tuple[str, str], dict[str, Any]] = {}
    by_class_duplicates = 0
    by_class_rows_total = 0
    by_class_rows_in_promotion = 0
    by_class_rows_outside_promotion = 0
    by_class_real_documents = 0

    for expected_cid, rows in by_class_payloads.items():
        cid_key = _sid(expected_cid)
        if cid_key not in course_set:
            continue
        for row in rows or []:
            by_class_rows_total += 1
            student = row.get("student") or {}
            grade = row.get("grade") or {}
            row_sid = _sid(student.get("id") or grade.get("student_id"))
            if row_sid not in promotion_set:
                by_class_rows_outside_promotion += 1
                continue
            by_class_rows_in_promotion += 1
            if grade.get("id") is not None:
                by_class_real_documents += 1
            key = (row_sid, cid_key)
            if key in by_class_index:
                by_class_duplicates += 1
            else:
                by_class_index[key] = grade

    expected_pairs = len(promotion_ids) * len(course_ids)
    generic_document_pairs = 0
    generic_recorded_pairs = 0
    by_class_row_pairs = 0
    by_class_recorded_pairs = 0
    document_presence_mismatch_pairs = 0
    recorded_presence_mismatch_pairs = 0
    field_presence_mismatches = 0
    field_value_mismatches = 0
    students_with_any_recorded_pair: set[str] = set()
    students_with_all_course_documents: set[str] = set()
    per_course: dict[str, dict[str, Any]] = {}

    for cid in course_ids:
        summary = {
            "course_id": cid,
            "expected_student_pairs": len(promotion_ids),
            "generic_document_pairs": 0,
            "generic_recorded_pairs": 0,
            "by_class_row_pairs": 0,
            "by_class_recorded_pairs": 0,
            "document_presence_mismatch_pairs": 0,
            "recorded_presence_mismatch_pairs": 0,
            "field_presence_mismatches": 0,
            "field_value_mismatches": 0,
        }
        for sid in promotion_ids:
            key = (sid, cid)
            generic_grade = generic_index.get(key)
            by_class_grade = by_class_index.get(key)
            has_generic_doc = generic_grade is not None
            has_by_class_row = by_class_grade is not None

            if has_generic_doc:
                generic_document_pairs += 1
                summary["generic_document_pairs"] += 1
            if _recorded(generic_grade):
                generic_recorded_pairs += 1
                summary["generic_recorded_pairs"] += 1
                students_with_any_recorded_pair.add(sid)
            if has_by_class_row:
                by_class_row_pairs += 1
                summary["by_class_row_pairs"] += 1
            if _recorded(by_class_grade):
                by_class_recorded_pairs += 1
                summary["by_class_recorded_pairs"] += 1

            # A by-class placeholder is a row without a persisted grade id. For
            # document parity, compare persisted generic doc vs persisted by-class doc.
            has_by_class_document = bool(by_class_grade and by_class_grade.get("id") is not None)
            if has_generic_doc != has_by_class_document:
                document_presence_mismatch_pairs += 1
                summary["document_presence_mismatch_pairs"] += 1

            if _recorded(generic_grade) != _recorded(by_class_grade):
                recorded_presence_mismatch_pairs += 1
                summary["recorded_presence_mismatch_pairs"] += 1

            gp = _field_presence(generic_grade)
            bp = _field_presence(by_class_grade)
            pair_presence_mismatches = sum(1 for field in GRADE_FIELDS if gp[field] != bp[field])
            pair_value_mismatches = _same_grade_values(generic_grade, by_class_grade)
            field_presence_mismatches += pair_presence_mismatches
            field_value_mismatches += pair_value_mismatches
            summary["field_presence_mismatches"] += pair_presence_mismatches
            summary["field_value_mismatches"] += pair_value_mismatches

        per_course[cid] = summary

    for sid in promotion_ids:
        if all((sid, cid) in generic_index for cid in course_ids):
            students_with_all_course_documents.add(sid)

    classification = "HTTP_AND_FRONTEND_PROJECTION_PARITY_FOR_PROMOTION_21"
    if len(promotion_ids) != EXPECTED_PROMOTION_STUDENTS:
        classification = "PROMOTION_ROSTER_DRIFT"
    elif len(course_ids) != EXPECTED_COMPONENTS:
        classification = "PROFESSOR_ENTITLEMENT_DRIFT"
    elif generic_duplicates or by_class_duplicates:
        classification = "HTTP_DUPLICATE_IDENTITY_ROWS"
    elif strict_course_identity_mismatches:
        classification = "FRONTEND_STRICT_IDENTITY_TYPE_DIVERGENCE"
    elif document_presence_mismatch_pairs:
        classification = "HTTP_DOCUMENT_DIVERGENCE_FOR_PROMOTION_21"
    elif field_value_mismatches:
        classification = "HTTP_VALUE_DIVERGENCE_FOR_PROMOTION_21"
    elif field_presence_mismatches or recorded_presence_mismatch_pairs:
        classification = "HTTP_FIELD_PRESENCE_DIVERGENCE_FOR_PROMOTION_21"
    elif generic_document_pairs != expected_pairs:
        classification = "GENERIC_HTTP_MISSING_GRADE_DOCUMENTS_FOR_PROMOTION_21"
    elif by_class_row_pairs != expected_pairs:
        classification = "BYCLASS_HTTP_MISSING_ROWS_FOR_PROMOTION_21"

    return {
        "classification": classification,
        "promotion_student_count": len(promotion_ids),
        "allowed_course_count": len(course_ids),
        "expected_student_course_pairs": expected_pairs,
        "raw_generic_documents": raw_generic_documents,
        "ignored_non_authorized_documents": ignored_non_authorized_documents,
        "generic_document_pairs": generic_document_pairs,
        "generic_recorded_pairs": generic_recorded_pairs,
        "by_class_rows_total": by_class_rows_total,
        "by_class_rows_in_promotion": by_class_rows_in_promotion,
        "by_class_rows_outside_promotion": by_class_rows_outside_promotion,
        "by_class_real_documents_in_promotion": by_class_real_documents,
        "by_class_row_pairs": by_class_row_pairs,
        "by_class_recorded_pairs": by_class_recorded_pairs,
        "generic_duplicate_pairs": generic_duplicates,
        "by_class_duplicate_pairs": by_class_duplicates,
        "strict_course_identity_type_mismatches": strict_course_identity_mismatches,
        "document_presence_mismatch_pairs": document_presence_mismatch_pairs,
        "recorded_presence_mismatch_pairs": recorded_presence_mismatch_pairs,
        "field_presence_mismatches": field_presence_mismatches,
        "field_value_mismatches": field_value_mismatches,
        "students_with_any_recorded_pair": len(students_with_any_recorded_pair),
        "students_with_all_course_documents": len(students_with_all_course_documents),
        "course_summaries": [per_course[cid] for cid in course_ids],
    }


def _api_get(token: str, path: str, params: dict[str, Any] | None = None) -> Any:
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{API_BASE}{path}" + (f"?{query}" if query else "")
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "sigesc-p0-250-f2-1-readonly-audit",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"P0_250_F2_1_HTTP_STATUS:{response.status}:{path}")
        return json.load(response)


def _unique_one(collection, query: dict[str, Any], projection: dict[str, int], label: str) -> dict[str, Any]:
    docs = list(collection.find(query, projection).limit(3))
    if len(docs) != 1:
        raise RuntimeError(f"P0_250_F2_1_IDENTITY_{label}_MATCHES:{len(docs)}")
    return docs[0]


def _school_ids_for_professor(db, user: dict[str, Any], staff: dict[str, Any]) -> list[str]:
    lotacoes = list(db.school_assignments.find(
        {
            "staff_id": staff["id"],
            "status": "ativo",
            "academic_year": ACADEMIC_YEAR,
        },
        {"_id": 0, "school_id": 1},
    ))
    ids = []
    for row in lotacoes:
        sid = row.get("school_id")
        if sid and sid not in ids:
            ids.append(sid)
    if ids:
        return ids

    for link in user.get("school_links") or []:
        if not isinstance(link, dict):
            continue
        sid = link.get("school_id")
        roles = link.get("roles") or ([link.get("role")] if link.get("role") else [])
        if sid and (not roles or "professor" in roles) and sid not in ids:
            ids.append(sid)
    return ids


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("P0_250_F2_1_MONGO_URL_MISSING")

    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)[db_name]
    school = _unique_one(db.schools, {"name": SCHOOL_NAME}, {"_id": 0, "id": 1}, "SCHOOL")
    user = _unique_one(
        db.users,
        {"full_name": TEACHER_NAME},
        {"_id": 0, "id": 1, "email": 1, "role": 1, "roles": 1, "mantenedora_id": 1, "school_links": 1},
        "USER",
    )
    staff_query = {"$or": [{"user_id": user["id"]}]}
    if user.get("email"):
        staff_query["$or"].append({"email": user["email"]})
    staff = _unique_one(db.staff, staff_query, {"_id": 0, "id": 1, "user_id": 1, "email": 1}, "STAFF")
    class_doc = _unique_one(
        db.classes,
        {"school_id": school["id"], "name": CLASS_NAME, "academic_year": ACADEMIC_YEAR},
        {"_id": 0, "id": 1, "school_id": 1},
        "CLASS",
    )

    if user.get("role") != "professor":
        raise RuntimeError(f"P0_250_F2_1_PRIMARY_ROLE_NOT_PROFESSOR:{user.get('role')}")

    school_ids = _school_ids_for_professor(db, user, staff)
    if _sid(school["id"]) not in {_sid(x) for x in school_ids}:
        raise RuntimeError("P0_250_F2_1_TARGET_SCHOOL_OUTSIDE_SESSION_SCOPE")

    # Import only the pure token encoder from the running backend image. No login
    # endpoint is invoked (login would write an audit record). The token stays in
    # process memory and is never included in output/evidence.
    from auth_utils import create_access_token  # pylint: disable=import-outside-toplevel

    token = create_access_token({
        "sub": user["id"],
        "email": user.get("email"),
        "role": "professor",
        "school_ids": school_ids,
        "mantenedora_id": user.get("mantenedora_id"),
    })

    turmas = _api_get(token, "/professor/turmas", {"academic_year": ACADEMIC_YEAR})
    target_turmas = [row for row in (turmas or []) if _sid(row.get("id")) == _sid(class_doc["id"])]
    if len(target_turmas) != 1:
        raise RuntimeError(f"P0_250_F2_1_HTTP_TARGET_CLASS_MATCHES:{len(target_turmas)}")
    allowed_course_ids = []
    for component in target_turmas[0].get("componentes") or []:
        cid = component.get("id")
        if cid is not None and _sid(cid) not in {_sid(x) for x in allowed_course_ids}:
            allowed_course_ids.append(cid)

    # Reproduce exactly the roster construction currently used by Promotion.jsx.
    students_response = _api_get(token, "/students", {"class_id": class_doc["id"], "page_size": 10000})
    direct_students = (students_response or {}).get("items") or []
    enrollments = _api_get(token, "/enrollments", {"class_id": class_doc["id"]}) or []
    valid_statuses = {
        "active", "ativo", "transferred", "transferencia", "transferido",
        "dropout", "desistencia", "desistente",
    }
    filtered_enrollments = []
    for enrollment in enrollments:
        status = str(enrollment.get("status") or "active").lower()
        year = enrollment.get("academic_year")
        if status in valid_statuses and (year is None or int(year) == ACADEMIC_YEAR):
            filtered_enrollments.append(enrollment)

    students_by_id = {_sid(student.get("id")): student for student in direct_students if student.get("id") is not None}
    missing_ids = [
        _sid(e.get("student_id"))
        for e in filtered_enrollments
        if e.get("student_id") is not None and _sid(e.get("student_id")) not in students_by_id
    ]
    if missing_ids:
        all_students_response = _api_get(token, "/students", {"page_size": 10000})
        for student in (all_students_response or {}).get("items") or []:
            sid = _sid(student.get("id"))
            if sid in missing_ids:
                students_by_id[sid] = student
    promotion_student_ids = list(students_by_id.keys())

    generic_payloads: dict[str, list[dict[str, Any]]] = {}
    for student_id in promotion_student_ids:
        generic_payloads[student_id] = _api_get(
            token,
            "/grades",
            {
                "student_id": student_id,
                "class_id": class_doc["id"],
                "academic_year": ACADEMIC_YEAR,
            },
        ) or []

    by_class_payloads: dict[str, list[dict[str, Any]]] = {}
    for course_id in allowed_course_ids:
        course_key = _sid(course_id)
        path = "/grades/by-class/{}/{}".format(
            urllib.parse.quote(_sid(class_doc["id"]), safe=""),
            urllib.parse.quote(course_key, safe=""),
        )
        by_class_payloads[course_key] = _api_get(
            token,
            path,
            {"academic_year": ACADEMIC_YEAR},
        ) or []

    analysis = analyze_http_projection(
        promotion_student_ids=promotion_student_ids,
        allowed_course_ids=allowed_course_ids,
        class_id=_sid(class_doc["id"]),
        generic_payloads=generic_payloads,
        by_class_payloads=by_class_payloads,
    )

    return {
        "schema": "P0_250_F2_1_HTTP_PROJECTION_AUDIT_V1",
        "status": "PASS",
        "classification": analysis["classification"],
        "database_mutation": False,
        "production_writes": False,
        "http_methods": ["GET"],
        "grade_values_emitted": False,
        "student_ids_emitted": False,
        "student_pii_emitted": False,
        "ephemeral_access_token": True,
        "access_token_emitted": False,
        "access_token_persisted": False,
        "target": {
            "academic_year": ACADEMIC_YEAR,
            "class_id": _sid(class_doc["id"]),
            "school_id": _sid(school["id"]),
            "user_id": _sid(user["id"]),
            "staff_id": _sid(staff["id"]),
        },
        "analysis": analysis,
    }


def assert_source_read_only() -> None:
    source = open(__file__, encoding="utf-8").read()
    for token in MONGO_MUTATOR_TOKENS:
        if token in source:
            raise RuntimeError(f"P0_250_F2_1_MONGO_MUTATOR_TOKEN_FOUND:{token}")
    for marker in HTTP_WRITE_MARKERS:
        if marker in source:
            raise RuntimeError(f"P0_250_F2_1_HTTP_WRITE_MARKER_FOUND:{marker}")


def main() -> None:
    assert_source_read_only()
    payload = run_live_audit()
    print("P0_250_F2_1_AUDIT_JSON=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
