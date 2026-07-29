
const IMG = 'https://imrs.foodibd.com/api/v1/image-resize';
const S3 = 'https://s3.ap-southeast-1.amazonaws.com/cdn.foodibd.com';
let charts = {};
let currentSort = 'name';
let currentOrder = 'asc';
let currentPage = 1;
let currentView = 'grid';
let gridSize = 4;
let dealFilter = 'all';
let dealData = {};
let allProducts = [];
let compareMode = false;
let compareCart = JSON.parse(localStorage.getItem('foodie_compare_cart') || '[]');
let newDaysThreshold = 7;
const chartColors = ['#3b82f6','#8b5cf6','#10b981','#f59e0b','#ef4444','#ec4899','#06b6d4','#84cc16','#f97316','#a855f7','#14b8a6','#e11d48','#6366f1','#eab308','#22c55e','#d946ef','#0ea5e9','#f43f5e','#8b5cf6','#10b981','#f59e0b','#ef4444','#ec4899','#06b6d4'];

// ---- Helpers ----
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const fmt = n => n == null ? '—' : `৳${Number(n).toLocaleString()}`;
const API = p => fetch(p).then(r => r.json());

function log(level, msg) {
  const c = $('#consoleOutput');
  const t = new Date().toTimeString().slice(0,8);
  const cls = {info:'info',warn:'warn',error:'error',ok:'ok'}[level] || 'info';
  c.innerHTML += `<div class="line"><span class="time">${t}</span><span class="level ${cls}">${level.toUpperCase()}</span><span>${msg}</span></div>`;
  c.scrollTop = c.scrollHeight;
}
function clearConsole() { $('#consoleOutput').innerHTML = ''; }
function imgSrc(p, w=80) { return `${IMG}?imageUrl=${S3}${p.image_path}&width=${w}`; }

// ---- Grid / Table view ----
function setView(v) {
  currentView = v;
  $('#viewGrid').classList.toggle('active', v === 'grid');
  $('#viewTable').classList.toggle('active', v === 'table');
  $('#productGridView').style.display = v === 'grid' ? 'grid' : 'none';
  $('#productTableView').style.display = v === 'table' ? 'block' : 'none';
  $('#gridSliderWrap').style.display = v === 'grid' ? 'flex' : 'none';
  loadProducts(currentPage);
}
function setGridSize(v) {
  gridSize = parseInt(v);
  $('#gridSizeLabel').textContent = v;
  $('#productGridView').style.gridTemplateColumns = `repeat(${v}, 1fr)`;
  loadProducts(currentPage);
}

// ---- Tab switching ----
$$('.tab').forEach(tab => tab.addEventListener('click', () => {
  $$('.tab').forEach(t => t.classList.remove('active'));
  $$('.panel').forEach(p => p.classList.remove('active'));
  tab.classList.add('active');
  $(`#${tab.dataset.panel}`).classList.add('active');
  log('info', `Switched to ${tab.textContent}`);
}));

// ---- Overview ----
async function loadOverview() {
  log('info', 'Loading overview...');
  const d = await API('/api/analytics');
  const stats = $('#overviewStats');
  stats.innerHTML = `
    <div class="card"><h3>Total Products</h3><div class="stat">${d.total_products}</div></div>
    <div class="card"><h3>Categories</h3><div class="stat">${d.total_categories}</div></div>
    <div class="card"><h3>Avg Price</h3><div class="stat">${fmt(d.avg_price)}</div></div>
    <div class="card"><h3>In Stock</h3><div class="stat" style="color:var(--green)">${d.in_stock}</div><div class="text-xs text-dim">${d.out_of_stock} out of stock</div></div>
  `;

  // Category chart
  const catData = d.category_stats;
  destroyChart('catChart');
  charts.catChart = new Chart($('#catChart'), {
    type: 'bar',
    data: {
      labels: catData.map(c => c.category_name),
      datasets: [{label:'Products', data: catData.map(c => c.count), backgroundColor: 'rgba(59,130,246,.6)', borderRadius: 4}]
    },
    options: {responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{ticks:{color:'#6b7280',font:{size:10},maxRotation:45}},y:{ticks:{color:'#6b7280'},grid:{color:'#1e1e2e'}}}}
  });

  // Price distribution
  destroyChart('priceDistChart');
  charts.priceDistChart = new Chart($('#priceDistChart'), {
    type: 'bar',
    data: {
      labels: d.price_buckets.map(b => b.bucket),
      datasets: [{label:'Products', data: d.price_buckets.map(b => b.count), backgroundColor: 'rgba(139,92,246,.6)', borderRadius: 4}]
    },
    options: {responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{ticks:{color:'#6b7280'}},y:{ticks:{color:'#6b7280'},grid:{color:'#1e1e2e'}}}}
  });

  // Top expensive
  const topE = $('#topExpensive');
  topE.innerHTML = d.top_expensive.map(p => `
    <div class="item" onclick="showPH(${p.product_id},'${p.name.replace(/'/g,"\\'")}')">
      <span>${p.name}</span><span class="price">${fmt(p.discounted_price)}</span>
    </div>
  `).join('');

  // Top discounts
  const topD = $('#topDiscounts');
  topD.innerHTML = d.top_discounts.map(p => `
    <div class="item" onclick="showPH(${p.product_id},'${p.name.replace(/'/g,"\\'")}')">
      <span>${p.name}</span>
      <span><span class="old-price">${fmt(p.base_price)}</span> <span class="discount">-${p.is_discount_in_perc ? p.discount+'%' : fmt(p.discount)}</span></span>
    </div>
  `).join('');

  if (d.scrape_runs.length) {
    const r = d.scrape_runs[0];
    $('#lastRun').textContent = `Last run: ${r.finished_at ? new Date(r.finished_at).toLocaleString() : 'Running...'} (${r.products_scraped || '?'} products)`;
  }

  log('ok', `Overview loaded: ${d.total_products} products, ${d.total_categories} categories`);
}

