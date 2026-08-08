const SHELL_CACHE = 'lagebericht-shell-v11';
const DATA_CACHE = 'lagebericht-data-v1';
const SHELL = ['./', './index.html', './offline.html', './manifest.webmanifest', './assets/app.css', './assets/freshness-model.js?v=11', './assets/rating-model.js?v=11', './assets/period-model.js?v=11', './assets/cost-model.js?v=11', './assets/app.js?v=11', './assets/icons/icon.svg', './assets/icons/icon-192.png', './assets/icons/icon-512.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL.map((url) => new Request(url, { cache: 'reload' })))));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => ![SHELL_CACHE, DATA_CACHE].includes(key)).map((key) => caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).then((response) => {
      if (response.ok) caches.open(SHELL_CACHE).then((cache) => cache.put('./index.html', response.clone()));
      return response;
    }).catch(() => caches.match('./index.html').then((cached) => cached || caches.match('./offline.html'))));
    return;
  }
  if (url.pathname.includes('/data/')) {
    event.respondWith(fetch(request).then((response) => {
      if (response.ok) caches.open(DATA_CACHE).then((cache) => cache.put(request, response.clone()));
      return response;
    }).catch(() => caches.match(request)));
    return;
  }
  event.respondWith(caches.match(request).then((cached) => cached || fetch(request).catch(() => caches.match('./offline.html'))));
});
