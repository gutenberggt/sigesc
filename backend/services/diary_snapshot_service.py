"""
Serviço de Snapshot Imutável do Diário Escolar (Fase 5 — Mai/2026).

PRINCÍPIO ABSOLUTO: snapshot é CONGELADO no momento da publicação.
NUNCA recalcular a partir do banco vivo. NUNCA recalcular o hash.

Diretrizes (10 do owner):
  1. PDF lê snapshot, não banco vivo.
  2. Multi-autoria preservada (created_by, updated_by, published_by, validated_by).
  3. Hash SHA-256 imutável, computado sobre payload canônico (UTF-8, sort_keys, sem campos voláteis).
  4. branding[] reservado no schema agora — mudar depois é péssimo.
  5. renders[] (array) — snapshot é verdade, PDFs são derivações.
  6. semantic_rules_version — congela significado institucional do "complete/empty/etc".
  7. signatures append-only com revoked_signature_at (nunca delete).
  8. Idempotência: retorna existente enquanto draft/published; novo só após supersede.
  9. supersede ≠ revoke (substituição vs invalidação institucional).
  10. Canonicalização documentada explicitamente.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import string
import uuid
from datetime import datetime, timezone
from typing import Optional

from utils.document_hash import compute_document_hash

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Versionamento congelado (bump exige nova rodada arquitetural)
# ----------------------------------------------------------------------------
SCHEMA_VERSION = "1"
SEMANTIC_RULES_VERSION = "1"          # significado de "complete/empty/inconsistent/..."
TEMPLATE_VERSION = "diary-v1"          # layout do PDF
RENDER_ENGINE_VERSION = "1"            # versão do motor de render

DOCUMENT_TYPE = "diary_period"

VALID_STATUSES = ("draft", "published", "superseded", "revoked")
VALID_PERIOD_TYPES = ("month", "bimester", "custom")

# Status que ainda "ocupam" o slot de idempotência. `superseded`/`revoked` liberam.
ACTIVE_STATUSES = ("draft", "published")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_code() -> str:
    """Gera código humano SIGESC-DIARY-XXXX-XXXX (16 chars úteis + prefixo)."""
    alphabet = string.ascii_uppercase + string.digits
    p1 = "".join(random.choices(alphabet, k=4))
    p2 = "".join(random.choices(alphabet, k=4))
    return f"SIGESC-DIARY-{p1}-{p2}"


def _gen_verification_token() -> str:
    """UUID hex 32 chars (opaco) para URL pública /v/ ou /verify/diary/ futura."""
    return uuid.uuid4().hex


# ============================================================================
# CANONICALIZAÇÃO (documentação explícita do owner — diretriz 10)
# ============================================================================
# Regras:
#   - JSON dump com sort_keys=True (ordem determinística).
#   - separators=(",",":") — sem espaços inseridos.
#   - ensure_ascii=False — UTF-8 preservado.
#   - default=str — datetime/UUID → string ISO/repr.
#   - Campos transitórios e mutáveis EXCLUÍDOS antes do hash:
#       signatures, audit_trail, renders, status, superseded_by_snapshot_id,
#       revoked_at, revoked_reason, revoked_by_user_id, payload_hash_sha256,
#       verification_token (gerado em paralelo), _id, code (renderizado por
#       conveniência humana, não é parte do conteúdo institucional).
# A FUNÇÃO `compute_document_hash` (utils/document_hash.py) já honra isto.

def canonical_serialize(payload: dict) -> str:
    """Serialização canônica determinística (UTF-8, ordenada). Pública só para auditoria."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), default=str,
    )


# ============================================================================
# CONSOLIDAÇÃO DO PAYLOAD (lê banco vivo APENAS na hora de criar o draft)
# ============================================================================
async def _resolve_branding(db, *, mantenedora_id: Optional[str], school_id: str) -> dict:
    """Branding reservado já — mudar schema depois é péssimo (diretriz 5)."""
    school = await db.schools.find_one({"id": school_id}, {"_id": 0, "name": 1})
    mant = None
    if mantenedora_id:
        mant = await db.mantenedoras.find_one(
            {"id": mantenedora_id},
            {"_id": 0, "nome": 1, "brasao_url": 1, "logotipo_url": 1, "cor_primaria": 1, "cor_secundaria": 1, "secretaria": 1},
        )
    return {
        "mantenedora_name": (mant or {}).get("nome"),
        "school_name": (school or {}).get("name"),
        "logo_file_id": (mant or {}).get("brasao_url") or (mant or {}).get("logotipo_url"),
        "primary_color": (mant or {}).get("cor_primaria") or "#1E40AF",
        "secondary_color": (mant or {}).get("cor_secundaria") or "#0F172A",
        "document_footer": (mant or {}).get("secretaria"),
        "signature_layout": "row",  # placeholder p/ futuro
    }


