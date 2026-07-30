"""
FrequencyRepository — acesso exclusivo às coleções operacionais do envio de frequência CMDE.

Sprint 002.b: apenas ESCRITA de lotes/itens construídos (insert do batch + upsert idempotente
do item por `idempotency_key`). NÃO contém lógica de reserva/lease/processamento — isso é o
Queue Manager (Sprint 002.c). Nunca toca coleções pedagógicas.
"""
from mig.cmde.frequency_models import FrequencyBatch, QueueItem

BATCHES = "mig_cmde_frequency_batches"
QUEUE = "mig_cmde_send_queue"
RECEIPTS = "mig_cmde_send_receipts"


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
