import React from 'react';
import { Lock } from 'lucide-react';
import {
  DependencyBadge,
  DependencyDividerRow,
  shouldShowDependencyDivider,
} from '@/features/dependency';
import { hasRole } from '@/utils/permissions';
import {
  GradeInput,
  ConceitoSelect,
  StatusBadge,
  formatGrade,
  valorParaConceito,
  CONCEITOS_ANOS_INICIAIS,
  CONCEITOS_EDUCACAO_INFANTIL,
} from './gradeHelpers';
import { useGrades } from '@/contexts/GradesContext';

export const GradesTable = () => {
  const {
    gradesData, currentGradeLevel,
    usaConceito, isAnosIniciaisConc,
    canEditField, canEditStudentGrade,
    isStudentBlockedForProfessor, getBlockedMessage,
    updateLocalGrade,
    user,
  } = useGrades();

  return (
<table className="min-w-full divide-y divide-gray-200">
  <thead className="bg-gray-50">
    <tr>
      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Aluno</th>
      <th className={`px-4 py-3 text-center text-xs font-medium uppercase ${!canEditField(1) ? 'bg-red-50 text-red-500' : 'text-gray-500'}`}>
        {usaConceito ? '1º Bim' : 'B1 (×2)'}
        {!canEditField(1) && <Lock className="inline w-3 h-3 ml-1" />}
      </th>
      <th className={`px-4 py-3 text-center text-xs font-medium uppercase ${!canEditField(2) ? 'bg-red-50 text-red-500' : 'text-gray-500'}`}>
        {usaConceito ? '2º Bim' : 'B2 (×3)'}
        {!canEditField(2) && <Lock className="inline w-3 h-3 ml-1" />}
      </th>
      {!usaConceito && (
        <th className="px-4 py-3 text-center text-xs font-medium text-blue-600 uppercase bg-blue-50">Rec. 1º</th>
      )}
      <th className={`px-4 py-3 text-center text-xs font-medium uppercase ${!canEditField(3) ? 'bg-red-50 text-red-500' : 'text-gray-500'}`}>
        {usaConceito ? '3º Bim' : 'B3 (×2)'}
        {!canEditField(3) && <Lock className="inline w-3 h-3 ml-1" />}
      </th>
      <th className={`px-4 py-3 text-center text-xs font-medium uppercase ${!canEditField(4) ? 'bg-red-50 text-red-500' : 'text-gray-500'}`}>
        {usaConceito ? '4º Bim' : 'B4 (×3)'}
        {!canEditField(4) && <Lock className="inline w-3 h-3 ml-1" />}
      </th>
      {!usaConceito && (
        <th className="px-4 py-3 text-center text-xs font-medium text-blue-600 uppercase bg-blue-50">Rec. 2º</th>
      )}
      <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
        {usaConceito ? 'Conceito' : 'Média'}
      </th>
      <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
    </tr>
  </thead>
  <tbody className="bg-white divide-y divide-gray-200" data-testid="grades-tbody">
    {gradesData.map((item, index) => {
      const isBlocked = isStudentBlockedForProfessor(item.student);
      const blockedMessage = getBlockedMessage(item.student);
      const hasActionLabel = !!item.student.action_label;
      const hasAnyBlocking = isBlocked || hasActionLabel || 
        (item.student.blocked_before_enrollment && item.student.blocked_before_enrollment.length > 0) ||
        (item.student.blocked_after_action && item.student.blocked_after_action.length > 0);

      // Fase 2 — Dependência de Estudos (cf. DIARY_API_CONTRACT.md §17)
      const isDependency = !!item.student.is_dependency;
      const showDependencyDivider = shouldShowDependencyDivider(gradesData, index);

      // Helper: verifica se um bimestre específico está bloqueado para este aluno
      const canEditBim = (bim) => canEditStudentGrade(item.student, bim, item.grade);
      // Feb 2026: nota migrada da turma origem
      const isMigratedGrade = !!item.grade?.migrated_from_class_id;
      
      // Tooltip para campos bloqueados por data de matrícula
      const getBlockTooltip = (bim) => {
        if (isMigratedGrade && !hasRole(user, ['admin', 'admin_teste', 'super_admin', 'gerente', 'secretario'])) {
          return 'Nota migrada da turma de origem — apenas secretário, gerente ou super administrador podem editar';
        }
        if (item.student.blocked_after_action && item.student.blocked_after_action.includes(bim)) {
          return `${item.student.action_label || 'Movimentado'} - bimestre bloqueado`;
        }
        if (item.student.blocked_before_enrollment && item.student.blocked_before_enrollment.includes(bim)) {
          const isAdminOrSecretary = hasRole(user, ['admin', 'admin_teste', 'secretario']);
          if (!isAdminOrSecretary) {
            return `Aluno matriculado após este bimestre (${item.student.enrollment_date || ''})`;
          }
        }
        return '';
      };
      
      return (
      <React.Fragment key={item.student.id}>
        {showDependencyDivider && (
          <DependencyDividerRow colSpan={usaConceito ? 7 : 9} />
        )}
      <tr
        data-testid={isDependency ? `grades-row-dep-${item.student.id}` : `grades-row-${item.student.id}`}
        className={`hover:bg-gray-50 ${hasAnyBlocking ? 'bg-gray-50' : ''} ${isDependency ? 'bg-amber-50/30' : ''}`}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <div>
              <div className="text-sm font-medium text-gray-900">
                {item.student.full_name}
                {hasActionLabel && (
                  <span className="ml-2 inline-flex items-center px-2 py-0.5 bg-orange-100 text-orange-700 text-xs font-medium rounded-full">
                    ({item.student.action_label})
                  </span>
                )}
                {isMigratedGrade && (
                  <span
                    className="ml-2 inline-flex items-center px-2 py-0.5 bg-amber-100 text-amber-700 text-xs font-medium rounded-full"
                    title="Notas migradas da turma de origem"
                    data-testid={`migrated-badge-${item.student.id}`}
                  >
                    Migrado
                  </span>
                )}
                {isDependency && (
                  <DependencyBadge
                    student={item.student}
                    originAcademicYear={item.student.origin_academic_year}
                    className="ml-2"
                  />
                )}
              </div>
              <div className="text-xs text-gray-500">
                {item.student.enrollment_number}
                {item.student.enrollment_date && (
                  <span className="ml-2 text-gray-400">
                    Matr: {item.student.enrollment_date.split('-').reverse().join('/')}
                  </span>
                )}
              </div>
            </div>
            {isBlocked && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-200 text-gray-600 text-xs font-medium rounded-full" title={blockedMessage}>
                <Lock size={10} />
              </span>
            )}
          </div>
        </td>
        <td className={`px-4 py-3 text-center ${!canEditBim(1) ? 'bg-red-50/50' : ''}`} title={getBlockTooltip(1)}>
          {usaConceito ? (
            <ConceitoSelect
              value={item.grade.b1}
              onChange={(v) => updateLocalGrade(index, 'b1', v)}
              disabled={!canEditBim(1)}
              gradeLevel={currentGradeLevel}
            />
          ) : (
            <GradeInput
              value={item.grade.b1}
              onChange={(v) => updateLocalGrade(index, 'b1', v)}
              disabled={!canEditBim(1)}
            />
          )}
        </td>
        <td className={`px-4 py-3 text-center ${!canEditBim(2) ? 'bg-red-50/50' : ''}`} title={getBlockTooltip(2)}>
          {usaConceito ? (
            <ConceitoSelect
              value={item.grade.b2}
              onChange={(v) => updateLocalGrade(index, 'b2', v)}
              disabled={!canEditBim(2)}
              gradeLevel={currentGradeLevel}
            />
          ) : (
            <GradeInput
              value={item.grade.b2}
              onChange={(v) => updateLocalGrade(index, 'b2', v)}
              disabled={!canEditBim(2)}
            />
          )}
        </td>
        {!usaConceito && (
          <td className="px-4 py-3 text-center bg-blue-50">
            <GradeInput
              value={item.grade.rec_s1}
              onChange={(v) => updateLocalGrade(index, 'rec_s1', v)}
              disabled={!canEditBim(1) && !canEditBim(2)}
              placeholder="-"
            />
          </td>
        )}
        <td className={`px-4 py-3 text-center ${!canEditBim(3) ? 'bg-red-50/50' : ''}`} title={getBlockTooltip(3)}>
          {usaConceito ? (
            <ConceitoSelect
              value={item.grade.b3}
              onChange={(v) => updateLocalGrade(index, 'b3', v)}
              disabled={!canEditBim(3)}
              gradeLevel={currentGradeLevel}
            />
          ) : (
            <GradeInput
              value={item.grade.b3}
              onChange={(v) => updateLocalGrade(index, 'b3', v)}
              disabled={!canEditBim(3)}
            />
          )}
        </td>
        <td className={`px-4 py-3 text-center ${!canEditBim(4) ? 'bg-red-50/50' : ''}`} title={getBlockTooltip(4)}>
          {usaConceito ? (
            <ConceitoSelect
              value={item.grade.b4}
              onChange={(v) => updateLocalGrade(index, 'b4', v)}
              disabled={!canEditBim(4)}
              gradeLevel={currentGradeLevel}
            />
          ) : (
            <GradeInput
              value={item.grade.b4}
              onChange={(v) => updateLocalGrade(index, 'b4', v)}
              disabled={!canEditBim(4)}
            />
          )}
        </td>
        {!usaConceito && (
          <td className="px-4 py-3 text-center bg-blue-50">
            <GradeInput
              value={item.grade.rec_s2}
              onChange={(v) => updateLocalGrade(index, 'rec_s2', v)}
              disabled={!canEditBim(3) && !canEditBim(4)}
              placeholder="-"
            />
          </td>
        )}
        <td className="px-4 py-3 text-center">
          {usaConceito ? (
            <span className={`font-bold ${
              isAnosIniciaisConc 
                ? (CONCEITOS_ANOS_INICIAIS[valorParaConceito(item.grade.final_average, currentGradeLevel)]?.cor || 'text-gray-400')
                : (CONCEITOS_EDUCACAO_INFANTIL[valorParaConceito(item.grade.final_average, currentGradeLevel)]?.cor || 'text-gray-400')
            }`}>
              {item.grade.final_average !== null ? valorParaConceito(item.grade.final_average, currentGradeLevel) : '-'}
            </span>
          ) : (
            <span className={`font-bold ${
              item.grade.final_average !== null
                ? item.grade.final_average >= 5 ? 'text-green-600' : 'text-red-600'
                : 'text-gray-400'
            }`}>
              {item.grade.final_average !== null ? formatGrade(item.grade.final_average) : '-'}
            </span>
          )}
        </td>
        <td className="px-4 py-3 text-center">
          <StatusBadge status={item.grade.status} />
        </td>
      </tr>
      </React.Fragment>
    )})}
  </tbody>
</table>
  );
};

export default GradesTable;
