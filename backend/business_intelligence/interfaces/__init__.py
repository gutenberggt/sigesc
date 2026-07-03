"""Portas (interfaces) do Motor de Indicadores — princípios SOLID.

Todas as dependências do Engine são ABSTRAÇÕES (Dependency Inversion).
Nenhum componente do Motor depende de implementação concreta nem de MongoDB.
As implementações concretas serão fornecidas em sprints futuras via DI.
"""
from .ports import (
    IRegistry,
    ICalculator,
    IAggregator,
    ICacheProvider,
    ITraceabilityProvider,
    IDataProvider,
    IMaterializer,
    IObservabilityProvider,
)

__all__ = [
    "IRegistry", "ICalculator", "IAggregator", "ICacheProvider",
    "ITraceabilityProvider", "IDataProvider", "IMaterializer",
    "IObservabilityProvider",
]
