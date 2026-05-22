"""
School Calendar Helper — Fase 11 (Fev/2026).

Lê `calendar_events` (Gerenciamento de Eventos) e devolve quais datas do
período são:
  - non_school_days: feriados nacionais/estaduais/municipais + recessos
  - explicit_school_days: sábados letivos (override letivo)

Princípios:
  - Read-only. Pura. Sem mutação.
  - Eventos podem ter intervalo (start_date / end_date) — expandidos dia a dia.
  - Frontend NUNCA decide. Backend devolve a classificação institucional.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

NON_SCHOOL_EVENT_TYPES = {
    "feriado_nacional",
    "feriado_estadual",
    "feriado_municipal",
    "recesso_escolar",
}
EXPLICIT_SCHOOL_EVENT_TYPES = {
    "sabado_letivo",
}


def _expand_event_dates(start_date: str, end_date: str | None) -> Iterable[str]:
    """Expande um evento com intervalo dia-a-dia."""
    if not start_date:
        return []
    try:
        d_from = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        return []
    d_to = d_from
    if end_date:
        try:
            d_to = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            d_to = d_from
    out = []
    cur = d_from
    while cur <= d_to:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


async def load_school_calendar(
    db, *, academic_year: int, period_from: str, period_to: str,
    mantenedora_id: str | None = None,
) -> dict:
    """Carrega o calendário letivo no período.

    Returns:
      {
        "non_school_days": dict[str, dict] — date_iso → {title, event_type},
        "explicit_school_days": dict[str, dict] — date_iso → {title, event_type},
      }
    """
    query: dict = {"academic_year": academic_year}
    if mantenedora_id:
        # alguns documentos legacy podem não ter mantenedora_id; o filtro é opt-in
        query["$or"] = [
            {"mantenedora_id": mantenedora_id},
            {"mantenedora_id": {"$exists": False}},
            {"mantenedora_id": None},
        ]
    # Intersecta com o período: evento.start_date <= period_to AND
    # (evento.end_date >= period_from OR evento.end_date é null)
    query["start_date"] = {"$lte": period_to}
    query["$and"] = [
        {"$or": [
            {"end_date": None},
            {"end_date": {"$exists": False}},
            {"end_date": {"$gte": period_from}},
        ]}
    ]

    events = await db.calendar_events.find(
        query,
        {"_id": 0, "id": 1, "event_type": 1, "title": 1,
         "start_date": 1, "end_date": 1},
    ).to_list(2000)

    non_school_days: dict[str, dict] = {}
    explicit_school_days: dict[str, dict] = {}

    for ev in events:
        etype = ev.get("event_type")
        dates = _expand_event_dates(ev.get("start_date"), ev.get("end_date"))
        meta = {"title": ev.get("title"), "event_type": etype}
        for d in dates:
            if d < period_from or d > period_to:
                continue
            if etype in NON_SCHOOL_EVENT_TYPES:
                # 1ª ocorrência vence (event mais granular sobrescreve)
                non_school_days.setdefault(d, meta)
            elif etype in EXPLICIT_SCHOOL_EVENT_TYPES:
                explicit_school_days.setdefault(d, meta)

    # Sábado letivo PROMOVE: se a mesma data está nos dois, vence o sábado letivo.
    for d in list(explicit_school_days.keys()):
        non_school_days.pop(d, None)

    return {
        "non_school_days": non_school_days,
        "explicit_school_days": explicit_school_days,
    }
