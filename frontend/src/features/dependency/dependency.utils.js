/**
 * Funções puras para inspecionar items vindos do contrato do Diário (v1).
 *
 * [Fev/2026] P1a — centraliza o conhecimento sobre is_dependency / dependency_id
 * para que componentes consumidores não dupliquem lógica.
 *
 * IMPORTANTE: SEM useState / useContext / useReducer aqui. Funções puras apenas.
 */
import { DEPENDENCY_STATUS, DEPENDENCY_TYPE } from './dependency.constants';

/**
 * Item canônico do diário tem:
 *   { student_id, student_name, is_dependency, dependency_id, ...}
 * Em endpoints legacy o flag pode estar em `student.is_dependency`.
 */
export function isDependencyItem(item) {
  if (!item) return false;
  if (typeof item.is_dependency === 'boolean') return item.is_dependency;
  if (item.student && typeof item.student.is_dependency === 'boolean') {
    return item.student.is_dependency;
  }
  return false;
}

export function getDependencyId(item) {
  if (!item) return null;
  if (item.dependency_id) return item.dependency_id;
  if (item.student && item.student.dependency_id) return item.student.dependency_id;
  return null;
}

/**
 * Separa uma lista em duas: regulares e dependências, preservando ordem original.
 * Útil para componentes que querem renderizar duas seções distintas.
 */
export function splitRegularAndDependency(items = []) {
  const regular = [];
  const dependency = [];
  for (const it of items) {
    if (isDependencyItem(it)) dependency.push(it);
    else regular.push(it);
  }
  return { regular, dependency };
}

/**
 * Decide se DEVE renderizar o divisor visual antes do item atual.
 * Backend já entrega regulares primeiro + deps depois (cf. contrato §17).
 */
export function shouldShowDependencyDivider(items, idx) {
  const current = items[idx];
  if (!isDependencyItem(current)) return false;
  const previous = items[idx - 1];
  return !previous || !isDependencyItem(previous);
}

/**
 * Resolve o `dependency_id` que deve ser enviado em payload de save
 * (frequência ou nota) para um item. Retorna null se for regular.
 */
export function resolveDependencyPayloadField(item) {
  if (!isDependencyItem(item)) return null;
  return getDependencyId(item);
}

/**
 * True quando o status é o canônico ativo. Defensivo contra strings ruidosas.
 */
export function isActiveStatus(value) {
  if (!value || typeof value !== 'string') return false;
  return value.trim().toLowerCase() === DEPENDENCY_STATUS.ACTIVE;
}

/**
 * True quando o tipo é 'dependency_only' (aluno cursa SOMENTE dependência).
 */
export function isDependencyOnly(student) {
  return student && student.dependency_mode === DEPENDENCY_TYPE.DEPENDENCY_ONLY;
}

/**
 * True quando o aluno está matriculado regularmente E tem dependência paralela.
 */
export function hasParallelDependency(student) {
  return student && student.dependency_mode === DEPENDENCY_TYPE.WITH_DEPENDENCY;
}
