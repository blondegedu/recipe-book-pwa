const CACHE_NAME = 'recipe-book-v5';
const STATIC_ASSETS = [
  '/manifest.json',
  '/icon-512.png'
];

// Pre-cache static assets on install
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Clean up old caches on activate
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames =>
      Promise.all(
        cacheNames
          .filter(name => name !== CACHE_NAME)
          .map(name => caches.delete(name))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  // Let API requests pass through to network; don't cache them
  if (event.request.url.includes('/api/') || event.request.url.includes('/shared')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Network-first for HTML — always get latest version when online
  if (event.request.mode === 'navigate' || event.request.url.endsWith('.html') || event.request.url.endsWith('/')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          // Cache the fresh copy for offline use
          const toCache = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, toCache));
          return response;
        })
        .catch(() => {
          // Offline — serve cached version
          return caches.match(event.request).then(cached => cached || caches.match('/index.html'));
        })
    );
    return;
  }

  // Cache-first for static assets (images, manifest, etc.)
  event.respondWith(
    caches.match(event.request).then(cached => {
      if (cached) return cached;
      return fetch(event.request).then(response => {
        if (!response || response.status !== 200 || response.type !== 'basic') {
          return response;
        }
        const toCache = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, toCache));
        return response;
      });
    }).catch(() => caches.match('/index.html'))
  );
});
