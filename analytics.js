// GroceryGOD Analytics — a Vercel-style analytics page over the public parquet snapshots.
// Everything is computed in the browser with DuckDB-WASM; nothing leaves the page.
import * as duckdb from 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm';

const STORES = {
    shwapno: 'Shwapno', chaldal: 'Chaldal', meenabazar: 'Meena Bazar', othoba: 'Othoba',
    metromart: 'Metro Mart', unimart: 'Unimart', shotejbazar: 'ShotejBazar', foodi: 'FooDIE'
};
const RANGES = ['7', '30', '90', 'all'];
const PREMIUM_RANGES = new Set(['90', 'all']);
const KPIS = [
    { id: 'index', label: 'Price index', title: 'Price index (base 100 at range start)' },
    { id: 'listed', label: 'Listed items', title: 'Items listed in stock per day' },
    { id: 'moves', label: 'Price moves', title: 'Price hikes and drops per day' },
    { id: 'instock', label: 'In-stock rate', title: 'Share of tracked items in stock' },
    { id: 'new', label: 'New listings', title: 'Items seen for the first time' }
];
// A day-over-day ratio outside e^±1.1 (~3x) is almost always a unit/pack-size glitch, not a price move.
const MAX_LOG_MOVE = 1.1;

const $ = id => document.getElementById(id);
const store = {
    get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (_) {} }
};
const premium = store.get('god_premium_unlocked') === '1';

const state = {
    store: 'all', range: '30', kpi: 'index',
    tabs: { stores: 'items', categories: 'items', movers: 'down', stock: 'oos', deals: 'deep' }
};
(() => {
    const qs = new URLSearchParams(location.search);
    if (STORES[qs.get('store')]) state.store = qs.get('store');
    if (RANGES.includes(qs.get('range'))) state.range = qs.get('range');
    if (KPIS.some(k => k.id === qs.get('metric'))) state.kpi = qs.get('metric');
    if (!premium && PREMIUM_RANGES.has(state.range)) state.range = '30';
})();

let conn = null;
const loaded = new Set();
let productStores = [];
let bounds = { min: null, max: null };
let daily = null;          // { key, rows: [{store,d,live,oos,ups,downs,slr,nlr}], fresh: [{store,d,n}] }
let scoped = null;         // results of the store-scoped queries
let chart = null;

/* ---------------- helpers ---------------- */
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const sqlStr = s => `'${String(s).replace(/'/g, "''")}'`;
const addDays = (iso, n) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const dayDiff = (a, b) => Math.round((new Date(b + 'T00:00:00Z') - new Date(a + 'T00:00:00Z')) / 86400000);
const fmtDate = (iso, year = false) => new Date(iso + 'T00:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', ...(year ? { year: 'numeric' } : {}), timeZone: 'UTC' });
const fmtInt = n => Number.isFinite(n) ? Math.round(n).toLocaleString('en-US') : '—';
const fmtPct = (x, digits = 1) => {
    if (!Number.isFinite(x)) return '—';
    const t = (x * 100).toFixed(digits);
    return Number(t) === 0 ? `${(0).toFixed(digits)}%` : `${x > 0 ? '+' : ''}${t}%`;
};
const fmtTaka = n => !Number.isFinite(n) ? '—' : '৳' + (n >= 1000 ? Math.round(n).toLocaleString('en-US') : n >= 100 ? n.toFixed(0) : n.toFixed(n < 10 ? 2 : 1));
const prettyCat = c => { c = String(c || 'Uncategorised').trim(); return (!c.includes(' ') && c.includes('-')) ? c.replace(/-/g, ' ').replace(/\b\w/g, m => m.toUpperCase()) : c; };
const storeName = s => STORES[s] || s;
const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const dhakaToday = () => new Date(Date.now() + 6 * 3600000).toISOString().slice(0, 10);

// duckdb-wasm runs one statement at a time per connection; queue them so callers can't interleave.
let queryChain = Promise.resolve();
function exec(sql) {
    const run = queryChain.then(() => conn.query(sql));
    queryChain = run.catch(() => {});
    return run;
}
async function q(sql) {
    const res = await exec(sql);
    return res.toArray().map(row => {
        const o = row.toJSON();
        for (const k in o) if (typeof o[k] === 'bigint') o[k] = Number(o[k]);
        return o;
    });
}

let toastTimer;
function toast(msg) {
    const el = $('an-toast');
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
}

function windowDates() {
    const E = bounds.max;
    if (!E) return null;
    if (state.range === 'all') return { start: bounds.min, end: E, prevStart: null, prevEnd: null, n: dayDiff(bounds.min, E) + 1 };
    const n = Number(state.range);
    const start = addDays(E, -(n - 1));
    return { start, end: E, prevStart: addDays(start, -n), prevEnd: addDays(start, -1), n };
}
const storeCond = (col = 'store') => state.store === 'all' ? '' : `AND ${col} = ${sqlStr(state.store)}`;

/* ---------------- boot & loading ---------------- */
async function fetchBytes(name) {
    const r = await fetch(name);
    if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
    return new Uint8Array(await r.arrayBuffer());
}

let db = null;
let histFrom = null;            // earliest date materialised into the h_<store> tables
const httpFiles = new Set();    // history files read with HTTP range requests

