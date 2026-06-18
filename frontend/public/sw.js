// SIGESC Service Worker - Versão 2.11.0
// [Jun/2026] LOGIN OFFLINE SEMPRE: o app shell (index.html) é pré-cacheado já na
// instalação do SW (visita online) e também a cada navegação online. Offline, a
// navegação serve o shell cacheado → React inicia → tela de LOGIN, nunca a página
// estática offline.html (esta só aparece em dispositivo que NUNCA acessou online).
// [Jun/2026] Background Sync agora envia X-CSRF-Token (derivado do JWT) → corrige
// o 403 silencioso que quebrava a sincronização automática em segundo plano.
// [Fev/2026] Bump após fix CORS + correção do loop "Carregando" em browsers com SW antigo.
// Removidos '/' e '/index.html' do precache para sempre puxar a versão fresca do servidor
// (impedindo que bundles JS antigos quebrem o app após deploy).
const CACHE_NAME = 'sigesc-cache-v17';
const OFFLINE_URL = '/offline.html';
// Chave fixa onde o app shell (index.html) é cacheado dinamicamente a cada visita online.
const APP_SHELL_URL = '/index.html';
const DB_NAME = 'SigescOfflineDB';

// Assets estáticos para cache imediato.
// IMPORTANTE: NÃO incluir '/' nem '/index.html' aqui — isso causa loop após deploy
// pois o index cacheado aponta para bundles JS com hash antigo que já não existem.
const STATIC_ASSETS = [
  '/offline.html',
  '/manifest.json'
];

// Padrões de URL para cache dinâmico
const CACHE_PATTERNS = {
  static: /\.(js|css|png|jpg|jpeg|svg|ico|woff|woff2)$/,
  pages: /^\/(login|dashboard|admin|professor)/,
  api: /\/api\/(schools|classes|courses|students|mantenedora)/
};

// Endpoints de roster MUITO dinâmicos (frequência/notas/detalhes da turma).
// NUNCA devem ser cacheados pelo SW: precisam refletir na hora cancelamentos,
// transferências, novas matrículas etc. Quando offline, o app usa o IndexedDB
// (Dexie) próprio — não a resposta da API cacheada pelo SW.
const NEVER_CACHE_API = /\/api\/(attendance|grades|classes\/[^/]+\/(details|cancelled-enrollments))/;

// ============= IndexedDB Helper para Service Worker =============

