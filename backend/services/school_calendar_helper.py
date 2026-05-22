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
    school_id: str | None = None,
) -> dict:
    """Carrega o calendário letivo no período.

    Combina duas fontes:
      1. `calendario_letivo` — define os 4 bimestres do ano letivo.
         Qualquer data FORA dos 4 bimestres é considerada não-letiva
         automaticamente (recesso entre bimestres, antes do início, depois
         do fim do ano letivo).
      2. `calendar_events` — feriados/recessos pontuais e sábados letivos.

    Returns:
      {
        "non_school_days": dict[str, dict] — date_iso → {title, event_type},
        "explicit_school_days": dict[str, dict] — date_iso → {title, event_type},
      }
    """
    # ---------- Fonte 1: calendario_letivo (bimestres) ----------
    # Prioridade: school_id específico, depois mantenedora-wide (school_id=None)
    cal_doc = None
    if school_id:
        cal_doc = await db.calendario_letivo.find_one(
            {"ano_letivo": academic_year, "school_id": school_id},
            {"_id": 0},
        )
    if not cal_doc:
        cal_doc = await db.calendario_letivo.find_one(
            {"ano_letivo": academic_year, "school_id": None},
            {"_id": 0},
        )

    # Construir lista de intervalos letivos [(start_iso, end_iso), ...]
    letivo_intervals: list[tuple[str, str]] = []
    if cal_doc:
        for i in (1, 2, 3, 4):
            ini = cal_doc.get(f"bimestre_{i}_inicio")
            fim = cal_doc.get(f"bimestre_{i}_fim")
            if ini and fim:
                letivo_intervals.append((ini, fim))

    # Pré-computa: para cada dia do período, é letivo? (apenas se há bimestres)
    out_of_school_year: dict[str, dict] = {}
    if letivo_intervals:
        d_from = datetime.strptime(period_from, "%Y-%m-%d").date()
        d_to = datetime.strptime(period_to, "%Y-%m-%d").date()
        cur = d_from
        while cur <= d_to:
            iso = cur.isoformat()
            is_inside_bimestre = any(ini <= iso <= fim for ini, fim in letivo_intervals)
            if not is_inside_bimestre:
                out_of_school_year[iso] = {
                    "title": "Fora do período letivo",
                    "event_type": "fora_periodo_letivo",
                }
            cur += timedelta(days=1)

    # ---------- Fonte 2: calendar_events ----------
    query: dict = {"academic_year": academic_year}
    if mantenedora_id:
        query["$or"] = [
            {"mantenedora_id": mantenedora_id},
            {"mantenedora_id": {"$exists": False}},
            {"mantenedora_id": None},
        ]
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

    non_school_days: dict[str, dict] = dict(out_of_school_year)
    explicit_school_days: dict[str, dict] = {}

    for ev in events:
        etype = ev.get("event_type")
        dates = _expand_event_dates(ev.get("start_date"), ev.get("end_date"))
        meta = {"title": ev.get("title"), "event_type": etype}
        for d in dates:
            if d < period_from or d > period_to:
                continue
            if etype in NON_SCHOOL_EVENT_TYPES:
                non_school_days[d] = meta  # eventos pontuais sobrescrevem fora_periodo
            elif etype in EXPLICIT_SCHOOL_EVENT_TYPES:
                explicit_school_days[d] = meta

    # Sábado letivo PROMOVE: vence em colisão com qualquer non_school.
    for d in list(explicit_school_days.keys()):
        non_school_days.pop(d, None)

    return {
        "non_school_days": non_school_days,
        "explicit_school_days": explicit_school_days,
    }
