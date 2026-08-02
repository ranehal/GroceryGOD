(() => {
  "use strict";


  const COLORS = {
    "Dairy & Eggs": ["#e6efd9", "#6e9d74"],
    "Rice & Grains": ["#f3e8c7", "#aa7d37"],
    "Cooking Essentials": ["#f7ddc5", "#cf713d"],
    "Fresh Produce": ["#d9ead9", "#43835d"],
    "Meat & Fish": ["#efd9d2", "#a34c45"],
    "Beverages": ["#dce9ef", "#4b7e99"],
    "Snacks": ["#f1e1c2", "#b6782d"],
    "Home Care": ["#dce8e2", "#4b8376"],
    "Personal Care": ["#eaddee", "#8a5e8f"]
  };

  const SVG_ART = {
    milk: (c) => `<svg viewBox="0 0 120 160" aria-hidden="true"><path fill="#f7faf2" stroke="${c}" stroke-width="3" d="M29 38h62l-5 111H34Z"/><path fill="${c}" d="M31 39 43 14h36l12 25Z"/><path fill="#fff" d="M45 19h31l7 15H38Z"/><path fill="${c}" opacity=".18" d="M35 71h51v54H35Z"/><circle cx="60" cy="97" r="18" fill="${c}"/><path d="M52 98c6-8 12-8 18 0-4 9-14 9-18 0Z" fill="#fff"/></svg>`,
    eggs: (c) => `<svg viewBox="0 0 130 150" aria-hidden="true"><path fill="#d7c29e" stroke="${c}" stroke-width="3" d="M15 67h100l-8 62H23Z"/><path fill="#ead9b9" stroke="${c}" stroke-width="3" d="m20 66 12-34h66l12 34Z"/><g fill="#fff8e8" stroke="${c}" stroke-width="2"><ellipse cx="40" cy="59" rx="11" ry="18"/><ellipse cx="65" cy="54" rx="11" ry="18"/><ellipse cx="90" cy="59" rx="11" ry="18"/></g><path d="M24 89h82" stroke="${c}" stroke-width="3"/><text x="65" y="112" text-anchor="middle" fill="${c}" font-size="13" font-weight="800">FARM</text></svg>`,
    rice: (c) => `<svg viewBox="0 0 120 160" aria-hidden="true"><path fill="#fff9e8" stroke="${c}" stroke-width="3" d="M27 25h66l10 116c-26 11-56 11-86 0Z"/><path fill="${c}" d="M28 25h64l-4 17H32Z"/><rect x="34" y="61" width="52" height="52" rx="6" fill="${c}" opacity=".17"/><path fill="none" stroke="${c}" stroke-width="3" d="M60 77c-8 8-8 21 0 27m0-27c8 8 8 21 0 27m-17-14h34"/><text x="60" y="128" text-anchor="middle" fill="${c}" font-size="10" font-weight="800">PREMIUM</text></svg>`,
    oil: (c) => `<svg viewBox="0 0 100 170" aria-hidden="true"><path fill="${c}" d="M39 7h24v22H39Z"/><path fill="#f5c746" stroke="${c}" stroke-width="3" d="M31 28h39l8 118c-15 10-42 10-56 0Z"/><rect x="27" y="70" width="48" height="49" rx="5" fill="#fff8dc"/><circle cx="51" cy="93" r="15" fill="${c}" opacity=".85"/><path d="M42 94c7-8 15-7 20 0-6 8-14 8-20 0Z" fill="#f5c746"/></svg>`,
    bottle: (c) => `<svg viewBox="0 0 100 170" aria-hidden="true"><path fill="${c}" d="M39 7h22v19H39Z"/><path fill="#f4faf9" stroke="${c}" stroke-width="3" d="M33 25h34l8 123c-15 8-34 8-49 0Z"/><rect x="28" y="63" width="44" height="58" rx="7" fill="${c}" opacity=".2"/><circle cx="50" cy="91" r="16" fill="${c}"/><path d="M42 92h16" stroke="#fff" stroke-width="3"/></svg>`,
    produce: (c, icon) => `<svg viewBox="0 0 140 150" aria-hidden="true"><path fill="#c8a16a" stroke="${c}" stroke-width="3" d="M21 69h98l-13 65H34Z"/><path d="M27 83h86M30 103h80M45 70l8 64m42-64-8 64" stroke="${c}" stroke-width="3" opacity=".6"/><text x="70" y="68" text-anchor="middle" font-size="58">${icon}</text></svg>`,
    box: (c, label) => `<svg viewBox="0 0 120 160" aria-hidden="true"><rect x="23" y="22" width="74" height="126" rx="8" fill="#fffaf0" stroke="${c}" stroke-width="3"/><path fill="${c}" d="M24 22h72v27H24Z"/><rect x="34" y="65" width="52" height="48" rx="6" fill="${c}" opacity=".17"/><circle cx="60" cy="89" r="15" fill="${c}"/><text x="60" y="93" text-anchor="middle" fill="#fff" font-size="10" font-weight="800">${label.slice(0,4).toUpperCase()}</text><path d="M38 128h44" stroke="${c}" stroke-width="3"/></svg>`,
    meat: (c, icon) => `<svg viewBox="0 0 140 150" aria-hidden="true"><path fill="#f8ede8" stroke="${c}" stroke-width="3" d="M17 48h106l-8 85H25Z"/><path fill="${c}" d="M18 48h104v19H18Z"/><text x="70" y="107" text-anchor="middle" font-size="51">${icon}</text></svg>`
  };

  function artFor(type, color) {
    if (type && type.startsWith("http")) {
      return `<img src="${type}" style="width:100%;height:100%;object-fit:contain;mix-blend-mode:multiply;padding:8px;box-sizing:border-box;" loading="lazy" alt="" />`;
    }
    if (["milk"].includes(type)) return SVG_ART.milk(color);
    if (type === "eggs") return SVG_ART.eggs(color);
    if (["rice", "lentil", "oats", "flour", "sugar", "salt"].includes(type)) return SVG_ART.rice(color);
    if (["oil"].includes(type)) return SVG_ART.oil(color);
    if (["juice", "water", "shampoo", "cleaner"].includes(type)) return SVG_ART.bottle(color);
    if (["banana", "apple", "potato", "tomato", "onion"].includes(type)) {
      const icons = { banana: "🍌", apple: "🍎", potato: "🥔", tomato: "🍅", onion: "🧅" };
      return SVG_ART.produce(color, icons[type]);
    }
    if (["chicken", "meat", "fish", "shrimp"].includes(type)) {
      const icons = { chicken: "🍗", meat: "🥩", fish: "🐟", shrimp: "🍤" };
      return SVG_ART.meat(color, icons[type]);
    }
    return SVG_ART.box(color, type || "ITEM");
  }

  const averageOf = values => values.length ? values.reduce((sum, n) => sum + n, 0) / values.length : 0;

  const PALETTE = [
    ["#e6efd9", "#6e9d74"],
    ["#f3e8c7", "#aa7d37"],
    ["#f7ddc5", "#cf713d"],
    ["#d9ead9", "#43835d"],
    ["#efd9d2", "#a34c45"],
    ["#dce9ef", "#4b7e99"],
    ["#f1e1c2", "#b6782d"],
    ["#dce8e2", "#4b8376"],
    ["#eaddee", "#8a5e8f"]
  ];
  function getColorCategory(categoryName) {
    if (COLORS[categoryName]) return COLORS[categoryName];
    let hash = 0;
    for(let i=0; i<categoryName.length; i++) hash = categoryName.charCodeAt(i) + ((hash << 5) - hash);
    return PALETTE[Math.abs(hash) % PALETTE.length];
  }

  let products = [];

  const storage = {
    get(key, fallback = null) { try { return window.localStorage.getItem(key) ?? fallback; } catch { return fallback; } },
    set(key, value) { try { window.localStorage.setItem(key, value); } catch { /* Storage can be unavailable in previews. */ } }
  };

  function readSaved() {
    try {
      const value = JSON.parse(storage.get("pulse-market-saved", "[]"));
      return Array.isArray(value) ? value : [];
    } catch { return []; }
  }

  const state = {
    query: "",
    window: 30,
    sort: "smart",
    categories: new Set(),
    subcategories: new Set(),
    unit: "all",
    maxPrice: 2500,
    inStockOnly: true,
    deal: "all",
    savedOnly: false,
    saved: new Set(readSaved()),
    activeProductId: null,
    chartRange: 90,
    chartPoints: []
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const money = value => `৳${Math.round(value).toLocaleString("en-BD")}`;
  const percent = value => `${Math.abs(value).toFixed(value < 10 ? 1 : 0)}%`;
  const unitLabel = unit => unit === "l" ? "L" : unit.length > 2 ? unit : unit.toUpperCase();
  const packageLabel = product => product.unit || `${product.quantity} PCS`;
  const perUnitLabel = product => `per ${product.unit && product.unit.match(/kg|l|gm/i) ? product.unit : "item"}`;
  const windowPoints = (product, days) => product.history.slice(-Math.min(days, product.history.length));

  const els = {
    grid: $("#productGrid"), resultCount: $("#resultCount"), search: $("#searchInput"), sort: $("#sortSelect"),
    maxPrice: $("#maxPrice"), maxPriceOutput: $("#maxPriceOutput"), stock: $("#inStockOnly"),
    savedToggle: $("#savedToggle"), savedCount: $("#savedCount"), activeFilters: $("#activeFilters"),
    empty: $("#emptyState"), categoryPopover: $("#categoryPopover"), subcategoryPopover: $("#subcategoryPopover"),
    categorySummary: $("#categorySummary"), subcategorySummary: $("#subcategorySummary"),
    trackedStat: $("#trackedStat"), directionStat: $("#directionStat"), directionDetail: $("#directionDetail"),
    bestValueStat: $("#bestValueStat"), savingsStat: $("#savingsStat"), toast: $("#toast"),
    modal: $("#historyModal"), chart: $("#historyChart"), chartGrid: $("#chartGrid"), chartLabels: $("#chartLabels"),
    chartLine: $("#chartLine"), chartArea: $("#chartArea"), chartAverage: $("#chartAverageLine"),
    crosshair: $("#chartCrosshair"), chartPoint: $("#chartPoint"), chartHitArea: $("#chartHitArea"),
    tooltip: $("#chartTooltip"), tooltipDate: $("#tooltipDate"), tooltipPrice: $("#tooltipPrice"), tooltipDelta: $("#tooltipDelta"),
    chartStage: $("#chartStage"), modalChartArt: $("#modalChartArt"), historyPosition: $("#historyPosition"),
    heroObserved: $("#heroObserved"), heroDiscountCount: $("#heroDiscountCount"), heroStockRate: $("#heroStockRate"),
    heroDrops: $("#heroDrops"), heroMedianSaving: $("#heroMedianSaving")
  };

  function metrics(product, days = state.window) {
    const points = windowPoints(product, days);
    const prices = points.map(p => p.price);
    const avg = averageOf(prices);
    const low = Math.min(...prices);
    const high = Math.max(...prices);
    const current = points.at(-1).price;
    const first = points[0].price;
    const variance = averageOf(prices.map(price => (price - avg) ** 2));
    return {
      points, avg, low, high, current, first,
      change: current - first,
      changePct: first ? ((current - first) / first) * 100 : 0,
      vsAvgPct: avg ? ((current - avg) / avg) * 100 : 0,
      volatility: avg ? Math.sqrt(variance) / avg * 100 : 0,
      isLowest: current <= low,
      savings: Math.max(0, avg - current)
    };
  }

  function dealClass(product) {
    const m = metrics(product);
    const lifetime = metrics(product, product.history.length);
    if (lifetime.isLowest) return "alltime";
    if (m.isLowest) return "lowest";
    if (product.discount >= 15 || m.vsAvgPct <= -12) return "great";
    return "good";
  }

  function dealLabel(product) {
    const m = metrics(product);
    const lifetime = metrics(product, product.history.length);
    if (lifetime.isLowest) return "All-time low";
    if (m.isLowest) return `Lowest in ${state.window} days`;
    if (product.discount >= 15 || m.vsAvgPct <= -12) return `Great deal · ${Math.max(product.discount, Math.abs(Math.round(m.vsAvgPct)))}%`;
    if (m.vsAvgPct <= -5 || product.discount >= 5) return `Good buy · ${Math.max(product.discount, Math.abs(Math.round(m.vsAvgPct)))}%`;
    if (m.change < 0) return `Price falling · ${money(Math.abs(m.change))}`;
    return "Near usual price";
  }

  function sparklinePath(points, width = 270, height = 34) {
    const values = points.map(p => p.price);
    const min = Math.min(...values), max = Math.max(...values), spread = max - min || 1;
    return points.map((point, index) => {
      const x = index / Math.max(1, points.length - 1) * width;
      const y = 2 + (max - point.price) / spread * (height - 5);
      return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
  }

  function productCard(product, index = 0) {
    const m = metrics(product);
    const score = Math.round(Math.max(0, (m.avg - product.price) / m.avg * 100));
    const saved = state.saved.has(product.id);
    const card = document.createElement("article");
    card.className = "product-card";
    card.style.setProperty("--card-index", String(Math.min(index, 14)));
    card.tabIndex = 0;
    card.dataset.productId = product.id;
    card.setAttribute("aria-label", `${product.name}, ${money(product.price)}. Open price history.`);
    card.innerHTML = `
      <div class="product-visual" style="--art-bg:${product.background};--art-dot:${product.accent}">
        <span class="deal-ribbon ${dealClass(product)}">${dealLabel(product)}</span>
        <button class="bookmark-button ${saved ? "is-saved" : ""}" type="button" aria-label="${saved ? "Remove" : "Save"} ${product.name}" aria-pressed="${saved}">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4.8A1.8 1.8 0 0 1 7.8 3h8.4A1.8 1.8 0 0 1 18 4.8V21l-6-3.7L6 21Z"/></svg>
        </button>
        <div class="product-art" style="--art-rotate:${product.rotation}">${artFor(product.art, product.accent)}</div>
      </div>
      <div class="card-body">
        <div class="card-meta"><span>${product.brand}</span><span class="stock-status ${product.inStock ? "" : "out"}">${product.inStock ? "● In stock" : "● Out of stock"}</span></div>
        <h3>${product.name}</h3>
        <p class="package-line">${packageLabel(product)} · ${product.subcategory}</p>
        <div class="price-block">
          <div>
            <span class="current-price">${money(product.price)}</span>${product.oldPrice > product.price ? `<span class="old-price">${money(product.oldPrice)}</span>` : ""}
            <span class="unit-price">${money(product.unitPrice)} ${perUnitLabel(product)}</span>
          </div>
          <div class="price-score"><strong>${score ? `${score}% below avg.` : "At average"}</strong><span>${state.window}-day context</span></div>
        </div>
        <div class="sparkline-wrap">
          <span class="sparkline-caption">${m.change <= 0 ? "Falling" : "Rising"} ${money(Math.abs(m.change))}</span>
          <svg class="sparkline" viewBox="0 0 270 36" preserveAspectRatio="none" aria-hidden="true">
            <path d="${sparklinePath(m.points, 270, 34)}"/>
            <circle cx="270" cy="${(() => { const vals = m.points.map(p => p.price), min = Math.min(...vals), max = Math.max(...vals), spread = max-min||1; return (2+(max-vals.at(-1))/spread*29).toFixed(1); })()}" r="3"/>
          </svg>
        </div>
        <div class="card-footer">
          <button class="history-link" type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19V5m0 14h16M7 15l4-4 3 2 5-7"/></svg> View full history</button>
          <span class="category-dot" style="--art-dot:${product.accent}" title="${product.category}"></span>
        </div>
      </div>`;
    card.addEventListener("click", event => {
      if (event.target.closest(".bookmark-button")) return toggleSaved(product.id);
      openHistory(product.id);
    });
    card.addEventListener("keydown", event => {
      if ((event.key === "Enter" || event.key === " ") && !event.target.closest("button")) {
        event.preventDefault(); openHistory(product.id);
      }
    });
    return card;
  }

  function filteredProducts() {
    const query = state.query.trim().toLowerCase();
    return products.filter(product => {
      const m = metrics(product);
      const matchesQuery = !query || [product.name, product.brand, product.category, product.subcategory].some(v => v.toLowerCase().includes(query));
      const matchesCategory = !state.categories.size || state.categories.has(product.category);
      const matchesSubcategory = !state.subcategories.size || state.subcategories.has(product.subcategory);
      const matchesUnit = state.unit === "all" || product.unit === state.unit;
      const matchesPrice = product.price <= state.maxPrice;
      const matchesStock = !state.inStockOnly || product.inStock;
      const matchesSaved = !state.savedOnly || state.saved.has(product.id);
      const matchesDeal = state.deal === "all"
        || (state.deal === "great" && (product.discount >= 15 || m.vsAvgPct <= -12))
        || (state.deal === "good" && (product.discount >= 5 || m.vsAvgPct <= -5))
        || (state.deal === "drop" && m.change < 0)
        || (state.deal === "alltime" && metrics(product, product.history.length).isLowest)
        || (state.deal === "lowest" && m.isLowest);
      return matchesQuery && matchesCategory && matchesSubcategory && matchesUnit && matchesPrice && matchesStock && matchesSaved && matchesDeal;
    });
  }

  function sortProducts(items) {
    return items.sort((a, b) => {
      const ma = metrics(a), mb = metrics(b);
      switch (state.sort) {
        case "discount": return b.discount - a.discount;
        case "drop": return ma.change - mb.change;
        case "price-asc": return a.price - b.price;
        case "price-desc": return b.price - a.price;
        case "unit-asc": return a.unitPrice - b.unitPrice;
        case "name": return a.name.localeCompare(b.name);
        default: {
          const scoreA = a.discount * 1.2 - ma.vsAvgPct + (ma.isLowest ? 18 : 0) + (metrics(a, a.history.length).isLowest ? 25 : 0) - (a.inStock ? 0 : 100);
          const scoreB = b.discount * 1.2 - mb.vsAvgPct + (mb.isLowest ? 18 : 0) + (metrics(b, b.history.length).isLowest ? 25 : 0) - (b.inStock ? 0 : 100);
          return scoreB - scoreA;
        }
      }
    });
  }

  function render() {
    const items = sortProducts(filteredProducts());
    els.grid.replaceChildren(...items.map((product, index) => productCard(product, index)));
    els.resultCount.textContent = items.length.toLocaleString();
    els.savedCount.textContent = state.saved.size;
    els.savedToggle.setAttribute("aria-pressed", String(state.savedOnly));
    els.maxPriceOutput.value = money(state.maxPrice);
    els.empty.hidden = items.length > 0;
    els.grid.hidden = items.length === 0;
    renderStats(items);
    renderHeroStats();
    renderActiveFilters();
    updateSummaries();
  }

  function renderStats(items) {
    els.trackedStat.textContent = items.length.toLocaleString();
    const falling = items.filter(p => metrics(p).change < 0).length;
    const below = items.filter(p => metrics(p).vsAvgPct < 0).length;
    els.directionStat.textContent = falling >= items.length / 2 ? "Falling" : "Mixed";
    els.directionStat.classList.toggle("positive", falling >= items.length / 2);
    els.directionDetail.textContent = `${below} product${below === 1 ? "" : "s"} below average`;
    const best = [...items].sort((a,b) => a.unitPrice - b.unitPrice)[0];
    els.bestValueStat.textContent = best ? `${money(best.unitPrice)}/${unitLabel(best.unit)}` : "—";
    els.savingsStat.textContent = money(items.reduce((sum, item) => sum + metrics(item).savings, 0));
  }

  function renderHeroStats() {
    const discounts = products.filter(product => product.oldPrice > product.price).length;
    const inStock = products.filter(product => product.inStock).length;
    const drops = products.filter(product => product.trend < 0).length;
    const savings = products.map(product => Math.max(0, product.average - product.price)).sort((a, b) => a - b);
    const middle = Math.floor(savings.length / 2);
    const median = savings.length % 2 ? savings[middle] : averageOf(savings.slice(Math.max(0, middle - 1), middle + 1));
    els.heroObserved.textContent = products.length.toLocaleString();
    els.heroDiscountCount.textContent = discounts.toLocaleString();
    els.heroStockRate.textContent = `${(inStock / products.length * 100).toFixed(1)}%`;
    els.heroDrops.textContent = drops.toLocaleString();
    els.heroMedianSaving.textContent = money(median);
  }

  function renderActiveFilters() {
    const filters = [];
    state.categories.forEach(value => filters.push({ label: value, clear: () => state.categories.delete(value) }));
    state.subcategories.forEach(value => filters.push({ label: value, clear: () => state.subcategories.delete(value) }));
    if (state.unit !== "all") filters.push({ label: `Unit: ${unitLabel(state.unit)}`, clear: () => state.unit = "all" });
    if (state.deal !== "all") filters.push({ label: `View: ${state.deal}`, clear: () => state.deal = "all" });
    if (state.savedOnly) filters.push({ label: "Saved only", clear: () => state.savedOnly = false });
    if (state.query) filters.push({ label: `Search: “${state.query}”`, clear: () => { state.query = ""; els.search.value = ""; } });
    els.activeFilters.replaceChildren(...filters.map(({ label, clear }) => {
      const chip = document.createElement("span");
      chip.className = "active-filter";
      chip.innerHTML = `${label}<button type="button" aria-label="Remove ${label}">×</button>`;
      chip.querySelector("button").addEventListener("click", () => { clear(); syncControls(); render(); });
      return chip;
    }));
  }

  function availableSubcategories() {
    const selected = state.categories.size ? products.filter(p => state.categories.has(p.category)) : products;
    return [...new Set(selected.map(p => p.subcategory))].sort();
  }

  function renderPopover(popover, items, selectedSet, type) {
    const counts = Object.fromEntries(items.map(item => [item, products.filter(p => p[type] === item).length]));
    popover.innerHTML = `
      <div class="popover-actions"><button type="button" data-action="all">Select all</button><button type="button" data-action="none">Clear</button></div>
      ${items.map(item => `<label class="popover-option"><input type="checkbox" value="${item.replaceAll('"', '&quot;')}" ${selectedSet.has(item) ? "checked" : ""}><span>${item}</span><small>${counts[item]}</small></label>`).join("")}`;
    popover.querySelector('[data-action="all"]').addEventListener("click", () => {
      selectedSet.clear(); items.forEach(item => selectedSet.add(item));
      if (type === "category") refreshSubcategoryPopover();
      renderPopover(popover, items, selectedSet, type); render();
    });
    popover.querySelector('[data-action="none"]').addEventListener("click", () => {
      selectedSet.clear();
      if (type === "category") { state.subcategories.clear(); refreshSubcategoryPopover(); }
      renderPopover(popover, items, selectedSet, type); render();
    });
    $$('input[type="checkbox"]', popover).forEach(input => input.addEventListener("change", () => {
      input.checked ? selectedSet.add(input.value) : selectedSet.delete(input.value);
      if (type === "category") {
        const valid = new Set(availableSubcategories());
        state.subcategories = new Set([...state.subcategories].filter(sub => valid.has(sub)));
        refreshSubcategoryPopover();
      }
      render();
    }));
  }

  function refreshSubcategoryPopover() {
    renderPopover(els.subcategoryPopover, availableSubcategories(), state.subcategories, "subcategory");
  }

  function updateSummaries() {
    els.categorySummary.textContent = !state.categories.size ? "All categories" : state.categories.size === 1 ? [...state.categories][0] : `${state.categories.size} selected`;
    els.subcategorySummary.textContent = !state.subcategories.size ? "All subcategories" : state.subcategories.size === 1 ? [...state.subcategories][0] : `${state.subcategories.size} selected`;
  }

  function syncControls() {
    $$("[data-window]").forEach(button => button.classList.toggle("is-active", +button.dataset.window === state.window));
    $$("[data-unit]").forEach(button => button.classList.toggle("is-active", button.dataset.unit === state.unit));
    $$("[data-deal]").forEach(button => button.classList.toggle("is-active", button.dataset.deal === state.deal));
    els.sort.value = state.sort;
    els.stock.checked = state.inStockOnly;
    els.maxPrice.value = state.maxPrice;
    renderPopover(els.categoryPopover, [...new Set(products.map(p => p.category))].sort(), state.categories, "category");
    refreshSubcategoryPopover();
  }

  function toggleSaved(id) {
    state.saved.has(id) ? state.saved.delete(id) : state.saved.add(id);
    storage.set("pulse-market-saved", JSON.stringify([...state.saved]));
    showToast(state.saved.has(id) ? "Saved to your pricebook" : "Removed from saved items");
    render();
    if (state.activeProductId === id && els.modal.open) updateModalBookmark();
  }

  let toastTimer;
  function showToast(message) {
    clearTimeout(toastTimer);
    els.toast.textContent = message;
    els.toast.classList.add("is-visible");
    toastTimer = setTimeout(() => els.toast.classList.remove("is-visible"), 1800);
  }

  function resetFilters() {
    state.query = ""; state.window = 30; state.sort = "smart"; state.categories.clear(); state.subcategories.clear();
    state.unit = "all"; state.maxPrice = 2500; state.inStockOnly = true; state.deal = "all"; state.savedOnly = false;
    els.search.value = "";
    syncControls(); render();
  }

  function historySequence() {
    const visible = sortProducts(filteredProducts());
    return visible.some(product => product.id === state.activeProductId) ? visible : products;
  }

  function updateHistoryPosition() {
    const sequence = historySequence();
    const index = Math.max(0, sequence.findIndex(product => product.id === state.activeProductId));
    els.historyPosition.textContent = `${index + 1} / ${sequence.length}`;
  }

  function openHistory(id, { preserveRange = false, focusChart = true } = {}) {
    const product = products.find(p => p.id === id);
    if (!product) return;
    state.activeProductId = id;
    if (!preserveRange) state.chartRange = 90;
    $("#modalProductName").textContent = product.name;
    $("#modalProductMeta").textContent = `${product.category} · ${product.subcategory} · ${packageLabel(product)}`;
    $("#modalProductArt").style.background = product.background;
    $("#modalProductArt").innerHTML = artFor(product.art, product.accent);
    els.modalChartArt.innerHTML = artFor(product.art, product.accent);
    $("#modalCurrentPrice").textContent = money(product.price);
    $("#modalUnitPrice").textContent = `${money(product.unitPrice)} ${perUnitLabel(product)}`;
    updateModalBookmark();
    updateHistoryPosition();
    $$("[data-chart-range]").forEach(button => button.classList.toggle("is-active", +button.dataset.chartRange === state.chartRange));
    renderHistoryChart();
    if (!els.modal.open) els.modal.showModal();
    document.body.style.overflow = "hidden";
    if (focusChart) requestAnimationFrame(() => els.chartStage.focus({ preventScroll: true }));
  }

  function cycleHistory(direction) {
    const sequence = historySequence();
    if (!sequence.length) return;
    const current = Math.max(0, sequence.findIndex(product => product.id === state.activeProductId));
    const next = (current + direction + sequence.length) % sequence.length;
    const app = $(".history-app");
    app.classList.remove("is-cycling");
    void app.offsetWidth;
    app.classList.add("is-cycling");
    openHistory(sequence[next].id, { preserveRange: true, focusChart: true });
    window.setTimeout(() => app.classList.remove("is-cycling"), 360);
  }

  function closeHistory() {
    els.modal.close();
    document.body.style.overflow = "";
    state.activeProductId = null;
  }

  function updateModalBookmark() {
    const saved = state.saved.has(state.activeProductId);
    $("#modalBookmark").classList.toggle("is-saved", saved);
    $("#modalBookmark").setAttribute("aria-pressed", String(saved));
    $("#modalBookmark span").textContent = saved ? "Saved" : "Save";
  }

  function svgEl(tag, attrs = {}) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  }

  function longestStableRun(points) {
    let best = 1, run = 1;
    for (let i = 1; i < points.length; i++) {
      if (points[i].price === points[i - 1].price) run++; else run = 1;
      best = Math.max(best, run);
    }
    return best;
  }

  function renderHistoryChart() {
    const product = products.find(p => p.id === state.activeProductId);
    if (!product) return;
    const m = metrics(product, state.chartRange);
    state.chartPoints = m.points;
    const W = 1200, H = 620, left = 75, right = 45, top = 28, bottom = 52;
    const innerW = W - left - right, innerH = H - top - bottom;
    const pad = Math.max(4, (m.high - m.low) * .15);
    const yMin = Math.max(0, m.low - pad), yMax = m.high + pad, ySpread = yMax - yMin || 1;
    const x = index => left + index / Math.max(1, m.points.length - 1) * innerW;
    const y = price => top + (yMax - price) / ySpread * innerH;
    const line = m.points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(2)},${y(p.price).toFixed(2)}`).join(" ");
    const area = `${line} L${x(m.points.length - 1).toFixed(2)},${top + innerH} L${left},${top + innerH} Z`;
    els.chartLine.setAttribute("d", line);
    els.chartArea.setAttribute("d", area);
    els.chartAverage.setAttribute("d", `M${left},${y(m.avg)}H${W - right}`);
    els.chartGrid.replaceChildren();
    els.chartLabels.replaceChildren();
    for (let i = 0; i < 5; i++) {
      const gy = top + i / 4 * innerH;
      const value = yMax - i / 4 * ySpread;
      els.chartGrid.append(svgEl("line", { x1: left, x2: W - right, y1: gy, y2: gy, class: "chart-grid-line" }));
      const label = svgEl("text", { x: left - 14, y: gy + 4, "text-anchor": "end", class: "chart-axis-label" });
      label.textContent = money(value);
      els.chartLabels.append(label);
    }
    const tickCount = window.innerWidth < 700 ? 4 : 6;
    for (let i = 0; i < tickCount; i++) {
      const index = Math.round(i / (tickCount - 1) * (m.points.length - 1));
      const p = m.points[index];
      const label = svgEl("text", { x: x(index), y: H - 16, "text-anchor": i === 0 ? "start" : i === tickCount - 1 ? "end" : "middle", class: "chart-axis-label" });
      label.textContent = p.date.toLocaleDateString("en", { month: "short", day: "numeric" });
      els.chartLabels.append(label);
    }
    $("#chartHeadline").textContent = `${state.chartRange === 365 ? "One-year" : `${state.chartRange}-day`} view`;
    const trend = m.changePct < -1 ? `Down ${percent(m.changePct)}` : m.changePct > 1 ? `Up ${percent(m.changePct)}` : "Stable";
    $("#chartTrendLabel").textContent = trend;
    $("#metricLow").textContent = money(m.low);
    $("#metricHigh").textContent = money(m.high);
    $("#metricAverage").textContent = money(m.avg);
    $("#metricVolatility").textContent = `${m.volatility.toFixed(1)}%`;
    $("#metricVsAverage").textContent = `${m.vsAvgPct <= 0 ? "↓" : "↑"} ${percent(m.vsAvgPct)}`;
    $("#modalDealBadge").textContent = m.isLowest ? `Lowest in ${state.chartRange} days` : m.vsAvgPct <= -5 ? `${percent(m.vsAvgPct)} below average` : m.vsAvgPct > 5 ? `${percent(m.vsAvgPct)} above average` : "Near window average";
    const lowPoint = m.points.find(p => p.price === m.low);
    $("#bestDay").textContent = lowPoint.date.toLocaleDateString("en", { month: "short", day: "numeric" });
    $("#stableRun").textContent = `${longestStableRun(m.points)} days`;
    $("#savedVsPeak").textContent = money(m.high - m.current);
    els.crosshair.hidden = true; els.chartPoint.hidden = true; els.tooltip.hidden = true;
  }

  function chartPointerMove(event) {
    if (!state.chartPoints.length) return;
    const rect = els.chart.getBoundingClientRect();
    const svgX = (event.clientX - rect.left) / rect.width * 1200;
    const left = 75, right = 45, innerW = 1200 - left - right;
    const ratio = Math.max(0, Math.min(1, (svgX - left) / innerW));
    const index = Math.round(ratio * (state.chartPoints.length - 1));
    const product = products.find(p => p.id === state.activeProductId);
    const m = metrics(product, state.chartRange);
    const point = state.chartPoints[index];
    const pad = Math.max(4, (m.high - m.low) * .15), yMin = Math.max(0, m.low - pad), yMax = m.high + pad;
    const chartX = left + index / Math.max(1, state.chartPoints.length - 1) * innerW;
    const chartY = 28 + (yMax - point.price) / (yMax - yMin || 1) * 540;
    els.crosshair.setAttribute("x1", chartX); els.crosshair.setAttribute("x2", chartX); els.crosshair.hidden = false;
    els.chartPoint.setAttribute("cx", chartX); els.chartPoint.setAttribute("cy", chartY); els.chartPoint.hidden = false;
    els.tooltipDate.textContent = point.date.toLocaleDateString("en", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
    els.tooltipPrice.textContent = money(point.price);
    const delta = (point.price - m.avg) / m.avg * 100;
    els.tooltipDelta.textContent = Math.abs(delta) < 1 ? "At window average" : `${percent(delta)} ${delta < 0 ? "below" : "above"} average`;
    const px = chartX / 1200 * rect.width, py = chartY / 620 * rect.height;
    els.tooltip.style.left = `${Math.max(70, Math.min(rect.width - 70, px))}px`;
    els.tooltip.style.top = `${Math.max(75, py)}px`;
    els.tooltip.hidden = false;
  }

  function bindEvents() {
    els.search.addEventListener("input", event => { state.query = event.target.value; render(); });
    document.addEventListener("keydown", event => {
      if (els.modal.open) {
        if (event.key === "ArrowLeft") { event.preventDefault(); cycleHistory(-1); return; }
        if (event.key === "ArrowRight") { event.preventDefault(); cycleHistory(1); return; }
        if (event.key === "Escape" || (event.code === "Space" && !event.target.closest("button, input, select, textarea, a"))) {
          event.preventDefault(); closeHistory(); return;
        }
      }
      if (event.key === "/" && document.activeElement.tagName !== "INPUT") { event.preventDefault(); els.search.focus(); }
    });
    els.sort.addEventListener("change", event => { state.sort = event.target.value; render(); });
    els.maxPrice.addEventListener("input", event => { state.maxPrice = +event.target.value; render(); });
    els.stock.addEventListener("change", event => { state.inStockOnly = event.target.checked; render(); });
    els.savedToggle.addEventListener("click", () => { state.savedOnly = !state.savedOnly; render(); });
    $("#savedNavButton").addEventListener("click", () => { state.savedOnly = true; render(); $("#catalog").scrollIntoView(); });
    $$("[data-window]").forEach(button => button.addEventListener("click", () => { state.window = +button.dataset.window; syncControls(); render(); }));
    $$("[data-unit]").forEach(button => button.addEventListener("click", () => { state.unit = button.dataset.unit; syncControls(); render(); }));
    $$("[data-deal]").forEach(button => button.addEventListener("click", () => { state.deal = button.dataset.deal; syncControls(); render(); }));
    $$(".multi-select > .filter-button").forEach(button => button.addEventListener("click", event => {
      event.stopPropagation();
      const popover = button.nextElementSibling;
      $$(".filter-popover").forEach(other => { if (other !== popover) { other.classList.remove("is-open"); other.previousElementSibling.setAttribute("aria-expanded", "false"); } });
      const open = popover.classList.toggle("is-open");
      button.setAttribute("aria-expanded", String(open));
    }));
    document.addEventListener("click", event => {
      if (!event.target.closest(".multi-select")) $$(".filter-popover").forEach(popover => { popover.classList.remove("is-open"); popover.previousElementSibling.setAttribute("aria-expanded", "false"); });
    });
    $("#clearFilters").addEventListener("click", resetFilters);
    $("#emptyReset").addEventListener("click", resetFilters);
    $("#themeToggle").addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "" : "dark";
      document.documentElement.dataset.theme = next;
      storage.set("pulse-market-theme", next);
      if (els.modal.open) renderHistoryChart();
    });
    $("#openFeaturedHistory").addEventListener("click", () => openHistory("meadow-milk"));
    $("#historyClose").addEventListener("click", closeHistory);
    $("#historyCloseIcon").addEventListener("click", closeHistory);
    $("#historyPrev").addEventListener("click", () => cycleHistory(-1));
    $("#historyNext").addEventListener("click", () => cycleHistory(1));
    $("#modalBookmark").addEventListener("click", () => toggleSaved(state.activeProductId));
    els.modal.addEventListener("click", event => { if (event.target === els.modal) closeHistory(); });
    els.modal.addEventListener("cancel", event => { event.preventDefault(); closeHistory(); });
    $$("[data-chart-range]").forEach(button => button.addEventListener("click", () => {
      state.chartRange = +button.dataset.chartRange;
      $$("[data-chart-range]").forEach(item => item.classList.toggle("is-active", item === button));
      renderHistoryChart();
    }));
    els.chartHitArea.addEventListener("pointermove", chartPointerMove);
    els.chartHitArea.addEventListener("pointerleave", () => { els.crosshair.hidden = true; els.chartPoint.hidden = true; els.tooltip.hidden = true; });
    window.addEventListener("resize", () => { if (els.modal.open) renderHistoryChart(); });
  }

  async function init() {
    const savedTheme = storage.get("pulse-market-theme", "");
    if (savedTheme) document.documentElement.dataset.theme = savedTheme;
    try {
      const res = await fetch('catalog.json');
      if (res.ok) {
        const data = await res.json();
        products = data.products.map((p, index) => {
          const id = p.id;
          const name = p.name;
          const category = p.category ? p.category.name : "Uncategorized";
          const subcategory = p.subcategory ? p.subcategory.name : "General";
          const brand = p.brand ? p.brand.name : "Unknown";
          const quantity = 1;
          const unit = p.unit ? p.unit : "pcs";
          const price = p.price;
          const oldPrice = p.regular_price;
          const discount = p.discount;
          const inStock = p.in_stock;
          const art = p.image_url;
          
          const [background, accent] = getColorCategory(category);
          
          const today = new Date();
          const past = new Date(today);
          past.setDate(today.getDate() - 365);
          const history = [
            { date: past, price: price },
            { date: today, price: price }
          ];

          const average = averageOf(history.map(pt => pt.price));
          const lowest = Math.min(...history.map(pt => pt.price));
          
          return {
            id, name, category, subcategory, brand, quantity, unit, price, oldPrice, discount, inStock, art,
            background, accent, history,
            unitPrice: price / quantity,
            average, lowest, isLowest: price <= lowest,
            trend: price - history[Math.max(0, history.length - 8)].price,
            rotation: `${(index % 7 - 3) * .65}deg`
          };
        });
      }
    } catch (e) {
      console.error("Failed to load catalog.json", e);
    }
    syncControls();
    bindEvents();
    render();
  }

  init();
})();
