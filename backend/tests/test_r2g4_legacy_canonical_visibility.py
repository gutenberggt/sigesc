from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "frontend/src/services/contentLegacyCanonicalVisibilityBridge.js"
PREFILL = ROOT / "frontend/src/hooks/useDiaryPrefill.js"


def _bridge() -> str:
    return BRIDGE.read_text(encoding="utf-8")


def test_bridge_is_registered_after_existing_content_resolvers():
    source = PREFILL.read_text(encoding="utf-8")
    marker = "import '@/services/contentLegacyCanonicalVisibilityBridge';"
    assert marker in source
    assert source.index(marker) > source.index("import '@/services/contentPartialCutoverResolver';")


def test_component_specific_legacy_list_is_augmented_from_canonical_read_only():
    source = _bridge()
    assert "__legacyCanonicalVisibilityList" in source
    assert "componentId = params.course_id || params.component_id || null" in source
    assert "axios.get(canonicalRoot" in source
    assert "__skipContentDvdBridge: true" in source
    assert ".filter((item) => !item?.assignment_id)" in source
    assert "filterByLegacyWindow" in source
    assert "mergeLegacyAndCanonical" in source


def test_dvd_rewrite_keeps_precedence_over_legacy_visibility_fallback():
    source = _bridge()
    assert "finalUrl.includes('/learning-objects')" in source
    assert "if (config.__legacyCanonicalVisibilityList" in source
    assert "&& finalUrl.includes('/learning-objects')" in source


def test_check_date_sees_assignmentless_canonical_record():
    source = _bridge()
    assert "__legacyCanonicalVisibilityCheckDate" in source
    assert "if (response.data?.has_record) return response" in source
    assert "response.data = { has_record: true, record: canonical[0] }" in source


def test_visibility_read_path_does_not_mutate_or_migrate_content():
    source = _bridge()
    start = source.index("const loadCanonicalLegacyMode")
    end = source.index("// Axios executa request interceptors", start)
    read_block = source[start:end]
    assert "axios.get(" in read_block
    assert "axios.post(" not in read_block
    assert "axios.put(" not in read_block
    assert "axios.delete(" not in read_block
    assert "learning_objects.insert" not in source
    assert "content_entries.insert" not in source
    assert "save_content_canonical" not in source


def test_canonical_record_get_stays_on_canonical_endpoint_after_list_merge():
    source = _bridge()
    assert "canonicalCache" in source
    assert "canonicalCache.get(id)" in source
    assert "config.url = `${canonicalRoot(url)}/${encodeURIComponent(id)}`" in source
    assert "__legacyCanonicalRecord" in source


def test_explicit_edit_and_delete_never_fall_back_to_learning_objects():
    source = _bridge()
    assert "if (method === 'put')" in source
    assert "config.url = canonicalRoot(url)" in source
    assert "assignment_id: null" in source
    assert "teacher_id: current.teacher_id || null" in source
    assert "__legacyCanonicalAutoPublish" in source
    assert "if (method === 'delete')" in source
    assert "__legacyCanonicalDelete" in source
    assert "Exclusão realizada pelo formulário histórico sobre conteúdo canônico." in source
