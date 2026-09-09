#!/usr/bin/env python3
"""F2.3 — preflight read-only de um caso real de retificação.

Este script é executado dentro do backend de produção por um gate owner-only.
Ele:
- resolve escola/turmas por identidade canônica;
- localiza a estudante somente por fingerprint salted de nome+nascimento;
- chama o dry-run canônico já publicado;
- emite evidência sanitizada, sem PII e sem IDs técnicos brutos.

Nenhuma função de preparação, execução ou rollback é importada/chamada.
Nenhuma escrita Mongo é permitida neste arquivo.
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

from services.enrollment_rectification import (
    RectificationDryRunError,
    build_rectification_dry_run,
)


SCHEMA = "ENROLLMENT_RECTIFICATION_F2_3_CASE_PREFLIGHT_V1"
TARGET_SCHOOL = "E M E I E F Monsenhor Augusto Dias de Brito"
SOURCE_CLASS = "6º ANO B"
DESTINATION_CLASS = "7º ANO B"
ACADEMIC_YEAR = 2026


def _execution_flag_enabled() -> bool:
    return os.environ.get(
        "ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "false"
    ).strip().lower() == "true"


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
    if not raw:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return raw


def identity_fingerprint(salt: str, full_name: Any, birth_date: Any) -> str:
    material = f"{salt}|{_norm(full_name)}|{_normalize_birth_date(birth_date)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _code_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get("code") or "UNKNOWN") for item in items).items()))


def _safe_course_map(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_name": item.get("source_name"),
            "target_name": item.get("target_name"),
            "method": item.get("method"),
            "ok": bool(item.get("ok")),
        }
        for item in items
    ]


def _safe_summary(
    dry_run: dict[str, Any],
    *,
    identity_hash: str,
    projection_matches_source: bool,
) -> dict[str, Any]:
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
        "identity_fingerprint": identity_hash,
        "student_projection_matches_source": projection_matches_source,
        "contract_version": dry_run.get("contract_version"),
        "operation": dry_run.get("operation"),
        "execution_enabled_from_dry_run": bool(dry_run.get("execution_enabled")),
        "execution_flag_enabled": _execution_flag_enabled(),
        "can_execute_later": bool(dry_run.get("can_execute_later")),
        "counts": dry_run.get("counts") or {},
        "course_map": _safe_course_map(list(dry_run.get("course_map") or [])),
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


async def run_live_preflight() -> dict[str, Any]:
    salt = os.environ.get("F2_3_IDENTITY_SALT", "").strip()
    expected_hash = os.environ.get("F2_3_IDENTITY_HASH", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", salt):
        raise RuntimeError("F2_3_IDENTITY_SALT_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise RuntimeError("F2_3_IDENTITY_HASH_INVALID")

    mongo_url = os.environ.get("MONGO_URL", "").strip()
    db_name = os.environ.get("DB_NAME", "").strip()
    if not mongo_url or not db_name:
        raise RuntimeError("F2_3_DATABASE_ENV_MISSING")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    try:
        schools = await db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}).to_list(None)
        school_matches = [item for item in schools if _norm(item.get("name")) == _norm(TARGET_SCHOOL)]
        if len(school_matches) != 1:
            return {
                "schema": SCHEMA,
                "status": "BLOCKED",
                "reason": "SCHOOL_CARDINALITY_INVALID",
                "school_match_count": len(school_matches),
                "database_mutation": False,
                "production_writes": False,
                "student_pii_emitted": False,
                "technical_ids_emitted": False,
            }
        school = school_matches[0]
        tenant_id = str(school.get("mantenedora_id") or "")
        school_id = str(school.get("id") or "")
        if not tenant_id or not school_id:
            return {
                "schema": SCHEMA,
                "status": "BLOCKED",
                "reason": "SCHOOL_IDENTITY_INCOMPLETE",
                "database_mutation": False,
                "production_writes": False,
                "student_pii_emitted": False,
                "technical_ids_emitted": False,
            }

        class_docs = await db.classes.find(
            {
                "mantenedora_id": tenant_id,
                "school_id": school_id,
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            },
            {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1, "academic_year": 1},
        ).to_list(None)
        source_matches = [item for item in class_docs if _norm(item.get("name")) == _norm(SOURCE_CLASS)]
        destination_matches = [item for item in class_docs if _norm(item.get("name")) == _norm(DESTINATION_CLASS)]
        if len(source_matches) != 1 or len(destination_matches) != 1:
            return {
                "schema": SCHEMA,
                "status": "BLOCKED",
                "reason": "CLASS_CARDINALITY_INVALID",
                "source_class_match_count": len(source_matches),
                "destination_class_match_count": len(destination_matches),
                "database_mutation": False,
                "production_writes": False,
                "student_pii_emitted": False,
                "technical_ids_emitted": False,
            }
        source = source_matches[0]
        destination = destination_matches[0]
        source_id = str(source.get("id") or "")
        destination_id = str(destination.get("id") or "")

        enrollments = await db.enrollments.find(
            {
                "mantenedora_id": tenant_id,
                "class_id": source_id,
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
                "status": "active",
            },
            {"_id": 0, "student_id": 1},
        ).to_list(None)
        candidate_ids = sorted({str(item.get("student_id")) for item in enrollments if item.get("student_id")})
        students = await db.students.find(
            {
                "mantenedora_id": tenant_id,
                "id": {"$in": candidate_ids},
            },
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "class_id": 1},
        ).to_list(None)
        identity_matches = [
            item for item in students
            if identity_fingerprint(salt, item.get("full_name"), item.get("birth_date")) == expected_hash
        ]
        if len(identity_matches) != 1:
            return {
                "schema": SCHEMA,
                "status": "BLOCKED",
                "reason": "STUDENT_IDENTITY_CARDINALITY_INVALID",
                "candidate_count": len(students),
                "identity_match_count": len(identity_matches),
                "database_mutation": False,
                "production_writes": False,
                "student_pii_emitted": False,
                "technical_ids_emitted": False,
            }

        student = identity_matches[0]
        student_id = str(student.get("id") or "")
        projection_matches_source = str(student.get("class_id") or "") == source_id

        try:
            dry_run = await build_rectification_dry_run(
                db,
                student_id=student_id,
                destination_class_id=destination_id,
                tenant_id=tenant_id,
                actor={"id": "f2-3-readonly-preflight", "role": "super_admin"},
            )
        except RectificationDryRunError as exc:
            return {
                "schema": SCHEMA,
                "status": "BLOCKED",
                "reason": "CANONICAL_DRY_RUN_ERROR",
                "dry_run_error_code": exc.code,
                "dry_run_error_status": exc.status_code,
                "identity_match_count": 1,
                "identity_fingerprint": expected_hash,
                "student_projection_matches_source": projection_matches_source,
                "execution_flag_enabled": _execution_flag_enabled(),
                "dry_run_invoked": True,
                "database_mutation": False,
                "production_writes": False,
                "prepare_execution_called": False,
                "execute_called": False,
                "rollback_called": False,
                "feature_flag_modified": False,
                "student_pii_emitted": False,
                "technical_ids_emitted": False,
            }

        return _safe_summary(
            dry_run,
            identity_hash=expected_hash,
            projection_matches_source=projection_matches_source,
        )
    finally:
        client.close()


def main() -> None:
    result = asyncio.run(run_live_preflight())
    print("ENROLLMENT_RECTIFICATION_F2_3_PREFLIGHT_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
