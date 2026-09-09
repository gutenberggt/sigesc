#!/usr/bin/env python3
"""F2.3C — executor one-shot do piloto controlado 6º A -> 7º B.

Recebe credenciais do operador exclusivamente por stdin JSON. Resolve a estudante
por fingerprints salted, gera dry-run canônico, reautentica e persiste PREPARED
com a flag desligada. A execução acontece em uma janela process-local em que
ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED=true; o finally sempre restaura false.
Em caso de APPLIED com pós-condição inválida, tenta rollback somente pelo contrato
canônico e registra estado sanitizado. Nenhum segredo, PII ou ID técnico é emitido.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from audit_service import AuditService
from services.enrollment_rectification import (
    CONFIRMATION_PHRASE,
    RectificationDryRunError,
    build_rectification_dry_run,
)
from services.enrollment_rectification_documents import (
    DOCUMENT_ACKNOWLEDGEMENT,
    detect_rectification_origin_residues,
)
from services.enrollment_rectification_saga_runtime import (
    RectificationSagaError,
    execute_rectification_saga,
    prepare_rectification_saga_execution,
    rollback_rectification_saga,
)

SCHEMA = "ENROLLMENT_RECTIFICATION_F2_3C_PILOT_V1"
TARGET_SCHOOL = "E M E I E F Monsenhor Augusto Dias de Brito"
SOURCE_CLASS = "6º ANO A"
DESTINATION_CLASS = "7º ANO B"
ACADEMIC_YEAR = 2026
ALLOWED_ROLES = {"super_admin", "admin", "gerente"}
JUSTIFICATION = (
    "Piloto F2.3C autorizado para retificar erro documental de enturmação "
    "do 6º ANO A para o 7º ANO B, preservando rastreabilidade integral."
)
ROLLBACK_JUSTIFICATION = (
    "Rollback automático do piloto F2.3C porque uma pós-condição obrigatória "
    "falhou após a aplicação; restauração canônica autorizada pelo gate humano."
)


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
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return raw


def _cpf_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _component_hash(salt: str, kind: str, value: str) -> str:
    return hashlib.sha256(f"{salt}|{kind}|{value}".encode()).hexdigest()


def _flag() -> bool:
    return os.environ.get(
        "ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "false"
    ).strip().lower() == "true"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16] if value else ""


def _safe_result(**fields: Any) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        **fields,
        "student_pii_emitted": False,
        "operator_secret_emitted": False,
        "technical_ids_emitted": False,
    }


async def _resolve_case(db, *, salt: str, name_hash: str, dob_hash: str, cpf_hash: str):
    schools = await db.schools.find(
        {}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}
    ).to_list(None)
    school_matches = [s for s in schools if _norm(s.get("name")) == _norm(TARGET_SCHOOL)]
    if len(school_matches) != 1:
        raise RuntimeError("PILOT_SCHOOL_CARDINALITY_INVALID")
    school = school_matches[0]
    school_id = str(school.get("id") or "")
    tenant_id = str(school.get("mantenedora_id") or "")
    if not school_id or not tenant_id:
        raise RuntimeError("PILOT_SCHOOL_IDENTITY_INCOMPLETE")

    classes = await db.classes.find(
        {
            "mantenedora_id": tenant_id,
            "school_id": school_id,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        },
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(None)
    source = [c for c in classes if _norm(c.get("name")) == _norm(SOURCE_CLASS)]
    destination = [c for c in classes if _norm(c.get("name")) == _norm(DESTINATION_CLASS)]
    if len(source) != 1 or len(destination) != 1:
        raise RuntimeError("PILOT_CLASS_CARDINALITY_INVALID")
    source_id = str(source[0].get("id") or "")
    destination_id = str(destination[0].get("id") or "")

    enrollments = await db.enrollments.find(
        {
            "mantenedora_id": tenant_id,
            "class_id": source_id,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "status": "active",
        },
        {"_id": 0, "id": 1, "student_id": 1, "class_id": 1},
    ).to_list(None)
    ids = [str(e.get("student_id")) for e in enrollments if e.get("student_id")]
    students = await db.students.find(
        {"mantenedora_id": tenant_id, "id": {"$in": ids}},
        {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "cpf": 1, "class_id": 1},
    ).to_list(None)

    cpf_matches = [
        s for s in students
        if _cpf_digits(s.get("cpf"))
        and _component_hash(salt, "cpf", _cpf_digits(s.get("cpf"))) == cpf_hash
    ]
    if len(cpf_matches) != 1:
        raise RuntimeError("PILOT_CPF_CARDINALITY_INVALID")
    student = cpf_matches[0]
    if _component_hash(salt, "dob", _normalize_birth_date(student.get("birth_date"))) != dob_hash:
        raise RuntimeError("PILOT_DOB_IDENTITY_MISMATCH")

    actual_name = _norm(student.get("full_name"))
    if _component_hash(salt, "name", actual_name) != name_hash:
        alphabet = "abcdefghijklmnopqrstuvwxyz "
        variants = set()
        for i in range(len(actual_name)):
            variants.add(_norm(actual_name[:i] + actual_name[i + 1 :]))
        for i in range(len(actual_name) - 1):
            if actual_name[i] != actual_name[i + 1]:
                variants.add(_norm(actual_name[:i] + actual_name[i + 1] + actual_name[i] + actual_name[i + 2 :]))
        for i in range(len(actual_name)):
            for ch in alphabet:
                if ch != actual_name[i]:
                    variants.add(_norm(actual_name[:i] + ch + actual_name[i + 1 :]))
        for i in range(len(actual_name) + 1):
            for ch in alphabet:
                variants.add(_norm(actual_name[:i] + ch + actual_name[i:]))
        variants.discard("")
        matches = sum(1 for v in variants if _component_hash(salt, "name", v) == name_hash)
        if matches != 1:
            raise RuntimeError("PILOT_NAME_IDENTITY_MISMATCH")

    student_id = str(student.get("id") or "")
    active_all = await db.enrollments.find(
        {
            "mantenedora_id": tenant_id,
            "student_id": student_id,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "status": "active",
        },
        {"_id": 0, "id": 1, "class_id": 1},
    ).to_list(None)
    if len(active_all) != 1 or str(active_all[0].get("class_id") or "") != source_id:
        raise RuntimeError("PILOT_ACTIVE_SOURCE_PRECONDITION_FAILED")
    if str(student.get("class_id") or "") != source_id:
        raise RuntimeError("PILOT_STUDENT_PROJECTION_PRECONDITION_FAILED")

    return {
        "school_id": school_id,
        "tenant_id": tenant_id,
        "source_id": source_id,
        "destination_id": destination_id,
        "student_id": student_id,
        "enrollment_id": str(active_all[0].get("id") or ""),
    }


async def _resolve_operator(db, *, tenant_id: str, email: str) -> dict[str, Any]:
    email = email.strip()
    if not email or len(email) > 320:
        raise RuntimeError("PILOT_OPERATOR_EMAIL_REQUIRED")
    users = await db.users.find(
        {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
        {
            "_id": 0,
            "id": 1,
            "email": 1,
            "role": 1,
            "roles": 1,
            "mantenedora_id": 1,
            "status": 1,
        },
    ).to_list(3)
    if len(users) != 1:
        raise RuntimeError("PILOT_OPERATOR_CARDINALITY_INVALID")
    user = users[0]
    role = str(user.get("role") or "")
    roles = {str(x) for x in (user.get("roles") or []) if x}
    if role:
        roles.add(role)
    if not (roles & ALLOWED_ROLES):
        raise RuntimeError("PILOT_OPERATOR_ROLE_FORBIDDEN")
    if user.get("status") not in (None, "", "active"):
        raise RuntimeError("PILOT_OPERATOR_INACTIVE")
    if "super_admin" not in roles and str(user.get("mantenedora_id") or "") != tenant_id:
        raise RuntimeError("PILOT_OPERATOR_TENANT_MISMATCH")
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "role": role or sorted(roles)[0],
        "roles": sorted(roles),
        "active_mantenedora_id": tenant_id,
        "mantenedora_id": tenant_id,
    }


async def _postvalidate(db, *, case: dict[str, str], prepare_id: str, protocol: str) -> dict[str, Any]:
    tenant = case["tenant_id"]
    student_id = case["student_id"]
    enrollment_id = case["enrollment_id"]
    source = case["source_id"]
    destination = case["destination_id"]

    active = await db.enrollments.find(
        {
            "mantenedora_id": tenant,
            "student_id": student_id,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "status": "active",
        },
        {"_id": 0, "id": 1, "class_id": 1},
    ).to_list(None)
    student = await db.students.find_one(
        {"mantenedora_id": tenant, "id": student_id},
        {"_id": 0, "class_id": 1},
    )
    residues = await detect_rectification_origin_residues(
        db,
        student_id=student_id,
        source_enrollment_id=enrollment_id,
        source_class_id=source,
        academic_year=ACADEMIC_YEAR,
        tenant_id=tenant,
    )
    destination_attendance = await db.attendance.count_documents(
        {
            "mantenedora_id": tenant,
            "class_id": destination,
            "records.student_id": student_id,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        }
    )
    run = await db["enrollment_rectification_runs"].find_one(
        {"_id": prepare_id, "tenant_id": tenant}, {"_id": 0}
    )
    audit_count = await db.audit_logs.count_documents(
        {
            "mantenedora_id": tenant,
            "collection": "enrollments",
            "document_id": enrollment_id,
            "extra_data.protocol": protocol,
        }
    )
    checks = {
        "one_active_enrollment": len(active) == 1,
        "active_enrollment_in_destination": len(active) == 1 and str(active[0].get("class_id") or "") == destination,
        "student_projection_in_destination": bool(student) and str(student.get("class_id") or "") == destination,
        "origin_residues_zero": bool(residues.get("ok")),
        "destination_attendance_not_fabricated": destination_attendance == 0,
        "run_applied": bool(run) and run.get("state") == "APPLIED",
        "audit_event_present": audit_count >= 1,
    }
    return {
        "checks": checks,
        "all_pass": all(checks.values()),
        "origin_residue_counts": residues.get("residues") or {},
        "destination_attendance_documents": int(destination_attendance),
        "run_state": (run or {}).get("state"),
        "audit_event_count": int(audit_count),
    }


async def run(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    required = ("operator_email", "operator_password", "component_salt", "name_hash", "dob_hash", "cpf_hash")
    if any(not str(payload.get(k) or "").strip() for k in required):
        return _safe_result(status="BLOCKED", reason="PILOT_SECURE_INPUT_MISSING", flag_enabled=_flag()), 2
    salt = str(payload["component_salt"]).strip().lower()
    name_hash = str(payload["name_hash"]).strip().lower()
    dob_hash = str(payload["dob_hash"]).strip().lower()
    cpf_hash = str(payload["cpf_hash"]).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", salt) or any(
        not re.fullmatch(r"[0-9a-f]{64}", v) for v in (name_hash, dob_hash, cpf_hash)
    ):
        return _safe_result(status="BLOCKED", reason="PILOT_FINGERPRINT_INVALID", flag_enabled=_flag()), 2
    if _flag():
        return _safe_result(status="BLOCKED", reason="PILOT_FLAG_MUST_START_DISABLED", flag_enabled=True), 2

    mongo_url = os.environ.get("MONGO_URL", "").strip()
    db_name = os.environ.get("DB_NAME", "").strip()
    if not mongo_url or not db_name:
        return _safe_result(status="BLOCKED", reason="PILOT_DATABASE_ENV_MISSING", flag_enabled=_flag()), 2

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    prepare_id = ""
    protocol = ""
    actor: dict[str, Any] | None = None
    case: dict[str, str] | None = None
    flag_ever_enabled = False
    try:
        case = await _resolve_case(
            db, salt=salt, name_hash=name_hash, dob_hash=dob_hash, cpf_hash=cpf_hash
        )
        actor = await _resolve_operator(
            db, tenant_id=case["tenant_id"], email=str(payload["operator_email"])
        )

        try:
            dry_run = await build_rectification_dry_run(
                db,
                student_id=case["student_id"],
                destination_class_id=case["destination_id"],
                tenant_id=case["tenant_id"],
                actor=actor,
            )
        except RectificationDryRunError as exc:
            return _safe_result(
                status="BLOCKED",
                reason="PILOT_CANONICAL_DRY_RUN_ERROR",
                dry_run_error_code=exc.code,
                flag_enabled=_flag(),
            ), 3

        blockers = list(dry_run.get("blockers") or [])
        if blockers or not dry_run.get("can_execute_later"):
            return _safe_result(
                status="BLOCKED",
                reason="PILOT_DRY_RUN_NOT_EXECUTABLE",
                blocker_codes=sorted({str(x.get("code") or "UNKNOWN") for x in blockers}),
                flag_enabled=_flag(),
            ), 3
        token = str(dry_run.get("dry_run_token") or "")
        if not token:
            return _safe_result(status="BLOCKED", reason="PILOT_DRY_RUN_TOKEN_MISSING", flag_enabled=_flag()), 3

        idem = f"f2-3c-602-{os.environ.get('SIGESC_GIT_SHA', 'production')[:12]}"
        prepared = await prepare_rectification_saga_execution(
            db,
            dry_run_token=token,
            tenant_id=case["tenant_id"],
            actor=actor,
            password=str(payload["operator_password"]),
            confirmation=CONFIRMATION_PHRASE,
            justification=JUSTIFICATION,
            idempotency_key=idem,
        )
        prepare_id = str(prepared.get("prepare_id") or "")
        protocol = str(prepared.get("protocol") or "")
        if prepared.get("state") != "PREPARED" or not prepare_id or not protocol:
            return _safe_result(
                status="BLOCKED",
                reason="PILOT_PREPARE_NOT_PREPARED",
                prepared_state=prepared.get("state"),
                flag_enabled=_flag(),
            ), 4
        if _flag():
            return _safe_result(status="BLOCKED", reason="PILOT_FLAG_CHANGED_DURING_PREPARE", flag_enabled=True), 4

        audit = AuditService()
        audit.set_db(db)

        os.environ["ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED"] = "true"
        flag_ever_enabled = True
        try:
            executed = await execute_rectification_saga(
                db,
                prepare_id=prepare_id,
                tenant_id=case["tenant_id"],
                actor=actor,
                document_acknowledgement=DOCUMENT_ACKNOWLEDGEMENT,
                request=None,
                audit_service=audit,
            )
        finally:
            os.environ["ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED"] = "false"

        if executed.get("state") != "APPLIED":
            return _safe_result(
                status="FAILED",
                reason="PILOT_EXECUTION_NOT_APPLIED",
                execution_state=executed.get("state"),
                flag_enabled=_flag(),
                flag_ever_enabled=flag_ever_enabled,
                prepare_digest=_digest(prepare_id),
                protocol_digest=_digest(protocol),
            ), 5

        validation = await _postvalidate(
            db, case=case, prepare_id=prepare_id, protocol=protocol
        )
        if not validation["all_pass"]:
            rollback_state = None
            rollback_error_code = None
            try:
                rolled = await rollback_rectification_saga(
                    db,
                    prepare_id=prepare_id,
                    tenant_id=case["tenant_id"],
                    actor=actor,
                    justification=ROLLBACK_JUSTIFICATION,
                    request=None,
                    audit_service=audit,
                )
                rollback_state = rolled.get("state")
            except RectificationSagaError as exc:
                rollback_error_code = exc.code
            return _safe_result(
                status="FAILED_POSTVALIDATION",
                reason="PILOT_POSTCONDITION_FAILED",
                validation=validation,
                rollback_state=rollback_state,
                rollback_error_code=rollback_error_code,
                flag_enabled=_flag(),
                flag_ever_enabled=flag_ever_enabled,
                prepare_digest=_digest(prepare_id),
                protocol_digest=_digest(protocol),
            ), 6

        return _safe_result(
            status="APPLIED",
            source_class=SOURCE_CLASS,
            destination_class=DESTINATION_CLASS,
            academic_year=ACADEMIC_YEAR,
            dry_run_status="READY",
            prepare_state="PREPARED",
            execution_state="APPLIED",
            validation=validation,
            flag_enabled=_flag(),
            flag_ever_enabled=flag_ever_enabled,
            rollback_called=False,
            prepare_digest=_digest(prepare_id),
            protocol_digest=_digest(protocol),
        ), 0

    except RectificationSagaError as exc:
        run_state = None
        if prepare_id and case:
            doc = await db["enrollment_rectification_runs"].find_one(
                {"_id": prepare_id, "tenant_id": case["tenant_id"]}, {"_id": 0, "state": 1}
            )
            run_state = (doc or {}).get("state")
        return _safe_result(
            status="FAILED",
            reason="PILOT_SAGA_ERROR",
            error_code=exc.code,
            run_state=run_state,
            flag_enabled=_flag(),
            flag_ever_enabled=flag_ever_enabled,
            prepare_digest=_digest(prepare_id),
            protocol_digest=_digest(protocol),
        ), 7
    except Exception as exc:
        return _safe_result(
            status="FAILED",
            reason="PILOT_RUNTIME_ERROR",
            error_type=type(exc).__name__,
            flag_enabled=_flag(),
            flag_ever_enabled=flag_ever_enabled,
            prepare_digest=_digest(prepare_id),
            protocol_digest=_digest(protocol),
        ), 8
    finally:
        os.environ["ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED"] = "false"
        client.close()


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        result, code = _safe_result(
            status="BLOCKED", reason="PILOT_SECURE_INPUT_INVALID", flag_enabled=_flag()
        ), 2
    else:
        result, code = asyncio.run(run(payload))
    result["flag_enabled_at_exit"] = _flag()
    print("ENROLLMENT_RECTIFICATION_F2_3C_PILOT_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
