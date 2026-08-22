"""AEE v2 Fase 6.0A — proteção da âncora legada contra exclusão.

Este adapter é deliberadamente aditivo: não altera ``routers/aee.py`` nem
qualquer coleção histórica. Ele acrescenta uma dependência à rota DELETE
legada de Plano AEE e impede a exclusão quando já existe um head do Dossiê V2
associado ao ``legacy_plano_id``.

A razão é estrutural: heads e snapshots V2 usam o ID do Plano AEE legado como
âncora estável. Remover esse documento depois da inicialização do sidecar
quebraria o acesso normal ao Dossiê e deixaria a cadeia versionada órfã.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.dependencies.utils import get_parameterless_sub_dependant
from fastapi.routing import APIRoute

from aee_v2.repository import AEEV2Repository
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

_BLOCK_MESSAGE = (
    "Este Plano AEE possui Dossiê AEE V2 e integra uma cadeia histórica "
    "versionada. A exclusão não é permitida."
)


async def ensure_legacy_plan_delete_allowed(db, legacy_plano_id: str) -> None:
    """Bloqueia exclusão quando o Plano legado já possui head no sidecar V2."""

    head = await db[AEEV2Repository.HEADS].find_one(
        {"legacy_plano_id": legacy_plano_id},
        {"_id": 0, "id": 1, "legacy_plano_id": 1},
    )
    if head:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_BLOCK_MESSAGE,
        )


def _make_delete_guard(db):
    async def protect_legacy_anchor(plano_id: str, request: Request) -> None:
        # A rota legada faz a mesma autorização dentro do endpoint. Repeti-la
        # aqui evita que o guard revele, a perfis não autorizados, se determinado
        # plano possui ou não sidecar V2.
        await AuthMiddleware.require_roles(list(_DELETE_ROLES))(request)
        await ensure_legacy_plan_delete_allowed(db, plano_id)

    return protect_legacy_anchor


def install_aee_v2_delete_guard(base_router, db):
    """Anexa o guard apenas ao DELETE legado de ``/aee/planos/{plano_id}``."""

    if getattr(base_router, "_aee_v2_delete_guard_installed", False):
        return base_router

    target = next(
        (
            route
            for route in base_router.routes
            if isinstance(route, APIRoute)
            and route.path == "/aee/planos/{plano_id}"
            and "DELETE" in (route.methods or set())
        ),
        None,
    )
    if target is None:
        raise RuntimeError(
            "Rota DELETE /aee/planos/{plano_id} não encontrada; "
            "proteção AEE V2 não pode ser instalada silenciosamente."
        )

    dependency = Depends(_make_delete_guard(db))
    target.dependant.dependencies.insert(
        0,
        get_parameterless_sub_dependant(
            depends=dependency,
            path=target.path_format,
        ),
    )

    setattr(base_router, "_aee_v2_delete_guard_installed", True)
    return base_router


def install_aee_v2_delete_guard_setup(aee_module):
    """Encadeia a proteção depois dos demais adapters AEE V2 já instalados."""

    if getattr(aee_module, "_aee_v2_delete_guard_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_delete_guard(configured, db)

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_delete_guard_setup_installed = True
