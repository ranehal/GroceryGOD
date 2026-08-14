/* ═══════════════════════════════════════════════════════════════
   ChaldalTracker — app.js
   Full SPA: loads scraped JSON data, renders all views,
   price history charts, analytics, watchlist, search.
   ═══════════════════════════════════════════════════════════════ */
'use strict';

// ── State ──────────────────────────────────────────────────────
const State = {
  products: {},       // { id: {...} }
  categories: [],     // [{Id,Name,ParentCategoryId,...}]
  priceHistory: {},   // { id: [{d,p,m,s}] }
  catProducts: {},    // { catId: [pid,...] }
  banners: {},        // { section: [...] }
  initMeta: {},
  dailyDeals: [],
  watchlist: new Set(JSON.parse(localStorage.getItem('watchlist') || '[]')),
  currentView: 'home',
  currentCatId: null,
  currentPage: 1,
  pageSize: 24,
  sortBy: 'name',
  activeFilters: [],
  searchQuery: '',
  charts: {},          // chartjs instances
  activePeriod: '30d', // modal chart period
  activeProductId: null,
  themeLight: localStorage.getItem('theme') === 'light',
};

// ── Data loading ────────────────────────────────────────────────
const DATA_FILES = [
  ['data/products.json',      'products'],
  ['data/categories.json',    'categories'],
  ['data/price_history.json', 'priceHistory'],
  ['data/cat_products.json',  'catProducts'],
  ['data/banners.json',       'banners'],
  ['data/init_meta.json',     'initMeta'],
  ['data/daily_deals.json',   'dailyDeals'],
];

async function loadAll() {
  const results = await Promise.allSettled(DATA_FILES.map(([url]) => fetch(url).then(r => r.json())));
  DATA_FILES.forEach(([, key], i) => {
    if (results[i].status === 'fulfilled') State[key] = results[i].value;
    else console.warn('Could not load', DATA_FILES[i][0]);
  });
}

