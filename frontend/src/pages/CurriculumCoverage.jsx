/**
 * CurriculumCoverage — Widget de Cobertura Curricular (v2).
 *
 * Rota: /admin/curriculo/cobertura
 * Consome: GET /api/curriculum/coverage
 *
 * Regras de cor:
 *   ≥90%  → verde  (ok)
 *   70–89 → âmbar  (atenção)
 *   <70%  → vermelho (crítico)
 *   bimestre futuro → cinza neutro (não iniciado, sem %)
 *
 * Forecast:
 *   no_ritmo / em_risco / nao_cumpre / fechado_critico / nao_iniciado
 */
import { useEffect, useMemo, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, AlertTriangle, ChevronDown, ChevronUp, TrendingUp, Clock, CheckCircle2 } from 'lucide-react';
import { curriculumAPI, classesAPI } from '@/services/api';

const STATUS_STYLE = {
  ok: { bar: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'Adequado' },
  atencao: { bar: 'bg-amber-500', badge: 'bg-amber-50 text-amber-700 border-amber-200', label: 'Atenção' },
  critico: { bar: 'bg-red-600', badge: 'bg-red-50 text-red-700 border-red-200', label: 'Crítico' },
  nao_iniciado: { bar: 'bg-gray-200', badge: 'bg-gray-100 text-gray-500 border-gray-200', label: 'Não iniciado' },
};

const FORECAST_LABEL = {
  no_ritmo: { text: 'No ritmo', icon: CheckCircle2, color: 'text-emerald-600' },
  em_risco: { text: 'Em risco', icon: TrendingUp, color: 'text-amber-600' },
  nao_cumpre: { text: 'Não cumpre', icon: AlertTriangle, color: 'text-red-600' },
  fechado_critico: { text: 'Bimestre fechado abaixo de 90%', icon: AlertTriangle, color: 'text-red-700' },
  nao_iniciado: { text: 'Não iniciado', icon: Clock, color: 'text-gray-400' },
};

