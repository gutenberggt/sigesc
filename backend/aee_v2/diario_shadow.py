"""Fase 6.2A — Shadow Mode da fonte efetiva no Diário AEE.

A rota legado ``GET /aee/diario`` continua responsável por toda a resposta já
consumida pelo frontend. Esta camada apenas anexa metadados ``effective_*`` às
fichas retornadas, usando o resolver central read-only da Fase 6.1A.

Nenhum campo legado é substituído e nenhum dado é persistido nesta fase.
"""

from __future__ import annotations

from functools import wraps
import logging
from typing import Any, Awaitable, Callable, Optional

from .effective_source import resolve_effective_dossier
from .repository import AEEV2RepositoryError


logger = logging.getLogger(__name__)

Resolver = Callable[[Any, str], Awaitable[Any]]


def _route_for(base_router, path: str, method: str):
    method = method.upper()
    matches = [
        route
        for route in base_router.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"AEE v2 Shadow Mode esperava exatamente uma rota {method} {path}; "
            f"encontrou {len(matches)}."
        )
    return matches[0]


def _schedule_payload(resolved) -> dict:
    return resolved.dossier.schedule.model_dump(mode="json")


def _version_payload(resolved) -> Optional[dict]:
    if resolved.source != "sidecar_active":
        return None
    return {
        "active_snapshot_id": resolved.active_snapshot_id,
        "document_version": resolved.document_version,
        "revision": resolved.revision,
    }


async def enrich_diario_shadow(
    db,
    payload: Any,
    *,
    resolver: Optional[Resolver] = None,
):
    """Anexa diagnóstico de fonte efetiva sem alterar o contrato legado.

    Falhas do shadow não derrubam o Diário legado: ficam explícitas em
    ``effective_shadow_error`` para auditoria, sem produzir fallback V2 falso.
    """

    if not isinstance(payload, dict):
        return payload

    fichas = payload.get("fichas")
    if not isinstance(fichas, list):
        return payload

    resolve = resolver or resolve_effective_dossier

    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        plano = ficha.get("plano")
        plano_id = plano.get("id") if isinstance(plano, dict) else None
        if not plano_id:
            ficha["effective_source"] = None
            ficha["effective_version"] = None
            ficha["effective_schedule"] = None
            ficha["effective_shadow_error"] = {
                "code": "AEE_V2_SHADOW_PLAN_ID_MISSING",
                "message": "Ficha do Diário AEE sem identificador do Plano AEE.",
            }
            continue

        try:
            resolved = await resolve(db, str(plano_id))
            ficha["effective_source"] = resolved.source
            ficha["effective_version"] = _version_payload(resolved)
            ficha["effective_schedule"] = _schedule_payload(resolved)
            ficha["effective_shadow_error"] = None
        except AEEV2RepositoryError as exc:
            ficha["effective_source"] = None
            ficha["effective_version"] = None
            ficha["effective_schedule"] = None
            ficha["effective_shadow_error"] = {
                "code": getattr(exc, "code", "AEE_V2_REPOSITORY_ERROR"),
                "message": str(exc),
            }
            logger.warning(
                "AEE v2 shadow: falha controlada ao resolver plano %s: %s",
                plano_id,
                exc,
            )
        except Exception:  # pragma: no cover - isolamento defensivo do shadow
            ficha["effective_source"] = None
            ficha["effective_version"] = None
            ficha["effective_schedule"] = None
            ficha["effective_shadow_error"] = {
                "code": "AEE_V2_SHADOW_RESOLUTION_ERROR",
                "message": "Falha inesperada ao calcular a fonte efetiva em Shadow Mode.",
            }
            logger.exception(
                "AEE v2 shadow: falha inesperada ao resolver plano %s",
                plano_id,
            )

    return payload


def install_aee_v2_diario_shadow(
    base_router,
    db,
    *,
    resolver: Optional[Resolver] = None,
):
    """Envolve somente ``GET /aee/diario`` com metadados read-only."""

    if getattr(base_router, "_aee_v2_diario_shadow_installed", False):
        return base_router

    target = _route_for(base_router, "/aee/diario", "GET")
    original_endpoint = target.endpoint

    @wraps(original_endpoint)
    async def shadow_endpoint(*args, **kwargs):
        result = await original_endpoint(*args, **kwargs)
        return await enrich_diario_shadow(db, result, resolver=resolver)

    # FastAPI 0.110.1 clona APIRoute em include_router() a partir de endpoint.
    # Atualizar também dependant.call mantém o APIRouter corrente coerente.
    target.endpoint = shadow_endpoint
    target.dependant.call = shadow_endpoint

    setattr(base_router, "_aee_v2_diario_shadow_installed", True)
    return base_router


def install_aee_v2_diario_shadow_setup(aee_module):
    """Instala o shadow depois de todos os adapters AEE já encadeados."""

    if getattr(aee_module, "_aee_v2_diario_shadow_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_diario_shadow(configured, db)

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_diario_shadow_setup_installed = True
