// SIGESC Service Worker - Versão 2.0.0
// Atualizado com Background Sync completo
const CACHE_NAME = 'sigesc-cache-v2';
const OFFLINE_URL = '/offline.html';
const DB_NAME = 'SigescOfflineDB';
const DB_VERSION = 1;

// Assets estáticos para cache imediato
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/offline.html',
  '/manifest.json'
];

// Padrões de URL para cache dinâmico
const CACHE_PATTERNS = {
  static: /\.(js|css|png|jpg|jpeg|svg|ico|woff|woff2)$/,
  pages: /^\/(login|dashboard|admin|professor)/,
  api: /\/api\/(schools|classes|courses|students|mantenedora)/
};

// ============= IndexedDB Helper para Service Worker =============

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      
      // Cria stores se não existirem
      if (!db.objectStoreNames.contains('syncQueue')) {
        const syncStore = db.createObjectStore('syncQueue', { keyPath: 'id', autoIncrement: true });
        syncStore.createIndex('status', 'status', { unique: false });
        syncStore.createIndex('collection', 'collection', { unique: false });
      }
    };
  });
}

async function getPendingSyncItems() {
  try {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(['syncQueue'], 'readonly');
      const store = transaction.objectStore('syncQueue');
      const index = store.index('status');
      const request = index.getAll('pending');
      
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  } catch (error) {
    console.error('[SW] Erro ao buscar itens pendentes:', error);
    return [];
  }
}

async function updateSyncItem(id, updates) {
  try {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(['syncQueue'], 'readwrite');
      const store = transaction.objectStore('syncQueue');
      const getRequest = store.get(id);
      
      getRequest.onsuccess = () => {
        const item = getRequest.result;
        if (item) {
          Object.assign(item, updates);
          const putRequest = store.put(item);
          putRequest.onsuccess = () => resolve(true);
          putRequest.onerror = () => reject(putRequest.error);
        } else {
          resolve(false);
        }
      };
      getRequest.onerror = () => reject(getRequest.error);
    });
  } catch (error) {
    console.error('[SW] Erro ao atualizar item:', error);
    return false;
  }
}

async function removeSyncItem(id) {
  try {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(['syncQueue'], 'readwrite');
      const store = transaction.objectStore('syncQueue');
      const request = store.delete(id);
      
      request.onsuccess = () => resolve(true);
      request.onerror = () => reject(request.error);
    });
  } catch (error) {
    console.error('[SW] Erro ao remover item:', error);
    return false;
  }
}

function getAuthToken() {
  // Service Worker não tem acesso direto ao localStorage
  // Usa a API de clients para pedir o token
  return self.clients.matchAll().then(clients => {
    if (clients.length > 0) {
      return new Promise((resolve) => {
        const messageChannel = new MessageChannel();
        messageChannel.port1.onmessage = (event) => {
          resolve(event.data.token);
        };
        clients[0].postMessage({ type: 'GET_AUTH_TOKEN' }, [messageChannel.port2]);
        
        // Timeout de 5 segundos
        setTimeout(() => resolve(null), 5000);
      });
    }
    return null;
  });
}

// ============= Instalação do Service Worker =============

self.addEventListener('install', (event) => {
  console.log('[SW] Instalando Service Worker v2.0.0...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Cacheando assets estáticos');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        console.log('[SW] Service Worker instalado');
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error('[SW] Erro na instalação:', error);
      })
  );
});

// ============= Ativação do Service Worker =============

self.addEventListener('activate', (event) => {
  console.log('[SW] Ativando Service Worker...');
  
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => name !== CACHE_NAME)
            .map((name) => {
              console.log('[SW] Removendo cache antigo:', name);
              return caches.delete(name);
            })
        );
      })
      .then(() => {
        console.log('[SW] Service Worker ativado');
        return self.clients.claim();
      })
  );
});

// ============= Interceptação de requisições =============

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  if (request.method !== 'GET') {
    return;
  }
  
  if (url.protocol === 'chrome-extension:' || url.protocol === 'moz-extension:') {
    return;
  }
  
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstStrategy(request));
  } else if (CACHE_PATTERNS.static.test(url.pathname)) {
    event.respondWith(cacheFirstStrategy(request));
  } else {
    event.respondWith(networkFirstStrategy(request));
  }
});

