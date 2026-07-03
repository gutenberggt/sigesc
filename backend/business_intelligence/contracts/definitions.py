"""Contratos de DEFINIÇÃO de indicadores (espelham `bi_indicator_defs`).

Objetivo: representar, em memória, a definição declarativa de um indicador.
Responsabilidade: estrutura imutável, sem lógica de cálculo.
Uso previsto: registrada no Formula Registry; consumida pelo Resolver/Engine.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

from ..models.enums import (
    Grain, IndicatorCategory, FormulaType, RefreshStrategy,
    IndicatorStatus, Unit, KpiDirection, SourceKind, ParameterType,
)


@dataclass(frozen=True)
class ParameterSpec:
    """Parâmetro configurável de um indicador (parametrização sem código)."""
    key: str
    type: ParameterType
    default: Any = None
    values: tuple = ()            # para ENUM
    min: Optional[float] = None
    max: Optional[float] = None
    description: str = ""


@dataclass(frozen=True)
class FormulaSpec:
    """Fórmula declarativa. Referencia indicadores base por `code` (COMPOSITE/DERIVED)."""
    type: FormulaType
    expression: str = ""                 # forma legível/documental
    numerator: str = ""
    denominator: str = ""
    weights: tuple = ()                  # p/ WEIGHTED_AVG
    depends_on_codes: tuple = ()         # p/ COMPOSITE/DERIVED
    pre: tuple = ()                      # pré-processamentos (ex.: consolidacao_diaria)


@dataclass(frozen=True)
class SourceSpec:
    """Origem dos dados (independência de origem via Data Provider/adapter)."""
    kind: SourceKind
    provider: str = ""                   # id do Data Provider/adapter
    collections: tuple = ()              # coleções OLTP de referência (documental)
    external_ref: str = ""               # endpoint/arquivo externo


@dataclass(frozen=True)
class KpiSpec:
    is_kpi: bool = False
    target: Optional[float] = None
    warn: Optional[float] = None
    critical: Optional[float] = None
    direction: KpiDirection = KpiDirection.HIGHER_IS_BETTER


@dataclass(frozen=True)
class RefreshSpec:
    periodicity: str = "on_demand"       # daily | monthly | on_demand ...
    strategy: RefreshStrategy = RefreshStrategy.REALTIME


@dataclass(frozen=True)
class CacheSpec:
    enabled: bool = False
    ttl_seconds: int = 0


@dataclass(frozen=True)
class MaterializationSpec:
    enabled: bool = False
    mart: str = ""
    incremental_key: str = ""


@dataclass(frozen=True)
class IndicatorMetadata:
    owner: str = ""                      # responsável (produtor)
    notes: str = ""
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    supersedes_version: Optional[int] = None


@dataclass(frozen=True)
class IndicatorDefinition:
    """Definição declarativa e VERSIONADA de um indicador (SSoT).

    `code` é imutável; alteração de fórmula => nova `version` (a anterior é
    marcada DEPRECATED, preservando compatibilidade retroativa).
    """
    code: str
    version: int
    name: str
    category: IndicatorCategory
    formula: FormulaSpec
    source: SourceSpec
    unit: Unit = Unit.RATIO
    status: IndicatorStatus = IndicatorStatus.DRAFT
    description: str = ""
    objective: str = ""
    dependencies: tuple = ()             # nós do DAG (codes ou calculadoras base)
    supported_grains: tuple = ()         # tuple[Grain]
    supported_dimensions: tuple = ()
    default_grain: Grain = Grain.ESCOLA
    parameters: tuple = ()               # tuple[ParameterSpec]
    refresh: RefreshSpec = field(default_factory=RefreshSpec)
    cache: CacheSpec = field(default_factory=CacheSpec)
    materialization: MaterializationSpec = field(default_factory=MaterializationSpec)
    kpi: KpiSpec = field(default_factory=KpiSpec)
    min_roles: tuple = ()                # RBAC de leitura
    metadata: IndicatorMetadata = field(default_factory=IndicatorMetadata)

    @property
    def key(self) -> str:
        """Chave única de definição (code@version)."""
        return f"{self.code}@{self.version}"
