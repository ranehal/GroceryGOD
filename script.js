// GroceryGOD Core Engine - Unified Market Intelligence
let allProducts = [];
let metadata = {};
let favorites = JSON.parse(localStorage.getItem('god_favorites') || '[]');
let selectedForComparison = JSON.parse(localStorage.getItem('god_comparison') || '[]');
let customGroups = JSON.parse(localStorage.getItem('god_custom_groups') || '{}');
let shoppingLists = JSON.parse(localStorage.getItem('god_shopping_lists') || '{}');

let detailChart = null;
let compareChart = null;

let searchQuery = '';
let activeUnitFilters = new Set(['kg', 'liter', 'piece']);
let sortOption = 'name_asc';
let activeIntelFilter = 'all';
let compareModeActive = false;
let showFavoritesOnly = false;
let activeShopFilters = new Set(['shwapno', 'chaldal', 'meenabazar', 'dailyshopping']);
let activeCategories = new Set(); // Multi-check support

let greatDealThreshold = 0.85;
let goodBuyThreshold = 0.95;

const STORE_CONFIG = {
    shwapno: { color: '#ff4081', name: 'Shwapno' },
    chaldal: { color: '#007aff', name: 'Chaldal' },
    meenabazar: { color: '#34c759', name: 'Meena Bazar' },
    dailyshopping: { color: '#ff9f0a', name: 'Daily Shopping' }
};

// Helper: Format price (no .0 if integer, remove ৳ symbol)
function fmt(num) {
    if (num === null || num === undefined) return '0';
    return Number.isInteger(num) ? num.toString() : num.toFixed(1).replace(/\.0$/, '');
}

document.addEventListener('DOMContentLoaded', async () => {
    document.title = "GroceryGOD";
    showLoading(true, 'Initializing GODdata Matrix...');
    
    // Merge individual store data
    const storeKeys = ['shwapno', 'chaldal', 'meenabazar', 'dailyshopping'];
    storeKeys.forEach(key => {
        const globalData = window[key + 'Data'];
        if (globalData && globalData.products) {
            allProducts.push(...Object.values(globalData.products));
            if (globalData.metadata) {
                metadata.stores = metadata.stores || {};
                metadata.stores[key] = globalData.metadata;
            }
        }
    });

    processData();
    renderSidebar();
    renderProducts();
    setupEventListeners();
    updateStoreStats();
    updateStatsBar();
    showLoading(false);
});

function showLoading(show, message = 'Loading...') {
    const loader = document.getElementById('loading-spinner');
    if (loader) {
        loader.classList.toggle('active', show);
        const text = loader.querySelector('span');
        if (text) text.textContent = message;
    }
}

function processData() {
    allProducts.forEach(p => {
        const history = p.history || [];
        const prices = history.map(h => h.normalized_price || h.price);
        p.avgPrice = prices.length > 0 ? prices.reduce((a, b) => a + b, 0) / prices.length : p.normalized_price;
        p.minPrice = prices.length > 0 ? Math.min(...prices) : p.normalized_price;
        p.maxPrice = prices.length > 0 ? Math.max(...prices) : p.normalized_price;
        p.hasPriceHistory = prices.length > 1 && (p.maxPrice > p.minPrice);
        
        p.priceChangePercent = 0;
        if (history.length >= 2) {
            const curr = history[history.length - 1].normalized_price || history[history.length - 1].price;
            const prev = history[history.length - 2].normalized_price || history[history.length - 2].price;
            p.priceChangePercent = prev > 0 ? ((curr - prev) / prev * 100) : 0;
        }
        p.isFavorite = favorites.includes(p.id);
    });
}

