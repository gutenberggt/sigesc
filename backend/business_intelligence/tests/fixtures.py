"""Fixtures e helpers de teste do domínio BI."""
from __future__ import annotations

from ..di.container import BIContainer
from ..core.engine import BIEngine
from .mocks import FakeDataProvider, FakeCalculator


def make_wired_engine() -> BIEngine:
    """Monta um Engine COMPLETO com mocks (registry vazio até o teste registrar)."""
    container = BIContainer()
    container.data_provider = FakeDataProvider()
    container.calculators.register(FakeCalculator())
    return container.build_engine()


def make_bare_container() -> BIContainer:
    """Container de fundação (no-op, sem data provider) — estado da Sprint BI-1A."""
    return BIContainer()
