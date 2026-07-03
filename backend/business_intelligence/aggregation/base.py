"""Agregação por granularidade.

Objetivo: subir um resultado do grão fino para o grão-alvo por COMPOSIÇÃO,
sem reescrever a fórmula (a regra de cálculo vive no Calculator).
Nesta sprint: base + `IdentityAggregator` (no-op) + escada de grãos.
"""
from __future__ import annotations
from abc import abstractmethod

from ..interfaces.ports import IAggregator
from ..contracts.execution import AggregationContext
from ..contracts.results import IndicatorResult
from ..models.enums import Grain


class GrainLadder:
    """Ordem canônica de agregação (fino -> amplo)."""
    ORDER = [Grain.ALUNO, Grain.TURMA, Grain.ESCOLA, Grain.ETAPA, Grain.REDE]

    @classmethod
    def is_upward(cls, source: Grain, target: Grain) -> bool:
        try:
            return cls.ORDER.index(target) > cls.ORDER.index(source)
        except ValueError:
            # PROFESSOR é grão especial (resolvido via alocação) — fora da escada linear
            return False


class BaseAggregator(IAggregator):
    """Base para agregadores (sem lógica concreta nesta sprint)."""

    @abstractmethod
    async def aggregate(self, base: IndicatorResult, ctx: AggregationContext) -> IndicatorResult:
        ...


class IdentityAggregator(BaseAggregator):
    """No-op: retorna o próprio resultado (usado quando source_grain == target_grain).

    Mantém a arquitetura completa sem introduzir comportamento nesta fase.
    """

    async def aggregate(self, base: IndicatorResult, ctx: AggregationContext) -> IndicatorResult:
        return base
