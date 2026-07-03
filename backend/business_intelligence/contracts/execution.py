"""Contratos de EXECUÇÃO: request e contextos passados pelo Engine às portas.

Responsabilidade: transportar intenção + escopo + parâmetros (sem lógica).
Uso: o BIEngine constrói estes contextos e os injeta nas interfaces
(Calculator, Aggregator, CacheProvider, Materializer).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

from ..models.enums import Grain


@dataclass(frozen=True)
class IndicatorRequest:
    """Solicitação de um indicador para um escopo/granularidade/período."""
    code: str
    grain: Grain
    scope_id: Optional[str] = None       # id do grão (None => rede inteira)
    academic_year: Optional[int] = None
    period: Optional[str] = None         # mes | bimestre | ano
    dimensions: tuple = ()               # recortes solicitados
    params: dict = field(default_factory=dict)
    version: Optional[int] = None        # None => versão ACTIVE
    # Escopo de segurança (RLS) — resolvido pela API a partir do usuário:
    tenant_id: Optional[str] = None
    allowed_school_ids: tuple = ()


@dataclass(frozen=True)
class CalculationContext:
    """Contexto entregue ao Calculator (Strategy)."""
    request: IndicatorRequest
    definition: Any                      # IndicatorDefinition (evita import circular)
    resolved_params: dict = field(default_factory=dict)
    dependency_results: dict = field(default_factory=dict)  # code -> IndicatorResult


@dataclass(frozen=True)
class AggregationContext:
    """Contexto de agregação por granularidade."""
    request: IndicatorRequest
    definition: Any
    target_grain: Grain
    source_grain: Grain


@dataclass(frozen=True)
class CacheContext:
    """Contexto para chaveamento/consulta de cache."""
    code: str
    version: int
    grain: Grain
    scope_id: Optional[str]
    academic_year: Optional[int]
    period: Optional[str]
    params_fingerprint: str = ""

    @property
    def cache_key(self) -> str:
        return "|".join([
            self.code, str(self.version), self.grain.value,
            self.scope_id or "*", str(self.academic_year or "*"),
            self.period or "*", self.params_fingerprint or "-",
        ])


@dataclass(frozen=True)
class MaterializationContext:
    """Contexto para leitura/gravação de mart materializado."""
    code: str
    version: int
    mart: str
    incremental_key: str
    grain: Grain
    scope_id: Optional[str] = None
    academic_year: Optional[int] = None
    period: Optional[str] = None
