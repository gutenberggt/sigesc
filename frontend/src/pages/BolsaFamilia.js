import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { schoolsAPI } from '@/services/api';
import { Home, FileText, Save, Loader2, Download, Users, Search, CheckCircle2 } from 'lucide-react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const MESES = {
  1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
  7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
};

export default function BolsaFamilia() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const token = localStorage.getItem('accessToken');
  const headers = { Authorization: `Bearer ${token}` };
  const academicYear = new Date().getFullYear();

  const [schools, setSchools] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [students, setStudents] = useState([]);
  const [municipioUf, setMunicipioUf] = useState('');
  const [canEdit, setCanEdit] = useState(false);
  const [loading, setLoading] = useState(false);
  const [savingAll, setSavingAll] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [dirty, setDirty] = useState({});
  const [monthStart, setMonthStart] = useState(2);
  const [monthEnd, setMonthEnd] = useState(new Date().getMonth() + 1 || 12);
  const [generatingPdf, setGeneratingPdf] = useState(false);

  useEffect(() => {
    schoolsAPI.getAll().then(data => {
      setSchools(data.sort((a, b) => (a.name || '').localeCompare(b.name || '')));
    }).catch(console.error);
  }, []);

  const loadStudents = useCallback(async () => {
    if (!selectedSchool) { setStudents([]); return; }
    setLoading(true);
    try {
      const res = await axios.get(`${API}/bolsa-familia/students?school_id=${selectedSchool}&academic_year=${academicYear}`, { headers });
      setStudents(res.data.students || []);
      setMunicipioUf(res.data.municipio_uf || '');
      setCanEdit(res.data.can_edit !== false);
      setDirty({});
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [selectedSchool, academicYear]);

  useEffect(() => { loadStudents(); }, [loadStudents]);

  const handleMotiveChange = (studentId, month, value) => {
    setStudents(prev => prev.map(s => {
      if (s.id !== studentId) return s;
      return {
        ...s,
        months: {
          ...s.months,
          [month]: { ...s.months[month], motive: value }
        }
      };
    }));
    // Marca esta combinação (aluno × mês) como modificada para envio em batch.
    setDirty(prev => ({ ...prev, [`${studentId}_${month}`]: true }));
  };

  const dirtyCount = Object.keys(dirty).length;

  const handleSaveAll = async () => {
    if (dirtyCount === 0) {
      setSavedAt(Date.now());
      return;
    }
    setSavingAll(true);
    // Monta o payload em batch a partir das chaves dirty.
    const items = Object.keys(dirty).map(key => {
      const [studentId, monthStr] = key.split('_');
      const stu = students.find(s => s.id === studentId);
      const motive = stu?.months?.[monthStr]?.motive || '';
      return {
        student_id: studentId,
        school_id: selectedSchool,
        month: parseInt(monthStr, 10),
        academic_year: academicYear,
        motive,
      };
    });
    try {
      await axios.put(`${API}/bolsa-familia/tracking/bulk`, { items }, { headers });
      setDirty({});
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 2500);
    } catch (e) {
      console.error(e);
    }
    setSavingAll(false);
  };

  const handleGeneratePdf = async () => {
    if (!selectedSchool) return;
    setGeneratingPdf(true);
    try {
      const res = await axios.get(
        `${API}/bolsa-familia/pdf/${selectedSchool}?academic_year=${academicYear}&month_start=${monthStart}&month_end=${monthEnd}`,
        { headers, responseType: 'blob' }
      );
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      window.open(url, '_blank');
    } catch (e) { console.error(e); }
    setGeneratingPdf(false);
  };

  const monthsRange = [];
  for (let m = monthStart; m <= monthEnd; m++) monthsRange.push(m);

  const formatDate = (d) => {
    if (!d) return '';
    try {
      const dt = new Date(d + 'T00:00:00');
      return dt.toLocaleDateString('pt-BR');
    } catch { return d; }
  };

  return (
    <Layout>
      <div className="space-y-6" data-testid="bolsa-familia-page">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/dashboard')} className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors" data-testid="bf-home-btn">
              <Home size={18} /><span>Início</span>
            </button>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <FileText size={24} /> Acompanhamento Bolsa Família
            </h1>
          </div>
          {students.length > 0 && (
            <div className="flex items-center gap-2">
              {canEdit && (
                <button
                  onClick={handleSaveAll}
                  disabled={savingAll || dirtyCount === 0}
                  className="px-4 py-2 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-2 transition-colors"
                  data-testid="bf-save-all-btn"
                >
                  {savingAll ? <Loader2 className="h-4 w-4 animate-spin" /> :
                   savedAt ? <CheckCircle2 className="h-4 w-4" /> :
                   <Save className="h-4 w-4" />}
                  {savingAll
                    ? 'Salvando...'
                    : savedAt
                      ? 'Salvo!'
                      : (dirtyCount > 0 ? `Salvar (${dirtyCount})` : 'Salvar')}
                </button>
              )}
              <button onClick={handleGeneratePdf} disabled={generatingPdf}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2 transition-colors"
                data-testid="generate-pdf-btn">
                {generatingPdf ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                Gerar PDF
              </button>
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border p-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
              <select value={selectedSchool} onChange={e => setSelectedSchool(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
                data-testid="bf-school-filter">
                <option value="">Selecione uma escola</option>
                {schools.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Mês Inicial</label>
              <select value={monthStart} onChange={e => setMonthStart(Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
                data-testid="bf-month-start">
                {Object.entries(MESES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Mês Final</label>
              <select value={monthEnd} onChange={e => setMonthEnd(Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
                data-testid="bf-month-end">
                {Object.entries(MESES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
          </div>
        </div>

        {loading && (
          <div className="bg-white rounded-xl border p-12 flex items-center justify-center">
            <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
            <span className="ml-3 text-gray-500">Carregando alunos...</span>
          </div>
        )}

        {!loading && selectedSchool && students.length === 0 && (
          <div className="bg-white rounded-xl border p-12 text-center">
            <Users className="h-12 w-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">Nenhum aluno com Bolsa Família encontrado nesta escola.</p>
            <p className="text-gray-400 text-sm mt-1">Verifique se o campo "Bolsa Família" está marcado nos dados complementares dos alunos.</p>
          </div>
        )}

        {!loading && !selectedSchool && (
          <div className="bg-white rounded-xl border p-12 text-center">
            <Search className="h-12 w-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">Selecione uma escola para visualizar os alunos beneficiários do Bolsa Família.</p>
          </div>
        )}

        {!loading && students.length > 0 && (
          <div className="space-y-4">
            <p className="text-sm text-gray-600"><strong>{students.length}</strong> aluno(s) com Bolsa Família</p>

            {students.map((student) => (
              <div key={student.id} className="bg-white rounded-xl border overflow-hidden" data-testid={`bf-student-${student.id}`}>
                <div className="bg-gray-50 px-4 py-3 border-b">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-sm">
                    <div><span className="text-gray-500">Nome:</span> <strong>{student.full_name}</strong></div>
                    <div><span className="text-gray-500">Dt. Nasc.:</span> {formatDate(student.birth_date)}</div>
                    <div><span className="text-gray-500">NIS:</span> {student.nis || 'Não informado'}</div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-sm mt-1">
                    <div><span className="text-gray-500">Responsável familiar:</span> {student.responsible || 'Não informado'}</div>
                    <div><span className="text-gray-500">Código INEP:</span> {student.inep_code || 'Não informado'}</div>
                    <div><span className="text-gray-500">Série:</span> {student.series || 'Não informada'}</div>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-100">
                        <th className="text-left px-4 py-2 text-xs font-medium text-gray-500 uppercase w-28">Mês</th>
                        <th className="text-center px-3 py-2 text-xs font-medium text-gray-500 uppercase w-24">Frequência</th>
                        <th className="text-left px-3 py-2 text-xs font-medium text-gray-500 uppercase">Motivo</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {monthsRange.map(m => {
                        const data = student.months[String(m)] || {};
                        return (
                          <tr key={m} className="hover:bg-gray-50">
                            <td className="px-4 py-2 font-medium text-gray-700">{MESES[m]}</td>
                            <td className="px-3 py-2 text-center font-medium text-gray-900">
                              {data.frequency || <span className="text-gray-300">-</span>}
                            </td>
                            <td className="px-3 py-2">
                              <input type="text" value={data.motive || ''} placeholder={canEdit ? "Informe o motivo..." : ""}
                                onChange={e => handleMotiveChange(student.id, String(m), e.target.value)}
                                disabled={!canEdit}
                                className="w-full border rounded px-2 py-1 text-sm disabled:bg-gray-50 disabled:text-gray-500"
                                data-testid={`bf-motive-${student.id}-${m}`} />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
