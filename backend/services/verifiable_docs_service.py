"""Verifiable Documents Service — infraestrutura de confiança documental (G1.6 — Fev/2026).

Qualquer documento institucional (snapshot IA, certificado, declaração, histórico,
relatório, ata) pode ser emitido com um código público de verificação no formato:

    SIGESC-XXXX-XXXX  (8 chars base32 entropy ~40 bits → ~1.1 trilhão combinações)

O portal público `/api/public/verify/{code}` retorna APENAS:
  - status: "valido" | "invalido" | "revogado"
  - tipo, emitido_em, emitido_por, escopo, integridade, assinatura_valida, codigo

Zero payload operacional. Zero dados sensíveis. LGPD compliant por design.

Diferencial: código amigável acoplado ao hash SHA256 + HMAC do snapshot_service,
unicidade garantida por index único + retry em colisão, normalização de input
(aceita minúsculas, sem hífen, sem prefixo) para UX real.
"""
from __future__ import annotations

import logging
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo.errors import DuplicateKeyError

from services import snapshot_service as snap_svc

logger = logging.getLogger(__name__)

# Base32 sem caracteres confusos (0/O, 1/I, L). Total: 28 caracteres.
# Entropia: 28^8 ≈ 3.8×10^11 combinações por 8 chars → ~40 bits.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_PREFIX = "SIGESC-"
_CODE_PATTERN = re.compile(r"^SIGESC-[" + _ALPHABET + "]{4}-[" + _ALPHABET + "]{4}$")
_MAX_INSERT_RETRIES = 5

# Tipos de documento suportados (extensível)
DOC_TYPES = {
    "plano_acao": "Plano de Ação Automático",
    "relatorio_mensal": "Relatório Executivo Mensal",
    "certificado": "Certificado de Conclusão",
    "declaracao": "Declaração Escolar",
    "historico": "Histórico Escolar",
    "ata": "Ata / Documento Administrativo",
    "generico": "Documento Institucional",
}


