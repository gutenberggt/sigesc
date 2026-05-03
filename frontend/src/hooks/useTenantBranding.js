/**
 * useTenantBranding — hook que resolve branding do tenant via Host header.
 *
 * - Backend resolve por `Host` (sem confiar em query params).
 * - Cache leve em sessionStorage (5 min) para evitar flicker em navegação.
 * - Aplica CSS vars globais em :root via document.documentElement.
 */
import { useEffect, useState } from 'react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const CACHE_KEY = 'sigesc_branding_v1';
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 min

const DEFAULT_BRANDING = {
  default: true,
  name: 'SIGESC',
  logo_url: null,
  primary_color: '#7c3aed',
  secondary_color: '#a855f7',
  slogan: 'Sistema Integrado de Gestão Escolar',
};

function readCache() {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Date.now() - parsed.t > CACHE_TTL_MS) return null;
    return parsed.data;
  } catch { return null; }
}

function writeCache(data) {
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ t: Date.now(), data }));
  } catch { /* quota */ }
}

function applyCssVars(b) {
  if (!b || typeof document === 'undefined') return;
  const root = document.documentElement;
  if (b.primary_color) root.style.setProperty('--brand-primary', b.primary_color);
  if (b.secondary_color) root.style.setProperty('--brand-secondary', b.secondary_color);
  if (b.name) document.title = b.name;
}

export default function useTenantBranding() {
  const cached = readCache();
  const [branding, setBranding] = useState(cached || DEFAULT_BRANDING);
  const [loading, setLoading] = useState(!cached);

  useEffect(() => {
    if (cached) {
      applyCssVars(cached);
      // refresh in background sem bloquear UI
    }
    let cancel = false;
    fetch(`${API}/tenant/branding/public`, {
      credentials: 'include',
      headers: { 'Accept': 'application/json' },
    })
      .then(r => r.ok ? r.json() : DEFAULT_BRANDING)
      .then(data => {
        if (cancel) return;
        const final = data || DEFAULT_BRANDING;
        setBranding(final);
        writeCache(final);
        applyCssVars(final);
      })
      .catch(() => {
        if (cancel) return;
        applyCssVars(DEFAULT_BRANDING);
      })
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, []);  // eslint-disable-line

  return { branding, loading };
}
