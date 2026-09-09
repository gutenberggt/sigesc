"""Router F2.2 da saga de Retificação de Matrícula/Turma.

Este sub-router é anexado ao router F2.0. O RBAC/MT-1 permanece centralizado em
``require_rectification_context``. A publicação do endpoint não habilita a
mutação: ``/execute`` é fail-closed pela feature flag da F2.2.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from audit_service import audit_service
from routers.enrollment_rectification import require_rectification_context
from services.enrollment_rectification_saga_runtime import (
    RectificationSagaError,
    execute_rectification_saga,
    rollback_rectification_saga,
)


class RectificationExecuteRequest(BaseModel):
    prepare_id: str = Field(..., min_length=20)
    document_acknowledgement: str = Field(..., min_length=20)


class RectificationRollbackRequest(BaseModel):
    prepare_id: str = Field(..., min_length=20)
    justification: str = Field(..., min_length=30)


def setup_router(db):
    router = APIRouter()

    @router.post("/execute")
    async def execute(payload: RectificationExecuteRequest, request: Request):
        user, tenant = await require_rectification_context(db, request)
        try:
            return await execute_rectification_saga(
                db,
                prepare_id=payload.prepare_id,
                tenant_id=tenant.id,
                actor=user,
                document_acknowledgement=payload.document_acknowledgement,
                request=request,
                audit_service=audit_service,
            )
        except RectificationSagaError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc

    @router.post("/rollback")
    async def rollback(payload: RectificationRollbackRequest, request: Request):
        user, tenant = await require_rectification_context(db, request)
        try:
            return await rollback_rectification_saga(
                db,
                prepare_id=payload.prepare_id,
                tenant_id=tenant.id,
                actor=user,
                justification=payload.justification,
                request=request,
                audit_service=audit_service,
            )
        except RectificationSagaError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc

    return router