// ---- Products ----
async function loadProducts(page=1) {
  currentPage = page;
  const q = $('#searchInput').value;
  const cat = $('#catFilter').value;
  const sort = $('#sortSelect').value;
  const order = $('#orderSelect').value;
  const minP = $('#minPrice').value;
  const maxP = $('#maxPrice').value;
  const stock = $('#stockFilter').value;

  currentSort = sort; currentOrder = order;

  const params = new URLSearchParams({page, per_page:200, sort, order});
  if (q) params.set('q', q);
  if (cat) params.set('category', cat);
  if (minP) params.set('min_price', minP);
  if (maxP) params.set('max_price', maxP);
  if (stock) params.set('in_stock', stock);

  log('info', `Loading products page ${page} (q="${q}", cat=${cat||'all'}, deal=${dealFilter})`);
  const d = await API(`/api/products?${params}`);

  // Store all loaded products for cart/compare
  allProducts = d.data;

  // Apply deal filter client-side (we loaded 200 per page for filtering)
  let filtered = filterByDeal(d.data);
  const totalFiltered = filtered.length;

  // Paginate filtered results
  const perPage = 50;
  const totalPages = Math.ceil(totalFiltered / perPage);
  const startIdx = (page - 1) * perPage;
  const pageData = filtered.slice(startIdx, startIdx + perPage);

  $('#resultCount').textContent = `Showing ${Math.min(startIdx+1, totalFiltered)}-${Math.min(startIdx+perPage, totalFiltered)} of ${totalFiltered} products${dealFilter !== 'all' ? ' (filtered)' : ''}`;

  const tbody = $('#productBody');
  tbody.innerHTML = pageData.map(p => `
    <tr>
      <td><img class="thumb" src="${imgSrc(p)}" loading="lazy" onerror="this.style.display='none'"></td>
      <td><div class="product-name"><span>${p.name}</span></div></td>
      <td class="text-sm text-dim">${p.sku}</td>
      <td><span class="badge cat">${p.category_name}</span></td>
      <td>${p.base_price != p.discounted_price ? `<span class="old-price">${fmt(p.base_price)}</span>` : ''}</td>
      <td class="price">${fmt(p.discounted_price)}</td>
      <td>${p.discount > 0 ? `<span class="discount">${p.is_discount_in_perc ? p.discount+'%' : fmt(p.discount)}</span>` : '—'}</td>
      <td><span class="badge ${p.has_stock ? 'stock' : 'oos'}">${p.has_stock ? 'In Stock' : 'OOS'}</span></td>
      <td><button onclick="showPH(${p.product_id},'${p.name.replace(/'/g,"\\'")}')" style="font-size:.75rem;padding:4px 8px">History</button></td>
    </tr>
  `).join('');

  const grid = $('#productGridView');
  grid.style.gridTemplateColumns = `repeat(${gridSize}, 1fr)`;
  grid.innerHTML = pageData.map(p => `
    <div class="grid-card ${compareMode && compareCart.includes(p.product_id) ? 'selected' : ''}" onclick="${compareMode ? `addToCart(${p.product_id})` : `showPH(${p.product_id},'${p.name.replace(/'/g,"\\'")}')`}">
      ${getDealBadge(p)}
      <img src="${imgSrc(p, 200)}" loading="lazy" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22><rect fill=%22%231a1a2e%22 width=%22100%22 height=%22100%22/><text x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 dy=%22.3em%22 fill=%22%236b7280%22 font-size=%2212%22>No Image</text></svg>'">
      <div class="name" title="${p.name}">${p.name}</div>
      <div class="cat">${p.category_name}</div>
      <div class="price-row">
        <span class="sale">${fmt(p.discounted_price)}</span>
        ${p.discount > 0 ? `<span class="orig">${fmt(p.base_price)}</span><span class="disc">${p.is_discount_in_perc ? '-'+p.discount+'%' : '-'+fmt(p.discount)}</span>` : ''}
      </div>
    </div>
  `).join('');

  // Pagination
  const pag = $('#pagination');
  let html = '';
  if (page > 1) html += `<button onclick="loadProducts(${page-1})">Prev</button>`;
  const start = Math.max(1, page-3), end = Math.min(totalPages, page+3);
  for (let i = start; i <= end; i++) {
    html += `<button class="${i===page?'current':''}" onclick="loadProducts(${i})">${i}</button>`;
  }
  if (page < totalPages) html += `<button onclick="loadProducts(${page+1})">Next</button>`;
  html += `<span class="text-sm text-dim" style="margin-left:8px">Page ${page}/${totalPages || 1}</span>`;
  pag.innerHTML = html;

  log('ok', `Loaded ${pageData.length} products (${totalFiltered} total)`);
}

function sortTable(field) {
  const sel = $('#sortSelect');
  if (sel.value === field) {
    $('#orderSelect').value = $('#orderSelect').value === 'asc' ? 'desc' : 'asc';
  } else {
    sel.value = field;
    $('#orderSelect').value = 'asc';
  }
  loadProducts(1);
}

// ---- Analytics ----
async function loadAnalytics() {
  log('info', 'Loading analytics...');
  const d = await API('/api/analytics');

  // KPIs
  const avgDiscount = d.total_discounted > 0 ? Math.round(d.total_discounted / d.total_products * 100) : 0;
  const inStockPct = Math.round(d.in_stock / d.total_products * 100);
  const totalValue = d.category_stats.reduce((s, c) => s + c.total_value, 0);
  const priceSpread = d.max_price - d.min_price;
  const kpis = [
    {lbl:'Total Products', val:d.total_products, cls:'blue'},
    {lbl:'Categories', val:d.total_categories, cls:'purple'},
    {lbl:'Avg Price', val:fmt(d.avg_price), sub:`Spread: ${fmt(priceSpread)}`, cls:'green'},
    {lbl:'In Stock', val:`${inStockPct}%`, sub:`${d.in_stock} / ${d.total_products}`, cls:'green'},
    {lbl:'Discounted', val:`${avgDiscount}%`, sub:`${d.total_discounted} items`, cls:'red'},
    {lbl:'Est. Total Value', val:`৳${(totalValue).toLocaleString(undefined,{maximumFractionDigits:0})}`, sub:`Across ${d.total_categories} categories`, cls:'yellow'}
  ];
  $('#kpiRow').innerHTML = kpis.map(k => `<div class="kpi ${k.cls}"><div class="lbl">${k.lbl}</div><div class="val">${k.val}</div>${k.sub?`<div class="sub">${k.sub}</div>`:''}</div>`).join('');

  // Revenue by category (bar)
  destroyChart('catRevenueChart');
  charts.catRevenueChart = new Chart($('#catRevenueChart'), {
    type: 'bar',
    data: {
      labels: d.category_stats.map(c => c.category_name),
      datasets: [{label:'Est. Revenue ৳', data: d.category_stats.map(c => c.total_value), backgroundColor: chartColors.slice(0, d.category_stats.length), borderRadius: 4}]
    },
    options: {indexAxis:'y', responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{ticks:{color:'#6b7280',callback:v=>'৳'+v.toLocaleString()},grid:{color:'#1e1e2e'}},y:{ticks:{color:'#6b7280',font:{size:10}}}}}
  });

  // Stock pie
  destroyChart('stockPie');
  charts.stockPie = new Chart($('#stockPie'), {
    type: 'doughnut',
    data: {
      labels: ['In Stock', 'Out of Stock'],
      datasets: [{data:[d.in_stock, d.out_of_stock], backgroundColor:['rgba(16,185,129,.7)','rgba(239,68,68,.7)'], borderWidth:0, hoverOffset:8}]
    },
    options: {responsive:true, maintainAspectRatio:false, cutout:'60%', plugins:{legend:{labels:{color:'#e0e0e8',padding:16}}}}
  });

  // Category price comparison (min/avg/max grouped bar)
  destroyChart('catCompareChart');
  const shortNames = d.category_stats.map(c => c.category_name.length > 12 ? c.category_name.slice(0,12)+'…' : c.category_name);
  charts.catCompareChart = new Chart($('#catCompareChart'), {
    type: 'bar',
    data: {
      labels: shortNames,
      datasets: [
        {label:'Min', data:d.category_stats.map(c=>c.min_price), backgroundColor:'rgba(16,185,129,.5)', borderRadius:2},
        {label:'Avg', data:d.category_stats.map(c=>c.avg_price), backgroundColor:'rgba(59,130,246,.6)', borderRadius:2},
        {label:'Max', data:d.category_stats.map(c=>c.max_price), backgroundColor:'rgba(239,68,68,.5)', borderRadius:2}
      ]
    },
    options: {responsive:true, maintainAspectRatio:false, plugins:{legend:{labels:{color:'#e0e0e8'}}}, scales:{x:{ticks:{color:'#6b7280',font:{size:9},maxRotation:45}},y:{ticks:{color:'#6b7280',callback:v=>'৳'+v},grid:{color:'#1e1e2e'}}}}
  });

  // Discount depth (histogram-like bar)
  destroyChart('discountDepthChart');
  const depthBuckets = {};
  d.top_discounts.forEach(p => {
    const pct = p.is_discount_in_perc ? p.discount : (p.base_price > 0 ? Math.round((1 - p.discounted_price/p.base_price)*100) : 0);
    const bucket = pct < 5 ? '0-5%' : pct < 10 ? '5-10%' : pct < 20 ? '10-20%' : pct < 30 ? '20-30%' : pct < 50 ? '30-50%' : '50%+';
    depthBuckets[bucket] = (depthBuckets[bucket] || 0) + 1;
  });
  const dbLabels = ['0-5%','5-10%','10-20%','20-30%','30-50%','50%+'];
  const dbData = dbLabels.map(b => depthBuckets[b] || 0);
  charts.discountDepthChart = new Chart($('#discountDepthChart'), {
    type: 'bar',
    data: {
      labels: dbLabels,
      datasets: [{label:'Products', data:dbData, backgroundColor:['#10b981','#06b6d4','#3b82f6','#8b5cf6','#f59e0b','#ef4444'], borderRadius:4}]
    },
    options: {responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{ticks:{color:'#6b7280'}},y:{ticks:{color:'#6b7280'},grid:{color:'#1e1e2e'}}}}
  });

  // Discount pie
  destroyChart('discountPie');
  charts.discountPie = new Chart($('#discountPie'), {
    type: 'doughnut',
    data: {
      labels: ['Discounted', 'Full Price'],
      datasets: [{data:[d.total_discounted, d.total_products-d.total_discounted], backgroundColor:['rgba(239,68,68,.7)','rgba(59,130,246,.6)'], borderWidth:0, hoverOffset:8}]
    },
    options: {responsive:true, maintainAspectRatio:false, cutout:'60%', plugins:{legend:{labels:{color:'#e0e0e8',padding:16}}}}
  });

  // Buckets
  destroyChart('bucketChart');
  charts.bucketChart = new Chart($('#bucketChart'), {
    type: 'bar',
    data: {
      labels: d.price_buckets.map(b=>b.bucket),
      datasets: [{label:'Count', data: d.price_buckets.map(b=>b.count), backgroundColor:['#3b82f6','#8b5cf6','#10b981','#f59e0b','#ef4444','#ec4899'], borderRadius:4}]
    },
    options: {responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{ticks:{color:'#6b7280'}},y:{ticks:{color:'#6b7280'},grid:{color:'#1e1e2e'}}}}
  });

  // Daily chart
  destroyChart('dailyChart');
  if (d.daily_counts.length > 0) {
    charts.dailyChart = new Chart($('#dailyChart'), {
      type: 'line',
      data: {
        labels: d.daily_counts.map(c=>c.day),
        datasets: [{label:'Products Scraped', data:d.daily_counts.map(c=>c.count), borderColor:'var(--accent)', backgroundColor:'rgba(59,130,246,.1)', fill:true, tension:.3, pointRadius:4, pointBackgroundColor:'var(--accent)'}]
      },
      options: {responsive:true, maintainAspectRatio:false, plugins:{legend:{labels:{color:'#e0e0e8'}}}, scales:{x:{ticks:{color:'#6b7280'}},y:{ticks:{color:'#6b7280'},grid:{color:'#1e1e2e'}}}}
    });
  }

  // Category avg price
  destroyChart('catAvgChart');
  charts.catAvgChart = new Chart($('#catAvgChart'), {
    type: 'bar',
    data: {
      labels: shortNames,
      datasets: [{label:'Avg ৳', data: d.category_stats.map(c => c.avg_price), backgroundColor: 'rgba(16,185,129,.6)', borderRadius: 4}]
    },
    options: {indexAxis:'y', responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{ticks:{color:'#6b7280'},grid:{color:'#1e1e2e'}},y:{ticks:{color:'#6b7280',font:{size:11}}}}}
  });

  // Leaderboard: expensive
  const maxPrice = d.top_expensive.length ? d.top_expensive[0].discounted_price : 1;
  $('#leaderExpensive').innerHTML = d.top_expensive.map((p, i) => {
    const rankCls = i===0?'gold':i===1?'silver':i===2?'bronze':'';
    const barW = Math.round(p.discounted_price / maxPrice * 100);
    return `<div class="row"><span class="rank ${rankCls}">${i+1}</span><span style="flex:2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.name}</span><span class="bar-wrap"><span class="bar" style="width:${barW}%;background:var(--accent)"></span></span><span class="price" style="min-width:70px;text-align:right">${fmt(p.discounted_price)}</span></div>`;
  }).join('');

  // Leaderboard: discounts
  const maxDisc = d.top_discounts.length ? Math.max(...d.top_discounts.map(p => p.discount)) : 1;
  $('#leaderDiscounts').innerHTML = d.top_discounts.map((p, i) => {
    const rankCls = i===0?'gold':i===1?'silver':i===2?'bronze':'';
    const barW = Math.round(p.discount / maxDisc * 100);
    return `<div class="row"><span class="rank ${rankCls}">${i+1}</span><span style="flex:2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.name}</span><span class="bar-wrap"><span class="bar" style="width:${barW}%;background:var(--red)"></span></span><span class="discount" style="min-width:50px;text-align:right">${p.is_discount_in_perc ? p.discount+'%' : fmt(p.discount)}</span></div>`;
  }).join('');

  // Price spread heatmap
  const hDiv = $('#priceHeatmap');
  const pcts = ['P10','P25','P50','P75','P90'];
  let hHtml = '<div style="display:grid;grid-template-columns:100px repeat(5,1fr);gap:2px;font-size:.7rem">';
  hHtml += '<div></div>' + pcts.map(p => `<div class="heatmap-header">${p}</div>`).join('');
  d.category_stats.forEach((c, ci) => {
    const range = c.max_price - c.min_price || 1;
    const vals = [.1,.25,.5,.75,.9].map(pct => c.min_price + range * pct);
    hHtml += `<div style="padding:4px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${c.category_name}">${c.category_name.length>12?c.category_name.slice(0,12)+'…':c.category_name}</div>`;
    vals.forEach(v => {
      const intensity = Math.min(1, v / (d.avg_price * 2));
      const r = Math.round(59 + intensity * 180);
      const g = Math.round(130 - intensity * 60);
      const b = Math.round(246 - intensity * 180);
      hHtml += `<div class="heatmap-cell" style="background:rgba(${r},${g},${b},.4)" title="${c.category_name}: ৳${Math.round(v)}"></div>`;
    });
  });
  hHtml += '</div>';
  hDiv.innerHTML = hHtml;

  // Correlations / key metrics
  const corrMetrics = [
    {label:'Discount Rate', value:`${avgDiscount}%`, cls:'red'},
    {label:'Avg Category Size', value:Math.round(d.total_products/d.total_categories), cls:'blue'},
    {label:'Price Coefficient', value:(priceSpread / d.avg_price).toFixed(1)+'x', sub:'Spread / Avg', cls:'purple'},
    {label:'Premium Ratio', value:`${d.top_expensive.filter(p=>p.discounted_price>500).length}/${d.total_products}`, sub:'Products > ৳500', cls:'yellow'},
    {label:'Avg Discount', value: d.total_discounted>0 ? fmt(Math.round(d.top_discounts.reduce((s,p)=>s+p.discount,0)/Math.max(d.top_discounts.length,1))) : '—', cls:'green'},
    {label:'Stock Rate', value:`${inStockPct}%`, cls:'green'}
  ];
  $('#correlationGrid').innerHTML = corrMetrics.map(m => `<div class="correlation-card"><div class="label">${m.label}</div><div class="value" style="color:var(--${m.cls==='blue'?'accent':m.cls==='purple'?'accent2':m.cls})">${m.value}</div>${m.sub?`<div style="font-size:.65rem;color:var(--dim)">${m.sub}</div>`:''}</div>`).join('');

  // Category stats table
  const tb = $('#catStatsBody');
  tb.innerHTML = d.category_stats.map(c => {
    const spread = (c.max_price - c.min_price).toFixed(0);
    const discPct = c.count > 0 ? Math.round(c.discounted / c.count * 100) : 0;
    return `<tr>
      <td><span class="badge cat">${c.category_name}</span></td>
      <td>${c.count}</td>
      <td class="price">${fmt(c.avg_price)}</td>
      <td>${fmt(c.min_price)}</td>
      <td>${fmt(c.max_price)}</td>
      <td class="text-dim">${fmt(spread)}</td>
      <td>${fmt(c.total_value)}</td>
      <td><span style="color:${discPct>50?'var(--red)':discPct>25?'var(--yellow)':'var(--green)'}">${discPct}%</span></td>
      <td><span style="color:var(--green)">${inStockPct}%</span></td>
    </tr>`;
  }).join('');

  log('ok', `Analytics loaded: ${d.category_stats.length} categories, ${d.total_products} products`);
}

