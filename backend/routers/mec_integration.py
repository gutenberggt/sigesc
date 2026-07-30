"""
Router da Integração MEC Gestão Presente (CMDE).

Camada fina: autenticação/permissão, parse de request, delegação ao CmdeService (mig/cmde)
e formatação da resposta HTTP. NÃO contém regra de negócio nem chamadas HTTP diretas.
Contratos (URLs, métodos, respostas) preservados — ver memory/audit/SPRINT_000_*.md.
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Optional
import logging

from auth_middleware import AuthMiddleware
from mig.cmde.service import CmdeService
from mig.core.exceptions import MigError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MEC Integration"])


def setup_router(db, **kwargs):
    service = CmdeService(db)

    async def _guard(request: Request):
        await AuthMiddleware.require_permission(db, 'nav-mec-button', ['super_admin'])(request)

    @router.get("/mec/config")
    async def get_config(request: Request):
        await _guard(request)
        return await service.get_config()

    @router.put("/mec/config")
    async def update_config(request: Request):
        await _guard(request)
        body = await request.json()
        return await service.update_config(body)

    @router.get("/mec/elegibilidades")
    async def consultar_elegibilidades(request: Request, search: Optional[str] = None,
                                       inep: Optional[str] = None, page: int = 1, page_size: int = 50):
        await _guard(request)
        try:
            return await service.query(search=search, inep=inep, page=page, page_size=page_size)
        except MigError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    @router.get("/mec/students/mapping")
    async def get_students_mapping(request: Request, school_id: Optional[str] = None):
        await _guard(request)
        return await service.students_mapping(school_id=school_id)

    @router.get("/mec/sync/status")
    async def get_sync_status(request: Request):
        await _guard(request)
        return await service.sync_status()

    return router
