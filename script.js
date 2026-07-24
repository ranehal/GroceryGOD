// GroceryGOD Core Engine - Unified Market Intelligence
let allProducts = [];
let metadata = {};
let godDB = null; // persistent DuckDB connection for on-demand queries
const ASSET_VERSION = window.GOD_ASSET_VERSION || '20260723b';
let favorites = JSON.parse(localStorage.getItem('god_favorites') || '[]');
let selectedForComparison = JSON.parse(localStorage.getItem('god_comparison') || '[]');
let customGroups = JSON.parse(localStorage.getItem('god_custom_groups') || '{}');
let shoppingLists = JSON.parse(localStorage.getItem('god_shopping_lists') || '{}');

let detailChart = null;
let compareChart = null;
let currentDetailProductIndex = -1;
let currentFilteredProducts = [];

let searchQuery = '';
let activeUnitFilters = new Set(['kg', 'liter', 'piece']);
let sortOption = 'unit_price_asc';
let activeIntelFilter = 'low';
let compareModeActive = false;
let showFavoritesOnly = false;
let showNewOnly = false;
let activeShopFilters = new Set(['shwapno']);
let activeCategories = new Set();
window.loadedStores = new Set(['shwapno']);

let greatDealThreshold = 0.85;
let goodBuyThreshold = 0.95;
let newDaysThreshold = parseInt(localStorage.getItem('god_new_days') || '7');
let customOverrides = JSON.parse(localStorage.getItem('god_custom_overrides') || '{}');
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
    shotejbazar: { color: '#9c27b0', name: 'ShotejBazar' }
};

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
    const [pBuf, hBuf] = await Promise.all([
        fetch('products.parquet').then(r => { log(`products.parquet: ${r.status} ${(r.headers.get('content-length')||'?')} bytes`); return r.arrayBuffer(); }),
        fetch('history.parquet').then(r => { log(`history.parquet: ${r.status} ${(r.headers.get('content-length')||'?')} bytes`); return r.arrayBuffer(); })
    ]);
    log(`Fetched parquet in ${((performance.now()-t1)/1000).toFixed(1)}s — products: ${(pBuf.byteLength/1024/1024).toFixed(1)}MB, history: ${(hBuf.byteLength/1024/1024).toFixed(1)}MB`);
    await db.registerFileBuffer('products.parquet', new Uint8Array(pBuf));
    await db.registerFileBuffer('history.parquet', new Uint8Array(hBuf));
    log('Files registered in virtual FS');

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
        LEFT JOIN read_parquet('history.parquet') h ON p.id = h.product_id
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
    metadata.stores = {};
    const stores = ['shwapno','chaldal','meenabazar','othoba','metromart','unimart','shotejbazar'];
    stores.forEach(s => {
        const manifest = window[s + 'Manifest'];
        if (manifest && manifest.metadata) metadata.stores[s] = manifest.metadata;
    });

    const elapsed = ((performance.now()-t0)/1000).toFixed(1);
    log(`DONE — ${allProducts.length} products loaded in ${elapsed}s`);
}

