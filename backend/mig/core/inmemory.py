"""
Implementações de REFERÊNCIA em memória dos contratos do MIG (Sprint 002.a).

Uso: testes automatizados e o Simulador CMDE de homologação. NÃO é a fila de produção
(o Queue Manager real sobre MongoDB é escopo da Sprint 002.c). Sem thread-safety cross-process;
suficiente para validar o CONTRATO (QueuePort/IdempotencyStore) e os fluxos determinísticos.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from mig.core.ports import QueuePort, IdempotencyStore

_TERMINAL = {"accepted", "rejected", "error", "sent"}


def _now():
    return datetime.now(timezone.utc)


class InMemoryQueue(QueuePort):
    def __init__(self):
        self._items: dict = {}

    async def enqueue(self, item: dict) -> dict:
        doc = dict(item)
        doc.setdefault("status", "pending")
        doc.setdefault("attempts", 0)
        doc.setdefault("lease_until", None)
        self._items[doc["id"]] = doc
        return dict(doc)

    async def reserve(self, tenant: str, lease_seconds: int = 60) -> Optional[dict]:
        for it in self._items.values():
            if it.get("tenant") == tenant and it.get("status") == "pending":
                it["status"] = "leased"
                it["attempts"] = it.get("attempts", 0) + 1
                it["lease_until"] = (_now() + timedelta(seconds=lease_seconds)).isoformat()
                it["updated_at"] = _now().isoformat()
                return dict(it)
        return None

    async def complete(self, item_id: str, status: str) -> None:
        it = self._items.get(item_id)
        if it is not None:
            it["status"] = status if status in _TERMINAL else "error"
            it["lease_until"] = None
            it["updated_at"] = _now().isoformat()

    async def release(self, item_id: str) -> None:
        it = self._items.get(item_id)
        if it is not None:
            it["status"] = "pending"
            it["lease_until"] = None
            it["updated_at"] = _now().isoformat()

    async def requeue_expired(self) -> int:
        now_iso = _now().isoformat()
        count = 0
        for it in self._items.values():
            if it.get("status") == "leased" and (it.get("lease_until") or "") < now_iso:
                it["status"] = "pending"
                it["lease_until"] = None
                count += 1
        return count

    async def stats(self, tenant: str) -> dict:
        out: dict = {}
        for it in self._items.values():
            if it.get("tenant") == tenant:
                out[it["status"]] = out.get(it["status"], 0) + 1
        return out


class InMemoryIdempotencyStore(IdempotencyStore):
    def __init__(self):
        self._store: dict = {}

    async def seen(self, key: str) -> Optional[dict]:
        v = self._store.get(key)
        return dict(v) if v is not None else None

    async def remember(self, key: str, result: dict) -> None:
        self._store[key] = dict(result)
