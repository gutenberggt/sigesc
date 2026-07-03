"""Formula Registry — Registro Oficial de Fórmulas/Definições (infraestrutura)."""
from .errors import (
    RegistryError, IndicatorNotFoundError, DuplicateDefinitionError,
    NoActiveVersionError,
)
from .formula_registry import FormulaRegistry

__all__ = [
    "FormulaRegistry", "RegistryError", "IndicatorNotFoundError",
    "DuplicateDefinitionError", "NoActiveVersionError",
]
