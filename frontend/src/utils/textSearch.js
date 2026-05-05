/**
 * Utilitários de busca textual — accent + case insensitive.
 *
 * Padrão acordado em Mai/2026: TODA busca de nomes no SIGESC ignora
 * acentuação e diferença de caixa, tanto no termo digitado quanto no
 * conteúdo comparado.
 *
 * Backend já normaliza via campos auxiliares `nome_busca` em students,
 * staff, schools, classes etc. Este módulo replica a mesma normalização
 * para filtros LOCAIS em memória (listas pequenas, autocomplete de UI,
 * filtro de tabelas client-side).
 */

/**
 * Normaliza string para BUSCA: lowercase + sem acentos + sem cedilha + espaços colapsados.
 * Espelha `text_utils.normalize_for_search()` no backend.
 *
 * Exemplos:
 *   'Cláudio dos Reis'   → 'claudio dos reis'
 *   'CRIAÇÃO de Conteúdo' → 'criacao de conteudo'
 *   'Conceição-Maria'    → 'conceicao-maria'
 */
export function normalizeForSearch(value) {
  if (!value) return '';
  if (typeof value !== 'string') value = String(value);
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')   // remove diacríticos (acentos)
    .replace(/ç/gi, 'c')                // cedilha → c (NFD não decompõe ç em alguns casos)
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Filtra uma lista de objetos por um termo, comparando campos especificados
 * de forma accent/case-insensitive.
 *
 * @param {Array} items
 * @param {string} term
 * @param {string|string[]} fields  campos a verificar (default 'name')
 * @returns {Array}
 */
export function filterByTerm(items, term, fields = 'name') {
  const norm = normalizeForSearch(term);
  if (!norm) return items;
  const fieldList = Array.isArray(fields) ? fields : [fields];
  return items.filter(it =>
    fieldList.some(f => normalizeForSearch(it?.[f]).includes(norm))
  );
}

/**
 * Realça (highlight) ocorrências do termo no texto, ignorando acentos.
 * Útil para destacar trechos casados em listas de autocomplete.
 *
 * Retorna array de pedaços `{ text, match }` para o React renderizar
 * com <mark> nos pedaços `match=true`.
 */
export function highlightSegments(text, term) {
  if (!text) return [{ text: '', match: false }];
  if (!term) return [{ text, match: false }];
  const normText = normalizeForSearch(text);
  const normTerm = normalizeForSearch(term);
  if (!normTerm || !normText.includes(normTerm)) {
    return [{ text, match: false }];
  }
  const segments = [];
  let cursor = 0;
  let pos = normText.indexOf(normTerm, cursor);
  while (pos !== -1) {
    if (pos > cursor) segments.push({ text: text.slice(cursor, pos), match: false });
    segments.push({ text: text.slice(pos, pos + normTerm.length), match: true });
    cursor = pos + normTerm.length;
    pos = normText.indexOf(normTerm, cursor);
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), match: false });
  return segments;
}
