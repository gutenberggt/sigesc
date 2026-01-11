import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { syncService } from '@/services/syncService';
import { countPendingSyncItems } from '@/db/database';

const OfflineContext = createContext(null);

export const OfflineProvider = ({ children }) => {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [isServiceWorkerReady, setIsServiceWorkerReady] = useState(false);
  const [pendingSyncCount, setPendingSyncCount] = useState(0);
  const [lastSyncTime, setLastSyncTime] = useState(null);
  const [syncStatus, setSyncStatus] = useState('idle'); // 'idle' | 'syncing' | 'error' | 'success'
  const [syncProgress, setSyncProgress] = useState({ current: 0, total: 0 });
  
  // Ref para funções que precisam ser acessadas antes de serem declaradas
  const triggerSyncRef = useRef(null);

  // Atualiza contador de itens pendentes
  const updatePendingCount = useCallback(async () => {
    try {
      const count = await countPendingSyncItems();
      setPendingSyncCount(count);
    } catch (err) {
      console.error('[PWA] Erro ao contar pendências:', err);
    }
  }, []);

  // Trigger de sincronização
  const triggerSync = useCallback(async () => {
    if (!navigator.onLine) {
      console.log('[PWA] Offline - sincronização adiada');
      return { success: false, reason: 'offline' };
    }

    setSyncStatus('syncing');
    setSyncProgress({ current: 0, total: 0 });

    try {
      // Processa fila de sincronização
      const result = await syncService.processQueue();

      if (result.success) {
        setLastSyncTime(new Date());
        setSyncStatus('success');
        
        // Reset status após 3 segundos
        setTimeout(() => {
          setSyncStatus('idle');
        }, 3000);
      } else {
        setSyncStatus(result.reason === 'already_syncing' ? 'syncing' : 'error');
      }

      await updatePendingCount();
      return result;

    } catch (error) {
      console.error('[PWA] Erro na sincronização:', error);
      setSyncStatus('error');
      return { success: false, error: error.message };
    }
  }, [updatePendingCount]);

  // Atualiza a ref quando triggerSync muda
  useEffect(() => {
    triggerSyncRef.current = triggerSync;
  }, [triggerSync]);

  // Listener para eventos do syncService
  useEffect(() => {
    const unsubscribe = syncService.addListener((event, data) => {
      switch (event) {
        case 'sync_start':
          setSyncStatus('syncing');
          break;
        case 'sync_progress':
          setSyncProgress({ current: data.current, total: data.total });
          break;
        case 'sync_complete':
          setSyncStatus('success');
          updatePendingCount();
          break;
        case 'sync_error':
          setSyncStatus('error');
          break;
        default:
          break;
      }
    });

    return unsubscribe;
  }, [updatePendingCount]);

  // Monitora status de conexão
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      console.log('[PWA] Conexão restaurada');
      
      // Tenta sincronizar quando volta online
      setTimeout(() => {
        if (triggerSyncRef.current) {
          triggerSyncRef.current();
        }
      }, 1000);
    };

    const handleOffline = () => {
      setIsOnline(false);
      console.log('[PWA] Conexão perdida');
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Registra o Service Worker
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker
        .register('/sw.js')
        .then((registration) => {
          console.log('[PWA] Service Worker registrado:', registration.scope);
          setIsServiceWorkerReady(true);

          // Verifica atualizações
          registration.addEventListener('updatefound', () => {
            const newWorker = registration.installing;
            if (newWorker) {
              newWorker.addEventListener('statechange', () => {
                if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                  console.log('[PWA] Nova versão disponível');
                }
              });
            }
          });
        })
        .catch((error) => {
          console.error('[PWA] Erro ao registrar Service Worker:', error);
        });

      // Escuta mensagens do Service Worker
      navigator.serviceWorker.addEventListener('message', (event) => {
        if (event.data.type === 'SYNC_COMPLETE') {
          setLastSyncTime(new Date());
          setSyncStatus('success');
          updatePendingCount();
        }
      });
    }
  }, [updatePendingCount]);

  // Carrega contador inicial de pendências
  useEffect(() => {
    updatePendingCount();
  }, [updatePendingCount]);

  // Força atualização do Service Worker
  const updateServiceWorker = useCallback(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.ready.then((registration) => {
        registration.update();
      });
    }
  }, []);

  // Limpa cache
  const clearCache = useCallback(async () => {
    if ('caches' in window) {
      const cacheNames = await caches.keys();
      await Promise.all(
        cacheNames.map((name) => caches.delete(name))
      );
      console.log('[PWA] Cache limpo');
    }
  }, []);

  const value = {
    isOnline,
    isServiceWorkerReady,
    pendingSyncCount,
    lastSyncTime,
    syncStatus,
    syncProgress,
    triggerSync,
    updateServiceWorker,
    clearCache,
    updatePendingCount
  };

  return (
    <OfflineContext.Provider value={value}>
      {children}
    </OfflineContext.Provider>
  );
};

export const useOffline = () => {
  const context = useContext(OfflineContext);
  if (!context) {
    throw new Error('useOffline deve ser usado dentro de OfflineProvider');
  }
  return context;
};

export default OfflineContext;
