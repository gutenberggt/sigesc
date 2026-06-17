/**
 * Relatório Executivo Mensal — /admin/relatorios-mensais
 *
 * Sprint G3 (Fev/2026): produto dentro do produto.
 *
 *   - Lista cards por mês com nível de risco e KPIs essenciais
 *   - Botão Gerar (manual) para o mês anterior ou outro período
 *   - Visualizar PDF executivo · auditor
 *   - Verificar publicamente via QR / código SIGESC
 *   - Reenviar email-gatilho aos gestores
 *
 * Toda saída tem snapshot imutável (G1.5) + código verificável (G1.6) + 30d
 * de validade do link público.
 */
import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import {
  ChevronLeft, FileText, Download, Send, RefreshCw, ShieldCheck,
  AlertTriangle, AlertCircle, CheckCircle2, Loader2, X, Calendar,
  Mail, Hash, ArrowUpRight, ChevronDown, ChevronUp, TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { useProgressTask } from '@/contexts/ProgressContext';
import { downloadBlobWithProgress } from '@/utils/downloadBlob';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const MES_NOMES = [
  '', 'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
];

const RISK_STYLE = {
  alto: { label: 'ALTO', icon: AlertCircle, bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200', pill: 'bg-red-600' },
  medio: { label: 'MÉDIO', icon: AlertTriangle, bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', pill: 'bg-amber-600' },
  baixo: { label: 'BAIXO', icon: CheckCircle2, bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', pill: 'bg-emerald-600' },
};

function previousMonth() {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

function formatPct(v) {
  if (v === null || v === undefined) return '—';
  return `${Number(v).toFixed(1)}%`;
}

export default function MonthlyReports() {
  const progress = useProgressTask();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [emailModal, setEmailModal] = useState(null); // {report, recipients, sending}
  const [periodInput, setPeriodInput] = useState(previousMonth());
  const [toast, setToast] = useState(null);

  const showToast = (kind, msg) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 4000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/monthly-reports?limit=24`);
      setItems(r.data?.items || []);
    } catch (e) {
      showToast('error', e.response?.data?.detail || 'Erro ao carregar relatórios');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleGenerate = async (force = false) => {
    setGenerating(true);
    try {
      const r = await axios.post(`${API}/monthly-reports/generate`, {
        year: Number(periodInput.year),
        month: Number(periodInput.month),
        force,
      });
      const cached = r.data?.from_cache;
      showToast('success', cached
        ? `Relatório de ${periodInput.month}/${periodInput.year} já existia (cache)`
        : `Relatório de ${periodInput.month}/${periodInput.year} gerado com sucesso`);
      await load();
      setExpandedId(r.data?.id || null);
    } catch (e) {
      showToast('error', e.response?.data?.detail || 'Falha ao gerar relatório');
    } finally {
      setGenerating(false);
    }
  };

  const handleDownloadPdf = async (id, mode) => {
    try {
      await downloadBlobWithProgress({
        url: `${API}/monthly-reports/${id}/pdf?mode=${mode}`,
        filename: `relatorio-${id.slice(0, 8)}-${mode}.pdf`,
        progress,
        title: 'Gerando Relatório SEMED',
      });
    } catch (e) {
      showToast('error', e?.message || 'Falha ao baixar PDF');
    }
  };

  const handleSendEmail = async () => {
    if (!emailModal) return;
    const recipients = emailModal.recipients
      .split(/[\s,;]+/)
      .map(s => s.trim())
      .filter(s => s && s.includes('@'));
    if (recipients.length === 0) {
      showToast('error', 'Informe ao menos 1 e-mail válido');
      return;
    }
    setEmailModal({ ...emailModal, sending: true });
    try {
      const r = await axios.post(
        `${API}/monthly-reports/${emailModal.report.id}/send-email`,
        { recipients }
      );
      showToast('success', `${r.data?.sent_count || 0} e-mail(s) enviados`);
      setEmailModal(null);
      await load();
    } catch (e) {
      showToast('error', e.response?.data?.detail || 'Falha ao enviar emails');
      setEmailModal({ ...emailModal, sending: false });
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-slate-950 text-gray-900 dark:text-slate-100">
      {/* Toast */}
      {toast && (
        <div
          data-testid="monthly-report-toast"
          className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg max-w-sm text-sm font-medium ${
            toast.kind === 'success'
              ? 'bg-emerald-600 text-white'
              : 'bg-red-600 text-white'
          }`}
        >
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-800 sticky top-0 z-30 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center gap-3">
          <Link
            to="/dashboard"
            data-testid="monthly-reports-back-link"
            className="p-2 hover:bg-gray-100 dark:hover:bg-slate-800 rounded-lg transition"
          >
            <ChevronLeft className="w-5 h-5" />
          </Link>
          <div className="flex-1">
            <h1 className="text-xl font-bold">Relatórios Executivos Mensais</h1>
            <p className="text-xs text-gray-500 dark:text-slate-400">
              Diagnóstico institucional auditável · IA Claude 4.5 + Snapshot HMAC + QR público
            </p>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Painel de geração */}
        <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h2 className="font-semibold text-base flex items-center gap-2">
                <Calendar className="w-4 h-4 text-indigo-600" />
                Gerar relatório de um período
              </h2>
              <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
                Idempotente: chamar 2× no mesmo período retorna o mesmo snapshot.
                Use <strong>regerar</strong> apenas se houve correção retroativa.
              </p>
            </div>
            <div className="flex items-end gap-3">
              <div>
                <label className="text-xs text-gray-500 dark:text-slate-400 block mb-1">Ano</label>
                <input
                  data-testid="monthly-reports-year-input"
                  type="number"
                  min="2020"
                  max="2100"
                  value={periodInput.year}
                  onChange={(e) => setPeriodInput({ ...periodInput, year: e.target.value })}
                  className="w-24 px-3 py-2 rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 dark:text-slate-400 block mb-1">Mês</label>
                <select
                  data-testid="monthly-reports-month-input"
                  value={periodInput.month}
                  onChange={(e) => setPeriodInput({ ...periodInput, month: e.target.value })}
                  className="px-3 py-2 rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-sm"
                >
                  {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                    <option key={m} value={m}>{MES_NOMES[m]}</option>
                  ))}
                </select>
              </div>
              <button
                data-testid="monthly-reports-generate-btn"
                onClick={() => handleGenerate(false)}
                disabled={generating}
                className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium disabled:opacity-60 inline-flex items-center gap-2"
              >
                {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowUpRight className="w-4 h-4" />}
                Gerar
              </button>
              <button
                data-testid="monthly-reports-regenerate-btn"
                onClick={() => handleGenerate(true)}
                disabled={generating}
                title="Força nova análise (cria novo snapshot)"
                className="px-3 py-2 rounded-lg border border-gray-300 dark:border-slate-700 hover:bg-gray-50 dark:hover:bg-slate-800 text-sm inline-flex items-center gap-2"
              >
                <RefreshCw className="w-4 h-4" />
                Regerar
              </button>
            </div>
          </div>
        </div>

        {/* Lista */}
        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-500">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="bg-white dark:bg-slate-900 border border-dashed border-gray-300 dark:border-slate-700 rounded-xl p-12 text-center">
            <FileText className="w-12 h-12 mx-auto text-gray-300 dark:text-slate-700" />
            <h3 className="mt-4 font-semibold">Nenhum relatório ainda</h3>
            <p className="text-sm text-gray-500 dark:text-slate-400 mt-1">
              Gere o primeiro relatório executivo do mês passado usando o painel acima.
            </p>
          </div>
        ) : (
          <div className="grid gap-4">
            {items.map((r) => (
              <ReportCard
                key={r.id}
                report={r}
                expanded={expandedId === r.id}
                onToggle={() => setExpandedId(expandedId === r.id ? null : r.id)}
                onPdf={(mode) => handleDownloadPdf(r.id, mode)}
                onSendEmail={() => setEmailModal({ report: r, recipients: '', sending: false })}
              />
            ))}
          </div>
        )}
      </div>

      {/* Modal envio email */}
      {emailModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 rounded-xl shadow-2xl max-w-lg w-full p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="font-bold text-lg flex items-center gap-2">
                  <Mail className="w-5 h-5 text-indigo-600" />
                  Enviar gatilho de ação
                </h3>
                <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
                  Email com 3 ações prioritárias e link para o diagnóstico completo
                </p>
              </div>
              <button
                data-testid="monthly-reports-email-close"
                onClick={() => setEmailModal(null)}
                className="p-1 hover:bg-gray-100 dark:hover:bg-slate-800 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <label className="text-xs text-gray-500 dark:text-slate-400 block mb-1">
              Destinatários (separe por vírgula ou linha)
            </label>
            <textarea
              data-testid="monthly-reports-email-recipients"
              value={emailModal.recipients}
              onChange={(e) => setEmailModal({ ...emailModal, recipients: e.target.value })}
              rows={4}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-sm font-mono"
              placeholder="secretario@municipio.gov.br&#10;diretor1@escola.edu.br"
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => setEmailModal(null)}
                className="px-4 py-2 rounded-lg text-sm hover:bg-gray-100 dark:hover:bg-slate-800"
              >
                Cancelar
              </button>
              <button
                data-testid="monthly-reports-email-send"
                onClick={handleSendEmail}
                disabled={emailModal.sending}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium inline-flex items-center gap-2 disabled:opacity-60"
              >
                {emailModal.sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                Enviar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ReportCard({ report, expanded, onToggle, onPdf, onSendEmail }) {
  const risk = RISK_STYLE[report.risco] || RISK_STYLE.medio;
  const RiskIcon = risk.icon;
  const summary = report.rede_summary || {};
  const ai = report.ai || {};
  const verifyUrl = report.verification_code
    ? `${window.location.origin}/verificar/${report.verification_code}`
    : null;

  return (
    <div
      data-testid={`monthly-report-card-${report.id}`}
      className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl shadow-sm overflow-hidden"
    >
      <div className="p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full ${risk.bg} ${risk.text} text-xs font-bold uppercase tracking-wide border ${risk.border}`}>
                <RiskIcon className="w-3.5 h-3.5" />
                Risco {risk.label}
              </span>
              <h3 className="text-lg font-bold">
                {MES_NOMES[report.month]?.toUpperCase()} / {report.year}
              </h3>
              {report.email_sent_at && (
                <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                  <Mail className="w-3.5 h-3.5" /> Enviado
                </span>
              )}
            </div>
            <p className="text-sm text-gray-600 dark:text-slate-400 mt-2 line-clamp-2">
              {summary.mantenedora_nome || 'Rede'} ·
              <strong className="text-gray-900 dark:text-slate-100"> {summary.total_escolas ?? 0}</strong> escolas ·
              <strong className="text-gray-900 dark:text-slate-100"> {summary.total_alunos ?? 0}</strong> alunos
            </p>
            <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-slate-400 mt-2 flex-wrap">
              <span className="inline-flex items-center gap-1">
                <TrendingUp className="w-3.5 h-3.5" />
                Frequência {formatPct(summary.frequencia_media_pct)}
              </span>
              <span className="inline-flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Cobertura {formatPct(summary.cobertura_curricular_media_pct)}
              </span>
              <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                <TrendingDown className="w-3.5 h-3.5" />
                {summary.escolas_com_alertas_ativos ?? 0} escolas com alertas
              </span>
              {report.verification_code && (
                <span className="inline-flex items-center gap-1 font-mono text-indigo-600 dark:text-indigo-400">
                  <Hash className="w-3.5 h-3.5" />
                  {report.verification_code}
                </span>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-2 shrink-0">
            <button
              data-testid={`monthly-report-toggle-${report.id}`}
              onClick={onToggle}
              className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-slate-700 hover:bg-gray-50 dark:hover:bg-slate-800 text-xs font-medium inline-flex items-center gap-1"
            >
              {expanded ? <><ChevronUp className="w-3.5 h-3.5" /> Recolher</> : <><ChevronDown className="w-3.5 h-3.5" /> Detalhes</>}
            </button>
            <div className="flex gap-2">
              <button
                data-testid={`monthly-report-pdf-exec-${report.id}`}
                onClick={() => onPdf('executive')}
                className="flex-1 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium inline-flex items-center justify-center gap-1"
              >
                <Download className="w-3.5 h-3.5" />
                PDF Exec.
              </button>
              <button
                data-testid={`monthly-report-pdf-aud-${report.id}`}
                onClick={() => onPdf('auditor')}
                title="PDF para auditoria com payload técnico anexo"
                className="px-3 py-1.5 rounded-lg border border-indigo-300 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-950 text-xs font-medium inline-flex items-center gap-1"
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                Auditor
              </button>
            </div>
            <div className="flex gap-2">
              <button
                data-testid={`monthly-report-email-${report.id}`}
                onClick={onSendEmail}
                className="flex-1 px-3 py-1.5 rounded-lg border border-gray-300 dark:border-slate-700 hover:bg-gray-50 dark:hover:bg-slate-800 text-xs font-medium inline-flex items-center justify-center gap-1"
              >
                <Send className="w-3.5 h-3.5" />
                Enviar
              </button>
              {verifyUrl && (
                <a
                  data-testid={`monthly-report-verify-${report.id}`}
                  href={verifyUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-3 py-1.5 rounded-lg border border-emerald-300 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-950 text-xs font-medium inline-flex items-center gap-1"
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  Verificar
                </a>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Conteúdo expandido */}
      {expanded && (
        <div className="border-t border-gray-200 dark:border-slate-800 bg-gray-50 dark:bg-slate-950/50 p-5 space-y-5">
          {/* Resumo */}
          {ai.resumo_executivo && (
            <section>
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-slate-400 mb-2">
                Resumo executivo
              </h4>
              <p className="text-sm leading-relaxed text-gray-800 dark:text-slate-200">
                {ai.resumo_executivo}
              </p>
            </section>
          )}

          {/* Ranking */}
          {ai.ranking && (
            <section className="grid md:grid-cols-2 gap-4">
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 mb-2 flex items-center gap-1">
                  <TrendingUp className="w-3.5 h-3.5" />
                  Top 5 escolas
                </h4>
                <ul className="space-y-2">
                  {(ai.ranking.top5 || []).map((s, i) => (
                    <li key={i} className="text-sm border border-emerald-200 dark:border-emerald-900 rounded-lg p-2.5 bg-emerald-50/50 dark:bg-emerald-950/20">
                      <div className="flex justify-between items-start gap-2">
                        <strong className="font-semibold text-gray-900 dark:text-slate-100">{s.escola}</strong>
                        <span className="px-2 py-0.5 rounded text-xs font-bold bg-emerald-600 text-white">{s.score}</span>
                      </div>
                      <p className="text-xs text-gray-600 dark:text-slate-400 mt-1">{s.destaque}</p>
                    </li>
                  ))}
                  {(!ai.ranking.top5 || ai.ranking.top5.length === 0) && (
                    <li className="text-xs text-gray-500 italic">Sem ranking disponível</li>
                  )}
                </ul>
              </div>
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-red-600 dark:text-red-400 mb-2 flex items-center gap-1">
                  <TrendingDown className="w-3.5 h-3.5" />
                  Bottom 3 — atenção
                </h4>
                <ul className="space-y-2">
                  {(ai.ranking.bottom3 || []).map((s, i) => (
                    <li key={i} className="text-sm border border-red-200 dark:border-red-900 rounded-lg p-2.5 bg-red-50/50 dark:bg-red-950/20">
                      <div className="flex justify-between items-start gap-2">
                        <strong className="font-semibold text-gray-900 dark:text-slate-100">{s.escola}</strong>
                        <span className="px-2 py-0.5 rounded text-xs font-bold bg-red-600 text-white">{s.score}</span>
                      </div>
                      <p className="text-xs text-gray-600 dark:text-slate-400 mt-1">{s.alerta}</p>
                    </li>
                  ))}
                  {(!ai.ranking.bottom3 || ai.ranking.bottom3.length === 0) && (
                    <li className="text-xs text-gray-500 italic">Nenhuma escola crítica</li>
                  )}
                </ul>
              </div>
            </section>
          )}

          {/* Diagnóstico */}
          {ai.diagnostico_causal && (
            <section>
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-slate-400 mb-2">
                Diagnóstico causal
              </h4>
              <p className="text-sm leading-relaxed text-gray-800 dark:text-slate-200 whitespace-pre-line">
                {ai.diagnostico_causal}
              </p>
            </section>
          )}

          {/* Ações prioritárias */}
          {ai.acoes_prioritarias && ai.acoes_prioritarias.length > 0 && (
            <section>
              <h4 className="text-xs font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-2">
                3 ações prioritárias
              </h4>
              <ol className="space-y-2">
                {ai.acoes_prioritarias.map((a, i) => (
                  <li key={i} className="border border-indigo-200 dark:border-indigo-900 rounded-lg p-3 bg-white dark:bg-slate-900">
                    <div className="flex items-start gap-2 flex-wrap">
                      <span className="px-2 py-0.5 rounded bg-indigo-600 text-white text-xs font-bold shrink-0">{i + 1}</span>
                      <strong className="font-semibold text-sm text-gray-900 dark:text-slate-100 flex-1 min-w-0">
                        {a.acao}
                      </strong>
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                        a.impacto === 'alto' ? 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300'
                        : a.impacto === 'medio' ? 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300'
                        : 'bg-gray-100 text-gray-700 dark:bg-slate-800 dark:text-slate-300'
                      }`}>
                        {a.impacto}
                      </span>
                    </div>
                    <p className="text-xs text-gray-600 dark:text-slate-400 mt-2">{a.justificativa}</p>
                    <div className="flex items-center gap-3 mt-2 text-xs text-gray-500 dark:text-slate-400">
                      <span>Prazo: <strong>{a.prazo_dias} dias</strong></span>
                      <span>Responsável: <strong className="capitalize">{(a.responsavel || '').replace('_', ' ')}</strong></span>
                      {a.escolas_alvo && a.escolas_alvo.length > 0 && (
                        <span className="truncate" title={a.escolas_alvo.join(', ')}>
                          Escolas-alvo: {a.escolas_alvo.length}
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {/* Selo de integridade */}
          <section className="text-xs text-gray-500 dark:text-slate-500 border-t border-gray-200 dark:border-slate-800 pt-3 flex items-center gap-2 flex-wrap">
            <ShieldCheck className="w-3.5 h-3.5 text-indigo-500" />
            Snapshot imutável <code className="font-mono text-[10px]">{(report.snapshot_id || '').slice(0, 8)}</code>
            · IA <code className="font-mono text-[10px]">{report.model}</code>
            · Emitido <strong>{new Date(report.created_at).toLocaleString('pt-BR')}</strong>
          </section>
        </div>
      )}
    </div>
  );
}
