"""Router Relatórios Mensais Executivos (Sprint G3 — Fev/2026).

Endpoints:
  POST   /api/monthly-reports/generate       — gera (ou retorna cache) {year, month, force?}
  GET    /api/monthly-reports                — lista (escopo por role)
  GET    /api/monthly-reports/{id}           — detalhes
  GET    /api/monthly-reports/{id}/pdf       — PDF executivo|auditor (reuses snapshot_pdf)
  POST   /api/monthly-reports/{id}/send-email— envia gatilho via Resend

Acesso: super_admin/admin/admin_teste/gerente/secretario.
Diretor/coordenador: 403 (relatório é de rede).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from services import monthly_report_service as mr_svc
from services import snapshot_service as snap_svc
from services.email_service import send_email
from services.monthly_report_email import (render_monthly_report_email,
                                            report_url_for, verify_url_for)
from services.snapshot_pdf import build_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/monthly-reports", tags=["Monthly Reports"])

_REPORT_ROLES = ("super_admin", "admin", "admin_teste", "gerente", "secretario")


class GenerateRequest(BaseModel):
    year: int = Field(..., ge=2020, le=2100)
    month: int = Field(..., ge=1, le=12)
    force: bool = False


class SendEmailRequest(BaseModel):
    recipients: list[str] = Field(..., min_length=1, max_length=20)


def setup_router(db, **_kwargs):

    async def _require_report_role(request: Request) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") not in _REPORT_ROLES:
            raise HTTPException(403, "Acesso restrito a relatórios mensais")
        return user

    def _resolve_mantenedora(user: dict) -> Optional[str]:
        """super_admin pode passar X-Mantenedora-Id (cross-tenant); demais usam o seu."""
        return user.get("mantenedora_id")

    @router.post("/generate")
    async def generate_report(body: GenerateRequest, request: Request):
        user = await _require_report_role(request)
        mantenedora_id = _resolve_mantenedora(user)
        try:
            doc = await mr_svc.generate_monthly_report(
                db,
                mantenedora_id=mantenedora_id,
                year=body.year,
                month=body.month,
                user=user,
                force=body.force,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        return doc

    @router.get("")
    async def list_reports(
        request: Request,
        limit: int = Query(24, ge=1, le=120),
    ):
        user = await _require_report_role(request)
        mantenedora_id = _resolve_mantenedora(user)
        items = await mr_svc.list_monthly_reports(
            db, mantenedora_id=mantenedora_id, limit=limit
        )
        return {"items": items, "total": len(items)}

    @router.get("/{report_id}")
    async def get_report(report_id: str, request: Request):
        user = await _require_report_role(request)
        doc = await mr_svc.get_monthly_report(db, report_id=report_id)
        if not doc:
            raise HTTPException(404, "Relatório não encontrado")
        if user.get("role") != "super_admin":
            if doc.get("mantenedora_id") != user.get("mantenedora_id"):
                raise HTTPException(403, "Fora do seu escopo")
        return doc

    @router.get("/{report_id}/pdf")
    async def report_pdf(
        report_id: str,
        request: Request,
        mode: str = Query("executive", pattern="^(executive|auditor)$"),
    ):
        user = await _require_report_role(request)
        report = await mr_svc.get_monthly_report(db, report_id=report_id)
        if not report:
            raise HTTPException(404, "Relatório não encontrado")
        if user.get("role") != "super_admin":
            if report.get("mantenedora_id") != user.get("mantenedora_id"):
                raise HTTPException(403, "Fora do seu escopo")

        snap = await db.ai_analysis_snapshots.find_one(
            {"id": report["snapshot_id"]}, {"_id": 0, "expires_at_dt": 0}
        )
        if not snap:
            raise HTTPException(404, "Snapshot do relatório não encontrado")

        # Adapta payload do snapshot para o build_pdf entender (espera school_name etc)
        snap.setdefault("verification_code", report.get("verification_code"))
        # Garante que o título do PDF aparece com nome da rede
        if isinstance(snap.get("payload_snapshot"), dict):
            rede = (snap["payload_snapshot"].get("rede") or {})
            snap["payload_snapshot"].setdefault(
                "school_name", rede.get("mantenedora_nome") or "Rede"
            )
            snap["payload_snapshot"].setdefault("period", rede.get("mes_label"))
        # ai_output do build_pdf espera analise_executiva/insight_historico/acoes etc
        # → mapeamos do nosso schema relatório mensal para o esperado:
        ai = snap.get("ai_output") or {}
        adapted = {
            "analise_executiva": ai.get("resumo_executivo"),
            "analise_evidencias": ai.get("evidencias") or [],
            "insight_historico": ai.get("diagnostico_causal"),
            "insight_evidencias": [],
            "recomendacoes_extra": [
                {
                    "titulo": a.get("acao"),
                    "descricao": a.get("justificativa"),
                    "prioridade": (1 if a.get("impacto") == "alto"
                                   else 2 if a.get("impacto") == "medio" else 3),
                    "impacto": a.get("impacto"),
                    "prazo_dias": a.get("prazo_dias"),
                    "responsavel": a.get("responsavel"),
                    "metrica_sucesso": "Escolas-alvo: " + ", ".join(a.get("escolas_alvo") or []),
                    "baseado_em": [],
                }
                for a in (ai.get("acoes_prioritarias") or [])
            ],
            "acoes_enriquecidas": {},
            # Campos extras nossos (build_pdf ignora desconhecidos)
            "_ranking": ai.get("ranking"),
            "_risco": ai.get("risco"),
        }
        snap["ai_output"] = adapted

        pdf_bytes = build_pdf(snap, mode=mode)
        filename = f"sigesc-relatorio-{report.get('month_label', '').replace('/', '-')}-{mode}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/{report_id}/send-email")
    async def send_report_email_endpoint(
        report_id: str, body: SendEmailRequest, request: Request,
    ):
        user = await _require_report_role(request)
        report = await mr_svc.get_monthly_report(db, report_id=report_id)
        if not report:
            raise HTTPException(404, "Relatório não encontrado")
        if user.get("role") != "super_admin":
            if report.get("mantenedora_id") != user.get("mantenedora_id"):
                raise HTTPException(403, "Fora do seu escopo")

        rede_nome = (report.get("rede_summary") or {}).get("mantenedora_nome") or "Rede"
        ai = report.get("ai") or {}
        bottom3 = (ai.get("ranking") or {}).get("bottom3") or []
        acoes_top3 = ai.get("acoes_prioritarias") or []
        risco = report.get("risco") or "medio"
        n_alertas = (report.get("rede_summary") or {}).get("escolas_com_alertas_ativos") or 0

        verification_code = report.get("verification_code")
        verify_url = verify_url_for(verification_code) if verification_code else None

        subject, html, text = render_monthly_report_email(
            rede_nome=rede_nome,
            year=report["year"],
            month=report["month"],
            risco=risco,
            n_escolas_alerta=n_alertas,
            bottom3=bottom3,
            acoes_top3=acoes_top3,
            report_url=report_url_for(report_id),
            verify_url=verify_url,
            verification_code=verification_code,
        )

        results = []
        success_recipients = []
        for to in body.recipients:
            res = await send_email(to=to, subject=subject, html=html, text=text)
            results.append({"to": to, **res})
            if res.get("success"):
                success_recipients.append(to)

        if success_recipients:
            await mr_svc.mark_email_sent(
                db, report_id=report_id, recipients=success_recipients
            )

        return {
            "subject": subject,
            "results": results,
            "sent_count": len(success_recipients),
        }

    return router
