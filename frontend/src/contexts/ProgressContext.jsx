/**
 * ProgressContext — infraestrutura GLOBAL e reutilizável de progresso de tarefas
 * longas (geração de PDFs, importações CSV, sincronização offline, cálculos em
 * lote do SIE, fechamento de bimestre, relatórios da SEMED).
 *
 * Princípio (governança SIGESC): construir UMA vez, reutilizar em toda a plataforma.
 *
 * Modelo de estados (sem números falsos):
 *   - preparing    → backend gerando; SEM percentual ("Preparando documento...")
 *   - transferring → bytes chegando; percentual REAL (Content-Length)
 *   - completed    → arquivo pronto / download iniciado
 *   - error        → falha com mensagem
 *
 * API já preparada para SSE (Nível 2). Quando o backend emitir
 * `{ progress, current, total, step }`, basta chamar `updateTask(...)` — nenhuma
 * tela precisará ser refeita.
 */
import { createContext, useCallback, useContext, useMemo, useState } from 'react';

const INITIAL = {
  open: false,
  title: 'Gerando documento',
  status: 'preparing', // preparing | transferring | completed | error
  progress: null, // 0-100 (null = desconhecido → não exibir número)
  currentStep: '',
  current: 0,
  total: 0,
  bytesLoaded: 0,
  bytesTotal: 0,
  message: 'Preparando documento...',
  error: '',
};

const ProgressContext = createContext(null);

export const ProgressProvider = ({ children }) => {
  const [task, setTask] = useState(INITIAL);

  const startTask = useCallback((opts = {}) => {
    setTask({
      ...INITIAL,
      open: true,
      title: opts.title || INITIAL.title,
      message: opts.message || INITIAL.message,
      currentStep: opts.currentStep || '',
    });
  }, []);

  // Patch genérico — usado tanto pelo download (Nível 1) quanto por SSE (Nível 2).
  const updateTask = useCallback((patch = {}) => {
    setTask((prev) => ({ ...prev, ...patch, open: true }));
  }, []);

  const setTransferring = useCallback((patch = {}) => {
    setTask((prev) => ({
      ...prev,
      open: true,
      status: 'transferring',
      message: patch.message || 'Transferindo arquivo...',
      progress: patch.progress ?? prev.progress,
      bytesLoaded: patch.bytesLoaded ?? prev.bytesLoaded,
      bytesTotal: patch.bytesTotal ?? prev.bytesTotal,
      current: patch.current ?? prev.current,
      total: patch.total ?? prev.total,
      currentStep: patch.currentStep ?? prev.currentStep,
    }));
  }, []);

  const completeTask = useCallback((opts = {}) => {
    setTask((prev) => ({
      ...prev,
      open: true,
      status: 'completed',
      progress: 100,
      message: opts.message || 'Arquivo pronto. Iniciando download...',
    }));
  }, []);

  const failTask = useCallback((errorMsg) => {
    setTask((prev) => ({
      ...prev,
      open: true,
      status: 'error',
      error: errorMsg || 'Falha ao gerar o documento.',
      message: errorMsg || 'Falha ao gerar o documento.',
    }));
  }, []);

  const closeTask = useCallback(() => {
    setTask((prev) => ({ ...prev, open: false }));
  }, []);

  const value = useMemo(
    () => ({ task, startTask, updateTask, setTransferring, completeTask, failTask, closeTask }),
    [task, startTask, updateTask, setTransferring, completeTask, failTask, closeTask],
  );

  return <ProgressContext.Provider value={value}>{children}</ProgressContext.Provider>;
};

/** Hook para controlar o modal global de progresso a partir de qualquer fluxo. */
export const useProgressTask = () => {
  const ctx = useContext(ProgressContext);
  if (!ctx) {
    throw new Error('useProgressTask deve ser usado dentro de <ProgressProvider>');
  }
  return ctx;
};

export default ProgressContext;
