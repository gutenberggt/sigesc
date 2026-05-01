/**
 * SkillPicker — selector de Habilidades BNCC / DCM com autocomplete.
 *
 * Uso:
 *   <SkillPicker
 *     value={['EF03MA02', 'EF03MA05']}
 *     onChange={(codigos) => setForm({ ...form, skill_codigos: codigos })}
 *     ano={3}                          // pré-filtro opcional por ano da turma
 *     componenteCodigo="MA"            // pré-filtro opcional por componente
 *     onAppendDescription={(text) => setContent(c => c + '\n' + text)}
 *   />
 *
 * Comportamento:
 *   - Cada habilidade aparece como chip removível (X) com seu código + tooltip da descrição.
 *   - Campo de busca + dropdown com até 10 resultados; debounce 300ms.
 *   - Ao selecionar, se `onAppendDescription` for passado, mostra ícone "+" para
 *     o usuário inserir a descrição da habilidade no campo de conteúdo.
 *   - Vazio = aceita registro sem habilidade (retrocompatível com texto livre).
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { Search, X, BookOpen, Plus, Loader2 } from 'lucide-react';
import { curriculumAPI } from '@/services/api';

const FONTE_BADGE = {
  BNCC: { label: 'BNCC', color: 'bg-blue-50 text-blue-700 border-blue-200' },
  BNCC_COMPUTACAO: { label: 'Computação', color: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  DCM_FA: { label: 'DCM', color: 'bg-amber-50 text-amber-700 border-amber-200' },
  MUNICIPAL: { label: 'Municipal', color: 'bg-violet-50 text-violet-700 border-violet-200' },
};

export default function SkillPicker({
  value = [],
  onChange,
  ano,
  componenteCodigo,
  onAppendDescription,
  disabled = false,
  label = 'Habilidades BNCC / DCM',
  placeholder = 'Buscar por código (ex.: EF03MA02) ou descrição...',
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectedCache, setSelectedCache] = useState({}); // codigo → skill (para mostrar chip rico)
  const inputRef = useRef(null);
  const containerRef = useRef(null);

  /** Carrega detalhe das habilidades já selecionadas (para mostrar descrição no chip). */
  useEffect(() => {
    const missing = value.filter(c => !selectedCache[c]);
    if (missing.length === 0) return;
    Promise.all(missing.map(c =>
      curriculumAPI.skillByCodigo(c).catch(() => null)
    )).then(skills => {
      setSelectedCache(prev => {
        const next = { ...prev };
        skills.forEach(s => { if (s) next[s.codigo] = s; });
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
        const params = { limit: 10 };
        if (query.trim()) params.q = query.trim();
        if (ano) params.ano = ano;
        const r = await curriculumAPI.skills(params);
        // Filtra por componente se passado e backend não fizer
        let items = r.items || [];
        if (componenteCodigo) {
          items = items.filter(s => s.componente_codigo === componenteCodigo);
        }
        // Não mostra os já selecionados
        items = items.filter(s => !value.includes(s.codigo));
        setResults(items);
      } catch (e) {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(id);
  }, [query, open, ano, componenteCodigo, value, disabled]);

  /** Fecha dropdown ao clicar fora. */
  useEffect(() => {
    const onDocClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const addSkill = useCallback((skill) => {
    if (!skill || value.includes(skill.codigo)) return;
    setSelectedCache(prev => ({ ...prev, [skill.codigo]: skill }));
    onChange?.([...value, skill.codigo]);
    setQuery('');
    inputRef.current?.focus();
  }, [value, onChange]);

  const removeSkill = useCallback((codigo) => {
    onChange?.(value.filter(c => c !== codigo));
  }, [value, onChange]);

  return (
    <div ref={containerRef} className="relative" data-testid="skill-picker">
      <div className="flex items-center justify-between mb-1">
        <label className="block text-sm font-medium text-gray-700">{label}</label>
        {value.length > 0 && (
          <span className="text-[10px] text-gray-500" data-testid="skill-picker-count">
            {value.length} selecionada{value.length === 1 ? '' : 's'}
          </span>
        )}
      </div>

      {/* Chips das habilidades selecionadas */}
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {value.map((codigo) => {
            const skill = selectedCache[codigo];
            const fonte = skill?.fonte || 'BNCC';
            const badge = FONTE_BADGE[fonte] || FONTE_BADGE.BNCC;
            return (
              <span
                key={codigo}
                className="inline-flex items-center gap-1 px-2 py-1 bg-purple-50 border border-purple-200 rounded-full text-xs"
                title={skill?.descricao || codigo}
                data-testid={`skill-chip-${codigo}`}
              >
                <BookOpen className="h-3 w-3 text-purple-600" />
                <span className="font-mono font-semibold text-purple-700">{codigo}</span>
                {skill?.descricao && (
                  <span className="text-gray-600 max-w-[280px] truncate hidden sm:inline">
                    — {skill.descricao}
                  </span>
                )}
                <span className={`text-[9px] px-1 rounded border ${badge.color}`}>{badge.label}</span>
                {onAppendDescription && skill?.descricao && (
                  <button
                    type="button"
                    onClick={() => onAppendDescription(`${codigo} — ${skill.descricao}`)}
                    className="text-purple-500 hover:text-purple-800"
                    title="Inserir descrição no campo Conteúdo"
                    data-testid={`skill-append-${codigo}`}
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => removeSkill(codigo)}
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

      {/* Input de busca */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          disabled={disabled}
          placeholder={placeholder}
          className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm disabled:bg-gray-100"
          data-testid="skill-picker-input"
        />
        {loading && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 animate-spin" />
        )}
      </div>

      {/* Dropdown de resultados */}
      {open && (results.length > 0 || loading) && (
        <div
          className="absolute z-30 left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-80 overflow-y-auto"
          data-testid="skill-picker-dropdown"
        >
          {results.length === 0 && !loading && (
            <div className="px-3 py-4 text-xs text-gray-400 italic text-center">
              Nenhuma habilidade encontrada
            </div>
          )}
          {results.map((s) => {
            const badge = FONTE_BADGE[s.fonte] || FONTE_BADGE.BNCC;
            return (
              <button
                type="button"
                key={s.id}
                onClick={() => addSkill(s)}
                className="w-full text-left px-3 py-2 hover:bg-purple-50 border-b last:border-b-0 transition-colors"
                data-testid={`skill-option-${s.codigo}`}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="font-mono text-xs font-semibold text-purple-700">{s.codigo}</span>
                  <span className={`text-[9px] px-1 rounded border ${badge.color}`}>{badge.label}</span>
                  {s.ano != null && (
                    <span className="text-[10px] text-gray-500">{s.ano}º ano</span>
                  )}
                  {s.componente_codigo && (
                    <span className="text-[10px] text-gray-400">· {s.componente_codigo}</span>
                  )}
                </div>
                <div className="text-xs text-gray-700 line-clamp-2">{s.descricao}</div>
                {s.objeto_conhecimento && (
                  <div className="text-[10px] text-gray-400 mt-0.5">📘 {s.objeto_conhecimento}</div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
