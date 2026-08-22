const pad2 = (value) => String(value).padStart(2, '0');

/**
 * Converte um instante em data civil YYYY-MM-DD usando EXCLUSIVAMENTE o fuso
 * horário configurado no navegador/computador do usuário.
 *
 * Regra de produto SIGESC:
 * - "hoje" é sempre o dia civil percebido no dispositivo do usuário;
 * - nunca usar toISOString().slice/split para decidir a data pedagógica atual,
 *   porque toISOString() converte primeiro para UTC e pode avançar/retroceder o dia;
 * - timestamps de auditoria/API podem continuar em UTC. Esta função é apenas
 *   para datas civis (calendário, frequência, conteúdo e seletores de data).
 */
export const browserLocalDateISO = (value = new Date()) => {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';

  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
};

export const browserLocalTodayISO = () => browserLocalDateISO(new Date());

/**
 * Compatibilidade temporária com telas antigas que inicializam "hoje" via UTC.
 * Só troca o valor quando ele coincide exatamente com o dia UTC do mesmo instante
 * e difere do dia civil do navegador. Datas escolhidas explicitamente permanecem
 * intactas quando não correspondem a esse default legado.
 */
export const normalizeLegacyUtcTodayDefault = (currentDate, now = new Date()) => {
  if (!currentDate) return currentDate;

  const localToday = browserLocalDateISO(now);
  const utcToday = now.toISOString().slice(0, 10);
  return currentDate === utcToday && utcToday !== localToday ? localToday : currentDate;
};
