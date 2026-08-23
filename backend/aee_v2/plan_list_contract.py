"""Fase 6.6B — contrato HTTP aditivo da listagem de Planos AEE.

O adapter preserva integralmente os campos legado de ``GET /aee/planos`` e
acrescenta, por item, o read model público da Fonte Efetiva V2. A resolução
batch é executada exatamente uma vez por request.

Invariantes centrais:
- nenhum write provocado pela listagem;
- nenhuma alteração de filtros, total, paginação ou ordenação legado;
- nenhum cutover visual nesta fase;
- no máximo 1 query de heads + 1 query de snapshots por lote;
- o wrapper 6.6A não pode ficar empilhado sob a 6.6B.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from functools import wraps
import inspect
import json
import logging
from time import perf_counter
from typing import Any, Awaitable, Callable, Optional

from fastapi import HTTPException, status

from .plan_list_effective import resolve_plan_list_effective_batch
from .plan_list_shadow import build_plan_list_shadow_diagnostic


logger = logging.getLogger(__name__)

BatchResolver = Callable[[Any, Sequence[Mapping[str, Any]]], Awaitable[dict[str, Any]]]
UserGetter = Callable[[Any], Awaitable[dict[str, Any]]]

PUBLIC_FIELDS = (
    "v2_managed",
    "effective_source",
    "effective_version",
    "effective_summary",
    "effective_error",
    "mutation_policy",
)

_ALLOWED_SOURCES = {"legacy", "sidecar_active", None}
_ALLOWED_SCHEDULE_SHAPES = {
    "legacy_projection",
    "empty",
    "homogeneous",
    "heterogeneous",
    None,
}


class PlanListContractError(ValueError):
    """Falha estrutural que impede materializar o contrato aditivo 6.6B."""


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
            f"AEE v2 Plan List Contract esperava exatamente uma rota {method} {path}; "
            f"encontrou {len(matches)}."
        )
    return matches[0]


def _plan_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def derive_mutation_policy(summary: Mapping[str, Any]) -> str:
    """Deriva somente a política informativa da 6.6B, sem enforcement."""

    if isinstance(summary.get("integrity_error"), Mapping):
        return "blocked_integrity"
    if isinstance(summary.get("working_integrity_error"), Mapping):
        return "blocked_integrity"
    if bool(summary.get("v2_managed")):
        return "dossier_v2_required"
    return "legacy_allowed"


def _public_effective_error(summary: Mapping[str, Any]) -> Optional[dict[str, str]]:
    error = summary.get("integrity_error")
    if error is None:
        return None
    if not isinstance(error, Mapping) or not error.get("code"):
        raise PlanListContractError("Erro de integridade do resolver sem código estável.")
    return {
        "code": str(error.get("code")),
        "message": str(
            error.get("message")
            or "Falha de integridade da Fonte Efetiva AEE v2."
        ),
    }


def project_plan_list_contract_item(
    legacy_item: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Copia o item legado e acrescenta exclusivamente os seis campos 6.6B."""

    if not isinstance(legacy_item, Mapping) or not isinstance(summary, Mapping):
        raise PlanListContractError("Item legado/summary inválido para contrato 6.6B.")

    collisions = [field for field in PUBLIC_FIELDS if field in legacy_item]
    if collisions:
        raise PlanListContractError(
            "Contrato legado já contém campos reservados da 6.6B: "
            + ", ".join(sorted(collisions))
        )

    source = summary.get("effective_source")
    if source not in _ALLOWED_SOURCES:
        raise PlanListContractError(f"Fonte Efetiva não suportada: {source!r}.")

    version = summary.get("effective_version")
    if not isinstance(version, Mapping):
        raise PlanListContractError("Resolver batch sem effective_version válido.")

    shape = summary.get("schedule_shape")
    if shape not in _ALLOWED_SCHEDULE_SHAPES:
        raise PlanListContractError(f"Formato de agenda não suportado: {shape!r}.")

    days = summary.get("effective_days")
    if days is None:
        public_days = None
    elif isinstance(days, (list, tuple)):
        public_days = list(days)
    else:
        raise PlanListContractError("effective_days deve ser lista ou null.")

    effective_error = _public_effective_error(summary)
    if source is None and effective_error is None:
        raise PlanListContractError(
            "Fonte Efetiva nula sem effective_error representável."
        )

    projected = dict(legacy_item)
    projected.update(
        {
            "v2_managed": bool(summary.get("v2_managed")),
            "effective_source": source,
            "effective_version": {
                "active_snapshot_id": version.get("active_snapshot_id"),
                "document_version": version.get("document_version"),
                "revision": version.get("revision"),
                "working_snapshot_id": version.get("working_snapshot_id"),
            },
            "effective_summary": {
                "lifecycle_status": summary.get("effective_lifecycle_status"),
                "legacy_compatible_status": summary.get("effective_legacy_status"),
                "schedule_summary": {
                    "days": public_days,
                    "shape": shape,
                },
            },
            "effective_error": effective_error,
            "mutation_policy": derive_mutation_policy(summary),
        }
    )
    return projected


