"""MigMonitoring — contadores de execução em memória (fundação).

Métricas exportáveis para o Dashboard Técnico na sprint de infra.
"""
from collections import defaultdict


class MigMonitoring:
    def __init__(self):
        self._counters = defaultdict(int)

    def incr(self, key: str, by: int = 1):
        self._counters[key] += by

    def snapshot(self) -> dict:
        return dict(self._counters)
