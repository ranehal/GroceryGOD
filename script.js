// GroceryGOD Core Engine - Market Intelligence
// Dev notes: matha thanda kore grouping logic likhlam, ebar apples/rice ek jaigay thakbe.

let allProducts = [];
let metadata = {};
let favorites = JSON.parse(localStorage.getItem('god_favorites') || '[]');
let selectedForComparison = JSON.parse(localStorage.getItem('god_comparison') || '[]');
let customGroups = JSON.parse(localStorage.getItem('god_custom_groups') || '{}');

let currentStore = 'all';
let searchQuery = '';
let activeUnitFilters = new Set(['kg', 'liter', 'piece']);
let sortOption = 'name_asc';
let activeIntelFilter = 'all';
let compareModeActive = false;
let showFavoritesOnly = false;
let activeShopFilters = new Set(['shwapno', 'chaldal', 'meenabazar', 'dailyshopping']);
let activeCategories = new Set();

let intelDateRange = { start: null, end: null };
let greatDealThreshold = 0.85;
let goodBuyThreshold = 0.95;

const STORE_CONFIG = {
    shwapno: { color: '#ff4081', name: 'Shwapno' },
    chaldal: { color: '#007aff', name: 'Chaldal' },
    meenabazar: { color: '#34c759', name: 'Meena Bazar' },
    dailyshopping: { color: '#ff9f0a', name: 'Daily Shopping' }
};

// Initial setup
document.addEventListener('DOMContentLoaded', async () => {
    document.title = "GroceryGOD";
    showLoading(true, 'Initializing Market Uplink...');
    
    if (window.godData) {
        allProducts = Object.values(window.godData.products);
        metadata = window.godData.metadata;
        processData();
    }
    
    renderSidebar();
    renderProducts();
    setupEventListeners();
    updateStoreStats();
    
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
        
        p.priceChangePercent = 0;
        if (history.length >= 2) {
            const curr = history[history.length - 1].normalized_price || history[history.length - 1].price;
            const prev = history[history.length - 2].normalized_price || history[history.length - 2].price;
            p.priceChangePercent = prev > 0 ? ((curr - prev) / prev * 100) : 0;
        }
        
        p.isFavorite = favorites.includes(p.id);
    });
    updateStats();
}

function updateStats() {
    const totalEl = document.getElementById('total-items');
    if (totalEl) totalEl.innerText = allProducts.length;
    const goodBuys = allProducts.filter(p => p.normalized_price < (p.avgPrice * 0.95)).length;
    const goodEl = document.getElementById('good-buys-count');
    if (goodEl) goodEl.innerText = goodBuys;
}

function updateStoreStats() {
    const sidebarStats = document.getElementById('store-stats-sidebar');
    if (!sidebarStats || !metadata.stores) return;
    
    let html = '<div style="font-size: 0.6rem; color: #444; margin-bottom: 8px; font-weight: 800;">UPLINK STATUS</div>';
    Object.entries(metadata.stores).forEach(([store, data]) => {
        html += `
            <div class="legend-item" style="display:flex; justify-content:space-between;">
                <span style="color:${STORE_CONFIG[store].color}">${store.toUpperCase()}</span>
                <span>${data.last_update}</span>
            </div>
        `;
    });
    sidebarStats.innerHTML = html;
}

