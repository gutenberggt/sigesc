import axios from 'axios';
import { browserLocalDateISO } from '@/utils/browserLocalDate';

const HEADER_TIMEZONE = 'X-SIGESC-Timezone';
const HEADER_OFFSET = 'X-SIGESC-UTC-Offset-Minutes';
const HEADER_LOCAL_DATE = 'X-SIGESC-Local-Date';

const pad2 = (value) => String(Math.abs(value)).padStart(2, '0');

export function browserLocalDateTimeISO(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';

  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const abs = Math.abs(offsetMinutes);
  const offset = `${sign}${pad2(Math.floor(abs / 60))}:${pad2(abs % 60)}`;

  return `${browserLocalDateISO(date)}T${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}${offset}`;
}

export function getClientTimeHeaders(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  const timezone = (() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    } catch {
      return '';
    }
  })();

  return {
    [HEADER_TIMEZONE]: timezone,
    [HEADER_OFFSET]: String(-date.getTimezoneOffset()),
    [HEADER_LOCAL_DATE]: browserLocalDateISO(date),
  };
}

function shouldAttachToFetch(input) {
  try {
    const raw = typeof input === 'string' ? input : input?.url;
    if (!raw) return false;
    const url = new URL(raw, window.location.origin);
    const backend = process.env.REACT_APP_BACKEND_URL;
    if (backend) {
      const backendUrl = new URL(backend, window.location.origin);
      if (url.origin === backendUrl.origin) return true;
    }
    return url.origin === window.location.origin && url.pathname.startsWith('/api');
  } catch {
    return false;
  }
}

let installed = false;

/**
 * Instala o contexto temporal global do SIGESC.
 *
 * O navegador informa apenas o FUSO/offset do dispositivo. O backend continua
 * sendo a fonte autoritativa do instante UTC; ele converte esse instante para o
 * fuso do usuário para auditoria, documentos e regras civis. Assim evitamos
 * depender do fuso do container sem confiar cegamente no relógio do cliente.
 */
export function installClientTimeContext() {
  if (installed || typeof window === 'undefined') return;
  installed = true;

  axios.interceptors.request.use((config) => {
    config.headers = config.headers || {};
    Object.assign(config.headers, getClientTimeHeaders());
    return config;
  });

  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    if (!shouldAttachToFetch(input)) return nativeFetch(input, init);

    const inherited = input instanceof Request ? input.headers : undefined;
    const headers = new Headers(inherited || {});
    if (init.headers) {
      new Headers(init.headers).forEach((value, key) => headers.set(key, value));
    }
    Object.entries(getClientTimeHeaders()).forEach(([key, value]) => {
      if (value !== '') headers.set(key, value);
    });
    return nativeFetch(input, { ...init, headers });
  };
}

export const CLIENT_TIME_HEADERS = {
  timezone: HEADER_TIMEZONE,
  offsetMinutes: HEADER_OFFSET,
  localDate: HEADER_LOCAL_DATE,
};
