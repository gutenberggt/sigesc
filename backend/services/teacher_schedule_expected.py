"""
Aulas previstas por componente (grade horária) — usado no Desempenho dos Professores.

Reutiliza a MESMA fonte de verdade do Diário:
  - `teacher_class_assignments` (modelo novo, com `weekly_slots`) ou
  - fallback `legacy_schedule_bridge.build_assignments_from_legacy` (grade legacy).

Expande os slots semanais sobre os dias letivos do período (respeitando
feriados/recessos e a rotação de sábado letivo) e devolve, por componente,
o CONJUNTO de datas em que havia aula prevista (component_dates). Também
devolve o conjunto de dias letivos do período (letivo_dates) para o regime
de regência/diário (Anos Iniciais). O numerador (lançamentos) é sempre
interseccionado com esses conjuntos, garantindo que a cobertura fique ⊆ 100%
e reflita apenas os dias efetivamente previstos.
"""
from __future__ import annotations

from datetime import datetime, timedelta


def _parse(s: str):
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def _daterange(d_from, d_to):
    cur = d_from
    while cur <= d_to:
        yield cur
        cur += timedelta(days=1)


def _active_on(a: dict, day) -> bool:
    vf = a.get("valid_from")
    if vf and day < _parse(vf):
        return False
    vu = a.get("valid_until")
    if vu is not None and day > _parse(vu):
        return False
    return True


async def compute_class_expected(
    db, klass: dict, period_from: str, period_to: str,
    non_school_days: dict, explicit_school_days: dict, saturday_map: dict,
) -> dict:
    """Retorna:
      {
        'letivo_dates': set[str]  — dias letivos (ISO) do período (regime diário),
        'letivo_days': int        — len(letivo_dates),
        'component_dates': {course_id: set[str]}  — datas com aula prevista por componente,
      }
    """
    class_id = klass.get("id")

    # Grade: modelo novo tem prioridade; senão, bridge legacy.
    assignments = await db.teacher_class_assignments.find(
        {
            "class_id": class_id,
            "deleted": False,
            "valid_from": {"$lte": period_to},
            "$or": [{"valid_until": None}, {"valid_until": {"$gte": period_from}}],
        },
        {"_id": 0},
    ).to_list(2000)
    if not assignments:
        from services.legacy_schedule_bridge import build_assignments_from_legacy
        assignments = await build_assignments_from_legacy(db, class_doc=klass)

    d_from = _parse(period_from)
    d_to = _parse(period_to)

    letivo_dates: set = set()
    for day in _daterange(d_from, d_to):
        iso = day.isoformat()
        if iso in non_school_days and iso not in explicit_school_days:
            continue
        # Domingo (7) nunca é letivo; sábado (6) só se for sábado letivo.
        if day.isoweekday() == 7:
            continue
        if day.isoweekday() == 6 and iso not in saturday_map:
            continue
        letivo_dates.add(iso)

    component_dates: dict = {}
    for a in assignments:
        comp = a.get("component_id") or a.get("course_id")
        weekdays = {slot.get("weekday") for slot in (a.get("weekly_slots") or [])
                    if slot.get("weekday") and slot.get("aula_numero")}
        if not comp or not weekdays:
            continue
        dates = component_dates.setdefault(comp, set())
        for day in _daterange(d_from, d_to):
            if not _active_on(a, day):
                continue
            iso = day.isoformat()
            if iso not in letivo_dates:
                continue
            eff_wd = saturday_map.get(iso, day.isoweekday())
            if eff_wd in weekdays:
                dates.add(iso)

    return {
        "letivo_dates": letivo_dates,
        "letivo_days": len(letivo_dates),
        "component_dates": component_dates,
    }
