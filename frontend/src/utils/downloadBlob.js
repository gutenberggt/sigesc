/**
 * Faz o download de um PDF (ou qualquer blob) diretamente para o dispositivo
 * do usuário, sem abrir aba intermediária.
 *
 * Padrão:
 *   1. Faz fetch com headers autenticados.
 *   2. Lê resposta como blob.
 *   3. Cria <a download> programaticamente e dispara click.
 *   4. Revoga o objectURL após pequena espera (libera memória).
 *
 * @param {string} url Endpoint absoluto (ex.: `${BACKEND_URL}/api/...`)
 * @param {string} filename Nome sugerido do arquivo (extensão incluída)
 * @param {object} [headers={}] Headers extras (Authorization, X-Mantenedora-Id, etc.)
 */
export async function downloadBlob(url, filename, headers = {}) {
  const response = await fetch(url, { headers, credentials: 'include' });
  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json();
      detail = body?.detail || '';
    } catch (_e) {
      detail = await response.text().catch(() => '');
    }
    const err = new Error(detail || `Erro ${response.status} ao baixar documento`);
    err.status = response.status;
    throw err;
  }
  const blob = await response.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  // Necessário em alguns navegadores para garantir o trigger do download.
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Libera memória depois de o navegador ter iniciado o download.
  setTimeout(() => window.URL.revokeObjectURL(blobUrl), 1000);
}

/**
 * Resolve o filename a partir do header `Content-Disposition`, fazendo fallback
 * para o nome sugerido se o header não for retornado pelo backend.
 */
export function filenameFromContentDisposition(headerValue, fallback) {
  if (!headerValue) return fallback;
  // Tenta filename*=UTF-8'' primeiro (RFC 5987), depois filename=
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(headerValue);
  if (utf8) {
    try { return decodeURIComponent(utf8[1]); } catch (_e) { /* noop */ }
  }
  const plain = /filename=["']?([^"';]+)["']?/i.exec(headerValue);
  return plain ? plain[1] : fallback;
}

// ============================================================================
// downloadBlobWithProgress — download com PROGRESSO REAL para o ProgressModal.
//
// Modelo de 3 estados (sem números falsos):
//   preparing    → enquanto aguardamos o servidor montar o PDF (sem %)
//   transferring → bytes chegando; % REAL via Content-Length / stream
//   completed    → download disparado
//
// Reutilizável em qualquer fluxo (PDF, CSV, etc). API preparada para SSE.
// ============================================================================

import { getToken, getActiveTenantId, getCsrfToken } from '@/services/api';

const _WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function _buildAuthHeaders(method, hasJsonBody) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const tenantId = getActiveTenantId();
  if (tenantId) headers['X-Mantenedora-Id'] = tenantId;
  if (_WRITE_METHODS.has(method.toUpperCase())) {
    const csrf = getCsrfToken();
    if (csrf) headers['X-CSRF-Token'] = csrf; // fetch não passa pelo interceptor axios
    if (hasJsonBody) headers['Content-Type'] = 'application/json';
  }
  return headers;
}

/**
 * Baixa um documento exibindo progresso REAL no ProgressModal global.
 *
 * @param {object}  opts
 * @param {string}  opts.url          Endpoint absoluto.
 * @param {string}  opts.filename     Nome sugerido do arquivo.
 * @param {string} [opts.method='GET']
 * @param {object} [opts.body]        Corpo (objeto → JSON) para POST/PUT.
 * @param {object} [opts.headers]     Headers extras.
 * @param {object}  opts.progress     Controller do hook `useProgressTask()`.
 * @param {string} [opts.title]       Título do modal.
 * @param {boolean}[opts.openInNewTab=false] Abre em nova aba em vez de baixar.
 * @returns {Promise<Blob>}
 */
export async function downloadBlobWithProgress({
  url,
  filename,
  method = 'GET',
  body = null,
  headers = {},
  progress,
  title = 'Gerando documento',
  openInNewTab = false,
}) {
  const hasJsonBody = body !== null && typeof body === 'object';
  const finalHeaders = { ..._buildAuthHeaders(method, hasJsonBody), ...headers };
  const fetchBody = hasJsonBody ? JSON.stringify(body) : body;

  if (progress) progress.startTask({ title, message: 'Preparando documento...' });

  let response;
  try {
    response = await fetch(url, {
      method, headers: finalHeaders, body: fetchBody, credentials: 'include',
    });
  } catch (e) {
    if (progress) progress.failTask('Falha de conexão ao gerar o documento.');
    throw e;
  }

  if (!response.ok) {
    let detail = '';
    try {
      const obj = await response.clone().json();
      detail = obj?.detail || obj?.message || '';
      if (detail && typeof detail !== 'string') detail = JSON.stringify(detail);
    } catch (_e) {
      try { detail = await response.text(); } catch (_e2) { detail = ''; }
    }
    const msg = detail || `Erro ${response.status} ao gerar o documento`;
    if (progress) progress.failTask(msg);
    const err = new Error(msg);
    err.status = response.status;
    throw err;
  }

  const total = Number(response.headers.get('Content-Length')) || 0;
  const ctype = response.headers.get('Content-Type') || 'application/pdf';

  let blob;
  if (response.body && typeof response.body.getReader === 'function') {
    const reader = response.body.getReader();
    const chunks = [];
    let loaded = 0;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      loaded += value.length;
      if (progress) {
        progress.setTransferring({
          progress: total ? Math.min(99, Math.round((loaded / total) * 100)) : null,
          bytesLoaded: loaded,
          bytesTotal: total,
        });
      }
    }
    blob = new Blob(chunks, { type: ctype });
  } else {
    // Fallback (navegador sem streams): sem % real, mas honesto.
    blob = await response.blob();
  }

  if (progress) progress.completeTask({ message: 'Arquivo pronto. Iniciando download...' });

  const blobUrl = window.URL.createObjectURL(blob);
  if (openInNewTab) {
    window.open(blobUrl, '_blank');
  } else {
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
  setTimeout(() => window.URL.revokeObjectURL(blobUrl), openInNewTab ? 10000 : 1000);
  if (progress) setTimeout(() => progress.closeTask(), 1500);

  return blob;
}
