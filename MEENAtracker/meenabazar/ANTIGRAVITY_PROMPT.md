# Prompt for Antigravity / Gemini

Build the complete production-ready repository described below. Work directly in the repository, create every required file, and finish with a concise summary of what you created and the exact setup steps. Do not return a tutorial or pseudocode. Do not ask questions; make sensible defaults.

## Goal

Create a state-of-the-art, mobile-first Meena Bazar price-history and product-discovery web app for GitHub Pages, inspired by the useful parts of CamelCamelCamel and SteamDB but tailored to groceries. It must show the full catalog, categories, subcategories, brands, live promotional sections, search/filter/sort, product pages, compact long-term price history, comparisons, and useful price analytics.

Use the supplied `scripts/scrape.py` and `HAR_FINDINGS.md` as the API contract. Improve the scraper only where needed, but never require the HAR at runtime.

## Non-negotiable architecture

- Static frontend hosted on GitHub Pages.
- Scheduled server-side scraping only through GitHub Actions.
- Never call the Meena API from browser code.
- Never put the bearer token, HAR data, cookies, account profile, phone number, cart data, or other secrets in source, build artifacts, logs, or public JSON.
- Read the token only from the GitHub Actions secret `MEENA_BEARER_TOKEN`.
- Add `*.har`, `.env`, generated caches, and secrets to `.gitignore`.
- Use the captured default `AreaId=265` and `SubUnitId=11`, configurable through environment variables.
- Treat all 2xx responses as potentially successful and also validate JSON `status === "success"` because the API returns 201/202 for successful requests.
- Use a conservative request rate, retries with backoff, bounded timeouts, clear failure logs, and atomic output writes.
- Do not attempt token discovery, login automation, certificate pinning bypass, private-data collection, cart access, or account impersonation.

## YAGNI rules

- One repository, one static app, one Python scraper, one data format, one deploy path.
- No backend server, database service, Docker, Kubernetes, GraphQL, microservices, queues, user accounts, admin dashboard, notifications, affiliate system, machine learning, or speculative abstractions.
- Prefer one-line commands and small single-purpose functions over frameworks or layers that do not solve a current requirement.
- Do not deliberately compress readable source code into literal one-line programs.
- Use the fewest dependencies that deliver clear value.

## Technology

Use:

- Vite, React, and TypeScript.
- React Router with hash routing so every route works on GitHub Pages without server rewrites.
- Tailwind CSS for responsive styling.
- Apache ECharts through a thin React wrapper for interactive price charts.
- DOMPurify before rendering any API-provided HTML.
- Vitest and React Testing Library for a small, meaningful test suite.
- Python 3.12 and `requests` for scraping.
- GitHub Actions for daily scraping, validation, build, and Pages deployment.

Avoid a global state framework. Use URL state, React context only where genuinely shared, and ordinary hooks.

## HAR-derived API contract

Base URL:

`https://meenabazardev.com/api/mobile/front`

Required header:

`Authorization: Bearer ${MEENA_BEARER_TOKEN}`

Catalog endpoints:

1. `GET /nav/categories/list`
   - Returns menu categories with nested subcategories and slugs.

2. `POST /product/category/{slug}` with JSON:

```json
{
  "StartSl": 1,
  "NoOfItem": 50,
  "AreaId": 265,
  "SubUnitId": 11,
  "SearchType": "C",
  "CategoryId": [],
  "BrandId": [],
  "SubCategoryId": []
}
```

   - `SearchType="C"` for categories and `SearchType="S"` for subcategories.
   - Response data can contain `banner_image_show`, `all_category`, `category_name`, `category_product`, and `nav_serch`.
   - `nav_serch` uses `FilterType="S"` for subcategories and `FilterType="B"` for brands.
   - The first product usually contains `TotalItem`.

3. `GET /home/section` with JSON body `{ "AreaId": 265, "SubUnitId": 11 }`
   - Returns `home_daily_deal`, `homet_top_banner`, `home_offer_tag`, `section_product`, `ad_image_section`, `section_thumbnail`, `payment_offer_show`, and `brand_show`.

4. `GET /tag/product?StartSl=1&NoOfItem=50&AreaId=265&SubUnitId=11&TagSlug={slug}`
   - Returns `{ "product": [...] }`.
   - Discover tag slugs from `home_offer_tag[].OfferTagLink` and banner links beginning with `tag/`; never hard-code seasonal campaign names.

