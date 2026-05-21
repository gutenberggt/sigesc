/**
 * BuscaAtivaDashboard — Painel operacional de Busca Ativa Escolar
 *
 * Owner spec (Fev/2026 Fase 3B):
 *   - Dashboard OPERACIONAL, não decorativo.
 *   - Responde "Onde agir primeiro?" — não "quais gráficos temos?"
 *   - Severity 5 com destaque visual forte.
 *   - Paginação obrigatória.
 *   - Botão "Baixar planilha" pré-filtrado por categoria (1 clique para ação).
 *
 * Consome:
 *   - GET /api/bolsa-familia/stats/network
 *   - GET /api/bolsa-familia/stats/network/followup
 *   - GET /api/bolsa-familia/stats/network/followup/export
 *   - GET /api/bolsa-familia/stats/snapshots
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import {
  Home, AlertTriangle, Activity, Download, ChevronLeft, ChevronRight,
  AlertCircle, ShieldAlert, Stethoscope, Bus, GraduationCap, RefreshCw,
  Loader2, ExternalLink, ListChecks, School as SchoolIcon,
} from 'lucide-react';
import axios from 'axios';
import { LegacyMigrationDialog } from '@/components/LegacyMigrationDialog';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Tabela canônica de categorias MEC — alinhada com `attendance_frequency_reason_groups`.
const CATEGORY_META = {
  HEALTH: { label: 'Saúde', icon: Stethoscope, color: 'sky' },
  FAMILY: { label: 'Família', icon: AlertCircle, color: 'amber' },
  ACCESS: { label: 'Acesso/Transporte', icon: Bus, color: 'orange' },
  DISCIPLINARY: { label: 'Disciplinar', icon: AlertCircle, color: 'rose' },
  PEDAGOGICAL: { label: 'Pedagógico', icon: GraduationCap, color: 'indigo' },
  VIOLENCE: { label: 'Violência', icon: ShieldAlert, color: 'red' },
  SOCIAL: { label: 'Social', icon: AlertCircle, color: 'purple' },
  CHILD_LABOR: { label: 'Trabalho Infantil', icon: ShieldAlert, color: 'red' },
  WORK: { label: 'Trabalho', icon: AlertCircle, color: 'amber' },
  EVASION: { label: 'Evasão', icon: AlertTriangle, color: 'red' },
  DOCUMENTATION: { label: 'Documentação', icon: AlertCircle, color: 'slate' },
  INCLUSION: { label: 'Inclusão', icon: AlertCircle, color: 'teal' },
  MANAGEMENT: { label: 'Gestão', icon: AlertCircle, color: 'slate' },
  ACTIVE_SEARCH: { label: 'Não Localizado', icon: AlertTriangle, color: 'red' },
  EMERGENCY: { label: 'Emergência', icon: AlertCircle, color: 'orange' },
  NO_ENROLLMENT: { label: 'Sem Vínculo', icon: AlertTriangle, color: 'red' },
  OTHER: { label: 'Outros', icon: AlertCircle, color: 'slate' },
};

const PAGE_SIZE = 25;

function severityClasses(level) {
  const lvl = Number(level) || 0;
  if (lvl >= 5) return 'bg-red-100 text-red-800 border-red-300 font-bold';
  if (lvl >= 4) return 'bg-orange-100 text-orange-800 border-orange-300';
  if (lvl >= 3) return 'bg-amber-100 text-amber-800 border-amber-300';
  if (lvl >= 2) return 'bg-yellow-50 text-yellow-700 border-yellow-200';
  return 'bg-slate-100 text-slate-700 border-slate-300';
}

const MONTHS_PT = {
  '1': 'Jan', '2': 'Fev', '3': 'Mar', '4': 'Abr', '5': 'Mai', '6': 'Jun',
  '7': 'Jul', '8': 'Ago', '9': 'Set', '10': 'Out', '11': 'Nov', '12': 'Dez',
};

export default function BuscaAtivaDashboard() {
  const navigate = useNavigate();
  const token = localStorage.getItem('accessToken');
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const academicYear = new Date().getFullYear();

  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState(null);

  const [followupCases, setFollowupCases] = useState([]);
  const [followupLoading, setFollowupLoading] = useState(true);
  const [categoryFilter, setCategoryFilter] = useState(null);
  const [severityMin, setSeverityMin] = useState(1);
  const [page, setPage] = useState(0);
  const [exportingFormat, setExportingFormat] = useState(null);
  const [legacyDialogOpen, setLegacyDialogOpen] = useState(false);

  const fetchStats = useCallback(async (force = false) => {
    setStatsLoading(true);
    setStatsError(null);
    try {
      const url = `${API}/bolsa-familia/stats/network?academic_year=${academicYear}${force ? '&force_refresh=true' : ''}`;
      let res = await axios.get(url, { headers });
      // Auto-recuperação: se response veio vazia E veio do cache, força refresh
      // (cobre o cenário onde o cache foi popado vazio antes de novos trackings chegarem).
      if (
        !force &&
        res.data?.cached &&
        (res.data?.total_with_reason === 0)
      ) {
        const refreshed = await axios.get(
          `${API}/bolsa-familia/stats/network?academic_year=${academicYear}&force_refresh=true`,
          { headers },
        );
        res = refreshed;
      }
      setStats(res.data);
    } catch (e) {
      console.error(e);
      setStatsError(e?.response?.data?.detail || 'Falha ao carregar estatísticas');
    } finally {
      setStatsLoading(false);
    }
  }, [academicYear, headers]);

  const fetchFollowup = useCallback(async () => {
    setFollowupLoading(true);
    try {
      const params = new URLSearchParams({
        academic_year: String(academicYear),
        severity_min: String(severityMin),
        limit: '500',
      });
      if (categoryFilter) params.set('category', categoryFilter);
      const res = await axios.get(
        `${API}/bolsa-familia/stats/network/followup?${params.toString()}`,
        { headers },
      );
      setFollowupCases(res.data.cases || []);
      setPage(0);
    } catch (e) {
      console.error(e);
    } finally {
      setFollowupLoading(false);
    }
  }, [academicYear, categoryFilter, severityMin, headers]);

  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => { fetchFollowup(); }, [fetchFollowup]);

  const handleExport = async (format, opts = {}) => {
    setExportingFormat(format + (opts.category ? `-${opts.category}` : ''));
    try {
      const params = new URLSearchParams({
        format,
        academic_year: String(academicYear),
        severity_min: String(opts.severityMin ?? severityMin),
        limit: '5000',
      });
      if (opts.category) params.set('category', opts.category);
      const res = await axios.get(
        `${API}/bolsa-familia/stats/network/followup/export?${params.toString()}`,
        { headers, responseType: 'blob' },
      );
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      const ext = format === 'xlsx' ? 'xlsx' : 'csv';
      const catSuffix = opts.category ? `_${opts.category.toLowerCase()}` : '';
      link.download = `bolsa_familia_busca_ativa_${academicYear}${catSuffix}.${ext}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
    } finally {
      setExportingFormat(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(followupCases.length / PAGE_SIZE));
  const pageCases = followupCases.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // Top categoria + top escola — extraídos do `stats`
  const topCategoryEntry = useMemo(() => {
    if (!stats?.by_category) return null;
    const entries = Object.entries(stats.by_category).sort((a, b) => b[1] - a[1]);
    return entries[0] || null;
  }, [stats]);

  const topSchool = stats?.top_schools?.[0] || null;

  return (
    <Layout>
      <div className="space-y-6" data-testid="busca-ativa-dashboard">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/admin/bolsa-familia')} className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors" data-testid="ba-back-btn">
              <Home size={18} /><span>Bolsa Família</span>
            </button>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Activity size={24} className="text-red-600" />
              Busca Ativa Escolar — {academicYear}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchStats(true)}
              disabled={statsLoading}
              className="px-3 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-1.5"
              data-testid="ba-refresh-btn"
            >
              <RefreshCw size={14} className={statsLoading ? 'animate-spin' : ''} />
              Atualizar
            </button>
            <button
              onClick={() => handleExport('xlsx')}
              disabled={exportingFormat !== null}
              className="px-3 py-2 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 flex items-center gap-1.5"
              data-testid="ba-export-xlsx-btn"
            >
              {exportingFormat === 'xlsx' ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
              XLSX (rede toda)
            </button>
          </div>
        </div>

        {/* Banner pergunta-resposta */}
        <div className="bg-gradient-to-r from-slate-900 to-slate-700 text-white rounded-xl px-6 py-4">
          <p className="text-sm opacity-80">Pergunta institucional</p>
          <p className="text-lg font-semibold">Onde devemos agir primeiro?</p>
        </div>

        {statsError && (
          <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg text-sm">
            {statsError}
          </div>
        )}

        {/* Alerta secundário: há legacy pendente, MAS dashboard já tem dados estruturados.
            Mostrado como banner discreto acima dos cards. */}
        {!statsLoading && (stats?.total_with_reason || 0) > 0 && (stats?.total_legacy || 0) > 0 && (
          <div
            className="flex items-center justify-between gap-3 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5"
            data-testid="ba-legacy-pending-banner"
          >
            <div className="flex items-center gap-2 text-sm text-amber-900">
              <AlertTriangle size={16} className="text-amber-600" />
              <span>
                Ainda há <strong>{stats.total_legacy} registros legados</strong> aguardando reclassificação MEC v4.2.
              </span>
            </div>
            <button
              onClick={() => setLegacyDialogOpen(true)}
              className="px-3 py-1 text-xs bg-amber-600 text-white rounded hover:bg-amber-700"
              data-testid="ba-cta-migrate-legacy-secondary"
            >
              Reclassificar agora
            </button>
          </div>
        )}

        {/* Empty state com call-to-action para migração legacy */}
        {!statsLoading && (stats?.total_with_reason || 0) === 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-5" data-testid="ba-empty-state">
            <div className="flex items-start gap-3">
              <AlertTriangle size={20} className="text-amber-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="font-semibold text-amber-900">
                  Ainda não há motivos MEC registrados para {academicYear}
                </h3>
                {(stats?.total_legacy || 0) > 0 ? (
                  <>
                    <p className="text-sm text-amber-800 mt-1">
                      Existem <strong>{stats.total_legacy} registros legados</strong> (versão
                      antiga, texto livre) aguardando classificação no padrão oficial MEC v4.2.
                      Após reclassificá-los, o dashboard começará a operar.
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        onClick={() => setLegacyDialogOpen(true)}
                        className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded-lg hover:bg-amber-700 inline-flex items-center gap-1.5"
                        data-testid="ba-cta-migrate-legacy"
                      >
                        Reclassificar automaticamente ({stats.total_legacy})
                      </button>
                      <button
                        onClick={() => navigate('/admin/bolsa-familia')}
                        className="px-3 py-1.5 text-sm border border-amber-400 text-amber-900 rounded-lg hover:bg-amber-100 inline-flex items-center gap-1.5"
                        data-testid="ba-cta-classify-legacy"
                      >
                        Ir reclassificar manualmente <ExternalLink size={13} />
                      </button>
                    </div>
                  </>
                ) : (stats?.total_pending || 0) > 0 ? (
                  <>
                    <p className="text-sm text-amber-800 mt-1">
                      Há <strong>{stats.total_pending} registros sem motivo informado</strong>.
                      Os motivos MEC são obrigatórios para alunos com frequência abaixo de
                      75%. Acesse a tela de Bolsa Família para preencher.
                    </p>
                    <button
                      onClick={() => navigate('/admin/bolsa-familia')}
                      className="mt-3 px-3 py-1.5 text-sm bg-amber-600 text-white rounded-lg hover:bg-amber-700 inline-flex items-center gap-1.5"
                      data-testid="ba-cta-fill-pending"
                    >
                      Ir preencher motivos <ExternalLink size={13} />
                    </button>
                  </>
                ) : (
                  <p className="text-sm text-amber-800 mt-1">
                    Nenhum acompanhamento de Bolsa Família foi salvo no ano letivo de {academicYear}.
                    Quando o secretário/admin classificar alunos com baixa frequência usando o
                    Combobox de Motivos MEC, este painel passará a refletir a rede.
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* LINHA 1 — Cards executivos */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="ba-cards-row">
          <ExecutiveCard
            label="Total c/ motivo"
            value={stats?.total_with_reason ?? '-'}
            icon={ListChecks}
            tone="slate"
            testId="ba-card-total"
            loading={statsLoading}
          />
          <ExecutiveCard
            label="Severidade ≥ 5"
            value={stats?.severity_5_plus ?? '-'}
            icon={ShieldAlert}
            tone="red"
            highlighted={(stats?.severity_5_plus || 0) > 0}
            testId="ba-card-severity5"
            loading={statsLoading}
          />
          <ExecutiveCard
            label="Req. acompanhamento"
            value={stats?.requires_followup ?? '-'}
            icon={AlertTriangle}
            tone="orange"
            testId="ba-card-followup"
            loading={statsLoading}
          />
          <ExecutiveCard
            label="Top categoria"
            value={topCategoryEntry ? `${CATEGORY_META[topCategoryEntry[0]]?.label || topCategoryEntry[0]}` : '-'}
            sub={topCategoryEntry ? `${topCategoryEntry[1]} casos` : ''}
            icon={Activity}
            tone="indigo"
            testId="ba-card-top-category"
            loading={statsLoading}
          />
          <ExecutiveCard
            label="Top escola"
            value={topSchool?.school_name || topSchool?.school_id || '-'}
            sub={topSchool ? `${topSchool.count} casos` : ''}
            icon={SchoolIcon}
            tone="amber"
            testId="ba-card-top-school"
            loading={statsLoading}
          />
        </div>

        {/* LINHA 2 — Distribuição por categoria com botão de export */}
        <div className="bg-white rounded-xl border p-5" data-testid="ba-distribution-row">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-900">Distribuição por categoria MEC</h2>
            <span className="text-xs text-gray-500">clique para filtrar a lista abaixo</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {Object.entries(stats?.by_category || {})
              .sort((a, b) => b[1] - a[1])
              .map(([cat, count]) => {
                const meta = CATEGORY_META[cat] || { label: cat, icon: AlertCircle, color: 'slate' };
                const Icon = meta.icon;
                const active = categoryFilter === cat;
                return (
                  <div
                    key={cat}
                    className={`relative group border rounded-lg p-3 cursor-pointer transition-all ${
                      active
                        ? 'border-blue-500 ring-2 ring-blue-200 bg-blue-50'
                        : `border-gray-200 hover:border-${meta.color}-400 hover:bg-${meta.color}-50`
                    }`}
                    onClick={() => setCategoryFilter(active ? null : cat)}
                    data-testid={`ba-category-card-${cat}`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <Icon size={16} className={`text-${meta.color}-600`} />
                      <span className="text-2xl font-bold text-gray-900">{count}</span>
                    </div>
                    <p className="text-xs font-medium text-gray-700">{meta.label}</p>
                    <p className="text-[10px] text-gray-400 font-mono">{cat}</p>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleExport('xlsx', { category: cat, severityMin: 1 });
                      }}
                      disabled={exportingFormat !== null}
                      title={`Baixar planilha de ${meta.label}`}
                      className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-white border border-gray-200"
                      data-testid={`ba-export-category-${cat}`}
                    >
                      {exportingFormat === `xlsx-${cat}` ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Download size={12} className="text-gray-600" />
                      )}
                    </button>
                  </div>
                );
              })}
          </div>
          {Object.keys(stats?.by_category || {}).length === 0 && !statsLoading && (
            <p className="text-sm text-gray-400 italic py-6 text-center">
              Ainda não há motivos MEC registrados para o ano letivo.
            </p>
          )}
        </div>

        {/* LINHA 3 — Top escolas */}
        <div className="bg-white rounded-xl border p-5" data-testid="ba-top-schools-row">
          <h2 className="text-base font-semibold text-gray-900 mb-3">Top escolas</h2>
          {(stats?.top_schools?.length || 0) === 0 && !statsLoading && (
            <p className="text-sm text-gray-400 italic py-3">Sem dados.</p>
          )}
          {stats?.top_schools?.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase">
                    <th className="px-3 py-2 font-medium">Escola</th>
                    <th className="px-3 py-2 font-medium text-right">Casos</th>
                    <th className="px-3 py-2 font-medium w-32"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {stats.top_schools.map(s => (
                    <tr key={s.school_id} data-testid={`ba-school-row-${s.school_id}`}>
                      <td className="px-3 py-2 font-medium text-gray-800">
                        {s.school_name || <span className="font-mono text-xs text-gray-500">{s.school_id}</span>}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">{s.count}</td>
                      <td className="px-3 py-2 text-right">
                        <button
                          className="text-xs text-blue-600 hover:underline inline-flex items-center gap-0.5"
                          onClick={() => {
                            const params = new URLSearchParams({ school_id: s.school_id });
                            navigate(`/admin/bolsa-familia?${params.toString()}`);
                          }}
                        >
                          Abrir <ExternalLink size={11} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* LINHA 4 — Casos prioritários */}
        <div className="bg-white rounded-xl border" data-testid="ba-cases-row">
          <div className="flex items-center justify-between flex-wrap gap-3 px-5 py-4 border-b border-gray-200">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-gray-900">
                Casos prioritários
              </h2>
              {categoryFilter && (
                <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded flex items-center gap-1.5">
                  {CATEGORY_META[categoryFilter]?.label || categoryFilter}
                  <button
                    onClick={() => setCategoryFilter(null)}
                    className="hover:text-blue-900 font-bold"
                    data-testid="ba-category-clear"
                  >×</button>
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-sm">
              <label className="text-gray-600">Severidade mínima:</label>
              <select
                value={severityMin}
                onChange={(e) => setSeverityMin(Number(e.target.value))}
                className="border border-gray-300 rounded px-2 py-1 text-sm"
                data-testid="ba-severity-filter"
              >
                <option value={1}>Todos (≥1 ou req. acompanhamento)</option>
                <option value={3}>≥ 3</option>
                <option value={4}>≥ 4</option>
                <option value={5}>Apenas críticos (5)</option>
              </select>
              <button
                onClick={() => handleExport('xlsx', { category: categoryFilter })}
                disabled={exportingFormat !== null || followupCases.length === 0}
                className="px-3 py-1.5 text-xs bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-1"
                data-testid="ba-export-filtered-btn"
              >
                {exportingFormat?.startsWith('xlsx') ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                Baixar filtrados
              </button>
            </div>
          </div>

          {followupLoading ? (
            <div className="p-12 flex items-center justify-center text-gray-500">
              <Loader2 size={20} className="animate-spin mr-2" /> Carregando casos...
            </div>
          ) : followupCases.length === 0 ? (
            <p className="p-10 text-center text-sm text-gray-500 italic">
              Nenhum caso prioritário com os filtros atuais.
            </p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr className="text-left text-xs text-gray-500 uppercase">
                      <th className="px-3 py-2 font-medium">Aluno</th>
                      <th className="px-3 py-2 font-medium">Escola</th>
                      <th className="px-3 py-2 font-medium">Mês</th>
                      <th className="px-3 py-2 font-medium">Motivo MEC</th>
                      <th className="px-3 py-2 font-medium">Categoria</th>
                      <th className="px-3 py-2 font-medium">Severidade</th>
                      <th className="px-3 py-2 font-medium">Obs.</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {pageCases.map((c, idx) => (
                      <tr
                        key={`${c.student_id}-${c.month}-${idx}`}
                        className={c.severity_level >= 5 ? 'bg-red-50/40' : ''}
                        data-testid={`ba-case-row-${idx}`}
                      >
                        <td className="px-3 py-2 font-medium text-gray-800">
                          {c.student_name || <span className="font-mono text-xs text-gray-400">{c.student_id}</span>}
                        </td>
                        <td className="px-3 py-2 text-gray-700">{c.school_name || c.school_id}</td>
                        <td className="px-3 py-2 text-gray-600">{MONTHS_PT[String(c.month)] || c.month}</td>
                        <td className="px-3 py-2">
                          <span className="font-mono text-xs text-gray-500 mr-1">{c.reason_subcode}</span>
                          {c.reason_name}
                        </td>
                        <td className="px-3 py-2 text-xs">
                          {CATEGORY_META[c.category]?.label || c.category}
                        </td>
                        <td className="px-3 py-2">
                          <span className={`inline-block px-2 py-0.5 rounded text-xs border ${severityClasses(c.severity_level)}`}>
                            {c.severity_level}
                            {c.severity_level >= 5 ? ' • CRÍTICO' : ''}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-600 truncate max-w-xs" title={c.notes}>
                          {c.notes || <span className="text-gray-300">—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100">
                <p className="text-xs text-gray-500">
                  Página {page + 1} de {totalPages} — {followupCases.length} casos
                </p>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setPage(p => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="p-1.5 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
                    data-testid="ba-page-prev"
                  >
                    <ChevronLeft size={14} />
                  </button>
                  <button
                    onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                    disabled={page >= totalPages - 1}
                    className="p-1.5 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
                    data-testid="ba-page-next"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
      <LegacyMigrationDialog
        open={legacyDialogOpen}
        onClose={() => setLegacyDialogOpen(false)}
        onApplied={() => {
          fetchStats(true);
          fetchFollowup();
        }}
        academicYear={academicYear}
      />
    </Layout>
  );
}

function ExecutiveCard({ label, value, sub, icon: Icon, tone = 'slate', highlighted = false, testId, loading }) {
  const tones = {
    slate: 'bg-slate-50 border-slate-200 text-slate-900',
    red: 'bg-red-50 border-red-300 text-red-900',
    orange: 'bg-orange-50 border-orange-200 text-orange-900',
    amber: 'bg-amber-50 border-amber-200 text-amber-900',
    indigo: 'bg-indigo-50 border-indigo-200 text-indigo-900',
    sky: 'bg-sky-50 border-sky-200 text-sky-900',
  };
  const highlightedRing = highlighted ? 'ring-2 ring-red-500 ring-offset-1' : '';
  return (
    <div
      className={`border rounded-xl p-4 ${tones[tone] || tones.slate} ${highlightedRing}`}
      data-testid={testId}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} className="opacity-70" />
        <p className="text-xs uppercase tracking-wide font-medium opacity-80">{label}</p>
      </div>
      <p className="text-2xl font-bold leading-none">
        {loading ? <Loader2 size={20} className="animate-spin opacity-50" /> : value}
      </p>
      {sub && <p className="text-xs opacity-60 mt-1">{sub}</p>}
    </div>
  );
}
