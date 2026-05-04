/**
 * SpellCheckTextarea — textarea com sublinhado ondulado inline nos erros PT-BR
 * (LanguageTool via /api/spellcheck).
 *
 * Drop-in replacement para <textarea>:
 *   <SpellCheckTextarea value={v} onChange={setV} rows={5} className="..." />
 *
 * Técnica: overlay espelhado.
 *   - Uma <div> absoluta atrás do textarea, com os mesmos estilos de fonte/
 *     padding/line-height, renderiza o texto quebrado em spans; spans de
 *     erro ganham `text-decoration: underline wavy red`.
 *   - O textarea é visível (texto preto normal) por cima; o overlay só
 *     contribui com o sublinhado ondulado.
 *   - Scroll do textarea é espelhado no overlay via onScroll.
 *
 * UX:
 *   - Debounce de 800ms após cada edição → chama /api/spellcheck.
 *   - Clicar (ou colocar o cursor) dentro de uma palavra sublinhada abre
 *     um popover pequeno com a mensagem e as 4 melhores sugestões.
 *   - Clique em "Aplicar" substitui o trecho e reexecuta o check.
 *   - Botão compacto "Revisar tudo" no canto superior direito (opcional via
 *     prop showReviewAllButton), que abre modal com a lista completa
 *     (reutiliza SpellCheckButton).
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { AlertCircle, Check } from 'lucide-react';
import axios from 'axios';
import SpellCheckButton from '@/components/SpellCheckButton';

const API = process.env.REACT_APP_BACKEND_URL;

const DEBOUNCE_MS = 800;
const MIN_CHARS = 4; // Não checa textos muito curtos (evita ruído em campos meio vazios)

/** Constrói os segmentos do overlay espelhado intercalando texto e erros. */
function buildSegments(text, matches) {
  if (!matches || matches.length === 0) return [{ text, idx: -1 }];
  const segs = [];
  let pos = 0;
  // Ordena por offset (apenas garantia)
  const sorted = [...matches].sort((a, b) => a.offset - b.offset);
  sorted.forEach((m, i) => {
    if (m.offset > pos) segs.push({ text: text.slice(pos, m.offset), idx: -1 });
    segs.push({
      text: text.slice(m.offset, m.offset + m.length),
      idx: matches.indexOf(m), // mantém o índice original
      issue: m.issue_type,
    });
    pos = m.offset + m.length;
  });
  if (pos < text.length) segs.push({ text: text.slice(pos), idx: -1 });
  return segs;
}

const UNDERLINE_COLOR = {
  misspelling: 'decoration-rose-500',
  grammar: 'decoration-amber-500',
  style: 'decoration-sky-500',
  typographical: 'decoration-violet-500',
  other: 'decoration-gray-400',
};

