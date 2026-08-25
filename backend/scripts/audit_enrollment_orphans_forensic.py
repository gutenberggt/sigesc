#!/usr/bin/env python3
"""Auditoria forense READ-ONLY de enrollments ativos órfãos.

Investiga exclusivamente enrollments com status=active cujo student_id e/ou class_id
não resolvem para documentos existentes. Não contém qualquer operação de escrita no
MongoDB. Opcionalmente grava o relatório JSON em arquivo local com --output.
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

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _year(value: Any) -> str:
    raw = _norm(value)
    return raw if raw else "__missing__"


def escaped(value: Any) -> str:
    return json.dumps(_norm(value), ensure_ascii=True)[1:-1]


def has_control_chars(value: Any) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in _norm(value))


def is_uuid_like(value: Any) -> bool:
    return bool(UUID_RE.fullmatch(_norm(value)))


def orphan_kind(*, student_exists: bool, class_exists: bool) -> str:
    if not student_exists and not class_exists:
        return "BOTH_MISSING"
    if not class_exists:
        return "MISSING_CLASS_ONLY"
    if not student_exists:
        return "MISSING_STUDENT_ONLY"
    return "NOT_ORPHAN"


def _counter_by_year(items: list[dict[str, Any]]) -> dict[str, int]:
    c = Counter(_year(x.get("academic_year")) for x in items)
    return dict(sorted(c.items(), key=lambda kv: kv[0]))


async def _student_evidence(db, sid: str) -> dict[str, int]:
    if not sid:
        return {
            "grades": 0,
            "attendance_records": 0,
            "student_history": 0,
            "audit_logs": 0,
            "planos_aee": 0,
            "bolsa_familia_tracking": 0,
        }
    return {
        "grades": await db.grades.count_documents({"student_id": sid}),
        "attendance_records": await db.attendance.count_documents({"records.student_id": sid}),
        "student_history": await db.student_history.count_documents({"student_id": sid}),
        "audit_logs": await db.audit_logs.count_documents(
            {"$or": [{"document_id": sid}, {"student_id": sid}]}
        ),
        "planos_aee": await db.planos_aee.count_documents({"student_id": sid}),
        "bolsa_familia_tracking": await db.bolsa_familia_tracking.count_documents({"student_id": sid}),
    }


async def _class_evidence(db, cid: str) -> dict[str, int]:
    if not cid:
        return {
            "grades": 0,
            "attendance": 0,
            "content_entries": 0,
            "student_projections": 0,
            "student_history": 0,
        }
    return {
        "grades": await db.grades.count_documents({"class_id": cid}),
        "attendance": await db.attendance.count_documents({"class_id": cid}),
        "content_entries": await db.content_entries.count_documents({"class_id": cid}),
        "student_projections": await db.students.count_documents({"class_id": cid}),
        "student_history": await db.student_history.count_documents({"class_id": cid}),
    }


async def audit(db) -> dict[str, Any]:
    active = await db.enrollments.find({"status": "active"}, {"_id": 0}).to_list(length=None)

    student_ids = sorted({_norm(e.get("student_id")) for e in active if _norm(e.get("student_id"))})
    class_ids = sorted({_norm(e.get("class_id")) for e in active if _norm(e.get("class_id"))})
    school_ids = sorted({_norm(e.get("school_id")) for e in active if _norm(e.get("school_id"))})

    students = await db.students.find(
        {"id": {"$in": student_ids}},
        {"_id": 0, "id": 1, "full_name": 1, "status": 1, "school_id": 1, "class_id": 1,
         "enrollment_number": 1, "mantenedora_id": 1},
    ).to_list(length=None)
    classes = await db.classes.find(
        {"id": {"$in": class_ids}},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1,
         "mantenedora_id": 1, "atendimento_programa": 1, "school_history": 1},
    ).to_list(length=None)
    schools = await db.schools.find(
        {"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}
    ).to_list(length=None)

    students_by_id = {x.get("id"): x for x in students if x.get("id")}
    classes_by_id = {x.get("id"): x for x in classes if x.get("id")}
    schools_by_id = {x.get("id"): x for x in schools if x.get("id")}

    missing_class: list[dict[str, Any]] = []
    missing_student: list[dict[str, Any]] = []
    union: list[dict[str, Any]] = []

    for e in active:
        sid = _norm(e.get("student_id"))
        cid = _norm(e.get("class_id"))
        student_exists = bool(sid and sid in students_by_id)
        class_exists = bool(cid and cid in classes_by_id)
        if student_exists and class_exists:
            continue

        item = {
            "enrollment_id": e.get("id"),
            "enrollment_id_escaped": escaped(e.get("id")),
            "enrollment_id_uuid_like": is_uuid_like(e.get("id")),
            "enrollment_id_has_control_chars": has_control_chars(e.get("id")),
            "kind": orphan_kind(student_exists=student_exists, class_exists=class_exists),
            "academic_year": e.get("academic_year"),
            "student_id": e.get("student_id"),
            "class_id": e.get("class_id"),
            "school_id": e.get("school_id"),
            "school_name": (schools_by_id.get(e.get("school_id")) or {}).get("name"),
            "mantenedora_id": e.get("mantenedora_id"),
            "status": e.get("status"),
            "enrollment_number": e.get("enrollment_number"),
            "previous_enrollment_number": e.get("previous_enrollment_number"),
            "enrollment_date": e.get("enrollment_date"),
            "created_at": e.get("created_at"),
            "updated_at": e.get("updated_at"),
            "source": e.get("source"),
            "student_exists": student_exists,
            "class_exists": class_exists,
        }
        if student_exists:
            s = students_by_id[sid]
            item["student"] = {
                "full_name": s.get("full_name"),
                "status": s.get("status"),
                "school_id": s.get("school_id"),
                "class_id": s.get("class_id"),
                "enrollment_number": s.get("enrollment_number"),
                "mantenedora_id": s.get("mantenedora_id"),
            }
        if class_exists:
            c = classes_by_id[cid]
            item["class"] = {
                "name": c.get("name"),
                "school_id": c.get("school_id"),
                "academic_year": c.get("academic_year"),
                "mantenedora_id": c.get("mantenedora_id"),
                "atendimento_programa": c.get("atendimento_programa"),
            }

        union.append(item)
        if not class_exists:
            missing_class.append(item)
        if not student_exists:
            missing_student.append(item)

    student_evidence_cache: dict[str, dict[str, int]] = {}
    class_evidence_cache: dict[str, dict[str, int]] = {}
    for item in union:
        sid = _norm(item.get("student_id"))
        cid = _norm(item.get("class_id"))
        if not item["student_exists"] and sid not in student_evidence_cache:
            student_evidence_cache[sid] = await _student_evidence(db, sid)
        if not item["class_exists"] and cid not in class_evidence_cache:
            class_evidence_cache[cid] = await _class_evidence(db, cid)
        if not item["student_exists"]:
            item["missing_student_evidence"] = student_evidence_cache[sid]
        if not item["class_exists"]:
            item["missing_class_evidence"] = class_evidence_cache[cid]

    intersection = [x for x in union if x["kind"] == "BOTH_MISSING"]
    malformed = [
        x for x in union
        if x["enrollment_id_has_control_chars"] or not x["enrollment_id_uuid_like"]
    ]
    current_2026 = [x for x in union if _year(x.get("academic_year")) == "2026"]

    return {
        "mode": "READ_ONLY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "active enrollments missing referenced student and/or class",
        "counts": {
            "active_enrollments_scanned": len(active),
            "missing_class": len(missing_class),
            "missing_student": len(missing_student),
            "intersection_both_missing": len(intersection),
            "unique_orphan_enrollments": len(union),
            "current_year_2026": len(current_2026),
            "non_uuid_or_control_char_enrollment_ids": len(malformed),
        },
        "by_kind": dict(sorted(Counter(x["kind"] for x in union).items())),
        "by_year": {
            "missing_class": _counter_by_year(missing_class),
            "missing_student": _counter_by_year(missing_student),
            "intersection_both_missing": _counter_by_year(intersection),
            "unique_union": _counter_by_year(union),
        },
        "intersection_enrollment_ids": [x.get("enrollment_id") for x in intersection],
        "malformed_or_non_uuid": malformed,
        "cases_2026": current_2026,
        "cases": sorted(union, key=lambda x: (_year(x.get("academic_year")), escaped(x.get("enrollment_id")))),
    }


def human(report: dict[str, Any]) -> str:
    c = report["counts"]
    lines = [
        "SIGESC — AUDITORIA FORENSE DE ENROLLMENTS ÓRFÃOS (READ-ONLY)",
        "=" * 72,
        f"Active enrollments examinados: {c['active_enrollments_scanned']}",
        "",
        "CONTAGENS EXATAS",
        f"- missing class: {c['missing_class']}",
        f"- missing student: {c['missing_student']}",
        f"- interseção (ambos ausentes): {c['intersection_both_missing']}",
        f"- união única de órfãos: {c['unique_orphan_enrollments']}",
        f"- casos 2026 na união: {c['current_year_2026']}",
        f"- enrollment IDs não-UUID ou com controle: {c['non_uuid_or_control_char_enrollment_ids']}",
        "",
        "POR TIPO",
    ]
    for key, value in report["by_kind"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("POR ANO")
    for group, values in report["by_year"].items():
        lines.append(f"- {group}: {values}")
    lines.append("")
    lines.append("CASOS 2026")
    if report["cases_2026"]:
        for x in report["cases_2026"]:
            lines.append(
                f"- {x['kind']} | enr={x['enrollment_id_escaped']} | "
                f"student={escaped(x.get('student_id'))} | class={escaped(x.get('class_id'))} | "
                f"school={escaped(x.get('school_id'))}"
            )
    else:
        lines.append("- nenhum")
    lines.append("")
    lines.append("Use --json para relatório completo; --output grava JSON local sem escrever no MongoDB.")
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--output", help="arquivo JSON local opcional (ex.: /tmp/orphans.json)")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc_db")
    if not mongo_url:
        raise SystemExit("MONGO_URL não configurada")

    client = AsyncIOMotorClient(mongo_url)
    try:
        report = await audit(client[db_name])
    finally:
        client.close()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(human(report))
        if args.output:
            print(f"Relatório JSON: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
