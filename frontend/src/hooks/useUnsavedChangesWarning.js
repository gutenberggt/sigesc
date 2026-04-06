import { useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * Hook para alertar o usuário sobre alterações não salvas ao sair da página.
 * - Intercepta fechar aba / reload (beforeunload)
 * - Intercepta botão voltar do navegador (popstate)
 * - Retorna uma função `guardedNavigate` que verifica alterações antes de navegar
 * @param {boolean} hasUnsavedChanges - Se há alterações não salvas
 * @param {string} message - Mensagem do alerta
 * @returns {{ guardedNavigate: (path: string) => void }}
 */
export const useUnsavedChangesWarning = (hasUnsavedChanges, message = 'Você tem alterações não salvas. Deseja sair sem salvar?') => {
  const changesRef = useRef(hasUnsavedChanges);
  changesRef.current = hasUnsavedChanges;
  const navigate = useNavigate();

  // Navegação protegida para uso em botões/links internos
  const guardedNavigate = useCallback((path) => {
    if (changesRef.current) {
      const leave = window.confirm(message);
      if (!leave) return;
    }
    navigate(path);
  }, [navigate, message]);

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
        window.history.pushState(null, '', window.location.href);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('popstate', handlePopState);
    if (hasUnsavedChanges) {
      window.history.pushState(null, '', window.location.href);
    }

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('popstate', handlePopState);
    };
  }, [hasUnsavedChanges, message]);

  return { guardedNavigate };
};
