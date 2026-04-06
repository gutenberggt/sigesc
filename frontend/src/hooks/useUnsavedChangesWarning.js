import { useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';

/**
 * Hook para alertar o usuário sobre alterações não salvas ao sair da página.
 * - Intercepta fechar aba / reload (beforeunload)
 * - Intercepta botão voltar do navegador (popstate)
 * - Retorna guardedNavigate para proteger navegação programática
 * - Sincroniza com contexto global para proteger o botão Sair (logout)
 */
export const useUnsavedChangesWarning = (hasUnsavedChanges, message = 'Você tem alterações não salvas. Deseja sair sem salvar?') => {
  const changesRef = useRef(hasUnsavedChanges);
  changesRef.current = hasUnsavedChanges;
  const navigate = useNavigate();
  const { setUnsavedState } = useUnsavedChangesContext();

  // Sincroniza com o contexto global (Layout lê isso para o botão Sair)
  useEffect(() => {
    setUnsavedState(hasUnsavedChanges, message);
    return () => setUnsavedState(false, '');
  }, [hasUnsavedChanges, message, setUnsavedState]);

  // Navegação protegida para botões internos (ex: Início)
  const guardedNavigate = useCallback((path) => {
    if (changesRef.current) {
      const leave = window.confirm(message);
      if (!leave) return;
    }
    navigate(path);
  }, [navigate, message]);

  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (!changesRef.current) return;
      e.preventDefault();
      e.returnValue = message;
      return message;
    };

    const handlePopState = () => {
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
