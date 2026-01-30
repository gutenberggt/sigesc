import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { syncService } from '@/services/syncService';
import { countPendingSyncItems, initializeDatabase } from '@/db/database';
import { notificationService } from '@/services/notificationService';

const OfflineContext = createContext(null);

export const OfflineProvider = ({ children }) => {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [isServiceWorkerReady, setIsServiceWorkerReady] = useState(false);
  const [isDatabaseReady, setIsDatabaseReady] = useState(false);
  const [pendingSyncCount, setPendingSyncCount] = useState(0);
  const [lastSyncTime, setLastSyncTime] = useState(null);
  const [syncStatus, setSyncStatus] = useState('idle'); // 'idle' | 'syncing' | 'error' | 'success'
  const [syncProgress, setSyncProgress] = useState({ current: 0, total: 0 });
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  
  // Ref para funções que precisam ser acessadas antes de serem declaradas
  const triggerSyncRef = useRef(null);
  const wasOfflineRef = useRef(false);

  // Inicializa o banco de dados na montagem
  useEffect(() => {
    const init = async () => {
      try {
        const success = await initializeDatabase();
        setIsDatabaseReady(success);
        if (success) {
          console.log('[PWA] Banco de dados inicializado');
        }
      } catch (error) {
        console.error('[PWA] Erro ao inicializar banco de dados:', error);
        setIsDatabaseReady(false);
      }
    };
    init();
  }, []);

  // Solicita permissão para notificações ao carregar
  useEffect(() => {
    const checkNotificationPermission = async () => {
      if (notificationService.hasPermission()) {
        setNotificationsEnabled(true);
      }
    };
    checkNotificationPermission();
  }, []);

  // Função para solicitar permissão de notificações
  const requestNotificationPermission = useCallback(async () => {
    const granted = await notificationService.requestPermission();
    setNotificationsEnabled(granted);
    return granted;
  }, []);

  // Atualiza contador de itens pendentes
  const updatePendingCount = useCallback(async () => {
    if (!isDatabaseReady) return;
    try {
      const count = await countPendingSyncItems();
      setPendingSyncCount(count);
    } catch (err) {
      console.error('[PWA] Erro ao contar pendências:', err);
      // Se for erro de versão, tenta reinicializar
      if (err.name === 'VersionError') {
        console.warn('[PWA] Erro de versão do banco, tentando reinicializar...');
        await initializeDatabase();
      }
    }
  }, [isDatabaseReady]);

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
        
        // Notifica sucesso se tiver itens sincronizados
        if (notificationsEnabled && result.results?.succeeded > 0) {
          await notificationService.notifySyncComplete(result.results.succeeded);
        }
        
        // Reset status após 3 segundos
        setTimeout(() => {
          setSyncStatus('idle');
        }, 3000);
      } else {
        setSyncStatus(result.reason === 'already_syncing' ? 'syncing' : 'error');
        
        // Notifica erro se tiver falhas
        if (notificationsEnabled && result.results?.failed > 0) {
          await notificationService.notifySyncError(result.results.failed);
        }
      }

      await updatePendingCount();
      return result;

    } catch (error) {
      console.error('[PWA] Erro na sincronização:', error);
      setSyncStatus('error');
      
      if (notificationsEnabled) {
        await notificationService.notifySyncError(1);
      }
      
      return { success: false, error: error.message };
    }
  }, [updatePendingCount, notificationsEnabled]);

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
    const handleOnline = async () => {
      setIsOnline(true);
      console.log('[PWA] Conexão restaurada');
      
      // Notifica que voltou online (apenas se estava offline antes)
      if (wasOfflineRef.current && notificationsEnabled) {
        await notificationService.notifyOnline();
      }
      wasOfflineRef.current = false;
      
      // Tenta sincronizar quando volta online
      setTimeout(() => {
        if (triggerSyncRef.current) {
          triggerSyncRef.current();
        }
      }, 1000);
    };

    const handleOffline = async () => {
      setIsOnline(false);
      wasOfflineRef.current = true;
      console.log('[PWA] Conexão perdida');
      
      // Notifica que ficou offline
      if (notificationsEnabled) {
        await notificationService.notifyOffline();
      }
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [notificationsEnabled]);

  // Registra o Service Worker e configura Background Sync
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker
        .register('/sw.js')
        .then(async (registration) => {
          console.log('[PWA] Service Worker registrado:', registration.scope);
          setIsServiceWorkerReady(true);

          // Registra Background Sync se disponível
          if ('sync' in registration) {
            try {
              await registration.sync.register('sync-pending-data');
              console.log('[PWA] Background Sync registrado');
            } catch (err) {
              console.log('[PWA] Background Sync não disponível:', err);
            }
          }

          // Registra Periodic Background Sync se disponível (para verificações periódicas)
          if ('periodicSync' in registration) {
            try {
              const status = await navigator.permissions.query({ name: 'periodic-background-sync' });
              if (status.state === 'granted') {
                await registration.periodicSync.register('sync-check', {
                  minInterval: 60 * 60 * 1000 // 1 hora
                });
                console.log('[PWA] Periodic Background Sync registrado');
              }
            } catch (err) {
              console.log('[PWA] Periodic Sync não disponível:', err);
            }
          }

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
        const { type, payload } = event.data || {};
        
        switch (type) {
          case 'SYNC_COMPLETE':
            console.log('[PWA] Sincronização em background concluída:', payload);
            setLastSyncTime(new Date());
            setSyncStatus('success');
            updatePendingCount();
            setTimeout(() => setSyncStatus('idle'), 3000);
            break;
            
          case 'SYNC_ERROR':
            console.error('[PWA] Erro na sincronização em background:', payload);
            setSyncStatus('error');
            break;
            
          case 'GET_SYNC_INFO':
            // Service Worker está pedindo informações para sincronização
            if (event.ports && event.ports[0]) {
              const token = localStorage.getItem('accessToken');
              const apiUrl = process.env.REACT_APP_BACKEND_URL;
              event.ports[0].postMessage({ token, apiUrl });
            }
            break;
            
          case 'GET_AUTH_TOKEN':
            // Service Worker está pedindo o token
            if (event.ports && event.ports[0]) {
              const token = localStorage.getItem('accessToken');
              event.ports[0].postMessage({ token });
            }
            break;
            
          default:
            break;
        }
      });
    }
  }, [updatePendingCount]);

  // Carrega contador inicial de pendências
  useEffect(() => {
    const loadInitialCount = async () => {
      try {
        const count = await countPendingSyncItems();
        setPendingSyncCount(count);
      } catch (err) {
        console.error('[PWA] Erro ao carregar contagem inicial:', err);
      }
    };
    loadInitialCount();
  }, []);

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
    updatePendingCount,
    notificationsEnabled,
    requestNotificationPermission
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
