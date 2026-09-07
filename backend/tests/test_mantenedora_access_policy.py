import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.mantenedora_access_policy import (
    can_access_tenant,
    inactive_allowed_roles,
    is_tenant_active,
    normalize_allowed_roles,
)
from tenant_scope import (
    requires_operational_tenant_context,
    resolve_operational_tenant_context,
)


BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


class _Mantenedoras:
    def __init__(self, tenant):
        self.tenant = tenant

    async def find_one(self, query, projection=None):
        if self.tenant and str(self.tenant.get("id")) == str(query.get("id")):
            return dict(self.tenant)
        return None


class _Db:
    def __init__(self, tenant):
        self.mantenedoras = _Mantenedoras(tenant)


def _request(path="/api/students", *, tenant_header=None):
    headers = {}
    if tenant_header:
        headers["X-Mantenedora-Id"] = tenant_header
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        method="GET",
        headers=headers,
        query_params={},
        scope={"path": path},
        state=SimpleNamespace(),
    )


def test_active_tenant_allows_normal_role():
    tenant = {"id": "t1", "status": "active"}
    assert is_tenant_active(tenant) is True
    assert can_access_tenant(tenant, {"role": "professor"}) is True


def test_inactive_tenant_is_fail_closed_without_explicit_role():
    tenant = {"id": "t1", "status": "inactive"}
    assert is_tenant_active(tenant) is False
    assert can_access_tenant(tenant, {"role": "professor"}) is False
    assert inactive_allowed_roles(tenant) == []


def test_inactive_tenant_allows_only_selected_active_role():
    tenant = {
        "id": "t1",
        "ativo": False,
        "acesso_desativado_roles": ["professor", "diretor"],
    }
    assert can_access_tenant(tenant, {"role": "professor"}) is True
    assert can_access_tenant(tenant, {"role": "diretor"}) is True
    assert can_access_tenant(tenant, {"role": "secretario"}) is False


def test_only_active_session_role_can_cross_inactive_tenant_gate():
    tenant = {
        "id": "t1",
        "status": "inactive",
        "acesso_desativado_roles": ["diretor"],
    }
    # Uma role secundária presente em `roles` não muda o papel ativo da sessão.
    # A trava institucional só libera o papel ativo; RBAC continua independente.
    user = {"role": "professor", "roles": ["professor", "diretor"]}
    assert can_access_tenant(tenant, user) is False


def test_super_admin_has_no_implicit_operational_bypass_when_inactive():
    tenant = {"id": "t1", "status": "inactive", "acesso_desativado_roles": []}
    assert can_access_tenant(tenant, {"role": "super_admin"}) is False


def test_allowed_roles_are_normalized_and_unknown_roles_are_not_persistable():
    roles = normalize_allowed_roles(["professor", "professor", "diretor", "root", ""])
    assert roles == ["diretor", "professor"]


def test_global_tenant_resolver_blocks_unselected_role():
    tenant = {"id": "t1", "nome": "Rede Teste", "status": "inactive"}
    user = {"id": "u1", "role": "professor", "mantenedora_id": "t1"}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(resolve_operational_tenant_context(_Db(tenant), user, _request()))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "TENANT_INACTIVE"


def test_global_tenant_resolver_allows_selected_role_but_keeps_tenant_scope():
    tenant = {
        "id": "t1",
        "nome": "Rede Teste",
        "status": "inactive",
        "acesso_desativado_roles": ["professor"],
    }
    user = {"id": "u1", "role": "professor", "mantenedora_id": "t1"}
    request = _request()
    ctx = asyncio.run(resolve_operational_tenant_context(_Db(tenant), user, request))
    assert ctx.id == "t1"
    assert request.state.active_mantenedora_id == "t1"


def test_access_status_is_session_plane_for_blocked_user():
    user = {"id": "u1", "role": "professor", "mantenedora_id": "t1"}
    assert requires_operational_tenant_context(
        user,
        _request("/api/mantenedoras/access-status"),
    ) is False


def test_super_admin_is_blocked_on_operational_route_for_inactive_tenant():
    tenant = {"id": "t1", "nome": "Rede Teste", "status": "inactive"}
    user = {"id": "root", "role": "super_admin"}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            resolve_operational_tenant_context(
                _Db(tenant),
                user,
                _request("/api/students", tenant_header="t1"),
            )
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "TENANT_INACTIVE"


def test_super_admin_can_resolve_inactive_tenant_only_in_control_plane():
    tenant = {"id": "t1", "nome": "Rede Teste", "status": "inactive"}
    user = {"id": "root", "role": "super_admin"}
    request = _request("/api/mantenedora", tenant_header="t1")
    assert requires_operational_tenant_context(user, request) is False
    ctx = asyncio.run(resolve_operational_tenant_context(_Db(tenant), user, request))
    assert ctx.id == "t1"
    assert request.state.active_mantenedora_id == "t1"


def test_access_control_panel_uses_canonical_tenant_aware_transport_and_selector():
    source = (
        REPO
        / "frontend"
        / "src"
        / "components"
        / "mantenedora"
        / "MantenedoraAccessControlPanel.jsx"
    ).read_text(encoding="utf-8")
    assert "apiFetch" in source
    assert "getActiveTenantId" in source
    assert "mantenedora-access-selector" in source
    assert "Mantenedora a gerenciar" in source
    assert "axios.get(API)" not in source
    assert "axios.put(API" not in source


def test_generic_mantenedora_edit_cannot_bypass_availability_control():
    source = (BACKEND / "routers" / "mantenedoras.py").read_text(encoding="utf-8")
    assert "MANTENEDORA_AVAILABILITY_REQUIRES_ACCESS_CONTROL" in source
    assert 'k not in {"ativo", "ativa", "status", "acesso_desativado_roles"}' in source
    assert "/mantenedoras/access-control" in source
