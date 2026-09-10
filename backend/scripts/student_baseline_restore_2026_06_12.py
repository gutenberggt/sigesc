#!/usr/bin/env python3
"""Restauração cirúrgica de matrícula 2026 para um estudante por fingerprint.

Contrato do caso:
- baseline válido: 12/06/2026, Monsenhor Augusto Dias de Brito, 7º ANO D;
- movimentos posteriores ao baseline deixam a trilha operacional;
- vínculos posteriores em Paulette Camille Margaret Planchon, 7º ANO A, deixam
  a coleção canônica de matrículas;
- a matrícula original do 7º ANO D volta a ``active``;
- ``students`` é reconstruído exclusivamente pelo serviço canônico de matrícula;
- grades, attendance e student_dependencies são somente leitura e bloqueiam
  ``apply`` se houver qualquer registro no vínculo a ignorar.

Nenhuma PII do estudante é codificada ou emitida. A identidade é resolvida apenas
no host de produção por SHA-256 salted do nome normalizado, mais a forma exata do
histórico e das matrículas.
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
from services.enrollment_service import rebuild_student_home_projection

YEAR = 2026
TARGET_SCHOOL = "E M E I E F Monsenhor Augusto Dias de Brito"
TARGET_CLASS = "7º ANO D"
IGNORED_SCHOOL = "E M E F T I Paulette Camille Margaret Planchon"
IGNORED_CLASS = "7º ANO A"
BASELINE_DATE = "2026-06-12"
EXPECTED_POST_HISTORY = 8
OPERATION_ID = "student-baseline-restore-2026-06-12-v1"
SPECIAL_PROGRAMS = {"aee", "recomposicao_aprendizagem", "reforco_escolar"}


class RestoreError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def emit(key: str, value: Any) -> None:
    print(f"STUDENT_BASELINE_RESTORE_{key}={value}", flush=True)


def _norm(value: Any) -> str:
    if value is None:
        return ""
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", str(value))
        if not unicodedata.combining(char)
    )
    return " ".join(text.casefold().strip().split())


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
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _active(value: Any) -> bool:
    return _norm(value) in {"active", "ativo"}


async def _named_docs(collection, name: str, query: dict | None = None) -> list[dict]:
    docs = await collection.find(query or {}, {"_id": 0}).to_list(None)
    return [doc for doc in docs if _norm(doc.get("name")) == _norm(name)]


async def _resolve_case(db, salt: str, wanted_hash: str) -> dict[str, str]:
    target_schools = await _named_docs(db.schools, TARGET_SCHOOL)
    ignored_schools = await _named_docs(db.schools, IGNORED_SCHOOL)
    if len(target_schools) != 1 or len(ignored_schools) != 1:
        raise RestoreError("SCHOOL_CARDINALITY")

    target_school = target_schools[0]
    ignored_school = ignored_schools[0]
    tenant = str(target_school.get("mantenedora_id") or "")
    if not tenant or str(ignored_school.get("mantenedora_id") or "") != tenant:
        raise RestoreError("SCHOOL_TENANT_MISMATCH")

    year_query = {"$in": [YEAR, str(YEAR)]}
    target_classes = await _named_docs(
        db.classes,
        TARGET_CLASS,
        {"school_id": target_school.get("id"), "academic_year": year_query},
    )
    ignored_classes = await _named_docs(
        db.classes,
        IGNORED_CLASS,
        {"school_id": ignored_school.get("id"), "academic_year": year_query},
    )
    if len(target_classes) != 1 or len(ignored_classes) != 1:
        raise RestoreError("CLASS_CARDINALITY")

    target_class = target_classes[0]
    ignored_class = ignored_classes[0]
    for class_doc in (target_class, ignored_class):
        if str(class_doc.get("mantenedora_id") or tenant) != tenant:
            raise RestoreError("CLASS_TENANT_MISMATCH")
        if _norm(class_doc.get("atendimento_programa")) in SPECIAL_PROGRAMS:
            raise RestoreError("REGULAR_CLASS_REQUIRED")

    candidates: list[str] = []
    cursor = db.students.find(
        {"mantenedora_id": tenant}, {"_id": 0, "id": 1, "full_name": 1}
    )
    async for student in cursor:
        if _name_hash(salt, student.get("full_name")) == wanted_hash:
            candidates.append(str(student.get("id") or ""))
    if len(candidates) != 1 or not candidates[0]:
        emit("TARGET_STUDENTS", len(candidates))
        raise RestoreError("STUDENT_IDENTITY_CARDINALITY")

    return {
        "tenant": tenant,
        "student_id": candidates[0],
        "target_school_id": str(target_school.get("id") or ""),
        "target_class_id": str(target_class.get("id") or ""),
        "ignored_school_id": str(ignored_school.get("id") or ""),
        "ignored_class_id": str(ignored_class.get("id") or ""),
    }


async def _attendance_count(db, student_id: str, class_id: str) -> int:
    pipeline = [
        {"$match": {"class_id": class_id, "records.student_id": student_id}},
        {
            "$project": {
                "n": {
                    "$size": {
                        "$filter": {
                            "input": {"$ifNull": ["$records", []]},
                            "as": "record",
                            "cond": {"$eq": ["$$record.student_id", student_id]},
                        }
                    }
                }
            }
        },
        {"$group": {"_id": None, "total": {"$sum": "$n"}}},
    ]
    rows = await db.attendance.aggregate(pipeline).to_list(1)
    return int(rows[0].get("total", 0)) if rows else 0


async def _inspect(db, case: dict[str, str]) -> dict[str, Any]:
    sid = case["student_id"]
    tenant = case["tenant"]
    target_school_id = case["target_school_id"]
    target_class_id = case["target_class_id"]
    ignored_school_id = case["ignored_school_id"]
    ignored_class_id = case["ignored_class_id"]
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
        and str(item.get("school_id") or "") == target_school_id
        and str(item.get("class_id") or "") == target_class_id
        and _active(item.get("new_status"))
    ]
    if len(baseline) != 1:
        conflicts.append("BASELINE_EVENT_CARDINALITY")
        baseline_at = None
    else:
        baseline_at = _as_utc(baseline[0].get("action_date"))
        if baseline_at is None:
            conflicts.append("BASELINE_DATE_INVALID")

    if any(item.get("action_date") and _as_utc(item.get("action_date")) is None for item in histories):
        conflicts.append("HISTORY_INVALID_DATE")

    post = [
        item
        for item in histories
        if baseline_at is not None
        and _as_utc(item.get("action_date")) is not None
        and _as_utc(item.get("action_date")) > baseline_at
    ]
    post_target = [
        item
        for item in post
        if str(item.get("school_id") or "") == target_school_id
        and str(item.get("class_id") or "") == target_class_id
    ]
    post_ignored = [
        item
        for item in post
        if str(item.get("school_id") or "") == ignored_school_id
        and str(item.get("class_id") or "") == ignored_class_id
    ]
    post_na = [item for item in post if not item.get("school_id") and not item.get("class_id")]

    enrollments = await db.enrollments.find(
        {"student_id": sid, "academic_year": {"$in": [YEAR, str(YEAR)]}}
    ).to_list(None)
    target_enrollments = [
        item
        for item in enrollments
        if str(item.get("school_id") or "") == target_school_id
        and str(item.get("class_id") or "") == target_class_id
    ]
    ignored_enrollments = [
        item
        for item in enrollments
        if str(item.get("school_id") or "") == ignored_school_id
        and str(item.get("class_id") or "") == ignored_class_id
    ]
    if len(target_enrollments) != 1:
        conflicts.append("TARGET_ENROLLMENT_CARDINALITY")
        target_enrollment: dict[str, Any] = {}
    else:
        target_enrollment = target_enrollments[0]
        if not str(target_enrollment.get("enrollment_number") or "").strip():
            conflicts.append("TARGET_ENROLLMENT_NUMBER_MISSING")
        if str(target_enrollment.get("mantenedora_id") or tenant) != tenant:
            conflicts.append("TARGET_ENROLLMENT_TENANT_MISMATCH")

    class_ids = list({str(item.get("class_id")) for item in enrollments if item.get("class_id")})
    classes = (
        await db.classes.find(
            {"id": {"$in": class_ids}}, {"_id": 0, "id": 1, "atendimento_programa": 1}
        ).to_list(None)
        if class_ids
        else []
    )
    class_map = {str(item.get("id")): item for item in classes}
    regular = [
        item
        for item in enrollments
        if _norm((class_map.get(str(item.get("class_id"))) or {}).get("atendimento_programa"))
        not in SPECIAL_PROGRAMS
    ]
    other_regular = [
        item
        for item in regular
        if str(item.get("class_id") or "") not in {target_class_id, ignored_class_id}
    ]
    active_regular = [item for item in regular if _norm(item.get("status")) == "active"]
    active_ignored = [
        item
        for item in ignored_enrollments
        if _norm(item.get("status")) == "active"
    ]
    if other_regular:
        conflicts.append("OTHER_REGULAR_ENROLLMENT")
    if active_ignored:
        conflicts.append("IGNORED_ENROLLMENT_STILL_ACTIVE")

    ignored_grades = await db.grades.count_documents(
        {"student_id": sid, "class_id": ignored_class_id}
    )
    ignored_attendance = await _attendance_count(db, sid, ignored_class_id)
    ignored_dependencies = await db.student_dependencies.count_documents(
        {"student_id": sid, "class_id": ignored_class_id}
    )
    if ignored_grades:
        conflicts.append("IGNORED_CLASS_GRADES_PRESENT")
    if ignored_attendance:
        conflicts.append("IGNORED_CLASS_ATTENDANCE_PRESENT")
    if ignored_dependencies:
        conflicts.append("IGNORED_CLASS_DEPENDENCY_PRESENT")

    currently_restored = bool(
        student
        and len(target_enrollments) == 1
        and _active(target_enrollment.get("status"))
        and _active(student.get("status"))
        and str(student.get("school_id") or "") == target_school_id
        and str(student.get("class_id") or "") == target_class_id
        and str(student.get("enrollment_number") or "")
        == str(target_enrollment.get("enrollment_number") or "")
        and not ignored_enrollments
        and not post
    )

    if not currently_restored and len(baseline) == 1:
        if len(post) != EXPECTED_POST_HISTORY:
            conflicts.append("POST_HISTORY_COUNT")
        if len(post_target) != 2:
            conflicts.append("POST_TARGET_HISTORY_SHAPE")
        if len(post_ignored) != 5:
            conflicts.append("POST_IGNORED_HISTORY_SHAPE")
        if len(post_na) != 1:
            conflicts.append("POST_NA_HISTORY_SHAPE")
        expected_dates = {
            "2026-06-22": 2,
            "2026-08-06": 2,
            "2026-08-11": 1,
            "2026-09-09": 1,
            "2026-09-10": 2,
        }
        for date_value, count in expected_dates.items():
            actual = sum(1 for item in post if _date_key(item.get("action_date")) == date_value)
            if actual != count:
                conflicts.append("POST_DATE_SHAPE_" + date_value)
        if any(_date_key(item.get("action_date")) not in expected_dates for item in post):
            conflicts.append("POST_UNEXPECTED_DATE")

    return {
        "student": student,
        "baseline": baseline,
        "post": post,
        "post_target": post_target,
        "post_ignored": post_ignored,
        "post_na": post_na,
        "target_enrollments": target_enrollments,
        "target_enrollment": target_enrollment,
        "ignored_enrollments": ignored_enrollments,
        "other_regular": other_regular,
        "active_regular": active_regular,
        "ignored_grades": int(ignored_grades),
        "ignored_attendance": int(ignored_attendance),
        "ignored_dependencies": int(ignored_dependencies),
        "currently_restored": currently_restored,
        "conflicts": sorted(set(conflicts)),
    }


def _emit_plan(state: dict[str, Any]) -> None:
    emit("TARGET_STUDENTS", 1)
    emit("BASELINE_EVENTS", len(state["baseline"]))
    emit("POST_HISTORY", len(state["post"]))
    emit("POST_TARGET_SCHOOL", len(state["post_target"]))
    emit("POST_IGNORED_SCHOOL", len(state["post_ignored"]))
    emit("POST_NA", len(state["post_na"]))
    emit("TARGET_ENROLLMENTS", len(state["target_enrollments"]))
    emit("IGNORED_ENROLLMENTS", len(state["ignored_enrollments"]))
    emit("OTHER_REGULAR_ENROLLMENTS", len(state["other_regular"]))
    emit("ACTIVE_REGULAR_ENROLLMENTS", len(state["active_regular"]))
    emit("IGNORED_GRADES", state["ignored_grades"])
    emit("IGNORED_ATTENDANCE", state["ignored_attendance"])
    emit("IGNORED_DEPENDENCIES", state["ignored_dependencies"])
    emit("ALREADY_RESTORED", "YES" if state["currently_restored"] else "NO")
    emit("CONFLICTS", len(state["conflicts"]))
    if state["conflicts"]:
        emit("CONFLICT_TYPES", ",".join(state["conflicts"]))


async def _compensate(db, archive: dict[str, Any], audit_id: str | None) -> bool:
    """Repõe snapshots sem criar/alterar identidade de matrícula.

    Os documentos de enrollment são replay byte-semântico do snapshot arquivado;
    depois a projeção é novamente derivada pelo serviço canônico.
    """
    try:
        target = archive["target_enrollment_before"]
        await db.enrollments.replace_one({"_id": target["_id"]}, target, upsert=True)
        for item in archive.get("ignored_enrollments_before") or []:
            await db.enrollments.replace_one({"_id": item["_id"]}, item, upsert=True)
        for item in archive.get("removed_history_before") or []:
            await db.student_history.replace_one({"_id": item["_id"]}, item, upsert=True)
        previous_status = str(archive.get("student_status_before") or "inactive")
        await rebuild_student_home_projection(
            db,
            archive["student_id"],
            academic_year=YEAR,
            no_primary_status=previous_status,
        )
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
    if state["currently_restored"] and not state["conflicts"]:
        emit("MODE", "APPLY")
        emit("APPLY_NOOP", "ALREADY_RESTORED")
        print("PRODUCTION_DATABASE_TOUCHED=NO", flush=True)
        return
    if state["conflicts"]:
        raise RestoreError("PRECONDITION_CONFLICT")
    if await db.student_recovery_archives.find_one({"_id": OPERATION_ID}, {"_id": 1}):
        raise RestoreError("ARCHIVE_ALREADY_EXISTS")

    sid = case["student_id"]
    tenant = case["tenant"]
    student = state["student"]
    target = state["target_enrollment"]
    archive = {
        "_id": OPERATION_ID,
        "operation": "restore_student_to_baseline",
        "academic_year": YEAR,
        "tenant_id": tenant,
        "student_id": sid,
        "run_id": run_id,
        "state": "PREPARED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_history_id": state["baseline"][0].get("_id"),
        "student_status_before": student.get("status"),
        "student_projection_before": {
            "school_id": student.get("school_id"),
            "class_id": student.get("class_id"),
            "status": student.get("status"),
            "enrollment_number": student.get("enrollment_number"),
            "mantenedora_id": student.get("mantenedora_id"),
        },
        "target_enrollment_before": target,
        "ignored_enrollments_before": state["ignored_enrollments"],
        "removed_history_before": state["post"],
        "academic_guard": {
            "grades": state["ignored_grades"],
            "attendance": state["ignored_attendance"],
            "dependencies": state["ignored_dependencies"],
        },
    }
    await db.student_recovery_archives.insert_one(archive)

    audit_id: str | None = None
    try:
        history_ids = [item["_id"] for item in state["post"]]
        enrollment_ids = [item["_id"] for item in state["ignored_enrollments"]]

        if history_ids:
            result = await db.student_history.delete_many({"_id": {"$in": history_ids}})
            if result.deleted_count != len(history_ids):
                raise RestoreError("HISTORY_DELETE_MISMATCH")
        if enrollment_ids:
            result = await db.enrollments.delete_many({"_id": {"$in": enrollment_ids}})
            if result.deleted_count != len(enrollment_ids):
                raise RestoreError("IGNORED_ENROLLMENT_DELETE_MISMATCH")

        now = datetime.now(timezone.utc).isoformat()
        result = await db.enrollments.update_one(
            {
                "_id": target["_id"],
                "student_id": sid,
                "school_id": case["target_school_id"],
                "class_id": case["target_class_id"],
            },
            {
                "$set": {
                    "status": "active",
                    "mantenedora_id": tenant,
                    "updated_at": now,
                },
                "$unset": {
                    "transfer_date": "",
                    "transferred_at": "",
                    "cancelled_at": "",
                    "cancellation_date": "",
                    "cancel_reason": "",
                    "end_date": "",
                    "exit_date": "",
                    "destination_school_id": "",
                    "destination_class_id": "",
                },
            },
        )
        if result.matched_count != 1:
            raise RestoreError("TARGET_ENROLLMENT_CONCURRENT_CHANGE")

        primary = await rebuild_student_home_projection(db, sid, academic_year=YEAR)
        if not primary:
            raise RestoreError("CANONICAL_PROJECTION_NO_PRIMARY")
        if (
            str(primary.get("school_id") or "") != case["target_school_id"]
            or str(primary.get("class_id") or "") != case["target_class_id"]
            or str(primary.get("enrollment_number") or "")
            != str(target.get("enrollment_number") or "")
        ):
            raise RestoreError("CANONICAL_PROJECTION_WRONG_PRIMARY")

        audit_id = str(uuid.uuid4())
        await db.audit_logs.insert_one(
            {
                "id": audit_id,
                "action": "restore",
                "collection": "students",
                "document_id": str(sid),
                "mantenedora_id": tenant,
                "user_id": "system:student-baseline-restore-2026",
                "school_id": case["target_school_id"],
                "academic_year": YEAR,
                "old_value": archive["student_projection_before"],
                "new_value": {
                    "school_id": case["target_school_id"],
                    "class_id": case["target_class_id"],
                    "status": "active",
                    "enrollment_number": target.get("enrollment_number"),
                },
                "description": (
                    "Restauração forense autorizada ao estado válido de 12/06/2026; "
                    "movimentos posteriores arquivados e retirados da trilha operacional."
                ),
                "extra_data": {
                    "operation_id": OPERATION_ID,
                    "run_id": run_id,
                    "history_removed": len(history_ids),
                    "ignored_enrollments_removed": len(enrollment_ids),
                    "projection_writer": "rebuild_student_home_projection",
                    "academic_records_changed": False,
                },
                "timestamp_utc": now,
                "timestamp_local": now,
            }
        )

        verify = await _inspect(db, case)
        if not verify["currently_restored"] or verify["conflicts"]:
            raise RestoreError("POST_VERIFY_FAILED")
        if (
            verify["ignored_grades"] != state["ignored_grades"]
            or verify["ignored_attendance"] != state["ignored_attendance"]
            or verify["ignored_dependencies"] != state["ignored_dependencies"]
        ):
            raise RestoreError("ACADEMIC_DATA_CHANGED")

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
        emit("HISTORY_REMOVED", len(history_ids))
        emit("IGNORED_ENROLLMENTS_REMOVED", len(enrollment_ids))
        emit("TARGET_ENROLLMENT_REACTIVATED", 1)
        emit("STUDENT_PROJECTION_RESTORED", 1)
        emit("POST_HISTORY_AFTER_BASELINE", len(verify["post"]))
        emit("POST_IGNORED_ENROLLMENTS", len(verify["ignored_enrollments"]))
        emit("AUDIT_EVENTS", 1)
        emit("MODE", "APPLY")
        print(
            "PRODUCTION_DATABASE_TOUCHED=YES_AUTHORIZED_STUDENT_BASELINE_RESTORE_ONLY",
            flush=True,
        )
    except Exception as exc:
        code = exc.code if isinstance(exc, RestoreError) else "UNEXPECTED_APPLY_FAILURE"
        compensated = await _compensate(db, archive, audit_id)
        emit("ERROR", code)
        emit("COMPENSATION", "SUCCESS" if compensated else "FAILED")
        print(
            "PRODUCTION_DATABASE_TOUCHED=COMPENSATED"
            if compensated
            else "PRODUCTION_DATABASE_TOUCHED=POSSIBLE_PARTIAL_APPLY",
            flush=True,
        )
        raise RestoreError(code) from exc


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
    except RestoreError as exc:
        emit("ERROR", exc.code)
        if mode == "preview" or exc.code in {
            "SCHOOL_CARDINALITY",
            "SCHOOL_TENANT_MISMATCH",
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
