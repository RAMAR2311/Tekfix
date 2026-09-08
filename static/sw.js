// Service Worker Tekfix POS PWA
const CACHE_NAME = 'tekfix-pwa-v1';
const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/img/Tekfix.jpg',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  '/static/img/icon-maskable-512.png',
  '/static/img/apple-touch-icon.png',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css'
];

// Instalación: Precacheo de recursos esenciales
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[Tekfix PWA] Precaching recursos estáticos');
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[Tekfix PWA] Advertencia precaching:', err);
      });
    })
  );
  self.skipWaiting();
});

// Activación: Limpieza de cachés antiguas
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[Tekfix PWA] Eliminando caché antigua:', key);
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Estrategia de Fetch:
// - Para navegación (HTML): Network-First con fallback a caché
// - Para estáticos (imágenes, CSS, fuentes): Stale-While-Revalidate
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Ignorar peticiones que no sean GET
  if (req.method !== 'GET') return;

  // Ignorar rutas dinámicas de API o descargas que requieran red viva
  if (url.pathname.startsWith('/api/') || url.pathname.includes('/search') || url.pathname.includes('/descargar')) {
    return;
  }

  // Peticiones de navegación (páginas HTML)
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const copy = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }
          return networkResponse;
        })
        .catch(() => {
          return caches.match(req).then((cachedResponse) => {
            if (cachedResponse) return cachedResponse;
            return caches.match('/');
          });
        })
    );
    return;
  }

  // Recursos estáticos: Stale-While-Revalidate
  event.respondWith(
    caches.match(req).then((cachedResponse) => {
      const fetchPromise = fetch(req)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const copy = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }
          return networkResponse;
        })
        .catch(() => {
          // Si falla la red, el caché ya responderá
        });

      return cachedResponse || fetchPromise;
    })
  );
});
