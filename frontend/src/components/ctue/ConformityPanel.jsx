import { CheckCircle2, AlertTriangle, AlertCircle, XCircle, MinusCircle, Clock, Award, FileText, Loader2 } from 'lucide-react';

// SSoT dos estados (rótulo/cor/ícone). Nenhum cálculo aqui — só apresentação.
export const STATE_META = {
  conforme:      { label: 'Atualizado',      dot: 'bg-green-500',  text: 'text-green-700',  bg: 'bg-green-50',  border: 'border-green-200',  Icon: CheckCircle2 },
  atencao:       { label: 'Parcialmente Atualizado',       dot: 'bg-yellow-500', text: 'text-yellow-700', bg: 'bg-yellow-50', border: 'border-yellow-200', Icon: AlertTriangle },
  critico:       { label: 'Desatualizado',       dot: 'bg-orange-500', text: 'text-orange-700', bg: 'bg-orange-50', border: 'border-orange-200', Icon: AlertCircle },
  nao_conforme:  { label: 'Necessita Atualização',  dot: 'bg-red-500',    text: 'text-red-700',    bg: 'bg-red-50',    border: 'border-red-200',    Icon: XCircle },
  nao_avaliado:  { label: 'Não avaliado',  dot: 'bg-gray-300',   text: 'text-gray-500',   bg: 'bg-gray-50',   border: 'border-gray-200',   Icon: MinusCircle },
};

const FRESH_META = {
  recent: 'text-green-600',
  ok: 'text-blue-600',
  stale: 'text-amber-600',
  never: 'text-red-500',
};

// Mapa seção de conformidade -> índice da aba do formulário (Índice Inteligente).
const SECTION_TO_TAB = {
  identificacao: 0, localizacao: 0, gestao_vinculacao: 0,
  infraestrutura_fisica: 2, ambientes_pedagogicos: 2,
  acessibilidade: 1, agua_saneamento_energia: 1, seguranca: 1, conectividade: 1, conservacao: 1,
  equipamentos: 3,
};

function Metric({ label, value, testid }) {
  return (
    <div className="flex-1 text-center" data-testid={testid}>
      <div className="text-3xl font-bold text-gray-900">{value}%</div>
      <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</div>
    </div>
  );
}

export function ConformityPanel({ result, profiles = [], profile = 'default', onProfileChange, onNavigateSection, onGenerateDossie, generatingDossie = false }) {
  if (!result) return null;
  const selo = STATE_META[result.selo_geral] || STATE_META.nao_avaliado;
  const fresh = result.atualizacao || {};

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden" data-testid="ctue-conformity-panel">
      {/* Cabeçalho */}
      <div className={`px-4 py-3 flex flex-wrap items-center justify-between gap-3 border-b ${selo.bg} ${selo.border}`}>
        <div className="flex items-center gap-2">
          <selo.Icon className={selo.text} size={22} />
          <span className="font-semibold text-gray-900">CTUE — Situação da Unidade Escolar</span>
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${selo.text} ${selo.bg} border ${selo.border}`} data-testid="ctue-selo-geral">
            <span className={`w-2 h-2 rounded-full ${selo.dot}`} /> {selo.label}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500">Perfil de avaliação:</label>
          <select
            value={profile}
            onChange={(e) => onProfileChange && onProfileChange(e.target.value)}
            className="text-sm border border-gray-300 rounded-lg px-2 py-1 focus:ring-2 focus:ring-blue-500"
            data-testid="ctue-profile-select"
          >
            {profiles.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
          {onGenerateDossie && (
            <button
              type="button"
              onClick={onGenerateDossie}
              disabled={generatingDossie}
              className="inline-flex items-center gap-1.5 text-sm font-medium px-3 py-1 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              data-testid="ctue-generate-dossie-button"
            >
              {generatingDossie ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />}
              {generatingDossie ? 'Gerando…' : 'Gerar Dossiê'}
            </button>
          )}
        </div>
      </div>

      {/* Métricas + maturidade + atualização */}
      <div className="px-4 py-4 grid grid-cols-1 md:grid-cols-4 gap-4 items-center">
        <div className="md:col-span-2 flex items-center divide-x divide-gray-200">
          <Metric label="Completude" value={result.completude_geral} testid="ctue-completude" />
          <Metric label="Conformidade" value={result.conformidade_geral} testid="ctue-conformidade" />
        </div>
        <div className="flex items-center gap-2 justify-center" data-testid="ctue-maturidade">
          <Award className="text-indigo-600" size={20} />
          <div>
            <div className="text-sm font-semibold text-gray-900">Nível {result.maturidade?.nivel}</div>
            <div className="text-xs text-gray-500">{result.maturidade?.nome}</div>
          </div>
        </div>
        <div className="flex items-center gap-2 justify-center" data-testid="ctue-atualizacao">
          <Clock className={FRESH_META[fresh.freshness] || 'text-gray-400'} size={18} />
          <span className={`text-sm font-medium ${FRESH_META[fresh.freshness] || 'text-gray-500'}`}>{fresh.label}</span>
        </div>
      </div>

      {/* Índice Inteligente — status por seção (clicável) */}
      <div className="px-4 pb-4">
        <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Índice Inteligente</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {result.sections.map((sec) => {
            const meta = STATE_META[sec.status] || STATE_META.nao_avaliado;
            const tab = SECTION_TO_TAB[sec.key];
            const clickable = tab !== undefined && onNavigateSection;
            return (
              <button
                key={sec.key}
                type="button"
                onClick={() => clickable && onNavigateSection(tab)}
                disabled={!clickable}
                data-testid={`ctue-index-${sec.key}`}
                className={`flex items-center justify-between gap-2 px-3 py-2 rounded-lg border text-left transition-colors ${meta.bg} ${meta.border} ${clickable ? 'hover:shadow-sm cursor-pointer' : 'cursor-default opacity-90'}`}
                title={sec.avaliada === false ? 'Ainda não avaliado nesta versão' : `${sec.label}`}
              >
                <span className="flex items-center gap-2 min-w-0">
                  <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${meta.dot}`} />
                  <span className="text-xs font-medium text-gray-800 truncate">{sec.label}</span>
                </span>
                <span className="text-[11px] font-semibold text-gray-500 flex-shrink-0">
                  {sec.avaliada === false ? '—' : `${sec.conformidade}%`}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// Indicador compacto por seção (para o topo de cada aba).
export function SectionIndicator({ section }) {
  if (!section) return null;
  const meta = STATE_META[section.status] || STATE_META.nao_avaliado;
  if (section.avaliada === false) {
    return (
      <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-gray-50 border border-gray-200 text-gray-500" data-testid={`ctue-section-indicator-${section.key}`}>
        <MinusCircle size={16} /> <span className="text-sm">Ainda não avaliado nesta versão</span>
      </div>
    );
  }
  return (
    <div className={`flex items-center justify-between mb-4 px-3 py-2 rounded-lg border ${meta.bg} ${meta.border}`} data-testid={`ctue-section-indicator-${section.key}`}>
      <span className={`flex items-center gap-2 text-sm font-medium ${meta.text}`}>
        <span className={`w-2.5 h-2.5 rounded-full ${meta.dot}`} /> {section.label} · {meta.label}
      </span>
      <span className="text-sm text-gray-600">
        {section.itens_preenchidos}/{section.itens_total} itens · <strong>{section.conformidade}%</strong>
      </span>
    </div>
  );
}
