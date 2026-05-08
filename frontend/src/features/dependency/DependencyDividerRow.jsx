/**
 * Divisor visual para a seção de Dependência de Estudos em tabelas.
 *
 * Renderizado como uma <tr> que ocupa todas as colunas via colSpan.
 * Componente pequeno, sem estado, sem hooks.
 */
import React from 'react';
import { DEPENDENCY_SECTION_TITLE } from './dependency.constants';

export function DependencyDividerRow({ colSpan, label = DEPENDENCY_SECTION_TITLE, testId = 'dependency-divider-row' }) {
  return (
    <tr data-testid={testId} className="bg-amber-50/60" aria-label={`Início da seção ${label}`}>
      <td colSpan={colSpan} className="px-4 py-2">
        <div className="flex items-center gap-3">
          <div className="h-px bg-amber-300 flex-1" />
          <span className="text-xs font-semibold tracking-wide uppercase text-amber-700">
            {label}
          </span>
          <div className="h-px bg-amber-300 flex-1" />
        </div>
      </td>
    </tr>
  );
}

export default DependencyDividerRow;