5. `GET /offer/product/all?StartSl=1&NoOfItem=50&AreaId=265&SubUnitId=11`

6. Optional featured-brand section membership:
   - `GET /product/brand/{slug}` with the same paging body and `SearchType="B"`.
   - Only crawl brands currently exposed by `brand_show`; do not crawl every brand endpoint because the category crawl already contains the products.

Do not use `/startup`, `/cart/items`, or `/areas/search`.

The category endpoint's `all_category` can include categories absent from the menu endpoint. Merge both lists by category ID and crawl every discovered category slug. Enrich subcategories from both nested navigation data and `nav_serch` filters. Stop pagination after the reported total, an empty/short page, or a repeated page signature. Abort publication if any core category crawl fails; never overwrite good public data with a partial catalog.

## Product normalization

Use `ItemId` as the stable primary key. Normalize at least:

- `id`, `external_id`, `slug`, `name`, `description`, sanitized `details_html`.
- Category, subcategory, and brand objects with IDs, names, and slugs where available.
- Unit, regular price, current price, discount amount, discount percent.
- Stock quantity, `in_stock`, maximum quantity.
- Product image and optional tag image.
- Restricted-item flag and description.
- Observation date and generated timestamp at dataset level.

The list response already contains product details; do not invent a missing detail endpoint.

Deduplicate all category, home, tag, offer, and featured-brand results by `ItemId`. Category pages are the canonical source; auxiliary sections add membership and may fill a product missing from the category crawl.

## Static data layout

Keep browser payloads practical and predictable:

```text
public/data/meta.json
public/data/catalog.json
public/data/sections.json
public/data/history/00.json ... ff.json
```

- `catalog.json`: categories, subcategories, brands, and normalized current products.
- `sections.json`: top banners, home sections, daily deals, offer tags, tag memberships, offer memberships, payment banners, and featured brands. Store product IDs instead of repeating full products.
- `meta.json`: generation time, observation date, item counts, availability, discount counts, scraper version, and a schema version.
- History shard: choose `productId % 256` and load only the required shard on a product page.

Store price history as compact change segments, not one duplicate point per day:

```json
{
  "from": "2026-08-01",
  "to": "2026-08-05",
  "price": 384,
  "regular_price": 399.5,
  "in_stock": true
}
```

Extend `to` when price and availability are unchanged; append a new segment only when one changes. Preserve history for products no longer in the current catalog. Write JSON atomically and deterministically so Git diffs remain small.

## Frontend experience

Create an original visual identity; do not copy Meena Bazar branding beyond factual product and campaign data. Add a visible disclaimer that the site is an independent price archive and is not affiliated with or endorsed by Meena Bazar.

Required routes:

- `#/` — home dashboard.
- `#/products` — all products.
- `#/category/:slug`.
- `#/subcategory/:slug`.
- `#/tag/:slug`.
- `#/offers`.
- `#/brand/:id`.
- `#/product/:id/:slug?`.
- `#/compare?ids=1,2,3`.
- `#/about` — data methodology, update time, limitations, and privacy/security statement.

Home page:

- Search bar with suggestions.
- Current catalog/discount/availability statistics.
- Live data freshness indicator.
- Dynamic banners and campaign cards using `sections.json` links.
- Daily deals and API-defined home sections.
- Biggest current discounts, recently changed prices, lowest recorded prices, and back-in-stock products when history supports them.

Product listing:

- Responsive cards with image, name, unit, current price, struck-through regular price, discount, stock state, category, and brand.
- Search across name, brand, category, subcategory, external ID, and unit.
- Filters for category, subcategory, brand, stock, discount, and price range.
- Sort by relevance, price low/high, discount, name, and newest observed.
- URL-persisted filters and shareable views.
- Pagination or virtualization; do not render thousands of cards at once.
- Empty, loading, stale-data, and error states.

Product detail:

- Accessible image and complete normalized details.
- Current price, regular price, savings, stock, unit, brand, hierarchy, last observation.
- Interactive ECharts step-line history with zoom, tooltip, date range controls, regular-price overlay, stock-out shading, lowest/highest markers, and responsive resizing.
- Analytics computed from history segments: lowest, highest, average, median, current versus 7/30/90-day prior price, absolute/percentage change, volatility, days at lowest price, discount duration, and availability percentage. Show “insufficient history” instead of fake precision.
- A history table beneath the graph.
- Related products from the same subcategory and brand.
- Add/remove comparison button.

