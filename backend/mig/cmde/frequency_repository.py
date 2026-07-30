"""
FrequencyRepository — acesso exclusivo às coleções operacionais do envio de frequência CMDE.

Sprint 002.b: apenas ESCRITA de lotes/itens construídos (insert do batch + upsert idempotente
do item por `idempotency_key`). NÃO contém lógica de reserva/lease/processamento — isso é o
Queue Manager (Sprint 002.c). Nunca toca coleções pedagógicas.
"""
from mig.cmde.frequency_models import FrequencyBatch, QueueItem, SendReceipt
from datetime import datetime, timezone

BATCHES = "mig_cmde_frequency_batches"
QUEUE = "mig_cmde_send_queue"
RECEIPTS = "mig_cmde_send_receipts"


def _iso():
    return datetime.now(timezone.utc).isoformat()


class FrequencyRepository:
    def __init__(self, db):
        self.db = db

    async def save_batch(self, batch: FrequencyBatch) -> dict:
        doc = batch.to_doc()
        await self.db[BATCHES].insert_one(dict(doc))
        doc.pop("_id", None)
        return doc

    async def upsert_item(self, item: QueueItem) -> None:
        """Upsert idempotente por idempotency_key (re-build não duplica itens)."""
        doc = item.to_doc()
        await self.db[QUEUE].update_one(
            {"idempotency_key": doc["idempotency_key"]},
            {"$setOnInsert": doc},
            upsert=True,
        )

    async def count_existing_keys(self, keys: list) -> int:
        if not keys:
            return 0
        return await self.db[QUEUE].count_documents({"idempotency_key": {"$in": keys}})

    # ---- Recibos + reconciliação de lote (Sprint 002.d) ----
    async def save_receipt(self, receipt: SendReceipt) -> None:
        await self.db[RECEIPTS].insert_one(dict(receipt.to_doc()))

    async def batch_item_counts(self, batch_id: str) -> dict:
        rows = await self.db[QUEUE].aggregate([
            {"$match": {"batch_id": batch_id}},
            {"$group": {"_id": "$status", "n": {"$sum": 1}}},
        ]).to_list(50)
        return {r["_id"]: r["n"] for r in rows}

    async def update_batch(self, batch_id: str, status: str = None, totals: dict = None) -> None:
        set_doc = {"updated_at": _iso()}
        if status:
            set_doc["status"] = status
        if totals is not None:
            set_doc["totals"] = totals
        await self.db[BATCHES].update_one({"id": batch_id}, {"$set": set_doc})
