"""NullCacheProvider — implementação no-op (cache desligado).

Objetivo: permitir montar o Engine completo sem cache real nesta fase.
Sempre "miss"; `set`/`invalidate` são no-ops. Substituível por Redis/Mongo depois.
"""
from __future__ import annotations
from typing import Optional

from ..interfaces.ports import ICacheProvider
from ..contracts.execution import CacheContext
from ..contracts.results import IndicatorResult


class NullCacheProvider(ICacheProvider):
    async def get(self, ctx: CacheContext) -> Optional[IndicatorResult]:
        return None

    async def set(self, ctx: CacheContext, result: IndicatorResult, ttl_seconds: int) -> None:
        return None

    async def invalidate(self, ctx: CacheContext) -> None:
        return None
