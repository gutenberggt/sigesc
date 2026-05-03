"""Agendador de tarefas SIGESC (Sprint G3 — Fev/2026).

Inicia tarefas em background:
- Dia 1º de cada mês 06:00 UTC: gera Relatório Mensal Executivo do mês
  ANTERIOR para CADA mantenedora ativa e envia gatilho aos gestores
  (admin/gerente/secretario com email cadastrado).

A geração é IDEMPOTENTE — se executado mais de uma vez no mesmo período,
retorna o relatório existente (snapshot único por mantenedora+mês).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services import monthly_report_service as mr_svc
from services.email_service import send_email
from services.monthly_report_email import (render_monthly_report_email,
                                            report_url_for, verify_url_for)

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


_SYSTEM_USER = {
    "id": "system",
    "email": "system@sigesc",
    "role": "system",
}


async def run_monthly_reports_for_all_tenants(db, *, year: int, month: int) -> dict:
    """Executa a geração+envio para cada mantenedora ativa.

    Retorna estatísticas agregadas para logging.
    """
    tenants = await db.mantenedoras.find(
        {"$or": [{"status": "active"}, {"status": {"$exists": False}}]},
        {"_id": 0, "id": 1, "nome": 1},
    ).to_list(length=500)

    stats = {"total_tenants": len(tenants), "generated": 0, "emailed": 0, "errors": 0}

    for t in tenants:
        try:
            report = await mr_svc.generate_monthly_report(
                db,
                mantenedora_id=t["id"],
                year=year,
                month=month,
                user=_SYSTEM_USER,
                force=False,
            )
            stats["generated"] += 1

            # Coleta destinatários: admin/gerente/secretario da mantenedora com email
            recipients = await db.users.find(
                {
                    "mantenedora_id": t["id"],
                    "status": "active",
                    "role": {"$in": ["admin", "gerente", "secretario"]},
                    "email": {"$exists": True, "$ne": ""},
                },
                {"_id": 0, "email": 1},
            ).to_list(length=50)
            emails = list({u["email"] for u in recipients if u.get("email")})
            if not emails:
                logger.info("[cron] %s sem destinatários — pulando email", t.get("nome"))
                continue

            ai = report.get("ai") or {}
            bottom3 = (ai.get("ranking") or {}).get("bottom3") or []
            acoes = ai.get("acoes_prioritarias") or []
            n_alertas = (report.get("rede_summary") or {}).get("escolas_com_alertas_ativos") or 0
            verification_code = report.get("verification_code")
            verify_url = verify_url_for(verification_code) if verification_code else None

            subject, html, text = render_monthly_report_email(
                rede_nome=t.get("nome") or "Rede",
                year=year,
                month=month,
                risco=report.get("risco") or "medio",
                n_escolas_alerta=n_alertas,
                bottom3=bottom3,
                acoes_top3=acoes,
                report_url=report_url_for(report["id"]),
                verify_url=verify_url,
                verification_code=verification_code,
            )
            ok_recipients = []
            for to in emails:
                r = await send_email(to=to, subject=subject, html=html, text=text)
                if r.get("success"):
                    ok_recipients.append(to)
            if ok_recipients:
                await mr_svc.mark_email_sent(
                    db, report_id=report["id"], recipients=ok_recipients
                )
                stats["emailed"] += len(ok_recipients)
        except Exception as e:
            logger.exception("[cron] falha p/ mantenedora %s: %s", t.get("id"), e)
            stats["errors"] += 1

    logger.info("[cron] monthly_reports stats=%s", stats)
    return stats


async def _monthly_job(db) -> None:
    """Job disparado dia 1º — gera relatório do mês ANTERIOR para todos."""
    year, month = mr_svc._previous_month()
    logger.info("[cron] disparando geração de relatório mensal %02d/%d", month, year)
    await run_monthly_reports_for_all_tenants(db, year=year, month=month)


def start_scheduler(db) -> None:
    """Inicializa scheduler global (idempotente)."""
    global _scheduler
    if _scheduler is not None:
        return

    if os.environ.get("DISABLE_CRON") == "1":
        logger.info("[cron] DISABLE_CRON=1 — scheduler não iniciado")
        return

    _scheduler = AsyncIOScheduler(timezone="UTC")
    # Dia 1, 06:00 UTC (≈ 03:00 BRT). Hour 6 → 6h da manhã UTC.
    _scheduler.add_job(
        _monthly_job,
        CronTrigger(day=1, hour=6, minute=0),
        kwargs={"db": db},
        id="monthly_reports_job",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("[cron] scheduler iniciado — monthly_reports_job ativo (1º dia, 06:00 UTC)")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