// ── App bootstrap ───────────────────────────────────────────────
const App = {
  async init() {
    applyTheme();
    await loadAll();
    buildCategoryTree();
    renderStatRow();
    renderBanners();
    renderHomeGroups();
    renderRecentDrops();
    renderPopular();
    renderHeroPriceCard();
    renderFreshnessIndicator();
    renderWatchlistCount();
    bindEvents();
    hideLoading();
  },

  showView(name, catId = null) {
    // Deactivate all views
    document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    document.getElementById('view-' + name)?.classList.remove('hidden');
    document.getElementById('nav-' + name)?.classList.add('active');
    State.currentView = name;

    if (name === 'products') {
      State.currentCatId = catId;
      State.currentPage  = 1;
      renderProductsView();
    } else if (name === 'deals') {
      renderDealsView();
    } else if (name === 'analytics') {
      renderAnalytics();
    } else if (name === 'watchlist') {
      renderWatchlist();
    }

    // Close sidebar on mobile
    if (window.innerWidth < 768) document.getElementById('sidebar').classList.remove('open');
  },

  openProduct(pid) {
    State.activeProductId = pid;
    State.activePeriod = '30d';
    renderModal(pid);
    document.getElementById('product-modal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  },

  closeModal() {
    document.getElementById('product-modal').classList.add('hidden');
    document.body.style.overflow = '';
    // Destroy modal chart
    if (State.charts.modal) { State.charts.modal.destroy(); State.charts.modal = null; }
  },

  toggleWatchlist(pid) {
    pid = String(pid);
    if (State.watchlist.has(pid)) {
      State.watchlist.delete(pid);
      toast('Removed from watchlist');
    } else {
      State.watchlist.add(pid);
      toast('Added to watchlist ⭐', 'success');
    }
    localStorage.setItem('watchlist', JSON.stringify([...State.watchlist]));
    renderWatchlistCount();
    // Update all watchlist buttons on page
    document.querySelectorAll(`.watchlist-btn[data-pid="${pid}"]`).forEach(btn => {
      btn.textContent = State.watchlist.has(pid) ? '⭐' : '☆';
      btn.classList.toggle('active', State.watchlist.has(pid));
    });
    // Update modal button if open
    const modalBtn = document.querySelector('.btn-watch');
    if (modalBtn && State.activeProductId === pid)
      modalBtn.innerHTML = State.watchlist.has(pid) ? '⭐ Watching' : '☆ Add to Watchlist';
    if (State.currentView === 'watchlist') renderWatchlist();
  },
};

// ── Category helpers ────────────────────────────────────────────
const catMap = () => Object.fromEntries((State.categories || []).map(c => [c.Id, c]));

function buildCategoryTree() {
  const cats = State.categories || [];
  const map = catMap();
  const roots = cats.filter(c => c.ParentCategoryId === 0).sort((a, b) => a.DisplayOrder - b.DisplayOrder);
  const childrenOf = id => cats.filter(c => c.ParentCategoryId === id).sort((a, b) => a.DisplayOrder - b.DisplayOrder);

  const nav = document.getElementById('cat-nav');
  nav.innerHTML = '';

  roots.forEach(root => {
    const children = childrenOf(root.Id);
    const div = document.createElement('div');
    div.className = 'cat-root';
    div.innerHTML = `
      <div class="cat-root-header" data-id="${root.Id}">
        <span>${root.Name}</span>
        ${children.length ? '<span class="cat-caret">▶</span>' : ''}
      </div>
      ${children.length ? `<div class="cat-children">${
        children.map(ch => `<div class="cat-child" data-id="${ch.Id}">${ch.Name}</div>`).join('')
      }</div>` : ''}
    `;
    div.querySelector('.cat-root-header').addEventListener('click', () => {
      if (children.length) {
        div.classList.toggle('open');
      } else {
        App.showView('products', root.Id);
        updateCatActive(root.Id);
      }
    });
    div.querySelectorAll('.cat-child').forEach(el => {
      el.addEventListener('click', () => {
        App.showView('products', +el.dataset.id);
        updateCatActive(+el.dataset.id);
      });
    });
    nav.appendChild(div);
  });
}

function updateCatActive(id) {
  document.querySelectorAll('.cat-root-header, .cat-child').forEach(el => el.classList.remove('active'));
  document.querySelectorAll(`[data-id="${id}"]`).forEach(el => el.classList.add('active'));
}

// ── Stats row ───────────────────────────────────────────────────
function renderStatRow() {
  const prods    = Object.keys(State.products).length;
  const cats     = (State.categories || []).length;
  const history  = State.priceHistory || {};
  let drops = 0, totalDiscount = 0, discountCount = 0;

  Object.entries(State.products).forEach(([pid, p]) => {
    const h = history[pid] || [];
    if (h.length >= 2) {
      const [prev, last] = [h[h.length - 2], h[h.length - 1]];
      if (last.p < prev.p) drops++;
    }
    if (p.mrp > p.price) {
      totalDiscount += ((p.mrp - p.price) / p.mrp) * 100;
      discountCount++;
    }
  });

  setText('stat-products', prods.toLocaleString());
  setText('stat-cats', cats.toLocaleString());
  setText('stat-drops', drops.toLocaleString());
  setText('stat-savings', discountCount ? Math.round(totalDiscount / discountCount) + '%' : '0%');
}

// ── Banners ─────────────────────────────────────────────────────
function renderBanners() {
  const grid = document.getElementById('banner-grid');
  const banners = State.banners || {};
  const allBanners = Object.values(banners).flat();
  if (!allBanners.length) { document.getElementById('banner-section').style.display = 'none'; return; }
  grid.innerHTML = allBanners.slice(0, 6).map(b => `
    <div class="banner-item">
      ${b.ImageUrl
        ? `<img src="${b.ImageUrl}" alt="banner" loading="lazy" onerror="this.parentElement.innerHTML='<div class=banner-placeholder>🛒</div>'">`
        : '<div class="banner-placeholder">🛒</div>'}
    </div>
  `).join('');
}

// ── Home groups ─────────────────────────────────────────────────
const CAT_EMOJI = { 2:'🛒',23:'🥩',58:'🥛',104:'🌾',17:'🥤',49:'🍿',81:'🧹',30:'💄',209:'👶',229:'🐾',3:'📎',1484:'💊',1574:'⚽',229:'🐾',65:'🥫',14:'🍯',100:'🎂',108:'🫙',111:'🧁',80:'🥦' };
const DEFAULT_EMOJI = '📦';

function renderHomeGroups() {
  const groups = State.initMeta?.homeGroups || {};
  const all = [...new Set(Object.values(groups).flat())];
  const map = catMap();
  const catProds = State.catProducts || {};
  const grid = document.getElementById('group-grid');
  if (!all.length) { grid.innerHTML = '<p style="color:var(--text3)">No categories loaded</p>'; return; }
  grid.innerHTML = all.slice(0, 20).map(id => {
    const cat = map[id];
    if (!cat) return '';
    const count = (catProds[id] || []).length;
    return `<div class="group-card" onclick="App.showView('products',${id})">
      <div class="group-icon">${CAT_EMOJI[id] || DEFAULT_EMOJI}</div>
      <div class="group-name">${cat.Name}</div>
      ${count ? `<div class="group-count">${count} items</div>` : ''}
    </div>`;
  }).join('');
}

// ── Price helpers ───────────────────────────────────────────────
function getHistory(pid) { return State.priceHistory[String(pid)] || []; }

function getPriceChange(pid) {
  const h = getHistory(pid);
  if (h.length < 2) return null;
  const [prev, cur] = [h[h.length - 2], h[h.length - 1]];
  const delta = cur.p - prev.p;
  return { delta, pct: prev.p ? ((delta / prev.p) * 100).toFixed(1) : 0, prev: prev.p, cur: cur.p };
}

function formatPrice(p) { return '৳' + Number(p).toFixed(2).replace(/\.00$/, ''); }

function priceDeltaHtml(pid) {
  const ch = getPriceChange(pid);
  if (!ch) return '';
  if (ch.delta === 0) return '';
  const cls = ch.delta < 0 ? 'down' : 'up';
  const arrow = ch.delta < 0 ? '↓' : '↑';
  return `<span class="price-delta ${cls}">${arrow}${Math.abs(ch.pct)}%</span>`;
}

// ── Product card ────────────────────────────────────────────────
function productCardHtml(p, compact = false) {
  const pid = String(p.id);
  const disc = p.mrp > p.price ? Math.round(((p.mrp - p.price) / p.mrp) * 100) : 0;
  const isNew = getHistory(pid).length <= 1;
  const isWatched = State.watchlist.has(pid);
  const ch = getPriceChange(pid);
  return `
  <div class="product-card" data-pid="${pid}" onclick="App.openProduct(${pid})">
    <div class="product-img-wrap">
      <div class="product-badges">
        ${disc > 0 ? `<span class="badge-pill badge-drop">-${disc}%</span>` : ''}
        ${isNew ? `<span class="badge-pill badge-new">New</span>` : ''}
        ${!p.inStock ? `<span class="badge-pill" style="background:var(--text3);color:#fff">OOS</span>` : ''}
      </div>
      ${p.imageUrl
        ? `<img class="product-img" src="${p.imageUrl}" alt="${esc(p.name)}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='grid'">`
        : ''}
      <div class="product-img-placeholder" style="${p.imageUrl ? 'display:none' : ''}">🛒</div>
      <button class="watchlist-btn ${isWatched ? 'active' : ''}" data-pid="${pid}"
        onclick="event.stopPropagation();App.toggleWatchlist(${pid})"
        title="${isWatched ? 'Remove from watchlist' : 'Add to watchlist'}">
        ${isWatched ? '⭐' : '☆'}
      </button>
    </div>
    <div class="product-info">
      <div class="product-name">${esc(p.name)}</div>
      ${p.subText ? `<div class="product-subtext">${esc(p.subText)}</div>` : ''}
      <div class="product-price-row">
        <span class="product-price">${formatPrice(p.price)}</span>
        ${p.mrp > p.price ? `<span class="product-mrp">${formatPrice(p.mrp)}</span>` : ''}
        ${disc > 0 ? `<span class="product-discount">-${disc}%</span>` : ''}
        ${priceDeltaHtml(pid)}
      </div>
      <div class="${p.inStock ? 'product-instock' : 'product-outstock'}">${p.inStock ? '● In Stock' : '● Out of Stock'}</div>
    </div>
  </div>`;
}

// ── Home: recent drops ──────────────────────────────────────────
function renderRecentDrops() {
  const drops = Object.values(State.products)
    .filter(p => { const ch = getPriceChange(p.id); return ch && ch.delta < 0; })
    .sort((a, b) => {
      const ca = getPriceChange(a.id), cb = getPriceChange(b.id);
      return ca.pct - cb.pct; // most negative first
    }).slice(0, 8);
  document.getElementById('drops-grid').innerHTML = drops.length
    ? drops.map(p => productCardHtml(p)).join('')
    : '<p style="color:var(--text3);padding:1rem">No price drops yet — run the scraper daily to track changes.</p>';
}

// ── Home: popular ───────────────────────────────────────────────
function renderPopular() {
  const all = Object.values(State.products);
  const shuffled = all.sort(() => Math.random() - 0.5).slice(0, 8);
  document.getElementById('popular-grid').innerHTML = shuffled.map(p => productCardHtml(p)).join('');
}

// ── Hero price preview ──────────────────────────────────────────
function renderHeroPriceCard() {
  const p = Object.values(State.products).find(x => x.imageUrl && x.price > 0);
  if (!p) return;
  const card = document.getElementById('hero-price-preview');
  card.innerHTML = `
    <div style="font-size:.7rem;color:rgba(255,255,255,.5);margin-bottom:.5rem">Latest price check</div>
    <div style="display:flex;gap:.75rem;align-items:center">
      <img src="${p.imageUrl}" style="width:56px;height:56px;object-fit:contain;border-radius:8px;background:rgba(255,255,255,.05)"
           onerror="this.style.display='none'">
      <div>
        <div style="font-size:.8rem;font-weight:600;opacity:.9">${p.name.slice(0,30)}…</div>
        <div style="font-size:1.4rem;font-weight:900;color:#00d68f;font-family:'JetBrains Mono',monospace">
          ${formatPrice(p.price)}
        </div>
      </div>
    </div>
    <div style="margin-top:.75rem;font-size:.7rem;opacity:.5">Updated ${p.scraped || 'today'}</div>`;
}

// ── Freshness ───────────────────────────────────────────────────
function renderFreshnessIndicator() {
  const date = State.initMeta?.lastUpdated || State.categories?.[0]?.scraped || 'Unknown';
  document.getElementById('freshness-text').textContent = `Updated ${date}`;
}

function renderWatchlistCount() {
  const el = document.getElementById('watchlist-count');
  const n = State.watchlist.size;
  el.textContent = n;
  el.style.display = n ? '' : 'none';
}

// ── Products view ───────────────────────────────────────────────
function getProductsForView() {
  let ids;
  if (State.currentCatId) {
    ids = State.catProducts[String(State.currentCatId)] || [];
  } else {
    ids = Object.keys(State.products);
  }
  let prods = ids.map(id => State.products[String(id)]).filter(Boolean);

  // Apply search
  if (State.searchQuery) {
    const q = State.searchQuery.toLowerCase();
    prods = prods.filter(p => p.name?.toLowerCase().includes(q) || p.nameBn?.includes(q));
  }

  // Sort
  switch (State.sortBy) {
    case 'price-asc':  prods.sort((a,b) => { const av=Number(a.price),bv=Number(b.price); const am=!(av>0)||Number.isNaN(av); const bm=!(bv>0)||Number.isNaN(bv); if(am&&bm)return 0; if(am)return 1; if(bm)return -1; return av-bv; }); break;
    case 'price-desc': prods.sort((a,b) => { const av=Number(a.price),bv=Number(b.price); const am=!(av>0)||Number.isNaN(av); const bm=!(bv>0)||Number.isNaN(bv); if(am&&bm)return 0; if(am)return 1; if(bm)return -1; return bv-av; }); break;
    case 'drop':
      prods.sort((a,b) => {
        const ca = getPriceChange(a.id), cb = getPriceChange(b.id);
        const pa = ca ? ca.pct : 0, pb = cb ? cb.pct : 0;
        return pa - pb;
      }); break;
    case 'new': prods.sort((a,b) => (b.scraped||'').localeCompare(a.scraped||'')); break;
    default: prods.sort((a,b) => (a.name||'').localeCompare(b.name||'')); break;
  }
  return prods;
}

function renderProductsView() {
  const catMap2 = catMap();
  const cat = State.currentCatId ? catMap2[State.currentCatId] : null;

  // Title & breadcrumb
  const title = cat ? cat.Name : 'All Products';
  setText('products-title', title);
  renderBreadcrumb(cat, catMap2);

  // Subcategory sidebar
  renderSubcatSidebar(cat, catMap2);

  const prods = getProductsForView();
  const total = prods.length;
  const pageProds = prods.slice((State.currentPage - 1) * State.pageSize, State.currentPage * State.pageSize);

  document.getElementById('products-grid').innerHTML = pageProds.length
    ? pageProds.map(p => productCardHtml(p)).join('')
    : '<p style="color:var(--text3);padding:2rem;grid-column:1/-1">No products found.</p>';

  renderPagination(Math.ceil(total / State.pageSize));
}

function renderBreadcrumb(cat, map) {
  const bc = document.getElementById('breadcrumb');
  if (!cat) { bc.innerHTML = ''; return; }
  const chain = [];
  let c = cat;
  while (c) { chain.unshift(c); c = map[c.ParentCategoryId]; }
  bc.innerHTML = [
    `<span onclick="App.showView('products')">All</span>`,
    ...chain.map((c, i) =>
      `<span class="breadcrumb-sep">›</span>
       <span onclick="App.showView('products',${c.Id})">${c.Name}</span>`)
  ].join('');
}

function renderSubcatSidebar(cat, map) {
  const sb = document.getElementById('subcat-sidebar');
  const cats = State.categories || [];
  const parentId = cat ? cat.Id : 0;
  const children = cats.filter(c => c.ParentCategoryId === parentId).sort((a,b) => a.DisplayOrder - b.DisplayOrder);
  if (!children.length) { sb.innerHTML = ''; sb.style.display = 'none'; return; }
  sb.style.display = '';
  sb.innerHTML = `<h4>${cat ? cat.Name : 'Categories'}</h4>` +
    `<div class="cat-item ${!State.currentCatId||State.currentCatId===parentId?'active':''}"
       onclick="App.showView('products',${parentId||''})">All</div>` +
    children.map(c => {
      const count = (State.catProducts[String(c.Id)] || []).length;
      return `<div class="cat-item ${State.currentCatId===c.Id?'active':''}"
        onclick="App.showView('products',${c.Id})">${c.Name}${count?` <span style="color:var(--text3);font-size:.7rem">(${count})</span>`:''}
      </div>`;
    }).join('');
}

function renderPagination(pages) {
  const pg = document.getElementById('pagination');
  if (pages <= 1) { pg.innerHTML = ''; return; }
  const cur = State.currentPage;
  let btns = '';
  for (let i = 1; i <= pages; i++) {
    if (i === 1 || i === pages || Math.abs(i - cur) <= 2)
      btns += `<button class="page-btn ${i===cur?'active':''}" onclick="App.goPage(${i})">${i}</button>`;
    else if (btns.slice(-6) !== '…</button>'.slice(-6) && Math.abs(i - cur) > 2)
      btns += `<button class="page-btn" disabled>…</button>`;
  }
  pg.innerHTML = `
    <button class="page-btn" ${cur<=1?'disabled':''} onclick="App.goPage(${cur-1})">‹</button>
    ${btns}
    <button class="page-btn" ${cur>=pages?'disabled':''} onclick="App.goPage(${cur+1})">›</button>`;
}

App.goPage = (n) => { State.currentPage = n; renderProductsView(); window.scrollTo(0, 0); };

// ── Deals view ──────────────────────────────────────────────────
function renderDealsView() {
  const discounted = Object.values(State.products)
    .filter(p => p.mrp > p.price)
    .sort((a, b) => ((b.mrp - b.price) / b.mrp) - ((a.mrp - a.price) / a.mrp));
  document.getElementById('deals-grid').innerHTML = discounted.length
    ? discounted.map(p => productCardHtml(p)).join('')
    : '<p style="color:var(--text3);padding:2rem">No discounted products found.</p>';
}

// ── Analytics ───────────────────────────────────────────────────
function renderAnalytics() {
  const cats = (State.categories || []).filter(c => c.ParentCategoryId === 0).slice(0, 20);
  const catMap2 = catMap();

  // Populate category select
  const sel = document.getElementById('analytics-cat-select');
  sel.innerHTML = cats.map(c => `<option value="${c.Id}">${c.Name}</option>`).join('');
  sel.onchange = () => renderPriceDist(+sel.value);
  renderPriceDist(cats[0]?.Id);

  renderTrendChart();
  renderCatCountChart(cats);
  renderTopDrops();
}

function renderPriceDist(catId) {
  const ids = State.catProducts[String(catId)] || [];
  const prods = ids.map(id => State.products[String(id)]).filter(Boolean);
  const buckets = [0,100,200,300,500,750,1000,2000,5000];
  const labels = buckets.map((v,i) => i < buckets.length-1 ? `৳${v}–${buckets[i+1]}` : `৳${v}+`);
  const counts = buckets.map((lo, i) => prods.filter(p => {
    const hi = buckets[i+1] || Infinity;
    return p.price >= lo && p.price < hi;
  }).length);

  const ctx = document.getElementById('chart-price-dist');
  if (State.charts.priceDist) State.charts.priceDist.destroy();
  State.charts.priceDist = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label: 'Products', data: counts, backgroundColor: 'rgba(0,214,143,0.6)',
        borderColor: 'rgba(0,214,143,1)', borderWidth: 1, borderRadius: 6 }]
    },
    options: chartDefaults({ plugins: { legend: { display: false } }, scales: {
      x: { ticks: { color: '#8896b3' }, grid: { color: 'rgba(255,255,255,0.05)' } },
      y: { ticks: { color: '#8896b3' }, grid: { color: 'rgba(255,255,255,0.05)' } }
    }}),
  });
}

