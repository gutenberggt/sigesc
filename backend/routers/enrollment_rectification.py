"""Router da Retificação de Matrícula/Turma.

F1.0 mantém `POST /dry-run` estritamente read-only.
F2.0 acrescenta `POST /prepare-execution`, que valida token/TOCTOU,
reautentica o ator e grava somente o journal PREPARED. Não existe `/execute`
e nenhuma mutação acadêmica é habilitada nesta fase.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from services.enrollment_rectification import (
    RectificationDryRunError,
    build_rectification_dry_run,
)
from services.enrollment_rectification_execution import (
    RectificationExecutionError,
    prepare_rectification_execution,
)
from tenant_scope import resolve_operational_tenant_context


AUTHORIZED_ROLES = frozenset({"super_admin", "admin", "gerente"})


class RectificationDryRunRequest(BaseModel):
    student_id: str = Field(..., min_length=1)
    destination_class_id: str = Field(..., min_length=1)


class RectificationPrepareExecutionRequest(BaseModel):
    dry_run_token: str = Field(..., min_length=20)
    password: str = Field(..., min_length=1)
    justification: str = Field(..., min_length=1)
    confirmation: str = Field(..., min_length=1)


def _user_roles(user: dict) -> set[str]:
    roles = {str(role).strip() for role in (user.get("roles") or []) if role}
    if user.get("role"):
        roles.add(str(user["role"]).strip())
    return roles


async def require_rectification_context(db, request: Request) -> tuple[dict, object]:
    """Autentica, aplica RBAC estrito e resolve MT-1 antes de qualquer leitura."""
    user = await AuthMiddleware.get_current_user(request)
    if not (_user_roles(user) & AUTHORIZED_ROLES):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "RECTIFICATION_ROLE_FORBIDDEN",
                "message": "Retificação de Matrícula/Turma é restrita a super_admin, admin e gerente.",
            },
        )
    tenant = await resolve_operational_tenant_context(db, user, request)
    return user, tenant


def setup_router(db):
    router = APIRouter(
        prefix="/admin/enrollment-rectification",
        tags=["Retificação de Matrícula/Turma"],
    )

    @router.post("/dry-run")
    async def dry_run(payload: RectificationDryRunRequest, request: Request):
        user, tenant = await require_rectification_context(db, request)
        try:
            return await build_rectification_dry_run(
                db,
                student_id=payload.student_id,
                destination_class_id=payload.destination_class_id,
                tenant_id=tenant.id,
                actor=user,
            )
        except RectificationDryRunError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc

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