async def _resolve_user_names(db, user_ids: set[str]) -> dict[str, dict]:
    """Resolve {user_id → {full_name, role}} em batch (sem PII além desses 2)."""
    user_ids = {u for u in user_ids if u}
    if not user_ids:
        return {}
    cursor = db.users.find({"id": {"$in": list(user_ids)}}, {"_id": 0, "id": 1, "full_name": 1, "role": 1})
    users = await cursor.to_list(len(user_ids))
    return {u["id"]: {"full_name": u.get("full_name"), "role": u.get("role")} for u in users}


def _normalize_attendance_record(rec: dict) -> dict:
    """Snapshot de 1 registro de frequência (campos mínimos para reprodução)."""
    return {
        "student_id": rec.get("student_id"),
        "status": rec.get("status"),
        "dependency_id": rec.get("dependency_id"),
    }


async def consolidate_diary_payload(
    db,
    *,
    class_id: str,
    period_from: str,    # YYYY-MM-DD
    period_to: str,      # YYYY-MM-DD
) -> dict:
    """Lê banco vivo e CONGELA o payload completo do período.

    Reusa `calendar_diary_state` como fonte de verdade do shape semântico —
    mas DESACOPLADO (chama internamente as mesmas queries). Para evitar
    importar o router HTTP, replicamos a lógica essencial aqui.

    NOTA arquitetural: poderíamos importar a função do router, mas o router
    depende de Request/auth. Mantemos o serviço puro.
    """
    from routers.calendar_diary_state import (
        _parse_date,
        _daterange,
        _is_assignment_active_on,
        ATTENDANCE_DONE_STATUSES,
        CONTENT_PUBLISHED_LIKE,
        _classify_day,
    )

    d_from = _parse_date(period_from)
    d_to = _parse_date(period_to)

    klass = await db.classes.find_one(
        {"id": class_id},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "grade_level": 1,
         "education_level": 1, "shift": 1, "academic_year": 1, "mantenedora_id": 1},
    )
    if not klass:
        raise ValueError(f"Class not found: {class_id}")

    # ------------------------ Assignments vigentes ------------------------
    assignments = await db.teacher_class_assignments.find(
        {
            "class_id": class_id,
            "deleted": False,
            "valid_from": {"$lte": period_to},
            "$or": [{"valid_until": None}, {"valid_until": {"$gte": period_from}}],
        },
        {"_id": 0},
    ).to_list(2000)

    expected_by_date: dict = {}
    for a in assignments:
        for slot in a.get("weekly_slots", []) or []:
            wd = slot.get("weekday")
            aula = slot.get("aula_numero")
            if not wd or not aula:
                continue
            for day in _daterange(d_from, d_to):
                if not _is_assignment_active_on(a, day):
                    continue
                if day.isoweekday() != wd:
                    continue
                iso = day.isoformat()
                expected_by_date.setdefault(iso, []).append({
                    "component_id": a.get("component_id"),
                    "component_name": a.get("component_id"),  # fallback até mapping da Fase 9
                    "aula_numero": aula,
                    "teacher_id": a.get("teacher_id"),
                    "teacher_name": a.get("teacher_name"),
                    "assignment_id": a["id"],
                    "is_substitute": a.get("is_substitute", False),
                    "attendance_status": "missing",
                    "content_status": "missing",
                    "attendance_records": [],
                    "content_text": None,
                    "content_methodology": None,
                    "content_observations": None,
                    "published_by": None,
                    "published_at": None,
                    "corrected_by": None,
                    "corrected_at": None,
                    "validated_by": None,
                    "validated_at": None,
                    "version": None,
                    "slot_start": slot.get("start_time"),
                    "slot_end": slot.get("end_time"),
                    "expected_by_schedule": True,
                })

    # ------------------------ Evidências (attendance + content) -----------
    dates_in_range = [day.isoformat() for day in _daterange(d_from, d_to)]
    attendances = await db.attendance.find(
        {"class_id": class_id, "date": {"$in": dates_in_range}},
        {"_id": 0},
    ).to_list(5000)
    content_entries = await db.content_entries.find(
        {"class_id": class_id, "date": {"$in": dates_in_range}, "deleted": False},
        {"_id": 0},
    ).to_list(5000)

    # Index attendance (anos finais vs iniciais)
    att_by_date_aula: dict = {}
    att_by_date_only: dict = {}
    for att in attendances:
        aula = att.get("aula_numero")
        if aula is None:
            att_by_date_only.setdefault(att["date"], []).append(att)
        else:
            att_by_date_aula.setdefault((att["date"], aula), []).append(att)

    # Index content por chave completa
    ce_index: dict = {}
    for ce in content_entries:
        key = (ce["date"], ce.get("component_id"), ce.get("aula_numero"), ce.get("teacher_id"))
        existing = ce_index.get(key)
        if (not existing) or (ce.get("version", 0) > existing.get("version", 0)):
            ce_index[key] = ce

    used_attendance_ids: set = set()
    used_content_ids: set = set()
    all_user_ids: set = set()

    def _apply_attendance(entry, att):
        if att.get("validated_by"):
            entry["attendance_status"] = "validated"
        elif att.get("records"):
            entry["attendance_status"] = "completed"
        else:
            entry["attendance_status"] = "draft"
        entry["attendance_id"] = att["id"]
        entry["attendance_records"] = [_normalize_attendance_record(r) for r in att.get("records", [])]
        entry["attendance_created_by"] = att.get("created_by")
        entry["attendance_updated_by"] = att.get("updated_by")
        entry["validated_by"] = att.get("validated_by")
        entry["validated_at"] = att.get("validated_at")
        for u in (att.get("created_by"), att.get("updated_by"), att.get("validated_by")):
            if u:
                all_user_ids.add(u)

    def _apply_content(entry, ce):
        entry["content_status"] = ce.get("status", "draft")
        entry["content_entry_id"] = ce["id"]
        entry["content_text"] = ce.get("content")
        entry["content_methodology"] = ce.get("methodology")
        entry["content_observations"] = ce.get("observations")
        entry["version"] = ce.get("version")
        entry["content_created_by"] = ce.get("created_by")
        entry["published_by"] = ce.get("published_by")
        entry["published_at"] = ce.get("published_at")
        entry["corrected_by"] = ce.get("corrected_by")
        entry["corrected_at"] = ce.get("corrected_at")
        for u in (ce.get("created_by"), ce.get("published_by"), ce.get("corrected_by")):
            if u:
                all_user_ids.add(u)

    for iso, entries in expected_by_date.items():
        for e in entries:
            specific = att_by_date_aula.get((iso, e["aula_numero"]), [])
            if specific:
                att = next((a for a in specific if a["id"] not in used_attendance_ids), specific[0])
                used_attendance_ids.add(att["id"])
                _apply_attendance(e, att)
            else:
                day_atts = att_by_date_only.get(iso, [])
                if day_atts:
                    att = day_atts[0]
                    used_attendance_ids.add(att["id"])
                    _apply_attendance(e, att)
            ck = (iso, e["component_id"], e["aula_numero"], e["teacher_id"])
            ce = ce_index.get(ck)
            if ce:
                used_content_ids.add(ce["id"])
                _apply_content(e, ce)
            if e.get("teacher_id"):
                all_user_ids.add(e["teacher_id"])

    # Evidência órfã
    orphan_attendance_dates = sorted({a["date"] for a in attendances if a["id"] not in used_attendance_ids})
    orphan_content_dates = sorted({c["date"] for c in content_entries if c["id"] not in used_content_ids})

    # Resolve autores em batch (1 query)
    user_map = await _resolve_user_names(db, all_user_ids)

    # Para cada entry, anotar teacher_name resolvido (não confiar em snapshot do assignment)
    days: list = []
    summary = {
        "expected_slots": 0,
        "attendance_completed": 0,
        "attendance_validated": 0,
        "content_published": 0,
        "content_corrected": 0,
        "content_drafts": 0,
        "day_status_counts": {
            "not_expected": 0, "empty": 0, "partial": 0,
            "complete": 0, "corrected": 0, "inconsistent": 0,
        },
    }
    for day in _daterange(d_from, d_to):
        iso = day.isoformat()
        entries = expected_by_date.get(iso, [])
        entries.sort(key=lambda x: (x["aula_numero"] or 0, x.get("component_id") or ""))
        for e in entries:
            tid = e.get("teacher_id")
            if tid and tid in user_map:
                e["teacher_name"] = user_map[tid].get("full_name") or e.get("teacher_name")
        has_orphan_today = iso in orphan_attendance_dates or iso in orphan_content_dates
        day_status = _classify_day(entries, has_orphan_today)
        days.append({
            "date": iso,
            "weekday": day.isoweekday(),
            "status": day_status,
            "expected_slots": len(entries),
            "entries": entries,
            "has_orphan_evidence": has_orphan_today,
        })
        summary["day_status_counts"][day_status] = summary["day_status_counts"].get(day_status, 0) + 1
        summary["expected_slots"] += len(entries)
        for e in entries:
            if e["attendance_status"] == "completed":
                summary["attendance_completed"] += 1
            elif e["attendance_status"] == "validated":
                summary["attendance_validated"] += 1
            if e["content_status"] == "published":
                summary["content_published"] += 1
            elif e["content_status"] == "corrected":
                summary["content_corrected"] += 1
            elif e["content_status"] == "draft":
                summary["content_drafts"] += 1

    # ----- Authors registry (multi-autoria preservada — diretriz 2) -------
    contribution_kinds: dict[str, set] = {}
    for d in days:
        for e in d["entries"]:
            for kind, key in (
                ("attendance", "attendance_created_by"),
                ("content_creation", "content_created_by"),
                ("content_publication", "published_by"),
                ("content_correction", "corrected_by"),
                ("validation", "validated_by"),
                ("teaching_assignment", "teacher_id"),
            ):
                u = e.get(key)
                if u:
                    contribution_kinds.setdefault(u, set()).add(kind)

    authors_registry = []
    for uid, kinds in contribution_kinds.items():
        info = user_map.get(uid, {})
        authors_registry.append({
            "user_id": uid,
            "full_name": info.get("full_name") or "—",
            "role": info.get("role"),
            "contribution_types": sorted(kinds),
        })
    authors_registry.sort(key=lambda a: a["full_name"])

    return {
        "class": {
            "id": klass.get("id"),
            "name": klass.get("name"),
            "grade_level": klass.get("grade_level"),
            "education_level": klass.get("education_level"),
            "shift": klass.get("shift"),
            "academic_year": klass.get("academic_year"),
        },
        "summary": summary,
        "days": days,
        "authors_registry": authors_registry,
        "orphan_evidence": {
            "attendance_dates": orphan_attendance_dates,
            "content_dates": orphan_content_dates,
        },
    }


