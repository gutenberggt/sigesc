"""P0 — regressão da resolução class-wide de conteúdo no Diário por Vínculo."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESOLVER = ROOT / "frontend/src/services/contentDvdClassWideResolver.js"
PREFILL = ROOT / "frontend/src/hooks/useDiaryPrefill.js"
BACKEND_SCOPE = ROOT / "backend/services/content_assignment_scope.py"


def test_backend_contract_accepts_classwide_assignment_for_component():
    source = BACKEND_SCOPE.read_text(encoding="utf-8")
    assert "return assignment_component_id is None or assignment_component_id == component_id" in source


def test_frontend_classwide_fallback_preserves_specific_precedence():
    source = RESOLVER.read_text(encoding="utf-8")
    assert "const exactCandidates = eligible.filter((item) => item?.component_id === componentId);" in source
    assert "if (exactCandidates.length > 0) return null;" in source
    assert "const classWideCandidates = eligible.filter((item) => !item?.component_id);" in source
    assert "if (classWideCandidates.length > 1)" in source
    assert "DVD_CONTENT_ASSIGNMENT_AMBIGUOUS" in source


def test_classwide_create_is_routed_to_canonical_content_entries():
    source = RESOLVER.read_text(encoding="utf-8")
    start = source.index("if (method === 'post' && /\\/learning-objects\\/?$/.test(url))")
    end = source.index("if (isCopyUrl(url) && method === 'post')", start)
    block = source[start:end]

    assert "payload.assignment_id = fallback.assignment_id" in block
    assert "payload.component_id = componentId" in block
    assert "config.url = canonicalBase(url)" in block
    assert "config.__contentDvdAutoPublish = true" in block
    assert "learning_objects" not in block


def test_classwide_copy_target_is_routed_to_canonical_copy_adapter():
    source = RESOLVER.read_text(encoding="utf-8")
    start = source.index("if (isCopyUrl(url) && method === 'post')")
    end = source.index("return config;\n});", start)
    block = source[start:end]

    assert "target_assignment_id: fallback.assignment_id" in block
    assert "source_assignment_id: sourceAssignmentId" in block
    assert "config.url = canonicalBase(url)" in block
    assert "current?.history_assignment_id" in block


def test_classwide_list_and_check_date_use_same_canonical_assignment():
    source = RESOLVER.read_text(encoding="utf-8")
    assert "config.__contentDvdCheckDate = true" in source
    assert "config.__contentDvdList = {" in source
    assert "primaryAssignmentId: fallback.assignment_id" in source
    assert "assignment_id: fallback.assignment_id" in source


def test_classwide_resolver_is_registered_after_original_bridge_and_before_late_errors():
    source = PREFILL.read_text(encoding="utf-8")
    bridge = source.index("import '@/services/contentDvdBridge';")
    resolver = source.index("import '@/services/contentDvdClassWideResolver';")
    late = source.index("import '@/utils/contentCopyErrorNormalizerLate';")
    assert bridge < resolver < late
