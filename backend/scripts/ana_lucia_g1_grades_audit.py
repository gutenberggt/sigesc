#!/usr/bin/env python3
"""ANA-LUCIA-G1 — auditoria read-only das notas históricas.

Escopo: oito turmas de Língua Inglesa (6º/9º anos) de Ana Lucia Faria Pinto,
ano letivo de 2026. A auditoria compara documentos em ``grades`` sob a
identidade legada EJA Final e a identidade canônica Fundamental/Anos Finais.

O coletor NÃO escreve no MongoDB e NÃO publica PII nem valores acadêmicos.
Valores são lidos apenas para classificar igualdade/complementaridade/conflito.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import os
import re
import sys
import unicodedata
from typing import Any, Mapping

from pymongo import MongoClient

ACADEMIC_YEAR = 2026
TEACHER_NAME = "Ana Lucia Faria Pinto"
COMPONENT_NAME = "Língua Inglesa"
CURRENT_LEVEL = "fundamental_anos_finais"
LEGACY_LEVEL = "eja_final"
ACTIVE_STATUSES = ("ativo", "active")
TARGET_CLASSES = (
    "6º ANO A", "6º ANO B", "6º ANO C", "6º ANO D",
    "9º ANO A", "9º ANO B", "9º ANO C", "9º ANO D",
)
PEDAGOGICAL_FIELDS = ("b1", "b2", "b3", "b4", "rec_s1", "rec_s2", "recovery", "observations")
OWNERSHIP_FIELDS = ("b1", "b2", "b3", "b4", "rec_s1", "rec_s2", "recovery", "observations")
GRADE_PROJECTION = {
    "_id": 0,
    "id": 1,
    "student_id": 1,
    "class_id": 1,
    "course_id": 1,
    "academic_year": 1,
    "mantenedora_id": 1,
    "assignment_id": 1,
    "grade_ownership": 1,
    "migrated_from_class_id": 1,
    "rectified_fields": 1,
    "b1": 1,
    "b2": 1,
    "b3": 1,
    "b4": 1,
    "rec_s1": 1,
    "rec_s2": 1,
    "recovery": 1,
    "observations": 1,
    "final_average": 1,
    "status": 1,
    "created_at": 1,
    "updated_at": 1,
}


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _sid(value))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.casefold().replace("º", "o").replace("ª", "a")
    return re.sub(r"\s+", " ", raw).strip()


def _fp(value: Any, size: int = 12) -> str | None:
    raw = _sid(value)
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:size]


def _year_filter() -> dict[str, Any]:
    return {"academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}}


def _unique_teacher_identity(db) -> tuple[dict[str, Any], dict[str, Any]]:
    users = list(db.users.find(
        {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "name": 1, "role": 1, "mantenedora_id": 1},
    ).limit(5))
    users = [row for row in users if _norm(row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)]
    if len(users) != 1 or users[0].get("role") != "professor":
        raise RuntimeError(f"ANA_LUCIA_G1_TEACHER_IDENTITY_INVALID:{len(users)}")
    user = users[0]

    clauses = [{"user_id": user["id"]}]
    if user.get("email"):
        clauses.append({"email": user["email"]})
    rows = list(db.staff.find(
        {"$or": clauses},
        {"_id": 0, "id": 1, "user_id": 1, "email": 1, "mantenedora_id": 1},
    ).limit(5))
    dedup = {_sid(row.get("id")): row for row in rows if _sid(row.get("id"))}
    if len(dedup) != 1:
        raise RuntimeError(f"ANA_LUCIA_G1_STAFF_IDENTITY_INVALID:{len(dedup)}")
    return user, next(iter(dedup.values()))


def _resolve_context(db, user: Mapping[str, Any], staff: Mapping[str, Any]) -> dict[str, Any]:
    assignments = list(db.teacher_assignments.find(
        {
            "staff_id": staff["id"],
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "status": {"$in": list(ACTIVE_STATUSES)},
        },
        {"_id": 0, "id": 1, "class_id": 1, "course_id": 1, "school_id": 1, "mantenedora_id": 1},
    ))
    class_ids = sorted({_sid(row.get("class_id")) for row in assignments if _sid(row.get("class_id"))})
    classes = list(db.classes.find(
        {"id": {"$in": class_ids}},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1, "academic_year": 1},
    ))
    class_by_id = {_sid(row.get("id")): row for row in classes if _sid(row.get("id"))}
    school_ids = sorted({_sid(row.get("school_id")) for row in classes if _sid(row.get("school_id"))})
    schools = list(db.schools.find(
        {"id": {"$in": school_ids}},
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    ))
    school_by_id = {_sid(row.get("id")): row for row in schools if _sid(row.get("id"))}
    course_ids = sorted({_sid(row.get("course_id")) for row in assignments if _sid(row.get("course_id"))})
    courses = list(db.courses.find(
        {"id": {"$in": course_ids}},
        {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1},
    ))
    course_by_id = {_sid(row.get("id")): row for row in courses if _sid(row.get("id"))}

    targets: list[dict[str, Any]] = []
    current_ids: set[str] = set()
    tenants: set[str] = set()
    for class_name in TARGET_CLASSES:
        matches = []
        for assignment in assignments:
            klass = class_by_id.get(_sid(assignment.get("class_id"))) or {}
            course = course_by_id.get(_sid(assignment.get("course_id"))) or {}
            if _norm(klass.get("name")) == _norm(class_name) and _norm(course.get("name")) == _norm(COMPONENT_NAME):
                matches.append(assignment)
        if len(matches) != 1:
            raise RuntimeError(f"ANA_LUCIA_G1_TARGET_NOT_EXACT:{class_name}:{len(matches)}")
        assignment = matches[0]
        klass = class_by_id[_sid(assignment.get("class_id"))]
        school = school_by_id.get(_sid(klass.get("school_id"))) or {}
        anchors = {
            _sid(assignment.get("mantenedora_id")),
            _sid(klass.get("mantenedora_id")),
            _sid(school.get("mantenedora_id")),
            _sid(user.get("mantenedora_id")),
            _sid(staff.get("mantenedora_id")),
        } - {""}
        if len(anchors) != 1:
            raise RuntimeError(f"ANA_LUCIA_G1_TENANT_ANCHORS_INVALID:{class_name}:{len(anchors)}")
        tenant_id = next(iter(anchors))
        current_id = _sid(assignment.get("course_id"))
        if not current_id:
            raise RuntimeError(f"ANA_LUCIA_G1_CURRENT_COURSE_MISSING:{class_name}")
        current_ids.add(current_id)
        tenants.add(tenant_id)
        targets.append({
            "class": class_name,
            "class_id": _sid(klass.get("id")),
            "school_id": _sid(klass.get("school_id")),
            "tenant_id": tenant_id,
        })

    if len(current_ids) != 1 or len(tenants) != 1:
        raise RuntimeError("ANA_LUCIA_G1_CONTEXT_NOT_UNIQUE")
    current_id = next(iter(current_ids))
    tenant_id = next(iter(tenants))

    same_name = list(db.courses.find(
        {
            "name": {"$exists": True},
            "$or": [
                {"mantenedora_id": tenant_id},
                {"mantenedora_id": {"$exists": False}},
                {"mantenedora_id": None},
                {"mantenedora_id": ""},
            ],
        },
        {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1},
    ))
    same_name = [row for row in same_name if _norm(row.get("name")) == _norm(COMPONENT_NAME)]
    current_matches = [
        row for row in same_name
        if _sid(row.get("id")) == current_id and _norm(row.get("nivel_ensino")) == _norm(CURRENT_LEVEL)
    ]
    legacy_matches = [row for row in same_name if _norm(row.get("nivel_ensino")) == _norm(LEGACY_LEVEL)]
    if len(current_matches) != 1 or len(legacy_matches) != 1:
        raise RuntimeError(
            f"ANA_LUCIA_G1_COURSE_IDENTITIES_INVALID:{len(current_matches)}:{len(legacy_matches)}"
        )
    legacy_id = _sid(legacy_matches[0].get("id"))
    if not legacy_id or legacy_id == current_id:
        raise RuntimeError("ANA_LUCIA_G1_IDENTITIES_INVALID")

    return {
        "targets": targets,
        "class_by_id": {row["class_id"]: row for row in targets},
        "tenant_id": tenant_id,
        "current_id": current_id,
        "legacy_id": legacy_id,
    }


def _load_grades(db, class_ids: set[str], course_id: str) -> list[dict[str, Any]]:
    return list(db.grades.find(
        {
            "class_id": {"$in": sorted(class_ids)},
            "course_id": course_id,
            **_year_filter(),
        },
        GRADE_PROJECTION,
    ))


def _nonempty_fields(row: Mapping[str, Any]) -> set[str]:
    return {field for field in PEDAGOGICAL_FIELDS if row.get(field) is not None}


def _classify_pair(legacy: Mapping[str, Any], current: Mapping[str, Any]) -> str:
    legacy_fields = _nonempty_fields(legacy)
    current_fields = _nonempty_fields(current)
    overlap = legacy_fields & current_fields
    for field in overlap:
        if legacy.get(field) != current.get(field):
            return "BOTH_CONFLICTING"
    if all(legacy.get(field) == current.get(field) for field in PEDAGOGICAL_FIELDS):
        return "BOTH_IDENTICAL"
    if legacy_fields.isdisjoint(current_fields) or all(
        legacy.get(field) == current.get(field) for field in overlap
    ):
        return "BOTH_COMPLEMENTARY"
    return "BOTH_CONFLICTING"


def _ownership_summary(row: Mapping[str, Any], current_assignment_ids: set[str]) -> str:
    ownership = row.get("grade_ownership") or {}
    if not isinstance(ownership, Mapping) or not ownership:
        return "NO_OWNERSHIP"
    owner_ids = {
        _sid(snapshot.get("assignment_id"))
        for field, snapshot in ownership.items()
        if field in OWNERSHIP_FIELDS and isinstance(snapshot, Mapping) and _sid(snapshot.get("assignment_id"))
    }
    if not owner_ids:
        return "OWNERSHIP_WITHOUT_ASSIGNMENT_ID"
    own = owner_ids & current_assignment_ids
    foreign = owner_ids - current_assignment_ids
    if own and foreign:
        return "MIXED_CURRENT_AND_FOREIGN_OWNERSHIP"
    if own:
        return "CURRENT_ASSIGNMENT_OWNERSHIP"
    return "FOREIGN_OR_HISTORICAL_ASSIGNMENT_OWNERSHIP"


def _current_assignment_ids(db, context: Mapping[str, Any], teacher_user_id: str) -> set[str]:
    class_ids = sorted(context["class_by_id"])
    rows = list(db.teacher_class_assignments.find(
        {
            "class_id": {"$in": class_ids},
            "component_id": context["current_id"],
            "teacher_id": teacher_user_id,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "deleted": {"$ne": True},
        },
        {"_id": 0, "id": 1, "class_id": 1, "component_id": 1, "teacher_id": 1},
    ))
    return {_sid(row.get("id")) for row in rows if _sid(row.get("id"))}


def _enrollment_keys(db, class_ids: set[str]) -> set[tuple[str, str]]:
    rows = list(db.enrollments.find(
        {
            "class_id": {"$in": sorted(class_ids)},
            "$or": [
                {"academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
                {"academic_year": {"$exists": False}},
                {"academic_year": None},
            ],
            "status": {"$ne": "cancelled"},
        },
        {"_id": 0, "class_id": 1, "student_id": 1},
    ))
    return {
        (_sid(row.get("class_id")), _sid(row.get("student_id")))
        for row in rows
        if _sid(row.get("class_id")) and _sid(row.get("student_id"))
    }


def _group_by_student(rows: list[Mapping[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (_sid(row.get("class_id")), _sid(row.get("student_id")))
        if not all(key):
            raise RuntimeError("ANA_LUCIA_G1_GRADE_KEY_MISSING")
        out[key].append(dict(row))
    return out


def run_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("ANA_LUCIA_G1_MONGO_URL_MISSING")

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
    try:
        db = client[db_name]
        user, staff = _unique_teacher_identity(db)
        context = _resolve_context(db, user, staff)
        class_ids = set(context["class_by_id"])
        legacy_rows = _load_grades(db, class_ids, context["legacy_id"])
        current_rows = _load_grades(db, class_ids, context["current_id"])
        legacy_map = _group_by_student(legacy_rows)
        current_map = _group_by_student(current_rows)
        enrollment_keys = _enrollment_keys(db, class_ids)
        current_assignment_ids = _current_assignment_ids(db, context, _sid(user.get("id")))

        classifications: Counter[str] = Counter()
        ownership: Counter[str] = Counter()
        provenance: Counter[str] = Counter()
        class_counts: dict[str, Counter[str]] = {
            row["class"]: Counter() for row in context["targets"]
        }
        class_name_by_id = {row["class_id"]: row["class"] for row in context["targets"]}

        all_keys = enrollment_keys | set(legacy_map) | set(current_map)
        for key in sorted(all_keys):
            legacy = legacy_map.get(key, [])
            current = current_map.get(key, [])
            class_name = class_name_by_id.get(key[0], "UNKNOWN")
            if len(legacy) > 1:
                classifications["DUPLICATE_LEGACY"] += 1
                class_counts[class_name]["DUPLICATE_LEGACY"] += 1
                continue
            if len(current) > 1:
                classifications["DUPLICATE_CANONICAL"] += 1
                class_counts[class_name]["DUPLICATE_CANONICAL"] += 1
                continue
            if legacy and not current:
                category = "LEGACY_ONLY"
            elif current and not legacy:
                category = "CANONICAL_ONLY"
            elif legacy and current:
                category = _classify_pair(legacy[0], current[0])
            else:
                category = "NO_GRADE"
            classifications[category] += 1
            class_counts[class_name][category] += 1

            for row in legacy + current:
                ownership[_ownership_summary(row, current_assignment_ids)] += 1
                if row.get("migrated_from_class_id"):
                    provenance["MIGRATED_FROM_CLASS"] += 1
                if row.get("rectified_fields"):
                    provenance["RECTIFIED_FIELDS"] += 1
                if row.get("assignment_id"):
                    provenance["TOP_LEVEL_ASSIGNMENT_ID"] += 1
                tenant = _sid(row.get("mantenedora_id"))
                if tenant:
                    if tenant == context["tenant_id"]:
                        provenance["TENANT_MATCH"] += 1
                    else:
                        provenance["TENANT_MISMATCH"] += 1
                else:
                    provenance["TENANT_MISSING"] += 1

        if provenance["TENANT_MISMATCH"]:
            raise RuntimeError("ANA_LUCIA_G1_TENANT_MISMATCH")

        blocking = {
            name: int(classifications.get(name, 0))
            for name in (
                "BOTH_IDENTICAL", "BOTH_COMPLEMENTARY", "BOTH_CONFLICTING",
                "DUPLICATE_LEGACY", "DUPLICATE_CANONICAL",
            )
            if classifications.get(name, 0)
        }
        safe_course_id_only = not blocking

        return {
            "schema": "ANA_LUCIA_G1_GRADES_AUDIT_V1",
            "status": "READ_ONLY_AUDIT_COMPLETE",
            "production_writes": False,
            "database_mutation": False,
            "academic_year": ACADEMIC_YEAR,
            "target_pair_count": len(context["targets"]),
            "legacy_course_fingerprint": _fp(context["legacy_id"]),
            "current_course_fingerprint": _fp(context["current_id"]),
            "legacy_grade_documents": len(legacy_rows),
            "current_grade_documents": len(current_rows),
            "enrollment_student_pairs": len(enrollment_keys),
            "classifications": dict(sorted(classifications.items())),
            "ownership": dict(sorted(ownership.items())),
            "provenance": dict(sorted(provenance.items())),
            "blocking_collisions": blocking,
            "safe_course_id_only_remap": safe_course_id_only,
            "current_assignment_count": len(current_assignment_ids),
            "per_class": {
                class_name: dict(sorted(counts.items()))
                for class_name, counts in class_counts.items()
            },
            "privacy": {
                "student_ids_emitted": False,
                "student_names_read": False,
                "grade_values_emitted": False,
                "grade_values_read_for_classification_only": True,
            },
        }
    finally:
        client.close()


def main() -> int:
    payload = run_audit()
    print("ANA_LUCIA_G1_JSON=" + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
