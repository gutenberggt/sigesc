/**
 * SkillPicker v2 — selector de habilidades via `curriculum_adaptations`.
 *
 * Uso:
 *   <SkillPicker
 *     value={['adapt_abc123', 'adapt_def456']}   // adaptation_ids
 *     onChange={(ids) => setForm(p => ({ ...p, adaptation_ids: ids }))}
 *     ano={3}
 *     bimestre={2}
 *     componenteCodigo="LP"
 *     onAppendDescription={(text) => setContent(c => c + '\n' + text)}
 *     maxSelections={3}
 *   />
 *
 * Diferente da v1: emite adaptation_ids (não codigos BNCC), com máx 3 itens,
 * filtro inclusivo por bimestre (matching OR null), e badges com origem.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { Search, X, BookOpen, Plus, Loader2, AlertCircle } from 'lucide-react';
import { curriculumAPI } from '@/services/api';

const FONTE_BADGE = {
  BNCC_COMPUTACAO: { label: 'Computação', color: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  DCM_FA: { label: 'DCM', color: 'bg-amber-50 text-amber-700 border-amber-200' },
  MUNICIPAL: { label: 'Municipal', color: 'bg-violet-50 text-violet-700 border-violet-200' },
};

export default function SkillPicker({
  value = [],
  onChange,
  ano,
  bimestre,
  componenteCodigo,
  onAppendDescription,
  disabled = false,
  maxSelections = 3,
  label = 'Habilidades BNCC / DCM',
  placeholder = 'Buscar por código (ex.: EF03LP02) ou descrição...',
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showAllBimestres, setShowAllBimestres] = useState(false);
  const [selectedCache, setSelectedCache] = useState({}); // id → adaptation
  const inputRef = useRef(null);
  const containerRef = useRef(null);

  /** Carrega detalhe das adaptações selecionadas (para mostrar chip rico). */
  useEffect(() => {
    const missing = value.filter(id => !selectedCache[id]);
    if (missing.length === 0) return;
    Promise.all(missing.map(id =>
      curriculumAPI.adaptationById(id).then(d => ({
        id,
        ...d.adaptation,
        codigo: (d.bncc && d.bncc.codigo_bncc) || d.adaptation?.codigo_local,
        descricao: d.adaptation?.descricao_local || (d.bncc && d.bncc.descricao_bncc) || '',
        componente_codigo: d.componente?.codigo,
      })).catch(() => null)
    )).then(adapts => {
      setSelectedCache(prev => {
        const next = { ...prev };
        adapts.forEach(a => { if (a) next[a.id] = a; });
        return next;
      });
    });
  }, [value, selectedCache]);

  /** Busca remota debounced. */
  useEffect(() => {
    if (disabled) return;
    if (!open) return;
    const id = setTimeout(async () => {
      setLoading(true);
      try {
        const params = { limit: 15 };
        const hasQuery = !!query.trim();
        if (hasQuery) params.q = query.trim();
        if (ano) params.ano = ano;
        if (componenteCodigo) params.componente_codigo = componenteCodigo;
        if (bimestre && !hasQuery && !showAllBimestres) {
          params.bimestre = bimestre;
        }
        const r = await curriculumAPI.adaptations(params);
        let items = r.items || [];
        items = items.filter(a => !value.includes(a.adaptation_id));
        setResults(items);
      } catch (e) {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(id);
  }, [query, open, ano, bimestre, showAllBimestres, componenteCodigo, value, disabled]);

  useEffect(() => {
    const onDocClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const addAdaptation = useCallback((a) => {
    if (!a || value.includes(a.adaptation_id)) return;
    if (value.length >= maxSelections) return;
    setSelectedCache(prev => ({ ...prev, [a.adaptation_id]: a }));
    onChange?.([...value, a.adaptation_id]);
    setQuery('');
    inputRef.current?.focus();
  }, [value, onChange, maxSelections]);

  const removeAdaptation = useCallback((id) => {
    onChange?.(value.filter(v => v !== id));
  }, [value, onChange]);

  const atLimit = value.length >= maxSelections;

  return (
    <div ref={containerRef} className="relative" data-testid="skill-picker">
      <div className="flex items-center justify-between mb-1">
        <label className="block text-sm font-medium text-gray-700">{label}</label>
        <span
          className={`text-[10px] ${atLimit ? 'text-amber-700 font-semibold' : 'text-gray-500'}`}
          data-testid="skill-picker-count"
        >
          {value.length}/{maxSelections} {value.length === 1 ? 'selecionada' : 'selecionadas'}
        </span>
      </div>

      {/* Chips das adaptações selecionadas */}
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {value.map((id) => {
            const a = selectedCache[id];
            const fonte = a?.fonte || 'MUNICIPAL';
            const badge = FONTE_BADGE[fonte] || FONTE_BADGE.MUNICIPAL;
            const codigo = a?.codigo || id.slice(0, 8);
            return (
              <span
                key={id}
                className="inline-flex items-center gap-1 px-2 py-1 bg-purple-50 border border-purple-200 rounded-full text-xs"
                title={a?.descricao || codigo}
                data-testid={`skill-chip-${codigo}`}
              >
                <BookOpen className="h-3 w-3 text-purple-600" />
                <span className="font-mono font-semibold text-purple-700">{codigo}</span>
                {a?.descricao && (
                  <span className="text-gray-600 max-w-[280px] truncate hidden sm:inline">
                    — {a.descricao}
                  </span>
                )}
                <span className={`text-[9px] px-1 rounded border ${badge.color}`}>{badge.label}</span>
                {onAppendDescription && a?.descricao && (
                  <button
                    type="button"
                    onClick={() => onAppendDescription(`${codigo} — ${a.descricao}`)}
                    className="text-purple-500 hover:text-purple-800"
                    title="Inserir descrição no campo Conteúdo"
                    data-testid={`skill-append-${codigo}`}
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => removeAdaptation(id)}
                  disabled={disabled}
                  className="text-purple-500 hover:text-red-600"
                  title="Remover habilidade"
                  data-testid={`skill-remove-${codigo}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            );
          })}
        </div>
      )}

      {/* Aviso limite */}
      {atLimit && (
        <div className="mb-2 flex items-center gap-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 px-2 py-1 rounded">
          <AlertCircle className="h-3 w-3" />
          Máximo de {maxSelections} habilidades por registro — remova uma para adicionar outra.
        </div>
      )}

      {/* Input de busca */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          disabled={disabled || atLimit}
          placeholder={atLimit ? `Limite de ${maxSelections} atingido` : placeholder}
          className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm disabled:bg-gray-100"
          data-testid="skill-picker-input"
        />
        {loading && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 animate-spin" />
        )}
      </div>

      {/* Indicador de filtro por bimestre */}
      {bimestre && !query.trim() && !atLimit && (
        <div className="mt-1 flex items-center justify-between text-[10px]">
          <span className="text-purple-700" data-testid="skill-picker-bimestre-info">
            {showAllBimestres
              ? 'Mostrando habilidades de todos os bimestres'
              : `Filtrando pelo ${bimestre}º bimestre da turma`}
          </span>
          <button
            type="button"
            onClick={() => setShowAllBimestres(s => !s)}
            className="text-purple-600 hover:text-purple-800 underline"
            data-testid="skill-picker-toggle-bimestre"
          >
            {showAllBimestres ? `Filtrar pelo ${bimestre}º bim.` : 'Mostrar todos'}
          </button>
        </div>
      )}

      {/* Dropdown de resultados */}
      {open && !atLimit && (results.length > 0 || loading) && (
        <div
          className="absolute z-30 left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-80 overflow-y-auto"
          data-testid="skill-picker-dropdown"
        >
          {results.length === 0 && !loading && (
            <div className="px-3 py-4 text-xs text-gray-400 italic text-center">
              Nenhuma habilidade encontrada
            </div>
          )}
          {results.map((a) => {
            const fonte = a.fonte || 'MUNICIPAL';
            const badge = FONTE_BADGE[fonte] || FONTE_BADGE.MUNICIPAL;
            return (
              <button
                type="button"
                key={a.adaptation_id}
                onClick={() => addAdaptation(a)}
                className="w-full text-left px-3 py-2 hover:bg-purple-50 border-b last:border-b-0 transition-colors"
                data-testid={`skill-option-${a.codigo}`}
              >
                <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                  <span className="font-mono text-xs font-semibold text-purple-700">{a.codigo}</span>
                  <span className={`text-[9px] px-1 rounded border ${badge.color}`}>{badge.label}</span>
                  {a.ano != null && (
                    <span className="text-[10px] text-gray-500">{a.ano}º ano</span>
                  )}
                  {a.bimestre != null && (
                    <span
                      className={`text-[10px] px-1 rounded ${
                        bimestre && a.bimestre === bimestre
                          ? 'bg-purple-100 text-purple-700 font-semibold'
                          : 'text-gray-500'
                      }`}
                      data-testid={`skill-option-bimestre-${a.codigo}`}
                    >
                      {a.bimestre}º bim.
                    </span>
                  )}
                  {a.componente_codigo && (
                    <span className="text-[10px] text-gray-400">· {a.componente_codigo}</span>
                  )}
                </div>
                <div className="text-xs text-gray-700 line-clamp-2">{a.descricao}</div>
                {a.objeto_conhecimento && (
                  <div className="text-[10px] text-gray-400 mt-0.5">📘 {a.objeto_conhecimento}</div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