function renderTrendChart() {
  // Aggregate average price across all products per day
  const dailyAvg = {};
  Object.values(State.priceHistory).forEach(hist => {
    hist.forEach(({ d, p }) => {
      if (!dailyAvg[d]) dailyAvg[d] = { sum: 0, count: 0 };
      dailyAvg[d].sum += p;
      dailyAvg[d].count++;
    });
  });
  const days = Object.keys(dailyAvg).sort().slice(-30);
  const avgs = days.map(d => +(dailyAvg[d].sum / dailyAvg[d].count).toFixed(2));

  const ctx = document.getElementById('chart-trend');
  if (State.charts.trend) State.charts.trend.destroy();
  State.charts.trend = new Chart(ctx, {
    type: 'line',
    data: {
      labels: days,
      datasets: [{ label: 'Avg Price (৳)', data: avgs,
        borderColor: '#4d88ff', backgroundColor: 'rgba(77,136,255,0.1)',
        fill: true, tension: 0.4, pointRadius: 3, pointBackgroundColor: '#4d88ff' }]
    },
    options: chartDefaults(),
  });
}

function renderCatCountChart(cats) {
  const catProds = State.catProducts || {};
  const labels = cats.map(c => c.Name.slice(0, 12));
  const counts = cats.map(c => (catProds[String(c.Id)] || []).length);

  const ctx = document.getElementById('chart-cat-count');
  if (State.charts.catCount) State.charts.catCount.destroy();
  State.charts.catCount = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data: counts,
        backgroundColor: cats.map((_, i) => `hsl(${(i * 25) % 360},70%,55%)`),
        borderWidth: 0 }]
    },
    options: { ...chartDefaults(), cutout: '65%' },
  });
}

