from pathlib import Path


BACKEND_ROUTER = Path("routers/learning_objects.py")
CONTENT_ENTRIES_ROUTER = Path("routers/content_entries.py")
FRONTEND_BRIDGE = Path("../frontend/src/services/contentDvdBridge.js")
LEARNING_OBJECTS_PAGE = Path("../frontend/src/pages/LearningObjects.js")
DASHBOARD = Path("../frontend/src/components/professor/MyDiariesSection.jsx")
PREFILL_HOOK = Path("../frontend/src/hooks/useDiaryPrefill.js")


def test_legacy_router_has_professor_antibypass_guards():
    src = BACKEND_ROUTER.read_text(encoding="utf-8")
    assert "def _block_legacy_if_dvd" in src
    assert src.count("await _block_legacy_if_dvd(") >= 7
    assert "DVD_CONTENT_LEGACY_BLOCKED" not in src  # detalhe fica centralizado no serviço


def test_pdf_switches_to_canonical_content_entries_for_dvd():
    src = BACKEND_ROUTER.read_text(encoding="utf-8")
    assert "assignment_id: Optional[str] = None" in src
    assert "await authorize_assignment_access(" in src
    assert 'query["assignment_id"] = assignment_id' in src
    assert "DVD_CONTENT_ASSIGNMENT_REQUIRED" in src
    assert "db.content_entries.find(" in src
    assert "filter_visible_content_entries(" in src
    assert "get_mantenedora_scope(current_user, request)" in src


def test_frontend_pdf_propagates_assignment_id():
    src = LEARNING_OBJECTS_PAGE.read_text(encoding="utf-8")
    assert "new URLSearchParams(window.location.search).get('assignment_id')" in src
    assert "params.append('assignment_id', assignmentId)" in src


def test_frontend_bridge_is_assignment_contextual_and_canonical():
    src = FRONTEND_BRIDGE.read_text(encoding="utf-8")
    assert "assignment_id" in src
    assert "'/content-entries'" in src
    assert "if (!assignmentId || !isLearningObjectsUrl" in src
    assert "__contentDvdList" in src
    assert "change_note" in src


def test_legacy_save_semantics_become_publish_or_versioned_correction():
    bridge = FRONTEND_BRIDGE.read_text(encoding="utf-8")
    canonical = CONTENT_ENTRIES_ROUTER.read_text(encoding="utf-8")
    assert "__contentDvdAutoPublish = true" in bridge
    assert "/publish`" in bridge
    assert "/correct`" in bridge
    assert "current.status === 'published' || current.status === 'corrected'" in bridge
    assert "number_of_classes: Optional[int]" in canonical
    assert 'set_fields["number_of_classes"] = payload.number_of_classes' in canonical


def test_learning_objects_page_installs_bridge_through_existing_prefill_hook():
    src = PREFILL_HOOK.read_text(encoding="utf-8")
    assert "@/services/contentDvdBridge" in src


def test_active_dvd_content_button_is_enabled_and_assignment_aware():
    src = DASHBOARD.read_text(encoding="utf-8")
    assert "open-content-disabled" not in src
    assert "data-testid={`open-content-${diary.assignment_id}`}" in src
    assert "buildDiaryActionUrl('/professor/objetos-conhecimento', actionContext)" in src
    assert "assignmentId: diary.assignment_id" in src
