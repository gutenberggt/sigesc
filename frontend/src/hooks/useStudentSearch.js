/**
 * useStudentSearch — Hook reutilizável para busca/autocomplete de alunos.
 *
 * Diretriz arquitetural SIGESC [Fev/2026]:
 * - Frontend NUNCA carrega lista completa de alunos para filtrar local.
 * - Toda busca server-side via /api/students/autocomplete (prefix-first indexado).
 * - Cache tenant-aware com TTL de 30s (stale-while-revalidate).
 * - Debounce 300ms + AbortController para cancelar requests obsoletos.
 *
 * Ver /app/docs/SEARCH_ARCHITECTURE.md para o padrão completo.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const DEBOUNCE_MS = 300;
const MIN_CHARS = 2;
const CACHE_TTL_MS = 30 * 1000;

// Cache em módulo (compartilhado entre instâncias do hook).
// Chave: `${tenantId}:${query}:${JSON.stringify(filters)}`
const _cache = new Map();

function buildCacheKey(tenantId, query, filters) {
  return `${tenantId || 'global'}:${query.toLowerCase().trim()}:${JSON.stringify(filters || {})}`;
}

function readCache(key) {
  const entry = _cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.ts > CACHE_TTL_MS) {
    _cache.delete(key);
    return null;
  }
  return entry.value;
}

function writeCache(key, value) {
  _cache.set(key, { ts: Date.now(), value });
  // Limpa entradas velhas se cache crescer demais (limite simples).
  if (_cache.size > 200) {
    const oldest = [..._cache.entries()].sort((a, b) => a[1].ts - b[1].ts)[0];
    if (oldest) _cache.delete(oldest[0]);
  }
}

/**
 * @param {string} query - termo de busca digitado pelo usuário
 * @param {object} options
 * @param {string} [options.tenantId] - id da mantenedora atual (para chave de cache)
 * @param {object} [options.filters] - { school_id, class_id, status }
 * @param {number} [options.limit=10] - máx. resultados (1..10)
 * @param {boolean} [options.enabled=true] - desativa o hook (ex.: enquanto modal fechada)
 *
 * @returns {{ results, loading, error, usedFallback }}
 */
export function useStudentSearch(query, options = {}) {
  const {
    tenantId = null,
    filters = {},
    limit = 10,
    enabled = true,
  } = options;

  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [usedFallback, setUsedFallback] = useState(false);

  const abortRef = useRef(null);
  const debounceRef = useRef(null);
  const filtersRef = useRef(filters);

  // Stringify filters para dep estável
  const filtersKey = JSON.stringify(filters || {});
  filtersRef.current = filters;

  const performSearch = useCallback(async (q) => {
    const trimmed = (q || '').trim();
    const currentFilters = filtersRef.current || {};
    if (!enabled || trimmed.length < MIN_CHARS) {
      setResults([]);
      setLoading(false);
      setError(null);
      setUsedFallback(false);
      return;
    }

    const cacheKey = buildCacheKey(tenantId, trimmed, currentFilters);
    const cached = readCache(cacheKey);
    if (cached) {
      setResults(cached.items);
      setUsedFallback(cached.used_fallback);
      setLoading(false);
      setError(null);
      return;
    }

    // Cancela request anterior se ainda pendente
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const params = { q: trimmed, limit };
      if (currentFilters.school_id) params.school_id = currentFilters.school_id;
      if (currentFilters.class_id) params.class_id = currentFilters.class_id;
      if (currentFilters.status) params.status = currentFilters.status;

      const { data } = await axios.get(`${API}/students/autocomplete`, {
        params,
        signal: controller.signal,
      });
      writeCache(cacheKey, data);
      setResults(data.items || []);
      setUsedFallback(!!data.used_fallback);
    } catch (err) {
      if (axios.isCancel?.(err) || err.name === 'CanceledError' || err.name === 'AbortError') {
        return; // ignorado, foi cancelado
      }
      console.error('[useStudentSearch] erro:', err);
      setError(err.response?.data?.detail || err.message || 'Erro na busca');
      setResults([]);
    } finally {
      if (abortRef.current === controller) {
        setLoading(false);
        abortRef.current = null;
      }
    }
  }, [enabled, tenantId, filtersKey, limit]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      performSearch(query);
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, performSearch]);

  // Cleanup ao desmontar
  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  return { results, loading, error, usedFallback };
}

export default useStudentSearch;
