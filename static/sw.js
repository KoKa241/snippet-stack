const CACHE = 'snippet-stack-public-v5';
const PUBLIC_ASSETS = ['/static/offline.html', '/static/offline.js', '/static/i18n/ru.json', '/static/app.css', '/static/fonts.css', '/static/theme.js', '/static/app.js', '/static/icons/icon-192.png', '/static/icons/icon-512.png'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PUBLIC_ASSETS))); self.skipWaiting(); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('snippet-stack-public-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (event.request.mode === 'navigate') { event.respondWith(fetch(event.request).catch(() => caches.match('/static/offline.html'))); return; }
  if (url.pathname.startsWith('/static/')) event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
