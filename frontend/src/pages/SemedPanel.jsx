import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Loader2, Activity, AlertTriangle, CheckCircle2, XCircle, Home, RefreshCw, FileSignature,
  Users, BookOpen, Award, Clock, CalendarRange
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { pmpiAPI } from '@/services/api';

const KPI_META = {
  frequencia:     { label: 'Frequência',     icon: Users,         accent: 'text-sky-600',     bgAccent: 'bg-sky-50'     },
  aulas_lancadas: { label: 'Aulas Lançadas', icon: BookOpen,      accent: 'text-indigo-600',  bgAccent: 'bg-indigo-50'  },
  notas_lancadas: { label: 'Notas Lançadas', icon: Award,         accent: 'text-amber-600',   bgAccent: 'bg-amber-50'   },
  atrasos_dias:   { label: 'Atraso (dias)',  icon: Clock,         accent: 'text-rose-600',    bgAccent: 'bg-rose-50'    },
  carga_horaria:  { label: 'Carga Horária',  icon: CalendarRange, accent: 'text-emerald-600', bgAccent: 'bg-emerald-50' }
};

const KPI_SUFFIX = {
  frequencia: '%',
  aulas_lancadas: '%',
  notas_lancadas: '%',
  atrasos_dias: ' dias',
  carga_horaria: '%'
};

const RISK_COLORS = {
  verde:     { bg: 'bg-green-50',  border: 'border-green-300',   text: 'text-green-700',   dot: 'bg-green-500',  label: 'OK' },
  amarelo:   { bg: 'bg-yellow-50', border: 'border-yellow-300',  text: 'text-yellow-800',  dot: 'bg-yellow-500', label: 'Atenção' },
  vermelho:  { bg: 'bg-red-50',    border: 'border-red-300',     text: 'text-red-700',     dot: 'bg-red-500',    label: 'Crítico' },
  sem_dados: { bg: 'bg-gray-50',   border: 'border-gray-200',    text: 'text-gray-600',    dot: 'bg-gray-400',   label: 'Sem dados' }
};

