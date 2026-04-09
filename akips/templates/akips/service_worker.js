{% load static %}
const CACHE_NAME = '{{ cache_name|escapejs }}';
const OFFLINE_URL = '{{ offline_url|escapejs }}';
const PRECACHE_URLS = [
    OFFLINE_URL,
    '{% static 'akips/css/ocnes.css' %}',
    '{% static 'akips/js/ocnes.js' %}',
    '{% static 'akips/img/icon-192.png' %}',
    '{% static 'akips/img/icon-512.png' %}',
    '{% static 'akips/img/apple-touch-icon.png' %}',
    '{% static 'akips/img/favicon.ico' %}',
    '{% static 'admin-lte/plugins/jquery/jquery.min.js' %}',
    '{% static 'admin-lte/plugins/bootstrap/js/bootstrap.bundle.min.js' %}',
    '{% static 'admin-lte/dist/js/adminlte.min.js' %}',
    '{% static 'admin-lte/dist/css/adminlte.min.css' %}'
];

self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.addAll(PRECACHE_URLS);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys.map(function (key) {
                    if (key !== CACHE_NAME) {
                        return caches.delete(key);
                    }
                    return Promise.resolve();
                })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

self.addEventListener('fetch', function (event) {
    if (event.request.method !== 'GET') {
        return;
    }

    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(function () {
                return caches.match(OFFLINE_URL);
            })
        );
        return;
    }

    event.respondWith(
        caches.match(event.request).then(function (cachedResponse) {
            if (cachedResponse) {
                return cachedResponse;
            }

            return fetch(event.request).then(function (networkResponse) {
                if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
                    return networkResponse;
                }

                if (!event.request.url.startsWith(self.location.origin)) {
                    return networkResponse;
                }

                var responseToCache = networkResponse.clone();
                caches.open(CACHE_NAME).then(function (cache) {
                    cache.put(event.request, responseToCache);
                });
                return networkResponse;
            }).catch(function () {
                if (event.request.destination === 'document') {
                    return caches.match(OFFLINE_URL);
                }
                return Promise.reject(new Error('Network request failed'));
            });
        })
    );
});