"""Router operacional da Retificação de Matrícula/Turma.

Preserva o contrato F2.0 de `POST /prepare-execution`, mas a preparação passa a
usar a saga F2.2 e o mesmo router agrega os sub-endpoints `/execute` e `/rollback`.
O RBAC/MT-1 continua centralizado em `require_rectification_context` e a execução
acadêmica permanece fail-closed por `ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routers.enrollment_rectification import require_rectification_context
from routers.enrollment_rectification_saga import (
    setup_router as setup_enrollment_rectification_saga_router,
)
from services.enrollment_rectification import RectificationDryRunError
from services.enrollment_rectification_execution import RectificationExecutionError
from services.enrollment_rectification_saga import (
    RectificationSagaError,
    prepare_rectification_saga_execution,
)


class RectificationPrepareExecutionRequest(BaseModel):
    dry_run_token: str = Field(..., min_length=20)
    password: str = Field(..., min_length=1)
    justification: str = Field(..., min_length=1)
    confirmation: str = Field(..., min_length=1)


def setup_router(db):
    router = APIRouter(
        prefix="/admin/enrollment-rectification",
        tags=["Retificação de Matrícula/Turma"],
    )

    @router.post("/prepare-execution")
    async def prepare_execution(payload: RectificationPrepareExecutionRequest, request: Request):
        """Fecha gates humanos/TOCTOU e persiste somente journal PREPARED.

        `Idempotency-Key` é obrigatório. A senha é usada apenas para
        reautenticação e nunca é persistida no journal. A preparação F2.2 não
        realiza write acadêmico e devolve `execution_enabled` para evidenciar o
        estado operacional da feature flag.
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

    # F2.2 é um sub-router sem prefixo próprio; ao ser incluído aqui herda o
    # prefixo canônico /admin/enrollment-rectification e publica apenas
    # /execute e /rollback, sem duplicar dry-run ou prepare-execution.
    router.include_router(setup_enrollment_rectification_saga_router(db))
    return router
