import { useState } from 'react';
import { useOffline } from '@/contexts/OfflineContext';
import { db } from '@/db/database';
import { useLiveQuery } from 'dexie-react-hooks';
import { 
  Cloud, CloudOff, RefreshCw, CheckCircle, AlertCircle, 
  Upload, Loader2
} from 'lucide-react';
import { toast } from 'sonner';

/**
 * Indicador compacto de sincronização para uso no header/navbar
 * Mostra status de conexão e pendências de forma minimalista
 */
export function SyncIndicator({ className = '' }) {
  const { isOnline, syncStatus, triggerSync } = useOffline();
  const [syncing, setSyncing] = useState(false);

  // Conta pendências em tempo real
  const pendingCount = useLiveQuery(
    () => db.syncQueue.where('status').anyOf(['pending', 'failed']).count(),
    [],
    0
  );

  const handleSync = async (e) => {
    e.stopPropagation();
    
    if (!isOnline) {
      toast.error('Sem conexão com internet');
      return;
    }
    
    if (pendingCount === 0) {
      toast.info('Nenhum item pendente para sincronizar');
      return;
    }

    setSyncing(true);
    try {
      const result = await triggerSync();
      if (result.success) {
        toast.success(`${result.results?.succeeded || 0} item(ns) sincronizado(s)`);
      }
    } catch (err) {
      toast.error('Erro na sincronização');
    } finally {
      setSyncing(false);
    }
  };

  // Status: sincronizando
  if (syncing || syncStatus === 'syncing') {
    return (
      <div className={`flex items-center gap-2 px-3 py-1.5 bg-blue-100 text-blue-700 rounded-full text-sm ${className}`}>
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="hidden sm:inline">Sincronizando...</span>
      </div>
    );
  }

  // Status: offline
  if (!isOnline) {
    return (
      <div className={`flex items-center gap-2 px-3 py-1.5 bg-gray-100 text-gray-600 rounded-full text-sm ${className}`}>
        <CloudOff className="w-4 h-4" />
        <span className="hidden sm:inline">Offline</span>
        {pendingCount > 0 && (
          <span className="bg-orange-500 text-white text-xs px-1.5 py-0.5 rounded-full">
            {pendingCount}
          </span>
        )}
      </div>
    );
  }

  // Status: pendências
  if (pendingCount > 0) {
    return (
      <button
        onClick={handleSync}
        className={`flex items-center gap-2 px-3 py-1.5 bg-orange-100 text-orange-700 rounded-full text-sm hover:bg-orange-200 transition-colors ${className}`}
        title="Clique para sincronizar"
      >
        <Upload className="w-4 h-4" />
        <span className="hidden sm:inline">{pendingCount} pendente(s)</span>
        <span className="sm:hidden">{pendingCount}</span>
      </button>
    );
  }

  // Status: sincronizado
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 bg-green-100 text-green-700 rounded-full text-sm ${className}`}>
      <CheckCircle className="w-4 h-4" />
      <span className="hidden sm:inline">Sincronizado</span>
    </div>
  );
}

/**
 * Badge flutuante de sincronização (canto inferior direito)
 * Mostra status persistente sem ocupar espaço no header
 */
export function SyncFloatingBadge() {
  const { isOnline, triggerSync } = useOffline();
  const [syncing, setSyncing] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const pendingCount = useLiveQuery(
    () => db.syncQueue.where('status').anyOf(['pending', 'failed']).count(),
    [],
    0
  );

  const failedCount = useLiveQuery(
    () => db.syncQueue.where('status').equals('failed').count(),
    [],
    0
  );

  const handleSync = async () => {
    if (!isOnline || syncing) return;
    
    setSyncing(true);
    try {
      await triggerSync();
      toast.success('Sincronização concluída!');
    } catch (err) {
      toast.error('Erro na sincronização');
    } finally {
      setSyncing(false);
    }
  };

  // Não mostra se está tudo ok e online
  if (isOnline && pendingCount === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <div 
        className={`flex items-center gap-2 px-4 py-2 rounded-full shadow-lg cursor-pointer transition-all ${
          !isOnline 
            ? 'bg-gray-800 text-white' 
            : failedCount > 0
              ? 'bg-red-600 text-white'
              : 'bg-orange-500 text-white'
        }`}
        onClick={() => setExpanded(!expanded)}
      >
        {syncing ? (
          <Loader2 className="w-5 h-5 animate-spin" />
        ) : !isOnline ? (
          <CloudOff className="w-5 h-5" />
        ) : failedCount > 0 ? (
          <AlertCircle className="w-5 h-5" />
        ) : (
          <Upload className="w-5 h-5" />
        )}
        
        <span className="font-medium">
          {!isOnline 
            ? 'Modo Offline' 
            : syncing 
              ? 'Sincronizando...'
              : `${pendingCount} pendente(s)`
          }
        </span>
      </div>

      {/* Menu expandido */}
      {expanded && (
        <div className="absolute bottom-full right-0 mb-2 bg-white rounded-lg shadow-xl border p-3 min-w-[200px]">
          <div className="text-sm text-gray-600 mb-2">
            {!isOnline ? (
              <p>Você está offline. Os dados serão sincronizados quando a conexão for restaurada.</p>
            ) : (
              <p>{pendingCount} operação(ões) aguardando envio ao servidor.</p>
            )}
          </div>
          
          {failedCount > 0 && (
            <p className="text-xs text-red-600 mb-2">
              {failedCount} item(ns) com erro de sincronização.
            </p>
          )}
          
          {isOnline && pendingCount > 0 && (
            <button
              onClick={handleSync}
              disabled={syncing}
              className="w-full px-3 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:bg-gray-400 flex items-center justify-center gap-2"
            >
              {syncing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              Sincronizar agora
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default SyncIndicator;