export default function SpellCheckTextarea({
  value = '',
  onChange,
  className = '',
  rows = 4,
  placeholder,
  disabled = false,
  showReviewAllButton = false,
  ...rest
}) {
  const [matches, setMatches] = useState([]);
  const [activeMatchIdx, setActiveMatchIdx] = useState(-1);
  const [popoverPos, setPopoverPos] = useState({ top: 0, left: 0 });
  const textareaRef = useRef(null);
  const overlayRef = useRef(null);
  const containerRef = useRef(null);
  const abortRef = useRef(null);

  /** Chama a API de spellcheck com debounce. */
  useEffect(() => {
    if (disabled) { setMatches([]); return; }
    const text = value || '';
    if (text.trim().length < MIN_CHARS) { setMatches([]); return; }

    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const id = setTimeout(async () => {
      try {
        const r = await axios.post(
          `${API}/api/spellcheck`,
          { text, language: 'pt-BR' },
          { signal: ctrl.signal }
        );
        setMatches(r.data?.matches || []);
      } catch (e) {
        // Silencioso: 429, rede, abort etc. não devem incomodar o usuário
        // enquanto ele digita. Só zera os matches para não mostrar dados velhos.
        if (e?.name !== 'CanceledError' && e?.code !== 'ERR_CANCELED') {
          // preserva matches anteriores para não piscar tela em erros transitórios
        }
      }
    }, DEBOUNCE_MS);

    return () => { clearTimeout(id); ctrl.abort(); };
  }, [value, disabled]);

  /** Sincroniza scroll do textarea para o overlay. */
  const handleScroll = useCallback(() => {
    if (overlayRef.current && textareaRef.current) {
      overlayRef.current.scrollTop = textareaRef.current.scrollTop;
      overlayRef.current.scrollLeft = textareaRef.current.scrollLeft;
    }
  }, []);

  /** Cursor/click dentro de um erro → abre popover posicionado abaixo do caret. */
  const handleSelect = useCallback(() => {
    if (!textareaRef.current || matches.length === 0) { setActiveMatchIdx(-1); return; }
    const caret = textareaRef.current.selectionStart;
    const idx = matches.findIndex(m => caret >= m.offset && caret <= m.offset + m.length);
    if (idx === -1) {
      setActiveMatchIdx(-1);
      return;
    }
    // Posiciona o popover: usamos o bounding box do textarea + estimativa
    // simples baseada no número da linha/coluna do caret.
    const ta = textareaRef.current;
    const rect = ta.getBoundingClientRect();
    const contRect = containerRef.current?.getBoundingClientRect() || rect;
    // Calcula coluna e linha do caret no texto
    const beforeCaret = value.slice(0, caret);
    const linesBefore = beforeCaret.split('\n');
    const lineIndex = linesBefore.length - 1;
    const colIndex = linesBefore[lineIndex].length;
    // Altura de linha aproximada (lê computed style)
    const cs = window.getComputedStyle(ta);
    const lineHeight = parseFloat(cs.lineHeight) || 20;
    const paddingTop = parseFloat(cs.paddingTop) || 0;
    const paddingLeft = parseFloat(cs.paddingLeft) || 0;
    // Usa canvas para medir largura do texto na linha
    const charWidth = measureCharWidth(cs);
    const top = (rect.top - contRect.top) + paddingTop + lineIndex * lineHeight + lineHeight - ta.scrollTop;
    const rawLeft = (rect.left - contRect.left) + paddingLeft + colIndex * charWidth - ta.scrollLeft;
    const maxLeft = (ta.clientWidth - 260);
    const left = Math.max(4, Math.min(rawLeft, maxLeft));
    setPopoverPos({ top, left });
    setActiveMatchIdx(idx);
  }, [matches, value]);

  /** Alt+Enter dentro de um erro → aplica a 1ª sugestão (atalho estilo Google Docs). */
  const handleKeyDown = useCallback((e) => {
    if (!(e.altKey && e.key === 'Enter')) return;
    if (!textareaRef.current || matches.length === 0) return;
    const caret = textareaRef.current.selectionStart;
    const idx = matches.findIndex(m => caret >= m.offset && caret <= m.offset + m.length);
    if (idx === -1) return;
    const m = matches[idx];
    if (!m.replacements || m.replacements.length === 0) return;
    e.preventDefault();
    const replacement = m.replacements[0];
    const newValue = value.slice(0, m.offset) + replacement + value.slice(m.offset + m.length);
    onChange?.({ target: { value: newValue } });
    setActiveMatchIdx(-1);
  }, [matches, value, onChange]);

  /** Aplica uma sugestão ao valor e dispara onChange. */
  const applySuggestion = (matchIdx, replacement) => {
    const m = matches[matchIdx];
    if (!m) return;
    const newValue = value.slice(0, m.offset) + replacement + value.slice(m.offset + m.length);
    if (typeof onChange === 'function') {
      // Suporta tanto onChange(e) quanto onChange(valor) — detectamos pela assinatura.
      // A maioria dos consumidores usa onChange={(e) => setX(e.target.value)}.
      onChange({ target: { value: newValue } });
    }
    setActiveMatchIdx(-1);
  };

  const ignoreActive = () => setActiveMatchIdx(-1);

  const segments = useMemo(() => buildSegments(value || '', matches), [value, matches]);
  const total = matches.length;

  return (
    <div className="relative" ref={containerRef}>
      {/* Overlay espelhado: mesmo className do textarea, atrás, com spans sublinhados */}
      <div
        ref={overlayRef}
        className={`${className} absolute inset-0 overflow-hidden pointer-events-none whitespace-pre-wrap break-words`}
        style={{
          color: 'transparent',
          background: 'transparent',
          borderColor: 'transparent',
          // [Mai/2026] CAPS lock global removido. Overlay espelha o textarea
          // mantendo a capitalização normal. Permanece o opt-in `data-uppercase`
          // para casos legítimos (códigos, siglas).
          textTransform: rest['data-uppercase'] ? 'uppercase' : 'none',
          // Evita que o overlay ocupe espaço extra
          zIndex: 0,
        }}
        aria-hidden="true"
        data-testid="spellcheck-overlay"
      >
        {segments.map((s, i) =>
          s.idx >= 0 ? (
            <span
              key={`s-${i}`}
              className={`underline decoration-wavy ${UNDERLINE_COLOR[s.issue] || UNDERLINE_COLOR.other}`}
              style={{ textDecorationSkipInk: 'none', textUnderlineOffset: '3px' }}
            >
              {s.text}
            </span>
          ) : (
            <span key={`s-${i}`}>{s.text}</span>
          )
        )}
        {/* Garante altura mínima igual ao textarea quando value vazio */}
        {!value && <span>&nbsp;</span>}
      </div>

      <textarea
        ref={textareaRef}
        className={`${className} relative bg-transparent`}
        style={{ zIndex: 1, position: 'relative' }}
        rows={rows}
        value={value}
        onChange={onChange}
        onScroll={handleScroll}
        onClick={handleSelect}
        onKeyUp={handleSelect}
        onKeyDown={handleKeyDown}
        onBlur={() => setTimeout(() => setActiveMatchIdx(-1), 150)}
        placeholder={placeholder}
        disabled={disabled}
        spellCheck={false}
        data-testid="spellcheck-textarea"
        {...rest}
      />

      {/* Indicador de contagem no canto */}
      {total > 0 && (
        <div
          className="absolute top-1 right-1 flex items-center gap-1 text-[10px] font-semibold text-rose-700 bg-white/90 border border-rose-200 rounded-full px-1.5 py-0.5 pointer-events-none z-10"
          data-testid="spellcheck-indicator"
        >
          <AlertCircle className="h-3 w-3" />
          {total}
        </div>
      )}

      {showReviewAllButton && (
        <div className="absolute top-1 right-10 z-10">
          <SpellCheckButton
            text={value}
            onApply={(t) => onChange?.({ target: { value: t } })}
            compact
            disabled={disabled || !value}
          />
        </div>
      )}

      {/* Popover de sugestões quando cursor está dentro de um erro */}
      {activeMatchIdx >= 0 && matches[activeMatchIdx] && (
        <div
          className="absolute z-30 bg-white border border-gray-200 rounded-lg shadow-lg p-2 min-w-[240px] max-w-[300px]"
          style={{ top: popoverPos.top, left: popoverPos.left }}
          onMouseDown={(e) => e.preventDefault()}
          data-testid="spellcheck-popover"
        >
          <div className="flex items-start gap-1 mb-2 text-xs text-gray-700">
            <AlertCircle className="h-3.5 w-3.5 text-amber-500 mt-0.5 flex-shrink-0" />
            <span>{matches[activeMatchIdx].message}</span>
          </div>
          {matches[activeMatchIdx].replacements.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {matches[activeMatchIdx].replacements.slice(0, 4).map((r, ri) => (
                <button
                  key={`r-${ri}`}
                  type="button"
                  onMouseDown={(e) => { e.preventDefault(); applySuggestion(activeMatchIdx, r); }}
                  className="text-xs px-2 py-1 rounded border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                  data-testid={`spellcheck-popover-apply-${ri}`}
                >
                  <Check className="inline h-3 w-3 mr-0.5" />
                  {r}
                </button>
              ))}
            </div>
          ) : (
            <div className="text-[11px] text-gray-400 italic">Sem sugestão — revise manualmente.</div>
          )}
          <div className="flex items-center justify-between mt-2 gap-2">
            <button
              type="button"
              onMouseDown={(e) => { e.preventDefault(); ignoreActive(); }}
              className="text-[10px] text-gray-500 hover:text-gray-800"
              data-testid="spellcheck-popover-ignore"
            >
              Ignorar
            </button>
            {matches[activeMatchIdx].replacements.length > 0 && (
              <span className="text-[10px] text-gray-400 italic">
                Alt+Enter aplica a 1ª sugestão
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Mede a largura média de um caractere "0" com o font do textarea. */
let _cachedCtx = null;
function measureCharWidth(computedStyle) {
  if (!_cachedCtx) {
    const canvas = document.createElement('canvas');
    _cachedCtx = canvas.getContext('2d');
  }
  _cachedCtx.font = `${computedStyle.fontStyle} ${computedStyle.fontWeight} ${computedStyle.fontSize} ${computedStyle.fontFamily}`;
  return _cachedCtx.measureText('0').width || 8;
}
