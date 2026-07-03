"""Composição/Wiring do domínio BI (Dependency Injection)."""
from .container import BIContainer, build_default_engine

__all__ = ["BIContainer", "build_default_engine"]
