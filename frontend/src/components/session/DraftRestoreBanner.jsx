import { RotateCcw, X } from 'lucide-react';

function timeAgo(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return 'agora há pouco';
  if (min < 60) return `há ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `há ${h} h`;
  const d = Math.floor(h / 24);
  return `há ${d} dia(s)`;
}

/**
 * Banner de recuperação de rascunho (P1). Aparece quando há um rascunho salvo
 * localmente para o formulário atual, oferecendo restaurar ou descartar.
 */
export const DraftRestoreBanner = ({ draft, onRestore, onDiscard, label = 'rascunho' }) => {
  if (!draft) return null;
  return (
    <div
      className="mb-4 flex flex-col gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 sm:flex-row sm:items-center sm:justify-between"
      data-testid="draft-restore-banner"
    >
      <p className="text-sm text-amber-900">
        <strong>Rascunho não salvo encontrado</strong> ({label}, salvo {timeAgo(draft.updatedAt)}).
        Deseja restaurar o que você havia digitado?
      </p>
      <div className="flex shrink-0 gap-2">
        <button
          onClick={onRestore}
          className="inline-flex items-center gap-1.5 rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-700"
          data-testid="draft-restore-button"
        >
          <RotateCcw size={15} /> Restaurar
        </button>
        <button
          onClick={onDiscard}
          className="inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-white px-3 py-1.5 text-sm font-medium text-amber-800 hover:bg-amber-100"
          data-testid="draft-discard-button"
        >
          <X size={15} /> Descartar
        </button>
      </div>
    </div>
  );
};

export default DraftRestoreBanner;
