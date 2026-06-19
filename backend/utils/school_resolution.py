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


# ===========================================================================
# ESCOPO DE ESCOLA POR PERÍODO (serviço central p/ relatórios/analytics)
# ===========================================================================
def _to_list(school_ids) -> List[str]:
    if school_ids is None:
        return []
    return [school_ids] if isinstance(school_ids, str) else list(school_ids)


async def get_school_scope_for_period(db, school_ids, start_date, end_date) -> Dict[str, Any]:
    """Serviço CENTRAL de escopo temporal por período.

    Retorna as turmas (e janelas de data) que pertenceram a `school_ids` durante
    `[start_date, end_date]`, honrando `classes.school_history[]`. Usado por
    relatórios com registros datados (ex.: frequência por `date`).

    Retorno:
        {
          "fully_in":  [class_id, ...],                  # período inteiro na escola
          "partial":   [{class_id, date_gte, date_lt}],  # apenas sub-janela na escola
          "all_class_ids": [...],
        }
    """
    schools = _to_list(school_ids)
    school_set = set(schools)
    candidates = await db.classes.find(
        {"$or": [
            {"school_id": {"$in": schools}},
            {"school_history.school_id": {"$in": schools}},
        ]},
        {"_id": 0, "id": 1, "school_id": 1, "school_history": 1},
    ).to_list(None)

    ps = _parse(start_date)
    pe = _parse(end_date)
    fully_in: List[str] = []
    partial: List[Dict] = []

    for c in candidates:
        hist = c.get("school_history")
        if not hist:
            if c.get("school_id") in school_set:
                fully_in.append(c["id"])
            continue
        segs = [s for s in resolve_school_period(hist, start_date, end_date)
                if s.get("school_id") in school_set]
        if not segs:
            continue
        covers_full = False
        if len(segs) == 1:
            ss = _parse(segs[0].get("start_date"))
            se = _parse(segs[0].get("end_date"))
            starts_ok = ss is None or (ps is not None and ss <= ps)
            ends_ok = se is None or (pe is not None and se >= pe)
            covers_full = starts_ok and ends_ok
        if covers_full:
            fully_in.append(c["id"])
        else:
            for s in segs:
                partial.append({"class_id": c["id"],
                                "date_gte": s.get("start_date"),
                                "date_lt": s.get("end_date")})

    return {"fully_in": fully_in, "partial": partial,
            "all_class_ids": fully_in + [p["class_id"] for p in partial]}


def school_scope_to_date_match(scope: Dict[str, Any], date_field: str = "date") -> Dict:
    """Converte o escopo em um `$match` Mongo para uma coleção com `class_id` +
    campo de data string `YYYY-MM-DD` (ex.: attendance). Janelas parciais
    aplicam restrição de data half-open `[gte, lt)`."""
    ors: List[Dict] = []
    if scope.get("fully_in"):
        ors.append({"class_id": {"$in": scope["fully_in"]}})
    for p in scope.get("partial", []):
        clause: Dict[str, Any] = {"class_id": p["class_id"]}
        rng: Dict[str, str] = {}
        if p.get("date_gte"):
            rng["$gte"] = str(p["date_gte"])[:10]
        if p.get("date_lt"):
            rng["$lt"] = str(p["date_lt"])[:10]
        if rng:
            clause[date_field] = rng
        ors.append(clause)
    if not ors:
        return {"class_id": {"$in": ["__none__"]}}
    return ors[0] if len(ors) == 1 else {"$or": ors}


async def get_school_class_ids_at(
    db, school_ids, reference_date, extra_class_filter: Optional[Dict] = None,
) -> List[str]:
    """`class_id`s cuja atribuição temporal (`school_history`) recai em
    `school_ids` na `reference_date`. Para relatórios ANO-BASE (ex.: notas, que
    têm `academic_year` mas não data fina por registro). Política recomendada:
    `reference_date = f"{year}-01-01"` (escola onde o ano foi conduzido)."""
    schools = _to_list(school_ids)
    school_set = set(schools)
    q: Dict[str, Any] = {"$or": [
        {"school_id": {"$in": schools}},
        {"school_history.school_id": {"$in": schools}},
    ]}
    if extra_class_filter:
        q = {"$and": [q, extra_class_filter]}
    out: List[str] = []
    async for c in db.classes.find(
        q, {"_id": 0, "id": 1, "school_id": 1, "school_history": 1}
    ):
        sid = resolve_school_at(c.get("school_history"), reference_date, c.get("school_id"))
        if sid in school_set:
            out.append(c["id"])
    return out