async function loadProductHistory(productId) {
    if (!godDB) return [];
    const result = await godDB.conn.query(`
        SELECT date, price, normalized_price 
        FROM read_parquet('history.parquet') 
        WHERE product_id = '${productId.replace(/'/g, "''")}'
        ORDER BY date ASC
    `);
    return result.toArray().map(r => {
        const h = r.toJSON();
        return { date: h.date, price: Number(h.price), normalized_price: Number(h.normalized_price) };
    });
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
            FROM read_parquet('history.parquet')
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

function processData() {
    let latestDataDate = null;
    allProducts.forEach(p => {
        if (p.newest_date && (!latestDataDate || p.newest_date > latestDataDate)) latestDataDate = p.newest_date;
    });
    todayStr = latestDataDate || dhakaTodayStr();
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
            const thresholdMs = newDaysThreshold * 24 * 60 * 60 * 1000;
            const oldestDate = toDhaka(new Date(p.oldest_date || p.first_seen));
            const ageOfOldest = today - oldestDate;
            if (ageOfOldest > thresholdMs) {
                p.isNew = false;
            }
        } else {
            p.isNew = true;
        }
    });
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
            if (cb.checked) {
                activeShopFilters.add(sid);
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
            }
            renderProducts(); updateStatsBar();
        };
        cb.onclick = (e) => e.stopPropagation(); 

        const catList = document.createElement('ul');
        catList.className = 'shop-categories';

        categories.forEach(cat => {
            const catProducts = shopProducts.filter(p => p.category === cat);
            const count = catProducts.length;
            const newCount = catProducts.filter(p => p.ageDays <= 7).length;

            const li = document.createElement('li');
            const isPinned = cat.includes('📌');
            li.className = `shop-cat-item ${activeCategories.has(sid + '_' + cat) ? 'active' : ''} ${isPinned ? 'pinned' : ''}`;
            const catId = sid + '_' + cat;
            li.innerHTML = `
                <div class="cat-row-content" style="display:flex; align-items:center; gap:12px; flex:1;">
                    <input type="checkbox" class="cat-checkbox" ${activeCategories.has(catId) ? 'checked' : ''}>
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
                if (catCb.checked) { activeCategories.add(catId); li.classList.add('active'); }
                else { activeCategories.delete(catId); li.classList.remove('active'); }
                renderProducts();
            };
            catCb.onclick = (e) => e.stopPropagation();
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

function saveGroups() { localStorage.setItem('god_custom_groups', JSON.stringify(customGroups)); }

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
        if (showNewOnly && !p.isNew) return false;
        if (searchQuery && !p.name.toLowerCase().includes(searchQuery) && !p.category.toLowerCase().includes(searchQuery)) return false;
        if (!activeUnitFilters.has(p.unit_type)) return false;
        if (activeIntelFilter === 'great') return p.normalized_price < (p.avgPrice * greatDealThreshold);
        if (activeIntelFilter === 'good') return p.normalized_price < (p.avgPrice * goodBuyThreshold);
        if (activeIntelFilter === 'wait') return p.normalized_price > (p.avgPrice * 1.05);
        if (activeIntelFilter === 'low') return p.hist_count >= 1 && p.maxPrice > p.minPrice && p.normalized_price <= (p.minPrice + 0.01);
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

    const frag = document.createDocumentFragment();
    currentFilteredProducts.slice(0, 250).forEach(p => frag.appendChild(createProductCard(p)));
    grid.appendChild(frag);
}

function createProductCard(p) {
    const card = document.createElement('div');
    const storeColor = STORE_CONFIG[p.store].color;
    card.className = 'p-item-sh ' + (selectedForComparison.includes(p.id) ? 'selected' : '');
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
        if (e.target.closest('.fav-btn')) return;
        if (compareModeActive) {
            if (selectedForComparison.includes(p.id)) {
                selectedForComparison = selectedForComparison.filter(x => x !== p.id);
                card.classList.remove('selected');
            } else if (selectedForComparison.length < 6) {
                selectedForComparison.push(p.id);
                card.classList.add('selected');
            }
            localStorage.setItem('god_comparison', JSON.stringify(selectedForComparison));
        } else {
            openDetailedChart(p);
        }
    };
    return card;
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
    localStorage.setItem('god_favorites', JSON.stringify(favorites));
    renderProducts();
}

function setupEventListeners() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const searchInput = document.getElementById('product-search');

    document.getElementById('sidebar-toggle').onclick = () => { sidebar.classList.add('visible'); overlay.classList.add('active'); };
    overlay.onclick = () => { sidebar.classList.remove('visible'); overlay.classList.remove('active'); };

    searchInput.oninput = (e) => {
        searchQuery = e.target.value.toLowerCase();
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

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal').forEach(m => {
                m.classList.add('hidden');
                m.style.display = 'none';
            });
            document.getElementById('search-suggestions').style.display = 'none';
        }
        if (document.getElementById('chart-modal').classList.contains('hidden') === false) {
            if (e.key === 'ArrowRight') cycleProduct(1);
            if (e.key === 'ArrowLeft') cycleProduct(-1);
            if (e.key === 'Escape') {
                closeModal();
            }
        }
    });

    document.getElementById('sort-options').onchange = (e) => { sortOption = e.target.value; renderProducts(); };
    
    document.getElementById('bookmark-cat-btn').onclick = () => {
        showFavoritesOnly = !showFavoritesOnly;
        document.getElementById('bookmark-cat-btn').classList.toggle('active', showFavoritesOnly);
        renderProducts();
    };

    const newOnlyCb = document.getElementById('new-only-checkbox');
    if (newOnlyCb) {
        newOnlyCb.onchange = (e) => {
            showNewOnly = e.target.checked;
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

    document.getElementById('compare-btn').onclick = () => {
        if (compareModeActive && selectedForComparison.length > 0) openCompareModal();
        compareModeActive = !compareModeActive;
        document.getElementById('compare-btn').classList.toggle('active', compareModeActive);
        renderProducts();
    };

    document.getElementById('cart-comp-btn').onclick = openCartModal;
    document.getElementById('reset-cart-btn').onclick = () => {
        if(confirm('Empty Cart?')) {
            favorites = []; localStorage.setItem('god_favorites', '[]');
            allProducts.forEach(p => p.isFavorite = false);
            openCartModal(); renderProducts();
        }
    };

    document.getElementById('save-current-list-btn').onclick = () => {
        if (favorites.length === 0) return alert("Cart is empty!");
        const name = prompt("Enter List name:");
        if (name) { shoppingLists[name] = [...favorites]; localStorage.setItem('god_shopping_lists', JSON.stringify(shoppingLists)); renderShoppingLists(); }
    };

    document.getElementById('compare-clear-all').onclick = () => {
        if(confirm('Clear staged Matrix?')) {
            selectedForComparison = []; localStorage.setItem('god_comparison', '[]');
            document.getElementById('compare-modal').style.display = 'none';
            renderProducts();
        }
    };

    const newDaysInput = document.getElementById('new-days-input');
    if (newDaysInput) {
        newDaysInput.value = newDaysThreshold;
        newDaysInput.onchange = (e) => {
            newDaysThreshold = parseInt(e.target.value) || 7;
            localStorage.setItem('god_new_days', newDaysThreshold);
            processData();
            renderProducts();
        };
    }

    document.querySelectorAll('.close-modal').forEach(btn => btn.onclick = () => btn.closest('.modal').style.display = 'none');

    let touchStartX = 0;
    let touchStartY = 0;
    const chartModal = document.getElementById('chart-modal');
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
                favorites = [...shoppingLists[name]]; localStorage.setItem('god_favorites', JSON.stringify(favorites));
                processData(); openCartModal(); renderProducts();
            }
        };
        const del = document.createElement('button');
        del.className = 'btn-icon danger'; del.style.padding = '5px 8px';
        del.innerHTML = '<i class="fas fa-trash"></i>';
        del.onclick = (e) => {
            e.stopPropagation();
            if(confirm('Delete list "' + name + '"?')) { delete shoppingLists[name]; localStorage.setItem('god_shopping_lists', JSON.stringify(shoppingLists)); renderShoppingLists(); }
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
        localStorage.setItem('god_favorites', JSON.stringify(favorites));
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
            scales: { y: { grid: { color: '#222' }, ticks: { color: '#ccc', font: { size: 11, weight: 'bold' } } }, x: { grid: { color: '#1a1a1a' }, ticks: { color: '#ccc', font: { size: 11, weight: 'bold' }, maxRotation: 45 } } },
            plugins: { legend: { labels: { color: '#fff', boxWidth: 10, font: { size: 10, weight: 'bold' } } } }
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
}

async function openDetailedChart(product) {
    currentDetailProductIndex = currentFilteredProducts.findIndex(p => p.id === product.id);
    const modal = document.getElementById('chart-modal');
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
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
        ? '<span style="color:var(--gold); font-weight:900;">ALL TIME LOW: ' + fmt(product.minPrice) + '</span>'
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
        <button class="btn-icon" onclick="closeModal()"><i class="fas fa-arrow-left"></i> Back</button>
        <div style="display:flex; gap:10px;">
            <button class="btn-icon" onclick="customizeItem('${product.id}')"><i class="fas fa-edit"></i> Customize Details</button>
            <button class="btn-icon" onclick="setNewThreshold()"><i class="fas fa-calendar-alt"></i> Set "New" Days (${newDaysThreshold})</button>
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
    const history = product.history || [];
    const rawDates = history.map(h => h.date);
    const labels = formatChartDates(rawDates);
    if (detailChart) detailChart.destroy();
    detailChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                { label: 'Unit Price', data: history.map(h => h.normalized_price), borderColor: store.color, backgroundColor: store.color + '22', fill: true, tension: 0.3, yAxisID: 'y', pointRadius: 2, pointHoverRadius: 5 },
                { label: 'Actual Price', data: history.map(h => h.price), borderColor: '#ffffff', borderDash: [5, 5], fill: false, tension: 0, yAxisID: 'y1', pointRadius: 1, pointHoverRadius: 4 }
            ]
        },
        options: { 
            responsive: true, maintainAspectRatio: false,
            scales: {
                y: { position: 'left', title: { display: true, text: 'Unit Price', color: store.color, font: { weight: 'bold' } }, grid: { color: '#222' }, ticks: { color: store.color, font: { size: 11, weight: 'bold' } } },
                y1: { position: 'right', title: { display: true, text: 'Actual Price', color: '#fff', font: { weight: 'bold' } }, grid: { display: false }, ticks: { color: '#fff', font: { size: 11, weight: 'bold' } } },
                x: { ticks: { color: '#ccc', font: { size: 11, weight: 'bold' }, maxRotation: 45 }, grid: { color: '#1a1a1a' } }
            },
            plugins: { legend: { labels: { color: '#fff', font: { size: 12, weight: 'bold' } } } }
        }
    });
}

function updateStoreStats() {
    const sidebarStats = document.getElementById('store-stats-sidebar');
    if (!sidebarStats) return;
    
    const stores = ['shwapno', 'chaldal', 'meenabazar', 'othoba', 'metromart', 'unimart', 'shotejbazar'];
    stores.forEach(s => {
        if (!metadata.stores) metadata.stores = {};
        if (!metadata.stores[s]) {
            const manifest = window[s + 'Manifest'];
            if (manifest && manifest.metadata) {
                metadata.stores[s] = manifest.metadata;
            }
        }
    });

    let html = '<div style="font-size: 0.65rem; color: var(--gold); margin-bottom: 12px; font-weight: 800; letter-spacing:1px; border-bottom:1px solid #222; padding-bottom:5px;">GODDATA UPLINK STATUS</div>';
    
    const sortedStores = Object.entries(metadata.stores).sort((a, b) => a[0].localeCompare(b[0]));
    
    sortedStores.forEach(([store, data]) => {
        const config = STORE_CONFIG[store] || { color: '#888', name: store };
        html += `
        <div class="legend-item" style="display:flex; flex-direction:column; margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; font-weight:800; font-size:0.75rem;">
                <span style="color:${config.color}">${config.name.toUpperCase()}</span>
                <span style="color:#eee;">${data.total} units</span>
            </div>
            <div style="font-size:0.6rem; opacity:0.6; color:#888;">Range: ${data.date_range || 'N/A'}</div>
        </div>`;
    });
    sidebarStats.innerHTML = html;
}

window.customizeItem = (id) => {
    const p = allProducts.find(x => x.id === id);
    if (!p) return;
    const name = prompt("Customize Name:", p.name) || p.name;
    const cat = prompt("Customize Category:", p.category) || p.category;
    const unit = prompt("Customize Pack/Unit:", p.unit) || p.unit;
    const unitType = prompt("Customize Unit Type (kg/liter/piece):", p.unit_type) || p.unit_type;
    
    customOverrides[id] = { name, category: cat, unit, unit_type: unitType };
    localStorage.setItem('god_custom_overrides', JSON.stringify(customOverrides));
    processData();
    renderProducts();
    openDetailedChart(allProducts.find(x => x.id === id));
};

window.setNewThreshold = () => {
    const val = prompt("Days to consider item as 'NEW':", newDaysThreshold);
    if (val !== null) {
        newDaysThreshold = parseInt(val);
        localStorage.setItem('god_new_days', newDaysThreshold);
        processData();
        renderProducts();
        alert('New items threshold set to ' + newDaysThreshold + ' days.');
    }
};