// History chunks are written sorted by date in small row groups (convert_to_parquet.py), so a
// `date >= from` filter over an HTTP-registered file downloads only the row groups it needs:
// a 30-day view reads a few MB instead of every store's full history.
async function registerHistory(s) {
    const name = `history_${s}.parquet`;
    if (httpFiles.has(s)) return;
    try {
        await db.registerFileURL(name, new URL(name, location.href).href, duckdb.DuckDBDataProtocol.HTTP, false);
    } catch (_) {
        await db.registerFileBuffer(name, await fetchBytes(name));
    }
    httpFiles.add(s);
}

async function materialiseStore(s, from) {
    const sql = `CREATE OR REPLACE TABLE h_${s} AS
        SELECT product_id, left(date, 10) AS d, min(price) FILTER (WHERE price > 0) AS price, '${s}' AS store
        FROM read_parquet('history_${s}.parquet') WHERE date >= '${from}' GROUP BY product_id, left(date, 10)`;
    try {
        await registerHistory(s);
        await exec(sql);
    } catch (e) {
        // Range reads can fail behind some proxies: fall back to one full download.
        console.warn(`Range read for ${s} failed, downloading the whole chunk`, e);
        await db.registerFileBuffer(`history_${s}.parquet`, await fetchBytes(`history_${s}.parquet`));
        await exec(sql);
    }
}

function neededFrom() {
    if (state.range === 'all') return '0000-00-00';
    const n = Number(state.range);
    // current + previous period, plus a few days of slack for the lag() baseline
    return addDays(catalogEnd, -(2 * n + 3));
}

let catalogEnd = null;
async function ensureHistory() {
    const from = neededFrom();
    if (histFrom && from >= histFrom) return;
    histFrom = from;
    loaded.clear(); failed.clear();
    updateProgress();
    for (const s of productStores) {
        try {
            await materialiseStore(s, from);
            loaded.add(s);
            await exec(`CREATE OR REPLACE VIEW h AS ${[...loaded].map(x => `SELECT * FROM h_${x}`).join(' UNION ALL ')}`);
            const b = (await q(`SELECT min(d) mn, max(d) mx FROM h`))[0];
            bounds = { min: b.mn, max: b.mx };
            updateProgress();
            schedule('all');
        } catch (e) {
            console.warn(`History for ${s} failed`, e);
            updateProgress(s);
        }
    }
    updateProgress();
}

async function boot() {
    initControls();
    renderSkeletons();
    const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
    const workerUrl = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], { type: 'text/javascript' }));
    db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING), new Worker(workerUrl));
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
    URL.revokeObjectURL(workerUrl);
    try { await db.open({ filesystem: { allowFullHTTPReads: true } }); } catch (_) {}
    conn = await db.connect();

    let productsFile = null;
    for (const name of ['products_free.parquet', 'products.parquet']) {
        try { await db.registerFileBuffer(name, await fetchBytes(name)); productsFile = name; break; } catch (_) {}
    }
    if (!productsFile) throw new Error('Could not load the product catalogue.');
    await exec(`CREATE TABLE p AS SELECT id, name, store, url, unit, unit_type, in_stock, left(first_seen, 10) AS first_seen,
        trim(regexp_replace(coalesce(category, 'Uncategorised'), '^[^\\p{L}\\p{N}]+', '')) AS category
        FROM read_parquet('${productsFile}')`);
    productStores = (await q(`SELECT DISTINCT store FROM p WHERE store IS NOT NULL`)).map(r => r.store)
        .filter(s => STORES[s]).sort((a, b) => Object.keys(STORES).indexOf(a) - Object.keys(STORES).indexOf(b));
    catalogEnd = (await q(`SELECT max(left(last_seen, 10)) AS mx FROM read_parquet('${productsFile}')`))[0].mx || dhakaToday();
    populateStoreSelect();
    await renderStores();

    try {
        await db.registerFileBuffer('atl.parquet', await fetchBytes('atl.parquet'));
        await exec(`CREATE TABLE atl AS SELECT * FROM read_parquet('atl.parquet')`);
        await renderDeals();
    } catch (e) {
        console.warn('ATL snapshot unavailable', e);
        $('an-deals').innerHTML = '<li class="an-empty">All-time-low snapshot unavailable.</li>';
    }

    await ensureHistory();
}

const failed = new Set();
function updateProgress(failedStore) {
    if (failedStore) failed.add(failedStore);
    const total = productStores.length;
    const el = $('an-progress');
    if (loaded.size + failed.size < total) el.textContent = `Loading history ${loaded.size}/${total}…`;
    else el.textContent = failed.size ? `${failed.size} store${failed.size > 1 ? 's' : ''} failed to load` : '';
    const live = $('an-live');
    if (!bounds.max) return;
    const lag = dayDiff(bounds.max, dhakaToday());
    live.classList.toggle('ok', lag <= 2);
    live.classList.toggle('warn', lag > 2);
    $('an-live-text').textContent = `Data through ${fmtDate(bounds.max, true)}${lag > 2 ? ` · ${lag}d old` : ''}`;
}

/* ---------------- refresh pump (one query stream at a time) ---------------- */
const dirty = { daily: false, scoped: false };
let running = false, pumpTimer;
function schedule(kind) {
    if (kind === 'all' || kind === 'daily') dirty.daily = true;
    dirty.scoped = true;
    clearTimeout(pumpTimer);
    pumpTimer = setTimeout(pump, 120);
}
async function pump() {
    if (running) return;
    running = true;
    try {
        while (dirty.daily || dirty.scoped) {
            if (dirty.daily) { dirty.daily = false; await refreshDaily(); renderOverview(); await renderStores(); }
            if (dirty.scoped) { dirty.scoped = false; await refreshScoped(); }
        }
    } catch (e) {
        console.error(e);
        toast('A query failed — see the console for details.');
    } finally {
        running = false;
    }
}

