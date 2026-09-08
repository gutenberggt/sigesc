from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODAL = REPO_ROOT / "frontend" / "src" / "components" / "documents" / "DocumentGeneratorModal.js"
DOWNLOAD = REPO_ROOT / "frontend" / "src" / "utils" / "downloadBlob.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_document_generator_does_not_rebuild_auth_manually():
    source = _read(MODAL)

    assert "getToken" not in source
    assert "Authorization:" not in source
    assert "await downloadBlob(url, filenameMap[type]);" in source


def test_download_blob_injects_canonical_mt1_context_at_request_time():
    source = _read(DOWNLOAD)

    assert "import { buildFetchAuthHeaders } from '@/services/api';" in source
    assert "const finalHeaders = { ...buildFetchAuthHeaders('GET'), ...headers };" in source
    assert "fetch(url, { headers: finalHeaders, credentials: 'include' })" in source


def test_download_blob_normalizes_structured_backend_detail():
    source = _read(DOWNLOAD)

    assert "export function normalizeDownloadErrorDetail" in source
    assert "detail.message || detail.msg || detail.error || detail.detail" in source
    assert "normalizeDownloadErrorDetail(body)" in source
    assert "response.clone().json()" in source

    # Regressão do sintoma observado no modal: objeto de detail não pode chegar
    # diretamente ao construtor de Error, que o converteria em [object Object].
    assert "new Error(body" not in source
    assert "new Error(payload" not in source


def test_progressive_download_uses_the_same_error_normalizer():
    source = _read(DOWNLOAD)

    assert "detail = normalizeDownloadErrorDetail(obj);" in source
    assert "JSON.stringify(detail)" in source  # fallback explícito, nunca coerção implícita
