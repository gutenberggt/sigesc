from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "frontend/src/services/contentLegacyCanonicalVisibilityBridge.js"
POLICY = ROOT / "frontend/src/services/contentLegacyCanonicalVisibilityPolicy.js"
BEHAVIOR = ROOT / "frontend/src/services/contentLegacyCanonicalVisibilityPolicy.test.js"
PREFILL = ROOT / "frontend/src/hooks/useDiaryPrefill.js"


def _bridge() -> str:
    return BRIDGE.read_text(encoding="utf-8")


def _policy() -> str:
    return POLICY.read_text(encoding="utf-8")


def test_bridge_is_registered_after_existing_content_resolvers():
    source = PREFILL.read_text(encoding="utf-8")
    marker = "import '@/services/contentLegacyCanonicalVisibilityBridge';"
    assert marker in source
    assert source.index(marker) > source.index("import '@/services/contentPartialCutoverResolver';")


def test_component_specific_fallback_revalidates_scope_locally():
    bridge = _bridge()
    policy = _policy()
    assert "selectCanonicalVisibilityRecords" in bridge
    assert "return selectCanonicalVisibilityRecords(items, meta)" in bridge
    assert "record.class_id !== meta.classId" in policy
    assert "componentOf(record) !== meta.componentId" in policy
    assert "if (record.assignment_id) return false" in policy
    assert "if (meta.date && recordDate !== dayOf(meta.date)) return false" in policy
    assert "recordYear !== Number(meta.academicYear)" in policy
    assert "recordMonth !== Number(meta.month)" in policy


def test_dvd_rewrite_keeps_precedence_over_legacy_visibility_fallback():
    bridge = _bridge()
    policy = _policy()
    assert "shouldComposeLegacyCanonicalFallback" in bridge
    assert bridge.count("shouldComposeLegacyCanonicalFallback(finalUrl)") >= 2
    assert "url.includes('/learning-objects')" in policy
    assert "!url.includes('/content-entries')" in policy


def test_check_date_sees_only_exact_assignmentless_canonical_record():
    bridge = _bridge()
    assert "__legacyCanonicalVisibilityCheckDate" in bridge
    assert "if (response.data?.has_record) return response" in bridge
    assert "response.data = { has_record: true, record: canonical[0] }" in bridge
    assert "selectCanonicalVisibilityRecords(items, meta)" in bridge


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


def test_canonical_record_get_edit_delete_never_fall_back_to_learning_objects():
    source = _bridge()
    assert "canonicalCache.get(id)" in source
    assert "config.url = `${canonicalRoot(url)}/${encodeURIComponent(id)}`" in source
    assert "if (method === 'put')" in source
    assert "assignment_id: null" in source
    assert "teacher_id: current.teacher_id || null" in source
    assert "__legacyCanonicalAutoPublish" in source
    assert "if (method === 'delete')" in source
    assert "__legacyCanonicalDelete" in source


def test_canonical_root_is_idempotent_after_request_rewrite():
    source = _bridge()
    assert "if (value.includes('/content-entries'))" in source
    assert "value.split('/content-entries')[0]" in source


def test_behavioral_regression_explicitly_covers_historical_false_projection_risk():
    source = BEHAVIOR.read_text(encoding="utf-8")
    assert "faz aparecer somente o content_entry administrativo" in source
    assert "111/98 candidatos históricos de outros componentes" in source
    assert "um registro legado normal de maio permanece inalterado" in source
    assert "bridge DVD já reescreveu para content_entries" in source
    assert "check-date canônico só aceita a data exata" in source
    assert "legacy_id continua impedindo duplicação" in source
