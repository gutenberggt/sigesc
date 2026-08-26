"""Impersonação segura para testes de perfil pelo Super Administrador.

Este módulo NÃO implementa senha mestra no login. A senha do Super Administrador
é usada somente como reautenticação (step-up) para iniciar uma sessão temporária
em nome de outro usuário. Autorização continua sendo avaliada como o usuário-alvo,
enquanto a auditoria preserva o Super Administrador como ator real.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from typing import Any, Mapping, Optional
import uuid

from fastapi import HTTPException, Request, Response, status

from auth_middleware import AuthMiddleware
from auth_utils import (
    ACCESS_COOKIE_NAME,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_csrf_token,
    set_auth_cookies,
    token_blacklist,
    verify_password,
)
from models import RefreshTokenRequest, UserInDB
from role_context import get_authorized_roles, resolve_role_context


IMPERSONATION_MAX_MINUTES = min(
    max(int(os.environ.get("IMPERSONATION_MAX_MINUTES", "60")), 15),
    120,
)
IMPERSONATION_ACCESS_JTI_PREFIX = "impersonation-session:"

SENSITIVE_PATHS_BLOCKED_DURING_IMPERSONATION = {
    "/api/auth/logout",
    "/api/auth/logout-all",
    "/api/auth/change-account",
    "/api/auth/resend-email-change",
    "/api/users/switch-role",
}


def _remove_route(router, path: str, method: str):
    for route in list(router.routes):
        methods = getattr(route, "methods", set()) or set()
        if getattr(route, "path", None) == path and method in methods:
            router.routes.remove(route)
            return route.endpoint
    return None


def _request_access_token(request: Request) -> Optional[str]:
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if token:
        return token
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return request.query_params.get("token")


async def _request_refresh_token(request: Request) -> Optional[str]:
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token:
        return token
    try:
        body = await request.json()
    except Exception:
        body = {}
    return (body or {}).get("refresh_token")


def _impersonation_claims(
    *,
    actor: Mapping[str, Any],
    subject: Mapping[str, Any],
    session_id: str,
    started_at: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    return {
        "impersonation": True,
        "impersonation_session_id": session_id,
        "impersonation_started_at": int(started_at.timestamp()),
        "impersonation_expires_at": int(expires_at.timestamp()),
        "impersonation_actor_id": actor.get("id"),
        "impersonation_actor_email": actor.get("email"),
        "impersonation_actor_role": "super_admin",
        "impersonation_actor_name": actor.get("full_name") or actor.get("name"),
        "impersonation_subject_name": subject.get("full_name") or subject.get("name"),
    }


def _impersonation_public_meta(current_user: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "active": True,
        "session_id": current_user.get("impersonation_session_id"),
        "started_at": current_user.get("impersonation_started_at"),
        "expires_at": current_user.get("impersonation_expires_at"),
        "actor": {
            "id": current_user.get("actor_id"),
            "name": current_user.get("actor_name"),
            "email": current_user.get("actor_email"),
            "role": "super_admin",
        },
        "subject": {
            "id": current_user.get("id"),
            "name": current_user.get("subject_name"),
            "email": current_user.get("email"),
            "role": current_user.get("role"),
        },
    }


def _user_response_data(
    user_doc: Mapping[str, Any],
    *,
    effective_role: str,
    school_links: list[dict[str, Any]],
    impersonation_meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    data = {
        key: value
        for key, value in dict(user_doc).items()
        if key not in {"_id", "password_hash"}
    }
    data["role"] = effective_role
    data["school_links"] = school_links
    if impersonation_meta:
        data["impersonation"] = impersonation_meta
    return data


def _actor_from_effective_user(user: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": user.get("actor_id"),
        "email": user.get("actor_email"),
        "role": "super_admin",
        "full_name": user.get("actor_name"),
    }


def _install_audit_actor_policy(audit_service) -> None:
    """Faz logs de domínio apontarem para o ator real durante impersonação."""
    if getattr(audit_service, "_impersonation_actor_policy_installed", False):
        return

    original_log = audit_service.log

    async def impersonation_aware_log(*args, **kwargs):
        user = kwargs.get("user")
        if isinstance(user, Mapping) and user.get("impersonation") and user.get("actor_id"):
            extra = dict(kwargs.get("extra_data") or {})
            extra["impersonation"] = {
                "session_id": user.get("impersonation_session_id"),
                "actor_id": user.get("actor_id"),
                "actor_email": user.get("actor_email"),
                "subject_user_id": user.get("id"),
                "subject_email": user.get("email"),
                "subject_role": user.get("role"),
                "subject_name": user.get("subject_name"),
            }
            kwargs["extra_data"] = extra
            kwargs["user"] = _actor_from_effective_user(user)
            description = kwargs.get("description")
            if description and not str(description).startswith("[IMPERSONAÇÃO]"):
                kwargs["description"] = f"[IMPERSONAÇÃO] {description}"
        return await original_log(*args, **kwargs)

    audit_service.log = impersonation_aware_log
    audit_service._impersonation_actor_policy_installed = True


def _install_auth_context_policy(db, audit_service) -> None:
    """Propaga ator/subject para todos os guards e gera trilha global por request."""
    if getattr(AuthMiddleware, "_impersonation_context_policy_installed", False):
        return

    original_get_current_user = AuthMiddleware.get_current_user

    async def impersonation_aware_get_current_user(request: Request) -> dict:
        user = await original_get_current_user(request)
        token = _request_access_token(request)
        payload = decode_token(token) if token else None

        if not payload or not payload.get("impersonation"):
            return user

        now_ts = int(datetime.now(timezone.utc).timestamp())
        hard_exp = int(payload.get("impersonation_expires_at") or 0)
        if not hard_exp or now_ts >= hard_exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão de teste expirada",
            )

        actor_id = payload.get("impersonation_actor_id")
        if not actor_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão de teste inválida",
            )

        actor = await db.users.find_one(
            {"id": actor_id},
            {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1, "status": 1},
        )
        if not actor or actor.get("status") != "active" or actor.get("role") != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super Administrador não está mais autorizado a manter esta sessão de teste",
            )

        subject = await db.users.find_one(
            {"id": user.get("id")},
            {"_id": 0, "id": 1, "status": 1},
        )
        if not subject or subject.get("status") != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário testado não está mais ativo",
            )

        path = request.url.path
        if path in SENSITIVE_PATHS_BLOCKED_DURING_IMPERSONATION:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ação de conta/sessão bloqueada durante o modo de teste. Encerre o teste primeiro.",
            )

        user.update({
            "impersonation": True,
            "impersonation_session_id": payload.get("impersonation_session_id"),
            "impersonation_started_at": payload.get("impersonation_started_at"),
            "impersonation_expires_at": hard_exp,
            "actor_id": actor.get("id"),
            "actor_email": actor.get("email"),
            "actor_name": actor.get("full_name"),
            "actor_role": "super_admin",
            "subject_name": payload.get("impersonation_subject_name"),
            "token_jti": payload.get("jti"),
        })

        if not getattr(request.state, "impersonation_access_logged", False):
            request.state.impersonation_access_logged = True
            await audit_service.log(
                action="access",
                collection="impersonation",
                user=user,
                request=request,
                document_id=user.get("id"),
                description=(
                    f"[IMPERSONAÇÃO] {request.method} {path} como "
                    f"{user.get('subject_name') or user.get('email')} ({user.get('role')})"
                ),
                extra_data={
                    "request_method": request.method,
                    "request_path": path,
                },
            )

        return user

    AuthMiddleware.get_current_user = staticmethod(impersonation_aware_get_current_user)
    AuthMiddleware._impersonation_context_policy_installed = True


async def _validated_actor_and_subject(
    db,
    *,
    current_user: Mapping[str, Any],
    target_user_id: str,
    password: str,
    active_role: Optional[str],
):
    if current_user.get("impersonation"):
        raise HTTPException(status_code=409, detail="Impersonação aninhada não é permitida")
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Apenas o Super Administrador pode iniciar modo de teste")

    actor_doc = await db.users.find_one({"id": current_user.get("id")}, {"_id": 0})
    if not actor_doc or actor_doc.get("status") != "active" or actor_doc.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super Administrador inválido ou inativo")
    if not verify_password(password, actor_doc.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Senha do Super Administrador incorreta")

    target_doc = await db.users.find_one({"id": target_user_id}, {"_id": 0})
    if not target_doc:
        raise HTTPException(status_code=404, detail="Usuário a testar não encontrado")
    if target_doc.get("status") != "active":
        raise HTTPException(status_code=403, detail="Usuário a testar está inativo")
    if target_user_id == actor_doc.get("id"):
        raise HTTPException(status_code=400, detail="Não é necessário testar como o próprio Super Administrador")

    target_roles = get_authorized_roles(target_doc)
    if target_doc.get("role") == "super_admin" or "super_admin" in target_roles:
        raise HTTPException(status_code=403, detail="Impersonação de outro Super Administrador não é permitida")

    effective_role = active_role or target_doc.get("role")
    if effective_role not in target_roles:
        raise HTTPException(status_code=403, detail="Papel solicitado não pertence ao usuário a testar")

    role_context = await resolve_role_context(db, target_doc, effective_role)
    return actor_doc, target_doc, effective_role, role_context


def install_auth_impersonation(router, db, audit_service):
    """Instala impersonação sobre o router Auth já configurado."""
    if getattr(router, "_super_admin_impersonation_installed", False):
        return router

    _install_audit_actor_policy(audit_service)
    _install_auth_context_policy(db, audit_service)

    original_refresh = _remove_route(router, "/auth/refresh", "POST")
    _remove_route(router, "/auth/me", "GET")

    if original_refresh is None:
        raise RuntimeError("AUTH_IMPERSONATION_INSTALL_FAILED: /auth/refresh ausente")

    @router.post("/impersonation/start")
    async def start_impersonation(request: Request, response: Response):
        current_user = await AuthMiddleware.get_current_user(request)
        try:
            body = await request.json()
        except Exception:
            body = {}

        target_user_id = str((body or {}).get("target_user_id") or "").strip()
        password = str((body or {}).get("password") or "")
        active_role = str((body or {}).get("active_role") or "").strip() or None
        if not target_user_id or not password:
            raise HTTPException(status_code=400, detail="Usuário e senha do Super Administrador são obrigatórios")

        actor_doc, target_doc, effective_role, role_context = await _validated_actor_and_subject(
            db,
            current_user=current_user,
            target_user_id=target_user_id,
            password=password,
            active_role=active_role,
        )

        now = datetime.now(timezone.utc)
        hard_exp = now + timedelta(minutes=IMPERSONATION_MAX_MINUTES)
        session_id = str(uuid.uuid4())
        claims = _impersonation_claims(
            actor=actor_doc,
            subject=target_doc,
            session_id=session_id,
            started_at=now,
            expires_at=hard_exp,
        )
        session_access_jti = f"{IMPERSONATION_ACCESS_JTI_PREFIX}{session_id}"
        school_ids = role_context["school_ids"]
        school_links = role_context["school_links"]

        access_data = {
            "sub": target_doc.get("id"),
            "email": target_doc.get("email"),
            "role": effective_role,
            "school_ids": school_ids,
            "mantenedora_id": target_doc.get("mantenedora_id"),
            "jti": session_access_jti,
            **claims,
        }
        refresh_data = {
            "sub": target_doc.get("id"),
            "active_role": effective_role,
            **claims,
        }
        csrf_token = generate_csrf_token()
        access_token = create_access_token(access_data, csrf=csrf_token)
        refresh_token = create_refresh_token(refresh_data)
        set_auth_cookies(
            response,
            access_token=access_token,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
        )

        await audit_service.log(
            action="access",
            collection="users",
            user={
                "id": actor_doc.get("id"),
                "email": actor_doc.get("email"),
                "role": "super_admin",
                "full_name": actor_doc.get("full_name"),
            },
            request=request,
            document_id=target_doc.get("id"),
            description=(
                f"Iniciou modo de teste como {target_doc.get('full_name')} "
                f"no papel {effective_role}"
            ),
            extra_data={
                "impersonation_session_id": session_id,
                "subject_user_id": target_doc.get("id"),
                "subject_email": target_doc.get("email"),
                "subject_role": effective_role,
                "expires_at": int(hard_exp.timestamp()),
            },
        )

        current_for_meta = {
            "id": target_doc.get("id"),
            "email": target_doc.get("email"),
            "role": effective_role,
            "subject_name": target_doc.get("full_name"),
            "actor_id": actor_doc.get("id"),
            "actor_email": actor_doc.get("email"),
            "actor_name": actor_doc.get("full_name"),
            "impersonation_session_id": session_id,
            "impersonation_started_at": int(now.timestamp()),
            "impersonation_expires_at": int(hard_exp.timestamp()),
        }
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "csrf_token": csrf_token,
            "token_type": "bearer",
            "user": _user_response_data(
                target_doc,
                effective_role=effective_role,
                school_links=school_links,
                impersonation_meta=_impersonation_public_meta(current_for_meta),
            ),
        }

    @router.post("/refresh")
    async def refresh_with_impersonation(request: Request, response: Response):
        incoming_refresh = await _request_refresh_token(request)
        if not incoming_refresh:
            raise HTTPException(status_code=401, detail="Refresh token ausente")

        payload = decode_token(incoming_refresh)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token inválido")

        if not payload.get("impersonation"):
            return await original_refresh(
                request,
                response,
                RefreshTokenRequest(refresh_token=incoming_refresh),
            )

        now = datetime.now(timezone.utc)
        now_ts = int(now.timestamp())
        hard_exp_ts = int(payload.get("impersonation_expires_at") or 0)
        if not hard_exp_ts or now_ts >= hard_exp_ts:
            raise HTTPException(status_code=401, detail="Sessão de teste expirada")

        subject_id = payload.get("sub")
        actor_id = payload.get("impersonation_actor_id")
        refresh_jti = payload.get("jti")
        refresh_iat = payload.get("iat")
        if await token_blacklist.is_token_revoked(
            jti=refresh_jti,
            user_id=subject_id,
            issued_at=refresh_iat,
        ):
            raise HTTPException(status_code=401, detail="Refresh token revogado")

        actor_doc = await db.users.find_one({"id": actor_id}, {"_id": 0})
        target_doc = await db.users.find_one({"id": subject_id}, {"_id": 0})
        if not actor_doc or actor_doc.get("status") != "active" or actor_doc.get("role") != "super_admin":
            raise HTTPException(status_code=403, detail="Super Administrador não está mais autorizado")
        if not target_doc or target_doc.get("status") != "active":
            raise HTTPException(status_code=403, detail="Usuário testado não está mais ativo")

        available_roles = get_authorized_roles(target_doc)
        effective_role = payload.get("active_role") or target_doc.get("role")
        if effective_role not in available_roles or effective_role == "super_admin":
            raise HTTPException(status_code=403, detail="Papel da sessão de teste não é mais autorizado")

        role_context = await resolve_role_context(db, target_doc, effective_role)
        session_id = payload.get("impersonation_session_id")
        hard_exp = datetime.fromtimestamp(hard_exp_ts, tz=timezone.utc)
        remaining = hard_exp - now
        access_ttl = min(timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES), remaining)
        if access_ttl.total_seconds() <= 0:
            raise HTTPException(status_code=401, detail="Sessão de teste expirada")

        claims = _impersonation_claims(
            actor=actor_doc,
            subject=target_doc,
            session_id=session_id,
            started_at=datetime.fromtimestamp(
                int(payload.get("impersonation_started_at") or now_ts),
                tz=timezone.utc,
            ),
            expires_at=hard_exp,
        )
        access_data = {
            "sub": target_doc.get("id"),
            "email": target_doc.get("email"),
            "role": effective_role,
            "school_ids": role_context["school_ids"],
            "mantenedora_id": target_doc.get("mantenedora_id"),
            "jti": f"{IMPERSONATION_ACCESS_JTI_PREFIX}{session_id}",
            **claims,
        }
        refresh_data = {
            "sub": target_doc.get("id"),
            "active_role": effective_role,
            **claims,
        }
        csrf_token = generate_csrf_token()
        new_access_token = create_access_token(
            access_data,
            expires_delta=access_ttl,
            csrf=csrf_token,
        )
        new_refresh_token = create_refresh_token(refresh_data)

        if refresh_jti:
            try:
                refresh_exp = payload.get("exp")
                refresh_exp_dt = (
                    datetime.fromtimestamp(refresh_exp, tz=timezone.utc)
                    if refresh_exp
                    else now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
                )
                await token_blacklist.revoke_token(
                    jti=refresh_jti,
                    user_id=target_doc.get("id"),
                    expires_at=refresh_exp_dt,
                    reason="impersonation_refresh_rotation",
                )
            except Exception:
                pass

        set_auth_cookies(
            response,
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            csrf_token=csrf_token,
        )
        current_for_meta = {
            "id": target_doc.get("id"),
            "email": target_doc.get("email"),
            "role": effective_role,
            "subject_name": target_doc.get("full_name"),
            "actor_id": actor_doc.get("id"),
            "actor_email": actor_doc.get("email"),
            "actor_name": actor_doc.get("full_name"),
            "impersonation_session_id": session_id,
            "impersonation_started_at": claims["impersonation_started_at"],
            "impersonation_expires_at": hard_exp_ts,
        }
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "csrf_token": csrf_token,
            "token_type": "bearer",
            "user": _user_response_data(
                target_doc,
                effective_role=effective_role,
                school_links=role_context["school_links"],
                impersonation_meta=_impersonation_public_meta(current_for_meta),
            ),
        }

    @router.get("/me")
    async def me_with_impersonation(request: Request):
        current_user = await AuthMiddleware.get_current_user(request)
        user_doc = await db.users.find_one({"id": current_user.get("id")}, {"_id": 0})
        if not user_doc:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        effective_role = current_user.get("role") or user_doc.get("role")
        school_links = [
            {
                "school_id": school_id,
                "roles": [effective_role],
                "class_ids": [],
            }
            for school_id in current_user.get("school_ids", [])
        ]
        meta = _impersonation_public_meta(current_user) if current_user.get("impersonation") else None
        return _user_response_data(
            user_doc,
            effective_role=effective_role,
            school_links=school_links,
            impersonation_meta=meta,
        )

    @router.post("/impersonation/stop")
    async def stop_impersonation(request: Request, response: Response):
        current_user = await AuthMiddleware.get_current_user(request)
        if not current_user.get("impersonation"):
            raise HTTPException(status_code=409, detail="Não há modo de teste ativo")

        actor_doc = await db.users.find_one({"id": current_user.get("actor_id")}, {"_id": 0})
        if not actor_doc or actor_doc.get("status") != "active" or actor_doc.get("role") != "super_admin":
            raise HTTPException(status_code=403, detail="Super Administrador não está mais autorizado")

        hard_exp_ts = int(current_user.get("impersonation_expires_at") or 0)
        hard_exp = (
            datetime.fromtimestamp(hard_exp_ts, tz=timezone.utc)
            if hard_exp_ts
            else datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        session_id = current_user.get("impersonation_session_id")
        if session_id:
            await token_blacklist.revoke_token(
                jti=f"{IMPERSONATION_ACCESS_JTI_PREFIX}{session_id}",
                user_id=current_user.get("id"),
                expires_at=hard_exp,
                reason="impersonation_stopped",
            )

        incoming_refresh = await _request_refresh_token(request)
        if incoming_refresh:
            try:
                refresh_payload = decode_token(incoming_refresh)
                if (
                    refresh_payload
                    and refresh_payload.get("impersonation")
                    and refresh_payload.get("impersonation_session_id") == session_id
                    and refresh_payload.get("jti")
                ):
                    refresh_exp = refresh_payload.get("exp")
                    await token_blacklist.revoke_token(
                        jti=refresh_payload.get("jti"),
                        user_id=current_user.get("id"),
                        expires_at=(
                            datetime.fromtimestamp(refresh_exp, tz=timezone.utc)
                            if refresh_exp
                            else hard_exp
                        ),
                        reason="impersonation_stopped",
                    )
            except Exception:
                pass

        role_context = await resolve_role_context(db, actor_doc, "super_admin")
        csrf_token = generate_csrf_token()
        access_token = create_access_token(
            {
                "sub": actor_doc.get("id"),
                "email": actor_doc.get("email"),
                "role": "super_admin",
                "school_ids": role_context["school_ids"],
                "mantenedora_id": actor_doc.get("mantenedora_id"),
            },
            csrf=csrf_token,
        )
        refresh_token = create_refresh_token({
            "sub": actor_doc.get("id"),
            "active_role": "super_admin",
        })
        set_auth_cookies(
            response,
            access_token=access_token,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
        )

        await audit_service.log(
            action="access",
            collection="users",
            user=current_user,
            request=request,
            document_id=current_user.get("id"),
            description=(
                f"Encerrou modo de teste como "
                f"{current_user.get('subject_name') or current_user.get('email')}"
            ),
            extra_data={"impersonation_session_id": session_id, "event": "stop"},
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "csrf_token": csrf_token,
            "token_type": "bearer",
            "user": _user_response_data(
                actor_doc,
                effective_role="super_admin",
                school_links=role_context["school_links"],
            ),
        }

    router._super_admin_impersonation_installed = True
    return router
