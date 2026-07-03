"""Calculators — Strategy Pattern para cálculo de indicadores.

Nesta sprint: apenas a BASE e o dispatcher (CalculatorRegistry).
NENHUM indicador concreto é implementado (Sprint BI-2).
"""
from .base import BaseCalculator, CalculatorRegistry, NoCalculatorError

__all__ = ["BaseCalculator", "CalculatorRegistry", "NoCalculatorError"]