// ---- Price History ----
let phChart = null;

async function searchForHistory() {
  const q = $('#phSearch').value;
  if (!q) return;
  log('info', `Searching for price history: "${q}"`);
  const results = await API(`/api/search?q=${encodeURIComponent(q)}&limit=10`);
  const div = $('#phResults');
  if (!results.length) { div.innerHTML = '<div class="empty">No products found</div>'; return; }
  div.innerHTML = results.map(p => `
    <div class="flex" style="padding:10px;border-bottom:1px solid var(--border);cursor:pointer" onclick="showPH(${p.product_id},'${p.name.replace(/'/g,"\\'")}')">
      <img class="thumb" src="${imgSrc(p)}" loading="lazy" onerror="this.style.display='none'">
      <div style="flex:1"><strong>${p.name}</strong><div class="text-xs text-dim">${p.sku} | ${p.category_name}</div></div>
      <div class="price">${fmt(p.discounted_price)}</div>
    </div>
  `).join('');

  // Auto-show first result
  if (results.length) showPH(results[0].product_id, results[0].name);
}

async function showPH(productId, name) {
  log('info', `Loading price history for: ${name} (${productId})`);
  let data;
  try {
    const resp = await API(`/api/parquet/price-history/${productId}?days=365`);
    data = resp.data || [];
    if (data.length) log('info', `Loaded ${data.length} points from Parquet`);
  } catch(e) {
    log('warn', `Parquet unavailable, falling back to SQLite`);
    data = await API(`/api/price-history/${productId}?days=365`);
  }

  $('#phTitle').textContent = `Price History: ${name}`;
  $('#phChart').style.display = 'block';

  if (phChart) phChart.destroy();
  phChart = new Chart($('#phCanvas'), {
    type: 'line',
    data: {
      labels: data.map(d => new Date(d.scraped_at).toLocaleDateString()),
      datasets: [
        {label:'Sale Price', data: data.map(d => d.discounted_price), borderColor:'#10b981', backgroundColor:'rgba(16,185,129,.1)', fill:true, tension:.3, pointRadius:4},
        {label:'Base Price', data: data.map(d => d.base_price), borderColor:'#6b7280', borderDash:[5,5], tension:.3, pointRadius:2}
      ]
    },
    options: {responsive:true, maintainAspectRatio:false, plugins:{legend:{labels:{color:'#e0e0e8'}}}, scales:{x:{ticks:{color:'#6b7280'}},y:{ticks:{color:'#6b7280'},grid:{color:'#1e1e2e'}}}}
  });

  // Price changes
  if (data.length >= 2) {
    const first = data[0], last = data[data.length-1];
    if (first.discounted_price !== last.discounted_price) {
      log('info', `Price changed: ${fmt(first.discounted_price)} -> ${fmt(last.discounted_price)}`);
    }
  }

  // Show changes table
  loadPriceChanges();
}

