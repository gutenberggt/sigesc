"""Base do Strategy Pattern de cálculo + dispatcher.

Objetivo: permitir múltiplas estratégias de cálculo (RATIO, WEIGHTED_AVG,
COMPOSITE, DERIVED, EXTERNAL, ...) sem que o Engine conheça implementações.
Open/Closed: registrar uma nova estratégia não altera o Engine.

Reutilização: implementações futuras DEVEM reusar as calculadoras canônicas
existentes do backend (ex.: `attendance_utils`, `grade_calculator`) em vez de
reimplementar regras — o Motor apenas orquestra e padroniza.
"""
from __future__ import annotations
from abc import abstractmethod
from typing import Optional

from ..interfaces.ports import ICalculator, IDataProvider
from ..contracts.definitions import IndicatorDefinition
from ..contracts.execution import CalculationContext
from ..contracts.results import IndicatorResult


class NoCalculatorError(Exception):
    """Nenhuma estratégia registrada suporta a definição solicitada."""


class BaseCalculator(ICalculator):
    """Classe base para estratégias de cálculo (sem lógica concreta)."""

    #: FormulaType.value suportado por esta estratégia (definido nas subclasses)
    formula_type: Optional[str] = None

    def supports(self, definition: IndicatorDefinition) -> bool:
        return bool(self.formula_type) and definition.formula.type.value == self.formula_type

    @abstractmethod
    async def calculate(self, ctx: CalculationContext, data: IDataProvider) -> IndicatorResult:
        """Implementado nas estratégias concretas (Sprint BI-2)."""


class CalculatorRegistry:
    """Dispatcher que seleciona a estratégia adequada a uma definição."""

    def __init__(self) -> None:
        self._strategies: list[ICalculator] = []

    def register(self, calculator: ICalculator) -> None:
        self._strategies.append(calculator)

    def resolve(self, definition: IndicatorDefinition) -> ICalculator:
        for strategy in self._strategies:
            if strategy.supports(definition):
                return strategy
        raise NoCalculatorError(
            f"Sem calculator para {definition.code} (fórmula {definition.formula.type})"
        )

    def has_strategy_for(self, definition: IndicatorDefinition) -> bool:
        return any(s.supports(definition) for s in self._strategies)
