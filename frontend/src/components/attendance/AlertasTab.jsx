import { AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAttendance } from '@/contexts/AttendanceContext';

export const AlertasTab = () => {
  const {
    schools, selectedSchool, setSelectedSchool, loadAlerts, loading, alertsData,
    dvdMode, dvdDiary, dvdContext,
  } = useAttendance();

  const documentary = dvdMode && (
    dvdContext?.attendance_purpose === 'pdf_only'
    || dvdDiary?.capabilities?.attendance_purpose === 'pdf_only'
  );

  if (documentary) {
    return (
      <div className="space-y-4" data-testid="attendance-alertas-tab">
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 flex items-start gap-3 text-amber-900">
          <Info size={20} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold">Registro documental não gera alertas de frequência</p>
            <p className="mt-1 text-sm">
              O componente integrador é opcional e não oficial. Suas marcações não geram faltas,
              infrequência, Busca Ativa, Bolsa Família ou qualquer alerta acadêmico.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="attendance-alertas-tab">
      {dvdMode && (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-4 flex items-start gap-3 text-indigo-900">
          <Info size={20} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold">Alertas do seu Diário por Vínculo</p>
            <p className="mt-1 text-sm">
              Esta visão considera somente a frequência oficial da turma acessível pelo seu vínculo,
              incluindo o histórico legado compatível quando o vínculo veio do cutover. Dados de outros
              vínculos docentes não são expostos.
            </p>
          </div>
        </div>
      )}

      <div className="flex gap-4">
        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">Filtrar por Escola</label>
          <select
            value={selectedSchool}
            onChange={(e) => setSelectedSchool(e.target.value)}
            disabled={dvdMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg disabled:bg-gray-100"
            data-testid="alertas-school-select"
          >
            {!dvdMode && <option value="">Todas as escolas</option>}
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
          <div className={`${alertsData.total_alerts > 0 ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'} border rounded-lg p-4 mb-4`}>
            <div className={`flex items-center gap-2 ${alertsData.total_alerts > 0 ? 'text-red-700' : 'text-green-700'}`}>
              {alertsData.total_alerts > 0 ? <AlertTriangle size={20} /> : <CheckCircle size={20} />}
              <span className="font-semibold">
                {alertsData.total_alerts} estudante(s) com frequência abaixo de 75%
              </span>
            </div>
          </div>

          {alertsData.alerts.length > 0 ? (
            <div className="bg-white border rounded-lg overflow-hidden">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Estudante</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Turma</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Faltas</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">% Frequência</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {alertsData.alerts.map((alert, idx) => (
                    <tr key={`${alert.student_id || idx}-${idx}`} className="hover:bg-gray-50">
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
              <p>Nenhum estudante com frequência abaixo de 75%</p>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-12 text-gray-500">
          <AlertTriangle size={48} className="mx-auto mb-4 opacity-30" />
          <p>Clique em "Buscar Alertas" para ver estudantes com baixa frequência</p>
        </div>
      )}
    </div>
  );
};

export default AlertasTab;