function renderTopDrops() {
  const drops = Object.entries(State.priceHistory)
    .map(([pid, hist]) => {
      if (hist.length < 2) return null;
      const first = hist[0].p, last = hist[hist.length - 1].p;
      const pct = first ? ((last - first) / first * 100) : 0;
      return { pid, pct, first, last };
    })
    .filter(x => x && x.pct < 0)
    .sort((a, b) => a.pct - b.pct)
    .slice(0, 8);

  const el = document.getElementById('analytics-top-drops');
  el.innerHTML = drops.map(({ pid, pct, first, last }) => {
    const p = State.products[pid];
    if (!p) return '';
    return `<div class="drop-row">
      <img src="${p.imageUrl}" alt="${esc(p.name)}" onerror="this.style.display='none'">
      <div class="drop-info">
        <div class="drop-name">${esc(p.name)}</div>
        <div class="drop-meta">${formatPrice(first)} → ${formatPrice(last)}</div>
      </div>
      <div class="drop-pct">${pct.toFixed(1)}%</div>
    </div>`;
  }).join('') || '<p style="color:var(--text3)">No price drops recorded yet.</p>';
}

// ── Chart defaults ──────────────────────────────────────────────
function chartDefaults(extra = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: '#8896b3', font: { family: 'Inter', size: 11 } } },
      tooltip: { backgroundColor: '#1e2535', titleColor: '#e8ecf4', bodyColor: '#8896b3' }
    },
    scales: {
      x: { ticks: { color: '#8896b3', font: { size: 11 } }, grid: { color: 'rgba(255,255,255,0.05)' } },
      y: { ticks: { color: '#8896b3', font: { size: 11 } }, grid: { color: 'rgba(255,255,255,0.05)' } }
    },
    ...extra
  };
}

