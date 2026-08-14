"""
Router da Integração MEC Gestão Presente (CMDE).

Camada fina: autenticação/permissão, parse de request, delegação ao CmdeService (mig/cmde)
e formatação da resposta HTTP. NÃO contém regra de negócio nem chamadas HTTP diretas.
Contratos dos 5 endpoints originais preservados. Sprint 001 adiciona endpoints operacionais
(métricas/auditoria/flags) sem alterar os existentes.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from typing import Optional
import logging

from auth_middleware import AuthMiddleware
from tenant_scope import get_mantenedora_scope
from mig.cmde.service import CmdeService
from mig.cmde.dtos import FrequencyBatchRequestDTO
from mig.cmde.preview import CmdeOperationalPreviewService, CmdeStudentPreviewRequestDTO
from mig.core.exceptions import MigError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MEC Integration"])


def setup_router(db, **kwargs):
    service = CmdeService(db)
    preview_service = CmdeOperationalPreviewService(db)

    async def _guard(request: Request) -> dict:
        """Valida permissão e retorna contexto {actor, tenant}."""
        user = await AuthMiddleware.require_permission(db, 'nav-mec-button', ['super_admin'])(request)
        try:
            tenant = get_mantenedora_scope(user, request)
        except Exception:
            tenant = None
        return {"actor": user.get("email") or user.get("id"), "tenant": tenant,
                "role": user.get("role")}

    # ---------- Endpoints existentes (contratos preservados) ----------
    @router.get("/mec/config")
    async def get_config(request: Request):
        await _guard(request)
        return await service.get_config()

    @router.put("/mec/config")
    async def update_config(request: Request):
        ctx = await _guard(request)
        body = await request.json()
        return await service.update_config(body, context=ctx)

    @router.get("/mec/elegibilidades")
    async def consultar_elegibilidades(request: Request, search: Optional[str] = None,
                                       inep: Optional[str] = None, page: int = 1, page_size: int = 50):
        ctx = await _guard(request)
        try:
            return await service.query(search=search, inep=inep, page=page, page_size=page_size, context=ctx)
        except MigError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @router.get("/mec/students/mapping")
    async def get_students_mapping(request: Request, school_id: Optional[str] = None):
        await _guard(request)
        return await service.students_mapping(school_id=school_id)

    # ---------- Preview operacional Student + Enrollment (Fase B.6) ----------
    @router.post("/mec/students/preview")
    async def students_preview(request: Request):
        ctx = await _guard(request)
        body = await request.json()
        try:
            req = CmdeStudentPreviewRequestDTO.model_validate(body or {})
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors())
        try:
            report = await preview_service.build(req, context=ctx)
            return report.model_dump(mode="json")
        except MigError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @router.get("/mec/sync/status")
    async def get_sync_status(request: Request):
        await _guard(request)
        return await service.sync_status()

    # ---------- Camada operacional (Sprint 001) ----------
    @router.get("/mec/metrics")
    async def get_metrics(request: Request):
        ctx = await _guard(request)
        return await service.metrics(context=ctx)

    @router.get("/mec/audit")
    async def get_audit(request: Request, page: int = 1, page_size: int = 50,
                        limit: int = None, status: Optional[str] = None,
                        operation: Optional[str] = None, date_from: Optional[str] = None,
                        date_to: Optional[str] = None):
        ctx = await _guard(request)
        # Compatibilidade: `limit` legado mapeia para page_size na primeira página
        if limit is not None:
            page, page_size = 1, min(max(limit, 1), 200)
        return await service.audit_events(context=ctx, page=page, page_size=page_size,
                                          status=status, operation=operation,
                                          date_from=date_from, date_to=date_to)

    @router.get("/mec/flags")
    async def get_flags(request: Request):
        ctx = await _guard(request)
        return await service.feature_flags(context=ctx)

    @router.put("/mec/flags")
    async def set_flag(request: Request):
        ctx = await _guard(request)
        body = await request.json()
        flag = body.get("flag")
        if not flag:
            raise HTTPException(status_code=400, detail="Campo 'flag' é obrigatório.")
        return await service.set_feature_flag(flag, bool(body.get("enabled")), context=ctx,
                                              environment=body.get("environment"))

    # ---------- Batch Builder de Frequência (Sprint 002.b) ----------
    @router.post("/mec/frequency/preview")
    async def frequency_preview(request: Request):
        ctx = await _guard(request)
        body = await request.json()
        competencia = (body or {}).get("competencia")
        if not competencia:
            raise HTTPException(status_code=400, detail="Campo 'competencia' (AAAA-MM) é obrigatório.")
        req = FrequencyBatchRequestDTO(
            competencia=competencia, school_id=(body or {}).get("school_id"),
            class_id=(body or {}).get("class_id"), dry_run=bool((body or {}).get("dry_run", True)))
        try:
            return await service.build_frequency_batch(req, context=ctx)
        except MigError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    # ---------- Scheduler + Dead Letters (Sprint 002.e) ----------
    @router.get("/mec/scheduler")
    async def scheduler_status(request: Request):
        ctx = await _guard(request)
        return await service.scheduler_status(context=ctx)

    @router.post("/mec/scheduler/config")
    async def scheduler_config(request: Request):
        ctx = await _guard(request)
        body = await request.json()
        return await service.scheduler_set_config(body or {}, context=ctx)

    @router.post("/mec/scheduler/tick")
    async def scheduler_tick(request: Request):
        ctx = await _guard(request)
        return await service.scheduler_tick(context=ctx, manual=True)

    @router.get("/mec/dead-letters")
    async def dead_letters(request: Request, page: int = 1, page_size: int = 50):
        ctx = await _guard(request)
        return await service.dead_letters(context=ctx, page=page, page_size=page_size)

    @router.post("/mec/dead-letters/{item_id}/reprocess")
    async def reprocess_dead_letter(item_id: str, request: Request):
        ctx = await _guard(request)
        return await service.reprocess_dead_letter(item_id, context=ctx)

    return router