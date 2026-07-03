"""Definição das portas (ABCs). Nenhuma lógica concreta aqui.

Cada interface tem responsabilidade única (SRP) e é substituível (LSP/DIP).
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional

from ..contracts.definitions import IndicatorDefinition
from ..contracts.execution import (
    IndicatorRequest, CalculationContext, AggregationContext,
    CacheContext, MaterializationContext,
)
from ..contracts.results import IndicatorResult
from ..contracts.observability import ObservabilityEvent


class IRegistry(ABC):
    """Formula Registry: fonte oficial das definições de indicadores."""

    @abstractmethod
    def register(self, definition: IndicatorDefinition) -> None: ...

    @abstractmethod
    def get(self, code: str, version: Optional[int] = None) -> IndicatorDefinition:
        """Retorna a definição (versão ACTIVE se `version` None)."""

    @abstractmethod
    def list(self, *, category: Optional[str] = None, active_only: bool = True) -> list: ...

    @abstractmethod
    def versions(self, code: str) -> list: ...

    @abstractmethod
    def exists(self, code: str, version: Optional[int] = None) -> bool: ...


class ICalculator(ABC):
    """Estratégia de cálculo de UM tipo de fórmula (Strategy Pattern)."""

    @abstractmethod
    def supports(self, definition: IndicatorDefinition) -> bool:
        """Indica se esta estratégia calcula a fórmula da definição."""

    @abstractmethod
    async def calculate(self, ctx: CalculationContext, data: "IDataProvider") -> IndicatorResult: ...


class IAggregator(ABC):
    """Agrega um resultado do grão de origem para o grão-alvo (sem duplicar fórmula)."""

    @abstractmethod
    async def aggregate(self, base: IndicatorResult, ctx: AggregationContext) -> IndicatorResult: ...


class ICacheProvider(ABC):
    """Cache de resultados (TTL)."""

    @abstractmethod
    async def get(self, ctx: CacheContext) -> Optional[IndicatorResult]: ...

    @abstractmethod
    async def set(self, ctx: CacheContext, result: IndicatorResult, ttl_seconds: int) -> None: ...

    @abstractmethod
    async def invalidate(self, ctx: CacheContext) -> None: ...


class IMaterializer(ABC):
    """Leitura/escrita de resultados materializados (marts)."""

    @abstractmethod
    async def read(self, ctx: MaterializationContext) -> Optional[IndicatorResult]: ...

    @abstractmethod
    async def is_fresh(self, ctx: MaterializationContext) -> bool: ...

    @abstractmethod
    async def write(self, ctx: MaterializationContext, result: IndicatorResult) -> None: ...


class ITraceabilityProvider(ABC):
    """Registra a proveniência de cada resultado (rastreabilidade)."""

    @abstractmethod
    async def record(self, result: IndicatorResult) -> None: ...


class IDataProvider(ABC):
    """Abstração da ORIGEM dos dados (independência de origem / DIP).

    Implementações futuras: SIGESC/OLTP, MEC, INEP, FNDE, IBGE, CSV/Excel, manual.
    O Motor NUNCA acessa MongoDB diretamente — só através desta porta.
    """

    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    async def fetch(self, request: IndicatorRequest, definition: IndicatorDefinition) -> Any:
        """Retorna dados brutos/base necessários ao cálculo (formato acordado por calculator)."""


class IObservabilityProvider(ABC):
    """Coleta de métricas/eventos do Motor (no-op nesta fase)."""

    @abstractmethod
    def emit(self, event: ObservabilityEvent) -> None: ...
