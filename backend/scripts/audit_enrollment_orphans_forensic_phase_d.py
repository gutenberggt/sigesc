#!/usr/bin/env python3
"""Fase D — correlação determinística e READ-ONLY dos órfãos 2026.

Usa o CPF preservado no old_value do DELETE apenas em memória para verificar
identidade entre um student excluído e um student atual. O CPF bruto nunca é
impresso nem gravado no JSON. Não existe --apply e não há escrita no MongoDB.
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
SAFE_CURRENT_FIELDS = (
    "id",
    "full_name",
    "status",
    "school_id",
    "class_id",
    "enrollment_number",
    "mantenedora_id",
    "created_at",
    "updated_at",
)


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
    """Normaliza CPF somente em memória. Nunca retornar o valor normalizado."""
    return re.sub(r"\D", "", _norm(value))


def cpf_shape_valid(value: Any) -> bool:
    digits = norm_cpf(value)
    return len(digits) == 11 and len(set(digits)) > 1


def _safe_student(doc: dict[str, Any] | None) -> dict[str, Any]:
    doc = doc or {}
    return {k: doc.get(k) for k in SAFE_CURRENT_FIELDS if k in doc}


def _parse_dt(value: Any) -> datetime | None:
    raw = _norm(value)
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def days_between(a: Any, b: Any) -> int | None:
    da = _parse_dt(a)
    db = _parse_dt(b)
    if not da or not db:
        return None
    return (db - da).days


def _delete_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    deletes = [e for e in events if _norm(e.get("action")).lower() == "delete"]
    return deletes[-1] if deletes else None


def _safe_delete_event(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not event:
        return None
    # Não copiar description nem old_value: ambos podem conter CPF bruto.
    return {
        "action": event.get("action"),
        "timestamp": event.get("timestamp") or event.get("timestamp_utc"),
        "user_email": event.get("user_email"),
    }


def identity_disposition(
    cpf_match_count: int,
    name_match_count: int,
    *,
    unique_cpf_name_match: bool = False,
) -> str:
    if cpf_match_count > 1:
        return "AMBIGUOUS_CPF_COLLISION"
    if cpf_match_count == 1 and unique_cpf_name_match:
        return "VERIFIED_CPF_AND_NAME"
    if cpf_match_count == 1:
        return "VERIFIED_CPF_NAME_CHANGED"
    if name_match_count > 0:
        return "NAME_ONLY_UNVERIFIED"
    return "NO_CURRENT_MATCH"


def _contains_raw_sensitive_key(value: Any) -> bool:
    """Guard recursivo para impedir serialização acidental de identidade bruta."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"cpf", "rg", "birth_date", "mother_name", "father_name", "inep_code"}:
                return True
            if _contains_raw_sensitive_key(child):
                return True
    elif isinstance(value, list):
        return any(_contains_raw_sensitive_key(x) for x in value)
    return False


async def _audit_events(db, student_id: str) -> list[dict[str, Any]]:
    return await db.audit_logs.find(
        {"collection": "students", "document_id": student_id},
        {"_id": 0},
    ).sort("timestamp", 1).to_list(length=None)


async def _candidate_enrollments(db, student_id: str) -> list[dict[str, Any]]:
    docs = await db.enrollments.find(
        {"student_id": student_id},
        {
            "_id": 0,
            "id": 1,
            "school_id": 1,
            "class_id": 1,
            "academic_year": 1,
            "status": 1,
            "enrollment_number": 1,
            "enrollment_date": 1,
            "source": 1,
        },
    ).to_list(length=None)
    return sorted(
        docs,
        key=lambda x: (
            _norm(x.get("academic_year")),
            _norm(x.get("enrollment_date")),
            _norm(x.get("id")),
        ),
    )


async def _academic_evidence(db, student_id: str) -> dict[str, int]:
    return {
        "grades": await db.grades.count_documents({"student_id": student_id}),
        "attendance": await db.attendance.count_documents({"student_id": student_id}),
        "student_history": await db.student_history.count_documents({"student_id": student_id}),
    }


async def _class_evidence(db, class_id: str) -> dict[str, int]:
    if not class_id:
        return {"grades": 0, "attendance": 0, "content_entries": 0, "student_history": 0}
    return {
        "grades": await db.grades.count_documents({"class_id": class_id}),
        "attendance": await db.attendance.count_documents({"class_id": class_id}),
        "content_entries": await db.content_entries.count_documents({"class_id": class_id}),
        "student_history": await db.student_history.count_documents({"class_id": class_id}),
    }


