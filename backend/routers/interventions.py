"""Intervenções Curriculares — Feed + Gerenciamento (Sprint C Feb 2026).

Endpoints:
  GET  /api/intervencoes                    — feed ativo para o gestor
  GET  /api/intervencoes/notifications      — inbox in-app do usuário logado
  POST /api/intervencoes/notifications/{id}/read — marcar lida
  POST /api/intervencoes/{id}/resolve       — marcar resolvida manualmente
  POST /api/intervencoes/run-detection      — trigger manual (debug/admin)

Scheduler: roda toda segunda-feira às 07:00 UTC.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from auth_middleware import AuthMiddleware
from services.intervention_detector import run_intervention_detection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intervencoes", tags=["Intervenções"])

_scheduler: Optional[AsyncIOScheduler] = None


def setup_router(db, **_kwargs):

    global _scheduler

    async def _auth_manager(request: Request):
        return await AuthMiddleware.require_roles(
            ['super_admin', 'admin', 'coordenador', 'apoio_pedagogico', 'diretor', 'secretario']
        )(request)

    async def _auth_any(request: Request):
        return await AuthMiddleware.get_current_user(request)

    # =================== FEED (gestão) ===================

    @router.get("")
    async def list_interventions(
        request: Request,
        school_id: Optional[str] = None,
        class_id: Optional[str] = None,
        include_resolved: bool = False,
        limit: int = Query(200, le=500),
    ):
        user = await _auth_manager(request)
        filt: dict = {} if include_resolved else {"resolved_at": None}
        if school_id:
            filt["school_id"] = school_id
        if class_id:
            filt["class_id"] = class_id
        # Escopo por usuário não-admin: suas escolas apenas
        if user.get('role') not in ('super_admin', 'admin', 'admin_teste', 'gerente'):
            user_schools = [s.get('school_id') for s in user.get('school_links') or []]
            if user_schools:
                filt["school_id"] = {"$in": user_schools} if not school_id else school_id
        cursor = (
            db.intervention_alerts.find(filt, {"_id": 0})
            # piores primeiro: nao_cumpre > fechado_critico > em_risco; dentro deles mais antigos
            .sort([("escalation_level", -1), ("first_detected_at", 1)])
            .limit(limit)
        )
        items = await cursor.to_list(length=limit)
        summary = {
            "total_active": await db.intervention_alerts.count_documents({"resolved_at": None}),
            "critical": await db.intervention_alerts.count_documents(
                {"resolved_at": None, "status": {"$in": ["nao_cumpre", "fechado_critico"]}}
            ),
            "level_3": await db.intervention_alerts.count_documents(
                {"resolved_at": None, "escalation_level": 3}
            ),
        }
        return {"items": items, "summary": summary}

    @router.post("/{alert_id}/resolve")
    async def resolve_intervention(alert_id: str, request: Request):
        user = await _auth_manager(request)
        r = await db.intervention_alerts.update_one(
            {"id": alert_id, "resolved_at": None},
            {"$set": {
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": user.get('email'),
            }},
        )
        if r.matched_count == 0:
            raise HTTPException(404, "Alerta não encontrado ou já resolvido")
        return {"ok": True}

    @router.post("/run-detection")
    async def trigger_detection(request: Request, academic_year: Optional[int] = None):
        """Trigger manual (uso admin/debug). Em produção, prefira o cron."""
        await AuthMiddleware.require_roles(['super_admin', 'admin'])(request)
        stats = await run_intervention_detection(db, academic_year=academic_year)
        return {"ok": True, **stats}

    # =================== INBOX IN-APP ===================

    @router.get("/notifications")
    async def my_notifications(request: Request, limit: int = Query(30, le=200)):
        user = await _auth_any(request)
        cursor = (
            db.intervention_notifications.find({"user_id": user['id']}, {"_id": 0})
            .sort([("read", 1), ("created_at", -1)])
            .limit(limit)
        )
        items = await cursor.to_list(length=limit)
        unread = await db.intervention_notifications.count_documents(
            {"user_id": user['id'], "read": False}
        )
        return {"items": items, "unread": unread}

    @router.post("/notifications/{notif_id}/read")
    async def mark_read(notif_id: str, request: Request):
        user = await _auth_any(request)
        await db.intervention_notifications.update_one(
            {"id": notif_id, "user_id": user['id']},
            {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True}

    @router.post("/notifications/read-all")
    async def mark_all_read(request: Request):
        user = await _auth_any(request)
        r = await db.intervention_notifications.update_many(
            {"user_id": user['id'], "read": False},
            {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True, "updated": r.modified_count}

    # =================== SCHEDULER ===================

    if _scheduler is None:
        _scheduler = AsyncIOScheduler()

        async def scheduled_job():
            logger.info("[interventions] Cron semanal disparado")
            try:
                stats = await run_intervention_detection(db)
                logger.info("[interventions] detecção OK: %s", stats)
            except Exception as e:
                logger.error("[interventions] falha na detecção semanal: %s", e)

        # Toda segunda-feira às 07:00 UTC
        _scheduler.add_job(
            scheduled_job,
            CronTrigger(day_of_week='mon', hour=7, minute=0, timezone='UTC'),
            id='interventions_weekly',
            replace_existing=True,
        )
        try:
            _scheduler.start()
            logger.info("[interventions] Scheduler iniciado (seg 07:00 UTC)")
        except Exception as e:
            logger.warning("[interventions] Scheduler não pôde iniciar: %s", e)

    return router
