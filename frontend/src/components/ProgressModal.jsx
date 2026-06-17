/**
 * ProgressModal — modal GLOBAL de progresso (consome ProgressContext).
 *
 * Honesto por design: durante a geração (preparing) NÃO exibe percentual; só
 * mostra número quando ele é REAL (transferring, via Content-Length).
 */
import { Loader2, CheckCircle2, AlertCircle, FileDown, X } from 'lucide-react';
import { useProgressTask } from '@/contexts/ProgressContext';

function formatMB(bytes) {
  if (!bytes || bytes <= 0) return null;
  return (bytes / (1024 * 1024)).toFixed(1).replace('.', ',') + ' MB';
}

export const ProgressModal = () => {
  const { task, closeTask } = useProgressTask();
  if (!task.open) return null;

  const { status, progress, bytesLoaded, bytesTotal, message, error, title, currentStep, current, total } = task;
  const canClose = status === 'completed' || status === 'error';
  const hasRealPercent = status === 'transferring' && typeof progress === 'number';
  const pct = hasRealPercent ? Math.max(0, Math.min(100, progress)) : (status === 'completed' ? 100 : 0);

  const headerIcon = status === 'completed'
    ? <CheckCircle2 className="w-6 h-6 text-emerald-600" />
    : status === 'error'
      ? <AlertCircle className="w-6 h-6 text-red-600" />
      : status === 'transferring'
        ? <FileDown className="w-6 h-6 text-indigo-600" />
        : <Loader2 className="w-6 h-6 text-indigo-600 animate-spin" />;

  const loadedStr = formatMB(bytesLoaded);
  const totalStr = formatMB(bytesTotal);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
      data-testid="progress-modal-overlay"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-2xl bg-white shadow-xl" data-testid="progress-modal">
        <div className="flex items-center gap-3 border-b px-6 py-4">
          {headerIcon}
          <h2 className="flex-1 text-lg font-semibold text-gray-900" data-testid="progress-modal-title">
            {title}
          </h2>
          {canClose && (
            <button
              onClick={closeTask}
              className="text-gray-400 transition-colors hover:text-gray-600"
              data-testid="progress-modal-close"
              aria-label="Fechar"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        <div className="space-y-4 px-6 py-6">
          {/* Estado 1 — Preparando (sem percentual) */}
          {status === 'preparing' && (
            <div className="flex flex-col items-center gap-3 py-2" data-testid="progress-state-preparing">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
              <p className="text-sm font-medium text-gray-700">{message || 'Preparando documento...'}</p>
              <p className="text-xs text-gray-400">Aguarde — o servidor está montando o documento.</p>
            </div>
          )}

          {/* Estado 2 — Transferindo (percentual REAL) */}
          {status === 'transferring' && (
            <div className="space-y-3" data-testid="progress-state-transferring">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium text-gray-700">{message || 'Transferindo arquivo...'}</span>
                {hasRealPercent && (
                  <span className="font-semibold text-indigo-700" data-testid="progress-percent">{pct}%</span>
                )}
              </div>
              <div className="h-3 w-full overflow-hidden rounded-full bg-gray-100">
                <div
                  className={`h-full rounded-full bg-indigo-600 transition-[width] duration-200 ${hasRealPercent ? '' : 'w-1/3 animate-pulse'}`}
                  style={hasRealPercent ? { width: `${pct}%` } : undefined}
                  data-testid="progress-bar"
                />
              </div>
              {(loadedStr) && (
                <p className="text-xs text-gray-500" data-testid="progress-bytes">
                  {totalStr ? `${loadedStr} de ${totalStr}` : `${loadedStr} recebidos`}
                </p>
              )}
              {total > 0 && (
                <p className="text-xs text-gray-500" data-testid="progress-items">
                  {currentStep ? `${currentStep} — ` : ''}{current} de {total}
                </p>
              )}
            </div>
          )}

          {/* Estado 3 — Concluído */}
          {status === 'completed' && (
            <div className="space-y-3" data-testid="progress-state-completed">
              <div className="flex items-center gap-2 text-emerald-700">
                <CheckCircle2 className="h-5 w-5" />
                <span className="text-sm font-medium">{message || 'Arquivo pronto. Iniciando download...'}</span>
              </div>
              <div className="h-3 w-full overflow-hidden rounded-full bg-gray-100">
                <div className="h-full rounded-full bg-emerald-500" style={{ width: '100%' }} />
              </div>
            </div>
          )}

          {/* Estado de erro */}
          {status === 'error' && (
            <div className="space-y-3" data-testid="progress-state-error">
              <div className="flex items-start gap-2 text-red-700">
                <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                <span className="text-sm">{error || 'Falha ao gerar o documento.'}</span>
              </div>
              <button
                onClick={closeTask}
                className="w-full rounded-lg bg-gray-100 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200"
                data-testid="progress-error-close-btn"
              >
                Fechar
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProgressModal;
