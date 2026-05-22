"""
Endpoint público de verificação institucional (Fase 5b — Mai/2026).

`GET /verify/diary/{token}` — SEM autenticação.

Política LGPD aprovada pelo owner (1c):
  Exposto:
    code, status, school_name, class_name, period, issued_at,
    payload_hash_sha256, signatures[role, full_name, signed_at,
    signature_type, status]
  Bloqueado (NUNCA expor):
    alunos, frequência, conteúdo, observações pedagógicas,
    authors_registry, user_ids, emails, audit_trail, validation_history,
    file_ids internos, rationale de revoke/supersede.

Rate-limit aprovado (2b):
  60 req/min por IP + bloqueio temporário 5 min se 404 > 10/min
  (anti-enumeração de tokens).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Optional

from fastapi import APIRouter, HTTPException, Request


# ============================================================================
# Rate-limit in-process (suficiente para 1 instância; trocar por Redis depois)
# ============================================================================
_LOCK = Lock()
_HITS: dict[str, deque] = defaultdict(deque)           # ip → timestamps (req)
_NOT_FOUND_HITS: dict[str, deque] = defaultdict(deque)  # ip → timestamps (404)
_BLOCKED: dict[str, float] = {}                         # ip → unblock_at_ts

WINDOW_SECONDS = 60
MAX_REQ_PER_MIN = 60
MAX_404_PER_MIN = 10
BLOCK_DURATION_SECONDS = 300  # 5 min


def _client_ip(request: Request) -> str:
    # Honra X-Forwarded-For atrás de proxy (Kubernetes ingress / CDN)
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return (request.client.host if request.client else "0.0.0.0") or "0.0.0.0"


def _check_rate_limit(ip: str) -> None:
    """Verifica e atualiza contadores; raises HTTPException(429) se bloqueado."""
    now = time.time()
    with _LOCK:
        # Limpa bloqueio expirado
        if ip in _BLOCKED and _BLOCKED[ip] <= now:
            del _BLOCKED[ip]
        if ip in _BLOCKED:
            retry = int(_BLOCKED[ip] - now)
            raise HTTPException(
                status_code=429,
                detail={"code": "RATE_LIMIT_BLOCKED",
                        "message": f"Tente novamente em {retry}s."},
                headers={"Retry-After": str(retry)},
            )
        # Janela deslizante de 60s
        dq = _HITS[ip]
        while dq and dq[0] <= now - WINDOW_SECONDS:
            dq.popleft()
        if len(dq) >= MAX_REQ_PER_MIN:
            raise HTTPException(
                status_code=429,
                detail={"code": "RATE_LIMIT",
                        "message": "Limite de requisições por minuto excedido."},
                headers={"Retry-After": "60"},
            )
        dq.append(now)


def _record_not_found(ip: str) -> None:
    """Conta 404 do IP. Se > MAX_404_PER_MIN em 60s → bloqueia."""
    now = time.time()
    with _LOCK:
        dq = _NOT_FOUND_HITS[ip]
        while dq and dq[0] <= now - WINDOW_SECONDS:
            dq.popleft()
        dq.append(now)
        if len(dq) > MAX_404_PER_MIN:
            _BLOCKED[ip] = now + BLOCK_DURATION_SECONDS


# ============================================================================
# Sanitização LGPD (1c)
# ============================================================================
def _sanitize_signature(sig: dict) -> dict:
    return {
        "role": sig.get("role"),
        "full_name": sig.get("full_name"),
        "signed_at": sig.get("signed_at"),
        "signature_type": sig.get("signature_type", "manual"),
        "status": sig.get("status", "active"),
    }


def _sanitize_snapshot(snap: dict) -> dict:
    """Aplica política LGPD-1c: expõe APENAS verificação institucional.

    NÃO expõe: payload (alunos/frequência/conteúdo/autores), audit_trail,
    user_ids, file_ids, rationale, validation_history.
    """
    return {
        "code": snap.get("code"),
        "status": snap.get("status"),
        "school_name": (snap.get("branding") or {}).get("school_name"),
        "mantenedora_name": (snap.get("branding") or {}).get("mantenedora_name"),
        "class_name": ((snap.get("payload") or {}).get("class") or {}).get("name"),
        "period": {
            "from": (snap.get("period") or {}).get("from"),
            "to": (snap.get("period") or {}).get("to"),
            "label": (snap.get("period") or {}).get("label"),
        },
        "issued_at": snap.get("issued_at"),
        "payload_hash_sha256": snap.get("payload_hash_sha256"),
        "schema_version": snap.get("schema_version"),
        "semantic_rules_version": snap.get("semantic_rules_version"),
        "signatures": [_sanitize_signature(s) for s in (snap.get("signatures") or [])],
    }


# ============================================================================
# Router
# ============================================================================
def setup_public_verify_router(db):
    """Roteador SEM AUTH. Será exposto em /verify (sem prefixo /api)."""
    router = APIRouter(tags=["Verificação Pública"])

    @router.get("/verify/diary/{verification_token}")
    async def verify_diary(verification_token: str, request: Request):
        ip = _client_ip(request)
        _check_rate_limit(ip)

        # Tamanho mínimo válido (token = 32 hex chars). Bloqueia probes baratos.
        if not verification_token or len(verification_token) < 16:
            _record_not_found(ip)
            raise HTTPException(status_code=404, detail="Documento não encontrado.")

        snap = await db.diary_snapshots.find_one(
            {"verification_token": verification_token},
            {"_id": 0},
        )
        if not snap:
            _record_not_found(ip)
            raise HTTPException(
                status_code=404,
                detail="Documento não encontrado ou ainda não publicado.",
            )
        return _sanitize_snapshot(snap)

    return router