// ── Modal ───────────────────────────────────────────────────────
function renderModal(pid) {
  const p = State.products[String(pid)];
  if (!p) return;
  const disc = p.mrp > p.price ? Math.round(((p.mrp - p.price) / p.mrp) * 100) : 0;
  const isWatched = State.watchlist.has(String(pid));
  const ch = getPriceChange(pid);

  document.getElementById('modal-content').innerHTML = `
    <div class="modal-product-header">
      <img class="modal-img" src="${p.imageUrl}" alt="${esc(p.name)}"
           onerror="this.src='';this.style.background='var(--bg3)'">
      <div class="modal-meta">
        <div class="modal-name">${esc(p.name)}</div>
        ${p.subText ? `<div class="modal-subtext">${esc(p.subText)}</div>` : ''}
        <div class="modal-price-big">${formatPrice(p.price)}</div>
        ${p.mrp > p.price ? `<div class="modal-mrp">MRP ${formatPrice(p.mrp)}</div>` : ''}
        <div class="modal-badges">
          ${disc > 0 ? `<span class="badge-pill badge-drop">-${disc}% off</span>` : ''}
          ${ch && ch.delta < 0 ? `<span class="badge-pill badge-low">↓ Price drop ${Math.abs(ch.pct)}%</span>` : ''}
          ${!p.inStock ? `<span class="badge-pill" style="background:var(--red-dim);color:var(--red)">Out of stock</span>` : ''}
        </div>
        <div class="modal-actions">
          <button class="btn-watch ${isWatched ? 'active' : ''}"
            onclick="App.toggleWatchlist(${pid})">
            ${isWatched ? '⭐ Watching' : '☆ Add to Watchlist'}
          </button>
          <a class="btn-chaldal" href="https://chaldal.com/p/${esc(p.slug)}" target="_blank" rel="noopener">
            🛒 Buy on Chaldal
          </a>
        </div>
      </div>
    </div>

    <!-- Price history chart -->
    <div class="modal-chart-section">
      <div class="modal-chart-header">
        <h4>📈 Price History</h4>
        <div class="chart-period-btns">
          <button class="period-btn ${State.activePeriod==='7d'?'active':''}"  onclick="App.setPeriod('7d')">7D</button>
          <button class="period-btn ${State.activePeriod==='30d'?'active':''}" onclick="App.setPeriod('30d')">30D</button>
          <button class="period-btn ${State.activePeriod==='all'?'active':''}" onclick="App.setPeriod('all')">All</button>
        </div>
      </div>
      <div class="chart-wrapper"><canvas id="modal-price-chart"></canvas></div>
      <div class="price-stats-row" id="modal-price-stats"></div>
    </div>

    ${p.longDesc ? `<div class="modal-desc">
      <h4>About this product</h4>
      <p>${esc(p.longDesc)}</p>
    </div>` : ''}
  `;

  renderModalChart(pid);
}

