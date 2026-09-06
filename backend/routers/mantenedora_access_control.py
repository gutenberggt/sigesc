"""Controle administrativo de ativação da Mantenedora.

Instalado sobre ``routers.admin.setup_router`` para reutilizar o rastreador de
sessões e o ConnectionManager já injetados pelo bootstrap, sem criar uma segunda
fonte de verdade de presença.

Invariantes:
- somente super_admin altera o estado da mantenedora;
- desativação falha fechada se houver usuário do tenant conectado;
- nenhuma cascata altera escolas/dados: a trava é operacional no tenant_scope;
- papéis excepcionalmente autorizados continuam sujeitos ao RBAC normal;
- super_admin mantém bypass administrativo apenas no control plane para
  diagnóstico/configuração/reativação; não recebe bypass operacional.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request, status
from pydantic import BaseModel

from auth_middleware import AuthMiddleware
from services.mantenedora_access_policy import (
    CONFIGURABLE_INACTIVE_ACCESS_ROLES,
    INACTIVE_ACCESS_ROLE_LABELS,
    can_access_tenant,
    inactive_allowed_roles,
    is_super_admin,
    is_tenant_active,
    normalize_allowed_roles,
)


class MantenedoraAccessControlUpdate(BaseModel):
    ativo: Optional[bool] = None
    allowed_roles: Optional[list[str]] = None


def _selected_superadmin_tenant(request: Request) -> Optional[str]:
    header = (request.headers.get("X-Mantenedora-Id") or "").strip()
    if header:
        return header
    try:
        query = (request.query_params.get("mantenedora_id") or "").strip()
    except Exception:
        query = ""
    return query or None


def _role_options() -> list[dict[str, str]]:
    return [
        {"value": role, "label": INACTIVE_ACCESS_ROLE_LABELS.get(role, role)}
        for role in CONFIGURABLE_INACTIVE_ACCESS_ROLES
    ]


async def _tenant_for_request(db, current_user: dict, request: Request) -> Optional[dict]:
    if is_super_admin(current_user):
        tenant_id = _selected_superadmin_tenant(request)
    else:
        tenant_id = str(current_user.get("mantenedora_id") or "").strip() or None
    if not tenant_id:
        return None
    return await db.mantenedoras.find_one({"id": tenant_id}, {"_id": 0})


async def _collect_active_tenant_users(
    db,
    *,
    tenant_id: str,
    current_user_id: Optional[str],
    active_sessions=None,
    connection_manager=None,
) -> list[dict[str, Any]]:
    """Cruza presença em memória com a identidade persistida do tenant.

    O tracker não é usado como fonte de tenant/role; ele fornece somente IDs
    potencialmente presentes. Tenant, papel e status são sempre relidos de users.
    """
    candidate_ids: set[str] = set()
    if active_sessions is not None:
        try:
            candidate_ids.update(str(uid) for uid in active_sessions.get_online(threshold_minutes=5).keys())
        except Exception:
            pass
    if connection_manager is not None:
        try:
            candidate_ids.update(str(uid) for uid in connection_manager.active_connections.keys())
        except Exception:
            pass

    if current_user_id:
        candidate_ids.discard(str(current_user_id))
    if not candidate_ids:
        return []

    rows = await db.users.find(
        {
            "id": {"$in": list(candidate_ids)},
            "mantenedora_id": tenant_id,
            "status": "active",
        },
        {
            "_id": 0,
            "id": 1,
            "full_name": 1,
            "email": 1,
            "role": 1,
        },
    ).to_list(None)

    blockers = [row for row in rows if not is_super_admin(row)]
    blockers.sort(key=lambda row: (str(row.get("full_name") or row.get("email") or "").casefold()))
    return blockers


async def _audit_access_control(
    *,
    action: str,
    tenant: dict,
    current_user: dict,
    request: Request,
    extra_data: Optional[dict] = None,
) -> None:
    try:
        from audit_service import audit_service

        await audit_service.log(
            action=action,
            collection="mantenedoras",
            user=current_user,
            request=request,
            document_id=tenant.get("id"),
            description=f"Controle de acesso da mantenedora: {tenant.get('nome') or tenant.get('id')}",
            extra_data=extra_data or {},
        )
    except Exception:
        # Auditoria não deve transformar uma leitura/erro de governança em 500.
        pass


def install_admin_mantenedora_access_setup(admin_module) -> None:
    """Envolve ``admin.setup_router`` e registra as rotas uma única vez."""
    if getattr(admin_module, "_mantenedora_access_control_setup_installed", False):
        return

    original_setup = admin_module.setup_router

    def setup_with_mantenedora_access(
        db,
        active_sessions=None,
        connection_manager=None,
        get_db_for_user=None,
        **kwargs,
    ):
        result = original_setup(
            db,
            active_sessions=active_sessions,
            connection_manager=connection_manager,
            get_db_for_user=get_db_for_user,
            **kwargs,
        )

        router = admin_module.router
        if getattr(router, "_mantenedora_access_control_routes_installed", False):
            return result

        @router.get("/mantenedoras/access-status")
        async def get_mantenedora_access_status(request: Request):
            """Status leve pós-login, acessível mesmo se o tenant estiver desativado."""
            current_user = await AuthMiddleware.get_current_user(request)
            current_db = get_db_for_user(current_user) if get_db_for_user else db
            tenant = await _tenant_for_request(current_db, current_user, request)

            if tenant is None:
                if is_super_admin(current_user):
                    return {
                        "tenant_selected": False,
                        "active": True,
                        "access_allowed": True,
                        "management_allowed": True,
                        "reason": "SUPER_ADMIN_CONTROL_PLANE",
                        "mantenedora": None,
                        "allowed_roles": [],
                    }
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "TENANT_CONTEXT_REQUIRED",
                        "message": "Usuário sem mantenedora vinculada.",
                    },
                )

            active = is_tenant_active(tenant)
            operational_allowed = can_access_tenant(tenant, current_user)
            management_allowed = is_super_admin(current_user)
            return {
                "tenant_selected": True,
                "active": active,
                "access_allowed": operational_allowed,
                "management_allowed": management_allowed,
                "reason": (
                    "ACTIVE"
                    if active
                    else "INACTIVE_ROLE_ALLOWED"
                    if operational_allowed
                    else "TENANT_INACTIVE"
                ),
                "mantenedora": {
                    "id": tenant.get("id"),
                    "nome": tenant.get("nome") or tenant.get("name"),
                    "secretaria": tenant.get("secretaria"),
                    "municipio": tenant.get("municipio"),
                    "estado": tenant.get("estado"),
                    "brasao_url": tenant.get("brasao_url") or tenant.get("logotipo_url"),
                },
                "allowed_roles": inactive_allowed_roles(tenant),
            }

        @router.get("/mantenedoras/access-control")
        async def get_mantenedora_access_control(request: Request):
            current_user = await AuthMiddleware.get_current_user(request)
            if not is_super_admin(current_user):
                raise HTTPException(status_code=403, detail="Apenas Super Administrador pode gerenciar este controle")

            current_db = get_db_for_user(current_user) if get_db_for_user else db
            tenant = await _tenant_for_request(current_db, current_user, request)
            if not tenant:
                raise HTTPException(status_code=409, detail="Selecione uma mantenedora para gerenciar")

            blockers = await _collect_active_tenant_users(
                current_db,
                tenant_id=str(tenant.get("id")),
                current_user_id=current_user.get("id"),
                active_sessions=active_sessions,
                connection_manager=connection_manager,
            )
            return {
                "id": tenant.get("id"),
                "nome": tenant.get("nome") or tenant.get("name"),
                "active": is_tenant_active(tenant),
                "allowed_roles": inactive_allowed_roles(tenant),
                "role_options": _role_options(),
                "online_blockers": blockers,
                "online_blocker_count": len(blockers),
                "super_admin_management_bypass": True,
            }

        @router.put("/mantenedoras/access-control")
        async def update_mantenedora_access_control(
            payload: MantenedoraAccessControlUpdate,
            request: Request,
        ):
            current_user = await AuthMiddleware.get_current_user(request)
            if not is_super_admin(current_user):
                raise HTTPException(status_code=403, detail="Apenas Super Administrador pode gerenciar este controle")

            current_db = get_db_for_user(current_user) if get_db_for_user else db
            tenant = await _tenant_for_request(current_db, current_user, request)
            if not tenant:
                raise HTTPException(status_code=409, detail="Selecione uma mantenedora para gerenciar")

            current_active = is_tenant_active(tenant)
            requested_active = current_active if payload.ativo is None else bool(payload.ativo)
            target_roles = (
                inactive_allowed_roles(tenant)
                if payload.allowed_roles is None
                else normalize_allowed_roles(payload.allowed_roles)
            )

            if payload.allowed_roles is not None:
                submitted = {str(role).strip() for role in payload.allowed_roles if str(role).strip()}
                invalid = sorted(submitted - set(CONFIGURABLE_INACTIVE_ACCESS_ROLES))
                if invalid:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={
                            "code": "INVALID_INACTIVE_ACCESS_ROLES",
                            "roles": invalid,
                        },
                    )

            # Transição ativa -> inativa: qualquer usuário operacional conectado
            # bloqueia a ação. A verificação ocorre imediatamente antes do write.
            if current_active and not requested_active:
                blockers = await _collect_active_tenant_users(
                    current_db,
                    tenant_id=str(tenant.get("id")),
                    current_user_id=current_user.get("id"),
                    active_sessions=active_sessions,
                    connection_manager=connection_manager,
                )
                if blockers:
                    await _audit_access_control(
                        action="reject",
                        tenant=tenant,
                        current_user=current_user,
                        request=request,
                        extra_data={
                            "event": "mantenedora_deactivation_blocked",
                            "connected_users": blockers,
                            "count": len(blockers),
                        },
                    )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "code": "TENANT_HAS_ACTIVE_SESSIONS",
                            "message": "Existem usuários conectados nesta mantenedora. A desativação foi bloqueada.",
                            "count": len(blockers),
                            "users": blockers,
                        },
                    )

            update = {
                "acesso_desativado_roles": target_roles,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "access_control_updated_by": current_user.get("id"),
            }
            if payload.ativo is not None:
                # Normaliza todos os marcadores históricos para evitar um ``ativo``
                # antigo contradizer o ``status`` novo (ou vice-versa).
                update.update(
                    {
                        "ativo": requested_active,
                        "ativa": requested_active,
                        "status": "active" if requested_active else "inactive",
                    }
                )

            await current_db.mantenedoras.update_one(
                {"id": tenant.get("id")},
                {"$set": update},
            )
            updated = await current_db.mantenedoras.find_one(
                {"id": tenant.get("id")},
                {"_id": 0},
            )

            await _audit_access_control(
                action="update",
                tenant=updated or tenant,
                current_user=current_user,
                request=request,
                extra_data={
                    "event": "mantenedora_access_control_updated",
                    "old_active": current_active,
                    "new_active": requested_active,
                    "allowed_roles": target_roles,
                },
            )
            return {
                "id": (updated or tenant).get("id"),
                "nome": (updated or tenant).get("nome") or (updated or tenant).get("name"),
                "active": is_tenant_active(updated or tenant),
                "allowed_roles": inactive_allowed_roles(updated or tenant),
                "role_options": _role_options(),
                "online_blockers": [],
                "online_blocker_count": 0,
                "super_admin_management_bypass": True,
            }

        router._mantenedora_access_control_routes_installed = True
        return result

    admin_module.setup_router = setup_with_mantenedora_access
    admin_module._mantenedora_access_control_setup_installed = True