function renderSidebar() {
    const list = document.getElementById('category-list');
    if (!list) return;
    list.innerHTML = '';
    
    // --- Matrix Groups ---
    const groupHeader = document.createElement('div');
    groupHeader.className = 'group-header';
    groupHeader.innerHTML = `<span><i class="fas fa-folder-plus"></i> Matrix Groups</span> <button id="add-group-btn" class="btn-icon"><i class="fas fa-plus"></i></button>`;
    list.appendChild(groupHeader);

    const groupList = document.createElement('div');
    Object.keys(customGroups).forEach(gName => {
        const item = document.createElement('div');
        item.className = 'group-item';
        item.innerHTML = `<span>${gName}</span> <i class="fas fa-trash delete-group-btn" style="color:var(--danger); font-size:0.7rem; cursor:pointer;"></i>`;
        item.onclick = () => filterByGroup(gName);
        item.querySelector('.delete-group-btn').onclick = (e) => {
            e.stopPropagation();
            if(confirm(`Delete matrix group "${gName}"?`)) { delete customGroups[gName]; saveGroups(); renderSidebar(); }
        };
        groupList.appendChild(item);
    });
    list.appendChild(groupList);

    // --- Market Uplinks ---
    const shopHeading = document.createElement('div');
    shopHeading.className = 'category-group-header';
    shopHeading.innerHTML = `<span><i class="fas fa-microchip"></i> Market Uplinks</span>`;
    list.appendChild(shopHeading);

    Object.keys(STORE_CONFIG).forEach(sid => {
        const shopProducts = allProducts.filter(p => p.store === sid);
        const categories = [...new Set(shopProducts.map(p => p.category))].sort();
        const group = document.createElement('div'); group.className = 'shop-group';
        const header = document.createElement('div');
        header.className = `shop-header ${activeShopFilters.has(sid) ? 'active' : ''}`;
        header.innerHTML = `
            <div class="shop-toggle-container">
                <input type="checkbox" class="shop-checkbox" ${activeShopFilters.has(sid) ? 'checked' : ''}>
                <span style="color:${STORE_CONFIG[sid].color}">${STORE_CONFIG[sid].name}</span>
            </div>
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="opacity:0.4; font-size:0.6rem;">${shopProducts.length}</span>
                <i class="fas fa-chevron-down toggle-icon" style="font-size:0.6rem;"></i>
            </div>
        `;
        
        const cb = header.querySelector('.shop-checkbox');
        cb.onclick = (e) => {
            e.stopPropagation();
            if (cb.checked) activeShopFilters.add(sid);
            else activeShopFilters.delete(sid);
            renderProducts(); updateStatsBar();
        };

        const catList = document.createElement('ul');
        catList.className = 'shop-categories';
        header.onclick = (e) => {
            if (e.target === cb) return;
            const isOpen = catList.classList.contains('active');
            document.querySelectorAll('.shop-categories').forEach(el => el.classList.remove('active'));
            if (!isOpen) catList.classList.add('active');
        };

        categories.forEach(cat => {
            const count = shopProducts.filter(p => p.category === cat).length;
            const li = document.createElement('li');
            li.className = 'shop-cat-item';
            const catId = `${sid}_${cat}`;
            li.innerHTML = `
                <input type="checkbox" class="cat-checkbox" ${activeCategories.has(catId) ? 'checked' : ''}>
                <span>${cat}</span> 
                <span style="opacity:0.3; font-size:0.6rem; margin-left:auto;">${count}</span>
            `;
            const catCb = li.querySelector('.cat-checkbox');
            li.onclick = () => {
                catCb.checked = !catCb.checked;
                if (catCb.checked) activeCategories.add(catId);
                else activeCategories.delete(catId);
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
    document.getElementById('current-view-title').innerText = `Group: ${name}`;
    const filtered = allProducts.filter(p => ids.includes(p.id));
    filtered.forEach(p => grid.appendChild(createProductCard(p)));
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
    
    let filtered = allProducts.filter(p => {
        if (!activeShopFilters.has(p.store)) return false;
        if (activeCategories.size > 0 && !activeCategories.has(`${p.store}_${p.category}`)) return false;
        if (showFavoritesOnly && !p.isFavorite) return false;
        if (searchQuery && !p.name.toLowerCase().includes(searchQuery) && !p.category.toLowerCase().includes(searchQuery)) return false;
        if (!activeUnitFilters.has(p.unit_type)) return false;
        if (activeIntelFilter === 'great') return p.normalized_price < (p.avgPrice * greatDealThreshold);
        if (activeIntelFilter === 'good') return p.normalized_price < (p.avgPrice * goodBuyThreshold);
        if (activeIntelFilter === 'wait') return p.normalized_price > (p.avgPrice * 1.05);
        if (activeIntelFilter === 'low') return p.hasPriceHistory && p.normalized_price <= (p.minPrice + 0.01);
        return true;
    });

    filtered.sort((a, b) => {
        if (sortOption === 'name_asc') return a.name.localeCompare(b.name);
        if (sortOption === 'unit_price_asc') return a.normalized_price - b.normalized_price;
        if (sortOption === 'unit_price_desc') return b.normalized_price - a.normalized_price;
        if (sortOption === 'actual_price_asc') return a.current_price - b.current_price;
        if (sortOption === 'drop_desc') return a.priceChangePercent - b.priceChangePercent;
        return 0;
    });

    const frag = document.createDocumentFragment();
    filtered.slice(0, 250).forEach(p => frag.appendChild(createProductCard(p)));
    grid.appendChild(frag);
}

function createProductCard(p) {
    const card = document.createElement('div');
    const storeColor = STORE_CONFIG[p.store].color;
    card.className = `p-item-sh ${selectedForComparison.includes(p.id) ? 'selected' : ''}`;
    card.style.setProperty('--store-color', storeColor);
    
    const trend = p.priceChangePercent !== 0 ? `
        <div style="position:absolute; top:35px; left:8px; font-size:0.55rem; font-weight:900; background:rgba(0,0,0,0.85); padding:1px 5px; border-radius:3px; color:${p.priceChangePercent < 0 ? 'var(--accent-secondary)' : 'var(--danger)'}; z-index:11;">
            ${p.priceChangePercent > 0 ? '▲' : '▼'}${Math.abs(p.priceChangePercent).toFixed(0)}%
        </div>
    ` : '';

    card.innerHTML = `
        <div class="store-badge" style="background:${storeColor}">${p.store}</div>
        <div class="fav-btn ${p.isFavorite ? 'active' : ''}" onclick="toggleFavorite(event, '${p.id}')">
            <i class="${p.isFavorite ? 'fa-solid' : 'fa-regular'} fa-star"></i>
        </div>
        ${trend}
        <div class="p-img-box">
            <img src="${p.image}" class="product-image" loading="lazy" onerror="this.src='https://placehold.co/200x200/000/fff?text=NO_SIGNAL'">
            <div class="price-tag">${Math.round(p.current_price)}</div>
        </div>
        <div class="p-detail-sh">
            <div class="product-name" title="${p.name}">${p.name}</div>
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

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
            document.getElementById('search-suggestions').style.display = 'none';
        }
    });

    document.getElementById('sort-options').onchange = (e) => { sortOption = e.target.value; renderProducts(); };

    document.querySelectorAll('.multi-filter-group input').forEach(cb => {
        cb.onchange = () => {
            if (cb.checked) activeUnitFilters.add(cb.value);
            else activeUnitFilters.delete(cb.value);
            renderProducts();
        };
    });

    document.querySelectorAll('.intel-btn').forEach(btn => {
        btn.onclick = () => {
            activeIntelFilter = activeIntelFilter === btn.dataset.filter ? 'all' : btn.dataset.filter;
            document.querySelectorAll('.intel-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === activeIntelFilter));
            renderProducts();
        };
    });

    document.getElementById('compare-btn').onclick = () => {
        if (compareModeActive && selectedForComparison.length > 0) openCompareModal();
        compareModeActive = !compareModeActive;
        document.getElementById('compare-btn').classList.toggle('active', compareModeActive);
        renderProducts();
    };

    document.getElementById('cart-comp-btn').onclick = openCartModal;
    
    document.getElementById('reset-cart-btn').onclick = () => {
        if(confirm("Empty Cart?")) {
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
        if(confirm("Clear staged Matrix?")) {
            selectedForComparison = []; localStorage.setItem('god_comparison', '[]');
            document.getElementById('compare-modal').style.display = 'none';
            renderProducts();
        }
    };

    document.querySelectorAll('.close-modal').forEach(btn => btn.onclick = () => btn.closest('.modal').style.display = 'none');
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
        btn.innerHTML = `<i class="fas fa-list"></i> ${name}`;
        btn.onclick = () => {
            if(confirm(`Load "${name}"?`)) {
                favorites = [...shoppingLists[name]]; localStorage.setItem('god_favorites', JSON.stringify(favorites));
                processData(); openCartModal(); renderProducts();
            }
        };
        
        const del = document.createElement('button');
        del.className = 'btn-icon danger'; del.style.padding = '5px 8px';
        del.innerHTML = `<i class="fas fa-trash"></i>`;
        del.onclick = (e) => {
            e.stopPropagation();
            if(confirm(`Delete list "${name}"?`)) { delete shoppingLists[name]; localStorage.setItem('god_shopping_lists', JSON.stringify(shoppingLists)); renderShoppingLists(); }
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

function openCompareModal() {
    document.getElementById('compare-modal').style.display = 'flex';
    const products = allProducts.filter(p => selectedForComparison.includes(p.id));
    document.getElementById('selected-count').innerText = `${products.length} units staged`;
    const ctrl = document.querySelector('.compare-details-grid') || document.getElementById('compare-details');
    ctrl.innerHTML = `<button id="matrix-to-cart-btn" class="btn-icon" style="margin:20px; width:200px; background:var(--gold); color:#000;"><i class="${p.isFavorite ? 'fa-solid' : 'fa-regular'} fa-star"></i> Move Matrix to Cart</button>`;
    document.getElementById('matrix-to-cart-btn').onclick = () => {
        selectedForComparison.forEach(id => { if (!favorites.includes(id)) favorites.push(id); });
        localStorage.setItem('god_favorites', JSON.stringify(favorites));
        processData(); alert("Items added to Cart!"); renderProducts();
    };
    const ctx = document.getElementById('compare-chart').getContext('2d');
    if (compareChart) compareChart.destroy();
    const allDates = [...new Set(products.flatMap(p => p.history.map(h => h.date)))].sort();
    compareChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: allDates,
            datasets: products.map(p => ({
                label: `${p.name} [${p.store}]`,
                data: allDates.map(d => { const h = p.history.find(hx => hx.date === d); return h ? h.normalized_price : null; }),
                borderColor: STORE_CONFIG[p.store].color, borderWidth: 3, tension: 0.3, fill: false
            }))
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: { y: { grid: { color: '#222' }, ticks: { color: '#888' } }, x: { grid: { display: false }, ticks: { color: '#888' } } },
            plugins: { legend: { labels: { color: '#fff', boxWidth: 10, font: { size: 9 } } } }
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
                return `<div style="display:flex; align-items:center; gap:8px; padding:5px 0; border-bottom:1px solid #111;">
                    <img src="${match.image}" style="width:30px; height:30px; object-fit:contain; background:#fff; border-radius:4px;">
                    <div style="flex:1; font-size:0.75rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${item.name}</div>
                    <div style="font-weight:800; font-size:0.8rem;">${Math.round(match.current_price)}</div>
                </div>`;
            }
            return '';
        }).join('');
        if (total > 0) {
            html += `<div style="padding:15px; background:#050505; border-radius:12px; border:1px solid ${STORE_CONFIG[sid].color}33;">
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

function openDetailedChart(product) {
    document.getElementById('chart-modal').style.display = 'flex';
    document.getElementById('chart-product-name').innerText = product.name;
    const store = STORE_CONFIG[product.store];
    document.getElementById('chart-store-tag').innerText = store.name;
    document.getElementById('chart-store-tag').style.background = store.color;
    document.getElementById('chart-actual').innerText = fmt(product.current_price);
    document.getElementById('chart-unit').innerText = fmt(product.normalized_price);
    document.getElementById('chart-avg').innerText = fmt(product.avgPrice);
    document.getElementById('chart-min-max').innerHTML = `<span style="color:var(--accent-secondary)">${fmt(product.minPrice)}</span> / <span style="color:var(--danger)">${fmt(product.maxPrice)}</span>`;
    
    const ctx = document.getElementById('price-history-chart').getContext('2d');
    const history = product.history || [];
    if (detailChart) detailChart.destroy();
    detailChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: history.map(h => h.date),
            datasets: [
                { label: 'Unit Price', data: history.map(h => h.normalized_price), borderColor: store.color, backgroundColor: store.color + '22', fill: true, tension: 0.3, yAxisID: 'y' },
                { label: 'Actual Price', data: history.map(h => h.price), borderColor: '#ffffff', borderDash: [5, 5], fill: false, tension: 0, yAxisID: 'y1' }
            ]
        },
        options: { 
            responsive: true, maintainAspectRatio: false,
            scales: {
                y: { position: 'left', title: { display: true, text: 'Unit Price', color: store.color }, grid: { color: '#222' }, ticks: { color: store.color } },
                y1: { position: 'right', title: { display: true, text: 'Actual Price', color: '#fff' }, grid: { display: false }, ticks: { color: '#fff' } }
            },
            plugins: { legend: { labels: { color: '#fff' } } }
        }
    });
}

function updateStoreStats() {
    const sidebarStats = document.getElementById('store-stats-sidebar');
    if (!sidebarStats || !metadata.stores) return;
    let html = '<div style="font-size: 0.6rem; color: #444; margin-bottom: 8px; font-weight: 800;">GODDATA UPLINK STATUS</div>';
    Object.entries(metadata.stores).forEach(([store, data]) => {
        html += `<div class="legend-item" style="display:flex; flex-direction:column; margin-bottom:8px;">
            <div style="display:flex; justify-content:space-between; font-weight:700;">
                <span style="color:${STORE_CONFIG[store].color}">${store.toUpperCase()}</span>
                <span>${data.total} items</span>
            </div>
            <div style="font-size:0.55rem; opacity:0.5;">Range: ${data.date_range || 'N/A'}</div>
        </div>`;
    });
    sidebarStats.innerHTML = html;
}
