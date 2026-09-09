"""Router F2.2 da saga de Retificação de Matrícula/Turma.

Este router é o sibling F2 efetivamente exposto: reutiliza o RBAC/MT-1
centralizado em ``require_rectification_context`` (F1.0) e delega toda regra
de negócio ao serviço ``services.enrollment_rectification_saga``. Expõe
``/prepare-execution``, ``/execute`` e ``/rollback``. A preparação aqui
integra corretamente o eixo documental F2.1C (artefatos resolvíveis não
bloqueiam para sempre a saga); o núcleo F2.0 em
``services/enrollment_rectification_execution.py`` permanece intacto e é
reutilizado como base (reautenticação, lock, idempotência, snapshot), mas seu
router isolado deixa de ser montado no agregado — ver ``routers/__init__.py``.

A publicação destes endpoints não habilita mutação: ``/execute`` é
fail-closed pela feature flag da F2.2. Nenhuma rota executa estudante
automaticamente.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from audit_service import audit_service
from routers.enrollment_rectification import require_rectification_context
from services.enrollment_rectification import RectificationDryRunError
from services.enrollment_rectification_execution import RectificationExecutionError
from services.enrollment_rectification_saga import (
    RectificationSagaError,
    execute_rectification_saga,
    prepare_rectification_saga_execution,
    rollback_rectification_saga,
)


class RectificationPrepareSagaRequest(BaseModel):
    dry_run_token: str = Field(..., min_length=20)
    password: str = Field(..., min_length=1)
    justification: str = Field(..., min_length=1)
    confirmation: str = Field(..., min_length=1)


class RectificationExecuteRequest(BaseModel):
    prepare_id: str = Field(..., min_length=20)
    document_acknowledgement: str = Field(..., min_length=20)


class RectificationRollbackRequest(BaseModel):
    prepare_id: str = Field(..., min_length=20)
    password: str = Field(..., min_length=1)
    justification: str = Field(..., min_length=30)


def setup_router(db):
    router = APIRouter(
        prefix="/admin/enrollment-rectification",
        tags=["Retificação de Matrícula/Turma"],
    )

    @router.post("/prepare-execution")
    async def prepare_execution(payload: RectificationPrepareSagaRequest, request: Request):
        """Fecha os gates F2.0 e integra o eixo documental F2.1C.

        ``Idempotency-Key`` é obrigatório. A senha é usada apenas para
        reautenticação e nunca é persistida no journal.
        """
        user, tenant = await require_rectification_context(db, request)
        idempotency_key = request.headers.get("Idempotency-Key", "")
        try:
            return await prepare_rectification_saga_execution(
                db,
                dry_run_token=payload.dry_run_token,
                tenant_id=tenant.id,
                actor=user,
                password=payload.password,
                confirmation=payload.confirmation,
                justification=payload.justification,
                idempotency_key=idempotency_key,
            )
        except (RectificationSagaError, RectificationExecutionError, RectificationDryRunError) as exc:
            status_code = getattr(exc, "status_code", 409)
            detail = exc.as_detail() if hasattr(exc, "as_detail") else {"message": str(exc)}
            raise HTTPException(status_code=status_code, detail=detail) from exc

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
                password=payload.password,
                justification=payload.justification,
                request=request,
                audit_service=audit_service,
            )
        except RectificationSagaError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc

    return router