async function refreshDaily() {
    const w = windowDates();
    if (!w) return;
    const from = w.prevStart || w.start;
    const rows = await q(`
        WITH b AS (SELECT store, product_id, d, price FROM h WHERE d BETWEEN '${from}' AND '${w.end}'),
        pos AS (SELECT store, d, price, lag(price) OVER (PARTITION BY product_id ORDER BY d) AS prev FROM b WHERE price IS NOT NULL),
        a AS (
            SELECT store, d, count(*) AS live,
                count(*) FILTER (WHERE prev IS NOT NULL AND price > prev) AS ups,
                count(*) FILTER (WHERE prev IS NOT NULL AND price < prev) AS downs,
                sum(CASE WHEN prev > 0 AND abs(ln(price / prev)) < ${MAX_LOG_MOVE} THEN ln(price / prev) END) AS slr,
                count(CASE WHEN prev > 0 AND abs(ln(price / prev)) < ${MAX_LOG_MOVE} THEN 1 END) AS nlr
            FROM pos GROUP BY ALL),
        o AS (SELECT store, d, count(*) AS oos FROM b WHERE price IS NULL GROUP BY ALL)
        SELECT coalesce(a.store, o.store) AS store, coalesce(a.d, o.d) AS d,
            coalesce(live, 0) AS live, coalesce(oos, 0) AS oos, coalesce(ups, 0) AS ups, coalesce(downs, 0) AS downs,
            coalesce(slr, 0) AS slr, coalesce(nlr, 0) AS nlr
        FROM a FULL OUTER JOIN o ON a.store = o.store AND a.d = o.d ORDER BY 2`);
    // First sighting per product comes from the catalogue (history is loaded for the window only),
    // ignoring each store's first scrape day, when everything is "new".
    const fresh = await q(`
        WITH s0 AS (SELECT store, min(first_seen) AS sd FROM p GROUP BY 1)
        SELECT p.store, p.first_seen AS d, count(*) AS n FROM p JOIN s0 USING (store)
        WHERE p.first_seen > s0.sd AND p.first_seen BETWEEN '${from}' AND '${w.end}' GROUP BY ALL`);
    daily = { rows, fresh, w };
}

/* ---------------- series & KPIs ---------------- */
function buildSeries() {
    if (!daily) return null;
    const { w } = daily;
    const inScope = r => state.store === 'all' || r.store === state.store;
    const byDay = new Map();
    const blank = () => ({ live: 0, oos: 0, ups: 0, downs: 0, slr: 0, nlr: 0, fresh: 0 });
    for (const r of daily.rows) {
        if (!inScope(r)) continue;
        const o = byDay.get(r.d) || blank();
        o.live += r.live; o.oos += r.oos; o.ups += r.ups; o.downs += r.downs; o.slr += r.slr; o.nlr += r.nlr;
        byDay.set(r.d, o);
    }
    for (const r of daily.fresh) {
        if (!inScope(r)) continue;
        const o = byDay.get(r.d) || blank();
        o.fresh += r.n;
        byDay.set(r.d, o);
    }
    const period = (start, end) => {
        const days = [];
        for (let d = start; d <= end; d = addDays(d, 1)) days.push({ d, ...(byDay.get(d) || blank()), has: byDay.has(d) });
        // Base 100 sits on the first day that has data, so a range opening on a scrape gap still starts at 100.
        let cum = 0, started = false;
        days.forEach(x => {
            if (started && x.nlr > 0) cum += x.slr / x.nlr;
            if (x.has) started = true;
            x.index = 100 * Math.exp(cum);
            const tot = x.live + x.oos;
            x.rate = tot > 0 ? x.live / tot : null;
        });
        return days;
    };
    const cur = period(w.start, w.end);
    const prev = w.prevStart ? period(w.prevStart, w.prevEnd) : null;
    return { cur, prev, w };
}

// Stores scrape on different days, so a "latest" snapshot takes each store's last day in the period.
function snapshot(endDate, startDate) {
    let live = 0, oos = 0;
    const latest = new Map();
    for (const r of daily.rows) {
        if (state.store !== 'all' && r.store !== state.store) continue;
        if (r.d > endDate || r.d < startDate) continue;
        const cur = latest.get(r.store);
        if (!cur || r.d > cur.d) latest.set(r.store, r);
    }
    for (const r of latest.values()) { live += r.live; oos += r.oos; }
    return { live, oos, rate: live + oos > 0 ? live / (live + oos) : null };
}