function renderSidebar() {
    const list = document.getElementById('category-list');
    if (!list) return;
    list.innerHTML = '';
    
    // 1. Shop Toggles with Counts
    const shopHeading = document.createElement('div');
    shopHeading.className = 'category-group-header';
    shopHeading.innerHTML = `<span><i class="fas fa-store"></i> Shops</span>`;
    list.appendChild(shopHeading);

    const shopList = document.createElement('ul');
    shopList.className = 'category-sub-list active';
    Object.keys(STORE_CONFIG).forEach(id => {
        const count = allProducts.filter(p => p.store === id).length;
        const li = document.createElement('li');
        li.className = 'category-item';
        li.innerHTML = `
            <label style="cursor:pointer; display:flex; width:100%; justify-content:space-between; align-items:center;">
                <span style="color:${STORE_CONFIG[id].color}">${STORE_CONFIG[id].name}</span>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="opacity:0.4; font-size:0.7rem;">${count}</span>
                    <input type="checkbox" value="${id}" ${activeShopFilters.has(id) ? 'checked' : ''}>
                </div>
            </label>
        `;
        li.querySelector('input').onclick = (e) => {
            if (e.target.checked) activeShopFilters.add(id);
            else activeShopFilters.delete(id);
            renderProducts();
        };
        shopList.appendChild(li);
    });
    list.appendChild(shopList);

    // 2. Categories with Toggles & Counts
    const catHeading = document.createElement('div');
    catHeading.className = 'category-group-header';
    catHeading.innerHTML = `<span><i class="fas fa-tags"></i> Categories</span>`;
    list.appendChild(catHeading);

    const categories = [...new Set(allProducts.map(p => p.category))].sort();
    const catList = document.createElement('ul');
    catList.className = 'category-sub-list active';
    categories.forEach(cat => {
        const count = allProducts.filter(p => p.category === cat).length;
        const li = document.createElement('li');
        li.className = 'category-item';
        li.innerHTML = `
            <label style="cursor:pointer; display:flex; width:100%; justify-content:space-between; align-items:center;">
                <span style="max-width:150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${cat}</span>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="opacity:0.4; font-size:0.7rem;">${count}</span>
                    <input type="checkbox" value="${cat}" ${activeCategories.has(cat) ? 'checked' : ''}>
                </div>
            </label>
        `;
        li.querySelector('input').onclick = (e) => {
            if (e.target.checked) activeCategories.add(cat);
            else activeCategories.delete(cat);
            renderProducts();
        };
        catList.appendChild(li);
    });
    list.appendChild(catList);

    // 3. User Custom Groups (CRUD)
    const customHeading = document.createElement('div');
    customHeading.className = 'category-group-header';
    customHeading.innerHTML = `<span><i class="fas fa-folder-plus"></i> My Groups</span> <button id="add-group-btn" class="btn-icon" style="padding:2px;"><i class="fas fa-plus"></i></button>`;
    list.appendChild(customHeading);

    const customList = document.createElement('ul');
    customList.className = 'category-sub-list active';
    
    Object.keys(customGroups).forEach(groupName => {
        const li = document.createElement('li');
        li.className = 'category-item';
        li.innerHTML = `
            <span class="group-name-trigger" style="flex:1;">${groupName}</span>
            <div style="display:flex; gap:5px;">
                <span style="opacity:0.4; font-size:0.7rem;">${customGroups[groupName].length}</span>
                <i class="fas fa-trash delete-group-btn" style="color:var(--danger); font-size:0.7rem; cursor:pointer;"></i>
            </div>
        `;
        li.querySelector('.group-name-trigger').onclick = () => {
            // Show only items in this group
            renderGroupItems(groupName);
        };
        li.querySelector('.delete-group-btn').onclick = (e) => {
            e.stopPropagation();
            if (confirm(`Delete group "${groupName}"?`)) {
                delete customGroups[groupName];
                saveCustomGroups();
                renderSidebar();
            }
        };
        customList.appendChild(li);
    });
    list.appendChild(customList);

    document.getElementById('add-group-btn').onclick = () => {
        const name = prompt("Enter new group name:");
        if (name && !customGroups[name]) {
            // Create group from currently selected (comparison) items
            if (selectedForComparison.length === 0) {
                alert("Add some items to Comparison Matrix first to create a group!");
                return;
            }
            customGroups[name] = [...selectedForComparison];
            saveCustomGroups();
            renderSidebar();
        }
    };
}

function saveCustomGroups() {
    localStorage.setItem('god_custom_groups', JSON.stringify(customGroups));
}

function renderGroupItems(groupName) {
    const itemIds = customGroups[groupName] || [];
    searchQuery = '';
    document.getElementById('product-search').value = '';
    activeIntelFilter = 'all';
    showFavoritesOnly = false;
    
    const grid = document.getElementById('sh-grid');
    grid.innerHTML = '';
    
    const filtered = allProducts.filter(p => itemIds.includes(p.id));
    const fragment = document.createDocumentFragment();
    filtered.forEach(p => {
        fragment.appendChild(createProductCard(p));
    });
    grid.appendChild(fragment);
    
    document.getElementById('current-view-title').innerText = `Group: ${groupName}`;
}

