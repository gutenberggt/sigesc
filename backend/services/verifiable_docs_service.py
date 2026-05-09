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
import uuid
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

# Schema version dos verifiable_documents — bump em mudanças quebradoras.
SCHEMA_VERSION = "1"

# verification_token: UUID hex opaco (32 chars). Distinto do código humano.
_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")


def generate_verification_token() -> str:
    """Gera token opaco UUID-hex (32 chars). Usado em URL curta `/v/{token}`.

    Distinto do `code` humano (`SIGESC-XXXX-XXXX`) — token é o que vai no QR.
    """
    return uuid.uuid4().hex


def is_token_format(s: str) -> bool:
    """Heurística: identifier parece um verification_token (32 hex)?"""
    if not s:
        return False
    return bool(_TOKEN_RE.match(s.lower().strip()))

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
        await db.verifiable_documents.create_index(
            "verification_token", unique=True, sparse=True, background=True,
        )
        await db.verifiable_documents.create_index([("entity_id", 1), ("created_at", -1)])
        await db.verifiable_documents.create_index([("type", 1), ("created_at", -1)])
        await db.verifiable_documents.create_index("public_hash")
        await db.verifiable_documents.create_index("student_id", sparse=True)
        await db.verifiable_documents.create_index("school_id", sparse=True)
    except Exception as e:
        logger.warning("[verifiable_docs] falha ao criar índices: %s", e)


