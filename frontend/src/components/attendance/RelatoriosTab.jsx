import { FileText, FileDown, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';

export const RelatoriosTab = ({
  schools,
  selectedSchool,
  setSelectedSchool,
  classes,
  selectedClass,
  setSelectedClass,
  selectedBimestre,
  setSelectedBimestre,
  isAnosFinaisOrEja,
  courses,
  reportCourseId,
  setReportCourseId,
  setClassReport,
  loading,
  classReport,
  loadClassReport,
  generateBimestrePdf,
}) => {
  return (
    <div className="space-y-4" data-testid="attendance-relatorios-tab">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
          <select
            value={selectedSchool}
            onChange={(e) => setSelectedSchool(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
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
            disabled={!selectedSchool}
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

        {isAnosFinaisOrEja && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Componente Curricular <span className="text-red-500">*</span>
            </label>
            <select
              value={reportCourseId}
              onChange={(e) => {
                setReportCourseId(e.target.value);
                setClassReport(null);
              }}
              className={`w-full px-3 py-2 border rounded-lg ${!reportCourseId ? 'border-orange-300' : 'border-gray-300'}`}
              data-testid="report-course-select"
            >
              <option value="">Selecione o componente</option>
              {courses.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
        )}

        <div className="flex items-end gap-2">
          <Button onClick={() => loadClassReport()} disabled={!selectedClass || (isAnosFinaisOrEja && !reportCourseId)}>
            <FileText size={18} className="mr-2" />
            Ver na Tela
          </Button>
          <Button
            onClick={generateBimestrePdf}
            disabled={!selectedClass || (isAnosFinaisOrEja && !reportCourseId)}
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
              {classReport.course_id && reportCourseId && (
                <span className="font-medium text-blue-600">
                  {courses.find(c => c.id === reportCourseId)?.name || 'Componente'} •
                </span>
              )}
              {classReport.total_school_days_recorded} {classReport.report_type === 'aulas' ? 'aulas' : 'dias'} com frequência registrada •
              {classReport.total_students} alunos
            </p>
          </div>

          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Aluno</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Presenças</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Faltas</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Justificadas</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Atestado</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">% Frequência</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {classReport.students.map(student => (
                <tr key={student.student_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{student.student_name}</td>
                  <td className="px-4 py-3 text-center text-green-600">{student.present}</td>
                  <td className="px-4 py-3 text-center text-red-600">{student.absent}</td>
                  <td className="px-4 py-3 text-center text-yellow-600">{student.justified}</td>
                  <td className="px-4 py-3 text-center text-blue-600">{student.medical || 0}</td>
                  <td className="px-4 py-3 text-center font-bold">
                    <span className={student.attendance_percentage >= 75 ? 'text-green-600' : 'text-red-600'}>
                      {student.attendance_percentage}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    {student.status === 'regular' ? (
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
          <p>Selecione uma turma para gerar o relatório</p>
        </div>
      )}
    </div>
  );
};

export default RelatoriosTab;
