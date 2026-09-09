#!/usr/bin/env python3
"""F2.3 — dry-run canônico read-only do caso identificado 6º A -> 7º B.

O executor recebe somente hashes salted de identidade. A estudante precisa ser
resolvida de forma 1:1 no roster ativo da escola por CPF exato, nascimento exato
e nome exato ou a uma edição. Além disso, sua única matrícula ativa precisa ser
6º ANO A. Só então o serviço canônico build_rectification_dry_run é chamado para
7º ANO B. Nenhum token operacional, PII ou ID técnico é emitido.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter
from datetime import date, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from services.enrollment_rectification import RectificationDryRunError, build_rectification_dry_run

SCHEMA = "ENROLLMENT_RECTIFICATION_F2_3_IDENTIFIED_DRYRUN_V1"
TARGET_SCHOOL = "E M E I E F Monsenhor Augusto Dias de Brito"
SOURCE_CLASS = "6º ANO A"
DESTINATION_CLASS = "7º ANO B"
ACADEMIC_YEAR = 2026
NAME_EDIT_ALPHABET = "abcdefghijklmnopqrstuvwxyz "


def _norm(value: Any) -> str:
    if value is None:
        return ""
    text = "".join(c for c in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(c))
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
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return raw


def _cpf_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def component_hash(salt: str, kind: str, value: str) -> str:
    return hashlib.sha256(f"{salt}|{kind}|{value}".encode("utf-8")).hexdigest()


def _one_edit_name_variants(value: Any) -> set[str]:
    source = _norm(value)
    if not source:
        return set()
    variants: set[str] = set()
    n = len(source)
    for i in range(n):
        variants.add(_norm(source[:i] + source[i + 1 :]))
    for i in range(n - 1):
        if source[i] != source[i + 1]:
            variants.add(_norm(source[:i] + source[i + 1] + source[i] + source[i + 2 :]))
    for i in range(n):
        for char in NAME_EDIT_ALPHABET:
            if char != source[i]:
                variants.add(_norm(source[:i] + char + source[i + 1 :]))
    for i in range(n + 1):
        for char in NAME_EDIT_ALPHABET:
            variants.add(_norm(source[:i] + char + source[i:]))
    variants.discard(source)
    variants.discard("")
    return variants


def _execution_flag_enabled() -> bool:
    return os.environ.get("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "false").strip().lower() == "true"


def _code_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get("code") or "UNKNOWN") for item in items).items()))


def _blocked(reason: str, **fields: Any) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "BLOCKED",
        "reason": reason,
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


def _safe_summary(dry_run: dict[str, Any]) -> dict[str, Any]:
    grades = list(dry_run.get("grades_manifest") or [])
    attendance = list(dry_run.get("attendance_manifest") or [])
    blockers = list(dry_run.get("blockers") or [])
    warnings = list(dry_run.get("warnings") or [])
    documents = dry_run.get("documents") or {}
    preservation = dry_run.get("preservations") or {}
    origin = dry_run.get("origin_class") or {}
    destination = dry_run.get("destination_class") or {}
    return {
        "schema": SCHEMA,
        "status": "READY_FOR_REVIEW",
        "academic_year": ACADEMIC_YEAR,
        "school": TARGET_SCHOOL,
        "source_class": origin.get("name"),
        "destination_class": destination.get("name"),
        "identity_match_count": 1,
        "identity_resolution_method": "cpf_exact+dob_exact+name_exact_or_one_edit",
        "contract_version": dry_run.get("contract_version"),
        "operation": dry_run.get("operation"),
        "can_execute_later": bool(dry_run.get("can_execute_later")),
        "execution_enabled_from_dry_run": bool(dry_run.get("execution_enabled")),
        "execution_flag_enabled": _execution_flag_enabled(),
        "counts": dry_run.get("counts") or {},
        "grades_summary": {
            "documents": len(grades),
            "migratable_fields": sum(len(item.get("migratable_fields") or []) for item in grades),
            "destination_overlapping_fields": sum(len(item.get("overlapping_fields") or []) for item in grades),
            "metadata_conflicts": sum(len(item.get("destination_metadata_conflicts") or []) for item in grades),
        },
        "attendance_summary": {
            "student_records": len(attendance),
            "validated_source_records": sum(1 for item in attendance if item.get("validated")),
            "destination_overlap_total": sum(int(item.get("destination_overlap_count") or 0) for item in attendance),
        },
        "documents": {
            "coverage_complete": bool(documents.get("coverage_complete")),
            "tracked_total": int(documents.get("tracked_total") or 0),
            "tracked_counts": documents.get("tracked_counts") or {},
            "coverage_gap_code": ((documents.get("coverage_gap") or {}).get("code")),
        },
        "preservations": {
            "content_entries": preservation.get("content_entries"),
            "aee": preservation.get("aee"),
            "bolsa_familia_tracking": preservation.get("bolsa_familia_tracking"),
            "medical_certificates": preservation.get("medical_certificates"),
            "current_counts": preservation.get("current_counts") or {},
        },
        "blocker_code_counts": _code_counts(blockers),
        "warning_code_counts": _code_counts(warnings),
        "expected_postconditions": list(dry_run.get("expected_postconditions") or []),
        "dry_run_invoked": True,
        "dry_run_token_emitted": False,
        "precondition_hash_emitted": False,
        "database_mutation": False,
        "production_writes": False,
        "prepare_execution_called": False,
        "execute_called": False,
        "rollback_called": False,
        "feature_flag_modified": False,
        "student_pii_emitted": False,
        "technical_ids_emitted": False,
    }


async def run() -> dict[str, Any]:
    salt = os.environ.get("F2_3_COMPONENT_SALT", "").strip()
    name_hash = os.environ.get("F2_3_NAME_HASH", "").strip().lower()
    dob_hash = os.environ.get("F2_3_DOB_HASH", "").strip().lower()
    cpf_hash = os.environ.get("F2_3_CPF_HASH", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", salt):
        raise RuntimeError("F2_3_DRYRUN_SALT_INVALID")
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in (name_hash, dob_hash, cpf_hash)):
        raise RuntimeError("F2_3_DRYRUN_HASH_INVALID")
    if _execution_flag_enabled():
        return _blocked("EXECUTION_FLAG_MUST_BE_DISABLED")

    mongo_url = os.environ.get("MONGO_URL", "").strip()
    db_name = os.environ.get("DB_NAME", "").strip()
    if not mongo_url or not db_name:
        raise RuntimeError("F2_3_DRYRUN_DATABASE_ENV_MISSING")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    try:
        schools = await db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}).to_list(None)
        school_matches = [s for s in schools if _norm(s.get("name")) == _norm(TARGET_SCHOOL)]
        if len(school_matches) != 1:
            return _blocked("SCHOOL_CARDINALITY_INVALID", school_match_count=len(school_matches))
        school = school_matches[0]
        school_id = str(school.get("id") or "")
        tenant_id = str(school.get("mantenedora_id") or "")
        if not school_id or not tenant_id:
            return _blocked("SCHOOL_IDENTITY_INCOMPLETE")

        classes = await db.classes.find(
            {"mantenedora_id": tenant_id, "school_id": school_id,
             "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(None)
        source_matches = [c for c in classes if _norm(c.get("name")) == _norm(SOURCE_CLASS)]
        destination_matches = [c for c in classes if _norm(c.get("name")) == _norm(DESTINATION_CLASS)]
        if len(source_matches) != 1 or len(destination_matches) != 1:
            return _blocked("CLASS_CARDINALITY_INVALID",
                            source_class_match_count=len(source_matches),
                            destination_class_match_count=len(destination_matches))
        source_id = str(source_matches[0].get("id") or "")
        destination_id = str(destination_matches[0].get("id") or "")
        class_ids = [str(c.get("id")) for c in classes if c.get("id")]

        enrollments = await db.enrollments.find(
            {"mantenedora_id": tenant_id, "class_id": {"$in": class_ids},
             "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}, "status": "active"},
            {"_id": 0, "student_id": 1, "class_id": 1},
        ).to_list(None)
        candidate_ids = sorted({str(e.get("student_id")) for e in enrollments if e.get("student_id")})
        students = await db.students.find(
            {"mantenedora_id": tenant_id, "id": {"$in": candidate_ids}},
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "cpf": 1, "class_id": 1},
        ).to_list(None)

        cpf_matches = [s for s in students if _cpf_digits(s.get("cpf")) and component_hash(salt, "cpf", _cpf_digits(s.get("cpf"))) == cpf_hash]
        if len(cpf_matches) != 1:
            return _blocked("CPF_CARDINALITY_INVALID", candidate_count=len(students), cpf_match_count=len(cpf_matches))
        student = cpf_matches[0]
        if component_hash(salt, "dob", _normalize_birth_date(student.get("birth_date"))) != dob_hash:
            return _blocked("DOB_IDENTITY_MISMATCH", candidate_count=len(students), cpf_match_count=1)
        normalized_name = _norm(student.get("full_name"))
        name_ok = component_hash(salt, "name", normalized_name) == name_hash or any(
            component_hash(salt, "name", variant) == name_hash for variant in _one_edit_name_variants(normalized_name)
        )
        if not name_ok:
            return _blocked("NAME_IDENTITY_MISMATCH", candidate_count=len(students), cpf_match_count=1, dob_match_count=1)

        student_id = str(student.get("id") or "")
        active = [e for e in enrollments if str(e.get("student_id") or "") == student_id]
        if len(active) != 1:
            return _blocked("ACTIVE_ENROLLMENT_CARDINALITY_INVALID", active_enrollment_count=len(active))
        if str(active[0].get("class_id") or "") != source_id:
            return _blocked("ACTIVE_SOURCE_CLASS_MISMATCH", active_enrollment_count=1)
        if str(student.get("class_id") or "") != source_id:
            return _blocked("STUDENT_PROJECTION_SOURCE_MISMATCH")

        try:
            dry_run = await build_rectification_dry_run(
                db,
                student_id=student_id,
                destination_class_id=destination_id,
                tenant_id=tenant_id,
                actor={"id": "f2-3-identified-readonly", "role": "super_admin"},
            )
        except RectificationDryRunError as exc:
            return _blocked("CANONICAL_DRY_RUN_ERROR",
                            dry_run_error_code=exc.code,
                            dry_run_error_status=exc.status_code,
                            identity_match_count=1,
                            dry_run_invoked=True)
        return _safe_summary(dry_run)
    finally:
        client.close()


def main() -> None:
    result = asyncio.run(run())
    print("ENROLLMENT_RECTIFICATION_F2_3_IDENTIFIED_DRYRUN_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
