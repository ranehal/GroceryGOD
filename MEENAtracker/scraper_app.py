#!/usr/bin/env python3
"""Daily Meena Bazar catalog scraper derived from the supplied HAR contract.

The HAR is not read at runtime. Authentication comes only from
MEENA_BEARER_TOKEN. Output is static JSON suitable for GitHub Pages.
"""

from __future__ import annotations

import json
import logging
import os
import statistics
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = os.getenv("MEENA_BASE_URL", "https://meenabazardev.com/api/mobile/front").rstrip("/")
TOKEN = os.getenv("MEENA_BEARER_TOKEN", "").strip()
AREA_ID = int(os.getenv("MEENA_AREA_ID", "265"))
SUBUNIT_ID = int(os.getenv("MEENA_SUBUNIT_ID", "11"))
PAGE_SIZE = int(os.getenv("MEENA_PAGE_SIZE", "50"))
REQUEST_DELAY = float(os.getenv("MEENA_REQUEST_DELAY", "0.15"))
OUTPUT_DIR = Path(os.getenv("MEENA_OUTPUT_DIR", "."))
TODAY = datetime.now(ZoneInfo("Asia/Dhaka")).date().isoformat()
GENERATED_AT = datetime.now(ZoneInfo("Asia/Dhaka")).isoformat(timespec="seconds")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(message)s")
LOG = logging.getLogger("meena-scraper")


def session() -> requests.Session:
    retry = Retry(total=4, connect=4, read=4, status=4, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=None)
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MeenaPriceTracker/1.0 (scheduled catalog archive)",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    s.headers.update(headers)
    return s


HTTP: requests.Session | None = None


def http() -> requests.Session:
    global HTTP
    HTTP = HTTP or session()
    return HTTP


def api(method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> Any:
    time.sleep(REQUEST_DELAY)
    response = http().request(method, f"{BASE_URL}/{path.lstrip('/')}", params=params, json=body, timeout=(10, 60))
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"API failure for {method} {path}: {payload.get('message', payload)}")
    return payload.get("data")


def as_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return round(float(value), 5)
    except (TypeError, ValueError):
        return default


def compact(items: Iterable[Any]) -> list[Any]:
    return [item for item in items if item not in (None, "", [])]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(path)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def category_body(start: int, search_type: str = "C") -> dict[str, Any]:
    return {
        "StartSl": start,
        "NoOfItem": PAGE_SIZE,
        "AreaId": AREA_ID,
        "SubUnitId": SUBUNIT_ID,
        "SearchType": search_type,
        "CategoryId": [],
        "BrandId": [],
        "SubCategoryId": [],
    }


def category_page(slug: str, start: int = 1, search_type: str = "C") -> dict[str, Any]:
    return api("POST", f"product/category/{quote(slug, safe='&.-_')}", body=category_body(start, search_type))


