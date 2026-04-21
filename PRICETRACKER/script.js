// --- State ---
let products = window.PRODUCT_DATA ? Object.values(window.PRODUCT_DATA) : [];
let favorites = new Set(JSON.parse(localStorage.getItem('tracker_favs') || '[]'));
let pinnedCategories = new Set(JSON.parse(localStorage.getItem('pinnedCategories') || '[]'));
let activeViewCategories = new Set(JSON.parse(localStorage.getItem('activeViewCategories') || '[]'));
let selectedForCompare = new Set();
let isCompareMode = false;
let currentProductViewLimit = 100;
let chartInstance = null;

// Date Range Analysis State
let analysisRange = { from: null, to: null, active: false };

const dom = {
    productGrid: document.getElementById('product-grid'),
    categoryList: document.getElementById('categoryList'),
    pinnedCategoryList: document.getElementById('pinnedCategoryList'),
    pinnedSection: document.getElementById('pinnedCategoriesSection'),
    catSearch: document.getElementById('catSearch'),
    searchInput: document.getElementById('searchInput'),
    selectAllCats: document.getElementById('selectAllCats'),
    totalItems: document.getElementById('totalItems'),
    sidebar: document.getElementById('sidebar'),
    sidebarOverlay: document.getElementById('sidebar-overlay'),
    compareBar: document.getElementById('compareBar'),
    modal: document.getElementById('historyModal'),
    recentModal: document.getElementById('recentUpdatesModal'),
    hamburger: document.getElementById('mobileMenuBtn'),
    closeSidebar: document.getElementById('toggleSidebarBtn'),
    themeToggle: document.getElementById('themeToggle'),
    scrapeNowBtn: document.getElementById('scrapeNowBtn'),
    showChangesBtn: document.getElementById('showChangesBtn'),
    recentUpdatesBtn: document.getElementById('recentUpdatesBtn'),
    sortSelect: document.getElementById('sortSelect'),
    filterType: document.getElementById('filterType'),
    changesOptions: document.getElementById('changesOptions'),
    changesMovement: document.getElementById('changesMovement'),
    changesSort: document.getElementById('changesSort'),
    toggleCompareBtn: document.getElementById('toggleCompareBtn'),
    doCompareBtn: document.getElementById('doCompareBtn'),
    modalDetails: document.getElementById('modalDetails'),
    modalTitle: document.getElementById('modalTitle'),
    priceChart: document.getElementById('priceChart'),
    priceDrops: document.getElementById('priceDrops'),
    lastUpdate: document.getElementById('lastUpdate'),
    rangeAnalysisBar: document.getElementById('rangeAnalysisBar'),
    rangeDisplay: document.getElementById('rangeDisplay'),
    resetRangeBtn: document.getElementById('resetRangeBtn'),
    updateFromDate: document.getElementById('updateFromDate'),
    updateToDate: document.getElementById('updateToDate'),
    applyUpdatesBtn: document.getElementById('applyUpdatesFilterBtn')
};

// --- Initialization ---
async function init() {
    initEvents();
    await loadCategories();
    updateStats();
    renderProducts();
}

