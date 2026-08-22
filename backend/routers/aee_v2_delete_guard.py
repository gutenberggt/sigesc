"""AEE v2 Fase 6.0A — adapter de autenticação/setup do guard de exclusão.

A regra de integridade vive em ``aee_v2.delete_guard``. Este arquivo apenas
preserva a autorização institucional da rota DELETE legada e encadeia o guard
no setup do módulo AEE, sem alterar ``routers/aee.py``.
"""

from __future__ import annotations

from fastapi import Request

from aee_v2.delete_guard import install_aee_v2_delete_guard
from auth_middleware import AuthMiddleware


_DELETE_ROLES = (
    "super_admin",
    "gerente",
    "admin",
    "admin_teste",
    "coordenador",
    "apoio_pedagogico",
    "auxiliar_secretaria",
    "secretario",
)


async def _authorize_delete(request: Request) -> None:
    await AuthMiddleware.require_roles(list(_DELETE_ROLES))(request)


def install_aee_v2_delete_guard_setup(aee_module):
    """Encadeia a proteção depois dos demais adapters AEE V2 já instalados."""

    if getattr(aee_module, "_aee_v2_delete_guard_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_delete_guard(
            configured,
            db,
            authorize_delete=_authorize_delete,
        )

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_delete_guard_setup_installed = True
