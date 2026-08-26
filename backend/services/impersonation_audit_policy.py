"""Política central de auditoria para sessões de impersonação.

O endpoint/serviço que executa uma ação não precisa preservar metadados de
impersonação no dicionário ``user`` enviado ao AuditService. Quando o request
carrega um access token de impersonação válido, o ator auditável é sempre o
Super Administrador contido nos claims assinados; o usuário efetivo permanece
registrado como subject em ``extra_data.impersonation``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from auth_utils import ACCESS_COOKIE_NAME, decode_token


def _request_access_payload(request) -> Optional[dict[str, Any]]:
    if request is None:
        return None

    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization") or ""
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
    if not token:
        token = request.query_params.get("token")
    if not token:
        return None

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    if not payload.get("impersonation"):
        return None
    if not payload.get("impersonation_actor_id") or not payload.get("sub"):
        return None
    return payload


def _actor_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("impersonation_actor_id"),
        "email": payload.get("impersonation_actor_email"),
        "role": "super_admin",
        "full_name": payload.get("impersonation_actor_name"),
    }


def _subject_meta(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "session_id": payload.get("impersonation_session_id"),
        "actor_id": payload.get("impersonation_actor_id"),
        "actor_email": payload.get("impersonation_actor_email"),
        "subject_user_id": payload.get("sub"),
        "subject_email": payload.get("email"),
        "subject_role": payload.get("role"),
        "subject_name": payload.get("impersonation_subject_name"),
    }


def install_impersonation_request_audit_policy(audit_service) -> None:
    """Garante ator real por request, mesmo se a rota reconstruir ``user``.

    Esta camada é instalada depois da política de auditoria do módulo Auth. Ela
    cobre o caso em que uma rota faz, por exemplo, ``user={'id': ..., ...}`` e
    descarta os campos de impersonação antes de chamar ``AuditService.log``.
    """
    if getattr(audit_service, "_impersonation_request_policy_installed", False):
        return

    original_log = audit_service.log

    async def request_aware_log(*args, **kwargs):
        request = kwargs.get("request")
        if request is None and len(args) >= 4:
            request = args[3]

        payload = _request_access_payload(request)
        if payload:
            actor = _actor_from_payload(payload)

            if "user" in kwargs:
                kwargs["user"] = actor
            elif len(args) >= 3:
                mutable_args = list(args)
                mutable_args[2] = actor
                args = tuple(mutable_args)
            else:
                kwargs["user"] = actor

            # extra_data é normalmente keyword no SIGESC. Evita conflito apenas
            # no caso excepcional de uma chamada totalmente posicional que já
            # tenha preenchido esse argumento.
            if len(args) < 13:
                extra = dict(kwargs.get("extra_data") or {})
                prior = extra.get("impersonation")
                merged = dict(prior) if isinstance(prior, Mapping) else {}
                merged.update(_subject_meta(payload))
                extra["impersonation"] = merged
                kwargs["extra_data"] = extra

            description = kwargs.get("description")
            if description and not str(description).startswith("[IMPERSONAÇÃO]"):
                kwargs["description"] = f"[IMPERSONAÇÃO] {description}"

        return await original_log(*args, **kwargs)

    audit_service.log = request_aware_log
    audit_service._impersonation_request_policy_installed = True
