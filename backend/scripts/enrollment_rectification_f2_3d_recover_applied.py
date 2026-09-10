#!/usr/bin/env python3
"""F2.3D — recuperação ordinal de uma retificação histórica já APPLIED.

Não repete matrícula, não cria aula e não toca em notas. Resolve o caso por
fingerprints salted, exige uma única saga APPLIED com ledger F2.1A preservado,
constrói o plano ordinal em leitura, abre a feature flag somente neste processo
e faz replay idempotente da saga pelo runtime F2.3D.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any, Mapping

from motor.motor_asyncio import AsyncIOMotorClient

from audit_service import AuditService
from services.enrollment_rectification_attendance import LEDGER_COLLECTION as SOURCE_LEDGER_COLLECTION
from services.enrollment_rectification_attendance_ordinal import (
    ORDINAL_LEDGER_COLLECTION,
    build_ordinal_attendance_plan,
)
from services.enrollment_rectification_documents import DOCUMENT_ACKNOWLEDGEMENT
from services.enrollment_rectification_saga import RUNS_COLLECTION
from services.enrollment_rectification_saga_ordinal_runtime import (
    RectificationSagaError,
    execute_rectification_saga,
)

SCHEMA = "ENROLLMENT_RECTIFICATION_F2_3D_RECOVER_APPLIED_V1"
TARGET_SCHOOL = "E M E I E F Monsenhor Augusto Dias de Brito"
SOURCE_CLASS = "6º ANO A"
DESTINATION_CLASS = "7º ANO B"
ACADEMIC_YEAR = 2026


def _norm(value: Any) -> str:
    text = "".join(
        c for c in unicodedata.normalize("NFKD", str(value or ""))
        if not unicodedata.combining(c)
    )
    return " ".join(text.casefold().strip().split())


def _normalize_birth_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value or "").strip()
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
        variants.add(_norm(actual[:i] + actual[i + 1] + actual[i] + actual[i + 2:]))
    for i in range(len(actual)):
        for ch in alphabet:
            if ch != actual[i]:
                variants.add(_norm(actual[:i] + ch + actual[i + 1:]))
    for i in range(len(actual) + 1):
        for ch in alphabet:
            variants.add(_norm(actual[:i] + ch + actual[i:]))
    variants.discard("")
    return sum(1 for value in variants if _component_hash(salt, "name", value) == wanted) == 1


def _flag() -> bool:
    return os.environ.get("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "false").strip().lower() == "true"


def _safe(**fields):
    return {
        "schema": SCHEMA,
        **fields,
        "student_pii_emitted": False,
        "technical_ids_emitted": False,
        "operator_credentials_used": False,
    }


def _source_sort_key(item: Mapping[str, Any]) -> tuple[str, int, str]:
    try:
        aula = int(item.get("source_aula_numero") or 0)
    except (TypeError, ValueError):
        aula = 0
    return (str(item.get("source_date") or ""), aula, str(item.get("source_attendance_id") or ""))


async def _resolve_case(db, *, salt: str, name_hash: str, dob_hash: str, cpf_hash: str):
    schools = await db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}).to_list(None)
    matches = [s for s in schools if _norm(s.get("name")) == _norm(TARGET_SCHOOL)]
    if len(matches) != 1:
        raise RuntimeError("F2_3D_SCHOOL_CARDINALITY_INVALID")
    school_id = str(matches[0].get("id") or "")
    tenant = str(matches[0].get("mantenedora_id") or "")
    classes = await db.classes.find(
        {
            "mantenedora_id": tenant,
            "school_id": school_id,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        },
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(None)
    src = [c for c in classes if _norm(c.get("name")) == _norm(SOURCE_CLASS)]
    dst = [c for c in classes if _norm(c.get("name")) == _norm(DESTINATION_CLASS)]
    if len(src) != 1 or len(dst) != 1:
        raise RuntimeError("F2_3D_CLASS_CARDINALITY_INVALID")
    source = str(src[0].get("id") or "")
    destination = str(dst[0].get("id") or "")

    active = await db.enrollments.find(
        {
            "mantenedora_id": tenant,
            "class_id": destination,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "status": "active",
        },
        {"_id": 0, "id": 1, "student_id": 1, "class_id": 1},
    ).to_list(None)
    ids = [str(e.get("student_id")) for e in active if e.get("student_id")]
    students = await db.students.find(
        {"mantenedora_id": tenant, "id": {"$in": ids}},
        {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "cpf": 1, "class_id": 1},
    ).to_list(None)
    cpf_matches = [
        s for s in students
        if _cpf_digits(s.get("cpf"))
        and _component_hash(salt, "cpf", _cpf_digits(s.get("cpf"))) == cpf_hash
    ]
    if len(cpf_matches) != 1:
        raise RuntimeError(f"F2_3D_CPF_CARDINALITY_INVALID:{len(cpf_matches)}")
    student = cpf_matches[0]
    if _component_hash(salt, "dob", _normalize_birth_date(student.get("birth_date"))) != dob_hash:
        raise RuntimeError("F2_3D_DOB_IDENTITY_MISMATCH")
    if not _name_hash_matches(salt, student.get("full_name"), name_hash):
        raise RuntimeError("F2_3D_NAME_IDENTITY_MISMATCH")
    sid = str(student.get("id") or "")
    enrollment = [e for e in active if str(e.get("student_id") or "") == sid]
    if len(enrollment) != 1 or str(student.get("class_id") or "") != destination:
        raise RuntimeError("F2_3D_DESTINATION_PRECONDITION_FAILED")
    return {
        "tenant_id": tenant,
        "student_id": sid,
        "source_id": source,
        "destination_id": destination,
        "enrollment_id": str(enrollment[0].get("id") or ""),
    }


async def _find_run(db, case):
    runs = await db[RUNS_COLLECTION].find(
        {
            "tenant_id": case["tenant_id"],
            "student_id": case["student_id"],
            "source_class_id": case["source_id"],
            "destination_class_id": case["destination_id"],
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "state": "APPLIED",
        },
        {"_id": 0},
    ).sort("executed_at", -1).to_list(10)
    candidates = []
    for run in runs:
        if run.get("ordinal_attendance_state") == "APPLIED":
            continue
        count = await db[SOURCE_LEDGER_COLLECTION].count_documents(
            {
                "mantenedora_id": case["tenant_id"],
                "protocol": run.get("protocol"),
                "student_id": case["student_id"],
                "state": "APPLIED",
            }
        )
        if count:
            candidates.append((run, int(count)))
    if len(candidates) != 1:
        raise RuntimeError(f"F2_3D_APPLIED_RUN_CARDINALITY_INVALID:{len(candidates)}")
    run, source_count = candidates[0]
    actor = dict(run.get("actor") or {})
    if not actor.get("id") or actor.get("role") not in {"super_admin", "admin", "gerente"}:
        raise RuntimeError("F2_3D_RUN_ACTOR_INVALID")
    actor["active_mantenedora_id"] = case["tenant_id"]
    actor["mantenedora_id"] = case["tenant_id"]
    return run, actor, source_count


async def _component_validation(db, *, case, run):
    protocol = str(run.get("protocol") or "")
    tenant = case["tenant_id"]
    sid = case["student_id"]
    source = await db[SOURCE_LEDGER_COLLECTION].find(
        {"mantenedora_id": tenant, "protocol": protocol, "student_id": sid, "state": "APPLIED"},
        {"_id": 0},
    ).to_list(10000)
    ordinal = await db[ORDINAL_LEDGER_COLLECTION].find(
        {"mantenedora_id": tenant, "protocol": protocol, "student_id": sid, "state": "APPLIED"},
        {"_id": 0},
    ).to_list(10000)
    source_by_course = defaultdict(list)
    ordinal_by_course = defaultdict(list)
    for item in source:
        source_by_course[str(item.get("target_course_id") or "")].append(item)
    for item in ordinal:
        ordinal_by_course[str(item.get("target_course_id") or "")].append(item)

    course_ids = [cid for cid in source_by_course if cid]
    courses = await db.courses.find(
        {"id": {"$in": course_ids}}, {"_id": 0, "id": 1, "name": 1, "nome": 1}
    ).to_list(None) if course_ids else []
    names = {str(c.get("id")): c.get("name") or c.get("nome") or "Componente" for c in courses}

    components = []
    all_sequences_match = True
    actual_destination_records = 0
    for cid, src_items in sorted(source_by_course.items()):
        src_items = sorted(src_items, key=_source_sort_key)
        ord_items = sorted(ordinal_by_course.get(cid, []), key=lambda x: int(x.get("ordinal") or 0))
        expected = [str(x.get("attendance_status") or "") for x in src_items[:len(ord_items)]]
        migrated = [str(x.get("status") or "") for x in ord_items]
        sequence_match = expected == migrated
        all_sequences_match = all_sequences_match and sequence_match
        materialized_ok = True
        for ledger in ord_items:
            doc = await db.attendance.find_one(
                {"id": ledger.get("target_attendance_id"), "mantenedora_id": tenant},
                {"_id": 0, "records": 1},
            )
            matches = [r for r in (doc or {}).get("records", []) if str(r.get("student_id")) == sid]
            if len(matches) != 1 or str(matches[0].get("status") or "") != str(ledger.get("status") or ""):
                materialized_ok = False
            else:
                actual_destination_records += 1
        all_sequences_match = all_sequences_match and materialized_ok
        components.append({
            "component": names.get(cid, "Componente"),
            "source_count": len(src_items),
            "applied_count": len(ord_items),
            "ignored_excess_count": max(0, len(src_items) - len(ord_items)),
            "sequence_match": sequence_match,
            "materialized_match": materialized_ok,
            "status_counts": dict(Counter(migrated)),
        })

    return {
        "source_records": len(source),
        "ordinal_ledgers_applied": len(ordinal),
        "destination_records_verified": actual_destination_records,
        "all_sequences_match": all_sequences_match,
        "components": components,
    }


async def run(payload):
    salt = str(payload.get("component_salt") or "").strip().lower()
    name_hash = str(payload.get("name_hash") or "").strip().lower()
    dob_hash = str(payload.get("dob_hash") or "").strip().lower()
    cpf_hash = str(payload.get("cpf_hash") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", salt) or any(
        not re.fullmatch(r"[0-9a-f]{64}", value) for value in (name_hash, dob_hash, cpf_hash)
    ):
        return _safe(status="BLOCKED", reason="F2_3D_FINGERPRINT_INVALID", flag_enabled_at_exit=_flag()), 2
    if _flag():
        return _safe(status="BLOCKED", reason="F2_3D_FLAG_MUST_START_DISABLED", flag_enabled_at_exit=True), 2

    mongo_url = os.environ.get("MONGO_URL", "").strip()
    db_name = os.environ.get("DB_NAME", "").strip()
    if not mongo_url or not db_name:
        return _safe(status="BLOCKED", reason="F2_3D_DATABASE_ENV_MISSING", flag_enabled_at_exit=_flag()), 2

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    flag_ever_enabled = False
    try:
        case = await _resolve_case(db, salt=salt, name_hash=name_hash, dob_hash=dob_hash, cpf_hash=cpf_hash)
        run_doc, actor, source_count = await _find_run(db, case)
        protocol = str(run_doc.get("protocol") or "")
        prepare_id = str(run_doc.get("prepare_id") or run_doc.get("_id") or "")
        if not protocol or not prepare_id:
            raise RuntimeError("F2_3D_RUN_IDENTITY_INCOMPLETE")

        plan = await build_ordinal_attendance_plan(
            db,
            protocol=protocol,
            tenant_id=case["tenant_id"],
            student_id=case["student_id"],
            target_class_id=case["destination_id"],
            academic_year=ACADEMIC_YEAR,
        )
        if plan.get("blockers"):
            counts = Counter(str(b.get("code") or "UNKNOWN") for b in plan.get("blockers") or [])
            return _safe(
                status="BLOCKED",
                reason="F2_3D_PLAN_BLOCKED",
                blocker_code_counts=dict(counts),
                plan_totals=plan.get("totals") or {},
                flag_enabled_at_exit=_flag(),
            ), 3

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

        latest = await db[RUNS_COLLECTION].find_one(
            {"_id": prepare_id, "tenant_id": case["tenant_id"]}, {"_id": 0}
        )
        validation = await _component_validation(db, case=case, run=run_doc)
        enrollment = await db.enrollments.find_one(
            {"id": case["enrollment_id"], "mantenedora_id": case["tenant_id"]},
            {"_id": 0, "class_id": 1, "status": 1},
        )
        student = await db.students.find_one(
            {"id": case["student_id"], "mantenedora_id": case["tenant_id"]},
            {"_id": 0, "class_id": 1},
        )
        checks = {
            "run_still_applied": bool(latest) and latest.get("state") == "APPLIED",
            "ordinal_state_applied": bool(latest) and latest.get("ordinal_attendance_state") == "APPLIED",
            "enrollment_still_destination": bool(enrollment) and enrollment.get("status") == "active" and str(enrollment.get("class_id")) == case["destination_id"],
            "student_projection_still_destination": bool(student) and str(student.get("class_id")) == case["destination_id"],
            "source_ledger_preserved": validation["source_records"] == source_count,
            "ordinal_count_matches_destination": validation["ordinal_ledgers_applied"] == validation["destination_records_verified"],
            "ordinal_sequences_match": validation["all_sequences_match"],
            "flag_disabled_at_exit": not _flag(),
        }
        if result.get("state") != "APPLIED" or not all(checks.values()):
            return _safe(
                status="FAILED_POSTVALIDATION",
                reason="F2_3D_POSTCONDITION_FAILED",
                checks=checks,
                validation=validation,
                plan_totals=plan.get("totals") or {},
                flag_ever_enabled=flag_ever_enabled,
                flag_enabled_at_exit=_flag(),
            ), 6

        return _safe(
            status="APPLIED",
            operation="ordinal_attendance_recovery",
            source_class=SOURCE_CLASS,
            destination_class=DESTINATION_CLASS,
            academic_year=ACADEMIC_YEAR,
            checks=checks,
            validation=validation,
            plan_totals=plan.get("totals") or {},
            runtime_summary=result.get("attendance_ordinal_summary") or {},
            flag_ever_enabled=flag_ever_enabled,
            flag_enabled_at_exit=_flag(),
        ), 0
    except RectificationSagaError as exc:
        return _safe(
            status="FAILED",
            reason=exc.code,
            flag_ever_enabled=flag_ever_enabled,
            flag_enabled_at_exit=_flag(),
        ), 5
    except Exception as exc:
        return _safe(
            status="BLOCKED",
            reason=str(exc).split(":", 1)[0],
            flag_ever_enabled=flag_ever_enabled,
            flag_enabled_at_exit=_flag(),
        ), 4
    finally:
        os.environ["ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED"] = "false"
        client.close()


def main():
    payload = {
        "component_salt": os.environ.get("F2_3D_COMPONENT_SALT", ""),
        "name_hash": os.environ.get("F2_3D_NAME_HASH", ""),
        "dob_hash": os.environ.get("F2_3D_DOB_HASH", ""),
        "cpf_hash": os.environ.get("F2_3D_CPF_HASH", ""),
    }
    output, code = asyncio.run(run(payload))
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