async function loadPriceChanges() {
  const changes = await API('/api/price-changes');
  const div = $('#phChanges');
  if (!changes.length) { div.style.display = 'none'; return; }
  div.style.display = 'block';
  const tb = $('#phChangesBody');
  tb.innerHTML = changes.map(c => `
    <tr>
      <td>${c.name}</td>
      <td><span class="badge cat">${c.category_name}</span></td>
      <td>${fmt(c.old_price)}</td>
      <td>${fmt(c.new_price)}</td>
      <td style="color:${c.price_diff > 0 ? 'var(--red)' : 'var(--green)'}">${c.price_diff > 0 ? '+' : ''}${fmt(c.price_diff)}</td>
      <td class="text-xs text-dim">${new Date(c.old_date).toLocaleDateString()}</td>
    </tr>
  `).join('');
}

// ---- Categories ----
async function loadCategories() {
  log('info', 'Loading categories...');
  const cats = await API('/api/categories');

  // Populate filter
  const sel = $('#catFilter');
  sel.innerHTML = '<option value="">All Categories</option>' + cats.map(c => `<option value="${c.category_id}">${c.category_name} (${c.product_count})</option>`).join('');

  // Cards
  const cards = $('#catCards');
  cards.innerHTML = cats.map(c => `
    <div class="card" style="cursor:pointer" onclick="$('#catFilter').value='${c.category_id}';switchTab('products');loadProducts(1)">
      <h3>${c.category_name}</h3>
      <div class="stat sm">${c.product_count} products</div>
      <div class="text-sm mt-8">Avg: <span class="price">${fmt(c.avg_price)}</span></div>
      <div class="text-xs text-dim">${c.discounted_count} discounted</div>
    </div>
  `).join('');

  log('ok', `Loaded ${cats.length} categories`);
}

