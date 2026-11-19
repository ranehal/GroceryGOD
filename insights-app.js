// GroceryGOD Insights dashboard — reads aggregates from the Vercel stats API (key-protected).
(() => {
    const API = 'https://grocerygod-insights.vercel.app/api/stats';
    const KEY_STORE = 'god_insights_key';
    const RANGES = ['24h', '7d', '30d', '90d'];
    const DIM_LABEL = { path: 'Page', ref: 'Referrer', country: 'Country', city: 'City', device: 'Device', browser: 'Browser', os: 'OS', utm_source: 'UTM source', utm_medium: 'UTM medium', utm_campaign: 'UTM campaign', event: 'Event' };
    const KPIS = [
        { id: 'visitors', label: 'Visitors', good: 'up' },
        { id: 'pageviews', label: 'Page views', good: 'up' },
        { id: 'bounce', label: 'Bounce rate', good: 'down' },
        { id: 'avg', label: 'Avg. time on page', good: 'up' }
    ];
    const VITAL_INFO = {
        LCP: { label: 'Largest Contentful Paint', fmt: v => `${(v / 1000).toFixed(2)}s` },
        INP: { label: 'Interaction to Next Paint', fmt: v => `${Math.round(v)}ms` },
        CLS: { label: 'Cumulative Layout Shift', fmt: v => v.toFixed(3) },
        FCP: { label: 'First Contentful Paint', fmt: v => `${(v / 1000).toFixed(2)}s` },
        TTFB: { label: 'Time to First Byte', fmt: v => `${Math.round(v)}ms` }
    };

    const $ = id => document.getElementById(id);
    const store = {
        get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
        set(k, v) { try { localStorage.setItem(k, v); } catch (_) {} },
        del(k) { try { localStorage.removeItem(k); } catch (_) {} }
    };
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const fmtInt = n => Number.isFinite(n) ? Math.round(n).toLocaleString('en-US') : '—';
    const fmtDur = ms => {
        if (!Number.isFinite(ms)) return '—';
        const s = Math.round(ms / 1000);
        return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
    };
    const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    let regionNames = null;
    try { regionNames = new Intl.DisplayNames(['en'], { type: 'region' }); } catch (_) {}
    const countryName = c => { if (!c || c === '(none)') return 'Unknown'; try { return regionNames ? regionNames.of(c) : c; } catch (_) { return c; } };

    const state = { range: '7d', kpi: 'visitors', filters: {}, tabs: { ref: 'ref', geo: 'country', tech: 'device' } };
    (() => {
        const qs = new URLSearchParams(location.search);
        if (RANGES.includes(qs.get('range'))) state.range = qs.get('range');
        for (const k of Object.keys(DIM_LABEL)) { const v = qs.get(k); if (v) state.filters[k] = v; }
    })();
    let data = null, chart = null, inflight = null, toastTimer;

    function toast(msg) {
        const el = $('an-toast');
        el.textContent = msg; el.classList.add('show');
        clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
    }

    /* ---------- gate ---------- */
    function showGate(message) {
        $('in-app').hidden = true; $('in-gate').hidden = false;
        $('in-gate-error').textContent = message || '';
        $('in-key').focus();
    }
    $('in-gate-form').addEventListener('submit', e => {
        e.preventDefault();
        const k = $('in-key').value.trim();
        if (!k) return;
        store.set(KEY_STORE, k);
        $('in-key').value = '';
        load();
    });
    $('in-signout').addEventListener('click', () => { store.del(KEY_STORE); data = null; showGate('Signed out.'); });

    /* ---------- data ---------- */
    async function load(quiet) {
        const key = store.get(KEY_STORE);
        if (!key) { showGate(); return; }
        const qs = new URLSearchParams({ range: state.range });
        for (const [k, v] of Object.entries(state.filters)) qs.set(k === 'event' ? 'f_event' : `f_${k}`, v);
        if (inflight) inflight.abort();
        inflight = new AbortController();
        if (!quiet) $('in-status').textContent = 'Loading…';
        try {
            const res = await fetch(`${API}?${qs}`, { headers: { 'X-Insights-Key': key }, signal: inflight.signal, cache: 'no-store' });
            if (res.status === 401) { store.del(KEY_STORE); showGate('That key was not accepted.'); return; }
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            data = await res.json();
            $('in-gate').hidden = true; $('in-app').hidden = false;
            $('in-status').textContent = `Updated ${new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`;
            render();
        } catch (err) {
            if (err.name === 'AbortError') return;
            $('in-status').textContent = 'Could not reach the Insights API.';
            if (!data) showGate('Could not reach the Insights API. Check your connection and try again.');
        }
    }

    function syncUrl() {
        const qs = new URLSearchParams();
        if (state.range !== '7d') qs.set('range', state.range);
        for (const [k, v] of Object.entries(state.filters)) qs.set(k, v);
        const s = qs.toString();
        history.replaceState(null, '', location.pathname + (s ? `?${s}` : ''));
    }

    /* ---------- render ---------- */
    function render() {
        renderRange(); renderFilters(); renderOnline(); renderKpis(); renderChart();
        renderDim('in-pages', 'path');
        renderDim('in-ref', state.tabs.ref);
        renderDim('in-geo', state.tabs.geo);
        renderDim('in-tech', state.tabs.tech);
        renderEvents(); renderVitals(); renderLive();
    }

    function renderRange() {
        document.querySelectorAll('#in-range button').forEach(b => {
            const on = b.dataset.range === state.range;
            b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on));
        });
    }

    function renderFilters() {
        const box = $('in-filters');
        const entries = Object.entries(state.filters);
        box.innerHTML = entries.map(([k, v]) => `<button type="button" class="an-chip" data-clear="${esc(k)}" aria-label="Remove filter ${esc(DIM_LABEL[k])}: ${esc(label(k, v))}">
            <span class="an-chip-k">${esc(DIM_LABEL[k])}</span> ${esc(label(k, v))}<svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button>`).join('');
    }

    function renderOnline() {
        const el = $('in-online');
        el.hidden = false;
        el.classList.toggle('ok', data.online > 0);
        $('in-online-text').textContent = `${fmtInt(data.online)} online`;
    }

    function kpiValue(id, s) {
        switch (id) {
            case 'visitors': return s.visitors;
            case 'pageviews': return s.pageviews;
            case 'bounce': return s.bounce;
            case 'avg': return s.avg_ms;
        }
    }
    function renderKpis() {
        $('in-kpis').innerHTML = KPIS.map(k => {
            const cur = kpiValue(k.id, data.current), prev = kpiValue(k.id, data.previous);
            const value = k.id === 'bounce' ? (cur == null ? '—' : `${Math.round(cur * 100)}%`) : k.id === 'avg' ? fmtDur(cur) : fmtInt(cur);
            let delta = '';
            if (cur != null && prev) {
                const d = k.id === 'bounce' ? cur - prev : cur / prev - 1;
                if (Number.isFinite(d) && Math.abs(d) >= 0.005) {
                    const better = k.good === 'up' ? d > 0 : d < 0;
                    const txt = k.id === 'bounce' ? `${d > 0 ? '+' : ''}${Math.round(d * 100)} pts` : `${d > 0 ? '+' : ''}${Math.round(d * 100)}%`;
                    delta = `<span class="an-delta ${better ? 'good' : 'bad'}">${txt}</span>`;
                }
            }
            return `<button class="an-kpi" role="tab" aria-controls="in-chart-wrap" type="button" data-kpi="${k.id}" aria-selected="${state.kpi === k.id}">
                <span class="an-kpi-label">${k.label}</span><span class="an-kpi-row"><span class="an-kpi-value">${value}</span>${delta}</span></button>`;
        }).join('');
    }

    // Fill missing buckets so quiet hours/days show as zero rather than a skipped point.
    function buckets() {
        const out = [];
        const step = data.bucket === 'hour' ? 3600e3 : 864e5;
        const toKey = ms => {
            const d = new Date(ms + 6 * 3600e3).toISOString();
            return data.bucket === 'hour' ? `${d.slice(0, 10)} ${d.slice(11, 13)}:00` : d.slice(0, 10);
        };
        const map = new Map(data.series.map(r => [r.b, r]));
        for (let t = data.from + step; t <= data.to + 1; t += step) {
            const k = toKey(t);
            if (out.length && out[out.length - 1].b === k) continue;
            out.push(map.get(k) || { b: k, visitors: 0, pageviews: 0 });
        }
        return out;
    }

    function renderChart() {
        if (typeof Chart === 'undefined') return;
        const rows = buckets();
        const labels = rows.map(r => data.bucket === 'hour' ? r.b.slice(11, 16)
            : new Date(r.b + 'T00:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }));
        const paper = cssVar('--paper'), paper2 = cssVar('--paper-2'), paper3 = cssVar('--paper-3'), rule = cssVar('--rule'), taka = cssVar('--taka'), ink1 = cssVar('--ink-1');
        const ctx = $('in-chart').getContext('2d');
        const grad = c => { const g = ctx.createLinearGradient(0, 0, 0, 300); g.addColorStop(0, c + '55'); g.addColorStop(1, c + '00'); return g; };
        const metric = state.kpi === 'pageviews' ? 'pageviews' : 'visitors';
        const title = state.kpi === 'pageviews' ? 'Page views' : 'Visitors';
        $('in-chart-title').textContent = title + (Object.keys(state.filters).length ? ' · filtered' : '');
        $('in-chart-note').textContent = state.kpi === 'bounce' || state.kpi === 'avg'
            ? `${KPIS.find(k => k.id === state.kpi).label} is shown for the whole range; chart shows visitors`
            : `${data.bucket === 'hour' ? 'Hourly' : 'Daily'} · Dhaka time`;
        $('in-chart').setAttribute('aria-label', `${title} per ${data.bucket}, ${labels[0]} to ${labels[labels.length - 1]}. Total ${fmtInt(data.current[metric])}.`);
        if (chart) chart.destroy();
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: title, data: rows.map(r => r[metric]), borderColor: taka, backgroundColor: grad(taka),
                    fill: true, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: .25, cubicInterpolationMode: 'monotone'
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false, animation: { duration: 220 }, transitions: { resize: { animation: { duration: 0 } } },
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: ink1, borderColor: cssVar('--rule-strong'), borderWidth: 1, titleColor: paper, bodyColor: paper2, padding: 10,
                        titleFont: { family: 'IBM Plex Mono', size: 11 }, bodyFont: { family: 'IBM Plex Mono', size: 12 },
                        callbacks: { label: c => ` ${c.dataset.label}: ${fmtInt(c.raw)}` }
                    }
                },
                scales: {
                    x: { grid: { display: false }, border: { color: rule }, ticks: { color: paper3, maxTicksLimit: 8, maxRotation: 0, font: { family: 'IBM Plex Mono', size: 11 } } },
                    y: { beginAtZero: true, grid: { color: rule }, border: { display: false }, ticks: { color: paper3, maxTicksLimit: 5, precision: 0, font: { family: 'IBM Plex Mono', size: 11 } } }
                }
            }
        });
    }

    function label(dim, k) {
        if (dim === 'country') return countryName(k);
        if (dim === 'ref' && k === '(direct)') return 'Direct / none';
        return k;
    }

    function rows(items, opts = {}) {
        if (!items.length) return `<li class="an-empty">${opts.empty || 'No data yet for this range.'}</li>`;
        const max = Math.max(...items.map(i => i.weight || 0), 1);
        return items.map(i => {
            const pct = Math.max(2, (i.weight || 0) / max * 100);
            const inner = `<span class="fill ${i.tone || ''}" style="width:${pct}%"></span>
                <span class="name">${i.lead || ''}<span title="${esc(i.title || i.label)}">${esc(i.label)}</span>${i.meta ? `<span class="meta">${esc(i.meta)}</span>` : ''}</span>
                <span class="val">${i.value}${i.sub ? `<small>${i.sub}</small>` : ''}</span>`;
            return i.filter
                ? `<li><button type="button" class="an-row as-btn" data-fdim="${esc(i.filter[0])}" data-fval="${esc(i.filter[1])}" title="Filter by ${esc(i.title || i.label)}">${inner}</button></li>`
                : `<li class="an-row">${inner}</li>`;
        }).join('');
    }

    function renderDim(listId, dim) {
        const list = (data.dims[dim] || []).filter(r => !(dim.startsWith('utm_') && r.k === '(none)'));
        const total = data.current.visitors || 1;
        $(listId).innerHTML = rows(list.map(r => ({
            lead: dim === 'country' && /^[A-Z]{2}$/.test(r.k) ? `<span class="an-tag">${r.k}</span>` : '',
            label: label(dim, r.k), title: r.k, weight: r.visitors,
            value: fmtInt(r.visitors), sub: `${Math.round(r.visitors / total * 100)}%`,
            filter: state.filters[dim] === r.k ? null : [dim, r.k]
        })), { empty: dim.startsWith('utm_') ? 'No tagged campaigns in this range. Add ?utm_source= to links you share.' : undefined });
    }

    function renderEvents() {
        if (state.filters.event && data.eventProps) {
            $('in-events-sub').textContent = `Properties of “${state.filters.event}”`;
            $('in-events-col-a').textContent = 'Property'; $('in-events-col-b').textContent = 'Count';
            $('in-events').innerHTML = rows(data.eventProps.map(r => ({ label: `${r.key}: ${r.value}`, weight: r.n, value: fmtInt(r.n) })), { empty: 'This event has no properties.' });
            return;
        }
        $('in-events-sub').textContent = 'Click an event to see its properties';
        $('in-events-col-a').textContent = 'Event'; $('in-events-col-b').textContent = 'Count · visitors';
        $('in-events').innerHTML = rows(data.events.map(r => ({
            label: r.k, weight: r.n, value: fmtInt(r.n), sub: `${fmtInt(r.visitors)} visitors`, filter: ['event', r.k]
        })), { empty: 'No custom events in this range.' });
    }

    function renderVitals() {
        const order = ['LCP', 'INP', 'CLS', 'FCP', 'TTFB'];
        const byName = new Map(data.vitals.map(v => [v.name, v]));
        $('in-vitals').innerHTML = rows(order.filter(n => byName.has(n)).map(n => {
            const v = byName.get(n);
            const tone = v.rating === 'good' ? 'good' : v.rating === 'poor' ? 'bad' : '';
            return {
                lead: `<span class="an-status ${v.rating === 'good' ? 'ok' : v.rating === 'poor' ? 'bad' : 'warn'}" title="${esc(v.rating || '')}"></span><span class="an-tag">${n}</span>`,
                label: VITAL_INFO[n].label, weight: v.good ?? 0, tone,
                value: v.p75 == null ? '—' : VITAL_INFO[n].fmt(v.p75),
                sub: `${v.good == null ? '—' : Math.round(v.good * 100) + '% good'} · ${fmtInt(v.n)}`
            };
        }), { empty: 'No Web Vitals reported yet. They arrive when visitors leave a page.' });
    }

    function renderLive() {
        $('in-live').innerHTML = rows((data.onlinePages || []).map(r => ({ label: r.k, weight: r.n, value: fmtInt(r.n) })), { empty: 'Nobody on the site right now.' });
    }

    /* ---------- controls ---------- */
    $('in-range').addEventListener('click', e => {
        const b = e.target.closest('button[data-range]');
        if (!b || b.dataset.range === state.range) return;
        state.range = b.dataset.range; syncUrl(); renderRange(); load();
    });
    $('in-kpis').addEventListener('click', e => {
        const b = e.target.closest('[data-kpi]');
        if (!b || !data) return;
        state.kpi = b.dataset.kpi; renderKpis(); renderChart();
    });
    document.addEventListener('click', e => {
        const f = e.target.closest('[data-fdim]');
        if (f) { state.filters[f.dataset.fdim] = f.dataset.fval; syncUrl(); load(); return; }
        const c = e.target.closest('[data-clear]');
        if (c) { delete state.filters[c.dataset.clear]; syncUrl(); load(); }
    });
    document.querySelectorAll('[data-tabs]').forEach(group => {
        group.addEventListener('click', e => {
            const b = e.target.closest('button[data-tab]');
            if (!b || !data) return;
            state.tabs[group.dataset.tabs] = b.dataset.tab;
            group.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
            const target = { ref: 'in-ref', geo: 'in-geo', tech: 'in-tech' }[group.dataset.tabs];
            renderDim(target, b.dataset.tab);
        });
    });
    $('in-refresh').addEventListener('click', () => load());
    $('an-theme').addEventListener('click', () => {
        const light = document.documentElement.dataset.theme !== 'light';
        if (light) document.documentElement.dataset.theme = 'light'; else delete document.documentElement.dataset.theme;
        store.set('god_theme', light ? 'light' : 'amoled');
        if (data) renderChart();
    });
    // Refresh quietly every minute while the tab is visible (keeps "online" honest).
    setInterval(() => { if (document.visibilityState === 'visible' && data) load(true); }, 60e3);

    load();
})();
