import axios from 'axios';

const BRIDGE_FLAG = '__sigescGradesDvdBridgeInstalled';

const getAssignmentId = () => {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search || '').get('assignment_id') || '';
};

const appendAssignmentId = (url, assignmentId) => {
  if (!url || !assignmentId) return url;
  if (/(?:[?&])assignment_id=/.test(url)) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}assignment_id=${encodeURIComponent(assignmentId)}`;
};

/**
 * Fase 5 já aceita assignment_id explícito e o revalida no backend. Este bridge
 * apenas preserva o contexto escolhido em "Meus Diários" nas chamadas da tela
 * canônica Grades.js. Fora desse contexto, o fluxo legado permanece inalterado.
 */
export const installGradesDvdAxiosBridge = () => {
  if (typeof window === 'undefined' || window[BRIDGE_FLAG]) return;
  window[BRIDGE_FLAG] = true;

  axios.interceptors.request.use((config) => {
    const assignmentId = getAssignmentId();
    if (!assignmentId || !config?.url || !config.url.includes('/grades')) {
      return config;
    }
    config.url = appendAssignmentId(config.url, assignmentId);
    return config;
  });
};

installGradesDvdAxiosBridge();