// ---- Debug ----
async function pollLogs() {
  log('info', 'Polling latest log file...');
  try {
    const r = await fetch('/api/analytics');
    const d = await r.json();
    log('ok', `API alive. ${d.total_products} products in database`);
    if (d.scrape_runs.length) {
      const runs = d.scrape_runs;
      const tb = $('#runsBody');
      tb.innerHTML = runs.map(r => `
        <tr>
          <td>${r.id}</td>
          <td class="text-sm">${r.started_at ? new Date(r.started_at).toLocaleString() : '—'}</td>
          <td class="text-sm">${r.finished_at ? new Date(r.finished_at).toLocaleString() : '—'}</td>
          <td>${r.products_scraped || '—'}</td>
          <td>${r.categories_scraped || '—'}</td>
          <td><span class="badge ${r.status==='completed'?'stock':'oos'}">${r.status}</span></td>
        </tr>
      `).join('');
    }
  } catch(e) {
    log('error', `API unreachable: ${e.message}`);
  }
}

// ---- Utilities ----
function destroyChart(id) { if (charts[id]) { charts[id].destroy(); delete charts[id]; } }

function switchTab(name) {
  $$('.tab').forEach(t => t.classList.remove('active'));
  $$('.panel').forEach(p => p.classList.remove('active'));
  $(`.tab[data-panel="${name}"]`).classList.add('active');
  $(`#${name}`).classList.add('active');
}

