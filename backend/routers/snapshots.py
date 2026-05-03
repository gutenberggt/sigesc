"""Snapshots imutáveis de análises IA — Modo Auditor (Sprint G1.5 — Fev/2026).

Endpoints:
  GET  /api/snapshots                    — lista (escopo por role)
  GET  /api/snapshots/{id}               — detalhes
  GET  /api/snapshots/{id}/verify        — recalcula hash + HMAC
  GET  /api/snapshots/{id}/pdf?mode=...  — PDF auditável (executive|auditor)
  GET  /api/snapshots/retention-policy   — mostra política vigente
  PUT  /api/snapshots/retention-policy   — super_admin/admin define política

Access Control:
  - super_admin → global
  - admin/gerente → sua mantenedora
  - secretario → sua mantenedora (rede)
  - diretor → apenas snapshots de suas escolas
  - demais roles → 403
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import Response

from auth_middleware import AuthMiddleware
from services import snapshot_service as svc
from services.snapshot_pdf import build_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/snapshots", tags=["Snapshots Auditáveis"])


_AUDITOR_ROLES = ("super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor")


def setup_router(db, **_kwargs):

    async def _require_auditor(request: Request) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") not in _AUDITOR_ROLES:
            raise HTTPException(403, "Acesso restrito ao Modo Auditor")
        return user

    def _apply_scope(user: dict, filt: dict) -> dict:
        scope = svc.get_scope_for_user(user)
        if scope is None:
            raise HTTPException(403, "Sem escopo de acesso a snapshots")
        if "mantenedora_id" in scope:
            filt["mantenedora_id"] = scope["mantenedora_id"]
        if "entity_ids" in scope:
            # diretor: só suas escolas
            ids = scope["entity_ids"]
            if "entity_id" in filt and filt["entity_id"] not in ids:
                raise HTTPException(403, "Fora do seu escopo")
            if "entity_id" not in filt:
                filt["entity_id"] = {"$in": ids}
        return filt

    @router.get("")
    async def list_snapshots(
        request: Request,
        entity_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        analysis_type: Optional[str] = None,
        limit: int = Query(50, le=200),
    ):
        user = await _require_auditor(request)
        filt: dict = {}
        if entity_id:
            filt["entity_id"] = entity_id
        if entity_type:
            filt["entity_type"] = entity_type
        if analysis_type:
            filt["analysis_type"] = analysis_type
        filt = _apply_scope(user, filt)

        cursor = db.ai_analysis_snapshots.find(
            filt,
            {
                "_id": 0, "id": 1, "entity_id": 1, "entity_type": 1,
                "analysis_type": 1, "model": 1, "public_hash": 1,
                "created_at": 1, "expires_at": 1, "created_by": 1,
                "version": 1,
            }
        ).sort("created_at", -1).limit(limit)
        items = await cursor.to_list(length=limit)
        return {"items": items, "total": len(items), "scope_applied": svc.get_scope_for_user(user)}

    @router.get("/retention-policy")
    async def get_retention_policy(request: Request):
        user = await _require_auditor(request)
        mantenedora_id = user.get("mantenedora_id")
        if user.get("role") in ("super_admin",) and not mantenedora_id:
            # super_admin sem mantenedora ativa → retorna default
            return {"mantenedora_id": None, "mode": "default",
                    "days": svc.DEFAULT_RETENTION_DAYS,
                    "min_days": svc.MIN_RETENTION_DAYS}
        policy = await svc._get_retention_policy(db, mantenedora_id)
        return {
            "mantenedora_id": mantenedora_id,
            **policy,
            "min_days": svc.MIN_RETENTION_DAYS,
            "default_days": svc.DEFAULT_RETENTION_DAYS,
            "allowed_modes": list(svc.ALLOWED_RETENTION_MODES),
        }

    @router.put("/retention-policy")
    async def update_retention_policy(request: Request):
        """Define política de retenção para a mantenedora do usuário.

        Apenas super_admin/admin podem alterar. Body: {mode, days?}
        """
        user = await _require_auditor(request)
        if user.get("role") not in ("super_admin", "admin", "admin_teste", "gerente"):
            raise HTTPException(403, "Apenas admin pode alterar retenção")
        mantenedora_id = user.get("mantenedora_id")
        if not mantenedora_id:
            raise HTTPException(400, "Mantenedora ativa obrigatória")
        body = await request.json()
        mode = body.get("mode")
        days = body.get("days")
        try:
            doc = await svc.set_retention_policy(
                db, mantenedora_id=mantenedora_id, mode=mode, days=days
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        return doc

    @router.get("/{snapshot_id}")
    async def get_snapshot(snapshot_id: str, request: Request):
        user = await _require_auditor(request)
        doc = await db.ai_analysis_snapshots.find_one(
            {"id": snapshot_id}, {"_id": 0, "expires_at_dt": 0}
        )
        if not doc:
            raise HTTPException(404, "Snapshot não encontrado")
        # Verifica escopo
        scope = svc.get_scope_for_user(user)
        if scope is None:
            raise HTTPException(403, "Sem escopo")
        if "mantenedora_id" in scope and scope["mantenedora_id"] != doc.get("mantenedora_id"):
            raise HTTPException(403, "Fora do seu escopo")
        if "entity_ids" in scope and doc.get("entity_id") not in scope["entity_ids"]:
            raise HTTPException(403, "Fora do seu escopo")
        return doc

    @router.get("/{snapshot_id}/verify")
    async def verify_snapshot(snapshot_id: str, request: Request):
        user = await _require_auditor(request)
        doc = await db.ai_analysis_snapshots.find_one(
            {"id": snapshot_id}, {"_id": 0, "expires_at_dt": 0}
        )
        if not doc:
            raise HTTPException(404, "Snapshot não encontrado")
        scope = svc.get_scope_for_user(user)
        if scope is None:
            raise HTTPException(403, "Sem escopo")
        if "mantenedora_id" in scope and scope["mantenedora_id"] != doc.get("mantenedora_id"):
            raise HTTPException(403, "Fora do seu escopo")
        if "entity_ids" in scope and doc.get("entity_id") not in scope["entity_ids"]:
            raise HTTPException(403, "Fora do seu escopo")
        result = svc.verify_snapshot_integrity(doc)
        # Adiciona metadados úteis
        result["snapshot_id"] = snapshot_id
        result["entity_id"] = doc.get("entity_id")
        result["entity_type"] = doc.get("entity_type")
        result["analysis_type"] = doc.get("analysis_type")
        return result

    @router.get("/{snapshot_id}/pdf")
    async def snapshot_pdf(
        snapshot_id: str,
        request: Request,
        mode: str = Query("executive", pattern="^(executive|auditor)$"),
    ):
        user = await _require_auditor(request)
        doc = await db.ai_analysis_snapshots.find_one(
            {"id": snapshot_id}, {"_id": 0, "expires_at_dt": 0}
        )
        if not doc:
            raise HTTPException(404, "Snapshot não encontrado")
        scope = svc.get_scope_for_user(user)
        if scope is None:
            raise HTTPException(403, "Sem escopo")
        if "mantenedora_id" in scope and scope["mantenedora_id"] != doc.get("mantenedora_id"):
            raise HTTPException(403, "Fora do seu escopo")
        if "entity_ids" in scope and doc.get("entity_id") not in scope["entity_ids"]:
            raise HTTPException(403, "Fora do seu escopo")

        # G1.6: busca código público verificável (pode não existir se retroativo)
        vdoc = await db.verifiable_documents.find_one(
            {"snapshot_id": snapshot_id}, {"_id": 0, "code": 1}
        )
        if vdoc:
            doc["verification_code"] = vdoc["code"]

        pdf_bytes = build_pdf(doc, mode=mode)
        filename = f"sigesc-snapshot-{snapshot_id[:8]}-{mode}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    return router