function renderProducts() {
    const grid = document.getElementById('sh-grid');
    if (!grid) return;
    grid.innerHTML = '';
    document.getElementById('current-view-title').innerText = `GroceryGOD Unified`;

    let filtered = allProducts.filter(p => {
        if (!activeShopFilters.has(p.store)) return false;
        if (activeCategories.size > 0 && !activeCategories.has(p.category)) return false;
        if (showFavoritesOnly && !p.isFavorite) return false;
        if (searchQuery && !p.name.toLowerCase().includes(searchQuery) && !p.category.toLowerCase().includes(searchQuery)) return false;
        if (!activeUnitFilters.has(p.unit_type)) return false;
        
        if (activeIntelFilter === 'great') return p.normalized_price < (p.avgPrice * greatDealThreshold);
        if (activeIntelFilter === 'good') return p.normalized_price < (p.avgPrice * goodBuyThreshold);
        if (activeIntelFilter === 'wait') return p.normalized_price > (p.avgPrice * 1.05);
        if (activeIntelFilter === 'low') return p.normalized_price <= p.minPrice && p.minPrice < p.maxPrice;
        
        return true;
    });

    filtered.sort((a, b) => {
        if (sortOption === 'name_asc') return a.name.localeCompare(b.name);
        if (sortOption === 'unit_price_asc') return a.normalized_price - b.normalized_price;
        if (sortOption === 'unit_price_desc') return b.normalized_price - a.normalized_price;
        if (sortOption === 'actual_price_asc') return a.current_price - b.current_price;
        if (sortOption === 'drop_desc') return a.priceChangePercent - b.priceChangePercent;
        if (sortOption === 'rise_desc') return b.priceChangePercent - a.priceChangePercent;
        if (sortOption === 'savings_desc') return (b.avgPrice - b.normalized_price) - (a.avgPrice - a.normalized_price);
        return 0;
    });

    const fragment = document.createDocumentFragment();
    filtered.slice(0, 200).forEach(p => {
        const card = createProductCard(p);
        fragment.appendChild(card);
    });
    grid.appendChild(fragment);
}

function createProductCard(p) {
    const card = document.createElement('div');
    const storeColor = STORE_CONFIG[p.store].color;
    card.className = `p-item-sh ${selectedForComparison.includes(p.id) ? 'selected' : ''}`;
    card.style.setProperty('--store-color', storeColor);
    
    const changeTag = p.priceChangePercent !== 0 ? `
        <div style="position:absolute; top:35px; left:8px; font-size:0.6rem; font-weight:900; background:rgba(0,0,0,0.8); padding:2px 6px; border-radius:4px; color:${p.priceChangePercent < 0 ? 'var(--accent-secondary)' : 'var(--danger)'}">
            ${p.priceChangePercent > 0 ? '+' : ''}${p.priceChangePercent.toFixed(1)}%
        </div>
    ` : '';

    card.innerHTML = `
        <div class="store-badge" style="background:${storeColor}">${p.store}</div>
        <div class="fav-btn ${p.isFavorite ? 'active' : ''}" onclick="toggleFavorite(event, '${p.id}')">
            <i class="${p.isFavorite ? 'fas' : 'far'} fa-star"></i>
        </div>
        ${changeTag}
        <div class="p-img-box">
            <img src="${p.image}" class="product-image" loading="lazy" onerror="this.src='https://placehold.co/200x200/000/fff?text=NO_SIGNAL'">
            <div class="price-tag">${Math.round(p.current_price)}৳</div>
        </div>
        <div class="p-detail-sh">
            <div class="product-name" title="${p.name}">${p.name}</div>
            <div class="product-meta">
                <div style="color:${storeColor}; font-weight:800; font-size:0.9rem;">${p.normalized_price.toFixed(2)} <span style="font-size:0.6rem; opacity:0.6;">/ ${p.unit_type}</span></div>
                <div style="display:flex; justify-content:space-between; align-items:center; opacity:0.5;">
                    <span>Pack: ${p.unit}</span>
                    <span style="font-style:italic; font-size:0.55rem; background:#111; padding:1px 4px; border-radius:3px; max-width:80px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${p.category}</span>
                </div>
            </div>
        </div>
    `;
    
    card.onclick = (e) => {
        if (e.target.closest('.fav-btn')) return;
        if (compareModeActive) {
            toggleComparison(p.id);
        } else {
            openDetailedChart(p);
        }
    };
    
    return card;
}

function toggleFavorite(e, id) {
    e.stopPropagation();
    if (favorites.includes(id)) {
        favorites = favorites.filter(f => f !== id);
    } else {
        favorites.push(id);
    }
    localStorage.setItem('god_favorites', JSON.stringify(favorites));
    processData();
    renderProducts();
}

