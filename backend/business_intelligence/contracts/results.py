"""Contratos de RESULTADO + rastreabilidade.

Responsabilidade: representar o valor oficial de um indicador e sua proveniência.
Uso: retornado pelo Engine; consumido por API/Dashboards/IA/Relatórios.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

from ..models.enums import Grain, Unit, KpiStatus, ResultSource


@dataclass(frozen=True)
class BreakdownItem:
    """Recorte de um resultado por dimensão (ex.: por escola, por série)."""
    dimension: str
    key: str
    label: str
    value: Optional[float]


@dataclass(frozen=True)
class TraceRecord:
    """Rastreabilidade: liga TODA resposta ao indicador oficial que a produziu.

    Garante o princípio de rastreabilidade (dashboard/IA -> indicador oficial).
    """
    indicator_code: str
    definition_version: int
    engine_version: str
    computed_at: str                     # ISO-8601 (preenchido em runtime futuro)
    result_source: ResultSource
    period: Optional[str] = None
    grain: Optional[Grain] = None
    scope_id: Optional[str] = None
    params: dict = field(default_factory=dict)
    inputs_fingerprint: str = ""         # hash das entradas (auditoria)
    data_sources: tuple = ()             # coleções/adapters efetivamente lidos


@dataclass(frozen=True)
class IndicatorResult:
    """Valor oficial de um indicador (com KPI e rastreabilidade)."""
    code: str
    name: str
    unit: Unit
    grain: Grain
    scope_id: Optional[str]
    value: Optional[float]
    kpi_status: KpiStatus = KpiStatus.UNKNOWN
    target: Optional[float] = None
    breakdown: tuple = ()                # tuple[BreakdownItem]
    trace: Optional[TraceRecord] = None
    extra: dict = field(default_factory=dict)
