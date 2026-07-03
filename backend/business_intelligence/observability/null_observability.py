"""NullObservabilityProvider — no-op (não coleta métricas nesta fase)."""
from __future__ import annotations

from ..interfaces.ports import IObservabilityProvider
from ..contracts.observability import ObservabilityEvent


class NullObservabilityProvider(IObservabilityProvider):
    def emit(self, event: ObservabilityEvent) -> None:
        return None
