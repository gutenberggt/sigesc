"""
Router PMPI-GE (Política Municipal de Monitoramento, Prevenção e Intervenção).

Onda 1 (MVP) — Fundação:
- Cálculo de 5 KPIs por escola (frequência, aulas lançadas, notas lançadas,
  atrasos de lançamento, cumprimento de carga horária).
- Overview agregado para Painel do Secretário (SEMED) com semáforo
  verde/amarelo/vermelho.
- Endpoints leves de leitura.

S5.3:
- a fonte dos KPIs de Conteúdo é o serviço compartilhado ``pmpi_compute``;
- esse serviço usa S1/S2 para aulas lançadas, atraso e carga horária;
- ``learning_objects`` permanece visível apenas no endpoint diagnóstico legado.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from auth_middleware import AuthMiddleware
from services.pmpi_compute import compute_kpis_for_school
from tenant_scope import apply_tenant_filter

router = APIRouter(prefix="/pmpi", tags=["PMPI-GE"])


THRESHOLDS = {
    "frequencia": {"verde": 85.0, "amarelo": 70.0},
    "aulas_lancadas": {"verde": 90.0, "amarelo": 70.0},
    "notas_lancadas": {"verde": 90.0, "amarelo": 70.0},
    "atrasos_dias": {"verde": 2.0, "amarelo": 5.0},
    "carga_horaria": {"verde": 85.0, "amarelo": 65.0},
}


def _classify(metric: str, value: Optional[float]) -> str:
    """Retorna 'verde'|'amarelo'|'vermelho'|'sem_dados'."""
    if value is None:
        return "sem_dados"
    t = THRESHOLDS.get(metric)
    if not t:
        return "sem_dados"
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
        return await AuthMiddleware.require_permission(
            db, 'nav-semed-panel-button', ['admin']
        )(request)

    def _user_school_ids(user: dict) -> Optional[list]:
        role = user.get("role")
        if role in (
            "super_admin", "semed", "semed1", "semed2", "semed3", "gerente",
            "admin", "admin_teste",
        ):
            return None
        links = user.get("school_links") or []
        return [link.get("school_id") for link in links if link.get("school_id")]

    async def _compute_kpis_for_school(
        current_db, school_id: str, tenant_filter_base: dict, days_window: int = 30
    ) -> dict:
        tenant_id = tenant_filter_base.get("mantenedora_id")
        kpis = await compute_kpis_for_school(
            current_db,
            school_id,
            days_window=days_window,
            tenant_id=tenant_id,
        )
        for metric, value in kpis.items():
            value["status"] = _classify(metric, value.get("value"))
        return kpis

    @router.get("/overview")
    async def overview(request: Request):
        await _require_admin_tier(request)
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        base_filter = apply_tenant_filter({}, user, request)
        user_schools = _user_school_ids(user)
        query = dict(base_filter)
        if user_schools is not None:
            query["id"] = {"$in": user_schools}
        schools = [
            school
            async for school in current_db.schools.find(
                query, {"_id": 0, "id": 1, "name": 1}
            )
        ]
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
        risk_count = {"verde": 0, "amarelo": 0, "vermelho": 0, "sem_dados": 0}
        for row in result:
            risk_count[row["risk"]] = risk_count.get(row["risk"], 0) + 1
        return {
            "schools": result,
            "totals": risk_count,
            "total_schools": len(result),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    @router.get("/kpis/{school_id}")
    async def school_kpis(school_id: str, request: Request, days: int = 30):
        await _require_admin_tier(request)
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        base_filter = apply_tenant_filter({}, user, request)
        school = await current_db.schools.find_one(
            {**base_filter, "id": school_id}, {"_id": 0, "id": 1, "name": 1}
        )
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")
        user_schools = _user_school_ids(user)
        if user_schools is not None and school_id not in user_schools:
            raise HTTPException(status_code=403, detail="Sem acesso a esta escola")
        kpis = await _compute_kpis_for_school(
            current_db, school_id, base_filter, days_window=days
        )
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
        await _require_admin_tier(request)
        await AuthMiddleware.get_current_user(request)
        return THRESHOLDS

    @router.get("/_diag/{school_id}")
    async def diag_school(school_id: str, request: Request):
        """Diagnóstico legado. Não é fonte de nenhum KPI S5.3."""
        await _require_admin_tier(request)
        user = await AuthMiddleware.get_current_user(request)
        current_db = user and _get_db(user)
        if current_db is None:
            raise HTTPException(status_code=500, detail="sem db")
        from datetime import timedelta as _td
        now = datetime.now(timezone.utc)
        window_start = (now - _td(days=30)).isoformat()[:10]
        sf = {"school_id": school_id}

        out = {
            "school_id": school_id,
            "window_start": window_start,
            "now": now.isoformat(),
            "samples": {},
            "counts": {},
            "stats": {},
            "warning": "learning_objects é exibido apenas como diagnóstico legado; KPIs usam S1/S2",
        }

        for coll in (
            "attendance", "learning_objects", "grades", "enrollments", "classes", "courses"
        ):
            try:
                out["counts"][coll] = await current_db[coll].count_documents(sf)
            except Exception as e:
                out["counts"][coll] = f"erro: {e}"

        try:
            sample = await current_db.attendance.find_one(sf, {"_id": 0})
            out["samples"]["attendance"] = sample
            dates = await current_db.attendance.distinct("date", sf)
            out["stats"]["attendance_dates_count"] = len(dates)
            out["stats"]["attendance_dates_sample"] = sorted(
                [str(d) for d in dates], reverse=True
            )[:5]
            out["stats"]["attendance_in_window"] = await current_db.attendance.count_documents({
                **sf, "date": {"$gte": window_start}
            })
        except Exception as e:
            out["samples"]["attendance"] = f"erro: {e}"

        try:
            sample = await current_db.learning_objects.find_one(sf, {"_id": 0})
            out["samples"]["learning_objects"] = sample
            dates = await current_db.learning_objects.distinct("date", sf)
            out["stats"]["lo_dates_count"] = len(dates)
            out["stats"]["lo_dates_sample"] = sorted(
                [str(d) for d in dates], reverse=True
            )[:5]
            out["stats"]["lo_in_window"] = await current_db.learning_objects.count_documents({
                **sf, "date": {"$gte": window_start}
            })
            years = await current_db.learning_objects.distinct("academic_year", sf)
            out["stats"]["lo_academic_years"] = sorted([y for y in years if y])
        except Exception as e:
            out["samples"]["learning_objects"] = f"erro: {e}"

        try:
            sample = await current_db.grades.find_one(sf, {"_id": 0})
            out["samples"]["grades"] = sample
            years = await current_db.grades.distinct("academic_year", sf)
            out["stats"]["grades_academic_years"] = sorted([y for y in years if y])
            for field in (
                "b1", "b2", "b3", "b4", "nota_b1", "nota_b2", "nota_b3", "nota_b4",
                "nota1", "nota2", "nota3", "nota4",
            ):
                try:
                    count = await current_db.grades.count_documents({
                        **sf, field: {"$ne": None, "$exists": True}
                    })
                    if count > 0:
                        out["stats"][f"grades_with_{field}"] = count
                except Exception:
                    pass
        except Exception as e:
            out["samples"]["grades"] = f"erro: {e}"

        try:
            sample = await current_db.classes.find_one(sf, {"_id": 0})
            out["samples"]["classes"] = sample
            years = await current_db.classes.distinct("academic_year", sf)
            out["stats"]["classes_academic_years"] = sorted([y for y in years if y])
        except Exception as e:
            out["samples"]["classes"] = f"erro: {e}"

        try:
            sample = await current_db.enrollments.find_one(sf, {"_id": 0})
            out["samples"]["enrollments"] = sample
            status_vals = await current_db.enrollments.distinct("status", sf)
            out["stats"]["enrollments_status_values"] = list(status_vals)[:10]
        except Exception as e:
            out["samples"]["enrollments"] = f"erro: {e}"

        return out

    return router