# ============================================================================
# IDEMPOTÊNCIA / CRIAÇÃO DE SNAPSHOT
# ============================================================================
async def find_active_snapshot(
    db, *, class_id: str, period_from: str, period_to: str
) -> Optional[dict]:
    """Retorna snapshot existente em draft|published — ou None.

    Regra (diretriz 8 do owner): só permite NOVO snapshot quando o anterior
    estiver `superseded` ou `revoked`. Bloqueia 12 versões do mesmo período.
    """
    return await db.diary_snapshots.find_one(
        {
            "class_id": class_id,
            "period.from": period_from,
            "period.to": period_to,
            "status": {"$in": list(ACTIVE_STATUSES)},
        },
        {"_id": 0},
    )


async def create_draft_snapshot(
    db,
    *,
    class_id: str,
    period_type: str,
    period_from: str,
    period_to: str,
    period_label: Optional[str],
    user: dict,
) -> dict:
    """Cria um novo snapshot em `draft`. Idempotente (retorna existente)."""
    if period_type not in VALID_PERIOD_TYPES:
        raise ValueError(f"period_type inválido: {period_type}")

    existing = await find_active_snapshot(
        db, class_id=class_id, period_from=period_from, period_to=period_to
    )
    if existing:
        existing["_idempotent_hit"] = True
        return existing

    payload = await consolidate_diary_payload(
        db, class_id=class_id, period_from=period_from, period_to=period_to
    )
    klass = payload["class"]
    branding = await _resolve_branding(
        db,
        mantenedora_id=user.get("mantenedora_id") or user.get("active_mantenedora_id"),
        school_id=None or (
            await db.classes.find_one({"id": class_id}, {"_id": 0, "school_id": 1})
        ).get("school_id"),
    )
    school_doc = await db.classes.find_one({"id": class_id}, {"_id": 0, "school_id": 1, "mantenedora_id": 1})
    snapshot = {
        "id": str(uuid.uuid4()),
        "code": _gen_code(),
        "schema_version": SCHEMA_VERSION,
        "semantic_rules_version": SEMANTIC_RULES_VERSION,
        "template_version": TEMPLATE_VERSION,
        "render_engine_version": RENDER_ENGINE_VERSION,
        "document_type": DOCUMENT_TYPE,
        "class_id": class_id,
        "school_id": (school_doc or {}).get("school_id"),
        "mantenedora_id": (school_doc or {}).get("mantenedora_id") or user.get("mantenedora_id"),
        "period": {
            "type": period_type,
            "from": period_from,
            "to": period_to,
            "label": period_label or f"{period_from} → {period_to}",
            "academic_year": klass.get("academic_year"),
        },
        "branding": branding,
        "payload": payload,
        "payload_hash_sha256": None,         # gerado no publish
        # verification_token: AUSENTE (não None) — só inserido no publish
        # para não colidir no unique sparse index quando vários drafts coexistem.
        "renders": [],                        # diretriz 5: array, não singular
        "status": "draft",
        "superseded_by_snapshot_id": None,
        "revoked_at": None,
        "revoked_reason": None,
        "revoked_by_user_id": None,
        "signatures": [],                     # diretriz 7: append-only
        "issued_at": None,                    # preenchido no publish
        "issued_by_user_id": None,
        "created_at": _now_iso(),
        "created_by_user_id": user.get("id"),
        "audit_trail": [
            {"action": "created_draft", "at": _now_iso(), "by": user.get("id")}
        ],
    }
    await db.diary_snapshots.insert_one(snapshot.copy())
    snapshot.pop("_id", None)
    return snapshot


