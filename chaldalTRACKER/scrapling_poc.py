#!/usr/bin/env python3
"""
Scrapling Chaldal POC (todo s1)
--------------------------------
Proof-of-concept: scrape Chaldal category pages using the Scrapling library
as an alternative to the raw Playwright HTML fallback (scraper_web.py).
Evaluates Scrapling's fetch + CSS-selector parsing + anti-bot handling.

Standalone: does NOT touch the production scrapers (scraper_app.py /
scraper_web.py). Selectors and product schema mirror scraper_web.py so the
output is comparable.

Setup:
    pip install "scrapling[fetchers]"
    scrapling install        # installs browser deps (Playwright Chromium)

Run:
    python scrapling_poc.py
    python scrapling_poc.py fresh-vegetables --max 30 --out poc_output.json
    python scrapling_poc.py rice --fetcher dynamic
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone

BASE = "https://chaldal.com"
DHAKA = timezone(timedelta(hours=6))

# CSS selectors mirrored from chaldalTRACKER/scraper_web.py
SEL_CARD = ".product, .productV2"
NAME_SELS = [".nameTextWithEllipsis"]
PRICE_SELS = [".productV2discountedPrice span", ".price span", ".price"]
UNIT_SELS = [".subText span", ".quantity"]
IMG_SELS = [".imageWrapperWrapper img", "img"]


def parse_price(text: str | None) -> float:
    if not text:
        return 0.0
    m = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group()) if m else 0.0


def first_text(node, selectors) -> str:
    for sel in selectors:
        val = node.css(sel + "::text").get()
        if val and val.strip():
            return val.strip()
    return ""


def first_attr(node, selectors, attr) -> str:
    for sel in selectors:
        val = node.css(f"{sel}::attr({attr})").get()
        if val:
            return val
    return ""


def fetch_page(url: str, fetcher: str = "stealthy"):
    """Fetch a Chaldal page. Chaldal is JS-rendered and bot-protected, so the
    stealthy (real-browser) fetcher is the default; 'dynamic' and 'static' are
    provided for comparison."""
    from scrapling.fetchers import DynamicFetcher, Fetcher, StealthyFetcher

    if fetcher == "static":
        return Fetcher.fetch(url)
    F = StealthyFetcher if fetcher == "stealthy" else DynamicFetcher
    # kwargs vary across Scrapling versions; fall back to a bare fetch.
    try:
        return F.fetch(url, headless=True, network_idle=True, wait_selector=SEL_CARD)
    except TypeError:
        return F.fetch(url)


def extract_products(page, max_items: int):
    products = []
    today = datetime.now(DHAKA).strftime("%Y-%m-%d")
    for card in page.css(SEL_CARD)[:max_items]:
        name = first_text(card, NAME_SELS)
        if not name:
            continue
        price = parse_price(first_text(card, PRICE_SELS))
        products.append(
            {
                "name": name,
                "price": price,
                "unit": first_text(card, UNIT_SELS),
                "imageUrl": first_attr(card, IMG_SELS, "src"),
                "inStock": price > 0,
                "scraped": today,
            }
        )
    return products


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrapling Chaldal POC")
    ap.add_argument("category", nargs="?", default="fresh-vegetables",
                    help="Chaldal category slug, e.g. fresh-vegetables")
    ap.add_argument("--max", type=int, default=20, help="max products to extract")
    ap.add_argument("--out", default=None, help="optional path to write JSON output")
    ap.add_argument("--fetcher", choices=["stealthy", "dynamic", "static"],
                    default="stealthy", help="fetch strategy (default: stealthy)")
    args = ap.parse_args()

    url = f"{BASE}/{args.category.strip('/')}"
    print(f"[poc] fetching {url} via {args.fetcher} fetcher ...")
    try:
        page = fetch_page(url, args.fetcher)
    except ImportError:
        print('[poc] Scrapling not installed. Run: pip install "scrapling[fetchers]" '
              "&& scrapling install", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - POC: surface any fetch error
        print(f"[poc] fetch failed: {exc}", file=sys.stderr)
        return 2

    status = getattr(page, "status", "?")
    cards = len(page.css(SEL_CARD))
    products = extract_products(page, args.max)
    print(f"[poc] http_status={status}  cards_found={cards}  extracted={len(products)}")
    print(json.dumps(products, ensure_ascii=False, indent=2))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(products, fh, ensure_ascii=False, indent=2)
        print(f"[poc] wrote {len(products)} products -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
