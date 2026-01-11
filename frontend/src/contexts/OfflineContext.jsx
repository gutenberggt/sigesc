import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';

const OfflineContext = createContext(null);

export const OfflineProvider = ({ children }) => {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [isServiceWorkerReady, setIsServiceWorkerReady] = useState(false);
  const [pendingSyncCount, setPendingSyncCount] = useState(0);
  const [lastSyncTime, setLastSyncTime] = useState(null);
  const [syncStatus, setSyncStatus] = useState('idle'); // 'idle' | 'syncing' | 'error' | 'success'
  
  // Ref para funções que precisam ser acessadas antes de serem declaradas
  const triggerSyncRef = useRef(null);

  // Atualiza contador de itens pendentes
  const updatePendingCount = useCallback(async () => {
    // Será implementado quando IndexedDB for adicionado
    // Por enquanto, retorna 0
    setPendingSyncCount(0);
  }, []);

  // Sincronização manual (fallback)
  const manualSync = useCallback(async () => {
    // Será implementado na Fase 3
    console.log('[PWA] Sincronização manual iniciada');
    return Promise.resolve();
  }, []);

  // Trigger de sincronização
  const triggerSync = useCallback(async () => {
    if (!navigator.onLine || !isServiceWorkerReady) return;

    setSyncStatus('syncing');

    try {
      // Background Sync API
      if ('serviceWorker' in navigator && 'SyncManager' in window) {
        const registration = await navigator.serviceWorker.ready;
        await registration.sync.register('sync-grades');
        await registration.sync.register('sync-attendance');
      } else {
        // Fallback: sincronização manual
        await manualSync();
      }

      setLastSyncTime(new Date());
      setSyncStatus('success');
      updatePendingCount();
    } catch (error) {
      console.error('[PWA] Erro na sincronização:', error);
      setSyncStatus('error');
    }
  }, [isServiceWorkerReady, updatePendingCount, manualSync]);

  // Atualiza a ref quando triggerSync muda
  useEffect(() => {
    triggerSyncRef.current = triggerSync;
  }, [triggerSync]);

  // Monitora status de conexão
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      // Tenta sincronizar quando volta online
      if (triggerSyncRef.current) {
        triggerSyncRef.current();
      }
    };

    const handleOffline = () => {
      setIsOnline(false);
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
                  // Nova versão disponível
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