def merge_categories(nav: list[dict[str, Any]], all_categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    for raw in [*all_categories, *nav]:
        category_id = as_int(raw.get("ItemCategoryId"))
        if category_id is None:
            continue
        item = by_id.setdefault(category_id, {"id": category_id, "subcategories": []})
        item.update({
            "name": raw.get("ItemCategoryName") or item.get("name"),
            "display_name": raw.get("DisplayName") or item.get("display_name"),
            "slug": raw.get("CategorySlug") or item.get("slug"),
            "image_url": raw.get("ItemCategoryLogoUrl") or item.get("image_url"),
        })
        for sub in raw.get("category", []):
            sub_id = as_int(sub.get("ItemSubCategoryId"))
            if sub_id is None or any(x["id"] == sub_id for x in item["subcategories"]):
                continue
            item["subcategories"].append({
                "id": sub_id,
                "name": sub.get("ItemSubCategoryName"),
                "display_name": sub.get("DisplayName"),
                "slug": sub.get("SubCategorySlug"),
            })
    return sorted(by_id.values(), key=lambda x: x["id"])


def enrich_filters(category: dict[str, Any], filters: list[dict[str, Any]], brands: dict[int, dict[str, Any]]) -> None:
    sub_by_id = {x["id"]: x for x in category["subcategories"]}
    for item in filters:
        filter_id = as_int(item.get("FilterId"))
        if not filter_id:
            continue
        normalized = {
            "id": filter_id,
            "name": item.get("FilterName"),
            "display_name": item.get("DisplayName"),
            "slug": item.get("FilterSlug"),
            "item_count": as_int(item.get("ItemCount"), 0),
        }
        if item.get("FilterType") == "S":
            sub_by_id[filter_id] = {**sub_by_id.get(filter_id, {}), **normalized}
        elif item.get("FilterType") == "B":
            brands[filter_id] = {**brands.get(filter_id, {}), **normalized}
    category["subcategories"] = sorted(sub_by_id.values(), key=lambda x: (x.get("display_name") or x.get("name") or "").casefold())


def normalize_product(raw: dict[str, Any], category_slugs: dict[int, str], subcategory_slugs: dict[int, str], brand_slugs: dict[int, str]) -> dict[str, Any]:
    product_id = as_int(raw.get("ItemId"))
    if product_id is None:
        raise ValueError("Product has no ItemId")
    category_id = as_int(raw.get("ItemCategoryId"))
    subcategory_id = as_int(raw.get("ItemSubCategoryId"))
    brand_id = as_int(raw.get("ItemBrandId"))
    stock = as_int(raw.get("StockQuantity"), 0) or 0
    return {
        "id": product_id,
        "external_id": raw.get("ItemExternalId"),
        "slug": raw.get("ItemSlug"),
        "name": raw.get("ItemDisplayName") or raw.get("ItemDescription"),
        "description": raw.get("ItemDescription"),
        "details_html": raw.get("ItemDetails") or "",
        "category": {"id": category_id, "name": raw.get("CategoryDisplayName") or raw.get("ItemCategoryName"), "slug": category_slugs.get(category_id)},
        "subcategory": {"id": subcategory_id, "name": raw.get("SubCategoryDisplayName") or raw.get("ItemSubCategoryName"), "slug": subcategory_slugs.get(subcategory_id)},
        "brand": {"id": brand_id, "name": raw.get("BrandDisplayName") or raw.get("ItemBrandName"), "slug": brand_slugs.get(brand_id)},
        "unit": raw.get("Unit"),
        "regular_price": as_float(raw.get("UnitSalesPrice")),
        "price": as_float(raw.get("DiscountSalesPrice"), as_float(raw.get("UnitSalesPrice"))),
        "discount": as_float(raw.get("UnitDiscount")),
        "discount_percent": as_float(raw.get("DisPercent")),
        "stock": stock,
        "in_stock": stock > 0,
        "max_quantity": as_int(raw.get("MaxQuantity"), 0),
        "image_url": raw.get("ImageUrl"),
        "tag_image_url": raw.get("ItemTagImageUrl") or None,
        "restricted": bool(as_int(raw.get("RestrictedStatusId"), 0)),
        "restricted_description": raw.get("ItemRestrictedDescription") or None,
        "note": raw.get("ItemNote") or None,
    }


def total_from(products: list[dict[str, Any]]) -> int:
    return as_int(products[0].get("TotalItem"), len(products)) if products else 0


def crawl_category(slug: str, first_page: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    page = first_page or category_page(slug)
    products = list(page.get("category_product", []))
    filters = list(page.get("nav_serch", []))
    total = total_from(products)
    start = 1 + len(products)
    signatures = {tuple(x.get("ItemId") for x in products)}
    while products and start <= total:
        current = category_page(slug, start)
        batch = list(current.get("category_product", []))
        signature = tuple(x.get("ItemId") for x in batch)
        if not batch or signature in signatures:
            break
        signatures.add(signature)
        products.extend(batch)
        start += len(batch)
        LOG.info("category=%s fetched=%s/%s", slug, len(products), total)
    return products, filters


def paginated_get(path: str, product_key: str | None = None, **extra: Any) -> list[dict[str, Any]]:
    start, output, seen = 1, [], set()
    while True:
        data = api("GET", path, params={"StartSl": start, "NoOfItem": PAGE_SIZE, "AreaId": AREA_ID, "SubUnitId": SUBUNIT_ID, **extra})
        batch = data.get(product_key, []) if product_key else data
        batch = list(batch or [])
        signature = tuple(x.get("ItemId") for x in batch)
        if not batch or signature in seen:
            break
        seen.add(signature)
        output.extend(batch)
        total = total_from(batch)
        if len(output) >= total:
            break
        start += len(batch)
    return output


def crawl_featured_brand(slug: str) -> list[dict[str, Any]]:
    start, output, seen = 1, [], set()
    while True:
        data = api("GET", f"product/brand/{quote(slug, safe='&.-_')}", body=category_body(start, "B"))
        batch = list(data.get("Brand", []) or [])
        signature = tuple(x.get("ItemId") for x in batch)
        if not batch or signature in seen:
            break
        seen.add(signature)
        output.extend(batch)
        total = total_from(batch)
        if len(output) >= total:
            break
        start += len(batch)
    return output


def discover_tag_slugs(home: dict[str, Any]) -> list[str]:
    slugs = {x.get("OfferTagLink") for x in home.get("home_offer_tag", [])}
    for banner in home.get("homet_top_banner", []):
        link = (banner.get("ImageLink") or "").strip("/")
        if link.startswith("tag/"):
            slugs.add(link.split("/", 1)[1])
    return sorted(x for x in slugs if x)


def group_home_sections(home: dict[str, Any], normalize) -> dict[str, Any]:
    thumbnails = {str(x.get("PageSectionId")): x for x in home.get("section_thumbnail", [])}
    grouped: dict[str, list[int]] = defaultdict(list)
    normalized_products = []
    for raw in [*home.get("home_daily_deal", []), *home.get("section_product", [])]:
        product = normalize(raw)
        normalized_products.append(product)
        section_id = str(raw.get("PageSectionId") or "daily-deal")
        grouped[section_id].append(product["id"])
    sections = []
    for section_id, ids in grouped.items():
        thumb = thumbnails.get(section_id, {})
        sections.append({
            "id": section_id,
            "title": thumb.get("SectionTitle") or (home.get("home_daily_deal", [{}])[0].get("DealTitle") if section_id == "daily-deal" else "Featured"),
            "image_url": thumb.get("ImageUrl"),
            "link": thumb.get("SeeMoreLink") or thumb.get("ImageLink"),
            "product_ids": list(dict.fromkeys(ids)),
        })
    return {
        "sections": sections,
        "top_banners": home.get("homet_top_banner", []),
        "offer_tags": home.get("home_offer_tag", []),
        "payment_offers": home.get("payment_offer_show", []),
        "featured_brands": home.get("brand_show", []),
        "products": normalized_products,
    }


def update_history(products: list[dict[str, Any]]) -> None:
    by_shard: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for product in products:
        by_shard[f"{product['id'] % 256:02x}"].append(product)
    for shard, shard_products in by_shard.items():
        path = OUTPUT_DIR / f"history_{shard}.json"
        document = read_json(path, {"version": 1, "products": {}})
        histories = document.setdefault("products", {})
        for product in shard_products:
            key = str(product["id"])
            history = histories.setdefault(key, [])
            point = {
                "from": TODAY,
                "to": TODAY,
                "price": product["price"],
                "regular_price": product["regular_price"],
                "in_stock": product["in_stock"],
            }
            if history and all(history[-1].get(k) == point[k] for k in ("price", "regular_price", "in_stock")):
                history[-1]["to"] = TODAY
            elif not history or history[-1].get("from") != TODAY:
                history.append(point)
            else:
                history[-1] = point
        write_json(path, document)


def analytics(products: list[dict[str, Any]]) -> dict[str, Any]:
    prices = [x["price"] for x in products if x["price"] > 0]
    discounts = [x["regular_price"] - x["price"] for x in products if x["regular_price"] > x["price"]]
    return {
        "product_count": len(products),
        "in_stock_count": sum(x["in_stock"] for x in products),
        "discounted_count": len(discounts),
        "average_price": round(statistics.fmean(prices), 2) if prices else 0,
        "median_price": round(statistics.median(prices), 2) if prices else 0,
        "average_discount": round(statistics.fmean(discounts), 2) if discounts else 0,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    nav = api("GET", "nav/categories/list")
    if not nav:
        raise RuntimeError("No categories returned")

    seed_slug = nav[0]["CategorySlug"]
    seed_page = category_page(seed_slug)
    categories = merge_categories(nav, seed_page.get("all_category", []))
    categories_by_slug = {x["slug"]: x for x in categories if x.get("slug")}
    brands: dict[int, dict[str, Any]] = {}
    raw_products: dict[int, dict[str, Any]] = {}

    for category in categories:
        slug = category.get("slug")
        if not slug:
            continue
        LOG.info("Crawling category %s", slug)
        products, filters = crawl_category(slug, seed_page if slug == seed_slug else None)
        enrich_filters(category, filters, brands)
        for product in products:
            product_id = as_int(product.get("ItemId"))
            if product_id is not None:
                raw_products[product_id] = product

    category_slugs = {x["id"]: x.get("slug") for x in categories}
    subcategory_slugs = {sub["id"]: sub.get("slug") for category in categories for sub in category["subcategories"]}
    brand_slugs = {brand_id: brand.get("slug") for brand_id, brand in brands.items()}
    normalize = lambda raw: normalize_product(raw, category_slugs, subcategory_slugs, brand_slugs)

    home = api("GET", "home/section", body={"AreaId": AREA_ID, "SubUnitId": SUBUNIT_ID})
    home_data = group_home_sections(home, normalize)
    for product in home_data.pop("products"):
        raw_products.setdefault(product["id"], next((x for x in [*home.get("home_daily_deal", []), *home.get("section_product", [])] if as_int(x.get("ItemId")) == product["id"]), {}))

    featured_brand_sections = []
    for brand in home.get("brand_show", []):
        slug = brand.get("BrandSlug")
        if not slug:
            continue
        LOG.info("Crawling featured brand %s", slug)
        brand_products = crawl_featured_brand(slug)
        for raw in brand_products:
            product_id = as_int(raw.get("ItemId"))
            if product_id is not None:
                raw_products[product_id] = raw_products.get(product_id, raw)
        featured_brand_sections.append({
            "id": as_int(brand.get("ItemBrandId")),
            "name": brand.get("DisplayName") or brand.get("ItemBrandName"),
            "slug": slug,
            "image_url": brand.get("ImageUrl"),
            "product_ids": compact(as_int(x.get("ItemId")) for x in brand_products),
        })
    home_data["featured_brands"] = featured_brand_sections

    tag_sections = []
    for slug in discover_tag_slugs(home):
        LOG.info("Crawling tag %s", slug)
        tag_products = paginated_get("tag/product", "product", TagSlug=slug)
        for raw in tag_products:
            product_id = as_int(raw.get("ItemId"))
            if product_id is not None:
                raw_products[product_id] = raw_products.get(product_id, raw)
        tag_sections.append({"slug": slug, "product_ids": compact(as_int(x.get("ItemId")) for x in tag_products)})

    offer_products = paginated_get("offer/product/all")
    for raw in offer_products:
        product_id = as_int(raw.get("ItemId"))
        if product_id is not None:
            raw_products[product_id] = raw_products.get(product_id, raw)

    products = sorted((normalize(raw) for raw in raw_products.values() if raw), key=lambda x: x["id"])
    update_history(products)

    catalog = {
        "version": 1,
        "generated_at": GENERATED_AT,
        "observation_date": TODAY,
        "area_id": AREA_ID,
        "subunit_id": SUBUNIT_ID,
        "categories": categories,
        "brands": sorted(brands.values(), key=lambda x: (x.get("display_name") or x.get("name") or "").casefold()),
        "products": products,
    }
    sections = {
        "version": 1,
        "generated_at": GENERATED_AT,
        **home_data,
        "tags": tag_sections,
        "offers": {"product_ids": compact(as_int(x.get("ItemId")) for x in offer_products)},
    }
    meta = {"version": 1, "generated_at": GENERATED_AT, "observation_date": TODAY, **analytics(products)}
    write_json(OUTPUT_DIR / "catalog.json", catalog)
    write_json(OUTPUT_DIR / "sections.json", sections)
    write_json(OUTPUT_DIR / "meta.json", meta)
    LOG.info("Done: %s products, %s categories, %s tags", len(products), len(categories), len(tag_sections))


if __name__ == "__main__":
    main()
