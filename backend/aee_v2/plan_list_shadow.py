"""Fase 6.6A — Shadow Mode read-only da listagem de Planos AEE.

O endpoint legado ``GET /aee/planos`` executa primeiro e sua resposta é devolvida
sem qualquer mutação. Esta camada observa apenas os itens já autorizados,
filtrados e paginados pelo legado, resolve a Fonte Efetiva em lote e registra
telemetria agregada.

Nenhum campo ``effective_*`` é exposto ao HTTP e nenhuma coleção é escrita.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import wraps
import inspect
import json
import logging
from time import perf_counter
from typing import Any, Awaitable, Callable, Optional

from auth_middleware import AuthMiddleware

from .plan_list_effective import resolve_plan_list_effective_batch


logger = logging.getLogger(__name__)

BatchResolver = Callable[[Any, list[Mapping[str, Any]]], Awaitable[dict[str, Any]]]
UserGetter = Callable[[Any], Awaitable[dict[str, Any]]]


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
            f"AEE v2 Plan List Shadow esperava exatamente uma rota {method} {path}; "
            f"encontrou {len(matches)}."
        )
    return matches[0]


def _increment(counter: dict[str, int], key: Optional[str]) -> None:
    if not key:
        return
    counter[key] = counter.get(key, 0) + 1


def build_plan_list_shadow_diagnostic(
    legacy_result: Mapping[str, Any],
    batch_result: Mapping[str, Any],
    *,
    academic_year: Optional[int],
    school_id: Optional[str],
    student_id: Optional[str],
    professor_aee_id: Optional[str],
    status_filter: Optional[str],
    skip: int,
    limit: int,
    role: Optional[str],
    shadow_ms: float,
) -> dict[str, Any]:
    """Agrega métricas sem PII e sem alterar os objetos observados."""

    batch_items = batch_result.get("items")
    if not isinstance(batch_items, list):
        raise ValueError("Resolver batch 6.6A não retornou lista de itens.")

    v2_managed = 0
    legacy_effective = 0
    working_only = 0
    sidecar_active = 0

    status_compared = 0
    status_equal = 0
    status_divergent = 0
    transitions: dict[str, int] = {}

    days_compared = 0
    days_equal = 0
    days_divergent = 0
    heterogeneous = 0

    returned_effective_mismatch = 0
    integrity_errors = 0
    working_errors = 0
    integrity_by_code: dict[str, int] = {}

    for item in batch_items:
        if not isinstance(item, Mapping):
            continue

        if item.get("v2_managed"):
            v2_managed += 1
        if item.get("effective_source") == "legacy":
            legacy_effective += 1
        if item.get("management_state") == "working_only":
            working_only += 1
        if item.get("effective_source") == "sidecar_active":
            sidecar_active += 1

        status_parity = item.get("status_parity")
        if isinstance(status_parity, bool):
            status_compared += 1
            if status_parity:
                status_equal += 1
            else:
                status_divergent += 1
                transition = (
                    f"{item.get('legacy_status') or 'null'}"
                    f"->{item.get('effective_legacy_status') or 'null'}"
                )
                _increment(transitions, transition)

        days_parity = item.get("days_parity")
        if isinstance(days_parity, bool):
            days_compared += 1
            if days_parity:
                days_equal += 1
            else:
                days_divergent += 1

        if item.get("schedule_shape") == "heterogeneous":
            heterogeneous += 1

        if (
            status_filter
            and item.get("effective_source") in {"legacy", "sidecar_active"}
            and item.get("effective_legacy_status") != status_filter
        ):
            returned_effective_mismatch += 1

        integrity_error = item.get("integrity_error")
        if isinstance(integrity_error, Mapping):
            integrity_errors += 1
            _increment(integrity_by_code, str(integrity_error.get("code") or "UNKNOWN"))

        working_error = item.get("working_integrity_error")
        if isinstance(working_error, Mapping):
            working_errors += 1
            _increment(
                integrity_by_code,
                str(working_error.get("code") or "AEE_V2_WORKING_UNKNOWN"),
            )

    if integrity_errors or working_errors:
        status = "partial_error"
    elif status_divergent or days_divergent or returned_effective_mismatch:
        status = "divergent"
    else:
        status = "parity"

    performance = batch_result.get("performance")
    if not isinstance(performance, Mapping):
        performance = {}

    legacy_items = legacy_result.get("items")
    items_returned = len(legacy_items) if isinstance(legacy_items, list) else 0

    return {
        "phase": "6.6A",
        "mode": "shadow_read_only",
        "status": status,
        "scope": {
            "academic_year": academic_year,
            "school_filter": bool(school_id),
            "student_filter": bool(student_id),
            "professor_filter": bool(professor_aee_id),
            "status_filter": status_filter,
            "role": role or "unknown",
        },
        "page": {
            "skip": int(skip or 0),
            "limit": int(limit or 100),
            "items_returned": items_returned,
            "legacy_total": legacy_result.get("total"),
        },
        "sources": {
            "v2_managed": v2_managed,
            "legacy_effective": legacy_effective,
            "working_only": working_only,
            "sidecar_active": sidecar_active,
        },
        "status_compare": {
            "compared": status_compared,
            "equal": status_equal,
            "divergent": status_divergent,
            "transitions": transitions,
        },
        "schedule_compare": {
            "days_compared": days_compared,
            "days_equal": days_equal,
            "days_divergent": days_divergent,
            "heterogeneous_v2": heterogeneous,
        },
        "filter_shadow": {
            "returned_effective_mismatch": returned_effective_mismatch,
            "population_audit_required": bool(status_filter),
        },
        "integrity": {
            "errors": integrity_errors,
            "working_errors": working_errors,
            "by_code": integrity_by_code,
        },
        "performance": {
            "head_queries": int(performance.get("head_queries") or 0),
            "snapshot_queries": int(performance.get("snapshot_queries") or 0),
            "batch_ms": float(performance.get("batch_ms") or 0.0),
            "shadow_ms": round(float(shadow_ms), 3),
        },
    }


def _log_diagnostic(diagnostic: Mapping[str, Any]) -> None:
    sources = diagnostic.get("sources") if isinstance(diagnostic.get("sources"), Mapping) else {}
    needs_warning = (
        diagnostic.get("status") != "parity"
        or int(sources.get("sidecar_active") or 0) > 0
    )
    level = logging.WARNING if needs_warning else logging.INFO
    logger.log(
        level,
        "AEE_V2_PLAN_LIST_SHADOW %s",
        json.dumps(diagnostic, ensure_ascii=False, default=str, sort_keys=True),
    )


async def _role_for_request(request: Any, user_getter: Optional[UserGetter]) -> Optional[str]:
    if request is None:
        return None
    getter = user_getter or AuthMiddleware.get_current_user
    try:
        user = await getter(request)
    except Exception:
        # Autenticação/autorização do endpoint legado já ocorreu. Falha nesta leitura
        # secundária afeta somente a cardinalidade do log, nunca a resposta.
        return None
    if isinstance(user, Mapping):
        role = user.get("role")
        return str(role) if role else None
    return None


def install_aee_v2_plan_list_shadow(
    base_router,
    db,
    *,
    batch_resolver: Optional[BatchResolver] = None,
    user_getter: Optional[UserGetter] = None,
):
    """Envolve somente ``GET /aee/planos`` e preserva o mesmo resultado legado."""

    if getattr(base_router, "_aee_v2_plan_list_shadow_installed", False):
        return base_router

    target = _route_for(base_router, "/aee/planos", "GET")
    original_endpoint = target.endpoint
    signature = inspect.signature(original_endpoint)
    resolve_batch = batch_resolver or resolve_plan_list_effective_batch

    @wraps(original_endpoint)
    async def shadow_endpoint(*args, **kwargs):
        result = await original_endpoint(*args, **kwargs)
        started = perf_counter()

        try:
            if not isinstance(result, Mapping):
                raise ValueError("Resposta legado da listagem AEE não é objeto JSON.")
            items = result.get("items")
            if not isinstance(items, list):
                raise ValueError("Resposta legado da listagem AEE não contém items list.")

            bound = signature.bind_partial(*args, **kwargs)
            batch = await resolve_batch(db, items)
            request = bound.arguments.get("request")
            role = await _role_for_request(request, user_getter)
            diagnostic = build_plan_list_shadow_diagnostic(
                result,
                batch,
                academic_year=bound.arguments.get("academic_year"),
                school_id=bound.arguments.get("school_id"),
                student_id=bound.arguments.get("student_id"),
                professor_aee_id=bound.arguments.get("professor_aee_id"),
                status_filter=bound.arguments.get("status_filter"),
                skip=bound.arguments.get("skip", 0),
                limit=bound.arguments.get("limit", 100),
                role=role,
                shadow_ms=(perf_counter() - started) * 1000.0,
            )
            _log_diagnostic(diagnostic)
        except Exception:  # pragma: no cover - isolamento defensivo do Shadow
            logger.exception(
                "AEE v2 plan list shadow: diagnóstico falhou; resposta legado preservada"
            )

        # Invariante central 6.6A: exatamente o objeto devolvido pelo endpoint legado.
        return result

    target.endpoint = shadow_endpoint
    target.dependant.call = shadow_endpoint
    setattr(base_router, "_aee_v2_plan_list_shadow_installed", True)
    return base_router


def install_aee_v2_plan_list_shadow_setup(aee_module):
    """Instala a 6.6A após os adapters AEE previamente encadeados."""

    if getattr(aee_module, "_aee_v2_plan_list_shadow_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_plan_list_shadow(configured, db)

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_plan_list_shadow_setup_installed = True
