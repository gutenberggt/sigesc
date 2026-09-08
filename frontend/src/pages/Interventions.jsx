/**
 * Intervenções Curriculares — S5.5
 *
 * Feed informativo da Cobertura Curricular F5. Não há escalonamento punitivo:
 * após a tolerância inicial, <70% alerta; nos últimos 15 dias letivos, <=50%
 * é grave. O detalhe continua apontando para a Cobertura Curricular.
 */
import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { ChevronLeft, AlertTriangle, CheckCircle2, Info, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/contexts/AuthContext';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SEVERITY_META = {
  informativo: { label: 'Informativo', badge: 'bg-amber-50 text-amber-700 border-amber-200', icon: Info },
  grave: { label: 'Grave', badge: 'bg-red-100 text-red-800 border-red-300', icon: AlertTriangle },
};

export default function Interventions() {
  const { user } = useAuth();
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
        `Detecção: +${r.data.created || 0} novos, ${r.data.resolved || 0} resolvidos, ${r.data.notified_inapp || 0} notificações`,
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
    if (!window.confirm(`Marcar como resolvido o alerta de "${alert.componente_codigo} · ${alert.class_name}"? A próxima detecção reabre o alerta se a condição continuar.`)) return;
    try {
      await axios.post(`${API}/intervencoes/${alert.id}/resolve`);
      toast.success('Alerta marcado como resolvido');
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro');
    }
  };

  const items = data?.items || [];
  const summary = data?.summary || {};
  const canRun = ['super_admin', 'admin'].includes(user?.role);

  return (
    <div className="max-w-7xl mx-auto px-4 py-6" data-testid="interventions-page">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <Link to="/dashboard" className="inline-flex items-center text-sm text-gray-600 hover:text-purple-700 mb-2">
            <ChevronLeft className="h-4 w-4 mr-1" /> Voltar
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">📌 Alertas de Cobertura Curricular</h1>
          <p className="text-sm text-gray-500">
            Alertas informativos calculados pela Cobertura F5 e por dias letivos reais.
          </p>
        </div>
        {canRun && (
          <button
            onClick={runDetection}
            disabled={runningDetection}
            className="px-3 py-2 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700 disabled:opacity-60"
            data-testid="btn-run-detection"
          >
            {runningDetection ? 'Rodando...' : 'Atualizar alertas agora'}
          </button>
        )}
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 text-sm text-blue-800">
        Estes alertas têm caráter <strong>informativo e preventivo</strong>. Nos primeiros 15 dias letivos do bimestre há tolerância; depois, cobertura abaixo de 70% gera alerta. Nos últimos 15 dias letivos, cobertura de até 50% é classificada como grave.
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4" data-testid="interv-summary">
        <div className="bg-white border border-gray-200 rounded-lg p-3">
          <div className="text-xs text-gray-500">Alertas ativos</div>
          <div className="text-3xl font-bold text-gray-900">{summary.total_active ?? 0}</div>
        </div>
        <div className="bg-white border border-amber-200 rounded-lg p-3">
          <div className="text-xs text-amber-700">Informativos</div>
          <div className="text-3xl font-bold text-amber-700">{summary.informativo ?? 0}</div>
        </div>
        <div className="bg-white border border-red-300 rounded-lg p-3">
          <div className="text-xs text-red-700">Graves</div>
          <div className="text-3xl font-bold text-red-700">{summary.grave ?? 0}</div>
        </div>
      </div>

      {loading && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-gray-500">Carregando...</div>
      )}

      {!loading && items.length === 0 && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-6 flex items-center gap-3" data-testid="interv-empty">
          <CheckCircle2 className="h-8 w-8 text-emerald-600" />
          <div>
            <div className="font-semibold text-emerald-800">Nenhum alerta de cobertura ativo</div>
            <div className="text-xs text-emerald-700">Não há escopos F5 que atendam aos critérios de alerta neste momento.</div>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {items.map((it) => {
          const severity = it.severity || it.status || 'informativo';
          const meta = SEVERITY_META[severity] || SEVERITY_META.informativo;
          const MetaIcon = meta.icon;
          const link = `/admin/curriculo/cobertura?class_id=${it.class_id || ''}&component=${it.componente_codigo || ''}&ano=${it.ano || ''}&bim=${it.bimestre || ''}`;
          return (
            <div
              key={it.id}
              className="bg-white border border-gray-200 rounded-lg p-3 flex items-start justify-between gap-3"
              data-testid={`interv-row-${it.id.slice(0, 8)}`}
            >
              <div className="flex items-start gap-3 flex-1">
                <MetaIcon className={`h-5 w-5 mt-0.5 flex-shrink-0 ${severity === 'grave' ? 'text-red-600' : 'text-amber-600'}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-mono font-semibold text-purple-700">{it.componente_codigo || '—'}</span>
                    <span className="text-gray-700">·</span>
                    <span className="font-semibold text-gray-800 truncate">{it.class_name || '—'}</span>
                    <span className="text-gray-500 text-xs">
                      {it.ano != null ? `· ${it.ano}º ano` : ''} {it.bimestre != null ? `· ${it.bimestre}º bim.` : ''}
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded border ${meta.badge}`}>{meta.label}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500 mt-1">
                    <span><strong>{it.last_coverage_pct}%</strong> de cobertura F5</span>
                    <span>{it.instructional_days_elapsed ?? '—'} dias letivos decorridos</span>
                    <span>{it.instructional_days_remaining ?? '—'} dias letivos restantes</span>
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
                  data-testid={`interv-view-coverage-${it.id.slice(0, 8)}`}
                >
                  Ver cobertura <ExternalLink className="h-3 w-3" />
                </Link>
                <button
                  onClick={() => resolve(it)}
                  className="px-2 py-1 border border-gray-300 text-gray-600 rounded text-xs hover:bg-gray-50"
                  title="Marcar manualmente como resolvido"
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
