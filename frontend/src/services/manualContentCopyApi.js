import { apiFetch } from '@/services/api';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const BASE = `${BACKEND_URL}/api/content-entries/admin/manual-copy`;

function detailToMessage(detail) {
  if (!detail) return 'Erro inesperado no serviço de cópia.';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.message || item?.msg || item?.code || String(item))
      .join(' • ');
  }
  if (detail.message) return detail.message;
  if (detail.code) return detail.code;
  if (detail.errors) return detailToMessage(detail.errors);
  return 'Erro inesperado no serviço de cópia.';
}

async function requestJson(url, options = {}) {
  const response = await apiFetch(url, options);
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const detail = data?.detail ?? data;
    const error = new Error(detailToMessage(detail));
    error.status = response.status;
    error.detail = detail;
    throw error;
  }
  return data;
}

function query(params) {
  return new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
  ).toString();
}

export const manualContentCopyAPI = {
  options: () => requestJson(`${BASE}/options`),

  source: ({ classId, componentId, month }) =>
    requestJson(
      `${BASE}/source?${query({
        class_id: classId,
        component_id: componentId,
        month,
      })}`
    ),

  destinations: ({ classId, componentId, month }) =>
    requestJson(
      `${BASE}/destinations?${query({
        class_id: classId,
        component_id: componentId,
        month,
      })}`
    ),

  preflight: (payload) =>
    requestJson(`${BASE}/preflight`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  apply: (payload) =>
    requestJson(`${BASE}/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
};

export function manualCopyErrorMessage(error) {
  if (!error) return 'Erro inesperado no serviço de cópia.';
  if (error.detail) return detailToMessage(error.detail);
  return error.message || 'Erro inesperado no serviço de cópia.';
}
