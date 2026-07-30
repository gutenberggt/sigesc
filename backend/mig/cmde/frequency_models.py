"""
Modelos de domínio (documentos) do envio de frequência CMDE — Sprint 002.a.

Definem o SHAPE das coleções operacionais (sem tocar coleções pedagógicas):
- FrequencyBatch  → `mig_cmde_frequency_batches`
- QueueItem       → `mig_cmde_send_queue`
- SendReceipt     → `mig_cmde_send_receipts`

Identidade por `id` (uuid4, str) — não usa ObjectId no payload. `to_doc()` devolve dict
pronto para persistência. A persistência REAL (repositório/índices) é escopo da 002.b/002.c.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

BATCH_STATUSES = ("draft", "ready", "processing", "completed", "partial", "failed")
QUEUE_STATUSES = ("pending", "leased", "sent", "accepted", "rejected", "error")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


class BatchTotals(BaseModel):
    items: int = 0
    sent: int = 0
    accepted: int = 0
    rejected: int = 0


class FrequencyBatch(BaseModel):
    id: str = Field(default_factory=_uuid)
    correlation_id: Optional[str] = None
    tenant: Optional[str] = None
    environment: str = "homologacao"
    competencia: str                                   # YYYY-MM
    scope: dict = Field(default_factory=dict)          # {school_id?, class_id?}
    status: str = "draft"
    totals: BatchTotals = Field(default_factory=BatchTotals)
    created_by: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def to_doc(self) -> dict:
        return self.model_dump()


class QueueItem(BaseModel):
    id: str = Field(default_factory=_uuid)
    batch_id: str
    correlation_id: Optional[str] = None
    tenant: Optional[str] = None
    idempotency_key: str
    student_id: str
    school_inep: str = ""
    competencia: str
    payload_snapshot: dict = Field(default_factory=dict)   # nunca inclui segredos
    status: str = "pending"
    attempts: int = 0
    lease_until: Optional[str] = None
    last_error: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def to_doc(self) -> dict:
        return self.model_dump()


class SendReceipt(BaseModel):
    id: str = Field(default_factory=_uuid)
    queue_item_id: str
    batch_id: str
    correlation_id: Optional[str] = None
    tenant: Optional[str] = None
    mec_protocol: Optional[str] = None
    http_status: Optional[int] = None
    accepted: bool = False
    rejection_code: Optional[str] = None
    rejection_reason: Optional[str] = None
    raw_response_hash: Optional[str] = None
    received_at: str = Field(default_factory=_now_iso)

    def to_doc(self) -> dict:
        return self.model_dump()
