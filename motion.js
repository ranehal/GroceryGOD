// GroceryGOD motion layer — Bazar Ledger (2026-11-02).
// GSAP + ScrollTrigger + Lenis, with React Bits ideas ported to vanilla
// (SplitText-style line reveal, DecryptedText price tally, CountUp, Magnet,
// pointer spotlight background). Pure enhancement: every element is visible
// and fully functional without this file, and script.js is never touched.
(() => {
    const root = document.documentElement;
    const release = () => root.classList.remove('motion-pending');
    const gsap = window.gsap;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    if (!gsap || reduce) { release(); return; }

    const ScrollTrigger = window.ScrollTrigger;
    if (ScrollTrigger) gsap.registerPlugin(ScrollTrigger);
    const EASE = 'expo.out';
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
    const catalogActive = () => document.body.classList.contains('catalog-active');

    // ---- 1. Focal moment: masthead set like type, board tallies its prices --
    function heroEntrance(full = true) {
        const lines = $$('.hero-editorial-title .title-line');
        const rest = $$('.hero-kicker-badge, .hero-editorial-desc, .hero-search-container, .hero-store-strip');
        const board = $('.bazar-board');
        const tl = gsap.timeline({ defaults: { ease: EASE }, onComplete: () => gsap.set([...lines, ...rest, board], { clearProps: 'all' }) });
        tl.fromTo(lines, { clipPath: 'inset(0 0 100% 0)', y: '0.32em' },
            { clipPath: 'inset(0 0 -20% 0)', y: 0, duration: full ? 0.72 : 0.5, stagger: 0.09 }, 0)
          .fromTo(rest, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.42, stagger: 0.06 }, full ? 0.18 : 0.08)
          .fromTo(board, { opacity: 0, y: 10, scale: 0.985 }, { opacity: 1, y: 0, scale: 1, duration: 0.56 }, full ? 0.12 : 0.04);
        release();
        return tl;
    }

    // DecryptedText-style tally: digits roll, then settle on the real price.
    const DIGITS = '0123456789';
    function tally(node, delay = 0) {
        const text = node.firstChild;
        if (!text || text.nodeType !== 3 || node.dataset.tallied === text.nodeValue) return;
        const final = text.nodeValue;
        node.dataset.tallied = final;
        const state = { p: 0 };
        gsap.to(state, {
            p: 1, duration: 0.5, delay, ease: 'power2.out',
            onUpdate() {
                const settled = Math.floor(state.p * final.length);
                text.nodeValue = final.replace(/\d/g, (d, i) => (i < settled ? d : DIGITS[(Math.random() * 10) | 0]));
            },
            onComplete() { text.nodeValue = final; },
        });
    }
    function tallyBoard() {
        $$('#bazar-board-rows .board-row:not(.board-skeleton) .board-price').forEach((n, i) => tally(n, 0.05 + i * 0.07));
    }

    // CountUp for the board footer totals, whenever script.js writes them.
    function countUp(el) {
        let written = '';
        const run = () => {
            if (el.textContent === written) return; // our own tween frame
            const target = Number(String(el.textContent).replace(/[^\d.]/g, ''));
            if (!Number.isFinite(target) || target <= 0) return;
            const from = Number(el.dataset.shown || 0);
            if (from === target) return;
            el.dataset.shown = target;
            const state = { v: from };
            gsap.to(state, {
                v: target, duration: from ? 0.45 : 0.9, ease: 'power3.out', overwrite: true,
                onUpdate() { written = Math.round(state.v).toLocaleString('en-US'); el.textContent = written; },
            });
        };
        new MutationObserver(run).observe(el, { childList: true, characterData: true, subtree: true });
        run();
    }

    // ---- 2. Magnet buttons (React Bits Magnet) — pointer devices only --------
    // Uses the CSS `translate` property via custom props, so the existing
    // `:active { transform: scale(.97) }` press feedback still composes.
    function magnet(el, strength = 0.22, max = 6) {
        const to = (x, y, d) => gsap.to(el, { '--mx': `${x}px`, '--my': `${y}px`, duration: d, ease: 'power3.out', overwrite: 'auto' });
        el.classList.add('is-magnetic');
        el.addEventListener('pointermove', (e) => {
            const r = el.getBoundingClientRect();
            const clamp = (v) => Math.max(-max, Math.min(max, v));
            to(clamp((e.clientX - r.left - r.width / 2) * strength), clamp((e.clientY - r.top - r.height / 2) * strength), 0.3);
        });
        el.addEventListener('pointerleave', () => to(0, 0, 0.45));
    }

    // ---- 3. Ledger spotlight: the ruled grid is lit where the pointer reads --
    function spotlight() {
        const hero = $('#landing-hero');
        const grid = $('.hero-grid-pattern');
        if (!hero || !grid) return;
        hero.addEventListener('pointermove', (e) => {
            const r = hero.getBoundingClientRect();
            gsap.to(grid, {
                '--gx': `${((e.clientX - r.left) / r.width) * 100}%`,
                '--gy': `${((e.clientY - r.top) / r.height) * 100}%`,
                duration: 0.9, ease: 'power3.out', overwrite: 'auto',
            });
        });
    }

    // ---- 4. Lenis smooth scroll — the catalog only --------------------------
    // The hero is a mode switch (wheel/swipe -> catalog), so Lenis steps aside
    // there, inside any nested scroller (sidebar, modals, chat, suggestions)
    // and whenever a modal has locked page scroll.
    let lenis = null;
    let handoffUntil = 0; // trailing wheel momentum after the hero -> catalog switch stays native
    function isNestedScroller(node) {
        if (node === document.body || node === root) return false;
        const oy = getComputedStyle(node).overflowY;
        return (oy === 'auto' || oy === 'scroll') && node.scrollHeight > node.clientHeight + 1;
    }
    function initLenis() {
        if (!window.Lenis || !finePointer) return;
        lenis = new window.Lenis({
            duration: 0.9,
            easing: (t) => 1 - Math.pow(1 - t, 4),
            smoothWheel: true,
            prevent: (node) => !catalogActive()
                || performance.now() < handoffUntil
                || getComputedStyle(document.body).overflowY === 'hidden'
                || isNestedScroller(node),
        });
        if (ScrollTrigger) lenis.on('scroll', ScrollTrigger.update);
        gsap.ticker.add((t) => lenis.raf(t * 1000));
        gsap.ticker.lagSmoothing(0);
    }

    // Safe refresh waits for in-flight scrolls; a plain refresh() restores the
    // saved position and would cut off script.js's smooth scroll back to the hero.
    const refresh = () => { if (catalogActive()) ScrollTrigger.refresh(true); };

    // ---- 5. Scroll-linked ledger rule: where you are in the catalogue -------
    function progressRule() {
        if (!ScrollTrigger) return;
        const bar = document.createElement('div');
        bar.className = 'catalog-progress';
        bar.setAttribute('aria-hidden', 'true');
        document.body.appendChild(bar);
        const setX = gsap.quickSetter(bar, 'scaleX');
        ScrollTrigger.create({ start: 0, end: 'max', onUpdate: (self) => setX(self.progress) });
        let t;
        new ResizeObserver(() => { clearTimeout(t); t = setTimeout(refresh, 200); }).observe(document.body);
    }

    // ---- 6. Hand-off: the catalogue arrives from the board ------------------
    function catalogEntrance() {
        const chrome = $$('.dashboard-header, .intelligence-bar, .stats-bar').filter((n) => n.offsetParent);
        const cards = $$('#sh-grid .p-item-sh').filter((c) => c.getBoundingClientRect().top < innerHeight).slice(0, 18);
        gsap.fromTo(chrome, { opacity: 0, y: -6 }, { opacity: 1, y: 0, duration: 0.26, stagger: 0.04, ease: EASE, clearProps: 'opacity,transform' });
        gsap.fromTo(cards, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.34, ease: EASE, stagger: { each: 0.018, from: 'start' }, delay: 0.06, clearProps: 'opacity,transform' });
    }

    function watchMode() {
        let was = catalogActive();
        new MutationObserver(() => {
            const now = catalogActive();
            if (now === was) return;
            was = now;
            lenis?.reset();
            if (now) { handoffUntil = performance.now() + 600; catalogEntrance(); if (ScrollTrigger) refresh(); } else { heroEntrance(false); }
        }).observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }

    // ---- boot --------------------------------------------------------------
    const heroVisible = $('#landing-hero') && !catalogActive() && scrollY < innerHeight * 0.5;
    if (heroVisible) heroEntrance(true); else release();

    const rows = $('#bazar-board-rows');
    if (rows) { new MutationObserver(tallyBoard).observe(rows, { childList: true }); tallyBoard(); }
    ['hud-total-val', 'hud-deal-val'].forEach((id) => { const el = document.getElementById(id); if (el) countUp(el); });
    if (finePointer) {
        $$('#hero-cta-top, #hero-search-btn, #hero-scroll-down-btn').forEach((el) => magnet(el));
        spotlight();
    }
    initLenis();
    progressRule();
    watchMode();
})();