function kpiValues(series) {
    const { cur, prev, w } = series;
    const sum = (arr, f) => arr.reduce((s, x) => s + f(x), 0);
    const last = cur[cur.length - 1];
    const prevIndexChange = prev ? prev[prev.length - 1].index / 100 - 1 : null;
    const snapNow = snapshot(w.end, w.start);
    const snapPrev = prev ? snapshot(w.prevEnd, w.prevStart) : null;
    const movesNow = sum(cur, x => x.ups + x.downs);
    const movesPrev = prev ? sum(prev, x => x.ups + x.downs) : null;
    const freshNow = sum(cur, x => x.fresh);
    const freshPrev = prev ? sum(prev, x => x.fresh) : null;
    const rel = (a, b) => (b ? a / b - 1 : null);
    return {
        index: { value: last.index.toFixed(1), delta: last.index / 100 - 1, tone: last.index > 100.05 ? 'bad' : last.index < 99.95 ? 'good' : '',
                 note: prevIndexChange != null ? `previous ${state.range}d: ${fmtPct(prevIndexChange)}` : 'since first data' },
        listed: { value: fmtInt(snapNow.live), delta: snapPrev ? rel(snapNow.live, snapPrev.live) : null, tone: 'up-good' },
        moves: { value: fmtInt(movesNow), delta: movesPrev != null ? rel(movesNow, movesPrev) : null, tone: '',
                 note: `▲ ${fmtInt(sum(cur, x => x.ups))} hikes · ▼ ${fmtInt(sum(cur, x => x.downs))} drops` },
        instock: { value: snapNow.rate != null ? `${(snapNow.rate * 100).toFixed(1)}%` : '—',
                   delta: snapPrev?.rate != null && snapNow.rate != null ? snapNow.rate - snapPrev.rate : null, tone: 'up-good', points: true },
        new: { value: fmtInt(freshNow), delta: freshPrev != null ? rel(freshNow, freshPrev) : null, tone: 'up-good' }
    };
}

/* ---------------- rendering: overview ---------------- */
function renderOverview() {
    const series = buildSeries();
    const box = $('an-kpis');
    if (!series) return;
    const vals = kpiValues(series);
    box.innerHTML = KPIS.map(k => {
        const v = vals[k.id];
        let deltaHtml = '';
        if (v.delta != null && Number.isFinite(v.delta)) {
            let tone = v.tone;
            if (tone === 'up-good') tone = v.delta > 0.0005 ? 'good' : v.delta < -0.0005 ? 'bad' : '';
            const pts = (v.delta * 100).toFixed(1);
            const txt = v.points ? `${Number(pts) > 0 ? '+' : ''}${Number(pts) === 0 ? '0.0' : pts} pts` : fmtPct(v.delta);
            deltaHtml = `<span class="an-delta ${tone}">${txt}</span>`;
        }
        return `<button class="an-kpi" role="tab" aria-controls="an-chart-wrap" type="button" data-kpi="${k.id}" aria-selected="${state.kpi === k.id}">
            <span class="an-kpi-label">${k.label}</span>
            <span class="an-kpi-row"><span class="an-kpi-value">${v.value}</span>${deltaHtml}</span>
        </button>`;
    }).join('');
    const meta = KPIS.find(k => k.id === state.kpi);
    $('an-chart-title').textContent = meta.title + (state.store !== 'all' ? ` · ${storeName(state.store)}` : '');
    const v = vals[state.kpi];
    $('an-chart-note').textContent = v.note || `${fmtDate(series.w.start)} – ${fmtDate(series.w.end, true)}${series.prev ? ` · Δ vs previous ${series.w.n} days` : ''}`;
    $('an-chart').setAttribute('aria-label', `${$('an-chart-title').textContent}. ${$('an-chart-note').textContent}. Export CSV for the full series.`);
    drawChart(series);
}

function drawChart(series) {
    if (typeof Chart === 'undefined') return;
    const { cur } = series;
    const labels = cur.map(x => fmtDate(x.d));
    const paper2 = cssVar('--paper-2'), paper3 = cssVar('--paper-3'), rule = cssVar('--rule'), taka = cssVar('--taka'), chili = cssVar('--chili'), ink1 = cssVar('--ink-1'), paper = cssVar('--paper');
    const ctx = $('an-chart').getContext('2d');
    const gradient = color => {
        const g = ctx.createLinearGradient(0, 0, 0, 300);
        g.addColorStop(0, color + '55'); g.addColorStop(1, color + '00');
        return g;
    };
    const line = (label, data, color, fmt) => ({
        type: 'line', label, data, borderColor: color, backgroundColor: gradient(color), fill: true,
        borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: .25, spanGaps: true, _fmt: fmt
    });
    let datasets, stacked = false, yFmt = v => fmtInt(v);
    switch (state.kpi) {
        case 'index':
            datasets = [line('Index', cur.map(x => x.has ? +x.index.toFixed(2) : null), taka, v => v.toFixed(2))];
            yFmt = v => v.toFixed(1);
            break;
        case 'listed':
            datasets = [line('Listed in stock', cur.map(x => x.has ? x.live : null), taka, fmtInt)];
            break;
        case 'instock':
            datasets = [line('In stock', cur.map(x => x.rate != null ? +(x.rate * 100).toFixed(2) : null), taka, v => v.toFixed(1) + '%')];
            yFmt = v => v + '%';
            break;
        case 'moves':
            stacked = true;
            datasets = [
                { type: 'bar', label: 'Drops', data: cur.map(x => x.downs), backgroundColor: taka, borderRadius: 2, _fmt: fmtInt },
                { type: 'bar', label: 'Hikes', data: cur.map(x => x.ups), backgroundColor: chili, borderRadius: 2, _fmt: fmtInt }
            ];
            break;
        case 'new':
            datasets = [{ type: 'bar', label: 'New listings', data: cur.map(x => x.fresh), backgroundColor: paper2, borderRadius: 2, _fmt: fmtInt }];
            break;
    }
    if (chart) chart.destroy();
    chart = new Chart(ctx, {
        data: { labels, datasets },
        options: {
            responsive: true, maintainAspectRatio: false, animation: { duration: 220 }, transitions: { resize: { animation: { duration: 0 } } },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: stacked, position: 'bottom', align: 'end', labels: { color: paper2, boxWidth: 10, boxHeight: 10, font: { family: 'IBM Plex Mono', size: 11 } } },
                tooltip: {
                    backgroundColor: ink1, borderColor: cssVar('--rule-strong'), borderWidth: 1, titleColor: paper, bodyColor: paper2,
                    titleFont: { family: 'IBM Plex Mono', size: 11 }, bodyFont: { family: 'IBM Plex Mono', size: 12 }, padding: 10, displayColors: true, boxWidth: 8, boxHeight: 8,
                    callbacks: { label: c => ` ${c.dataset.label}: ${c.raw == null ? '—' : c.dataset._fmt(c.raw)}` }
                }
            },
            scales: {
                x: { stacked, grid: { display: false }, border: { color: rule }, ticks: { color: paper3, maxTicksLimit: 8, maxRotation: 0, font: { family: 'IBM Plex Mono', size: 11 } } },
                y: { stacked, grid: { color: rule }, border: { display: false }, ticks: { color: paper3, maxTicksLimit: 5, callback: yFmt, font: { family: 'IBM Plex Mono', size: 11 } } }
            }
        }
    });
}

