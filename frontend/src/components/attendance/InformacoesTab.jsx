import { Loader2, Phone } from 'lucide-react';
import { useAttendance } from '@/contexts/AttendanceContext';

const formatPhone = (phone) => {
  if (!phone) return null;
  const clean = phone.replace(/\D/g, '');
  if (clean.length < 10) return null;
  const withCountry = clean.startsWith('55') ? clean : `55${clean}`;
  return withCountry;
};

export const InformacoesTab = () => {
  const {
    academicYear, schools,
    infoSchool, setInfoSchool,
    infoClass, setInfoClass,
    infoClasses, infoLoading, infoStudents,
  } = useAttendance();

  return (
    <div className="space-y-4" data-testid="attendance-informacoes-tab">
      <div className="bg-white rounded-xl border p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Ano</label>
            <select value={academicYear} disabled className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-gray-50" data-testid="info-year">
              <option value={academicYear}>{academicYear}</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
            <select value={infoSchool} onChange={e => setInfoSchool(e.target.value)} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" data-testid="info-school">
              <option value="">Selecione uma escola</option>
              {schools.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
            <select value={infoClass} onChange={e => setInfoClass(e.target.value)} disabled={!infoSchool} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm disabled:bg-gray-100" data-testid="info-class">
              <option value="">Selecione uma turma</option>
              {infoClasses.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
        </div>
      </div>

      {infoLoading && (
        <div className="bg-white rounded-xl border p-8 flex items-center justify-center">
          <Loader2 className="h-6 w-6 text-blue-500 animate-spin" />
          <span className="ml-3 text-gray-500">Carregando...</span>
        </div>
      )}

      {!infoLoading && infoClass && infoStudents.length === 0 && (
        <div className="bg-white rounded-xl border p-8 text-center text-gray-500">
          Nenhum aluno encontrado nesta turma.
        </div>
      )}

      {!infoLoading && infoStudents.length > 0 && (
        <div className="bg-white rounded-xl border overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b flex justify-between items-center">
            <h3 className="font-semibold text-gray-900">Informações dos Alunos</h3>
            <span className="text-sm text-gray-500">{infoStudents.length} aluno(s)</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-100 border-b">
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase w-10">Nº</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Nome do Aluno</th>
                  <th className="text-center px-4 py-3 text-xs font-medium text-gray-500 uppercase w-32">Data de Nasc.</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Nome da Mãe</th>
                  <th className="text-center px-4 py-3 text-xs font-medium text-gray-500 uppercase w-40">Telefone da Mãe</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {infoStudents.map((student, idx) => {
                  const phoneFormatted = formatPhone(student.mother_phone);
                  const birthDate = student.birth_date
                    ? (() => { try { return new Date(student.birth_date + 'T00:00:00').toLocaleDateString('pt-BR'); } catch { return student.birth_date; } })()
                    : '-';
                  return (
                    <tr key={student.id} className="hover:bg-gray-50" data-testid={`info-student-${student.id}`}>
                      <td className="px-4 py-3 text-gray-500">{idx + 1}</td>
                      <td className="px-4 py-3 font-medium text-gray-900">{student.full_name}</td>
                      <td className="px-4 py-3 text-center text-gray-700">{birthDate}</td>
                      <td className="px-4 py-3 text-gray-700">{student.mother_name || '-'}</td>
                      <td className="px-4 py-3 text-center">
                        {phoneFormatted ? (
                          <a
                            href={`https://wa.me/${phoneFormatted}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 px-3 py-1 bg-green-50 text-green-700 rounded-lg hover:bg-green-100 transition-colors text-sm"
                            data-testid={`info-whatsapp-${student.id}`}
                          >
                            <Phone size={14} />
                            {student.mother_phone}
                          </a>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!infoClass && !infoLoading && (
        <div className="bg-white rounded-xl border p-8 text-center text-gray-400">
          Selecione uma escola e turma para visualizar as informações dos alunos.
        </div>
      )}
    </div>
  );
};

export default InformacoesTab;