# ============================================================================
# PUBLISH / SUPERSEDE / REVOKE / SIGN
# ============================================================================
async def publish_snapshot(db, *, snapshot_id: str, user: dict) -> dict:
    snap = await db.diary_snapshots.find_one({"id": snapshot_id}, {"_id": 0})
    if not snap:
        raise LookupError("SNAPSHOT_NOT_FOUND")
    if snap["status"] != "draft":
        raise ValueError(f"INVALID_TRANSITION: status atual {snap['status']}")

    # Hash calculado UMA VEZ — diretriz 3.
    doc_hash = compute_document_hash(snap)
    token = _gen_verification_token()
    now = _now_iso()

    await db.diary_snapshots.update_one(
        {"id": snapshot_id, "status": "draft"},
        {
            "$set": {
                "status": "published",
                "payload_hash_sha256": doc_hash,
                "verification_token": token,
                "issued_at": now,
                "issued_by_user_id": user.get("id"),
            },
            "$push": {
                "audit_trail": {
                    "action": "published", "at": now, "by": user.get("id"),
                    "payload_hash_sha256": doc_hash,
                },
            },
        },
    )
    return await db.diary_snapshots.find_one({"id": snapshot_id}, {"_id": 0})


async def supersede_snapshot(db, *, snapshot_id: str, new_snapshot_id: str, rationale: str, user: dict) -> dict:
    if not rationale or len(rationale.strip()) < 30:
        raise ValueError("RATIONALE_TOO_SHORT: mínimo 30 chars")
    if snapshot_id == new_snapshot_id:
        raise ValueError("SAME_DOCUMENT: supersede aponta para si mesmo")
    old = await db.diary_snapshots.find_one({"id": snapshot_id}, {"_id": 0})
    if not old:
        raise LookupError("SNAPSHOT_NOT_FOUND")
    new = await db.diary_snapshots.find_one({"id": new_snapshot_id}, {"_id": 0})
    if not new:
        raise LookupError("NEW_SNAPSHOT_NOT_FOUND")
    if old["status"] not in ACTIVE_STATUSES:
        raise ValueError(f"INVALID_TRANSITION: status {old['status']}")
    now = _now_iso()
    await db.diary_snapshots.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "status": "superseded",
                "superseded_by_snapshot_id": new_snapshot_id,
            },
            "$push": {
                "audit_trail": {
                    "action": "superseded", "at": now, "by": user.get("id"),
                    "by_snapshot_id": new_snapshot_id, "rationale": rationale[:512],
                },
            },
        },
    )
    return await db.diary_snapshots.find_one({"id": snapshot_id}, {"_id": 0})


