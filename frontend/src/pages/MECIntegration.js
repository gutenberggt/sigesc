import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { Settings, Key, Server, User, Mail, Phone, Briefcase, CheckCircle2, AlertCircle, XCircle, Loader2, ExternalLink, RefreshCw, School, Users, FileText, Shield, Copy, ChevronDown, ChevronUp, Info, Home } from 'lucide-react';
import { mecAPI } from '@/services/api';

const ENV_LABELS = {
  homologacao: 'Homologação (Testes)',
  producao: 'Produção'
};

const STATUS_MAP = {
  not_configured: { label: 'Não Configurada', icon: XCircle, color: 'text-gray-500', bg: 'bg-gray-100' },
  pending: { label: 'Pendente', icon: AlertCircle, color: 'text-yellow-600', bg: 'bg-yellow-100' },
  configured: { label: 'Configurada', icon: CheckCircle2, color: 'text-green-600', bg: 'bg-green-100' },
};

export default function MECIntegration() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [config, setConfig] = useState(null);
  const [syncStatus, setSyncStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [showMapping, setShowMapping] = useState(false);
  const [mappingData, setMappingData] = useState(null);
  const [loadingMapping, setLoadingMapping] = useState(false);
  const [activeTab, setActiveTab] = useState('config');
  const [metrics, setMetrics] = useState(null);
  const [auditEvents, setAuditEvents] = useState([]);
  const [flags, setFlags] = useState(null);
  const [loadingOps, setLoadingOps] = useState(false);
  const [auditPage, setAuditPage] = useState(1);
  const [auditTotalPages, setAuditTotalPages] = useState(1);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditStatusFilter, setAuditStatusFilter] = useState('');

  // Sprint 002.b — Preview de Lotes de Frequência (Batch Builder)
  const defaultCompetencia = () => {
    const d = new Date();
    d.setMonth(d.getMonth() - 1); // mês anterior (competência normalmente já encerrada)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  };
  const [freqCompetencia, setFreqCompetencia] = useState(defaultCompetencia());
  const [freqPreview, setFreqPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [previewError, setPreviewError] = useState('');

  const runFreqPreview = async () => {
    setLoadingPreview(true); setPreviewError(''); setFreqPreview(null);
    try {
      const data = await mecAPI.previewFrequency({ competencia: freqCompetencia, dryRun: true });
      setFreqPreview(data);
    } catch (e) {
      setPreviewError(e?.response?.data?.detail || 'Falha ao gerar o preview.');
    }
    setLoadingPreview(false);
  };

  const loadOps = useCallback(async (page = 1, statusFilter = '') => {
    setLoadingOps(true);
    try {
      const params = { page, page_size: 20 };
      if (statusFilter) params.status = statusFilter;
      const [m, a, f] = await Promise.all([mecAPI.getMetrics(), mecAPI.getAudit(params), mecAPI.getFlags()]);
      setMetrics(m); setAuditEvents(a.events || []); setFlags(f);
      setAuditPage(a.page || 1); setAuditTotalPages(a.total_pages || 1); setAuditTotal(a.total || 0);
    } catch (e) { console.error(e); }
    setLoadingOps(false);
  }, []);

  const toggleFlag = async (flag, enabled, environment) => {
    try { await mecAPI.setFlag({ flag, enabled, environment }); await loadOps(auditPage, auditStatusFilter); }
    catch (e) { console.error(e); }
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [configRes, statusRes] = await Promise.all([
        mecAPI.getConfig(),
        mecAPI.getSyncStatus()
      ]);
      setConfig(configRes);
      setSyncStatus(statusRes);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await mecAPI.updateConfig(config);
      await loadData();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const handleChange = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const loadMapping = async () => {
    setShowMapping(true);
    setLoadingMapping(true);
    try {
      const res = await mecAPI.getStudentsMapping();
      setMappingData(res);
    } catch (e) { console.error(e); }
    setLoadingMapping(false);
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
  };

  if (loading) {
    return (
      <Layout>
        <div className="p-8 flex items-center justify-center min-h-[400px]">
          <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
          <span className="ml-3 text-gray-500">Carregando...</span>
        </div>
      </Layout>
    );
  }

  const statusInfo = STATUS_MAP[config?.status || 'not_configured'];
  const StatusIcon = statusInfo.icon;

  return (
    <Layout>
    <div className="space-y-6" data-testid="mec-integration-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors" data-testid="mec-home-btn">
            <Home size={18} /><span>Início</span>
          </button>
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Integração MEC Gestão Presente</h2>
            <p className="text-gray-600 mt-1">Configure o envio e consulta de dados educacionais via API do MEC</p>
          </div>
        </div>
        <div className={`flex items-center gap-2 px-4 py-2 rounded-full ${statusInfo.bg}`}>
          <StatusIcon className={`h-5 w-5 ${statusInfo.color}`} />
          <span className={`font-medium ${statusInfo.color}`} data-testid="mec-status">{statusInfo.label}</span>
        </div>
      </div>

      {/* Status Cards */}
      {syncStatus?.details && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center"><Users className="h-5 w-5 text-blue-600" /></div>
              <div>
                <p className="text-xs text-gray-500">Alunos Ativos</p>
                <p className="text-xl font-bold">{syncStatus.details.students_total}</p>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-xl border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"><FileText className="h-5 w-5 text-green-600" /></div>
              <div>
                <p className="text-xs text-gray-500">Com CPF</p>
                <p className="text-xl font-bold text-green-600">{syncStatus.details.students_with_cpf}</p>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-xl border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center"><Shield className="h-5 w-5 text-purple-600" /></div>
              <div>
                <p className="text-xs text-gray-500">Com NIS</p>
                <p className="text-xl font-bold text-purple-600">{syncStatus.details.students_with_nis}</p>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-xl border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center"><School className="h-5 w-5 text-orange-600" /></div>
              <div>
                <p className="text-xs text-gray-500">Escolas com INEP</p>
                <p className="text-xl font-bold text-orange-600">{syncStatus.details.schools_with_inep}/{syncStatus.details.schools_total}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Abas: Configuração (administrativa) × Operação Técnica */}
      <div className="flex gap-1 border-b border-gray-200" data-testid="mec-tabs">
        <button
          onClick={() => setActiveTab('config')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'config' ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
          data-testid="tab-config"
        >
          <Settings className="inline h-4 w-4 mr-1" />Configuração
        </button>
        <button
          onClick={() => { setActiveTab('operacao'); loadOps(); }}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'operacao' ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
          data-testid="tab-operacao"
        >
          <RefreshCw className="inline h-4 w-4 mr-1" />Operação Técnica
        </button>
      </div>

      {/* ===== Operação Técnica (Dashboard Técnico MIG) ===== */}
      {activeTab === 'operacao' && (
        <div className="space-y-6" data-testid="mec-ops-panel">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900">Saúde da Integração</h3>
            <button onClick={() => loadOps(auditPage, auditStatusFilter)} disabled={loadingOps} className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border hover:bg-gray-50 disabled:opacity-60" data-testid="ops-refresh-btn">
              {loadingOps ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}Atualizar
            </button>
          </div>

          {/* Métricas */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4" data-testid="mec-metrics">
            {[
              { label: 'Total de chamadas', value: metrics?.total_calls ?? 0 },
              { label: 'Sucesso', value: metrics?.success ?? 0 },
              { label: 'Erros', value: metrics?.error ?? 0 },
              { label: 'Taxa de sucesso', value: metrics?.success_rate != null ? `${metrics.success_rate}%` : '—' },
              { label: 'Latência média', value: metrics?.avg_latency_ms != null ? `${metrics.avg_latency_ms} ms` : '—' },
              { label: 'Volume processado', value: metrics?.volume_processed ?? 0 },
            ].map((c, i) => (
              <div key={i} className="bg-white rounded-xl border p-4">
                <p className="text-xs text-gray-500">{c.label}</p>
                <p className="text-xl font-bold text-gray-900">{c.value}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-500">Última execução: {metrics?.last_execution ? new Date(metrics.last_execution).toLocaleString('pt-BR') : 'Nenhuma execução registrada'}</p>

          {/* Feature Flags */}
          <div className="bg-white rounded-xl border p-5">
            <h4 className="font-semibold text-gray-900 mb-1">Feature Flags {flags?.environment ? `(ambiente: ${flags.environment})` : ''}</h4>
            <p className="text-xs text-gray-500 mb-3">Ativação controlada por tenant/ambiente. Alterações são auditadas.</p>
            <div className="space-y-2" data-testid="mec-flags">
              {flags?.flags && Object.entries(flags.flags).map(([flag, enabled]) => (
                <div key={flag} className="flex items-center justify-between border border-gray-200 rounded-lg px-3 py-2">
                  <span className="text-sm font-mono text-gray-700">{flag}</span>
                  <button
                    onClick={() => toggleFlag(flag, !enabled, flags.environment)}
                    className={`text-xs px-3 py-1 rounded-full font-medium ${enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}
                    data-testid={`flag-toggle-${flag}`}
                  >
                    {enabled ? 'Habilitado' : 'Desabilitado'}
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Preview de Lotes de Frequência (Batch Builder — Sprint 002.b) */}
          <div className="bg-white rounded-xl border p-5" data-testid="freq-preview-panel">
            <div className="flex items-center justify-between gap-3 flex-wrap mb-1">
              <h4 className="font-semibold text-gray-900">Preview de Lotes de Frequência</h4>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">DRY-RUN (não envia)</span>
            </div>
            <p className="text-xs text-gray-500 mb-3">
              Simulação (somente leitura) da montagem de lotes CMDE a partir da frequência consolidada (SSoT). Nada é enviado ao MEC.
            </p>
            <div className="flex items-end gap-3 flex-wrap mb-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Competência (AAAA-MM)</label>
                <input
                  type="month"
                  value={freqCompetencia}
                  onChange={(e) => setFreqCompetencia(e.target.value)}
                  className="text-sm border border-gray-300 rounded-lg px-3 py-1.5"
                  data-testid="freq-competencia-input"
                />
              </div>
              <button
                onClick={runFreqPreview}
                disabled={loadingPreview || !freqCompetencia}
                className="inline-flex items-center gap-1.5 text-sm px-4 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                data-testid="freq-preview-btn"
              >
                {loadingPreview ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />}Gerar preview
              </button>
            </div>

            {previewError && (
              <p className="text-sm text-red-600 mb-2" data-testid="freq-preview-error">{previewError}</p>
            )}

            {freqPreview && (
              <div data-testid="freq-preview-result">
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-3">
                  {[
                    { label: 'Competência', value: freqPreview.competencia },
                    { label: 'Alunos analisados', value: freqPreview.analyzed },
                    { label: 'Prontos', value: freqPreview.ready_count },
                    { label: 'Pendências', value: freqPreview.pending_count },
                    { label: 'Lotes previstos', value: freqPreview.lotes_previstos },
                    { label: 'Modo', value: freqPreview.dry_run ? 'Dry-run' : 'Real' },
                  ].map((c, i) => (
                    <div key={i} className="rounded-lg border p-3 bg-gray-50">
                      <p className="text-[11px] text-gray-500">{c.label}</p>
                      <p className="text-base font-bold text-gray-900" data-testid={`freq-metric-${i}`}>{c.value}</p>
                    </div>
                  ))}
                </div>
                <p className="text-xs mb-3">
                  {freqPreview.competencia_fechada
                    ? <span className="text-green-700">Competência encerrada — apta a construção real (fora do dry-run).</span>
                    : <span className="text-amber-700">Competência em curso — apenas preview; construção real bloqueada.</span>}
                  {' '}<span className="text-gray-400 font-mono">{freqPreview.correlation_id}</span>
                </p>

                {freqPreview.pendencias?.length > 0 && (
                  <div className="border border-amber-200 rounded-lg overflow-hidden">
                    <div className="px-4 py-2 bg-amber-50 text-amber-800 text-sm font-medium">
                      Relatório de inconsistências ({freqPreview.pendencias.length})
                    </div>
                    <div className="overflow-x-auto max-h-56 overflow-y-auto">
                      <table className="w-full text-sm" data-testid="freq-pendencias-table">
                        <thead className="bg-gray-50 text-gray-600 sticky top-0">
                          <tr>
                            <th className="text-left px-4 py-2 font-medium">Aluno</th>
                            <th className="text-left px-4 py-2 font-medium">Dados faltantes</th>
                          </tr>
                        </thead>
                        <tbody>
                          {freqPreview.pendencias.map((p, i) => (
                            <tr key={i} className="border-t">
                              <td className="px-4 py-2">{p.full_name || p.student_id}</td>
                              <td className="px-4 py-2 text-gray-600">{(p.missing || []).join(', ')}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Falhas recentes */}
          {metrics?.recent_failures?.length > 0 && (
            <div className="bg-white rounded-xl border p-5">
              <h4 className="font-semibold text-red-700 mb-3">Falhas Recentes</h4>
              <div className="space-y-2">
                {metrics.recent_failures.map((f, i) => (
                  <div key={i} className="text-sm text-gray-700 flex items-center gap-2">
                    <XCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
                    <span className="font-medium">{f.operation}</span>
                    <span className="text-gray-400">·</span>
                    <span>HTTP {f.http_status ?? '—'}</span>
                    <span className="text-gray-400">·</span>
                    <span className="text-gray-500">{f.error_message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Histórico de eventos */}
          <div className="bg-white rounded-xl border overflow-hidden">
            <div className="px-5 py-3 border-b flex items-center justify-between gap-3 flex-wrap">
              <h4 className="font-semibold text-gray-900">Histórico de Eventos <span className="text-xs font-normal text-gray-400">({auditTotal})</span></h4>
              <div className="flex items-center gap-2">
                <select
                  value={auditStatusFilter}
                  onChange={(e) => { setAuditStatusFilter(e.target.value); loadOps(1, e.target.value); }}
                  className="text-sm border border-gray-300 rounded-lg px-2 py-1"
                  data-testid="audit-status-filter"
                >
                  <option value="">Todos os status</option>
                  <option value="success">Sucesso</option>
                  <option value="error">Erro</option>
                </select>
              </div>
            </div>
            {auditEvents.length === 0 ? (
              <p className="p-5 text-sm text-gray-400">Nenhum evento de integração registrado ainda.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="mec-audit-table">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="text-left px-4 py-2 font-medium">Correlation ID</th>
                      <th className="text-left px-4 py-2 font-medium">Operação</th>
                      <th className="text-left px-4 py-2 font-medium">Status</th>
                      <th className="text-left px-4 py-2 font-medium">Registros</th>
                      <th className="text-left px-4 py-2 font-medium">Tentativas</th>
                      <th className="text-left px-4 py-2 font-medium">Duração</th>
                      <th className="text-left px-4 py-2 font-medium">Responsável</th>
                      <th className="text-left px-4 py-2 font-medium">Quando</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditEvents.map((e, i) => (
                      <tr key={i} className="border-t">
                        <td className="px-4 py-2 font-mono text-xs text-gray-500">{e.correlation_id || '—'}</td>
                        <td className="px-4 py-2">{e.operation}</td>
                        <td className="px-4 py-2">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${e.status === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>{e.status}</span>
                        </td>
                        <td className="px-4 py-2">{e.records_processed ?? 0}</td>
                        <td className="px-4 py-2">{e.attempts ?? 1}</td>
                        <td className="px-4 py-2">{e.duration_ms != null ? `${e.duration_ms} ms` : '—'}</td>
                        <td className="px-4 py-2 text-gray-500">{e.actor || '—'}</td>
                        <td className="px-4 py-2 text-gray-500">{e.created_at ? new Date(e.created_at).toLocaleString('pt-BR') : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===== Configuração (administrativa) ===== */}
      {activeTab === 'config' && (<>
      {/* Guia Passo a Passo */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <button
          onClick={() => setShowGuide(!showGuide)}
          className="w-full flex items-center justify-between px-6 py-4 hover:bg-gray-50 transition-colors"
          data-testid="toggle-guide"
        >
          <div className="flex items-center gap-3">
            <Info className="h-5 w-5 text-blue-600" />
            <span className="font-semibold text-gray-900">Guia: Como Solicitar Acesso à API do MEC</span>
          </div>
          {showGuide ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
        </button>

        {showGuide && (
          <div className="px-6 pb-6 border-t">
            <div className="mt-4 space-y-4">
              <div className="flex gap-4">
                <div className="w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm">1</div>
                <div>
                  <h4 className="font-medium text-gray-900">Gerar Chave PGP</h4>
                  <p className="text-sm text-gray-600 mt-1">Crie um par de chaves PGP (pública e privada). A chave pública (.asc) será enviada ao MEC.</p>
                  <a href="https://www.youtube.com/watch?v=TGHoGHEICVE" target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 hover:underline flex items-center gap-1 mt-1">
                    <ExternalLink size={12} /> Tutorial em vídeo
                  </a>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm">2</div>
                <div>
                  <h4 className="font-medium text-gray-900">Enviar E-mail ao MEC</h4>
                  <p className="text-sm text-gray-600 mt-1">Envie para <strong>gestaopresente@mec.gov.br</strong> com:</p>
                  <ul className="text-sm text-gray-600 mt-1 list-disc ml-4 space-y-0.5">
                    <li>Chave PGP pública (arquivo .asc)</li>
                    <li>IP do servidor que fará as consultas</li>
                    <li>Nome completo, e-mail institucional, CPF, telefone e cargo do responsável</li>
                  </ul>
                  <button onClick={() => copyToClipboard('gestaopresente@mec.gov.br')} className="text-sm text-blue-600 hover:underline flex items-center gap-1 mt-1">
                    <Copy size={12} /> Copiar e-mail
                  </button>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm">3</div>
                <div>
                  <h4 className="font-medium text-gray-900">Receber Chaves do MEC</h4>
                  <p className="text-sm text-gray-600 mt-1">O MEC enviará duas chaves criptografadas: uma para homologação e outra para produção. Descriptografe-as com sua chave privada PGP.</p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm">4</div>
                <div>
                  <h4 className="font-medium text-gray-900">Configurar no SIGESC</h4>
                  <p className="text-sm text-gray-600 mt-1">Insira a chave de API recebida no formulário abaixo e selecione o ambiente.</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Configuração */}
      <div className="bg-white rounded-xl border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-6 flex items-center gap-2">
          <Settings className="h-5 w-5 text-gray-600" />
          Configuração da Integração
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Ambiente */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Ambiente</label>
            <select
              value={config?.environment || 'homologacao'}
              onChange={e => handleChange('environment', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
              data-testid="env-select"
            >
              <option value="homologacao">Homologação (Testes)</option>
              <option value="producao">Produção</option>
            </select>
          </div>

          {/* Chave API */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Key className="inline h-4 w-4 mr-1" />Chave de API
            </label>
            <input
              type="password"
              value={config?.api_key || ''}
              onChange={e => handleChange('api_key', e.target.value)}
              placeholder="Cole a chave de API recebida do MEC"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
              data-testid="api-key-input"
            />
          </div>

          {/* IP do Servidor */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Server className="inline h-4 w-4 mr-1" />IP do Servidor
            </label>
            <input
              type="text"
              value={config?.server_ip || ''}
              onChange={e => handleChange('server_ip', e.target.value)}
              placeholder="Ex: 192.168.1.100"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
              data-testid="server-ip-input"
            />
          </div>
        </div>

        {/* Dados do Responsável */}
        <h4 className="text-sm font-semibold text-gray-700 mt-6 mb-4">Dados do Responsável pela Integração</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1"><User className="inline h-3 w-3 mr-1" />Nome Completo</label>
            <input type="text" value={config?.responsible_name || ''} onChange={e => handleChange('responsible_name', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" data-testid="resp-name" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1"><Mail className="inline h-3 w-3 mr-1" />E-mail Institucional</label>
            <input type="email" value={config?.responsible_email || ''} onChange={e => handleChange('responsible_email', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" data-testid="resp-email" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">CPF</label>
            <input type="text" value={config?.responsible_cpf || ''} onChange={e => handleChange('responsible_cpf', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" data-testid="resp-cpf" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1"><Phone className="inline h-3 w-3 mr-1" />Telefone</label>
            <input type="text" value={config?.responsible_phone || ''} onChange={e => handleChange('responsible_phone', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" data-testid="resp-phone" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1"><Briefcase className="inline h-3 w-3 mr-1" />Cargo</label>
            <input type="text" value={config?.responsible_role || ''} onChange={e => handleChange('responsible_role', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" data-testid="resp-role" />
          </div>
        </div>

        {/* Botão Salvar */}
        <div className="mt-6 flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2 transition-colors"
            data-testid="save-config-btn"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
            Salvar Configuração
          </button>
        </div>
      </div>

      {/* Links Úteis */}
      <div className="bg-white rounded-xl border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Links Úteis</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <a href="https://api-cmde.hmg.gestaopresente.mec.gov.br/v1/documentation" target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 border rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-colors">
            <ExternalLink className="h-4 w-4 text-blue-600" />
            <div>
              <p className="font-medium text-sm text-gray-900">Swagger - Homologação</p>
              <p className="text-xs text-gray-500">Documentação interativa da API (ambiente de testes)</p>
            </div>
          </a>
          <a href="https://api-cmde.gestaopresente.mec.gov.br/v1/documentation" target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 border rounded-lg hover:bg-green-50 hover:border-green-300 transition-colors">
            <ExternalLink className="h-4 w-4 text-green-600" />
            <div>
              <p className="font-medium text-sm text-gray-900">Swagger - Produção</p>
              <p className="text-xs text-gray-500">Documentação interativa da API (ambiente de produção)</p>
            </div>
          </a>
        </div>
      </div>

      {/* Mapeamento de Dados */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <div className="px-6 py-4 flex items-center justify-between border-b">
          <h3 className="text-lg font-semibold text-gray-900">Mapeamento de Dados SIGESC → MEC</h3>
          <button
            onClick={loadMapping}
            disabled={loadingMapping}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 flex items-center gap-2 transition-colors"
            data-testid="load-mapping-btn"
          >
            {loadingMapping ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Verificar Dados
          </button>
        </div>

        {showMapping && mappingData && (
          <div>
            <div className="px-6 py-3 bg-gray-50 border-b flex items-center gap-6 text-sm">
              <span className="text-gray-600">Total: <strong>{mappingData.total}</strong></span>
              <span className="text-green-600">Prontos: <strong>{mappingData.ready_count}</strong></span>
              <span className="text-red-600">Incompletos: <strong>{mappingData.not_ready_count}</strong></span>
            </div>

            {mappingData.not_ready_count > 0 && (
              <div className="max-h-80 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="text-left px-6 py-2 text-xs text-gray-500 uppercase">Aluno</th>
                      <th className="text-left px-4 py-2 text-xs text-gray-500 uppercase">Escola</th>
                      <th className="text-left px-4 py-2 text-xs text-gray-500 uppercase">Campos Faltantes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {mappingData.students.filter(s => !s.ready).slice(0, 50).map(s => (
                      <tr key={s.id} className="hover:bg-gray-50">
                        <td className="px-6 py-2 font-medium text-gray-900">{s.full_name}</td>
                        <td className="px-4 py-2 text-gray-600">{s.school_name}</td>
                        <td className="px-4 py-2">
                          {s.missing_fields.map(f => (
                            <span key={f} className="inline-block px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs mr-1">{f}</span>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {showMapping && loadingMapping && (
          <div className="p-8 flex items-center justify-center">
            <Loader2 className="h-6 w-6 text-blue-500 animate-spin" />
            <span className="ml-3 text-gray-500">Verificando dados...</span>
          </div>
        )}
      </div>
      </>)}
    </div>
    </Layout>
  );
}
