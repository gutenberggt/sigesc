"""DTOs de contrato da API BI (documental — sem endpoints).

Cada par Query/Response corresponde a um recurso projetado em BI_ENGINE_ARCHITECTURE.md §9.
Autenticação (JWT) e RLS (tenant/escola) serão aplicadas na implementação (BI-4).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ---- GET /api/bi/indicators -------------------------------------------------
@dataclass(frozen=True)
class BiIndicatorQuery:
    codes: tuple                         # 1..n códigos
    grain: str                           # rede|escola|etapa|turma|professor|aluno
    scope_id: Optional[str] = None
    academic_year: Optional[int] = None
    period: Optional[str] = None
    dimensions: tuple = ()
    params: dict = field(default_factory=dict)
    page: int = 1
    page_size: int = 50


@dataclass(frozen=True)
class BiIndicatorResponse:
    code: str
    name: str
    unit: str
    version: int
    grain: str
    scope_id: Optional[str]
    value: Optional[float]
    kpi_status: str
    breakdown: tuple = ()
    source: str = "realtime"             # mart|cache|realtime
    computed_at: Optional[str] = None


# ---- GET /api/bi/dashboard/{dashboard_id} -----------------------------------
@dataclass(frozen=True)
class BiDashboardQuery:
    dashboard_id: str                    # operacional|executivo|<especializado>
    scope_id: Optional[str] = None
    academic_year: Optional[int] = None
    period: Optional[str] = None
    filters: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BiDashboardResponse:
    dashboard: str
    generated_at: Optional[str]
    indicators: tuple = ()               # tuple[BiIndicatorResponse]
    filters_applied: dict = field(default_factory=dict)


# ---- GET /api/bi/trends -----------------------------------------------------
@dataclass(frozen=True)
class BiTrendQuery:
    code: str
    grain: str
    scope_id: Optional[str]
    date_from: str
    date_to: str
    bucket: str = "mes"                  # mes|bimestre|ano


@dataclass(frozen=True)
class BiTrendResponse:
    code: str
    series: tuple = ()                   # tuple[(period, value)]
    delta: Optional[float] = None
    direction: Optional[str] = None      # up|down|flat


# ---- GET /api/bi/rankings ---------------------------------------------------
@dataclass(frozen=True)
class BiRankingQuery:
    code: str
    grain: str
    academic_year: Optional[int] = None
    period: Optional[str] = None
    order: str = "desc"
    limit: int = 20
    filters: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BiRankingResponse:
    criteria: str
    ranking: tuple = ()                  # tuple[(scope_id, name, value, position)]


# ---- GET /api/bi/alerts -----------------------------------------------------
@dataclass(frozen=True)
class BiAlertsQuery:
    severity: Optional[str] = None       # warn|critical
    scope_id: Optional[str] = None
    category: Optional[str] = None


@dataclass(frozen=True)
class BiAlertsResponse:
    alerts: tuple = ()                   # tuple[(code, scope, value, target, severity, since)]
