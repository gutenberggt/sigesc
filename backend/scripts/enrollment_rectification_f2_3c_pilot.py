#!/usr/bin/env python3
"""F2.3C — execução one-shot pós-PREPARED do piloto 6º A -> 7º B.

Pré-condição: a preparação foi feita no SIGESC autenticado, com reautenticação
canônica por senha. Este executor não recebe credenciais: resolve a estudante
por fingerprints salted e exige exatamente um journal PREPARED compatível. Usa
o mesmo ator persistido no journal, abre a feature flag apenas neste processo,
executa a saga canônica, valida pós-condições e sempre restaura a flag para false.
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
from services.enrollment_rectification_documents import (
    DOCUMENT_ACKNOWLEDGEMENT,
    detect_rectification_origin_residues,
)
from services.enrollment_rectification_saga_runtime import (
    RectificationSagaError,
    execute_rectification_saga,
    rollback_rectification_saga,
)

SCHEMA = "ENROLLMENT_RECTIFICATION_F2_3C_EXECUTE_PREPARED_V1"
TARGET_SCHOOL = "E M E I E F Monsenhor Augusto Dias de Brito"
SOURCE_CLASS = "6º ANO A"
DESTINATION_CLASS = "7º ANO B"
ACADEMIC_YEAR = 2026
RUNS_COLLECTION = "enrollment_rectification_runs"
ROLLBACK_JUSTIFICATION = (
    "Rollback automático do piloto F2.3C porque uma pós-condição obrigatória "
    "falhou após a aplicação; restauração canônica autorizada pelo gate humano."
)


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


def _component_hash(salt: str, kind: str, value: str) -> str:
    return hashlib.sha256(f"{salt}|{kind}|{value}".encode()).hexdigest()


def _name_hash_matches(salt: str, actual: str, wanted: str) -> bool:
    actual = _norm(actual)
    if _component_hash(salt, "name", actual) == wanted:
        return True
    alphabet = "abcdefghijklmnopqrstuvwxyz "
    variants = set()
    for i in range(len(actual)):
        variants.add(_norm(actual[:i] + actual[i + 1:]))
    for i in range(len(actual) - 1):
        if actual[i] != actual[i + 1]:
            variants.add(_norm(actual[:i] + actual[i + 1] + actual[i] + actual[i + 2:]))
    for i in range(len(actual)):
        for ch in alphabet:
            if ch != actual[i]:
                variants.add(_norm(actual[:i] + ch + actual[i + 1:]))
    for i in range(len(actual) + 1):
        for ch in alphabet:
            variants.add(_norm(actual[:i] + ch + actual[i:]))
    variants.discard("")
    return sum(1 for v in variants if _component_hash(salt, "name", v) == wanted) == 1


def _flag() -> bool:
    return os.environ.get("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "false").strip().lower() == "true"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16] if value else ""


def _safe(**fields):
    return {
        "schema": SCHEMA,
        **fields,
        "student_pii_emitted": False,
        "technical_ids_emitted": False,
        "operator_credentials_used": False,
    }


async def _resolve_case(db, *, salt: str, name_hash: str, dob_hash: str, cpf_hash: str):
    schools = await db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}).to_list(None)
    sm = [s for s in schools if _norm(s.get("name")) == _norm(TARGET_SCHOOL)]
    if len(sm) != 1:
        raise RuntimeError("PILOT_SCHOOL_CARDINALITY_INVALID")
    school_id = str(sm[0].get("id") or "")
    tenant = str(sm[0].get("mantenedora_id") or "")
    classes = await db.classes.find(
        {"mantenedora_id": tenant, "school_id": school_id, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(None)
    src = [c for c in classes if _norm(c.get("name")) == _norm(SOURCE_CLASS)]
    dst = [c for c in classes if _norm(c.get("name")) == _norm(DESTINATION_CLASS)]
    if len(src) != 1 or len(dst) != 1:
        raise RuntimeError("PILOT_CLASS_CARDINALITY_INVALID")
    source = str(src[0].get("id") or "")
    destination = str(dst[0].get("id") or "")
    active = await db.enrollments.find(
        {"mantenedora_id": tenant, "class_id": source, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}, "status": "active"},
        {"_id": 0, "id": 1, "student_id": 1, "class_id": 1},
    ).to_list(None)
    ids = [str(e.get("student_id")) for e in active if e.get("student_id")]
    students = await db.students.find(
        {"mantenedora_id": tenant, "id": {"$in": ids}},
        {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "cpf": 1, "class_id": 1},
    ).to_list(None)
    cm = [s for s in students if _cpf_digits(s.get("cpf")) and _component_hash(salt, "cpf", _cpf_digits(s.get("cpf"))) == cpf_hash]
    if len(cm) != 1:
        raise RuntimeError("PILOT_CPF_CARDINALITY_INVALID")
    student = cm[0]
    if _component_hash(salt, "dob", _normalize_birth_date(student.get("birth_date"))) != dob_hash:
        raise RuntimeError("PILOT_DOB_IDENTITY_MISMATCH")
    if not _name_hash_matches(salt, student.get("full_name"), name_hash):
        raise RuntimeError("PILOT_NAME_IDENTITY_MISMATCH")
    sid = str(student.get("id") or "")
    ae = [e for e in active if str(e.get("student_id") or "") == sid]
    if len(ae) != 1 or str(student.get("class_id") or "") != source:
        raise RuntimeError("PILOT_SOURCE_PRECONDITION_FAILED")
    return {
        "school_id": school_id, "tenant_id": tenant, "source_id": source,
        "destination_id": destination, "student_id": sid,
        "enrollment_id": str(ae[0].get("id") or ""),
    }


async def _find_prepared(db, case):
    runs = await db[RUNS_COLLECTION].find(
        {
            "tenant_id": case["tenant_id"],
            "student_id": case["student_id"],
            "source_enrollment_id": case["enrollment_id"],
            "source_class_id": case["source_id"],
            "destination_class_id": case["destination_id"],
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "state": "PREPARED",
            "academic_mutation_performed": False,
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(3)
    if len(runs) != 1:
        raise RuntimeError(f"PILOT_PREPARED_CARDINALITY_INVALID:{len(runs)}")
    run = runs[0]
    actor = dict(run.get("actor") or {})
    if not actor.get("id") or actor.get("role") not in {"super_admin", "admin", "gerente"}:
        raise RuntimeError("PILOT_PREPARED_ACTOR_INVALID")
    actor["active_mantenedora_id"] = case["tenant_id"]
    actor["mantenedora_id"] = case["tenant_id"]
    return run, actor


async def _postvalidate(db, case, run):
    tenant = case["tenant_id"]
    sid = case["student_id"]
    enrollment_id = case["enrollment_id"]
    source = case["source_id"]
    destination = case["destination_id"]
    active = await db.enrollments.find(
        {"mantenedora_id": tenant, "student_id": sid, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}, "status": "active"},
        {"_id": 0, "class_id": 1},
    ).to_list(None)
    student = await db.students.find_one({"mantenedora_id": tenant, "id": sid}, {"_id": 0, "class_id": 1})
    residues = await detect_rectification_origin_residues(
        db, student_id=sid, source_enrollment_id=enrollment_id, source_class_id=source,
        academic_year=ACADEMIC_YEAR, tenant_id=tenant,
    )
    dest_attendance = await db.attendance.count_documents(
        {"mantenedora_id": tenant, "class_id": destination, "records.student_id": sid, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}}
    )
    latest = await db[RUNS_COLLECTION].find_one({"_id": run.get("prepare_id"), "tenant_id": tenant}, {"_id": 0})
    protocol = str(run.get("protocol") or "")
    audit_count = await db.audit_logs.count_documents(
        {"mantenedora_id": tenant, "collection": "enrollments", "document_id": enrollment_id, "extra_data.protocol": protocol}
    )
    checks = {
        "one_active_enrollment": len(active) == 1,
        "active_enrollment_in_destination": len(active) == 1 and str(active[0].get("class_id") or "") == destination,
        "student_projection_in_destination": bool(student) and str(student.get("class_id") or "") == destination,
        "origin_residues_zero": bool(residues.get("ok")),
        "destination_attendance_not_fabricated": dest_attendance == 0,
        "run_applied": bool(latest) and latest.get("state") == "APPLIED",
        "audit_event_present": audit_count >= 1,
    }
    return {
        "all_pass": all(checks.values()),
        "checks": checks,
        "origin_residue_counts": residues.get("residues") or {},
        "destination_attendance_documents": int(dest_attendance),
        "run_state": (latest or {}).get("state"),
        "audit_event_count": int(audit_count),
    }


async def run(payload):
    salt = str(payload.get("component_salt") or "").strip().lower()
    hashes = [str(payload.get(k) or "").strip().lower() for k in ("name_hash", "dob_hash", "cpf_hash")]
    if not re.fullmatch(r"[0-9a-f]{32}", salt) or any(not re.fullmatch(r"[0-9a-f]{64}", x) for x in hashes):
        return _safe(status="BLOCKED", reason="PILOT_FINGERPRINT_INVALID", flag_enabled_at_exit=_flag()), 2
    if _flag():
        return _safe(status="BLOCKED", reason="PILOT_FLAG_MUST_START_DISABLED", flag_enabled_at_exit=True), 2
    mongo_url = os.environ.get("MONGO_URL", "").strip()
    db_name = os.environ.get("DB_NAME", "").strip()
    if not mongo_url or not db_name:
        return _safe(status="BLOCKED", reason="PILOT_DATABASE_ENV_MISSING", flag_enabled_at_exit=_flag()), 2
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    case = None
    prepared = None
    flag_ever_enabled = False
    try:
        case = await _resolve_case(db, salt=salt, name_hash=hashes[0], dob_hash=hashes[1], cpf_hash=hashes[2])
        prepared, actor = await _find_prepared(db, case)
        prepare_id = str(prepared.get("prepare_id") or "")
        protocol = str(prepared.get("protocol") or "")
        if not prepare_id or not protocol:
            raise RuntimeError("PILOT_PREPARED_IDENTITY_INCOMPLETE")

        audit = AuditService()
        audit.set_db(db)
        os.environ["ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED"] = "true"
        flag_ever_enabled = True
        try:
            result = await execute_rectification_saga(
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

        if result.get("state") != "APPLIED":
            return _safe(
                status="FAILED", reason="PILOT_EXECUTION_NOT_APPLIED",
                execution_state=result.get("state"), flag_ever_enabled=flag_ever_enabled,
                flag_enabled_at_exit=_flag(), prepare_digest=_digest(prepare_id),
                protocol_digest=_digest(protocol),
            ), 5

        validation = await _postvalidate(db, case, prepared)
        if not validation["all_pass"]:
            rollback_state = None
            rollback_error_code = None
            try:
                rolled = await rollback_rectification_saga(
                    db, prepare_id=prepare_id, tenant_id=case["tenant_id"], actor=actor,
                    justification=ROLLBACK_JUSTIFICATION, request=None, audit_service=audit,
                )
                rollback_state = rolled.get("state")
            except RectificationSagaError as exc:
                rollback_error_code = exc.code
            return _safe(
                status="FAILED_POSTVALIDATION", reason="PILOT_POSTCONDITION_FAILED",
                validation=validation, rollback_state=rollback_state,
                rollback_error_code=rollback_error_code, flag_ever_enabled=flag_ever_enabled,
                flag_enabled_at_exit=_flag(), prepare_digest=_digest(prepare_id),
                protocol_digest=_digest(protocol),
            ), 6

        return _safe(
            status="APPLIED", source_class=SOURCE_CLASS, destination_class=DESTINATION_CLASS,
            academic_year=ACADEMIC_YEAR, execution_state="APPLIED", validation=validation,
            flag_ever_enabled=flag_ever_enabled, flag_enabled_at_exit=_flag(),
            rollback_called=False, prepare_digest=_digest(prepare_id),
            protocol_digest=_digest(protocol),
        ), 0
    except RectificationSagaError as exc:
        state = None
        if prepared and case:
            current = await db[RUNS_COLLECTION].find_one(
                {"_id": prepared.get("prepare_id"), "tenant_id": case["tenant_id"]}, {"_id": 0, "state": 1}
            )
            state = (current or {}).get("state")
        return _safe(
            status="FAILED", reason="PILOT_SAGA_ERROR", error_code=exc.code,
            run_state=state, flag_ever_enabled=flag_ever_enabled,
            flag_enabled_at_exit=_flag(),
        ), 7
    except Exception as exc:
        return _safe(
            status="FAILED", reason="PILOT_RUNTIME_ERROR", error_type=type(exc).__name__,
            error_code=str(exc).split(":", 1)[0] if str(exc).startswith("PILOT_") else None,
            flag_ever_enabled=flag_ever_enabled, flag_enabled_at_exit=_flag(),
        ), 8
    finally:
        os.environ["ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED"] = "false"
        client.close()


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        result, code = _safe(status="BLOCKED", reason="PILOT_INPUT_INVALID", flag_enabled_at_exit=_flag()), 2
    else:
        result, code = asyncio.run(run(payload))
    result["flag_enabled_at_exit"] = _flag()
    print("ENROLLMENT_RECTIFICATION_F2_3C_EXECUTE_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
