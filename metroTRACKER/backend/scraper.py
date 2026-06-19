import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import asyncio
import re
from playwright.async_api import async_playwright
from datetime import datetime, timedelta, timezone
DHAKA_TZ = timezone(timedelta(hours=6))
from collections import Counter
from database import SessionLocal, Category, Product, PriceHistory, init_db

BASE_URL = "https://www.metromartonline.com"

# Updated categories list based on site discovery
CATEGORIES = [
    {"name": "Beverage", "url": f"{BASE_URL}/shop?category=old_cat_129"},
    {"name": "Food & Grocery", "url": f"{BASE_URL}/shop?category=old_cat_130"},
    {"name": "Baby Items & Care", "url": f"{BASE_URL}/shop?category=old_cat_132"},
    {"name": "Household & Cleaning", "url": f"{BASE_URL}/shop?category=old_cat_133"},
    {"name": "Electric & Electronics", "url": f"{BASE_URL}/shop?category=old_cat_135"},
    {"name": "Grains & Commodities", "url": f"{BASE_URL}/shop?category=old_cat_136"},
    {"name": "Home & Kitchen", "url": f"{BASE_URL}/shop?category=old_cat_137"},
    {"name": "Office & Stationary", "url": f"{BASE_URL}/shop?category=old_cat_138"},
    {"name": "Frozen Food", "url": f"{BASE_URL}/shop?category=old_cat_140"},
    {"name": "Dairy", "url": f"{BASE_URL}/shop?q=Dairy"},
    {"name": "Snacks", "url": f"{BASE_URL}/shop?q=Snacks"}
]

async def scrape_products_in_category(page, category_url):
    print(f"\n[Scraping Category] {category_url}")
    try:
        # Increase timeout for potential slow responses
        await page.goto(category_url, wait_until="networkidle", timeout=90000)
        # Check if items exist, otherwise skip early
        try:
            await page.wait_for_selector('a[href*="/product/"]', timeout=20000)
        except:
            print(f" -> No immediate items found in {category_url}. Moving on.")
            return []
    except Exception as e:
        print(f" -> Access failed for {category_url}: {e}")
        return []

    print(" -> Expanding list via infinite scroll...")
    last_count = 0
    scroll_attempts = 0
    max_scrolls = 50 
    
    while scroll_attempts < max_scrolls:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)
        
        cards = await page.query_selector_all('a[href*="/product/"]')
        current_count = len(cards)
        print(f"   [+] Loaded {current_count} products...", end='\r')
        
        if current_count == last_count:
            # Try one more wait to be sure
            await asyncio.sleep(2)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
            cards = await page.query_selector_all('a[href*="/product/"]')
            if len(cards) == current_count:
                break
        
        last_count = current_count
        scroll_attempts += 1
            
    cards = await page.query_selector_all('a[href*="/product/"]')
    print(f"\n -> Extraction: Found {len(cards)} product units.")
    products = []
    for card in cards:
        try:
            name_el = await card.query_selector('p.line-clamp-2')
            if not name_el: continue
            name = await name_el.get_attribute('title') or await name_el.inner_text()
            name = name.strip()
            
            img_el = await card.query_selector('img')
            image_url = await img_el.get_attribute('src') if img_el else ""
            
            price_el = await card.query_selector('span:has-text("৳")')
            if not price_el: continue
            price_text = await price_el.inner_text()
            price_match = re.search(r'৳\s*([\d,.]+)', price_text)
            actual_price = float(price_match.group(1).replace(',', '')) if price_match else 0.0
            
            if not name or actual_price == 0: continue
            
            # Unit extraction from name if not present elsewhere
            unit = "1 piece"
            # Try to find unit at the end of the name (e.g., "500gm", "1kg", "2 ltr", "50ml")
            unit_match = re.search(r'(\d+\s*(?:gm|g|kg|ltr|liter|l|ml|piece|pc|s))\s*$', name, re.IGNORECASE)
            if unit_match:
                unit = unit_match.group(1).strip()
            
            # Unit Normalization
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
                
            external_id = f"metro_{name}_{unit}".replace(" ", "_").lower()
            products.append({
                "external_id": external_id, "name": name, "unit": unit,
                "actual_price": actual_price, "unit_price": round(unit_price, 2),
                "unit_type": unit_type, "image_url": image_url,
                "scraped_at": datetime.now(DHAKA_TZ)
            })
        except Exception as e: 
            print(f"Error parsing card: {e}")
            continue
    return products

async def save_to_db(category_name, category_url, products, summary):
    """Save scraped data to the database using synchronous session."""
    db = SessionLocal()
    try:
        db_cat = db.query(Category).filter(Category.name == category_name).first()
        if not db_cat:
            db_cat = Category(name=category_name, url=category_url)
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
        print(f" [!] Metro Mart Database Error: {e}")
        raise e
    finally:
        db.close()

async def main():
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    init_db()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use a standard user agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        for cat in CATEGORIES:
            products = await scrape_products_in_category(page, cat['url'])
            if products: 
                await save_to_db(cat['name'], cat['url'], products, summary)
        
        save_last_run_log(summary)
        await browser.close()

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