/* ---------------- rendering: list panels ---------------- */
function rowsHtml(items, { empty = 'No data in this range.' } = {}) {
    if (!items.length) return `<li class="an-empty">${empty}</li>`;
    const max = Math.max(...items.map(i => Math.abs(i.weight ?? 0)), 1e-9);
    return items.map(i => {
        const pct = Math.max(2, Math.min(100, Math.abs(i.weight ?? 0) / max * 100));
        const inner = `<span class="fill ${i.fillTone || ''}" style="width:${i.weight == null ? 0 : pct}%"></span>
            <span class="name">${i.lead || ''}${i.href ? `<a href="${esc(i.href)}" target="_blank" rel="noopener noreferrer" title="${esc(i.label)}">${esc(i.label)}</a>` : `<span title="${esc(i.label)}">${esc(i.label)}</span>`}${i.meta ? `<span class="meta">${esc(i.meta)}</span>` : ''}</span>
            <span class="val ${i.tone || ''}">${i.value}${i.sub ? `<small>${i.sub}</small>` : ''}</span>`;
        return i.action
            ? `<li><button type="button" class="an-row as-btn" data-action="${esc(i.action)}">${inner}</button></li>`
            : `<li class="an-row">${inner}</li>`;
    }).join('');
}
const skeleton = n => Array.from({ length: n }, () => '<li class="an-skel"></li>').join('');
function renderSkeletons() {
    ['an-stores', 'an-categories', 'an-movers', 'an-stock', 'an-deals', 'an-health'].forEach(id => { $(id).innerHTML = skeleton(7); });
    $('an-kpis').innerHTML = KPIS.map(k => `<button class="an-kpi" role="tab" aria-controls="an-chart-wrap" type="button" data-kpi="${k.id}" aria-selected="${state.kpi === k.id}"><span class="an-kpi-label">${k.label}</span><span class="an-kpi-row"><span class="an-kpi-value">—</span></span></button>`).join('');
}
const storeTag = s => `<span class="an-tag">${esc(storeName(s).slice(0, 3))}</span>`;

async function renderStores() {
    const tab = state.tabs.stores;
    const counts = await q(`SELECT store, count(*) AS n, count(*) FILTER (WHERE in_stock) AS live FROM p GROUP BY 1`);
    const byStore = new Map(counts.map(r => [r.store, r]));
    let items;
    if (tab === 'items') {
        $('an-stores-col-b').textContent = 'Items · in stock';
        items = productStores.map(s => ({ s, n: byStore.get(s)?.n || 0, live: byStore.get(s)?.live || 0 }))
            .sort((a, b) => b.n - a.n)
            .map(r => ({ label: storeName(r.s), action: r.s, weight: r.n, value: fmtInt(r.n), sub: `${fmtInt(r.live)} live` }));
    } else if (!daily) {
        $('an-stores').innerHTML = skeleton(productStores.length);
        return;
    } else if (tab === 'index') {
        $('an-stores-col-b').textContent = `Price change · ${state.range === 'all' ? 'all time' : state.range + 'd'}`;
        const w = daily.w;
        const per = new Map(), first = new Map();
        for (const r of daily.rows) {
            if (r.d < w.start || r.d > w.end) continue;
            if (!first.has(r.store) || r.d < first.get(r.store)) first.set(r.store, r.d);
        }
        for (const r of daily.rows) {
            if (r.d <= (first.get(r.store) || w.start) || r.d > w.end || !r.nlr) continue;
            per.set(r.store, (per.get(r.store) || 0) + r.slr / r.nlr);
        }
        items = productStores.filter(s => loaded.has(s)).map(s => ({ s, ch: Math.exp(per.get(s) || 0) - 1 }))
            .sort((a, b) => b.ch - a.ch)
            .map(r => ({ label: storeName(r.s), action: r.s, weight: r.ch, value: fmtPct(r.ch, 2), tone: r.ch > 0.0005 ? 'bad' : r.ch < -0.0005 ? 'good' : '', fillTone: r.ch > 0 ? 'bad' : 'good' }));
    } else {
        $('an-stores-col-b').textContent = 'In stock (latest scrape)';
        const w = daily.w;
        items = productStores.filter(s => loaded.has(s)).map(s => {
            let last = null;
            for (const r of daily.rows) if (r.store === s && r.d >= w.start && r.d <= w.end && (!last || r.d > last.d)) last = r;
            const rate = last && last.live + last.oos ? last.live / (last.live + last.oos) : null;
            return { s, rate, last };
        }).sort((a, b) => (b.rate ?? -1) - (a.rate ?? -1))
          .map(r => ({ label: storeName(r.s), action: r.s, weight: r.rate ?? 0, value: r.rate == null ? '—' : `${(r.rate * 100).toFixed(1)}%`, sub: r.last ? `${fmtInt(r.last.live)} / ${fmtInt(r.last.live + r.last.oos)}` : '' }));
    }
    $('an-stores').innerHTML = rowsHtml(items);
    if (state.store !== 'all') $('an-stores').querySelectorAll('.an-row').forEach(b => { if (b.dataset.action !== state.store) b.style.opacity = '.55'; });
}

