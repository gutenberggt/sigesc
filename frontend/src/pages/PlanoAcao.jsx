/**
 * Plano de Ação Automático — /admin/plano-acao
 *
 * Gerado por regras fixas a partir do score + cobertura + alertas + lançamentos.
 * Cada ação tem link direto para a página onde o gestor age em 1 clique.
 */
import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import {
  ChevronLeft, AlertTriangle, Clock, Zap, CheckCircle2, ExternalLink, Info,
} from 'lucide-react';
import { schoolsAPI } from '@/services/api';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const IMPACT_BADGE = {
  alto: 'bg-red-50 text-red-700 border-red-200',
  medio: 'bg-amber-50 text-amber-700 border-amber-200',
  baixo: 'bg-gray-50 text-gray-700 border-gray-200',
};

const CLASSIF_STYLE = {
  'Adequado': 'bg-emerald-50 text-emerald-800 border-emerald-200',
  'Atenção': 'bg-amber-50 text-amber-800 border-amber-200',
  'Crítico': 'bg-red-50 text-red-800 border-red-200',
};

export default function PlanoAcao() {
  const [schools, setSchools] = useState([]);
  const [schoolId, setSchoolId] = useState('');
  const [period, setPeriod] = useState('30d');
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    schoolsAPI.list().then(d => {
      setSchools(d || []);
      if (!schoolId && d?.length > 0) setSchoolId(d[0].id);
    }).catch(() => {});
  }, [schoolId]);

  const load = useCallback(async () => {
    if (!schoolId) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/intervencoes/plano-acao`, {
        params: { school_id: schoolId, period },
      });
      setPlan(r.data);
    } catch (e) {
      setPlan(null);
    } finally {
      setLoading(false);
    }
  }, [schoolId, period]);

  useEffect(() => { load(); }, [load]);

  const ctx = plan?.contexto || {};
  const classif = plan?.classificacao;
  const classifStyle = CLASSIF_STYLE[classif] || 'bg-gray-50 text-gray-700 border-gray-200';

  return (
    <div className="max-w-7xl mx-auto px-4 py-6" data-testid="plano-acao-page">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <Link to="/dashboard" className="inline-flex items-center text-sm text-gray-600 hover:text-purple-700 mb-2">
            <ChevronLeft className="h-4 w-4 mr-1" /> Voltar
          </Link>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Zap className="h-6 w-6 text-amber-500" />
            Plano de Ação Automático
          </h1>
          <p className="text-sm text-gray-500 max-w-3xl">
            Gerado por regras objetivas a partir dos dados reais do sistema. Máx. 5 ações priorizadas, executáveis e mensuráveis.
          </p>
        </div>
        <div className="flex gap-2 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Escola</label>
            <select
              className="border border-gray-300 rounded px-3 py-2 text-sm min-w-[240px]"
              value={schoolId}
              onChange={e => setSchoolId(e.target.value)}
              data-testid="plano-school"
            >
              {schools.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Período</label>
            <select
              className="border border-gray-300 rounded px-3 py-2 text-sm"
              value={period}
              onChange={e => setPeriod(e.target.value)}
              data-testid="plano-period"
            >
              <option value="7d">7 dias</option>
              <option value="30d">30 dias</option>
              <option value="60d">60 dias</option>
              <option value="90d">90 dias</option>
            </select>
          </div>
        </div>
      </div>

      {loading && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-gray-500">Gerando plano...</div>
      )}

      {!loading && plan && (
        <>
          {/* Cabeçalho com score e classificação */}
          <div className={`border rounded-lg p-4 mb-4 ${classifStyle}`} data-testid="plano-header">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <div className="text-xs uppercase opacity-70">Escola</div>
                <div className="text-xl font-bold">{plan.school_name}</div>
                <div className="mt-2 flex items-center gap-4 text-xs">
                  <span>Cobertura: <strong>{ctx.coverage_pct ?? 0}%</strong></span>
                  <span>Alertas: <strong>{ctx.received ?? 0}</strong> recebidos · <strong>{ctx.resolved ?? 0}</strong> resolvidos · <strong>{ctx.active ?? 0}</strong> ativos</span>
                  {ctx.level_3_active > 0 && <span className="text-red-700 font-semibold">⚠ {ctx.level_3_active} Nível 3 ativos</span>}
                  {ctx.avg_resolution_days != null && <span>Tempo médio: <strong>{ctx.avg_resolution_days}d</strong></span>}
                  <span>Lançamentos: <strong>{Math.round((ctx.lancamento_rate ?? 1) * 100)}%</strong> da meta</span>
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs uppercase opacity-70">Score</div>
                <div className="text-4xl font-bold">{plan.score}</div>
                <div className="text-xs font-semibold mt-1">{classif}</div>
              </div>
            </div>
          </div>

          {/* Ações */}
          {plan.acoes.length === 0 ? (
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-6 flex items-center gap-3" data-testid="plano-empty">
              <CheckCircle2 className="h-8 w-8 text-emerald-600" />
              <div>
                <div className="font-semibold text-emerald-800">Nenhuma ação recomendada</div>
                <div className="text-xs text-emerald-700">Indicadores dentro dos parâmetros esperados para esta escola.</div>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {plan.acoes.map(a => (
                <ActionCard key={a.ordem} action={a} />
              ))}
            </div>
          )}

          <div className="mt-6 text-xs text-gray-500 max-w-3xl flex items-start gap-2">
            <Info className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <div>
              Regras determinísticas (não-IA): cobertura &lt; 70% / Nível 3 ≥ 3 / taxa &lt; 60% / tempo &gt; 5d / lançamentos &lt; 70%.
              Plano gerado em {plan.generated_at ? new Date(plan.generated_at).toLocaleString('pt-BR') : '—'}.
              <Link to="/admin/ranking-gestores" className="text-purple-700 underline ml-1">Ver ranking</Link>.
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ActionCard({ action }) {
  const impactClass = IMPACT_BADGE[action.impacto] || IMPACT_BADGE.baixo;
  const prioClass = action.prioridade === 1
    ? 'border-red-300 bg-red-50/30'
    : action.prioridade === 2
      ? 'border-amber-300 bg-amber-50/30'
      : 'border-gray-300 bg-white';

  return (
    <div
      className={`border rounded-lg p-4 ${prioClass}`}
      data-testid={`plano-action-${action.ordem}`}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-xs font-bold text-gray-700 bg-white border border-gray-300 rounded-full px-2 py-0.5">
              #{action.ordem} · Prioridade {action.prioridade}
            </span>
            <span className={`text-[10px] px-2 py-0.5 rounded border ${impactClass} uppercase`}>
              Impacto {action.impacto}
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] text-gray-600">
              <Clock className="h-3 w-3" /> {action.prazo_dias} dias
            </span>
            <span className="text-[11px] text-gray-500">
              Responsável: <strong className="text-gray-700 capitalize">{action.responsavel}</strong>
            </span>
          </div>
          <div className="text-base font-semibold text-gray-900 mb-0.5">
            {action.titulo}
          </div>
          <div className="text-sm text-gray-700 mb-2">{action.descricao}</div>
          <div className="text-xs text-gray-500 flex items-start gap-1">
            <AlertTriangle className="h-3 w-3 mt-0.5 text-amber-600 flex-shrink-0" />
            <span><strong>Métrica de sucesso:</strong> {action.metrica_sucesso}</span>
          </div>
        </div>
        {action.link && (
          <Link
            to={action.link}
            className="inline-flex items-center gap-1 px-3 py-2 bg-purple-600 text-white rounded text-xs hover:bg-purple-700 font-semibold"
            data-testid={`plano-action-go-${action.ordem}`}
          >
            Agir agora <ExternalLink className="h-3 w-3" />
          </Link>
        )}
      </div>
    </div>
  );
}
