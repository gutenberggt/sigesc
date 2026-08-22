"""Fase 6.0A — regra canônica de preservação da âncora legada AEE V2.

O módulo não conhece autenticação nem o router AEE completo. Ele contém apenas
a regra de integridade e a instalação da dependência sobre a rota DELETE já
existente. A camada ``routers`` fornece a autorização institucional.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.dependencies.utils import get_parameterless_sub_dependant
from fastapi.routing import APIRoute

from .repository import AEEV2Repository


_BLOCK_MESSAGE = (
    "Este Plano AEE possui Dossiê AEE V2 e integra uma cadeia histórica "
    "versionada. A exclusão não é permitida."
)

AuthorizeDelete = Callable[[Request], Awaitable[None]]


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


def _make_delete_guard(db, authorize_delete: AuthorizeDelete):
    async def protect_legacy_anchor(plano_id: str, request: Request) -> None:
        # A autorização vem antes da consulta ao sidecar para não revelar a
        # existência de Dossiê V2 a perfis sem permissão de exclusão.
        await authorize_delete(request)
        await ensure_legacy_plan_delete_allowed(db, plano_id)

    return protect_legacy_anchor


def install_aee_v2_delete_guard(
    base_router,
    db,
    *,
    authorize_delete: AuthorizeDelete,
):
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

    dependency = Depends(_make_delete_guard(db, authorize_delete))
    target.dependant.dependencies.insert(
        0,
        get_parameterless_sub_dependant(
            depends=dependency,
            path=target.path_format,
        ),
    )

    setattr(base_router, "_aee_v2_delete_guard_installed", True)
    return base_router
