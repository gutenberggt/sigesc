"""P0 — regressão do crash React #31 ao copiar conteúdo entre turmas."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NORMALIZER = ROOT / "frontend/src/utils/contentCopyErrorNormalizer.js"
LATE_NORMALIZER = ROOT / "frontend/src/utils/contentCopyErrorNormalizerLate.js"
PREFILL = ROOT / "frontend/src/hooks/useDiaryPrefill.js"
LEARNING_OBJECTS = ROOT / "frontend/src/pages/LearningObjects.js"


def test_content_error_normalizer_accepts_objects_and_fastapi_arrays():
    source = NORMALIZER.read_text(encoding="utf-8")
    assert "detail !== null && typeof detail === 'object'" in source
    assert "Array.isArray(detail)" in source
    assert "item.message || item.msg" in source
    assert "technical_detail: detail" in source


def test_content_routes_with_structured_detail_are_normalized_to_text():
    source = NORMALIZER.read_text(encoding="utf-8")
    assert "url.includes('/copy-to-class')" in source
    assert "url.includes('/content-entries')" in source
    assert "url.includes('/learning-objects')" in source
    assert "detail: message" in source
    assert "error.message = message" in source


def test_late_normalizer_is_registered_after_content_dvd_bridge():
    prefill = PREFILL.read_text(encoding="utf-8")
    bridge_pos = prefill.index("import '@/services/contentDvdBridge';")
    normalizer_pos = prefill.index("import '@/utils/contentCopyErrorNormalizerLate';")
    assert bridge_pos < normalizer_pos

    late = LATE_NORMALIZER.read_text(encoding="utf-8")
    assert "normalizeContentCopyError" in late
    assert "axios.interceptors.response.use" in late


def test_copy_alert_still_renders_only_the_normalized_message_slot():
    source = LEARNING_OBJECTS.read_text(encoding="utf-8")
    assert "const msg = err.response?.data?.detail || err.message || 'Erro ao copiar registro';" in source
    assert "showAlert('error', msg);" in source
    assert "{alert.message}" in source