App.setPeriod = (period) => {
  State.activePeriod = period;
  document.querySelectorAll('.period-btn').forEach(b => b.classList.toggle('active', b.textContent.toLowerCase().replace('d','') === period.replace('d','')));
  if (State.charts.modal) { State.charts.modal.destroy(); State.charts.modal = null; }
  renderModalChart(State.activeProductId);
};

function renderModalChart(pid) {
  let hist = getHistory(pid);
  const now = new Date();
  if (State.activePeriod !== 'all') {
    const days = State.activePeriod === '7d' ? 7 : 30;
    const cutoff = new Date(now - days * 864e5).toISOString().slice(0, 10);
    hist = hist.filter(h => h.d >= cutoff);
  }

  const labels = hist.map(h => h.d);
  const prices = hist.map(h => h.p);
  const mrps   = hist.map(h => h.m);

  const ctx = document.getElementById('modal-price-chart');
  if (!ctx) return;

  State.charts.modal = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Price', data: prices, borderColor: '#00d68f', backgroundColor: 'rgba(0,214,143,0.1)',
          fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: '#00d68f', borderWidth: 2 },
        ...(mrps.some(m => m > prices[prices.indexOf(m)])
          ? [{ label: 'MRP', data: mrps, borderColor: '#ff4d6a', borderDash: [5,5],
               borderWidth: 1.5, pointRadius: 0, fill: false }]
          : [])
      ]
    },
    options: { ...chartDefaults(), maintainAspectRatio: false, scales: {
      x: { ticks: { color: '#8896b3', maxTicksLimit: 8, font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } },
      y: { ticks: { color: '#8896b3', callback: v => '৳' + v, font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } }
    }},
  });

  // Stats below chart
  const minP = prices.length ? Math.min(...prices) : 0;
  const maxP = prices.length ? Math.max(...prices) : 0;
  const curP = prices[prices.length - 1] || 0;
  const avgP = prices.length ? (prices.reduce((s,v)=>s+v,0)/prices.length).toFixed(2) : 0;
  const stats = document.getElementById('modal-price-stats');
  if (stats) stats.innerHTML = `
    <div class="price-stat"><div class="price-stat-val green">${formatPrice(minP)}</div><div class="price-stat-lbl">All-time Low</div></div>
    <div class="price-stat"><div class="price-stat-val red">${formatPrice(maxP)}</div><div class="price-stat-lbl">All-time High</div></div>
    <div class="price-stat"><div class="price-stat-val">${formatPrice(avgP)}</div><div class="price-stat-lbl">Average</div></div>
    <div class="price-stat"><div class="price-stat-val ${curP <= minP ? 'green' : ''}">${formatPrice(curP)}</div><div class="price-stat-lbl">Current</div></div>
  `;
}