// ---- Scraper ----
async function triggerScrape() {
  const btn = $('#scrapeBtn');
  btn.disabled = true; btn.textContent = 'Starting...';
  try {
    const r = await fetch('/api/scrape', {method:'POST'});
    const d = await r.json();
    if (d.status === 'already_running') {
      log('warn', 'Scraper already running');
    } else {
      log('ok', 'Scraper started');
      pollScraperStatus();
    }
  } catch(e) { log('error', `Scraper trigger failed: ${e.message}`); }
  btn.disabled = false; btn.textContent = 'Run Scraper';
}

async function pollScraperStatus() {
  const dot = $('#scraperDot');
  const txt = $('#scraperText');
  const poll = async () => {
    try {
      const r = await fetch('/api/scrape/status');
      const s = await r.json();
      if (s.running) {
        dot.className = 'dot running'; txt.textContent = 'Scraping...';
        setTimeout(poll, 3000);
      } else {
        dot.className = 'dot done'; txt.textContent = s.returncode === 0 ? 'Done' : 'Failed';
        log(s.returncode === 0 ? 'ok' : 'error', `Scraper finished (code ${s.returncode})`);
        if (s.returncode === 0) { await refreshAll(); }
      }
    } catch(e) { dot.className = 'dot idle'; txt.textContent = 'Error'; }
  };
  poll();
}

