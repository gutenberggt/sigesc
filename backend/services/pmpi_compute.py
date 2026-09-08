"""
Service compartilhado para cálculo de KPIs do PMPI-GE.

S5.3 preserva a semântica dos cinco KPIs, mas os três indicadores dependentes
de Conteúdo deixam de consultar ``learning_objects`` diretamente:
- aulas_lancadas -> contagem projetada S1/S2;
- atrasos_dias -> média projetada somente com proveniência integralmente comparável;
- carga_horaria -> soma projetada de ``number_of_classes``.

Frequência e notas permanecem nas fontes históricas próprias do PMPI.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from services.content_reporting_pmpi_s5 import get_pmpi_content_facts


async def _get_class_ids(current_db, school_id: str) -> list:
    """Retorna lista histórica de IDs de turmas vinculadas à escola."""
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


async def compute_kpis_for_school(
    current_db,
    school_id: str,
    days_window: int = 30,
    *,
    tenant_id: Optional[str] = None,
) -> dict:
    """Calcula os 5 KPIs para uma escola com Conteúdo projetado por S1/S2."""
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

    # Academic year vigente (mais recente em classes) — contrato histórico do PMPI.
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

    # 1. Frequência — inalterada.
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

    # Fatos de Conteúdo projetados uma única vez para os KPIs 2, 4 e 5.
    content_facts = None
    try:
        content_facts = await get_pmpi_content_facts(
            current_db,
            school_id=school_id,
            days_window=days_window,
            tenant_id=tenant_id,
            now=now,
        )
    except Exception as e:
        detail = {"erro": str(e), "source": "content_reporting_s1_s2"}
        kpis["aulas_lancadas"]["detail"] = dict(detail)
        kpis["atrasos_dias"]["detail"] = dict(detail)
        kpis["carga_horaria"]["detail"] = dict(detail)

    # 2. Aulas lançadas — mesma fórmula, novo numerador projetado.
    if content_facts is not None:
        try:
            lancadas = int(content_facts.get("record_count_window") or 0)
            n_classes = len(class_ids)
            previstas = max(n_classes * 5 * days_window * 5 // 7, 1)
            pct = 100.0 * lancadas / previstas if previstas else None
            kpis["aulas_lancadas"]["value"] = round(min(pct, 100.0), 2) if pct is not None else None
            kpis["aulas_lancadas"]["detail"] = {
                "lancadas": lancadas,
                "previstas_estimadas": previstas,
                "n_classes": n_classes,
                "source": "content_reporting_s1_s2",
            }
        except Exception as e:
            kpis["aulas_lancadas"]["detail"] = {"erro": str(e)}

    # 3. Notas lançadas — inalterada.
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
            "preenchidas": filled,
            "esperado_estimado": expected,
            "total_matriculas": total_enrol,
            "n_courses": n_courses,
        }
    except Exception as e:
        kpis["notas_lancadas"]["detail"] = {"erro": str(e)}

    # 4. Atraso médio — não calcula média parcial quando a proveniência é incompleta.
    if content_facts is not None:
        try:
            sample_count = int(content_facts.get("delay_sample_count") or 0)
            incomparable = int(content_facts.get("delay_incomparable_count") or 0)
            fully_comparable = bool(content_facts.get("delay_fully_comparable"))
            if fully_comparable and sample_count > 0:
                kpis["atrasos_dias"]["value"] = round(
                    float(content_facts.get("delay_average_days") or 0), 2
                )
                kpis["atrasos_dias"]["detail"] = {
                    "amostras": sample_count,
                    "source": "content_reporting_s1_s2",
                }
            elif incomparable > 0:
                kpis["atrasos_dias"]["detail"] = {
                    "provenance_incomparable": True,
                    "amostras_comparaveis": sample_count,
                    "registros_sem_proveniencia": incomparable,
                    "source": "content_reporting_s1_s2",
                }
        except Exception as e:
            kpis["atrasos_dias"]["detail"] = {"erro": str(e)}

    # 5. Carga horária — denominador histórico preservado; numerador projetado.
    if content_facts is not None:
        try:
            total_lo = float(content_facts.get("number_of_classes_sum_year") or 0)
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
                    "aulas_dadas_total": int(total_lo) if total_lo.is_integer() else total_lo,
                    "previsto_proporcional": round(prorated, 1),
                    "mes_referencia": now.month,
                    "source": "content_reporting_s1_s2",
                }
        except Exception as e:
            kpis["carga_horaria"]["detail"] = {"erro": str(e)}

    return kpis
