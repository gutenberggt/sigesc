import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useOffline } from '@/contexts/OfflineContext';
import { useAuth } from '@/contexts/AuthContext';
import { useSessionStatus } from '@/hooks/useSessionStatus';
import {
  Popover, PopoverTrigger, PopoverContent,
} from '@/components/ui/popover';
import {
  CheckCircle2, CloudOff, Upload, AlertTriangle, RefreshCw, Loader2,
  Wifi, Clock, LogIn,
} from 'lucide-react';
import { toast } from 'sonner';

const CATEGORY_LABELS = {
  grades: 'Notas',
  attendance: 'Frequência',
  learning_objects: 'Conteúdo',
  content: 'Conteúdo',
  outros: 'Outros',
};
const categoryLabel = (k) => CATEGORY_LABELS[k] || (k ? k.charAt(0).toUpperCase() + k.slice(1) : 'Outros');

function timeAgo(date) {
  if (!date) return 'Nunca';
  const d = date instanceof Date ? date : new Date(date);
  const diff = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diff < 60) return 'há poucos segundos';
  if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
  return d.toLocaleDateString('pt-BR');
}

function formatRemaining(ms) {
  if (ms == null) return null;
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m <= 0) return `${s}s`;
  return `${m}min`;
}

/**
 * StatusIndicator (P2) — pílula PERMANENTE no header que consolida conexão,
 * fila de sincronização e estado da sessão numa única fonte de verdade.
 * Prioridade (maior risco pedagógico primeiro):
 *   1. Sessão expirada  2. Falhas  3. Pendências  4. Offline  5. Sincronizando  6. Online
 */
