const CLASSES_PATH = '/admin/classes';

const normalizeTriggerText = (trigger) => {
  const title = trigger?.getAttribute?.('title') || '';
  const text = trigger?.textContent || '';
  return `${title} ${text}`.trim().toLowerCase();
};

export const resolveClassPdfFilename = (trigger) => {
  const triggerText = normalizeTriggerText(trigger);

  if (triggerText.includes('boletim')) {
    return 'boletins-da-turma.pdf';
  }
  if (triggerText.includes('ficha')) {
    return 'fichas-individuais-da-turma.pdf';
  }
  return 'detalhes-da-turma.pdf';
};

/**
 * Em /admin/classes os PDFs autenticados são recebidos como Blob e, até aqui,
 * eram abertos com window.open() somente depois do await da API. Navegadores
 * podem tratar isso como popup não iniciado diretamente pelo usuário e bloquear
 * a abertura sem qualquer feedback visível.
 *
 * Convertemos apenas blob URLs desta tela em download direto. Outros usos de
 * window.open e outras telas continuam com o comportamento nativo.
 */
export const installClassPdfDirectDownload = () => {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  if (window.__sigescClassPdfDirectDownloadInstalled) return;

  const nativeOpen = window.open.bind(window);

  window.open = (url, target, features) => {
    const shouldDownload =
      typeof url === 'string' &&
      url.startsWith('blob:') &&
      window.location.pathname === CLASSES_PATH;

    if (!shouldDownload) {
      return nativeOpen(url, target, features);
    }

    const link = document.createElement('a');
    link.href = url;
    link.download = resolveClassPdfFilename(document.activeElement);
    link.rel = 'noopener';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    link.remove();

    return null;
  };

  window.__sigescClassPdfDirectDownloadInstalled = true;
};