async def backfill_verification_tokens(db) -> int:
    """Preenche `verification_token` para documentos antigos sem ele.

    Idempotente: roda ao startup e em hot-reloads. Retorna a contagem
    de documentos atualizados.
    """
    updated = 0
    cursor = db.verifiable_documents.find(
        {"$or": [{"verification_token": {"$exists": False}},
                 {"verification_token": None}]},
        {"_id": 1, "code": 1},
    )
    async for d in cursor:
        token = generate_verification_token()
        try:
            await db.verifiable_documents.update_one(
                {"_id": d["_id"]},
                {"$set": {"verification_token": token,
                          "schema_version": SCHEMA_VERSION}},
            )
            updated += 1
        except DuplicateKeyError:
            # colisão extremamente improvável — tenta de novo uma vez
            await db.verifiable_documents.update_one(
                {"_id": d["_id"]},
                {"$set": {"verification_token": generate_verification_token(),
                          "schema_version": SCHEMA_VERSION}},
            )
            updated += 1
    if updated:
        logger.info("[verifiable_docs] backfill: %d documentos receberam verification_token", updated)
    return updated


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
    student_id: Optional[str] = None,
    school_id: Optional[str] = None,
    template_version: Optional[str] = None,
    render_job_id: Optional[str] = None,
    file_id: Optional[str] = None,
) -> dict:
    """Persiste um documento verificável. Retorna o doc criado.

    Cada documento recebe:
      - `code` humano `SIGESC-XXXX-XXXX` (URLs/comunicação manual)
      - `verification_token` UUID opaco de 32 chars (URL curta `/v/{token}`,
        carregada no QR)
      - `signatures: []` (vazio na emissão; assinaturas adicionadas via
        `add_signature`)
      - `superseded_by_document_id: None` (substituições posteriores via
        `supersede_document`)

    Metadata pública (o que vai aparecer no portal) é MÍNIMA:
      - codigo, tipo (label humano), emitido_em, emitido_por, escopo (opcional).

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
        token = generate_verification_token()
        doc = {
            "code": code,
            "verification_token": token,
            "schema_version": SCHEMA_VERSION,
            "template_version": template_version,
            "type": type,
            "document_type": type,  # alias canônico (contrato Verifiable Documents MVP)
            "public_hash": public_hash,
            "server_signature": server_signature,
            "mantenedora_id": mantenedora_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "student_id": student_id,
            "school_id": school_id,
            "snapshot_id": snapshot_id,
            "render_job_id": render_job_id,
            "file_id": file_id,
            "issued_by": issued_by or {},
            "public_metadata": public_metadata,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
            "revoked": False,
            "revoked_at": None,
            "revoked_reason": None,
            "revoked_by": None,
            "signatures": [],
            "superseded_by_document_id": None,
            "superseded_at": None,
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


async def resolve_token(db, token: str) -> Optional[dict]:
    """Busca doc pelo `verification_token` opaco (UUID-hex 32 chars)."""
    if not token:
        return None
    cleaned = token.lower().strip()
    if not _TOKEN_RE.match(cleaned):
        return None
    return await db.verifiable_documents.find_one(
        {"verification_token": cleaned}, {"_id": 0}
    )


async def resolve_either(db, identifier: str) -> Optional[dict]:
    """Resolve identifier — tenta como `verification_token` primeiro
    (UUID-hex 32 chars), depois como `code` humano `SIGESC-XXXX-XXXX`.

    Endpoint público canônico aceita ambos transparentemente.
    """
    if is_token_format(identifier):
        doc = await resolve_token(db, identifier)
        if doc:
            return doc
    return await resolve_code(db, identifier)


async def add_signature(
    db,
    *,
    code_or_token: str,
    role: str,
    full_name: str,
    signed_by_user_id: Optional[str] = None,
    signed_at: Optional[str] = None,
) -> dict:
    """Adiciona uma assinatura institucional ao documento.

    NÃO altera o `document_hash_sha256` (o hash é congelado na emissão).
    Cada assinatura é registrada em `signatures: []` com role/full_name/signed_at.
    """
    doc = await resolve_either(db, code_or_token)
    if not doc:
        raise KeyError("Documento não encontrado")
    if doc.get("revoked"):
        raise ValueError("Documento revogado — não aceita novas assinaturas")
    sig = {
        "role": (role or "").strip()[:60],
        "full_name": (full_name or "").strip()[:120],
        "signed_at": signed_at or datetime.now(timezone.utc).isoformat(),
        "signed_by_user_id": signed_by_user_id,
    }
    if not sig["role"] or not sig["full_name"]:
        raise ValueError("role e full_name são obrigatórios")
    r = await db.verifiable_documents.find_one_and_update(
        {"code": doc["code"]},
        {"$push": {"signatures": sig}},
        return_document=True,
        projection={"_id": 0},
    )
    return r


async def supersede_document(
    db,
    *,
    old_code_or_token: str,
    new_code_or_token: str,
    user: dict,
) -> dict:
    """Marca `old` como substituído por `new`.

    Old fica com:
        document_status='superseded' (na visão pública),
        superseded_by_document_id = new_code,
        superseded_at = now.

    Não revoga old (revogação é estado distinto). Documento substituído
    permanece consultável publicamente como histórico.
    """
    old = await resolve_either(db, old_code_or_token)
    new = await resolve_either(db, new_code_or_token)
    if not old:
        raise KeyError("Documento original não encontrado")
    if not new:
        raise KeyError("Novo documento não encontrado")
    if old["code"] == new["code"]:
        raise ValueError("Documentos novos e antigos são iguais")
    now_iso = datetime.now(timezone.utc).isoformat()
    r = await db.verifiable_documents.find_one_and_update(
        {"code": old["code"]},
        {"$set": {
            "superseded_by_document_id": new["code"],
            "superseded_at": now_iso,
            "superseded_by_user_id": user.get("id") if user else None,
        }},
        return_document=True,
        projection={"_id": 0},
    )
    return r


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


def _public_signatures(doc: dict) -> list[dict]:
    """Retorna assinaturas em formato LGPD-safe.

    Apenas role + full_name + signed_at. Sem user_id, sem email, sem CPF.
    """
    out = []
    for sig in (doc.get("signatures") or []):
        out.append({
            "role": sig.get("role"),
            "full_name": sig.get("full_name"),
            "signed_at": (sig.get("signed_at") or "")[:19],
        })
    return out


def build_portal_response(doc: Optional[dict]) -> dict:
    """Constrói a resposta LGPD-safe do portal público.

    Estados claros: "valido" | "expirado" | "revogado" | "substituido" | "invalido".
    ZERO payload, ZERO dados operacionais.
    """
    if not doc:
        return {
            "status": "invalido",
            "codigo": None,
            "verification_token": None,
            "mensagem": "Documento não encontrado. Verifique o código digitado.",
        }

    base = {
        "codigo": doc.get("code"),
        "verification_token": doc.get("verification_token"),
        "schema_version": doc.get("schema_version") or SCHEMA_VERSION,
        "document_type": doc.get("document_type") or doc.get("type"),
        "assinaturas": _public_signatures(doc),
    }

    # Estado: substituído (precede revogação na semântica — owner spec).
    if doc.get("superseded_by_document_id"):
        meta = doc.get("public_metadata") or {}
        return {
            **base,
            "status": "substituido",
            "tipo": meta.get("tipo"),
            "tipo_label": meta.get("tipo_label"),
            "emitido_em": meta.get("emitido_em"),
            "emitido_por": meta.get("emitido_por"),
            "escopo": meta.get("escopo"),
            "substituido_por": doc.get("superseded_by_document_id"),
            "substituido_em": (doc.get("superseded_at") or "")[:10],
            "integridade": "confirmada",
            "assinatura_valida": bool(doc.get("server_signature")),
            "mensagem": (
                "Este documento foi substituído por uma versão mais recente "
                "e não possui mais validade institucional."
            ),
        }

    if doc.get("revoked"):
        meta = doc.get("public_metadata") or {}
        return {
            **base,
            "status": "revogado",
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

    # Verifica expiração (escolar: validade limitada por tipo)
    expires_at = doc.get("expires_at")
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp_dt:
                meta = doc.get("public_metadata") or {}
                return {
                    **base,
                    "status": "expirado",
                    "tipo": meta.get("tipo"),
                    "tipo_label": meta.get("tipo_label"),
                    "emitido_em": meta.get("emitido_em"),
                    "emitido_por": meta.get("emitido_por"),
                    "escopo": meta.get("escopo"),
                    "valido_ate": exp_dt.date().isoformat(),
                    "integridade": "confirmada",
                    "assinatura_valida": bool(doc.get("server_signature")),
                    "mensagem": (
                        "Este documento perdeu a validade institucional. "
                        "Solicite uma nova emissão à secretaria da escola."
                    ),
                }
        except Exception:
            pass

    # Verifica hash e assinatura se há snapshot associado
    hash_valid = True
    sig_valid = bool(doc.get("server_signature"))
    if doc.get("snapshot_id"):
        recomputed_sig = snap_svc.compute_signature(doc.get("public_hash") or "")
        sig_valid = bool(recomputed_sig) and recomputed_sig == doc.get("server_signature")

    meta = doc.get("public_metadata") or {}
    # expires_at convertido para exibição (pode não estar expirado ainda)
    valido_ate = None
    if expires_at:
        try:
            valido_ate = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            pass
    return {
        **base,
        "status": "valido" if (hash_valid and sig_valid) else "invalido",
        "tipo": meta.get("tipo"),
        "tipo_label": meta.get("tipo_label"),
        "emitido_em": meta.get("emitido_em"),
        "emitido_por": meta.get("emitido_por"),
        "escopo": meta.get("escopo"),
        "valido_ate": valido_ate,
        "integridade": "confirmada" if hash_valid else "alterada",
        "assinatura_valida": sig_valid,
        "mensagem": (
            "Documento autêntico e íntegro, emitido pelo SIGESC."
            if (hash_valid and sig_valid)
            else "Não foi possível confirmar a integridade do documento."
        ),
    }