function initEvents() {
    // Basic UI Navigation
    if (dom.hamburger) dom.hamburger.onclick = () => dom.sidebar?.classList.add('visible');
    if (dom.closeSidebar) dom.closeSidebar.onclick = () => dom.sidebar?.classList.remove('visible');
    if (dom.sidebarOverlay) dom.sidebarOverlay.onclick = () => dom.sidebar?.classList.remove('visible');
    
    // Theme
    if (dom.themeToggle) {
        dom.themeToggle.onclick = () => {
            document.body.classList.toggle('theme-dark');
        };
    }

    // Modal Backdrop Closing (Easy Unfocus)
    document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
        backdrop.onclick = (e) => {
            e.stopPropagation();
            dom.modal?.classList.add('hidden');
            dom.recentModal?.classList.add('hidden');
        };
    });

    document.querySelectorAll('.close-modal').forEach(btn => {
        btn.onclick = () => {
            dom.modal?.classList.add('hidden');
            dom.recentModal?.classList.add('hidden');
        };
    });

    // Date Range Analysis Logic
    if (dom.recentUpdatesBtn) {
        dom.recentUpdatesBtn.onclick = () => {
            dom.recentModal?.classList.remove('hidden');
        };
    }

    if (dom.applyUpdatesBtn) {
        dom.applyUpdatesBtn.onclick = () => {
            const from = dom.updateFromDate?.value;
            const to = dom.updateToDate?.value;
            if (from && to) {
                analysisRange = { from, to, active: true };
                dom.rangeDisplay.innerText = `${from} // ${to}`;
                dom.rangeAnalysisBar?.classList.remove('hidden');
                dom.recentModal?.classList.add('hidden');
                renderProducts();
            } else {
                alert("PLEASE_SPECIFY_COMPLETE_TEMPORAL_RANGE");
            }
        };
    }

    if (dom.resetRangeBtn) {
        dom.resetRangeBtn.onclick = () => {
            analysisRange.active = false;
            dom.rangeAnalysisBar?.classList.add('hidden');
            renderProducts();
        };
    }

    // Filters & Grid Updates
    if (dom.catSearch) {
        dom.catSearch.oninput = (e) => {
            const term = e.target.value.toLowerCase();
            document.querySelectorAll('.category-item').forEach(li => {
                const name = li.querySelector('.category-name')?.innerText.toLowerCase() || "";
                li.style.display = name.includes(term) ? 'flex' : 'none';
            });
        };
    }

    if (dom.searchInput) dom.searchInput.oninput = () => renderProducts();
    if (dom.sortSelect) dom.sortSelect.onchange = () => renderProducts();
    if (dom.filterType) dom.filterType.onchange = () => renderProducts();

    if (dom.showChangesBtn) {
        dom.showChangesBtn.onclick = () => {
            dom.showChangesBtn.classList.toggle('active');
            dom.changesOptions?.classList.toggle('hidden');
            renderProducts();
        };
    }

    if (dom.changesMovement) dom.changesMovement.onchange = () => renderProducts();
    if (dom.changesSort) dom.changesSort.onchange = () => renderProducts();

    if (dom.selectAllCats) {
        dom.selectAllCats.onchange = (e) => {
            const checked = e.target.checked;
            document.querySelectorAll('.view-toggle').forEach(cb => {
                cb.checked = checked;
                const name = cb.dataset.catname;
                if (checked) activeViewCategories.add(name);
                else activeViewCategories.delete(name);
            });
            localStorage.setItem('activeViewCategories', JSON.stringify([...activeViewCategories]));
            renderProducts();
        };
    }

    if (dom.toggleCompareBtn) {
        dom.toggleCompareBtn.onclick = () => {
            isCompareMode = !isCompareMode;
            dom.toggleCompareBtn.classList.toggle('active', isCompareMode);
            dom.compareBar?.classList.toggle('visible', isCompareMode);
            if (!isCompareMode) selectedForCompare.clear();
            renderProducts();
        };
    }

    if (dom.doCompareBtn) dom.doCompareBtn.onclick = showComparisonGraph;
    if (dom.scrapeNowBtn) dom.scrapeNowBtn.onclick = () => fetch('/api/scrape', { method: 'POST' });
}

// --- Logic ---

async function loadCategories() {
    let categories = [];
    if (window.CATEGORY_DATA) {
        categories = window.CATEGORY_DATA;
    } else {
        try {
            const res = await fetch('/api/categories');
            if (res.ok) categories = await res.json();
        } catch (e) {}
    }

    if (!dom.categoryList) return;
    
    // Calculate counts
    const categoryCounts = {};
    Object.values(window.PRODUCT_DATA || {}).forEach(p => {
        const cat = p.category || "Uncategorized";
        categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
    });

    // Sort
    categories.sort((a,b) => a.name.localeCompare(b.name));
    
    dom.categoryList.innerHTML = '';
    dom.pinnedCategoryList.innerHTML = '';
    
    let pinnedCount = 0;
    const frag = document.createDocumentFragment();
    const pinFrag = document.createDocumentFragment();

    categories.forEach(cat => {
        const count = categoryCounts[cat.name] || 0;
        const li = createCategoryItem(cat, count);
        
        if (pinnedCategories.has(cat.name)) {
            const pinLi = li.cloneNode(true);
            attachCategoryEvents(pinLi, cat);
            pinFrag.appendChild(pinLi);
            pinnedCount++;
        }
        
        attachCategoryEvents(li, cat);
        frag.appendChild(li);
    });

    dom.categoryList.appendChild(frag);
    dom.pinnedCategoryList.appendChild(pinFrag);
    
    if (pinnedCount > 0) dom.pinnedSection?.classList.remove('hidden');
    else dom.pinnedSection?.classList.add('hidden');
}

