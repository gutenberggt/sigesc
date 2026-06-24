/**
 * Lógica pura do SessionMonitor (P0) — testável sem React.
 */

export const WARN_5_MS = 5 * 60 * 1000;
export const WARN_1_MS = 1 * 60 * 1000;

/** Decodifica o `exp` (em ms) de um JWT. Retorna null p/ token offline/inválido. */
export function getTokenExpMs(token) {
  if (!token || token === 'offline-session-token' || !token.includes('.')) return null;
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const json = typeof atob === 'function'
      ? atob(part)
      : Buffer.from(part, 'base64').toString('binary');
    const payload = JSON.parse(json);
    return payload && payload.exp ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

/**
 * Estado da sessão a partir do tempo restante (ms) até o `exp`.
 * @returns {'active'|'warn5'|'warn1'|'expired'}
 */
export function computeSessionState(remainingMs) {
  if (remainingMs <= 0) return 'expired';
  if (remainingMs <= WARN_1_MS) return 'warn1';
  if (remainingMs <= WARN_5_MS) return 'warn5';
  return 'active';
}