async function refreshScoped() {
    const w = windowDates();
    if (!w || !loaded.size) return;
    const sc = storeCond();
    await exec(`CREATE OR REPLACE TEMP TABLE win AS
        WITH b AS (SELECT product_id, d, price FROM h WHERE price IS NOT NULL AND d BETWEEN '${w.start}' AND '${w.end}' ${sc}),
        f AS (SELECT product_id, arg_min(price, d) AS p0, arg_max(price, d) AS p1, min(d) AS fd, max(d) AS ld FROM b GROUP BY 1)
        SELECT f.*, p.name, p.store, p.category, p.url, p.unit FROM f JOIN p ON p.id = f.product_id`);
    const recent = addDays(w.end, -3);
    const sane = `p0 > 0 AND p1 / p0 BETWEEN 0.2 AND 5`;
    const [cats, drops, hikes, stock, health] = await Promise.all([
        q(`SELECT category, count(*) AS n,
              avg(CASE WHEN ${sane} THEN p1 / p0 - 1 END) AS avg_ch,
              count(*) FILTER (WHERE p1 > p0) AS up, count(*) FILTER (WHERE p1 < p0) AS dn
           FROM win GROUP BY 1`),
        q(`SELECT name, store, url, unit, p0, p1, p1 / p0 - 1 AS pct FROM win WHERE ${sane} AND p1 < p0 AND ld >= '${recent}' ORDER BY pct ASC LIMIT 40`),
        q(`SELECT name, store, url, unit, p0, p1, p1 / p0 - 1 AS pct FROM win WHERE ${sane} AND p1 > p0 AND ld >= '${recent}' ORDER BY pct DESC LIMIT 40`),
        // Free history rarely carries OOS sentinels: an item that drops out simply stops appearing.
        // So stock is read per store scrape: k = the store's n-th scrape day in the window.
        // Went out = seen in >= 3 scrapes, then missing from the store's last 2. Restocked = in a recent scrape after missing >= 2.
        q(`WITH sd AS (SELECT store, d, dense_rank() OVER (PARTITION BY store ORDER BY d) AS k
                         FROM (SELECT DISTINCT store, d FROM h WHERE d BETWEEN '${w.start}' AND '${w.end}' ${sc})),
              smax AS (SELECT store, max(k) AS km FROM sd GROUP BY 1),
              o AS (SELECT h.product_id, h.store, h.d, h.price, sd.k FROM h JOIN sd USING (store, d) WHERE h.price IS NOT NULL),
              g AS (SELECT *, k - lag(k) OVER (PARTITION BY product_id ORDER BY k) AS gap FROM o),
              f AS (SELECT product_id, store, max(k) AS lk, max(d) AS last_in, arg_max(price, k) AS last_price,
                           max(d) FILTER (WHERE gap >= 3) AS back_d, count(*) AS seen FROM g GROUP BY 1, 2)
           SELECT f.*, smax.km, p.name, p.url FROM f JOIN smax USING (store) JOIN p ON p.id = f.product_id
           WHERE smax.km >= 3 AND ((f.lk <= smax.km - 2 AND f.seen >= 3) OR (f.lk >= smax.km - 1 AND f.back_d IS NOT NULL))
           ORDER BY coalesce(f.back_d, f.last_in) DESC`),
        q(`SELECT store, min(d) AS first_d, max(d) AS last_d,
              count(DISTINCT d) FILTER (WHERE d BETWEEN '${w.start}' AND '${w.end}') AS days,
              count(*) FILTER (WHERE d BETWEEN '${w.start}' AND '${w.end}') AS points
           FROM h GROUP BY 1`)
    ]);
    scoped = { cats, drops, hikes, stock, health, w };
    renderCategories(); renderMovers(); renderStock(); renderHealth(); await renderDeals();
}

