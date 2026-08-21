import axios from 'axios';

const COPY_ERROR_PREFIX = 'CONTENT_COPY_';
const COPY_AMBIGUOUS_CODE = 'DVD_CONTENT_ASSIGNMENT_AMBIGUOUS';
const CONTENT_ERROR_PREFIXES = ['CONTENT_', 'DVD_CONTENT_', 'SOURCE_'];

const isStructuredDetail = (detail) => (
  detail !== null && typeof detail === 'object'
);

const isContentRoute = (url = '') => (
  url.includes('/copy-to-class') ||
  url.includes('/content-entries') ||
  url.includes('/learning-objects')
);

const isContentCopyError = (error, detail) => {
  const code = String(detail?.code || error?.response?.data?.code || '');
  const url = String(error?.config?.url || '');

  return (
    isContentRoute(url) ||
    code.startsWith(COPY_ERROR_PREFIX) ||
    code === COPY_AMBIGUOUS_CODE ||
    CONTENT_ERROR_PREFIXES.some((prefix) => code.startsWith(prefix))
  );
};

const detailMessage = (detail) => {
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          return String(item.message || item.msg || item.detail || item.error || JSON.stringify(item));
        }
        return String(item ?? '');
      })
      .filter(Boolean)
      .join(' | ');
  }

  if (detail && typeof detail === 'object') {
    return String(
      detail.message ||
      detail.msg ||
      detail.detail ||
      detail.error ||
      detail.code ||
      JSON.stringify(detail)
    );
  }

  return String(detail || '');
};

export const normalizeContentCopyError = (error) => {
  const data = error?.response?.data;
  const detail = data?.detail;

  if (!isStructuredDetail(detail) || !isContentCopyError(error, detail)) {
    return error;
  }

  const code = String(
    (!Array.isArray(detail) && detail?.code) ||
    data?.code ||
    ''
  );
  const message = detailMessage(detail) || code || error?.message || 'Erro ao copiar registro';

  error.response.data = {
    ...data,
    detail: message,
    error_code: code || null,
    technical_detail: detail,
  };
  error.message = message;

  return error;
};

// Primeira barreira: normaliza respostas HTTP que já chegam como erro estruturado.
// Uma segunda barreira é registrada depois do contentDvdBridge para capturar também
// erros produzidos por operações internas do bridge (ex.: publicação após cópia).
axios.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(normalizeContentCopyError(error)),
);
