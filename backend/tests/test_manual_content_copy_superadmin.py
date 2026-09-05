from pathlib import Path


ROUTER = Path("backend/routers/manual_content_copy_admin.py")
INIT = Path("backend/routers/__init__.py")


def _source():
    return ROUTER.read_text(encoding="utf-8")


def test_service_is_explicitly_super_admin_only():
    source = _source()
    assert 'AuthMiddleware.require_roles(["super_admin"])' in source
    assert 'user.get("role") != "super_admin"' in source
    assert "Serviço exclusivo do Super Administrador" in source
    assert source.count("user = await _require_super_admin(request)") == 4


def test_all_public_operations_are_guarded():
    source = _source()
    for route in (
        '/admin/manual-copy/source',
        '/admin/manual-copy/destinations',
        '/admin/manual-copy/preflight',
        '/admin/manual-copy/apply',
    ):
        assert route in source
    # Nenhum endpoint administrativo pode usar uma lista mais ampla de roles.
    assert 'require_roles(["admin"' not in source
    assert 'require_roles(["super_admin",' not in source


def test_manual_copy_reuses_canonical_writer_and_never_writes_legacy():
    source = _source()
    assert "save_content_canonical" in source
    assert "ContentEntryCreate" in source
    assert "learning_objects.insert" not in source
    assert "learning_objects.update" not in source
    assert 'COPY_TYPE = "MANUAL_MAPPED_CONTENT_COPY"' in source


def test_target_binding_is_fail_closed_and_does_not_attribute_to_super_admin():
    source = _source()
    assert '"TARGET_TEACHER_NOT_RESOLVED"' in source
    assert '"MULTIPLE_DVD_ASSIGNMENTS"' in source
    assert '"MULTIPLE_LEGACY_TEACHERS"' in source
    assert 'teacher_id=item.get("target_teacher_id")' in source
    # O usuário operador não é usado como fallback de autoria pedagógica no adapter.
    assert 'teacher_id=user.get("id")' not in source


def test_empty_target_means_skip_and_duplicate_target_is_blocked():
    source = _source()
    assert "selected = [m for m in payload.mappings if m.target_date]" in source
    assert '"DUPLICATE_TARGET_DATE"' in source
    assert '"skipped_without_target"' in source


def test_preflight_manifest_is_recomputed_before_apply():
    source = _source()
    assert "plan = await _build_plan" in source
    assert '"MANUAL_COPY_MANIFEST_CHANGED"' in source
    assert "plan.get(\"manifest_hash\") != payload.manifest_hash" in source


def test_apply_is_idempotent_and_rolls_back_only_own_batch():
    source = _source()
    assert '"request_id": payload.request_id' in source
    assert 'existing_batch.get("status") == "COMPLETED"' in source
    assert '"manual_copy_batch_id": batch_id' in source
    assert '"manual_copy_batch_id": batch_id, "deleted": False' in source
    assert '"FAILED_ROLLED_BACK"' in source


def test_tenant_context_is_operational_and_fail_closed():
    source = _source()
    assert "resolve_operational_tenant_context" in source
    assert source.count("resolve_operational_tenant_context(db, user, request)") == 4
    assert '"mantenedora_id": tenant_id' in source


def test_adapter_is_installed_before_content_router_is_imported_by_server():
    init_source = INIT.read_text(encoding="utf-8")
    assert "from .manual_content_copy_admin import install_manual_content_copy_setup" in init_source
    assert "install_manual_content_copy_setup(_content_entries_mod)" in init_source


def test_no_automatic_date_pairing_heuristic_is_present():
    source = _source()
    forbidden = (
        "GLOBAL_ORDINAL",
        "calendar_cross_month",
        "source_slot",
        "automatic_pair",
    )
    for token in forbidden:
        assert token not in source
