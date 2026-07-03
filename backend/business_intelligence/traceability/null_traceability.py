"""NullTraceabilityProvider — no-op.

Arquitetura de rastreabilidade pronta; persistência (ex.: coleção `bi_trace`)
será adicionada em sprint futura sem alterar o Engine.
"""
from __future__ import annotations

from ..interfaces.ports import ITraceabilityProvider
from ..contracts.results import IndicatorResult


class NullTraceabilityProvider(ITraceabilityProvider):
    async def record(self, result: IndicatorResult) -> None:
        return None
