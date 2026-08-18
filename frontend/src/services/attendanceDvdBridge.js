import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const BRIDGE_FLAG = '__sigescAttendanceDvdBridgeInstalled';

export const getAttendanceDvdLocation = () => {
  if (typeof window === 'undefined') {
    return { assignmentId: null, aulaNumero: null };
  }
  const params = new URLSearchParams(window.location.search || '');
  const rawAula = params.get('aula_numero');
  return {
    assignmentId: params.get('assignment_id'),
    aulaNumero: rawAula ? Number(rawAula) : null,
  };
};

export const setAttendanceDvdAulaNumero = (aulaNumero) => {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  if (aulaNumero === null || aulaNumero === undefined || aulaNumero === '') {
    url.searchParams.delete('aula_numero');
  } else {
    url.searchParams.set('aula_numero', String(aulaNumero));
  }
  window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
};

const appendQuery = (url, key, value) => {
  if (value === null || value === undefined || value === '') return url;
  const separator = url.includes('?') ? '&' : '?';
  const encodedKey = encodeURIComponent(key);
  if (new RegExp(`(?:[?&])${encodedKey}=`).test(url)) return url;
  return `${url}${separator}${encodedKey}=${encodeURIComponent(value)}`;
};

const parsePayload = (data) => {
  if (!data) return {};
  if (typeof data === 'string') {
    try { return JSON.parse(data); } catch { return {}; }
  }
  return { ...data };
};

/**
 * Mantém `Attendance.js` como tela canônica. Quando a URL contém assignment_id,
 * somente as chamadas do domínio attendance são adaptadas para as rotas DVD.
 * Fora desse contexto, o objeto attendanceAPI continua 100% legado.
 */
export const installAttendanceDvdAxiosBridge = () => {
  if (typeof window === 'undefined' || window[BRIDGE_FLAG]) return;
  window[BRIDGE_FLAG] = true;

  axios.interceptors.request.use((config) => {
    const { assignmentId, aulaNumero } = getAttendanceDvdLocation();
    if (!assignmentId || !config?.url || !config.url.includes('/attendance')) {
      return config;
    }

    let url = config.url;
    const method = String(config.method || 'get').toLowerCase();

    // Escrita da tela histórica passa pelo endpoint DVD; class_id, teacher_id,
    // componente, modo e natureza enviados pelo browser não são fontes de verdade.
    if (method === 'post' && /\/attendance\/?(?:\?.*)?$/.test(url)) {
      url = url.replace(/\/attendance\/?(?:\?.*)?$/, '/attendance/dvd');
      const incoming = parsePayload(config.data);
      config.data = {
        assignment_id: assignmentId,
        date: incoming.date,
        records: incoming.records || [],
        period: incoming.period || 'regular',
        observations: incoming.observations || null,
        aula_numero: aulaNumero,
        expected_version: incoming.expected_version ?? incoming.base_version ?? null,
        force_overwrite: incoming.force_overwrite || false,
        change_note: incoming.change_note || null,
      };
      config.url = url;
      return config;
    }

    // Exclusão documental não existe na coleção attendance; por isso o caminho
    // explícito DVD é obrigatório para ambos os tipos de armazenamento.
    if (method === 'delete' && /\/attendance\/[^/?]+(?:\?.*)?$/.test(url) && !url.includes('/attendance/dvd/')) {
      url = url.replace('/attendance/', '/attendance/dvd/');
      config.url = url;
      return config;
    }

    // O PDF docente é sempre por assignment_id e mantém o gerador/layout atual.
    if (method === 'get' && url.includes('/attendance/pdf/bimestre/')) {
      const query = url.includes('?') ? url.substring(url.indexOf('?')) : '';
      const base = url.substring(0, url.indexOf('/attendance/pdf/bimestre/'));
      config.url = `${base}/attendance/dvd/pdf/bimestre/${encodeURIComponent(assignmentId)}${query}`;
      return config;
    }

    const assignmentAwareReads = [
      '/attendance/by-class/',
      '/attendance/report/class/',
      '/attendance/attendance-summary/',
      '/attendance/dates-with-records',
      '/attendance/bimestre-summary',
    ];
    if (method === 'get' && assignmentAwareReads.some((path) => url.includes(path))) {
      url = appendQuery(url, 'assignment_id', assignmentId);
      if (url.includes('/attendance/by-class/')) {
        url = appendQuery(url, 'aula_numero', aulaNumero);
      }
      config.url = url;
    }
    return config;
  });
};

export const fetchAttendanceDvdDiary = async (assignmentId, academicYear) => {
  const response = await axios.get(`${API}/professor/diarios`, {
    params: academicYear ? { academic_year: academicYear } : {},
  });
  const items = response.data?.items || [];
  return items.find((item) => item.assignment_id === assignmentId) || null;
};

export const fetchAttendanceDvdContext = async (assignmentId, date) => {
  const response = await axios.get(
    `${API}/attendance/dvd/context/${encodeURIComponent(assignmentId)}`,
    { params: date ? { date } : {} },
  );
  return response.data;
};

installAttendanceDvdAxiosBridge();
