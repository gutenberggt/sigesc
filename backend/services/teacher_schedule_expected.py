"""
Aulas previstas por componente (grade horária) — usado no Desempenho dos Professores.

Reutiliza a MESMA fonte de verdade do Diário:
  - `teacher_class_assignments` (modelo novo, com `weekly_slots`) ou
  - fallback `legacy_schedule_bridge.build_assignments_from_legacy` (grade legacy).

Expande os slots semanais sobre os dias letivos do período (respeitando
feriados/recessos e a rotação de sábado letivo) e conta, por componente,
quantas aulas eram esperadas. Também devolve o total de dias letivos
distintos do período (para o regime de regência/diário — Anos Iniciais).
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
    """Retorna {'by_component': {course_id: qtd_aulas_previstas}, 'letivo_days': int}."""
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

    by_component: dict = {}
    letivo_days = 0

    for day in _daterange(d_from, d_to):
        iso = day.isoformat()
        blocked = iso in non_school_days and iso not in explicit_school_days
        if blocked:
            continue
        eff_wd = saturday_map.get(iso, day.isoweekday())
        # Domingo (7) nunca é letivo; sábado (6) só se estiver no mapa de sábados letivos.
        if day.isoweekday() == 7:
            continue
        if day.isoweekday() == 6 and iso not in saturday_map:
            continue
        letivo_days += 1

    for a in assignments:
        comp = a.get("component_id") or a.get("course_id")
        for slot in a.get("weekly_slots", []) or []:
            wd = slot.get("weekday")
            aula = slot.get("aula_numero")
            if not wd or not aula:
                continue
            for day in _daterange(d_from, d_to):
                if not _active_on(a, day):
                    continue
                iso = day.isoformat()
                if iso in non_school_days and iso not in explicit_school_days:
                    continue
                eff_wd = saturday_map.get(iso, day.isoweekday())
                if eff_wd != wd:
                    continue
                by_component[comp] = by_component.get(comp, 0) + 1

    return {"by_component": by_component, "letivo_days": letivo_days}