function renderCategories() {
    if (!scoped) return;
    const tab = state.tabs.categories;
    let rows = scoped.cats.filter(r => r.category);
    if (tab === 'items') {
        $('an-cat-col-b').textContent = 'Items · avg change';
        rows = rows.sort((a, b) => b.n - a.n).slice(0, 30);
        $('an-categories').innerHTML = rowsHtml(rows.map(r => ({ label: prettyCat(r.category), weight: r.n, value: fmtInt(r.n), sub: fmtPct(r.avg_ch || 0, 2) })));
        return;
    }
    $('an-cat-col-b').textContent = 'Avg change · items';
    rows = rows.filter(r => r.n >= 15 && Number.isFinite(r.avg_ch) && (tab === 'up' ? r.avg_ch > 0 : r.avg_ch < 0))
        .sort((a, b) => tab === 'up' ? b.avg_ch - a.avg_ch : a.avg_ch - b.avg_ch).slice(0, 30);
    $('an-categories').innerHTML = rowsHtml(rows.map(r => ({
        label: prettyCat(r.category), weight: r.avg_ch, value: fmtPct(r.avg_ch, 2), tone: tab === 'up' ? 'bad' : 'good',
        fillTone: tab === 'up' ? 'bad' : 'good', sub: `${fmtInt(r.n)} items · ▲${fmtInt(r.up)} ▼${fmtInt(r.dn)}`
    })), { empty: tab === 'up' ? 'No category got pricier in this range.' : 'No category got cheaper in this range.' });
}

function renderMovers() {
    if (!scoped) return;
    const up = state.tabs.movers === 'up';
    const rows = up ? scoped.hikes : scoped.drops;
    $('an-movers').innerHTML = rowsHtml(rows.map(r => ({
        lead: state.store === 'all' ? storeTag(r.store) : '', label: r.name || '(unnamed)', href: r.url, meta: r.unit || '',
        weight: r.pct, fillTone: up ? 'bad' : 'good', tone: up ? 'bad' : 'good',
        value: fmtPct(r.pct), sub: `${fmtTaka(r.p0)} → ${fmtTaka(r.p1)}`
    })), { empty: up ? 'No price hikes in this range.' : 'No price drops in this range.' });
}

function renderStock() {
    if (!scoped) return;
    const oos = scoped.stock.filter(r => r.lk <= r.km - 2);
    const back = scoped.stock.filter(r => r.lk >= r.km - 1 && r.back_d);
    $('an-stock-col-b').textContent = state.tabs.stock === 'oos' ? 'Last seen' : 'Back since';
    const tabs = document.querySelector('[data-tabs="stock"]');
    tabs.querySelector('[data-tab="oos"]').textContent = `Went out · ${fmtInt(oos.length)}`;
    tabs.querySelector('[data-tab="back"]').textContent = `Restocked · ${fmtInt(back.length)}`;
    const rows = (state.tabs.stock === 'oos' ? oos : back).slice(0, 60);
    $('an-stock').innerHTML = rowsHtml(rows.map(r => ({
        lead: state.store === 'all' ? storeTag(r.store) : '', label: r.name || '(unnamed)', href: r.url,
        value: fmtDate(state.tabs.stock === 'oos' ? r.last_in : r.back_d), sub: r.last_price ? fmtTaka(r.last_price) : ''
    })), { empty: state.tabs.stock === 'oos' ? 'Nothing went out of stock in this range.' : 'Nothing came back in stock in this range.' });
}

function renderHealth() {
    if (!scoped) return;
    const w = scoped.w;
    const byStore = new Map(scoped.health.map(r => [r.store, r]));
    const items = productStores.map(s => {
        if (!loaded.has(s)) return { label: storeName(s), lead: '<span class="an-status"></span>', value: failed.has(s) ? 'failed' : 'loading…', tone: failed.has(s) ? 'bad' : '' };
        const r = byStore.get(s);
        if (!r) return { label: storeName(s), lead: '<span class="an-status bad" title="No scrapes in this range"></span>', meta: 'no data in range', value: '—', tone: 'bad' };
        const span = state.range === 'all' ? dayDiff(r.first_d, w.end) + 1 : w.n;
        const cov = span > 0 ? r.days / span : 0;
        const lag = dayDiff(r.last_d, w.end);
        const tone = lag <= 1 ? 'ok' : lag <= 3 ? 'warn' : 'bad';
        return {
            label: storeName(s), lead: `<span class="an-status ${tone}" title="${lag}d behind the newest store"></span>`,
            meta: lag > 0 ? `${lag}d behind` : 'current', weight: cov, fillTone: tone === 'bad' ? 'bad' : '',
            value: `${fmtDate(r.last_d)} · ${(cov * 100).toFixed(0)}%`, sub: `${fmtInt(r.days)} days · ${fmtInt(r.points)} pts`
        };
    });
    $('an-health').innerHTML = rowsHtml(items);
}

