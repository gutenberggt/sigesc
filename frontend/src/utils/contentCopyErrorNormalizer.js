import axios from 'axios';

const COPY_ERROR_PREFIX = 'CONTENT_COPY_';
const COPY_AMBIGUOUS_CODE = 'DVD_CONTENT_ASSIGNMENT_AMBIGUOUS';

const isStructuredDetail = (detail) => (
  detail !== null && typeof detail === 'object' && !Array.isArray(detail)
);

const isContentCopyError = (error, detail) => {
  const code = String(detail?.code || error?.response?.data?.code || '');
  const url = String(error?.config?.url || '');

  return (
    url.includes('/copy-to-class') ||
    code.startsWith(COPY_ERROR_PREFIX) ||
    code === COPY_AMBIGUOUS_CODE
  );
};

export const normalizeContentCopyError = (error) => {
  const data = error?.response?.data;
  const detail = data?.detail;

  if (!isStructuredDetail(detail) || !isContentCopyError(error, detail)) {
    return error;
  }

  const code = String(detail.code || data?.code || '');
  const message = String(
    detail.message ||
    detail.detail ||
    detail.error ||
    code ||
    error?.message ||
    'Erro ao copiar registro'
  );

  error.response.data = {
    ...data,
    detail: message,
    error_code: code || null,
    technical_detail: detail,
  };
  error.message = message;

  return error;
};

// O interceptor é deliberadamente estreito: apenas erros estruturados do fluxo
// de cópia de Objetos de Conhecimento são convertidos para mensagem textual.
// O payload técnico original permanece disponível para diagnóstico.
axios.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(normalizeContentCopyError(error)),
);
