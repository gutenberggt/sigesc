"""
Render Jobs Router — orquestração da fila de geração de documentos.

[Fev/2026] Passo 4. Escopo mínimo autorizado pelo owner:
- POST   /api/render-jobs              cria job (idempotente)
- GET    /api/render-jobs/{id}         status do job
- GET    /api/render-jobs              lista (filtros básicos)
- POST   /api/render-jobs/{id}/retry   força retry manual (admin only)

NÃO implementado nesta V1 (backlog explícito):
- /file (download do PDF) — depende dos handlers do Boletim/Histórico estarem prontos
- /public/render-jobs/{token}/file — idem
- Observabilidade dedicada — backlog
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, get_mantenedora_scope
from utils.render_jobs import (
    DOCUMENT_TYPES,
    JOB_STATUSES,
    compute_idempotency_key,
    compute_payload_hash,
    find_existing_job,
    has_render_handler,
    is_terminal_status,
    now_iso,
)

logger = logging.getLogger(__name__)

ROLES_CREATE_JOB = {
    "super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor",
    "coordenador", "professor",
}
ROLES_VIEW_JOB = ROLES_CREATE_JOB | {"apoio_pedagogico", "semed", "semed1", "semed2", "semed3"}
ROLES_FORCE_RETRY = {"super_admin", "admin", "admin_teste", "gerente"}


# ===========================================================================
class RenderJobCreate(BaseModel):
    document_type: str
    source_snapshot_id: str = Field(..., min_length=1)
    source_collection: str = Field(..., min_length=1)
    template_version: str = Field(..., min_length=1)
    render_engine_version: str = Field(..., min_length=1)
    render_options: dict = Field(default_factory=dict)
    school_id: Optional[str] = None
    force_reissue: bool = False


def setup_render_jobs_router(db, audit_service=None) -> APIRouter:
    router = APIRouter(prefix="/render-jobs", tags=["Render Jobs"])

    async def _require_role(request: Request, allowed: set[str]) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") not in allowed:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        return user

    # -------------------------------------------------------------------
    @router.post("", response_model=dict)
    async def create_job(payload: RenderJobCreate, request: Request):
        user = await _require_role(request, ROLES_CREATE_JOB)
        if payload.document_type not in DOCUMENT_TYPES:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_DOCUMENT_TYPE", "expected": list(DOCUMENT_TYPES)},
            )

        tenant = get_mantenedora_scope(user, request)
        idem_key = compute_idempotency_key(
            source_snapshot_id=payload.source_snapshot_id,
            document_type=payload.document_type,
            template_version=payload.template_version,
            render_engine_version=payload.render_engine_version,
        )

        existing = await find_existing_job(db, idempotency_key=idem_key)

        # Idempotência: a menos que force_reissue, retorna o existente.
        if existing and not payload.force_reissue:
            return {
                "id": existing["id"],
                "status": existing["status"],
                "idempotent_hit": True,
                "job": existing,
            }

        # Reissue: marca o existente como `superseded` se ainda não terminal.
        if existing and payload.force_reissue:
            now_s = now_iso()
            await db.document_render_jobs.update_one(
                {"idempotency_key": idem_key, "status": {"$in": ["pending", "processing"]}},
                {
                    "$set": {
                        "status": "superseded",
                        "superseded_at": now_s,
                    },
                    "$push": {
                        "audit_trail": {
                            "action": "superseded_by_reissue",
                            "at": now_s,
                            "by_user_id": user.get("id"),
                        },
                    },
                },
            )
            # Para reemissão, criamos um NOVO job com idempotency_key derivada
            # (mesma chave + sufixo do counter) — preserva histórico de tentativas.
            count = await db.document_render_jobs.count_documents({"idempotency_key": {"$regex": f"^{idem_key}"}})
            idem_key_new = f"{idem_key}#r{count}"
        else:
            idem_key_new = idem_key

        now_s = now_iso()
        job = {
            "id": str(uuid.uuid4()),
            "idempotency_key": idem_key_new,
            "document_type": payload.document_type,
            "source_snapshot_id": payload.source_snapshot_id,
            "source_collection": payload.source_collection,
            "template_version": payload.template_version,
            "render_engine_version": payload.render_engine_version,
            "render_options": payload.render_options,
            "payload_hash": compute_payload_hash({
                "source_snapshot_id": payload.source_snapshot_id,
                "document_type": payload.document_type,
                "template_version": payload.template_version,
                "render_engine_version": payload.render_engine_version,
                "render_options": payload.render_options,
            }),
            "status": "pending",
            "generated_file_id": None,
            "generated_file_size_bytes": None,
            "generated_at": None,
            "pdf_hash_sha256": None,
            "error_message": None,
            "retry_count": 0,
            "max_retries": 3,
            "next_retry_at": None,
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "requested_by_user_id": user.get("id"),
            "requested_at": now_s,
            "request_ip": request.client.host if request.client else None,
            "request_user_agent": request.headers.get("user-agent", "")[:512],
            "mantenedora_id": tenant,
            "school_id": payload.school_id,
            "audit_trail": [
                {"action": "queued", "at": now_s, "by_user_id": user.get("id")},
            ],
        }
        await db.document_render_jobs.insert_one(job)
        job.pop("_id", None)
        logger.info("[render-jobs] criado %s tipo=%s snapshot=%s", job["id"], payload.document_type, payload.source_snapshot_id)
        return {
            "id": job["id"],
            "status": job["status"],
            "idempotent_hit": False,
            "handler_registered": has_render_handler(payload.document_type),
            "job": job,
        }

    # -------------------------------------------------------------------
    @router.get("/{job_id}", response_model=dict)
    async def get_job(job_id: str, request: Request):
        user = await _require_role(request, ROLES_VIEW_JOB)
        flt = apply_tenant_filter({"id": job_id}, user, request)
        job = await db.document_render_jobs.find_one(flt, {"_id": 0})
        if not job:
            raise HTTPException(status_code=404, detail="Job não encontrado")
        return job

    # -------------------------------------------------------------------
    @router.get("", response_model=dict)
    async def list_jobs(
        request: Request,
        source_snapshot_id: Optional[str] = None,
        document_type: Optional[str] = None,
        status: Optional[str] = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
    ):
        user = await _require_role(request, ROLES_VIEW_JOB)
        flt: dict = {}
        if source_snapshot_id:
            flt["source_snapshot_id"] = source_snapshot_id
        if document_type:
            flt["document_type"] = document_type
        if status:
            if status not in JOB_STATUSES:
                raise HTTPException(status_code=422, detail={"code": "INVALID_STATUS"})
            flt["status"] = status
        flt = apply_tenant_filter(flt, user, request)

        total = await db.document_render_jobs.count_documents(flt)
        cursor = (
            db.document_render_jobs.find(flt, {"_id": 0})
            .sort("requested_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        items = await cursor.to_list(page_size)
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }

    # -------------------------------------------------------------------
    @router.post("/{job_id}/retry", response_model=dict)
    async def force_retry(job_id: str, request: Request):
        user = await _require_role(request, ROLES_FORCE_RETRY)
        flt = apply_tenant_filter({"id": job_id}, user, request)
        job = await db.document_render_jobs.find_one(flt, {"_id": 0})
        if not job:
            raise HTTPException(status_code=404, detail="Job não encontrado")

        if not is_terminal_status(job["status"]) and job["status"] != "pending":
            # Em processing — não interfere.
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "JOB_IN_PROGRESS",
                    "message": "Job já está em processamento. Aguarde finalizar.",
                },
            )

        if job["status"] == "completed":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "JOB_ALREADY_COMPLETED",
                    "message": "Use force_reissue=true em POST /render-jobs para regerar.",
                },
            )

        # Reseta para pending com retry_count zerado e next_retry_at imediato.
        now_s = now_iso()
        await db.document_render_jobs.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": "pending",
                    "retry_count": 0,
                    "next_retry_at": None,
                    "error_message": None,
                    "failed_at": None,
                },
                "$push": {
                    "audit_trail": {
                        "action": "force_retry",
                        "at": now_s,
                        "by_user_id": user.get("id"),
                    },
                },
            },
        )
        return {"id": job_id, "status": "pending", "force_retry": True}

    return router
