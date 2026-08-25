#!/usr/bin/env python3
"""Fase B — auditoria forense READ-ONLY dos enrollments órfãos de 2026.

Objetivo: explicar como cada referência ausente chegou ao estado atual, sem escrever
no MongoDB. Para student_id ausente, consolida eventos de audit_logs, último snapshot
seguro conhecido, student_history, notas/frequência, demais enrollments e possíveis
candidatos atuais por número/nome. Para class_id ausente, faz o equivalente com logs
de classes e o estado atual do aluno.

Não contém operações MongoDB de escrita. Opcionalmente grava JSON apenas no filesystem
local via --output.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

YEAR = 2026
SAFE_STUDENT_FIELDS = (
    "id", "full_name", "status", "school_id", "class_id", "student_series",
    "enrollment_number", "enrollment_date", "mantenedora_id", "created_at", "updated_at",
)
SAFE_CLASS_FIELDS = (
    "id", "name", "school_id", "academic_year", "grade_level", "shift",
    "atendimento_programa", "mantenedora_id", "created_at", "updated_at",
)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_subset(value: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {k: value.get(k) for k in fields if k in value}


def _event_instant(event: dict[str, Any]) -> str:
    return _norm(event.get("timestamp_utc") or event.get("timestamp") or event.get("timestamp_local"))


def _safe_event(event: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {
        "action": event.get("action"),
        "collection": event.get("collection"),
        "timestamp": _event_instant(event),
        "user_email": event.get("user_email"),
        "user_role": event.get("user_role"),
        "description": event.get("description"),
        "old_value": _safe_subset(event.get("old_value"), fields),
        "new_value": _safe_subset(event.get("new_value"), fields),
        "changes": _safe_subset(event.get("changes"), fields),
    }


def _latest_snapshot(events: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, Any]:
    """Obtém o snapshot mais recente que possua algum campo seguro útil.

    Para DELETE, old_value tem precedência. Nos demais eventos, new_value tem precedência.
    """
    ordered = sorted(events, key=_event_instant, reverse=True)
    for event in ordered:
        candidates = (
            [event.get("old_value"), event.get("new_value")]
            if _norm(event.get("action")).lower() == "delete"
            else [event.get("new_value"), event.get("old_value")]
        )
        for candidate in candidates:
            safe = _safe_subset(candidate, fields)
            if safe:
                safe["_snapshot_from_action"] = event.get("action")
                safe["_snapshot_at"] = _event_instant(event)
                return safe
    return {}


def classify_missing_student(*, grades: int, attendance: int, history_docs: int, audit_events: int,
                             delete_events: int, same_number_candidates: int, same_name_candidates: int) -> list[str]:
    labels: list[str] = []
    if grades or attendance:
        labels.append("ACADEMIC_DATA_PRESENT")
    elif history_docs:
        labels.append("ADMIN_HISTORY_PRESENT")
    elif audit_events:
        labels.append("AUDIT_TRACE_ONLY")
    else:
        labels.append("NO_TRACE")
    if delete_events:
        labels.append("STUDENT_DELETE_AUDITED")
    if same_number_candidates:
        labels.append("CURRENT_STUDENT_SAME_ENROLLMENT_NUMBER")
    if same_name_candidates:
        labels.append("CURRENT_STUDENT_SAME_NAME")
    return labels


def classify_missing_class(*, student_status: str, student_class_id: str, active_other_enrollments: int,
                           class_delete_events: int, class_evidence_total: int) -> list[str]:
    labels = ["MISSING_CLASS"]
    if _norm(student_status).lower() != "active" and not _norm(student_class_id):
        labels.append("STUDENT_CURRENTLY_INACTIVE_UNASSIGNED")
    if active_other_enrollments:
        labels.append("OTHER_ACTIVE_ENROLLMENT_PRESENT")
    if class_delete_events:
        labels.append("CLASS_DELETE_AUDITED")
    if class_evidence_total:
        labels.append("CLASS_REFERENCES_REMAIN")
    else:
        labels.append("NO_CLASS_REFERENCES_REMAIN")
    return labels


async def _audit_events(db, *, collection: str, document_id: str) -> list[dict[str, Any]]:
    if not document_id:
        return []
    docs = await db.audit_logs.find(
        {"collection": collection, "document_id": document_id},
        {
            "_id": 0, "action": 1, "collection": 1, "document_id": 1,
            "timestamp": 1, "timestamp_utc": 1, "timestamp_local": 1,
            "user_email": 1, "user_role": 1, "description": 1,
            "old_value": 1, "new_value": 1, "changes": 1,
        },
    ).to_list(length=None)
    return sorted(docs, key=_event_instant)


async def _history_summary(db, sid: str) -> dict[str, Any]:
    docs = await db.student_history.find(
        {"student_id": sid},
        {"_id": 0, "id": 1, "student_id": 1, "records": 1, "created_at": 1, "updated_at": 1},
    ).to_list(length=None)
    records: list[dict[str, Any]] = []
    for doc in docs:
        for rec in doc.get("records") or []:
            if not isinstance(rec, dict):
                continue
            records.append({
                "serie": rec.get("serie"),
                "ano_letivo": rec.get("ano_letivo"),
                "escola": rec.get("escola"),
                "resultado": rec.get("resultado"),
                "class_id": rec.get("class_id") or rec.get("_class_id"),
            })
    return {
        "documents": len(docs),
        "records": records,
        "created_at": [x.get("created_at") for x in docs if x.get("created_at")],
        "updated_at": [x.get("updated_at") for x in docs if x.get("updated_at")],
    }


async def _academic_summary(db, sid: str) -> dict[str, Any]:
    grades = await db.grades.find(
        {"student_id": sid},
        {"_id": 0, "id": 1, "academic_year": 1, "class_id": 1, "course_id": 1,
         "status": 1, "created_at": 1, "updated_at": 1},
    ).to_list(length=None)
    attendance_docs = await db.attendance.find(
        {"records.student_id": sid},
        {"_id": 0, "id": 1, "date": 1, "academic_year": 1, "class_id": 1,
         "course_id": 1, "records": 1},
    ).to_list(length=None)
    attendance_rows = []
    for doc in attendance_docs:
        for row in doc.get("records") or []:
            if _norm((row or {}).get("student_id")) == sid:
                attendance_rows.append({
                    "date": doc.get("date"),
                    "academic_year": doc.get("academic_year"),
                    "class_id": doc.get("class_id"),
                    "course_id": doc.get("course_id"),
                    "status": row.get("status"),
                })
    dates = sorted(_norm(x.get("date")) for x in attendance_rows if _norm(x.get("date")))
    return {
        "grades_count": len(grades),
        "grade_class_ids": sorted({_norm(x.get("class_id")) for x in grades if _norm(x.get("class_id"))}),
        "grade_years": sorted({_norm(x.get("academic_year")) for x in grades if _norm(x.get("academic_year"))}),
        "attendance_records": len(attendance_rows),
        "attendance_class_ids": sorted({_norm(x.get("class_id")) for x in attendance_rows if _norm(x.get("class_id"))}),
        "attendance_years": sorted({_norm(x.get("academic_year")) for x in attendance_rows if _norm(x.get("academic_year"))}),
        "attendance_first_date": dates[0] if dates else None,
        "attendance_last_date": dates[-1] if dates else None,
        "attendance_status_counts": dict(sorted(Counter(_norm(x.get("status")) or "__missing__" for x in attendance_rows).items())),
    }


async def _all_enrollments(db, sid: str) -> list[dict[str, Any]]:
    return await db.enrollments.find(
        {"student_id": sid},
        {"_id": 0, "id": 1, "student_id": 1, "school_id": 1, "class_id": 1,
         "academic_year": 1, "status": 1, "enrollment_number": 1,
         "previous_enrollment_number": 1, "enrollment_date": 1, "source": 1,
         "created_at": 1, "updated_at": 1},
    ).to_list(length=None)


async def _student_candidates(db, *, enrollment_number: str, historical_name: str) -> dict[str, Any]:
    by_number = []
    if enrollment_number:
        by_number = await db.students.find(
            {"enrollment_number": enrollment_number},
            {"_id": 0, **{k: 1 for k in SAFE_STUDENT_FIELDS}},
        ).to_list(length=None)
    by_name = []
    if historical_name:
        pattern = f"^{re.escape(historical_name)}$"
        by_name = await db.students.find(
            {"full_name": {"$regex": pattern, "$options": "i"}},
            {"_id": 0, **{k: 1 for k in SAFE_STUDENT_FIELDS}},
        ).to_list(length=None)
    return {"same_enrollment_number": by_number, "same_name": by_name}


async def _class_evidence(db, cid: str) -> dict[str, int]:
    if not cid:
        return {"grades": 0, "attendance": 0, "content_entries": 0, "student_projections": 0, "student_history": 0}
    return {
        "grades": await db.grades.count_documents({"class_id": cid}),
        "attendance": await db.attendance.count_documents({"class_id": cid}),
        "content_entries": await db.content_entries.count_documents({"class_id": cid}),
        "student_projections": await db.students.count_documents({"class_id": cid}),
        "student_history": await db.student_history.count_documents({"records.class_id": cid}),
    }


async def audit(db) -> dict[str, Any]:
    active = await db.enrollments.find(
        {"status": "active", "academic_year": {"$in": [YEAR, str(YEAR)]}},
        {"_id": 0},
    ).to_list(length=None)
    sids = sorted({_norm(x.get("student_id")) for x in active if _norm(x.get("student_id"))})
    cids = sorted({_norm(x.get("class_id")) for x in active if _norm(x.get("class_id"))})
    students = await db.students.find({"id": {"$in": sids}}, {"_id": 0}).to_list(length=None)
    classes = await db.classes.find({"id": {"$in": cids}}, {"_id": 0}).to_list(length=None)
    students_by_id = {x.get("id"): x for x in students if x.get("id")}
    classes_by_id = {x.get("id"): x for x in classes if x.get("id")}

    cases: list[dict[str, Any]] = []
    for enr in active:
        sid = _norm(enr.get("student_id"))
        cid = _norm(enr.get("class_id"))
        student = students_by_id.get(sid)
        cls = classes_by_id.get(cid)
        if student and cls:
            continue

        item: dict[str, Any] = {
            "enrollment": {
                "id": enr.get("id"), "student_id": enr.get("student_id"),
                "class_id": enr.get("class_id"), "school_id": enr.get("school_id"),
                "academic_year": enr.get("academic_year"), "status": enr.get("status"),
                "enrollment_number": enr.get("enrollment_number"),
                "enrollment_date": enr.get("enrollment_date"), "source": enr.get("source"),
                "created_at": enr.get("created_at"), "updated_at": enr.get("updated_at"),
            },
            "student_exists": bool(student),
            "class_exists": bool(cls),
        }

        if not student:
            events = await _audit_events(db, collection="students", document_id=sid)
            safe_events = [_safe_event(e, SAFE_STUDENT_FIELDS) for e in events]
            snapshot = _latest_snapshot(events, SAFE_STUDENT_FIELDS)
            name = _norm(snapshot.get("full_name"))
            history = await _history_summary(db, sid)
            academic = await _academic_summary(db, sid)
            enrollments = await _all_enrollments(db, sid)
            candidates = await _student_candidates(
                db,
                enrollment_number=_norm(enr.get("enrollment_number")),
                historical_name=name,
            )
            deletes = [x for x in safe_events if _norm(x.get("action")).lower() == "delete"]
            item.update({
                "kind": "MISSING_STUDENT_ONLY" if cls else "BOTH_MISSING",
                "class": _safe_subset(cls, SAFE_CLASS_FIELDS) if cls else None,
                "historical_student_snapshot": snapshot,
                "student_audit_events": safe_events,
                "student_delete_events": deletes,
                "student_history": history,
                "academic_evidence": academic,
                "all_enrollments_for_missing_student_id": enrollments,
                "current_student_candidates": candidates,
                "classification": classify_missing_student(
                    grades=academic["grades_count"],
                    attendance=academic["attendance_records"],
                    history_docs=history["documents"],
                    audit_events=len(safe_events),
                    delete_events=len(deletes),
                    same_number_candidates=len(candidates["same_enrollment_number"]),
                    same_name_candidates=len(candidates["same_name"]),
                ),
            })
        else:
            events = await _audit_events(db, collection="classes", document_id=cid)
            safe_events = [_safe_event(e, SAFE_CLASS_FIELDS) for e in events]
            snapshot = _latest_snapshot(events, SAFE_CLASS_FIELDS)
            deletes = [x for x in safe_events if _norm(x.get("action")).lower() == "delete"]
            enrollments = await _all_enrollments(db, sid)
            other_active = [x for x in enrollments if x.get("id") != enr.get("id") and _norm(x.get("status")).lower() == "active"]
            evidence = await _class_evidence(db, cid)
            item.update({
                "kind": "MISSING_CLASS_ONLY",
                "student": _safe_subset(student, SAFE_STUDENT_FIELDS),
                "historical_class_snapshot": snapshot,
                "class_audit_events": safe_events,
                "class_delete_events": deletes,
                "class_evidence": evidence,
                "all_enrollments_for_student": enrollments,
                "other_active_enrollments": other_active,
                "classification": classify_missing_class(
                    student_status=_norm(student.get("status")),
                    student_class_id=_norm(student.get("class_id")),
                    active_other_enrollments=len(other_active),
                    class_delete_events=len(deletes),
                    class_evidence_total=sum(evidence.values()),
                ),
            })
        cases.append(item)

    return {
        "mode": "READ_ONLY",
        "phase": "B",
        "academic_year": YEAR,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "orphan_active_2026": len(cases),
            "missing_student": sum(1 for x in cases if not x["student_exists"]),
            "missing_class": sum(1 for x in cases if not x["class_exists"]),
            "student_delete_audited": sum(1 for x in cases if "STUDENT_DELETE_AUDITED" in x.get("classification", [])),
            "academic_data_present": sum(1 for x in cases if "ACADEMIC_DATA_PRESENT" in x.get("classification", [])),
            "current_student_same_number": sum(1 for x in cases if "CURRENT_STUDENT_SAME_ENROLLMENT_NUMBER" in x.get("classification", [])),
            "current_student_same_name": sum(1 for x in cases if "CURRENT_STUDENT_SAME_NAME" in x.get("classification", [])),
        },
        "cases": cases,
    }


def human(report: dict[str, Any]) -> str:
    c = report["counts"]
    lines = [
        "SIGESC — AUDITORIA FORENSE DE ÓRFÃOS 2026 — FASE B (READ-ONLY)",
        "=" * 78,
        f"Casos órfãos ativos 2026: {c['orphan_active_2026']}",
        f"- missing student: {c['missing_student']}",
        f"- missing class: {c['missing_class']}",
        f"- exclusões de student comprovadas por audit log: {c['student_delete_audited']}",
        f"- casos com notas/frequência: {c['academic_data_present']}",
        f"- candidatos atuais com mesmo enrollment_number: {c['current_student_same_number']}",
        f"- candidatos atuais com mesmo nome histórico: {c['current_student_same_name']}",
        "",
        "CASOS",
    ]
    for i, x in enumerate(report["cases"], 1):
        e = x["enrollment"]
        snapshot = x.get("historical_student_snapshot") or x.get("historical_class_snapshot") or {}
        subject = snapshot.get("full_name") or snapshot.get("name") or "(sem nome recuperado)"
        lines.append(
            f"[{i:02d}] {x['kind']} | enr={e.get('id')} | num={e.get('enrollment_number')} | "
            f"subject={subject} | labels={','.join(x.get('classification', []))}"
        )
        if x.get("student_delete_events"):
            last = x["student_delete_events"][-1]
            lines.append(
                f"     student DELETE: {last.get('timestamp') or '?'} | user={last.get('user_email') or '?'}"
            )
        if x.get("class_delete_events"):
            last = x["class_delete_events"][-1]
            lines.append(
                f"     class DELETE: {last.get('timestamp') or '?'} | user={last.get('user_email') or '?'}"
            )
        academic = x.get("academic_evidence") or {}
        if academic:
            lines.append(
                f"     academic: grades={academic.get('grades_count', 0)} "
                f"attendance={academic.get('attendance_records', 0)} "
                f"range={academic.get('attendance_first_date')}..{academic.get('attendance_last_date')}"
            )
    lines.append("")
    lines.append("Use --json para saída completa; --output grava JSON local. Nenhuma escrita MongoDB é executada.")
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--output")
    args = parser.parse_args()
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc_db")
    if not mongo_url:
        raise SystemExit("MONGO_URL não configurada")
    client = AsyncIOMotorClient(mongo_url)
    try:
        report = await audit(client[db_name])
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str) if args.as_json else human(report))
        if args.output:
            print(f"Relatório JSON: {args.output}")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
