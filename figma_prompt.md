# Figma Prompt — GroceryGOD Flutter App (offline-cached price tracker)

Paste the section below into Figma's "Make Design" / AI prompt field. It gives Figma the product concept, user flows, and feature requirements — and deliberately leaves visual style, layout, colors, and typography completely open.

---

## Product: GroceryGOD — Bangladeshi Grocery Price Tracker (Mobile App)

### 1. Context (what the product is)
GroceryGOD is a price-tracking and price-history app for grocery shoppers in Bangladesh. It tracks **8 grocery stores/online shops**: Shwapno, Chaldal, Meena Bazar, Othoba, Metromart, Unimart, ShotejBazar, and Foodi. Every day, automated scrapers capture product prices from these stores. The app shows shoppers what a product costs today at each store, how the price changed over time, and which store is cheapest — **with prices normalized to a fair per-unit basis** (BDT per kg, BDT per liter, BDT per piece) so comparing a 500g pack vs a 1kg pack is meaningful.

Data is collected daily since February 2026 and stored as time-series price history per product.

### 2. Core product philosophy (design must respect this)
- **Offline-cached, not just offline-first.** On first launch the app downloads a compact data bundle once (product catalog + price history, a few MB). Product images are loaded from the stores' CDNs **on demand** and **cached on the device**: the first time a product is viewed online, its image is saved locally; afterwards that product's image (and all its data) is viewable **even fully offline**. The app never re-downloads the bundle; images and data accumulate in a local cache and everything stays usable with no connection. This is the app's defining promise.
- **Clarity over decoration.** This is a data/analytics tool at heart. Every screen should make numbers, dates, and comparisons easy to read at a glance.
- **Local + private.** All data lives on the user's device. Design should reflect trust and simplicity, not surveillance.

### 3. Target users
- Budget-conscious Bangladeshi shoppers (ages 18–50) comparing grocery prices before buying.
- Power users who track price trends (e.g., "should I buy rice this week or wait?").
- Primary language: English UI with clear support for Bangla product names and prices in Bangladeshi Taka (৳ / BDT).

### 4. First-launch workflow (the most important flow)
1. **Splash screen** — brief brand moment.
2. **One-time data download screen** — explains "Download once, works offline forever", shows the bundle size (~5 MB), a real download progress state, and friendly microcopy. Must include states for: downloading, paused/failed (with Retry), and completed.
3. **Welcome / free-tier summary** — after download completes, show what the user has: ~150k+ products, 8 stores, 6 months of price history.
4. **Home dashboard** — the main hub (see below).

The download must feel like a gift, not a barrier: one tap, no sign-up.

### 5. Paywall / premium workflow
- Free tier includes: all products, current prices, and **the last 6 months of price history**.
- Full history (everything since February 2026, growing daily) is locked behind a **premium unlock**.
- Unlock flow: a settings/paywall screen where the user enters a **premium key** (a license string). On submit, the app decrypts the full-history archive locally and permanently unlocks full timelines. No server round-trip, no account.
- Design requirements for this flow: make the value of "full history" tangible (show what they get: e.g., 12+ months of trends, "see what prices did last year"), a clear input field for the key, a success state that feels rewarding, and graceful error state for a wrong key.
- Premium status must be visible in the UI (e.g., a subtle badge) but not aggressive.

### 6. Screens to design (cover all; arrange them into a clear navigation structure you choose)

**A. Home dashboard**
- Overview of all 8 stores (store name, product count, price-data date coverage).
- Global stats row: total products tracked, stores covered, history span ("since Feb 2026"), last data update date.
- Quick highlights: e.g., "biggest price drops this week", "today's cheapest finds" (computed locally — feel free to propose your own highlight cards).
- Search entry point (global product search across all stores).
- Premium status / unlock entry point.

**B. Store page** (e.g., Shwapno)
- Header: store name, product count, data coverage range ("Price data: Feb 2026 → today").
- Product list: each row shows cached thumbnail (or placeholder), name (Bangla/English), unit, current price in ৳, normalized price (৳/kg, ৳/L, ৳/pc), a tiny trend indicator (up/down vs last week).
- **A full filter & sort toolbar above the list.** Design the controls — but they must cover:
  - **Category filter** — horizontal chip row (All, Dairy, Vegetables, Fruits, Rice & Grains, Meat, Fish, Snacks, Drinks, Household, …) with "All" default; multi-select via checkboxes in an expandable filter panel is fine too.
  - **Unit-type filter** — chips or checkboxes: kg / liter / piece (e.g., only show per-kg items).
  - **Price-range filter** — a min–max range slider (৳) with live result count.
  - **Availability filter** — checkbox "in stock only".
  - **Sort menu** — options: Price: low→high, Price: high→low, Biggest price drop (this week), Newest first, Name A–Z. Show an active-sort indicator.
  - **Active-filter summary row** — removable filter chips ("Dairy ×", "৳50–৳200 ×", "Clear all") so the user always knows what's applied and can clear instantly.
  - **Result count** ("1,240 of 8,501 products") always visible.
  - Empty state for zero matches with a "Clear filters" action.
