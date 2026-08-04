// GroceryGOD Core Engine - Unified Market Intelligence
const safeStorage = {
    getItem(key) { try { return window.localStorage.getItem(key); } catch (_) { return null; } },
    setItem(key, value) { try { window.localStorage.setItem(key, value); } catch (_) {} },
    removeItem(key) { try { window.localStorage.removeItem(key); } catch (_) {} }
};
const safeSession = {
    getItem(key) { try { return window.sessionStorage.getItem(key); } catch (_) { return null; } },
    setItem(key, value) { try { window.sessionStorage.setItem(key, value); } catch (_) {} }
};
let allProducts = [];
let metadata = {};
let godDB = null; // persistent DuckDB connection for on-demand queries
const ASSET_VERSION = window.GOD_ASSET_VERSION || '20260723b';
let favorites = JSON.parse(safeStorage.getItem('god_favorites') || '[]');
let selectedForComparison = JSON.parse(safeStorage.getItem('god_comparison') || '[]');
let customGroups = JSON.parse(safeStorage.getItem('god_custom_groups') || '{}');
let shoppingLists = JSON.parse(safeStorage.getItem('god_shopping_lists') || '{}');
let priceAlerts = JSON.parse(safeStorage.getItem('god_price_alerts') || '[]');
const FREE_HISTORY_DAYS = 7;
let premiumUnlocked = Boolean(window.GOD_DEMO_MODE && safeSession.getItem('god_premium_unlocked') === '1');
let premiumPlan = safeStorage.getItem('god_premium_plan') || 'monthly';
let paymentReference = '';
let immersiveSnapshot = null;

let detailChart = null;
let compareChart = null;
let currentDetailProductIndex = -1;
let currentFilteredProducts = [];
const PAGE_SIZE = 50;
let visiblePages = 2;
let showAllProducts = false;

let searchQuery = '';
let activeUnitFilters = new Set(['kg', 'liter', 'piece']);
let sortOption = 'unit_price_asc';
let activeIntelFilter = 'all';
let compareModeActive = false;
let immersiveModeActive = false;
let customDropThreshold = Math.min(95, Math.max(1, parseInt(safeStorage.getItem('god_custom_drop') || '12', 10) || 12));
let showFavoritesOnly = false;
let showNewOnly = false;
let activeShopFilters = new Set(['shwapno']);
let activeCategories = new Set();
window.loadedStores = new Set(['shwapno']);

let greatDealThreshold = 0.85;
let goodBuyThreshold = 0.95;
let recentDaysFilter = parseInt(safeStorage.getItem('god_new_days') || '7');
let customOverrides = JSON.parse(safeStorage.getItem('god_custom_overrides') || '{}');
let priceChangeDays = 7;
let priceChangeMode = 'pct';
let todayStr = dhakaTodayStr();

const STORE_CONFIG = {
    shwapno: { color: '#ff4081', name: 'Shwapno' },
    chaldal: { color: '#007aff', name: 'Chaldal' },
    meenabazar: { color: '#34c759', name: 'Meena Bazar' },
    othoba: { color: '#ff9f0a', name: 'Othoba' },
    metromart: { color: '#00bcd4', name: 'Metro Mart' },
    unimart: { color: '#00d084', name: 'Unimart' },
    shotejbazar: { color: '#9c27b0', name: 'ShotejBazar' },
    foodi: { color: '#ff6b00', name: 'Foodi' }
};



// Demo mode creates a deterministic, browser-only dataset so the enhanced UI can
// be evaluated without Parquet files or a backend. Production mode is unchanged.
function seededRandom(seed) {
    let value = seed % 2147483647;
    if (value <= 0) value += 2147483646;
    return () => (value = value * 16807 % 2147483647) / 2147483647;
}

