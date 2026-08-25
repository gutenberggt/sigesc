#!/usr/bin/env python3
"""Fase C — correlação de identidade READ-ONLY para órfãos de enrollment de 2026.

Objetivo: verificar se um student excluído e um student atual representam a mesma pessoa
sem reanexar dados e sem escrever no MongoDB. A correlação usa dados históricos apenas
internamente e não imprime nascimento, filiação, CPF, RG ou INEP no relatório.

Também aprofunda o único MISSING_CLASS_ONLY de 2026, verificando a trilha de mudanças do
student atual e as referências remanescentes à class_id ausente.
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
IDENTITY_FIELDS = (
    "full_name",
    "birth_date",
    "mother_name",
    "father_name",
    "sex",
    "inep_code",
)
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
SAFE_AUDIT_CHANGE_FIELDS = {
    "status",
    "school_id",
    "class_id",
    "enrollment_number",
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def norm_text(value: Any) -> str:
    raw = _norm(value)
    if not raw:
        return ""
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = re.sub(r"\s+", " ", raw).strip().upper()
    return raw


def _safe_subset(doc: dict[str, Any] | None, fields=SAFE_CURRENT_FIELDS) -> dict[str, Any]:
    doc = doc or {}
    return {k: doc.get(k) for k in fields if k in doc}


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


def _audit_snapshot(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Recupera o último valor conhecido dos campos de identidade.

    Prefere old_value do DELETE; depois percorre eventos do mais recente ao mais antigo.
    Os valores sensíveis são usados somente em memória e nunca retornados diretamente.
    """
    for event in reversed(events):
        if _norm(event.get("action")).lower() == "delete":
            old = event.get("old_value") or {}
            if isinstance(old, dict) and any(old.get(k) not in (None, "") for k in IDENTITY_FIELDS):
                return {k: old.get(k) for k in IDENTITY_FIELDS}
    out: dict[str, Any] = {}
    for event in reversed(events):
        for bucket_name in ("new_value", "old_value"):
            bucket = event.get(bucket_name) or {}
            if not isinstance(bucket, dict):
                continue
            for field in IDENTITY_FIELDS:
                if field not in out and bucket.get(field) not in (None, ""):
                    out[field] = bucket.get(field)
        if len(out) == len(IDENTITY_FIELDS):
            break
    return out


def _identity_available(identity: dict[str, Any]) -> dict[str, bool]:
    return {f: bool(_norm(identity.get(f))) for f in IDENTITY_FIELDS}


def _match_flags(identity: dict[str, Any], candidate: dict[str, Any]) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for field in IDENTITY_FIELDS:
        left = identity.get(field)
        right = candidate.get(field)
        if field in {"full_name", "mother_name", "father_name"}:
            flags[field] = bool(norm_text(left) and norm_text(left) == norm_text(right))
        else:
            flags[field] = bool(_norm(left) and _norm(left) == _norm(right))
    return flags


def score_identity(identity: dict[str, Any], candidate: dict[str, Any]) -> tuple[int, str, dict[str, bool]]:
    flags = _match_flags(identity, candidate)
    score = 0
    score += 5 if flags["full_name"] else 0
    score += 5 if flags["birth_date"] else 0
    score += 4 if flags["mother_name"] else 0
    score += 2 if flags["father_name"] else 0
    score += 1 if flags["sex"] else 0
    score += 8 if flags["inep_code"] else 0

    if flags["inep_code"] and (flags["birth_date"] or flags["full_name"]):
        confidence = "STRONG"
    elif flags["full_name"] and flags["birth_date"] and (flags["mother_name"] or flags["father_name"]):
        confidence = "STRONG"
    elif flags["birth_date"] and flags["mother_name"] and flags["father_name"]:
        confidence = "STRONG"
    elif flags["full_name"] and flags["birth_date"]:
        confidence = "PROBABLE"
    elif flags["full_name"] and flags["mother_name"]:
        confidence = "PROBABLE"
    elif flags["birth_date"] and flags["mother_name"]:
        confidence = "PROBABLE"
    elif flags["full_name"] or (flags["birth_date"] and flags["sex"]):
        confidence = "WEAK"
    else:
        confidence = "NONE"
    return score, confidence, flags


def _days_between(a: Any, b: Any) -> int | None:
    da = _parse_dt(a)
    db = _parse_dt(b)
    if not da or not db:
        return None
    return (db - da).days


def _safe_audit_event(event: dict[str, Any]) -> dict[str, Any]:
    changes = event.get("changes") or {}
    safe_changes = {
        k: v for k, v in changes.items() if k in SAFE_AUDIT_CHANGE_FIELDS
    } if isinstance(changes, dict) else {}
    return {
        "action": event.get("action"),
        "timestamp": event.get("timestamp") or event.get("timestamp_utc"),
        "user_email": event.get("user_email"),
        "description": event.get("description"),
        "changes": safe_changes,
    }


