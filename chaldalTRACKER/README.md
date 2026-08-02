# ChaldalTracker 🛒

**Bangladesh's first grocery price history tracker** — like CamelCamelCamel for Chaldal.

Track price changes, spot deals, and never overpay again on Bangladesh's largest online grocery platform.

[![GitHub Pages](https://img.shields.io/badge/Live%20Demo-GitHub%20Pages-0099ff?style=flat-square)](https://your-username.github.io/chaldal-tracker)
[![Daily Scrape](https://img.shields.io/github/actions/workflow/status/your-username/chaldal-tracker/scrape.yml?label=Daily%20Scrape&style=flat-square)](https://github.com/your-username/chaldal-tracker/actions)

---

## Features

| Feature | Details |
|---|---|
| **Price History** | Interactive Chart.js graphs per product (7D / 30D / All) |
| **Price Analytics** | Distribution charts, trend lines, category breakdowns |
| **Flash Deals** | Discounted products sorted by biggest savings |
| **Watchlist** | Star products, persisted in localStorage |
| **Search** | Instant autocomplete across 3000+ products |
| **Categories** | Full tree navigation with 233 categories/subcategories |
| **Responsive** | Works on mobile, tablet, desktop |
| **Dark/Light mode** | Toggle with memory |
| **Auto-refresh** | GitHub Actions scrapes daily at midnight BST |

## Quick Start

### 1. Interactive Menu (recommended)
Simply run [`runall.bat`](file:///C:/PROJECTS/CHALDAL/runall.bat) without arguments:
```cmd
runall.bat
```
You will be presented with an interactive prompt:
- **`[1] scraper`** — Run scraper only to refresh product & price history JSON files.
- **`[2] dashbrd`** — Launch dashboard web server (`http://localhost:8000`) only.
- **`[3] both`**    — Run scraper first, then launch dashboard.

### 2. Direct Command-Line Arguments
```cmd
runall.bat scraper  # Scrape data only
runall.bat dashbrd  # Launch web dashboard only
runall.bat both     # Scrape and launch web dashboard
```

### 3. Manual scraper options
```bash
# Full scrape
python scraper.py

# Single category (for testing)
python scraper.py --cat 108

# Custom store/warehouse/area
python scraper.py --store 1 --warehouse 8 --area 4

# Custom output directory
python scraper.py --output data
```

---

## API Endpoints Discovered

From the Reqable HAR capture of `com.chaldal.poached` (v10.5.3):

| Endpoint | Purpose |
|---|---|
| `GET eggyolk.chaldal.com/api-v4/Device/FetchInitDataForCombinedStore` | Categories, banners, home groups, areas, constants |
| `POST catalog.chaldal.com/searchPersonalized` | Product listings by category/search |
| `GET eggyolk.chaldal.com/api-v4/DailyDeal/RetrieveDailyDeals` | Daily flash deals |

### Key parameters (from HAR)
- `apiKey`: `e964fc2d51064efa97e94db7c64bf3d044279d4ed0ad4bdd9dce89fecc9156f0`  
- `storeId`: `1` (Chaldal main)  
- `warehouseId`: `8` (Banasree, covers Metro Dhaka)
- `metropolitanAreaId`: `1`

---

## Data Files (generated in `data/`)

```
data/
├── products.json        # { id: { name, price, mrp, imageUrl, inStock, ... } }
├── categories.json      # [ { Id, Name, ParentCategoryId, DisplayOrder, ... } ]
├── price_history.json   # { id: [ { d:"2026-08-01", p:355, m:355, s:true } ] }
├── cat_products.json    # { catId: [ productId, ... ] }
├── banners.json         # { AppHomeTop: [...], AppHomeMiddle1: [...] }
├── init_meta.json       # storeId, warehouseId, lastUpdated, homeGroups, shipping
└── daily_deals.json     # [ ... ]
```

---

## GitHub Pages Setup

1. Push to GitHub
2. Go to **Settings → Pages → Source: main branch / root**
3. The site will be live at `https://<username>.github.io/<repo>/`
4. The **GitHub Action** (`.github/workflows/scrape.yml`) runs daily at midnight BST, scrapes fresh prices and commits the updated `data/` files automatically.

---

## Architecture

```
scraper.py          ← Python 3.8+, stdlib only (no pip install needed)
    ↓ writes
data/*.json
    ↑ reads
app.js              ← Vanilla JS SPA, zero framework
index.html          ← Semantic HTML5
styles.css          ← Pure CSS, dark/light tokens
.github/workflows/  ← Daily automation
```

---

## Requirements

- **Scraper**: Python 3.8+ (stdlib only — no pip install required)
- **Web App**: Any static file server (or GitHub Pages)
- **Local dev**: `python -m http.server 8000` (included in `runall.bat`)

---

## License

MIT — Built with ❤️ from HAR analysis of the Chaldal Android app.
