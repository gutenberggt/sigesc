/**
 * Toca 3 bips curtos ao receber nova mensagem.
 * Usa Web Audio API — sem arquivo externo, sem dependências.
 * Silenciosamente falha se o navegador/contexto bloquear o som
 * (ex: autoplay policy exige interação prévia do usuário).
 */
let audioCtx = null;

const getAudioContext = () => {
  if (audioCtx) return audioCtx;
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return null;
    audioCtx = new AudioContext();
    return audioCtx;
  } catch (_e) {
    return null;
  }
};

const playBeep = (ctx, startAt, frequency = 880, durationMs = 120, volume = 0.18) => {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(frequency, startAt);
  // Envelope simples para evitar clique
  gain.gain.setValueAtTime(0, startAt);
  gain.gain.linearRampToValueAtTime(volume, startAt + 0.01);
  gain.gain.linearRampToValueAtTime(volume, startAt + durationMs / 1000 - 0.02);
  gain.gain.linearRampToValueAtTime(0, startAt + durationMs / 1000);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(startAt);
  osc.stop(startAt + durationMs / 1000);
};

/**
 * Toca três bips curtos (beep-beep-beep) ~120ms cada, espaçados 160ms.
 */
export const playMessageBeeps = () => {
  const ctx = getAudioContext();
  if (!ctx) return;
  try {
    // Alguns browsers pausam o contexto até uma interação
    if (ctx.state === 'suspended') ctx.resume().catch(() => {});
    const now = ctx.currentTime;
    playBeep(ctx, now, 880);
    playBeep(ctx, now + 0.16, 880);
    playBeep(ctx, now + 0.32, 880);
  } catch (_e) {
    // Silencioso — ambiente sem suporte a áudio
  }
};

export default playMessageBeeps;
