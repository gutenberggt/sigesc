import { Search, X, BookOpen, User, Lock } from 'lucide-react';
import {
  GradeInput,
  ConceitoSelect,
  StatusBadge,
  formatGrade,
  valorParaConceito,
  usaAvaliacaoConceitual,
  isAnosIniciaisConceitual,
  CONCEITOS_ANOS_INICIAIS,
  CONCEITOS_EDUCACAO_INFANTIL,
} from './gradeHelpers';
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
    canEdit, canEditField, updateStudentGrade,
    loading,
  } = useGrades();

  const isLocked = (grade, field) => (
    (grade?.dvd_locked_fields || []).includes(field)
    || (grade?.dvd_read_only_fields || []).includes(field)
  );

  const fieldCanEdit = (grade, field, bim) => (
    canEdit && canEditField(bim) && !isLocked(grade, field)
  );

  const lockedTitle = (grade, field) => {
    if ((grade?.dvd_read_only_fields || []).includes(field)) {
      return 'Histórico anterior ao Diário por Vínculo — somente leitura.';
    }
    if ((grade?.dvd_locked_fields || []).includes(field)) {
      return 'Campo pertencente a outro vínculo docente — somente leitura.';
    }
    return '';
  };

  const renderBimField = (grade, field, bim) => {
    const conceptual = usaAvaliacaoConceitual(grade.grade_level, grade.education_level);
    const disabled = !fieldCanEdit(grade, field, bim);
    const control = conceptual ? (
      <ConceitoSelect
        value={grade[field]}
        onChange={(v) => updateStudentGrade(grade.id, grade.course_id, field, v)}
        disabled={disabled}
        gradeLevel={grade.grade_level}
      />
    ) : (
      <GradeInput
        value={grade[field]}
        onChange={(v) => updateStudentGrade(grade.id, grade.course_id, field, v)}
        disabled={disabled}
      />
    );
    return (
      <div className="flex items-center justify-center gap-1" title={lockedTitle(grade, field)}>
        {control}
        {isLocked(grade, field) && <Lock size={12} className="text-amber-600 shrink-0" />}
      </div>
    );
  };

  return (
    <div className="space-y-6" data-testid="grades-aluno-tab">
      <div className="flex flex-wrap items-end gap-4">
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

      {selectedStudent && studentGrades && (
        <div className="space-y-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 bg-blue-200 rounded-full flex items-center justify-center">
                <User className="text-blue-600" size={24} />
              </div>
              <div>
                <h3 className="font-semibold text-lg text-gray-900">{studentGrades.student.full_name}</h3>
                <p className="text-sm text-gray-600">
                  Matrícula: {studentGrades.student.enrollment_number} | CPF: {studentGrades.student.cpf || '-'}
                </p>
                <p className="text-xs text-blue-700 mt-1">
                  Exibindo somente componentes dos vínculos avaliativos autorizados.
                </p>
              </div>
            </div>
          </div>

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
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B1</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B2</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-blue-600 uppercase bg-blue-50">Rec. 1º</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B3</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B4</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-blue-600 uppercase bg-blue-50">Rec. 2º</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Média/Conceito</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {studentGrades.grades.map((grade) => {
                    const conceptual = usaAvaliacaoConceitual(grade.grade_level, grade.education_level);
                    const anosIniciais = isAnosIniciaisConceitual(grade.grade_level);
                    const conceptMap = anosIniciais
                      ? CONCEITOS_ANOS_INICIAIS
                      : CONCEITOS_EDUCACAO_INFANTIL;
                    const finalConcept = conceptual
                      ? valorParaConceito(grade.final_average, grade.grade_level)
                      : null;
                    return (
                      <tr key={`${grade.class_id}:${grade.course_id}`} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-900">
                          <div>{grade.course_name}</div>
                          {grade.class_name && <div className="text-xs text-gray-500">{grade.class_name}</div>}
                          {grade.legacy_history && (
                            <span className="inline-flex mt-1 items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 text-[11px]">
                              <Lock size={10} /> Histórico read-only
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">{renderBimField(grade, 'b1', 1)}</td>
                        <td className="px-4 py-3 text-center">{renderBimField(grade, 'b2', 2)}</td>
                        <td className="px-4 py-3 text-center bg-blue-50">
                          {conceptual ? '-' : (
                            <div className="flex items-center justify-center gap-1" title={lockedTitle(grade, 'rec_s1')}>
                              <GradeInput
                                value={grade.rec_s1}
                                onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'rec_s1', v)}
                                disabled={!fieldCanEdit(grade, 'rec_s1', 2)}
                                placeholder="-"
                              />
                              {isLocked(grade, 'rec_s1') && <Lock size={12} className="text-amber-600" />}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">{renderBimField(grade, 'b3', 3)}</td>
                        <td className="px-4 py-3 text-center">{renderBimField(grade, 'b4', 4)}</td>
                        <td className="px-4 py-3 text-center bg-blue-50">
                          {conceptual ? '-' : (
                            <div className="flex items-center justify-center gap-1" title={lockedTitle(grade, 'rec_s2')}>
                              <GradeInput
                                value={grade.rec_s2}
                                onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'rec_s2', v)}
                                disabled={!fieldCanEdit(grade, 'rec_s2', 4)}
                                placeholder="-"
                              />
                              {isLocked(grade, 'rec_s2') && <Lock size={12} className="text-amber-600" />}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {conceptual ? (
                            <span className={`font-bold ${conceptMap[finalConcept]?.cor || 'text-gray-400'}`}>
                              {grade.final_average !== null ? finalConcept : '-'}
                            </span>
                          ) : (
                            <span className={`font-bold ${
                              grade.final_average !== null
                                ? grade.final_average >= 5 ? 'text-green-600' : 'text-red-600'
                                : 'text-gray-400'
                            }`}>
                              {grade.final_average !== null ? formatGrade(grade.final_average) : '-'}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <StatusBadge status={grade.status} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500 bg-gray-50 rounded-lg">
              <BookOpen size={48} className="mx-auto mb-4 text-gray-300" />
              <p>Nenhuma nota autorizada para este estudante</p>
            </div>
          )}
        </div>
      )}

      {!selectedStudent && (
        <div className="text-center py-12 text-gray-500">
          <User size={48} className="mx-auto mb-4 text-gray-300" />
          <p>Busque um estudante das suas turmas pelo nome ou CPF para visualizar suas notas</p>
        </div>
      )}
    </div>
  );
};

export default AlunoTab;
