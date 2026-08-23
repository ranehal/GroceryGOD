// GroceryGOD Service Worker — Cache Accelerator for Instant Loading
const CACHE_NAME = 'god-cache-v20260823a';
const TARGET_ASSET_PATTERNS = [
    /\.parquet(\?|$)/i,
    /_data_part\d+\.js(\?|$)/i,
    /_manifest\.js(\?|$)/i,
    /@duckdb\/duckdb-wasm/i,
    /duckdb.*\.wasm(\?|$)/i,
    /fonts\.(googleapis|gstatic)\.com/i,
    /cdnjs\.cloudflare\.com\/ajax\/libs\/font-awesome/i
];

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME && key.startsWith('god-cache-')) {
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
    const isTargetAsset = TARGET_ASSET_PATTERNS.some((pattern) => pattern.test(url));

    if (isTargetAsset) {
        event.respondWith(
            caches.open(CACHE_NAME).then((cache) => {
                return cache.match(req).then((cachedResponse) => {
                    if (cachedResponse) {
                        return cachedResponse;
                    }
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
