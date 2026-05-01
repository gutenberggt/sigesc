/**
 * SpellCheckButton — corretor ortográfico/gramatical PT-BR (LanguageTool).
 *
 * Uso:
 *   <SpellCheckButton
 *     text={content}
 *     onApply={(newText) => setContent(newText)}
 *     compact           // opcional: versão ícone-only
 *   />
 *
 * Fluxo:
 *   1. Clique "✍️ Revisar" → POST /api/spellcheck
 *   2. Modal lista erros, cada um com contexto (trecho), mensagem e sugestões
 *   3. Clique "Aplicar" em uma sugestão → substitui o trecho no texto e
 *      chama onApply(novoTexto). Offsets dos erros seguintes são ajustados.
 *   4. "Aplicar todas as principais" aplica a 1ª sugestão de cada erro (se houver).
 *
 * Obs.: trabalha em cima do texto como string. O componente NÃO controla o
 * textarea — apenas devolve a nova string via onApply.
 */
import { useState, useCallback } from 'react';
import { SpellCheck2, Loader2, Check, X, AlertCircle, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

const ISSUE_STYLES = {
  misspelling: { label: 'Ortografia', color: 'bg-rose-50 text-rose-700 border-rose-200' },
  grammar:     { label: 'Gramática',  color: 'bg-amber-50 text-amber-700 border-amber-200' },
  style:       { label: 'Estilo',     color: 'bg-sky-50 text-sky-700 border-sky-200' },
  typographical: { label: 'Pontuação', color: 'bg-violet-50 text-violet-700 border-violet-200' },
  other:       { label: 'Outro',      color: 'bg-gray-50 text-gray-700 border-gray-200' },
};

/** Aplica uma única correção sobre o texto original. */
function applyReplacement(text, offset, length, replacement) {
  return text.slice(0, offset) + replacement + text.slice(offset + length);
}

export default function SpellCheckButton({
  text,
  onApply,
  compact = false,
  label = 'Revisar',
  disabled = false,
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [matches, setMatches] = useState([]);
  const [resolvedIdx, setResolvedIdx] = useState(new Set()); // índices já aplicados/ignorados
  const [workingText, setWorkingText] = useState('');

  const runCheck = useCallback(async (input) => {
    setLoading(true);
    try {
      const response = await axios.post(`${API}/api/spellcheck`, {
        text: input,
        language: 'pt-BR',
      });
      setMatches(response.data.matches || []);
      setWorkingText(input);
      setResolvedIdx(new Set());
      if ((response.data.matches || []).length === 0) {
        toast.success('Tudo certo! Nenhum erro encontrado.');
        setOpen(false);
        return;
      }
      setOpen(true);
    } catch (e) {
      const status = e?.response?.status;
      if (status === 429) {
        toast.error('Limite de revisões atingido. Aguarde alguns segundos.');
      } else if (status === 504) {
        toast.error('Corretor demorou para responder. Tente novamente.');
      } else {
        toast.error('Falha ao executar o corretor.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const handleOpen = () => {
    const value = (text || '').trim();
    if (!value) {
      toast.info('Não há texto para revisar.');
      return;
    }
    if (value.length > 20000) {
      toast.error('Texto muito longo (máx. 20.000 caracteres).');
      return;
    }
    runCheck(value);
  };

  /**
   * Aplica uma sugestão específica ao texto atual (workingText) e propaga
   * para o pai via onApply. Reexecuta o check para reposicionar os offsets
   * restantes — abordagem mais segura e simples do que recalcular manualmente.
   */
  const applyOne = async (matchIdx, replacement) => {
    const m = matches[matchIdx];
    if (!m) return;
    const newText = applyReplacement(workingText, m.offset, m.length, replacement);
    onApply?.(newText);
    // Marca este como resolvido e re-executa o check com o novo texto.
    await runCheck(newText);
  };

  const ignoreOne = (matchIdx) => {
    setResolvedIdx(prev => {
      const n = new Set(prev);
      n.add(matchIdx);
      return n;
    });
  };

  const applyAllMain = async () => {
    // Aplica a 1ª sugestão de cada erro remanescente que tenha replacements.
    // Faz da direita para a esquerda para não invalidar offsets anteriores.
    let next = workingText;
    const ordered = [...matches]
      .map((m, i) => ({ m, i }))
      .filter(({ i }) => !resolvedIdx.has(i))
      .filter(({ m }) => m.replacements && m.replacements.length > 0)
      .sort((a, b) => b.m.offset - a.m.offset);

    if (ordered.length === 0) {
      toast.info('Nada para aplicar automaticamente.');
      return;
    }
    for (const { m } of ordered) {
      next = applyReplacement(next, m.offset, m.length, m.replacements[0]);
    }
    onApply?.(next);
    toast.success(`${ordered.length} correção(ões) aplicada(s).`);
    await runCheck(next);
  };

  const close = () => setOpen(false);

  const pending = matches.filter((_, i) => !resolvedIdx.has(i));

  return (
    <>
      {compact ? (
        <Button
          type="button"
          size="icon"
          variant="ghost"
          onClick={handleOpen}
          disabled={disabled || loading || !text}
          title="Revisar ortografia e gramática"
          data-testid="spellcheck-button"
          className="h-8 w-8"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <SpellCheck2 className="h-4 w-4" />}
        </Button>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={handleOpen}
          disabled={disabled || loading || !text}
          data-testid="spellcheck-button"
          className="gap-1.5"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <SpellCheck2 className="h-4 w-4" />}
          {label}
        </Button>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col" data-testid="spellcheck-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <SpellCheck2 className="h-5 w-5 text-blue-600" />
              Revisão de texto
              <span className="ml-auto text-sm font-normal text-gray-500" data-testid="spellcheck-count">
                {pending.length} {pending.length === 1 ? 'sugestão' : 'sugestões'}
              </span>
            </DialogTitle>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto space-y-3 pr-1">
            {pending.length === 0 && (
              <div className="py-10 text-center text-gray-500 flex flex-col items-center gap-2">
                <Check className="h-10 w-10 text-emerald-500" />
                <div className="font-medium">Tudo certo!</div>
                <div className="text-xs">Nenhuma sugestão pendente.</div>
              </div>
            )}
            {matches.map((m, idx) => {
              if (resolvedIdx.has(idx)) return null;
              const style = ISSUE_STYLES[m.issue_type] || ISSUE_STYLES.other;
              const errorStart = m.context.indexOf(workingText.slice(m.offset, m.offset + m.length));
              return (
                <div
                  key={`match-${idx}`}
                  className="border rounded-lg p-3 bg-white"
                  data-testid={`spellcheck-match-${idx}`}
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded border ${style.color}`}>
                        {style.label}
                      </span>
                      <span className="text-[10px] text-gray-400">{m.category}</span>
                    </div>
                    <button
                      type="button"
                      className="text-gray-400 hover:text-gray-700"
                      onClick={() => ignoreOne(idx)}
                      title="Ignorar esta sugestão"
                      data-testid={`spellcheck-ignore-${idx}`}
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                  <p className="text-sm text-gray-700 mb-2 flex items-start gap-1">
                    <AlertCircle className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
                    {m.message}
                  </p>
                  {m.context && (
                    <div className="text-xs bg-gray-50 rounded px-2 py-1.5 mb-2 font-mono">
                      {errorStart >= 0 ? (
                        <>
                          <span className="text-gray-500">{m.context.slice(0, errorStart)}</span>
                          <span className="bg-rose-100 text-rose-700 px-0.5 rounded font-semibold">
                            {m.context.slice(errorStart, errorStart + m.length)}
                          </span>
                          <span className="text-gray-500">{m.context.slice(errorStart + m.length)}</span>
                        </>
                      ) : (
                        <span className="text-gray-500">{m.context}</span>
                      )}
                    </div>
                  )}
                  {m.replacements.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {m.replacements.slice(0, 6).map((r, ri) => (
                        <button
                          key={`r-${idx}-${ri}`}
                          type="button"
                          onClick={() => applyOne(idx, r)}
                          className="text-xs px-2 py-1 rounded border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition-colors"
                          data-testid={`spellcheck-apply-${idx}-${ri}`}
                        >
                          <Check className="inline h-3 w-3 mr-0.5" />
                          {r}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-gray-400 italic">Sem sugestão automática — revise manualmente.</div>
                  )}
                </div>
              );
            })}
          </div>

          <DialogFooter className="gap-2 sm:gap-2 pt-3 border-t">
            <div className="text-[11px] text-gray-400 mr-auto flex items-center gap-1">
              <Sparkles className="h-3 w-3" />
              LanguageTool · Português do Brasil
            </div>
            {pending.length > 0 && (
              <Button
                type="button"
                size="sm"
                variant="default"
                onClick={applyAllMain}
                data-testid="spellcheck-apply-all"
              >
                Aplicar todas as principais
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={close}
              data-testid="spellcheck-close"
            >
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
