const CACHE_NAME = 'cleangram-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Pass-through for live API requests and dynamic pages
  event.respondWith(fetch(event.request));
});
