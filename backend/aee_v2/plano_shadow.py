"""Fase 6.4A — Shadow Mode do Plano AEE Individual.

A rota legado ``GET /aee/planos/{plano_id}`` continua responsável por toda a
resposta consumida pelo frontend. Esta camada executa o endpoint legado primeiro,
resolve em paralelo lógico a Fonte Efetiva da Fase 6.1A e registra apenas um
diagnóstico observacional.

Nenhum campo é anexado à resposta HTTP e nenhum dado é persistido nesta fase.
"""

from __future__ import annotations

from functools import wraps
import inspect
import json
import logging
from typing import Any, Awaitable, Callable, Optional

from .effective_source import resolve_effective_dossier
from .repository import AEEV2RepositoryError


logger = logging.getLogger(__name__)

Resolver = Callable[[Any, str], Awaitable[Any]]
DiagnosticBuilder = Callable[[Any, str], Awaitable[dict[str, Any]]]


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
            f"AEE v2 Plano Shadow esperava exatamente uma rota {method} {path}; "
            f"encontrou {len(matches)}."
        )
    return matches[0]


def _base_diagnostic(plano_id: str) -> dict[str, Any]:
    return {
        "phase": "6.4A",
        "mode": "shadow_read_only",
        "legacy_plano_id": str(plano_id),
        "effective_source": None,
        "active_snapshot_id": None,
        "document_version": None,
        "revision": None,
        "lifecycle_status": None,
        "study_case_state": None,
        "paee_state": None,
        "pei_state": None,
        "schedule_sessions": None,
        "error": None,
    }


async def build_plano_shadow_diagnostic(
    db,
    plano_id: str,
    *,
    resolver: Optional[Resolver] = None,
) -> dict[str, Any]:
    """Resolve a Fonte Efetiva sem alterar o Plano legado ou a resposta HTTP."""

    diagnostic = _base_diagnostic(plano_id)
    resolve = resolver or resolve_effective_dossier

    try:
        resolved = await resolve(db, str(plano_id))
        dossier = resolved.dossier

        diagnostic.update(
            {
                "effective_source": resolved.source,
                "active_snapshot_id": resolved.active_snapshot_id,
                "document_version": resolved.document_version,
                "revision": resolved.revision,
                "lifecycle_status": dossier.lifecycle.status,
                "study_case_state": dossier.study_case.state,
                "paee_state": dossier.paee.state,
                "pei_state": dossier.pei.state,
                "schedule_sessions": len(dossier.schedule.sessions),
            }
        )
    except AEEV2RepositoryError as exc:
        diagnostic["error"] = {
            "code": getattr(exc, "code", "AEE_V2_REPOSITORY_ERROR"),
            "message": str(exc),
        }
    except Exception:
        diagnostic["error"] = {
            "code": "AEE_V2_PLANO_SHADOW_RESOLUTION_ERROR",
            "message": "Falha inesperada ao calcular a Fonte Efetiva do Plano AEE.",
        }
        logger.exception(
            "AEE v2 plano shadow: falha inesperada ao resolver plano %s",
            plano_id,
        )

    return diagnostic


def _log_diagnostic(diagnostic: dict[str, Any]) -> None:
    level = logging.WARNING if diagnostic.get("error") else logging.INFO
    logger.log(
        level,
        "AEE_V2_PLANO_SHADOW %s",
        json.dumps(diagnostic, ensure_ascii=False, sort_keys=True),
    )


def install_aee_v2_plano_shadow(
    base_router,
    db,
    *,
    resolver: Optional[Resolver] = None,
    diagnostics_builder: Optional[DiagnosticBuilder] = None,
):
    """Envolve somente ``GET /aee/planos/{plano_id}`` em Shadow Mode."""

    if getattr(base_router, "_aee_v2_plano_shadow_installed", False):
        return base_router

    target = _route_for(base_router, "/aee/planos/{plano_id}", "GET")
    original_endpoint = target.endpoint
    signature = inspect.signature(original_endpoint)
    builder = diagnostics_builder

    @wraps(original_endpoint)
    async def shadow_endpoint(*args, **kwargs):
        result = await original_endpoint(*args, **kwargs)

        try:
            bound = signature.bind_partial(*args, **kwargs)
            plano_id = bound.arguments.get("plano_id")
            if plano_id is None and isinstance(result, dict):
                plano_id = result.get("id")

            if not plano_id:
                diagnostic = _base_diagnostic("UNKNOWN")
                diagnostic["legacy_plano_id"] = None
                diagnostic["error"] = {
                    "code": "AEE_V2_PLANO_SHADOW_PLAN_ID_MISSING",
                    "message": "Não foi possível identificar o Plano AEE retornado.",
                }
            elif builder is not None:
                diagnostic = await builder(db, str(plano_id))
            else:
                diagnostic = await build_plano_shadow_diagnostic(
                    db,
                    str(plano_id),
                    resolver=resolver,
                )

            _log_diagnostic(diagnostic)
        except Exception:  # pragma: no cover - isolamento defensivo do shadow
            logger.exception(
                "AEE v2 plano shadow: diagnóstico falhou; resposta legado preservada"
            )

        # Requisito central da 6.4A: o mesmo objeto retornado pelo legado.
        return result

    # FastAPI 0.110.1 clona APIRoute em include_router() a partir de endpoint.
    target.endpoint = shadow_endpoint
    target.dependant.call = shadow_endpoint

    setattr(base_router, "_aee_v2_plano_shadow_installed", True)
    return base_router


def install_aee_v2_plano_shadow_setup(aee_module):
    """Instala a 6.4A após os adapters AEE previamente configurados."""

    if getattr(aee_module, "_aee_v2_plano_shadow_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_plano_shadow(configured, db)

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_plano_shadow_setup_installed = True
