"""BIContainer — container de Dependency Injection do domínio BI.

Objetivo: montar o BIEngine trocando implementações sem alterar o núcleo.
Nesta fase, monta com providers NO-OP e SEM DataProvider/Calculators concretos
(o Engine fica pronto, porém inerte — não serve indicadores ainda).

Substituição futura (BI-2/BI-3):
    container.registry = MongoFormulaRegistry(db)
    container.data_provider = SigescDataProvider(db)
    container.calculators.register(RatioCalculator())   # etc.
    container.cache = RedisCacheProvider(...)
    container.materializer = MongoMaterializer(db)
"""
from __future__ import annotations
from typing import Optional

from ..interfaces.ports import (
    IRegistry, IAggregator, ICacheProvider, ITraceabilityProvider,
    IDataProvider, IMaterializer, IObservabilityProvider,
)
from ..registry.formula_registry import FormulaRegistry
from ..calculators.base import CalculatorRegistry
from ..aggregation.base import IdentityAggregator
from ..cache.null_cache import NullCacheProvider
from ..materialization.null_materializer import NullMaterializer
from ..traceability.null_traceability import NullTraceabilityProvider
from ..observability.null_observability import NullObservabilityProvider
from ..core.engine import BIEngine


class BIContainer:
    """Container simples e explícito (sem framework de DI)."""

    def __init__(self) -> None:
        self.registry: IRegistry = FormulaRegistry()
        self.calculators: CalculatorRegistry = CalculatorRegistry()
        self.aggregator: IAggregator = IdentityAggregator()
        self.cache: ICacheProvider = NullCacheProvider()
        self.materializer: IMaterializer = NullMaterializer()
        self.traceability: ITraceabilityProvider = NullTraceabilityProvider()
        self.observability: IObservabilityProvider = NullObservabilityProvider()
        self.data_provider: Optional[IDataProvider] = None  # concreto em BI-2

    def build_engine(self) -> BIEngine:
        return BIEngine(
            registry=self.registry,
            calculators=self.calculators,
            aggregator=self.aggregator,
            cache=self.cache,
            materializer=self.materializer,
            traceability=self.traceability,
            observability=self.observability,
            data_provider=self.data_provider,
        )


def build_default_engine() -> BIEngine:
    """Fábrica de conveniência: Engine com providers no-op (fundação)."""
    return BIContainer().build_engine()
