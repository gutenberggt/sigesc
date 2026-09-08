"""S5.5 — governança do router de Intervenções Curriculares.

Substitui apenas os endpoints operacionais de alerta/inbox do router legado,
preservando ranking e plano de ação enquanto esses consumidores auxiliares não
forem redesenhados. O feed S5.5 é sempre tenant-scoped; Super Administrador pode
consultá-lo somente dentro da mantenedora explicitamente selecionada, mas não
recebe notificações ativas.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from typing import Any, Optional

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, HTTPException, Query, Request

from auth_middleware import AuthMiddleware
from services.intervention_detector import run_intervention_detection
from services.plano_acao_ai import invalidate_ai_plans_for_school
from tenant_scope import INVALID_TENANT_SENTINEL, get_mantenedora_scope

POLICY_VERSION = "coverage-alert-v1"

MANAGEMENT_VIEW_ROLES = [
    "super_admin",
    "admin",
    "gerente",
    "semed",
    "semed1",
    "semed2",
    "semed3",
    "coordenador",
    "apoio_pedagogico",
    "diretor",
    "secretario",
]
GLOBAL_FEED_ROLES = {
    "super_admin",
    "admin",
    "gerente",
    "semed",
    "semed1",
    "semed2",
    "semed3",
}

# Somente estes contratos são substituídos. Ranking/plano-ação permanecem no
# router legado para não ampliar o escopo da S5.5.
CORE_ROUTE_KEYS = {
    ("/intervencoes", "GET"),
    ("/intervencoes/{alert_id}/resolve", "POST"),
    ("/intervencoes/run-detection", "POST"),
    ("/intervencoes/notifications", "GET"),
    ("/intervencoes/notifications/read-all", "POST"),
    ("/intervencoes/notifications/{notif_id}/read", "POST"),
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _tenant_id(user: dict, request: Request) -> str:
    value = get_mantenedora_scope(user, request)
    if not value or value == INVALID_TENANT_SENTINEL:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INTERVENTION_TENANT_REQUIRED",
                "message": "Selecione uma mantenedora para consultar intervenções curriculares.",
            },
        )
    return _norm(value)


def _school_ids(user: dict) -> set[str]:
    values = {_norm(v) for v in (user.get("school_ids") or []) if _norm(v)}
    if _norm(user.get("school_id")):
        values.add(_norm(user.get("school_id")))
    for link in user.get("school_links") or []:
        sid = _norm((link or {}).get("school_id"))
        if sid:
            values.add(sid)
    return values


def _scoped_feed_filter(
    user: dict,
    tenant_id: str,
    *,
    school_id: Optional[str],
    class_id: Optional[str],
    include_resolved: bool,
) -> dict:
    filt: dict[str, Any] = {
        "mantenedora_id": tenant_id,
        "policy_version": POLICY_VERSION,
    }
    if not include_resolved:
        filt["resolved_at"] = None
    if class_id:
        filt["class_id"] = class_id

    role = _norm(user.get("role"))
    if role not in GLOBAL_FEED_ROLES:
        allowed = _school_ids(user)
        if school_id and school_id not in allowed:
            raise HTTPException(403, "Escola fora do escopo do usuário")
        if school_id:
            filt["school_id"] = school_id
        elif allowed:
            filt["school_id"] = {"$in": sorted(allowed)}
        else:
            filt["school_id"] = {"$in": []}
    elif school_id:
        filt["school_id"] = school_id
    return filt


def build_interventions_s5_router(db) -> APIRouter:
    router = APIRouter(prefix="/intervencoes", tags=["Intervenções"])

    @router.get("")
    async def list_interventions(
        request: Request,
        school_id: Optional[str] = None,
        class_id: Optional[str] = None,
        include_resolved: bool = False,
        limit: int = Query(200, le=500),
    ):
        user = await AuthMiddleware.require_roles(MANAGEMENT_VIEW_ROLES)(request)
        tenant = _tenant_id(user, request)
        filt = _scoped_feed_filter(
            user,
            tenant,
            school_id=school_id,
            class_id=class_id,
            include_resolved=include_resolved,
        )
        items = await (
            db.intervention_alerts.find(filt, {"_id": 0})
            .sort([("severity_rank", -1), ("first_detected_at", 1)])
            .limit(limit)
        ).to_list(length=limit)

        active_filter = {**filt, "resolved_at": None}
        # `include_resolved=true` não deve contaminar o resumo dos ativos.
        if include_resolved:
            active_filter.pop("resolved_at", None)
            active_filter["resolved_at"] = None
        summary = {
            "total_active": await db.intervention_alerts.count_documents(active_filter),
            "grave": await db.intervention_alerts.count_documents({**active_filter, "severity": "grave"}),
            "informativo": await db.intervention_alerts.count_documents(
                {**active_filter, "severity": "informativo"}
            ),
        }
        return {"items": items, "summary": summary, "policy_version": POLICY_VERSION}

    @router.post("/run-detection")
    async def trigger_detection(request: Request, academic_year: Optional[int] = None):
        user = await AuthMiddleware.require_roles(["super_admin", "admin"])(request)
        tenant = _tenant_id(user, request)
        stats = await run_intervention_detection(
            db,
            academic_year=academic_year,
            mantenedora_id=tenant,
        )
        return {"ok": True, **stats}

    @router.post("/notifications/read-all")
    async def mark_all_read(request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") == "super_admin":
            return {"ok": True, "updated": 0}
        tenant = _tenant_id(user, request)
        result = await db.intervention_notifications.update_many(
            {
                "user_id": user["id"],
                "mantenedora_id": tenant,
                "policy_version": POLICY_VERSION,
                "read": False,
            },
            {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True, "updated": result.modified_count}

    @router.get("/notifications")
    async def my_notifications(request: Request, limit: int = Query(30, le=200)):
        user = await AuthMiddleware.get_current_user(request)
        # Super Administrador consulta o feed, mas não participa da audiência ativa.
        if user.get("role") == "super_admin":
            return {"items": [], "unread": 0, "policy_version": POLICY_VERSION}
        tenant = _tenant_id(user, request)
        filt = {
            "user_id": user["id"],
            "mantenedora_id": tenant,
            "policy_version": POLICY_VERSION,
        }
        items = await (
            db.intervention_notifications.find(filt, {"_id": 0})
            .sort([("read", 1), ("created_at", -1)])
            .limit(limit)
        ).to_list(length=limit)
        unread = await db.intervention_notifications.count_documents({**filt, "read": False})
        return {"items": items, "unread": unread, "policy_version": POLICY_VERSION}

    @router.post("/notifications/{notif_id}/read")
    async def mark_read(notif_id: str, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") == "super_admin":
            return {"ok": True}
        tenant = _tenant_id(user, request)
        await db.intervention_notifications.update_one(
            {
                "id": notif_id,
                "user_id": user["id"],
                "mantenedora_id": tenant,
                "policy_version": POLICY_VERSION,
            },
            {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True}

    @router.post("/{alert_id}/resolve")
    async def resolve_intervention(alert_id: str, request: Request):
        user = await AuthMiddleware.require_roles(MANAGEMENT_VIEW_ROLES)(request)
        tenant = _tenant_id(user, request)
        alert = await db.intervention_alerts.find_one(
            {
                "id": alert_id,
                "mantenedora_id": tenant,
                "policy_version": POLICY_VERSION,
                "resolved_at": None,
            },
            {"_id": 0},
        )
        if not alert:
            raise HTTPException(404, "Alerta não encontrado ou já resolvido")
        if user.get("role") not in GLOBAL_FEED_ROLES:
            allowed = _school_ids(user)
            if alert.get("school_id") not in allowed:
                raise HTTPException(403, "Alerta fora do escopo da escola")

        resolved_at = datetime.now(timezone.utc).isoformat()
        result = await db.intervention_alerts.update_one(
            {"id": alert_id, "mantenedora_id": tenant, "resolved_at": None},
            {"$set": {
                "resolved_at": resolved_at,
                "resolution_reason": "resolucao_manual_informativa",
                "resolved_by": user.get("email") or user.get("id"),
                "updated_at": resolved_at,
            }},
        )
        if result.matched_count == 0:
            raise HTTPException(404, "Alerta não encontrado ou já resolvido")
        await db.intervention_alert_events.insert_one({
            "id": f"manual_{alert_id}_{int(datetime.now(timezone.utc).timestamp())}",
            "alert_id": alert_id,
            "mantenedora_id": tenant,
            "school_id": alert.get("school_id"),
            "class_id": alert.get("class_id"),
            "component_id": alert.get("component_id"),
            "ano_letivo": alert.get("ano_letivo"),
            "bimestre": alert.get("bimestre"),
            "event_type": "manual_resolved",
            "policy_version": POLICY_VERSION,
            "actor_id": user.get("id"),
            "created_at": resolved_at,
        })
        if alert.get("school_id"):
            await invalidate_ai_plans_for_school(db, school_id=alert["school_id"])
        return {"ok": True}

    return router


def _route_is_replaced(route) -> bool:
    path = getattr(route, "path", "")
    methods = set(getattr(route, "methods", set()) or set())
    return any(path == expected_path and method in methods for expected_path, method in CORE_ROUTE_KEYS)


def install_interventions_coverage_s5_setup(interventions_mod: Any) -> None:
    """Envolve o setup legado sem reescrever ranking/plano de ação."""
    if getattr(interventions_mod, "_coverage_s5_installed", False):
        return
    original_setup = interventions_mod.setup_router

    @wraps(original_setup)
    def setup_router(db, **kwargs):
        legacy_router = original_setup(db, **kwargs)
        aggregate = APIRouter()
        aggregate.include_router(build_interventions_s5_router(db))
        for route in legacy_router.routes:
            if not _route_is_replaced(route):
                aggregate.routes.append(route)

        # O scheduler legado já foi criado pelo setup original. Apenas troca sua
        # cadência de semanal para diária; o callable permanece o mesmo e agora
        # delega ao detector S5.5 idempotente.
        scheduler = getattr(interventions_mod, "_scheduler", None)
        if scheduler is not None:
            try:
                scheduler.reschedule_job(
                    "interventions_weekly",
                    trigger=CronTrigger(hour=7, minute=0, timezone="UTC"),
                )
            except Exception:
                # Em contextos de import/teste sem event loop o próprio legado já
                # trata a ausência do scheduler. Não cria execução paralela.
                pass
        return aggregate

    interventions_mod.setup_router = setup_router
    interventions_mod._coverage_s5_installed = True