- **Comparison mode** — a "Compare" toggle in the store page (and search) that adds a **checkbox to every product row** and a floating action bar ("Compare (3)"); selecting 2–4 products opens a side-by-side comparison table (name, unit, price, ৳/unit, trend, history depth). Design this mode's toggle, row checkboxes, selection bar, and the comparison table.
- Loading, error, and offline states.

**C. Product detail** (the heart of the app)
- Large product image (or graceful placeholder — images come from store CDNs; they cache after first view, so the design must look good both with photos and without).
- Current price (৳), normalized per-unit price, store name, unit size, category, first-seen date.
- **Price history chart**: time-series line chart (date on X, price on Y), with min/max/current markers and the free/premium timeline boundary (6-month cutoff) clearly communicated. Include a **date-range selector (1M / 3M / 6M / All)** — design the segmented control. Tap a point for a tooltip showing date + price. Propose the chart style, colors, and axes; readable at phone size and in light/dark themes.
- Stats chips: highest price, lowest price, average, biggest single-day change.
- **Compare across stores**: which store sells this product (or similar) cheapest today — a small comparison list/table (design this — it's a key feature).
- History depth indicator: "Free tier: last 6 months" vs "Premium: full history since Feb 2026".
- Share/export the price chart (optional, your call).

**D. Global search**
- Search across all stores and products; results grouped by store; highlight product name matches; show price + normalized price + trend in results. Handle Bangla text.
- **Search filter panel** (design it): **store multi-select checkboxes** (Shwapno, Chaldal, …), category chips, unit-type checkboxes (kg/L/pc), price-range slider, "in stock only" checkbox, sort menu (same options as store page). Active-filter chips + "Clear all". Result count.
- Recent searches (tappable history) and popular search suggestions.
- Empty search state (no results) with suggestions to relax filters.

**E. Compare screen** (cross-store product comparison)
- Launched from comparison mode or product detail. A **side-by-side table** of 2–4 selected products: thumbnail, name, unit size, current price ৳, normalized ৳/kg·L·pc, weekly trend arrow, history depth, store badge. Highlight the cheapest column. Allow removing a column via an X or by unchecking its checkbox above the table.

**F. Settings & data**
- **Data & cache management**: data bundle info (size, last updated, stores covered); "Check for data update" (optional manual refresh when online); "Re-download data"; **image cache control** — storage used, "Clear image cache" with confirmation, and a note that cleared images reload next time the app is online.
- Premium: enter key field, premium status, restore.
- About: what the app is, how data is collected, privacy note ("all data stays on your device").
- App language toggle (English / বাংলা) and theme toggle (light/dark) if you choose to include them.

**G. Status/utility states**
- Offline indicator (subtle banner: "Offline — showing cached data").
- Download failure with retry; decryption failure; empty search results; no image available; premium-locked chart area (blurred/greyed with an elegant unlock CTA).

### 7. Facts the design must honor
- Currency is Bangladeshi Taka: **৳** (e.g., ৳125.50).
- Prices are normalized per unit: **৳/kg, ৳/L (liter), ৳/pc (piece)** — always display the unit basis, never a bare number.
- 8 stores: Shwapno, Chaldal, Meena Bazar, Othoba, Metromart, Unimart, ShotejBazar, Foodi.
- History starts **February 2026** and grows daily; free tier = last 6 months.
- Product names are often Bangla (with English brands) — typography must handle Bangla script gracefully.
- A simple store identity system (name + monogram/icon) is needed; each store should be visually distinguishable at a glance (colors/patterns of your choosing).
- Charts are the most-used element — they must be readable at small phone sizes and in both light and dark themes.
- **Every list view needs the filter/sort/checkbox patterns from section B** — apply the same toolbar language consistently across store page, search, and compare.

### 8. Design freedom — important
Do NOT design in any existing brand style. There is no existing app. Invent a fresh, distinctive identity for a data-driven grocery price tracker: a memorable app icon, a cohesive color system, typography that balances numbers, Bangla text, and UI labels, and a chart/visual language that feels precise and trustworthy. Choose your own navigation pattern (bottom tabs, home-scroll hub, etc.) that best serves: Home → Store → Product → Search → Compare → Settings. Aim for a modern, calm, high-information-density look — closer to a finance/analytics app than a typical colorful shopping app.

Deliver a full mobile app design: app icon, splash, download flow, home, store list (with filter/sort/compare controls), product detail with chart, search, compare table, settings (with cache management), premium unlock, and all key empty/error/locked/offline states — in light and dark themes.