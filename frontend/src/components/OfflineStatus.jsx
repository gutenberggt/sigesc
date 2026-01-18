import { useState, useEffect } from 'react';
import { useOffline } from '@/contexts/OfflineContext';
import { Wifi, WifiOff, RefreshCw, CloudOff, Check, AlertCircle, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

/**
 * Badge de status de conexão (para uso no header)
 */
export const ConnectionStatusBadge = ({ showDetails = false }) => {
  const { isOnline, pendingSyncCount, syncStatus, triggerSync } = useOffline();

  if (isOnline && pendingSyncCount === 0 && !showDetails) {
    return null; // Não mostra nada se está online e sincronizado
  }

  const getStatusColor = () => {
    if (!isOnline) return 'bg-red-500';
    if (syncStatus === 'syncing') return 'bg-yellow-500';
    if (pendingSyncCount > 0) return 'bg-orange-500';
    return 'bg-green-500';
  };

  const getStatusText = () => {
    if (!isOnline) return 'Offline';
    if (syncStatus === 'syncing') return 'Sincronizando...';
    if (pendingSyncCount > 0) return `${pendingSyncCount} pendente(s)`;
    return 'Sincronizado';
  };

  const getStatusIcon = () => {
    if (!isOnline) return <WifiOff className="w-4 h-4" />;
    if (syncStatus === 'syncing') return <RefreshCw className="w-4 h-4 animate-spin" />;
    if (pendingSyncCount > 0) return <CloudOff className="w-4 h-4" />;
    return <Check className="w-4 h-4" />;
  };

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={isOnline ? triggerSync : undefined}
            className={`
              flex items-center gap-2 px-3 py-1.5 rounded-full text-white text-sm font-medium
              transition-all duration-200 cursor-pointer
              ${getStatusColor()}
              ${isOnline && pendingSyncCount > 0 ? 'hover:opacity-80' : ''}
            `}
          >
            {getStatusIcon()}
            {showDetails && <span>{getStatusText()}</span>}
          </button>
        </TooltipTrigger>
        <TooltipContent>
          <p>{getStatusText()}</p>
          {isOnline && pendingSyncCount > 0 && (
            <p className="text-xs text-gray-400">Clique para sincronizar</p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

/**
 * Banner de aviso offline (para exibir no topo da página)
 */
export const OfflineBanner = () => {
  const { isOnline, pendingSyncCount, syncStatus, triggerSync, lastSyncTime } = useOffline();

  if (isOnline && pendingSyncCount === 0) {
    return null;
  }

  const formatLastSync = () => {
    if (!lastSyncTime) return 'Nunca sincronizado';
    const now = new Date();
    const diff = Math.floor((now - lastSyncTime) / 1000);
    
    if (diff < 60) return 'Há poucos segundos';
    if (diff < 3600) return `Há ${Math.floor(diff / 60)} minuto(s)`;
    if (diff < 86400) return `Há ${Math.floor(diff / 3600)} hora(s)`;
    return lastSyncTime.toLocaleDateString('pt-BR');
  };

  if (!isOnline) {
    return (
      <div className="bg-red-600 text-white px-4 py-2 flex items-center justify-center gap-3">
        <WifiOff className="w-5 h-5" />
        <span className="font-medium">Você está offline</span>
        <span className="text-red-200 text-sm">
          As alterações serão sincronizadas quando a conexão for restaurada
        </span>
      </div>
    );
  }

  if (pendingSyncCount > 0) {
    return (
      <div className="bg-orange-500 text-white px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <CloudOff className="w-5 h-5" />
          <span className="font-medium">{pendingSyncCount} alteração(ões) pendente(s)</span>
          <span className="text-orange-200 text-sm">
            Última sincronização: {formatLastSync()}
          </span>
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={triggerSync}
          disabled={syncStatus === 'syncing'}
          className="bg-white text-orange-600 hover:bg-orange-100"
        >
          {syncStatus === 'syncing' ? (
            <>
              <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
              Sincronizando...
            </>
          ) : (
            <>
              <RefreshCw className="w-4 h-4 mr-2" />
              Sincronizar agora
            </>
          )}
        </Button>
      </div>
    );
  }

  return null;
};

/**
 * Indicador flutuante de status (canto inferior)
 * Fase 5: Mostra detalhes da fila de sincronização quando expandido
 */
export const FloatingStatusIndicator = () => {
  const { isOnline, pendingSyncCount, syncStatus, triggerSync } = useOffline();
  const [expanded, setExpanded] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Busca itens pendentes da fila para mostrar detalhes
  const [pendingItems, setPendingItems] = useState([]);
  
  useEffect(() => {
    const loadPendingItems = async () => {
      try {
        // Importa dinamicamente para evitar dependência circular
        const { db } = await import('@/db/database');
        const items = await db.syncQueue
          .where('status')
          .anyOf(['pending', 'failed'])
          .limit(5)
          .toArray();
        setPendingItems(items);
      } catch (err) {
        console.error('Erro ao carregar itens pendentes:', err);
      }
    };
    
    if (expanded) {
      loadPendingItems();
    }
  }, [expanded, pendingSyncCount]);

  const handleSync = async () => {
    if (!isOnline || syncing) return;
    
    setSyncing(true);
    try {
      await triggerSync();
    } finally {
      setSyncing(false);
    }
  };

  const getIndicatorStyle = () => {
    if (!isOnline) {
      return {
        bg: 'bg-red-600',
        icon: <WifiOff className="w-5 h-5" />,
        text: 'Modo Offline',
        subtext: 'Dados salvos localmente'
      };
    }
    if (syncStatus === 'syncing' || syncing) {
      return {
        bg: 'bg-yellow-500',
        icon: <RefreshCw className="w-5 h-5 animate-spin" />,
        text: 'Sincronizando...',
        subtext: 'Aguarde'
      };
    }
    if (syncStatus === 'error') {
      return {
        bg: 'bg-red-500',
        icon: <AlertCircle className="w-5 h-5" />,
        text: 'Erro na sincronização',
        subtext: 'Tente novamente'
      };
    }
    if (pendingSyncCount > 0) {
      return {
        bg: 'bg-orange-500',
        icon: <CloudOff className="w-5 h-5" />,
        text: `${pendingSyncCount} pendente(s)`,
        subtext: 'Clique para detalhes'
      };
    }
    return null; // Não mostra quando está tudo OK
  };

  const style = getIndicatorStyle();

  if (!style) return null;

  const getOperationLabel = (op) => {
    switch (op) {
      case 'create': return 'Criar';
      case 'update': return 'Atualizar';
      case 'delete': return 'Excluir';
      default: return op;
    }
  };

  const getCollectionLabel = (col) => {
    switch (col) {
      case 'grades': return 'Nota';
      case 'attendance': return 'Frequência';
      default: return col;
    }
  };

  return (
    <div className="fixed bottom-24 right-6 z-50">
      {/* Painel expandido */}
      {expanded && (
        <div className="mb-2 bg-white rounded-lg shadow-xl border p-4 w-72 max-h-80 overflow-auto">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-medium text-gray-900">Fila de Sincronização</h4>
            <button 
              onClick={() => setExpanded(false)}
              className="text-gray-400 hover:text-gray-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          
          {pendingItems.length > 0 ? (
            <div className="space-y-2 mb-3">
              {pendingItems.map((item, idx) => (
                <div 
                  key={item.id || idx}
                  className={`text-xs p-2 rounded ${
                    item.status === 'failed' 
                      ? 'bg-red-50 border border-red-200' 
                      : 'bg-gray-50 border border-gray-200'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">
                      {getCollectionLabel(item.collection)}
                    </span>
                    <span className={`px-1.5 py-0.5 rounded text-xs ${
                      item.operation === 'create' ? 'bg-green-100 text-green-700' :
                      item.operation === 'update' ? 'bg-blue-100 text-blue-700' :
                      'bg-red-100 text-red-700'
                    }`}>
                      {getOperationLabel(item.operation)}
                    </span>
                  </div>
                  {item.lastError && (
                    <p className="text-red-600 mt-1 truncate">{item.lastError}</p>
                  )}
                </div>
              ))}
              {pendingSyncCount > 5 && (
                <p className="text-xs text-gray-500 text-center">
                  +{pendingSyncCount - 5} mais item(ns)
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-500 mb-3">Nenhum item na fila</p>
          )}
          
          {isOnline && pendingSyncCount > 0 && (
            <Button
              size="sm"
              onClick={handleSync}
              disabled={syncing}
              className="w-full bg-blue-600 hover:bg-blue-700"
            >
              {syncing ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Sincronizando...
                </>
              ) : (
                <>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Sincronizar agora
                </>
              )}
            </Button>
          )}
        </div>
      )}

      {/* Botão principal */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={`
          flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg
          text-white transition-all duration-300
          ${style.bg}
          cursor-pointer hover:opacity-90
        `}
      >
        {style.icon}
        <div className="text-left">
          <p className="font-medium text-sm">{style.text}</p>
          <p className="text-xs opacity-80">{style.subtext}</p>
        </div>
      </button>
    </div>
  );
};

/**
 * Wrapper para indicar que dados são offline
 */
export const OfflineDataIndicator = ({ children, isOfflineData = false }) => {
  if (!isOfflineData) return children;

  return (
    <div className="relative">
      <div className="absolute -top-2 -right-2 z-10">
        <span className="flex h-5 w-5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-5 w-5 bg-orange-500 items-center justify-center">
            <CloudOff className="w-3 h-3 text-white" />
          </span>
        </span>
      </div>
      {children}
    </div>
  );
};

export default {
  ConnectionStatusBadge,
  OfflineBanner,
  FloatingStatusIndicator,
  OfflineDataIndicator
};
