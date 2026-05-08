"""
SLA institucional para Academic Events.

[Fev/2026] Passo 2 — exigência do owner: lógica centralizada, NUNCA replicada em routers.

Regra inicial V1 (não configurável por mantenedora ainda):
    0–3 dias  → healthy
    4–7 dias  → warning
    >7 dias   → critical

Mudanças nessas faixas exigem PR + bump de `sla_version`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

SLA_VERSION = "1"

# Faixas (em dias). Tupla (limite_superior_inclusivo, status).
# Ordem importa: primeiro match vence.
_SLA_BANDS: tuple[tuple[int, str], ...] = (
    (3, "healthy"),
    (7, "warning"),
    (10**9, "critical"),
)


def compute_sla_days(created_at: object, *, now: Optional[datetime] = None) -> int:
    """Calcula a idade do evento em dias inteiros (truncados, mín 0).

    Aceita `created_at` como str ISO ou datetime. Se naïve, assume UTC.
    """
    if isinstance(created_at, str):
        s = created_at.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return 0
    elif isinstance(created_at, datetime):
        dt = created_at
    else:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta_seconds = (now - dt).total_seconds()
    days = int(delta_seconds // 86400)
    return max(0, days)


def compute_sla_status(sla_days: int) -> str:
    for upper, status in _SLA_BANDS:
        if sla_days <= upper:
            return status
    return "critical"


def annotate_event_with_sla(event: dict, *, now: Optional[datetime] = None) -> dict:
    """Anexa `sla_days`, `sla_status`, `sla_version` ao evento (in-place).

    Apenas faz sentido para eventos com `approval_status == "pending"`.
    Para outros status, marca `sla_status = "n/a"` mas mantém `sla_days` informativo.
    """
    days = compute_sla_days(event.get("created_at"), now=now)
    event["sla_days"] = days
    event["sla_version"] = SLA_VERSION
    if event.get("approval_status") == "pending":
        event["sla_status"] = compute_sla_status(days)
    else:
        event["sla_status"] = "n/a"
    return event