function openDatabase() {
  return new Promise((resolve, reject) => {
    // Abre SEM versão fixa para compatibilizar com qualquer versão existente
    const request = indexedDB.open(DB_NAME);

    request.onerror = () => reject(request.error);

    request.onsuccess = () => {
      const db = request.result;
      // Se o store syncQueue já existe, usa normalmente
      if (db.objectStoreNames.contains('syncQueue')) {
        resolve(db);
      } else {
        // Store não existe — precisa de upgrade para criá-lo
        const currentVersion = db.version;
        db.close();
        const upgradeRequest = indexedDB.open(DB_NAME, currentVersion + 1);
        upgradeRequest.onerror = () => reject(upgradeRequest.error);
        upgradeRequest.onsuccess = () => resolve(upgradeRequest.result);
        upgradeRequest.onupgradeneeded = (event) => {
          const upgradeDb = event.target.result;
          if (!upgradeDb.objectStoreNames.contains('syncQueue')) {
            const syncStore = upgradeDb.createObjectStore('syncQueue', { keyPath: 'id', autoIncrement: true });
            syncStore.createIndex('status', 'status', { unique: false });
            syncStore.createIndex('collection', 'collection', { unique: false });
          }
        };
      }
    };

    // Dispara se o banco está sendo criado pela primeira vez
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
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
    console.warn('[SW] IndexedDB indisponível para sync:', error.name);
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
    console.warn('[SW] Erro ao atualizar item:', error.name);
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
    console.warn('[SW] Erro ao remover item:', error.name);
    return false;
  }
}

function getAuthToken() {
  return self.clients.matchAll().then(clients => {
    if (clients.length > 0) {
      return new Promise((resolve) => {
        const messageChannel = new MessageChannel();
        messageChannel.port1.onmessage = (event) => {
          resolve(event.data.token);
        };
        clients[0].postMessage({ type: 'GET_AUTH_TOKEN' }, [messageChannel.port2]);
        setTimeout(() => resolve(null), 5000);
      });
    }
    return null;
  });
}

// ============= Instalação do Service Worker =============

self.addEventListener('install', (event) => {
  console.log('[SW] Instalando Service Worker v2.12.3...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(async (cache) => {
        console.log('[SW] Cacheando assets estáticos');
        await cache.addAll(STATIC_ASSETS);
        // Pré-cacheia o app shell (index.html) JÁ na instalação. Como a instalação
        // ocorre durante uma visita ONLINE, garante que o login offline esteja
        // disponível imediatamente na próxima navegação sem internet.
        await precacheAppShell(cache);
        // P0 (Jun/2026): pré-cacheia TODOS os chunks JS/CSS do build (asset-manifest)
        // para que QUALQUER rota lazy abra offline, mesmo nunca visitada online.
        await precacheBuildAssets(cache);
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

// Pré-cacheia TODOS os chunks JS/CSS do build lendo o asset-manifest.json do Webpack.
// Garante navegabilidade offline em QUALQUER rota lazy, mesmo nunca aberta online.
// - Tolerante a falhas: usa `cache.add` individual + `allSettled` (um 404 não aborta o install).
// - Source maps (.map) são propositalmente EXCLUÍDOS (não são carregados em runtime;
//   inflariam o cache em ~16 MB sem benefício offline).
// - Fetches iniciados pelo próprio SW NÃO passam pelo handler `fetch` → pega rede fresca.
async function precacheBuildAssets(cache) {
  try {
    const res = await fetch('/asset-manifest.json', { cache: 'no-store' });
    if (!res || !res.ok) {
      console.warn('[SW] asset-manifest.json indisponível — pulando pré-cache de chunks');
      return;
    }
    const manifest = await res.json();
    const files = manifest && manifest.files ? Object.values(manifest.files) : [];
    const assets = files.filter((f) => typeof f === 'string' && /\.(js|css)$/.test(f));
    console.log(`[SW] Pré-cacheando ${assets.length} chunks do build (js/css)`);
    const results = await Promise.allSettled(assets.map((url) => cache.add(url)));
    const ok = results.filter((r) => r.status === 'fulfilled').length;
    console.log(`[SW] Pré-cache de chunks concluído: ${ok} ok, ${results.length - ok} falha(s)`);
  } catch (e) {
    console.warn('[SW] Falha ao pré-cachear chunks do build:', e.message);
  }
}

// Busca o index.html fresco e o guarda sob a chave fixa do app shell.
// Tolerante a falha: se estiver offline na instalação, não quebra o SW.
async function precacheAppShell(cache) {
  try {
    const res = await fetch(APP_SHELL_URL, { cache: 'no-store' });
    if (res && res.ok) {
      await cache.put(APP_SHELL_URL, res.clone());
      console.log('[SW] App shell (index.html) pré-cacheado para login offline');
    }
  } catch (e) {
    console.warn('[SW] Não foi possível pré-cachear o app shell na instalação:', e.message);
  }
}

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
  
  // Ignora requisições não-GET
  if (request.method !== 'GET') {
    return;
  }
  
  // Ignora extensões do navegador
  if (url.protocol === 'chrome-extension:' || url.protocol === 'moz-extension:') {
    return;
  }
  
  // NÃO intercepta requisições cross-origin (ex: API em subdomínio diferente)
  // Isso evita interferência com CORS e headers de resposta da API
  if (url.origin !== self.location.origin) {
    return;
  }
  
  // Navegação (HTML / index): rede primeiro. Em sucesso, cacheia o app shell fresco.
  // Se a rede falhar (offline), serve o index.html cacheado para o React iniciar e
  // exibir o login offline; só cai em offline.html se nem o shell estiver em cache.
  if (request.mode === 'navigate' || (request.destination === 'document')) {
    event.respondWith(navigationStrategy(request));
    return;
  }

  // Apenas requisições same-origin são cacheadas/interceptadas
  if (url.pathname.startsWith('/api/')) {
    // Roster dinâmico (frequência/notas/detalhes): SEMPRE da rede, sem cachear,
    // para nunca exibir aluno cancelado/transferido a partir de cache do SW.
    if (NEVER_CACHE_API.test(url.pathname)) {
      event.respondWith(networkOnlyStrategy(request));
    } else {
      event.respondWith(networkFirstStrategy(request));
    }
  } else if (/\.(js|css)$/.test(url.pathname)) {
    // JS e CSS bundles: sempre buscar da rede primeiro (garante código atualizado após deploy)
    event.respondWith(networkFirstStrategy(request));
  } else if (CACHE_PATTERNS.static.test(url.pathname)) {
    // Imagens, fontes, ícones: cache first (raramente mudam)
    event.respondWith(cacheFirstStrategy(request));
  } else {
    event.respondWith(networkFirstStrategy(request));
  }
});

// Estratégia para navegação HTML — network-first com fallback para o app shell.
// Online: busca o index.html fresco e o cacheia (casado com os bundles network-first).
// Offline: serve o index.html cacheado da última visita online → React inicia → login offline.
async function navigationStrategy(request) {
  try {
    const networkResponse = await fetch(request, { cache: 'no-store' });
    // Cacheia o app shell fresco sob chave fixa para uso offline futuro.
    if (networkResponse && networkResponse.ok) {
      try {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(APP_SHELL_URL, networkResponse.clone());
      } catch (e) {
        console.warn('[SW] Não foi possível cachear o app shell:', e.message);
      }
    }
    return networkResponse;
  } catch (error) {
    console.log('[SW] Rede falhou em navegação — servindo app shell cacheado (index.html)');
    const cachedShell = await caches.match(APP_SHELL_URL);
    if (cachedShell) return cachedShell;
    // Fallback final: nenhum shell cacheado ainda (usuário nunca abriu online).
    const offline = await caches.match(OFFLINE_URL);
    if (offline) return offline;
    return new Response('Offline', { status: 503 });
  }
}

async function cacheFirstStrategy(request) {
  const cachedResponse = await caches.match(request);
  
  if (cachedResponse) {
    fetchAndCache(request);
    return cachedResponse;
  }
  
  return fetchAndCache(request);
}

// Network-only: nunca usa cache. Para rosters dinâmicos (frequência/notas/detalhes
// da turma) que precisam refletir cancelamentos/transferências imediatamente.
// Em caso de falha de rede, retorna 503 JSON e o app cai no fallback do Dexie.
async function networkOnlyStrategy(request) {
  try {
    return await fetch(request);
  } catch (error) {
    return new Response(
      JSON.stringify({ error: 'Offline - dados de turma não disponíveis sem conexão' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
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
    
    const operations = pendingItems.map(item => ({
      collection: item.collection,
      operation: item.operation,
      recordId: item.recordId,
      data: item.data,
      timestamp: item.timestamp,
      localId: item.id
    }));
    
    const result = await sendToServer(operations);
    
    if (result.success) {
      for (const item of result.succeeded) {
        await removeSyncItem(item.localId);
      }
      
      for (const item of result.failed) {
        await updateSyncItem(item.localId, {
          status: item.retries >= 3 ? 'failed' : 'pending',
          retries: (item.retries || 0) + 1,
          lastError: item.error
        });
      }
      
      console.log(`[SW] Sincronização concluída: ${result.succeeded.length} sucesso, ${result.failed.length} falhas`);
      
      await notifyClients('SYNC_COMPLETE', {
        processed: operations.length,
        succeeded: result.succeeded.length,
        failed: result.failed.length
      });
      
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

// Extrai o claim 'csrf' do JWT — é exatamente o valor que o middleware CSRF do
// backend valida (header X-CSRF-Token == claim csrf do access token).
function parseJwtCsrf(token) {
  try {
    let p = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    while (p.length % 4) p += '=';
    return JSON.parse(atob(p)).csrf || null;
  } catch (e) {
    console.warn('[SW] Falha ao extrair CSRF do JWT:', e.message);
    return null;
  }
}

// Envia dados para o servidor
async function sendToServer(operations) {
  try {
    const clients = await self.clients.matchAll();
    let apiUrl = '';
    let token = '';
    let csrf = '';
    
    if (clients.length > 0) {
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
      csrf = clientInfo.csrf;
    }
    
    if (!apiUrl || !token) {
      console.log('[SW] Não foi possível obter apiUrl ou token do cliente');
      return { success: false, error: 'Credenciais não disponíveis', succeeded: [], failed: operations };
    }

    // CSRF: usa o token vindo do cliente ou, como fallback, deriva do próprio JWT.
    // Sem ele, /api/sync/push responde 403 e a sync em background falha.
    csrf = csrf || parseJwtCsrf(token);
    if (!csrf) {
      console.error('[SW] CSRF token indisponível — push será rejeitado (403). Abortando sync em background.');
    }

    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    };
    if (csrf) headers['X-CSRF-Token'] = csrf;

    const response = await fetch(`${apiUrl}/api/sync/push`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ operations })
    });
    
    if (!response.ok) {
      // Logging explícito por tipo de falha — NADA de falha silenciosa.
      if (response.status === 401) {
        console.error('[SW] Sync push 401 — token expirado/inválido; sync adiada até novo login.');
      } else if (response.status === 403) {
        console.error('[SW] Sync push 403 — CSRF ausente/inválido.');
      } else {
        console.error(`[SW] Sync push falhou: HTTP ${response.status}`);
      }
      throw new Error(`HTTP ${response.status}`);
    }
    
    const serverResult = await response.json();
    
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
    // Inclui erros de rede (fetch lançou) — também logado explicitamente.
    console.error('[SW] Erro ao enviar para servidor (rede/HTTP):', error.message);
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
        for (const client of clientList) {
          if (client.url.includes('sigesc') && 'focus' in client) {
            return client.focus();
          }
        }
        if (clients.openWindow) {
          return clients.openWindow(event.notification.data || '/');
        }
      })
    );
  }
});

// ============= Mensagens do Cliente =============

self.addEventListener('message', (event) => {
  const { type } = event.data || {};
  
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
      syncAllPendingData();
      break;
      
    case 'GET_AUTH_TOKEN':
    case 'GET_SYNC_INFO':
      break;
  }
});

console.log('[SW] Service Worker v2.12.3 carregado (login offline + pré-cache chunks + sessão à prova de revogação/reset + TTL 30d + diagnóstico visível)');