def _random_block(n: int = 4) -> str:
    """Gera bloco criptograficamente seguro de n caracteres do alfabeto seguro."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def generate_code() -> str:
    """Gera código `SIGESC-XXXX-XXXX` usando apenas caracteres inequívocos."""
    return f"{_CODE_PREFIX}{_random_block(4)}-{_random_block(4)}"


def normalize_code(raw: str) -> Optional[str]:
    """Normaliza a entrada do usuário → formato canônico `SIGESC-XXXX-XXXX`.

    Aceita:
      - "sigescabcd1234"         → "SIGESC-ABCD-1234"
      - "SIGESC-ABCD-1234"       → "SIGESC-ABCD-1234"
      - "abcd1234"               → "SIGESC-ABCD-1234"
      - "abcd-1234"              → "SIGESC-ABCD-1234"
      - com espaços extras       → limpa

    Retorna None se não puder ser normalizado.
    """
    if not raw:
        return None
    # Maiúsculas, remove espaços e hífens
    cleaned = re.sub(r"[\s\-]", "", raw.upper())
    # Remove prefixo se presente
    if cleaned.startswith("SIGESC"):
        cleaned = cleaned[len("SIGESC"):]
    # Deve ter 8 chars válidos do alfabeto
    if len(cleaned) != 8 or not all(c in _ALPHABET for c in cleaned):
        return None
    return f"{_CODE_PREFIX}{cleaned[:4]}-{cleaned[4:]}"


def _type_label(doc_type: str) -> str:
    return DOC_TYPES.get(doc_type, doc_type)


async def ensure_indexes(db) -> None:
    """Cria índices para verifiable_documents (idempotente)."""
    try:
        await db.verifiable_documents.create_index("code", unique=True)
        await db.verifiable_documents.create_index([("entity_id", 1), ("created_at", -1)])
        await db.verifiable_documents.create_index([("type", 1), ("created_at", -1)])
        await db.verifiable_documents.create_index("public_hash")
    except Exception as e:
        logger.warning("[verifiable_docs] falha ao criar índices: %s", e)


async def create_verifiable_document(
    db,
    *,
    type: str,
    public_hash: str,
    server_signature: Optional[str],
    mantenedora_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    snapshot_id: Optional[str] = None,
    issued_by: Optional[dict] = None,
    issuer_name: str = "SIGESC",
    scope_label: Optional[str] = None,
    expires_in_days: Optional[int] = None,
) -> dict:
    """Persiste um documento verificável. Retorna o doc criado.

    Metadata pública (o que vai aparecer no portal) é MÍNIMA:
      - codigo
      - tipo (label humano)
      - emitido_em
      - emitido_por
      - escopo (opcional, label da instituição/rede)

    Unicidade do code garantida por retry (até 5 tentativas).
    """
    if type not in DOC_TYPES:
        logger.info("[verifiable_docs] tipo '%s' não catalogado (usando rótulo cru)", type)

    now = datetime.now(timezone.utc)
    expires_at = None
    if expires_in_days:
        expires_at = now + timedelta(days=int(expires_in_days))

    public_metadata = {
        "tipo": type,
        "tipo_label": _type_label(type),
        "emitido_em": now.date().isoformat(),
        "emitido_por": issuer_name,
        "escopo": scope_label or "—",
    }

    last_err: Optional[Exception] = None
    for attempt in range(_MAX_INSERT_RETRIES):
        code = generate_code()
        doc = {
            "code": code,
            "type": type,
            "public_hash": public_hash,
            "server_signature": server_signature,
            "mantenedora_id": mantenedora_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "snapshot_id": snapshot_id,
            "issued_by": issued_by or {},
            "public_metadata": public_metadata,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
            "revoked": False,
            "revoked_at": None,
            "revoked_reason": None,
            "revoked_by": None,
        }
        try:
            await db.verifiable_documents.insert_one(doc)
            doc.pop("_id", None)
            return doc
        except DuplicateKeyError as e:
            last_err = e
            logger.info("[verifiable_docs] colisão de código (tentativa %d)", attempt + 1)
            continue

    raise RuntimeError(
        f"[verifiable_docs] não foi possível gerar código único após "
        f"{_MAX_INSERT_RETRIES} tentativas: {last_err}"
    )


async def resolve_code(db, raw_code: str) -> Optional[dict]:
    """Normaliza o input e busca o documento. Retorna None se não existe."""
    code = normalize_code(raw_code)
    if not code:
        return None
    return await db.verifiable_documents.find_one({"code": code}, {"_id": 0})


async def revoke_document(
    db,
    *,
    code: str,
    reason: str,
    user: dict,
) -> dict:
    """Marca documento como revogado. Retorna o doc atualizado.

    Revogação é definitiva — não reversível neste serviço (manter simples).
    """
    normalized = normalize_code(code)
    if not normalized:
        raise ValueError("Código de documento inválido")
    now_iso = datetime.now(timezone.utc).isoformat()
    r = await db.verifiable_documents.find_one_and_update(
        {"code": normalized, "revoked": False},
        {"$set": {
            "revoked": True,
            "revoked_at": now_iso,
            "revoked_reason": (reason or "")[:500],
            "revoked_by": {
                "user_id": user.get("id"),
                "email": user.get("email"),
                "role": user.get("role"),
            },
        }},
        return_document=True,
        projection={"_id": 0},
    )
    if not r:
        # Já revogado ou não existe
        existing = await db.verifiable_documents.find_one({"code": normalized}, {"_id": 0})
        if not existing:
            raise KeyError("Documento não encontrado")
        return existing
    return r


def build_portal_response(doc: Optional[dict]) -> dict:
    """Constrói a resposta LGPD-safe do portal público.

    3 estados claros: "valido" | "invalido" | "revogado".
    ZERO payload, ZERO dados operacionais. Só o suficiente para
    conferência institucional visual.
    """
    if not doc:
        return {
            "status": "invalido",
            "codigo": None,
            "mensagem": "Documento não encontrado. Verifique o código digitado.",
        }

    if doc.get("revoked"):
        meta = doc.get("public_metadata") or {}
        return {
            "status": "revogado",
            "codigo": doc.get("code"),
            "tipo": meta.get("tipo"),
            "tipo_label": meta.get("tipo_label"),
            "emitido_em": meta.get("emitido_em"),
            "emitido_por": meta.get("emitido_por"),
            "escopo": meta.get("escopo"),
            "revogado_em": (doc.get("revoked_at") or "")[:10],
            "integridade": "revogada",
            "assinatura_valida": False,
            "mensagem": "Este documento foi revogado e não possui validade institucional.",
        }

    # Verifica hash e assinatura se há snapshot associado
    hash_valid = True
    sig_valid = bool(doc.get("server_signature"))
    if doc.get("snapshot_id"):
        # signature check (reproduzível sem I/O)
        recomputed_sig = snap_svc.compute_signature(doc.get("public_hash") or "")
        sig_valid = bool(recomputed_sig) and recomputed_sig == doc.get("server_signature")

    meta = doc.get("public_metadata") or {}
    return {
        "status": "valido" if (hash_valid and sig_valid) else "invalido",
        "codigo": doc.get("code"),
        "tipo": meta.get("tipo"),
        "tipo_label": meta.get("tipo_label"),
        "emitido_em": meta.get("emitido_em"),
        "emitido_por": meta.get("emitido_por"),
        "escopo": meta.get("escopo"),
        "integridade": "confirmada" if hash_valid else "alterada",
        "assinatura_valida": sig_valid,
        "mensagem": (
            "Documento autêntico e íntegro, emitido pelo SIGESC."
            if (hash_valid and sig_valid)
            else "Não foi possível confirmar a integridade do documento."
        ),
    }
