/**
 * Normaliza texto para busca acento-insensível.
 * "João" → "joao", "açaí" → "acai".
 *
 * Uso típico em filtros: normalizeForSearch(haystack).includes(normalizeForSearch(needle))
 */
export function normalizeForSearch(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}
