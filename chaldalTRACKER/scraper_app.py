#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chaldal Price Tracker — Dynamic Scraper
Discovers categories from the init API, scrapes all products by category,
appends daily price history for use by the web app.

Usage:
  python scraper.py                    # Full scrape
  python scraper.py --cat 108          # Single category (test)
  python scraper.py --output data/     # Custom output dir
"""
import json, os, sys, time, argparse, urllib.request, urllib.error, gzip, io
from datetime import datetime, timezone

# Force UTF-8 stdout for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── API endpoints (from HAR analysis) ──────────────────────────────────────────
CATALOG_URL = "https://catalog.chaldal.com/searchPersonalized"
INIT_URL    = "https://eggyolk.chaldal.com/api-v4/Device/FetchInitDataForCombinedStore"
DAILY_URL   = "https://eggyolk.chaldal.com/api-v4/DailyDeal/RetrieveDailyDeals"
API_KEY     = "e964fc2d51064efa97e94db7c64bf3d044279d4ed0ad4bdd9dce89fecc9156f0"

DEFAULT_STORE = 1
DEFAULT_WH    = 8   # Banasree warehouse
DEFAULT_AREA  = 4   # Banasree area  (MetropolitanAreaId=1)

BASE_HEADERS = {
    "accept":                   "application/json",
    "content-type":             "application/json",
    "x-egg-clientapp":          "Poached",
    "x-egg-appversion":         "10.5.3",
    "x-egg-appversionnumber":   "1005030",
    "x-egg-platform":           "Android",
    "x-egg-platformosversion":  "16",
    "x-egg-deviceuuid":         "ce27b9aefdbe2a1b",
    "x-egg-devicemodel":        "SM-G781B",
    "x-egg-devicebrand":        "samsung",
    "x-egg-devicemanufacturer": "samsung",
    "accept-encoding":          "gzip",
    "user-agent":               "okhttp/4.12.0",
    "cookie":  "Egg.Customer=bcb3d2f9-d6bc-4ddd-809d-fc85378c9ad1; sbcV2=%7B%22MetropolitanAreaId%22%3A1%2C%22PvIdToQtyStoreIdLastSeqRecType%22%3A%7B%7D%7D",
}


def req(url, body=None, store_id=DEFAULT_STORE):
    """HTTP GET/POST with gzip, auto-retry x3."""
    hdrs = {**BASE_HEADERS, "x-egg-storeid": str(store_id)}
    data = json.dumps(body).encode() if body else None
    for attempt in range(3):
        try:
            r = urllib.request.Request(url, data=data, headers=hdrs,
                                       method="POST" if data else "GET")
            with urllib.request.urlopen(r, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except Exception as ex:
            if attempt == 2:
                raise
            print(f"    retry {attempt+1}: {ex}", flush=True)
            time.sleep(2 ** attempt)


def fetch_init(store_id, warehouse_id):
    now = datetime.now()
    ts = f"{now.hour:02d}%3A{now.minute:02d}%3A{now.second:02d}%20GMT%2B0600"
    url = f"{INIT_URL}?serializationType=Javascript&timeStamp={ts}&warehouseId={warehouse_id}"
    return req(url, store_id=store_id)


def scrape_category(cat_id, store_id, warehouse_id, metro_area_id=1, page_size=50):
    """Return all product hits across all pages for one category."""
    products, page = [], 0
    while True:
        body = {
            "apiKey": API_KEY,
            "storeId": store_id,
            "warehouseId": warehouse_id,
            "pageSize": page_size,
            "currentPageIndex": page,
            "metropolitanAreaId": metro_area_id,
            "query": "",
            "productVariantId": -1,
            "bundleId": {"case": "None"},
            "canSeeOutOfStock": "false",
            "filters": [f"categories%3D{cat_id}"],
            "maxOutOfStockCount": {"case": "Some", "fields": [0]},
            "shouldShowAlternateProductsForAllOutOfStock": {"case": "Some", "fields": ["true"]},
            "customerGuid": {"case": "None"},
            "deliveryAreaId": {"case": "None"},
            "shouldShowCategoryBasedRecommendations": {"case": "None"},
        }
        data = req(CATALOG_URL, body=body, store_id=store_id)
        hits = data.get("hits", [])
        products.extend(hits)
        if page + 1 >= data.get("nbPages", 1) or not hits:
            break
        page += 1
        time.sleep(0.25)
    return products


def normalize(p, cat_id, today):
    return {
        "id":         p.get("objectID"),
        "name":       p.get("name", ""),
        "nameBn":     p.get("bengaliName", ""),
        "nameBase":   p.get("nameWithoutSubText", ""),
        "subText":    p.get("subText", ""),
        "slug":       p.get("slug", ""),
        "price":      p.get("price", 0),
        "mrp":        p.get("mrp", 0),
        "categories": p.get("recursiveCategories", [cat_id]),
        "imageUrl":   (p.get("picturesUrls") or [""])[0],
        "longDesc":   p.get("longDesc") or p.get("shortDesc") or "",
        "inStock":    bool(p.get("productAvailabilityForSelectedWarehouse")),
        "type":       p.get("catalogItemType", "Grocery"),
        "scraped":    today,
    }


def save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def load(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def main():
    ap = argparse.ArgumentParser(description="Chaldal scraper")
    ap.add_argument("--store",     type=int, default=DEFAULT_STORE, help="Store ID")
    ap.add_argument("--warehouse", type=int, default=DEFAULT_WH,    help="Warehouse ID")
    ap.add_argument("--area",      type=int, default=DEFAULT_AREA,  help="Area ID")
    ap.add_argument("--output",    default="data",                  help="Output dir")
    ap.add_argument("--cat",       type=int, default=0,             help="Single category (debug)")
    args = ap.parse_args()

    out   = args.output
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── 1. Fetch init data ──────────────────────────────────────────
    print(f"[{today}] Fetching init data (store={args.store}, wh={args.warehouse})...", flush=True)
    init = fetch_init(args.store, args.warehouse)

    all_cats = init.get("Categories", {}).get(str(args.store), [])
    banners  = init.get("HomeBannersByTags", {}).get(str(args.store), {})
    hgc      = init.get("HomeGroupCategoryIds", {}).get(str(args.store), {})
    gc       = init.get("GlobalConstants", {}).get(str(args.store), {})

    save(f"{out}/categories.json", all_cats)
    save(f"{out}/banners.json",    banners)
    save(f"{out}/init_meta.json",  {
        "storeId":     args.store,
        "warehouseId": args.warehouse,
        "areaId":      args.area,
        "lastUpdated": today,
        "homeGroups":  hgc,
        "shipping": {
            "fee":       gc.get("ShippingFee", {}).get("Lo", 59),
            "fee2":      gc.get("ShippingFeeTier2", {}).get("Lo", 49),
            "freeCutOff":gc.get("FreeShippingCutOff", {}).get("Lo", 399),
        },
    })
    print(f"  {len(all_cats)} categories, {sum(len(v) for v in banners.values())} banners saved.", flush=True)

    # ── 2. Scrape products ─────────────────────────────────────────
    products_index = load(f"{out}/products.json") or {}
    price_history  = load(f"{out}/price_history.json") or {}

    cats_to_scrape = ([c for c in all_cats if c["Id"] == args.cat] if args.cat else all_cats)
    total_new = 0

    for cat in cats_to_scrape:
        cid, cname = cat["Id"], cat["Name"]
        print(f"  [{cid}] {cname} ... ", end="", flush=True)
        try:
            hits  = scrape_category(cid, args.store, args.warehouse)
            count = 0
            for p in hits:
                norm = normalize(p, cid, today)
                pid  = str(norm["id"])
                # Update product index
                if pid in products_index:
                    products_index[pid].update({
                        "price": norm["price"], "mrp": norm["mrp"],
                        "inStock": norm["inStock"], "scraped": norm["scraped"]
                    })
                else:
                    products_index[pid] = norm
                # Append to price history (one entry per day)
                hist = price_history.get(pid, [])
                entry = {"d": today, "p": norm["price"], "m": norm["mrp"], "s": norm["inStock"]}
                if not hist or hist[-1]["d"] != today:
                    hist.append(entry)
                    price_history[pid] = hist
                    total_new += 1
                count += 1
            print(f"{count} products", flush=True)
        except Exception as ex:
            print(f"ERROR: {ex}", flush=True)
        time.sleep(0.4)

    # ── 3. Daily deals ─────────────────────────────────────────────
    try:
        print("  Daily deals ... ", end="", flush=True)
        dd = req(DAILY_URL, store_id=args.store)
        save(f"{out}/daily_deals.json", dd)
        print(f"{len(dd)} deals", flush=True)
    except Exception as ex:
        print(f"ERROR: {ex}", flush=True)
        save(f"{out}/daily_deals.json", [])

    # ── 4. Save indexes ────────────────────────────────────────────
    save(f"{out}/products.json",      products_index)
    save(f"{out}/price_history.json", price_history)

    # Build per-category product ID list for fast nav
    cat_prods = {}
    for pid, prod in products_index.items():
        for cid in prod.get("categories", []):
            cat_prods.setdefault(str(cid), []).append(pid)
    save(f"{out}/cat_products.json", cat_prods)

    print(f"\nDone. {total_new} new price points, {len(products_index)} total products.", flush=True)
    print(f"Output: {out}/products.json | categories.json | price_history.json | banners.json", flush=True)


if __name__ == "__main__":
    main()
