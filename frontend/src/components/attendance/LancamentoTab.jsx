import React from 'react';
import {
  Calendar,
  Users,
  CheckCircle,
  XCircle,
  ChevronLeft,
  ChevronRight,
  Trash2,
  Stethoscope,
} from 'lucide-react';
import {
  DependencyBadge,
  DependencyDividerRow,
  shouldShowDependencyDivider,
} from '@/features/dependency';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { EDUCATION_LEVEL_LABELS, inferEducationLevel } from '@/utils/educationLevel';
import { useAttendance } from '@/contexts/AttendanceContext';

const WEEKDAYS = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'];

const formatDate = (dateStr) => {
  if (!dateStr) return '';
  const [year, month, day] = dateStr.split('-');
  return `${day}/${month}/${year}`;
};

export const LancamentoTab = () => {
  const {
    academicYear, setAcademicYear, availableYears,
    schools, selectedSchool, setSelectedSchool,
    classes, selectedClass, setSelectedClass,
    courses, selectedCourse, setSelectedCourse,
    attendanceType, attendanceSummary, selectedClassData,
    selectedDate, setSelectedDate, dateCheck, navigateDate,
    loading, saving, attendanceData, hasChanges, canEdit,
    loadAttendance, markAll, saveAttendance,
    isMultiAula, numberOfAulas, setNumberOfAulas, setHasChanges,
    aulaStatuses, updateStudentStatus,
    vaccineStatuses,
    hasActiveCertificate, getCertificateInfo,
    isStudentBlockedForProfessor, getBlockedMessage,
    medicalCertificates, setShowDeleteModal,
  } = useAttendance();

  return (
    <div className="space-y-4" data-testid="attendance-lancamento-tab">
      {/* Filtros */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">
        <div className="lg:col-span-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">Ano Letivo</label>
          <select
            value={academicYear}
            onChange={(e) => setAcademicYear(parseInt(e.target.value))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            {availableYears.map(year => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </div>

        <div className="lg:col-span-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
          <select
            value={selectedSchool}
            onChange={(e) => setSelectedSchool(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Selecione a escola</option>
            {schools.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>

        <div className="lg:col-span-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
          <select
            value={selectedClass}
            onChange={(e) => setSelectedClass(e.target.value)}
            disabled={!selectedSchool}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">Selecione a turma</option>
            {classes.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        {attendanceType === 'by_component' && (
          <div className="lg:col-span-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Componente Curricular</label>
            <select
              value={selectedCourse}
              onChange={(e) => setSelectedCourse(e.target.value)}
              disabled={!selectedClass}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            >
              <option value="">Selecione o componente</option>
              {courses.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
        )}

        {selectedClass && attendanceSummary && (
          <div className={`${attendanceType === 'by_component' ? 'lg:col-span-2' : 'lg:col-span-3'} flex items-end`}>
            <div className="w-full grid grid-cols-3 gap-2" data-testid="attendance-summary">
              <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-center">
                <p className="text-xs font-medium text-blue-600">
                  {attendanceSummary.type === 'aulas' ? 'Previstas' : 'Previstos'}
                </p>
                <p className="text-lg font-bold text-blue-800">
                  {attendanceSummary.previstos} <span className="text-xs font-normal">{attendanceSummary.type === 'aulas' ? 'aulas' : 'dias'}</span>
                </p>
              </div>
              <div className="bg-green-50 border border-green-200 rounded-lg px-3 py-2 text-center">
                <p className="text-xs font-medium text-green-600">
                  {attendanceSummary.type === 'aulas' ? 'Registradas' : 'Registrados'}
                </p>
                <p className="text-lg font-bold text-green-800">
                  {attendanceSummary.registrados} <span className="text-xs font-normal">{attendanceSummary.type === 'aulas' ? 'aulas' : 'dias'}</span>
                </p>
              </div>
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-center">
                <p className="text-xs font-medium text-amber-600">Restantes</p>
                <p className="text-lg font-bold text-amber-800">
                  {attendanceSummary.restantes} <span className="text-xs font-normal">{attendanceSummary.type === 'aulas' ? 'aulas' : 'dias'}</span>
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Seletor de Data */}
      <div className="flex items-center gap-4 bg-gray-50 p-4 rounded-lg">
        <Button variant="outline" size="sm" onClick={() => navigateDate(-1)}>
          <ChevronLeft size={18} />
        </Button>

        <div className="flex items-center gap-2">
          <Calendar size={18} className="text-gray-500" />
          <Input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="w-40"
          />
          <span className="text-sm text-gray-600">
            {WEEKDAYS[new Date(selectedDate + 'T12:00:00').getDay()]}
          </span>
        </div>

        <Button variant="outline" size="sm" onClick={() => navigateDate(1)}>
          <ChevronRight size={18} />
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={() => setSelectedDate(new Date().toISOString().split('T')[0])}
        >
          Hoje
        </Button>

        {dateCheck && (
          <div className={`ml-auto px-3 py-1 rounded-full text-sm ${
            dateCheck.can_record ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          }`}>
            {dateCheck.message}
          </div>
        )}
      </div>

      {/* Info do tipo de frequência */}
      {selectedClassData && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-700">
          <strong>{EDUCATION_LEVEL_LABELS[inferEducationLevel(selectedClassData)] || selectedClassData.education_level || inferEducationLevel(selectedClassData)}</strong>
          {' - '}
          {attendanceType === 'daily'
            ? 'Frequência diária (uma por dia)'
            : 'Frequência por componente curricular'}
        </div>
      )}

      {/* Botão Carregar */}
      <div className="flex gap-2 flex-wrap items-center">
        <Button
          onClick={loadAttendance}
          disabled={!selectedClass || !selectedDate || (attendanceType === 'by_component' && !selectedCourse)}
        >
          Carregar Frequência
        </Button>

        {attendanceData && canEdit && (
          <>
            <Button variant="outline" onClick={() => markAll('P')}>
              <CheckCircle size={16} className="mr-1 text-green-600" />
              Todos Presentes
            </Button>
            <Button variant="outline" onClick={() => markAll('F')}>
              <XCircle size={16} className="mr-1 text-red-600" />
              Todos Ausentes
            </Button>
          </>
        )}

        {isMultiAula && attendanceData && (
          <div className="flex items-center gap-2 ml-auto bg-blue-50 border border-blue-200 rounded-lg px-3 py-1.5">
            <label className="text-sm font-medium text-blue-700 whitespace-nowrap">Nº de Aulas:</label>
            <select
              value={numberOfAulas}
              onChange={(e) => {
                const newNum = parseInt(e.target.value);
                setNumberOfAulas(newNum);
                setHasChanges(true);
              }}
              className="px-2 py-1 border border-blue-300 rounded text-sm bg-white focus:ring-2 focus:ring-blue-500"
              data-testid="num-aulas-select"
            >
              {[0, 1, 2, 3, 4, 5, 6].map(n => (
                <option key={n} value={n}>{n} {n === 1 ? 'aula' : 'aulas'}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Tabela de Frequência */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      ) : attendanceData ? (
        <div className="bg-white border rounded-lg overflow-hidden">
          <div className="p-3 bg-gray-50 border-b flex justify-between items-center">
            <div>
              <span className="font-medium">{attendanceData.class_name}</span>
              <span className="text-gray-500 ml-2">• {formatDate(attendanceData.date)}</span>
              <span className="text-gray-500 ml-2">• {attendanceData.students.length} alunos</span>
            </div>
            <div className="flex gap-4 text-sm">
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-500"></span>P = Presente</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-500"></span>F = Falta</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-yellow-500"></span>J = Justificado</span>
            </div>
          </div>

          {isMultiAula && numberOfAulas === 0 ? (
            <div className="text-center py-8 text-gray-500 bg-gray-50 rounded-lg border">
              <p className="font-medium">Nenhuma aula deste componente neste dia da semana</p>
              <p className="text-sm mt-1">Conforme o horário de aulas, não há aulas previstas para esta data.</p>
            </div>
          ) : (
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Aluno</th>
                  {isMultiAula ? (
                    Array.from({ length: numberOfAulas }, (_, i) => (
                      <th key={i} className="px-2 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                        {numberOfAulas > 1 ? `${i + 1}ª Aula` : 'Frequência'}
                      </th>
                    ))
                  ) : (
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Frequência</th>
                  )}
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200" data-testid="attendance-tbody">
                {attendanceData.students.map((student, idx) => {
                  const isDependency = !!student.is_dependency;
                  const showDependencyDivider = shouldShowDependencyDivider(attendanceData.students, idx);
                  const colSpan = 1 + (isMultiAula ? numberOfAulas : 1);
                  const hasCertificate = hasActiveCertificate(student.id);
                  const certInfo = getCertificateInfo(student.id);
                  const isBlocked = isStudentBlockedForProfessor(student);
                  const blockedMessage = getBlockedMessage(student);

                  const hasActionLabel = !!student.action_label;
                  const isBlockedByAction = hasActionLabel && student.action_date &&
                    attendanceData.date >= student.action_date.substring(0, 10);

                  const enrollDate = student.enrollment_date ? student.enrollment_date.substring(0, 10) : '';
                  const isBeforeEnrollment = enrollDate && attendanceData.date < enrollDate;

                  const enrollDateDisplay = enrollDate
                    ? `${enrollDate.substring(8, 10)}/${enrollDate.substring(5, 7)}/${enrollDate.substring(0, 4)}`
                    : '';

                  const isAnyBlock = isBlocked || isBlockedByAction || isBeforeEnrollment;

                  return (
                    <React.Fragment key={student.id}>
                    {showDependencyDivider && (
                      <DependencyDividerRow colSpan={colSpan} />
                    )}
                    <tr
                      data-testid={isDependency ? `attendance-row-dep-${student.id}` : `attendance-row-${student.id}`}
                      className={`hover:bg-gray-50 ${hasCertificate ? 'bg-red-50' : ''} ${isAnyBlock ? 'bg-gray-100' : ''} ${isDependency ? 'bg-amber-50/30' : ''}`}
                    >
                      <td className="px-4 py-3 font-medium text-gray-900">
                        <div className="flex items-center gap-2">
                          {(() => {
                            const vSt = vaccineStatuses[student.id];
                            const dotColor = vSt === 'up_to_date' ? 'bg-green-500' : vSt === 'not_up_to_date' ? 'bg-yellow-400' : 'bg-gray-300';
                            const dotTitle = vSt === 'up_to_date' ? 'Vacina em dia' : vSt === 'not_up_to_date' ? 'Vacina pendente' : 'Vacina não verificada';
                            return <span className={`inline-block w-2.5 h-2.5 rounded-full flex-shrink-0 ${dotColor}`} title={dotTitle} data-testid={`vaccine-dot-${student.id}`} />;
                          })()}
                          {student.full_name}
                          {hasActionLabel && (
                            <span className="inline-flex items-center px-2 py-0.5 bg-orange-100 text-orange-700 text-xs font-medium rounded-full">
                              ({student.action_label})
                            </span>
                          )}
                          {hasCertificate && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-red-100 text-red-700 text-xs font-medium rounded-full" title={certInfo?.period}>
                              <Stethoscope size={12} />
                              AM
                            </span>
                          )}
                          {isBlocked && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-200 text-gray-600 text-xs font-medium rounded-full" title={blockedMessage}>
                              Bloqueado
                            </span>
                          )}
                          {isDependency && (
                            <DependencyBadge
                              student={student}
                              originAcademicYear={student.origin_academic_year}
                            />
                          )}
                        </div>
                      </td>
                      {isMultiAula ? (
                        Array.from({ length: numberOfAulas }, (_, aulaIdx) => {
                          const aulaNum = aulaIdx + 1;
                          const aulaStatus = aulaStatuses[student.id]?.[aulaNum] || '';
                          return (
                            <td key={aulaIdx} className="px-2 py-3">
                              {hasCertificate ? (
                                <div className="flex justify-center">
                                  <div className="px-2 py-1 bg-red-100 text-red-700 rounded text-xs font-bold">AM</div>
                                </div>
                              ) : isAnyBlock ? (
                                <div className="flex justify-center">
                                  <div className="px-2 py-1 bg-gray-200 text-gray-500 rounded text-xs text-center leading-tight">
                                    {isBeforeEnrollment ? (
                                      <><div>A partir de</div><div>{enrollDateDisplay}</div></>
                                    ) : isBlockedByAction ? (
                                      student.action_label
                                    ) : '-'}
                                  </div>
                                </div>
                              ) : (
                                <div className="flex justify-center gap-1">
                                  {['P', 'F', 'J'].map(status => (
                                    <button
                                      key={status}
                                      onClick={() => canEdit && dateCheck?.can_record && updateStudentStatus(student.id, status, aulaNum)}
                                      disabled={!canEdit || !dateCheck?.can_record}
                                      className={`w-8 h-8 rounded-lg font-bold text-xs transition-all
                                        ${aulaStatus === status
                                          ? status === 'P' ? 'bg-green-500 text-white ring-2 ring-green-300'
                                            : status === 'F' ? 'bg-red-500 text-white ring-2 ring-red-300'
                                            : 'bg-yellow-500 text-white ring-2 ring-yellow-300'
                                          : 'bg-gray-300 text-gray-500 hover:bg-gray-400'
                                        }
                                        ${(!canEdit || !dateCheck?.can_record) ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}
                                      `}
                                    >
                                      {status}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </td>
                          );
                        })
                      ) : (
                        <td className="px-4 py-3">
                          {hasCertificate ? (
                            <div className="flex justify-center">
                              <div className="px-4 py-2 bg-red-100 text-red-700 rounded-lg font-bold text-center" title={`${certInfo?.reason}: ${certInfo?.period}`}>
                                <div className="flex items-center gap-1">
                                  <Stethoscope size={16} />
                                  <span>AM</span>
                                </div>
                                <span className="text-xs font-normal">Atestado Médico</span>
                              </div>
                            </div>
                          ) : isAnyBlock ? (
                            <div className="flex justify-center">
                              <div className="px-4 py-2 bg-gray-200 text-gray-600 rounded-lg text-center">
                                {isBeforeEnrollment ? (
                                  <>
                                    <span className="text-xs block">A partir de</span>
                                    <span className="text-sm font-medium">{enrollDateDisplay}</span>
                                  </>
                                ) : isBlockedByAction ? (
                                  <span className="text-sm">{student.action_label}</span>
                                ) : (
                                  <span className="text-sm">Edição bloqueada</span>
                                )}
                              </div>
                            </div>
                          ) : (
                            <div className="flex justify-center gap-2">
                              {['P', 'F', 'J'].map(status => (
                                <button
                                  key={status}
                                  onClick={() => canEdit && dateCheck?.can_record && updateStudentStatus(student.id, status)}
                                  disabled={!canEdit || !dateCheck?.can_record}
                                  className={`w-10 h-10 rounded-lg font-bold transition-all
                                    ${student.status === status
                                      ? status === 'P' ? 'bg-green-500 text-white ring-2 ring-green-300'
                                        : status === 'F' ? 'bg-red-500 text-white ring-2 ring-red-300'
                                        : 'bg-yellow-500 text-white ring-2 ring-yellow-300'
                                      : 'bg-gray-300 text-gray-500 hover:bg-gray-400'
                                    }
                                    ${(!canEdit || !dateCheck?.can_record) ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}
                                  `}
                                >
                                  {status}
                                </button>
                              ))}
                            </div>
                          )}
                        </td>
                      )}
                    </tr>
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          )}

          {Object.keys(medicalCertificates).length > 0 && (
            <div className="p-3 bg-red-50 border-t border-red-200 text-sm text-red-700">
              <div className="flex items-center gap-2">
                <Stethoscope size={16} />
                <span><strong>AM = Atestado Médico</strong> - Alunos com atestado médico não podem ter a frequência alterada.</span>
              </div>
            </div>
          )}

          {canEdit && dateCheck?.can_record && (
            <div className="p-4 bg-gray-50 border-t flex justify-between items-center">
              <div>
                {attendanceData.attendance_id && (
                  <Button
                    variant="outline"
                    onClick={() => setShowDeleteModal(true)}
                    className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-300"
                  >
                    <Trash2 size={16} className="mr-2" />
                    Excluir Frequência
                  </Button>
                )}
              </div>
              <Button data-testid="save-attendance-btn" onClick={saveAttendance} disabled={saving || !hasChanges}>
                {saving ? 'Salvando...' : 'Salvar Frequência'}
              </Button>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-12 text-gray-500">
          <Users size={48} className="mx-auto mb-4 opacity-30" />
          <p>Selecione os filtros e clique em "Carregar Frequência"</p>
        </div>
      )}
    </div>
  );
};

export default LancamentoTab;
