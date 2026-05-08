"""
Document Render Jobs — fila de geração de documentos (Passo 4, Fev/2026).

Implementa o contrato CONGELADO em `/app/docs/RENDER_JOBS_CONTRACT.md` no
ESCOPO MÍNIMO autorizado pelo owner:

✅ Persistência (status pending|processing|completed|failed|superseded)
✅ Idempotência por (source_snapshot_id, document_type, template_version,
   render_engine_version)
✅ Retry exponencial básico (3 tentativas: 30s → 2min → 10min)
✅ Snapshots imutáveis de template_version e render_engine_version

❌ Worker distribuído / brokers
❌ Pipeline paralelo
❌ Prioridade dinâmica
❌ Cache multicamada de PDF

Princípio: PDF é consequência do snapshot, NUNCA fonte. Reemissão fiel
exige template_version e render_engine_version preservados na criação.

Esta camada NÃO renderiza PDFs — apenas orquestra. Renderizadores (boletim,
histórico, etc.) são registrados via `register_render_handler(document_type, fn)`.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# ===========================================================================
# Constantes do contrato V1 (não alterar sem bumpar contract_version)
# ===========================================================================
JOB_STATUSES = ("pending", "processing", "completed", "failed", "superseded")

# Tipos de documento suportados — devem casar com handlers registrados.
DOCUMENT_TYPES = (
    "dependency_completion",
    "bulletin",
    "history",
    "enrollment_certificate",
)

# Backoff exponencial fixo (segundos): tentativa 1 falha → 30s; 2 → 2min; 3 → 10min
RETRY_BACKOFF_SECONDS = (30, 120, 600)
MAX_RETRIES = 3


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ===========================================================================
# Idempotência
# ===========================================================================
def compute_idempotency_key(
    *,
    source_snapshot_id: str,
    document_type: str,
    template_version: str,
    render_engine_version: str,
) -> str:
    """SHA-256 da tupla canônica que define um job único.

    Determinístico: mesma tupla → mesma chave. Permite buscar job existente
    antes de criar duplicado.
    """
    raw = f"{source_snapshot_id}|{document_type}|{template_version}|{render_engine_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_payload_hash(payload: dict) -> str:
    """Hash de um payload arbitrário (auditoria — qual conteúdo gerou o job)."""
    import json
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ===========================================================================
# Retry / backoff
# ===========================================================================
def compute_next_retry_at(retry_count: int) -> Optional[str]:
    """Retorna ISO timestamp UTC do próximo retry, ou None se esgotou.

    retry_count é o número de tentativas JÁ FEITAS (0 = nenhuma).
    """
    if retry_count >= MAX_RETRIES:
        return None
    if retry_count < 0:
        retry_count = 0
    if retry_count >= len(RETRY_BACKOFF_SECONDS):
        # fallback: usa o último valor da tabela (não deveria acontecer com MAX_RETRIES=3)
        seconds = RETRY_BACKOFF_SECONDS[-1]
    else:
        seconds = RETRY_BACKOFF_SECONDS[retry_count]
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ===========================================================================
# Registry de handlers (in-process, sem broker)
# ===========================================================================
RenderHandler = Callable[[dict], Awaitable[dict]]
"""Handler recebe o documento do job (dict) e retorna metadados:
{
  "generated_file_id": str | None,
  "generated_file_size_bytes": int | None,
  "pdf_hash_sha256": str | None,
}
Pode levantar exceção em caso de falha — o worker captura e marca retry/failed.
"""

_HANDLERS: dict[str, RenderHandler] = {}


def register_render_handler(document_type: str, handler: RenderHandler) -> None:
    """Registra handler para um tipo de documento.

    Chamado pelo módulo do Boletim/Histórico quando os geradores estiverem prontos.
    """
    if document_type not in DOCUMENT_TYPES:
        logger.warning("[render_jobs] document_type fora do contrato V1: %s", document_type)
    _HANDLERS[document_type] = handler
    logger.info("[render_jobs] handler registrado: %s", document_type)


def get_render_handler(document_type: str) -> Optional[RenderHandler]:
    return _HANDLERS.get(document_type)


def has_render_handler(document_type: str) -> bool:
    return document_type in _HANDLERS


# ===========================================================================
# Mongo: índices + busca
# ===========================================================================
async def ensure_indexes(db) -> None:
    """Indexes essenciais para o worker e idempotência."""
    await db.document_render_jobs.create_index("idempotency_key", unique=True, background=True)
    await db.document_render_jobs.create_index([("status", 1), ("next_retry_at", 1)], background=True)
    await db.document_render_jobs.create_index([("source_snapshot_id", 1), ("document_type", 1)], background=True)
    await db.document_render_jobs.create_index("mantenedora_id", background=True)
    await db.document_render_jobs.create_index([("requested_at", -1)], background=True)


async def find_existing_job(
    db,
    *,
    idempotency_key: str,
) -> Optional[dict]:
    return await db.document_render_jobs.find_one(
        {"idempotency_key": idempotency_key, "status": {"$ne": "superseded"}},
        {"_id": 0},
    )


def is_terminal_status(status: str) -> bool:
    return status in {"completed", "failed", "superseded"}
