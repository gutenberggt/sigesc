from pathlib import Path
from types import SimpleNamespace

from services.content_institutional_visibility_policy import (
    ADDITIONAL_INSTITUTIONAL_CONTENT_VIEW_ROLES,
    install_content_institutional_visibility_policy,
)


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "frontend/src/services/contentLegacyCanonicalVisibilityBridge.js"
ROUTERS_INIT = ROOT / "backend/routers/__init__.py"


def _module(**kwargs):
    return SimpleNamespace(**kwargs)


def test_additional_roles_cover_all_semed_read_profiles_and_auxiliary_reader():
    assert ADDITIONAL_INSTITUTIONAL_CONTENT_VIEW_ROLES == frozenset(
        {"auxiliar_secretaria", "semed", "semed1", "semed2"}
    )


def test_installer_expands_only_view_policies_and_preserves_write_roles():
    content_entries = _module(
        VIEW_ROLES=["professor", "coordenador", "admin", "secretario", "semed3"],
        WRITE_ROLES=["professor", "coordenador", "admin", "secretario"],
    )
    content_history = _module(
        VIEW_ROLES=["professor", "coordenador", "admin", "secretario", "semed3"]
    )
    diary_access = _module(
        MANAGEMENT_VIEW_ROLES=frozenset(
            {"super_admin", "admin", "gerente", "secretario", "semed3", "coordenador", "diretor"}
        ),
        MANAGEMENT_EDIT_ROLES=frozenset(
            {"super_admin", "admin", "gerente", "semed3", "coordenador"}
        ),
    )
    snapshot_access = _module(MANAGEMENT_VIEW_ROLES=diary_access.MANAGEMENT_VIEW_ROLES)

    write_before = tuple(content_entries.WRITE_ROLES)
    edit_before = diary_access.MANAGEMENT_EDIT_ROLES

    result = install_content_institutional_visibility_policy(
        content_entries,
        content_history,
        diary_access,
        snapshot_access,
    )

    expected_read = {"auxiliar_secretaria", "semed", "semed1", "semed2", "semed3"}
    assert expected_read.issubset(set(content_entries.VIEW_ROLES))
    assert expected_read.issubset(set(content_history.VIEW_ROLES))
    assert expected_read.issubset(set(diary_access.MANAGEMENT_VIEW_ROLES))
    assert snapshot_access.MANAGEMENT_VIEW_ROLES == diary_access.MANAGEMENT_VIEW_ROLES

    assert tuple(content_entries.WRITE_ROLES) == write_before
    assert diary_access.MANAGEMENT_EDIT_ROLES == edit_before

    assert expected_read.issubset(set(result["content_view_roles"]))
    assert expected_read.issubset(set(result["dvd_history_view_roles"]))
    assert expected_read.issubset(set(result["management_view_roles"]))


def test_installer_is_idempotent():
    content_entries = _module(VIEW_ROLES=["admin"], WRITE_ROLES=["admin"])
    content_history = _module(VIEW_ROLES=["admin"])
    diary_access = _module(
        MANAGEMENT_VIEW_ROLES=frozenset({"admin"}),
        MANAGEMENT_EDIT_ROLES=frozenset({"admin"}),
    )
    snapshot_access = _module(MANAGEMENT_VIEW_ROLES=frozenset({"admin"}))

    install_content_institutional_visibility_policy(
        content_entries, content_history, diary_access, snapshot_access
    )
    first = tuple(content_entries.VIEW_ROLES)
    install_content_institutional_visibility_policy(
        content_entries, content_history, diary_access, snapshot_access
    )
    second = tuple(content_entries.VIEW_ROLES)

    assert first == second


def test_frontend_bridge_covers_professor_and_management_surfaces():
    source = BRIDGE.read_text(encoding="utf-8")

    assert "'/professor/objetos-conhecimento'" in source
    assert "'/admin/learning-objects'" in source
    assert "includeAssignedCanonical: pageMode === 'management'" in source
    assert "assignment_id: current.assignment_id || null" in source


def test_institutional_policy_is_installed_before_content_history_setup():
    source = ROUTERS_INIT.read_text(encoding="utf-8")
    policy_call = source.index("install_content_institutional_visibility_policy(")
    history_call = source.index("install_content_history_setups(_content_entries_mod, _learning_objects_mod)")

    assert policy_call < history_call
