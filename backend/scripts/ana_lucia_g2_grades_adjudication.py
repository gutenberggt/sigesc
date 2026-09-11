#!/usr/bin/env python3
"""ANA-LUCIA-G2 — adjudicação read-only para reconciliação de notas.

Parte do baseline G1 e prova, sem escrita, se os 201 documentos legados e 54
canônicos podem ser reconciliados deterministicamente. Não emite PII nem valores.
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
VALUE_FIELDS = ("b1", "b2", "rec_s1", "b3", "b4", "rec_s2", "recovery")
PEDAGOGICAL_FIELDS = VALUE_FIELDS + ("observations",)
G1_BASELINE = {
    "legacy_documents": 201,
    "current_documents": 54,
    "classifications": {
        "LEGACY_ONLY": 149,
        "CANONICAL_ONLY": 2,
        "BOTH_COMPLEMENTARY": 47,
        "BOTH_IDENTICAL": 5,
        "NO_GRADE": 2,
    },
}
PROJECTION = {
    "_id": 0, "id": 1, "student_id": 1, "class_id": 1, "course_id": 1,
    "academic_year": 1, "mantenedora_id": 1, "dependency_id": 1,
    "assignment_id": 1, "grade_ownership": 1, "migrated_from_class_id": 1,
    "rectified_fields": 1, "b1": 1, "b2": 1, "b3": 1, "b4": 1,
    "rec_s1": 1, "rec_s2": 1, "recovery": 1, "observations": 1,
    "final_average": 1, "status": 1, "created_at": 1, "updated_at": 1,
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
    return hashlib.sha256(raw.encode()).hexdigest()[:size] if raw else None


def _teacher(db):
    users = list(db.users.find(
        {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "name": 1, "role": 1, "mantenedora_id": 1},
    ).limit(5))
    users = [u for u in users if _norm(u.get("full_name") or u.get("name")) == _norm(TEACHER_NAME)]
    if len(users) != 1 or users[0].get("role") != "professor":
        raise RuntimeError(f"ANA_LUCIA_G2_TEACHER_INVALID:{len(users)}")
    user = users[0]
    clauses = [{"user_id": user["id"]}]
    if user.get("email"):
        clauses.append({"email": user["email"]})
    staff = list(db.staff.find({"$or": clauses}, {"_id": 0, "id": 1, "mantenedora_id": 1}).limit(5))
    staff = {_sid(s.get("id")): s for s in staff if _sid(s.get("id"))}
    if len(staff) != 1:
        raise RuntimeError(f"ANA_LUCIA_G2_STAFF_INVALID:{len(staff)}")
    return user, next(iter(staff.values()))


def _context(db, user, staff):
    tas = list(db.teacher_assignments.find(
        {"staff_id": staff["id"], "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}, "status": {"$in": list(ACTIVE_STATUSES)}},
        {"_id": 0, "id": 1, "class_id": 1, "course_id": 1, "mantenedora_id": 1},
    ))
    class_ids = sorted({_sid(x.get("class_id")) for x in tas if _sid(x.get("class_id"))})
    classes = list(db.classes.find({"id": {"$in": class_ids}}, {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1}))
    cb = {_sid(x.get("id")): x for x in classes}
    schools = list(db.schools.find({"id": {"$in": sorted({_sid(x.get('school_id')) for x in classes if _sid(x.get('school_id'))})}}, {"_id": 0, "id": 1, "mantenedora_id": 1}))
    sb = {_sid(x.get("id")): x for x in schools}
    cids = sorted({_sid(x.get("course_id")) for x in tas if _sid(x.get("course_id"))})
    courses = list(db.courses.find({"id": {"$in": cids}}, {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1}))
    cob = {_sid(x.get("id")): x for x in courses}
    targets, currents, tenants = [], set(), set()
    for name in TARGET_CLASSES:
        matches = [a for a in tas if _norm((cb.get(_sid(a.get("class_id"))) or {}).get("name")) == _norm(name) and _norm((cob.get(_sid(a.get("course_id"))) or {}).get("name")) == _norm(COMPONENT_NAME)]
        if len(matches) != 1:
            raise RuntimeError(f"ANA_LUCIA_G2_TARGET_NOT_EXACT:{name}:{len(matches)}")
        a = matches[0]; k = cb[_sid(a.get("class_id"))]; s = sb.get(_sid(k.get("school_id"))) or {}
        anchors = {_sid(a.get("mantenedora_id")), _sid(k.get("mantenedora_id")), _sid(s.get("mantenedora_id")), _sid(user.get("mantenedora_id")), _sid(staff.get("mantenedora_id"))} - {""}
        if len(anchors) != 1:
            raise RuntimeError(f"ANA_LUCIA_G2_TENANT_ANCHORS:{name}:{len(anchors)}")
        tid = next(iter(anchors)); cid = _sid(a.get("course_id"))
        currents.add(cid); tenants.add(tid); targets.append({"class": name, "class_id": _sid(k.get("id")), "tenant_id": tid})
    if len(currents) != 1 or len(tenants) != 1:
        raise RuntimeError("ANA_LUCIA_G2_CONTEXT_NOT_UNIQUE")
    current = next(iter(currents)); tenant = next(iter(tenants))
    same = list(db.courses.find({"name": {"$exists": True}, "$or": [{"mantenedora_id": tenant}, {"mantenedora_id": {"$exists": False}}, {"mantenedora_id": None}, {"mantenedora_id": ""}]}, {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1}))
    same = [x for x in same if _norm(x.get("name")) == _norm(COMPONENT_NAME)]
    cm = [x for x in same if _sid(x.get("id")) == current and _norm(x.get("nivel_ensino")) == _norm(CURRENT_LEVEL)]
    lm = [x for x in same if _norm(x.get("nivel_ensino")) == _norm(LEGACY_LEVEL)]
    if len(cm) != 1 or len(lm) != 1:
        raise RuntimeError(f"ANA_LUCIA_G2_IDENTITIES_INVALID:{len(cm)}:{len(lm)}")
    return {"targets": targets, "class_ids": {x["class_id"] for x in targets}, "tenant_id": tenant, "current_id": current, "legacy_id": _sid(lm[0].get("id"))}


def _grades(db, class_ids, course_id):
    return list(db.grades.find({"class_id": {"$in": sorted(class_ids)}, "course_id": course_id, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}}, PROJECTION))


def _groups(rows):
    out = defaultdict(list)
    for row in rows:
        key = (_sid(row.get("class_id")), _sid(row.get("student_id")))
        if not all(key):
            raise RuntimeError("ANA_LUCIA_G2_KEY_MISSING")
        out[key].append(row)
    return out


def _enrollment_keys(db, class_ids):
    rows = list(db.enrollments.find({"class_id": {"$in": sorted(class_ids)}, "status": {"$ne": "cancelled"}}, {"_id": 0, "class_id": 1, "student_id": 1}))
    return {(_sid(x.get("class_id")), _sid(x.get("student_id"))) for x in rows if _sid(x.get("class_id")) and _sid(x.get("student_id"))}


def _nonempty(row, field):
    return row.get(field) not in (None, "", [], {})


def _classify(legacy, current):
    if len(legacy) > 1: return "DUPLICATE_LEGACY"
    if len(current) > 1: return "DUPLICATE_CANONICAL"
    if legacy and not current: return "LEGACY_ONLY"
    if current and not legacy: return "CANONICAL_ONLY"
    if not legacy and not current: return "NO_GRADE"
    a, b = legacy[0], current[0]
    for f in PEDAGOGICAL_FIELDS:
        if _nonempty(a, f) and _nonempty(b, f) and a.get(f) != b.get(f):
            return "BOTH_CONFLICTING"
    if all(a.get(f) == b.get(f) for f in PEDAGOGICAL_FIELDS):
        return "BOTH_IDENTICAL"
    return "BOTH_COMPLEMENTARY"


def run():
    url = os.environ.get("MONGO_URL"); name = os.environ.get("DB_NAME", "sigesc")
    if not url: raise RuntimeError("ANA_LUCIA_G2_MONGO_URL_MISSING")
    client = MongoClient(url, serverSelectionTimeoutMS=10000)
    try:
        db = client[name]; user, staff = _teacher(db); ctx = _context(db, user, staff)
        legacy = _grades(db, ctx["class_ids"], ctx["legacy_id"]); current = _grades(db, ctx["class_ids"], ctx["current_id"])
        if len(legacy) != G1_BASELINE["legacy_documents"] or len(current) != G1_BASELINE["current_documents"]:
            raise RuntimeError(f"ANA_LUCIA_G2_G1_DOCUMENT_DRIFT:{len(legacy)}:{len(current)}")
        lg, cg = _groups(legacy), _groups(current); keys = _enrollment_keys(db, ctx["class_ids"]) | set(lg) | set(cg)
        classes = Counter(); copies = Counter(); equal_overlaps = Counter(); source_migrated = Counter(); dest_migrated = Counter(); source_rectified = Counter(); dest_rectified = Counter(); dependency = Counter(); assignment = Counter(); tenant = Counter(); metadata_conflicts = Counter()
        for key in keys:
            ls, cs = lg.get(key, []), cg.get(key, []); cat = _classify(ls, cs); classes[cat] += 1
            for role, rows in (("source", ls), ("dest", cs)):
                for row in rows:
                    if row.get("dependency_id"): dependency[role] += 1
                    if row.get("assignment_id"): assignment[role] += 1
                    if row.get("migrated_from_class_id"): (source_migrated if role == "source" else dest_migrated)[cat] += 1
                    if row.get("rectified_fields"): (source_rectified if role == "source" else dest_rectified)[cat] += 1
                    rid = _sid(row.get("mantenedora_id"))
                    tenant["missing" if not rid else ("match" if rid == ctx["tenant_id"] else "mismatch")] += 1
                    if row.get("grade_ownership"): metadata_conflicts["grade_ownership_present"] += 1
            if cat == "BOTH_COMPLEMENTARY":
                a, b = ls[0], cs[0]
                for f in PEDAGOGICAL_FIELDS:
                    av, bv = _nonempty(a, f), _nonempty(b, f)
                    if av and not bv: copies[f] += 1
                    elif av and bv and a.get(f) == b.get(f): equal_overlaps[f] += 1
                    elif av and bv and a.get(f) != b.get(f): metadata_conflicts["value_conflict"] += 1
                # Granular metadata may only be merged when destination has no different entry.
                sr, dr = a.get("rectified_fields") or {}, b.get("rectified_fields") or {}
                for f in PEDAGOGICAL_FIELDS:
                    if f in sr and f in dr and sr.get(f) != dr.get(f): metadata_conflicts["rectified_field_conflict"] += 1
            elif cat == "BOTH_IDENTICAL":
                a, b = ls[0], cs[0]; sr, dr = a.get("rectified_fields") or {}, b.get("rectified_fields") or {}
                for f in PEDAGOGICAL_FIELDS:
                    if f in sr and f in dr and sr.get(f) != dr.get(f): metadata_conflicts["identical_rectified_conflict"] += 1
        expected = Counter(G1_BASELINE["classifications"])
        if classes != expected:
            raise RuntimeError("ANA_LUCIA_G2_G1_CLASSIFICATION_DRIFT:" + json.dumps(dict(classes), sort_keys=True))
        blockers = {}
        for k, v in {**dependency, **{f"assignment_{k}": v for k,v in assignment.items()}, **metadata_conflicts}.items():
            if v: blockers[k] = v
        if tenant["mismatch"]: blockers["tenant_mismatch"] = tenant["mismatch"]
        safe = not blockers
        return {
            "schema": "ANA_LUCIA_G2_GRADES_ADJUDICATION_V1", "status": "DETERMINISTIC_PLAN" if safe else "REVIEW_REQUIRED",
            "production_writes": False, "database_mutation": False, "target_pair_count": 8,
            "legacy_course_fingerprint": _fp(ctx["legacy_id"]), "current_course_fingerprint": _fp(ctx["current_id"]),
            "documents": {"legacy": len(legacy), "canonical": len(current)}, "classifications": dict(sorted(classes.items())),
            "plan": {"REMAP_LEGACY_ONLY": classes["LEGACY_ONLY"], "MERGE_AND_RETIRE_COMPLEMENTARY": classes["BOTH_COMPLEMENTARY"], "RETIRE_IDENTICAL_LEGACY": classes["BOTH_IDENTICAL"], "KEEP_CANONICAL_ONLY": classes["CANONICAL_ONLY"], "NO_GRADE": classes["NO_GRADE"]},
            "field_copies": dict(sorted(copies.items())), "equal_overlap_fields": dict(sorted(equal_overlaps.items())),
            "source_migrated_from_class": dict(sorted(source_migrated.items())), "destination_migrated_from_class": dict(sorted(dest_migrated.items())),
            "source_rectified_docs": dict(sorted(source_rectified.items())), "destination_rectified_docs": dict(sorted(dest_rectified.items())),
            "dependency_docs": dict(sorted(dependency.items())), "top_level_assignment_docs": dict(sorted(assignment.items())),
            "tenant": dict(sorted(tenant.items())), "blockers": blockers, "safe_to_execute_g3": safe,
            "expected_post": {"canonical_documents": 203, "legacy_documents": 0, "no_grade_pairs": 2},
            "privacy": {"student_ids_emitted": False, "student_names_read": False, "grade_values_emitted": False},
        }
    finally:
        client.close()


def main():
    print("ANA_LUCIA_G2_JSON=" + json.dumps(run(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0

if __name__ == "__main__": sys.exit(main())