function setupEventListeners() {
    const searchInput = document.getElementById('product-search');

    searchInput.addEventListener('input', (e) => {
        searchQuery = e.target.value.toLowerCase();
        document.getElementById('clear-search').classList.toggle('visible', searchQuery.length > 0);
        updateSuggestions(searchQuery);
        renderProducts();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
            if (document.activeElement === searchInput) {
                searchQuery = '';
                searchInput.value = '';
                document.getElementById('search-suggestions').style.display = 'none';
                renderProducts();
            }
        }
    });

    document.getElementById('sort-options').addEventListener('change', (e) => {
        sortOption = e.target.value;
        renderProducts();
    });

    document.querySelectorAll('.multi-filter-group input').forEach(cb => {
        cb.onchange = () => {
            if (cb.checked) activeUnitFilters.add(cb.value);
            else activeUnitFilters.delete(cb.value);
            renderProducts();
        };
    });

    document.querySelectorAll('.intel-btn').forEach(btn => {
        btn.onclick = () => {
            const filter = btn.dataset.filter;
            if (activeIntelFilter === filter) activeIntelFilter = 'all';
            else activeIntelFilter = filter;
            document.querySelectorAll('.intel-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === activeIntelFilter));
            renderProducts();
        };
    });

    document.getElementById('compare-btn').onclick = () => {
        compareModeActive = !compareModeActive;
        document.getElementById('compare-btn').classList.toggle('active', compareModeActive);
        if (!compareModeActive && selectedForComparison.length > 0) openCompareModal();
        renderProducts();
    };

    document.getElementById('cart-comp-btn').onclick = openCartModal;
    document.getElementById('sidebar-toggle').onclick = () => document.querySelector('.sidebar').classList.toggle('visible');
    document.getElementById('clear-search').onclick = () => {
        searchInput.value = '';
        searchQuery = '';
        document.getElementById('clear-search').classList.remove('visible');
        renderProducts();
    };

    document.getElementById('bookmark-cat-btn').onclick = () => {
        showFavoritesOnly = !showFavoritesOnly;
        document.getElementById('bookmark-cat-btn').classList.toggle('active', showFavoritesOnly);
        renderProducts();
    };

    // Sidebar Category Filter Fix
    document.getElementById('category-filter').addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase();
        document.querySelectorAll('.category-item').forEach(item => {
            const text = item.innerText.toLowerCase();
            item.style.display = text.includes(q) ? 'flex' : 'none';
        });
    });

    document.getElementById('reset-cart-btn').onclick = () => {
        if (confirm("Reset staged matrix and favorites?")) {
            selectedForComparison = [];
            favorites = [];
            localStorage.setItem('god_comparison', JSON.stringify(selectedForComparison));
            localStorage.setItem('god_favorites', JSON.stringify(favorites));
            updateCartAnalysis();
            processData();
            renderProducts();
        }
    };

    document.getElementById('compare-clear-all').onclick = () => {
        selectedForComparison = [];
        localStorage.setItem('god_comparison', JSON.stringify(selectedForComparison));
        renderProducts();
        document.getElementById('selected-count').innerText = '0 staged';
    };

    document.querySelectorAll('.close-modal').forEach(btn => {
        btn.onclick = () => btn.closest('.modal').style.display = 'none';
    });
}

function updateSuggestions(query) {
    const box = document.getElementById('search-suggestions');
    if (!query || query.length < 2) { box.style.display = 'none'; return; }
    const matches = allProducts.filter(p => p.name.toLowerCase().includes(query)).slice(0, 15);
    if (matches.length === 0) { box.style.display = 'none'; return; }
    box.innerHTML = matches.map(p => `
        <div class="suggestion-item" onclick="selectSuggestion('${p.name}')">
            <span>${p.name}</span>
            <span style="color:${STORE_CONFIG[p.store].color}; font-size:0.6rem; font-weight:900;">${p.store.toUpperCase()}</span>
        </div>
    `).join('');
    box.style.display = 'block';
}

window.selectSuggestion = (name) => {
    const input = document.getElementById('product-search');
    input.value = name;
    searchQuery = name.toLowerCase();
    document.getElementById('search-suggestions').style.display = 'none';
    renderProducts();
};