const KpiBadge = ({ metric, kpi }) => {
  const meta = KPI_META[metric];
  const Icon = meta?.icon || Activity;
  const status = kpi?.status || 'sem_dados';
  const risk = RISK_COLORS[status];
  // Indicador de status no topo direito + cor da borda;
  // o card mantém a cor base do KPI no ícone e header, para identidade visual própria
  return (
    <div
      className={`relative border ${risk.border} rounded-lg bg-white overflow-hidden min-w-[120px] shadow-sm hover:shadow-md transition-all`}
      data-testid={`kpi-${metric}`}
    >
      {/* Faixa lateral na cor base do KPI */}
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${meta?.accent?.replace('text-', 'bg-')}`} />
      {/* Dot de status no canto */}
      <span className={`absolute top-1.5 right-1.5 w-2 h-2 rounded-full ${risk.dot}`} title={risk.label} />
      <div className="pl-3 pr-2 py-2 flex flex-col gap-0.5">
        <div className="flex items-center gap-1.5">
          <Icon className={`w-3.5 h-3.5 ${meta?.accent || 'text-gray-500'}`} />
          <span className="text-[10px] uppercase tracking-wide text-gray-600 font-semibold">
            {meta?.label || metric}
          </span>
        </div>
        <div className="flex items-baseline gap-1">
          <span className={`font-bold text-xl ${risk.text}`}>
            {kpi?.value !== null && kpi?.value !== undefined ? kpi.value : '—'}
          </span>
          {kpi?.value !== null && kpi?.value !== undefined && (
            <span className="text-[11px] text-gray-500">{KPI_SUFFIX[metric]}</span>
          )}
        </div>
      </div>
    </div>
  );
};

const SchoolCard = ({ school }) => {
  const color = RISK_COLORS[school.risk] || RISK_COLORS.sem_dados;
  return (
    <Card className={`${color.border} border-l-4 hover:shadow-md transition-shadow`} data-testid={`school-card-${school.school_id}`}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base font-semibold leading-tight">
            {school.school_name}
          </CardTitle>
          <div className={`flex items-center gap-2 px-3 py-1 rounded-full ${color.bg} ${color.text} text-xs font-semibold`}>
            <span className={`w-2 h-2 rounded-full ${color.dot}`} />
            {color.label}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          {Object.keys(KPI_META).map(m => (
            <KpiBadge key={m} metric={m} kpi={school.kpis?.[m]} />
          ))}
        </div>
        <div className="mt-3 flex justify-end">
          <Link
            to={`/action-plans?school_id=${school.school_id}`}
            className="text-xs text-blue-600 hover:text-blue-700 hover:underline font-medium"
            data-testid={`plans-link-${school.school_id}`}
          >
            Ver planos de ação →
          </Link>
        </div>
      </CardContent>
    </Card>
  );
};

export default function SemedPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await pmpiAPI.getOverview();
      setData(res);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Erro ao carregar');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const totals = data?.totals || { verde: 0, amarelo: 0, vermelho: 0, sem_dados: 0 };

  return (
    <div className="space-y-6">
      {/* Cabeçalho */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <Link to="/dashboard" className="flex items-center gap-2 text-gray-600 hover:text-gray-900 transition-colors">
            <Home size={18} />
            <span>Início</span>
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2" data-testid="semed-panel-title">
              <Activity className="w-7 h-7 text-blue-600" />
              Painel do Secretário
            </h1>
            <p className="text-gray-600 text-sm">Monitoramento contínuo da rede — PMPI-GE</p>
          </div>
        </div>
        <Button variant="outline" onClick={load} disabled={loading} data-testid="refresh-semed-btn">
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Totais agregados */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-green-500">
          <CardContent className="p-4 flex items-center gap-3">
            <CheckCircle2 className="w-8 h-8 text-green-500" />
            <div>
              <div className="text-xs text-gray-500 uppercase">OK</div>
              <div className="text-2xl font-bold" data-testid="total-verde">{totals.verde}</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-yellow-500">
          <CardContent className="p-4 flex items-center gap-3">
            <AlertTriangle className="w-8 h-8 text-yellow-500" />
            <div>
              <div className="text-xs text-gray-500 uppercase">Atenção</div>
              <div className="text-2xl font-bold" data-testid="total-amarelo">{totals.amarelo}</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-red-500">
          <CardContent className="p-4 flex items-center gap-3">
            <XCircle className="w-8 h-8 text-red-500" />
            <div>
              <div className="text-xs text-gray-500 uppercase">Crítico</div>
              <div className="text-2xl font-bold" data-testid="total-vermelho">{totals.vermelho}</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-gray-400">
          <CardContent className="p-4 flex items-center gap-3">
            <FileSignature className="w-8 h-8 text-gray-400" />
            <div>
              <div className="text-xs text-gray-500 uppercase">Total de Escolas</div>
              <div className="text-2xl font-bold" data-testid="total-schools">{data?.total_schools || 0}</div>
            </div>
          </CardContent>
        </Card>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 rounded-lg p-4" data-testid="semed-error">
          {error}
        </div>
      )}

      {/* Lista de escolas com semáforo */}
      {loading ? (
        <div className="flex items-center justify-center min-h-[300px]">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-testid="schools-list">
          {(data?.schools || []).map(s => (
            <SchoolCard key={s.school_id} school={s} />
          ))}
          {(data?.schools || []).length === 0 && !error && (
            <div className="col-span-full text-center py-12 text-gray-500">
              Nenhuma escola acessível no tenant atual.
            </div>
          )}
        </div>
      )}

      {data?.computed_at && (
        <p className="text-xs text-gray-400 text-right">
          Calculado em: {new Date(data.computed_at).toLocaleString('pt-BR')}
        </p>
      )}
    </div>
  );
}