export default function CurriculumCoverage() {
  const [academicYear, setAcademicYear] = useState(new Date().getFullYear());
  const [classId, setClassId] = useState('');
  const [classes, setClasses] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    classesAPI.list({ academic_year: academicYear })
      .then(d => setClasses(d || []))
      .catch(() => setClasses([]));
  }, [academicYear]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { academic_year: academicYear };
      if (classId) params.class_id = classId;
      const r = await curriculumAPI.coverage(params);
      setData(r);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [academicYear, classId]);

  useEffect(() => { load(); }, [load]);

  // Agrupa por componente → ano
  const grouped = useMemo(() => {
    const map = {};
    (data?.rows || []).forEach(r => {
      const compKey = r.componente_codigo || '—';
      const anoKey = r.ano ?? 0;
      map[compKey] = map[compKey] || {};
      map[compKey][anoKey] = map[compKey][anoKey] || [];
      map[compKey][anoKey].push(r);
    });
    return map;
  }, [data]);

  // Totais por componente
  const componentTotals = useMemo(() => {
    const tot = {};
    Object.entries(grouped).forEach(([comp, byYear]) => {
      let total = 0, covered = 0;
      Object.values(byYear).forEach(rows => rows.forEach(r => {
        total += r.total;
        covered += r.covered;
      }));
      tot[comp] = {
        total,
        covered,
        pct: total ? Math.round((covered / total) * 1000) / 10 : 0,
      };
    });
    return tot;
  }, [grouped]);

  const closedCritical = data?.totals?.closed_critical || 0;
  const criticalRows = data?.totals?.critical_rows || 0;

  return (
    <div className="max-w-7xl mx-auto px-4 py-6" data-testid="curriculum-coverage-page">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <Link to="/dashboard" className="inline-flex items-center text-sm text-gray-600 hover:text-purple-700 mb-2">
            <ChevronLeft className="h-4 w-4 mr-1" /> Voltar
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">Cobertura Curricular</h1>
          <p className="text-sm text-gray-500">
            O que foi dado · o que falta · projeção até o fim do bimestre
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Ano letivo</label>
            <select
              className="border border-gray-300 rounded px-2 py-1 text-sm"
              value={academicYear}
              onChange={e => setAcademicYear(Number(e.target.value))}
              data-testid="cov-year"
            >
              {[2024, 2025, 2026, 2027].map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Turma</label>
            <select
              className="border border-gray-300 rounded px-2 py-1 text-sm min-w-[200px]"
              value={classId}
              onChange={e => setClassId(e.target.value)}
              data-testid="cov-class"
            >
              <option value="">— Rede inteira —</option>
              {classes.map(c => (
                <option key={c.id} value={c.id}>
                  {c.name} {c.grade_level ? `(${c.grade_level})` : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Banner de alerta crítico */}
      {(closedCritical > 0 || criticalRows > 0) && (
        <div
          className="flex items-start gap-3 bg-red-50 border border-red-300 rounded-lg px-4 py-3 mb-4"
          data-testid="cov-alert-banner"
        >
          <AlertTriangle className="h-6 w-6 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-red-800">
              ⚠️ Cobertura crítica detectada: intervenção necessária
            </div>
            <div className="text-xs text-red-700 mt-0.5">
              {closedCritical > 0 && <>{closedCritical} bimestre(s) fechado(s) abaixo de 90%. </>}
              {criticalRows > 0 && <>{criticalRows} componente(s)/ano(s) em risco agora.</>}
            </div>
          </div>
        </div>
      )}

      {/* Resumo geral */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4 grid grid-cols-3 gap-4" data-testid="cov-summary">
        <div>
          <div className="text-xs text-gray-500">Cobertura total</div>
          <div className="text-3xl font-bold text-gray-900">
            {data?.totals?.pct ?? 0}%
          </div>
          <div className="text-xs text-gray-500">
            {data?.totals?.covered || 0} de {data?.totals?.total || 0} habilidades
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Componentes em atenção</div>
          <div className="text-3xl font-bold text-amber-600">
            {(data?.rows || []).filter(r => r.status === 'atencao').length}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Componentes críticos</div>
          <div className="text-3xl font-bold text-red-600">
            {(data?.rows || []).filter(r => r.status === 'critico' && r.bimestre_state !== 'futuro').length}
          </div>
        </div>
      </div>

      {loading && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-gray-500">
          Calculando cobertura...
        </div>
      )}

      {!loading && Object.keys(grouped).length === 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-gray-500" data-testid="cov-empty">
          Nenhuma base curricular cadastrada ainda. Importe um PDF ou rode a sincronização BNCC em{' '}
          <Link to="/admin/curriculo/adaptacoes" className="text-purple-700 underline">Adaptações</Link>.
        </div>
      )}

      {/* Lista de componentes */}
      <div className="space-y-3">
        {Object.entries(grouped).map(([comp, byYear]) => {
          const total = componentTotals[comp];
          const compStatus = total.pct >= 90 ? 'ok' : total.pct >= 70 ? 'atencao' : 'critico';
          const compStyle = STATUS_STYLE[compStatus];
          return (
            <div key={comp} className="bg-white border border-gray-200 rounded-lg" data-testid={`cov-comp-${comp}`}>
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm font-bold text-purple-700 bg-purple-50 px-2 py-1 rounded">{comp}</span>
                  <span className="text-sm text-gray-700">
                    <span className="font-semibold">{total.pct}%</span> coberto
                    <span className="text-gray-400"> · {total.covered}/{total.total}</span>
                  </span>
                  <span className={`text-[10px] px-2 py-0.5 rounded border ${compStyle.badge}`}>{compStyle.label}</span>
                </div>
              </div>
              <div className="p-3 space-y-2">
                {Object.entries(byYear).sort(([a], [b]) => Number(a) - Number(b)).map(([ano, rows]) => (
                  <YearBlock
                    key={ano}
                    ano={ano}
                    rows={rows}
                    expanded={expanded}
                    setExpanded={setExpanded}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function YearBlock({ ano, rows, expanded, setExpanded }) {
  // Garante 4 bimestres + linha "sem bimestre" (null)
  const byBim = {};
  rows.forEach(r => { byBim[r.bimestre ?? 'null'] = r; });
  const slots = [1, 2, 3, 4].map(b => byBim[b]).filter(Boolean);
  const transversais = byBim['null'];

  return (
    <div className="border border-gray-100 rounded p-2" data-testid={`cov-year-${ano}`}>
      <div className="text-xs font-semibold text-gray-600 mb-1">
        {ano === '0' || ano === 0 ? 'Transversal' : `${ano}º ano`}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
        {[1, 2, 3, 4].map(b => {
          const row = byBim[b];
          if (!row) {
            return (
              <div key={b} className="border border-dashed border-gray-200 rounded px-2 py-1 text-[11px] text-gray-400">
                {b}º bim — sem base
              </div>
            );
          }
          return <BimestreCard key={b} row={row} expanded={expanded} setExpanded={setExpanded} />;
        })}
      </div>
      {transversais && (
        <div className="mt-2 text-[11px] text-gray-500">
          <strong>Transversais (sem bimestre):</strong> {transversais.covered}/{transversais.total} ({transversais.pct}%)
        </div>
      )}
      {slots.length === 0 && !transversais && (
        <div className="text-[11px] text-gray-400">Sem adaptações cadastradas.</div>
      )}
    </div>
  );
}

function BimestreCard({ row, expanded, setExpanded }) {
  const key = `${row.componente_codigo}-${row.ano}-${row.bimestre}`;
  const style = STATUS_STYLE[row.status];
  const forecast = FORECAST_LABEL[row.forecast];
  const ForecastIcon = forecast?.icon;
  const isFuture = row.bimestre_state === 'futuro';
  const isOpen = !!expanded[key];

  return (
    <div
      className={`border rounded px-2 py-1 ${row.status === 'critico' ? 'border-red-200' : 'border-gray-200'}`}
      data-testid={`cov-bim-${key}`}
    >
      <div className="flex items-center justify-between text-[11px]">
        <span className="font-semibold text-gray-700">{row.bimestre}º bim.</span>
        {!isFuture ? (
          <span className="font-semibold text-gray-800">{row.pct}%</span>
        ) : (
          <span className="text-gray-400">—</span>
        )}
      </div>
      <div className="h-2 bg-gray-100 rounded mt-1 overflow-hidden">
        <div
          className={`h-full ${style.bar}`}
          style={{ width: isFuture ? '0%' : `${row.pct}%` }}
          data-testid={`cov-bar-${key}`}
        />
      </div>
      <div className="flex items-center justify-between mt-1 text-[10px]">
        <span className="text-gray-500">{row.covered}/{row.total}</span>
        {forecast && (
          <span className={`flex items-center gap-0.5 ${forecast.color}`} title="Projeção">
            {ForecastIcon && <ForecastIcon className="h-3 w-3" />}
            {forecast.text}
          </span>
        )}
      </div>
      {row.pending_count > 0 && !isFuture && (
        <button
          onClick={() => setExpanded(x => ({ ...x, [key]: !x[key] }))}
          className="w-full mt-1 flex items-center justify-between text-[10px] text-purple-600 hover:text-purple-800"
          data-testid={`cov-toggle-${key}`}
        >
          <span>Ver {row.pending_count} pendência{row.pending_count === 1 ? '' : 's'}</span>
          {isOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>
      )}
      {isOpen && (
        <div
          className="mt-1 p-1 bg-gray-50 border border-gray-200 rounded max-h-40 overflow-y-auto"
          data-testid={`cov-pending-${key}`}
        >
          <ul className="space-y-0.5 text-[10px]">
            {row.pending.map(p => (
              <li key={p.adaptation_id} className="font-mono text-gray-700">
                {p.codigo || p.bncc_skill_id?.slice(0, 10) || p.adaptation_id.slice(0, 10)}
              </li>
            ))}
          </ul>
          {row.pending_count > row.pending.length && (
            <div className="text-[10px] text-gray-400 mt-1">
              … e mais {row.pending_count - row.pending.length}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