export function StatusIndicator() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const {
    isOnline, pendingSyncCount, failedSyncCount, pendingByCategory,
    lastSyncTime, syncStatus, triggerSync,
  } = useOffline();
  const { sessionState, remainingMs } = useSessionStatus();
  const [syncing, setSyncing] = useState(false);

  const isSyncing = syncing || syncStatus === 'syncing';
  const sessionExpired = sessionState === 'expired';

  // Resolve a aparência da pílula por prioridade
  const view = (() => {
    if (sessionExpired) {
      return { key: 'expired', bg: 'bg-red-100 text-red-700 hover:bg-red-200', dot: 'bg-red-500', icon: <LogIn className="w-4 h-4" />, label: 'Sessão expirada' };
    }
    if (failedSyncCount > 0) {
      return { key: 'failed', bg: 'bg-red-100 text-red-700 hover:bg-red-200', dot: 'bg-red-500', icon: <AlertTriangle className="w-4 h-4" />, label: `${failedSyncCount} falha(s)` };
    }
    if (pendingSyncCount > 0) {
      return { key: 'pending', bg: 'bg-orange-100 text-orange-700 hover:bg-orange-200', dot: 'bg-orange-500', icon: <Upload className="w-4 h-4" />, label: `${pendingSyncCount} pendência(s)` };
    }
    if (!isOnline) {
      return { key: 'offline', bg: 'bg-gray-200 text-gray-700 hover:bg-gray-300', dot: 'bg-gray-500', icon: <CloudOff className="w-4 h-4" />, label: 'Offline' };
    }
    if (isSyncing) {
      return { key: 'syncing', bg: 'bg-blue-100 text-blue-700', dot: 'bg-blue-500', icon: <Loader2 className="w-4 h-4 animate-spin" />, label: 'Sincronizando…' };
    }
    return { key: 'online', bg: 'bg-green-100 text-green-700 hover:bg-green-200', dot: 'bg-green-500', icon: <CheckCircle2 className="w-4 h-4" />, label: 'Sincronizado' };
  })();

  const handleSync = async () => {
    if (!isOnline) { toast.error('Sem conexão com a internet'); return; }
    if (pendingSyncCount === 0 && failedSyncCount === 0) { toast.info('Nada pendente para sincronizar'); return; }
    setSyncing(true);
    try {
      const result = await triggerSync();
      if (result?.success) toast.success(`${result.results?.succeeded || 0} item(ns) sincronizado(s)`);
      else toast.error('Não foi possível concluir a sincronização');
    } catch {
      toast.error('Erro na sincronização');
    } finally {
      setSyncing(false);
    }
  };

  const handleRelogin = async () => {
    await logout(); // preserva sessão offline e rascunhos locais
    navigate('/login');
  };

  const sessionText = (() => {
    if (sessionState === 'expired') return { color: 'text-red-600', label: 'Expirada — faça login novamente' };
    if (sessionState === 'warn1' || sessionState === 'warn5') return { color: 'text-amber-600', label: `Expira em ${formatRemaining(remainingMs)}` };
    return { color: 'text-green-600', label: remainingMs != null ? `Ativa (expira em ${formatRemaining(remainingMs)})` : 'Ativa' };
  })();

  const categories = Object.entries(pendingByCategory || {}).filter(([, v]) => (v.pending || 0) + (v.failed || 0) > 0);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${view.bg}`}
          data-testid="status-indicator"
          aria-label={`Status do sistema: ${view.label}`}
        >
          <span className="relative flex h-2 w-2">
            {(view.key === 'pending' || view.key === 'failed' || view.key === 'expired') && (
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-60 ${view.dot}`} />
            )}
            <span className={`relative inline-flex rounded-full h-2 w-2 ${view.dot}`} />
          </span>
          {view.icon}
          <span className="hidden sm:inline">{view.label}</span>
        </button>
      </PopoverTrigger>

      <PopoverContent align="end" className="w-80 p-0" data-testid="status-indicator-popover">
        <div className="p-4 border-b">
          <p className="text-sm font-semibold text-gray-900 flex items-center gap-2">
            {isOnline ? <Wifi className="w-4 h-4 text-green-600" /> : <CloudOff className="w-4 h-4 text-gray-500" />}
            {isOnline ? 'Conectado à internet' : 'Sem conexão (modo offline)'}
          </p>
          <p className="text-xs text-gray-500 mt-1 flex items-center gap-1">
            <Clock className="w-3 h-3" /> Última sincronização: {timeAgo(lastSyncTime)}
          </p>
        </div>

        {/* Sessão */}
        <div className="p-4 border-b">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Sessão</p>
          <p className={`text-sm font-medium ${sessionText.color}`} data-testid="status-session-state">{sessionText.label}</p>
          {sessionExpired && (
            <button
              onClick={handleRelogin}
              className="mt-2 w-full inline-flex items-center justify-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
              data-testid="status-relogin-button"
            >
              <LogIn className="w-4 h-4" /> Entrar novamente
            </button>
          )}
        </div>

        {/* Pendências / Falhas */}
        <div className="p-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Sincronização</p>
            <span className="text-xs text-gray-500">
              {pendingSyncCount} pend. · {failedSyncCount} falha(s)
            </span>
          </div>

          {categories.length > 0 ? (
            <div className="space-y-1.5 mb-3" data-testid="status-categories">
              {categories.map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-sm">
                  <span className="text-gray-700">{categoryLabel(k)}</span>
                  <span className="flex items-center gap-1.5">
                    {v.pending > 0 && <span className="text-xs px-1.5 py-0.5 rounded bg-orange-100 text-orange-700">{v.pending} pend.</span>}
                    {v.failed > 0 && <span className="text-xs px-1.5 py-0.5 rounded bg-red-100 text-red-700">{v.failed} falha(s)</span>}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500 mb-3">Tudo sincronizado. Nenhum item aguardando envio.</p>
          )}

          <button
            onClick={handleSync}
            disabled={!isOnline || isSyncing || (pendingSyncCount === 0 && failedSyncCount === 0)}
            className="w-full inline-flex items-center justify-center gap-1.5 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
            data-testid="status-resync-button"
          >
            {isSyncing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            {isSyncing ? 'Sincronizando…' : 'Sincronizar agora'}
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export default StatusIndicator;