async def audit(db) -> dict[str, Any]:
    active_2026 = await db.enrollments.find(
        {"status": "active", "academic_year": {"$in": [YEAR, str(YEAR)]}},
        {"_id": 0},
    ).to_list(length=None)

    current_students = await db.students.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "full_name": 1,
            "cpf": 1,  # uso somente em memória
            "status": 1,
            "school_id": 1,
            "class_id": 1,
            "enrollment_number": 1,
            "mantenedora_id": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    ).to_list(length=None)
    current_by_id = {s.get("id"): s for s in current_students if s.get("id")}

    cpf_index: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    name_index: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for student in current_students:
        cpf = norm_cpf(student.get("cpf"))
        if cpf_shape_valid(cpf):
            cpf_index[cpf].append(student)
        name = norm_text(student.get("full_name"))
        if name:
            name_index[name].append(student)

    class_ids = {_norm(e.get("class_id")) for e in active_2026 if _norm(e.get("class_id"))}
    classes = await db.classes.find(
        {"id": {"$in": list(class_ids)}},
        {"_id": 0, "id": 1},
    ).to_list(length=None)
    class_id_set = {c.get("id") for c in classes if c.get("id")}

    cases: list[dict[str, Any]] = []
    best_candidate_usage: defaultdict[str, list[str]] = defaultdict(list)

    for enr in active_2026:
        sid = _norm(enr.get("student_id"))
        cid = _norm(enr.get("class_id"))
        student_exists = bool(sid and sid in current_by_id)
        class_exists = bool(cid and cid in class_id_set)
        if student_exists and class_exists:
            continue

        base = {
            "enrollment": {
                "id": enr.get("id"),
                "student_id": enr.get("student_id"),
                "class_id": enr.get("class_id"),
                "school_id": enr.get("school_id"),
                "academic_year": enr.get("academic_year"),
                "status": enr.get("status"),
                "enrollment_number": enr.get("enrollment_number"),
                "enrollment_date": enr.get("enrollment_date"),
                "source": enr.get("source"),
            },
            "student_exists": student_exists,
            "class_exists": class_exists,
        }

        if not student_exists:
            events = await _audit_events(db, sid)
            delete_event = _delete_event(events)
            old = (delete_event or {}).get("old_value") or {}
            if not isinstance(old, dict):
                old = {}

            historical_name = old.get("full_name")
            historical_cpf = norm_cpf(old.get("cpf"))
            historical_cpf_valid = cpf_shape_valid(historical_cpf)

            cpf_matches = cpf_index.get(historical_cpf, []) if historical_cpf_valid else []
            name_matches = name_index.get(norm_text(historical_name), []) if historical_name else []

            cpf_match_ids = {_norm(s.get("id")) for s in cpf_matches}
            name_match_ids = {_norm(s.get("id")) for s in name_matches}
            unique_cpf = cpf_matches[0] if len(cpf_matches) == 1 else None
            unique_cpf_name_match = bool(
                unique_cpf
                and norm_text(unique_cpf.get("full_name"))
                and norm_text(unique_cpf.get("full_name")) == norm_text(historical_name)
            )
            disposition = identity_disposition(
                len(cpf_matches),
                len(name_matches),
                unique_cpf_name_match=unique_cpf_name_match,
            )

            candidates: list[dict[str, Any]] = []
            union_ids = []
            seen_ids = set()
            for candidate in [*cpf_matches, *name_matches]:
                candidate_id = _norm(candidate.get("id"))
                if not candidate_id or candidate_id in seen_ids:
                    continue
                seen_ids.add(candidate_id)
                union_ids.append(candidate_id)
                delete_ts = (delete_event or {}).get("timestamp") or (delete_event or {}).get("timestamp_utc")
                candidates.append({
                    "candidate": _safe_student(candidate),
                    "cpf_exact_match": candidate_id in cpf_match_ids,
                    "name_exact_match": candidate_id in name_match_ids,
                    "days_from_delete_to_candidate_create": days_between(delete_ts, candidate.get("created_at")),
                    "same_school_as_orphan_enrollment": _norm(candidate.get("school_id")) == _norm(enr.get("school_id")),
                    "same_class_as_orphan_enrollment": _norm(candidate.get("class_id")) == cid,
                    "enrollments": await _candidate_enrollments(db, candidate_id),
                })

            candidates.sort(
                key=lambda x: (
                    1 if x["cpf_exact_match"] else 0,
                    1 if x["name_exact_match"] else 0,
                    -(abs(x["days_from_delete_to_candidate_create"]) if x["days_from_delete_to_candidate_create"] is not None else 10**9),
                ),
                reverse=True,
            )

            best_candidate_id = None
            if len(cpf_matches) == 1:
                best_candidate_id = _norm(cpf_matches[0].get("id"))
            elif len(cpf_matches) == 0 and len(name_matches) == 1:
                best_candidate_id = _norm(name_matches[0].get("id"))
            if best_candidate_id:
                best_candidate_usage[best_candidate_id].append(sid)

            base.update({
                "kind": "MISSING_STUDENT_ONLY",
                "historical_name": historical_name,
                "historical_cpf_present": bool(historical_cpf),
                "historical_cpf_valid_shape": historical_cpf_valid,
                "delete_event": _safe_delete_event(delete_event),
                "cpf_exact_match_count": len(cpf_matches),
                "name_exact_match_count": len(name_matches),
                "identity_disposition": disposition,
                "best_candidate_id": best_candidate_id,
                "candidate_count": len(candidates),
                "candidates": candidates,
                "academic_evidence": await _academic_evidence(db, sid),
            })
        else:
            student = current_by_id[sid]
            base.update({
                "kind": "MISSING_CLASS_ONLY",
                "student": _safe_student(student),
                "class_evidence": await _class_evidence(db, cid),
                "all_enrollments_for_student": await _candidate_enrollments(db, sid),
                "identity_disposition": "NOT_APPLICABLE_MISSING_CLASS",
            })

        cases.append(base)

    shared_candidates = {
        candidate_id: old_student_ids
        for candidate_id, old_student_ids in best_candidate_usage.items()
        if candidate_id and len(old_student_ids) > 1
    }
    for item in cases:
        if item.get("kind") != "MISSING_STUDENT_ONLY":
            continue
        best_id = _norm(item.get("best_candidate_id"))
        item["best_candidate_shared_by_multiple_orphans"] = bool(best_id and best_id in shared_candidates)
        if best_id and best_id in shared_candidates:
            item["shared_orphan_student_ids"] = shared_candidates[best_id]

    dispositions = Counter(
        item.get("identity_disposition")
        for item in cases
        if item.get("kind") == "MISSING_STUDENT_ONLY"
    )

    report = {
        "mode": "READ_ONLY",
        "phase": "D",
        "academic_year": YEAR,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "orphan_active_2026": len(cases),
            "missing_student": sum(1 for x in cases if x.get("kind") == "MISSING_STUDENT_ONLY"),
            "missing_class": sum(1 for x in cases if x.get("kind") == "MISSING_CLASS_ONLY"),
            "verified_cpf_and_name": dispositions.get("VERIFIED_CPF_AND_NAME", 0),
            "verified_cpf_name_changed": dispositions.get("VERIFIED_CPF_NAME_CHANGED", 0),
            "ambiguous_cpf_collision": dispositions.get("AMBIGUOUS_CPF_COLLISION", 0),
            "name_only_unverified": dispositions.get("NAME_ONLY_UNVERIFIED", 0),
            "no_current_match": dispositions.get("NO_CURRENT_MATCH", 0),
            "shared_best_current_candidates": len(shared_candidates),
        },
        "privacy": {
            "raw_cpf_exposed": False,
            "raw_rg_exposed": False,
            "raw_birth_date_exposed": False,
            "raw_parent_names_exposed": False,
            "raw_inep_exposed": False,
        },
        "shared_best_candidates": shared_candidates,
        "cases": cases,
    }
    if _contains_raw_sensitive_key(report):
        raise RuntimeError("PRIVACY_GUARD_FAILED: relatório contém chave de identidade bruta")
    return report


