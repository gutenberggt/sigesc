import { Search, FileText, Users, BookOpen, Save } from 'lucide-react';
import { GradesTable } from './GradesTable';
import { useGrades } from '@/contexts/GradesContext';
import { DraftRestoreBanner } from '@/components/session/DraftRestoreBanner';

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
    gradesData,
    // Flags
    isMultiGrade, usaConceito, isAnosIniciaisConc, canEdit,
    // Handlers
    loadGradesByClass, saveGrades,
    setShowPdfModal,
    // AutoSave (P1)
    gradesDraft, restoreGradesDraft, discardGradesDraft,
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
            
            {/* Recuperação de rascunho (AutoSave P1) */}
            <DraftRestoreBanner
              draft={gradesDraft}
              onRestore={restoreGradesDraft}
              onDiscard={discardGradesDraft}
              label="notas"
            />
            
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
                  <GradesTable />
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