async def revoke_snapshot(db, *, snapshot_id: str, rationale: str, user: dict) -> dict:
    if not rationale or len(rationale.strip()) < 30:
        raise ValueError("RATIONALE_TOO_SHORT: mínimo 30 chars")
    snap = await db.diary_snapshots.find_one({"id": snapshot_id}, {"_id": 0})
    if not snap:
        raise LookupError("SNAPSHOT_NOT_FOUND")
    if snap["status"] == "revoked":
        return snap
    now = _now_iso()
    await db.diary_snapshots.update_one(
        {"id": snapshot_id},
        {
            "$set": {
                "status": "revoked",
                "revoked_at": now,
                "revoked_reason": rationale,
                "revoked_by_user_id": user.get("id"),
                # HASH PRESERVADO — não muda. Diretriz 3.
            },
            "$push": {
                "audit_trail": {
                    "action": "revoked", "at": now, "by": user.get("id"),
                    "rationale": rationale[:512],
                },
            },
        },
    )
    return await db.diary_snapshots.find_one({"id": snapshot_id}, {"_id": 0})


async def add_signature(db, *, snapshot_id: str, role: str, full_name: str, user: dict) -> dict:
    """Append-only — diretriz 7. Nunca delete; usar revoked_signature_at se necessário no futuro."""
    snap = await db.diary_snapshots.find_one({"id": snapshot_id}, {"_id": 0})
    if not snap:
        raise LookupError("SNAPSHOT_NOT_FOUND")
    if snap["status"] not in ("published",):
        raise ValueError("CANNOT_SIGN: snapshot precisa estar published")
    # Anti-duplicidade por (role, user_id)
    for s in snap.get("signatures", []):
        if s.get("role") == role and s.get("signed_by_user_id") == user.get("id"):
            raise ValueError("ROLE_ALREADY_SIGNED")
    now = _now_iso()
    signature = {
        "id": str(uuid.uuid4()),
        "role": role,
        "full_name": full_name,
        "signed_by_user_id": user.get("id"),
        "signed_at": now,
        "signed_document_hash": snap.get("payload_hash_sha256"),
        "revoked_signature_at": None,         # diretriz 7
        "revoked_signature_reason": None,
    }
    await db.diary_snapshots.update_one(
        {"id": snapshot_id},
        {
            "$push": {
                "signatures": signature,
                "audit_trail": {
                    "action": "signed", "at": now, "by": user.get("id"),
                    "role": role, "signature_id": signature["id"],
                },
            },
        },
    )
    return await db.diary_snapshots.find_one({"id": snapshot_id}, {"_id": 0})


