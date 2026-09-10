#!/usr/bin/env python3
"""Repara apenas a continuidade do número institucional da matrícula-base 2026.

Contrato do caso:
- estudante identificado somente por fingerprint salted recebido em runtime;
- matrícula-base: 12/06/2026, Monsenhor Augusto Dias de Brito, 7º ANO D;
- o número institucional já existente deve estar preservado em
  ``previous_enrollment_number`` da matrícula-base;
- ``students.enrollment_number`` e o primeiro log de matrícula devem confirmar o
  mesmo número;
- nenhum outro estudante/vínculo pode deter esse número;
- o apply move somente esse número de ``previous_enrollment_number`` para
  ``enrollment_number`` na matrícula-base. Status, turma projetada, histórico,
  notas, frequência e Dependência não são alterados por este reparo.

O saneamento completo da matrícula permanece responsabilidade do restaurador
``student_baseline_restore_2026_06_12.py`` após novo preview.
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

YEAR = 2026
TARGET_SCHOOL = "E M E I E F Monsenhor Augusto Dias de Brito"
TARGET_CLASS = "7º ANO D"
BASELINE_DATE = "2026-06-12"
EXPECTED_POST_HISTORY = 8
OPERATION_ID = "student-baseline-identity-restore-2026-06-12-v1"
SPECIAL_PROGRAMS = {"aee", "recomposicao_aprendizagem", "reforco_escolar"}
MATRICULA_RX = re.compile(r"matr[ií]cula:\s*(\d+)", re.IGNORECASE)


class RepairError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def emit(key: str, value: Any) -> None:
    print(f"STUDENT_BASELINE_IDENTITY_RESTORE_{key}={value}", flush=True)


def _norm(value: Any) -> str:
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", str(value or ""))
        if not unicodedata.combining(char)
    )
    return " ".join(text.casefold().strip().split())


def _text(value: Any) -> str:
    return str(value or "").strip()


def _name_hash(salt: str, value: Any) -> str:
    return hashlib.sha256(f"{salt}|name|{_norm(value)}".encode()).hexdigest()


def _date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value or "")[:10]


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


async def _first_logged_enrollment_number(db, student_id: str) -> str:
    cursor = db.audit_logs.find(
        {
            "collection": "students",
            "document_id": student_id,
            "extra_data.action_type": "matricula",
        },
        {"_id": 0, "timestamp": 1, "extra_data": 1},
    ).sort("timestamp", 1)
    async for log in cursor:
        observations = _text((log.get("extra_data") or {}).get("observations"))
        match = MATRICULA_RX.search(observations)
        if match:
            return match.group(1)
    return ""


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
    if _text(class_doc.get("mantenedora_id") or tenant) != tenant:
        raise RepairError("CLASS_TENANT_MISMATCH")
    if _norm(class_doc.get("atendimento_programa")) in SPECIAL_PROGRAMS:
        raise RepairError("REGULAR_CLASS_REQUIRED")

    matches: list[str] = []
    cursor = db.students.find(
        {"mantenedora_id": tenant},
        {"_id": 0, "id": 1, "full_name": 1},
    )
    async for student in cursor:
        if _name_hash(salt, student.get("full_name")) == wanted_hash:
            matches.append(_text(student.get("id")))
    emit("TARGET_STUDENTS", len(matches))
    if len(matches) != 1 or not matches[0]:
        raise RepairError("STUDENT_IDENTITY_CARDINALITY")

    return {
        "tenant": tenant,
        "student_id": matches[0],
        "school_id": _text(school.get("id")),
        "class_id": _text(class_doc.get("id")),
    }


async def _inspect(db, case: dict[str, str]) -> dict[str, Any]:
    sid = case["student_id"]
    tenant = case["tenant"]
    school_id = case["school_id"]
    class_id = case["class_id"]
    conflicts: list[str] = []

    student = await db.students.find_one({"id": sid, "mantenedora_id": tenant})
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
        and _text(item.get("school_id")) == school_id
        and _text(item.get("class_id")) == class_id
        and _norm(item.get("new_status")) in {"active", "ativo"}
    ]
    if len(baseline) != 1:
        conflicts.append("BASELINE_EVENT_CARDINALITY")
        baseline_at = None
    else:
        baseline_at = _as_utc(baseline[0].get("action_date"))
        if baseline_at is None:
            conflicts.append("BASELINE_DATE_INVALID")

    post = [
        item
        for item in histories
        if baseline_at is not None
        and _as_utc(item.get("action_date")) is not None
        and _as_utc(item.get("action_date")) > baseline_at
    ]
    if len(post) != EXPECTED_POST_HISTORY:
        conflicts.append("POST_HISTORY_COUNT")

    target_enrollments = await db.enrollments.find(
        {
            "student_id": sid,
            "school_id": school_id,
            "class_id": class_id,
            "academic_year": {"$in": [YEAR, str(YEAR)]},
        }
    ).to_list(None)
    if len(target_enrollments) != 1:
        conflicts.append("TARGET_ENROLLMENT_CARDINALITY")
        target: dict[str, Any] = {}
    else:
        target = target_enrollments[0]
        if _text(target.get("mantenedora_id") or tenant) != tenant:
            conflicts.append("TARGET_ENROLLMENT_TENANT_MISMATCH")

    enrollments = await db.enrollments.find({"student_id": sid}).to_list(None)
    class_ids = sorted({_text(e.get("class_id")) for e in enrollments if _text(e.get("class_id"))})
    class_docs = (
        await db.classes.find(
            {"id": {"$in": class_ids}},
            {"_id": 0, "id": 1, "atendimento_programa": 1},
        ).to_list(None)
        if class_ids
        else []
    )
    class_map = {_text(c.get("id")): c for c in class_docs}
    regular: list[dict] = []
    for enrollment in enrollments:
        current = _text(enrollment.get("enrollment_number"))
        previous = _text(enrollment.get("previous_enrollment_number"))
        class_doc = class_map.get(_text(enrollment.get("class_id")))
        if not class_doc:
            if current or previous:
                conflicts.append("NUMBERED_ENROLLMENT_CLASS_MISSING")
            continue
        if _norm(class_doc.get("atendimento_programa")) not in SPECIAL_PROGRAMS:
            regular.append(enrollment)

    current_numbers = {
        _text(e.get("enrollment_number"))
        for e in regular
        if _text(e.get("enrollment_number"))
    }
    previous_numbers = {
        _text(e.get("previous_enrollment_number"))
        for e in regular
        if _text(e.get("previous_enrollment_number"))
    }
    all_numbers = current_numbers | previous_numbers
    student_number = _text(student.get("enrollment_number"))
    logged_number = await _first_logged_enrollment_number(db, sid)
    target_current = _text(target.get("enrollment_number"))
    target_previous = _text(target.get("previous_enrollment_number"))

    if len(all_numbers) != 1:
        conflicts.append("IDENTITY_NUMBER_VARIANTS")
        resolved = ""
    else:
        resolved = next(iter(all_numbers))

    if not student_number:
        conflicts.append("STUDENT_NUMBER_MISSING")
    if not logged_number:
        conflicts.append("LOGGED_NUMBER_MISSING")
    if resolved and student_number and resolved != student_number:
        conflicts.append("STUDENT_NUMBER_MISMATCH")
    if resolved and logged_number and resolved != logged_number:
        conflicts.append("LOGGED_NUMBER_MISMATCH")

    already_restored = bool(
        resolved
        and target_current == resolved
        and not target_previous
        and student_number == resolved
        and logged_number == resolved
    )

    if not already_restored:
        if target_current:
            conflicts.append("TARGET_CURRENT_NUMBER_NOT_EMPTY")
        if resolved and target_previous != resolved:
            conflicts.append("TARGET_PREVIOUS_NUMBER_MISMATCH")

    other_student_owners = 0
    other_enrollment_owners = 0
    same_student_other_holders = 0
    same_student_active_holders = 0
    if resolved:
        other_student_owners = await db.students.count_documents(
            {"id": {"$ne": sid}, "enrollment_number": resolved}
        )
        other_enrollment_owners = await db.enrollments.count_documents(
            {
                "student_id": {"$ne": sid},
                "$or": [
                    {"enrollment_number": resolved},
                    {"previous_enrollment_number": resolved},
                ],
            }
        )
        target_id = _text(target.get("id"))
        for enrollment in regular:
            holds = resolved in {
                _text(enrollment.get("enrollment_number")),
                _text(enrollment.get("previous_enrollment_number")),
            }
            if not holds:
                continue
            if _text(enrollment.get("id")) != target_id:
                same_student_other_holders += 1
            if (
                _text(enrollment.get("enrollment_number")) == resolved
                and _norm(enrollment.get("status")) in {"active", "ativo"}
                and _text(enrollment.get("id")) != target_id
            ):
                same_student_active_holders += 1

    if other_student_owners or other_enrollment_owners:
        conflicts.append("IDENTITY_OWNED_BY_OTHER_STUDENT")
    if same_student_other_holders:
        conflicts.append("SAME_STUDENT_OTHER_NUMBER_HOLDER")
    if same_student_active_holders:
        conflicts.append("SAME_STUDENT_ACTIVE_NUMBER_HOLDER")

    return {
        "student": student,
        "baseline": baseline,
        "post": post,
        "target_enrollments": target_enrollments,
        "target": target,
        "resolved": resolved,
        "current_numbers": current_numbers,
        "previous_numbers": previous_numbers,
        "student_number": student_number,
        "logged_number": logged_number,
        "target_current": target_current,
        "target_previous": target_previous,
        "other_owners": other_student_owners + other_enrollment_owners,
        "same_student_other_holders": same_student_other_holders,
        "same_student_active_holders": same_student_active_holders,
        "already_restored": already_restored,
        "conflicts": sorted(set(conflicts)),
    }


def _emit_plan(state: dict[str, Any]) -> None:
    emit("BASELINE_EVENTS", len(state["baseline"]))
    emit("POST_HISTORY", len(state["post"]))
    emit("TARGET_ENROLLMENTS", len(state["target_enrollments"]))
    emit("CURRENT_VARIANTS", len(state["current_numbers"]))
    emit("PREVIOUS_VARIANTS", len(state["previous_numbers"]))
    emit("TARGET_CURRENT_PRESENT", "YES" if state["target_current"] else "NO")
    emit("TARGET_PREVIOUS_PRESENT", "YES" if state["target_previous"] else "NO")
    emit("STUDENT_NUMBER_MATCH", "YES" if state["resolved"] and state["student_number"] == state["resolved"] else "NO")
    emit("LOGGED_NUMBER_MATCH", "YES" if state["resolved"] and state["logged_number"] == state["resolved"] else "NO")
    emit("TARGET_PREVIOUS_MATCH", "YES" if state["resolved"] and state["target_previous"] == state["resolved"] else "NO")
    emit("OTHER_OWNERS", state["other_owners"])
    emit("SAME_STUDENT_OTHER_HOLDERS", state["same_student_other_holders"])
    emit("SAME_STUDENT_ACTIVE_HOLDERS", state["same_student_active_holders"])
    emit("ALREADY_RESTORED", "YES" if state["already_restored"] else "NO")
    emit("CONFLICTS", len(state["conflicts"]))
    emit("CONFLICT_TYPES", ",".join(state["conflicts"]) if state["conflicts"] else "NONE")


async def _compensate(db, archive: dict[str, Any], audit_id: str | None) -> bool:
    try:
        target = archive["target_before"]
        await db.enrollments.replace_one({"_id": target["_id"]}, target, upsert=True)
        if audit_id:
            await db.audit_logs.delete_one({"id": audit_id})
        await db.student_recovery_archives.update_one(
            {"_id": archive["_id"]},
            {
                "$set": {
                    "state": "COMPENSATED",
                    "compensated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        return True
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
        "target_before": target,
        "student_projection_changed": False,
        "academic_records_changed": False,
    }
    await db.student_recovery_archives.insert_one(archive)

    audit_id: str | None = None
    try:
        now = datetime.now(timezone.utc).isoformat()
        result = await db.enrollments.update_one(
            {
                "_id": target["_id"],
                "student_id": case["student_id"],
                "school_id": case["school_id"],
                "class_id": case["class_id"],
                "enrollment_number": target.get("enrollment_number"),
                "previous_enrollment_number": resolved,
            },
            {
                "$set": {
                    "enrollment_number": resolved,
                    "updated_at": now,
                },
                "$unset": {"previous_enrollment_number": ""},
            },
        )
        if result.matched_count != 1 or result.modified_count != 1:
            raise RepairError("TARGET_ENROLLMENT_CONCURRENT_CHANGE")

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
                "old_value": {
                    "enrollment_number": target.get("enrollment_number"),
                    "previous_enrollment_number": target.get("previous_enrollment_number"),
                },
                "new_value": {
                    "enrollment_number": resolved,
                    "previous_enrollment_number": None,
                },
                "description": (
                    "Reparo forense autorizado da continuidade da identidade institucional; "
                    "o número previamente liberado retorna ao vínculo-base de 12/06/2026."
                ),
                "extra_data": {
                    "operation_id": OPERATION_ID,
                    "run_id": run_id,
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
        compensated = await _compensate(db, archive, audit_id)
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
            "CLASS_TENANT_MISMATCH",
            "REGULAR_CLASS_REQUIRED",
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
