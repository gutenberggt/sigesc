#!/usr/bin/env python3
"""Fase E — plano de reparo READ-ONLY para enrollments órfãos de 2026.

Esta fase NÃO altera MongoDB. Ela parte da identidade confirmada por CPF da Fase D,
compara o enrollment órfão com o cadastro/matrículas atuais e mede referências em
notas, frequência e histórico antes de sugerir uma classe de reparo.

Nenhum CPF, nota ou outro dado sensível bruto é serializado no relatório.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

YEAR = 2026
SPECIAL_PROGRAMS = frozenset({"aee", "recomposicao_aprendizagem", "reforco_escolar"})
GRADE_FIELDS = ("b1", "b2", "b3", "b4", "rec_s1", "rec_s2", "recovery", "final_average", "average")
FORBIDDEN_REPORT_KEYS = {
    "cpf", "rg", "mother_name", "father_name", "birth_date", "inep_code", "nis",
    "civil_certificate_number", "old_value", "new_value",
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def norm_text(value: Any) -> str:
    raw = _norm(value)
    if not raw:
        return ""
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", raw).strip().upper()


def norm_cpf(value: Any) -> str:
    digits = re.sub(r"\D", "", _norm(value))
    return digits if len(digits) == 11 else ""


def _safe_student(doc: dict[str, Any] | None) -> dict[str, Any]:
    doc = doc or {}
    fields = ("id", "full_name", "status", "school_id", "class_id", "enrollment_number", "mantenedora_id", "created_at", "updated_at")
    return {k: doc.get(k) for k in fields if k in doc}


def _safe_enrollment(doc: dict[str, Any] | None) -> dict[str, Any]:
    doc = doc or {}
    fields = (
        "id", "student_id", "school_id", "class_id", "academic_year", "status",
        "enrollment_number", "previous_enrollment_number", "enrollment_date", "source",
        "mantenedora_id", "created_at", "updated_at",
    )
    return {k: doc.get(k) for k in fields if k in doc}


def _event_instant(event: dict[str, Any]) -> str:
    return _norm(event.get("timestamp_utc") or event.get("timestamp") or event.get("timestamp_local"))


def _delete_identity(events: list[dict[str, Any]]) -> tuple[str, str]:
    """Retorna (nome, cpf normalizado) somente em memória."""
    ordered = sorted(events, key=_event_instant, reverse=True)
    for event in ordered:
        if _norm(event.get("action")).lower() != "delete":
            continue
        old = event.get("old_value") or {}
        if isinstance(old, dict):
            return _norm(old.get("full_name")), norm_cpf(old.get("cpf"))
    return "", ""


def _grade_key(doc: dict[str, Any]) -> tuple[str, str, str]:
    return (_norm(doc.get("class_id")), _norm(doc.get("course_id")), _norm(doc.get("academic_year")))


def compare_grade_docs(old_docs: list[dict[str, Any]], target_docs: list[dict[str, Any]]) -> dict[str, int]:
    target_by_key: defaultdict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for doc in target_docs:
        target_by_key[_grade_key(doc)].append(doc)

    overlap = 0
    conflicts = 0
    mergeable = 0
    for old in old_docs:
        matches = target_by_key.get(_grade_key(old), [])
        if not matches:
            continue
        overlap += 1
        conflict = False
        for target in matches:
            for field in GRADE_FIELDS:
                left, right = old.get(field), target.get(field)
                if left not in (None, "") and right not in (None, "") and left != right:
                    conflict = True
                    break
            if conflict:
                break
        if conflict:
            conflicts += 1
        else:
            mergeable += 1
    return {
        "old_grade_docs": len(old_docs),
        "target_grade_docs": len(target_docs),
        "overlap_keys": overlap,
        "conflicting_overlap_keys": conflicts,
        "mergeable_overlap_keys": mergeable,
    }


def _attendance_rows(docs: list[dict[str, Any]], sid: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for doc in docs:
        for row in doc.get("records") or []:
            if _norm((row or {}).get("student_id")) != sid:
                continue
            out.append({
                "doc_id": doc.get("id"),
                "date": doc.get("date"),
                "class_id": doc.get("class_id"),
                "course_id": doc.get("course_id"),
                "academic_year": doc.get("academic_year"),
                "status": (row or {}).get("status"),
            })
    return out


def compare_attendance_docs(old_docs: list[dict[str, Any]], target_docs: list[dict[str, Any]], old_sid: str, target_sid: str) -> dict[str, int]:
    old_rows = _attendance_rows(old_docs, old_sid)
    target_rows = _attendance_rows(target_docs, target_sid)
    target_by_doc: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in target_rows:
        target_by_doc[_norm(row.get("doc_id"))].append(row)

    overlap = 0
    conflicts = 0
    for row in old_rows:
        matches = target_by_doc.get(_norm(row.get("doc_id")), [])
        if not matches:
            continue
        overlap += 1
        old_status = _norm(row.get("status"))
        if any(old_status and _norm(x.get("status")) and old_status != _norm(x.get("status")) for x in matches):
            conflicts += 1
    return {
        "old_attendance_rows": len(old_rows),
        "target_attendance_rows": len(target_rows),
        "overlap_rows": overlap,
        "conflicting_overlap_rows": conflicts,
    }


def classify_repair_plan(*, verified: bool, shared_target: bool, target_regular_active: int,
                         grade_conflicts: int, attendance_conflicts: int,
                         old_reference_total: int) -> str:
    if not verified:
        return "IDENTITY_REVIEW_REQUIRED"
    if shared_target:
        return "SHARED_TARGET_CONSOLIDATION_REQUIRED"
    if target_regular_active != 1:
        return "TARGET_CANONICAL_ENROLLMENT_REVIEW_REQUIRED"
    if grade_conflicts or attendance_conflicts:
        return "ACADEMIC_COLLISION_REQUIRES_REVIEW"
    if old_reference_total:
        return "MIGRATE_REFERENCES_THEN_CLOSE_ORPHAN"
    return "CLOSE_ORPHAN_NO_REFERENCES"


def _assert_report_safe(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_REPORT_KEYS:
                raise RuntimeError(f"Campo sensível proibido no relatório: {path}.{key}")
            _assert_report_safe(child, f"{path}.{key}")
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            _assert_report_safe(child, f"{path}[{idx}]")


async def _audit_events(db, sid: str) -> list[dict[str, Any]]:
    return await db.audit_logs.find(
        {"collection": "students", "document_id": sid},
        {"_id": 0, "action": 1, "timestamp": 1, "timestamp_utc": 1, "timestamp_local": 1, "old_value": 1},
    ).to_list(length=None)


async def _enrollments(db, sid: str) -> list[dict[str, Any]]:
    docs = await db.enrollments.find({"student_id": sid}, {"_id": 0}).to_list(length=None)
    return sorted(docs, key=lambda x: (_norm(x.get("academic_year")), _norm(x.get("enrollment_date")), _norm(x.get("id"))))


async def _grade_docs(db, sid: str) -> list[dict[str, Any]]:
    projection = {"_id": 0, "id": 1, "student_id": 1, "class_id": 1, "course_id": 1, "academic_year": 1}
    for field in GRADE_FIELDS:
        projection[field] = 1
    return await db.grades.find({"student_id": sid}, projection).to_list(length=None)


async def _attendance_docs(db, sid: str) -> list[dict[str, Any]]:
    return await db.attendance.find(
        {"records.student_id": sid},
        {"_id": 0, "id": 1, "date": 1, "class_id": 1, "course_id": 1, "academic_year": 1, "records": 1},
    ).to_list(length=None)


async def _history_summary(db, sid: str) -> dict[str, int]:
    docs = await db.student_history.find(
        {"student_id": sid}, {"_id": 0, "records": 1}
    ).to_list(length=None)
    return {
        "documents": len(docs),
        "records": sum(len(x.get("records") or []) for x in docs),
    }


def _regular_active_2026(enrollments: list[dict[str, Any]], classes_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for enr in enrollments:
        if _norm(enr.get("status")).lower() != "active":
            continue
        if _norm(enr.get("academic_year")) != str(YEAR):
            continue
        cls = classes_by_id.get(_norm(enr.get("class_id")))
        if not cls:
            continue
        if _norm(cls.get("atendimento_programa")).lower() in SPECIAL_PROGRAMS:
            continue
        out.append(enr)
    return out


def _relationship(orphan: dict[str, Any], target_regular: list[dict[str, Any]]) -> str:
    if len(target_regular) != 1:
        return "NO_UNIQUE_TARGET_REGULAR_2026"
    target = target_regular[0]
    if _norm(orphan.get("class_id")) == _norm(target.get("class_id")):
        return "SAME_CLASS"
    if _norm(orphan.get("school_id")) == _norm(target.get("school_id")):
        return "SAME_SCHOOL_DIFFERENT_CLASS"
    return "DIFFERENT_SCHOOL"


async def audit(db) -> dict[str, Any]:
    active = await db.enrollments.find(
        {"status": "active", "academic_year": {"$in": [YEAR, str(YEAR)]}}, {"_id": 0}
    ).to_list(length=None)

    sids = sorted({_norm(x.get("student_id")) for x in active if _norm(x.get("student_id"))})
    cids = sorted({_norm(x.get("class_id")) for x in active if _norm(x.get("class_id"))})
    existing_students = await db.students.find({"id": {"$in": sids}}, {"_id": 0}).to_list(length=None)
    existing_classes = await db.classes.find({"id": {"$in": cids}}, {"_id": 0}).to_list(length=None)
    students_by_id = {x.get("id"): x for x in existing_students if x.get("id")}
    classes_by_id = {x.get("id"): x for x in existing_classes if x.get("id")}

    orphans: list[dict[str, Any]] = []
    for enr in active:
        sid, cid = _norm(enr.get("student_id")), _norm(enr.get("class_id"))
        if sid in students_by_id and cid in classes_by_id:
            continue
        orphans.append(enr)

    # Candidates atuais: CPF permanece apenas em memória.
    current_students = await db.students.find(
        {}, {"_id": 0, "id": 1, "full_name": 1, "cpf": 1, "status": 1, "school_id": 1,
             "class_id": 1, "enrollment_number": 1, "mantenedora_id": 1, "created_at": 1, "updated_at": 1}
    ).to_list(length=None)
    current_by_cpf: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for student in current_students:
        cpf = norm_cpf(student.get("cpf"))
        if cpf:
            current_by_cpf[cpf].append(student)

    # Carrega turmas adicionais usadas pelas matrículas dos candidatos.
    all_candidate_enrollments: dict[str, list[dict[str, Any]]] = {}
    candidate_class_ids = set(cids)
    identity_map: dict[str, dict[str, Any]] = {}
    target_usage: defaultdict[str, list[str]] = defaultdict(list)

    for enr in orphans:
        sid = _norm(enr.get("student_id"))
        if sid in students_by_id:
            continue
        events = await _audit_events(db, sid)
        historical_name, historical_cpf = _delete_identity(events)
        cpf_matches = current_by_cpf.get(historical_cpf, []) if historical_cpf else []
        target = cpf_matches[0] if len(cpf_matches) == 1 else None
        identity_map[sid] = {
            "historical_name": historical_name,
            "verified": bool(target),
            "cpf_match_count": len(cpf_matches),
            "target": target,
        }
        if target:
            tid = _norm(target.get("id"))
            target_usage[tid].append(sid)
            enrs = await _enrollments(db, tid)
            all_candidate_enrollments[tid] = enrs
            candidate_class_ids.update(_norm(x.get("class_id")) for x in enrs if _norm(x.get("class_id")))

    extra_classes = await db.classes.find(
        {"id": {"$in": sorted(candidate_class_ids)}},
        {"_id": 0, "id": 1, "school_id": 1, "atendimento_programa": 1, "name": 1, "academic_year": 1},
    ).to_list(length=None)
    classes_by_id.update({x.get("id"): x for x in extra_classes if x.get("id")})

    cases: list[dict[str, Any]] = []
    for enr in orphans:
        sid, cid = _norm(enr.get("student_id")), _norm(enr.get("class_id"))
        if sid in students_by_id:
            student = students_by_id[sid]
            other_active = [x for x in await _enrollments(db, sid) if x.get("id") != enr.get("id") and _norm(x.get("status")).lower() == "active"]
            class_refs = {
                "grades": await db.grades.count_documents({"class_id": cid}),
                "attendance": await db.attendance.count_documents({"class_id": cid}),
                "content_entries": await db.content_entries.count_documents({"class_id": cid}),
                "student_history": await db.student_history.count_documents({"records.class_id": cid}),
                "student_projections": await db.students.count_documents({"class_id": cid}),
            }
            refs_total = sum(class_refs.values())
            if _norm(student.get("status")).lower() != "active" and not _norm(student.get("class_id")) and not other_active and refs_total == 0:
                plan = "CLOSE_STALE_MISSING_CLASS_CANDIDATE"
            else:
                plan = "MISSING_CLASS_REVIEW_REQUIRED"
            cases.append({
                "kind": "MISSING_CLASS_ONLY",
                "enrollment": _safe_enrollment(enr),
                "student": _safe_student(student),
                "other_active_enrollments": [_safe_enrollment(x) for x in other_active],
                "class_reference_counts": class_refs,
                "repair_plan": plan,
            })
            continue

        identity = identity_map.get(sid) or {}
        target = identity.get("target")
        verified = bool(identity.get("verified") and target)
        target_id = _norm((target or {}).get("id"))
        target_enrollments = all_candidate_enrollments.get(target_id, []) if target_id else []
        target_regular = _regular_active_2026(target_enrollments, classes_by_id) if target_id else []

        old_grades = await _grade_docs(db, sid)
        old_att = await _attendance_docs(db, sid)
        old_hist = await _history_summary(db, sid)
        grade_cmp = compare_grade_docs(old_grades, await _grade_docs(db, target_id)) if target_id else compare_grade_docs(old_grades, [])
        att_cmp = compare_attendance_docs(old_att, await _attendance_docs(db, target_id), sid, target_id) if target_id else compare_attendance_docs(old_att, [], sid, "")
        target_hist = await _history_summary(db, target_id) if target_id else {"documents": 0, "records": 0}

        old_reference_total = grade_cmp["old_grade_docs"] + att_cmp["old_attendance_rows"] + old_hist["records"]
        shared = bool(target_id and len(target_usage.get(target_id, [])) > 1)
        plan = classify_repair_plan(
            verified=verified,
            shared_target=shared,
            target_regular_active=len(target_regular),
            grade_conflicts=grade_cmp["conflicting_overlap_keys"],
            attendance_conflicts=att_cmp["conflicting_overlap_rows"],
            old_reference_total=old_reference_total,
        )

        cases.append({
            "kind": "MISSING_STUDENT_ONLY",
            "enrollment": _safe_enrollment(enr),
            "historical_name": identity.get("historical_name"),
            "identity_verified_by_unique_cpf": verified,
            "cpf_match_count": identity.get("cpf_match_count", 0),
            "target_student": _safe_student(target) if target else None,
            "target_regular_active_2026": [_safe_enrollment(x) for x in target_regular],
            "relationship_to_target_regular": _relationship(enr, target_regular),
            "shared_target": shared,
            "shared_orphan_count": len(target_usage.get(target_id, [])) if target_id else 0,
            "grades": grade_cmp,
            "attendance": att_cmp,
            "student_history": {
                "old_documents": old_hist["documents"],
                "old_records": old_hist["records"],
                "target_documents": target_hist["documents"],
                "target_records": target_hist["records"],
            },
            "old_reference_total": old_reference_total,
            "repair_plan": plan,
        })

    counts = Counter(x.get("repair_plan") for x in cases)
    report = {
        "mode": "READ_ONLY",
        "phase": "E",
        "academic_year": YEAR,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "orphan_active_2026": len(cases),
            "missing_student": sum(1 for x in cases if x.get("kind") == "MISSING_STUDENT_ONLY"),
            "missing_class": sum(1 for x in cases if x.get("kind") == "MISSING_CLASS_ONLY"),
            "repair_plans": dict(sorted(counts.items())),
            "verified_identity": sum(1 for x in cases if x.get("identity_verified_by_unique_cpf")),
            "shared_targets": len([tid for tid, olds in target_usage.items() if tid and len(olds) > 1]),
        },
        "cases": cases,
    }
    _assert_report_safe(report)
    return report


def human(report: dict[str, Any]) -> str:
    c = report["counts"]
    lines = [
        "SIGESC — PLANO FORENSE DE REPARO DE ÓRFÃOS 2026 — FASE E (READ-ONLY)",
        "=" * 78,
        f"Casos órfãos ativos 2026: {c['orphan_active_2026']}",
        f"- missing student: {c['missing_student']}",
        f"- missing class: {c['missing_class']}",
        f"- identidades verificadas por CPF único: {c['verified_identity']}",
        f"- candidatos atuais compartilhados: {c['shared_targets']}",
        "- planos: " + ", ".join(f"{k}={v}" for k, v in c["repair_plans"].items()),
        "",
        "CASOS",
    ]
    for idx, item in enumerate(report["cases"], 1):
        enr = item["enrollment"]
        if item["kind"] == "MISSING_CLASS_ONLY":
            student = item.get("student") or {}
            lines.append(
                f"[{idx:02d}] MISSING_CLASS | enr={enr.get('id')} | student={student.get('full_name')} | "
                f"plan={item.get('repair_plan')} | refs={sum(item.get('class_reference_counts', {}).values())}"
            )
            continue
        target = item.get("target_student") or {}
        grades = item.get("grades") or {}
        attendance = item.get("attendance") or {}
        hist = item.get("student_history") or {}
        lines.append(
            f"[{idx:02d}] MISSING_STUDENT | enr={enr.get('id')} | num={enr.get('enrollment_number')} | "
            f"historical={item.get('historical_name')} | plan={item.get('repair_plan')}"
        )
        lines.append(
            f"     target={target.get('id') or '-'} | name={target.get('full_name') or '-'} | "
            f"regular2026={len(item.get('target_regular_active_2026') or [])} | relation={item.get('relationship_to_target_regular')} | "
            f"shared={item.get('shared_target')}"
        )
        lines.append(
            f"     refs: grades={grades.get('old_grade_docs', 0)} conflict={grades.get('conflicting_overlap_keys', 0)} | "
            f"attendance={attendance.get('old_attendance_rows', 0)} conflict={attendance.get('conflicting_overlap_rows', 0)} | "
            f"history={hist.get('old_records', 0)}"
        )
    lines += [
        "",
        "Nenhuma escrita MongoDB é executada. O relatório não contém CPF nem valores de notas.",
        "Use --json para saída completa; --output grava JSON local.",
    ]
    return "\n".join(lines)


async def _main(args) -> int:
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        raise SystemExit("MONGO_URL não definido")
    db_name = os.environ.get("DB_NAME", "sigesc_db")
    client = AsyncIOMotorClient(mongo_url)
    try:
        report = await audit(client[db_name])
    finally:
        client.close()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        print(f"Relatório JSON: {args.output}")
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(human(report))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fase E READ-ONLY: plano de reparo dos órfãos de enrollment 2026")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--output")
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
