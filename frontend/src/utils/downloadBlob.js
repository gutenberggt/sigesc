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
