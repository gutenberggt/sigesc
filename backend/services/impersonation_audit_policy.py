"""Política central de auditoria para sessões de impersonação.

O endpoint/serviço que executa uma ação não precisa preservar metadados de
impersonação no dicionário ``user`` enviado ao AuditService. A primeira chamada
auditável feita pelo AuthMiddleware carrega o usuário autenticado completo; a
política fixa esse actor/subject em ``request.state`` e reutiliza o contexto nas
auditorias subsequentes da mesma requisição.

Assim, autoria não depende de cada rota preservar o dicionário ``user`` e também
não é inferida de um token bruto em rotas públicas: somente contexto que já
passou pela autenticação pode promover o Super Administrador a ator auditável.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


REQUEST_STATE_KEY = "impersonation_audit_context"


def _context_from_effective_user(user: Any) -> Optional[dict[str, Any]]:
    if not isinstance(user, Mapping):
        return None
    if not user.get("impersonation") or not user.get("actor_id") or not user.get("id"):
        return None
    return {
        "session_id": user.get("impersonation_session_id"),
        "actor_id": user.get("actor_id"),
        "actor_email": user.get("actor_email"),
        "actor_name": user.get("actor_name"),
        "subject_user_id": user.get("id"),
        "subject_email": user.get("email"),
        "subject_role": user.get("role"),
        "subject_name": user.get("subject_name"),
    }


def _request_context(request, user: Any = None) -> Optional[dict[str, Any]]:
    if request is None:
        return None

    state = getattr(request, "state", None)
    if state is None:
        return None

    current = getattr(state, REQUEST_STATE_KEY, None)
    if isinstance(current, Mapping) and current.get("actor_id") and current.get("subject_user_id"):
        return dict(current)

    derived = _context_from_effective_user(user)
    if derived:
        setattr(state, REQUEST_STATE_KEY, dict(derived))
        return derived
    return None


def _actor_from_context(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": context.get("actor_id"),
        "email": context.get("actor_email"),
        "role": "super_admin",
        "full_name": context.get("actor_name"),
    }


def _subject_meta(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "session_id": context.get("session_id"),
        "actor_id": context.get("actor_id"),
        "actor_email": context.get("actor_email"),
        "subject_user_id": context.get("subject_user_id"),
        "subject_email": context.get("subject_email"),
        "subject_role": context.get("subject_role"),
        "subject_name": context.get("subject_name"),
    }


def _merge_impersonation_extra(current: Any, context: Mapping[str, Any]) -> dict[str, Any]:
    extra = dict(current) if isinstance(current, Mapping) else {}
    prior = extra.get("impersonation")
    merged = dict(prior) if isinstance(prior, Mapping) else {}
    merged.update(_subject_meta(context))
    extra["impersonation"] = merged
    return extra


def install_impersonation_request_audit_policy(audit_service) -> None:
    """Garante ator real por request, mesmo se a rota reconstruir ``user``.

    A camada é instalada depois da política de auditoria do módulo Auth. Na
    primeira auditoria da request, ``user`` ainda contém o contexto enriquecido
    pelo AuthMiddleware e esse contexto é fixado no ``request.state``. Chamadas
    posteriores podem passar um ``user`` reduzido sem perder a autoria real.
    """
    if getattr(audit_service, "_impersonation_request_policy_installed", False):
        return

    original_log = audit_service.log

    async def request_aware_log(*args, **kwargs):
        mutable_args = list(args)
        request = kwargs.get("request")
        if request is None and len(mutable_args) >= 4:
            request = mutable_args[3]

        if "user" in kwargs:
            supplied_user = kwargs.get("user")
        elif len(mutable_args) >= 3:
            supplied_user = mutable_args[2]
        else:
            supplied_user = None

        context = _request_context(request, supplied_user)
        if context:
            actor = _actor_from_context(context)

            if "user" in kwargs:
                kwargs["user"] = actor
            elif len(mutable_args) >= 3:
                mutable_args[2] = actor
            else:
                kwargs["user"] = actor

            # AuditService.log possui 12 argumentos após self; extra_data é o
            # 12º (índice 11) quando a chamada é totalmente posicional.
            if len(mutable_args) >= 12:
                mutable_args[11] = _merge_impersonation_extra(mutable_args[11], context)
            else:
                kwargs["extra_data"] = _merge_impersonation_extra(
                    kwargs.get("extra_data"),
                    context,
                )

            if "description" in kwargs:
                description = kwargs.get("description")
                if description and not str(description).startswith("[IMPERSONAÇÃO]"):
                    kwargs["description"] = f"[IMPERSONAÇÃO] {description}"
            elif len(mutable_args) >= 6:
                description = mutable_args[5]
                if description and not str(description).startswith("[IMPERSONAÇÃO]"):
                    mutable_args[5] = f"[IMPERSONAÇÃO] {description}"

            args = tuple(mutable_args)

        return await original_log(*args, **kwargs)

    audit_service.log = request_aware_log
    audit_service._impersonation_request_policy_installed = True
