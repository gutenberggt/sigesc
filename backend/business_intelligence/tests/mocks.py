"""Mocks das portas (interfaces) do Motor — para testes de orquestração.

Permitem exercitar o BIEngine sem implementações reais (nem MongoDB).
"""
from __future__ import annotations
from typing import Optional

from ..interfaces.ports import (
    ICalculator, IDataProvider, IObservabilityProvider,
)
from ..calculators.base import BaseCalculator
from ..contracts.definitions import IndicatorDefinition
from ..contracts.execution import CalculationContext
from ..contracts.results import IndicatorResult, TraceRecord
from ..contracts.observability import ObservabilityEvent
from ..models.enums import Grain, Unit, KpiStatus, ResultSource


class FakeDataProvider(IDataProvider):
    """DataProvider de teste (retorna payload fixo, sem tocar em banco)."""

    def __init__(self, payload=None) -> None:
        self._payload = payload if payload is not None else {"numerator": 87, "denominator": 100}

    @property
    def source_id(self) -> str:
        return "fake"

    async def fetch(self, request, definition):
        return self._payload


class FakeCalculator(BaseCalculator):
    """Calculator de teste que devolve um IndicatorResult determinístico."""
    formula_type = "ratio"

    async def calculate(self, ctx: CalculationContext, data: IDataProvider) -> IndicatorResult:
        payload = await data.fetch(ctx.request, ctx.definition)
        num = payload.get("numerator", 0)
        den = payload.get("denominator", 1) or 1
        value = num / den
        trace = TraceRecord(
            indicator_code=ctx.definition.code,
            definition_version=ctx.definition.version,
            engine_version="test",
            computed_at="2026-06-30T00:00:00Z",
            result_source=ResultSource.REALTIME,
        )
        return IndicatorResult(
            code=ctx.definition.code, name=ctx.definition.name, unit=Unit.PERCENT,
            grain=ctx.request.grain, scope_id=ctx.request.scope_id, value=value,
            kpi_status=KpiStatus.OK, trace=trace,
        )


class RecordingObservability(IObservabilityProvider):
    """Coletor de eventos em memória (para asserts em testes)."""

    def __init__(self) -> None:
        self.events: list[ObservabilityEvent] = []

    def emit(self, event: ObservabilityEvent) -> None:
        self.events.append(event)