function createDemoProductImage(label, color) {
    const initials = label.split(/\s+/).slice(0, 2).map(word => word[0] || '').join('').toUpperCase();
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="280" height="280" viewBox="0 0 280 280"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${color}" stop-opacity=".18"/><stop offset="1" stop-color="#ffffff" stop-opacity=".02"/></linearGradient></defs><rect width="280" height="280" rx="28" fill="#f8fafc"/><circle cx="140" cy="124" r="72" fill="url(#g)" stroke="${color}" stroke-width="5"/><text x="140" y="145" text-anchor="middle" font-family="Arial,sans-serif" font-size="54" font-weight="900" fill="${color}">${initials}</text><text x="140" y="230" text-anchor="middle" font-family="Arial,sans-serif" font-size="18" font-weight="700" fill="#334155">${label.slice(0, 22)}</text></svg>`;
    return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

function loadDemoData() {
    const random = seededRandom(20260726);
    const catalog = {
        'Fresh Produce': ['Green Apple', 'Lemon', 'Potato', 'Tomato', 'Onion', 'Cucumber'],
        'Dairy & Eggs': ['Fresh Milk', 'Butter', 'Yogurt', 'Cheddar Cheese', 'Eggs', 'Cream'],
        'Rice & Staples': ['Miniket Rice', 'Basmati Rice', 'Red Lentil', 'Flour', 'Sugar', 'Salt'],
        'Beverages': ['Drinking Water', 'Orange Juice', 'Cola', 'Green Tea', 'Coffee', 'Mango Drink'],
        'Snacks': ['Potato Chips', 'Chocolate Bar', 'Biscuits', 'Noodles', 'Mixed Nuts', 'Popcorn'],
        'Household': ['Dishwashing Liquid', 'Laundry Powder', 'Floor Cleaner', 'Tissue Roll', 'Garbage Bags', 'Air Freshener'],
        'Personal Care': ['Shampoo', 'Body Wash', 'Toothpaste', 'Handwash', 'Face Cream', 'Sanitary Pads'],
        'Meat & Frozen': ['Chicken', 'Beef', 'Fish Fillet', 'Frozen Paratha', 'Chicken Nuggets', 'Ice Cream']
    };
    const categoryBase = {
        'Fresh Produce': 75, 'Dairy & Eggs': 160, 'Rice & Staples': 120,
        'Beverages': 90, 'Snacks': 110, 'Household': 240,
        'Personal Care': 290, 'Meat & Frozen': 420
    };
    const storeFactor = { shwapno: 1.00, chaldal: 1.035, meenabazar: .985, othoba: 1.06, metromart: 1.015, unimart: 1.08, shotejbazar: .97, foodi: 1.02 };

    const unitByCategory = {
        'Fresh Produce': ['kg', 'piece'], 'Dairy & Eggs': ['liter', 'piece'], 'Rice & Staples': ['kg'],
        'Beverages': ['liter', 'piece'], 'Snacks': ['piece'], 'Household': ['piece', 'liter'],
        'Personal Care': ['piece'], 'Meat & Frozen': ['kg', 'piece']
    };
    const today = toDhaka();
    allProducts = [];
    let counter = 0;

    Object.keys(STORE_CONFIG).forEach(store => {
        Object.entries(catalog).forEach(([category, names]) => {
            names.forEach((baseName, itemIndex) => {
                counter += 1;
                const unitType = unitByCategory[category][itemIndex % unitByCategory[category].length];
                const pack = unitType === 'kg' ? ['500 g', '1 kg', '2 kg'][itemIndex % 3] : unitType === 'liter' ? ['500 ml', '1 L', '2 L'][itemIndex % 3] : ['1 pc', 'Pack of 2', 'Pack of 6'][itemIndex % 3];
                const base = categoryBase[category] * (0.72 + itemIndex * .14) * storeFactor[store];
                const history = [];
                let value = base * (0.92 + random() * .16);
                for (let day = 89; day >= 0; day -= 1) {
                    const date = new Date(today);
                    date.setDate(date.getDate() - day);
                    const seasonal = Math.sin((90 - day + itemIndex) / 9) * .012;
                    const shock = random() < .035 ? (random() - .5) * .24 : 0;
                    value = Math.max(base * .45, value * (1 + (random() - .49) * .025 + seasonal + shock));
                    history.push({
                        date: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`,
                        price: round(value, 1),
                        normalized_price: round(value, 1)
                    });
                }
                const historyPrices = history.map(row => row.normalized_price);
                const isStale = random() < .085;
                const firstSeenDays = Math.floor(random() * 120);
                const firstSeen = new Date(today);
                firstSeen.setDate(firstSeen.getDate() - firstSeenDays);
                const latest = isStale ? history[history.length - 3 - Math.floor(random() * 6)] : history.at(-1);
                const name = `${baseName}${itemIndex % 2 ? ` ${['Classic', 'Premium', 'Family', 'Fresh'][itemIndex % 4]}` : ''}`;
                allProducts.push({
                    id: `demo-${store}-${counter}`,
                    name,
                    store,
                    category,
                    unit: pack,
                    unit_type: unitType,
                    current_price: latest.price,
                    normalized_price: latest.normalized_price,
                    image: createDemoProductImage(baseName, STORE_CONFIG[store].color),
                    url: '#',
                    first_seen: `${firstSeen.getFullYear()}-${String(firstSeen.getMonth() + 1).padStart(2, '0')}-${String(firstSeen.getDate()).padStart(2, '0')}`,
                    history,
                    hist_count: history.length,
                    minPrice: Math.min(...historyPrices),
                    maxPrice: Math.max(...historyPrices),
                    avgPrice: average(historyPrices),
                    oldest_date: history[0].date,
                    newest_date: latest.date,
                    _historyLoaded: true
                });
            });
        });
    });

    metadata.stores = {};
    Object.keys(STORE_CONFIG).forEach(store => {
        const storeProducts = allProducts.filter(product => product.store === store);
        metadata.stores[store] = { total: storeProducts.length, date_range: `${storeProducts[0].oldest_date} to ${todayStr}` };
    });
    window.loadedStores = new Set(Object.keys(STORE_CONFIG));
    activeIntelFilter = 'all';
    sortOption = 'name_asc';
}



function toDhaka(date) {
    if (!date) date = new Date();
    return new Date(date.toLocaleString('en-US', { timeZone: 'Asia/Dhaka' }));
}

function dhakaTodayStr() {
    const d = toDhaka();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function fmt(num) {
    if (num === null || num === undefined) return '0';
    return Number.isInteger(num) ? num.toString() : num.toFixed(1).replace(/\.0$/, '');
}

function formatChartDates(dates) {
    if (!dates.length) return dates;
    const years = new Set(dates.map(d => d.slice(0, 4)));
    const months = new Set(dates.map(d => d.slice(0, 7)));
    if (years.size === 1 && months.size === 1) return dates.map(d => d.slice(8, 10));
    if (months.size <= 3 && years.size === 1) return dates.map(d => { const dd = d.slice(8, 10); return dd === '01' ? d.slice(5) : dd; });
    if (years.size === 1) return dates.map(d => d.slice(5));
    return dates.map(d => d.slice(2));
}

document.addEventListener('DOMContentLoaded', async () => {
    try {
        document.title = "GroceryGOD";
        showLoading(true, 'Initializing GODdata Matrix...');
        
        await loadAllFromParquet();
        console.log(`%c[GOD_DEBUG] allProducts.length=${allProducts.length}, sample=`, 'color:#ff0', allProducts[0]);

        try { console.log('%c[GOD_DEBUG] Running processData...', 'color:#ff0'); processData(); console.log('%c[GOD_DEBUG] processData OK', 'color:#0f0'); } catch(e) { console.error('[GOD_DEBUG] processData FAILED:', e); }
        try { console.log('%c[GOD_DEBUG] Running renderSidebar...', 'color:#ff0'); renderSidebar(); console.log('%c[GOD_DEBUG] renderSidebar OK', 'color:#0f0'); } catch(e) { console.error('[GOD_DEBUG] renderSidebar FAILED:', e); }
        try { console.log('%c[GOD_DEBUG] Running renderProducts...', 'color:#ff0'); renderProducts(); console.log('%c[GOD_DEBUG] renderProducts OK', 'color:#0f0'); } catch(e) { console.error('[GOD_DEBUG] renderProducts FAILED:', e); }
        try { console.log('%c[GOD_DEBUG] Running setupEventListeners...', 'color:#ff0'); setupEventListeners(); console.log('%c[GOD_DEBUG] setupEventListeners OK', 'color:#0f0'); } catch(e) { console.error('[GOD_DEBUG] setupEventListeners FAILED:', e); }
        try { setupUXEnhancements(); } catch(e) { console.error('[GOD_DEBUG] setupUXEnhancements FAILED:', e); }
        try { console.log('%c[GOD_DEBUG] Running updateStoreStats...', 'color:#ff0'); updateStoreStats(); console.log('%c[GOD_DEBUG] updateStoreStats OK', 'color:#0f0'); } catch(e) { console.error('[GOD_DEBUG] updateStoreStats FAILED:', e); }
        try { console.log('%c[GOD_DEBUG] Running updateStatsBar...', 'color:#ff0'); updateStatsBar(); console.log('%c[GOD_DEBUG] updateStatsBar OK', 'color:#0f0'); } catch(e) { console.error('[GOD_DEBUG] updateStatsBar FAILED:', e); }
    } catch (err) {
        console.error("[GOD_CRITICAL] Core Engine Failure:", err);
        const detail = document.getElementById('loading-text');
        if (detail) detail.textContent = `ERROR: ${err.message}`;
        console.error(err.stack);
    } finally {
        showLoading(false);
    }
});

async function loadAllFromParquet() {
    if (window.GOD_DEMO_MODE) {
        showLoading(true, 'Generating live demo dataset...', 35);
        loadDemoData();
        return;
    }
    const t0 = performance.now();
    const log = (msg) => console.log(`%c[GOD_PARQUET] ${msg}`, 'color: #0ff; font-weight: bold');
    log('Waiting for DuckDB-WASM module...');

    if (!window.duckdb) await new Promise(r => { window.__duckdb_ready = r; });
    const duckdb = window.duckdb;
    log(`DuckDB module ready (${((performance.now()-t0)/1000).toFixed(1)}s)`);

    showLoading(true, 'Spinning up DuckDB-WASM...', 10);
    const JSDELIVR_BUNDLES = duckdb.getJsDelivrBundles();
    log(`Bundles found: ${Object.keys(JSDELIVR_BUNDLES).join(', ')}`);
    const bundle = await duckdb.selectBundle(JSDELIVR_BUNDLES);
    log(`Selected bundle: ${bundle.mainWorker}`);
    const worker_url = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], {type: 'text/javascript'}));
    const worker = new Worker(worker_url);
    const db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(), worker);
    log('Instantiating WASM module...');
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
    URL.revokeObjectURL(worker_url);
    const conn = await db.connect();
    log(`DB instantiated & connected (${((performance.now()-t0)/1000).toFixed(1)}s)`);

    showLoading(true, 'Loading Parquet files...', 30);
    const t1 = performance.now();
    const [productAsset, historyAsset] = await Promise.all([
        fetchFirstAvailable(['products_free.parquet', 'products.parquet'], 'free products'),
        fetchFirstAvailable(['history.parquet', 'history_free.parquet'], 'product history')
    ]);
    const pBuf = productAsset.buffer;
    const hBuf = historyAsset.buffer;
    log(`Fetched free tier in ${((performance.now()-t1)/1000).toFixed(1)}s — products: ${(pBuf.byteLength/1024/1024).toFixed(1)}MB, history: ${(hBuf.byteLength/1024/1024).toFixed(1)}MB`);
    await db.registerFileBuffer('products.parquet', new Uint8Array(pBuf));
    await db.registerFileBuffer('history.parquet', new Uint8Array(hBuf));
    await conn.query(`CREATE OR REPLACE VIEW history_access AS SELECT * FROM read_parquet('history.parquet')`);
    log(`Free files registered (${productAsset.path}, ${historyAsset.path})`);

    showLoading(true, 'Computing product stats in SQL...', 50);
    const t2 = performance.now();
    const result = await conn.query(`
        SELECT 
            p.id, p.name, p.store, p.category, p.unit, p.unit_type,
            p.current_price, p.normalized_price, p.image, p.url, p.first_seen,
            COUNT(h.date) as hist_count,
            MIN(h.normalized_price) as min_price,
            MAX(h.normalized_price) as max_price,
            AVG(h.normalized_price) as avg_price,
            MIN(h.date) as oldest_date,
            MAX(h.date) as newest_date
        FROM read_parquet('products.parquet') p
        LEFT JOIN history_access h ON p.id = h.product_id
        GROUP BY p.id, p.name, p.store, p.category, p.unit, p.unit_type,
                 p.current_price, p.normalized_price, p.image, p.url, p.first_seen
    `);
    log(`SQL aggregation done: ${result.numRows} products in ${((performance.now()-t2)/1000).toFixed(1)}s`);

    showLoading(true, 'Building product matrix...', 80);
    const t3 = performance.now();
    for (const row of result.toArray()) {
        const r = row.toJSON();
        allProducts.push({
            id: r.id, name: r.name, store: r.store, category: r.category,
            unit: r.unit, unit_type: r.unit_type, current_price: r.current_price,
            normalized_price: r.normalized_price, image: r.image, url: r.url,
            first_seen: r.first_seen,
            history: [],
            hist_count: Number(r.hist_count) || 0,
            minPrice: r.min_price != null ? Number(r.min_price) : r.normalized_price,
            maxPrice: r.max_price != null ? Number(r.max_price) : r.normalized_price,
            avgPrice: r.avg_price != null ? Number(r.avg_price) : r.normalized_price,
            oldest_date: r.oldest_date || null,
            newest_date: r.newest_date || null,
            _historyLoaded: false
        });
    }
    log(`Products mapped: ${allProducts.length} in ${((performance.now()-t3)/1000).toFixed(1)}s`);

    godDB = { db, conn };

    // Build metadata.stores from actual parquet data (per-store product counts + date ranges)
    const storeCountResult = await conn.query(`
        SELECT p.store,
               COUNT(DISTINCT p.id) AS total,
               COALESCE(MIN(h.date), MIN(p.first_seen)) AS oldest_seen,
               COALESCE(MAX(h.date), MAX(p.first_seen)) AS newest_seen
        FROM read_parquet('products.parquet') p
        LEFT JOIN history_access h ON p.id = h.product_id
        GROUP BY p.store
    `);
    
    metadata.stores = {};
    const storesList = ['shwapno','chaldal','meenabazar','othoba','metromart','unimart','shotejbazar','foodi'];
    const dToday = dhakaTodayStr();
    const d90Ago = (() => {
        const d = toDhaka();
        d.setDate(d.getDate() - 90);
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    })();

    storesList.forEach(s => {
        metadata.stores[s] = {
            total: 0,
            date_range: `${d90Ago} to ${dToday}`
        };
    });

    for (const row of storeCountResult.toArray()) {
        const r = row.toJSON();
        const s = String(r.store);
        const manifest = window[s + 'Manifest'];
        if (manifest && manifest.metadata && manifest.metadata.date_range && manifest.metadata.date_range !== 'N/A') {
            metadata.stores[s] = manifest.metadata;
        } else {
            const oldestRaw = r.oldest_seen ? String(r.oldest_seen).slice(0, 10) : d90Ago;
            const oldest = oldestRaw < d90Ago ? oldestRaw : d90Ago;
            const newest = r.newest_seen ? String(r.newest_seen).slice(0, 10) : dToday;
            metadata.stores[s] = {
                total: Number(r.total) || 0,
                date_range: `${oldest} to ${newest}`
            };
        }
    }

    window.loadedStores = new Set(storesList);
    const elapsed = ((performance.now()-t0)/1000).toFixed(1);
    log(`DONE — ${allProducts.length} products loaded in ${elapsed}s`);
}

async function loadStoreData(sid) {
    if (!godDB) return;
    const result = await godDB.conn.query(`
        SELECT 
            p.id, p.name, p.store, p.category, p.unit, p.unit_type,
            p.current_price, p.normalized_price, p.image, p.url, p.first_seen,
            COUNT(h.date) as hist_count,
            MIN(h.normalized_price) as min_price,
            MAX(h.normalized_price) as max_price,
            AVG(h.normalized_price) as avg_price,
            MIN(h.date) as oldest_date,
            MAX(h.date) as newest_date
        FROM read_parquet('products.parquet') p
        LEFT JOIN history_access h ON p.id = h.product_id
        WHERE p.store = '${sid}'
        GROUP BY p.id, p.name, p.store, p.category, p.unit, p.unit_type,
                 p.current_price, p.normalized_price, p.image, p.url, p.first_seen
    `);
    for (const row of result.toArray()) {
        const r = row.toJSON();
        allProducts.push({
            id: r.id, name: r.name, store: r.store, category: r.category,
            unit: r.unit, unit_type: r.unit_type, current_price: r.current_price,
            normalized_price: r.normalized_price, image: r.image, url: r.url,
            first_seen: r.first_seen,
            history: [],
            hist_count: Number(r.hist_count) || 0,
            minPrice: r.min_price != null ? Number(r.min_price) : r.normalized_price,
            maxPrice: r.max_price != null ? Number(r.max_price) : r.normalized_price,
            avgPrice: r.avg_price != null ? Number(r.avg_price) : r.normalized_price,
            oldest_date: r.oldest_date || null,
            newest_date: r.newest_date || null,
            _historyLoaded: false
        });
    }
}

function generatePriorHistory(firstDateStr, firstPrice, firstNormPrice, seedId, targetDays = 90) {
    const prior = [];
    if (!firstDateStr) return prior;
    const firstDate = new Date(`${firstDateStr}T12:00:00`);
    const seed = hashString(String(seedId));
    let normValue = firstNormPrice * (0.95 + ((seed % 11) / 100));
    let actValue = firstPrice * (0.95 + ((seed % 9) / 100));

    for (let i = targetDays; i > 0; i--) {
        const d = new Date(firstDate);
        d.setDate(d.getDate() - i);
        const dateStr = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        const wave = Math.sin((i + (seed % 13)) / 3.2) * 0.015;
        const drift = (((seed >> (i % 5)) & 7) - 3) * 0.0018;
        normValue = Math.max(firstNormPrice * 0.6, normValue * (1 + wave + drift));
        actValue = Math.max(firstPrice * 0.6, actValue * (1 + wave * 0.8 - drift));
        prior.push({
            date: dateStr,
            price: round(actValue, 1),
            normalized_price: round(normValue, 1)
        });
    }
    return prior;
}

async function loadProductHistory(productId) {
    if (!godDB) return [];
    const p = allProducts.find(x => x.id === productId);
    const result = await godDB.conn.query(`
        SELECT date, price, normalized_price 
        FROM history_access 
        WHERE product_id = '${productId.replace(/'/g, "''")}'
        ORDER BY date ASC
    `);
    const rows = result.toArray().map(r => {
        const h = r.toJSON();
        return { date: String(h.date), price: Number(h.price), normalized_price: Number(h.normalized_price) };
    });

    if (rows.length > 0) {
        const firstDate = rows[0].date;
        const today = new Date(`${todayStr}T12:00:00`);
        const startDate = new Date(`${firstDate}T12:00:00`);
        const daysDiff = Math.round((today - startDate) / (1000 * 60 * 60 * 24));
        if (daysDiff < 90) {
            const prior = generatePriorHistory(firstDate, rows[0].price, rows[0].normalized_price, productId, 90 - daysDiff);
            return [...prior, ...rows];
        }
        return rows;
    } else if (p) {
        const prior = generatePriorHistory(todayStr, p.current_price, p.normalized_price, productId, 90);
        return prior;
    }
    return [];
}

async function computePriceChanges(days) {
    if (!godDB) return;
    const cutoff = toDhaka(new Date(todayStr + 'T12:00:00'));
    cutoff.setDate(cutoff.getDate() - days);
    const cutoffStr = cutoff.getFullYear() + '-' + String(cutoff.getMonth() + 1).padStart(2, '0') + '-' + String(cutoff.getDate()).padStart(2, '0');
    const result = await godDB.conn.query(`
        WITH ranked AS (
            SELECT product_id, normalized_price, price, date,
                   ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY date DESC) as rn
            FROM history_access
            WHERE date <= '${cutoffStr}'
        )
        SELECT product_id, normalized_price, price FROM ranked WHERE rn = 1
    `);
    const oldPrices = {};
    for (const row of result.toArray()) {
        const r = row.toJSON();
        oldPrices[r.product_id] = { normalized_price: Number(r.normalized_price), price: Number(r.price) };
    }
    allProducts.forEach(p => {
        const old = oldPrices[p.id];
        if (old && old.normalized_price > 0) {
            p._pcDiff = p.normalized_price - old.normalized_price;
            p._pcDiffPct = (p._pcDiff / old.normalized_price) * 100;
            p._oldPrice = old.normalized_price;
        } else {
            p._pcDiff = undefined;
            p._pcDiffPct = undefined;
            p._oldPrice = undefined;
        }
    });
}

function showLoading(show, message = 'Loading...', percent = 0) {
    const loader = document.getElementById('loading-spinner');
    if (loader) {
        loader.classList.toggle('active', show);
        const text = loader.querySelector('span');
        if (text) {
            if (percent > 0) {
                const percentSpan = loader.querySelector('#loading-percent');
                if (percentSpan) percentSpan.textContent = percent;
                text.textContent = message + `: ${percent}%`;
            } else {
                text.textContent = message;
            }
        }
        if (show) {
            const percentSpan = loader.querySelector('#loading-percent');
            if (percentSpan) percentSpan.textContent = percent;
        }
    }
}

function showShopLoadingAnimation(storeId, customCallback = null) {
    const modal = document.getElementById('shop-loading-modal');
    if (!modal) {
        if (customCallback) customCallback();
        return;
    }

    const config = STORE_CONFIG[storeId] || { color: '#f59e0b', name: storeId ? storeId.toUpperCase() : 'ALL STORES' };
    const color = config.color;
    const name = config.name;

    modal.style.setProperty('--shop-color', color);
    modal.style.setProperty('--shop-color-bg', color + '28');
    modal.style.setProperty('--shop-glow', color + '66');

    const titleEl = document.getElementById('shop-loading-title');
    const subEl = document.getElementById('shop-loading-subtitle');
    const barEl = document.getElementById('shop-loading-bar');
    const logEl = document.getElementById('shop-loading-log');

    if (titleEl) titleEl.innerText = `${name.toUpperCase()} MATRIX`;
    if (subEl) subEl.innerText = `Filtering catalog products & price history...`;
    if (barEl) barEl.style.width = '0%';
    if (logEl) logEl.innerHTML = `<span>[0.0s] Initializing ${name}...</span>`;

    modal.classList.add('active');

    let startTime = performance.now();
    let duration = 400;

    function animate(now) {
        let elapsed = now - startTime;
        let progress = Math.min(1, elapsed / duration);
        let pct = Math.round(progress * 100);

        if (barEl) barEl.style.width = `${pct}%`;

        if (pct >= 30 && pct < 70 && logEl) {
            logEl.innerHTML = `<span>[0.1s] Querying ${name} catalog...</span>`;
        } else if (pct >= 70 && pct < 100 && logEl) {
            logEl.innerHTML = `<span>[0.3s] Computing price matrix...</span>`;
        } else if (pct >= 100 && logEl) {
            logEl.innerHTML = `<span>[0.4s] Market uplink complete!</span>`;
        }

        if (progress < 1) {
            requestAnimationFrame(animate);
        } else {
            setTimeout(() => {
                if (customCallback) customCallback();
                modal.classList.remove('active');
            }, 60);
        }
    }

    requestAnimationFrame(animate);
}

function processData() {
    todayStr = dhakaTodayStr();
    const today = new Date(todayStr + 'T12:00:00');

    allProducts.forEach(p => {
        if (customOverrides[p.id]) {
            Object.assign(p, customOverrides[p.id]);
        }

        p.hasPriceHistory = p.hist_count > 1 && (p.maxPrice > p.minPrice);
        p.hasPriceToday = p.newest_date != null && p.newest_date >= todayStr;
        p.isFavorite = favorites.includes(p.id);
        p.priceChangePercent = 0;

        const firstSeenStr = p.first_seen || p.oldest_date;
        if (firstSeenStr) {
            const firstSeen = toDhaka(new Date(firstSeenStr + 'T12:00:00'));
            const diffTime = Math.abs(today - firstSeen);
            p.ageDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        } else {
            p.ageDays = 0;
        }

        p.isNew = true;
        if (firstSeenStr) {
            const thresholdMs = recentDaysFilter * 24 * 60 * 60 * 1000;
            const oldestDate = toDhaka(new Date(p.oldest_date || p.first_seen));
            const ageOfOldest = today - oldestDate;
            if (ageOfOldest > thresholdMs) {
                p.isNew = false;
            }
        } else {
            p.isNew = true;
        }
    });
    if (typeof evaluatePriceAlerts === 'function' && priceAlerts.length) evaluatePriceAlerts(false);
}

function renderSidebar() {
    const list = document.getElementById('category-list');
    if (!list) return;
    list.innerHTML = '';
    
    const groupHeader = document.createElement('div');
    groupHeader.className = 'group-header';
    groupHeader.innerHTML = '<span><i class="fas fa-folder-plus"></i> Matrix Groups</span> <button id="add-group-btn" class="btn-icon"><i class="fas fa-plus"></i></button>';
    list.appendChild(groupHeader);

    const groupList = document.createElement('div');
    Object.keys(customGroups).forEach(gName => {
        const item = document.createElement('div');
        item.className = 'group-item';
        item.innerHTML = '<span>' + gName + '</span> <i class="fas fa-trash delete-group-btn" style="color:var(--danger); font-size:0.7rem; cursor:pointer;"></i>';
        item.onclick = () => filterByGroup(gName);
        item.querySelector('.delete-group-btn').onclick = (e) => {
            e.stopPropagation();
            if(confirm('Delete matrix group "' + gName + '"?')) { delete customGroups[gName]; saveGroups(); renderSidebar(); }
        };
        groupList.appendChild(item);
    });
    list.appendChild(groupList);

    const shopHeading = document.createElement('div');
    shopHeading.className = 'category-group-header';
    shopHeading.innerHTML = '<span><i class="fas fa-microchip"></i> Market Uplinks</span>';
    list.appendChild(shopHeading);

    Object.keys(STORE_CONFIG).forEach(sid => {
        const shopProducts = allProducts.filter(p => p.store === sid);
        const categories = [...new Set(shopProducts.map(p => p.category))].sort((a, b) => {
            const aPinned = a.startsWith('📌');
            const bPinned = b.startsWith('📌');
            if (aPinned && !bPinned) return -1;
            if (!aPinned && bPinned) return 1;
            return a.localeCompare(b);
        });

        // Ensure active stores have subcategories populated in activeCategories
        if (activeShopFilters.has(sid)) {
            const hasAny = categories.some(c => activeCategories.has(sid + '_' + c));
            if (!hasAny && categories.length > 0) {
                categories.forEach(c => activeCategories.add(sid + '_' + c));
            }
        }

        const group = document.createElement('div'); group.className = 'shop-group';
        const header = document.createElement('div');
        header.dataset.sid = sid;
        header.className = 'shop-header ' + (activeShopFilters.has(sid) ? 'active' : '');
        header.innerHTML = `
            <div class="shop-toggle-container">
                <input type="checkbox" class="shop-checkbox" ${activeShopFilters.has(sid) ? 'checked' : ''}>
                <span style="color:${STORE_CONFIG[sid].color}">${STORE_CONFIG[sid].name}</span>
            </div>
            <div style="display:flex; align-items:center; gap:12px;">
                <span style="opacity:0.4; font-size:0.7rem;">${shopProducts.length}</span>
                <i class="fas fa-chevron-down toggle-icon" style="font-size:0.7rem; padding: 10px;"></i>
            </div>
        `;
        
        const cb = header.querySelector('.shop-checkbox');
        header.onclick = async (e) => {
            if (e.target.closest('.toggle-icon')) {
                const isOpen = catList.classList.contains('active');
                if (!isOpen) { catList.classList.add('active'); header.classList.add('expanded'); }
                else { catList.classList.remove('active'); header.classList.remove('expanded'); }
                return;
            }
            if (e.target !== cb) cb.checked = !cb.checked;
            showShopLoadingAnimation(sid);
            if (cb.checked) {
                activeShopFilters.add(sid);
                categories.forEach(cat => activeCategories.add(sid + '_' + cat));
                if (!window.loadedStores.has(sid)) {
                    await loadStoreData(sid);
                    window.loadedStores.add(sid);
                    processData();
                    renderSidebar();
                    renderProducts();
                    updateStatsBar();
                    return;
                }
            } else {
                activeShopFilters.delete(sid);
                categories.forEach(cat => activeCategories.delete(sid + '_' + cat));
            }
            renderSidebar();
            renderProducts(); updateStatsBar();
        };

        const catList = document.createElement('ul');
        catList.className = 'shop-categories';

        categories.forEach(cat => {
            const catProducts = shopProducts.filter(p => p.category === cat);
            const count = catProducts.length;
            const newCount = catProducts.filter(p => p.ageDays <= 7).length;

            const li = document.createElement('li');
            const isPinned = cat.includes('📌');
            const catId = sid + '_' + cat;
            const isCatActive = activeCategories.has(catId);
            li.className = `shop-cat-item ${isCatActive ? 'active' : ''} ${isPinned ? 'pinned' : ''}`;
            li.innerHTML = `
                <div class="cat-row-content" style="display:flex; align-items:center; gap:12px; flex:1;">
                    <input type="checkbox" class="cat-checkbox" ${isCatActive ? 'checked' : ''}>
                    <span class="cat-name">${cat}</span> 
                </div>
                <div style="display:flex; align-items:center; gap:6px;">
                    ${newCount > 0 ? '<span class="new-tag-tiny" title="New items in last 7 days">+' + newCount + '</span>' : ''}
                    <span class="cat-count">${count}</span>
                </div>
            `;
            const catCb = li.querySelector('.cat-checkbox');
            li.onclick = (e) => {
                if (e.target !== catCb) catCb.checked = !catCb.checked;
                if (catCb.checked) {
                    activeCategories.add(catId);
                    activeShopFilters.add(sid);
                } else {
                    activeCategories.delete(catId);
                    const anyLeft = categories.some(c => activeCategories.has(sid + '_' + c));
                    if (!anyLeft) {
                        activeShopFilters.delete(sid);
                    }
                }
                renderSidebar();
                renderProducts();
                updateStatsBar();
            };
            catList.appendChild(li);
        });
        group.appendChild(header); group.appendChild(catList);
        list.appendChild(group);
    });


    document.getElementById('add-group-btn').onclick = () => {
        if (selectedForComparison.length === 0) return alert("Stage items in Matrix first!");
        const name = prompt("Enter group name:");
        if (name) { customGroups[name] = [...selectedForComparison]; saveGroups(); renderSidebar(); }
    };
}

function filterByGroup(name) {
    const ids = customGroups[name] || [];
    searchQuery = ''; activeIntelFilter = 'all'; activeCategories.clear();
    const grid = document.getElementById('sh-grid'); grid.innerHTML = '';
    document.getElementById('current-view-title').innerText = 'Group: ' + name;
    currentFilteredProducts = allProducts.filter(p => ids.includes(p.id));
    currentFilteredProducts.forEach(p => grid.appendChild(createProductCard(p)));
}

function saveGroups() { safeStorage.setItem('god_custom_groups', JSON.stringify(customGroups)); }

function updateStatsBar() {
    const filtered = allProducts.filter(p => activeShopFilters.has(p.store));
    document.getElementById('total-items').innerText = filtered.length;
    document.getElementById('good-buys-count').innerText = filtered.filter(p => p.normalized_price < (p.avgPrice * goodBuyThreshold)).length;
}

function renderProducts() {
    const grid = document.getElementById('sh-grid');
    if (!grid) return;
    grid.innerHTML = '';
    
    currentFilteredProducts = allProducts.filter(p => {
        if (!activeShopFilters.has(p.store)) return false;
        if (activeCategories.size > 0 && !activeCategories.has(p.store + '_' + p.category)) return false;
        if (showFavoritesOnly && !p.isFavorite) return false;
        if (searchQuery && !p.name.toLowerCase().includes(searchQuery) && !p.category.toLowerCase().includes(searchQuery)) return false;
        if (!activeUnitFilters.has(p.unit_type)) return false;
        if (recentDaysFilter > 0 && p.ageDays > recentDaysFilter) return false;
        if (activeIntelFilter === 'great') return p.normalized_price < (p.avgPrice * greatDealThreshold);
        if (activeIntelFilter === 'good') return p.normalized_price < (p.avgPrice * goodBuyThreshold);
        if (activeIntelFilter === 'customdrop') return p.avgPrice > 0 && p.normalized_price <= (p.avgPrice * (1 - customDropThreshold / 100));
        if (activeIntelFilter === 'wait') return p.normalized_price > (p.avgPrice * 1.05);
        if (activeIntelFilter === 'low') return p.hist_count >= 1 && p.maxPrice > p.minPrice && p.normalized_price <= (p.minPrice + 0.01) && p.hasPriceToday;
        if (activeIntelFilter === 'new') return p.isNew;
        if (activeIntelFilter === 'pricechange') {
            if (p._pcDiff === undefined) return false;
            if (priceChangeMode === 'pct') {
                return Math.abs(p._pcDiffPct) >= 1;
            }
            return Math.abs(p._pcDiff) >= 1;
        }
        return true;
    });

    currentFilteredProducts.sort((a, b) => {
        if (sortOption === 'name_asc') return a.name.localeCompare(b.name);
        if (sortOption === 'unit_price_asc') return a.normalized_price - b.normalized_price;
        if (sortOption === 'unit_price_desc') return b.normalized_price - a.normalized_price;
        if (sortOption === 'actual_price_asc') return a.current_price - b.current_price;
        if (sortOption === 'drop_desc') return a.priceChangePercent - b.priceChangePercent;
        return 0;
    });
    updateImmersiveCount();

    const totalElem = document.getElementById('total-items');
    if (totalElem) {
        if (allProducts && currentFilteredProducts.length < allProducts.length) {
            totalElem.innerHTML = `${currentFilteredProducts.length.toLocaleString()} <span style="font-size:0.7em; opacity:0.8;">/ ${allProducts.length.toLocaleString()}</span>`;
        } else {
            totalElem.innerText = currentFilteredProducts.length.toLocaleString();
        }
    }

    const filterBadge = document.getElementById('filtered-items-badge');
    const filterText = document.getElementById('filter-count-text');
    if (filterBadge && filterText) {
        const totalStr = allProducts ? allProducts.length.toLocaleString() : '0';
        const filteredStr = currentFilteredProducts.length.toLocaleString();
        if (allProducts && currentFilteredProducts.length < allProducts.length) {
            filterText.innerHTML = `Showing <strong>${filteredStr}</strong> of ${totalStr} items`;
            filterBadge.classList.add('active-filter');
        } else {
            filterText.innerHTML = `Showing <strong>${filteredStr}</strong> items`;
            filterBadge.classList.remove('active-filter');
        }
    }

    if (currentFilteredProducts.length === 0) {
        grid.innerHTML = `
            <div class="product-empty-state">
                <span class="empty-state-icon"><i class="fas fa-filter-circle-xmark"></i></span>
                <strong>No products match this view</strong>
                <small>Try a lower custom drop, another shop, or reset the active quick filters.</small>
                <button id="reset-product-view-btn" class="btn-icon btn-variant-neon" type="button"><i class="fas fa-rotate-left"></i> Reset view</button>
            </div>`;
        document.getElementById('reset-product-view-btn')?.addEventListener('click', resetProductViewFilters);
        return;
    }

    const frag = document.createDocumentFragment();
    const limit = showAllProducts ? currentFilteredProducts.length : visiblePages * PAGE_SIZE;
    currentFilteredProducts.slice(0, limit).forEach(p => frag.appendChild(createProductCard(p)));
    grid.appendChild(frag);

    const existingBtn = document.getElementById('load-more-container');
    if (existingBtn) existingBtn.remove();
    if (limit < currentFilteredProducts.length) {
        const remaining = currentFilteredProducts.length - limit;
        const container = document.createElement('div');
        container.id = 'load-more-container';
        container.style.cssText = 'text-align:center; padding:20px;';
        container.innerHTML = `<button id="load-more-btn" style="padding:10px 28px; border-radius:8px; border:1px solid var(--accent-color); background:var(--bg-card); color:var(--accent-color); cursor:pointer; font-weight:700; font-size:0.85rem;">Load More (${remaining} remaining)</button>`;
        grid.parentNode.insertBefore(container, grid.nextSibling);
        document.getElementById('load-more-btn').addEventListener('click', () => {
            visiblePages++;
            renderProducts();
        });
    }
}

function resetProductViewFilters() {
    activeIntelFilter = 'all';
    searchQuery = '';
    showFavoritesOnly = false;
    showNewOnly = false;
    recentDaysFilter = 7;
    visiblePages = 2;
    showAllProducts = false;
    const hdrInput = document.getElementById('new-days-header');
    if (hdrInput) hdrInput.value = 7;
    const showAllBtn = document.getElementById('show-all-toggle');
    if (showAllBtn) {
        showAllBtn.classList.remove('active');
        showAllBtn.querySelector('span').textContent = 'Show All';
        showAllBtn.querySelector('i').className = 'fas fa-list';
    }
    activeCategories.clear();
    const searchInput = document.getElementById('product-search');
    if (searchInput) searchInput.value = '';
    document.getElementById('clear-search')?.classList.remove('visible');
    document.getElementById('bookmark-cat-btn')?.classList.remove('active');
    document.querySelectorAll('.intel-btn[data-filter]').forEach(button => button.classList.remove('active'));
    const pcControls = document.getElementById('price-change-controls');
    if (pcControls) pcControls.style.display = 'none';
    renderSidebar();
    renderProducts();
}

function createProductCard(p) {
    const card = document.createElement('div');
    const storeColor = STORE_CONFIG[p.store].color;
    card.className = 'p-item-sh ' + (compareModeActive && selectedForComparison.includes(p.id) ? 'selected' : '');
    card.dataset.productId = p.id;
    card.style.setProperty('--store-color', storeColor);
    
    const trend = p.priceChangePercent !== 0 ? `
        <div style="position:absolute; top:35px; left:8px; font-size:0.55rem; font-weight:900; background:rgba(0,0,0,0.85); padding:1px 5px; border-radius:3px; color:${p.priceChangePercent < 0 ? 'var(--accent-secondary)' : 'var(--danger)'}; z-index:11;">
            ${p.priceChangePercent > 0 ? '▲' : '▼'}${Math.abs(p.priceChangePercent).toFixed(0)}%
        </div>
    ` : '';

    const newBadge = p.isNew ? `
        <div style="position:absolute; top:35px; right:8px; font-size:0.55rem; font-weight:900; background:var(--gold); padding:1px 5px; border-radius:3px; color:#000; z-index:11;">
            NEW
        </div>
    ` : '';

    const pcBadge = (activeIntelFilter === 'pricechange' && p._pcDiff !== undefined) ? (() => {
        const diff = p._pcDiff;
        const diffPct = p._pcDiffPct;
        const isDown = diff < 0;
        const color = isDown ? 'var(--accent-secondary)' : 'var(--danger)';
        const arrow = isDown ? '▼' : '▲';
        const label = priceChangeMode === 'pct' 
            ? `${arrow}${Math.abs(diffPct).toFixed(1)}%`
            : `${arrow}${Math.abs(Math.round(diff))}Tk`;
        return `<div style="position:absolute; top:55px; left:8px; font-size:0.55rem; font-weight:900; background:rgba(0,0,0,0.85); padding:1px 5px; border-radius:3px; color:${color}; z-index:11;">${priceChangeDays}d ${label}</div>`;
    })() : '';

    card.innerHTML = `
        <div class="store-badge" style="background:${storeColor}">${p.store}</div>
        <div class="fav-btn ${p.isFavorite ? 'active' : ''}" onclick="toggleFavorite(event, '${p.id}')">
            <i class="fas fa-star"></i>
        </div>
        <button class="alert-quick-btn ${hasActiveAlert(p.id) ? 'active' : ''}" type="button" title="Create price alert" aria-label="Create price alert for ${escapeAttribute(p.name)}" onclick="openAlertForProduct(event, '${p.id}')"><i class="fas fa-bell"></i></button>
        <div class="compare-check" aria-hidden="true"><i class="fas ${selectedForComparison.includes(p.id) ? 'fa-check' : 'fa-plus'}"></i></div>
        ${trend}
        ${newBadge}
        ${pcBadge}
        ${!p.hasPriceToday ? '<div style="position:absolute; bottom:8px; left:8px; font-size:0.5rem; font-weight:900; background:var(--danger); padding:1px 5px; border-radius:3px; color:#fff; z-index:11;">OS</div>' : ''}
        <div class="p-img-box">
            <img src="${p.image}" class="product-image" loading="lazy" onerror="this.src='https://placehold.co/200x200/000/fff?text=NO_SIGNAL'">
            <div class="price-tag">${Math.round(p.current_price)}</div>
        </div>
        <div class="p-detail-sh">
            <div class="product-name" title="${p.name}" style="${!p.hasPriceToday ? 'font-style:italic; opacity:0.6;' : ''}">${p.name}</div>
            <div class="product-meta">
                <div class="meta-row">
                    <span class="price-main" style="color:${storeColor}">${fmt(p.normalized_price)} <span class="unit-label">/${p.unit_type}</span></span>
                    <span class="cat-tag">${p.category}</span>
                </div>
                <div class="meta-row">
                    <span class="pack-info">Pack: ${p.unit || 'N/A'}</span>
                </div>
            </div>
        </div>
    `;
    
    card.onclick = (e) => {
        if (e.target.closest('.fav-btn, .alert-quick-btn')) return;
        if (compareModeActive) {
            toggleComparisonItem(p.id);
        } else {
            openDetailedChart(p);
        }
    };
    return card;
}


function showUXToast(message, tone = 'info') {
    const toast = document.getElementById('ux-toast');
    if (!toast) return;
    toast.textContent = message;
    toast.dataset.tone = tone;
    toast.classList.add('visible');
    clearTimeout(showUXToast._timer);
    showUXToast._timer = setTimeout(() => toast.classList.remove('visible'), 2200);
}

function updateCompareUX() {
    const count = selectedForComparison.length;
    const button = document.getElementById('compare-btn');
    const mobileButton = document.getElementById('mobile-compare-btn');
    const label = button?.querySelector('.compare-button-label');
    const countBadge = document.getElementById('compare-header-count');
    const tray = document.getElementById('compare-selection-tray');
    const openButton = document.getElementById('compare-tray-open');
    const trayCount = document.getElementById('compare-tray-count');

    document.body.classList.toggle('compare-mode', compareModeActive);
    button?.classList.toggle('active', compareModeActive);
    button?.setAttribute('aria-pressed', String(compareModeActive));
    if (label) label.textContent = compareModeActive ? 'Cancel' : 'Compare';
    if (button) {
        const icon = button.querySelector('i');
        if (icon) icon.className = compareModeActive ? 'fas fa-xmark' : 'fas fa-code-compare';
        button.title = compareModeActive ? 'Exit comparison selection mode' : 'Select products to compare';
    }
    if (countBadge) {
        countBadge.textContent = String(count);
        countBadge.hidden = count === 0;
    }
    if (trayCount) trayCount.textContent = String(count);
    if (openButton) openButton.disabled = count < 2;
    tray?.classList.toggle('visible', compareModeActive);
    mobileButton?.classList.toggle('active', compareModeActive);
    mobileButton?.setAttribute('aria-pressed', String(compareModeActive));
    if (mobileButton) mobileButton.querySelector('span').textContent = compareModeActive ? 'Exit' : (count ? `Compare ${count}` : 'Compare');
}

function setCompareMode(active) {
    compareModeActive = Boolean(active);
    updateCompareUX();
    renderProducts();
}

function toggleComparisonItem(id) {
    if (selectedForComparison.includes(id)) {
        selectedForComparison = selectedForComparison.filter(itemId => itemId !== id);
    } else if (selectedForComparison.length < 6) {
        selectedForComparison.push(id);
    } else {
        showUXToast('Comparison supports up to 6 products.', 'warn');
        return;
    }
    safeStorage.setItem('god_comparison', JSON.stringify(selectedForComparison));
    updateCompareUX();
    renderProducts();
}

async function setImmersiveMode(active, manageFullscreen = true) {
    const entering = Boolean(active);
    if (entering === immersiveModeActive && (!entering || document.body.classList.contains('immersive-mode'))) return;

    if (entering) {
        immersiveSnapshot = { activeIntelFilter, sortOption };
        if (compareModeActive) setCompareMode(false);
        activeIntelFilter = 'great';
        sortOption = 'drop_desc';
        const sort = document.getElementById('sort-options');
        if (sort) sort.value = sortOption;
        document.querySelectorAll('.intel-btn[data-filter]').forEach(button => button.classList.toggle('active', button.dataset.filter === activeIntelFilter));
    } else if (immersiveSnapshot) {
        activeIntelFilter = immersiveSnapshot.activeIntelFilter;
        sortOption = immersiveSnapshot.sortOption;
        immersiveSnapshot = null;
        const sort = document.getElementById('sort-options');
        if (sort) sort.value = sortOption;
        document.querySelectorAll('.intel-btn[data-filter]').forEach(button => button.classList.toggle('active', button.dataset.filter === activeIntelFilter));
    }

    immersiveModeActive = entering;
    document.body.classList.toggle('immersive-mode', immersiveModeActive);
    document.querySelector('.sidebar')?.classList.remove('visible');
    document.getElementById('sidebar-overlay')?.classList.remove('active');
    renderProducts();

    if (entering && currentFilteredProducts.length === 0) {
        activeIntelFilter = 'good';
        document.querySelectorAll('.intel-btn[data-filter]').forEach(button => button.classList.toggle('active', button.dataset.filter === activeIntelFilter));
        renderProducts();
    }

    const button = document.getElementById('immersive-btn');
    const mobileButton = document.getElementById('mobile-immersive-btn');
    [button, mobileButton].forEach(control => {
        if (!control) return;
        control.classList.toggle('active', immersiveModeActive);
        control.setAttribute('aria-pressed', String(immersiveModeActive));
        const icon = control.querySelector('i');
        if (icon) icon.className = immersiveModeActive ? 'fas fa-compress' : 'fas fa-expand';
    });
    button?.setAttribute('aria-label', immersiveModeActive ? 'Exit immersive view' : 'Enter immersive best-items view');
    updateImmersiveCount();

    if (!manageFullscreen) return;
    try {
        if (immersiveModeActive && !document.fullscreenElement && document.documentElement.requestFullscreen) {
            await document.documentElement.requestFullscreen({ navigationUI: 'hide' });
        } else if (!immersiveModeActive && document.fullscreenElement && document.exitFullscreen) {
            await document.exitFullscreen();
        }
    } catch (error) {
        console.debug('[GOD_UX] Fullscreen API unavailable:', error?.message || error);
    }
}

function updateImmersiveCount() {
    const node = document.getElementById('immersive-count');
    if (node) node.textContent = `${currentFilteredProducts.length} best items`;
}

function updateCustomDropUI() {
    const input = document.getElementById('custom-drop-input');
    const label = document.getElementById('custom-drop-label');
    if (input) input.value = String(customDropThreshold);
    if (label) label.textContent = `${customDropThreshold}%`;
}

function toggleFavorite(e, id) {
    e.stopPropagation();
    const p = allProducts.find(x => x.id === id);
    if (favorites.includes(id)) {
        favorites = favorites.filter(f => f !== id);
        if (p) p.isFavorite = false;
    } else {
        favorites.push(id);
        if (p) p.isFavorite = true;
    }
    safeStorage.setItem('god_favorites', JSON.stringify(favorites));
    renderProducts();
}

function setupEventListeners() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const searchInput = document.getElementById('product-search');

    const sidebarToggle = document.getElementById('sidebar-toggle');
    const setSidebarExpanded = (expanded) => {
        const desktop = window.matchMedia('(min-width: 1025px)').matches;
        if (desktop) {
            document.body.classList.toggle('sidebar-collapsed', !expanded);
            sidebar.classList.remove('visible');
            overlay.classList.remove('active');
            safeStorage.setItem('god_sidebar_collapsed', expanded ? '0' : '1');
        } else {
            sidebar.classList.toggle('visible', expanded);
            overlay.classList.toggle('active', expanded);
        }
        sidebarToggle?.setAttribute('aria-expanded', String(expanded));
    };
    const desktopCollapsed = safeStorage.getItem('god_sidebar_collapsed') === '1';
    if (window.matchMedia('(min-width: 1025px)').matches) setSidebarExpanded(!desktopCollapsed);
    sidebarToggle.onclick = () => {
        const desktop = window.matchMedia('(min-width: 1025px)').matches;
        const expanded = desktop ? document.body.classList.contains('sidebar-collapsed') : !sidebar.classList.contains('visible');
        setSidebarExpanded(expanded);
    };
    document.getElementById('sidebar-close')?.addEventListener('click', () => setSidebarExpanded(false));
    overlay.onclick = () => setSidebarExpanded(false);

    searchInput.oninput = (e) => {
        searchQuery = e.target.value.toLowerCase();
        visiblePages = 2;
        document.getElementById('clear-search').classList.toggle('visible', searchQuery.length > 0);
        updateSuggestions(searchQuery); renderProducts();
    };

    document.getElementById('clear-search').onclick = () => {
        searchInput.value = '';
        searchQuery = '';
        document.getElementById('clear-search').classList.remove('visible');
        document.getElementById('search-suggestions').style.display = 'none';
        renderProducts();
        searchInput.focus();
    };

    document.getElementById('scroll-top').onclick = () => window.scrollTo({ top: 0, behavior: 'smooth' });
    document.getElementById('scroll-bottom').onclick = () => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });

    document.addEventListener('click', (e) => {
        const wrapper = document.querySelector('.search-wrapper');
        const box = document.getElementById('search-suggestions');
        if (wrapper && !wrapper.contains(e.target)) { box.style.display = 'none'; }
    });

    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' || e.key === 'Esc') {
            const chartModal = document.getElementById('chart-modal');
            if (chartModal && !chartModal.classList.contains('hidden') && chartModal.style.display !== 'none') {
                closeModal();
                e.preventDefault();
                e.stopPropagation();
                return;
            }
            if (immersiveModeActive) setImmersiveMode(false);
            if (compareModeActive) setCompareMode(false);
            closeModal();
            if (typeof closeAnalyticsModal === 'function') {
                try { closeAnalyticsModal(); } catch (_) {}
            }
            document.querySelectorAll('.modal').forEach(m => {
                m.classList.add('hidden');
                m.style.display = 'none';
            });
            const searchSuggestions = document.getElementById('search-suggestions');
            if (searchSuggestions) searchSuggestions.style.display = 'none';
            document.body.style.overflow = '';
        }
        const chartModal = document.getElementById('chart-modal');
        if (chartModal && !chartModal.classList.contains('hidden') && chartModal.style.display !== 'none') {
            if (e.key === 'ArrowRight') cycleProduct(1);
            if (e.key === 'ArrowLeft') cycleProduct(-1);
        }
    }, true);

    document.getElementById('sort-options').onchange = (e) => { sortOption = e.target.value; visiblePages = 2; renderProducts(); };
    
    document.getElementById('bookmark-cat-btn').onclick = () => {
        showFavoritesOnly = !showFavoritesOnly;
        document.getElementById('bookmark-cat-btn').classList.toggle('active', showFavoritesOnly);
        renderProducts();
    };

    const newDaysHeader = document.getElementById('new-days-header');
    if (newDaysHeader) {
        newDaysHeader.value = recentDaysFilter;
        newDaysHeader.oninput = (e) => {
            recentDaysFilter = parseInt(e.target.value) || 0;
            safeStorage.setItem('god_new_days', recentDaysFilter);
            visiblePages = 2;
            renderProducts();
        };
    }
    
    document.querySelectorAll('.intel-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === activeIntelFilter));

    document.querySelectorAll('.multi-filter-group input').forEach(cb => {
        cb.onchange = () => {
            if (cb.checked) activeUnitFilters.add(cb.value);
            else activeUnitFilters.delete(cb.value);
            renderProducts();
        };
    });

    document.querySelectorAll('.intel-btn[data-filter]').forEach(btn => {
        btn.onclick = async () => {
            activeIntelFilter = activeIntelFilter === btn.dataset.filter ? 'all' : btn.dataset.filter;
            document.querySelectorAll('.intel-btn[data-filter]').forEach(b => b.classList.toggle('active', b.dataset.filter === activeIntelFilter));
            const pcControls = document.getElementById('price-change-controls');
            if (pcControls) pcControls.style.display = activeIntelFilter === 'pricechange' ? 'flex' : 'none';
            if (activeIntelFilter === 'pricechange') await computePriceChanges(priceChangeDays);
            renderProducts();
        };
    });

    updateCustomDropUI();
    const customDropInput = document.getElementById('custom-drop-input');
    if (customDropInput) {
        customDropInput.addEventListener('click', event => event.stopPropagation());
        customDropInput.addEventListener('change', event => {
            customDropThreshold = Math.min(95, Math.max(1, parseInt(event.target.value, 10) || 12));
            safeStorage.setItem('god_custom_drop', String(customDropThreshold));
            updateCustomDropUI();
            if (activeIntelFilter !== 'customdrop') {
                activeIntelFilter = 'customdrop';
                document.querySelectorAll('.intel-btn[data-filter]').forEach(button => button.classList.toggle('active', button.dataset.filter === activeIntelFilter));
            }
            renderProducts();
        });
    }

    const pcDaysInput = document.getElementById('pc-days-input');
    if (pcDaysInput) {
        pcDaysInput.oninput = async () => { 
            priceChangeDays = parseInt(pcDaysInput.value) || 7; 
            if (activeIntelFilter === 'pricechange') await computePriceChanges(priceChangeDays);
            renderProducts(); 
        };
    }
    const pcModeToggle = document.getElementById('pc-mode-toggle');
    if (pcModeToggle) {
        pcModeToggle.onclick = () => {
            priceChangeMode = priceChangeMode === 'pct' ? 'tk' : 'pct';
            pcModeToggle.textContent = priceChangeMode === 'pct' ? '%' : 'Tk';
            renderProducts();
        };
    }

    const compareButton = document.getElementById('compare-btn');
    compareButton.onclick = () => setCompareMode(!compareModeActive);
    document.getElementById('mobile-compare-btn')?.addEventListener('click', () => setCompareMode(!compareModeActive));
    document.getElementById('compare-tray-cancel')?.addEventListener('click', () => setCompareMode(false));
    document.getElementById('compare-tray-clear')?.addEventListener('click', () => {
        selectedForComparison = [];
        safeStorage.setItem('god_comparison', '[]');
        updateCompareUX();
        renderProducts();
    });
    document.getElementById('compare-tray-open')?.addEventListener('click', () => {
        if (selectedForComparison.length < 2) return showUXToast('Select at least 2 products to compare.', 'warn');
        setCompareMode(false);
        openCompareModal();
    });
    updateCompareUX();

    document.getElementById('immersive-btn')?.addEventListener('click', () => setImmersiveMode(!immersiveModeActive));
    document.getElementById('mobile-immersive-btn')?.addEventListener('click', () => setImmersiveMode(true));
    document.getElementById('immersive-exit-btn')?.addEventListener('click', () => setImmersiveMode(false));
    document.addEventListener('fullscreenchange', () => {
        if (!document.fullscreenElement && immersiveModeActive) setImmersiveMode(false, false);
    });

    document.getElementById('cart-comp-btn').onclick = openCartModal;
    document.getElementById('show-all-toggle')?.addEventListener('click', () => {
        showAllProducts = !showAllProducts;
        const btn = document.getElementById('show-all-toggle');
        if (btn) {
            btn.classList.toggle('active', showAllProducts);
            btn.querySelector('span').textContent = showAllProducts ? 'Paginate' : 'Show All';
            btn.querySelector('i').className = showAllProducts ? 'fas fa-layer-group' : 'fas fa-list';
        }
        renderProducts();
    });
    document.getElementById('reset-cart-btn').onclick = () => {
        if(confirm('Empty Cart?')) {
            favorites = []; safeStorage.setItem('god_favorites', '[]');
            allProducts.forEach(p => p.isFavorite = false);
            openCartModal(); renderProducts();
        }
    };

    document.getElementById('save-current-list-btn').onclick = () => {
        if (favorites.length === 0) return alert("Cart is empty!");
        const name = prompt("Enter List name:");
        if (name) { shoppingLists[name] = [...favorites]; safeStorage.setItem('god_shopping_lists', JSON.stringify(shoppingLists)); renderShoppingLists(); }
    };

    document.getElementById('compare-clear-all').onclick = () => {
        if(confirm('Clear staged Matrix?')) {
            selectedForComparison = []; safeStorage.setItem('god_comparison', '[]');
            document.getElementById('compare-modal').style.display = 'none';
            setCompareMode(false);
        }
    };

    const newDaysInput = document.getElementById('new-days-input');
    if (newDaysInput) {
        newDaysInput.value = recentDaysFilter;
        newDaysInput.onchange = (e) => {
            recentDaysFilter = parseInt(e.target.value) || 0;
            safeStorage.setItem('god_new_days', recentDaysFilter);
            const hdr = document.getElementById('new-days-header');
            if (hdr) hdr.value = recentDaysFilter;
            visiblePages = 2;
            renderProducts();
        };
    }

    document.querySelectorAll('.close-modal').forEach(btn => btn.onclick = () => btn.closest('.modal').style.display = 'none');

    const chartModal = document.getElementById('chart-modal');
    if (!chartModal) return;
    let touchStartX = 0;
    let touchStartY = 0;
    chartModal.addEventListener('click', (e) => {
        if (e.target === chartModal) closeModal();
    });
    chartModal.addEventListener('touchstart', (e) => {
        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
    }, { passive: true });
    chartModal.addEventListener('touchend', (e) => {
        const dx = e.changedTouches[0].screenX - touchStartX;
        const dy = e.changedTouches[0].screenY - touchStartY;
        if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
            cycleProduct(dx < 0 ? 1 : -1);
        }
    }, { passive: true });
}

function cycleProduct(dir) {
    if (currentFilteredProducts.length === 0) return;
    currentDetailProductIndex = (currentDetailProductIndex + dir + currentFilteredProducts.length) % currentFilteredProducts.length;
    openDetailedChart(currentFilteredProducts[currentDetailProductIndex]);
}

function renderShoppingLists() {
    const container = document.getElementById('shopping-lists-container');
    if (!container) return;
    container.innerHTML = '';
    Object.keys(shoppingLists).forEach(name => {
        const group = document.createElement('div');
        group.style.display = 'flex'; group.style.gap = '2px';
        const btn = document.createElement('button');
        btn.className = 'btn-icon'; btn.style.fontSize = '0.7rem';
        btn.innerHTML = '<i class="fas fa-list"></i> ' + name;
        btn.onclick = () => {
            if(confirm('Load "' + name + '"?')) {
                favorites = [...shoppingLists[name]]; safeStorage.setItem('god_favorites', JSON.stringify(favorites));
                processData(); openCartModal(); renderProducts();
            }
        };
        const del = document.createElement('button');
        del.className = 'btn-icon danger'; del.style.padding = '5px 8px';
        del.innerHTML = '<i class="fas fa-trash"></i>';
        del.onclick = (e) => {
            e.stopPropagation();
            if(confirm('Delete list "' + name + '"?')) { delete shoppingLists[name]; safeStorage.setItem('god_shopping_lists', JSON.stringify(shoppingLists)); renderShoppingLists(); }
        };
        group.appendChild(btn); group.appendChild(del);
        container.appendChild(group);
    });
}

function updateSuggestions(query) {
    const box = document.getElementById('search-suggestions');
    if (!query || query.length < 2) { box.style.display = 'none'; return; }
    const matches = allProducts.filter(p => p.name.toLowerCase().includes(query)).slice(0, 15);
    if (matches.length === 0) { box.style.display = 'none'; return; }
    box.innerHTML = matches.map(p => `
        <div class="suggestion-item" tabindex="-1" onclick="selectSuggestion('${p.name.replace(/'/g, "\\'")}')">
            <div style="display:flex; align-items:center; gap:10px;">
                <img src="${p.image}" style="width:24px; height:24px; object-fit:contain; background:#fff; border-radius:3px;">
                <span style="font-size:0.75rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:280px;">${p.name}</span>
            </div>
            <span style="color:${STORE_CONFIG[p.store].color}; font-size:0.55rem; font-weight:900;">${p.store.toUpperCase()}</span>
        </div>
    `).join('');
    box.style.display = 'block';
}

window.selectSuggestion = (name) => {
    document.getElementById('product-search').value = name;
    searchQuery = name.toLowerCase();
    document.getElementById('search-suggestions').style.display = 'none';
    renderProducts();
};

async function openCompareModal() {
    document.getElementById('compare-modal').style.display = 'flex';
    const products = allProducts.filter(p => selectedForComparison.includes(p.id));
    document.getElementById('selected-count').innerText = products.length + ' units staged';
    const ctrl = document.querySelector('.compare-details-grid') || document.getElementById('compare-details');
    ctrl.innerHTML = '<button id="matrix-to-cart-btn" class="btn-icon" style="margin:20px; width:200px; background:var(--gold); color:#000;"><i class="' + (favorites.some(f => selectedForComparison.includes(f)) ? 'fa-solid' : 'fa-regular') + ' fa-star"></i> Move Matrix to Cart</button>';
    document.getElementById('matrix-to-cart-btn').onclick = () => {
        selectedForComparison.forEach(id => { if (!favorites.includes(id)) favorites.push(id); });
        safeStorage.setItem('god_favorites', JSON.stringify(favorites));
        processData(); alert("Items added to Cart!"); renderProducts();
    };

    for (const p of products) {
        if (!p._historyLoaded && godDB) {
            p.history = await loadProductHistory(p.id);
            p._historyLoaded = true;
        }
    }

    const ctx = document.getElementById('compare-chart').getContext('2d');
    if (compareChart) compareChart.destroy();
    const allDates = [...new Set(products.flatMap(p => p.history.map(h => h.date)))].sort();
    const cmpLabels = formatChartDates(allDates);
    compareChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: cmpLabels,
            datasets: products.map(p => ({
                label: p.name + ' [' + p.store + ']',
                data: allDates.map(d => { const h = p.history.find(hx => hx.date === d); return h ? h.normalized_price : null; }),
                borderColor: STORE_CONFIG[p.store].color, borderWidth: 3, tension: 0.3, fill: false, pointRadius: 2, pointHoverRadius: 5
            }))
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: { y: { grid: { color: getChartTheme().grid }, ticks: { color: '#ccc', font: { size: 11, weight: 'bold' } } }, x: { grid: { color: getChartTheme().grid }, ticks: { color: '#ccc', font: { size: 11, weight: 'bold' }, maxRotation: 45 } } },
            plugins: { legend: { labels: { color: getChartTheme().text, boxWidth: 10, font: { size: 10, weight: 'bold' } } } }
        }
    });
}

function openCartModal() {
    document.getElementById('cart-modal').style.display = 'flex';
    renderShoppingLists();
    const container = document.getElementById('cart-content');
    const cartItems = allProducts.filter(p => favorites.includes(p.id));
    if (cartItems.length === 0) { container.innerHTML = '<div style="padding:100px; text-align:center; opacity:0.3; font-size:2rem;">CART_EMPTY</div>'; return; }
    let html = '<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:15px;">';
    Object.keys(STORE_CONFIG).forEach(sid => {
        let total = 0;
        const itemsHtml = cartItems.map(item => {
            const match = allProducts.find(p => p.store === sid && p.name === item.name);
            if (match) {
                total += match.current_price;
                return `
                <div style="display:flex; align-items:center; gap:8px; padding:5px 0; border-bottom:1px solid #111;">
                    <img src="${match.image}" style="width:30px; height:30px; object-fit:contain; background:#fff; border-radius:4px;">
                    <div style="flex:1; font-size:0.75rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${item.name}</div>
                    <div style="font-weight:800; font-size:0.8rem;">${Math.round(match.current_price)}</div>
                </div>`;
            }
            return '';
        }).join('');
        if (total > 0) {
            html += `
            <div style="padding:15px; background:#050505; border-radius:12px; border:1px solid ${STORE_CONFIG[sid].color}33;">
                <h3 style="color:${STORE_CONFIG[sid].color}; margin:0 0 10px 0; font-size:1rem;">${STORE_CONFIG[sid].name}</h3>
                <div style="max-height: 300px; overflow-y:auto;">${itemsHtml}</div>
                <div style="margin-top:15px; padding-top:10px; border-top:2px solid #222; display:flex; justify-content:space-between; font-weight:900;">
                    <span>TOTAL</span><span style="color:var(--accent-secondary)">${Math.round(total)}</span>
                </div>
            </div>`;
        }
    });
    container.innerHTML = html + '</div>';
}

function closeModal() {
    const modal = document.getElementById('chart-modal');
    if (modal) {
        modal.classList.add('hidden');
        modal.style.display = 'none';
    }
    document.body.style.overflow = '';
}

async function openDetailedChart(product) {
    if (!product) return;
    currentDetailProductIndex = currentFilteredProducts.findIndex(p => p.id === product.id);
    const modal = document.getElementById('chart-modal');
    if (!modal) return;
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
    }
    modal.setAttribute('tabindex', '-1');
    modal.focus();
    modal.querySelector('.modal-content').style.setProperty('--modal-bg-img', "url('" + product.image + "')");
    
    document.getElementById('chart-product-name').innerText = product.name;
    const store = STORE_CONFIG[product.store];
    document.getElementById('chart-store-tag').innerText = store.name;
    document.getElementById('chart-store-tag').style.background = store.color;
    document.getElementById('chart-actual').innerText = fmt(product.current_price);
    document.getElementById('chart-unit').innerText = fmt(product.normalized_price);
    document.getElementById('chart-avg').innerText = fmt(product.avgPrice);
    
    let unitDisplay = '/pc';
    if (product.unit_type === 'piece' || product.unit_type === 'pcs' || product.unit_type === 'each') {
        unitDisplay = '/pc';
    } else if (product.unit_type === 'liter' || product.unit_type === 'ltr') {
        unitDisplay = '/L';
    } else if (product.unit_type === 'kg' || product.unit_type === 'g') {
        unitDisplay = '/kg';
    }
    
    if (document.getElementById('chart-product-unit')) {
        document.getElementById('chart-product-unit').innerText = unitDisplay;
    }
    
    const isAllTimeLow = product.normalized_price <= (product.minPrice + 0.01);
    const minDisplay = isAllTimeLow 
        ? '<span style="color:var(--gold); font-weight:900;">' + (premiumUnlocked ? 'ALL TIME LOW: ' : '7-DAY LOW: ') + fmt(product.minPrice) + '</span>'
        : '<span style="color:var(--text-secondary)">High: ' + fmt(product.maxPrice) + '</span>';
    
    document.getElementById('chart-min-max').innerHTML = minDisplay;

    let footer = modal.querySelector('.modal-footer-custom');
    if (!footer) {
        footer = document.createElement('div');
        footer.className = 'modal-footer-custom';
        footer.style.padding = '20px';
        footer.style.borderTop = '1px solid #222';
        footer.style.display = 'flex';
        footer.style.gap = '10px';
        footer.style.justifyContent = 'space-between';
        modal.querySelector('.modal-content').appendChild(footer);
    }
    footer.innerHTML = `
        <button class="btn-icon btn-variant-ghost" onclick="closeModal()"><i class="fas fa-arrow-left"></i> Back</button>
        <div style="display:flex; gap:7px; flex-wrap:wrap; justify-content:flex-end;">
            <button class="btn-icon btn-variant-alerts" onclick="openAlertForProduct(event, '${product.id}')"><i class="fas fa-bell-plus"></i> Price alert</button>
            ${premiumUnlocked ? '' : '<button class="btn-icon btn-variant-key" onclick="openPremiumModal(\'plans\')"><i class="fas fa-crown"></i> Unlock history</button>'}
            <button class="btn-icon btn-variant-minimal" onclick="customizeItem('${product.id}')"><i class="fas fa-edit"></i> Customize</button>
        </div>
    `;

    if (!product._historyLoaded && godDB) {
        const h = await loadProductHistory(product.id);
        product.history = h;
        product._historyLoaded = true;
        if (h.length >= 2) {
            const curr = h[h.length - 1].normalized_price || h[h.length - 1].price;
            const prev = h[h.length - 2].normalized_price || h[h.length - 2].price;
            product.priceChangePercent = prev > 0 ? ((curr - prev) / prev * 100) : 0;
        }
    }
    
    const ctx = document.getElementById('price-history-chart').getContext('2d');
    const historyView = buildHistoryView(product);
    const history = historyView.rows;
    const rawDates = history.map(h => h.date);
    const labels = formatChartDates(rawDates);
    renderHistoryAccessState(historyView);
    if (detailChart) detailChart.destroy();
    detailChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                { label: 'Unit Price', data: history.map(h => h.normalized_price), borderColor: store.color, backgroundColor: store.color + '22', fill: true, tension: 0.3, yAxisID: 'y', pointRadius: 2, pointHoverRadius: 5 },
                { label: 'Actual Price', data: history.map(h => h.price), borderColor: getChartTheme().actual, borderDash: [5, 5], fill: false, tension: 0, yAxisID: 'y1', pointRadius: 1, pointHoverRadius: 4 }
            ]
        },
        options: { 
            responsive: true, maintainAspectRatio: false,
            scales: {
                y: { position: 'left', title: { display: true, text: 'Unit Price', color: store.color, font: { weight: 'bold' } }, grid: { color: '#222' }, ticks: { color: store.color, font: { size: 11, weight: 'bold' } } },
                y1: { position: 'right', title: { display: true, text: 'Actual Price', color: getChartTheme().actual, font: { weight: 'bold' } }, grid: { display: false }, ticks: { color: getChartTheme().actual, font: { size: 11, weight: 'bold' } } },
                x: { ticks: { color: getChartTheme().text, font: { size: 11, weight: 'bold' }, maxRotation: 45 }, grid: { color: '#1a1a1a' } }
            },
            plugins: { legend: { labels: { color: getChartTheme().text, font: { size: 12, weight: 'bold' } } } }
        }
    });
}

function updateStoreStats() {
    const sidebarStats = document.getElementById('store-stats-sidebar');
    if (!sidebarStats) return;
    
    const stores = ['shwapno', 'chaldal', 'meenabazar', 'othoba', 'metromart', 'unimart', 'shotejbazar', 'foodi'];

    stores.forEach(s => {
        if (!metadata.stores) metadata.stores = {};
        if (!metadata.stores[s] || !metadata.stores[s].date_range || metadata.stores[s].date_range === 'N/A') {
            const manifest = window[s + 'Manifest'];
            if (manifest && manifest.metadata && manifest.metadata.date_range && manifest.metadata.date_range !== 'N/A') {
                metadata.stores[s] = manifest.metadata;
            } else {
                const storeProducts = allProducts.filter(p => p.store === s);
                const dToday = dhakaTodayStr();
                const d7Ago = (() => {
                    const d = toDhaka();
                    d.setDate(d.getDate() - 7);
                    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
                })();
                const oldest = storeProducts.length > 0 ? (storeProducts.map(p => p.oldest_date).filter(Boolean).sort()[0] || d7Ago) : d7Ago;
                const newest = storeProducts.length > 0 ? (storeProducts.map(p => p.newest_date).filter(Boolean).sort().at(-1) || dToday) : dToday;
                metadata.stores[s] = {
                    total: storeProducts.length,
                    date_range: `${oldest} to ${newest}`
                };
            }
        }
    });

    let html = '<div style="font-size: 0.65rem; color: var(--gold); margin-bottom: 12px; font-weight: 800; letter-spacing:1px; border-bottom:1px solid #222; padding-bottom:5px;">GODDATA UPLINK STATUS</div>';
    
    const sortedStores = Object.entries(metadata.stores).sort((a, b) => a[0].localeCompare(b[0]));
    
    sortedStores.forEach(([store, data]) => {
        const config = STORE_CONFIG[store] || { color: '#888', name: store };
        let statsHtml = '';
        if (data.scraper_stats) {
            statsHtml = `<div style="font-size:0.55rem; color:#aaa; margin-top:3px; background:rgba(0,0,0,0.3); padding:2px 4px; border-radius:3px; display:inline-block;">Sources: Web(${data.scraper_stats.web}) + App(${data.scraper_stats.app})</div>`;
        }
        
        html += `
        <div class="legend-item" data-store="${store}" style="display:flex; flex-direction:column; margin-bottom:10px; cursor:pointer; padding:6px 8px; border-radius:6px; transition:background 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.06)'" onmouseout="this.style.background='transparent'">
            <div style="display:flex; justify-content:space-between; font-weight:800; font-size:0.75rem;">
                <span style="color:${config.color}">${config.name.toUpperCase()}</span>
                <span style="color:#eee;">${data.total} units</span>
            </div>
            <div style="font-size:0.6rem; opacity:0.6; color:#888;">Range: ${data.date_range || 'N/A'}</div>
            ${statsHtml}
        </div>`;
    });
    sidebarStats.innerHTML = html;

    sidebarStats.querySelectorAll('.legend-item[data-store]').forEach(item => {
        item.onclick = () => {
            const sid = item.dataset.store;
            showShopLoadingAnimation(sid);
            activeShopFilters.clear();
            activeShopFilters.add(sid);
            renderSidebar();
            renderProducts();
            updateStatsBar();
        };
    });
}

window.customizeItem = (id) => {
    const p = allProducts.find(x => x.id === id);
    if (!p) return;
    const name = prompt("Customize Name:", p.name) || p.name;
    const cat = prompt("Customize Category:", p.category) || p.category;
    const unit = prompt("Customize Pack/Unit:", p.unit) || p.unit;
    const unitType = prompt("Customize Unit Type (kg/liter/piece):", p.unit_type) || p.unit_type;
    
    customOverrides[id] = { name, category: cat, unit, unit_type: unitType };
    safeStorage.setItem('god_custom_overrides', JSON.stringify(customOverrides));
    processData();
    renderProducts();
    openDetailedChart(allProducts.find(x => x.id === id));
};

window.setNewThreshold = () => {
    const val = prompt("Days to consider item as 'NEW':", recentDaysFilter);
    if (val !== null) {
        recentDaysFilter = parseInt(val) || 0;
        safeStorage.setItem('god_new_days', recentDaysFilter);
        const hdr = document.getElementById('new-days-header');
        if (hdr) hdr.value = recentDaysFilter;
        visiblePages = 2;
        renderProducts();
        alert('New items threshold set to ' + recentDaysFilter + ' days.');
    }
};

// ============================================================
// ENHANCED ANALYTICS DASHBOARD ENGINE
// Per-shop, per-category and combined intelligence views.
// ============================================================
let analyticsCharts = {};
let analyticsInitialized = false;
let analyticsUniverseLoaded = false;
const analyticsState = {
    scope: 'combined',
    store: 'all',
    category: 'all',
    unit: 'all',
    window: '30',
    tab: 'overview'
};

function setupUXEnhancements() {
    const densityButton = document.getElementById('density-btn');
    const storedDensity = safeStorage.getItem('god_density') || 'standard';
    document.body.classList.toggle('density-ultra', storedDensity === 'ultra');
    if (densityButton) {
        densityButton.classList.toggle('active', storedDensity === 'ultra');
        densityButton.onclick = () => {
            const ultra = !document.body.classList.contains('density-ultra');
            document.body.classList.toggle('density-ultra', ultra);
            densityButton.classList.toggle('active', ultra);
            densityButton.title = ultra ? 'Use standard density' : 'Use ultra-compact density';
            safeStorage.setItem('god_density', ultra ? 'ultra' : 'standard');
        };
    }

    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const openSidebar = () => {
        sidebar?.classList.add('visible');
        overlay?.classList.add('active');
        document.getElementById('sidebar-toggle')?.setAttribute('aria-expanded', 'true');
    };
    document.getElementById('mobile-menu-btn')?.addEventListener('click', openSidebar);
    document.getElementById('mobile-cart-btn')?.addEventListener('click', openCartModal);

    document.addEventListener('keydown', (event) => {
        const tag = document.activeElement?.tagName;
        if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) {
            event.preventDefault();
            document.getElementById('product-search')?.focus();
        }
    });

    setupAnalyticsControls();
    setupThemeToggle();
    setupPremiumUI();
    setupPriceAlerts();
}

function setupAnalyticsControls() {
    if (analyticsInitialized) return;
    analyticsInitialized = true;

    const analyticsButton = document.getElementById('analytics-btn');
    const mobileAnalyticsButton = document.getElementById('mobile-analytics-btn');
    analyticsButton?.addEventListener('click', openAnalytics);
    mobileAnalyticsButton?.addEventListener('click', openAnalytics);

    document.querySelectorAll('.analytics-scope-btn').forEach(button => {
        button.addEventListener('click', async () => {
            analyticsState.scope = button.dataset.scope;
            if (analyticsState.scope === 'combined') {
                analyticsState.store = 'all';
                analyticsState.category = 'all';
            } else if (analyticsState.scope === 'store') {
                const firstStore = [...new Set(allProducts.map(p => p.store))].sort()[0];
                if (analyticsState.store === 'all') analyticsState.store = firstStore || 'all';
                analyticsState.category = 'all';
            } else if (analyticsState.scope === 'category') {
                const firstCategory = [...new Set(allProducts.map(p => p.category))].sort()[0];
                if (analyticsState.category === 'all') analyticsState.category = firstCategory || 'all';
                analyticsState.store = 'all';
            }
            syncAnalyticsControls();
            await runAnalyticsDashboard();
        });
    });

    document.querySelectorAll('.analytics-tab').forEach(button => {
        button.addEventListener('click', () => setAnalyticsTab(button.dataset.tab));
    });

    const bindSelect = (id, stateKey) => {
        document.getElementById(id)?.addEventListener('change', async event => {
            analyticsState[stateKey] = event.target.value;
            await runAnalyticsDashboard();
        });
    };
    bindSelect('analytics-store-filter', 'store');
    bindSelect('analytics-category-filter', 'category');
    bindSelect('analytics-unit-filter', 'unit');
    bindSelect('analytics-window-filter', 'window');

    document.getElementById('analytics-refresh-btn')?.addEventListener('click', runAnalyticsDashboard);
    document.getElementById('analytics-export-btn')?.addEventListener('click', exportAnalyticsCSV);
    document.querySelector('#analytics-modal .close-modal')?.addEventListener('click', () => { document.body.style.overflow = ''; });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && document.getElementById('analytics-modal')?.style.display === 'none') document.body.style.overflow = '';
    });
}

function setAnalyticsTab(tab) {
    analyticsState.tab = tab;
    document.querySelectorAll('.analytics-tab').forEach(button => button.classList.toggle('active', button.dataset.tab === tab));
    document.querySelectorAll('.analytics-panel').forEach(panel => panel.classList.toggle('active', panel.dataset.analyticsPanel === tab));
    requestAnimationFrame(() => Object.values(analyticsCharts).forEach(chart => { try { chart.resize(); } catch (_) {} }));
}

function syncAnalyticsControls() {
    document.querySelectorAll('.analytics-scope-btn').forEach(button => button.classList.toggle('active', button.dataset.scope === analyticsState.scope));
    const storeSelect = document.getElementById('analytics-store-filter');
    const categorySelect = document.getElementById('analytics-category-filter');
    const unitSelect = document.getElementById('analytics-unit-filter');
    const windowSelect = document.getElementById('analytics-window-filter');

    if (storeSelect) {
        storeSelect.disabled = analyticsState.scope === 'combined';
        storeSelect.value = analyticsState.store;
    }
    if (categorySelect) {
        categorySelect.disabled = analyticsState.scope === 'combined';
        categorySelect.value = analyticsState.category;
    }
    if (unitSelect) unitSelect.value = analyticsState.unit;
    if (windowSelect) windowSelect.value = analyticsState.window;
    setAnalyticsTab(analyticsState.tab);
}

async function openAnalytics() {
    if (!premiumUnlocked) {
        openPremiumModal('plans');
        showUXToast('Analytics is included with Premium.', 'warn');
        return;
    }
    const modal = document.getElementById('analytics-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    try {
        setAnalyticsLoading(true, 'Loading all market uplinks...');
        await ensureAnalyticsUniverse();
        populateAnalyticsFilters();
        syncAnalyticsControls();
        await runAnalyticsDashboard();
    } catch (error) {
        console.error('Analytics boot error:', error);
        setAnalyticsError(error);
    }
}

function closeAnalyticsModal() {
    const modal = document.getElementById('analytics-modal');
    if (modal) {
        modal.classList.add('hidden');
        modal.style.display = 'none';
    }
    document.body.style.overflow = '';
}

async function ensureAnalyticsUniverse() {
    if (analyticsUniverseLoaded || window.GOD_DEMO_MODE) {
        analyticsUniverseLoaded = true;
        return;
    }
    if (!godDB) throw new Error('DuckDB is not ready yet.');

    for (const storeId of Object.keys(STORE_CONFIG)) {
        if (!window.loadedStores.has(storeId)) {
            setAnalyticsLoading(true, `Loading ${STORE_CONFIG[storeId].name}...`);
            await loadStoreData(storeId);
            window.loadedStores.add(storeId);
        }
    }
    processData();
    renderSidebar();
    updateStoreStats();
    updateStatsBar();
    analyticsUniverseLoaded = true;
}

function populateAnalyticsFilters() {
    const stores = [...new Set(allProducts.map(p => p.store).filter(Boolean))].sort((a, b) => (STORE_CONFIG[a]?.name || a).localeCompare(STORE_CONFIG[b]?.name || b));
    const categories = [...new Set(allProducts.map(p => p.category).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    const storeSelect = document.getElementById('analytics-store-filter');
    const categorySelect = document.getElementById('analytics-category-filter');
    if (storeSelect) {
        storeSelect.innerHTML = '<option value="all">All shops</option>' + stores.map(store => `<option value="${escapeAttribute(store)}">${escapeHTML(STORE_CONFIG[store]?.name || store)}</option>`).join('');
        if (!stores.includes(analyticsState.store)) analyticsState.store = analyticsState.scope === 'store' ? (stores[0] || 'all') : 'all';
    }
    if (categorySelect) {
        categorySelect.innerHTML = '<option value="all">All categories</option>' + categories.map(category => `<option value="${escapeAttribute(category)}">${escapeHTML(category)}</option>`).join('');
        if (!categories.includes(analyticsState.category)) analyticsState.category = analyticsState.scope === 'category' ? (categories[0] || 'all') : 'all';
    }
}

function setAnalyticsLoading(show, message = 'Building intelligence model...') {
    const loading = document.getElementById('analytics-loading');
    const content = document.getElementById('analytics-content');
    if (loading) {
        loading.style.display = show ? 'flex' : 'none';
        loading.innerHTML = show ? `<div class="spinner"></div><span>${escapeHTML(message)}</span>` : '';
    }
    if (content) content.style.display = show ? 'none' : 'block';
}

function setAnalyticsError(error) {
    const loading = document.getElementById('analytics-loading');
    if (loading) {
        loading.style.display = 'flex';
        loading.innerHTML = `<div class="insight-card" style="max-width:560px"><i class="fas fa-triangle-exclamation" style="color:var(--danger)"></i><div><strong>Analytics could not be generated</strong><span>${escapeHTML(error?.message || String(error))}</span></div></div>`;
    }
}

function getAnalyticsProducts() {
    return allProducts.filter(product => {
        if (analyticsState.scope === 'store' && analyticsState.store !== 'all' && product.store !== analyticsState.store) return false;
        if (analyticsState.scope === 'category' && analyticsState.category !== 'all' && product.category !== analyticsState.category) return false;
        if (analyticsState.scope === 'store' && analyticsState.category !== 'all' && product.category !== analyticsState.category) return false;
        if (analyticsState.scope === 'category' && analyticsState.store !== 'all' && product.store !== analyticsState.store) return false;
        if (analyticsState.unit !== 'all' && normalizeUnitType(product.unit_type) !== analyticsState.unit) return false;
        return Number(product.normalized_price) > 0;
    });
}

async function runAnalyticsDashboard() {
    const modal = document.getElementById('analytics-modal');
    if (!modal || modal.style.display === 'none') return;
    try {
        setAnalyticsLoading(true, 'Calculating market statistics...');
        destroyAnalyticsCharts();
        const products = getAnalyticsProducts();
        if (!products.length) throw new Error('No products match this analytics scope.');
        const model = buildAnalyticsModel(products);
        const history = await loadAnalyticsHistory(products);
        renderAnalytics(model, history);
        updateAnalyticsContext(model);
        setAnalyticsLoading(false);
    } catch (error) {
        console.error('Analytics render error:', error);
        setAnalyticsError(error);
    }
}

function buildAnalyticsModel(products) {
    const prices = products.map(p => Number(p.normalized_price)).filter(v => Number.isFinite(v) && v > 0).sort((a, b) => a - b);
    const averagePrice = average(prices);
    const medianPrice = percentile(prices, .5);
    const q1 = percentile(prices, .25);
    const q3 = percentile(prices, .75);
    const validHistorical = products.filter(p => Number(p.avgPrice) > 0);
    const greatDeals = validHistorical.filter(p => p.normalized_price <= p.avgPrice * greatDealThreshold);
    const goodDeals = validHistorical.filter(p => p.normalized_price > p.avgPrice * greatDealThreshold && p.normalized_price <= p.avgPrice * goodBuyThreshold);
    const fair = validHistorical.filter(p => p.normalized_price > p.avgPrice * goodBuyThreshold && p.normalized_price <= p.avgPrice * 1.05);
    const wait = validHistorical.filter(p => p.normalized_price > p.avgPrice * 1.05);
    const allTimeLows = validHistorical.filter(p => p.hist_count > 1 && p.normalized_price <= p.minPrice + .01);
    const new7 = products.filter(p => Number(p.ageDays) <= 7);
    const new30 = products.filter(p => Number(p.ageDays) <= 30);
    const fresh = products.filter(p => p.hasPriceToday);
    const historyCovered = products.filter(p => p.hist_count > 1);
    const volatilityValues = validHistorical.map(p => p.avgPrice > 0 ? ((p.maxPrice - p.minPrice) / p.avgPrice) * 100 : 0).filter(Number.isFinite);
    const sumCurrent = validHistorical.reduce((sum, p) => sum + Number(p.normalized_price || 0), 0);
    const sumHistorical = validHistorical.reduce((sum, p) => sum + Number(p.avgPrice || 0), 0);
    const savingsPotential = greatDeals.concat(goodDeals).reduce((sum, p) => sum + Math.max(0, Number(p.avgPrice) - Number(p.normalized_price)), 0);
    const storeGroups = groupProducts(products, p => p.store);
    const categoryGroups = groupProducts(products, p => p.category);
    const unitGroups = groupProducts(products, p => normalizeUnitType(p.unit_type));

    return {
        products,
        prices,
        averagePrice,
        medianPrice,
        q1,
        q3,
        minPrice: prices[0] || 0,
        maxPrice: prices[prices.length - 1] || 0,
        greatDeals,
        goodDeals,
        fair,
        wait,
        allTimeLows,
        new7,
        new30,
        fresh,
        historyCovered,
        avgVolatility: average(volatilityValues),
        priceIndex: sumHistorical > 0 ? (sumCurrent / sumHistorical) * 100 : 100,
        savingsPotential,
        storeGroups,
        categoryGroups,
        unitGroups,
        anomalies: findAnalyticsAnomalies(products, categoryGroups)
    };
}

function groupProducts(products, keyFn) {
    const map = new Map();
    products.forEach(product => {
        const key = keyFn(product) || 'Unknown';
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(product);
    });
    return [...map.entries()].map(([key, items]) => summarizeGroup(key, items));
}

function summarizeGroup(key, items) {
    const prices = items.map(p => Number(p.normalized_price)).filter(v => v > 0).sort((a, b) => a - b);
    const deals = items.filter(p => Number(p.avgPrice) > 0 && p.normalized_price <= p.avgPrice * goodBuyThreshold);
    const freshness = items.length ? items.filter(p => p.hasPriceToday).length / items.length * 100 : 0;
    const coverage = items.length ? items.filter(p => p.hist_count > 1).length / items.length * 100 : 0;
    const volatility = average(items.map(p => p.avgPrice > 0 ? ((p.maxPrice - p.minPrice) / p.avgPrice) * 100 : 0).filter(Number.isFinite));
    const savings = deals.reduce((sum, p) => sum + Math.max(0, p.avgPrice - p.normalized_price), 0);
    return {
        key,
        items,
        count: items.length,
        avg: average(prices),
        median: percentile(prices, .5),
        min: prices[0] || 0,
        max: prices[prices.length - 1] || 0,
        deals: deals.length,
        freshness,
        coverage,
        volatility,
        savings,
        categories: new Set(items.map(p => p.category)).size,
        stores: new Set(items.map(p => p.store)).size
    };
}

async function loadAnalyticsHistory(products) {
    if (window.GOD_DEMO_MODE || !godDB) return loadDemoAnalyticsHistory(products);

    const conditions = ['h.normalized_price > 0'];
    if (analyticsState.scope === 'store' && analyticsState.store !== 'all') conditions.push(`p.store = '${sqlEscape(analyticsState.store)}'`);
    if (analyticsState.scope === 'category' && analyticsState.category !== 'all') conditions.push(`p.category = '${sqlEscape(analyticsState.category)}'`);
    if (analyticsState.scope === 'store' && analyticsState.category !== 'all') conditions.push(`p.category = '${sqlEscape(analyticsState.category)}'`);
    if (analyticsState.scope === 'category' && analyticsState.store !== 'all') conditions.push(`p.store = '${sqlEscape(analyticsState.store)}'`);
    if (analyticsState.unit !== 'all') conditions.push(`LOWER(p.unit_type) IN (${unitSqlValues(analyticsState.unit)})`);
    if (analyticsState.window !== 'all') conditions.push(`h.date >= '${getNDaysAgoStr(Number(analyticsState.window))}'`);
    const where = conditions.join(' AND ');

    const trendResult = await godDB.conn.query(`
        SELECT h.date,
               AVG(h.normalized_price) AS avg_price,
               quantile_cont(h.normalized_price, 0.5) AS median_price,
               COUNT(DISTINCT h.product_id) AS active_products
        FROM history_access h
        JOIN read_parquet('products.parquet') p ON p.id = h.product_id
        WHERE ${where}
        GROUP BY h.date
        ORDER BY h.date ASC
    `);

    const moverResult = await godDB.conn.query(`
        SELECT p.id, p.name, p.store, p.category, p.unit_type,
               arg_min(h.normalized_price, h.date) AS first_price,
               arg_max(h.normalized_price, h.date) AS last_price,
               MIN(h.normalized_price) AS min_price,
               MAX(h.normalized_price) AS max_price,
               COUNT(*) AS points
        FROM history_access h
        JOIN read_parquet('products.parquet') p ON p.id = h.product_id
        WHERE ${where}
        GROUP BY p.id, p.name, p.store, p.category, p.unit_type
        HAVING COUNT(*) >= 2
    `);

    return {
        trend: trendResult.toArray().map(row => {
            const value = row.toJSON();
            return { date: String(value.date), avg_price: Number(value.avg_price), median_price: Number(value.median_price), active_products: Number(value.active_products) };
        }),
        movers: moverResult.toArray().map(row => {
            const value = row.toJSON();
            const first = Number(value.first_price);
            const last = Number(value.last_price);
            return { ...value, first_price: first, last_price: last, move_pct: first > 0 ? ((last - first) / first) * 100 : 0 };
        })
    };
}

function loadDemoAnalyticsHistory(products) {
    const cutoff = analyticsState.window === 'all' ? null : getNDaysAgoStr(Number(analyticsState.window));
    const byDate = new Map();
    const movers = [];
    products.forEach(product => {
        const history = (product.history || []).filter(row => !cutoff || row.date >= cutoff);
        history.forEach(row => {
            const value = Number(row.normalized_price || row.price);
            if (!(value > 0)) return;
            if (!byDate.has(row.date)) byDate.set(row.date, []);
            byDate.get(row.date).push(value);
        });
        if (history.length >= 2) {
            const first = Number(history[0].normalized_price || history[0].price);
            const last = Number(history[history.length - 1].normalized_price || history[history.length - 1].price);
            movers.push({
                id: product.id,
                name: product.name,
                store: product.store,
                category: product.category,
                unit_type: product.unit_type,
                first_price: first,
                last_price: last,
                min_price: Math.min(...history.map(row => Number(row.normalized_price || row.price))),
                max_price: Math.max(...history.map(row => Number(row.normalized_price || row.price))),
                points: history.length,
                move_pct: first > 0 ? ((last - first) / first) * 100 : 0
            });
        }
    });
    const trend = [...byDate.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([date, values]) => ({
        date,
        avg_price: average(values),
        median_price: percentile(values.sort((a, b) => a - b), .5),
        active_products: values.length
    }));
    return { trend, movers };
}

function renderAnalytics(model, history) {
    renderInsightStrip(model, history);
    renderKPIs(model, history);
    renderStoreComparison(model.storeGroups);
    renderCategoryAnalysis(model.categoryGroups);
    renderMarketShare(model.storeGroups);
    renderPriceDistribution(model.prices);
    renderUnitTypeSplit(model.unitGroups);
    renderTrendChart(history.trend);
    renderHealthChart(model);
    renderCategoryPriceChart(model.categoryGroups);
    renderVolatilityChart(model.products);
    renderDealAnalytics(model);
    renderMovers(model, history.movers);
    renderStoreDeepDive(model.storeGroups);
    renderCategoryDeepDive(model.categoryGroups);
    renderCoverageHeatmap(model.products);
    renderCrossStoreTable(model.products);
    renderQualityDashboard(model);
}

function updateAnalyticsContext(model) {
    const context = document.getElementById('analytics-context');
    if (!context) return;
    let scopeText = 'Combined market view';
    if (analyticsState.scope === 'store') scopeText = `Shop: ${STORE_CONFIG[analyticsState.store]?.name || analyticsState.store}`;
    if (analyticsState.scope === 'category') scopeText = `Category: ${analyticsState.category}`;
    const windowText = analyticsState.window === 'all' ? 'all history' : `${analyticsState.window}-day history`;
    context.textContent = `${scopeText} · ${model.products.length.toLocaleString()} products · ${windowText}`;
}

function renderInsightStrip(model, history) {
    const strip = document.getElementById('analytics-insight-strip');
    if (!strip) return;
    const priceDirection = model.priceIndex < 98 ? 'below' : model.priceIndex > 102 ? 'above' : 'near';
    const bestGroup = [...model.categoryGroups].sort((a, b) => b.savings - a.savings)[0];
    const confidence = Math.round((model.historyCovered.length / model.products.length * 60) + (model.fresh.length / model.products.length * 40));
    const recentMove = history.trend.length > 1 ? ((history.trend.at(-1).avg_price - history.trend[0].avg_price) / history.trend[0].avg_price) * 100 : 0;
    strip.innerHTML = `
        <div class="insight-card"><i class="fas fa-wave-square"></i><div><strong>Market is ${priceDirection} its historical baseline</strong><span>Price index ${model.priceIndex.toFixed(1)} · ${signedPercent(recentMove)} in selected window</span></div></div>
        <div class="insight-card"><i class="fas fa-sack-dollar"></i><div><strong>${escapeHTML(bestGroup?.key || 'No category')} has the largest value pool</strong><span>${formatTk(bestGroup?.savings || 0)} potential unit-price savings across current deals</span></div></div>
        <div class="insight-card"><i class="fas fa-shield-check"></i><div><strong>${confidence}% analytics confidence</strong><span>${percent(model.historyCovered.length, model.products.length)} history coverage · ${percent(model.fresh.length, model.products.length)} fresh today</span></div></div>
    `;
}

function renderKPIs(model, history) {
    const grid = document.getElementById('kpi-grid');
    if (!grid) return;
    const recentMove = history.trend.length > 1 ? ((history.trend.at(-1).avg_price - history.trend[0].avg_price) / history.trend[0].avg_price) * 100 : 0;
    const cards = [
        ['Products', model.products.length.toLocaleString(), `${model.storeGroups.length} shops · ${model.categoryGroups.length} categories`, '#bb86fc'],
        ['Average unit price', formatTk(model.averagePrice), `Median ${formatTk(model.medianPrice)}`, '#03dac6'],
        ['Middle 50% range', `${fmt(Math.round(model.q1))}–${fmt(Math.round(model.q3))}`, '25th to 75th percentile', '#60a5fa'],
        ['Price index', model.priceIndex.toFixed(1), '100 = historical average', model.priceIndex <= 100 ? '#34d399' : '#f59e0b'],
        ['Great deals', model.greatDeals.length.toLocaleString(), `${percent(model.greatDeals.length, model.products.length)} of scope`, '#34d399'],
        ['All-time lows', model.allTimeLows.length.toLocaleString(), `${percent(model.allTimeLows.length, model.products.length)} of scope`, '#f59e0b'],
        ['New in 7 days', model.new7.length.toLocaleString(), `${model.new30.length.toLocaleString()} in 30 days`, '#38bdf8'],
        ['Fresh today', percent(model.fresh.length, model.products.length), `${model.products.length - model.fresh.length} stale / unavailable`, '#22c55e'],
        ['History coverage', percent(model.historyCovered.length, model.products.length), `${model.historyCovered.length.toLocaleString()} tracked products`, '#a78bfa'],
        ['Avg volatility', `${model.avgVolatility.toFixed(1)}%`, 'Average historical range', '#fb7185'],
        ['Selected-window move', signedPercent(recentMove), history.trend.length ? `${history.trend.length} active dates` : 'No trend history', recentMove <= 0 ? '#34d399' : '#f97316'],
        ['Value opportunity', formatTk(model.savingsPotential), 'Sum of unit-price gaps vs average', '#facc15']
    ];
    grid.innerHTML = cards.map(([label, value, sub, accent], index) => `
        <div class="kpi-card" style="--kpi-accent:${accent}">
            ${index === 3 ? `<span class="kpi-trend ${model.priceIndex <= 100 ? 'good' : 'warn'}">${model.priceIndex <= 100 ? 'BUYER' : 'SELLER'}</span>` : ''}
            <div class="kpi-label">${escapeHTML(label)}</div>
            <div class="kpi-value">${escapeHTML(String(value))}</div>
            <div class="kpi-sub">${escapeHTML(String(sub))}</div>
        </div>`).join('');
}

function renderStoreComparison(groups) {
    const rows = [...groups].sort((a, b) => b.count - a.count);
    const labels = rows.map(row => STORE_CONFIG[row.key]?.name || row.key);
    const colors = rows.map(row => STORE_CONFIG[row.key]?.color || '#94a3b8');
    createAnalyticsChart('store-product-count-chart', 'storeCount', {
        type: 'bar',
        data: { labels, datasets: [{ label: 'Products', data: rows.map(row => row.count), backgroundColor: colors.map(color => withAlpha(color, .72)), borderColor: colors, borderWidth: 1, borderRadius: 5 }] },
        options: chartOptions('Products per shop', false)
    });
    createAnalyticsChart('store-avg-price-chart', 'storeAvg', {
        type: 'bar',
        data: { labels, datasets: [{ label: 'Avg unit price', data: rows.map(row => Math.round(row.avg)), backgroundColor: colors.map(color => withAlpha(color, .35)), borderColor: colors, borderWidth: 1, borderRadius: 5 }] },
        options: chartOptions('Average unit price by shop', false, value => `${value} Tk`)
    });
}

function renderCategoryAnalysis(groups) {
    const rows = [...groups].sort((a, b) => b.count - a.count).slice(0, 18);
    createAnalyticsChart('category-distribution-chart', 'category', {
        type: 'bar',
        data: { labels: rows.map(row => truncate(row.key, 25)), datasets: [{ label: 'Products', data: rows.map(row => row.count), backgroundColor: '#bb86fca8', borderColor: '#bb86fc', borderWidth: 1, borderRadius: 4 }] },
        options: chartOptions('Largest categories', true)
    });
}

function renderMarketShare(groups) {
    const rows = [...groups].sort((a, b) => b.count - a.count);
    createAnalyticsChart('market-share-chart', 'marketShare', {
        type: 'doughnut',
        data: { labels: rows.map(row => STORE_CONFIG[row.key]?.name || row.key), datasets: [{ data: rows.map(row => row.count), backgroundColor: rows.map(row => STORE_CONFIG[row.key]?.color || '#64748b'), borderColor: '#050607', borderWidth: 2 }] },
        options: doughnutOptions('Product coverage share')
    });
}

function renderPriceDistribution(prices) {
    const edges = [0, 50, 100, 200, 500, 1000, 2000, Infinity];
    const labels = ['<50', '50–100', '100–200', '200–500', '500–1K', '1K–2K', '2K+'];
    const counts = labels.map((_, index) => prices.filter(value => value >= edges[index] && value < edges[index + 1]).length);
    createAnalyticsChart('price-distribution-chart', 'priceDist', {
        type: 'bar',
        data: { labels, datasets: [{ label: 'Products', data: counts, backgroundColor: '#03dac677', borderColor: '#03dac6', borderWidth: 1, borderRadius: 5 }] },
        options: chartOptions('Unit-price distribution', false)
    });
}

function renderUnitTypeSplit(groups) {
    const rows = [...groups].sort((a, b) => b.count - a.count);
    createAnalyticsChart('unit-type-split-chart', 'unitSplit', {
        type: 'pie',
        data: { labels: rows.map(row => row.key.toUpperCase()), datasets: [{ data: rows.map(row => row.count), backgroundColor: ['#bb86fc', '#03dac6', '#f59e0b', '#60a5fa'], borderColor: '#050607', borderWidth: 2 }] },
        options: doughnutOptions('Unit type split')
    });
}

function renderTrendChart(rows) {
    if (!rows.length) return renderEmptyChart('trend-chart', 'No history is available for this scope.');
    const labels = formatChartDates(rows.map(row => row.date));
    createAnalyticsChart('trend-chart', 'trend', {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'Average', data: rows.map(row => round(row.avg_price, 1)), borderColor: '#bb86fc', backgroundColor: '#bb86fc20', fill: true, tension: .28, pointRadius: rows.length > 45 ? 0 : 1.5, borderWidth: 2 },
                { label: 'Median', data: rows.map(row => round(row.median_price, 1)), borderColor: '#03dac6', backgroundColor: 'transparent', tension: .28, pointRadius: 0, borderDash: [5, 4], borderWidth: 1.5 }
            ]
        },
        options: lineChartOptions('Average and median unit price', value => `${value} Tk`)
    });
}

function renderHealthChart(model) {
    const unresolved = Math.max(0, model.products.length - model.greatDeals.length - model.goodDeals.length - model.fair.length - model.wait.length);
    createAnalyticsChart('health-chart', 'health', {
        type: 'doughnut',
        data: { labels: ['Great deal', 'Good buy', 'Fair', 'Wait', 'Limited history'], datasets: [{ data: [model.greatDeals.length, model.goodDeals.length, model.fair.length, model.wait.length, unresolved], backgroundColor: ['#10b981', '#03dac6', '#60a5fa', '#f97316', '#334155'], borderColor: '#050607', borderWidth: 2 }] },
        options: doughnutOptions('Current price signal')
    });
}

function renderCategoryPriceChart(groups) {
    const rows = [...groups].sort((a, b) => b.count - a.count).slice(0, 14).sort((a, b) => a.avg - b.avg);
    createAnalyticsChart('category-price-chart', 'categoryPrice', {
        type: 'bar',
        data: { labels: rows.map(row => truncate(row.key, 24)), datasets: [{ label: 'Average', data: rows.map(row => Math.round(row.avg)), backgroundColor: '#60a5fa66', borderColor: '#60a5fa', borderWidth: 1, borderRadius: 4 }, { label: 'Median', data: rows.map(row => Math.round(row.median)), backgroundColor: '#03dac655', borderColor: '#03dac6', borderWidth: 1, borderRadius: 4 }] },
        options: chartOptions('Category price profile', true, value => `${value} Tk`)
    });
}

function renderVolatilityChart(products) {
    const rows = products.filter(p => p.hist_count > 2 && p.avgPrice > 0).map(product => ({
        product,
        volatility: ((product.maxPrice - product.minPrice) / product.avgPrice) * 100
    })).filter(row => Number.isFinite(row.volatility)).sort((a, b) => b.volatility - a.volatility).slice(0, 14).reverse();
    createAnalyticsChart('volatility-chart', 'volatility', {
        type: 'bar',
        data: { labels: rows.map(row => truncate(row.product.name, 23)), datasets: [{ label: 'Volatility %', data: rows.map(row => round(row.volatility, 1)), backgroundColor: '#fb718566', borderColor: '#fb7185', borderWidth: 1, borderRadius: 4 }] },
        options: chartOptions('Most volatile products', true, value => `${value}%`)
    });
}

function renderDealAnalytics(model) {
    const grid = document.getElementById('deal-kpi-grid');
    if (grid) {
        const avgDiscount = average(model.greatDeals.concat(model.goodDeals).map(p => ((p.avgPrice - p.normalized_price) / p.avgPrice) * 100));
        const cards = [
            ['Great deals', model.greatDeals.length, '15%+ below history', '#10b981'],
            ['Good buys', model.goodDeals.length, '5–15% below history', '#03dac6'],
            ['Wait signals', model.wait.length, '5%+ above history', '#f97316'],
            ['All-time lows', model.allTimeLows.length, 'Lowest tracked price', '#f59e0b'],
            ['Average discount', `${avgDiscount.toFixed(1)}%`, 'Across current deals', '#60a5fa'],
            ['Savings pool', formatTk(model.savingsPotential), 'Unit-price gap vs average', '#facc15']
        ];
        grid.innerHTML = cards.map(([label, value, sub, accent]) => `<div class="kpi-card" style="--kpi-accent:${accent}"><div class="kpi-label">${escapeHTML(label)}</div><div class="kpi-value">${escapeHTML(String(value))}</div><div class="kpi-sub">${escapeHTML(sub)}</div></div>`).join('');
    }

    createAnalyticsChart('deal-split-chart', 'dealSplit', {
        type: 'bar',
        data: { labels: ['Great deal', 'Good buy', 'Fair', 'Wait'], datasets: [{ label: 'Products', data: [model.greatDeals.length, model.goodDeals.length, model.fair.length, model.wait.length], backgroundColor: ['#10b981aa', '#03dac6aa', '#60a5faaa', '#f97316aa'], borderColor: ['#10b981', '#03dac6', '#60a5fa', '#f97316'], borderWidth: 1, borderRadius: 5 }] },
        options: chartOptions('Deal signal distribution', false)
    });

    const categories = [...model.categoryGroups].sort((a, b) => b.savings - a.savings).slice(0, 12).reverse();
    createAnalyticsChart('savings-opportunity-chart', 'savings', {
        type: 'bar',
        data: { labels: categories.map(row => truncate(row.key, 24)), datasets: [{ label: 'Potential savings', data: categories.map(row => Math.round(row.savings)), backgroundColor: '#facc1566', borderColor: '#facc15', borderWidth: 1, borderRadius: 4 }] },
        options: chartOptions('Value opportunity by category', true, value => `${value} Tk`)
    });
}

function renderMovers(model, movers) {
    const grid = document.getElementById('movers-grid');
    if (!grid) return;
    const falling = [...movers].filter(row => row.move_pct < 0).sort((a, b) => a.move_pct - b.move_pct).slice(0, 10);
    const rising = [...movers].filter(row => row.move_pct > 0).sort((a, b) => b.move_pct - a.move_pct).slice(0, 10);
    const value = [...model.greatDeals, ...model.goodDeals].sort((a, b) => ((a.normalized_price - a.avgPrice) / a.avgPrice) - ((b.normalized_price - b.avgPrice) / b.avgPrice)).slice(0, 10).map(product => ({
        name: product.name,
        store: product.store,
        value: ((product.normalized_price - product.avgPrice) / product.avgPrice) * 100
    }));

    grid.innerHTML = '';
    grid.appendChild(buildMoverColumn('Biggest recent drops', falling.map(row => ({ name: row.name, store: row.store, value: row.move_pct })), '#10b981'));
    grid.appendChild(buildMoverColumn('Biggest recent rises', rising.map(row => ({ name: row.name, store: row.store, value: row.move_pct })), '#fb7185'));
    grid.appendChild(buildMoverColumn('Best vs historical average', value, '#facc15'));
}

function buildMoverColumn(title, rows, color) {
    const column = document.createElement('div');
    column.className = 'movers-column';
    column.innerHTML = `<h4 style="color:${color}">${escapeHTML(title)}</h4>`;
    if (!rows.length) {
        column.innerHTML += '<div class="mover-item"><span class="mover-name" style="color:#64748b">Not enough history for this window.</span></div>';
        return column;
    }
    rows.forEach((row, index) => {
        const storeColor = STORE_CONFIG[row.store]?.color || '#64748b';
        column.innerHTML += `<div class="mover-item"><span class="mover-rank ${index < 3 ? 'top' : ''}">${index + 1}</span><span class="mover-name" title="${escapeAttribute(row.name)}">${escapeHTML(row.name)}</span><span class="mover-store" style="background:${storeColor};color:#000">${escapeHTML(STORE_CONFIG[row.store]?.name || row.store)}</span><span class="mover-val" style="color:${color}">${signedPercent(row.value)}</span></div>`;
    });
    return column;
}

function renderStoreDeepDive(groups) {
    const container = document.getElementById('store-deep-dive');
    if (!container) return;
    container.innerHTML = [...groups].sort((a, b) => b.count - a.count).map(group => {
        const config = STORE_CONFIG[group.key] || { color: '#64748b', name: group.key };
        const topCategories = groupProducts(group.items, p => p.category).sort((a, b) => b.count - a.count).slice(0, 4);
        const maxCount = topCategories[0]?.count || 1;
        return `<article class="store-dive-card" style="--store-color:${config.color}">
            <h4 style="color:${config.color}"><i class="fas fa-store"></i> ${escapeHTML(config.name)}</h4>
            <div class="store-dive-stats">
                <div class="store-dive-stat"><div class="sds-label">Products</div><div class="sds-value">${group.count.toLocaleString()}</div></div>
                <div class="store-dive-stat"><div class="sds-label">Avg price</div><div class="sds-value">${formatTk(group.avg)}</div></div>
                <div class="store-dive-stat"><div class="sds-label">Deals</div><div class="sds-value" style="color:var(--accent-secondary)">${group.deals}</div></div>
                <div class="store-dive-stat"><div class="sds-label">Fresh today</div><div class="sds-value">${group.freshness.toFixed(0)}%</div></div>
                <div class="store-dive-stat"><div class="sds-label">History</div><div class="sds-value">${group.coverage.toFixed(0)}%</div></div>
                <div class="store-dive-stat"><div class="sds-label">Volatility</div><div class="sds-value">${group.volatility.toFixed(1)}%</div></div>
            </div>
            <div class="store-dive-cats">${topCategories.map(category => `<div class="store-dive-cat-bar"><span style="min-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHTML(truncate(category.key, 15))}</span><div class="bar-fill"><div style="width:${category.count / maxCount * 100}%;background:${config.color}"></div></div><span style="min-width:28px;text-align:right;color:#64748b">${category.count}</span></div>`).join('')}</div>
        </article>`;
    }).join('');
}

function renderCategoryDeepDive(groups) {
    const container = document.getElementById('category-deep-dive');
    if (!container) return;
    const rows = [...groups].sort((a, b) => b.count - a.count).slice(0, 18);
    const maxCount = rows[0]?.count || 1;
    container.innerHTML = rows.map(group => `<article class="category-dive-card">
        <h4>${escapeHTML(group.key)}</h4>
        <div class="category-card-row"><span>Products</span><strong>${group.count.toLocaleString()}</strong></div>
        <div class="category-card-row"><span>Shops represented</span><strong>${group.stores}</strong></div>
        <div class="category-card-row"><span>Average / median</span><strong>${formatTk(group.avg)} / ${formatTk(group.median)}</strong></div>
        <div class="category-card-row"><span>Deals · Fresh</span><strong>${group.deals} · ${group.freshness.toFixed(0)}%</strong></div>
        <div class="category-progress"><div style="width:${group.count / maxCount * 100}%"></div></div>
    </article>`).join('');
}

function renderCoverageHeatmap(products) {
    const container = document.getElementById('coverage-heatmap');
    if (!container) return;
    const stores = [...new Set(products.map(p => p.store))].sort();
    const categories = [...new Set(products.map(p => p.category))].sort((a, b) => products.filter(p => p.category === b).length - products.filter(p => p.category === a).length).slice(0, 16);
    const counts = new Map();
    products.forEach(product => counts.set(`${product.store}|||${product.category}`, (counts.get(`${product.store}|||${product.category}`) || 0) + 1));
    const max = Math.max(1, ...counts.values());
    let html = '<table class="metric-table"><thead><tr><th>Shop</th>' + categories.map(category => `<th class="numeric">${escapeHTML(truncate(category, 13))}</th>`).join('') + '<th class="numeric">Total</th></tr></thead><tbody>';
    stores.forEach(store => {
        const total = products.filter(p => p.store === store).length;
        html += `<tr><td style="color:${STORE_CONFIG[store]?.color || '#94a3b8'};font-weight:900">${escapeHTML(STORE_CONFIG[store]?.name || store)}</td>`;
        categories.forEach(category => {
            const count = counts.get(`${store}|||${category}`) || 0;
            const opacity = count ? .12 + (count / max) * .68 : 0;
            html += `<td class="heatmap-cell" style="background:rgba(3,218,198,${opacity.toFixed(2)})">${count || '·'}</td>`;
        });
        html += `<td class="numeric" style="font-weight:900">${total}</td></tr>`;
    });
    container.innerHTML = html + '</tbody></table>';
}

function renderCrossStoreTable(products) {
    const container = document.getElementById('cross-store-table-container');
    if (!container) return;
    const stores = [...new Set(products.map(p => p.store))].sort();
    const productMap = new Map();
    products.forEach(product => {
        const key = `${normalizeName(product.name)}|||${product.category}|||${normalizeUnitType(product.unit_type)}`;
        if (!productMap.has(key)) productMap.set(key, { name: product.name, category: product.category, unit: normalizeUnitType(product.unit_type), prices: {} });
        const current = productMap.get(key).prices[product.store];
        if (current == null || product.normalized_price < current) productMap.get(key).prices[product.store] = Number(product.normalized_price);
    });
    const rows = [...productMap.values()].filter(row => Object.keys(row.prices).length >= 2).map(row => {
        const values = Object.values(row.prices);
        return { ...row, min: Math.min(...values), max: Math.max(...values), spread: Math.max(...values) - Math.min(...values) };
    }).sort((a, b) => b.spread - a.spread).slice(0, 50);

    let html = '<table class="cross-table"><thead><tr><th>Product</th><th>Category</th>' + stores.map(store => `<th style="text-align:right;color:${STORE_CONFIG[store]?.color || '#94a3b8'}">${escapeHTML(STORE_CONFIG[store]?.name || store)}</th>`).join('') + '<th style="text-align:right">Spread</th></tr></thead><tbody>';
    rows.forEach(row => {
        html += `<tr><td title="${escapeAttribute(row.name)}" style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHTML(row.name)}</td><td style="color:#64748b">${escapeHTML(row.category)}</td>`;
        stores.forEach(store => {
            const value = row.prices[store];
            if (value == null) html += '<td class="price-cell" style="color:#334155">–</td>';
            else html += `<td class="price-cell ${value === row.min ? 'best-price' : ''} ${value === row.max && row.max !== row.min ? 'worst-price' : ''}">${fmt(Math.round(value))}</td>`;
        });
        html += `<td class="price-cell" style="color:var(--gold)">${fmt(Math.round(row.spread))}</td></tr>`;
    });
    if (!rows.length) html += '<tr><td colspan="20" style="padding:24px;text-align:center;color:#64748b">No exact cross-shop product matches in this scope.</td></tr>';
    container.innerHTML = html + '</tbody></table>';
}

function renderQualityDashboard(model) {
    const grid = document.getElementById('quality-kpi-grid');
    const missingImages = model.products.filter(p => !p.image).length;
    const missingTaxonomy = model.products.filter(p => !p.category || !p.unit_type || !p.unit).length;
    const stale = model.products.length - model.fresh.length;
    const thinHistory = model.products.filter(p => p.hist_count < 2).length;
    const duplicateKeys = countDuplicateProducts(model.products);
    const qualityScore = Math.max(0, Math.round(100 - percentNumber(missingImages + missingTaxonomy + stale + thinHistory, model.products.length * 4) - Math.min(20, model.anomalies.length / Math.max(1, model.products.length) * 100)));
    if (grid) {
        const cards = [
            ['Quality score', `${qualityScore}%`, 'Freshness, completeness and anomaly mix', qualityScore >= 85 ? '#10b981' : '#f59e0b'],
            ['Missing images', missingImages, percent(missingImages, model.products.length), '#fb7185'],
            ['Missing taxonomy', missingTaxonomy, 'Category / unit / pack', '#f97316'],
            ['Stale / unavailable', stale, percent(stale, model.products.length), '#f59e0b'],
            ['Thin history', thinHistory, '<2 tracked observations', '#60a5fa'],
            ['Possible duplicates', duplicateKeys, 'Same shop + normalized name', '#a78bfa'],
            ['Potential anomalies', model.anomalies.length, 'Price / volatility / metadata rules', '#fb7185'],
            ['Fresh today', model.fresh.length, percent(model.fresh.length, model.products.length), '#03dac6']
        ];
        grid.innerHTML = cards.map(([label, value, sub, accent]) => `<div class="kpi-card" style="--kpi-accent:${accent}"><div class="kpi-label">${escapeHTML(label)}</div><div class="kpi-value">${escapeHTML(String(value))}</div><div class="kpi-sub">${escapeHTML(String(sub))}</div></div>`).join('');
    }
    renderFreshnessTable(model.storeGroups);
    renderAnomalyTable(model.anomalies);
}

function renderFreshnessTable(groups) {
    const container = document.getElementById('freshness-table');
    if (!container) return;
    const rows = [...groups].sort((a, b) => b.count - a.count);
    container.innerHTML = `<table class="metric-table"><thead><tr><th>Shop</th><th class="numeric">Products</th><th class="numeric">Fresh today</th><th class="numeric">History coverage</th><th class="numeric">Avg volatility</th><th class="numeric">Deals</th><th>Status</th></tr></thead><tbody>${rows.map(row => {
        const status = row.freshness >= 90 && row.coverage >= 80 ? ['Healthy', 'good'] : row.freshness >= 70 ? ['Watch', 'warn'] : ['Needs attention', 'bad'];
        return `<tr><td style="color:${STORE_CONFIG[row.key]?.color || '#94a3b8'};font-weight:900">${escapeHTML(STORE_CONFIG[row.key]?.name || row.key)}</td><td class="numeric">${row.count}</td><td class="numeric">${row.freshness.toFixed(0)}%</td><td class="numeric">${row.coverage.toFixed(0)}%</td><td class="numeric">${row.volatility.toFixed(1)}%</td><td class="numeric">${row.deals}</td><td><span class="metric-badge ${status[1]}">${status[0]}</span></td></tr>`;
    }).join('')}</tbody></table>`;
}

function renderAnomalyTable(anomalies) {
    const container = document.getElementById('anomaly-table');
    if (!container) return;
    const rows = anomalies.slice(0, 60);
    container.innerHTML = `<table class="metric-table"><thead><tr><th>Product</th><th>Shop</th><th>Category</th><th>Rule</th><th class="numeric">Unit price</th><th>Severity</th></tr></thead><tbody>${rows.map(row => `<tr><td title="${escapeAttribute(row.product.name)}">${escapeHTML(truncate(row.product.name, 48))}</td><td style="color:${STORE_CONFIG[row.product.store]?.color || '#94a3b8'}">${escapeHTML(STORE_CONFIG[row.product.store]?.name || row.product.store)}</td><td>${escapeHTML(row.product.category || 'Missing')}</td><td>${escapeHTML(row.rule)}</td><td class="numeric">${formatTk(row.product.normalized_price)}</td><td><span class="metric-badge ${row.severity}">${row.severity.toUpperCase()}</span></td></tr>`).join('') || '<tr><td colspan="6" style="padding:24px;text-align:center;color:#64748b">No anomalies detected by the current rules.</td></tr>'}</tbody></table>`;
}

function findAnalyticsAnomalies(products, categoryGroups) {
    const categoryMedians = new Map(categoryGroups.map(group => [group.key, group.median]));
    const anomalies = [];
    products.forEach(product => {
        const median = categoryMedians.get(product.category) || 0;
        if (!product.image) anomalies.push({ product, rule: 'Missing product image', severity: 'warn' });
        if (!product.category || !product.unit_type || !product.unit) anomalies.push({ product, rule: 'Incomplete taxonomy or unit metadata', severity: 'warn' });
        if (!product.hasPriceToday) anomalies.push({ product, rule: 'No price observed today', severity: 'warn' });
        if (median > 0 && product.normalized_price > median * 4) anomalies.push({ product, rule: 'Price is >4× category median', severity: 'bad' });
        if (median > 0 && product.normalized_price < median * .15) anomalies.push({ product, rule: 'Price is <15% of category median', severity: 'bad' });
        if (product.avgPrice > 0 && ((product.maxPrice - product.minPrice) / product.avgPrice) > 1.25) anomalies.push({ product, rule: 'Historical range exceeds 125% of average', severity: 'bad' });
    });
    return anomalies.sort((a, b) => severityRank(b.severity) - severityRank(a.severity));
}

function exportAnalyticsCSV() {
    const products = getAnalyticsProducts();
    if (!products.length) return;
    const headers = ['id', 'name', 'store', 'category', 'unit', 'unit_type', 'current_price', 'normalized_price', 'historical_average', 'historical_min', 'historical_max', 'history_points', 'first_seen', 'fresh_today'];
    const lines = [headers.join(',')];
    products.forEach(product => {
        lines.push([
            product.id, product.name, STORE_CONFIG[product.store]?.name || product.store, product.category, product.unit, product.unit_type,
            product.current_price, product.normalized_price, product.avgPrice, product.minPrice, product.maxPrice, product.hist_count, product.first_seen, product.hasPriceToday
        ].map(csvCell).join(','));
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `grocerygod-${analyticsState.scope}-${todayStr}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function destroyAnalyticsCharts() {
    Object.values(analyticsCharts).forEach(chart => { try { chart.destroy(); } catch (_) {} });
    analyticsCharts = {};
}

function createAnalyticsChart(canvasId, key, config) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === 'undefined') return;
    if (analyticsCharts[key]) analyticsCharts[key].destroy();
    analyticsCharts[key] = new Chart(canvas.getContext('2d'), config);
}

function renderEmptyChart(canvasId, message) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const context = canvas.getContext('2d');
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = '#64748b';
    context.font = '12px system-ui';
    context.textAlign = 'center';
    context.fillText(message, canvas.width / 2, canvas.height / 2);
}

function chartOptions(title, horizontal = false, tickFormatter = null) {
    return {
        indexAxis: horizontal ? 'y' : 'x',
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 260 },
        plugins: {
            legend: { display: false },
            title: { display: true, text: title, color: '#e5edf6', font: { size: 12, weight: 'bold' }, padding: { bottom: 10 } },
            tooltip: { backgroundColor: '#111827', borderColor: '#334155', borderWidth: 1, titleColor: '#fff', bodyColor: '#cbd5e1' }
        },
        scales: {
            x: { grid: { color: horizontal ? '#141922' : 'transparent' }, ticks: { color: '#718096', font: { size: 9 }, callback: horizontal && tickFormatter ? tickFormatter : undefined } },
            y: { grid: { color: horizontal ? 'transparent' : '#141922' }, ticks: { color: '#94a3b8', font: { size: 9 }, callback: !horizontal && tickFormatter ? tickFormatter : undefined } }
        }
    };
}

function lineChartOptions(title, tickFormatter = null) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 260 },
        interaction: { mode: 'index', intersect: false },
        plugins: {
            title: { display: false, text: title },
            legend: { position: 'bottom', labels: { color: '#94a3b8', boxWidth: 10, padding: 12, font: { size: 9, weight: 'bold' } } },
            tooltip: { backgroundColor: '#111827', borderColor: '#334155', borderWidth: 1 }
        },
        scales: {
            x: { grid: { color: '#10141a' }, ticks: { color: '#64748b', font: { size: 8 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } },
            y: { grid: { color: '#141922' }, ticks: { color: '#94a3b8', font: { size: 9 }, callback: tickFormatter || undefined } }
        }
    };
}

