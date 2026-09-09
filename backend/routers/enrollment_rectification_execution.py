"""Router F2.0 da Retificação de Matrícula/Turma.

Expõe somente `POST /prepare-execution`. Reutiliza o RBAC/MT-1 canônico de
`require_rectification_context` (F1.0) e delega toda a regra de negócio ao
núcleo seguro em `services/enrollment_rectification_execution.py`. Não existe
`/execute` nem `/rollback` neste módulo, e nenhuma mutação acadêmica é
habilitada nesta fase.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routers.enrollment_rectification import require_rectification_context
from services.enrollment_rectification import RectificationDryRunError
from services.enrollment_rectification_execution import (
    RectificationExecutionError,
    prepare_rectification_execution,
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
        """Fecha gates F2.0 e persiste somente journal PREPARED.

        `Idempotency-Key` é obrigatório. A senha é usada apenas para
        reautenticação e nunca é persistida no journal.
        """
        user, tenant = await require_rectification_context(db, request)
        idempotency_key = request.headers.get("Idempotency-Key", "")
        try:
            return await prepare_rectification_execution(
                db,
                dry_run_token=payload.dry_run_token,
                tenant_id=tenant.id,
                actor=user,
                password=payload.password,
                confirmation=payload.confirmation,
                justification=payload.justification,
                idempotency_key=idempotency_key,
            )
        except (RectificationExecutionError, RectificationDryRunError) as exc:
            status_code = getattr(exc, "status_code", 409)
            detail = exc.as_detail() if hasattr(exc, "as_detail") else {"message": str(exc)}
            raise HTTPException(status_code=status_code, detail=detail) from exc

    return router
