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
    assert source.count("user = await _require_super_admin(request)") == 5


def test_all_public_operations_are_guarded():
    source = _source()
    for route in (
        '/admin/manual-copy/options',
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
    assert '"LEGACY_TEACHER_USER_ID_UNRESOLVED"' in source
    assert '"ATTENDANCE_TEACHER_USER_ID_UNRESOLVED"' in source
    assert 'item.get("target_teacher_id")' in source
    # O usuário operador não é usado como fallback de autoria pedagógica no adapter.
    assert 'teacher_id=user.get("id")' not in source


def test_empty_target_means_skip_and_duplicate_target_is_blocked():
    source = _source()
    assert "selected = [mapping for mapping in payload.mappings if mapping.target_date]" in source
    assert '"DUPLICATE_TARGET_DATE"' in source
    assert '"skipped_without_target"' in source


def test_preflight_manifest_is_recomputed_before_apply():
    source = _source()
    assert "plan = await _build_plan" in source
    assert '"MANUAL_COPY_MANIFEST_CHANGED"' in source
    assert "plan.get(\"manifest_hash\") != payload.manifest_hash" in source


def test_apply_is_create_only_under_concurrent_target_change():
    source = _source()
    # Se um draft surgir entre preflight e writer, ev=0 gera conflito em vez de update.
    assert "expected_version=0" in source
    assert "update silencioso" in source


def test_apply_is_idempotent_by_native_unique_batch_key():
    source = _source()
    assert "DuplicateKeyError" in source
    assert "def _batch_key" in source
    assert '"_id": key' in source
    assert 'existing_batch.get("status") == "COMPLETED"' in source
    assert '"MANUAL_COPY_REQUEST_ALREADY_USED"' in source


def test_rollback_uses_only_ids_created_by_current_apply():
    source = _source()
    assert "created_ids: list[str] = []" in source
    assert '"created_by": user.get("id")' in source
    assert '"manual_copy_batch_id": batch_id' in source
    assert '"FAILED_ROLLED_BACK"' in source
    assert "A lista ``created_ids`` não vem do cliente" in source


def test_source_is_revalidated_against_original_scope_at_apply():
    source = _source()
    assert "expected_class_id=payload.source_class_id" in source
    assert "expected_component_id=payload.source_component_id" in source
    assert 'detail="Conteúdo de origem mudou de turma"' in source
    assert 'detail="Conteúdo de origem mudou de componente"' in source


def test_tenant_context_is_operational_and_fail_closed():
    source = _source()
    assert "resolve_operational_tenant_context" in source
    assert source.count("resolve_operational_tenant_context(") >= 5
    assert '"mantenedora_id": tenant_id' in source
    assert "_class_in_tenant" in source
    assert "_school_in_tenant" in source


def test_options_are_tenant_scoped_for_ui():
    source = _source()
    assert "async def _options" in source
    assert '{"mantenedora_id": tenant_id}' in source
    assert '"schools": school_items' in source
    assert '"classes": class_items' in source
    assert '"courses": course_items' in source


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
