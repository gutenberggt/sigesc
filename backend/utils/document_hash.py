"""
Hash documental canônico para snapshots imutáveis.

[Fev/2026] P1 — Snapshots imutáveis (Dependency Completions, Histórico, Boletim).

Princípios:
- `document_hash_sha256`: hash do conteúdo canônico — NUNCA recalculado após emissão.
- `signature_hash_sha256`: hash derivado por assinatura, referencia o doc original.
- Assinatura NÃO altera o documento. Documento NÃO conhece sua assinatura;
  a assinatura é que referencia o documento via `signed_document_hash`.

Sem essa separação:
- adicionar 2ª assinatura invalidaria a 1ª;
- ordem importaria;
- integridade jurídica colapsa.

Uso:
    from utils.document_hash import compute_document_hash, compute_signature_hash

    payload = {...}  # dict canônico do documento
    doc_hash = compute_document_hash(payload)
    # signatures appended later, never modify doc_hash
    sig_hash = compute_signature_hash(
        document_hash=doc_hash, role="diretor",
        user_id="...", signed_at="2026-...",
    )
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


# Campos REMOVIDOS antes do hash (mutáveis ou meta-info de auditoria pós-emissão).
_HASH_EXCLUDED_KEYS: frozenset[str] = frozenset({
    "_id",
    "document_hash_sha256",          # o hash não entra em si mesmo
    "signatures",                    # populado após hash
    "verification_token",            # gerado em paralelo, não faz parte do conteúdo
    "revoked_at",                    # mutável (se revogado depois)
    "revoked_reason",
    "revoked_by_user_id",
    "superseded_by_document_id",
    "audit_trail",
})


def _canonicalize(value: Any) -> Any:
    """Converte recursivamente para forma estável JSON-serializable."""
    if isinstance(value, dict):
        # remove keys excluídos no nível raiz e recursivamente
        return {
            k: _canonicalize(v)
            for k, v in sorted(value.items())
            if k not in _HASH_EXCLUDED_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    return value


def compute_document_hash(payload: dict) -> str:
    """SHA-256 hex do payload canônico, sort_keys, sem campos voláteis.

    Determinístico: mesmo input → mesmo hash, sempre.
    """
    canonical = _canonicalize(payload)
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_signature_hash(
    *,
    document_hash: str,
    role: str,
    user_id: str,
    signed_at: str,
) -> str:
    """SHA-256 derivado de (document_hash + assinante).

    Cada assinatura referencia o `document_hash` ORIGINAL, não o atual.
    Assim adicionar uma 2ª assinatura não invalida a 1ª.
    """
    raw = f"{document_hash}|{role}|{user_id}|{signed_at}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_document_hash(payload: dict, expected_hash: str) -> bool:
    """Valida se o payload atual ainda bate com o hash original."""
    return compute_document_hash(payload) == expected_hash
