/**
 * BrandingContext (Sprint G4 — Mai/2026).
 *
 * Carrega branding do tenant 1x no app-level e disponibiliza para
 * QUALQUER componente via `useBranding()`. Aplica CSS variables globais
 * (`--brand-primary`, `--brand-secondary`, `--brand-primary-soft`) que
 * são consumidas por classes Tailwind `bg-brand-primary`, etc.
 *
 * Multi-tenant: ouve o evento `tenant-changed` (disparado pelo
 * TenantSwitcher) e recarrega o branding do tenant ativo.
 *
 * Fallback: se o backend não retornar branding (default=true ou erro),
 * usa o padrão SIGESC (roxo institucional) — consistente em login E
 * em todas as rotas pós-login.
 */
import { createContext, useCallback, useContext, useEffect, useState } from 'react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const CACHE_KEY = 'sigesc_branding_v1';
const CACHE_TTL_MS = 5 * 60 * 1000; // 5min

const DEFAULT_BRANDING = {
  default: true,
  name: 'SIGESC',
  slogan: 'Sistema Integrado de Gestão Escolar',
  logo_url: null,
  primary_color: '#7c3aed',
  secondary_color: '#a855f7',
};

const BrandingContext = createContext(null);

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
  } catch { /* quota exceeded */ }
}

function clearCache() {
  try { sessionStorage.removeItem(CACHE_KEY); } catch { /* ignore */ }
}

/** Converte hex → RGB lighter (10% mix com branco) para variantes "soft" */
function softColor(hex) {
  if (!hex || typeof hex !== 'string' || !hex.startsWith('#') || hex.length !== 7) {
    return null;
  }
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const mix = (c) => Math.round(c * 0.12 + 255 * 0.88);
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
}

function applyCssVars(b) {
  if (!b || typeof document === 'undefined') return;
  const root = document.documentElement;
  if (b.primary_color) {
    root.style.setProperty('--brand-primary', b.primary_color);
    const soft = softColor(b.primary_color);
    if (soft) root.style.setProperty('--brand-primary-soft', soft);
  }
  if (b.secondary_color) {
    root.style.setProperty('--brand-secondary', b.secondary_color);
  }
  if (b.name) {
    document.title = b.default ? 'SIGESC' : `${b.name} · SIGESC`;
  }
}

export const BrandingProvider = ({ children }) => {
  const [branding, setBranding] = useState(() => readCache() || DEFAULT_BRANDING);
  const [loading, setLoading] = useState(() => !readCache());

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API}/tenant/branding/public`, {
        credentials: 'include',
        headers: { Accept: 'application/json' },
      });
      const data = res.ok ? await res.json() : DEFAULT_BRANDING;
      const final = data || DEFAULT_BRANDING;
      setBranding(final);
      writeCache(final);
      applyCssVars(final);
    } catch {
      setBranding(DEFAULT_BRANDING);
      applyCssVars(DEFAULT_BRANDING);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const cached = readCache();
    if (cached) applyCssVars(cached);
    // revalida em background mesmo com cache (TTL pode estar stale)
    load();
  }, [load]);

  // Recarrega quando o super_admin troca de tenant
  useEffect(() => {
    const handler = () => {
      clearCache();
      setLoading(true);
      load();
    };
    window.addEventListener('tenant-changed', handler);
    return () => window.removeEventListener('tenant-changed', handler);
  }, [load]);

  const refresh = useCallback(() => {
    clearCache();
    load();
  }, [load]);

  return (
    <BrandingContext.Provider value={{ branding, loading, refresh }}>
      {children}
    </BrandingContext.Provider>
  );
};

export const useBranding = () => {
  const ctx = useContext(BrandingContext);
  if (!ctx) {
    // Fallback gracioso: se algum componente for usado fora do provider
    // (ex.: StoryBook ou test isolation), retorna o default.
    return { branding: DEFAULT_BRANDING, loading: false, refresh: () => {} };
  }
  return ctx;
};

export { DEFAULT_BRANDING };
export default BrandingContext;