function createCategoryItem(cat, count) {
    const li = document.createElement('li');
    li.className = 'category-item';
    const isChecked = activeViewCategories.has(cat.name);
    const isPinned = pinnedCategories.has(cat.name);
    
    li.innerHTML = `
        <input type="checkbox" class="view-toggle" data-catname="${cat.name}" ${isChecked ? 'checked' : ''}>
        <span class="category-name">${cat.name}</span>
        <span class="item-count" style="font-size:0.7rem; opacity:0.5; margin-left:5px;">[${count}]</span>
        <button class="bookmark-btn ${isPinned ? 'active' : ''}" title="Pin to top">
            <i class="fa-solid fa-thumbtack"></i>
        </button>
    `;
    return li;
}

function attachCategoryEvents(li, cat) {
    li.onclick = (e) => {
        if (e.target.type === 'checkbox' || e.target.closest('.bookmark-btn')) return;
        const cb = li.querySelector('.view-toggle');
        if (cb) {
            cb.checked = !cb.checked;
            cb.dispatchEvent(new Event('change'));
        }
    };

    li.querySelector('.view-toggle').onchange = (e) => {
        if (e.target.checked) activeViewCategories.add(cat.name);
        else activeViewCategories.delete(cat.name);
        localStorage.setItem('activeViewCategories', JSON.stringify([...activeViewCategories]));
        renderProducts();
    };

    li.querySelector('.bookmark-btn').onclick = (e) => {
        e.stopPropagation();
        if (pinnedCategories.has(cat.name)) pinnedCategories.delete(cat.name);
        else pinnedCategories.add(cat.name);
        localStorage.setItem('pinnedCategories', JSON.stringify([...pinnedCategories]));
        loadCategories(); // Re-render sidebar
    };
}

