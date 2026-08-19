"""P0 — paridade operacional de Objetos de Conhecimento no DVD."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "frontend/src/services/contentDvdBridge.js"
DASHBOARD = ROOT / "frontend/src/pages/ProfessorDashboard.js"
COPY_ADAPTER = ROOT / "backend/routers/content_copy_dvd.py"
HISTORY_ADAPTER = ROOT / "backend/routers/content_dvd_history.py"
ROUTERS_INIT = ROOT / "backend/routers/__init__.py"


def test_quick_access_content_requires_diary_context():
    source = DASHBOARD.read_text(encoding="utf-8")
    assert 'data-testid="menu-objetos-conhecimento"' in source
    assert 'onClick={openFromMyDiaries}' in source
    assert source.count('Escolha o diário/vínculo abaixo') >= 2
    assert "onClick={() => navigate('/professor/objetos-conhecimento')}" not in source


def test_content_bridge_resolves_authorized_diaries_and_sibling_assignments():
    source = BRIDGE.read_text(encoding="utf-8")
    assert '/professor/diarios' in source
    assert 'contentDiariesFor' in source
    assert 'resolveAssignment' in source
    assert 'siblings:' in source
    assert 'sibling.assignment_id' in source
    assert 'sibling.component_id' in source
    assert 'assignment_id: assignmentId' in source


def test_multicomponent_create_uses_component_specific_assignment():
    source = BRIDGE.read_text(encoding="utf-8")
    assert 'const componentId = payload.component_id || payload.course_id || null' in source
    assert 'payload.assignment_id = assignmentId' in source
    assert 'preferredAssignmentId: rootAssignmentId' in source


def test_legacy_sibling_records_keep_history_assignment_for_copy_authorization():
    source = BRIDGE.read_text(encoding="utf-8")
    assert 'history_assignment_id:' in source
    assert 'withHistoryAssignment(item, sibling.assignment_id)' in source
    assert 'primaryHistoryAssignmentId' in source
    assert 'current.history_assignment_id' in source


def test_dvd_copy_is_enabled_only_with_target_assignment():
    source = BRIDGE.read_text(encoding="utf-8")
    assert "Cópia entre turmas ainda não está disponível" not in source
    assert 'CONTENT_COPY_TARGET_ASSIGNMENT_REQUIRED' in source
    assert 'target_assignment_id: targetAssignmentId' in source
    assert 'source_assignment_id:' in source


def test_copy_backend_reuses_canonical_content_engine_and_preserves_traceability():
    source = COPY_ADAPTER.read_text(encoding="utf-8")
    assert 'save_content_canonical' in source
    assert 'ContentEntryCreate' in source
    assert 'authorize_content_record' in source
    assert 'list_assignment_content_history' in source
    assert '"copied_from_id": source_id' in source
    assert '"copied_from_source": source_kind' in source
    assert 'target_assignment_id: str' in source


def test_copy_source_without_own_assignment_requires_authorized_history_view():
    source = COPY_ADAPTER.read_text(encoding="utf-8")
    assert 'SOURCE_ASSIGNMENT_REQUIRED' in source
    assert 'SOURCE_CONTENT_NOT_VISIBLE' in source
    assert '_assert_visible_through_source_assignment' in source
    assert 'if canonical.get("assignment_id")' in source
    assert 'else:\n            await _assert_visible_through_source_assignment' in source


def test_copy_never_writes_to_learning_objects():
    source = COPY_ADAPTER.read_text(encoding="utf-8")
    assert 'db.learning_objects.find_one' in source
    for forbidden in (
        'db.learning_objects.insert_one',
        'db.learning_objects.update_one',
        'db.learning_objects.delete_one',
        'db.learning_objects.replace_one',
    ):
        assert forbidden not in source


def test_initial_years_pdf_aggregates_only_authorized_content_siblings():
    source = HISTORY_ADAPTER.read_text(encoding="utf-8")
    assert 'list_teacher_diaries' in source
    assert '_is_multi_component_day_level' in source
    assert '_pdf_assignment_ids' in source
    assert 'item.get("capabilities", {}).get("content_enabled") is True' in source
    assert 'item.get("class_id") == primary_assignment.get("class_id")' in source
    assert '_merged_pdf_history' in source
    assert 'assignment_ids=assignment_ids' in source


def test_final_years_or_explicit_component_pdf_stays_single_assignment():
    source = HISTORY_ADAPTER.read_text(encoding="utf-8")
    assert 'if course_id or not _is_multi_component_day_level(class_info):' in source
    assert 'return [primary_id]' in source


def test_copy_setup_is_installed_after_history_bridge():
    source = ROUTERS_INIT.read_text(encoding="utf-8")
    history = source.index('install_content_history_setups(')
    copy = source.index('install_content_copy_setup(')
    assert history < copy