def apply_plan_list_contract(
    legacy_result: Mapping[str, Any],
    batch_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Materializa o contrato aditivo sem alterar ``total`` ou os itens origem."""

    if not isinstance(legacy_result, Mapping):
        raise PlanListContractError("Resposta legado da listagem não é objeto JSON.")
    legacy_items = legacy_result.get("items")
    if not isinstance(legacy_items, list):
        raise PlanListContractError("Resposta legado não contém items list.")

    if not isinstance(batch_result, Mapping):
        raise PlanListContractError("Resolver batch retornou estrutura inválida.")
    summaries = batch_result.get("items")
    if not isinstance(summaries, list):
        raise PlanListContractError("Resolver batch não retornou items list.")
    if len(summaries) != len(legacy_items):
        raise PlanListContractError(
            "Quantidade de summaries diverge da página legado retornada."
        )

    legacy_ids: list[str] = []
    seen_legacy: set[str] = set()
    for item in legacy_items:
        if not isinstance(item, Mapping):
            raise PlanListContractError("Página legado contém item não mapeável.")
        item_id = _plan_id(item.get("id"))
        if not item_id:
            raise PlanListContractError("Página legado contém Plano sem id.")
        if item_id in seen_legacy:
            raise PlanListContractError("Página legado contém id de Plano duplicado.")
        seen_legacy.add(item_id)
        legacy_ids.append(item_id)

    summaries_by_id: dict[str, Mapping[str, Any]] = {}
    for summary in summaries:
        if not isinstance(summary, Mapping):
            raise PlanListContractError("Resolver batch contém summary inválido.")
        summary_id = _plan_id(summary.get("legacy_plano_id"))
        if not summary_id:
            raise PlanListContractError("Resolver batch contém summary sem legacy_plano_id.")
        if summary_id in summaries_by_id:
            raise PlanListContractError("Resolver batch contém legacy_plano_id duplicado.")
        summaries_by_id[summary_id] = summary

    if set(legacy_ids) != set(summaries_by_id):
        raise PlanListContractError(
            "Não foi possível casar integralmente a página legado com os summaries V2."
        )

    result = dict(legacy_result)
    result["items"] = [
        project_plan_list_contract_item(item, summaries_by_id[item_id])
        for item, item_id in zip(legacy_items, legacy_ids)
    ]
    return result


def select_effective_ids_for_status(
    summaries: Sequence[Mapping[str, Any]],
    status_filter: str,
) -> set[str]:
    """Helper puro preparatório da 6.6C; não é usado no runtime 6.6B."""

    selected: set[str] = set()
    for summary in summaries:
        if not isinstance(summary, Mapping):
            continue
        if summary.get("effective_source") not in {"legacy", "sidecar_active"}:
            continue
        if summary.get("effective_legacy_status") != status_filter:
            continue
        plan_id = _plan_id(summary.get("legacy_plano_id"))
        if plan_id:
            selected.add(plan_id)
    return selected


def build_plan_list_additive_diagnostic(
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
    contract_ms: float,
) -> dict[str, Any]:
    """Reaproveita a métrica 6.6A sem ativar o wrapper Shadow no runtime."""

    diagnostic = build_plan_list_shadow_diagnostic(
        legacy_result,
        batch_result,
        academic_year=academic_year,
        school_id=school_id,
        student_id=student_id,
        professor_aee_id=professor_aee_id,
        status_filter=status_filter,
        skip=skip,
        limit=limit,
        role=role,
        shadow_ms=contract_ms,
    )
    diagnostic["phase"] = "6.6B"
    diagnostic["mode"] = "additive_contract"
    if diagnostic.get("status") == "parity":
        diagnostic["status"] = "effective"

    summaries = batch_result.get("items") or []
    policies = Counter(
        derive_mutation_policy(summary)
        for summary in summaries
        if isinstance(summary, Mapping)
    )
    diagnostic["mutation_policies"] = dict(sorted(policies.items()))
    diagnostic["filter_preview"] = diagnostic.pop("filter_shadow")

    performance = diagnostic.get("performance")
    if isinstance(performance, dict):
        performance.pop("shadow_ms", None)
        performance["contract_ms"] = round(float(contract_ms), 3)

    return diagnostic


def _log_diagnostic(diagnostic: Mapping[str, Any]) -> None:
    sources = diagnostic.get("sources")
    if not isinstance(sources, Mapping):
        sources = {}
    needs_warning = (
        diagnostic.get("status") != "effective"
        or int(sources.get("sidecar_active") or 0) > 0
    )
    logger.log(
        logging.WARNING if needs_warning else logging.INFO,
        "AEE_V2_PLAN_LIST_ADDITIVE %s",
        json.dumps(diagnostic, ensure_ascii=False, default=str, sort_keys=True),
    )


async def _role_for_request(request: Any, user_getter: Optional[UserGetter]) -> Optional[str]:
    if request is None:
        return None
    if user_getter is None:
        # Import lazy para manter o Contract Guard isolado da pilha JWT/bcrypt.
        from auth_middleware import AuthMiddleware

        getter = AuthMiddleware.get_current_user
    else:
        getter = user_getter
    try:
        user = await getter(request)
    except Exception:
        # O endpoint legado já autenticou/autorizou; esta leitura é só telemetria.
        return None
    if isinstance(user, Mapping) and user.get("role"):
        return str(user.get("role"))
    return None


def install_aee_v2_plan_list_contract(
    base_router,
    db,
    *,
    batch_resolver: Optional[BatchResolver] = None,
    user_getter: Optional[UserGetter] = None,
):
    """Substitui operacionalmente a 6.6A por um único adapter aditivo 6.6B."""

    if getattr(base_router, "_aee_v2_plan_list_contract_installed", False):
        return base_router
    if getattr(base_router, "_aee_v2_plan_list_shadow_installed", False):
        raise RuntimeError(
            "AEE v2 6.6B não pode ser empilhada sobre o wrapper 6.6A."
        )

    target = _route_for(base_router, "/aee/planos", "GET")
    original_endpoint = target.endpoint
    signature = inspect.signature(original_endpoint)
    resolve_batch = batch_resolver or resolve_plan_list_effective_batch

    @wraps(original_endpoint)
    async def additive_endpoint(*args, **kwargs):
        # Exceções normais do endpoint legado permanecem intactas.
        legacy_result = await original_endpoint(*args, **kwargs)
        started = perf_counter()

        try:
            if not isinstance(legacy_result, Mapping):
                raise PlanListContractError(
                    "Resposta legado da listagem AEE não é objeto JSON."
                )
            legacy_items = legacy_result.get("items")
            if not isinstance(legacy_items, list):
                raise PlanListContractError(
                    "Resposta legado da listagem AEE não contém items list."
                )

            bound = signature.bind_partial(*args, **kwargs)
            batch = await resolve_batch(db, legacy_items)
            additive_result = apply_plan_list_contract(legacy_result, batch)

            request = bound.arguments.get("request")
            role = await _role_for_request(request, user_getter)
            contract_ms = (perf_counter() - started) * 1000.0
            diagnostic = build_plan_list_additive_diagnostic(
                legacy_result,
                batch,
                academic_year=bound.arguments.get("academic_year"),
                school_id=bound.arguments.get("school_id"),
                student_id=bound.arguments.get("student_id"),
                professor_aee_id=bound.arguments.get("professor_aee_id"),
                status_filter=bound.arguments.get("status_filter"),
                skip=bound.arguments.get("skip", 0),
                limit=bound.arguments.get("limit", 100),
                role=role,
                contract_ms=contract_ms,
            )
            _log_diagnostic(diagnostic)
            return additive_result
        except Exception as exc:
            logger.exception(
                "AEE_V2_PLAN_LIST_ADDITIVE_ERROR %s",
                json.dumps(
                    {
                        "phase": "6.6B",
                        "mode": "additive_contract",
                        "status": "unavailable",
                    },
                    sort_keys=True,
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "AEE_V2_PLAN_LIST_CONTRACT_UNAVAILABLE",
                    "message": (
                        "O contrato de Fonte Efetiva da listagem AEE está "
                        "temporariamente indisponível."
                    ),
                },
            ) from exc

    target.endpoint = additive_endpoint
    target.dependant.call = additive_endpoint
    setattr(base_router, "_aee_v2_plan_list_contract_installed", True)
    return base_router


def install_aee_v2_plan_list_contract_setup(aee_module):
    """Instala somente a 6.6B na cadeia de setup do router AEE."""

    if getattr(aee_module, "_aee_v2_plan_list_contract_setup_installed", False):
        return
    if getattr(aee_module, "_aee_v2_plan_list_shadow_setup_installed", False):
        raise RuntimeError(
            "AEE v2 6.6B exige que o installer 6.6A não esteja ativo no setup."
        )

    original_setup = aee_module.setup_aee_router

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_plan_list_contract(configured, db)

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_plan_list_contract_setup_installed = True