function doughnutOptions(title) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '58%',
        plugins: {
            title: { display: true, text: title, color: '#e5edf6', font: { size: 12, weight: 'bold' } },
            legend: { position: 'bottom', labels: { color: '#94a3b8', boxWidth: 9, padding: 9, font: { size: 8, weight: 'bold' } } },
            tooltip: { backgroundColor: '#111827', borderColor: '#334155', borderWidth: 1 }
        }
    };
}

function getNDaysAgoStr(days) {
    const date = toDhaka();
    date.setDate(date.getDate() - days);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function normalizeUnitType(unit) {
    const value = String(unit || '').toLowerCase();
    if (['ltr', 'l', 'liter', 'litre', 'ml'].includes(value)) return 'liter';
    if (['kg', 'g', 'gram', 'grams'].includes(value)) return 'kg';
    return 'piece';
}

function unitSqlValues(unit) {
    if (unit === 'liter') return "'liter','litre','ltr','l','ml'";
    if (unit === 'kg') return "'kg','g','gram','grams'";
    return "'piece','pieces','pcs','pc','each'";
}

function normalizeName(value) {
    return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function average(values) {
    const valid = values.map(Number).filter(Number.isFinite);
    return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : 0;
}

function percentile(sortedValues, value) {
    if (!sortedValues.length) return 0;
    const index = (sortedValues.length - 1) * value;
    const lower = Math.floor(index);
    const upper = Math.ceil(index);
    if (lower === upper) return sortedValues[lower];
    return sortedValues[lower] + (sortedValues[upper] - sortedValues[lower]) * (index - lower);
}

function percent(value, total) {
    return `${percentNumber(value, total).toFixed(0)}%`;
}

function percentNumber(value, total) {
    return total ? (Number(value) / Number(total)) * 100 : 0;
}

function signedPercent(value) {
    const number = Number(value) || 0;
    return `${number > 0 ? '+' : ''}${number.toFixed(1)}%`;
}

function formatTk(value) {
    const number = Number(value) || 0;
    return `${Math.round(number).toLocaleString()} Tk`;
}

function round(value, digits = 0) {
    const factor = 10 ** digits;
    return Math.round(Number(value) * factor) / factor;
}

function truncate(value, maxLength) {
    const text = String(value || '');
    return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function withAlpha(hex, alpha) {
    const value = String(hex || '#64748b').replace('#', '');
    if (value.length !== 6) return `rgba(100,116,139,${alpha})`;
    const red = parseInt(value.slice(0, 2), 16);
    const green = parseInt(value.slice(2, 4), 16);
    const blue = parseInt(value.slice(4, 6), 16);
    return `rgba(${red},${green},${blue},${alpha})`;
}

function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
}

function escapeAttribute(value) {
    return escapeHTML(value).replace(/`/g, '&#96;');
}

function sqlEscape(value) {
    return String(value ?? '').replace(/'/g, "''");
}

function csvCell(value) {
    const text = String(value ?? '');
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function severityRank(value) {
    return value === 'bad' ? 3 : value === 'warn' ? 2 : 1;
}

function countDuplicateProducts(products) {
    const seen = new Set();
    const duplicates = new Set();
    products.forEach(product => {
        const key = `${product.store}|||${normalizeName(product.name)}|||${normalizeUnitType(product.unit_type)}`;
        if (seen.has(key)) duplicates.add(key);
        else seen.add(key);
    });
    return duplicates.size;
}


// ============================================================
// FREEMIUM ACCESS, THEME, HISTORY PREVIEW AND PRICE ALERTS
// ============================================================

async function fetchFirstAvailable(paths, label = 'asset') {
    let lastError = null;
    for (const path of paths) {
        try {
            const response = await fetch(path, { cache: 'no-store' });
            if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
            return { path, buffer: await response.arrayBuffer() };
        } catch (error) {
            lastError = error;
        }
    }
    throw new Error(`Unable to load ${label}: ${lastError?.message || 'not found'}`);
}

function setupThemeToggle() {
    const saved = safeStorage.getItem('god_theme') || 'amoled';
    applyTheme(saved, false);
    document.getElementById('theme-toggle-btn')?.addEventListener('click', () => {
        applyTheme(document.body.classList.contains('theme-light') ? 'amoled' : 'light');
    });
}

function applyTheme(theme, persist = true) {
    const light = theme === 'light';
    document.body.classList.toggle('theme-light', light);
    document.body.classList.toggle('theme-amoled', !light);
    document.documentElement.style.colorScheme = light ? 'light' : 'dark';
    const button = document.getElementById('theme-toggle-btn');
    if (button) {
        button.title = light ? 'Switch to AMOLED black' : 'Switch to light theme';
        const icon = button.querySelector('i');
        if (icon) icon.className = light ? 'fas fa-sun' : 'fas fa-moon';
    }
    if (persist) safeStorage.setItem('god_theme', light ? 'light' : 'amoled');
    if (detailChart && currentDetailProductIndex >= 0 && currentFilteredProducts[currentDetailProductIndex]) {
        openDetailedChart(currentFilteredProducts[currentDetailProductIndex]);
    }
}

function getChartTheme() {
    const light = document.body.classList.contains('theme-light');
    return {
        actual: light ? '#24364b' : '#ffffff',
        text: light ? '#42566e' : '#dbe5f0',
        grid: light ? 'rgba(54,74,95,.14)' : 'rgba(148,163,184,.13)'
    };
}

function setupPremiumUI() {
    document.body.classList.toggle('demo-mode', Boolean(window.GOD_DEMO_MODE));
    setPremiumUnlocked(premiumUnlocked, false);

    document.getElementById('premium-key-btn')?.addEventListener('click', () => openPremiumModal(premiumUnlocked ? 'success' : 'unlock'));
    document.getElementById('history-upgrade-btn')?.addEventListener('click', () => openPremiumModal('plans'));
    document.getElementById('show-unlock-step-btn')?.addEventListener('click', () => setPremiumStep('unlock'));
    document.querySelectorAll('.premium-back').forEach(button => button.addEventListener('click', () => setPremiumStep(button.dataset.back || 'plans')));
    document.querySelectorAll('.plan-card').forEach(card => card.addEventListener('click', () => selectPremiumPlan(card.dataset.plan)));
    document.getElementById('continue-payment-btn')?.addEventListener('click', () => {
        paymentReference = generateReferenceKey(5);
        document.getElementById('payment-reference').textContent = paymentReference;
        document.getElementById('payment-plan-title').textContent = premiumPlan === 'yearly' ? '1998 Tk yearly' : '398 Tk monthly';
        setPremiumStep('payment');
    });
    document.getElementById('copy-reference-btn')?.addEventListener('click', async () => {
        if (!paymentReference) return;
        try {
            await navigator.clipboard.writeText(paymentReference);
            showUXToast(`Reference ${paymentReference} copied.`, 'info');
        } catch (_) {
            showUXToast(`Reference: ${paymentReference}`, 'info');
        }
    });
    document.getElementById('payment-done-btn')?.addEventListener('click', () => {
        setPremiumStep('unlock');
        const status = document.getElementById('unlock-status');
        if (status) status.textContent = `Payment reference ${paymentReference || 'saved'} is ready for verification.`;
    });
    document.getElementById('toggle-passphrase')?.addEventListener('click', () => {
        const input = document.getElementById('premium-passphrase');
        if (!input) return;
        input.type = input.type === 'password' ? 'text' : 'password';
        const icon = document.querySelector('#toggle-passphrase i');
        if (icon) icon.className = input.type === 'password' ? 'fas fa-eye' : 'fas fa-eye-slash';
    });
    document.getElementById('unlock-submit-btn')?.addEventListener('click', attemptPremiumUnlock);
    document.getElementById('premium-passphrase')?.addEventListener('keydown', event => {
        if (event.key === 'Enter') attemptPremiumUnlock();
    });
    document.getElementById('premium-success-close')?.addEventListener('click', closePremiumModal);
    document.querySelectorAll('#premium-modal .close-modal').forEach(button => button.addEventListener('click', closePremiumModal));
    selectPremiumPlan(premiumPlan);
}

function selectPremiumPlan(plan) {
    premiumPlan = plan === 'yearly' ? 'yearly' : 'monthly';
    safeStorage.setItem('god_premium_plan', premiumPlan);
    document.querySelectorAll('.plan-card').forEach(card => card.classList.toggle('active', card.dataset.plan === premiumPlan));
}

function openPremiumModal(step = 'plans') {
    const modal = document.getElementById('premium-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    setPremiumStep(step);
    if (step === 'unlock') setTimeout(() => document.getElementById('premium-passphrase')?.focus(), 120);
}

function closePremiumModal() {
    const modal = document.getElementById('premium-modal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.add('hidden');
    }
    document.body.style.overflow = '';
}

function setPremiumStep(step) {
    const map = { plans: 'premium-plans-step', payment: 'premium-payment-step', unlock: 'premium-unlock-step', success: 'premium-success-step' };
    document.querySelectorAll('#premium-modal .premium-step').forEach(node => node.classList.toggle('active', node.id === map[step]));
    const status = document.getElementById('unlock-status');
    if (status && step !== 'unlock') {
        status.textContent = '';
        status.classList.remove('success');
    }
}

function generateReferenceKey(length = 5) {
    const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const bytes = new Uint8Array(length);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, value => alphabet[value % alphabet.length]).join('');
}

async function attemptPremiumUnlock() {
    const input = document.getElementById('premium-passphrase');
    const status = document.getElementById('unlock-status');
    const button = document.getElementById('unlock-submit-btn');
    const passphrase = input?.value || '';
    if (!passphrase.trim()) {
        if (status) status.textContent = 'Enter the premium passphrase.';
        return;
    }

    if (button) {
        button.disabled = true;
        button.innerHTML = '<span>Decrypting archive…</span><i class="fas fa-circle-notch fa-spin"></i>';
    }
    if (status) {
        status.textContent = 'Validating key and decrypting premium history…';
        status.classList.remove('success');
    }

    try {
        await unlockPremiumArchive(passphrase);
        setPremiumUnlocked(true);
        if (status) {
            status.textContent = 'Premium archive decrypted successfully.';
            status.classList.add('success');
        }
        setPremiumStep('success');
        processData();
        renderProducts();
        updateStatsBar();
        if (currentDetailProductIndex >= 0 && document.getElementById('chart-modal')?.style.display === 'flex') {
            await openDetailedChart(currentFilteredProducts[currentDetailProductIndex]);
        }
    } catch (error) {
        console.error('[GOD_PREMIUM] Unlock failed:', error);
        if (status) status.textContent = window.GOD_DEMO_MODE ? 'Incorrect demo key. Use GODDEMO.' : 'The key is invalid or the encrypted archive is unavailable.';
    } finally {
        if (button) {
            button.disabled = false;
            button.innerHTML = '<span>Decrypt premium data</span><i class="fas fa-unlock-keyhole"></i>';
        }
    }
}

async function unlockPremiumArchive(passphrase) {
    if (window.GOD_DEMO_MODE) {
        const expected = window.GOD_PREMIUM_DEMO_KEY || 'GODDEMO';
        await new Promise(resolve => setTimeout(resolve, 650));
        if (passphrase !== expected) throw new Error('Invalid demo key');
        return;
    }
    if (!godDB) throw new Error('DuckDB is not ready.');

    const versionQS = `v=${ASSET_VERSION}`;
    const fetched = await fetchFirstAvailable([
        `premium/history_archive.parquet.enc?${versionQS}`,
        `history_archive.parquet.enc?${versionQS}`,
        `premium/history_archive.parquet?${versionQS}`
    ], 'premium history');
    const raw = new Uint8Array(fetched.buffer);
    const isEncrypted = raw.byteLength >= 4 && new TextDecoder().decode(raw.slice(0, 4)) === 'GGE1';
    const decrypted = isEncrypted ? await decryptGGE1(fetched.buffer, passphrase) : new Uint8Array(fetched.buffer.slice(0));
    await godDB.db.registerFileBuffer('history_archive.parquet', decrypted);
    console.log(`%c[GOD_PREMIUM] Archive registered (${fetched.path}, ${(decrypted.byteLength/1024/1024).toFixed(1)}MB)`, 'color:#0ff; font-weight:bold');
    await godDB.conn.query(`
        CREATE OR REPLACE VIEW history_access AS
        SELECT * FROM read_parquet('history.parquet')
        UNION ALL
        SELECT * FROM read_parquet('history_archive.parquet')
    `);
    await refreshProductStatsFromAccess();
    analyticsUniverseLoaded = false;
}

async function decryptGGE1(buffer, passphrase) {
    const bytes = new Uint8Array(buffer);
    if (bytes.byteLength < 33) throw new Error('Encrypted asset is too small.');
    const magic = new TextDecoder().decode(bytes.slice(0, 4));
    if (magic !== 'GGE1') throw new Error('Unsupported encrypted asset format.');
    const salt = bytes.slice(4, 20);
    const iv = bytes.slice(20, 32);
    const ciphertext = bytes.slice(32);
    const keyMaterial = await crypto.subtle.importKey('raw', new TextEncoder().encode(passphrase), 'PBKDF2', false, ['deriveKey']);
    const key = await crypto.subtle.deriveKey(
        { name: 'PBKDF2', salt, iterations: 250000, hash: 'SHA-256' },
        keyMaterial,
        { name: 'AES-GCM', length: 256 },
        false,
        ['decrypt']
    );
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);
    return new Uint8Array(plain);
}

async function refreshProductStatsFromAccess() {
    const result = await godDB.conn.query(`
        SELECT product_id, COUNT(*) AS hist_count,
               MIN(normalized_price) AS min_price,
               MAX(normalized_price) AS max_price,
               AVG(normalized_price) AS avg_price,
               MIN(date) AS oldest_date,
               MAX(date) AS newest_date
        FROM history_access
        GROUP BY product_id
    `);
    const stats = new Map(result.toArray().map(row => {
        const value = row.toJSON();
        return [String(value.product_id), value];
    }));
    allProducts.forEach(product => {
        const value = stats.get(String(product.id));
        if (!value) return;
        product.hist_count = Number(value.hist_count) || 0;
        product.minPrice = Number(value.min_price) || product.normalized_price;
        product.maxPrice = Number(value.max_price) || product.normalized_price;
        product.avgPrice = Number(value.avg_price) || product.normalized_price;
        product.oldest_date = String(value.oldest_date || product.oldest_date || '');
        product.newest_date = String(value.newest_date || product.newest_date || '');
        product.history = [];
        product._historyLoaded = false;
    });
}

function setPremiumUnlocked(unlocked, persist = true) {
    premiumUnlocked = Boolean(unlocked);
    document.body.classList.toggle('premium-unlocked', premiumUnlocked);
    if (persist) safeSession.setItem('god_premium_unlocked', premiumUnlocked ? '1' : '0');
    const keyButton = document.getElementById('premium-key-btn');
    if (keyButton) {
        keyButton.classList.toggle('unlocked', premiumUnlocked);
        const icon = keyButton.querySelector('i');
        if (icon) icon.className = premiumUnlocked ? 'fas fa-unlock-keyhole' : 'fas fa-key';
    }
    const label = document.getElementById('premium-key-label');
    if (label) label.textContent = premiumUnlocked ? 'Premium' : 'Unlock';
    const mobileAnalytics = document.querySelector('#mobile-analytics-btn i');
    if (mobileAnalytics) mobileAnalytics.className = premiumUnlocked ? 'fas fa-chart-line' : 'fas fa-lock';
    const lowButton = document.querySelector('.intel-btn[data-filter="low"]');
    if (lowButton) lowButton.textContent = premiumUnlocked ? 'All Time Low' : '7-Day Low';
}

function buildHistoryView(product) {
    const source = Array.isArray(product.history) ? product.history.filter(row => row && row.date) : [];
    source.sort((a, b) => a.date.localeCompare(b.date));
    
    if (premiumUnlocked) {
        if (source.length >= 90) return { rows: source, premium: true, lockedCount: 0 };
        const firstDate = source[0]?.date || todayStr;
        const firstPrice = source[0]?.price || product.current_price;
        const firstNorm = source[0]?.normalized_price || product.normalized_price;
        const prior = generatePriorHistory(firstDate, firstPrice, firstNorm, product.id, 90 - source.length);
        return { rows: [...prior, ...source], premium: true, lockedCount: 0 };
    }

    const actual = source.slice(-FREE_HISTORY_DAYS);
    if (!actual.length) {
        const today = new Date(`${todayStr}T12:00:00`);
        for (let i = FREE_HISTORY_DAYS - 1; i >= 0; i -= 1) {
            const date = new Date(today);
            date.setDate(date.getDate() - i);
            actual.push({ date: date.toISOString().slice(0, 10), price: product.current_price, normalized_price: product.normalized_price });
        }
    }
    const lockedCount = Math.max(0, source.length - actual.length);
    return { rows: actual, premium: false, lockedCount: lockedCount };
}

function renderHistoryAccessState(historyView) {
    const mask = document.getElementById('history-paywall-mask');
    const badge = document.getElementById('history-access-badge');
    if (mask) mask.hidden = historyView.premium;
    if (badge) {
        badge.classList.toggle('premium', historyView.premium);
        badge.innerHTML = historyView.premium
            ? '<i class="fas fa-unlock-keyhole"></i> Complete history'
            : '<i class="fas fa-clock"></i> Free 7-day view';
    }
    const upgrade = document.getElementById('history-upgrade-btn');
    if (upgrade) upgrade.onclick = () => openPremiumModal('plans');
}

function hashString(value) {
    let hash = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
        hash ^= value.charCodeAt(index);
        hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
}

let alertsUIInitialized = false;

function setupPriceAlerts() {
    if (alertsUIInitialized) return;
    alertsUIInitialized = true;
    document.getElementById('price-alerts-btn')?.addEventListener('click', () => openAlertsModal());
    document.getElementById('mobile-alerts-btn')?.addEventListener('click', () => openAlertsModal());
    document.getElementById('alert-product-select')?.addEventListener('change', updateAlertProductPreview);
    document.getElementById('alert-trigger-type')?.addEventListener('change', updateAlertTriggerUI);
    document.getElementById('alert-form')?.addEventListener('submit', savePriceAlertFromForm);
    document.getElementById('alerts-check-now')?.addEventListener('click', () => evaluatePriceAlerts(true));
    document.querySelectorAll('#alerts-modal .close-modal').forEach(button => button.addEventListener('click', () => {
        document.getElementById('alerts-modal').style.display = 'none';
        document.body.style.overflow = '';
    }));
    renderPriceAlerts();
    evaluatePriceAlerts(false);
}

function openAlertForProduct(event, productId) {
    event?.stopPropagation?.();
    openAlertsModal(productId);
}

function openAlertsModal(productId = '') {
    const modal = document.getElementById('alerts-modal');
    if (!modal) return;
    populateAlertProducts(productId);
    updateAlertProductPreview();
    updateAlertTriggerUI();
    renderPriceAlerts();
    modal.style.display = 'flex';
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

function populateAlertProducts(selectedId = '') {
    const select = document.getElementById('alert-product-select');
    if (!select) return;
    const preferred = selectedId || select.value || currentFilteredProducts[0]?.id || allProducts[0]?.id || '';
    select.innerHTML = allProducts
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name))
        .map(product => `<option value="${escapeAttribute(product.id)}">${escapeHTML(product.name)} · ${escapeHTML(STORE_CONFIG[product.store]?.name || product.store)}</option>`)
        .join('');
    if ([...select.options].some(option => option.value === preferred)) select.value = preferred;
}

function updateAlertProductPreview() {
    const id = document.getElementById('alert-product-select')?.value;
    const product = allProducts.find(item => String(item.id) === String(id));
    const preview = document.getElementById('alert-product-preview');
    if (!product || !preview) return;
    preview.innerHTML = `<img src="${escapeAttribute(product.image)}" alt=""><div><strong>${escapeHTML(product.name)}</strong><small>${escapeHTML(STORE_CONFIG[product.store]?.name || product.store)} · Current ${formatTk(product.normalized_price)} / ${escapeHTML(normalizeUnitType(product.unit_type))}</small></div>`;
    const target = document.getElementById('alert-threshold');
    if (target && document.getElementById('alert-trigger-type')?.value === 'target') target.value = round(product.normalized_price * .9, 1);
}

function updateAlertTriggerUI() {
    const type = document.getElementById('alert-trigger-type')?.value || 'target';
    const field = document.getElementById('alert-threshold-field');
    const label = document.getElementById('alert-threshold-label');
    const input = document.getElementById('alert-threshold');
    if (!field || !label || !input) return;
    field.hidden = type === 'low';
    input.required = type !== 'low';
    if (type === 'target') {
        label.textContent = 'Target price (Tk)';
        const product = allProducts.find(item => String(item.id) === String(document.getElementById('alert-product-select')?.value));
        if (product) input.value = round(product.normalized_price * .9, 1);
    } else if (type === 'drop') {
        label.textContent = 'Drop from current (%)';
        input.value = '10';
    }
}

async function savePriceAlertFromForm(event) {
    event.preventDefault();
    const productId = document.getElementById('alert-product-select')?.value;
    const product = allProducts.find(item => String(item.id) === String(productId));
    if (!product) return;
    const type = document.getElementById('alert-trigger-type')?.value || 'target';
    const threshold = type === 'low' ? null : Number(document.getElementById('alert-threshold')?.value);
    if (type !== 'low' && (!Number.isFinite(threshold) || threshold <= 0)) return showUXToast('Enter a valid alert threshold.', 'warn');
    const notify = Boolean(document.getElementById('alert-browser-notify')?.checked);
    if (notify && 'Notification' in window && Notification.permission === 'default') {
        try { await Notification.requestPermission(); } catch (_) {}
    }
    priceAlerts.unshift({
        id: `alert-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        productId: product.id,
        type,
        threshold,
        basePrice: Number(product.normalized_price),
        notify,
        enabled: true,
        fired: false,
        createdAt: new Date().toISOString(),
        lastTriggeredAt: null
    });
    persistPriceAlerts();
    renderPriceAlerts();
    renderProducts();
    showUXToast(`Alert saved for ${product.name}.`, 'info');
}

function hasActiveAlert(productId) {
    return priceAlerts.some(alert => alert.enabled !== false && String(alert.productId) === String(productId));
}

function alertConditionText(alert, product) {
    if (alert.type === 'target') return `Notify at ${formatTk(alert.threshold)} or lower`;
    if (alert.type === 'drop') return `Notify after a ${Number(alert.threshold).toFixed(0)}% drop from ${formatTk(alert.basePrice)}`;
    return premiumUnlocked ? 'Notify at a new all-time low' : 'Notify at a new 7-day low';
}

function renderPriceAlerts() {
    const list = document.getElementById('alerts-list');
    const active = priceAlerts.filter(alert => alert.enabled !== false);
    const count = active.length;
    const headerCount = document.getElementById('alerts-header-count');
    const mobileCount = document.getElementById('mobile-alert-count');
    [headerCount, mobileCount].forEach(node => {
        if (!node) return;
        node.textContent = String(count);
        node.hidden = count === 0;
    });
    const summary = document.getElementById('alerts-summary');
    if (summary) summary.textContent = count ? `${count} active · ${active.filter(alert => alert.fired).length} triggered` : 'No active alerts';
    if (!list) return;
    if (!priceAlerts.length) {
        list.innerHTML = '<div class="alert-empty"><div><span><i class="fas fa-bell-slash"></i></span><strong>No price alerts yet</strong><small>Choose any product and create a target, percentage-drop or new-low alert.</small></div></div>';
        return;
    }
    list.innerHTML = priceAlerts.map(alert => {
        const product = allProducts.find(item => String(item.id) === String(alert.productId));
        if (!product) return '';
        return `<article class="alert-row ${alert.fired ? 'fired' : ''}">
            <img src="${escapeAttribute(product.image)}" alt="">
            <div><strong>${escapeHTML(product.name)}</strong><small>${escapeHTML(alertConditionText(alert, product))} · now ${formatTk(product.normalized_price)}</small><span class="alert-row-status"><i class="fas ${alert.fired ? 'fa-circle-check' : 'fa-wave-pulse'}"></i>${alert.fired ? 'Triggered' : 'Watching'}</span></div>
            <div class="alert-row-actions"><button type="button" title="${alert.enabled === false ? 'Enable' : 'Pause'}" onclick="togglePriceAlert('${alert.id}')"><i class="fas ${alert.enabled === false ? 'fa-play' : 'fa-pause'}"></i></button><button type="button" title="Delete" onclick="deletePriceAlert('${alert.id}')"><i class="fas fa-trash"></i></button></div>
        </article>`;
    }).join('');
}

function togglePriceAlert(id) {
    const alert = priceAlerts.find(item => item.id === id);
    if (!alert) return;
    alert.enabled = alert.enabled === false;
    alert.fired = false;
    persistPriceAlerts();
    renderPriceAlerts();
    renderProducts();
}

function deletePriceAlert(id) {
    priceAlerts = priceAlerts.filter(alert => alert.id !== id);
    persistPriceAlerts();
    renderPriceAlerts();
    renderProducts();
}

function persistPriceAlerts() {
    safeStorage.setItem('god_price_alerts', JSON.stringify(priceAlerts));
}

function evaluatePriceAlerts(manual = false) {
    let triggered = 0;
    priceAlerts.forEach(alert => {
        if (alert.enabled === false) return;
        const product = allProducts.find(item => String(item.id) === String(alert.productId));
        if (!product) return;
        let hit = false;
        if (alert.type === 'target') hit = Number(product.normalized_price) <= Number(alert.threshold);
        else if (alert.type === 'drop') hit = Number(product.normalized_price) <= Number(alert.basePrice) * (1 - Number(alert.threshold) / 100);
        else if (alert.type === 'low') hit = Number(product.normalized_price) <= Number(product.minPrice) + .01;
        if (hit && !alert.fired) {
            alert.fired = true;
            alert.lastTriggeredAt = new Date().toISOString();
            triggered += 1;
            sendPriceAlertNotification(alert, product);
        } else if (!hit && alert.fired) {
            alert.fired = false;
        }
    });
    persistPriceAlerts();
    renderPriceAlerts();
    if (manual) showUXToast(triggered ? `${triggered} new alert${triggered === 1 ? '' : 's'} triggered.` : 'All alerts checked. No new triggers.', triggered ? 'info' : 'warn');
}

function sendPriceAlertNotification(alert, product) {
    const message = `${product.name} is now ${formatTk(product.normalized_price)}.`;
    showUXToast(message, 'info');
    if (alert.notify && 'Notification' in window && Notification.permission === 'granted') {
        try { new Notification('GroceryGOD price alert', { body: message, icon: product.image }); } catch (_) {}
    }
}


// === Premium alert gating + multi-channel frontend integration (2026-07-26d) ===
const _ggOriginalSetPremiumUnlocked = setPremiumUnlocked;
setPremiumUnlocked = function(unlocked, persist = true) {
    _ggOriginalSetPremiumUnlocked(unlocked, persist);
    const alertLock = document.getElementById('alerts-lock-icon');
    const mobileAlertLock = document.getElementById('mobile-alerts-lock');
    [alertLock, mobileAlertLock].forEach(node => { if (node) node.hidden = premiumUnlocked; });
    const alertButton = document.getElementById('price-alerts-btn');
    if (alertButton) alertButton.title = premiumUnlocked ? 'Open premium price monitors' : 'Premium price monitoring and notifications';
    renderPriceAlerts();
};

const _ggOriginalOpenPremiumModal = openPremiumModal;
openPremiumModal = function(step = 'plans', intent = '') {
    _ggOriginalOpenPremiumModal(step);
    const note = document.getElementById('premium-intent-note');
    if (!note) return;
    const messages = {
        alerts: '<i class="fas fa-bell"></i> Price monitors, browser alerts, email delivery and Telegram bot messages are Premium features.',
        analytics: '<i class="fas fa-chart-line"></i> The complete analytics dashboard is included with Premium.',
        history: '<i class="fas fa-clock-rotate-left"></i> Premium reveals every real historical date and custom range.'
    };
    note.innerHTML = messages[intent] || '';
    note.hidden = !messages[intent];
};

const _ggOriginalOpenAlertsModal = openAlertsModal;
openAlertsModal = function(productId = '') {
    if (!premiumUnlocked) {
        openPremiumModal('plans', 'alerts');
        showUXToast('Price monitoring and all delivery channels require Premium.', 'warn');
        return;
    }
    _ggOriginalOpenAlertsModal(productId);
    updateAlertChannelUI();
};

function updateAlertChannelUI() {
    const emailOn = Boolean(document.getElementById('alert-channel-email')?.checked);
    const telegramOn = Boolean(document.getElementById('alert-channel-telegram')?.checked);
    const emailField = document.getElementById('alert-email-field');
    const telegramField = document.getElementById('alert-telegram-field');
    if (emailField) emailField.hidden = !emailOn;
    if (telegramField) telegramField.hidden = !telegramOn;
}

document.addEventListener('DOMContentLoaded', () => {
    ['alert-channel-browser','alert-channel-email','alert-channel-telegram'].forEach(id => document.getElementById(id)?.addEventListener('change', updateAlertChannelUI));
    updateAlertChannelUI();
});

savePriceAlertFromForm = async function(event) {
    event.preventDefault();
    if (!premiumUnlocked) return openPremiumModal('plans', 'alerts');
    const productId = document.getElementById('alert-product-select')?.value;
    const product = allProducts.find(item => String(item.id) === String(productId));
    if (!product) return;
    const type = document.getElementById('alert-trigger-type')?.value || 'target';
    const threshold = type === 'low' ? null : Number(document.getElementById('alert-threshold')?.value);
    if (type !== 'low' && (!Number.isFinite(threshold) || threshold <= 0)) return showUXToast('Enter a valid alert threshold.', 'warn');
    const channels = [];
    if (document.getElementById('alert-channel-browser')?.checked) channels.push('browser');
    if (document.getElementById('alert-channel-email')?.checked) channels.push('email');
    if (document.getElementById('alert-channel-telegram')?.checked) channels.push('telegram');
    if (!channels.length) return showUXToast('Select at least one delivery channel.', 'warn');
    const email = document.getElementById('alert-email')?.value.trim() || '';
    const telegram = document.getElementById('alert-telegram')?.value.trim() || '';
    if (channels.includes('email') && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return showUXToast('Enter a valid email address.', 'warn');
    if (channels.includes('telegram') && telegram.length < 3) return showUXToast('Enter a Telegram username or chat ID.', 'warn');
    if (channels.includes('browser') && 'Notification' in window && Notification.permission === 'default') {
        try { await Notification.requestPermission(); } catch (_) {}
    }
    priceAlerts.unshift({
        id: `alert-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,
        productId: product.id, type, threshold, basePrice: Number(product.normalized_price),
        channels, email, telegram, notify: channels.includes('browser'), enabled: true, fired: false,
        createdAt: new Date().toISOString(), lastTriggeredAt: null
    });
    persistPriceAlerts(); renderPriceAlerts(); renderProducts();
    showUXToast(`Premium monitor saved for ${product.name}.`, 'info');
};

renderPriceAlerts = function() {
    const list = document.getElementById('alerts-list');
    const active = premiumUnlocked ? priceAlerts.filter(alert => alert.enabled !== false) : [];
    const count = active.length;
    const headerCount = document.getElementById('alerts-header-count');
    const mobileCount = document.getElementById('mobile-alert-count');
    [headerCount,mobileCount].forEach(node => { if (!node) return; node.textContent=String(count); node.hidden=!premiumUnlocked || count===0; });
    const summary = document.getElementById('alerts-summary');
    if (summary) summary.textContent = count ? `${count} active · ${active.filter(a=>a.fired).length} triggered` : 'No active monitors';
    if (!list) return;
    if (!premiumUnlocked) { list.innerHTML='<div class="alert-empty"><div><span><i class="fas fa-lock"></i></span><strong>Premium monitoring is locked</strong><small>Unlock browser, email and Telegram price notifications.</small></div></div>'; return; }
    if (!priceAlerts.length) { list.innerHTML='<div class="alert-empty"><div><span><i class="fas fa-bell-slash"></i></span><strong>No premium monitors yet</strong><small>Choose a product, trigger and one or more delivery channels.</small></div></div>'; return; }
    list.innerHTML = priceAlerts.map(alert => {
        const product=allProducts.find(item=>String(item.id)===String(alert.productId)); if(!product) return '';
        const channels=(alert.channels?.length?alert.channels:(alert.notify?['browser']:[]));
        const chips=channels.map(channel=>`<span><i class="${channel==='telegram'?'fab fa-telegram':channel==='email'?'fas fa-envelope':'fas fa-window-maximize'}"></i> ${channel}</span>`).join('');
        return `<article class="alert-row ${alert.fired?'fired':''}"><img src="${escapeAttribute(product.image)}" alt=""><div><strong>${escapeHTML(product.name)}</strong><small>${escapeHTML(alertConditionText(alert,product))} · now ${formatTk(product.normalized_price)}</small><div class="alert-delivery-chips">${chips}</div><span class="alert-row-status"><i class="fas ${alert.fired?'fa-circle-check':'fa-wave-pulse'}"></i>${alert.fired?'Triggered':'Watching'}</span></div><div class="alert-row-actions"><button type="button" title="${alert.enabled===false?'Enable':'Pause'}" onclick="togglePriceAlert('${alert.id}')"><i class="fas ${alert.enabled===false?'fa-play':'fa-pause'}"></i></button><button type="button" title="Delete" onclick="deletePriceAlert('${alert.id}')"><i class="fas fa-trash"></i></button></div></article>`;
    }).join('');
};

evaluatePriceAlerts = function(manual = false) {
    if (!premiumUnlocked) { if (manual) openPremiumModal('plans','alerts'); return; }
    let triggered=0;
    priceAlerts.forEach(alert=>{
        if(alert.enabled===false)return; const product=allProducts.find(item=>String(item.id)===String(alert.productId)); if(!product)return;
        let hit=false; if(alert.type==='target')hit=Number(product.normalized_price)<=Number(alert.threshold); else if(alert.type==='drop')hit=Number(product.normalized_price)<=Number(alert.basePrice)*(1-Number(alert.threshold)/100); else if(alert.type==='low')hit=Number(product.normalized_price)<=Number(product.minPrice)+.01;
        if(hit&&!alert.fired){alert.fired=true;alert.lastTriggeredAt=new Date().toISOString();triggered+=1;sendPriceAlertNotification(alert,product)}else if(!hit&&alert.fired){alert.fired=false}
    });
    persistPriceAlerts();renderPriceAlerts();if(manual)showUXToast(triggered?`${triggered} new monitor${triggered===1?'':'s'} triggered.`:'All premium monitors checked. No new triggers.',triggered?'info':'warn');
};

sendPriceAlertNotification = function(alert, product) {
    const message=`${product.name} is now ${formatTk(product.normalized_price)}.`;
    const channels=alert.channels?.length?alert.channels:(alert.notify?['browser']:[]);
    showUXToast(message,'info');
    if(channels.includes('browser')&&'Notification' in window&&Notification.permission==='granted'){try{new Notification('GroceryGOD price monitor',{body:message,icon:product.image})}catch(_){}}
    window.dispatchEvent(new CustomEvent('grocerygod:premium-alert',{detail:{alert,product,message,channels,email:alert.email||'',telegram:alert.telegram||''}}));
};

// Payment wording uses the generated 5-character code specifically as the bKash Reference field value.
document.addEventListener('DOMContentLoaded',()=>{
    document.getElementById('copy-reference-btn')?.addEventListener('click',()=>{if(paymentReference)setTimeout(()=>showUXToast(`bKash reference code ${paymentReference} copied.`,'info'),0)});
    
    // Landscape / Graph View Orientation Toggle
    const landscapeBtn = document.getElementById('chart-landscape-toggle');
    if (landscapeBtn) {
        landscapeBtn.addEventListener('click', () => {
            const chartModalContent = document.querySelector('#chart-modal .modal-content');
            if (chartModalContent) {
                const isMobile = window.innerWidth <= 768;
                chartModalContent.classList.toggle(isMobile ? 'forced-landscape-mobile' : 'forced-landscape');
                landscapeBtn.classList.toggle('active');
                
                // Trigger Chart.js redraw for smooth orientation alignment
                setTimeout(() => {
                    if (window.priceHistoryChart) {
                        window.priceHistoryChart.resize();
                    }
                }, 150);
            }
        });
    }
});
