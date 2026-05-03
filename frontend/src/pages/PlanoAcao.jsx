/**
 * Plano de Ação Automático — /admin/plano-acao
 *
 * Base determinística (5 regras fixas) + camada opcional de IA
 * (Claude Sonnet 4.5) que gera análise executiva, insight do histórico
 * do gestor nos últimos 90d e até 2 recomendações extras.
 */
import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import {
  ChevronLeft, AlertTriangle, Clock, Zap, CheckCircle2, ExternalLink, Info,
  Sparkles, RefreshCw, Brain, TrendingUp,
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
  const [aiEnabled, setAiEnabled] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    schoolsAPI.list().then(d => {
      setSchools(d || []);
      if (!schoolId && d?.length > 0) setSchoolId(d[0].id);
    }).catch(() => {});
  }, [schoolId]);

  const load = useCallback(async (forceRefresh = false) => {
    if (!schoolId) return;
    setLoading(true);
    if (aiEnabled) setAiLoading(true);
    try {
      const r = await axios.get(`${API}/intervencoes/plano-acao`, {
        params: {
          school_id: schoolId,
          period,
          ai: aiEnabled ? 'true' : 'false',
          force_refresh: forceRefresh ? 'true' : 'false',
        },
      });
      setPlan(r.data);
    } catch (e) {
      setPlan(null);
    } finally {
      setLoading(false);
      setAiLoading(false);
    }
  }, [schoolId, period, aiEnabled]);

  useEffect(() => { load(false); }, [load]);

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
            Base determinística (5 regras) + camada de IA (Claude Sonnet 4.5) com insight histórico do gestor. Máx. 5 ações priorizadas, executáveis e mensuráveis.
          </p>
        </div>
        <div className="flex gap-2 items-end flex-wrap">
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
          <button
            type="button"
            onClick={() => setAiEnabled(v => !v)}
            className={`px-3 py-2 text-sm rounded border inline-flex items-center gap-1.5 ${
              aiEnabled
                ? 'bg-indigo-600 text-white border-indigo-700 hover:bg-indigo-700'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
            }`}
            data-testid="plano-ai-toggle"
            title="Ativar/desativar enriquecimento com Claude Sonnet 4.5"
          >
            <Sparkles className="h-4 w-4" />
            IA {aiEnabled ? 'ligada' : 'desligada'}
          </button>
          {aiEnabled && plan?.ai_enriched && (
            <button
              type="button"
              onClick={() => load(true)}
              disabled={aiLoading}
              className="px-3 py-2 text-sm rounded border bg-white text-gray-700 border-gray-300 hover:bg-gray-50 inline-flex items-center gap-1.5 disabled:opacity-50"
              data-testid="plano-ai-refresh"
              title="Forçar nova análise IA (ignora cache de 24h)"
            >
              <RefreshCw className={`h-4 w-4 ${aiLoading ? 'animate-spin' : ''}`} />
              Regenerar IA
            </button>
          )}
        </div>
      </div>

      {loading && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-gray-500" data-testid="plano-loading">
          {aiEnabled ? 'Gerando plano + análise IA...' : 'Gerando plano...'}
        </div>
      )}

      {!loading && plan && (
        <>
          {/* Cabeçalho com score e classificação */}
          <div className={`border rounded-lg p-4 mb-4 ${classifStyle}`} data-testid="plano-header">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <div className="text-xs uppercase opacity-70">Escola</div>
                <div className="text-xl font-bold">{plan.school_name}</div>
                <div className="mt-2 flex items-center gap-4 text-xs flex-wrap">
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

          {/* Análise IA (se habilitada e disponível) */}
          {plan.ai_enriched && plan.ai && (
            <AiAnalysisCard plan={plan} />
          )}
          {aiEnabled && !plan.ai_enriched && !loading && (
            <div className="mb-4 border border-dashed border-gray-300 rounded-lg p-3 text-xs text-gray-500 flex items-center gap-2" data-testid="plano-ai-fallback">
              <Brain className="h-4 w-4" />
              IA indisponível no momento — exibindo apenas plano determinístico.
            </div>
          )}

          {/* Ações determinísticas */}
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
                <ActionCard key={a.ordem} action={a} aiEnabled={plan.ai_enriched} />
              ))}
            </div>
          )}

          {/* Recomendações extras da IA */}
          {plan.ai_enriched && plan.ai?.recomendacoes_extra?.length > 0 && (
            <div className="mt-4" data-testid="plano-ai-extras">
              <div className="text-sm font-semibold text-indigo-800 mb-2 flex items-center gap-1.5">
                <Sparkles className="h-4 w-4" />
                Recomendações adicionais da IA
              </div>
              <div className="space-y-3">
                {plan.ai.recomendacoes_extra.map((r, i) => (
                  <ExtraRecommendationCard key={i} rec={r} index={i} />
                ))}
              </div>
            </div>
          )}

          <div className="mt-6 text-xs text-gray-500 max-w-3xl flex items-start gap-2">
            <Info className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <div>
              Regras determinísticas (não-IA): cobertura &lt; 70% / Nível 3 ≥ 3 / taxa &lt; 60% / tempo &gt; 5d / lançamentos &lt; 70%.
              Plano gerado em {plan.generated_at ? new Date(plan.generated_at).toLocaleString('pt-BR') : '—'}.
              {plan.ai_enriched && plan.ai_generated_at && (
                <> · IA ({plan.ai_model}) em {new Date(plan.ai_generated_at).toLocaleString('pt-BR')}
                  {plan.ai_from_cache ? ` (cache ${plan.ai_cache_age_hours}h)` : ''}.
                </>
              )}
              <Link to="/admin/ranking-gestores" className="text-purple-700 underline ml-1">Ver ranking</Link>.
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function AiAnalysisCard({ plan }) {
  const ai = plan.ai || {};
  const gestor = plan.gestor_historico;
  return (
    <div className="mb-4 rounded-lg border border-indigo-200 bg-gradient-to-br from-indigo-50 to-white p-4" data-testid="plano-ai-analysis">
      <div className="flex items-center gap-2 text-indigo-800 text-sm font-semibold mb-2">
        <Brain className="h-4 w-4" />
        Análise executiva · Claude Sonnet 4.5
        {plan.ai_from_cache && (
          <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 border border-indigo-200">
            cache · {plan.ai_cache_age_hours}h
          </span>
        )}
      </div>
      {ai.analise_executiva && (
        <p className="text-sm text-gray-800 leading-relaxed mb-3" data-testid="plano-ai-summary">
          {ai.analise_executiva}
        </p>
      )}
      {ai.insight_historico && (
        <div className="bg-white/60 border border-indigo-100 rounded p-3 text-xs text-gray-700 flex items-start gap-2" data-testid="plano-ai-insight">
          <TrendingUp className="h-4 w-4 text-indigo-600 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold text-indigo-900 mb-0.5">
              Histórico do gestor (90 dias){gestor?.nome && gestor.nome !== 'Não definido' ? ` — ${gestor.nome}` : ''}
            </div>
            <div>{ai.insight_historico}</div>
            {gestor && gestor.received_90d > 0 && (
              <div className="mt-1.5 text-[11px] text-gray-500 flex gap-3 flex-wrap">
                <span>Alertas recebidos: <strong>{gestor.received_90d}</strong></span>
                <span>Resolvidos: <strong>{gestor.resolved_90d}</strong></span>
                {gestor.avg_resolution_days_90d != null && (
                  <span>Tempo médio próprio: <strong>{gestor.avg_resolution_days_90d}d</strong></span>
                )}
                {gestor.most_neglected_component && gestor.most_neglected_active_count > 0 && (
                  <span>Categoria + negligenciada: <strong>{gestor.most_neglected_component}</strong> ({gestor.most_neglected_active_count})</span>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ActionCard({ action, aiEnabled }) {
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
            {aiEnabled && action.descricao_ia && (
              <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 border border-indigo-200 uppercase font-semibold">
                <Sparkles className="h-3 w-3" /> IA
              </span>
            )}
          </div>
          <div className="text-base font-semibold text-gray-900 mb-0.5">
            {action.titulo}
          </div>
          <div className="text-sm text-gray-700 mb-2">
            {action.descricao_ia || action.descricao}
          </div>
          {action.descricao_ia && action.descricao !== action.descricao_ia && (
            <details className="text-[11px] text-gray-500 mb-2">
              <summary className="cursor-pointer">Ver descrição técnica original</summary>
              <div className="mt-1 pl-2 border-l-2 border-gray-200">{action.descricao}</div>
            </details>
          )}
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

function ExtraRecommendationCard({ rec, index }) {
  const impactClass = IMPACT_BADGE[rec.impacto] || IMPACT_BADGE.baixo;
  return (
    <div
      className="border rounded-lg p-4 border-indigo-300 bg-indigo-50/40"
      data-testid={`plano-ai-extra-${index}`}
    >
      <div className="flex items-center gap-2 flex-wrap mb-1">
        <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 border border-indigo-200 uppercase font-semibold">
          <Sparkles className="h-3 w-3" /> IA · Extra
        </span>
        <span className="text-xs font-bold text-gray-700 bg-white border border-gray-300 rounded-full px-2 py-0.5">
          Prioridade {rec.prioridade}
        </span>
        <span className={`text-[10px] px-2 py-0.5 rounded border ${impactClass} uppercase`}>
          Impacto {rec.impacto}
        </span>
        <span className="inline-flex items-center gap-1 text-[11px] text-gray-600">
          <Clock className="h-3 w-3" /> {rec.prazo_dias} dias
        </span>
        <span className="text-[11px] text-gray-500">
          Responsável: <strong className="text-gray-700 capitalize">{rec.responsavel}</strong>
        </span>
      </div>
      <div className="text-base font-semibold text-gray-900 mb-0.5">{rec.titulo}</div>
      <div className="text-sm text-gray-700 mb-2">{rec.descricao}</div>
      {rec.metrica_sucesso && (
        <div className="text-xs text-gray-500 flex items-start gap-1">
          <AlertTriangle className="h-3 w-3 mt-0.5 text-amber-600 flex-shrink-0" />
          <span><strong>Métrica de sucesso:</strong> {rec.metrica_sucesso}</span>
        </div>
      )}
    </div>
  );
}
