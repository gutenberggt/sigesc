"""
Auditoria de Segurança Multi-Tenant (permanente).

Registra APENAS eventos de divergência/risco de isolamento entre mantenedoras
— nunca tráfego normal. Mantém o log "inteligente" (pequeno e relevante):
  - missing_tenant        → usuário não-super_admin sem mantenedora_id
  - tenant_mismatch       → escopo solicitado difere do escopo do usuário
  - cross_tenant_attempt  → tentativa de acessar documento de outra mantenedora
  - invalid_token         → token com tipo inválido / malformado (não expiração normal)

Cada evento é (1) emitido no log da aplicação com o prefixo "TENANT_SECURITY" e
(2) persistido (best-effort, fire-and-forget) na coleção `tenant_security_events`
para auditoria durável — importante por se tratar de dados de menores em educação
pública.
"""
from __future__ import annotations

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request

logger = logging.getLogger("tenant.security")

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            _client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            _collection = _client[os.environ.get("DB_NAME", "sigesc_db")]["tenant_security_events"]
        except Exception:  # pragma: no cover - ambiente sem mongo
            _collection = None
    return _collection


async def _persist(doc: dict) -> None:
    try:
        col = _get_collection()
        if col is not None:
            await col.insert_one(doc)
    except Exception:  # pragma: no cover - auditoria nunca pode quebrar a request
        pass


def log_tenant_event(
    event: str,
    user: Optional[dict] = None,
    request: Optional[Request] = None,
    requested_mantenedora: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """Registra um evento de segurança de tenant (log + persistência best-effort)."""
    user = user or {}
    doc = {
        "event": event,
        "user_id": user.get("id"),
        "role": user.get("role"),
        "user_mantenedora": user.get("mantenedora_id"),
        "requested_mantenedora": requested_mantenedora,
        "endpoint": (request.url.path if request is not None and getattr(request, "url", None) else None),
        "method": (request.method if request is not None else None),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        doc.update(extra)

    try:
        logger.warning("TENANT_SECURITY %s", json.dumps(doc, ensure_ascii=False, default=str))
    except Exception:
        pass

    # Persistência durável best-effort (só funciona dentro de um event loop ativo,
    # que é o caso de qualquer endpoint FastAPI async).
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_persist(dict(doc)))
    except RuntimeError:
        pass