async def _audit_events(db, collection: str, document_id: str) -> list[dict[str, Any]]:
    return await db.audit_logs.find(
        {"collection": collection, "document_id": document_id},
        {"_id": 0},
    ).sort("timestamp", 1).to_list(length=None)


async def _candidate_enrollments(db, student_id: str) -> list[dict[str, Any]]:
    docs = await db.enrollments.find(
        {"student_id": student_id},
        {
            "_id": 0,
            "id": 1,
            "student_id": 1,
            "school_id": 1,
            "class_id": 1,
            "academic_year": 1,
            "status": 1,
            "enrollment_number": 1,
            "enrollment_date": 1,
            "source": 1,
        },
    ).to_list(length=None)
    return sorted(docs, key=lambda x: (_norm(x.get("academic_year")), _norm(x.get("enrollment_date")), _norm(x.get("id"))))


async def _class_evidence(db, cid: str) -> dict[str, int]:
    if not cid:
        return {"grades": 0, "attendance": 0, "content_entries": 0, "student_history": 0}
    return {
        "grades": await db.grades.count_documents({"class_id": cid}),
        "attendance": await db.attendance.count_documents({"class_id": cid}),
        "content_entries": await db.content_entries.count_documents({"class_id": cid}),
        "student_history": await db.student_history.count_documents({"class_id": cid}),
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
            "birth_date": 1,
            "mother_name": 1,
            "father_name": 1,
            "sex": 1,
            "inep_code": 1,
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

    class_ids = {_norm(e.get("class_id")) for e in active_2026 if _norm(e.get("class_id"))}
    classes = await db.classes.find({"id": {"$in": list(class_ids)}}, {"_id": 0, "id": 1}).to_list(length=None)
    class_id_set = {c.get("id") for c in classes if c.get("id")}

    orphans: list[dict[str, Any]] = []
    for enr in active_2026:
        sid = _norm(enr.get("student_id"))
        cid = _norm(enr.get("class_id"))
        student_exists = bool(sid and sid in current_by_id)
        class_exists = bool(cid and cid in class_id_set)
        if student_exists and class_exists:
            continue
        orphans.append({"enrollment": enr, "student_exists": student_exists, "class_exists": class_exists})

    cases: list[dict[str, Any]] = []
    top_candidate_usage: defaultdict[str, list[str]] = defaultdict(list)

    for raw in orphans:
        enr = raw["enrollment"]
        sid = _norm(enr.get("student_id"))
        cid = _norm(enr.get("class_id"))
        item: dict[str, Any] = {
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
            "student_exists": raw["student_exists"],
            "class_exists": raw["class_exists"],
        }

        if not raw["student_exists"]:
            events = await _audit_events(db, "students", sid)
            delete_events = [e for e in events if _norm(e.get("action")).lower() == "delete"]
            delete_event = delete_events[-1] if delete_events else None
            identity = _audit_snapshot(events)

            scored: list[dict[str, Any]] = []
            for candidate in current_students:
                score, confidence, flags = score_identity(identity, candidate)
                if confidence == "NONE":
                    continue
                delete_ts = (delete_event or {}).get("timestamp") or (delete_event or {}).get("timestamp_utc")
                delta_days = _days_between(delete_ts, candidate.get("created_at"))
                scored.append({
                    "candidate": _safe_subset(candidate),
                    "score": score,
                    "confidence": confidence,
                    "match_flags": flags,
                    "created_after_delete": delta_days is not None and delta_days >= 0,
                    "days_from_delete_to_candidate_create": delta_days,
                })

            confidence_order = {"STRONG": 3, "PROBABLE": 2, "WEAK": 1}
            scored.sort(
                key=lambda x: (
                    confidence_order.get(x["confidence"], 0),
                    x["score"],
                    -(x["days_from_delete_to_candidate_create"] if x["days_from_delete_to_candidate_create"] is not None else 10**9),
                ),
                reverse=True,
            )
            scored = scored[:5]

            for candidate_item in scored:
                candidate_item["enrollments"] = await _candidate_enrollments(
                    db, _norm(candidate_item["candidate"].get("id"))
                )

            best = scored[0] if scored else None
            if best and best["confidence"] in {"STRONG", "PROBABLE"}:
                top_candidate_usage[_norm(best["candidate"].get("id"))].append(sid)

            item.update({
                "kind": "MISSING_STUDENT_ONLY",
                "historical_name": identity.get("full_name"),
                "historical_identity_fields_available": _identity_available(identity),
                "delete_event": _safe_audit_event(delete_event) if delete_event else None,
                "candidate_count": len(scored),
                "candidates": scored,
                "best_confidence": best["confidence"] if best else "NONE",
                "best_candidate_id": (best or {}).get("candidate", {}).get("id") if best else None,
            })
        else:
            student = current_by_id[sid]
            student_events = await _audit_events(db, "students", sid)
            class_events = await _audit_events(db, "classes", cid)
            class_delete_events = [e for e in class_events if _norm(e.get("action")).lower() == "delete"]
            item.update({
                "kind": "MISSING_CLASS_ONLY",
                "student": _safe_subset(student),
                "student_audit_events": [_safe_audit_event(e) for e in student_events],
                "class_delete_events": [_safe_audit_event(e) for e in class_delete_events],
                "class_evidence": await _class_evidence(db, cid),
                "all_enrollments_for_student": await _candidate_enrollments(db, sid),
            })
        cases.append(item)

    shared_candidates = {
        cid: old_ids for cid, old_ids in top_candidate_usage.items() if cid and len(old_ids) > 1
    }
    for item in cases:
        best_id = _norm(item.get("best_candidate_id"))
        if best_id and best_id in shared_candidates:
            item["best_candidate_shared_by_multiple_orphans"] = True
            item["shared_orphan_student_ids"] = shared_candidates[best_id]
        elif item.get("kind") == "MISSING_STUDENT_ONLY":
            item["best_candidate_shared_by_multiple_orphans"] = False

    confidence_counts = Counter(
        item.get("best_confidence", "NONE")
        for item in cases
        if item.get("kind") == "MISSING_STUDENT_ONLY"
    )

    return {
        "mode": "READ_ONLY",
        "phase": "C",
        "academic_year": YEAR,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "orphan_active_2026": len(cases),
            "missing_student": sum(1 for x in cases if x.get("kind") == "MISSING_STUDENT_ONLY"),
            "missing_class": sum(1 for x in cases if x.get("kind") == "MISSING_CLASS_ONLY"),
            "best_strong": confidence_counts.get("STRONG", 0),
            "best_probable": confidence_counts.get("PROBABLE", 0),
            "best_weak": confidence_counts.get("WEAK", 0),
            "best_none": confidence_counts.get("NONE", 0),
            "shared_best_current_candidates": len(shared_candidates),
        },
        "privacy": {
            "raw_birth_date_exposed": False,
            "raw_parent_names_exposed": False,
            "raw_inep_exposed": False,
            "raw_cpf_exposed": False,
        },
        "shared_best_candidates": shared_candidates,
        "cases": cases,
    }