// ── Watchlist ───────────────────────────────────────────────────
function renderWatchlist() {
  const grid = document.getElementById('watchlist-grid');
  const empty = document.getElementById('watchlist-empty');
  const pids = [...State.watchlist];
  const prods = pids.map(id => State.products[id]).filter(Boolean);
  if (!prods.length) {
    grid.innerHTML = '';
    empty.classList.remove('hidden');
  } else {
    empty.classList.add('hidden');
    grid.innerHTML = prods.map(p => productCardHtml(p)).join('');
  }
}

// ── Search ──────────────────────────────────────────────────────
function bindSearch() {
  const input = document.getElementById('search-input');
  const dd    = document.getElementById('search-dropdown');
  let timer;

  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { dd.classList.add('hidden'); return; }
    timer = setTimeout(() => {
      const results = Object.values(State.products)
        .filter(p => p.name?.toLowerCase().includes(q.toLowerCase()) || p.nameBn?.includes(q))
        .slice(0, 8);
      if (!results.length) { dd.classList.add('hidden'); return; }
      dd.innerHTML = results.map(p => `
        <div class="search-result" onclick="App.openProduct(${p.id});document.getElementById('search-dropdown').classList.add('hidden');document.getElementById('search-input').value=''">
          <img class="search-result-img" src="${p.imageUrl}" alt="${esc(p.name)}" onerror="this.style.display='none'">
          <div>
            <div class="search-result-name">${esc(p.name)}</div>
            <div class="search-result-price">${formatPrice(p.price)}</div>
          </div>
        </div>`).join('');
      dd.classList.remove('hidden');
    }, 250);
  });

  input.addEventListener('blur', () => setTimeout(() => dd.classList.add('hidden'), 200));
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); input.focus(); }
    if (e.key === 'Escape') { App.closeModal(); dd.classList.add('hidden'); input.value = ''; }
  });
}

