// SIGESC Service Worker - Versão 1.0.0
const CACHE_NAME = 'sigesc-cache-v1';
const OFFLINE_URL = '/offline.html';

// Assets estáticos para cache imediato
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/offline.html',
  '/manifest.json'
];

// Padrões de URL para cache dinâmico
const CACHE_PATTERNS = {
  // Cache de assets estáticos (JS, CSS, imagens)
  static: /\.(js|css|png|jpg|jpeg|svg|ico|woff|woff2)$/,
  // Cache de páginas da aplicação
  pages: /^\/(login|dashboard|admin|professor)/,
  // APIs que podem ser cacheadas (GET only)
  api: /\/api\/(schools|classes|courses|students|mantenedora)/
};

// Instalação do Service Worker
self.addEventListener('install', (event) => {
  console.log('[SW] Instalando Service Worker...');
  
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

// Ativação do Service Worker
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

// Interceptação de requisições
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // Ignorar requisições não-GET (POST, PUT, DELETE vão para a rede)
  if (request.method !== 'GET') {
    return;
  }
  
  // Ignorar requisições de extensões e chrome-extension
  if (url.protocol === 'chrome-extension:' || url.protocol === 'moz-extension:') {
    return;
  }
  
  // Estratégia: Network First para APIs, Cache First para assets
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstStrategy(request));
  } else if (CACHE_PATTERNS.static.test(url.pathname)) {
    event.respondWith(cacheFirstStrategy(request));
  } else {
    event.respondWith(networkFirstStrategy(request));
  }
});

// Estratégia: Cache First (para assets estáticos)
async function cacheFirstStrategy(request) {
  const cachedResponse = await caches.match(request);
  
  if (cachedResponse) {
    // Atualiza o cache em background
    fetchAndCache(request);
    return cachedResponse;
  }
  
  return fetchAndCache(request);
}

// Estratégia: Network First (para APIs e páginas)
async function networkFirstStrategy(request) {
  try {
    const networkResponse = await fetch(request);
    
    // Cacheia resposta bem-sucedida
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
    
    // Se for uma navegação, retorna página offline
    if (request.mode === 'navigate') {
      return caches.match(OFFLINE_URL);
    }
    
    // Retorna erro para requisições que não podem ser atendidas
    return new Response(
      JSON.stringify({ error: 'Offline - dados não disponíveis' }),
      { 
        status: 503,
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
}

// Helper: Busca e cacheia
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

// Background Sync para operações pendentes
self.addEventListener('sync', (event) => {
  console.log('[SW] Background Sync:', event.tag);
  
  if (event.tag === 'sync-grades') {
    event.waitUntil(syncPendingGrades());
  } else if (event.tag === 'sync-attendance') {
    event.waitUntil(syncPendingAttendance());
  }
});

// Sync de notas pendentes
async function syncPendingGrades() {
  console.log('[SW] Sincronizando notas pendentes...');
  // Será implementado na Fase 3
  const clients = await self.clients.matchAll();
  clients.forEach(client => {
    client.postMessage({
      type: 'SYNC_COMPLETE',
      payload: { collection: 'grades' }
    });
  });
}

// Sync de frequência pendente
async function syncPendingAttendance() {
  console.log('[SW] Sincronizando frequência pendente...');
  // Será implementado na Fase 3
  const clients = await self.clients.matchAll();
  clients.forEach(client => {
    client.postMessage({
      type: 'SYNC_COMPLETE',
      payload: { collection: 'attendance' }
    });
  });
}

// Notificações Push (para alertas de sincronização)
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

// Clique em notificação
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  if (event.action === 'open') {
    event.waitUntil(
      clients.openWindow(event.notification.data)
    );
  }
});

// Mensagens do cliente
self.addEventListener('message', (event) => {
  console.log('[SW] Mensagem recebida:', event.data);
  
  if (event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data.type === 'CLEAR_CACHE') {
    caches.delete(CACHE_NAME).then(() => {
      console.log('[SW] Cache limpo');
    });
  }
});

console.log('[SW] Service Worker carregado');
