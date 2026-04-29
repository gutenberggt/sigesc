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

    async def _require_admin_tier(request: Request):
        """Apr 2026: Painel do Secretário (rotas /pmpi/*) restrito a
        Super Administrador + Administração (admin/admin_teste/gerente)."""
        return await AuthMiddleware.require_roles(['admin'])(request)

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
        """Calcula os 5 KPIs para uma escola no período (últimos N dias).
        
        IMPORTANTE: `grades`, `learning_objects` e `attendance` podem NÃO ter o
        campo `school_id`. Nesses casos filtra-se por `class_id ∈ [classes da escola]`.
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=days_window)
        window_start_iso = window_start.isoformat()

        kpis = {
            "frequencia": {"value": None, "detail": {}},
            "aulas_lancadas": {"value": None, "detail": {}},
            "notas_lancadas": {"value": None, "detail": {}},
            "atrasos_dias": {"value": None, "detail": {}},
            "carga_horaria": {"value": None, "detail": {}},
        }

        # 0. Turmas da escola (base para filtrar dados que não têm school_id)
        class_ids = []
        try:
            async for c in current_db.classes.find({"school_id": school_id}, {"_id": 0, "id": 1}):
                if c.get("id"):
                    class_ids.append(c["id"])
        except Exception:
            pass

        # Filtros alternativos
        school_filter = {"school_id": school_id}
        class_filter = {"class_id": {"$in": class_ids}} if class_ids else None

        # Helper: busca documentos tentando school_id primeiro, class_id depois
        async def _count_with_fallback(coll, extra_match=None):
            extra = extra_match or {}
            total = 0
            # Primeiro tenta com school_id
            try:
                total = await current_db[coll].count_documents({**school_filter, **extra})
            except Exception:
                total = 0
            if total == 0 and class_filter:
                try:
                    total = await current_db[coll].count_documents({**class_filter, **extra})
                except Exception:
                    pass
            return total

        # ---- Auto-detecta academic_year vigente da escola ----
        academic_year = now.year
        try:
            latest_class = await current_db.classes.find_one(
                {"school_id": school_id}, {"_id": 0, "academic_year": 1},
                sort=[("academic_year", -1)],
            )
            if latest_class and latest_class.get("academic_year"):
                academic_year = int(latest_class["academic_year"])
        except Exception:
            pass

        # ---------------- 1. Frequência (% presença) ----------------
        try:
            total_records = 0
            presentes = 0
            # Procura attendance pela escola OU pelas turmas
            query = {"date": {"$gte": window_start_iso[:10]}}
            try:
                first = await current_db.attendance.find_one({**school_filter, **query}, {"_id": 0, "id": 1})
            except Exception:
                first = None
            if first is None and class_filter:
                try:
                    first = await current_db.attendance.find_one({**class_filter, **query}, {"_id": 0, "id": 1})
                    if first:
                        base_q = {**class_filter, **query}
                    else:
                        base_q = None
                except Exception:
                    base_q = None
            else:
                base_q = {**school_filter, **query} if first else None
            if base_q is not None:
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

        # ---------------- 2. % Aulas lançadas ----------------
        try:
            lancadas = await _count_with_fallback(
                "learning_objects", {"date": {"$gte": window_start_iso[:10]}}
            )
            n_classes = len(class_ids)
            previstas = max(n_classes * 5 * days_window * 5 // 7, 1)
            pct = 100.0 * lancadas / previstas if previstas else None
            kpis["aulas_lancadas"]["value"] = round(min(pct, 100.0), 2) if pct is not None else None
            kpis["aulas_lancadas"]["detail"] = {
                "lancadas": lancadas,
                "previstas_estimadas": previstas,
                "n_classes": n_classes,
            }
        except Exception as e:
            kpis["aulas_lancadas"]["detail"] = {"erro": str(e)}

        # ---------------- 3. % Notas lançadas (QUALQUER bimestre com dados) ----------------
        try:
            total_enrol = await _count_with_fallback("enrollments", {
                "academic_year": academic_year,
                "status": {"$in": ["ativa", "active", "matriculado", "matriculada"]},
            })
            if total_enrol == 0:
                total_enrol = await _count_with_fallback("enrollments", {
                    "status": {"$in": ["ativa", "active", "matriculado", "matriculada"]},
                })
            n_courses = await _count_with_fallback("courses")
            expected = total_enrol * max(n_courses, 1)
            grades_filter_extra = {
                "academic_year": academic_year,
                "$or": [
                    {"b1": {"$ne": None, "$exists": True}},
                    {"b2": {"$ne": None, "$exists": True}},
                    {"b3": {"$ne": None, "$exists": True}},
                    {"b4": {"$ne": None, "$exists": True}},
                ],
            }
            filled = await _count_with_fallback("grades", grades_filter_extra)
            if filled == 0:
                # Sem filtro de ano
                filled = await _count_with_fallback("grades", {
                    "$or": [
                        {"b1": {"$ne": None, "$exists": True}},
                        {"b2": {"$ne": None, "$exists": True}},
                        {"b3": {"$ne": None, "$exists": True}},
                        {"b4": {"$ne": None, "$exists": True}},
                    ],
                })
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

        # ---------------- 4. Atraso médio (dias) em lançamento de aulas ----------------
        try:
            total_delay = 0
            n = 0
            query = {"date": {"$gte": window_start_iso[:10]}}
            # Tenta school_id primeiro, class_id como fallback
            find_filter = {**school_filter, **query}
            first = await current_db.learning_objects.find_one(find_filter, {"_id": 0, "id": 1})
            if first is None and class_filter:
                find_filter = {**class_filter, **query}
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

        # ---------------- 5. % Carga horária cumprida ----------------
        try:
            # Tenta school_id → fallback class_id
            lo_match = {**school_filter, "academic_year": academic_year}
            any_with_school = await current_db.learning_objects.find_one(lo_match, {"_id": 0, "id": 1})
            if any_with_school is None and class_filter:
                lo_match = {**class_filter, "academic_year": academic_year}
                any_with_class = await current_db.learning_objects.find_one(lo_match, {"_id": 0, "id": 1})
                if any_with_class is None:
                    lo_match = dict(class_filter) if class_filter else school_filter
            total_lo = 0
            async for row in current_db.learning_objects.aggregate([
                {"$match": lo_match},
                {"$group": {"_id": None, "total": {"$sum": "$number_of_classes"}}},
            ]):
                total_lo = row.get("total") or 0
            # Courses da escola (com fallback class_id)
            courses_match = school_filter
            first_c = await current_db.courses.find_one(school_filter, {"_id": 0, "id": 1})
            if first_c is None and class_filter:
                courses_match = class_filter
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
        await _require_admin_tier(request)
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
        await _require_admin_tier(request)
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
        await _require_admin_tier(request)
        await AuthMiddleware.get_current_user(request)
        return THRESHOLDS

    @router.get("/_diag/{school_id}")
    async def diag_school(school_id: str, request: Request):
        """Diagnóstico completo dos dados de uma escola para debug de KPIs."""
        await _require_admin_tier(request)
        user = await AuthMiddleware.get_current_user(request)
        current_db = user and _get_db(user)
        if current_db is None:
            raise HTTPException(status_code=500, detail="sem db")
        from datetime import timedelta as _td
        now = datetime.now(timezone.utc)
        window_start = (now - _td(days=30)).isoformat()[:10]
        sf = {"school_id": school_id}

        out = {"school_id": school_id, "window_start": window_start,
               "now": now.isoformat(), "samples": {}, "counts": {}, "stats": {}}

        # Counts por collection
        for coll in ("attendance", "learning_objects", "grades", "enrollments",
                     "classes", "courses"):
            try:
                out["counts"][coll] = await current_db[coll].count_documents(sf)
            except Exception as e:
                out["counts"][coll] = f"erro: {e}"

        # Attendance - sample + dates distintas
        try:
            sample = await current_db.attendance.find_one(sf, {"_id": 0})
            out["samples"]["attendance"] = sample
            dates = await current_db.attendance.distinct("date", sf)
            out["stats"]["attendance_dates_count"] = len(dates)
            out["stats"]["attendance_dates_sample"] = sorted([str(d) for d in dates], reverse=True)[:5]
            out["stats"]["attendance_in_window"] = await current_db.attendance.count_documents({
                **sf, "date": {"$gte": window_start}
            })
        except Exception as e:
            out["samples"]["attendance"] = f"erro: {e}"

        # Learning objects
        try:
            sample = await current_db.learning_objects.find_one(sf, {"_id": 0})
            out["samples"]["learning_objects"] = sample
            dates = await current_db.learning_objects.distinct("date", sf)
            out["stats"]["lo_dates_count"] = len(dates)
            out["stats"]["lo_dates_sample"] = sorted([str(d) for d in dates], reverse=True)[:5]
            out["stats"]["lo_in_window"] = await current_db.learning_objects.count_documents({
                **sf, "date": {"$gte": window_start}
            })
            # Também academic_year distintos
            years = await current_db.learning_objects.distinct("academic_year", sf)
            out["stats"]["lo_academic_years"] = sorted([y for y in years if y])
        except Exception as e:
            out["samples"]["learning_objects"] = f"erro: {e}"

        # Grades
        try:
            sample = await current_db.grades.find_one(sf, {"_id": 0})
            out["samples"]["grades"] = sample
            years = await current_db.grades.distinct("academic_year", sf)
            out["stats"]["grades_academic_years"] = sorted([y for y in years if y])
            # Conta por campo de bimestre
            for field in ("b1", "b2", "b3", "b4",
                          "nota_b1", "nota_b2", "nota_b3", "nota_b4",
                          "nota1", "nota2", "nota3", "nota4"):
                try:
                    n = await current_db.grades.count_documents({
                        **sf, field: {"$ne": None, "$exists": True}
                    })
                    if n > 0:
                        out["stats"][f"grades_with_{field}"] = n
                except Exception:
                    pass
        except Exception as e:
            out["samples"]["grades"] = f"erro: {e}"

        # Classes
        try:
            sample = await current_db.classes.find_one(sf, {"_id": 0})
            out["samples"]["classes"] = sample
            years = await current_db.classes.distinct("academic_year", sf)
            out["stats"]["classes_academic_years"] = sorted([y for y in years if y])
        except Exception as e:
            out["samples"]["classes"] = f"erro: {e}"

        # Enrollments
        try:
            sample = await current_db.enrollments.find_one(sf, {"_id": 0})
            out["samples"]["enrollments"] = sample
            status_vals = await current_db.enrollments.distinct("status", sf)
            out["stats"]["enrollments_status_values"] = list(status_vals)[:10]
        except Exception as e:
            out["samples"]["enrollments"] = f"erro: {e}"

        return out

    return router
