"""
Router de Snapshots Imutáveis do Diário (Fase 5 — Mai/2026).

Endpoints autenticados (Fase 5b virá depois com /verify público).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from services import diary_snapshot_service as svc

logger = logging.getLogger(__name__)

WRITE_ROLES = ['admin', 'admin_teste', 'super_admin', 'secretario', 'gerente',
               'diretor', 'coordenador', 'semed3']
VIEW_ROLES = WRITE_ROLES + ['professor', 'apoio_pedagogico', 'auxiliar_secretaria',
                            'semed', 'semed1', 'semed2', 'ass_social_2']

# Garantia: "diary_period" deve estar listado em DOCUMENT_TYPES para o
# `register_render_handler` não emitir warning. Faz-se na sequência do server.


# ============================ MODELS ========================================

class CreateSnapshotRequest(BaseModel):
    class_id: str
    period_type: str = Field(..., pattern="^(month|bimester|custom)$")
    period_from: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    period_to: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    period_label: Optional[str] = Field(default=None, max_length=120)


class SupersedeRequest(BaseModel):
    new_snapshot_id: str
    rationale: str = Field(..., min_length=30, max_length=2000)


class RevokeRequest(BaseModel):
    rationale: str = Field(..., min_length=30, max_length=2000)


class SignRequest(BaseModel):
    role: str = Field(..., min_length=2, max_length=40)
    full_name: str = Field(..., min_length=3, max_length=200)


# ============================ HELPERS =======================================

def _period_default_dates(period_type: str, ref: Optional[str] = None) -> tuple[str, str]:
    """Calcula defaults razoáveis quando o frontend só envia o tipo."""
    today = datetime.utcnow().date() if not ref else datetime.strptime(ref, "%Y-%m-%d").date()
    if period_type == "month":
        first = today.replace(day=1)
        # último dia do mês
        next_month = first.replace(year=first.year + (first.month // 12),
                                   month=(first.month % 12) + 1, day=1)
        last = next_month - timedelta(days=1)
        return first.isoformat(), last.isoformat()
    # default custom: últimos 30 dias
    return (today - timedelta(days=29)).isoformat(), today.isoformat()


# ============================ ROUTER ========================================

def setup_diary_snapshots_router(db, audit_service: object | None = None):
    router = APIRouter(prefix="/diary/snapshots", tags=["Diário - Snapshots"])

    # ---------- POST / : criar draft (idempotente) ----------
    @router.post("")
    async def create_snapshot(payload: CreateSnapshotRequest, request: Request):
        await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        current_user = await AuthMiddleware.get_current_user(request)
        try:
            snap = await svc.create_draft_snapshot(
                db,
                class_id=payload.class_id,
                period_type=payload.period_type,
                period_from=payload.period_from,
                period_to=payload.period_to,
                period_label=payload.period_label,
                user=current_user,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return {
            "snapshot": snap,
            "idempotent_hit": bool(snap.get("_idempotent_hit")),
        }

    # ---------- POST /{id}/publish ----------
    @router.post("/{snapshot_id}/publish")
    async def publish(snapshot_id: str, request: Request):
        await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        current_user = await AuthMiddleware.get_current_user(request)
        try:
            snap = await svc.publish_snapshot(db, snapshot_id=snapshot_id, user=current_user)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

        # Enfileira render_job (PDF) — handler `diary_period`.
        render_job = await _enqueue_render_job(
            db, snapshot_id=snapshot_id,
            user_id=current_user.get("id"),
            mantenedora_id=snap.get("mantenedora_id"),
            school_id=snap.get("school_id"),
        )
        return {"snapshot": snap, "render_job": render_job}

    # ---------- POST /{id}/supersede ----------
    @router.post("/{snapshot_id}/supersede")
    async def supersede(snapshot_id: str, payload: SupersedeRequest, request: Request):
        await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        current_user = await AuthMiddleware.get_current_user(request)
        try:
            snap = await svc.supersede_snapshot(
                db, snapshot_id=snapshot_id,
                new_snapshot_id=payload.new_snapshot_id,
                rationale=payload.rationale, user=current_user,
            )
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return snap

    # ---------- POST /{id}/revoke ----------
    @router.post("/{snapshot_id}/revoke")
    async def revoke(snapshot_id: str, payload: RevokeRequest, request: Request):
        await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        current_user = await AuthMiddleware.get_current_user(request)
        try:
            snap = await svc.revoke_snapshot(
                db, snapshot_id=snapshot_id, rationale=payload.rationale, user=current_user,
            )
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return snap

    # ---------- POST /{id}/sign ----------
    @router.post("/{snapshot_id}/sign")
    async def sign(snapshot_id: str, payload: SignRequest, request: Request):
        await AuthMiddleware.require_roles(['admin', 'admin_teste', 'super_admin',
                                             'secretario', 'diretor', 'gerente'])(request)
        current_user = await AuthMiddleware.get_current_user(request)
        try:
            snap = await svc.add_signature(
                db, snapshot_id=snapshot_id,
                role=payload.role, full_name=payload.full_name, user=current_user,
            )
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return snap

    # ---------- GET /{id} ----------
    @router.get("/{snapshot_id}")
    async def get_snapshot(snapshot_id: str, request: Request):
        await AuthMiddleware.require_roles(VIEW_ROLES)(request)
        snap = await db.diary_snapshots.find_one({"id": snapshot_id}, {"_id": 0})
        if not snap:
            raise HTTPException(status_code=404, detail="Snapshot não encontrado")
        return snap

    # ---------- GET / lista ----------
    @router.get("")
    async def list_snapshots(
        request: Request,
        class_id: Optional[str] = None,
        status: Optional[str] = None,
        period_from: Optional[str] = None,
        period_to: Optional[str] = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        await AuthMiddleware.require_roles(VIEW_ROLES)(request)
        q: dict = {}
        if class_id:
            q["class_id"] = class_id
        if status:
            q["status"] = status
        if period_from:
            q["period.from"] = period_from
        if period_to:
            q["period.to"] = period_to
        total = await db.diary_snapshots.count_documents(q)
        skip = (page - 1) * page_size
        items = await db.diary_snapshots.find(
            q,
            {"_id": 0, "payload": 0},  # esconde payload grande na listagem
        ).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    return router


# ============================================================================
# Enqueue render_job — único ponto de integração com o worker
# ============================================================================
async def _enqueue_render_job(
    db, *, snapshot_id: str, user_id: Optional[str],
    mantenedora_id: Optional[str], school_id: Optional[str],
) -> dict:
    """Cria document_render_jobs com idempotency_key determinístico.

    Mesmo snapshot publicado 2x não duplica PDF — o render_job existente
    é retornado (status pode estar pending|processing|completed).
    """
    from utils.render_jobs import compute_idempotency_key, find_existing_job
    from datetime import datetime, timezone
    import uuid as _uuid

    idem_key = compute_idempotency_key(
        source_snapshot_id=snapshot_id,
        document_type="diary_period",
        template_version=svc.TEMPLATE_VERSION,
        render_engine_version=svc.RENDER_ENGINE_VERSION,
    )
    existing = await find_existing_job(db, idempotency_key=idem_key)
    if existing:
        return existing

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job = {
        "id": str(_uuid.uuid4()),
        "idempotency_key": idem_key,
        "document_type": "diary_period",
        "source_snapshot_id": snapshot_id,
        "source_collection": "diary_snapshots",
        "template_version": svc.TEMPLATE_VERSION,
        "render_engine_version": svc.RENDER_ENGINE_VERSION,
        "render_options": {},
        "status": "pending",
        "retry_count": 0,
        "max_retries": 3,
        "next_retry_at": None,
        "generated_file_id": None,
        "generated_file_size_bytes": None,
        "pdf_hash_sha256": None,
        "generated_at": None,
        "started_at": None,
        "completed_at": None,
        "failed_at": None,
        "error_message": None,
        "requested_by_user_id": user_id,
        "requested_at": now,
        "request_ip": None,
        "request_user_agent": None,
        "mantenedora_id": mantenedora_id,
        "school_id": school_id,
        "audit_trail": [{"action": "created", "at": now, "requested_by": user_id}],
    }
    await db.document_render_jobs.insert_one(job.copy())
    job.pop("_id", None)
    return job
