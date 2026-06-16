import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { schoolsAPI, classesAPI } from '@/services/api';
import { Home, FileText, Save, Loader2, Download, Users, Search, CheckCircle2, AlertTriangle, Info, Stethoscope, X } from 'lucide-react';
import axios from 'axios';
import ReasonCombobox from '@/components/ReasonCombobox';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const MESES = {
  1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
  7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
};

// Limiar oficial do MEC para Bolsa Família.
const FREQUENCY_THRESHOLD_PCT = 75;

// Roles autorizadas a consolidar TODAS as escolas (visão de rede).
const ALL_SCHOOLS_ROLES = ['super_admin', 'admin', 'gerente', 'semed3'];
const ALL_SCHOOLS_VALUE = '__all__';

function parseFrequencyPct(freqStr) {
  if (!freqStr) return null;
  const m = String(freqStr).match(/([0-9]+(?:\.[0-9]+)?)/);
  return m ? parseFloat(m[1]) : null;
}

export default function BolsaFamilia() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const token = localStorage.getItem('accessToken');
  const headers = { Authorization: `Bearer ${token}` };
  const academicYear = new Date().getFullYear();

  const [schools, setSchools] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [classes, setClasses] = useState([]);
  const [selectedClass, setSelectedClass] = useState('');
  const [classesLoading, setClassesLoading] = useState(false);
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

  // Motivos MEC carregados uma única vez (cache por sessão da página).
  const [reasonGroups, setReasonGroups] = useState([]);
  const [reasonsLoading, setReasonsLoading] = useState(false);

  const canSeeAllSchools = ALL_SCHOOLS_ROLES.includes(user?.role);
  const allSchoolsMode = selectedSchool === ALL_SCHOOLS_VALUE;

  useEffect(() => {
    schoolsAPI.getAll().then(data => {
      setSchools(data.sort((a, b) => (a.name || '').localeCompare(b.name || '')));
    }).catch(console.error);
  }, []);

  useEffect(() => {
    setReasonsLoading(true);
    axios.get(`${API}/bolsa-familia/reasons/grouped`, { headers })
      .then(res => setReasonGroups(res.data.groups || []))
      .catch(err => console.error('Erro ao carregar motivos MEC:', err))
      .finally(() => setReasonsLoading(false));
  }, []);

  const reasonIndex = useMemo(() => {
    const idx = new Map();
    reasonGroups.forEach((g) => {
      (g.reasons || []).forEach((r) => {
        idx.set(r.id, { ...r, group_name: g.name });
      });
    });
    return idx;
  }, [reasonGroups]);

  const loadStudents = useCallback(async () => {
    if (!selectedSchool) { setStudents([]); return; }
    setLoading(true);
    try {
      const params = new URLSearchParams({
        academic_year: String(academicYear),
      });
      // Modo "Todas as Escolas" → omite school_id; backend agrega.
      if (selectedSchool !== ALL_SCHOOLS_VALUE) {
        params.set('school_id', selectedSchool);
        if (selectedClass) params.set('class_id', selectedClass);
      }
      const res = await axios.get(`${API}/bolsa-familia/students?${params.toString()}`, { headers });
      setStudents(res.data.students || []);
      setMunicipioUf(res.data.municipio_uf || '');
      setCanEdit(res.data.can_edit !== false);
      setDirty({});
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [selectedSchool, selectedClass, academicYear]);

  useEffect(() => { loadStudents(); }, [loadStudents]);

  // Carrega turmas quando a escola muda. Limpa filtro de turma ao trocar escola.
  // Modo "Todas as Escolas" não carrega turmas (turmas são por-escola).
  useEffect(() => {
    setSelectedClass('');
    if (!selectedSchool || selectedSchool === ALL_SCHOOLS_VALUE) {
      setClasses([]);
      return;
    }
    setClassesLoading(true);
    classesAPI.list(selectedSchool)
      .then((data) => {
        const list = Array.isArray(data) ? data : (data?.classes || []);
        const sorted = [...list].sort((a, b) =>
          (a.name || '').localeCompare(b.name || '', 'pt', { sensitivity: 'base' })
        );
        setClasses(sorted);
      })
      .catch((err) => {
        console.error('Erro ao carregar turmas:', err);
        setClasses([]);
      })
      .finally(() => setClassesLoading(false));
  }, [selectedSchool]);

  const setMonthField = (studentId, month, patch) => {
    setStudents(prev => prev.map(s => {
      if (s.id !== studentId) return s;
      return {
        ...s,
        months: {
          ...s.months,
          [month]: { ...s.months[month], ...patch }
        }
      };
    }));
    setDirty(prev => ({ ...prev, [`${studentId}_${month}`]: true }));
  };

  const handleReasonChange = (studentId, month, reasonId) => {
    setMonthField(studentId, month, { reason_id: reasonId });
  };

  const handleNotesChange = (studentId, month, notes) => {
    setMonthField(studentId, month, { notes });
  };

  const dirtyCount = Object.keys(dirty).length;

  const monthsRange = useMemo(() => {
    const arr = [];
    for (let m = monthStart; m <= monthEnd; m++) arr.push(m);
    return arr;
  }, [monthStart, monthEnd]);

  // Mini-dashboard: por aluno, dentro do intervalo selecionado.
  const studentFlags = useMemo(() => {
    return students.map((s) => {
      let belowThreshold = false;
      let missingReason = false;
      monthsRange.forEach((m) => {
        const data = s.months?.[String(m)] || {};
        const freq = parseFrequencyPct(data.frequency);
        if (freq !== null && freq < FREQUENCY_THRESHOLD_PCT) {
          belowThreshold = true;
          if (!data.reason_id) missingReason = true;
        }
      });
      return { student: s, belowThreshold, missingReason };
    });
  }, [students, monthsRange]);

  const summary = useMemo(() => ({
    total: studentFlags.length,
    below: studentFlags.filter((f) => f.belowThreshold).length,
    missing: studentFlags.filter((f) => f.missingReason).length,
  }), [studentFlags]);

  // Filtro do mini-dashboard. null | 'below' | 'missing'
  const [summaryFilter, setSummaryFilter] = useState(null);

  // Limpa filtro de resumo ao trocar escola/turma/intervalo.
  useEffect(() => { setSummaryFilter(null); }, [selectedSchool, selectedClass, monthStart, monthEnd]);

  const displayedStudents = useMemo(() => {
    if (!summaryFilter) return students;
    return studentFlags
      .filter((f) => (summaryFilter === 'below' ? f.belowThreshold : f.missingReason))
      .map((f) => f.student);
  }, [students, studentFlags, summaryFilter]);

  const handleSaveAll = async () => {
    if (dirtyCount === 0) {
      setSavedAt(Date.now());
      return;
    }
    setSavingAll(true);
    const items = Object.keys(dirty).map(key => {
      const [studentId, monthStr] = key.split('_');
      const stu = students.find(s => s.id === studentId);
      const data = stu?.months?.[monthStr] || {};
      return {
        student_id: studentId,
        school_id: selectedSchool,
        month: parseInt(monthStr, 10),
        academic_year: academicYear,
        reason_id: data.reason_id || null,
        notes: data.notes || '',
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
      const params = new URLSearchParams({
        academic_year: String(academicYear),
        month_start: String(monthStart),
        month_end: String(monthEnd),
      });
      if (selectedClass) params.set('class_id', selectedClass);
      const res = await axios.get(
        `${API}/bolsa-familia/pdf/${selectedSchool}?${params.toString()}`,
        { headers, responseType: 'blob' }
      );
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      window.open(url, '_blank');
    } catch (e) { console.error(e); }
    setGeneratingPdf(false);
  };

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
            <button
              onClick={() => navigate('/admin/bolsa-familia/busca-ativa')}
              className="hidden md:flex px-3 py-1.5 text-sm bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 items-center gap-1.5 transition-colors"
              data-testid="bf-busca-ativa-link"
            >
              <AlertTriangle size={14} />
              Busca Ativa
            </button>
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
              <button onClick={handleGeneratePdf} disabled={generatingPdf || allSchoolsMode}
                title={allSchoolsMode ? 'PDF disponível apenas para uma escola específica' : ''}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
                data-testid="generate-pdf-btn">
                {generatingPdf ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                Gerar PDF
              </button>
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border p-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
              <select value={selectedSchool} onChange={e => setSelectedSchool(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
                data-testid="bf-school-filter">
                <option value="">Selecione uma escola</option>
                {canSeeAllSchools && (
                  <option value={ALL_SCHOOLS_VALUE} data-testid="bf-school-all-option">
                    Todas as Escolas
                  </option>
                )}
                {schools.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-1">
                Turma
                {classesLoading && <Loader2 size={12} className="animate-spin text-gray-400" />}
              </label>
              <select
                value={selectedClass}
                onChange={e => setSelectedClass(e.target.value)}
                disabled={!selectedSchool || allSchoolsMode || classesLoading}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
                data-testid="bf-class-filter"
              >
                <option value="">
                  {allSchoolsMode
                    ? 'Não disponível em "Todas as Escolas"'
                    : selectedSchool
                      ? `Todas as turmas (${classes.length})`
                      : 'Selecione uma escola primeiro'}
                </option>
                {!allSchoolsMode && classes.map(c => (
                  <option key={c.id} value={c.id}>
                    {c.name}{c.grade_level ? ` — ${c.grade_level}` : ''}
                  </option>
                ))}
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
          <div className="mt-4 text-xs text-gray-600 flex items-start gap-2" data-testid="bf-policy-banner">
            <Info size={14} className="mt-0.5 flex-shrink-0 text-blue-500" />
            <span>
              <strong>Política MEC:</strong> meses com frequência ≥ {FREQUENCY_THRESHOLD_PCT}% não exigem
              motivo. Meses com frequência abaixo de {FREQUENCY_THRESHOLD_PCT}% exigem motivo oficial
              do Sistema Presença (v4.2). Observações são opcionais e complementam o motivo.
            </span>
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
            <div className="flex items-center justify-between flex-wrap gap-2">
              <p className="text-sm text-gray-600">
                <strong>{students.length}</strong> aluno(s) com Bolsa Família
                {allSchoolsMode && (
                  <span
                    className="ml-2 inline-flex items-center gap-1 text-[11px] text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-full px-2 py-0.5 font-medium"
                    data-testid="bf-all-schools-badge"
                  >
                    Visão consolidada (somente leitura)
                  </span>
                )}
              </p>
              {reasonsLoading && (
                <span className="text-xs text-gray-400 flex items-center gap-1">
                  <Loader2 size={12} className="animate-spin" /> Carregando motivos MEC...
                </span>
              )}
            </div>

            {/* Mini-dashboard executivo: chips clicáveis filtram a lista abaixo */}
            <div
              className="bg-white rounded-xl border p-3 flex flex-wrap items-center gap-2"
              data-testid="bf-summary-row"
            >
              <button
                type="button"
                onClick={() => setSummaryFilter(null)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                  summaryFilter === null
                    ? 'bg-slate-800 text-white border-slate-800'
                    : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                }`}
                data-testid="bf-summary-total"
                title="Mostrar todos"
              >
                <Users size={14} />
                <strong>{summary.total}</strong>
                <span className="opacity-80">alunos</span>
              </button>

              <span className="text-gray-300">|</span>

              <button
                type="button"
                onClick={() => setSummaryFilter(summaryFilter === 'below' ? null : 'below')}
                disabled={summary.below === 0}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                  summaryFilter === 'below'
                    ? 'bg-amber-600 text-white border-amber-600'
                    : 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100'
                }`}
                data-testid="bf-summary-below"
                title={`Alunos com ao menos 1 mês abaixo de ${FREQUENCY_THRESHOLD_PCT}%`}
              >
                <AlertTriangle size={14} />
                <strong>{summary.below}</strong>
                <span className="opacity-80">abaixo de {FREQUENCY_THRESHOLD_PCT}%</span>
              </button>

              <span className="text-gray-300">|</span>

              <button
                type="button"
                onClick={() => setSummaryFilter(summaryFilter === 'missing' ? null : 'missing')}
                disabled={summary.missing === 0}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                  summaryFilter === 'missing'
                    ? 'bg-red-600 text-white border-red-600'
                    : 'bg-red-50 text-red-700 border-red-200 hover:bg-red-100'
                }`}
                data-testid="bf-summary-missing"
                title="Alunos com ao menos 1 mês <75% sem motivo MEC informado"
              >
                <FileText size={14} />
                <strong>{summary.missing}</strong>
                <span className="opacity-80">sem motivo informado</span>
              </button>

              {summaryFilter !== null && (
                <button
                  type="button"
                  onClick={() => setSummaryFilter(null)}
                  className="ml-auto flex items-center gap-1 text-xs text-gray-500 hover:text-gray-800 transition-colors"
                  data-testid="bf-summary-clear"
                  title="Limpar filtro"
                >
                  <X size={14} /> Limpar
                </button>
              )}
            </div>

            {summaryFilter !== null && displayedStudents.length === 0 && (
              <div
                className="bg-white rounded-xl border p-8 text-center text-sm text-gray-500"
                data-testid="bf-summary-filter-empty"
              >
                Nenhum aluno corresponde ao filtro selecionado.
              </div>
            )}

            {displayedStudents.map((student) => (
              <div key={student.id} className="bg-white rounded-xl border overflow-hidden" data-testid={`bf-student-${student.id}`}>
                <div className="bg-gray-50 px-4 py-3 border-b">
                  {allSchoolsMode && student.school_name && (
                    <div
                      className="text-xs text-indigo-700 font-semibold uppercase tracking-wide mb-1"
                      data-testid={`bf-student-school-${student.id}`}
                    >
                      {student.school_name}
                    </div>
                  )}
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
                        <th className="text-center px-3 py-2 text-xs font-medium text-gray-500 uppercase w-20">Faltas</th>
                        <th className="text-center px-3 py-2 text-xs font-medium text-gray-500 uppercase w-24">Frequência</th>
                        <th className="text-left px-3 py-2 text-xs font-medium text-gray-500 uppercase w-[420px]">Motivo Oficial MEC</th>
                        <th className="text-left px-3 py-2 text-xs font-medium text-gray-500 uppercase">Observações</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {monthsRange.map(m => {
                        const data = student.months[String(m)] || {};
                        const freq = parseFrequencyPct(data.frequency);
                        const aboveThreshold = freq !== null && freq >= FREQUENCY_THRESHOLD_PCT;
                        const belowThreshold = freq !== null && freq < FREQUENCY_THRESHOLD_PCT;
                        // Política: APENAS acima do limiar desabilita o combobox.
                        // Sem frequência calculada → enabled como opcional.
                        const reasonDisabled = !canEdit || aboveThreshold;
                        const reasonRequired = canEdit && belowThreshold;
                        const reasonInfo = data.reason_id ? reasonIndex.get(data.reason_id) : null;
                        const resolvedLegacyLabel = !data.reason_id && data.motive_legacy
                          ? `LEGADO: ${data.motive_legacy}`
                          : undefined;

                        return (
                          <tr key={m} className={`hover:bg-gray-50 ${belowThreshold ? 'bg-amber-50/40' : ''}`}>
                            <td className="px-4 py-2 font-medium text-gray-700">{MESES[m]}</td>
                            <td className="px-3 py-2 text-center" data-testid={`bf-absences-${student.id}-${m}`}>
                              {data.frequency ? (
                                <span className={`font-semibold ${data.absences > 0 ? 'text-amber-700' : 'text-gray-900'}`}>
                                  {data.absences ?? 0}
                                </span>
                              ) : (
                                <span className="text-gray-300">-</span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-center font-medium">
                              <div className="flex flex-col items-center gap-0.5">
                                {data.frequency ? (
                                  <span className={belowThreshold ? 'text-amber-700 font-bold' : (aboveThreshold ? 'text-emerald-700' : 'text-gray-900')}>
                                    {data.frequency}
                                  </span>
                                ) : (
                                  <span className="text-gray-300">-</span>
                                )}
                                {data.has_medical_certificate && (
                                  <span
                                    className="inline-flex items-center gap-1 text-[10px] text-sky-700 bg-sky-50 border border-sky-200 rounded-full px-1.5 py-0.5 font-medium"
                                    title={`${data.medical_days_count} dia(s) com atestado médico desconsiderado(s) do cálculo`}
                                    data-testid={`bf-medical-badge-${student.id}-${m}`}
                                  >
                                    <Stethoscope size={10} />
                                    Atestado: {data.medical_days_count}d
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="px-3 py-2">
                              {aboveThreshold ? (
                                <div
                                  className="w-full border border-dashed border-gray-200 rounded px-3 py-2 text-xs text-gray-400 bg-gray-50"
                                  data-testid={`bf-reason-disabled-${student.id}-${m}`}
                                >
                                  Frequência ≥ {FREQUENCY_THRESHOLD_PCT}% — motivo não obrigatório
                                </div>
                              ) : (
                                <ReasonCombobox
                                  value={data.reason_id || null}
                                  onChange={(rid) => handleReasonChange(student.id, String(m), rid)}
                                  groups={reasonGroups}
                                  disabled={reasonDisabled}
                                  required={reasonRequired}
                                  resolvedLabel={resolvedLegacyLabel}
                                  testIdPrefix={`bf-reason-${student.id}-${m}`}
                                  placeholder={
                                    belowThreshold
                                      ? 'Obrigatório: selecione o motivo MEC...'
                                      : 'Selecione o motivo MEC (opcional)'
                                  }
                                />
                              )}
                              {reasonInfo && (
                                <div className="mt-1 text-[10px] text-gray-400 font-mono">
                                  {reasonInfo.group_name}
                                </div>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              <input
                                type="text"
                                value={data.notes || ''}
                                placeholder={canEdit && !aboveThreshold ? 'Observações complementares...' : ''}
                                onChange={(e) => handleNotesChange(student.id, String(m), e.target.value)}
                                disabled={!canEdit || aboveThreshold}
                                className="w-full border border-gray-300 rounded px-2 py-1 text-sm disabled:bg-gray-50 disabled:text-gray-400"
                                data-testid={`bf-notes-${student.id}-${m}`}
                              />
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
