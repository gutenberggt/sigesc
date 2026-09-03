"""Router F1.0 da Retificação de Matrícula/Turma.

Somente `POST /dry-run` existe nesta fase. Não há endpoint de execução, rollback
ou qualquer writer. A origem é sempre inferida da matrícula regular canônica.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from services.enrollment_rectification import (
    RectificationDryRunError,
    build_rectification_dry_run,
)
from tenant_scope import resolve_operational_tenant_context


AUTHORIZED_ROLES = frozenset({"super_admin", "admin", "gerente"})


class RectificationDryRunRequest(BaseModel):
    student_id: str = Field(..., min_length=1)
    destination_class_id: str = Field(..., min_length=1)


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

    return router
