import { useState, useEffect, useRef, useCallback } from 'react';
import { saveDraft, loadDraft, deleteDraft } from '@/db/database';

/**
 * useAutoSaveDraft (P1) — salva continuamente o conteúdo de um formulário em
 * edição no IndexedDB (Dexie), para que NADA digitado seja perdido caso a
 * sessão expire, a internet caia ou o navegador feche.
 *
 * @param {object}   opts
 * @param {string}   opts.formId      identificador estável do formulário (ex.: "grades:{classId}:{courseId}:{year}")
 * @param {*}        opts.data        dados editáveis a persistir (array/objeto)
 * @param {boolean}  opts.enabled     só auto-salva quando true (ex.: hasChanges)
 * @param {string}   opts.userId
 * @param {string}   opts.route       rótulo do módulo (grades|attendance|content)
 * @param {number}   [opts.debounceMs=1200]
 *
 * @returns {{ draft, clearDraft, dismissDraft, refresh }}
 *   draft        rascunho existente carregado ao abrir o formId (p/ oferecer restauração)
 *   clearDraft   remove o rascunho (chamar após salvar no servidor)
 *   dismissDraft apenas oculta o aviso (mantém o autosave)
 *   refresh      recarrega o rascunho existente
 */
export function useAutoSaveDraft({ formId, data, enabled = true, userId, route, debounceMs = 1200 }) {
  const [draft, setDraft] = useState(null);
  const timer = useRef(null);

  // Carrega rascunho existente ao trocar de formId
  useEffect(() => {
    let active = true;
    if (!formId) {
      setDraft(null);
      return undefined;
    }
    loadDraft(formId).then((d) => {
      if (active) setDraft(d || null);
    });
    return () => { active = false; };
  }, [formId]);

  // Auto-save debounced quando habilitado e há dados
  useEffect(() => {
    if (!formId || !enabled || data == null) return undefined;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      saveDraft({ formId, userId, route, data });
    }, debounceMs);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [formId, enabled, data, userId, route, debounceMs]);

  const clearDraft = useCallback(async () => {
    if (!formId) return;
    await deleteDraft(formId);
    setDraft(null);
  }, [formId]);

  const dismissDraft = useCallback(() => setDraft(null), []);

  const refresh = useCallback(async () => {
    if (formId) setDraft((await loadDraft(formId)) || null);
  }, [formId]);

  return { draft, clearDraft, dismissDraft, refresh };
}

export default useAutoSaveDraft;
