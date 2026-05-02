/**
 * Ranking de Gestores — /admin/ranking-gestores
 *
 * Accountability real: tempo médio de resolução + taxa + backlog + score ponderado.
 * Super_admin/admin/secretário veem tudo. Diretor/coordenador veem apenas a própria escola.
 */
import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { ChevronLeft, Trophy, AlertTriangle, Info } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PERIOD_OPTIONS = [
  { v: '7d', label: '7 dias' },
  { v: '30d', label: '30 dias' },
  { v: '60d', label: '60 dias' },
  { v: '90d', label: '90 dias' },
  { v: 'all', label: 'Todo o período' },
];

const SCORE_COLOR = (s) => {
  if (s >= 80) return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  if (s >= 60) return 'text-amber-700 bg-amber-50 border-amber-200';
  return 'text-red-700 bg-red-50 border-red-200';
};

const MEDALS = ['🥇', '🥈', '🥉'];

export default function RankingGestores() {
  const [period, setPeriod] = useState('30d');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/intervencoes/ranking`, { params: { period } });
      setData(r.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => { load(); }, [load]);

  const rows = data?.rows || [];
  const bottom3 = rows.slice(-3).map(r => r.school_id);
  const self = data?.self;
  const hasFullAccess = data?.full_access;

  return (
    <div className="max-w-7xl mx-auto px-4 py-6" data-testid="ranking-page">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <Link to="/dashboard" className="inline-flex items-center text-sm text-gray-600 hover:text-purple-700 mb-2">
            <ChevronLeft className="h-4 w-4 mr-1" /> Voltar
          </Link>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Trophy className="h-6 w-6 text-amber-500" />
            Ranking de Gestão Curricular
          </h1>
          <p className="text-sm text-gray-500 max-w-3xl">
            Mede velocidade de resposta e resolução de intervenções. Score pondera tempo médio, taxa de resolução e backlog.
            <span className="ml-1 inline-flex items-center gap-1 text-xs text-purple-700" title="score = (100 - tempo_médio_dias × 5) × 50% + taxa_resolução × 40% − backlog × 2">
              <Info className="h-3 w-3" /> como é calculado?
            </span>
          </p>
        </div>
        <select
          className="border border-gray-300 rounded px-3 py-2 text-sm"
          value={period}
          onChange={e => setPeriod(e.target.value)}
          data-testid="rk-period"
        >
          {PERIOD_OPTIONS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
        </select>
      </div>

      {/* Aviso de escopo (não-admin) */}
      {!hasFullAccess && (
        <div className="flex items-start gap-2 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 mb-4 text-xs text-blue-800">
          <Info className="h-4 w-4 mt-0.5 flex-shrink-0" />
          <div>
            Você vê apenas o desempenho da sua escola. O ranking completo é restrito à Secretaria/Administração.
          </div>
        </div>
      )}

      {/* Self (resumo próprio) */}
      {self && (
        <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4" data-testid="rk-self">
          <div className="text-xs text-gray-500">Seu desempenho ({period})</div>
          <div className="flex items-center flex-wrap gap-4 mt-1">
            <span className="text-2xl font-bold text-gray-900">{self.school_name}</span>
            <span className={`px-2 py-0.5 rounded border text-sm font-semibold ${SCORE_COLOR(self.weighted_score)}`}>
              Score {self.weighted_score}
            </span>
            <span className="text-xs text-gray-500">
              {self.num_classes} turmas · {self.resolved}/{self.received} resolvidos
              {self.avg_resolution_days != null && <> · média {self.avg_resolution_days}d</>}
            </span>
          </div>
        </div>
      )}

      {loading && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-gray-500">Calculando ranking...</div>
      )}

      {!loading && hasFullAccess && rows.length === 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-gray-500" data-testid="rk-empty">
          Nenhum dado no período. Rode a detecção em <Link to="/admin/intervencoes" className="text-purple-700 underline">Intervenções</Link>.
        </div>
      )}

      {/* Tabela — apenas full_access */}
      {hasFullAccess && rows.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto" data-testid="rk-table">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-3 py-2 w-10">#</th>
                <th className="px-3 py-2">Escola</th>
                <th className="px-3 py-2">Gestor</th>
                <th className="px-3 py-2">Turmas</th>
                <th className="px-3 py-2">Alertas</th>
                <th className="px-3 py-2">Taxa</th>
                <th className="px-3 py-2">Tempo médio</th>
                <th className="px-3 py-2">Pendentes</th>
                <th className="px-3 py-2">Score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const isTop3 = r.rank <= 3;
                const isBottom = bottom3.includes(r.school_id) && rows.length > 5;
                return (
                  <tr
                    key={r.school_id}
                    className={`border-t border-gray-100 ${isBottom ? 'bg-red-50/40' : isTop3 ? 'bg-amber-50/40' : ''}`}
                    data-testid={`rk-row-${r.school_id}`}
                  >
                    <td className="px-3 py-2 font-bold text-gray-700">
                      {isTop3 ? <span className="text-lg">{MEDALS[r.rank - 1]}</span> : r.rank}
                    </td>
                    <td className="px-3 py-2 font-semibold text-gray-800">{r.school_name}</td>
                    <td className="px-3 py-2 text-xs text-gray-600">
                      {r.gestor_nome}
                      <div className="text-[10px] text-gray-400 uppercase">{r.gestor_role}</div>
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-600">{r.num_classes}</td>
                    <td className="px-3 py-2 text-xs">
                      <span className="text-gray-700">{r.received}</span>
                      <span className="text-gray-400"> recebidos · </span>
                      <span className="text-emerald-700">{r.resolved}</span>
                      <span className="text-gray-400"> resolv.</span>
                    </td>
                    <td className="px-3 py-2 text-xs">{r.resolution_rate}%</td>
                    <td className="px-3 py-2 text-xs">{r.avg_resolution_days != null ? `${r.avg_resolution_days}d` : '—'}</td>
                    <td className="px-3 py-2 text-xs">
                      {r.active > 0 && (
                        <span className={`inline-flex items-center gap-1 ${r.critical_level_3 > 0 ? 'text-red-700 font-semibold' : 'text-amber-700'}`}>
                          {r.critical_level_3 > 0 && <AlertTriangle className="h-3 w-3" />}
                          {r.active}
                          {r.critical_level_3 > 0 && ` (${r.critical_level_3} N3)`}
                        </span>
                      )}
                      {r.active === 0 && <span className="text-emerald-600">0</span>}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-0.5 rounded border text-xs font-semibold ${SCORE_COLOR(r.weighted_score)}`}>
                        {r.weighted_score}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Legenda / tooltip oficial */}
      <div className="mt-4 text-xs text-gray-500 max-w-3xl" data-testid="rk-legend">
        <strong className="text-gray-700">Como o score é calculado:</strong> premia resposta rápida (tempo médio até resolver)
        e consistência (taxa ponderada por nível de escalonamento). Backlog penaliza. Nível 3 conta 3× um Nível 1. O ranking
        considera <em>apenas alertas reais</em> gerados pelo sistema — não subjetividade.
      </div>
    </div>
  );
}
