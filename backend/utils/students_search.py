"""
Utilitários para busca/autocomplete de alunos (server-side).

[Fev/2026] Diretriz arquitetural SIGESC:
- Frontend NUNCA deve carregar lista completa de alunos para filtrar local.
- Toda busca deve passar por endpoint enxuto e indexado.
- Ver: /app/docs/SEARCH_ARCHITECTURE.md
"""
from __future__ import annotations

import re
import time
import logging
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ============================================================================
# Rate limiter in-memory (per-user, sliding window).
# Simples por design: autocomplete é alto-volume e não precisa de Redis para
# um teto de 30 req/min/user. Em produção multi-réplica, cada réplica aplica
# seu teto local — ainda assim protege contra abuso/loop runaway.
# ============================================================================
_rate_buckets: dict[str, list[float]] = defaultdict(list)
_RATE_MAX_CALLS = 30
_RATE_WINDOW_SECONDS = 60


def check_autocomplete_rate_limit(user_id: str) -> None:
    """Levanta 429 se o usuário ultrapassou o teto de chamadas/min."""
    if not user_id:
        return  # Sem ID não dá pra travar; deixa passar (auth já trava antes)
    now = time.monotonic()
    bucket = _rate_buckets[user_id]
    cutoff = now - _RATE_WINDOW_SECONDS
    # Remove timestamps fora da janela
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= _RATE_MAX_CALLS:
        raise HTTPException(
            status_code=429,
            detail=f"Muitas buscas em sequência. Aguarde alguns segundos."
        )
    bucket.append(now)


# ============================================================================
# Helpers
# ============================================================================
def mask_cpf(cpf: Optional[str]) -> Optional[str]:
    """Mascara CPF para autocomplete: ***.123.***-45.

    Mantém apenas o bloco 4-6 e os 2 dígitos verificadores visíveis.
    Se CPF mal-formatado, retorna None (não vaza dado).
    """
    if not cpf:
        return None
    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11:
        return None
    return f"***.{digits[3:6]}.***-{digits[9:11]}"


# ============================================================================
# Telemetria leve (counters em memória) — exposta via endpoint admin no futuro.
# Mede: total de chamadas, % fallback contains, tempo médio.
# ============================================================================
_metrics = {
    "total_calls": 0,
    "fallback_contains_calls": 0,
    "total_duration_ms": 0.0,
    "empty_results": 0,
}


def record_autocomplete_metrics(*, used_fallback: bool, duration_ms: float, result_count: int) -> None:
    _metrics["total_calls"] += 1
    if used_fallback:
        _metrics["fallback_contains_calls"] += 1
    _metrics["total_duration_ms"] += duration_ms
    if result_count == 0:
        _metrics["empty_results"] += 1
    # Log estruturado a cada 100 chamadas
    if _metrics["total_calls"] % 100 == 0:
        avg = _metrics["total_duration_ms"] / max(_metrics["total_calls"], 1)
        fallback_pct = 100.0 * _metrics["fallback_contains_calls"] / max(_metrics["total_calls"], 1)
        empty_pct = 100.0 * _metrics["empty_results"] / max(_metrics["total_calls"], 1)
        logger.info(
            "[autocomplete:students] checkpoint calls=%d avg=%.1fms fallback=%.1f%% empty=%.1f%%",
            _metrics["total_calls"], avg, fallback_pct, empty_pct,
        )


def get_autocomplete_metrics_snapshot() -> dict:
    avg = _metrics["total_duration_ms"] / max(_metrics["total_calls"], 1)
    fallback_pct = 100.0 * _metrics["fallback_contains_calls"] / max(_metrics["total_calls"], 1)
    empty_pct = 100.0 * _metrics["empty_results"] / max(_metrics["total_calls"], 1)
    return {
        "total_calls": _metrics["total_calls"],
        "fallback_contains_calls": _metrics["fallback_contains_calls"],
        "fallback_pct": round(fallback_pct, 2),
        "avg_duration_ms": round(avg, 2),
        "empty_results": _metrics["empty_results"],
        "empty_pct": round(empty_pct, 2),
    }
