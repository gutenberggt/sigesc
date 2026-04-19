import { Search, X, BookOpen, User } from 'lucide-react';
import { GradeInput, StatusBadge, formatGrade } from './gradeHelpers';
import { useGrades } from '@/contexts/GradesContext';

export const AlunoTab = () => {
  const {
    searchName, setSearchName,
    searchCpf, setSearchCpf,
    nameInputRef, cpfInputRef,
    showNameSuggestions, setShowNameSuggestions, nameSuggestions,
    showCpfSuggestions, setShowCpfSuggestions, cpfSuggestions,
    selectedStudent,
    handleSelectStudent, handleClearSearch,
    studentGrades,
    canEdit, updateStudentGrade,
    loading,
  } = useGrades();

  return (
    <div className="space-y-6" data-testid="grades-aluno-tab">
            {/* Busca */}
            <div className="flex flex-wrap items-end gap-4">
              {/* Busca por Nome */}
              <div className="relative flex-1 min-w-[250px]" ref={nameInputRef}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  <Search size={14} className="inline mr-1" />
                  Buscar por Nome
                </label>
                <input
                  type="text"
                  value={searchName}
                  onChange={(e) => {
                    setSearchName(e.target.value);
                    setShowNameSuggestions(e.target.value.length >= 3);
                  }}
                  onFocus={() => setShowNameSuggestions(searchName.length >= 3)}
                  placeholder="Digite pelo menos 3 letras..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
                {showNameSuggestions && nameSuggestions.length > 0 && (
                  <div className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                    {nameSuggestions.map((student) => (
                      <button
                        key={student.id}
                        type="button"
                        onClick={() => handleSelectStudent(student)}
                        className="w-full px-4 py-2 text-left hover:bg-blue-50 border-b border-gray-100 last:border-b-0"
                      >
                        <div className="font-medium text-gray-900">{student.full_name}</div>
                        <div className="text-xs text-gray-500">
                          Matrícula: {student.enrollment_number} | CPF: {student.cpf || '-'}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              
              {/* Busca por CPF */}
              <div className="relative flex-1 min-w-[250px]" ref={cpfInputRef}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  <Search size={14} className="inline mr-1" />
                  Buscar por CPF
                </label>
                <input
                  type="text"
                  value={searchCpf}
                  onChange={(e) => {
                    setSearchCpf(e.target.value);
                    setShowCpfSuggestions(e.target.value.length >= 3);
                  }}
                  onFocus={() => setShowCpfSuggestions(searchCpf.length >= 3)}
                  placeholder="Digite pelo menos 3 dígitos..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
                {showCpfSuggestions && cpfSuggestions.length > 0 && (
                  <div className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                    {cpfSuggestions.map((student) => (
                      <button
                        key={student.id}
                        type="button"
                        onClick={() => handleSelectStudent(student)}
                        className="w-full px-4 py-2 text-left hover:bg-blue-50 border-b border-gray-100 last:border-b-0"
                      >
                        <div className="font-medium text-gray-900">{student.cpf}</div>
                        <div className="text-xs text-gray-500">
                          {student.full_name} | Matrícula: {student.enrollment_number}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              
              {/* Botão Limpar */}
              {selectedStudent && (
                <button
                  onClick={handleClearSearch}
                  className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 border border-gray-300"
                >
                  <X size={18} />
                  Limpar
                </button>
              )}
            </div>
            
            {/* Dados do Aluno */}
            {selectedStudent && studentGrades && (
              <div className="space-y-4">
                {/* Card do Aluno */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 bg-blue-200 rounded-full flex items-center justify-center">
                      <User className="text-blue-600" size={24} />
                    </div>
                    <div>
                      <h3 className="font-semibold text-lg text-gray-900">{studentGrades.student.full_name}</h3>
                      <p className="text-sm text-gray-600">
                        Matrícula: {studentGrades.student.enrollment_number} | 
                        CPF: {studentGrades.student.cpf || '-'}
                      </p>
                    </div>
                  </div>
                </div>
                
                {/* Tabela de Notas por Componente */}
                {loading ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                  </div>
                ) : studentGrades.grades.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200 bg-white rounded-lg overflow-hidden">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Componente</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B1 (×2)</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B2 (×3)</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-blue-600 uppercase bg-blue-50">Rec. 1º</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B3 (×2)</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B4 (×3)</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-blue-600 uppercase bg-blue-50">Rec. 2º</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Média</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200">
                        {studentGrades.grades.map((grade) => (
                          <tr key={grade.course_id} className="hover:bg-gray-50">
                            <td className="px-4 py-3 font-medium text-gray-900">{grade.course_name}</td>
                            <td className="px-4 py-3 text-center">
                              <GradeInput
                                value={grade.b1}
                                onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'b1', v)}
                                disabled={!canEdit}
                              />
                            </td>
                            <td className="px-4 py-3 text-center">
                              <GradeInput
                                value={grade.b2}
                                onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'b2', v)}
                                disabled={!canEdit}
                              />
                            </td>
                            <td className="px-4 py-3 text-center bg-blue-50">
                              <GradeInput
                                value={grade.rec_s1}
                                onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'rec_s1', v)}
                                disabled={!canEdit}
                                placeholder="-"
                              />
                            </td>
                            <td className="px-4 py-3 text-center">
                              <GradeInput
                                value={grade.b3}
                                onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'b3', v)}
                                disabled={!canEdit}
                              />
                            </td>
                            <td className="px-4 py-3 text-center">
                              <GradeInput
                                value={grade.b4}
                                onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'b4', v)}
                                disabled={!canEdit}
                              />
                            </td>
                            <td className="px-4 py-3 text-center bg-blue-50">
                              <GradeInput
                                value={grade.rec_s2}
                                onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'rec_s2', v)}
                                disabled={!canEdit}
                                placeholder="-"
                              />
                            </td>
                            <td className="px-4 py-3 text-center">
                              <span className={`font-bold ${
                                grade.final_average !== null
                                  ? grade.final_average >= 5 ? 'text-green-600' : 'text-red-600'
                                  : 'text-gray-400'
                              }`}>
                                {grade.final_average !== null ? formatGrade(grade.final_average) : '-'}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-center">
                              <StatusBadge status={grade.status} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500 bg-gray-50 rounded-lg">
                    <BookOpen size={48} className="mx-auto mb-4 text-gray-300" />
                    <p>Nenhuma nota lançada para este aluno</p>
                  </div>
                )}
              </div>
            )}
            
            {!selectedStudent && (
              <div className="text-center py-12 text-gray-500">
                <User size={48} className="mx-auto mb-4 text-gray-300" />
                <p>Busque um aluno pelo nome ou CPF para visualizar suas notas</p>
              </div>
            )}
    </div>
  );
};

export default AlunoTab;
