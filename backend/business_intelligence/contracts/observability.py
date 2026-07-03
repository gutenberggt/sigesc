"""Contratos de OBSERVABILIDADE (métricas do Motor).

Responsabilidade: descrever eventos/métricas coletáveis futuramente.
Uso: emitidos pelo Engine via ObservabilityProvider (no-op nesta fase).
Nesta sprint: apenas contratos (sem coleta/persistência).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ObservabilityEvent:
    """Evento único de observabilidade de um cálculo."""
    indicator_code: str
    event: str                           # calculation | cache_hit | cache_miss | error | materialization
    duration_ms: Optional[float] = None
    result_source: Optional[str] = None
    error: Optional[str] = None
    at: Optional[str] = None             # ISO-8601


@dataclass
class EngineMetrics:
    """Agregado de métricas do Motor (para dashboards de operação futuros)."""
    calculations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    materializations: int = 0
    errors: int = 0
    total_calc_ms: float = 0.0
    last_refresh_ms: float = 0.0

    @property
    def cache_hit_ratio(self) -> float:
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total) if total else 0.0

    @property
    def avg_calc_ms(self) -> float:
        return (self.total_calc_ms / self.calculations) if self.calculations else 0.0
