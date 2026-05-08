/**
 * API pública do feature Dependência de Estudos.
 *
 * IMPORTANTE: outros componentes devem importar APENAS deste index,
 * nunca dos arquivos internos. Permite refatorar internamente sem
 * quebrar consumidores.
 *
 *     import { DependencyBadge, DependencyDividerRow,
 *              isDependencyItem, splitRegularAndDependency,
 *              DEPENDENCY_STATUS, DEPENDENCY_DISPLAY_LABEL } from '@/features/dependency';
 */
export {
  DEPENDENCY_STATUS,
  DEPENDENCY_STATUS_VALUES,
  DEPENDENCY_STATUS_LABELS,
  DEPENDENCY_TYPE,
  DEPENDENCY_TYPE_VALUES,
  DEPENDENCY_DISPLAY_LABEL,
  DEPENDENCY_SECTION_TITLE,
} from './dependency.constants';

export {
  isDependencyItem,
  getDependencyId,
  splitRegularAndDependency,
  shouldShowDependencyDivider,
  resolveDependencyPayloadField,
  isActiveStatus,
  isDependencyOnly,
  hasParallelDependency,
} from './dependency.utils';

export { DependencyBadge } from './DependencyBadge';
export { DependencyDividerRow } from './DependencyDividerRow';