// ---- Deal classification ----
async function reloadDealData() {
  newDaysThreshold = parseInt($('#newDaysInput').value) || 7;
  log('info', `Loading deal classification (new=${newDaysThreshold}d)...`);
  const d = await API(`/api/deal-classification?new_days=${newDaysThreshold}`);
  dealData = {};
  d.forEach(p => dealData[p.product_id] = p);

  // Update counts
  let great=0, good=0, wait=0, atl=0, nw=0, pc=0;
  d.forEach(p => {
    if (p.deal === 'great_deal') great++;
    else if (p.deal === 'good_buy') good++;
    else if (p.deal === 'wait') wait++;
    if (p.is_atl) atl++;
    if (p.is_new) nw++;
    if (p.pc_diff !== null && p.pc_diff !== undefined) pc++;
  });
  $('#cntGreat').textContent = great;
  $('#cntGood').textContent = good;
  $('#cntWait').textContent = wait;
  $('#cntATL').textContent = atl;
  $('#cntNew').textContent = nw;
  $('#cntPC').textContent = pc;
  log('ok', `Deal data: ${d.length} products classified`);
}

function setDealFilter(f) {
  dealFilter = dealFilter === f ? 'all' : f;
  document.querySelectorAll('.intel-btn[data-filter]').forEach(b => b.classList.toggle('active', b.dataset.filter === dealFilter));
  loadProducts(1);
}

