"""
Contratos internos genéricos do MIG (agnósticos de provedor) — Sprint 002.a.

Definem as PORTAS (interfaces) que a camada de envio assíncrono usará:
- QueuePort: fila durável de itens de envio (reserva atômica via lease).
- IdempotencyStore: memória de idempotência (curto-circuita reenvio já concluído).

IMPORTANTE: aqui ficam APENAS os contratos abstratos. A implementação REAL sobre
MongoDB (Queue Manager de produção) é escopo da Sprint 002.c — NÃO implementada aqui.
Implementações de referência em memória (para testes/simulador) vivem em `mig/core/inmemory.py`.
"""
from abc import ABC, abstractmethod
from typing import Optional


class QueuePort(ABC):
    """Fila durável de itens de envio. Escopada por tenant, com reserva por lease."""

    @abstractmethod
    async def enqueue(self, item: dict) -> dict: ...

    @abstractmethod
    async def reserve(self, tenant: str, lease_seconds: int = 60) -> Optional[dict]:
        """Reserva atômica de UM item `pending` do tenant → marca `leased` + `lease_until`."""

    @abstractmethod
    async def complete(self, item_id: str, status: str) -> None:
        """Finaliza o item com status terminal (accepted|rejected|error|sent)."""

    @abstractmethod
    async def release(self, item_id: str) -> None:
        """Devolve o item para `pending` (ex.: worker desistiu)."""

    @abstractmethod
    async def requeue_expired(self) -> int:
        """Reprocessa itens `leased` cujo `lease_until` expirou → `pending`. Retorna quantos."""

    @abstractmethod
    async def stats(self, tenant: str) -> dict:
        """Contagem por status para o tenant (observabilidade)."""


class IdempotencyStore(ABC):
    """Memória de idempotência: dado uma chave determinística, evita reprocessar/reenviar."""

    @abstractmethod
    async def seen(self, key: str) -> Optional[dict]:
        """Retorna o resultado previamente registrado para a chave, ou None."""

    @abstractmethod
    async def remember(self, key: str, result: dict) -> None:
        """Registra o resultado terminal associado à chave."""
