/**
 * Interventions Feed — /admin/intervencoes
 *
 * Lista intervenções ativas ordenadas por severidade + antiguidade.
 * Cada item tem botão "Resolver agora" (link direto para o slot).
 */
import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { ChevronLeft, AlertTriangle, CheckCircle2, TrendingUp, Clock, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_META = {
  em_risco: { label: 'Em risco', badge: 'bg-amber-50 text-amber-700 border-amber-200', icon: TrendingUp },
  nao_cumpre: { label: 'Não cumprirá', badge: 'bg-red-50 text-red-700 border-red-200', icon: AlertTriangle },
  fechado_critico: { label: 'Bimestre fechado <90%', badge: 'bg-red-100 text-red-800 border-red-300', icon: AlertTriangle },
};

const LEVEL_META = {
  1: { label: 'Coordenação', color: 'bg-amber-100 text-amber-700' },
  2: { label: 'Direção', color: 'bg-orange-100 text-orange-700' },
  3: { label: 'Secretaria', color: 'bg-red-100 text-red-800' },
};

export default function Interventions() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [runningDetection, setRunningDetection] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/intervencoes`);
      setData(r.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const runDetection = async () => {
    setRunningDetection(true);
    try {
      const r = await axios.post(`${API}/intervencoes/run-detection`);
      toast.success(
        `Detecção: +${r.data.created} criados, ${r.data.resolved} resolvidos, ${r.data.notified_inapp} notificações`,
        { duration: 8000 },
      );
      load();
    } catch {
      toast.error('Falha ao rodar detecção');
    } finally {
      setRunningDetection(false);
    }
  };

  const resolve = async (alert) => {
    if (!window.confirm(`Marcar como resolvido "${alert.componente_codigo} · ${alert.class_name}"? (o sistema vai verificar automaticamente na próxima rodada)`)) return;
    try {
      await axios.post(`${API}/intervencoes/${alert.id}/resolve`);
      toast.success('Marcado como resolvido');
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro');
    }
  };

  const items = data?.items || [];
  const summary = data?.summary || {};

  const weeksSince = (iso) => {
    if (!iso) return 0;
    try {
      const d = new Date(iso);
      const diff = (Date.now() - d.getTime()) / (1000 * 60 * 60 * 24 * 7);
      return Math.max(Math.floor(diff), 0);
    } catch { return 0; }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6" data-testid="interventions-page">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <Link to="/dashboard" className="inline-flex items-center text-sm text-gray-600 hover:text-purple-700 mb-2">
            <ChevronLeft className="h-4 w-4 mr-1" /> Voltar
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">📌 Intervenções Necessárias</h1>
          <p className="text-sm text-gray-500">
            O sistema identifica turmas em risco e cobra a ação da gestão semanalmente.
          </p>
        </div>
        <button
          onClick={runDetection}
          disabled={runningDetection}
          className="px-3 py-2 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700 disabled:opacity-60"
          data-testid="btn-run-detection"
        >
          {runningDetection ? 'Rodando...' : 'Rodar detecção agora'}
        </button>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4" data-testid="interv-summary">
        <div className="bg-white border border-gray-200 rounded-lg p-3">
          <div className="text-xs text-gray-500">Ativas</div>
          <div className="text-3xl font-bold text-gray-900">{summary.total_active ?? 0}</div>
        </div>
        <div className="bg-white border border-red-200 rounded-lg p-3">
          <div className="text-xs text-red-600">Críticas (não cumprirá / fechado)</div>
          <div className="text-3xl font-bold text-red-600">{summary.critical ?? 0}</div>
        </div>
        <div className="bg-white border border-red-300 rounded-lg p-3">
          <div className="text-xs text-red-700">Nível 3 — Secretaria</div>
          <div className="text-3xl font-bold text-red-700">{summary.level_3 ?? 0}</div>
        </div>
      </div>

      {loading && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-gray-500">Carregando...</div>
      )}

      {!loading && items.length === 0 && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-6 flex items-center gap-3" data-testid="interv-empty">
          <CheckCircle2 className="h-8 w-8 text-emerald-600" />
          <div>
            <div className="font-semibold text-emerald-800">Nenhuma intervenção pendente</div>
            <div className="text-xs text-emerald-700">Todas as turmas/componentes estão em ritmo adequado.</div>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {items.map((it) => {
          const meta = STATUS_META[it.status] || STATUS_META.em_risco;
          const MetaIcon = meta.icon;
          const level = LEVEL_META[it.escalation_level] || LEVEL_META[1];
          const weeks = weeksSince(it.first_detected_at);
          const link = `/admin/curriculo/cobertura?class_id=${it.class_id || ''}&component=${it.componente_codigo || ''}&ano=${it.ano || ''}&bim=${it.bimestre || ''}`;
          return (
            <div
              key={it.id}
              className="bg-white border border-gray-200 rounded-lg p-3 flex items-start justify-between gap-3"
              data-testid={`interv-row-${it.id.slice(0, 8)}`}
            >
              <div className="flex items-start gap-3 flex-1">
                <MetaIcon className={`h-5 w-5 mt-0.5 flex-shrink-0 ${it.status === 'em_risco' ? 'text-amber-600' : 'text-red-600'}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-mono font-semibold text-purple-700">{it.componente_codigo || '—'}</span>
                    <span className="text-gray-700">·</span>
                    <span className="font-semibold text-gray-800 truncate">{it.class_name || '—'}</span>
                    <span className="text-gray-500 text-xs">
                      {it.ano != null ? `· ${it.ano}º ano` : ''} {it.bimestre != null ? `· ${it.bimestre}º bim.` : ''}
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded border ${meta.badge}`}>{meta.label}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded ${level.color}`}>Nível {it.escalation_level} · {level.label}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500 mt-1">
                    <span><strong>{it.last_coverage_pct}%</strong> cobertura</span>
                    <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" />{weeks} semana{weeks === 1 ? '' : 's'} sem resolver</span>
                    {it.last_notified_at && (
                      <span className="text-gray-400">Último aviso: {new Date(it.last_notified_at).toLocaleDateString('pt-BR')}</span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex gap-1 flex-shrink-0">
                <Link
                  to={link}
                  className="inline-flex items-center gap-1 px-3 py-1 bg-purple-600 text-white rounded text-xs hover:bg-purple-700"
                  data-testid={`interv-resolve-now-${it.id.slice(0, 8)}`}
                >
                  Resolver agora <ExternalLink className="h-3 w-3" />
                </Link>
                <button
                  onClick={() => resolve(it)}
                  className="px-2 py-1 border border-gray-300 text-gray-600 rounded text-xs hover:bg-gray-50"
                  title="Marcar manualmente como resolvida"
                  data-testid={`interv-mark-resolved-${it.id.slice(0, 8)}`}
                >
                  ✓
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
