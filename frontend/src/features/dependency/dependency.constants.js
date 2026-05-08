/**
 * Constantes canônicas do subdomínio Dependência de Estudos.
 *
 * [Fev/2026] P1b — espelha o backend (`/app/backend/utils/dependency_enums.py`).
 *
 * IMPORTANTE: nunca importar strings literais ('active', 'with_dependency')
 * diretamente em outros componentes — sempre via estas constantes.
 */
export const DEPENDENCY_STATUS = Object.freeze({
  ACTIVE: 'active',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
});

export const DEPENDENCY_STATUS_VALUES = Object.freeze([
  DEPENDENCY_STATUS.ACTIVE,
  DEPENDENCY_STATUS.COMPLETED,
  DEPENDENCY_STATUS.FAILED,
  DEPENDENCY_STATUS.CANCELLED,
]);

export const DEPENDENCY_TYPE = Object.freeze({
  NONE: 'none',
  WITH_DEPENDENCY: 'with_dependency',
  DEPENDENCY_ONLY: 'dependency_only',
});

export const DEPENDENCY_TYPE_VALUES = Object.freeze([
  DEPENDENCY_TYPE.NONE,
  DEPENDENCY_TYPE.WITH_DEPENDENCY,
  DEPENDENCY_TYPE.DEPENDENCY_ONLY,
]);

/**
 * Label oficial e único — congelado pelo contrato.
 * Variantes proibidas: 'DP', 'Dep.', 'Dependente'.
 */
export const DEPENDENCY_DISPLAY_LABEL = 'Dependência';
export const DEPENDENCY_SECTION_TITLE = 'Dependência de Estudos';

/**
 * Labels legíveis por status (para UI administrativa de gerenciamento).
 */
export const DEPENDENCY_STATUS_LABELS = Object.freeze({
  active: 'Ativa',
  completed: 'Concluída',
  failed: 'Reprovado',
  cancelled: 'Cancelada',
});
