import asyncio
import re
import aiohttp
from datetime import datetime, timedelta, timezone
from collections import Counter
from database import SessionLocal, Category, Product, PriceHistory, init_db

DHAKA_TZ = timezone(timedelta(hours=6))
API_BASE = "https://api.metromartonline.com/api/v1"
OUTLET_ID = 9

CATEGORIES = [
    {"name": "Beverage", "code": "old_cat_129"},
    {"name": "Food & Grocery", "code": "old_cat_130"},
    {"name": "Baby Items & Care", "code": "old_cat_132"},
    {"name": "Household & Cleaning", "code": "old_cat_133"},
    {"name": "Electric & Electronics", "code": "old_cat_135"},
    {"name": "Grains & Commodities", "code": "old_cat_136"},
    {"name": "Home & Kitchen", "code": "old_cat_137"},
    {"name": "Office & Stationary", "code": "old_cat_138"},
    {"name": "Frozen Food", "code": "old_cat_140"},
]

async def fetch_products(session, category_code):
    products = []
    page = 1
    limit = 50

    while True:
        url = f"{API_BASE}/products"
        params = {"limit": limit, "page": page, "outletId": OUTLET_ID, "category": category_code}
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    print(f"  [!] API error {resp.status} for page {page}")
                    break
                data = await resp.json()
                if not data.get("success"):
                    print(f"  [!] API returned success=false for page {page}")
                    break
                items = data.get("data", {}).get("items", [])
                total = data.get("data", {}).get("total", 0)
                if not items:
                    break

                for item in items:
                    try:
                        cms = item.get("cms", {})
                        pos = item.get("pos", {})
                        name = (cms.get("strItem") or "").strip()
                        if not name:
                            continue

                        actual_price = float(pos.get("mrpPrice") or 0)
                        if actual_price <= 0:
                            actual_price = float(cms.get("decMrpPrice") or 0)
                        if actual_price <= 0:
                            continue

                        image_url = cms.get("strThumbnailUrl", "")
                        slug = cms.get("strSlug", "")

                        unit = "1 piece"
                        unit_match = re.search(r'(\d+\s*(?:gm|g|kg|ltr|liter|l|ml|piece|pc|s))\s*$', name, re.IGNORECASE)
                        if unit_match:
                            unit = unit_match.group(1).strip()

                        unit_type = "piece"
                        unit_price = actual_price
                        unit_lower = (unit + " " + name).lower()
                        if 'kg' in unit_lower:
                            match = re.search(r'(\d+\.?\d*)\s*kg', unit_lower)
                            weight = float(match.group(1)) if match else 1.0
                            unit_price = actual_price / weight
                            unit_type = "kg"
                        elif 'gm' in unit_lower or ' g ' in unit_lower or unit_lower.endswith(' g'):
                            match = re.search(r'(\d+\.?\d*)\s*g', unit_lower)
                            weight = float(match.group(1)) if match else 1.0
                            unit_price = (actual_price / weight) * 1000 if weight > 0 else actual_price
                            unit_type = "kg"
                        elif 'ltr' in unit_lower or 'liter' in unit_lower or ' l ' in unit_lower:
                            match = re.search(r'(\d+\.?\d*)\s*(ltr|liter|l)', unit_lower)
                            volume = float(match.group(1)) if match else 1.0
                            unit_price = actual_price / volume
                            unit_type = "liter"
                        elif 'ml' in unit_lower:
                            match = re.search(r'(\d+\.?\d*)\s*ml', unit_lower)
                            volume = float(match.group(1)) if match else 1.0
                            unit_price = (actual_price / volume) * 1000 if volume > 0 else actual_price
                            unit_type = "liter"

                        external_id = f"metro_{slug}" if slug else f"metro_{name}_{unit}".replace(" ", "_").lower()
                        products.append({
                            "external_id": external_id, "name": name, "unit": unit,
                            "actual_price": actual_price, "unit_price": round(unit_price, 2),
                            "unit_type": unit_type, "image_url": image_url,
                            "scraped_at": datetime.now(DHAKA_TZ)
                        })
                    except Exception as e:
                        print(f"  [!] Error parsing item: {e}")
                        continue

                print(f"  [+] Page {page}: {len(items)} items (total so far: {len(products)}/{total})")

                if len(products) >= total or len(items) < limit:
                    break
                page += 1
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"  [!] Request failed for page {page}: {e}")
            break

    return products

async def save_to_db(category_name, products, summary):
    db = SessionLocal()
    try:
        db_cat = db.query(Category).filter(Category.name == category_name).first()
        if not db_cat:
            db_cat = Category(name=category_name, url=f"https://www.metromartonline.com/shop?category={category_name}")
            db.add(db_cat)
            db.flush()

        for p in products:
            summary['total'] += 1
            summary['categories'][category_name] += 1

            db_p = db.query(Product).filter(Product.external_id == p['external_id']).first()
            if not db_p:
                db_p = Product(
                    external_id=p['external_id'], name=p['name'], unit=p['unit'],
                    unit_type=p['unit_type'], image_url=p['image_url'], category_id=db_cat.id
                )
                db.add(db_p)
                db.flush()
                summary['new'] += 1

            history = PriceHistory(
                product_id=db_p.id, actual_price=p['actual_price'],
                unit_price=p['unit_price'], scraped_at=p['scraped_at'].replace(tzinfo=None)
            )
            db.add(history)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"  [!] Metro Mart Database Error: {e}")
        raise e
    finally:
        db.close()

async def main():
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    init_db()
    async with aiohttp.ClientSession() as session:
        for cat in CATEGORIES:
            print(f"\n[Scraping] {cat['name']} ({cat['code']})")
            products = await fetch_products(session, cat['code'])
            print(f"  -> Found {len(products)} products")
            if products:
                await save_to_db(cat['name'], products, summary)
    save_last_run_log(summary)

def save_last_run_log(summary):
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base_dir, "last_run_log.txt")
    with open(log_path, "w", encoding='utf-8') as f:
        f.write(f"Last Run: {datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("-" * 30 + "\n")
        f.write(f"Total Scraped: {summary['total']}\n")
        f.write(f"New Items: {summary.get('new', 'N/A')}\n")
        f.write("-" * 30 + "\n")
        f.write("Categories:\n")
        for cat, count in sorted(summary['categories'].items(), key=lambda x: x[1], reverse=True)[:10]:
            f.write(f"- {cat}: {count}\n")
        if len(summary['categories']) > 10:
            f.write(f"... and {len(summary['categories']) - 10} more.")

if __name__ == "__main__":
    asyncio.run(main())