function renderProducts() {
    if (!dom.productGrid) return;
    dom.productGrid.innerHTML = '';

    const searchTerm = dom.searchInput?.value?.toLowerCase() || "";
    const sortMode = dom.sortSelect?.value || "name";
    const unitFilter = dom.filterType?.value || "all";
    const onlyChanges = dom.showChangesBtn?.classList.contains('active') || false;

    if (activeViewCategories.size === 0) {
        dom.productGrid.innerHTML = `
            <div style="grid-column:1/-1; padding:120px 20px; text-align:center; color:var(--text-muted); opacity:0.6;">
                <i class="fa-solid fa-satellite-dish" style="font-size:4rem; margin-bottom:20px;"></i>
                <h2 style="font-weight:800; letter-spacing:-1px;">SENSORS_OFFLINE</h2>
                <p>Select target categories in Discovery Deck to begin uplink.</p>
            </div>
        `;
        if (dom.totalItems) dom.totalItems.innerText = "0";
        return;
    }

    let filtered = Object.values(window.PRODUCT_DATA || {}).filter(p => {
        const matchCat = activeViewCategories.has(p.category || "");
        const matchSearch = p.name.toLowerCase().includes(searchTerm);
        return matchCat && matchSearch;
    });

    // Date Range Price Delta Logic
    if (analysisRange.active) {
        filtered = filtered.filter(p => {
            const hist = p.history || [];
            // Find price closest to 'from' and 'to' dates
            const startPoint = hist.find(h => h.date >= analysisRange.from);
            const endPoint = [...hist].reverse().find(h => h.date <= analysisRange.to);
            if (startPoint && endPoint && startPoint.date !== endPoint.date) {
                p._range_delta = endPoint.price - startPoint.price;
                p._range_start = startPoint.price;
                p._range_end = endPoint.price;
                return true;
            }
            return false;
        });
    }

    // Units
    if (unitFilter !== 'all') {
        filtered = filtered.filter(p => {
            const unit = (p.current_unit || "").toLowerCase();
            if (unitFilter === 'kg') return /kg|gm|g/i.test(unit);
            if (unitFilter === 'liter') return /ltr|l|ml/i.test(unit);
            if (unitFilter === 'piece') return /pcs|piece|each/i.test(unit);
            return true;
        });
    }

    // Price Changes (Normal Delta)
    if (onlyChanges) {
        const movement = dom.changesMovement?.value || 'any';
        filtered = filtered.filter(p => {
            if (!p.history || p.history.length < 2) return false;
            const curr = p.history[p.history.length - 1].price;
            const prev = p.history[p.history.length - 2].price;
            if (movement === 'up') return curr > prev;
            if (movement === 'down') return curr < prev;
            return curr !== prev;
        });
    }

    // Sort
    if (sortMode === 'priceAsc') filtered.sort((a,b) => window.normalizeProduct(a).price - window.normalizeProduct(b).price);
    else if (sortMode === 'priceDesc') filtered.sort((a,b) => window.normalizeProduct(b).price - window.normalizeProduct(a).price);
    else if (sortMode === 'fav') filtered.sort((a,b) => (favorites.has(b.id)?1:0) - (favorites.has(a.id)?1:0));
    else filtered.sort((a,b) => a.name.localeCompare(b.name));

    if (dom.totalItems) dom.totalItems.innerText = filtered.length;

    const frag = document.createDocumentFragment();
    filtered.slice(0, currentProductViewLimit).forEach((p, index) => {
        const std = window.normalizeProduct(p);
        const card = document.createElement('div');
        card.className = 'product-card';
        card.style.animation = `cardEntrance 0.3s ease-out backwards ${index * 15}ms`;
        
        // Badge logic (either Range Delta or Normal Delta)
        let badge = '';
        if (analysisRange.active && p._range_delta !== undefined) {
             const diff = p._range_delta;
             if (diff < 0) badge = `<span class="badge down">-${Math.abs(diff)}</span>`;
             else if (diff > 0) badge = `<span class="badge up">+${diff}</span>`;
        } else {
            const history = p.history || [];
            if (history.length > 1) {
                const curr = history[history.length - 1].price;
                const prev = history[history.length - 2].price;
                if (curr < prev) badge = `<span class="badge down">-${Math.round((1 - curr/prev) * 100)}%</span>`;
                else if (curr > prev) badge = `<span class="badge up">+${Math.round((curr/prev - 1) * 100)}%</span>`;
            }
        }

        const isFav = favorites.has(p.id);
        const isSelected = selectedForCompare.has(p.id);

        let priceClass = '';
        const history = p.history || [];
        if (history.length > 1) {
            const curr = history[history.length - 1].price;
            const prev = history[history.length - 2].price;
            if (curr < prev) priceClass = 'price-down';
            else if (curr > prev) priceClass = 'price-up';
        }

        card.innerHTML = `
            ${badge}
            <div class="product-img">
                <img src="${p.image}" loading="lazy" onerror="this.src='https://placehold.co/200x200?text=SIGNAL_LOST'">
                <!-- ACTUAL PRICE HOVER REVEAL -->
                <div class="hover-details">
                    <span class="hover-label">RAW_MARKET_PRICE</span>
                    <span class="hover-price">${p.current_price}</span>
                    <span class="hover-label">${p.current_unit}</span>
                </div>
            </div>
            <div class="product-name" title="${p.name}">${p.name}</div>
            <div class="price-row">
                <span class="price-val ${priceClass}">${Math.round(std.price)}</span>
                <span class="price-unit">${std.unit}</span>
            </div>
            <button class="icon-btn fav-btn ${isFav ? 'active' : ''}" style="position:absolute; bottom:12px; right:12px; width:34px; height:34px; border:none; background:transparent;">
                <i class="fa-${isFav ? 'solid' : 'regular'} fa-star" style="${isFav ? 'color:var(--magenta)' : ''}"></i>
            </button>
            ${isSelected ? '<i class="fa-solid fa-circle-check" style="position:absolute; top:12px; left:12px; color:var(--accent); font-size:1rem;"></i>' : ''}
        `;

        card.onclick = (e) => {
            if (e.target.closest('.fav-btn')) {
                window.toggleFav(p.id);
                return;
            }
            if (isCompareMode) {
                if (selectedForCompare.has(p.id)) selectedForCompare.delete(p.id);
                else if (selectedForCompare.size < 10) selectedForCompare.add(p.id);
                renderProducts();
            } else showHistory(p.id);
        };
        if (isSelected) card.style.borderColor = 'var(--accent)';
        frag.appendChild(card);
    });
    dom.productGrid.appendChild(frag);
}

