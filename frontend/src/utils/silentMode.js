/**
 * Helpers para "Modo Silencioso" (silencia bips e notificações por X minutos).
 * Estado persistido em localStorage: { until: timestamp_ms, minutes: number }
 */

const KEY = 'silent_mode_until';
const MINUTES_KEY = 'silent_mode_minutes';

export const isSilentModeActive = () => {
  const until = parseInt(localStorage.getItem(KEY) || '0', 10);
  return until > Date.now();
};

export const getSilentUntil = () => {
  const until = parseInt(localStorage.getItem(KEY) || '0', 10);
  return until > Date.now() ? until : null;
};

export const activateSilentMode = (minutes) => {
  const until = Date.now() + minutes * 60 * 1000;
  localStorage.setItem(KEY, String(until));
  localStorage.setItem(MINUTES_KEY, String(minutes));
  // Notifica outras abas/componentes
  window.dispatchEvent(new Event('silent-mode-changed'));
  return until;
};

export const deactivateSilentMode = () => {
  localStorage.removeItem(KEY);
  localStorage.removeItem(MINUTES_KEY);
  window.dispatchEvent(new Event('silent-mode-changed'));
};

export const formatSilentUntil = (until) => {
  if (!until) return '';
  const d = new Date(until);
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
};
