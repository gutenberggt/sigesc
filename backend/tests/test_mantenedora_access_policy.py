import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.mantenedora_access_policy import (
    can_access_tenant,
    inactive_allowed_roles,
    is_tenant_active,
    is_tenant_in_maintenance,
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
    assert is_tenant_in_maintenance(tenant) is False
    assert can_access_tenant(tenant, {"role": "professor"}) is True


def test_maintenance_flag_is_independent_from_availability():
    tenant = {"id": "t1", "status": "active", "maintenance_mode": True}
    assert is_tenant_active(tenant) is True
    assert is_tenant_in_maintenance(tenant) is True
    # can_access_tenant decide somente disponibilidade; manutenção é aplicada no tenant_scope.
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


def test_inactive_exception_precedes_maintenance_flag():
    tenant = {
        "id": "t1",
        "nome": "Rede Teste",
        "status": "inactive",
        "maintenance_mode": True,
        "acesso_desativado_roles": ["professor"],
    }
    user = {"id": "u1", "role": "professor", "mantenedora_id": "t1"}
    ctx = asyncio.run(resolve_operational_tenant_context(_Db(tenant), user, _request()))
    assert ctx.id == "t1"


def test_active_maintenance_blocks_normal_operational_user():
    tenant = {
        "id": "t1",
        "nome": "Rede Teste",
        "status": "active",
        "maintenance_mode": True,
    }
    user = {"id": "u1", "role": "professor", "mantenedora_id": "t1"}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(resolve_operational_tenant_context(_Db(tenant), user, _request()))
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "TENANT_MAINTENANCE"


def test_super_admin_keeps_operational_access_during_active_maintenance():
    tenant = {
        "id": "t1",
        "nome": "Rede Teste",
        "status": "active",
        "maintenance_mode": True,
    }
    user = {"id": "root", "role": "super_admin"}
    request = _request("/api/students", tenant_header="t1")
    ctx = asyncio.run(resolve_operational_tenant_context(_Db(tenant), user, request))
    assert ctx.id == "t1"
    assert request.state.active_mantenedora_id == "t1"


def test_access_status_is_session_plane_for_blocked_user():
    user = {"id": "u1", "role": "professor", "mantenedora_id": "t1"}
    assert requires_operational_tenant_context(
        user,
        _request("/api/mantenedora/access-status"),
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


def test_access_control_panel_exposes_only_current_selected_tenant_and_two_cards():
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
    assert "ACCESS_CONTROL_API" in source
    assert "MAINTENANCE_CONTROL_API" in source
    assert "TENANTS_API" not in source
    assert "mantenedora_id=" not in source
    assert "tenants.map" not in source
    assert "Promise.all(items.map" not in source
    assert "mantenedora-access-card-current" in source
    assert 'data-testid="mantenedora-control-cards-grid"' in source
    assert 'data-testid="mantenedora-active-switch"' in source
    assert 'data-testid="mantenedora-maintenance-card"' in source
    assert 'data-testid="mantenedora-maintenance-switch"' in source
    assert 'role="switch"' in source
    assert "Operação normal" in source
    assert "Em manutenção" in source
    assert "Super Administrador permanece com acesso operacional completo" in source
    assert "Acesso excepcional enquanto desativada" in source
    assert "!active && (" in source
    assert "Secretário Escolar" in source
    assert "Diretor" in source
    assert "Professor" in source
    assert "Coordenador" in source
    assert "CNPJ:" not in source
    assert "Mantenedora a gerenciar" not in source
    assert "mantenedora-access-selector" not in source
    assert "Verificar conexões" not in source
    assert "Sim, desativar" not in source


def test_maintenance_page_and_frontend_gate_are_wired():
    protected = (REPO / "frontend" / "src" / "components" / "ProtectedRoute.js").read_text(encoding="utf-8")
    page = (REPO / "frontend" / "src" / "pages" / "MantenedoraManutencao.jsx").read_text(encoding="utf-8")
    context = (REPO / "frontend" / "src" / "contexts" / "MantenedoraContext.js").read_text(encoding="utf-8")

    assert "TENANT_MAINTENANCE" in protected
    assert "MantenedoraManutencao" in protected
    assert "isMaintenanceTenant && !isSuperAdmin" in protected
    assert "Sistema em manutenção" in page
    assert "Seus dados permanecem preservados" in page
    assert 'data-testid="mantenedora-maintenance-page"' in page
    assert "TENANT_MAINTENANCE" in context
    assert "axios.interceptors.response.use" in context
    assert "setInterval" in context


def test_super_admin_control_plane_header_is_authoritative_and_cross_tenant_query_is_rejected():
    source = (BACKEND / "routers" / "mantenedora_access_control.py").read_text(encoding="utf-8")
    helper = source.split("def _selected_superadmin_tenant", 1)[1].split("def _role_options", 1)[0]
    header_lookup = 'request.headers.get("X-Mantenedora-Id")'
    query_lookup = 'request.query_params.get("mantenedora_id")'
    assert header_lookup in helper
    assert query_lookup in helper
    assert helper.index(header_lookup) < helper.index(query_lookup)
    assert "if query and query != header" in helper
    assert "CROSS_TENANT_CONTROL_FORBIDDEN" in helper
    assert "return header or None" in helper
    assert "return query" not in helper


def test_access_and_maintenance_routes_do_not_collide_with_dynamic_mantenedora_detail():
    access_source = (BACKEND / "routers" / "mantenedora_access_control.py").read_text(encoding="utf-8")
    tenants_source = (BACKEND / "routers" / "mantenedoras.py").read_text(encoding="utf-8")
    panel_source = (
        REPO
        / "frontend"
        / "src"
        / "components"
        / "mantenedora"
        / "MantenedoraAccessControlPanel.jsx"
    ).read_text(encoding="utf-8")
    context_source = (
        REPO / "frontend" / "src" / "contexts" / "MantenedoraContext.js"
    ).read_text(encoding="utf-8")

    assert '@router.get("/mantenedoras/{mid}")' in tenants_source
    assert '@router.get("/mantenedora/access-control")' in access_source
    assert '@router.put("/mantenedora/access-control")' in access_source
    assert '@router.get("/mantenedora/access-status")' in access_source
    assert '@router.get("/mantenedora/maintenance-control")' in access_source
    assert '@router.put("/mantenedora/maintenance-control")' in access_source
    assert '`${API_BASE}/mantenedora/access-control`' in panel_source
    assert '`${API_BASE}/mantenedora/maintenance-control`' in panel_source
    assert '/api/mantenedora/access-status' in context_source
    assert '@router.get("/mantenedoras/access-control")' not in access_source
    assert '@router.get("/mantenedoras/access-status")' not in access_source
    assert '@router.get("/mantenedoras/maintenance-control")' not in access_source


def test_maintenance_control_is_independent_and_does_not_block_on_connected_users():
    source = (BACKEND / "routers" / "mantenedora_access_control.py").read_text(encoding="utf-8")
    maintenance_section = source.split('@router.put("/mantenedora/maintenance-control")', 1)[1]
    assert '"maintenance_mode": requested_mode' in maintenance_section
    assert '"maintenance_updated_by": current_user.get("id")' in maintenance_section
    assert "mantenedora_maintenance_updated" in maintenance_section
    assert "TENANT_HAS_ACTIVE_SESSIONS" not in maintenance_section
    assert "connected_user_count" in maintenance_section


def test_generic_mantenedora_edit_cannot_bypass_availability_control():
    source = (BACKEND / "routers" / "mantenedoras.py").read_text(encoding="utf-8")
    assert "MANTENEDORA_AVAILABILITY_REQUIRES_ACCESS_CONTROL" in source
    assert 'k not in {"ativo", "ativa", "status", "acesso_desativado_roles"}' in source
