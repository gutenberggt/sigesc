"""AEE v2 Fase 1 — leitura canônica do Dossiê sem persistência.

Este adapter adiciona somente leitura ao router AEE já configurado. O Plano
legado permanece como fonte persistida nesta fase; a resposta v2 é projetada em
memória e inclui relatório de lacunas/mapeamento.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import HTTPException, Request, status

from aee_v2.contracts import AEELegacyProjection
from aee_v2.legacy_mapper import project_legacy_plan
from auth_middleware import AuthMiddleware


async def _require_aee_read(request: Request, access_roles: Iterable[str]) -> dict:
    user = await AuthMiddleware.get_current_user(request)
    if user.get("role") not in set(access_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso não autorizado ao módulo AEE",
        )
    return user


def install_aee_v2_dossier_read(base_router, db, *, access_roles: Iterable[str]):
    """Instala a projeção read-only do Dossiê AEE v2."""

    if getattr(base_router, "_aee_v2_dossier_read_installed", False):
        return base_router

    @base_router.get(
        "/planos/{plano_id}/dossie-v2",
        response_model=AEELegacyProjection,
    )
    async def get_aee_v2_dossier(plano_id: str, request: Request):
        await _require_aee_read(request, access_roles)

        plano = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        if not plano:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")

        try:
            return project_legacy_plan(plano)
        except ValueError as exc:
            # Documento existente com identidade estrutural incompleta: não alterar
            # nem mascarar o legado; devolver erro auditável para saneamento futuro.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "AEE_V2_LEGACY_IDENTITY_INCOMPLETE",
                    "message": str(exc),
                    "legacy_plano_id": plano.get("id"),
                },
            ) from exc

    setattr(base_router, "_aee_v2_dossier_read_installed", True)
    return base_router


def install_aee_v2_dossier_setup(aee_module):
    """Encadeia a Fase 1 depois dos adapters já instalados no setup AEE."""

    if getattr(aee_module, "_aee_v2_dossier_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router
    access_roles = tuple(getattr(aee_module, "ROLES_AEE", ()))

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_dossier_read(
            configured,
            db,
            access_roles=access_roles,
        )

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_dossier_setup_installed = True