async function renderDeals() {
    let exists = false;
    try { exists = (await q(`SELECT count(*) AS n FROM information_schema.tables WHERE table_name = 'atl'`))[0].n > 0; } catch (_) {}
    if (!exists) return;
    const sc = storeCond();
    const base = `FROM atl WHERE coalesce(in_stock, true) AND normalized_price > 0 AND max_price > normalized_price
        AND 1 - normalized_price / max_price <= 0.9 ${sc}`;
    if (state.tabs.deals === 'stores') {
        $('an-deals-col-a').textContent = 'Store'; $('an-deals-col-b').textContent = 'Items at all-time low';
        const rows = await q(`SELECT store, count(*) AS n, avg(1 - normalized_price / max_price) AS off ${base} GROUP BY 1 ORDER BY 2 DESC`);
        $('an-deals').innerHTML = rowsHtml(rows.map(r => ({ label: storeName(r.store), action: r.store, weight: r.n, value: fmtInt(r.n), sub: `avg ${(r.off * 100).toFixed(0)}% below peak`, fillTone: 'good' })));
        return;
    }
    $('an-deals-col-a').textContent = 'Product'; $('an-deals-col-b').textContent = 'Below peak';
    const rows = await q(`SELECT name, store, url, unit, current_price, normalized_price, max_price, unit_type,
        1 - normalized_price / max_price AS off ${base} ORDER BY off DESC LIMIT 40`);
    $('an-deals').innerHTML = rowsHtml(rows.map(r => ({
        lead: state.store === 'all' ? storeTag(r.store) : '', label: r.name || '(unnamed)', href: r.url, meta: r.unit || '',
        weight: r.off, fillTone: 'good', tone: 'good', value: `−${(r.off * 100).toFixed(0)}%`, sub: fmtTaka(r.current_price)
    })), { empty: 'No all-time lows for this selection.' });
}

/* ---------------- controls ---------------- */
function populateStoreSelect() {
    const sel = $('an-store');
    sel.innerHTML = '<option value="all">All stores</option>' + productStores.map(s => `<option value="${s}">${esc(storeName(s))}</option>`).join('');
    if (!productStores.includes(state.store)) state.store = 'all';
    sel.value = state.store;
}

function syncUrl() {
    const qs = new URLSearchParams();
    if (state.store !== 'all') qs.set('store', state.store);
    if (state.range !== '30') qs.set('range', state.range);
    if (state.kpi !== 'index') qs.set('metric', state.kpi);
    const s = qs.toString();
    history.replaceState(null, '', location.pathname + (s ? `?${s}` : ''));
}

function syncRangeButtons() {
    document.querySelectorAll('#an-range button').forEach(b => {
        b.classList.toggle('on', b.dataset.range === state.range);
        b.setAttribute('aria-pressed', String(b.dataset.range === state.range));
        const locked = !premium && b.hasAttribute('data-premium');
        b.classList.toggle('locked', locked);
        if (locked) b.title = 'Premium — unlock on the dashboard';
    });
}

function setStore(s) {
    if (s !== 'all' && !STORES[s]) return;
    state.store = state.store === s ? 'all' : s;
    $('an-store').value = state.store;
    syncUrl();
    renderOverview();
    renderStores();
    schedule('scoped');
}

function initControls() {
    syncRangeButtons();
    $('an-store').addEventListener('change', e => setStore(e.target.value === 'all' ? 'all' : e.target.value));
    $('an-range').addEventListener('click', e => {
        const b = e.target.closest('button[data-range]');
        if (!b) return;
        if (!premium && b.hasAttribute('data-premium')) { toast('90-day and full history are Premium — unlock them on the dashboard.'); return; }
        if (state.range === b.dataset.range) return;
        state.range = b.dataset.range;
        syncRangeButtons(); syncUrl();
        schedule('all');
        ensureHistory();
    });
    $('an-kpis').addEventListener('click', e => {
        const b = e.target.closest('[data-kpi]');
        if (!b) return;
        state.kpi = b.dataset.kpi;
        syncUrl();
        renderOverview();
    });
    document.querySelectorAll('[data-tabs]').forEach(group => {
        group.addEventListener('click', e => {
            const b = e.target.closest('button[data-tab]');
            if (!b) return;
            const key = group.dataset.tabs;
            state.tabs[key] = b.dataset.tab;
            group.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
            ({ stores: renderStores, categories: renderCategories, movers: renderMovers, stock: renderStock, deals: renderDeals })[key]?.();
        });
    });
    // Clicking a store row filters the whole page (click again to clear).
    document.addEventListener('click', e => {
        const b = e.target.closest('.an-row.as-btn[data-action]');
        if (b) setStore(b.dataset.action);
    });
    $('an-share').addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(location.href); toast('Link copied.'); }
        catch (_) { toast(location.href); }
    });
    $('an-csv').addEventListener('click', exportCsv);
    $('an-theme').addEventListener('click', () => {
        const light = document.documentElement.dataset.theme !== 'light';
        if (light) document.documentElement.dataset.theme = 'light'; else delete document.documentElement.dataset.theme;
        store.set('god_theme', light ? 'light' : 'amoled');
        if (daily) renderOverview();
    });
}

function exportCsv() {
    const series = buildSeries();
    if (!series) { toast('Data is still loading.'); return; }
    const head = ['date', 'listed_in_stock', 'out_of_stock', 'in_stock_rate', 'price_hikes', 'price_drops', 'price_index', 'new_listings'];
    const lines = series.cur.map(x => [x.d, x.live, x.oos, x.rate == null ? '' : x.rate.toFixed(4), x.ups, x.downs, x.index.toFixed(3), x.fresh].join(','));
    const blob = new Blob([head.join(',') + '\n' + lines.join('\n') + '\n'], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `grocerygod_${state.store}_${state.range === 'all' ? 'all' : state.range + 'd'}_${series.w.end}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

boot().catch(e => {
    console.error(e);
    $('an-live-text').textContent = 'Failed to load';
    $('an-progress').textContent = e.message || String(e);
    toast('Analytics failed to load: ' + (e.message || e));
});
