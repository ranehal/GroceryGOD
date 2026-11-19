/* GroceryGOD Insights — cookieless visitor analytics beacon (page views, custom events, Web Vitals).
   No cookies, no localStorage identifiers, no IP storage: the collector derives a daily-rotating
   visitor hash server-side. Skipped for Do Not Track / Global Privacy Control, bots and automation.
   Opt out on this device: localStorage.setItem('god_insights_optout', '1'). */
(() => {
    const ENDPOINT = 'https://grocerygod-insights.vercel.app/api/collect';
    const ls = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
    const debug = ls('god_insights_debug') === '1';
    const nav = navigator;
    if (ls('god_insights_optout') === '1') return;
    if (nav.doNotTrack === '1' || window.doNotTrack === '1' || nav.globalPrivacyControl === true) return;
    if (!debug && (nav.webdriver || /bot|crawl|spider|headless|lighthouse/i.test(nav.userAgent))) return;
    if (!debug && location.hostname !== 'ranehal.github.io') return;   // keep local dev out of the numbers

    let sid;
    try {
        sid = sessionStorage.getItem('god_insights_sid');
        if (!sid) { sid = Math.random().toString(36).slice(2, 12) + Date.now().toString(36); sessionStorage.setItem('god_insights_sid', sid); }
    } catch (_) { sid = Math.random().toString(36).slice(2, 12); }

    const path = (location.pathname.replace(/^\/GroceryGOD/i, '') || '/').replace(/\/index\.html$/, '/');
    const queue = [];
    let timer = null;
    const base = () => ({ s: sid, p: path });

    function flush(useBeacon) {
        clearTimeout(timer); timer = null;
        if (!queue.length) return;
        const body = JSON.stringify({ e: queue.splice(0, 25) });
        // A string body is sent as text/plain: a "simple" request, so no CORS preflight.
        if (useBeacon && nav.sendBeacon && nav.sendBeacon(ENDPOINT, body)) return;
        fetch(ENDPOINT, { method: 'POST', body, keepalive: true, mode: 'cors', credentials: 'omit' }).catch(() => {});
        if (queue.length) flush(useBeacon);
    }
    function push(e, now) {
        queue.push({ ...base(), ...e });
        if (now) flush(true);
        else if (!timer) timer = setTimeout(() => flush(false), 2000);
    }

    // ---- page view ----
    const qs = new URLSearchParams(location.search);
    let ref = document.referrer || null;
    try { if (ref && new URL(ref).hostname === location.hostname) ref = null; } catch (_) {}
    push({ t: 'pageview', r: ref, u: { source: qs.get('utm_source') || qs.get('ref'), medium: qs.get('utm_medium'), campaign: qs.get('utm_campaign') } }, true);

    // ---- custom events ----
    const sent = new Map();
    function track(name, props) {
        // de-duplicate bursts (double clicks, repeated keydown) within 800ms
        const key = name + JSON.stringify(props || {});
        const t = Date.now();
        if (t - (sent.get(key) || 0) < 800) return;
        sent.set(key, t);
        push({ t: 'event', n: String(name).slice(0, 60), d: props || undefined });
    }
    window.godTrack = track;

    const CLICKS = [
        ['#hero-search-btn', () => valueOf('#hero-search-input') ? ['Search', { q: valueOf('#hero-search-input'), where: 'hero' }] : ['Search (empty)']],
        ['.shop-redirect-card-btn', el => ['Outbound to store', { store: el.closest('.p-item-sh')?.querySelector('.store-badge')?.textContent?.trim() }]],
        ['.fav-btn', () => ['Favourite']],
        ['.alert-quick-btn, #price-alerts-btn, #mobile-alerts-btn', () => ['Price alert']],
        ['.cat-jump-btn', el => ['Category jump', { category: el.dataset.cat }]],
        ['#compare-btn', () => ['Compare']],
        ['#cart-comp-btn', () => ['Cart analysis']],
        ['#analytics-btn, #hero-nav-analytics-btn, #mobile-analytics-btn', () => ['Premium analytics']],
        ['#premium-key-btn', () => ['Unlock clicked']],
        ['.intel-btn[data-filter]', el => ['Deal filter', { filter: el.dataset.filter }]],
        ['.hero-store-chip', el => ['Store chip', { store: el.dataset.store }]],
        ['.quicktag-chip', el => ['Quick tag', { q: el.textContent.trim().slice(0, 40) }]],
        ['#god-chat-toggle', () => ['Assistant opened']],
        ['#hero-nav-stats-link', () => ['Market stats']],
        ['#theme-toggle-btn, #an-theme', () => ['Theme toggled']],
        ['#an-csv', () => ['CSV export']],
        ['#an-share', () => ['Share link']],
        ['#an-range button[data-range]', el => ['Range', { range: el.dataset.range }]],
        ['[data-kpi]', el => ['Metric tab', { metric: el.dataset.kpi }]],
        ['.p-item-sh', el => ['Product opened', { store: el.querySelector('.store-badge')?.textContent?.trim() }]]
    ];
    function valueOf(sel) { const el = document.querySelector(sel); return el && el.value ? el.value.trim().toLowerCase().slice(0, 40) : undefined; }

    document.addEventListener('click', e => {
        const target = e.target instanceof Element ? e.target : null;
        if (!target) return;
        for (const [sel, fn] of CLICKS) {
            const el = target.closest(sel);
            if (el) { const [n, d] = fn(el); track(n, d); return; }
        }
        const a = target.closest('a[href]');
        if (a) {
            try {
                const u = new URL(a.href, location.href);
                if (u.hostname !== location.hostname && /^https?:$/.test(u.protocol)) track('Outbound link', { host: u.hostname.replace(/^www\./, '') });
            } catch (_) {}
        }
    }, { capture: true, passive: true });

    // Search: Enter in either search box, or a pause after typing in the catalogue search.
    // The hero search mirrors its text into #product-search; don't count that as a second search.
    let searchTimer, lastHeroSearch = 0;
    document.addEventListener('click', e => { if (e.target instanceof Element && e.target.closest('#hero-search-btn')) lastHeroSearch = Date.now(); }, { capture: true, passive: true });
    document.addEventListener('keydown', e => {
        if (e.key === 'Enter' && e.target && (e.target.id === 'hero-search-input' || e.target.id === 'product-search')) {
            const q = e.target.value.trim().toLowerCase().slice(0, 40);
            if (e.target.id === 'hero-search-input') lastHeroSearch = Date.now();
            if (q.length >= 2) track('Search', { q, where: e.target.id === 'hero-search-input' ? 'hero' : 'catalog' });
        }
    }, { capture: true, passive: true });
    document.addEventListener('input', e => {
        if (!e.target || e.target.id !== 'product-search') return;
        clearTimeout(searchTimer);
        if (Date.now() - lastHeroSearch < 4000) return;
        searchTimer = setTimeout(() => {
            const q = e.target.value.trim().toLowerCase().slice(0, 40);
            if (q.length >= 2) track('Search', { q, where: 'catalog' });
        }, 1500);
    }, { capture: true, passive: true });
    document.addEventListener('change', e => {
        const t = e.target;
        if (!t) return;
        if (t.id === 'sort-options') track('Sort', { by: t.value });
        else if (t.id === 'an-store') track('Store filter', { store: t.value });
        else if (t.classList && t.classList.contains('shop-checkbox')) track('Store toggled', { on: t.checked });
    }, { capture: true, passive: true });

    let errors = 0;
    window.addEventListener('error', e => {
        if (errors++ >= 3) return;
        track('JS error', { msg: String(e.message || 'error').slice(0, 90), src: String(e.filename || '').split('/').pop().split('?')[0].slice(0, 40) });
    });

    // ---- Web Vitals (LCP, CLS, INP, FCP, TTFB) ----
    const vitals = {};
    const observe = (type, cb, opts = {}) => {
        try { new PerformanceObserver(list => list.getEntries().forEach(cb)).observe({ type, buffered: true, ...opts }); } catch (_) {}
    };
    observe('paint', e => { if (e.name === 'first-contentful-paint') vitals.FCP = e.startTime; });
    observe('largest-contentful-paint', e => { vitals.LCP = e.startTime; });
    let clsSession = 0, clsMax = 0, clsLast = 0, clsFirst = 0;
    observe('layout-shift', e => {
        if (e.hadRecentInput) return;
        // session windows: gap < 1s and window < 5s (the CLS definition)
        if (clsSession && e.startTime - clsLast < 1000 && e.startTime - clsFirst < 5000) clsSession += e.value;
        else { clsSession = e.value; clsFirst = e.startTime; }
        clsLast = e.startTime;
        clsMax = Math.max(clsMax, clsSession);
        vitals.CLS = clsMax;
    });
    const interactions = new Map();
    observe('event', e => {
        if (!e.interactionId) return;
        interactions.set(e.interactionId, Math.max(interactions.get(e.interactionId) || 0, e.duration));
        // INP ~ the worst interaction, ignoring one outlier per 50 interactions
        const d = [...interactions.values()].sort((a, b) => b - a);
        vitals.INP = d[Math.min(d.length - 1, Math.floor(d.length / 50))];
    }, { durationThreshold: 40 });
    try {
        const navEntry = performance.getEntriesByType('navigation')[0];
        if (navEntry && navEntry.responseStart > 0) vitals.TTFB = navEntry.responseStart;
    } catch (_) {}

    // ---- leave: time on page + vitals, sent once per hidden period ----
    let visibleSince = document.visibilityState === 'visible' ? performance.now() : null;
    let visibleMs = 0, vitalsSent = false;
    function onHide() {
        if (visibleSince != null) { visibleMs += performance.now() - visibleSince; visibleSince = null; }
        if (!vitalsSent) {
            vitalsSent = true;
            for (const [n, v] of Object.entries(vitals)) if (Number.isFinite(v)) queue.push({ ...base(), t: 'vitals', n, v: n === 'CLS' ? +v.toFixed(4) : Math.round(v) });
        }
        if (visibleMs > 0) queue.push({ ...base(), t: 'leave', ms: Math.round(visibleMs) });
        visibleMs = 0;
        flush(true);
    }
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') onHide();
        else visibleSince = performance.now();
    });
    window.addEventListener('pagehide', onHide);
})();