// ── Events ──────────────────────────────────────────────────────
function bindEvents() {
  // Nav items
  document.querySelectorAll('.nav-item[data-view]').forEach(el =>
    el.addEventListener('click', e => { e.preventDefault(); App.showView(el.dataset.view); }));

  // Modal close
  document.getElementById('modal-close').addEventListener('click', App.closeModal);
  document.getElementById('product-modal').addEventListener('click', e => {
    if (e.target.id === 'product-modal') App.closeModal();
  });

  // Sort
  document.getElementById('sort-select').addEventListener('change', e => {
    State.sortBy = e.target.value;
    State.currentPage = 1;
    if (State.currentView === 'products') renderProductsView();
  });

  // Grid/list toggle
  document.getElementById('grid-view-btn').addEventListener('click', () => {
    document.getElementById('products-grid').classList.remove('list-layout');
    document.getElementById('grid-view-btn').classList.add('active');
    document.getElementById('list-view-btn').classList.remove('active');
  });
  document.getElementById('list-view-btn').addEventListener('click', () => {
    document.getElementById('products-grid').classList.add('list-layout');
    document.getElementById('list-view-btn').classList.add('active');
    document.getElementById('grid-view-btn').classList.remove('active');
  });

  // Theme
  document.getElementById('theme-toggle').addEventListener('click', () => {
    State.themeLight = !State.themeLight;
    localStorage.setItem('theme', State.themeLight ? 'light' : 'dark');
    applyTheme();
  });

  // Refresh
  document.getElementById('refresh-btn').addEventListener('click', async () => {
    toast('Refreshing data…');
    await loadAll();
    buildCategoryTree();
    renderStatRow();
    renderBanners();
    renderHomeGroups();
    renderFreshnessIndicator();
    toast('Data refreshed!', 'success');
  });

  // Sidebar toggle (mobile)
  document.getElementById('sidebar-toggle').addEventListener('click', () =>
    document.getElementById('sidebar').classList.toggle('open'));

  // Watchlist clear
  document.getElementById('clear-watchlist').addEventListener('click', () => {
    State.watchlist.clear();
    localStorage.removeItem('watchlist');
    renderWatchlistCount();
    renderWatchlist();
  });

  bindSearch();
}

// ── Theme ────────────────────────────────────────────────────────
function applyTheme() {
  document.documentElement.dataset.theme = State.themeLight ? 'light' : 'dark';
  document.getElementById('theme-toggle').textContent = State.themeLight ? '☀️' : '🌙';
}

// ── Utilities ────────────────────────────────────────────────────
function setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
function esc(str) { return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function toast(msg, type = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function hideLoading() {
  const el = document.getElementById('loading');
  el.classList.add('hidden');
  setTimeout(() => el.remove(), 500);
}

// ── Boot ─────────────────────────────────────────────────────────
App.init().catch(err => {
  console.error('App init failed:', err);
  document.getElementById('loading').innerHTML = `<div style="color:#ff4d6a;text-align:center;padding:2rem">
    <h2>⚠️ Could not load data</h2>
    <p style="margin-top:.5rem;color:#8896b3">Run <code>runall.bat</code> first to scrape product data.</p>
    <p style="margin-top:.25rem;font-size:.8rem;color:#5a6888">Or run: <code>python scraper.py</code></p>
  </div>`;
});