function openCompareModal() {
    document.getElementById('compare-modal').style.display = 'flex';
    const products = allProducts.filter(p => selectedForComparison.includes(p.id));
    const ctx = document.getElementById('compare-chart').getContext('2d');
    if (compareChart) compareChart.destroy();
    const allDates = [...new Set(products.flatMap(p => p.history.map(h => h.date)))].sort();
    const datasets = products.map(p => ({
        label: `${p.name} [${p.store}]`,
        data: allDates.map(d => {
            const h = p.history.find(hx => hx.date === d);
            return h ? h.normalized_price : null;
        }),
        borderColor: STORE_CONFIG[p.store].color,
        borderWidth: 3, tension: 0.3, fill: false
    }));
    compareChart = new Chart(ctx, {
        type: 'line',
        data: { labels: allDates, datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                y: { grid: { color: '#222' }, ticks: { color: '#888' } },
                x: { grid: { display: false }, ticks: { color: '#888' } }
            },
            plugins: { legend: { labels: { color: '#fff', boxWidth: 10, font: { size: 9 } } } }
        }
    });
}

function openCartModal() {
    document.getElementById('cart-modal').style.display = 'flex';
    updateCartAnalysis();
}

function updateCartAnalysis() {
    const container = document.getElementById('cart-content');
    const cartItems = allProducts.filter(p => selectedForComparison.includes(p.id) || favorites.includes(p.id));
    if (cartItems.length === 0) {
        container.innerHTML = '<div style="padding:100px; text-align:center; opacity:0.3; font-size:2rem;">NO_UPLINK</div>';
        return;
    }
    const stores = Object.keys(STORE_CONFIG);
    let html = '<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:15px;">';
    stores.forEach(sid => {
        let total = 0;
        let found = false;
        const itemsHtml = cartItems.map(item => {
            const match = allProducts.find(p => p.store === sid && p.name === item.name);
            if (match) {
                total += match.current_price;
                found = true;
                return `<div style="display:flex; align-items:center; gap:8px; padding:5px 0; border-bottom:1px solid #111;">
                    <img src="${match.image}" style="width:30px; height:30px; object-fit:contain; background:#fff; border-radius:4px;">
                    <div style="flex:1; font-size:0.75rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${item.name}</div>
                    <div style="font-weight:800; font-size:0.8rem;">${match.current_price}৳</div>
                </div>`;
            }
            return '';
        }).join('');
        if (found) {
            html += `<div style="padding:15px; background:#050505; border-radius:12px; border:1px solid ${STORE_CONFIG[sid].color}33;">
                <h3 style="color:${STORE_CONFIG[sid].color}; margin:0 0 10px 0; font-size:1rem;">${STORE_CONFIG[sid].name}</h3>
                <div style="max-height: 300px; overflow-y:auto;">${itemsHtml}</div>
                <div style="margin-top:15px; padding-top:10px; border-top:2px solid #222; display:flex; justify-content:space-between; font-weight:900;">
                    <span>TOTAL</span><span style="color:var(--accent-secondary)">${total.toFixed(0)}৳</span>
                </div>
            </div>`;
        }
    });
    container.innerHTML = html + '</div>';
}

let detailChart = null;
function openDetailedChart(product) {
    document.getElementById('chart-modal').style.display = 'flex';
    document.getElementById('chart-product-name').innerText = product.name;
    document.getElementById('chart-product-unit').innerText = `/ ${product.unit_type}`;
    const store = STORE_CONFIG[product.store];
    const tag = document.getElementById('chart-store-tag');
    tag.innerText = store.name;
    tag.style.background = store.color;
    document.getElementById('chart-store-name').innerText = store.name;
    document.getElementById('chart-actual').innerText = `${product.current_price}৳`;
    document.getElementById('chart-unit').innerText = `${product.normalized_price.toFixed(2)}৳`;
    document.getElementById('chart-avg').innerText = `${product.avgPrice.toFixed(2)}৳`;
    document.getElementById('chart-min-max').innerHTML = `<span style="color:var(--accent-secondary)">${product.minPrice}</span> / <span style="color:var(--danger)">${product.maxPrice}</span>`;
    
    const ctx = document.getElementById('price-history-chart').getContext('2d');
    if (detailChart) detailChart.destroy();
    const history = product.history || [];
    detailChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: history.map(h => h.date),
            datasets: [
                { label: 'Unit Price', data: history.map(h => h.normalized_price || h.price), borderColor: store.color, fill: true, yAxisID: 'y' },
                { label: 'Market Trend', data: history.map(h => h.price), borderColor: '#fff', borderDash: [5, 5], fill: false, yAxisID: 'y1' }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                y: { position: 'left', grid: { color: '#222' }, title: { display: true, text: 'Unit Price' } },
                y1: { position: 'right', grid: { display: false }, title: { display: true, text: 'Actual Price' } }
            }
        }
    });
}
