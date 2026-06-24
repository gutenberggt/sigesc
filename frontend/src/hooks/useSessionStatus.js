import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { getTokenExpMs, computeSessionState } from '@/utils/sessionToken';

const TICK_MS = 15 * 1000; // 15s — leve, sem chamadas ao backend

/**
 * useSessionStatus (P2) — hook READ-ONLY que deriva o estado da sessão a partir
 * do JWT em memória (AuthContext), reutilizando a lógica pura de sessionToken.js.
 * Não dispara modais nem altera a sessão (isso é responsabilidade do SessionMonitor/P0).
 *
 * @returns {{ sessionState: 'active'|'warn5'|'warn1'|'expired', remainingMs: number|null, isOfflineSession: boolean }}
 */
export function useSessionStatus() {
  const { accessToken, isOfflineSession } = useAuth();

  const compute = useCallback(() => {
    // Sessão offline não expira pelo TTL do JWT — tratada como ativa.
    if (isOfflineSession) return { sessionState: 'active', remainingMs: null };
    const expMs = getTokenExpMs(accessToken);
    if (expMs == null) return { sessionState: 'active', remainingMs: null };
    const remainingMs = expMs - Date.now();
    return { sessionState: computeSessionState(remainingMs), remainingMs };
  }, [accessToken, isOfflineSession]);

  const [status, setStatus] = useState(compute);

  useEffect(() => {
    setStatus(compute());
    const id = setInterval(() => setStatus(compute()), TICK_MS);
    return () => clearInterval(id);
  }, [compute]);

  return { ...status, isOfflineSession };
}

export default useSessionStatus;