Comparison:

- Compare two to four products.
- Overlay normalized price history with clear labels.
- Show current price, low/high/average, unit, discount, stock, and data range.
- Warn that differently sized units are not directly comparable; do not fabricate unit-price conversions without reliable structured quantity data.

Accessibility and quality:

- Semantic HTML, keyboard navigation, visible focus, meaningful alt text, sufficient contrast, reduced-motion support, and chart/table alternatives.
- Mobile-first layout with excellent behavior from 320 px through desktop.
- Lazy-load images and history shards.
- Use `Intl.NumberFormat("en-BD", { style: "currency", currency: "BDT" })`.
- Use Asia/Dhaka for user-facing observation dates.
- Add basic SEO metadata, Open Graph defaults, sitemap-compatible static metadata where feasible with hash routing, and a web app manifest.
- Include a compact dark mode using system preference and a user toggle stored locally.

## Derived analytics pipeline

During scraping, compare the new catalog with the previous catalog before replacement and generate small derived arrays in `sections.json` or `meta.json`:

- `price_drops`: products whose current price decreased since the previous successful run.
- `price_rises`.
- `back_in_stock`.
- `new_products`.
- `removed_products`, but only after a conservative repeated-miss rule or mark them as “not observed”; do not claim discontinuation from one failed day.

Keep only the newest 100 IDs per feed. The product history remains the source of truth.

## GitHub Actions

Create a single clear production workflow or two small workflows if that is materially simpler:

- Triggers: push to `main`, daily schedule at `00:30 UTC` (06:30 Asia/Dhaka), and manual dispatch.
- On scheduled/manual runs, install Python dependencies and execute the scraper with `MEENA_BEARER_TOKEN` from secrets.
- Validate schema, product count sanity, duplicate IDs, invalid prices, category coverage, JSON parseability, and that no secret-like values appear in `public/`.
- Build the Vite app.
- Run tests.
- Commit changed public data with the GitHub Actions bot only after a successful complete scrape and validation.
- Deploy `dist/` through the official GitHub Pages artifact/deploy actions.
- Use concurrency to prevent overlapping scrapes/deployments.
- Set minimal permissions: `contents: write`, `pages: write`, and `id-token: write` only where needed.
- Fail clearly when the secret is missing.

Because a bot commit made with `GITHUB_TOKEN` may not trigger another workflow, ensure the same scheduled run builds and deploys the newly generated working-tree data before completion.

## Repository files

Create and finish at least:

```text
.github/workflows/pages.yml
scripts/scrape.py
scripts/validate_data.py
src/
public/data/
index.html
package.json
package-lock.json
vite.config.ts
tailwind.config.*
tsconfig*.json
README.md
LICENSE
.env.example
.gitignore
```

Add a small `public/data` fixture so the app renders before the first successful secret-backed scrape. Make it unmistakably sample data and replaceable.

README must include:

- Purpose and independent-site disclaimer.
- Local setup in one-line commands.
- How to create a fresh authorized token secret without publishing it; do not document bypass techniques.
- GitHub Pages setup.
- Data update schedule and schema.
- Troubleshooting for missing/expired token, API changes, partial crawl protection, and Pages base path.
- Ethical-use note: obey applicable terms, use conservative rates, archive only public catalog information, and rotate any token exposed in a HAR.

## Testing and acceptance criteria

Add focused tests for:

- Price-history segment merging.
- Category/all-category merge.
- Product deduplication.
- History shard selection.
- Analytics with sparse history.
- Product filters/search.
- GitHub Pages base path and hash routes.

The repository is complete only when:

1. `npm ci && npm test && npm run build` succeeds.
2. `python -m py_compile scripts/scrape.py scripts/validate_data.py` succeeds.
3. The app works from a repository subpath on GitHub Pages.
4. No browser request targets `meenabazardev.com`.
5. No secret or HAR-derived personal field exists in tracked/public files.
6. A product route loads only its history shard, renders the chart and table, and handles missing history.
7. Every current category, hidden `all_category` category, subcategory, tag, offer, and home section is data-driven rather than hard-coded.
8. The scraper refuses to publish a partial core catalog.
9. The design feels polished, fast, and useful without adding features outside this specification.

Now inspect the existing starter files, implement the complete repository, run all available checks, fix failures, and report the final file structure plus the few required GitHub settings and secret name.