# ============================================================================
# RENDERS ARRAY — registra cada PDF gerado (diretriz 6)
# ============================================================================
async def append_render(
    db, *, snapshot_id: str,
    render_id: str,
    template_version: str,
    render_engine_version: str,
    generated_file_id: Optional[str],
    checksum_sha256: Optional[str],
    generated_by_user_id: Optional[str],
) -> None:
    now = _now_iso()
    record = {
        "render_id": render_id,
        "template_version": template_version,
        "render_engine_version": render_engine_version,
        "generated_file_id": generated_file_id,
        "checksum_sha256": checksum_sha256,
        "generated_at": now,
        "generated_by": generated_by_user_id,
    }
    await db.diary_snapshots.update_one(
        {"id": snapshot_id},
        {
            "$push": {
                "renders": record,
                "audit_trail": {"action": "render_appended", "at": now, "render_id": render_id},
            },
        },
    )


# ============================================================================
# INDEXES
# ============================================================================
async def ensure_indexes(db) -> None:
    await db.diary_snapshots.create_index("id", unique=True, background=True)
    await db.diary_snapshots.create_index("code", unique=True, background=True)
    await db.diary_snapshots.create_index("verification_token", unique=True, sparse=True, background=True)
    await db.diary_snapshots.create_index(
        [("class_id", 1), ("period.from", 1), ("period.to", 1), ("status", 1)],
        background=True,
    )
    await db.diary_snapshots.create_index([("school_id", 1), ("created_at", -1)], background=True)
    await db.diary_snapshots.create_index("mantenedora_id", background=True)
