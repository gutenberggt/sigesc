"""
MongoFrequencyQueue — fila DURÁVEL de envio de frequência CMDE sobre MongoDB (Sprint 002.c).

Máquina de estados do item:
    PENDING → RESERVED → PROCESSING → SUCCESS
                        ↘ FAILED (não recuperável)
                        ↘ RETRYING → (reservável de novo) ↘ DEAD_LETTER (excedeu max_attempts)
    RESERVED/PROCESSING → PENDING (requeue por expiração de lease)

Recursos: reserva atômica (lease), renovação de lease, requeue automático por expiração,
backpressure por tenant, limite máximo de tentativas → DEAD_LETTER, métricas de fila e índices.

NÃO envia ao MEC. NÃO contém Worker nem Scheduler (o consumo é escopo da 002.d).
Integra a idempotência existente via índice unique em `idempotency_key`.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from pymongo import ReturnDocument

from mig.cmde.frequency_repository import QUEUE

PENDING = "PENDING"
RESERVED = "RESERVED"
PROCESSING = "PROCESSING"
RETRYING = "RETRYING"
SUCCESS = "SUCCESS"
FAILED = "FAILED"
DEAD_LETTER = "DEAD_LETTER"

AVAILABLE = (PENDING, RETRYING)      # reserváveis
INFLIGHT = (RESERVED, PROCESSING)    # ocupam capacidade (backpressure)
TERMINAL = (SUCCESS, FAILED, DEAD_LETTER)


def _now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _now()).isoformat()


class MongoFrequencyQueue:
    def __init__(self, db, max_attempts: int = 5, backpressure_per_tenant: Optional[int] = None,
                 base_backoff_seconds: float = 2.0, backoff_factor: float = 2.0):
        self.db = db
        self.col = db[QUEUE]
        self.max_attempts = max_attempts
        self.backpressure_per_tenant = backpressure_per_tenant
        self.base_backoff_seconds = base_backoff_seconds
        self.backoff_factor = backoff_factor

    async def ensure_indexes(self):
        await self.col.create_index([("idempotency_key", 1)], unique=True, name="uq_idem")
        await self.col.create_index([("tenant", 1), ("status", 1), ("next_attempt_at", 1)],
                                    name="reserve_idx")
        await self.col.create_index([("status", 1), ("lease_until", 1)], name="lease_idx")
        await self.col.create_index([("tenant", 1), ("status", 1)], name="metrics_idx")

    # ---- Escrita/idempotência ----
    async def enqueue(self, item: dict) -> dict:
        doc = dict(item)
        doc.setdefault("status", PENDING)
        doc.setdefault("attempts", 0)
        doc.setdefault("created_at", _iso())
        doc.setdefault("updated_at", _iso())
        await self.col.update_one({"idempotency_key": doc["idempotency_key"]},
                                  {"$setOnInsert": doc}, upsert=True)
        return await self.col.find_one({"idempotency_key": doc["idempotency_key"]}, {"_id": 0})

    async def _inflight_count(self, tenant: str) -> int:
        return await self.col.count_documents({"tenant": tenant, "status": {"$in": list(INFLIGHT)}})

    # ---- Reserva atômica (lease) ----
    async def reserve(self, tenant: str, lease_seconds: int = 60) -> Optional[dict]:
        if self.backpressure_per_tenant is not None:
            if await self._inflight_count(tenant) >= self.backpressure_per_tenant:
                return None
        now_iso = _iso()
        lease = _iso(_now() + timedelta(seconds=lease_seconds))
        query = {"tenant": tenant, "$or": [
            {"status": PENDING},
            {"status": RETRYING, "next_attempt_at": {"$lte": now_iso}},
        ]}
        doc = await self.col.find_one_and_update(
            query,
            {"$set": {"status": RESERVED, "lease_until": lease, "reserved_at": now_iso,
                      "updated_at": now_iso},
             "$inc": {"attempts": 1}},
            sort=[("created_at", 1)], return_document=ReturnDocument.AFTER,
            projection={"_id": 0})
        if doc and not doc.get("first_reserved_at"):
            await self.col.update_one({"id": doc["id"]}, {"$set": {"first_reserved_at": now_iso}})
            doc["first_reserved_at"] = now_iso
        return doc

    async def renew_lease(self, item_id: str, lease_seconds: int = 60) -> bool:
        lease = _iso(_now() + timedelta(seconds=lease_seconds))
        res = await self.col.update_one(
            {"id": item_id, "status": {"$in": list(INFLIGHT)}},
            {"$set": {"lease_until": lease, "updated_at": _iso()}})
        return res.modified_count == 1

    async def start_processing(self, item_id: str) -> bool:
        res = await self.col.update_one(
            {"id": item_id, "status": RESERVED},
            {"$set": {"status": PROCESSING, "updated_at": _iso()}})
        return res.modified_count == 1

    # ---- Transições terminais / retry ----
    async def succeed(self, item_id: str) -> None:
        await self.col.update_one({"id": item_id}, {"$set": {
            "status": SUCCESS, "lease_until": None, "updated_at": _iso()}})

    async def fail(self, item_id: str, error: str = None, recoverable: bool = True) -> str:
        item = await self.col.find_one({"id": item_id}, {"_id": 0, "attempts": 1})
        attempts = (item or {}).get("attempts", 0)
        set_doc = {"last_error": error, "lease_until": None, "updated_at": _iso()}
        if not recoverable:
            status = FAILED
        elif attempts >= self.max_attempts:
            status = DEAD_LETTER
        else:
            status = RETRYING
            delay = self.base_backoff_seconds * (self.backoff_factor ** max(0, attempts - 1))
            set_doc["next_attempt_at"] = _iso(_now() + timedelta(seconds=delay))
        set_doc["status"] = status
        await self.col.update_one({"id": item_id}, {"$set": set_doc})
        return status

    # ---- QueuePort-compatíveis ----
    async def complete(self, item_id: str, status: str = SUCCESS) -> None:
        status = status if status in TERMINAL else FAILED
        await self.col.update_one({"id": item_id},
                                  {"$set": {"status": status, "lease_until": None, "updated_at": _iso()}})

    async def release(self, item_id: str) -> None:
        await self.col.update_one({"id": item_id}, {"$set": {
            "status": PENDING, "lease_until": None, "updated_at": _iso()}})

    async def reprocess(self, item_id: str) -> bool:
        """Reprocessa item terminal (DEAD_LETTER/FAILED) → PENDING, respeitando idempotência
        (mesmo item/idempotency_key; não cria duplicata)."""
        res = await self.col.update_one(
            {"id": item_id, "status": {"$in": [DEAD_LETTER, FAILED]}},
            {"$set": {"status": PENDING, "attempts": 0, "lease_until": None,
                      "next_attempt_at": None, "last_error": None, "updated_at": _iso()}})
        return res.modified_count == 1

    async def requeue_expired(self) -> int:
        now_iso = _iso()
        res = await self.col.update_many(
            {"status": {"$in": list(INFLIGHT)}, "lease_until": {"$lt": now_iso}},
            {"$set": {"status": PENDING, "lease_until": None, "updated_at": now_iso}})
        return res.modified_count

    async def stats(self, tenant: str) -> dict:
        pipeline = [{"$match": {"tenant": tenant}},
                    {"$group": {"_id": "$status", "n": {"$sum": 1}}}]
        rows = await self.col.aggregate(pipeline).to_list(50)
        return {r["_id"]: r["n"] for r in rows}

    # ---- Métricas da fila (para o MIG) ----
    async def queue_metrics(self, tenant: str = None) -> dict:
        match = {"tenant": tenant} if tenant else {}
        rows = await self.col.aggregate(
            [{"$match": match}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(50)
        by_state = {r["_id"]: r["n"] for r in rows}
        # tempo médio em fila (created_at → primeira reserva, ou agora se ainda esperando)
        sample = await self.col.find(
            match, {"_id": 0, "created_at": 1, "first_reserved_at": 1, "status": 1}
        ).sort("created_at", -1).to_list(2000)
        waits = []
        now = _now()
        for it in sample:
            created = it.get("created_at")
            if not created:
                continue
            try:
                c = datetime.fromisoformat(created)
                end = datetime.fromisoformat(it["first_reserved_at"]) if it.get("first_reserved_at") \
                    else (now if it.get("status") in AVAILABLE else None)
            except Exception:
                continue
            if end is not None:
                waits.append((end - c).total_seconds() * 1000)
        avg_wait = round(sum(waits) / len(waits), 1) if waits else None
        return {
            "pendentes": by_state.get(PENDING, 0),
            "processando": by_state.get(RESERVED, 0) + by_state.get(PROCESSING, 0),
            "retries": by_state.get(RETRYING, 0),
            "dead_letters": by_state.get(DEAD_LETTER, 0),
            "success": by_state.get(SUCCESS, 0),
            "failed": by_state.get(FAILED, 0),
            "tempo_medio_fila_ms": avg_wait,
            "by_state": by_state,
        }
