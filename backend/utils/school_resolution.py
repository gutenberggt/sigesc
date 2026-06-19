"""
Resolução TEMPORAL de escola (Fase 1.5 — Transferência Institucional).

Quando uma turma sofre re-homing institucional (Opção A), seu `school_id` é
sobrescrito para o destino e `classes.school_history[]` passa a guardar os
intervalos `{school_id, start_date, end_date}` por onde a turma passou.

Estes helpers são a ÚNICA fonte canônica para responder, em qualquer relatório
histórico/Censo: "a qual escola este dado pertencia NA DATA X?". Toda consulta
crítica deve usar estes helpers em vez de `classes.school_id` (que é o ATUAL).

Princípios:
  - Sem `school_history` → fallback no `school_id` atual (turma nunca transferida).
  - Intervalos `[start_date, end_date)`; `end_date=None` = vigência corrente.
  - Data anterior ao primeiro `start_date` → primeira escola (origem) — best-effort
    para registros legados cuja data antecede `class.created_at`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _parse(dt: Any) -> Optional[datetime]:
    """Converte ISO date/datetime (ou datetime) em datetime tz-aware (UTC)."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    s = str(dt).strip()
    if not s:
        return None
    try:
        if len(s) == 10:  # YYYY-MM-DD
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _sorted_intervals(school_history: List[Dict]) -> List[Dict]:
    return sorted(school_history, key=lambda h: _parse(h.get("start_date")) or _MIN)


def resolve_school_at(
    school_history: Optional[List[Dict]],
    reference_date: Any,
    fallback_school_id: Optional[str] = None,
) -> Optional[str]:
    """Retorna o `school_id` dono da turma na `reference_date`.

    Args:
        school_history: lista de `{school_id, start_date, end_date}` (de `classes`).
        reference_date: ISO date/datetime de referência.
        fallback_school_id: usado quando não há histórico (turma não transferida).
    """
    if not school_history:
        return fallback_school_id

    ref = _parse(reference_date)
    intervals = _sorted_intervals(school_history)

    if ref is None:
        # Sem data: usa a vigência corrente (end_date None) ou fallback.
        for h in intervals:
            if h.get("end_date") is None:
                return h.get("school_id")
        return intervals[-1].get("school_id") or fallback_school_id

    first_start = _parse(intervals[0].get("start_date"))
    if first_start and ref < first_start:
        return intervals[0].get("school_id")

    for h in intervals:
        start = _parse(h.get("start_date")) or _MIN
        end = _parse(h.get("end_date"))  # None = aberto
        if ref >= start and (end is None or ref < end):
            return h.get("school_id")

    # Após o último intervalo fechado → última escola conhecida.
    return intervals[-1].get("school_id") or fallback_school_id


def resolve_school_period(
    school_history: Optional[List[Dict]],
    start_date: Any,
    end_date: Any,
    fallback_school_id: Optional[str] = None,
) -> List[Dict]:
    """Retorna os segmentos `[{school_id, start_date, end_date}]` que intersectam
    o período `[start_date, end_date]`. Útil para relatórios por intervalo
    (ex.: frequência mensal que cruza o período da transferência).

    Sem histórico → um único segmento com o `fallback_school_id`.
    """
    if not school_history:
        return [{"school_id": fallback_school_id,
                 "start_date": start_date, "end_date": end_date}]

    ps = _parse(start_date)
    pe = _parse(end_date)
    segs: List[Dict] = []
    for h in _sorted_intervals(school_history):
        hs = _parse(h.get("start_date")) or _MIN
        he = _parse(h.get("end_date"))  # None = aberto

        # Interseção [hs, he) ∩ [ps, pe]
        if pe is not None and hs > pe:
            continue
        if he is not None and ps is not None and he <= ps:
            continue

        seg_start = max(hs, ps) if ps else hs
        if he is None:
            seg_end = pe
        elif pe is None:
            seg_end = he
        else:
            seg_end = min(he, pe)

        segs.append({
            "school_id": h.get("school_id"),
            "start_date": seg_start.isoformat() if seg_start else None,
            "end_date": seg_end.isoformat() if seg_end else None,
        })

    return segs or [{"school_id": fallback_school_id,
                     "start_date": start_date, "end_date": end_date}]


async def resolve_school_for_class_at(
    db, class_id: str, reference_date: Any,
    cache: Optional[Dict[str, Dict]] = None,
) -> Optional[str]:
    """Conveniência async: busca a turma e resolve a escola na data.

    `cache` (opcional) evita re-buscar a mesma turma em loops de relatório.
    """
    cls = cache.get(class_id) if cache is not None else None
    if cls is None:
        cls = await db.classes.find_one(
            {"id": class_id}, {"_id": 0, "school_id": 1, "school_history": 1}
        ) or {}
        if cache is not None:
            cache[class_id] = cls
    return resolve_school_at(
        cls.get("school_history"), reference_date,
        fallback_school_id=cls.get("school_id"),
    )
