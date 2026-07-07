import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { pmeAnosFinaisAPI } from '@/services/api';

import { usePermissions } from '@/hooks/usePermissions';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, PieChart, Pie, Cell,
} from 'recharts';
import {
  Home, RefreshCw, Loader2, School, Users, Layers, Accessibility, GraduationCap,
  TrendingDown, Target, FileSpreadsheet, FileText, ClipboardList, MapPin, BookOpen, Bus,
} from 'lucide-react';
import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';

const YEARS = Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - i);
const LEVELS = [
  { value: 'educacao_infantil', label: 'Educação Infantil' },
  { value: 'fundamental_anos_iniciais', label: 'Anos Iniciais' },
  { value: 'fundamental_anos_finais', label: 'Anos Finais' },
  { value: 'eja', label: 'EJA' },
];
const PALETTE = ['#4f46e5', '#0ea5e9', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6', '#ec4899'];
const COR_RACA_LABEL = { branca: 'Branca', preta: 'Preta', parda: 'Parda', amarela: 'Amarela', indigena: 'Indígena', nao_informada: 'Não informada', nao_declarado: 'Não declarado' };
const REND_LABEL = { aprovado: 'Aprovado/Promovido', abandono: 'Abandono', transferido: 'Transferido', cursando: 'Cursando', cancelado: 'Cancelado', inativo: 'Inativo' };
const REND_COLOR = { aprovado: '#22c55e', abandono: '#ef4444', transferido: '#f59e0b', cursando: '#0ea5e9', cancelado: '#9ca3af', inativo: '#6b7280' };

const Stat = ({ icon: Icon, label, value, sub, color = 'indigo' }) => {
  const c = { indigo: 'text-indigo-600 bg-indigo-50', sky: 'text-sky-600 bg-sky-50', green: 'text-green-600 bg-green-50', amber: 'text-amber-600 bg-amber-50', red: 'text-red-600 bg-red-50', purple: 'text-purple-600 bg-purple-50' }[color];
  return (
    <Card><CardContent className="p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${c}`}>{Icon && <Icon size={20} />}</div>
        <div>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          <p className="text-xs text-gray-500">{label}</p>
          {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
        </div>
      </div>
    </CardContent></Card>
  );
};

const Block = ({ title, children, icon: Icon }) => (
  <Card><CardContent className="p-5">
    <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">{Icon && <Icon size={16} className="text-indigo-500" />}{title}</h3>
    {children}
  </CardContent></Card>
);

export default function PmeAnosFinais() {
  const navigate = useNavigate();
  const { isAdmin } = usePermissions();
  const reportRef = useRef(null);
  const [year, setYear] = useState(new Date().getFullYear());
  const [level, setLevel] = useState('fundamental_anos_finais');
  const [schoolId, setSchoolId] = useState('');
  const [zona, setZona] = useState('');
  const [schools, setSchools] = useState([]);
  const [data, setData] = useState(null);
  const [external, setExternal] = useState(null);
  const [loading, setLoading] = useState(false);

  // Escolas que oferecem o nível selecionado (no ano letivo).
  useEffect(() => {
    setSchoolId('');
    pmeAnosFinaisAPI.schoolsByLevel({ academic_year: year, level })
      .then((r) => setSchools(r.schools || [])).catch(() => setSchools([]));
  }, [level, year]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, e] = await Promise.all([
        pmeAnosFinaisAPI.analytics({ academic_year: year, level, school_id: schoolId || undefined, zona: zona || undefined }),
        pmeAnosFinaisAPI.getExternal(year, level),
      ]);
      setData(a); setExternal(e);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Falha ao carregar o painel.');
    } finally { setLoading(false); }
  }, [year, level, schoolId, zona]);

  useEffect(() => { load(); }, [load]);

  const corRacaData = useMemo(() => Object.entries(data?.cor_raca || {}).map(([k, v]) => ({ name: COR_RACA_LABEL[k] || k, value: v })), [data]);
  const matrEscolaData = useMemo(() => (data?.matriculas?.por_escola || []).map((x) => ({ name: x.school || '—', total: x.total })), [data]);
  const rendGeralData = useMemo(() => Object.entries(data?.rendimento?.geral || {}).filter(([, v]) => v > 0).map(([k, v]) => ({ name: REND_LABEL[k] || k, key: k, value: v })), [data]);
  const rendSerieData = useMemo(() => Object.entries(data?.rendimento?.por_serie || {}).sort().map(([s, o]) => ({ serie: `${s}º`, ...o })), [data]);
  const distorcaoData = useMemo(() => Object.entries(data?.distorcao_idade_serie || {}).sort().map(([s, o]) => ({ serie: `${s}º`, pct: o.total ? Math.round(1000 * o.distorcidos / o.total) / 10 : 0, distorcidos: o.distorcidos, total: o.total })), [data]);
  const evolucaoData = useMemo(() => (external?.evolucao || []).filter((e) => e.year).sort((a, b) => a.year - b.year), [external]);
  const bnccData = useMemo(() => (external?.bncc_descritores || []).filter((d) => d.descritor), [external]);

  const exportExcel = () => {
    if (!data) return;
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(data.escolas?.lista || []), 'Escolas');
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(data.matriculas?.por_escola || []), 'Matriculas');
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(rendSerieData), 'Rendimento');
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(distorcaoData), 'Distorcao');
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(corRacaData), 'CorRaca');
    XLSX.writeFile(wb, `PME_AnosFinais_${year}.xlsx`);
  };

  const exportPDF = async () => {
    if (!reportRef.current) return;
    toast.info('Gerando PDF…');
    try {
      const canvas = await html2canvas(reportRef.current, { scale: 1.5, useCORS: true, backgroundColor: '#ffffff' });
      const img = canvas.toDataURL('image/jpeg', 0.85);
      const pdf = new jsPDF('p', 'mm', 'a4');
      const pw = pdf.internal.pageSize.getWidth();
      const ph = pdf.internal.pageSize.getHeight();
      const iw = pw, ih = (canvas.height * pw) / canvas.width;
      let left = ih, pos = 0;
      pdf.addImage(img, 'JPEG', 0, pos, iw, ih);
      left -= ph;
      while (left > 0) { pos -= ph; pdf.addPage(); pdf.addImage(img, 'JPEG', 0, pos, iw, ih); left -= ph; }
      pdf.save(`PME_AnosFinais_${year}.pdf`);
    } catch (e) { toast.error('Falha ao gerar PDF.'); }
  };

  const m = data?.matriculas || {}; const esc = data?.escolas || {};
  const resumo = data ? buildResumo(data, external, year) : '';

  return (
    <Layout>
      <div className="space-y-6" data-testid="pme-dashboard-page">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/dashboard')} className="flex items-center gap-2 text-gray-500 hover:text-indigo-600" data-testid="pme-home"><Home size={20} /><span>Início</span></button>
            <h1 className="text-2xl font-bold flex items-center gap-2"><GraduationCap className="text-indigo-600" /> Análise PME</h1>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <select value={year} onChange={(e) => setYear(parseInt(e.target.value, 10))} className="px-3 py-2 border rounded-lg bg-white" data-testid="pme-year">{YEARS.map((y) => <option key={y} value={y}>{y}</option>)}</select>
            <select value={level} onChange={(e) => setLevel(e.target.value)} className="px-3 py-2 border rounded-lg bg-white" data-testid="pme-level">{LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select>
            <select value={schoolId} onChange={(e) => setSchoolId(e.target.value)} className="px-3 py-2 border rounded-lg bg-white max-w-[200px]" data-testid="pme-school"><option value="">Todas as escolas</option>{schools.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
            <select value={zona} onChange={(e) => setZona(e.target.value)} className="px-3 py-2 border rounded-lg bg-white" data-testid="pme-zona"><option value="">Todas as zonas</option><option value="urbana">Urbana</option><option value="rural">Rural</option></select>
            <Button variant="outline" size="icon" onClick={load} data-testid="pme-refresh"><RefreshCw size={16} /></Button>
            <Button variant="outline" onClick={exportExcel} data-testid="pme-export-excel"><FileSpreadsheet size={16} className="mr-2" /> Excel</Button>
            <Button variant="outline" onClick={exportPDF} data-testid="pme-export-pdf"><FileText size={16} className="mr-2" /> PDF</Button>
            {isAdmin && (
              <Button className="bg-indigo-600 hover:bg-indigo-700" onClick={() => navigate('/pme/anos-finais/indicadores')} data-testid="pme-go-external"><ClipboardList size={16} className="mr-2" /> Indicadores Externos</Button>
            )}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-gray-500 py-20 justify-center"><Loader2 className="animate-spin" size={20} /> Carregando indicadores…</div>
        ) : !data ? null : (
          <div ref={reportRef} className="space-y-6 bg-white">
            {/* Resumo */}
            <Card><CardContent className="p-5">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Descrição resumida</h3>
              <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-line" data-testid="pme-resumo">{resumo}</p>
            </CardContent></Card>

            {/* KPIs */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              <Stat icon={School} label="Escolas (Anos Finais)" value={esc.total ?? 0} sub={`${esc.por_zona?.urbana || 0} urb. / ${esc.por_zona?.rural || 0} rural`} color="indigo" />
              <Stat icon={Users} label="Matrículas" value={m.total ?? 0} sub={`${m.ativos || 0} ativas`} color="sky" />
              <Stat icon={Layers} label="Turmas multisseriadas" value={data.multisseriadas?.total ?? 0} sub={`de ${data.multisseriadas?.total_turmas_af || 0} turmas`} color="purple" />
              <Stat icon={Accessibility} label="Com deficiência" value={`${data.deficiencia?.percentual ?? 0}%`} sub={`${data.deficiencia?.com_deficiencia || 0} alunos`} color="amber" />
              <Stat icon={TrendingDown} label="Taxa de abandono" value={`${data.evasao?.taxa_abandono_pct ?? 0}%`} sub={`${data.evasao?.abandono_total || 0} alunos`} color="red" />
              <Stat icon={GraduationCap} label="Docentes c/ formação" value={`${data.docentes?.perc_com_formacao ?? 0}%`} sub={`${data.docentes?.total || 0} docentes`} color="green" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Block title="Matrículas por escola" icon={School}>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={matrEscolaData} layout="vertical" margin={{ left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" /><XAxis type="number" /><YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="total" fill="#4f46e5" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Block>

              <Block title="Cor/Raça (alunos ativos)" icon={Users}>
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart><Pie data={corRacaData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label>{corRacaData.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}</Pie><Tooltip /><Legend /></PieChart>
                </ResponsiveContainer>
              </Block>

              <Block title="Rendimento (situação de matrícula)" icon={Target}>
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart><Pie data={rendGeralData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label>{rendGeralData.map((d, i) => <Cell key={i} fill={REND_COLOR[d.key] || PALETTE[i % PALETTE.length]} />)}</Pie><Tooltip /><Legend /></PieChart>
                </ResponsiveContainer>
              </Block>

              <Block title="Rendimento por série (6º–9º)" icon={Target}>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={rendSerieData}>
                    <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="serie" /><YAxis /><Tooltip /><Legend />
                    <Bar dataKey="aprovado" stackId="a" fill={REND_COLOR.aprovado} name="Aprovado" />
                    <Bar dataKey="cursando" stackId="a" fill={REND_COLOR.cursando} name="Cursando" />
                    <Bar dataKey="abandono" stackId="a" fill={REND_COLOR.abandono} name="Abandono" />
                    <Bar dataKey="transferido" stackId="a" fill={REND_COLOR.transferido} name="Transferido" />
                  </BarChart>
                </ResponsiveContainer>
              </Block>

              <Block title="Distorção idade-série (% com 2+ anos de atraso)" icon={TrendingDown}>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={distorcaoData}>
                    <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="serie" /><YAxis unit="%" /><Tooltip formatter={(v, n, p) => [`${v}% (${p.payload.distorcidos}/${p.payload.total})`, 'Distorção']} /><Bar dataKey="pct" fill="#ef4444" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Block>

              <Block title="Socioeconômico — alunos com NIS (Cadastro Único)" icon={Users}>
                <div className="flex items-center justify-center h-[260px]">
                  <div className="text-center">
                    <p className="text-5xl font-bold text-indigo-600">{data.socioeconomico?.percentual ?? 0}%</p>
                    <p className="text-sm text-gray-500 mt-2">{data.socioeconomico?.com_nis || 0} de {data.socioeconomico?.total_ativos || 0} alunos com NIS registrado</p>
                  </div>
                </div>
              </Block>
            </div>

            {/* Indicadores externos */}
            <h2 className="text-lg font-semibold text-gray-800 pt-2 flex items-center gap-2"><ClipboardList size={18} className="text-indigo-600" /> Indicadores Externos (informados)</h2>
            {(!external || external.exists === false) ? (
              <Card><CardContent className="p-5 text-sm text-gray-500">
                Nenhum indicador externo informado para {year}.{isAdmin && <> <button onClick={() => navigate('/pme/anos-finais/indicadores')} className="text-indigo-600 underline">Informar agora</button>.</>}
              </CardContent></Card>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Block title="IDEB — atual x meta" icon={Target}>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={[{ name: 'IDEB', Atual: external.ideb_atual || 0, Meta: external.ideb_meta || 0 }]}>
                      <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis /><Tooltip /><Legend /><Bar dataKey="Atual" fill="#4f46e5" radius={[4, 4, 0, 0]} /><Bar dataKey="Meta" fill="#22c55e" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </Block>

                <Block title="Evolução IDEB / SAEB" icon={Target}>
                  {evolucaoData.length ? (
                    <ResponsiveContainer width="100%" height={220}>
                      <LineChart data={evolucaoData}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="year" /><YAxis /><Tooltip /><Legend /><Line dataKey="ideb" name="IDEB" stroke="#4f46e5" /><Line dataKey="lp" name="LP" stroke="#0ea5e9" /><Line dataKey="mat" name="Mat" stroke="#f59e0b" /></LineChart>
                    </ResponsiveContainer>
                  ) : <p className="text-sm text-gray-400 h-[220px] flex items-center justify-center">Sem histórico informado.</p>}
                </Block>

                <Block title="Defasagem por descritores BNCC/SAEB" icon={BookOpen}>
                  {bnccData.length ? (
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={bnccData} layout="vertical" margin={{ left: 20 }}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" unit="%" /><YAxis type="category" dataKey="descritor" width={120} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="nivel_defasagem_pct" name="% defasagem" fill="#ef4444" radius={[0, 4, 4, 0]} /></BarChart>
                    </ResponsiveContainer>
                  ) : <p className="text-sm text-gray-400 h-[220px] flex items-center justify-center">Sem descritores informados.</p>}
                </Block>

                <Block title="Atendimento populacional & Transporte" icon={MapPin}>
                  <div className="grid grid-cols-2 gap-4 py-4">
                    <ExtMini label="População 11–14 anos" value={external.pop_11_14_pct != null ? `${external.pop_11_14_pct}%` : '—'} />
                    <ExtMini label="População 16 anos" value={external.pop_16_pct != null ? `${external.pop_16_pct}%` : '—'} />
                    <ExtMini label="SAEB LP (9º)" value={external.saeb_lp_9 ?? '—'} />
                    <ExtMini label="SAEB Mat (9º)" value={external.saeb_mat_9 ?? '—'} />
                    <ExtMini label="Cobertura transporte" value={external.transporte_cobertura_pct != null ? `${external.transporte_cobertura_pct}%` : '—'} icon={Bus} />
                    <ExtMini label="Formação continuada" value={external.formacao_continuada_ativa == null ? '—' : external.formacao_continuada_ativa ? 'Sim' : 'Não'} />
                  </div>
                  {external.transporte_impacto_evasao && <p className="text-xs text-gray-500">Transporte: {external.transporte_impacto_evasao}</p>}
                  {external.observacoes_gerais && <p className="text-xs text-gray-500 mt-1">Obs.: {external.observacoes_gerais}</p>}
                </Block>
              </div>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
}

const ExtMini = ({ label, value, icon: Icon }) => (
  <div className="text-center p-2 bg-gray-50 rounded-lg">
    <p className="text-xl font-bold text-gray-800 flex items-center justify-center gap-1">{Icon && <Icon size={14} />}{value}</p>
    <p className="text-xs text-gray-500">{label}</p>
  </div>
);

function buildResumo(d, ext, year) {
  const esc = d.escolas || {}; const m = d.matriculas || {};
  const parts = [];
  const lvlLabel = d.level_label || 'o nível selecionado';
  parts.push(`No ano letivo de ${year}, a rede possui ${esc.total || 0} escola(s) que atendem ${lvlLabel} (${esc.por_zona?.urbana || 0} na zona urbana e ${esc.por_zona?.rural || 0} na rural), com ${m.total || 0} matrícula(s) (${m.ativos || 0} ativas).`);
  if (d.multisseriadas?.total) parts.push(`Há ${d.multisseriadas.total} turma(s) multisseriada(s) de um total de ${d.multisseriadas.total_turmas_af}.`);
  parts.push(`${d.deficiencia?.percentual || 0}% dos alunos ativos possuem deficiência/transtorno; ${d.socioeconomico?.percentual || 0}% têm NIS (Cadastro Único).`);
  parts.push(`A taxa de abandono é de ${d.evasao?.taxa_abandono_pct || 0}% (${d.evasao?.abandono_total || 0} aluno(s)), com ${d.evasao?.transferidos || 0} transferência(s).`);
  const dist = Object.entries(d.distorcao_idade_serie || {});
  if (dist.length) {
    const tot = dist.reduce((a, [, o]) => a + o.total, 0); const dd = dist.reduce((a, [, o]) => a + o.distorcidos, 0);
    parts.push(`A distorção idade-série atinge ${tot ? Math.round(1000 * dd / tot) / 10 : 0}% dos alunos (2+ anos de atraso).`);
  }
  parts.push(`Dos ${d.docentes?.total || 0} docentes vinculados a ${lvlLabel}, ${d.docentes?.perc_com_formacao || 0}% têm formação registrada.`);
  if (ext && ext.exists !== false && (ext.ideb_atual != null || ext.ideb_meta != null)) {
    parts.push(`IDEB atual: ${ext.ideb_atual ?? '—'} | meta: ${ext.ideb_meta ?? '—'}.`);
  }
  return parts.join(' ');
}
