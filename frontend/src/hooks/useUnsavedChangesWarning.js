import { useEffect, useRef } from 'react';

/**
 * Hook para alertar o usuário sobre alterações não salvas ao sair da página.
 * - Intercepta fechar aba / reload (beforeunload)
 * - Intercepta cliques no menu lateral / links internos (popstate)
 * @param {boolean} hasUnsavedChanges - Se há alterações não salvas
 * @param {string} message - Mensagem do alerta
 */
export const useUnsavedChangesWarning = (hasUnsavedChanges, message = 'Você tem alterações não salvas. Deseja sair sem salvar?') => {
  const changesRef = useRef(hasUnsavedChanges);
  changesRef.current = hasUnsavedChanges;

  useEffect(() => {
    // Intercepta fechar aba / F5
    const handleBeforeUnload = (e) => {
      if (!changesRef.current) return;
      e.preventDefault();
      e.returnValue = message;
      return message;
    };

    // Intercepta botão voltar do navegador
    const handlePopState = (e) => {
      if (!changesRef.current) return;
      const leave = window.confirm(message);
      if (!leave) {
        // Fica na página — re-push o estado atual
        window.history.pushState(null, '', window.location.href);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('popstate', handlePopState);
    // Push estado extra para interceptar "voltar"
    if (hasUnsavedChanges) {
      window.history.pushState(null, '', window.location.href);
    }

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('popstate', handlePopState);
    };
  }, [hasUnsavedChanges, message]);
};
