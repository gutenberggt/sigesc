"""Contratos da futura API BI (`/api/bi/*`).

IMPORTANTE: esta camada NÃO cria endpoints nem registra APIRouter. São apenas
DTOs que descrevem o contrato (request/response) da API projetada na Sprint BI-0.
A implementação real virá na Sprint BI-4 (router registrado no server.py).
"""
from .contracts import (
    BiIndicatorQuery, BiIndicatorResponse,
    BiDashboardQuery, BiDashboardResponse,
    BiTrendQuery, BiTrendResponse,
    BiRankingQuery, BiRankingResponse,
    BiAlertsQuery, BiAlertsResponse,
)

__all__ = [
    "BiIndicatorQuery", "BiIndicatorResponse",
    "BiDashboardQuery", "BiDashboardResponse",
    "BiTrendQuery", "BiTrendResponse",
    "BiRankingQuery", "BiRankingResponse",
    "BiAlertsQuery", "BiAlertsResponse",
]
