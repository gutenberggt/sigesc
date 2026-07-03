"""BIEngine — orquestrador do Motor de Indicadores (Single Source of Truth).

Depende EXCLUSIVAMENTE de interfaces (Dependency Inversion). Não conhece MongoDB,
dashboards, nem indicadores concretos. Define o FLUXO oficial de resolução:

    request -> registry.get(code, version)
            -> [materializer.read se fresco]
            -> [cache.get]
            -> data_provider.fetch -> calculator.calculate
            -> aggregator.aggregate (se grão-alvo != grão base)
            -> cache.set / (materialização é responsabilidade do ETL)
            -> traceability.record + observability.emit
            -> IndicatorResult (oficial, rastreável)

Na Sprint BI-1A o Engine é montado com providers no-op e SEM calculators/data
providers concretos — portanto `compute` lança `NoCalculatorError` de forma
controlada (nenhum indicador existe ainda). Isso é o comportamento esperado da
fundação: a arquitetura está completa e testável, aguardando a Sprint BI-2.
"""
from __future__ import annotations
from typing import Optional

from ..interfaces.ports import (
    IRegistry, IAggregator, ICacheProvider, ITraceabilityProvider,
    IDataProvider, IMaterializer, IObservabilityProvider,
)
from ..calculators.base import CalculatorRegistry
from ..contracts.execution import (
    IndicatorRequest, CalculationContext, AggregationContext,
    CacheContext, MaterializationContext,
)
from ..contracts.results import IndicatorResult
from ..models.enums import RefreshStrategy


class BIEngine:
    def __init__(
        self,
        *,
        registry: IRegistry,
        calculators: CalculatorRegistry,
        aggregator: IAggregator,
        cache: ICacheProvider,
        materializer: IMaterializer,
        traceability: ITraceabilityProvider,
        observability: IObservabilityProvider,
        data_provider: Optional[IDataProvider] = None,
    ) -> None:
        self._registry = registry
        self._calculators = calculators
        self._aggregator = aggregator
        self._cache = cache
        self._materializer = materializer
        self._trace = traceability
        self._obs = observability
        self._data = data_provider

    # -- Introspecção (segura nesta fase) -------------------------------------
    def is_ready_for(self, code: str, version: Optional[int] = None) -> bool:
        """True se há definição + calculator + data provider para servir o indicador."""
        if not self._registry.exists(code, version) or self._data is None:
            return False
        definition = self._registry.get(code, version)
        return self._calculators.has_strategy_for(definition)

    # -- Fluxo oficial de cálculo ---------------------------------------------
    async def compute(self, request: IndicatorRequest) -> IndicatorResult:
        definition = self._registry.get(request.code, request.version)

        # 1) Materialização (marts) — leitura se fresca
        if definition.materialization.enabled:
            mctx = MaterializationContext(
                code=definition.code, version=definition.version,
                mart=definition.materialization.mart,
                incremental_key=definition.materialization.incremental_key,
                grain=request.grain, scope_id=request.scope_id,
                academic_year=request.academic_year, period=request.period,
            )
            if await self._materializer.is_fresh(mctx):
                mat = await self._materializer.read(mctx)
                if mat is not None:
                    await self._trace.record(mat)
                    return mat

        # 2) Cache
        cache_ctx = self._build_cache_ctx(request, definition.version)
        if definition.cache.enabled:
            cached = await self._cache.get(cache_ctx)
            if cached is not None:
                return cached

        # 3) Cálculo (Strategy) — exige data provider concreto (BI-2)
        if self._data is None:
            from ..calculators.base import NoCalculatorError
            raise NoCalculatorError("Nenhum DataProvider configurado (fundação BI-1A)")

        calculator = self._calculators.resolve(definition)  # NoCalculatorError se ausente
        calc_ctx = CalculationContext(request=request, definition=definition)
        base = await calculator.calculate(calc_ctx, self._data)

        # 4) Agregação por granularidade (composição, sem reescrever fórmula)
        if base.grain != request.grain:
            agg_ctx = AggregationContext(
                request=request, definition=definition,
                target_grain=request.grain, source_grain=base.grain,
            )
            base = await self._aggregator.aggregate(base, agg_ctx)

        # 5) Cache set (materialização fica a cargo do ETL, não do caminho de leitura)
        if definition.cache.enabled and definition.refresh.strategy == RefreshStrategy.CACHED:
            await self._cache.set(cache_ctx, base, definition.cache.ttl_seconds)

        # 6) Rastreabilidade
        await self._trace.record(base)
        return base

    # -- Helpers ---------------------------------------------------------------
    @staticmethod
    def _build_cache_ctx(request: IndicatorRequest, version: int) -> CacheContext:
        fingerprint = "&".join(f"{k}={request.params[k]}" for k in sorted(request.params))
        return CacheContext(
            code=request.code, version=version, grain=request.grain,
            scope_id=request.scope_id, academic_year=request.academic_year,
            period=request.period, params_fingerprint=fingerprint,
        )
