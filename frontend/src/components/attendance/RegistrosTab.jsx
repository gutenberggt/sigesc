import { Calendar } from 'lucide-react';
import { useAttendance } from '@/contexts/AttendanceContext';

export const RegistrosTab = () => {
  const {
    selectedClass, isMultiAula, registrosLoading, academicYear,
    registrosBimSummary, registrosBlockedDates, registrosSabLetivos, registrosAttDates,
  } = useAttendance();

  if (!selectedClass) {
    return (
      <div className="space-y-4" data-testid="attendance-registros-tab">
        <div className="text-center py-12 text-gray-500">
          <Calendar size={48} className="mx-auto mb-4 opacity-30" />
          <p>Selecione a turma{isMultiAula ? ' e o componente curricular' : ''} para visualizar o calendário de registros</p>
        </div>
      </div>
    );
  }

  if (registrosLoading) {
    return (
      <div className="space-y-4" data-testid="attendance-registros-tab">
        <div className="text-center py-12 text-gray-500">Carregando...</div>
      </div>
    );
  }

  const bimPeriods = registrosBimSummary.map(b => ({
    start: b.period_start,
    end: b.period_end,
  }));
  const isWithinBimestre = (dateStr) => {
    if (bimPeriods.length === 0) return true;
    return bimPeriods.some(p => dateStr >= p.start && dateStr <= p.end);
  };

  const monthNames = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
  const weekDays = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'];

  return (
    <div className="space-y-4" data-testid="attendance-registros-tab">
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-700">
            Calendário de Registros — {academicYear}
          </h3>
          <div className="flex items-center gap-4 text-xs">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-200 border border-green-400"></span> Com registro</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-100 border border-red-300"></span> Não letivo</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-gray-100 border border-gray-300"></span> Sem registro</span>
          </div>
        </div>

        {registrosBimSummary.length > 0 && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
            {registrosBimSummary.map(bim => (
              <div key={bim.bimestre} className="border rounded-lg p-3 bg-white">
                <div className="text-center font-semibold text-sm text-gray-700 mb-2 border-b pb-1">
                  {bim.bimestre}º Bimestre
                </div>
                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">{bim.label_prev}:</span>
                    <span className="font-bold text-blue-600">{bim.previstos}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">{bim.label_reg}:</span>
                    <span className="font-bold text-green-600">{bim.registrados}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 12 }, (_, monthIdx) => {
            const year = academicYear;
            const firstDay = new Date(year, monthIdx, 1);
            const daysInMonth = new Date(year, monthIdx + 1, 0).getDate();
            const startingDay = firstDay.getDay();

            let diasLetivos = 0;
            for (let d = 1; d <= daysInMonth; d++) {
              const dateStr = `${year}-${String(monthIdx + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
              const dow = new Date(year, monthIdx, d).getDay();
              const isSunday = dow === 0;
              const isSaturday = dow === 6;
              const isHoliday = registrosBlockedDates.has(dateStr);
              const isSabLetivo = registrosSabLetivos.has(dateStr);
              const isOutOfYear = !isWithinBimestre(dateStr);
              if (!isSunday && !isHoliday && !isOutOfYear && (!isSaturday || isSabLetivo)) diasLetivos++;
            }

            return (
              <div key={monthIdx} className="border rounded-lg p-3 bg-white">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sm text-gray-800">{monthNames[monthIdx]}</span>
                  <span className="text-xs text-green-600 font-medium">{diasLetivos} dias letivos</span>
                </div>
                <div className="grid grid-cols-7 gap-px text-center">
                  {weekDays.map((wd, i) => (
                    <div key={i} className="text-[10px] font-medium text-gray-500 py-0.5">{wd}</div>
                  ))}
                  {Array.from({ length: startingDay }, (_, i) => (
                    <div key={`empty-${i}`} />
                  ))}
                  {Array.from({ length: daysInMonth }, (_, i) => {
                    const d = i + 1;
                    const dateStr = `${year}-${String(monthIdx + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
                    const dow = new Date(year, monthIdx, d).getDay();
                    const isSunday = dow === 0;
                    const isSaturday = dow === 6;
                    const isHoliday = registrosBlockedDates.has(dateStr);
                    const isSabLetivo = registrosSabLetivos.has(dateStr);
                    const isOutOfYear = !isWithinBimestre(dateStr);
                    const isBlocked = isSunday || isHoliday || isOutOfYear || (isSaturday && !isSabLetivo);
                    const hasRecord = registrosAttDates.has(dateStr);
                    const isToday = dateStr === new Date().toISOString().split('T')[0];

                    let bgClass = 'bg-white';
                    let textClass = 'text-gray-700';
                    if (isBlocked) {
                      bgClass = 'bg-red-100';
                      textClass = 'text-red-500 font-medium';
                    } else if (hasRecord) {
                      bgClass = 'bg-green-200';
                      textClass = 'text-green-800 font-medium';
                    }

                    return (
                      <div
                        key={d}
                        className={`text-[11px] py-0.5 rounded ${bgClass} ${textClass} ${isToday ? 'ring-1 ring-blue-500' : ''}`}
                        title={isBlocked ? (isHoliday ? 'Feriado / Recesso' : 'Dia não letivo') : hasRecord ? 'Frequência registrada' : ''}
                      >
                        {d}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default RegistrosTab;
