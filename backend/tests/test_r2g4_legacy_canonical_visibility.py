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
    # Se um bridge DVD anterior reescrever para /content-entries, este fallback
    # não deve compor uma segunda resposta canônica.
    assert "&& finalUrl.includes('/learning-objects')" in source


def test_check_date_sees_assignmentless_canonical_record():
    source = _bridge()
    assert "__legacyCanonicalVisibilityCheckDate" in source
    assert "if (response.data?.has_record) return response" in source
    assert "response.data = { has_record: true, record: canonical[0] }" in source


def test_visibility_bridge_does_not_write_or_migrate_content():
    source = _bridge()
    forbidden = [
        "axios.post(",
        "axios.put(",
        "axios.delete(",
        "learning_objects.insert",
        "content_entries.insert",
        "save_content_canonical",
    ]
    for marker in forbidden:
        assert marker not in source


def test_canonical_record_get_stays_on_canonical_endpoint_after_list_merge():
    source = _bridge()
    assert "canonicalCache" in source
    assert "canonicalCache.has(id)" in source
    assert "config.url = `${canonicalRoot(url)}/${encodeURIComponent(id)}`" in source