def human(report: dict[str, Any]) -> str:
    c = report["counts"]
    lines = [
        "SIGESC — AUDITORIA FORENSE DE ÓRFÃOS 2026 — FASE C (READ-ONLY)",
        "=" * 78,
        f"Casos órfãos ativos 2026: {c['orphan_active_2026']}",
        f"- missing student: {c['missing_student']}",
        f"- missing class: {c['missing_class']}",
        f"- melhor candidato STRONG: {c['best_strong']}",
        f"- melhor candidato PROBABLE: {c['best_probable']}",
        f"- melhor candidato WEAK: {c['best_weak']}",
        f"- sem candidato: {c['best_none']}",
        f"- candidatos atuais compartilhados por múltiplos órfãos: {c['shared_best_current_candidates']}",
        "",
        "CASOS",
    ]
    for i, item in enumerate(report["cases"], 1):
        enr = item["enrollment"]
        if item["kind"] == "MISSING_STUDENT_ONLY":
            lines.append(
                f"[{i:02d}] MISSING_STUDENT | enr={enr.get('id')} | num={enr.get('enrollment_number')} | "
                f"historical={item.get('historical_name') or '(sem nome)'} | best={item.get('best_confidence')}"
            )
            for cand in item.get("candidates", [])[:3]:
                cdoc = cand["candidate"]
                flags = [k for k, v in cand.get("match_flags", {}).items() if v]
                lines.append(
                    f"     candidate={cdoc.get('id')} | name={cdoc.get('full_name')} | "
                    f"status={cdoc.get('status')} | num={cdoc.get('enrollment_number')} | "
                    f"confidence={cand.get('confidence')} score={cand.get('score')} | "
                    f"flags={','.join(flags)} | days_from_delete={cand.get('days_from_delete_to_candidate_create')}"
                )
            if item.get("best_candidate_shared_by_multiple_orphans"):
                lines.append("     ATENÇÃO: melhor candidato atual é compartilhado por múltiplos órfãos antigos")
        else:
            st = item.get("student") or {}
            ev = item.get("class_evidence") or {}
            lines.append(
                f"[{i:02d}] MISSING_CLASS | enr={enr.get('id')} | student={st.get('full_name')} | "
                f"status={st.get('status')} | class={enr.get('class_id')} | refs={sum(ev.values())}"
            )
    lines.append("")
    lines.append("Dados de nascimento/filiação/INEP são usados apenas para flags de match e não são impressos.")
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
