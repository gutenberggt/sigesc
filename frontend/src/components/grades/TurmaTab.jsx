import { Search, Lock, FileText, Users, BookOpen, Save } from 'lucide-react';
import {
  GradeInput,
  ConceitoSelect,
  formatGrade,
  valorParaConceito,
  CONCEITOS_ANOS_INICIAIS,
  CONCEITOS_EDUCACAO_INFANTIL,
} from './gradeHelpers';
import { useGrades } from '@/contexts/GradesContext';

export const TurmaTab = () => {
  const {
    // Base lists
    schools, filteredClasses, filteredCourses, availableSeries,
    // Selection
    selectedSchool, setSelectedSchool,
    selectedClass, setSelectedClass,
    selectedSeries, setSelectedSeries,
    selectedCourse, setSelectedCourse,
    setGradesData,
    // Loading
    loading, saving, hasChanges,
    // Data
    gradesData, currentGradeLevel,
    // Flags
    isMultiGrade, usaConceito, isAnosIniciaisConc, canEdit,
    // Handlers
    loadGradesByClass, updateLocalGrade, saveGrades,
    canEditField, canEditStudentGrade,
    isStudentBlockedForProfessor, getBlockedMessage,
    renderStatus,
    setShowPdfModal,
    user,
  } = useGrades();

  return (
    <div className="space-y-6" data-testid="grades-turma-tab">
            {/* Filtros */}
            <div className="grid grid-cols-1 md:grid-cols-[1fr_0.5fr_0.5fr_0.5fr_auto] gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
                <select
                  value={selectedSchool}
                  onChange={(e) => {
                    setSelectedSchool(e.target.value);
                    setSelectedClass('');
                    setSelectedSeries('');
                    setSelectedCourse('');
                    setGradesData([]);
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Selecione a escola</option>
                  {schools.map(school => (
                    <option key={school.id} value={school.id}>{school.name}</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
                <select
                  value={selectedClass}
                  onChange={(e) => {
                    setSelectedClass(e.target.value);
                    setSelectedSeries('');
                    setSelectedCourse('');
                    setGradesData([]);
                  }}
                  disabled={!selectedSchool}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                >
                  <option value="">Selecione a turma</option>
                  {filteredClasses.map(cls => (
                    <option key={cls.id} value={cls.id}>{cls.name}</option>
                  ))}
                </select>
              </div>
              
              {/* Dropdown de Ano/Série - apenas para turmas multisseriadas */}
              {isMultiGrade && selectedClass && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Ano/Série</label>
                  <select
                    value={selectedSeries}
                    onChange={(e) => {
                      setSelectedSeries(e.target.value);
                      setSelectedCourse('');
                      setGradesData([]);
                    }}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    data-testid="select-series-filter"
                  >
                    <option value="">Selecione o ano/série</option>
                    {availableSeries.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Componente</label>
                <select
                  value={selectedCourse}
                  onChange={(e) => {
                    setSelectedCourse(e.target.value);
                    setGradesData([]);
                  }}
                  disabled={!selectedClass || (isMultiGrade && !selectedSeries)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                >
                  <option value="">Selecione o componente</option>
                  {filteredCourses.map(course => (
                    <option key={course.id} value={course.id}>{course.name}</option>
                  ))}
                </select>
              </div>
              
              {selectedCourse && (
              <div className="flex items-end gap-2">
                <button
                  onClick={loadGradesByClass}
                  disabled={!selectedClass || !selectedCourse || loading}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  <Search size={18} />
                  Carregar Notas
                </button>
                <button
                  onClick={() => setShowPdfModal(true)}
                  disabled={!selectedClass || !selectedCourse}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  data-testid="btn-generate-grades-pdf"
                >
                  <FileText size={18} />
                  Gerar PDF
                </button>
              </div>
              )}
            </div>
            
            {/* Tabela de Notas */}
            {loading ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                <p className="mt-4 text-gray-600">Carregando notas...</p>
              </div>
            ) : gradesData.length > 0 ? (
              <div>
                {/* Indicador de avaliação conceitual */}
                {usaConceito && (
                  <div className="mb-4 p-3 bg-purple-50 border border-purple-200 rounded-lg">
                    <p className="text-sm text-purple-800">
                      {isAnosIniciaisConc ? (
                        <>
                          <strong>1º/2º Ano - Avaliação Conceitual:</strong>
                          <span className="ml-2">
                            <strong>C</strong>=Consolidado | <strong>ED</strong>=Em Desenvolvimento | <strong>ND</strong>=Não Desenvolvido
                          </span>
                        </>
                      ) : (
                        <>
                          <strong>Educação Infantil:</strong> Avaliação por conceitos. 
                          <span className="ml-2">
                            <strong>OD</strong>=Desenvolvido | <strong>DP</strong>=Parcialmente | <strong>ND</strong>=Não Desenvolvido | <strong>NT</strong>=Não Trabalhado
                          </span>
                        </>
                      )}
                    </p>
                  </div>
                )}
                <div className="overflow-x-auto">
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
                    <tbody className="bg-white divide-y divide-gray-200">
                      {gradesData.map((item, index) => {
                        const isBlocked = isStudentBlockedForProfessor(item.student);
                        const blockedMessage = getBlockedMessage(item.student);
                        const hasActionLabel = !!item.student.action_label;
                        const hasAnyBlocking = isBlocked || hasActionLabel || 
                          (item.student.blocked_before_enrollment && item.student.blocked_before_enrollment.length > 0) ||
                          (item.student.blocked_after_action && item.student.blocked_after_action.length > 0);
                        
                        // Helper: verifica se um bimestre específico está bloqueado para este aluno
                        const canEditBim = (bim) => canEditStudentGrade(item.student, bim);
                        
                        // Tooltip para campos bloqueados por data de matrícula
                        const getBlockTooltip = (bim) => {
                          if (item.student.blocked_after_action && item.student.blocked_after_action.includes(bim)) {
                            return `${item.student.action_label || 'Movimentado'} - bimestre bloqueado`;
                          }
                          if (item.student.blocked_before_enrollment && item.student.blocked_before_enrollment.includes(bim)) {
                            const isAdminOrSecretary = ['admin', 'admin_teste', 'secretario'].includes(user?.role);
                            if (!isAdminOrSecretary) {
                              return `Aluno matriculado após este bimestre (${item.student.enrollment_date || ''})`;
                            }
                          }
                          return '';
                        };
                        
                        return (
                        <tr key={item.student.id} className={`hover:bg-gray-50 ${hasAnyBlocking ? 'bg-gray-50' : ''}`}>
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
                            {renderStatus(item.grade.status, null)}
                          </td>
                        </tr>
                      )})}
                    </tbody>
                  </table>
                </div>
                
                {/* Botão Salvar */}
                {canEdit && (
                  <div className="mt-4 flex justify-end">
                    <button
                      onClick={saveGrades}
                      disabled={saving || !hasChanges}
                      className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      <Save size={18} />
                      {saving ? 'Salvando...' : 'Salvar Notas'}
                    </button>
                  </div>
                )}
              </div>
            ) : selectedClass && selectedCourse ? (
              <div className="text-center py-8 text-gray-500">
                <BookOpen size={48} className="mx-auto mb-4 text-gray-300" />
                <p>Clique em &quot;Carregar Notas&quot; para visualizar</p>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                <Users size={48} className="mx-auto mb-4 text-gray-300" />
                <p>Selecione a escola, turma e componente curricular</p>
              </div>
            )}
    </div>
  );
};

export default TurmaTab;
