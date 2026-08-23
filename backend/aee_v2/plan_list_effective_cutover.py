"""Fase 6.6C — cutover controlado da leitura/UX da listagem de Planos AEE.

A 6.6C substitui operacionalmente o adapter 6.6B e mantém o router legado
intacto. Sem ``status_filter``, o endpoint legado continua responsável por
RBAC, filtros de identidade, total e paginação; a Fonte Efetiva é resolvida
somente para a página retornada. Com ``status_filter``, a seleção pelo status
precisa ocorrer antes de ``total``/``skip``/``limit`` e, por isso, este adapter
reproduz exatamente o escopo autorizado do endpoint legado, resolve todos os
candidatos em um único lote V2 e só então materializa a página final.

Invariantes:
- zero writes e zero migração;
- ``backend/routers/aee.py`` permanece intacto;
- uma única resolução batch por request;
- no máximo 1 query de heads + 1 query de snapshots por resolução batch;
- contrato público 6.6B preservado;
- erro de integridade não produz fallback silencioso para o legado;
- PUT/duplicação continuam fora de escopo até a Fase 6.6D.
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

from .plan_list_contract import (
    apply_plan_list_contract,
    derive_mutation_policy,
    select_effective_ids_for_status,
)
from .plan_list_effective import resolve_plan_list_effective_batch


logger = logging.getLogger(__name__)

BatchResolver = Callable[[Any, Sequence[Mapping[str, Any]]], Awaitable[dict[str, Any]]]
UserGetter = Callable[[Any], Awaitable[dict[str, Any]]]

_CANDIDATE_PROJECTION = {
    "_id": 0,
    "id": 1,
    "student_id": 1,
    "school_id": 1,
    "academic_year": 1,
    "status": 1,
    "dias_atendimento": 1,
}


class PlanListEffectiveCutoverError(ValueError):
    """Falha estrutural global que impede a leitura efetiva 6.6C."""


class PlanListEffectiveFilterIntegrityBlocked(Exception):
    """Filtro efetivo cujo universo contém status semanticamente indeterminado."""

    def __init__(self, diagnostic: Mapping[str, Any]):
        super().__init__("Filtro efetivo bloqueado por integridade AEE v2.")
        self.diagnostic = dict(diagnostic)


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
            f"AEE v2 Plan List Effective esperava exatamente uma rota {method} {path}; "
            f"encontrou {len(matches)}."
        )
    return matches[0]


def _plan_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_effective_candidate_filter(
    *,
    school_id: Optional[str],
    student_id: Optional[str],
    academic_year: Optional[int],
    professor_aee_id: Optional[str],
    current_user: Mapping[str, Any],
) -> dict[str, Any]:
    """Replica o escopo do GET legado sem aplicar ``status_filter``.

    A ordem e a combinação das condições reproduzem ``routers/aee.py``:
    filtros explícitos são AND; para professor acrescenta-se o OR
    ``professor_aee_id == uid`` ou ``created_by == uid``.
    """

    filter_query: dict[str, Any] = {}
    if school_id:
        filter_query["school_id"] = school_id
    if student_id:
        filter_query["student_id"] = student_id
    if academic_year:
        filter_query["academic_year"] = academic_year
    if professor_aee_id:
        filter_query["professor_aee_id"] = professor_aee_id

    if current_user.get("role") == "professor":
        uid = current_user.get("id")
        filter_query.setdefault("$or", []).extend(
            [
                {"professor_aee_id": uid},
                {"created_by": uid},
            ]
        )
    return filter_query


async def _authorized_current_user(
    request: Any,
    *,
    allowed_roles: Sequence[str],
    user_getter: Optional[UserGetter],
) -> Mapping[str, Any]:
    if user_getter is None:
        # Import lazy preserva o Contract Guard isolado da pilha JWT/bcrypt.
        from auth_middleware import AuthMiddleware

        getter = AuthMiddleware.get_current_user
    else:
        getter = user_getter

    user = await getter(request)
    if not isinstance(user, Mapping):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso não autorizado ao módulo AEE",
        )
    if user.get("role") not in set(allowed_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso não autorizado ao módulo AEE",
        )
    return user


async def _role_for_telemetry(
    request: Any,
    *,
    user_getter: Optional[UserGetter],
) -> Optional[str]:
    if request is None:
        return None
    if user_getter is None:
        from auth_middleware import AuthMiddleware

        getter = AuthMiddleware.get_current_user
    else:
        getter = user_getter
    try:
        user = await getter(request)
    except Exception:
        return None
    if isinstance(user, Mapping) and user.get("role"):
        return str(user.get("role"))
    return None


def _summaries_by_id(batch_result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    summaries = batch_result.get("items")
    if not isinstance(summaries, list):
        raise PlanListEffectiveCutoverError("Resolver batch não retornou items list.")

    indexed: dict[str, Mapping[str, Any]] = {}
    for summary in summaries:
        if not isinstance(summary, Mapping):
            raise PlanListEffectiveCutoverError("Resolver batch contém summary inválido.")
        plan_id = _plan_id(summary.get("legacy_plano_id"))
        if not plan_id:
            raise PlanListEffectiveCutoverError("Summary sem legacy_plano_id.")
        if plan_id in indexed:
            raise PlanListEffectiveCutoverError("Resolver batch contém Plano duplicado.")
        indexed[plan_id] = summary
    return indexed


def _primary_integrity_items(
    summaries: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return [
        summary
        for summary in summaries
        if summary.get("effective_source") is None
        or isinstance(summary.get("integrity_error"), Mapping)
    ]


def select_effective_page(
    candidates: Sequence[Mapping[str, Any]],
    batch_result: Mapping[str, Any],
    *,
    status_filter: str,
    skip: int,
    limit: int,
) -> dict[str, Any]:
    """Seleciona IDs pelo status efetivo antes da paginação, preservando ordem."""

    summaries = batch_result.get("items")
    if not isinstance(summaries, list) or len(summaries) != len(candidates):
        raise PlanListEffectiveCutoverError(
            "Quantidade de summaries diverge do universo candidato autorizado."
        )
    indexed = _summaries_by_id(batch_result)

    candidate_ids: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise PlanListEffectiveCutoverError("Candidato da listagem não é mapeável.")
        plan_id = _plan_id(candidate.get("id"))
        if not plan_id:
            raise PlanListEffectiveCutoverError("Candidato sem id de Plano.")
        if plan_id in seen:
            raise PlanListEffectiveCutoverError("Universo candidato contém id duplicado.")
        seen.add(plan_id)
        candidate_ids.append(plan_id)

    if set(candidate_ids) != set(indexed):
        raise PlanListEffectiveCutoverError(
            "Não foi possível casar candidatos com summaries da Fonte Efetiva."
        )

    primary_errors = _primary_integrity_items(
        [indexed[plan_id] for plan_id in candidate_ids]
    )
    if primary_errors:
        return {
            "blocked": True,
            "candidate_ids": candidate_ids,
            "effective_ids": [],
            "page_ids": [],
            "effective_total": None,
            "legacy_matches_preview": sum(
                1 for candidate in candidates if candidate.get("status") == status_filter
            ),
            "integrity_errors": len(primary_errors),
        }

    selected = select_effective_ids_for_status(
        [indexed[plan_id] for plan_id in candidate_ids],
        status_filter,
    )
    effective_ids = [plan_id for plan_id in candidate_ids if plan_id in selected]
    page_ids = effective_ids[skip : skip + limit]

    return {
        "blocked": False,
        "candidate_ids": candidate_ids,
        "effective_ids": effective_ids,
        "page_ids": page_ids,
        "effective_total": len(effective_ids),
        "legacy_matches_preview": sum(
            1 for candidate in candidates if candidate.get("status") == status_filter
        ),
        "integrity_errors": 0,
    }


async def _load_candidates(db, filter_query: Mapping[str, Any]) -> list[dict[str, Any]]:
    cursor = db.planos_aee.find(dict(filter_query), dict(_CANDIDATE_PROJECTION))
    rows = await cursor.to_list(length=None)
    return [dict(row) for row in rows if isinstance(row, Mapping)]


async def _materialize_page(
    db,
    page_ids: Sequence[str],
) -> list[dict[str, Any]]:
    if not page_ids:
        return []

    cursor = db.planos_aee.find(
        {"id": {"$in": list(page_ids)}},
        {"_id": 0},
    )
    docs = await cursor.to_list(length=len(page_ids))
    by_id = {
        str(doc.get("id")): dict(doc)
        for doc in docs
        if isinstance(doc, Mapping) and doc.get("id")
    }
    if set(by_id) != set(page_ids):
        raise PlanListEffectiveCutoverError(
            "Materialização da página não retornou todos os Planos selecionados."
        )

    ordered = [by_id[plan_id] for plan_id in page_ids]
    # Mantém o contrato histórico student_name; o N+1 legado fica restrito à página.
    for plan in ordered:
        student = await db.students.find_one(
            {"id": plan.get("student_id")},
            {"_id": 0, "full_name": 1},
        )
        plan["student_name"] = student.get("full_name") if student else "N/A"
    return ordered


def _source_counts(summaries: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "legacy_effective": sum(
            1 for item in summaries if item.get("effective_source") == "legacy"
        ),
        "sidecar_active": sum(
            1 for item in summaries if item.get("effective_source") == "sidecar_active"
        ),
        "v2_managed": sum(1 for item in summaries if bool(item.get("v2_managed"))),
        "working_only": sum(
            1 for item in summaries if item.get("management_state") == "working_only"
        ),
    }


def _status_compare(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    transitions = Counter()
    equal = 0
    divergent = 0
    for item in summaries:
        legacy = item.get("legacy_status")
        effective = item.get("effective_legacy_status")
        if legacy is None or effective is None:
            continue
        transitions[f"{legacy}->{effective}"] += 1
        if legacy == effective:
            equal += 1
        else:
            divergent += 1
    return {
        "equal": equal,
        "divergent": divergent,
        "transitions": dict(sorted(transitions.items())),
    }


def _integrity_counts(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    codes = Counter()
    errors = 0
    working_errors = 0
    for item in summaries:
        error = item.get("integrity_error")
        if isinstance(error, Mapping):
            errors += 1
            if error.get("code"):
                codes[str(error.get("code"))] += 1
        working = item.get("working_integrity_error")
        if isinstance(working, Mapping):
            working_errors += 1
            if working.get("code"):
                codes[str(working.get("code"))] += 1
    return {
        "errors": errors,
        "working_errors": working_errors,
        "by_code": dict(sorted(codes.items())),
    }


def build_effective_list_diagnostic(
    *,
    summaries: Sequence[Mapping[str, Any]],
    academic_year: Optional[int],
    school_id: Optional[str],
    student_id: Optional[str],
    professor_aee_id: Optional[str],
    status_filter: Optional[str],
    role: Optional[str],
    skip: int,
    limit: int,
    items_returned: int,
    effective_total: int,
    candidate_total: int,
    legacy_matches_preview: Optional[int],
    candidate_query_ms: float,
    materialize_ms: float,
    total_ms: float,
    batch_result: Mapping[str, Any],
    forced_status: Optional[str] = None,
) -> dict[str, Any]:
    """Monta telemetria agregada 6.6C sem PII/IDs de entidades."""

    summaries_list = [item for item in summaries if isinstance(item, Mapping)]
    integrity = _integrity_counts(summaries_list)
    status_compare = _status_compare(summaries_list)
    sources = _source_counts(summaries_list)

    batch_perf = batch_result.get("performance")
    if not isinstance(batch_perf, Mapping):
        batch_perf = {}

    effective_matches = effective_total if status_filter else None
    total_delta = (
        effective_total - legacy_matches_preview
        if status_filter and legacy_matches_preview is not None
        else 0
    )

    if forced_status:
        diagnostic_status = forced_status
    elif integrity["errors"]:
        diagnostic_status = "integrity_blocked"
    elif status_compare["divergent"]:
        diagnostic_status = "divergent"
    else:
        diagnostic_status = "effective"

    policies = Counter(
        derive_mutation_policy(item) for item in summaries_list
    )

    return {
        "phase": "6.6C",
        "mode": "effective_read_cutover",
        "status": diagnostic_status,
        "scope": {
            "academic_year": academic_year,
            "school_filter": bool(school_id),
            "student_filter": bool(student_id),
            "professor_filter": bool(professor_aee_id),
            "status_filter": status_filter,
            "role": role,
        },
        "page": {
            "skip": skip,
            "limit": limit,
            "items_returned": items_returned,
            "effective_total": effective_total,
        },
        "candidates": {"total": candidate_total},
        "sources": sources,
        "status_compare": status_compare,
        "filter": {
            "requested_status": status_filter,
            "effective_matches": effective_matches,
            "legacy_matches_preview": legacy_matches_preview,
            "total_delta": total_delta,
        },
        "integrity": integrity,
        "mutation_policies": dict(sorted(policies.items())),
        "performance": {
            "candidate_query_ms": round(float(candidate_query_ms), 3),
            "batch_ms": batch_perf.get("batch_ms"),
            "materialize_ms": round(float(materialize_ms), 3),
            "total_ms": round(float(total_ms), 3),
            "head_queries": int(batch_perf.get("head_queries") or 0),
            "snapshot_queries": int(batch_perf.get("snapshot_queries") or 0),
        },
    }


def _log_diagnostic(diagnostic: Mapping[str, Any]) -> None:
    sources = diagnostic.get("sources")
    if not isinstance(sources, Mapping):
        sources = {}
    filter_data = diagnostic.get("filter")
    if not isinstance(filter_data, Mapping):
        filter_data = {}
    warning = (
        diagnostic.get("status") != "effective"
        or int(sources.get("sidecar_active") or 0) > 0
        or int(filter_data.get("total_delta") or 0) != 0
    )
    logger.log(
        logging.WARNING if warning else logging.INFO,
        "AEE_V2_PLAN_LIST_EFFECTIVE %s",
        json.dumps(diagnostic, ensure_ascii=False, default=str, sort_keys=True),
    )


async def _build_filtered_result(
    db,
    *,
    current_user: Mapping[str, Any],
    school_id: Optional[str],
    student_id: Optional[str],
    academic_year: Optional[int],
    status_filter: str,
    professor_aee_id: Optional[str],
    skip: int,
    limit: int,
    batch_resolver: BatchResolver,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = perf_counter()
    filter_query = build_effective_candidate_filter(
        school_id=school_id,
        student_id=student_id,
        academic_year=academic_year,
        professor_aee_id=professor_aee_id,
        current_user=current_user,
    )

    candidate_started = perf_counter()
    candidates = await _load_candidates(db, filter_query)
    candidate_query_ms = (perf_counter() - candidate_started) * 1000.0

    batch = await batch_resolver(db, candidates)
    selection = select_effective_page(
        candidates,
        batch,
        status_filter=status_filter,
        skip=skip,
        limit=limit,
    )
    summaries = batch.get("items") or []

    if selection["blocked"]:
        diagnostic = build_effective_list_diagnostic(
            summaries=summaries,
            academic_year=academic_year,
            school_id=school_id,
            student_id=student_id,
            professor_aee_id=professor_aee_id,
            status_filter=status_filter,
            role=str(current_user.get("role") or "") or None,
            skip=skip,
            limit=limit,
            items_returned=0,
            effective_total=0,
            candidate_total=len(candidates),
            legacy_matches_preview=selection["legacy_matches_preview"],
            candidate_query_ms=candidate_query_ms,
            materialize_ms=0.0,
            total_ms=(perf_counter() - started) * 1000.0,
            batch_result=batch,
            forced_status="integrity_blocked",
        )
        raise PlanListEffectiveFilterIntegrityBlocked(diagnostic)

    materialize_started = perf_counter()
    docs = await _materialize_page(db, selection["page_ids"])
    materialize_ms = (perf_counter() - materialize_started) * 1000.0

    indexed = _summaries_by_id(batch)
    page_batch = {
        "items": [indexed[plan_id] for plan_id in selection["page_ids"]],
        "performance": dict(batch.get("performance") or {}),
    }
    result = apply_plan_list_contract(
        {"items": docs, "total": selection["effective_total"]},
        page_batch,
    )
    diagnostic = build_effective_list_diagnostic(
        summaries=summaries,
        academic_year=academic_year,
        school_id=school_id,
        student_id=student_id,
        professor_aee_id=professor_aee_id,
        status_filter=status_filter,
        role=str(current_user.get("role") or "") or None,
        skip=skip,
        limit=limit,
        items_returned=len(result.get("items") or []),
        effective_total=int(result.get("total") or 0),
        candidate_total=len(candidates),
        legacy_matches_preview=selection["legacy_matches_preview"],
        candidate_query_ms=candidate_query_ms,
        materialize_ms=materialize_ms,
        total_ms=(perf_counter() - started) * 1000.0,
        batch_result=batch,
    )
    return result, diagnostic


def install_aee_v2_plan_list_effective_cutover(
    base_router,
    db,
    *,
    allowed_roles: Sequence[str],
    batch_resolver: Optional[BatchResolver] = None,
    user_getter: Optional[UserGetter] = None,
):
    """Instala a 6.6C como único adapter ativo de ``GET /aee/planos``."""

    if getattr(base_router, "_aee_v2_plan_list_effective_cutover_installed", False):
        return base_router
    if getattr(base_router, "_aee_v2_plan_list_contract_installed", False):
        raise RuntimeError("AEE v2 6.6C não pode ser empilhada sobre o adapter 6.6B.")
    if getattr(base_router, "_aee_v2_plan_list_shadow_installed", False):
        raise RuntimeError("AEE v2 6.6C não pode ser empilhada sobre o Shadow 6.6A.")

    target = _route_for(base_router, "/aee/planos", "GET")
    original_endpoint = target.endpoint
    signature = inspect.signature(original_endpoint)
    resolve_batch = batch_resolver or resolve_plan_list_effective_batch

    @wraps(original_endpoint)
    async def effective_endpoint(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        status_filter = bound.arguments.get("status_filter")
        request = bound.arguments.get("request")
        school_id = bound.arguments.get("school_id")
        student_id = bound.arguments.get("student_id")
        academic_year = bound.arguments.get("academic_year")
        professor_aee_id = bound.arguments.get("professor_aee_id")
        skip = bound.arguments.get("skip", 0)
        limit = bound.arguments.get("limit", 100)

        # Caminho sem filtro: preserva integralmente RBAC/filtros/paginação legado.
        if not status_filter:
            legacy_result = await original_endpoint(*args, **kwargs)
            started = perf_counter()
            try:
                if not isinstance(legacy_result, Mapping):
                    raise PlanListEffectiveCutoverError(
                        "Resposta legado da listagem AEE não é objeto JSON."
                    )
                legacy_items = legacy_result.get("items")
                if not isinstance(legacy_items, list):
                    raise PlanListEffectiveCutoverError(
                        "Resposta legado da listagem AEE não contém items list."
                    )

                batch = await resolve_batch(db, legacy_items)
                result = apply_plan_list_contract(legacy_result, batch)
                role = await _role_for_telemetry(request, user_getter=user_getter)
                diagnostic = build_effective_list_diagnostic(
                    summaries=batch.get("items") or [],
                    academic_year=academic_year,
                    school_id=school_id,
                    student_id=student_id,
                    professor_aee_id=professor_aee_id,
                    status_filter=None,
                    role=role,
                    skip=skip,
                    limit=limit,
                    items_returned=len(result.get("items") or []),
                    effective_total=int(result.get("total") or 0),
                    candidate_total=int(result.get("total") or 0),
                    legacy_matches_preview=None,
                    candidate_query_ms=0.0,
                    materialize_ms=0.0,
                    total_ms=(perf_counter() - started) * 1000.0,
                    batch_result=batch,
                )
                _log_diagnostic(diagnostic)
                return result
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception(
                    "AEE_V2_PLAN_LIST_EFFECTIVE_ERROR %s",
                    json.dumps(
                        {
                            "phase": "6.6C",
                            "mode": "effective_read_cutover",
                            "status": "unavailable",
                        },
                        sort_keys=True,
                    ),
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "code": "AEE_V2_PLAN_LIST_EFFECTIVE_UNAVAILABLE",
                        "message": (
                            "A leitura efetiva da listagem AEE está temporariamente "
                            "indisponível."
                        ),
                    },
                ) from exc

        # Caminho com filtro: autentica/autoriza e resolve o universo antes da página.
        current_user = await _authorized_current_user(
            request,
            allowed_roles=allowed_roles,
            user_getter=user_getter,
        )
        try:
            result, diagnostic = await _build_filtered_result(
                db,
                current_user=current_user,
                school_id=school_id,
                student_id=student_id,
                academic_year=academic_year,
                status_filter=str(status_filter),
                professor_aee_id=professor_aee_id,
                skip=skip,
                limit=limit,
                batch_resolver=resolve_batch,
            )
            _log_diagnostic(diagnostic)
            return result
        except PlanListEffectiveFilterIntegrityBlocked as exc:
            _log_diagnostic(exc.diagnostic)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "AEE_V2_PLAN_LIST_EFFECTIVE_FILTER_INTEGRITY_BLOCKED",
                    "message": (
                        "Não é possível calcular o filtro de situação enquanto "
                        "houver Plano AEE com Fonte Efetiva sem integridade confirmada."
                    ),
                },
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "AEE_V2_PLAN_LIST_EFFECTIVE_ERROR %s",
                json.dumps(
                    {
                        "phase": "6.6C",
                        "mode": "effective_read_cutover",
                        "status": "unavailable",
                    },
                    sort_keys=True,
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "AEE_V2_PLAN_LIST_EFFECTIVE_UNAVAILABLE",
                    "message": (
                        "A leitura efetiva da listagem AEE está temporariamente "
                        "indisponível."
                    ),
                },
            ) from exc

    target.endpoint = effective_endpoint
    target.dependant.call = effective_endpoint
    setattr(base_router, "_aee_v2_plan_list_effective_cutover_installed", True)
    return base_router


def install_aee_v2_plan_list_effective_cutover_setup(aee_module):
    """Envolve ``setup_aee_router`` para instalar a 6.6C sem editar o router legado."""

    if getattr(
        aee_module,
        "_aee_v2_plan_list_effective_cutover_setup_installed",
        False,
    ):
        return

    original_setup = aee_module.setup_aee_router
    allowed_roles = tuple(getattr(aee_module, "ROLES_AEE", ()))
    if not allowed_roles:
        raise RuntimeError("AEE v2 6.6C não encontrou ROLES_AEE no módulo legado.")

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_plan_list_effective_cutover(
            configured,
            db,
            allowed_roles=allowed_roles,
        )

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_plan_list_effective_cutover_setup_installed = True
