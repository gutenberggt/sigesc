#!/usr/bin/env python3
"""F2.3 — localização escolar ampla da identidade do caso, estritamente read-only.

Usa hashes salted independentes de nome, nascimento e CPF. Primeiro procura no
roster ativo de 2026 da escola autorizada; depois nos estudantes associados à
escola; por fim, apenas para diagnóstico de vínculo escolar incorreto, no tenant.
Nunca emite PII ou IDs técnicos e nunca altera dados.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import unicodedata
from datetime import date, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

SCHEMA = "ENROLLMENT_RECTIFICATION_F2_3_SCHOOLWIDE_IDENTITY_V1"
TARGET_SCHOOL = "E M E I E F Monsenhor Augusto Dias de Brito"
DECLARED_SOURCE = "6º ANO B"
DECLARED_DESTINATION = "7º ANO B"
ACADEMIC_YEAR = 2026
NAME_EDIT_ALPHABET = "abcdefghijklmnopqrstuvwxyz "


def _norm(value: Any) -> str:
    if value is None:
        return ""
    text = "".join(
        c for c in unicodedata.normalize("NFKD", str(value))
        if not unicodedata.combining(c)
    )
    return " ".join(text.casefold().strip().split())


def _normalize_birth_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo}-{d}"
    return raw


def _cpf_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def component_hash(salt: str, kind: str, value: str) -> str:
    return hashlib.sha256(f"{salt}|{kind}|{value}".encode("utf-8")).hexdigest()


def _one_edit_name_variants(value: Any) -> set[str]:
    source = _norm(value)
    if not source:
        return set()
    out: set[str] = set()
    n = len(source)
    for i in range(n):
        out.add(_norm(source[:i] + source[i + 1 :]))
    for i in range(n - 1):
        if source[i] != source[i + 1]:
            out.add(_norm(source[:i] + source[i + 1] + source[i] + source[i + 2 :]))
    for i in range(n):
        for ch in NAME_EDIT_ALPHABET:
            if ch != source[i]:
                out.add(_norm(source[:i] + ch + source[i + 1 :]))
    for i in range(n + 1):
        for ch in NAME_EDIT_ALPHABET:
            out.add(_norm(source[:i] + ch + source[i:]))
    out.discard(source)
    out.discard("")
    return out


def _execution_flag_enabled() -> bool:
    return os.environ.get("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "false").strip().lower() == "true"


def _base(status: str, reason: str | None = None, **fields: Any) -> dict[str, Any]:
    result = {
        "schema": SCHEMA,
        "status": status,
        **fields,
        "execution_flag_enabled": _execution_flag_enabled(),
        "database_mutation": False,
        "production_writes": False,
        "prepare_execution_called": False,
        "execute_called": False,
        "rollback_called": False,
        "feature_flag_modified": False,
        "student_pii_emitted": False,
        "technical_ids_emitted": False,
    }
    if reason:
        result["reason"] = reason
    return result


def resolve_by_components(
    students: list[dict[str, Any]], *, salt: str,
    name_hash: str, dob_hash: str, cpf_hash: str,
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any]]:
    docs = {str(s.get("id") or ""): s for s in students if s.get("id")}
    exact_name: set[str] = set()
    edit_name: set[str] = set()
    exact_dob: set[str] = set()
    exact_cpf: set[str] = set()
    for sid, s in docs.items():
        name = _norm(s.get("full_name"))
        dob = _normalize_birth_date(s.get("birth_date"))
        cpf = _cpf_digits(s.get("cpf"))
        if component_hash(salt, "name", name) == name_hash:
            exact_name.add(sid)
        elif any(component_hash(salt, "name", v) == name_hash for v in _one_edit_name_variants(name)):
            edit_name.add(sid)
        if component_hash(salt, "dob", dob) == dob_hash:
            exact_dob.add(sid)
        if cpf and component_hash(salt, "cpf", cpf) == cpf_hash:
            exact_cpf.add(sid)

    counts = {
        "candidate_count": len(docs),
        "name_exact_count": len(exact_name),
        "name_one_edit_count": len(edit_name),
        "dob_exact_count": len(exact_dob),
        "cpf_exact_count": len(exact_cpf),
        "name_dob_count": len(exact_name & exact_dob),
        "name_cpf_count": len(exact_name & exact_cpf),
        "dob_cpf_count": len(exact_dob & exact_cpf),
        "one_edit_name_dob_count": len(edit_name & exact_dob),
        "one_edit_name_cpf_count": len(edit_name & exact_cpf),
    }
    methods = [
        ("cpf_exact", exact_cpf),
        ("name_dob_exact", exact_name & exact_dob),
        ("name_cpf_exact", exact_name & exact_cpf),
        ("dob_cpf_exact", exact_dob & exact_cpf),
        ("one_edit_name_cpf", edit_name & exact_cpf),
        ("one_edit_name_dob", edit_name & exact_dob),
    ]
    unique = [(method, ids) for method, ids in methods if len(ids) == 1]
    if not unique:
        return None, None, counts
    unique_ids = {next(iter(ids)) for _, ids in unique}
    if len(unique_ids) != 1:
        counts["unique_method_count"] = len(unique)
        counts["unique_method_agreement"] = False
        return None, "COMPONENT_SIGNAL_CONFLICT", counts
    sid = next(iter(unique_ids))
    counts["unique_method_count"] = len(unique)
    counts["unique_method_agreement"] = True
    method = "+".join(m for m, ids in unique if sid in ids)
    return docs[sid], method, counts


async def run() -> dict[str, Any]:
    salt = os.environ.get("F2_3_COMPONENT_SALT", "").strip()
    hashes = {
        "name": os.environ.get("F2_3_NAME_HASH", "").strip().lower(),
        "dob": os.environ.get("F2_3_DOB_HASH", "").strip().lower(),
        "cpf": os.environ.get("F2_3_CPF_HASH", "").strip().lower(),
    }
    if not re.fullmatch(r"[0-9a-f]{32}", salt):
        raise RuntimeError("F2_3_SCHOOLWIDE_SALT_INVALID")
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()):
        raise RuntimeError("F2_3_SCHOOLWIDE_HASH_INVALID")
    mongo_url = os.environ.get("MONGO_URL", "").strip()
    db_name = os.environ.get("DB_NAME", "").strip()
    if not mongo_url or not db_name:
        raise RuntimeError("F2_3_SCHOOLWIDE_DATABASE_ENV_MISSING")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    try:
        schools = await db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}).to_list(None)
        matches = [s for s in schools if _norm(s.get("name")) == _norm(TARGET_SCHOOL)]
        if len(matches) != 1:
            return _base("BLOCKED", "SCHOOL_CARDINALITY_INVALID", school_match_count=len(matches))
        school = matches[0]
        school_id = str(school.get("id") or "")
        tenant_id = str(school.get("mantenedora_id") or "")
        if not school_id or not tenant_id:
            return _base("BLOCKED", "SCHOOL_IDENTITY_INCOMPLETE")

        classes = await db.classes.find(
            {"mantenedora_id": tenant_id, "school_id": school_id,
             "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(None)
        class_name = {str(c.get("id")): str(c.get("name") or "") for c in classes if c.get("id")}
        class_ids = list(class_name)
        active_enrollments = await db.enrollments.find(
            {"mantenedora_id": tenant_id, "class_id": {"$in": class_ids},
             "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}, "status": "active"},
            {"_id": 0, "student_id": 1, "class_id": 1},
        ).to_list(None)
        active_ids = sorted({str(e.get("student_id")) for e in active_enrollments if e.get("student_id")})
        active_students = await db.students.find(
            {"mantenedora_id": tenant_id, "id": {"$in": active_ids}},
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "cpf": 1, "class_id": 1, "school_id": 1},
        ).to_list(None)
        resolved, method, counts = resolve_by_components(
            active_students, salt=salt, name_hash=hashes["name"], dob_hash=hashes["dob"], cpf_hash=hashes["cpf"]
        )
        if resolved is not None:
            sid = str(resolved.get("id") or "")
            active_classes = sorted({class_name.get(str(e.get("class_id")), "") for e in active_enrollments if str(e.get("student_id")) == sid} - {""})
            projection = class_name.get(str(resolved.get("class_id") or ""), "")
            declared_source_active = any(_norm(v) == _norm(DECLARED_SOURCE) for v in active_classes)
            return _base(
                "FOUND", None, scope="active_target_school_roster", identity_resolution_method=method,
                identity_match_count=1, active_enrollment_count=len(active_classes),
                current_active_classes=active_classes, projection_class_name=projection or None,
                declared_source_active=declared_source_active,
                declared_destination_active=any(_norm(v) == _norm(DECLARED_DESTINATION) for v in active_classes),
                **counts,
            )
        if method == "COMPONENT_SIGNAL_CONFLICT":
            return _base("BLOCKED", method, scope="active_target_school_roster", **counts)

        school_students = await db.students.find(
            {"mantenedora_id": tenant_id, "school_id": school_id},
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "cpf": 1, "class_id": 1, "school_id": 1},
        ).to_list(None)
        resolved, method, school_counts = resolve_by_components(
            school_students, salt=salt, name_hash=hashes["name"], dob_hash=hashes["dob"], cpf_hash=hashes["cpf"]
        )
        if resolved is not None:
            projection = class_name.get(str(resolved.get("class_id") or ""), "")
            return _base(
                "FOUND", "FOUND_IN_TARGET_SCHOOL_WITHOUT_ACTIVE_ROSTER_MATCH",
                scope="target_school_students", identity_resolution_method=method,
                identity_match_count=1, active_enrollment_count=0,
                current_active_classes=[], projection_class_name=projection or None,
                declared_source_active=False, **school_counts,
            )
        if method == "COMPONENT_SIGNAL_CONFLICT":
            return _base("BLOCKED", method, scope="target_school_students", **school_counts)

        tenant_students = await db.students.find(
            {"mantenedora_id": tenant_id},
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "cpf": 1, "class_id": 1, "school_id": 1},
        ).to_list(None)
        resolved, method, tenant_counts = resolve_by_components(
            tenant_students, salt=salt, name_hash=hashes["name"], dob_hash=hashes["dob"], cpf_hash=hashes["cpf"]
        )
        if resolved is not None:
            return _base(
                "FOUND", "FOUND_OUTSIDE_TARGET_SCHOOL",
                scope="tenant_students", identity_resolution_method=method,
                identity_match_count=1,
                school_matches_target=str(resolved.get("school_id") or "") == school_id,
                declared_source_active=False, **tenant_counts,
            )
        return _base(
            "BLOCKED", method or "IDENTITY_NOT_FOUND_IN_TARGET_SCHOOL_OR_TENANT",
            scope="tenant_students", **tenant_counts,
        )
    finally:
        client.close()


def main() -> None:
    result = asyncio.run(run())
    print("ENROLLMENT_RECTIFICATION_F2_3_SCHOOLWIDE_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
