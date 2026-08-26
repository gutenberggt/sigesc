import { useState } from 'react';

import { useAuth } from '@/contexts/AuthContext';
import { stopImpersonationSession } from '@/services/impersonationSession';
import { Layout as LegacyLayout } from './LayoutLegacy';

export const Layout = ({ children }) => {
  const { user } = useAuth();
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState('');
  const impersonation = user?.impersonation?.active ? user.impersonation : null;

  const stopTest = async () => {
    if (!impersonation || stopping) return;
    setStopping(true);
    setError('');
    try {
      await stopImpersonationSession();
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Não foi possível encerrar o modo de teste.');
      setStopping(false);
    }
  };

  const captureLogout = (event) => {
    if (!impersonation) return;
    const target = event.target instanceof Element ? event.target : null;
    const logoutButton = target?.closest?.('[data-testid="logout-button"]');
    if (!logoutButton) return;
    event.preventDefault();
    event.stopPropagation();
    stopTest();
  };

  return (
    <div onClickCapture={captureLogout}>
      <LegacyLayout>{children}</LegacyLayout>

      {impersonation && (
        <div
          className="fixed bottom-14 left-0 right-0 z-[70] border-y border-amber-300 bg-amber-100 px-4 py-2 shadow-lg"
          data-testid="impersonation-banner"
        >
          <div className="mx-auto flex max-w-7xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm text-amber-950">
              <strong>Modo de teste ativo:</strong>{' '}
              você está atuando como <strong>{impersonation.subject?.name || user?.full_name}</strong>
              {' '}({impersonation.subject?.role || user?.role}). Todas as ações são auditadas com
              {' '}<strong>{impersonation.actor?.name || 'Super Administrador'}</strong> como ator real.
              {error && <span className="ml-2 font-medium text-red-700">{error}</span>}
            </div>
            <button
              type="button"
              onClick={stopTest}
              disabled={stopping}
              className="shrink-0 rounded-lg bg-amber-900 px-4 py-1.5 text-sm font-semibold text-white hover:bg-amber-950 disabled:bg-gray-500"
              data-testid="stop-impersonation-button"
            >
              {stopping ? 'Encerrando...' : 'Encerrar teste'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