def human(report: dict[str, Any]) -> str:
    c = report["counts"]
    lines = [
        "SIGESC — AUDITORIA FORENSE DE ÓRFÃOS 2026 — FASE D (READ-ONLY)",
        "=" * 78,
        f"Casos órfãos ativos 2026: {c['orphan_active_2026']}",
        f"- missing student: {c['missing_student']}",
        f"- missing class: {c['missing_class']}",
        f"- CPF + nome verificados: {c['verified_cpf_and_name']}",
        f"- CPF verificado com nome diferente: {c['verified_cpf_name_changed']}",
        f"- colisão de CPF atual: {c['ambiguous_cpf_collision']}",
        f"- somente nome, não verificado: {c['name_only_unverified']}",
        f"- sem candidato atual: {c['no_current_match']}",
        f"- candidatos atuais compartilhados por múltiplos órfãos: {c['shared_best_current_candidates']}",
        "",
        "CASOS",
    ]

    for i, item in enumerate(report["cases"], 1):
        enr = item["enrollment"]
        if item["kind"] == "MISSING_CLASS_ONLY":
            st = item.get("student") or {}
            refs = sum((item.get("class_evidence") or {}).values())
            lines.append(
                f"[{i:02d}] MISSING_CLASS | enr={enr.get('id')} | student={st.get('full_name')} | "
                f"status={st.get('status')} | class={enr.get('class_id')} | refs={refs}"
            )
            continue

        lines.append(
            f"[{i:02d}] MISSING_STUDENT | enr={enr.get('id')} | num={enr.get('enrollment_number')} | "
            f"historical={item.get('historical_name') or '(sem nome)'} | disposition={item.get('identity_disposition')} | "
            f"cpf_matches={item.get('cpf_exact_match_count')} | name_matches={item.get('name_exact_match_count')}"
        )
        for cand in item.get("candidates", [])[:3]:
            cdoc = cand["candidate"]
            lines.append(
                f"     candidate={cdoc.get('id')} | name={cdoc.get('full_name')} | status={cdoc.get('status')} | "
                f"num={cdoc.get('enrollment_number')} | cpf_match={cand.get('cpf_exact_match')} | "
                f"name_match={cand.get('name_exact_match')} | days_from_delete={cand.get('days_from_delete_to_candidate_create')}"
            )
        if item.get("best_candidate_shared_by_multiple_orphans"):
            lines.append("     ATENÇÃO: candidato atual compartilhado por múltiplos órfãos antigos")

    lines.extend([
        "",
        "CPF é comparado somente em memória; o valor bruto não é impresso nem gravado no JSON.",
        "Use --json para saída completa; --output grava JSON local. Nenhuma escrita MongoDB é executada.",
    ])
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