async function cacheFirstStrategy(request) {
  const cachedResponse = await caches.match(request);
  
  if (cachedResponse) {
    fetchAndCache(request);
    return cachedResponse;
  }
  
  return fetchAndCache(request);
}

async function networkFirstStrategy(request) {
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('[SW] Rede falhou, buscando do cache:', request.url);
    
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
      return cachedResponse;
    }
    
    if (request.mode === 'navigate') {
      return caches.match(OFFLINE_URL);
    }
    
    return new Response(
      JSON.stringify({ error: 'Offline - dados não disponíveis' }),
      { 
        status: 503,
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
}

async function fetchAndCache(request) {
  try {
    const response = await fetch(request);
    
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    
    return response;
  } catch (error) {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    throw error;
  }
}

// ============= Background Sync Completo =============

self.addEventListener('sync', (event) => {
  console.log('[SW] Background Sync disparado:', event.tag);
  
  if (event.tag === 'sync-pending-data' || event.tag === 'sync-grades' || event.tag === 'sync-attendance') {
    event.waitUntil(syncAllPendingData());
  }
});

// Função principal de sincronização
async function syncAllPendingData() {
  console.log('[SW] Iniciando sincronização de dados pendentes...');
  
  try {
    const pendingItems = await getPendingSyncItems();
    
    if (pendingItems.length === 0) {
      console.log('[SW] Nenhum item pendente para sincronizar');
      await notifyClients('SYNC_COMPLETE', { processed: 0, succeeded: 0, failed: 0 });
      return;
    }
    
    console.log(`[SW] Sincronizando ${pendingItems.length} itens...`);
    
    // Agrupa por coleção
    const operations = pendingItems.map(item => ({
      collection: item.collection,
      operation: item.operation,
      recordId: item.recordId,
      data: item.data,
      timestamp: item.timestamp,
      localId: item.id
    }));
    
    // Tenta enviar para o servidor
    const result = await sendToServer(operations);
    
    if (result.success) {
      // Remove itens sincronizados com sucesso
      for (const item of result.succeeded) {
        await removeSyncItem(item.localId);
      }
      
      // Marca itens com erro para retry
      for (const item of result.failed) {
        await updateSyncItem(item.localId, {
          status: item.retries >= 3 ? 'failed' : 'pending',
          retries: (item.retries || 0) + 1,
          lastError: item.error
        });
      }
      
      console.log(`[SW] Sincronização concluída: ${result.succeeded.length} sucesso, ${result.failed.length} falhas`);
      
      // Notifica clientes
      await notifyClients('SYNC_COMPLETE', {
        processed: operations.length,
        succeeded: result.succeeded.length,
        failed: result.failed.length
      });
      
      // Mostra notificação se houver sucesso
      if (result.succeeded.length > 0) {
        await showSyncNotification(result.succeeded.length, result.failed.length);
      }
    } else {
      console.error('[SW] Erro na sincronização:', result.error);
      await notifyClients('SYNC_ERROR', { error: result.error });
    }
    
  } catch (error) {
    console.error('[SW] Erro crítico na sincronização:', error);
    await notifyClients('SYNC_ERROR', { error: error.message });
  }
}

// Envia dados para o servidor
async function sendToServer(operations) {
  try {
    // Obtém a URL do backend do primeiro cliente disponível
    const clients = await self.clients.matchAll();
    let apiUrl = '';
    let token = '';
    
    if (clients.length > 0) {
      // Pede informações ao cliente
      const clientInfo = await new Promise((resolve) => {
        const messageChannel = new MessageChannel();
        messageChannel.port1.onmessage = (event) => {
          resolve(event.data);
        };
        clients[0].postMessage({ type: 'GET_SYNC_INFO' }, [messageChannel.port2]);
        
        setTimeout(() => resolve({ apiUrl: '', token: '' }), 5000);
      });
      
      apiUrl = clientInfo.apiUrl;
      token = clientInfo.token;
    }
    
    if (!apiUrl || !token) {
      // Tenta usar valores do IndexedDB ou fallback
      console.log('[SW] Não foi possível obter apiUrl ou token do cliente');
      return { success: false, error: 'Credenciais não disponíveis', succeeded: [], failed: operations };
    }
    
    const response = await fetch(`${apiUrl}/api/sync/push`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ operations })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    const serverResult = await response.json();
    
    // Processa resultado do servidor
    const succeeded = [];
    const failed = [];
    
    for (const result of serverResult.results || []) {
      const op = operations.find(o => o.recordId === result.recordId);
      if (result.success) {
        succeeded.push({ ...op, serverId: result.serverId });
      } else {
        failed.push({ ...op, error: result.error });
      }
    }
    
    return { success: true, succeeded, failed };
    
  } catch (error) {
    console.error('[SW] Erro ao enviar para servidor:', error);
    return { 
      success: false, 
      error: error.message, 
      succeeded: [], 
      failed: operations.map(op => ({ ...op, error: error.message }))
    };
  }
}

