"""Fase 6.6D — governança fail-closed das mutações legado do Plano AEE.

Quando existe head V2, ``planos_aee`` permanece como âncora histórica, mas
não pode continuar sendo uma segunda autoridade de edição. Este adapter
protege PUT, duplicate e DELETE sem editar ``routers/aee.py`` e sem dual-write.

Invariantes:
- autenticação/autorização precedem qualquer consulta de governança;
- a policy é recalculada no backend imediatamente antes da mutação;
- ``legacy_allowed`` delega integralmente ao endpoint legado original;
- ``dossier_v2_required`` e ``blocked_integrity`` retornam 409 antes de writes;
- falha inesperada da governança retorna 503 (fail-closed);
- nenhuma mutação é feita pelo adapter;
- no máximo 1 query de heads + 1 query de snapshots por decisão.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from functools import wraps
import inspect
import json
import logging
from time import perf_counter
from typing import Any, Optional

from fastapi import HTTPException, status
from fastapi.routing import APIRoute

from .plan_list_contract import project_plan_list_contract_item
from .plan_list_effective import resolve_plan_list_effective_batch


logger = logging.getLogger(__name__)

BatchResolver = Callable[[Any, Sequence[Mapping[str, Any]]], Awaitable[dict[str, Any]]]
UserGetter = Callable[[Any], Awaitable[Mapping[str, Any]]]

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

_LEGACY_PLAN_PROJECTION = {
    "_id": 0,
    "id": 1,
    "student_id": 1,
    "school_id": 1,
    "academic_year": 1,
    "status": 1,
    "dias_atendimento": 1,
}

_ACTION_ROUTES = {
    "update": ("/aee/planos/{plano_id}", "PUT"),
    "duplicate": ("/aee/planos/{plano_id}/duplicate", "POST"),
    "delete": ("/aee/planos/{plano_id}", "DELETE"),
}

_DOSSIER_BLOCKS = {
    "update": {
        "code": "AEE_V2_PLAN_LEGACY_WRITE_REQUIRES_DOSSIER_V2",
        "message": (
            "Este Plano é gerenciado pelo Dossiê AEE V2 e não pode mais ser "
            "editado pelo formulário legado."
        ),
        "next_action": "open_dossier_v2",
    },
    "duplicate": {
        "code": "AEE_V2_PLAN_LEGACY_DUPLICATE_BLOCKED",
        "message": (
            "A duplicação do Plano legado não é permitida após o início da "
            "governança pelo Dossiê AEE V2."
        ),
    },
    "delete": {
        "code": "AEE_V2_PLAN_LEGACY_DELETE_BLOCKED",
        "message": (
            "A âncora histórica deste Plano é utilizada pelo Dossiê AEE V2 e "
            "não pode ser excluída pelo fluxo legado."
        ),
    },
}

_INTEGRITY_BLOCK = {
    "code": "AEE_V2_PLAN_WRITE_INTEGRITY_BLOCKED",
    "message": (
        "A mutação foi bloqueada porque a integridade da Fonte Efetiva precisa "
        "ser verificada."
    ),
}

_UNAVAILABLE = {
    "code": "AEE_V2_PLAN_WRITE_GOVERNANCE_UNAVAILABLE",
    "message": "A governança de escrita do Plano AEE está temporariamente indisponível.",
}


class PlanWriteGovernanceError(RuntimeError):
    """Falha estrutural da governança que exige bloqueio fail-closed."""


def _route_for(base_router, path: str, method: str) -> APIRoute:
    method = method.upper()
    matches = [
        route
        for route in base_router.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in (route.methods or set())
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"AEE v2 6.6D esperava exatamente uma rota {method} {path}; "
            f"encontrou {len(matches)}."
        )
    return matches[0]


def _collection(db: Any, name: str):
    try:
        return db[name]
    except (KeyError, TypeError, AttributeError):
        return getattr(db, name)


async def _get_user(request: Any, user_getter: Optional[UserGetter]) -> Mapping[str, Any]:
    if user_getter is None:
        # Import lazy mantém os testes/Contract Guard isolados da pilha JWT.
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
    return user


async def _authorize(
    request: Any,
    *,
    allowed_roles: Sequence[str],
    user_getter: Optional[UserGetter],
) -> Mapping[str, Any]:
    user = await _get_user(request, user_getter)
    role = user.get("role")
    if role not in set(allowed_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu perfil não permite esta alteração no módulo AEE",
        )
    return user


def _query_counts(batch: Mapping[str, Any]) -> tuple[int, int]:
    performance = batch.get("performance")
    if not isinstance(performance, Mapping):
        raise PlanWriteGovernanceError("Resolver V2 sem métricas de performance.")

    try:
        head_queries = int(performance.get("head_queries", 0) or 0)
        snapshot_queries = int(performance.get("snapshot_queries", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise PlanWriteGovernanceError("Métricas de queries V2 inválidas.") from exc

    if head_queries < 0 or snapshot_queries < 0:
        raise PlanWriteGovernanceError("Métricas de queries V2 negativas.")
    if head_queries > 1 or snapshot_queries > 1:
        raise PlanWriteGovernanceError(
            "Hard gate 6.6D excedido: mais de 1 query de head/snapshot."
        )
    return head_queries, snapshot_queries


def _policy_from_batch(
    legacy_plan: Mapping[str, Any],
    batch: Mapping[str, Any],
) -> dict[str, Any]:
    items = batch.get("items")
    if not isinstance(items, list) or len(items) != 1:
        raise PlanWriteGovernanceError(
            "Resolver V2 não retornou exatamente um summary para a mutação."
        )

    summary = items[0]
    if not isinstance(summary, Mapping):
        raise PlanWriteGovernanceError("Summary V2 inválido para governança.")

    plan_id = str(legacy_plan.get("id") or "")
    if not plan_id or str(summary.get("legacy_plano_id") or "") != plan_id:
        raise PlanWriteGovernanceError("Summary V2 não corresponde ao Plano legado.")

    # Reutiliza exatamente a projeção/policy já homologada na 6.6B/6.6C,
    # evitando uma segunda implementação independente de mutation_policy.
    projected = project_plan_list_contract_item(legacy_plan, summary)
    policy = projected.get("mutation_policy")
    if policy not in {"legacy_allowed", "dossier_v2_required", "blocked_integrity"}:
        raise PlanWriteGovernanceError(f"mutation_policy desconhecida: {policy!r}.")

    head_queries, snapshot_queries = _query_counts(batch)
    return {
        "policy": policy,
        "v2_managed": bool(projected.get("v2_managed")),
        "effective_source": projected.get("effective_source"),
        "head_queries": head_queries,
        "snapshot_queries": snapshot_queries,
    }


def _log_governance(
    *,
    action: str,
    role: Optional[str],
    decision: str,
    reason_code: str,
    governance_ms: float,
    policy_info: Optional[Mapping[str, Any]] = None,
) -> None:
    policy_info = policy_info or {}
    payload = {
        "phase": "6.6D",
        "mode": "write_governance",
        "action": action,
        "role": role,
        "v2_managed": policy_info.get("v2_managed"),
        "effective_source": policy_info.get("effective_source"),
        "mutation_policy": policy_info.get("policy"),
        "decision": decision,
        "reason_code": reason_code,
        "performance": {
            "head_queries": int(policy_info.get("head_queries", 0) or 0),
            "snapshot_queries": int(policy_info.get("snapshot_queries", 0) or 0),
            "governance_ms": round(float(governance_ms), 3),
        },
    }
    logger.warning(
        "AEE_V2_PLAN_WRITE_GOVERNANCE %s",
        json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True),
    )


def _old_delete_guard_call(value: Any) -> bool:
    call = getattr(value, "dependency", None) or getattr(value, "call", None)
    return (
        getattr(call, "__module__", None) == "aee_v2.delete_guard"
        and getattr(call, "__name__", None) == "protect_legacy_anchor"
    )


def _supersede_legacy_delete_guard(base_router, target: APIRoute) -> None:
    """Remove somente o guard 6.0A já substituído pela policy integral 6.6D.

    O 6.0A bloqueava qualquer head antes do endpoint e, se permanecesse
    empilhado, impediria os novos códigos/semântica de integridade da 6.6D.
    A autorização de DELETE é reaplicada pelo wrapper 6.6D antes de consultar o
    Plano, preservando a ordem de segurança.
    """

    before_route = len(target.dependencies)
    target.dependencies[:] = [
        dep for dep in target.dependencies if not _old_delete_guard_call(dep)
    ]
    removed_route = before_route - len(target.dependencies)

    before_dependant = len(target.dependant.dependencies)
    target.dependant.dependencies[:] = [
        dep for dep in target.dependant.dependencies if not _old_delete_guard_call(dep)
    ]
    removed_dependant = before_dependant - len(target.dependant.dependencies)

    if getattr(base_router, "_aee_v2_delete_guard_installed", False):
        if removed_route == 0 or removed_dependant == 0:
            raise RuntimeError(
                "AEE v2 6.6D detectou o guard 6.0A como instalado, mas não "
                "conseguiu substituí-lo de forma estrutural."
            )
        setattr(base_router, "_aee_v2_delete_guard_superseded_by_6_6d", True)


def _build_governed_endpoint(
    original_endpoint: Callable[..., Awaitable[Any]],
    *,
    action: str,
    db: Any,
    allowed_roles: Sequence[str],
    batch_resolver: BatchResolver,
    user_getter: Optional[UserGetter],
):
    signature = inspect.signature(original_endpoint)

    @wraps(original_endpoint)
    async def governed_endpoint(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        request = bound.arguments.get("request")
        plano_id = str(bound.arguments.get("plano_id") or "").strip()
        if not plano_id:
            raise PlanWriteGovernanceError(
                f"Rota governada 6.6D sem plano_id para ação {action}."
            )

        # Segurança: autenticação/autorização antes de qualquer lookup de Plano/head.
        user = await _authorize(
            request,
            allowed_roles=allowed_roles,
            user_getter=user_getter,
        )
        role = str(user.get("role") or "") or None
        started = perf_counter()

        try:
            legacy_plan = await _collection(db, "planos_aee").find_one(
                {"id": plano_id},
                _LEGACY_PLAN_PROJECTION,
            )
            if not legacy_plan:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Plano AEE não encontrado",
                )

            batch = await batch_resolver(db, [legacy_plan])
            policy_info = _policy_from_batch(legacy_plan, batch)
        except HTTPException:
            raise
        except Exception as exc:
            governance_ms = (perf_counter() - started) * 1000.0
            _log_governance(
                action=action,
                role=role,
                decision="unavailable",
                reason_code=_UNAVAILABLE["code"],
                governance_ms=governance_ms,
            )
            logger.exception(
                "AEE_V2_PLAN_WRITE_GOVERNANCE_ERROR %s",
                json.dumps(
                    {
                        "phase": "6.6D",
                        "mode": "write_governance",
                        "action": action,
                        "status": "unavailable",
                    },
                    sort_keys=True,
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=dict(_UNAVAILABLE),
            ) from exc

        governance_ms = (perf_counter() - started) * 1000.0
        policy = policy_info["policy"]

        if policy == "legacy_allowed":
            _log_governance(
                action=action,
                role=role,
                decision="allowed",
                reason_code="LEGACY_ALLOWED",
                governance_ms=governance_ms,
                policy_info=policy_info,
            )
            # O endpoint legado continua responsável por validação, auditoria e write.
            return await original_endpoint(*args, **kwargs)

        if policy == "blocked_integrity":
            detail = dict(_INTEGRITY_BLOCK)
        elif policy == "dossier_v2_required":
            detail = dict(_DOSSIER_BLOCKS[action])
        else:  # defesa adicional; _policy_from_batch já rejeita este estado.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=dict(_UNAVAILABLE),
            )

        _log_governance(
            action=action,
            role=role,
            decision="blocked",
            reason_code=detail["code"],
            governance_ms=governance_ms,
            policy_info=policy_info,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )

    return governed_endpoint


def install_aee_v2_plan_write_governance(
    base_router,
    db,
    *,
    write_roles: Sequence[str],
    delete_roles: Sequence[str] = _DELETE_ROLES,
    batch_resolver: Optional[BatchResolver] = None,
    user_getter: Optional[UserGetter] = None,
):
    """Instala a governança 6.6D em PUT/duplicate/DELETE do Plano legado."""

    if getattr(base_router, "_aee_v2_plan_write_governance_installed", False):
        return base_router

    resolve_batch = batch_resolver or resolve_plan_list_effective_batch
    targets = {
        action: _route_for(base_router, path, method)
        for action, (path, method) in _ACTION_ROUTES.items()
    }

    # Substitui o guard 6.0A apenas no DELETE; os demais wrappers AEE permanecem.
    _supersede_legacy_delete_guard(base_router, targets["delete"])

    for action, target in targets.items():
        original_endpoint = target.endpoint
        roles = delete_roles if action == "delete" else write_roles
        wrapped = _build_governed_endpoint(
            original_endpoint,
            action=action,
            db=db,
            allowed_roles=tuple(roles),
            batch_resolver=resolve_batch,
            user_getter=user_getter,
        )
        target.endpoint = wrapped
        target.dependant.call = wrapped

    setattr(base_router, "_aee_v2_plan_write_governance_installed", True)
    return base_router


def install_aee_v2_plan_write_governance_setup(aee_module):
    """Envolve ``setup_aee_router`` sem editar o router legado bloqueado."""

    if getattr(
        aee_module,
        "_aee_v2_plan_write_governance_setup_installed",
        False,
    ):
        return

    original_setup = aee_module.setup_aee_router
    write_roles = tuple(getattr(aee_module, "ROLES_AEE_WRITE", ()))
    if not write_roles:
        raise RuntimeError("AEE v2 6.6D não encontrou ROLES_AEE_WRITE no módulo legado.")

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_plan_write_governance(
            configured,
            db,
            write_roles=write_roles,
        )

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_plan_write_governance_setup_installed = True
