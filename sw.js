// GroceryGOD Service Worker — Cache Accelerator for Instant Loading
const CACHE_NAME = 'god-cache-v20261008_v1';
const STATIC_ASSET_PATTERNS = [
    /@duckdb\/duckdb-wasm/i,
    /duckdb.*\.wasm(\?|$)/i,
    /fonts\.(googleapis|gstatic)\.com/i,
    /cdnjs\.cloudflare\.com\/ajax\/libs\/font-awesome/i
];
const DATA_ASSET_PATTERNS = [
    /\.parquet(\?|$)/i,
    /_data_part\d+\.js(\?|$)/i,
    /_manifest\.js(\?|$)/i,
    /atl_preview\.json(\?|$)/i
];

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME && (key.startsWith('god-cache-') || key.startsWith('god-parquet-cache-'))) {
                        console.log('[SW] Purging old cache version:', key);
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;

    const url = req.url;

    // 1. Dynamic Market Data: Network-First with Cache Fallback (forces network revalidation online to guarantee fresh prices, fallback to cache offline)
    if (DATA_ASSET_PATTERNS.some((pattern) => pattern.test(url))) {
        event.respondWith(
            fetch(new Request(req.url, { method: 'GET', cache: 'no-cache' })).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const clone = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(req, clone)).catch(() => {});
                }
                return networkResponse;
            }).catch(() => {
                return caches.open(CACHE_NAME).then((cache) => cache.match(req));
            })
        );
        return;
    }

    // 2. Static CDN Libraries / Fonts: Cache-First
    if (STATIC_ASSET_PATTERNS.some((pattern) => pattern.test(url))) {
        event.respondWith(
            caches.open(CACHE_NAME).then((cache) => {
                return cache.match(req).then((cachedResponse) => {
                    if (cachedResponse) return cachedResponse;
                    return fetch(req).then((networkResponse) => {
                        if (networkResponse && networkResponse.status === 200) {
                            cache.put(req, networkResponse.clone()).catch(() => {});
                        }
                        return networkResponse;
                    });
                });
            })
        );
    }
});
