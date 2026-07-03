"""NullMaterializer — no-op (nenhum mart lido/escrito nesta fase).

`is_fresh` sempre False => Engine cai para cache/realtime.
Substituível por `MongoMaterializer(IMaterializer)` na Sprint BI-3.
"""
from __future__ import annotations
from typing import Optional

from ..interfaces.ports import IMaterializer
from ..contracts.execution import MaterializationContext
from ..contracts.results import IndicatorResult


class NullMaterializer(IMaterializer):
    async def read(self, ctx: MaterializationContext) -> Optional[IndicatorResult]:
        return None

    async def is_fresh(self, ctx: MaterializationContext) -> bool:
        return False

    async def write(self, ctx: MaterializationContext, result: IndicatorResult) -> None:
        return None
