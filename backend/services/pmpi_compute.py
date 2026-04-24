"""
Service compartilhado para cálculo de KPIs do PMPI-GE.

Extraído de routers/pmpi.py para ser reusado por:
- routers/pmpi_engine.py (motor de alertas + metas)
- routers/pmpi_ai.py (IA preditiva, ranking, cron)

Todos os cálculos usam estratégia **school_id com fallback para class_id**,
pois em produção collections como `grades`, `learning_objects` e `attendance`
podem NÃO ter o campo `school_id` — apenas `class_id`.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional


async def _get_class_ids(current_db, school_id: str) -> list:
    """Retorna lista de IDs de turmas vinculadas à escola."""
    ids = []
    try:
        async for c in current_db.classes.find(
            {"school_id": school_id}, {"_id": 0, "id": 1}
        ):
            if c.get("id"):
                ids.append(c["id"])
    except Exception:
        pass
    return ids


async def _count_with_fallback(current_db, coll: str, school_id: str,
                                class_ids: list, extra_match: Optional[dict] = None) -> int:
    """Conta docs filtrando por school_id; se 0, repete com class_id ∈ class_ids."""
    extra = extra_match or {}
    try:
        n = await current_db[coll].count_documents({"school_id": school_id, **extra})
    except Exception:
        n = 0
    if n == 0 and class_ids:
        try:
            n = await current_db[coll].count_documents(
                {"class_id": {"$in": class_ids}, **extra}
            )
        except Exception:
            pass
    return n


async def compute_kpis_for_school(current_db, school_id: str, days_window: int = 30) -> dict:
    """Calcula os 5 KPIs para uma escola.
    
    Retorna dict {metric: {value, detail}} onde metric ∈
    {frequencia, aulas_lancadas, notas_lancadas, atrasos_dias, carga_horaria}.
    Status (verde/amarelo/vermelho) é adicionado pelo caller.
    """
    now = datetime.now(timezone.utc)
    window_start_iso = (now - timedelta(days=days_window)).isoformat()[:10]

    kpis = {
        "frequencia": {"value": None, "detail": {}},
        "aulas_lancadas": {"value": None, "detail": {}},
        "notas_lancadas": {"value": None, "detail": {}},
        "atrasos_dias": {"value": None, "detail": {}},
        "carga_horaria": {"value": None, "detail": {}},
    }

    class_ids = await _get_class_ids(current_db, school_id)

    # Academic year vigente (mais recente em classes)
    academic_year = now.year
    try:
        latest = await current_db.classes.find_one(
            {"school_id": school_id}, {"_id": 0, "academic_year": 1},
            sort=[("academic_year", -1)],
        )
        if latest and latest.get("academic_year"):
            academic_year = int(latest["academic_year"])
    except Exception:
        pass

    # 1. Frequência
    try:
        total_records = 0
        presentes = 0
        query = {"date": {"$gte": window_start_iso}}
        base_q = {"school_id": school_id, **query}
        first = await current_db.attendance.find_one(base_q, {"_id": 0, "id": 1})
        if first is None and class_ids:
            base_q = {"class_id": {"$in": class_ids}, **query}
            first = await current_db.attendance.find_one(base_q, {"_id": 0, "id": 1})
        if first is not None:
            async for att in current_db.attendance.find(base_q, {"_id": 0, "records": 1}).limit(2000):
                for rec in (att.get("records") or []):
                    total_records += 1
                    if (rec.get("status") or "").lower() in ("presente", "present", "p"):
                        presentes += 1
        if total_records > 0:
            kpis["frequencia"]["value"] = round(100.0 * presentes / total_records, 2)
            kpis["frequencia"]["detail"] = {
                "total_registros": total_records,
                "presentes": presentes,
                "janela_dias": days_window,
            }
    except Exception as e:
        kpis["frequencia"]["detail"] = {"erro": str(e)}

    # 2. Aulas lançadas
    try:
        lancadas = await _count_with_fallback(
            current_db, "learning_objects", school_id, class_ids,
            {"date": {"$gte": window_start_iso}},
        )
        n_classes = len(class_ids)
        previstas = max(n_classes * 5 * days_window * 5 // 7, 1)
        pct = 100.0 * lancadas / previstas if previstas else None
        kpis["aulas_lancadas"]["value"] = round(min(pct, 100.0), 2) if pct is not None else None
        kpis["aulas_lancadas"]["detail"] = {
            "lancadas": lancadas, "previstas_estimadas": previstas, "n_classes": n_classes,
        }
    except Exception as e:
        kpis["aulas_lancadas"]["detail"] = {"erro": str(e)}

    # 3. Notas lançadas (QUALQUER bimestre)
    try:
        total_enrol = await _count_with_fallback(
            current_db, "enrollments", school_id, class_ids,
            {"academic_year": academic_year,
             "status": {"$in": ["ativa", "active", "matriculado", "matriculada"]}},
        )
        if total_enrol == 0:
            total_enrol = await _count_with_fallback(
                current_db, "enrollments", school_id, class_ids,
                {"status": {"$in": ["ativa", "active", "matriculado", "matriculada"]}},
            )
        n_courses = await _count_with_fallback(
            current_db, "courses", school_id, class_ids,
        )
        expected = total_enrol * max(n_courses, 1)
        bim_or = [
            {"b1": {"$ne": None, "$exists": True}},
            {"b2": {"$ne": None, "$exists": True}},
            {"b3": {"$ne": None, "$exists": True}},
            {"b4": {"$ne": None, "$exists": True}},
        ]
        filled = await _count_with_fallback(
            current_db, "grades", school_id, class_ids,
            {"academic_year": academic_year, "$or": bim_or},
        )
        if filled == 0:
            filled = await _count_with_fallback(
                current_db, "grades", school_id, class_ids,
                {"$or": bim_or},
            )
        pct = 100.0 * filled / expected if expected else None
        kpis["notas_lancadas"]["value"] = round(min(pct, 100.0), 2) if pct is not None else None
        kpis["notas_lancadas"]["detail"] = {
            "preenchidas": filled, "esperado_estimado": expected,
            "total_matriculas": total_enrol, "n_courses": n_courses,
        }
    except Exception as e:
        kpis["notas_lancadas"]["detail"] = {"erro": str(e)}

    # 4. Atraso médio (dias)
    try:
        total_delay = 0
        n = 0
        query = {"date": {"$gte": window_start_iso}}
        find_filter = {"school_id": school_id, **query}
        first = await current_db.learning_objects.find_one(find_filter, {"_id": 0, "id": 1})
        if first is None and class_ids:
            find_filter = {"class_id": {"$in": class_ids}, **query}
        cursor = current_db.learning_objects.find(
            find_filter, {"_id": 0, "date": 1, "created_at": 1}
        ).limit(500)
        async for lo in cursor:
            try:
                date_s = lo.get("date")
                created = lo.get("created_at")
                if not date_s or not created:
                    continue
                d_date = datetime.fromisoformat(str(date_s)[:10])
                d_created = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                if d_created.tzinfo:
                    d_created = d_created.replace(tzinfo=None)
                delta = (d_created - d_date).days
                if delta >= 0:
                    total_delay += delta
                    n += 1
            except Exception:
                continue
        if n > 0:
            kpis["atrasos_dias"]["value"] = round(total_delay / n, 2)
            kpis["atrasos_dias"]["detail"] = {"amostras": n}
    except Exception as e:
        kpis["atrasos_dias"]["detail"] = {"erro": str(e)}

    # 5. Carga horária
    try:
        lo_match = {"school_id": school_id, "academic_year": academic_year}
        any_doc = await current_db.learning_objects.find_one(lo_match, {"_id": 0, "id": 1})
        if any_doc is None and class_ids:
            lo_match = {"class_id": {"$in": class_ids}, "academic_year": academic_year}
            any_doc = await current_db.learning_objects.find_one(lo_match, {"_id": 0, "id": 1})
            if any_doc is None:
                lo_match = {"class_id": {"$in": class_ids}}
        total_lo = 0
        async for row in current_db.learning_objects.aggregate([
            {"$match": lo_match},
            {"$group": {"_id": None, "total": {"$sum": "$number_of_classes"}}},
        ]):
            total_lo = row.get("total") or 0
        courses_match = {"school_id": school_id}
        first_c = await current_db.courses.find_one(courses_match, {"_id": 0, "id": 1})
        if first_c is None and class_ids:
            courses_match = {"class_id": {"$in": class_ids}}
        total_prev = 0
        async for row in current_db.courses.aggregate([
            {"$match": courses_match},
            {"$group": {"_id": None, "total": {"$sum": "$workload"}}},
        ]):
            total_prev = row.get("total") or 0
        prorated = (total_prev or 1) * (now.month / 12.0)
        pct = 100.0 * total_lo / prorated if prorated else None
        if pct is not None:
            kpis["carga_horaria"]["value"] = round(min(pct, 100.0), 2)
            kpis["carga_horaria"]["detail"] = {
                "aulas_dadas_total": total_lo,
                "previsto_proporcional": round(prorated, 1),
                "mes_referencia": now.month,
            }
    except Exception as e:
        kpis["carga_horaria"]["detail"] = {"erro": str(e)}

    return kpis
