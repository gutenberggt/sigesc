import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ShieldAlert, WifiOff, LogIn } from 'lucide-react';
import {
  Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { getTokenExpMs, computeSessionState } from '@/utils/sessionToken';

const WARN_5_TOAST_ID = 'session-warn-5';
const WARN_1_TOAST_ID = 'session-warn-1';

/**
 * SessionMonitor (P0) — monitor global de sessão.
 * - Avisa aos 5 min e 1 min antes da expiração do access token.
 * - Botão "Continuar conectado" renova a sessão na hora.
 * - Ao expirar (token vencido + renovação falha), exibe modal obrigatório
 *   com "Entrar novamente" e "Continuar offline" (preserva dados locais).
 */
export const SessionMonitor = () => {
  const { user, accessToken, isOfflineSession, extendSession, enterOfflineMode, logout } = useAuth();
  const navigate = useNavigate();

  const [expired, setExpired] = useState(false);
  const warned5 = useRef(false);
  const warned1 = useRef(false);
  const lastExpMs = useRef(null);
  const expiringCheck = useRef(false);

  const resetWarnings = useCallback(() => {
    warned5.current = false;
    warned1.current = false;
    toast.dismiss(WARN_5_TOAST_ID);
    toast.dismiss(WARN_1_TOAST_ID);
  }, []);

  const handleExtend = useCallback(async () => {
    const ok = await extendSession();
    if (ok) {
      resetWarnings();
      setExpired(false);
      toast.success('Sessão renovada. Você continua conectado.', { id: 'session-renewed' });
    } else {
      setExpired(true);
    }
  }, [extendSession, resetWarnings]);

  useEffect(() => {
    if (!user) return undefined;

    const tick = async () => {
      // Sessão já em modo offline: não há contagem online a fazer.
      if (isOfflineSession) {
        resetWarnings();
        return;
      }
      const expMs = getTokenExpMs(accessToken);
      if (!expMs) return; // token offline/inválido — sem contador

      // Token renovado (exp avançou): zera avisos e modal.
      if (lastExpMs.current && expMs > lastExpMs.current) {
        resetWarnings();
        setExpired(false);
      }
      lastExpMs.current = expMs;

      const remaining = expMs - Date.now();
      const state = computeSessionState(remaining);

      if (state === 'expired') {
        if (!expiringCheck.current && !expired) {
          // Tenta renovar silenciosamente uma vez antes de declarar expirado.
          expiringCheck.current = true;
          const ok = await extendSession();
          expiringCheck.current = false;
          if (ok) {
            resetWarnings();
          } else {
            setExpired(true);
          }
        }
        return;
      }

      if (state === 'warn1') {
        if (!warned1.current) {
          warned1.current = true;
          toast.dismiss(WARN_5_TOAST_ID);
          toast.warning('Sua sessão expira em menos de 1 minuto.', {
            id: WARN_1_TOAST_ID,
            duration: 60000,
            description: 'Clique para continuar conectado e não perder seu trabalho.',
            action: { label: 'Continuar conectado', onClick: () => handleExtend() },
          });
        }
      } else if (state === 'warn5') {
        if (!warned5.current) {
          warned5.current = true;
          toast.warning(`Sua sessão expira em cerca de ${Math.ceil(remaining / 60000)} min.`, {
            id: WARN_5_TOAST_ID,
            duration: 60000,
            description: 'Salve seu trabalho ou continue conectado.',
            action: { label: 'Continuar conectado', onClick: () => handleExtend() },
          });
        }
      }
    };

    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [user, accessToken, isOfflineSession, expired, extendSession, handleExtend, resetWarnings]);

  const handleReLogin = useCallback(async () => {
    setExpired(false);
    resetWarnings();
    await logout(); // preserva sessão offline / rascunhos; apenas encerra a sessão online
    navigate('/login');
  }, [logout, navigate, resetWarnings]);

  const handleContinueOffline = useCallback(() => {
    enterOfflineMode();
    resetWarnings();
    setExpired(false);
    toast.info('Você está trabalhando offline. Seus dados ficam salvos neste dispositivo.', {
      id: 'session-offline',
    });
  }, [enterOfflineMode, resetWarnings]);

  if (!user) return null;

  return (
    <Dialog open={expired} onOpenChange={() => { /* modal obrigatório: não fecha por clique externo */ }}>
      <DialogContent
        className="sm:max-w-md [&>button]:hidden"
        data-testid="session-expired-modal"
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
            <ShieldAlert className="h-6 w-6 text-red-600" />
          </div>
          <DialogTitle className="text-center" data-testid="session-expired-title">
            Sua sessão online expirou
          </DialogTitle>
          <DialogDescription className="text-center">
            Por segurança, sua sessão online expirou. Você pode continuar trabalhando offline —
            seus dados permanecem salvos neste dispositivo e serão sincronizados após um novo login.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="flex-col gap-2 sm:flex-col">
          <Button
            onClick={handleReLogin}
            className="w-full"
            data-testid="session-relogin-button"
          >
            <LogIn className="mr-2 h-4 w-4" /> Entrar novamente
          </Button>
          <Button
            onClick={handleContinueOffline}
            variant="outline"
            className="w-full"
            data-testid="session-continue-offline-button"
          >
            <WifiOff className="mr-2 h-4 w-4" /> Continuar offline
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default SessionMonitor;
