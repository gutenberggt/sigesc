from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"


def test_tenant_switcher_has_no_cross_tenant_operational_option():
    source = (FRONTEND / "components" / "TenantSwitcher.jsx").read_text(encoding="utf-8")

    assert '<span>Todas (cross-tenant)</span>' not in source
    assert "tenant-option-all" not in source
    assert "Selecione a mantenedora" in source
    assert "activeMantenedoraId" in source
    assert "/admin/mantenedoras" in source


def test_operational_pages_are_gated_until_super_admin_selects_tenant():
    source = (FRONTEND / "components" / "TenantSyncBoundary.jsx").read_text(encoding="utf-8")

    assert "tenant-selection-required" in source
    assert "user?.role === 'super_admin'" in source
    assert "!activeTenantId" in source
    assert "/admin/mantenedoras" in source
    assert "/admin/tenant" in source
    assert "getActiveTenantId" in source


def test_mantenedora_context_does_not_fetch_operational_data_without_selection():
    source = (FRONTEND / "contexts" / "MantenedoraContext.js").read_text(encoding="utf-8")

    assert "user.role === 'super_admin' && !getActiveTenantId()" in source
    assert "Mantenedora não disponível" in source
    assert "Floresta do Araguaia" not in source