window.normalizeProduct = (p) => {
    let price = p.current_price || 0;
    let unit = (p.current_unit || "").toLowerCase().trim();
    let qty = 1;
    let standardUnit = "/pc";

    const match = unit.match(/^(\d+(\.\d+)?)\s*([a-z]+)/);
    if (match) {
        qty = parseFloat(match[1]);
        const uStr = match[3];
        if (['kg', 'kgs'].includes(uStr)) { standardUnit = "/kg"; }
        else if (['g', 'gm', 'gms', 'gram'].includes(uStr)) { standardUnit = "/kg"; qty = qty / 1000; }
        else if (['l', 'ltr', 'liter'].includes(uStr)) { standardUnit = "/L"; }
        else if (['ml', 'milli'].includes(uStr)) { standardUnit = "/L"; qty = qty / 1000; }
    }
    return { price: price / (qty || 1), unit: standardUnit };
};

window.toggleFav = (id) => {
    if (favorites.has(id)) favorites.delete(id);
    else favorites.add(id);
    localStorage.setItem('tracker_favs', JSON.stringify([...favorites]));
    renderProducts();
};

function showHistory(pid) {
    const p = (window.PRODUCT_DATA || {})[pid];
    if (!p || !dom.modal) return;
    
    dom.modal.classList.remove('hidden');
    if (dom.modalTitle) dom.modalTitle.innerText = p.name;
    
    const std = window.normalizeProduct(p);
    if (dom.modalDetails) {
        dom.modalDetails.innerHTML = `
            <span>SOURCE: <strong>CHALDAL</strong></span>
            <span>CATEGORY: <strong>${p.category || "UNSPECIFIED"}</strong></span>
            <span>STANDARD: <strong>${Math.round(std.price)}${std.unit}</strong></span>
        `;
    }

    const history = p.history || [];
    const labels = history.map(h => h.date);
    const data = history.map(h => h.price);

    if (chartInstance) chartInstance.destroy();
    if (dom.priceChart) {
        chartInstance = new Chart(dom.priceChart.getContext('2d'), {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'UNIT_PRICE_BY_DATE',
                    data,
                    borderColor: '#007aff',
                    backgroundColor: 'rgba(0, 122, 255, 0.1)',
                    borderWidth: 3,
                    tension: 0.2,
                    fill: true,
                    pointBackgroundColor: '#007aff',
                    pointRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { 
                    y: { beginAtZero: false, grid: { color: 'rgba(255,255,255,0.05)' } },
                    x: { grid: { display: false } }
                }
            }
        });
    }
}

function showComparisonGraph() {
    if (selectedForCompare.size < 2) return alert("SELECT_MINIMUM_TWO_UNITS");
    dom.modal?.classList.remove('hidden');
    if (dom.modalTitle) dom.modalTitle.innerText = "MARKET_COMPARISON_MATRIX";
    
    const selected = products.filter(p => selectedForCompare.has(p.id));
    const allDates = [...new Set(selected.flatMap(p => (p.history || []).map(h => h.date)))].sort();
    
    const datasets = selected.map((p, i) => ({
        label: p.name,
        data: allDates.map(d => {
            const h = (p.history || []).find(x => x.date === d);
            return h ? h.price : null;
        }),
        borderColor: `hsl(${i * (360/selected.length)}, 70%, 50%)`,
        borderWidth: 3,
        tension: 0.3,
        fill: false
    }));

    if (chartInstance) chartInstance.destroy();
    if (dom.priceChart) {
        chartInstance = new Chart(dom.priceChart.getContext('2d'), {
            type: 'line',
            data: { labels: allDates, datasets },
            options: { 
                responsive: true, 
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom', labels: { color: '#888' } } }
            }
        });
    }
}

function updateStats() {
    const drops = products.filter(p => {
        if (!p.history || p.history.length < 2) return false;
        return p.history[p.history.length-1].price < p.history[p.history.length-2].price;
    }).length;
    if (dom.priceDrops) dom.priceDrops.innerText = drops;
    const allDates = products.flatMap(p => (p.history || []).map(h => h.date)).sort();
    if (dom.lastUpdate) dom.lastUpdate.innerText = allDates.pop() || '--';
}

function clearCompare() {
    selectedForCompare.clear();
    dom.compareBar?.classList.remove('visible');
    renderProducts();
}

init();
