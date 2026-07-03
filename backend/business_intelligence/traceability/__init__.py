"""Traceability providers. No-op default (sem persistência nesta fase)."""
from .null_traceability import NullTraceabilityProvider

__all__ = ["NullTraceabilityProvider"]