// Notifica todos os clientes
async function notifyClients(type, payload) {
  const clients = await self.clients.matchAll();
  clients.forEach(client => {
    client.postMessage({ type, payload });
  });
}

// Mostra notificação de sincronização
async function showSyncNotification(succeeded, failed) {
  if (self.registration.showNotification) {
    const title = 'SIGESC - Sincronização';
    let body = `${succeeded} registro(s) sincronizado(s) com sucesso.`;
    if (failed > 0) {
      body += ` ${failed} falha(s).`;
    }
    
    await self.registration.showNotification(title, {
      body,
      icon: '/icons/icon-192x192.png',
      badge: '/icons/icon-72x72.png',
      vibrate: [100, 50, 100],
      tag: 'sync-notification',
      renotify: true
    });
  }
}

// ============= Periodic Background Sync (quando disponível) =============

self.addEventListener('periodicsync', (event) => {
  if (event.tag === 'sync-check') {
    console.log('[SW] Periodic Sync: verificando dados pendentes');
    event.waitUntil(syncAllPendingData());
  }
});

// ============= Notificações Push =============

self.addEventListener('push', (event) => {
  const data = event.data?.json() || {};
  
  const options = {
    body: data.body || 'Novos dados disponíveis',
    icon: '/icons/icon-192x192.png',
    badge: '/icons/icon-72x72.png',
    vibrate: [100, 50, 100],
    data: data.url || '/',
    actions: [
      { action: 'open', title: 'Abrir' },
      { action: 'close', title: 'Fechar' }
    ]
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title || 'SIGESC', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  if (event.action === 'open' || !event.action) {
    event.waitUntil(
      clients.matchAll({ type: 'window' }).then((clientList) => {
        // Se já tem uma janela aberta, foca nela
        for (const client of clientList) {
          if (client.url.includes('sigesc') && 'focus' in client) {
            return client.focus();
          }
        }
        // Senão, abre uma nova
        if (clients.openWindow) {
          return clients.openWindow(event.notification.data || '/');
        }
      })
    );
  }
});

// ============= Mensagens do Cliente =============

self.addEventListener('message', (event) => {
  console.log('[SW] Mensagem recebida:', event.data?.type);
  
  const { type, payload } = event.data || {};
  
  switch (type) {
    case 'SKIP_WAITING':
      self.skipWaiting();
      break;
      
    case 'CLEAR_CACHE':
      caches.delete(CACHE_NAME).then(() => {
        console.log('[SW] Cache limpo');
      });
      break;
      
    case 'TRIGGER_SYNC':
      // Dispara sincronização manual
      syncAllPendingData();
      break;
      
    case 'GET_AUTH_TOKEN':
      // Resposta para pedido de token (handled pelo cliente)
      break;
      
    case 'GET_SYNC_INFO':
      // Resposta para pedido de info de sync (handled pelo cliente)
      break;
  }
});

console.log('[SW] Service Worker v2.0.0 carregado com Background Sync');
