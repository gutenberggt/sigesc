"""Fase 6.4B — exposição aditiva da Fonte Efetiva no Plano AEE Individual.

Envolve somente ``GET /aee/planos/{plano_id}`` depois da Fase 6.4A. O endpoint
legado continua responsável pelos campos históricos; esta camada cria uma cópia
rasa da resposta e anexa metadados canônicos V2, sem remover/substituir campos
legados e sem qualquer persistência.

Em falha de integridade V2 não há fallback silencioso: ``effective_source`` e
``effective_dossier`` ficam nulos e ``effective_error`` explicita a falha. Uma
falha inesperada do próprio adapter preserva a resposta legado.
"""

from __future__ import annotations

from functools import wraps
import inspect
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
            f"AEE v2 Plano Effective Read esperava exatamente uma rota {method} {path}; "
            f"encontrou {len(matches)}."
        )
    return matches[0]


def _empty_effective_fields(*, error: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {
        "effective_source": None,
        "effective_version": None,
        "effective_dossier": None,
        "effective_error": error,
    }


def _version_payload(resolved) -> Optional[dict[str, Any]]:
    if resolved.source != "sidecar_active":
        return None
    return {
        "active_snapshot_id": resolved.active_snapshot_id,
        "document_version": resolved.document_version,
        "revision": resolved.revision,
    }


async def build_plano_effective_fields(
    db,
    plano_id: str,
    *,
    resolver: Optional[Resolver] = None,
) -> dict[str, Any]:
    """Resolve e serializa a Fonte Efetiva para exposição aditiva no GET."""

    resolve = resolver or resolve_effective_dossier

    try:
        resolved = await resolve(db, str(plano_id))
        return {
            "effective_source": resolved.source,
            "effective_version": _version_payload(resolved),
            "effective_dossier": resolved.dossier.model_dump(mode="json"),
            "effective_error": None,
        }
    except AEEV2RepositoryError as exc:
        return _empty_effective_fields(
            error={
                "code": getattr(exc, "code", "AEE_V2_REPOSITORY_ERROR"),
                "message": str(exc),
            }
        )
    except Exception:
        logger.exception(
            "AEE v2 plano effective read: falha inesperada ao resolver plano %s",
            plano_id,
        )
        return _empty_effective_fields(
            error={
                "code": "AEE_V2_PLANO_EFFECTIVE_RESOLUTION_ERROR",
                "message": "Falha inesperada ao resolver a Fonte Efetiva do Plano AEE.",
            }
        )


async def enrich_plano_effective_response(
    db,
    result: Any,
    *,
    plano_id: Optional[str] = None,
    resolver: Optional[Resolver] = None,
):
    """Retorna resposta aditiva sem mutar o objeto legado recebido."""

    if not isinstance(result, dict):
        return result

    effective_id = plano_id or result.get("id")
    enriched = dict(result)

    if not effective_id:
        enriched.update(
            _empty_effective_fields(
                error={
                    "code": "AEE_V2_PLANO_EFFECTIVE_PLAN_ID_MISSING",
                    "message": "Não foi possível identificar o Plano AEE retornado.",
                }
            )
        )
        return enriched

    fields = await build_plano_effective_fields(
        db,
        str(effective_id),
        resolver=resolver,
    )
    enriched.update(fields)
    return enriched


def install_aee_v2_plano_effective_read(
    base_router,
    db,
    *,
    resolver: Optional[Resolver] = None,
):
    """Expõe Fonte Efetiva de forma aditiva no GET individual do Plano AEE."""

    if getattr(base_router, "_aee_v2_plano_effective_read_installed", False):
        return base_router

    target = _route_for(base_router, "/aee/planos/{plano_id}", "GET")
    original_endpoint = target.endpoint
    signature = inspect.signature(original_endpoint)

    @wraps(original_endpoint)
    async def effective_endpoint(*args, **kwargs):
        result = await original_endpoint(*args, **kwargs)

        try:
            bound = signature.bind_partial(*args, **kwargs)
            plano_id = bound.arguments.get("plano_id")
            return await enrich_plano_effective_response(
                db,
                result,
                plano_id=str(plano_id) if plano_id is not None else None,
                resolver=resolver,
            )
        except Exception:  # pragma: no cover - fail-open defensivo do adapter
            logger.exception(
                "AEE v2 plano effective read: adapter falhou; resposta legado preservada"
            )
            return result

    # FastAPI 0.110.1 clona APIRoute em include_router() a partir de endpoint.
    target.endpoint = effective_endpoint
    target.dependant.call = effective_endpoint

    setattr(base_router, "_aee_v2_plano_effective_read_installed", True)
    return base_router


def install_aee_v2_plano_effective_read_setup(aee_module):
    """Instala a 6.4B depois da 6.4A, mantendo o router legado intacto."""

    if getattr(aee_module, "_aee_v2_plano_effective_read_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_plano_effective_read(configured, db)

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_plano_effective_read_setup_installed = True
