#!/usr/bin/env python3
"""Reparo cirúrgico da identidade institucional da matrícula-base de 12/06/2026.

Este executor NÃO cria um escritor novo de ``enrollment_number``. A devolução do
número previamente liberado é feita pelo rollback canônico da continuidade de
identidade; a compensação usa o handoff canônico inverso.

Nenhuma PII é codificada. O estudante é resolvido em produção por fingerprint
salted, e o número institucional nunca é emitido nos logs do gate.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from routers.student_enrollment_identity_continuity import (
    EnrollmentIdentityContinuityConflict,
    IdentityDecision,
    _assert_number_owned_only_by_student,
    _first_logged_enrollment_number,
    _regular_enrollments,
    _rollback_release_if_safe,
    choose_identity_number,
    resolve_and_prepare_identity_handoff,
)

YEAR = 2026
TARGET_SCHOOL = "E M E I E F Monsenhor Augusto Dias de Brito"
TARGET_CLASS = "7º ANO D"
BASELINE_DATE = "2026-06-12"
EXPECTED_POST_HISTORY = 8
OPERATION_ID = "student-baseline-identity-restore-2026-06-12-v2"


class RepairError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def emit(key: str, value: Any) -> None:
    print(f"STUDENT_BASELINE_IDENTITY_RESTORE_{key}={value}", flush=True)


def _norm(value: Any) -> str:
    text = "".join(
        c
        for c in unicodedata.normalize("NFKD", str(value or ""))
        if not unicodedata.combining(c)
    )
    return " ".join(text.casefold().strip().split())


def _text(value: Any) -> str:
    return str(value or "").strip()


def _name_hash(salt: str, value: Any) -> str:
    return hashlib.sha256(f"{salt}|name|{_norm(value)}".encode()).hexdigest()


def _date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return _text(value)[:10]


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = _text(value)
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def _named_docs(collection, name: str, query: dict | None = None) -> list[dict]:
    docs = await collection.find(query or {}, {"_id": 0}).to_list(None)
    return [doc for doc in docs if _norm(doc.get("name")) == _norm(name)]


async def _resolve_case(db, salt: str, wanted_hash: str) -> dict[str, str]:
    schools = await _named_docs(db.schools, TARGET_SCHOOL)
    if len(schools) != 1:
        raise RepairError("SCHOOL_CARDINALITY")
    school = schools[0]
    tenant = _text(school.get("mantenedora_id"))
    if not tenant:
        raise RepairError("SCHOOL_TENANT_MISSING")

    classes = await _named_docs(
        db.classes,
        TARGET_CLASS,
        {
            "school_id": school.get("id"),
            "academic_year": {"$in": [YEAR, str(YEAR)]},
        },
    )
    if len(classes) != 1:
        raise RepairError("CLASS_CARDINALITY")
    class_doc = classes[0]

    candidates: list[str] = []
    cursor = db.students.find(
        {"mantenedora_id": tenant},
        {"_id": 0, "id": 1, "full_name": 1},
    )
    async for student in cursor:
        if _name_hash(salt, student.get("full_name")) == wanted_hash:
            candidates.append(_text(student.get("id")))
    emit("TARGET_STUDENTS", len(candidates))
    if len(candidates) != 1 or not candidates[0]:
        raise RepairError("STUDENT_IDENTITY_CARDINALITY")

    return {
        "tenant": tenant,
        "student_id": candidates[0],
        "school_id": _text(school.get("id")),
        "class_id": _text(class_doc.get("id")),
    }


async def _inspect(db, case: dict[str, str]) -> dict[str, Any]:
    sid = case["student_id"]
    conflicts: list[str] = []

    student = await db.students.find_one(
        {"id": sid, "mantenedora_id": case["tenant"]}
    )
    if not student:
        conflicts.append("STUDENT_NOT_IN_TENANT")
        student = {}

    histories = await db.student_history.find(
        {"student_id": sid, "action_type": {"$exists": True}}
    ).to_list(None)
    baseline = [
        item
        for item in histories
        if _date_key(item.get("action_date")) == BASELINE_DATE
        and _text(item.get("school_id")) == case["school_id"]
        and _text(item.get("class_id")) == case["class_id"]
        and _norm(item.get("new_status")) in {"active", "ativo"}
    ]
    baseline_at = _as_utc(baseline[0].get("action_date")) if len(baseline) == 1 else None
    if len(baseline) != 1 or baseline_at is None:
        conflicts.append("BASELINE_EVENT_INVALID")

    post = [
        item
        for item in histories
        if baseline_at is not None
        and _as_utc(item.get("action_date")) is not None
        and _as_utc(item.get("action_date")) > baseline_at
    ]
    if len(post) != EXPECTED_POST_HISTORY:
        conflicts.append("POST_HISTORY_COUNT")

    targets = await db.enrollments.find(
        {
            "student_id": sid,
            "school_id": case["school_id"],
            "class_id": case["class_id"],
            "academic_year": {"$in": [YEAR, str(YEAR)]},
        }
    ).to_list(None)
    if len(targets) != 1:
        conflicts.append("TARGET_ENROLLMENT_CARDINALITY")
        target: dict[str, Any] = {}
    else:
        target = targets[0]

    try:
        regular = await _regular_enrollments(db, sid)
    except EnrollmentIdentityContinuityConflict:
        regular = []
        conflicts.append("REGULAR_ENROLLMENT_CONFLICT")

    numbers = {
        number
        for enrollment in regular
        for number in (
            _text(enrollment.get("enrollment_number")),
            _text(enrollment.get("previous_enrollment_number")),
        )
        if number
    }
    student_number = _text(student.get("enrollment_number"))
    logged_number = await _first_logged_enrollment_number(db, sid) if student else ""

    try:
        resolved, basis = choose_identity_number(
            student_number=student_number,
            enrollment_numbers=numbers,
            logged_number=logged_number,
        )
    except EnrollmentIdentityContinuityConflict:
        resolved, basis = None, "CANONICAL_CONFLICT"
        conflicts.append("CANONICAL_IDENTITY_CONFLICT")

    if not resolved:
        conflicts.append("IDENTITY_NOT_RESOLVED")

    target_current = _text(target.get("enrollment_number"))
    target_previous = _text(target.get("previous_enrollment_number"))
    already_restored = bool(
        resolved
        and target_current == resolved
        and not target_previous
        and student_number == resolved
        and logged_number == resolved
    )

    if resolved and not already_restored:
        if target_current:
            conflicts.append("TARGET_CURRENT_NUMBER_NOT_EMPTY")
        if target_previous != resolved:
            conflicts.append("TARGET_PREVIOUS_NUMBER_MISMATCH")
        try:
            await _assert_number_owned_only_by_student(db, sid, resolved)
        except EnrollmentIdentityContinuityConflict:
            conflicts.append("IDENTITY_OWNED_BY_OTHER_STUDENT")

    other_holders = 0
    active_holders = 0
    if resolved:
        target_id = _text(target.get("id"))
        for enrollment in regular:
            if _text(enrollment.get("id")) == target_id:
                continue
            if resolved in {
                _text(enrollment.get("enrollment_number")),
                _text(enrollment.get("previous_enrollment_number")),
            }:
                other_holders += 1
            if (
                _text(enrollment.get("enrollment_number")) == resolved
                and _norm(enrollment.get("status")) in {"active", "ativo"}
            ):
                active_holders += 1
    if other_holders:
        conflicts.append("SAME_STUDENT_OTHER_NUMBER_HOLDER")
    if active_holders:
        conflicts.append("SAME_STUDENT_ACTIVE_NUMBER_HOLDER")

    return {
        "student": student,
        "baseline": baseline,
        "post": post,
        "targets": targets,
        "target": target,
        "resolved": resolved or "",
        "basis": basis,
        "student_number": student_number,
        "logged_number": logged_number,
        "target_current": target_current,
        "target_previous": target_previous,
        "other_holders": other_holders,
        "active_holders": active_holders,
        "already_restored": already_restored,
        "conflicts": sorted(set(conflicts)),
    }


def _emit_plan(state: dict[str, Any]) -> None:
    emit("BASELINE_EVENTS", len(state["baseline"]))
    emit("POST_HISTORY", len(state["post"]))
    emit("TARGET_ENROLLMENTS", len(state["targets"]))
    emit("IDENTITY_BASIS", state["basis"])
    emit("TARGET_CURRENT_PRESENT", "YES" if state["target_current"] else "NO")
    emit("TARGET_PREVIOUS_PRESENT", "YES" if state["target_previous"] else "NO")
    emit(
        "STUDENT_NUMBER_MATCH",
        "YES"
        if state["resolved"] and state["student_number"] == state["resolved"]
        else "NO",
    )
    emit(
        "LOGGED_NUMBER_MATCH",
        "YES"
        if state["resolved"] and state["logged_number"] == state["resolved"]
        else "NO",
    )
    emit(
        "TARGET_PREVIOUS_MATCH",
        "YES"
        if state["resolved"] and state["target_previous"] == state["resolved"]
        else "NO",
    )
    emit("OTHER_HOLDERS", state["other_holders"])
    emit("ACTIVE_HOLDERS", state["active_holders"])
    emit("ALREADY_RESTORED", "YES" if state["already_restored"] else "NO")
    emit("CONFLICTS", len(state["conflicts"]))
    emit(
        "CONFLICT_TYPES",
        ",".join(state["conflicts"]) if state["conflicts"] else "NONE",
    )


async def _compensate(db, case: dict[str, str], resolved: str, audit_id: str | None) -> bool:
    """Libera novamente o número usando o handoff canônico, sem escritor local."""
    try:
        await resolve_and_prepare_identity_handoff(
            db,
            student_id=case["student_id"],
            target_class_id=case["class_id"],
            academic_year=YEAR,
        )
        target = await db.enrollments.find_one(
            {
                "student_id": case["student_id"],
                "school_id": case["school_id"],
                "class_id": case["class_id"],
                "academic_year": {"$in": [YEAR, str(YEAR)]},
            }
        )
        compensated = bool(
            target
            and not _text(target.get("enrollment_number"))
            and _text(target.get("previous_enrollment_number")) == resolved
        )
        if audit_id:
            await db.audit_logs.delete_one({"id": audit_id})
        await db.student_recovery_archives.update_one(
            {"_id": OPERATION_ID},
            {
                "$set": {
                    "state": "COMPENSATED" if compensated else "COMPENSATION_FAILED",
                    "compensated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        return compensated
    except Exception:
        return False


async def _apply(db, case: dict[str, str], state: dict[str, Any], run_id: str) -> None:
    if state["already_restored"] and not state["conflicts"]:
        emit("MODE", "APPLY")
        emit("APPLY_NOOP", "ALREADY_RESTORED")
        print("PRODUCTION_DATABASE_TOUCHED=NO", flush=True)
        return
    if state["conflicts"]:
        raise RepairError("PRECONDITION_CONFLICT")
    if await db.student_recovery_archives.find_one({"_id": OPERATION_ID}, {"_id": 1}):
        raise RepairError("ARCHIVE_ALREADY_EXISTS")

    target = state["target"]
    resolved = state["resolved"]
    archive = {
        "_id": OPERATION_ID,
        "operation": "restore_released_number_to_baseline_enrollment",
        "academic_year": YEAR,
        "tenant_id": case["tenant"],
        "student_id": case["student_id"],
        "run_id": run_id,
        "state": "PREPARED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target_enrollment_id": _text(target.get("id")),
        "student_projection_changed": False,
        "academic_records_changed": False,
    }
    await db.student_recovery_archives.insert_one(archive)

    audit_id: str | None = None
    try:
        decision = IdentityDecision(
            student_id=case["student_id"],
            number=resolved,
            basis="FORENSIC_BASELINE_ROLLBACK",
            student_number_before=state["student_number"],
            target_class_id=case["class_id"],
            academic_year=YEAR,
            source_enrollment_id=_text(target.get("id")),
            source_status=target.get("status"),
            source_previous_number=None,
            source_previous_present=False,
            released=True,
        )
        await _rollback_release_if_safe(db, decision)

        after = await db.enrollments.find_one({"id": _text(target.get("id"))})
        if not after or _text(after.get("enrollment_number")) != resolved:
            raise RepairError("CANONICAL_ROLLBACK_DID_NOT_RESTORE_NUMBER")
        if _text(after.get("previous_enrollment_number")):
            raise RepairError("CANONICAL_ROLLBACK_LEFT_PREVIOUS_NUMBER")

        now = datetime.now(timezone.utc).isoformat()
        audit_id = str(uuid.uuid4())
        await db.audit_logs.insert_one(
            {
                "id": audit_id,
                "action": "update",
                "collection": "enrollments",
                "document_id": _text(target.get("id")),
                "mantenedora_id": case["tenant"],
                "user_id": "system:student-baseline-identity-restore-2026",
                "school_id": case["school_id"],
                "academic_year": YEAR,
                "description": (
                    "Reparo forense autorizado: rollback canônico devolveu ao vínculo-base "
                    "o número institucional previamente liberado em movimentação."
                ),
                "extra_data": {
                    "operation_id": OPERATION_ID,
                    "run_id": run_id,
                    "canonical_writer": "_rollback_release_if_safe",
                    "student_projection_changed": False,
                    "academic_records_changed": False,
                },
                "timestamp_utc": now,
                "timestamp_local": now,
            }
        )

        verify = await _inspect(db, case)
        if not verify["already_restored"] or verify["conflicts"]:
            raise RepairError("POST_VERIFY_FAILED")

        await db.student_recovery_archives.update_one(
            {"_id": OPERATION_ID},
            {
                "$set": {
                    "state": "APPLIED",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "audit_id": audit_id,
                }
            },
        )
        emit("TARGET_ENROLLMENT_NUMBER_RESTORED", 1)
        emit("CANONICAL_WRITER", "_rollback_release_if_safe")
        emit("STUDENT_PROJECTION_CHANGED", "NO")
        emit("ACADEMIC_RECORDS_CHANGED", "NO")
        emit("AUDIT_EVENTS", 1)
        emit("MODE", "APPLY")
        print(
            "PRODUCTION_DATABASE_TOUCHED=YES_AUTHORIZED_BASELINE_IDENTITY_RESTORE_ONLY",
            flush=True,
        )
    except Exception as exc:
        code = exc.code if isinstance(exc, RepairError) else "UNEXPECTED_APPLY_FAILURE"
        compensated = await _compensate(db, case, resolved, audit_id)
        emit("ERROR", code)
        emit("COMPENSATION", "SUCCESS" if compensated else "FAILED")
        print(
            "PRODUCTION_DATABASE_TOUCHED=COMPENSATED"
            if compensated
            else "PRODUCTION_DATABASE_TOUCHED=POSSIBLE_PARTIAL_APPLY",
            flush=True,
        )
        raise RepairError(code) from exc


async def _run(mode: str, run_id: str, salt: str, wanted_hash: str) -> int:
    mongo_url = os.environ.get("MONGO_URL", "").strip()
    db_name = os.environ.get("DB_NAME", "").strip()
    if not mongo_url or not db_name:
        emit("ERROR", "DATABASE_ENV_MISSING")
        print("PRODUCTION_DATABASE_TOUCHED=NO", flush=True)
        return 3

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]
        case = await _resolve_case(db, salt, wanted_hash)
        state = await _inspect(db, case)
        _emit_plan(state)
        if mode == "preview":
            emit("MODE", "PREVIEW")
            emit("READY_FOR_APPLY", "YES" if not state["conflicts"] else "NO")
            print("PRODUCTION_DATABASE_TOUCHED=NO", flush=True)
            return 0
        await _apply(db, case, state, run_id)
        return 0
    except RepairError as exc:
        emit("ERROR", exc.code)
        if mode == "preview" or exc.code in {
            "SCHOOL_CARDINALITY",
            "SCHOOL_TENANT_MISSING",
            "CLASS_CARDINALITY",
            "STUDENT_IDENTITY_CARDINALITY",
            "PRECONDITION_CONFLICT",
            "ARCHIVE_ALREADY_EXISTS",
        }:
            print("PRODUCTION_DATABASE_TOUCHED=NO", flush=True)
        return 4
    finally:
        client.close()


def main() -> int:
    if len(sys.argv) != 5:
        emit("ERROR", "USAGE")
        return 2
    mode, run_id, salt, wanted_hash = sys.argv[1:]
    if mode not in {"preview", "apply"}:
        emit("ERROR", "MODE_INVALID")
        return 2
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        emit("ERROR", "RUN_ID_INVALID")
        return 2
    if not re.fullmatch(r"[0-9a-f]{32}", salt):
        emit("ERROR", "IDENTITY_SALT_INVALID")
        return 2
    if not re.fullmatch(r"[0-9a-f]{64}", wanted_hash):
        emit("ERROR", "IDENTITY_HASH_INVALID")
        return 2
    return asyncio.run(_run(mode, run_id, salt, wanted_hash))


if __name__ == "__main__":
    raise SystemExit(main())
