import { FileText, FileDown, AlertTriangle, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAttendance } from '@/contexts/AttendanceContext';

export const RelatoriosTab = () => {
  const {
    schools, selectedSchool, setSelectedSchool,
    classes, selectedClass, setSelectedClass,
    selectedBimestre, setSelectedBimestre,
    isAnosFinaisOrEja, courses,
    reportCourseId, setReportCourseId, setClassReport,
    loading, classReport, loadClassReport, generateBimestrePdf,
    dvdMode, dvdDiary, dvdContext, dvdError, dvdOnline,
  } = useAttendance();

  const documentary = dvdContext?.attendance_purpose === 'pdf_only'
    || dvdDiary?.capabilities?.attendance_purpose === 'pdf_only';
  const requiresLegacyCourse = !dvdMode && isAnosFinaisOrEja;
  const reportBlocked = dvdMode && (!dvdOnline || !!dvdError);
  const reportUnit = classReport?.report_type === 'sessoes'
    ? 'sessões'
    : classReport?.report_type === 'aulas'
      ? 'aulas'
      : 'dias';

  return (
    <div className="space-y-4" data-testid="attendance-relatorios-tab">
      {dvdMode && documentary && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 flex items-start gap-2">
          <Info size={18} className="mt-0.5 shrink-0" />
          <span>
            Este relatório pertence ao registro documental do componente integrador. Percentuais e marcações exibidos são descritivos deste diário e não produzem falta, infrequência ou efeito acadêmico oficial.
          </span>
        </div>
      )}

      {dvdMode && dvdError && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {dvdError}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
          <select
            value={selectedSchool}
            onChange={(e) => setSelectedSchool(e.target.value)}
            disabled={dvdMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg disabled:bg-gray-100"
          >
            <option value="">Selecione a escola</option>
            {schools.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
          <select
            value={selectedClass}
            onChange={(e) => setSelectedClass(e.target.value)}
            disabled={!selectedSchool || dvdMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg disabled:bg-gray-100"
          >
            <option value="">Selecione a turma</option>
            {classes.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Bimestre</label>
          <select
            value={selectedBimestre}
            onChange={(e) => setSelectedBimestre(Number(e.target.value))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          >
            <option value={1}>1º Bimestre</option>
            <option value={2}>2º Bimestre</option>
            <option value={3}>3º Bimestre</option>
            <option value={4}>4º Bimestre</option>
          </select>
        </div>

        {(requiresLegacyCourse || (dvdMode && dvdDiary?.component_id)) && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Componente Curricular {requiresLegacyCourse && <span className="text-red-500">*</span>}
            </label>
            <select
              value={dvdMode ? (dvdDiary?.component_id || '') : reportCourseId}
              onChange={(e) => {
                setReportCourseId(e.target.value);
                setClassReport(null);
              }}
              disabled={dvdMode}
              className={`w-full px-3 py-2 border rounded-lg disabled:bg-gray-100 ${requiresLegacyCourse && !reportCourseId ? 'border-orange-300' : 'border-gray-300'}`}
              data-testid="report-course-select"
            >
              <option value="">Selecione o componente</option>
              {(dvdMode && dvdDiary?.component_id
                ? [{ id: dvdDiary.component_id, name: dvdDiary.component_name || 'Componente do vínculo' }]
                : courses
              ).map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
        )}

        <div className="flex items-end gap-2">
          <Button
            onClick={() => loadClassReport()}
            disabled={reportBlocked || !selectedClass || (requiresLegacyCourse && !reportCourseId)}
          >
            <FileText size={18} className="mr-2" />
            Ver na Tela
          </Button>
          <Button
            onClick={generateBimestrePdf}
            disabled={reportBlocked || !selectedClass || (requiresLegacyCourse && !reportCourseId)}
            variant="outline"
            className="border-green-500 text-green-600 hover:bg-green-50"
          >
            <FileDown size={18} className="mr-2" />
            Gerar PDF
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      ) : classReport ? (
        <div className="bg-white border rounded-lg overflow-hidden">
          <div className="p-4 bg-gray-50 border-b">
            <h3 className="font-semibold">{classReport.class?.name}</h3>
            <p className="text-sm text-gray-500">
              {(classReport.course_id || dvdDiary?.component_id) && (
                <span className="font-medium text-blue-600">
                  {dvdMode
                    ? (dvdDiary?.component_name || 'Componente do vínculo')
                    : (courses.find(c => c.id === reportCourseId)?.name || 'Componente')} •
                </span>
              )}
              {classReport.total_school_days_recorded} {reportUnit} com registro •
              {classReport.total_students} estudantes
            </p>
          </div>

          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Estudante</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Presenças</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">{documentary ? 'Ausências marcadas' : 'Faltas'}</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Justificadas</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Atestado</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">% {documentary ? 'Registros P/J/AM' : 'Frequência'}</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {classReport.students.map(student => (
                <tr key={student.student_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{student.student_name}</td>
                  <td className="px-4 py-3 text-center text-green-600">{student.present}</td>
                  <td className={`px-4 py-3 text-center ${documentary ? 'text-slate-600' : 'text-red-600'}`}>{student.absent}</td>
                  <td className="px-4 py-3 text-center text-yellow-600">{student.justified}</td>
                  <td className="px-4 py-3 text-center text-blue-600">{student.medical || 0}</td>
                  <td className="px-4 py-3 text-center font-bold">
                    <span className={documentary ? 'text-slate-700' : (student.attendance_percentage >= 75 ? 'text-green-600' : 'text-red-600')}>
                      {student.attendance_percentage}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    {student.status === 'documental' ? (
                      <span className="px-2 py-1 bg-amber-100 text-amber-800 rounded-full text-xs">Documental</span>
                    ) : student.status === 'regular' ? (
                      <span className="px-2 py-1 bg-green-100 text-green-700 rounded-full text-xs">Regular</span>
                    ) : (
                      <span className="px-2 py-1 bg-red-100 text-red-700 rounded-full text-xs flex items-center gap-1 justify-center">
                        <AlertTriangle size={12} />
                        Alerta
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-12 text-gray-500">
          <FileText size={48} className="mx-auto mb-4 opacity-30" />
          <p>{dvdMode ? 'Selecione o bimestre e gere o relatório deste vínculo' : 'Selecione uma turma para gerar o relatório'}</p>
        </div>
      )}
    </div>
  );
};

export default RelatoriosTab;
