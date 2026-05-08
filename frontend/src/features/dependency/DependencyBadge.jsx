/**
 * Badge âmbar discreto da Dependência de Estudos.
 *
 * Não é alerta. Não é punição. Não é status crítico.
 * Pedagogicamente neutro. Visual cuidadosamente escolhido pelo owner.
 */
import React from 'react';
import { DEPENDENCY_DISPLAY_LABEL } from './dependency.constants';

export function DependencyBadge({ student, originAcademicYear, testId, className = '' }) {
  const tooltip = `Dependência de Estudos${
    originAcademicYear ? ` — origem ${originAcademicYear}` : ''
  }`;
  const finalTestId = testId || (student && student.id ? `dependency-badge-${student.id}` : 'dependency-badge');
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 bg-amber-100 text-amber-800 text-xs font-medium rounded-full ring-1 ring-amber-300 ${className}`}
      title={tooltip}
      data-testid={finalTestId}
    >
      {DEPENDENCY_DISPLAY_LABEL}
    </span>
  );
}

export default DependencyBadge;
