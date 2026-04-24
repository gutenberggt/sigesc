"""
Router PMPI-GE (Política Municipal de Monitoramento, Prevenção e Intervenção).

Onda 1 (MVP) — Fundação:
- Cálculo de 5 KPIs por escola (frequência, aulas lançadas, notas lançadas,
  atrasos de lançamento, cumprimento de carga horária).
- Overview agregado para Painel do Secretário (SEMED) com semáforo
  verde/amarelo/vermelho.
- Endpoints leves de leitura. Cálculo on-demand; cache posterior ficará a
  cargo da Onda 2 (cron diário).

Regras de escopo:
- super_admin / semed / gerente: enxerga todas as escolas da mantenedora ativa.
- diretor / demais papéis: enxerga apenas as escolas vinculadas em school_links.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request

from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, is_super_admin

router = APIRouter(prefix="/pmpi", tags=["PMPI-GE"])


# ----------------- Thresholds dos semáforos -----------------
# Valores percentuais (0..100). Acima do verde = OK. Entre amarelo e verde = atenção.
# Abaixo do amarelo = crítico.
THRESHOLDS = {
    "frequencia": {"verde": 85.0, "amarelo": 70.0},          # > 85% verde
    "aulas_lancadas": {"verde": 90.0, "amarelo": 70.0},
    "notas_lancadas": {"verde": 90.0, "amarelo": 70.0},
    "atrasos_dias": {"verde": 2.0, "amarelo": 5.0},          # MENOR é melhor (invertido)
    "carga_horaria": {"verde": 85.0, "amarelo": 65.0},
}


def _classify(metric: str, value: Optional[float]) -> str:
    """Retorna 'verde'|'amarelo'|'vermelho'|'sem_dados'."""
    if value is None:
        return "sem_dados"
    t = THRESHOLDS.get(metric)
    if not t:
        return "sem_dados"
    # Para atrasos_dias, quanto MENOR, melhor
    if metric == "atrasos_dias":
        if value <= t["verde"]:
            return "verde"
        if value <= t["amarelo"]:
            return "amarelo"
        return "vermelho"
    if value >= t["verde"]:
        return "verde"
    if value >= t["amarelo"]:
        return "amarelo"
    return "vermelho"


def _overall_risk(kpis: dict) -> str:
    """Agrega o pior caso dos 5 KPIs em um risco global."""
    statuses = [v.get("status", "sem_dados") for v in kpis.values()]
    if "vermelho" in statuses:
        return "vermelho"
    if "amarelo" in statuses:
        return "amarelo"
    if all(s == "verde" for s in statuses):
        return "verde"
    return "sem_dados"


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências injetadas."""

    def _get_db(user: dict):
        if user.get("is_sandbox"):
            return sandbox_db if sandbox_db else db
        return db

    def _user_school_ids(user: dict) -> Optional[list]:
        """Retorna IDs de escolas do usuário para escopo, ou None se acesso total."""
        role = user.get("role")
        if role in ("super_admin", "semed", "semed1", "semed2", "semed3", "gerente",
                    "admin", "admin_teste"):
            return None  # acesso a todas as escolas do tenant
        links = user.get("school_links") or []
        return [link.get("school_id") for link in links if link.get("school_id")]

    async def _compute_kpis_for_school(
        current_db, school_id: str, tenant_filter_base: dict, days_window: int = 30
    ) -> dict:
        """Calcula os 5 KPIs para uma escola no período (últimos N dias)."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=days_window)
        window_start_iso = window_start.isoformat()
        academic_year = now.year

        kpis = {
            "frequencia": {"value": None, "detail": {}},
            "aulas_lancadas": {"value": None, "detail": {}},
            "notas_lancadas": {"value": None, "detail": {}},
            "atrasos_dias": {"value": None, "detail": {}},
            "carga_horaria": {"value": None, "detail": {}},
        }

        school_filter = dict(tenant_filter_base)
        school_filter["school_id"] = school_id

        # ---------------- 1. Frequência (% presença) ----------------
        try:
            total_records = 0
            presentes = 0
            cursor = current_db.attendance.find(
                {**school_filter, "date": {"$gte": window_start_iso[:10]}},
                {"_id": 0, "records": 1},
            ).limit(2000)
            async for att in cursor:
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

        # ---------------- 2. % Aulas lançadas ----------------
        # Previsto: contar aulas esperadas ≈ (class_schedules.slots_per_day × dias letivos)
        # Lançadas: count de learning_objects no período.
        try:
            lancadas = await current_db.learning_objects.count_documents({
                **school_filter,
                "date": {"$gte": window_start_iso[:10]},
            })
            # Fallback simples de previsão: nº de turmas × 5 aulas/dia × dias úteis na janela
            n_classes = await current_db.classes.count_documents({
                **school_filter, "academic_year": academic_year,
            })
            previstas = max(n_classes * 5 * days_window * 5 // 7, 1)  # ~5 aulas/dia, dias úteis
            pct = 100.0 * lancadas / previstas if previstas else None
            kpis["aulas_lancadas"]["value"] = round(min(pct, 100.0), 2) if pct is not None else None
            kpis["aulas_lancadas"]["detail"] = {
                "lancadas": lancadas, "previstas_estimadas": previstas,
            }
        except Exception as e:
            kpis["aulas_lancadas"]["detail"] = {"erro": str(e)}

        # ---------------- 3. % Notas lançadas (bimestre atual) ----------------
        try:
            month = now.month
            bimestre = (month - 1) // 3 + 1  # 1-4 aproximado
            bim_field = f"b{bimestre}"
            total_enrol = await current_db.enrollments.count_documents({
                **school_filter,
                "academic_year": academic_year,
                "status": {"$in": ["ativa", "active", "matriculado"]},
            })
            # Esperado: total_enrol × nº courses ativos na escola (aproximação)
            n_courses = await current_db.courses.count_documents({
                **school_filter,
            })
            expected = total_enrol * max(n_courses, 1)
            filled = await current_db.grades.count_documents({
                **school_filter,
                "academic_year": academic_year,
                bim_field: {"$ne": None, "$exists": True},
            })
            pct = 100.0 * filled / expected if expected else None
            kpis["notas_lancadas"]["value"] = round(min(pct, 100.0), 2) if pct is not None else None
            kpis["notas_lancadas"]["detail"] = {
                "bimestre": bimestre, "preenchidas": filled,
                "esperado_estimado": expected,
            }
        except Exception as e:
            kpis["notas_lancadas"]["detail"] = {"erro": str(e)}

        # ---------------- 4. Atraso médio (dias) em lançamento de aulas ----------------
        try:
            total_delay = 0
            n = 0
            cursor = current_db.learning_objects.find(
                {**school_filter, "date": {"$gte": window_start_iso[:10]}},
                {"_id": 0, "date": 1, "created_at": 1},
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

        # ---------------- 5. % Carga horária cumprida ----------------
        try:
            # Soma das number_of_classes de learning_objects no ano
            pipeline = [
                {"$match": {
                    **school_filter, "academic_year": academic_year,
                }},
                {"$group": {"_id": None, "total": {"$sum": "$number_of_classes"}}},
            ]
            total_lo = 0
            async for row in current_db.learning_objects.aggregate(pipeline):
                total_lo = row.get("total") or 0
            # Previsto: soma de workload dos courses da escola (aproximação)
            pipeline2 = [
                {"$match": school_filter},
                {"$group": {"_id": None, "total": {"$sum": "$workload"}}},
            ]
            total_prev = 0
            async for row in current_db.courses.aggregate(pipeline2):
                total_prev = row.get("total") or 0
            # Prorateado pelo mês atual (total/12 × mês)
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

        # Classifica cada KPI
        for metric, v in kpis.items():
            v["status"] = _classify(metric, v.get("value"))

        return kpis

    # ================ Endpoints ================

    @router.get("/overview")
    async def overview(request: Request):
        """Retorna lista de escolas com KPIs resumidos e risco global.
        Resposta: [{ school_id, school_name, kpis, risk }]
        """
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        base_filter = apply_tenant_filter({}, user, request)
        user_schools = _user_school_ids(user)
        query = dict(base_filter)
        if user_schools is not None:
            query["id"] = {"$in": user_schools}
        schools_cursor = current_db.schools.find(query, {"_id": 0, "id": 1, "name": 1})
        schools = [s async for s in schools_cursor]
        result = []
        for school in schools:
            sid = school.get("id")
            if not sid:
                continue
            kpis = await _compute_kpis_for_school(current_db, sid, base_filter)
            result.append({
                "school_id": sid,
                "school_name": school.get("name") or "Escola",
                "kpis": kpis,
                "risk": _overall_risk(kpis),
            })
        # Agregados de rede
        risk_count = {"verde": 0, "amarelo": 0, "vermelho": 0, "sem_dados": 0}
        for r in result:
            risk_count[r["risk"]] = risk_count.get(r["risk"], 0) + 1
        return {
            "schools": result,
            "totals": risk_count,
            "total_schools": len(result),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    @router.get("/kpis/{school_id}")
    async def school_kpis(school_id: str, request: Request, days: int = 30):
        """KPIs detalhados de uma escola específica."""
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        base_filter = apply_tenant_filter({}, user, request)
        # Confirma se escola pertence ao tenant
        school = await current_db.schools.find_one(
            {**base_filter, "id": school_id}, {"_id": 0, "id": 1, "name": 1}
        )
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")
        user_schools = _user_school_ids(user)
        if user_schools is not None and school_id not in user_schools:
            raise HTTPException(status_code=403, detail="Sem acesso a esta escola")
        kpis = await _compute_kpis_for_school(current_db, school_id, base_filter, days_window=days)
        return {
            "school_id": school_id,
            "school_name": school.get("name"),
            "kpis": kpis,
            "risk": _overall_risk(kpis),
            "thresholds": THRESHOLDS,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "window_days": days,
        }

    @router.get("/thresholds")
    async def get_thresholds(request: Request):
        """Retorna os thresholds usados para classificar verde/amarelo/vermelho."""
        await AuthMiddleware.get_current_user(request)
        return THRESHOLDS

    return router
