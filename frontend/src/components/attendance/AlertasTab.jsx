import { AlertTriangle, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAttendance } from '@/contexts/AttendanceContext';

export const AlertasTab = () => {
  const { schools, selectedSchool, setSelectedSchool, loadAlerts, loading, alertsData } = useAttendance();

  return (
    <div className="space-y-4" data-testid="attendance-alertas-tab">
      <div className="flex gap-4">
        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">Filtrar por Escola</label>
          <select
            value={selectedSchool}
            onChange={(e) => setSelectedSchool(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
            data-testid="alertas-school-select"
          >
            <option value="">Todas as escolas</option>
            {schools.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
        <div className="flex items-end">
          <Button onClick={loadAlerts} data-testid="alertas-search-btn">
            <AlertTriangle size={18} className="mr-2" />
            Buscar Alertas
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      ) : alertsData ? (
        <div>
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
            <div className="flex items-center gap-2 text-red-700">
              <AlertTriangle size={20} />
              <span className="font-semibold">{alertsData.total_alerts} alunos com frequência abaixo de 75%</span>
            </div>
          </div>

          {alertsData.alerts.length > 0 ? (
            <div className="bg-white border rounded-lg overflow-hidden">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Aluno</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Turma</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Faltas</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">% Frequência</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {alertsData.alerts.map((alert, idx) => (
                    <tr key={idx} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">{alert.student_name}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">{alert.class_name}</td>
                      <td className="px-4 py-3 text-center text-red-600 font-bold">{alert.absent}</td>
                      <td className="px-4 py-3 text-center">
                        <span className="px-2 py-1 bg-red-100 text-red-700 rounded-full font-bold">
                          {alert.attendance_percentage}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-12 text-green-600">
              <CheckCircle size={48} className="mx-auto mb-4" />
              <p>Nenhum aluno com frequência abaixo de 75%</p>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-12 text-gray-500">
          <AlertTriangle size={48} className="mx-auto mb-4 opacity-30" />
          <p>Clique em "Buscar Alertas" para ver alunos com baixa frequência</p>
        </div>
      )}
    </div>
  );
};

export default AlertasTab;
