"""Contratos (DTOs) do domínio BI.

Separação clara por responsabilidade:
    definitions   -> DEFINIÇÃO do indicador (o "quê")
    execution     -> EXECUÇÃO (request + contextos)
    results       -> RESULTADO + rastreabilidade
    observability -> METADADOS de observabilidade
"""
from .definitions import (
    ParameterSpec, FormulaSpec, SourceSpec, KpiSpec, RefreshSpec,
    CacheSpec, MaterializationSpec, IndicatorMetadata, IndicatorDefinition,
)
from .execution import (
    IndicatorRequest, CalculationContext, AggregationContext,
    CacheContext, MaterializationContext,
)
from .results import IndicatorResult, TraceRecord, BreakdownItem
from .observability import ObservabilityEvent, EngineMetrics

__all__ = [
    "ParameterSpec", "FormulaSpec", "SourceSpec", "KpiSpec", "RefreshSpec",
    "CacheSpec", "MaterializationSpec", "IndicatorMetadata", "IndicatorDefinition",
    "IndicatorRequest", "CalculationContext", "AggregationContext",
    "CacheContext", "MaterializationContext",
    "IndicatorResult", "TraceRecord", "BreakdownItem",
    "ObservabilityEvent", "EngineMetrics",
]
