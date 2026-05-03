"""Snapshot imutável + integridade (Sprint G1.5 — Fev/2026).

Transforma toda análise IA em documento auditável:
- payload_snapshot: dados congelados usados no momento da análise
- ai_output: resposta completa da IA (validada)
- public_hash: SHA256 canônico → permite verificação externa
- server_signature: HMAC-SHA256 com secret do servidor → prova de origem
- expires_at: TTL configurável por mantenedora (LGPD, default 5 anos)

O hash é computado sobre um JSON canônico (sorted keys, ensure_ascii=False)
de {payload_snapshot, ai_output, created_at, model, version, entity_id,
analysis_type}. Alterar QUALQUER desses campos invalida o hash.

HMAC impede forjar snapshots externamente — só o servidor que conhece
SNAPSHOT_HMAC_SECRET pode gerar uma signature válida.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 1
# Retenção padrão / limites (dias)
DEFAULT_RETENTION_DAYS = 5 * 365   # 5 anos
MIN_RETENTION_DAYS = 2 * 365       # 2 anos
# "forever" é representado por expires_at=None (sem TTL)

ALLOWED_RETENTION_MODES = ("default", "custom", "forever")


def _get_hmac_secret() -> Optional[bytes]:
    """Lê SNAPSHOT_HMAC_SECRET do env. Retorna None se ausente (signature skip)."""
    secret = os.environ.get("SNAPSHOT_HMAC_SECRET")
    if not secret:
        logger.warning("[snapshot] SNAPSHOT_HMAC_SECRET ausente — signature será vazia")
        return None
    return secret.encode("utf-8")


def canonical_json(data: Any) -> str:
    """Serialização canônica determinística para hashing.

    - sort_keys=True → ordem de chaves não afeta o hash
    - ensure_ascii=False → caracteres acentuados são preservados
    - separators sem espaço → bytes exatos
    - default=str → datetime/UUID viram strings ISO/repr
    """
    return json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def compute_public_hash(
    *,
    entity_type: str,
    entity_id: str,
    analysis_type: str,
    payload_snapshot: dict,
    ai_output: dict,
    created_at_iso: str,
    model: str,
    version: int = SNAPSHOT_VERSION,
) -> str:
    """SHA256 do JSON canônico. Formato: 'sha256:<hex>'."""
    canonical = canonical_json({
        "version": version,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "analysis_type": analysis_type,
        "model": model,
        "created_at": created_at_iso,
        "payload_snapshot": payload_snapshot,
        "ai_output": ai_output,
    })
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{h}"


def compute_signature(public_hash: str) -> Optional[str]:
    """HMAC-SHA256(server_secret, public_hash). Formato: 'hmac-sha256:<hex>'.

    Retorna None se SNAPSHOT_HMAC_SECRET não estiver definido.
    """
    secret = _get_hmac_secret()
    if not secret:
        return None
    digest = hmac.new(secret, public_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"


async def _get_retention_policy(db, mantenedora_id: Optional[str]) -> dict:
    """Lê a política de retenção da mantenedora (fallback default 5 anos).

    Shape: {mode: 'default'|'custom'|'forever', days: int|None}
    """
    if not mantenedora_id:
        return {"mode": "default", "days": DEFAULT_RETENTION_DAYS}
    doc = await db.snapshot_retention_policies.find_one(
        {"mantenedora_id": mantenedora_id}, {"_id": 0}
    )
    if not doc:
        return {"mode": "default", "days": DEFAULT_RETENTION_DAYS}
    mode = doc.get("mode") or "default"
    if mode == "forever":
        return {"mode": "forever", "days": None}
    days = doc.get("days") or DEFAULT_RETENTION_DAYS
    if days < MIN_RETENTION_DAYS:
        days = MIN_RETENTION_DAYS
    return {"mode": mode, "days": days}


async def set_retention_policy(
    db,
    *,
    mantenedora_id: str,
    mode: str,
    days: Optional[int] = None,
) -> dict:
    """Define política de retenção para uma mantenedora.

    Validações:
      - mode em ('default', 'custom', 'forever')
      - se 'custom': days obrigatório, >= MIN_RETENTION_DAYS
      - se 'forever': days é ignorado
    """
    if mode not in ALLOWED_RETENTION_MODES:
        raise ValueError(f"mode inválido: {mode}")
    if mode == "custom":
        if not days or days < MIN_RETENTION_DAYS:
            raise ValueError(f"days mínimo é {MIN_RETENTION_DAYS}")
    doc = {
        "mantenedora_id": mantenedora_id,
        "mode": mode,
        "days": days if mode == "custom" else (None if mode == "forever" else DEFAULT_RETENTION_DAYS),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.snapshot_retention_policies.update_one(
        {"mantenedora_id": mantenedora_id},
        {"$set": doc},
        upsert=True,
    )
    return doc


async def create_snapshot(
    db,
    *,
    mantenedora_id: Optional[str],
    entity_type: str,
    entity_id: str,
    analysis_type: str,
    payload_snapshot: dict,
    ai_output: dict,
    model: str,
    user: dict,
) -> dict:
    """Cria um snapshot imutável com hash + HMAC + expires_at.

    Retorna o documento completo persistido.
    """
    now = datetime.now(timezone.utc)
    created_at_iso = now.isoformat()

    public_hash = compute_public_hash(
        entity_type=entity_type,
        entity_id=entity_id,
        analysis_type=analysis_type,
        payload_snapshot=payload_snapshot,
        ai_output=ai_output,
        created_at_iso=created_at_iso,
        model=model,
    )
    signature = compute_signature(public_hash)

    policy = await _get_retention_policy(db, mantenedora_id)
    expires_at = None
    if policy["mode"] != "forever" and policy.get("days"):
        expires_at = (now + timedelta(days=policy["days"]))

    doc = {
        "id": str(uuid.uuid4()),
        "version": SNAPSHOT_VERSION,
        "mantenedora_id": mantenedora_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "analysis_type": analysis_type,
        "payload_snapshot": payload_snapshot,
        "ai_output": ai_output,
        "model": model,
        "public_hash": public_hash,
        "server_signature": signature,
        "created_at": created_at_iso,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "created_by": {
            "user_id": user.get("id"),
            "email": user.get("email"),
            "role": user.get("role"),
        },
        "retention_policy": policy,
    }
    # Armazenamos expires_at como datetime para permitir TTL index do Mongo
    doc_for_db = {**doc}
    if expires_at is not None:
        doc_for_db["expires_at_dt"] = expires_at
    await db.ai_analysis_snapshots.insert_one(doc_for_db)
    return doc


def verify_snapshot_integrity(doc: dict) -> dict:
    """Recalcula hash + HMAC do snapshot e retorna dict rico.

    Nunca levanta — sempre retorna estrutura para o caller interpretar.
    """
    try:
        recomputed = compute_public_hash(
            entity_type=doc["entity_type"],
            entity_id=doc["entity_id"],
            analysis_type=doc["analysis_type"],
            payload_snapshot=doc["payload_snapshot"],
            ai_output=doc["ai_output"],
            created_at_iso=doc["created_at"],
            model=doc["model"],
            version=doc.get("version", SNAPSHOT_VERSION),
        )
        stored_hash = doc.get("public_hash") or ""
        hash_valid = hmac.compare_digest(recomputed, stored_hash)

        stored_sig = doc.get("server_signature") or ""
        recomputed_sig = compute_signature(recomputed) or ""
        sig_valid = bool(stored_sig) and bool(recomputed_sig) and hmac.compare_digest(stored_sig, recomputed_sig)

        return {
            "valid": hash_valid and (sig_valid or not stored_sig),
            "hash_valid": hash_valid,
            "signature_valid": sig_valid,
            "signature_present": bool(stored_sig),
            "public_hash": stored_hash,
            "recomputed_hash": recomputed,
            "server_signature": stored_sig,
            "recomputed_signature": recomputed_sig,
            "created_at": doc.get("created_at"),
            "model": doc.get("model"),
            "version": doc.get("version"),
        }
    except Exception as e:
        logger.exception("[snapshot] verify falhou")
        return {
            "valid": False,
            "hash_valid": False,
            "signature_valid": False,
            "error": str(e),
        }


def get_scope_for_user(user: dict) -> dict:
    """Determina o escopo de snapshots que um usuário pode listar.

    Retorna dict com chaves opcionais: 'mantenedora_id', 'entity_ids'.
    Se retorna {} → acesso global.
    Se retorna None → usuário sem acesso.
    """
    role = user.get("role")
    if role in ("super_admin", "admin", "admin_teste", "gerente"):
        # gerente/admin escopo mantenedora
        if role in ("gerente", "admin", "admin_teste") and user.get("mantenedora_id"):
            return {"mantenedora_id": user["mantenedora_id"]}
        return {}  # super_admin global
    if role == "secretario":
        # rede (mantenedora inteira)
        if user.get("mantenedora_id"):
            return {"mantenedora_id": user["mantenedora_id"]}
        return {}
    if role == "diretor":
        # somente sua(s) escola(s)
        school_ids = user.get("school_ids") or []
        if not school_ids:
            return None
        scope = {"entity_ids": school_ids}
        if user.get("mantenedora_id"):
            scope["mantenedora_id"] = user["mantenedora_id"]
        return scope
    # Outros papéis (professor, aluno, coordenador, etc.) → sem acesso
    return None


async def ensure_ttl_index(db) -> None:
    """Cria TTL index para expiração automática (idempotente)."""
    try:
        await db.ai_analysis_snapshots.create_index(
            "expires_at_dt", expireAfterSeconds=0, sparse=True
        )
        await db.ai_analysis_snapshots.create_index([("entity_id", 1), ("created_at", -1)])
        await db.ai_analysis_snapshots.create_index("public_hash", unique=True)
    except Exception as e:
        logger.warning("[snapshot] falha ao criar índices: %s", e)