function getDealBadge(p) {
  const dd = dealData[p.product_id];
  if (!dd) return '';
  if (dd.pc_diff !== null && dd.pc_diff !== undefined) {
    return dd.pc_diff < 0
      ? `<span class="deal-badge pc-down">▼${Math.abs(dd.pc_pct||0).toFixed(0)}%</span>`
      : `<span class="deal-badge pc-up">▲${(dd.pc_pct||0).toFixed(0)}%</span>`;
  }
  if (dd.is_atl) return '<span class="deal-badge atl">ALL TIME LOW</span>';
  if (dd.is_new) return '<span class="deal-badge new">NEW</span>';
  if (dd.deal === 'great_deal') return `<span class="deal-badge great">▼${(dd.deal_pct||0).toFixed(0)}% OFF</span>`;
  if (dd.deal === 'good_buy') return `<span class="deal-badge good">▼${(dd.deal_pct||0).toFixed(0)}%</span>`;
  if (dd.deal === 'wait') return '<span class="deal-badge wait">WAIT</span>';
  return '';
}

function filterByDeal(items) {
  if (dealFilter === 'all') return items;
  return items.filter(p => {
    const dd = dealData[p.product_id];
    if (!dd) return false;
    switch (dealFilter) {
      case 'great_deal': return dd.deal === 'great_deal';
      case 'good_buy': return dd.deal === 'good_buy';
      case 'wait': return dd.deal === 'wait';
      case 'all_time_low': return dd.is_atl;
      case 'new_items': return dd.is_new;
      case 'price_change': return dd.pc_diff !== null && dd.pc_diff !== undefined;
      default: return true;
    }
  });
}

// ---- Compare Cart ----
function toggleCompareMode() {
  compareMode = !compareMode;
  $('#compareModeBtn').classList.toggle('active', compareMode);
  log('info', compareMode ? 'Compare mode ON - click products to add' : 'Compare mode OFF');
}

function addToCart(productId) {
  if (!compareMode) return;
  if (compareCart.includes(productId)) {
    compareCart = compareCart.filter(id => id !== productId);
  } else {
    compareCart.push(productId);
  }
  localStorage.setItem('foodie_compare_cart', JSON.stringify(compareCart));
  $('#cartCount').textContent = compareCart.length;
  log('info', `Cart: ${compareCart.length} items`);
}

function openCompareCart() {
  if (compareCart.length === 0) { log('warn', 'Cart is empty'); return; }
  switchTab('price-history');
  const names = compareCart.map(id => {
    const p = allProducts.find(x => x.product_id === id);
    return p ? p.name : id;
  }).join(', ');
  log('info', `Compare cart: ${names}`);
  // Auto-search first cart item
  const first = allProducts.find(p => p.product_id === compareCart[0]);
  if (first) { $('#phSearch').value = first.name; searchForHistory(); }
}

// ---- Mean Analysis ----
async function runMeanAnalysis() {
  const start = $('#meanStartDate').value;
  const end = $('#meanEndDate').value;
  if (!start || !end) { log('warn', 'Select date range first'); return; }
  log('info', `Mean analysis: ${start} to ${end}`);
  const d = await API(`/api/mean-analysis?start_date=${start}&end_date=${end}`);
  if (!d.length) { $('#meanResult').textContent = 'No data in range'; return; }
  const avgMean = Math.round(d.reduce((s,r) => s + r.mean_price, 0) / d.length);
  const totalProducts = d.length;
  const highSpread = d.filter(r => (r.max_price - r.min_price) > r.mean_price * 0.2).length;
  $('#meanResult').innerHTML = `${totalProducts} products | Avg mean: ৳${avgMean} | ${highSpread} with >20% spread`;
  log('ok', `Mean analysis: ${totalProducts} products, avg ৳${avgMean}`);
}

// ---- Refresh all ----
async function refreshAll() {
  log('info', 'Refreshing all data...');
  await Promise.all([loadOverview(), loadCategories()]);
  await reloadDealData();
  await loadProducts(1);
  await loadAnalytics();
  log('ok', 'All data refreshed');
}

// ---- Keyboard shortcuts ----
document.addEventListener('keydown', e => {
  if (e.key === '/' && !['INPUT','TEXTAREA'].includes(document.activeElement.tagName)) {
    e.preventDefault(); $('#searchInput').focus(); switchTab('products');
  }
  if (e.key === 'Escape') document.activeElement.blur();
});

// ---- Init ----
(async () => {
  log('info', 'Initializing dashboard...');

  // Set mean analysis default dates (last 30 days)
  const today = new Date();
  const thirtyAgo = new Date(today); thirtyAgo.setDate(today.getDate() - 30);
  $('#meanEndDate').value = today.toISOString().split('T')[0];
  $('#meanStartDate').value = thirtyAgo.toISOString().split('T')[0];

  try {
    await refreshAll();
    log('ok', 'Dashboard ready');

    // Auto-trigger scraper if DB is empty or old
    const analytics = await API('/api/analytics');
    if (analytics.total_products === 0) {
      log('warn', 'No products in DB — auto-starting scraper');
      await triggerScrape();
    }
  } catch(e) {
    log('error', `Init failed: ${e.message}. Is the scraper DB populated?`);
  }

  // Poll scraper status on load
  pollScraperStatus();
})();
