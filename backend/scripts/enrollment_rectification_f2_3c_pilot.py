#!/usr/bin/env python3
"""F2.3C — executor one-shot do primeiro piloto real de Retificação.

Boundary operacional:
- resolve identidade apenas por hashes salted já aprovados;
- exige operador real + reautenticação por senha lida de arquivo efêmero;
- reutiliza MT-1 canônico com request operacional sintética e tenant explícito;
- gera dry-run F1.0 fresco no runtime publicado;
- prepara pela binding F2.3/F2.2 canônica;
- habilita a feature flag somente dentro deste processo one-shot;
- executa uma única saga;
- desabilita a flag em finally antes da pós-validação;
- em pós-condição inválida, tenta rollback canônico somente quando APPLIED;
- não grava diretamente em coleções acadêmicas: toda mutação passa pela saga.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorClient

from audit_service import audit_service
from services.enrollment_rectification import (
    CONFIRMATION_PHRASE,
    RectificationDryRunError,
    build_rectification_dry_run,
)
from services.enrollment_rectification_documents import (
    DOCUMENT_ACKNOWLEDGEMENT,
    detect_rectification_origin_residues,
)
from services.enrollment_rectification_saga import (
    EXECUTION_FLAG,
    RUNS_COLLECTION,
)
from services.enrollment_rectification_saga_runtime import (
    execute_rectification_saga,
    prepare_rectification_saga_execution,
    rollback_rectification_saga,
    saga_execution_enabled,
)
from tenant_scope import resolve_operational_tenant_context


SCHEMA = "ENROLLMENT_RECTIFICATION_F2_3C_PILOT_V1"
TARGET_SCHOOL = "E M E I E F Monsenhor Augusto Dias de Brito"
SOURCE_CLASS = "6º ANO A"
DESTINATION_CLASS = "7º ANO B"
ACADEMIC_YEAR = 2026
TRACKING_ISSUE = 602
ALLOWED_ROLES = frozenset({"super_admin", "admin", "gerente"})
ALLOWED_WARNING_CODES = frozenset({"DESTINATION_CURRICULUM_WARNING", "SYNC_PDF_LEDGER_GAP"})
NAME_EDIT_ALPHABET = "abcdefghijklmnopqrstuvwxyz "


def _norm(value: Any) -> str:
    if value is None:
        return ""
    text = "".join(
        c
        for c in unicodedata.normalize("NFKD", str(value))
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
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return raw


def _cpf_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _component_hash(salt: str, kind: str, value: str) -> str:
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


def _roles(actor: Mapping[str, Any]) -> set[str]:
    values = {str(role).strip() for role in (actor.get("roles") or []) if role}
    if actor.get("role"):
        values.add(str(actor.get("role")).strip())
    return values


def _request_for_tenant(tenant_id: str) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/admin/enrollment-rectification/prepare-execution",
        "raw_path": b"/api/admin/enrollment-rectification/prepare-execution",
        "query_string": b"",
        "headers": [(b"x-mantenedora-id", tenant_id.encode("utf-8"))],
        "client": ("127.0.0.1", 0),
        "server": ("localhost", 443),
    }
    return Request(scope)


def _warning_codes(dry_run: Mapping[str, Any]) -> list[str]:
    return sorted(
        {
            str(item.get("code"))
            for item in (dry_run.get("warnings") or [])
            if item.get("code")
        }
    )


def _safe_error(exc: Exception) -> dict[str, Any]:
    return {
        "code": str(getattr(exc, "code", exc.__class__.__name__)),
        "status_code": getattr(exc, "status_code", None),
    }


def _load_secret_payload() -> tuple[str, str]:
    path_text = os.environ.get("F2_3C_SECRET_FILE", "").strip()
    if not path_text:
        raise RuntimeError("F2_3C_SECRET_FILE_MISSING")
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
    email = str((payload or {}).get("email") or "").strip()
    password = str((payload or {}).get("password") or "")
    if not email or not password:
        raise RuntimeError("F2_3C_REAUTH_SECRET_PAYLOAD_INVALID")
    return email, password


async def _resolve_case(db, *, salt: str, name_hash: str, dob_hash: str, cpf_hash: str):
    schools = await db.schools.find(
        {},
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    ).to_list(None)
    school_matches = [s for s in schools if _norm(s.get("name")) == _norm(TARGET_SCHOOL)]
    if len(school_matches) != 1:
        raise RuntimeError("F2_3C_SCHOOL_CARDINALITY_INVALID")
    school = school_matches[0]
    school_id = str(school.get("id") or "")
    tenant_id = str(school.get("mantenedora_id") or "")
    if not school_id or not tenant_id:
        raise RuntimeError("F2_3C_SCHOOL_IDENTITY_INCOMPLETE")

    classes = await db.classes.find(
        {
            "mantenedora_id": tenant_id,
            "school_id": school_id,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        },
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(None)
    source_matches = [c for c in classes if _norm(c.get("name")) == _norm(SOURCE_CLASS)]
    destination_matches = [c for c in classes if _norm(c.get("name")) == _norm(DESTINATION_CLASS)]
    if len(source_matches) != 1 or len(destination_matches) != 1:
        raise RuntimeError("F2_3C_CLASS_CARDINALITY_INVALID")
    source_id = str(source_matches[0].get("id") or "")
    destination_id = str(destination_matches[0].get("id") or "")

    class_ids = [str(c.get("id")) for c in classes if c.get("id")]
    enrollments = await db.enrollments.find(
        {
            "mantenedora_id": tenant_id,
            "class_id": {"$in": class_ids},
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "status": "active",
        },
        {"_id": 0, "id": 1, "student_id": 1, "class_id": 1, "academic_year": 1},
    ).to_list(None)
    candidate_ids = sorted(
        {str(item.get("student_id")) for item in enrollments if item.get("student_id")}
    )
    students = await db.students.find(
        {"mantenedora_id": tenant_id, "id": {"$in": candidate_ids}},
        {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "cpf": 1, "class_id": 1},
    ).to_list(None)

    cpf_matches = [
        item
        for item in students
        if _cpf_digits(item.get("cpf"))
        and _component_hash(salt, "cpf", _cpf_digits(item.get("cpf"))) == cpf_hash
    ]
    if len(cpf_matches) != 1:
        raise RuntimeError("F2_3C_CPF_CARDINALITY_INVALID")
    student = cpf_matches[0]

    if _component_hash(
        salt,
        "dob",
        _normalize_birth_date(student.get("birth_date")),
    ) != dob_hash:
        raise RuntimeError("F2_3C_DOB_IDENTITY_MISMATCH")

    normalized_name = _norm(student.get("full_name"))
    name_ok = _component_hash(salt, "name", normalized_name) == name_hash or any(
        _component_hash(salt, "name", variant) == name_hash
        for variant in _one_edit_name_variants(normalized_name)
    )
    if not name_ok:
        raise RuntimeError("F2_3C_NAME_IDENTITY_MISMATCH")

    student_id = str(student.get("id") or "")
    active = [
        item
        for item in enrollments
        if str(item.get("student_id") or "") == student_id
    ]
    if len(active) != 1:
        raise RuntimeError("F2_3C_ACTIVE_ENROLLMENT_CARDINALITY_INVALID")
    source_enrollment_id = str(active[0].get("id") or "")
    if str(active[0].get("class_id") or "") != source_id:
        raise RuntimeError("F2_3C_ACTIVE_SOURCE_CLASS_MISMATCH")
    if str(student.get("class_id") or "") != source_id:
        raise RuntimeError("F2_3C_STUDENT_PROJECTION_SOURCE_MISMATCH")

    return {
        "school_id": school_id,
        "tenant_id": tenant_id,
        "student_id": student_id,
        "source_enrollment_id": source_enrollment_id,
        "source_class_id": source_id,
        "destination_class_id": destination_id,
    }


async def _resolve_actor(db, email: str) -> dict[str, Any]:
    escaped = re.escape(email.strip())
    users = await db.users.find(
        {"email": {"$regex": f"^{escaped}$", "$options": "i"}},
        {
            "_id": 0,
            "id": 1,
            "email": 1,
            "role": 1,
            "roles": 1,
            "mantenedora_id": 1,
            "full_name": 1,
            "name": 1,
            "status": 1,
            "active": 1,
        },
    ).to_list(3)
    if len(users) != 1:
        raise RuntimeError("F2_3C_OPERATOR_CARDINALITY_INVALID")
    actor = dict(users[0])
    if str(actor.get("role") or "").strip() not in ALLOWED_ROLES:
        raise RuntimeError("F2_3C_OPERATOR_ROLE_FORBIDDEN")
    if actor.get("status") in {"inactive", "disabled"} or actor.get("active") is False:
        raise RuntimeError("F2_3C_OPERATOR_INACTIVE")
    return actor


async def _pre_counts(db, case: Mapping[str, str]) -> dict[str, int]:
    tenant = case["tenant_id"]
    student = case["student_id"]
    source = case["source_class_id"]
    destination = case["destination_class_id"]
    year_values = [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]
    return {
        "source_attendance_docs": await db.attendance.count_documents(
            {
                "mantenedora_id": tenant,
                "class_id": source,
                "records.student_id": student,
                "academic_year": {"$in": year_values},
            }
        ),
        "destination_attendance_docs": await db.attendance.count_documents(
            {
                "mantenedora_id": tenant,
                "class_id": destination,
                "records.student_id": student,
                "academic_year": {"$in": year_values},
            }
        ),
        "source_grades": await db.grades.count_documents(
            {
                "mantenedora_id": tenant,
                "student_id": student,
                "class_id": source,
                "academic_year": {"$in": year_values},
            }
        ),
    }


async def _validate_destination(
    db,
    *,
    case: Mapping[str, str],
    pre: Mapping[str, int],
    run: Mapping[str, Any],
) -> dict[str, Any]:
    tenant = case["tenant_id"]
    student = case["student_id"]
    source = case["source_class_id"]
    destination = case["destination_class_id"]
    source_enrollment = case["source_enrollment_id"]
    year_values = [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]

    active = await db.enrollments.find(
        {
            "mantenedora_id": tenant,
            "student_id": student,
            "academic_year": {"$in": year_values},
            "status": "active",
        },
        {"_id": 0, "id": 1, "class_id": 1},
    ).to_list(3)
    student_doc = await db.students.find_one(
        {"mantenedora_id": tenant, "id": student},
        {"_id": 0, "class_id": 1},
    )
    source_attendance = await db.attendance.count_documents(
        {
            "mantenedora_id": tenant,
            "class_id": source,
            "records.student_id": student,
            "academic_year": {"$in": year_values},
        }
    )
    destination_attendance = await db.attendance.count_documents(
        {
            "mantenedora_id": tenant,
            "class_id": destination,
            "records.student_id": student,
            "academic_year": {"$in": year_values},
        }
    )
    source_grades = await db.grades.count_documents(
        {
            "mantenedora_id": tenant,
            "student_id": student,
            "class_id": source,
            "academic_year": {"$in": year_values},
        }
    )
    residues = await detect_rectification_origin_residues(
        db,
        student_id=student,
        source_enrollment_id=source_enrollment,
        source_class_id=source,
        academic_year=ACADEMIC_YEAR,
        tenant_id=tenant,
    )
    protocol = str(run.get("protocol") or "")
    audit_count = await db.audit_logs.count_documents(
        {
            "mantenedora_id": tenant,
            "collection": "enrollments",
            "document_id": source_enrollment,
            "extra_data.protocol": protocol,
        }
    )

    checks = {
        "single_active_enrollment": len(active) == 1,
        "active_enrollment_at_destination": len(active) == 1
        and str(active[0].get("class_id") or "") == destination,
        "student_projection_at_destination": bool(student_doc)
        and str(student_doc.get("class_id") or "") == destination,
        "source_attendance_zero": source_attendance == 0,
        "destination_attendance_not_fabricated": destination_attendance
        == int(pre.get("destination_attendance_docs") or 0),
        "source_grades_zero": source_grades == 0,
        "origin_residues_zero": bool(residues.get("ok")),
        "audit_event_present": audit_count >= 1,
        "run_state_applied": run.get("state") == "APPLIED",
        "academic_mutation_recorded": bool(run.get("academic_mutation_performed")),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "counts": {
            "active_enrollments": len(active),
            "source_attendance_docs": source_attendance,
            "destination_attendance_docs": destination_attendance,
            "source_grades": source_grades,
            "audit_events": audit_count,
        },
    }


async def _validate_origin_restored(
    db,
    *,
    case: Mapping[str, str],
    pre: Mapping[str, int],
) -> dict[str, Any]:
    tenant = case["tenant_id"]
    student = case["student_id"]
    source = case["source_class_id"]
    destination = case["destination_class_id"]
    year_values = [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]

    active = await db.enrollments.find(
        {
            "mantenedora_id": tenant,
            "student_id": student,
            "academic_year": {"$in": year_values},
            "status": "active",
        },
        {"_id": 0, "class_id": 1},
    ).to_list(3)
    student_doc = await db.students.find_one(
        {"mantenedora_id": tenant, "id": student},
        {"_id": 0, "class_id": 1},
    )
    source_attendance = await db.attendance.count_documents(
        {
            "mantenedora_id": tenant,
            "class_id": source,
            "records.student_id": student,
            "academic_year": {"$in": year_values},
        }
    )
    destination_attendance = await db.attendance.count_documents(
        {
            "mantenedora_id": tenant,
            "class_id": destination,
            "records.student_id": student,
            "academic_year": {"$in": year_values},
        }
    )
    source_grades = await db.grades.count_documents(
        {
            "mantenedora_id": tenant,
            "student_id": student,
            "class_id": source,
            "academic_year": {"$in": year_values},
        }
    )
    checks = {
        "single_active_enrollment": len(active) == 1,
        "active_enrollment_restored_to_source": len(active) == 1
        and str(active[0].get("class_id") or "") == source,
        "student_projection_restored_to_source": bool(student_doc)
        and str(student_doc.get("class_id") or "") == source,
        "source_attendance_restored": source_attendance
        == int(pre.get("source_attendance_docs") or 0),
        "destination_attendance_unchanged": destination_attendance
        == int(pre.get("destination_attendance_docs") or 0),
        "source_grades_restored": source_grades == int(pre.get("source_grades") or 0),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "counts": {
            "active_enrollments": len(active),
            "source_attendance_docs": source_attendance,
            "destination_attendance_docs": destination_attendance,
            "source_grades": source_grades,
        },
    }


def _base_result(status: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": status,
        "academic_year": ACADEMIC_YEAR,
        "school": TARGET_SCHOOL,
        "source_class": SOURCE_CLASS,
        "destination_class": DESTINATION_CLASS,
        "tracking_issue": TRACKING_ISSUE,
        "identity_match_count": 1,
        "pii_emitted": False,
        "technical_ids_emitted": False,
        "parent_feature_flag_modified": False,
        "feature_flag_mode": "process_local_ephemeral",
    }


async def run() -> dict[str, Any]:
    expected_sha = os.environ.get("F2_3C_EXPECTED_PRODUCTION_SHA", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise RuntimeError("F2_3C_EXPECTED_PRODUCTION_SHA_INVALID")

    salt = os.environ.get("F2_3_COMPONENT_SALT", "").strip()
    name_hash = os.environ.get("F2_3_NAME_HASH", "").strip().lower()
    dob_hash = os.environ.get("F2_3_DOB_HASH", "").strip().lower()
    cpf_hash = os.environ.get("F2_3_CPF_HASH", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", salt):
        raise RuntimeError("F2_3C_SALT_INVALID")
    if any(
        not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in (name_hash, dob_hash, cpf_hash)
    ):
        raise RuntimeError("F2_3C_IDENTITY_HASH_INVALID")

    if saga_execution_enabled():
        raise RuntimeError("F2_3C_PARENT_FLAG_MUST_START_DISABLED")

    mongo_url = os.environ.get("MONGO_URL", "").strip()
    db_name = os.environ.get("DB_NAME", "").strip()
    if not mongo_url or not db_name:
        raise RuntimeError("F2_3C_DATABASE_ENV_MISSING")

    operator_email, password = _load_secret_payload()
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    audit_service.set_db(db)

    case: dict[str, str] | None = None
    actor: dict[str, Any] | None = None
    prepare_id = ""
    pre: dict[str, int] = {}
    dry_run_warnings: list[str] = []
    academic_window_opened = False

    try:
        case = await _resolve_case(
            db,
            salt=salt,
            name_hash=name_hash,
            dob_hash=dob_hash,
            cpf_hash=cpf_hash,
        )
        actor = await _resolve_actor(db, operator_email)

        request = _request_for_tenant(case["tenant_id"])
        tenant_ctx = await resolve_operational_tenant_context(db, actor, request)
        if str(tenant_ctx.id) != str(case["tenant_id"]):
            raise RuntimeError("F2_3C_TENANT_CONTEXT_MISMATCH")
        actor["active_mantenedora_id"] = case["tenant_id"]

        pre = await _pre_counts(db, case)
        if int(pre.get("destination_attendance_docs") or 0) != 0:
            raise RuntimeError("F2_3C_DESTINATION_ATTENDANCE_PREEXISTS")

        try:
            dry_run = await build_rectification_dry_run(
                db,
                student_id=case["student_id"],
                destination_class_id=case["destination_class_id"],
                tenant_id=case["tenant_id"],
                actor=actor,
            )
        except RectificationDryRunError as exc:
            result = _base_result("BLOCKED_FRESH_DRY_RUN")
            result["error"] = _safe_error(exc)
            return result

        if (
            str((dry_run.get("origin_class") or {}).get("id") or "")
            != case["source_class_id"]
            or str((dry_run.get("destination_class") or {}).get("id") or "")
            != case["destination_class_id"]
        ):
            raise RuntimeError("F2_3C_FRESH_DRY_RUN_CLASS_MISMATCH")
        if dry_run.get("blockers") or not dry_run.get("can_execute_later"):
            result = _base_result("BLOCKED_FRESH_DRY_RUN")
            result["blocker_codes"] = sorted(
                {
                    str(item.get("code"))
                    for item in (dry_run.get("blockers") or [])
                    if item.get("code")
                }
            )
            return result

        dry_run_warnings = _warning_codes(dry_run)
        unexpected_warnings = sorted(set(dry_run_warnings) - ALLOWED_WARNING_CODES)
        if unexpected_warnings:
            result = _base_result("BLOCKED_UNEXPECTED_WARNING")
            result["warning_codes"] = dry_run_warnings
            return result

        dry_run_token = str(dry_run.get("dry_run_token") or "")
        if not dry_run_token:
            raise RuntimeError("F2_3C_FRESH_DRY_RUN_TOKEN_MISSING")

        idempotency_material = "|".join(
            [
                str(TRACKING_ISSUE),
                case["tenant_id"],
                case["student_id"],
                case["source_class_id"],
                case["destination_class_id"],
                str(ACADEMIC_YEAR),
            ]
        )
        idempotency_key = (
            "f2-3c-602-"
            + hashlib.sha256(idempotency_material.encode("utf-8")).hexdigest()[:24]
        )
        justification = (
            "Piloto controlado F2.3C autorizado para corrigir enturmação "
            "documental 2026, com validação e rollback governados."
        )

        try:
            prepared = await prepare_rectification_saga_execution(
                db,
                dry_run_token=dry_run_token,
                tenant_id=case["tenant_id"],
                actor=actor,
                password=password,
                confirmation=CONFIRMATION_PHRASE,
                justification=justification,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            result = _base_result("PREPARE_FAILED")
            result["error"] = _safe_error(exc)
            result["fresh_dry_run_can_execute"] = True
            result["warning_codes"] = dry_run_warnings
            return result
        finally:
            password = ""

        prepare_id = str(prepared.get("prepare_id") or "")
        if prepared.get("state") != "PREPARED" or not prepare_id:
            raise RuntimeError("F2_3C_PREPARE_STATE_INVALID")
        if prepared.get("academic_mutation_performed"):
            raise RuntimeError("F2_3C_PREPARE_MUTATED_ACADEMIC_STATE")
        if saga_execution_enabled():
            raise RuntimeError("F2_3C_FLAG_ENABLED_BEFORE_EXECUTION_WINDOW")

        execution_error: dict[str, Any] | None = None
        execute_result: dict[str, Any] | None = None
        os.environ[EXECUTION_FLAG] = "true"
        academic_window_opened = True
        try:
            execute_result = await execute_rectification_saga(
                db,
                prepare_id=prepare_id,
                tenant_id=case["tenant_id"],
                actor=actor,
                document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
                request=request,
                audit_service=audit_service,
            )
        except Exception as exc:
            execution_error = _safe_error(exc)
        finally:
            os.environ[EXECUTION_FLAG] = "false"
            academic_window_opened = False

        if saga_execution_enabled():
            raise RuntimeError("F2_3C_FLAG_FAILED_TO_CLOSE")

        run_doc = await db[RUNS_COLLECTION].find_one(
            {"_id": prepare_id, "tenant_id": case["tenant_id"]},
            {"_id": 0},
        )
        run_doc = run_doc or {}

        if execution_error is not None:
            result = _base_result(str(run_doc.get("state") or "EXECUTION_FAILED"))
            result.update(
                {
                    "error": execution_error,
                    "fresh_dry_run_can_execute": True,
                    "warning_codes": dry_run_warnings,
                    "prepare_state": prepared.get("state"),
                    "run_state": run_doc.get("state"),
                    "feature_flag_after": saga_execution_enabled(),
                    "academic_mutation_recorded": bool(
                        run_doc.get("academic_mutation_performed")
                    ),
                }
            )
            if run_doc.get("state") == "FAILED_COMPENSATED":
                result["origin_after_compensation"] = await _validate_origin_restored(
                    db,
                    case=case,
                    pre=pre,
                )
            return result

        if not execute_result or execute_result.get("state") != "APPLIED":
            result = _base_result("EXECUTION_RESULT_INVALID")
            result["run_state"] = run_doc.get("state")
            return result

        post = await _validate_destination(
            db,
            case=case,
            pre=pre,
            run=run_doc,
        )
        if post.get("ok"):
            result = _base_result("APPLIED_VALIDATED")
            result.update(
                {
                    "fresh_dry_run_can_execute": True,
                    "warning_codes": dry_run_warnings,
                    "prepare_state": prepared.get("state"),
                    "run_state": run_doc.get("state"),
                    "attendance_items_applied": int(
                        execute_result.get("attendance_items_applied") or 0
                    ),
                    "grade_items_applied": int(
                        execute_result.get("grade_items_applied") or 0
                    ),
                    "documents_revoked": int(
                        execute_result.get("documents_revoked") or 0
                    ),
                    "postconditions": post,
                    "feature_flag_after": saga_execution_enabled(),
                    "academic_mutation_recorded": True,
                }
            )
            return result

        # Pós-condição falhou depois de APPLIED: flag já está desligada.
        rollback_result: dict[str, Any] | None = None
        rollback_error: dict[str, Any] | None = None
        try:
            rollback_result = await rollback_rectification_saga(
                db,
                prepare_id=prepare_id,
                tenant_id=case["tenant_id"],
                actor=actor,
                justification=(
                    "Rollback automático do piloto F2.3C porque uma ou mais "
                    "pós-condições obrigatórias falharam após APPLIED."
                ),
                request=request,
                audit_service=audit_service,
            )
        except Exception as exc:
            rollback_error = _safe_error(exc)

        latest = await db[RUNS_COLLECTION].find_one(
            {"_id": prepare_id, "tenant_id": case["tenant_id"]},
            {"_id": 0},
        )
        latest = latest or {}
        restored = await _validate_origin_restored(db, case=case, pre=pre)
        result = _base_result(
            "ROLLED_BACK_AFTER_POSTVALIDATION_FAILURE"
            if rollback_result and rollback_result.get("state") == "ROLLED_BACK"
            else "POSTVALIDATION_FAILED_ROLLBACK_FAILED"
        )
        result.update(
            {
                "fresh_dry_run_can_execute": True,
                "warning_codes": dry_run_warnings,
                "postconditions": post,
                "rollback_error": rollback_error,
                "rollback_state": (rollback_result or {}).get("state"),
                "run_state": latest.get("state"),
                "origin_after_rollback": restored,
                "feature_flag_after": saga_execution_enabled(),
            }
        )
        return result

    finally:
        # Belt-and-suspenders: nunca deixar a flag ligada neste processo.
        os.environ[EXECUTION_FLAG] = "false"
        password = ""
        client.close()
        if academic_window_opened:
            # Apenas um marcador interno; a atribuição acima já fecha a janela.
            academic_window_opened = False


def main() -> None:
    try:
        result = asyncio.run(run())
    except Exception as exc:
        result = _base_result("PILOT_ABORTED_PREMUTATION_OR_UNCLASSIFIED")
        result["error"] = _safe_error(exc)
        result["feature_flag_after"] = False
    print(
        "ENROLLMENT_RECTIFICATION_F2_3C_JSON="
        + json.dumps(result, ensure_ascii=False, sort_keys=True)
    )


if __name__ == "__main__":
    main()