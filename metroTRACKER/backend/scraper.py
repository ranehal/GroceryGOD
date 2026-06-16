import asyncio
import re
from playwright.async_api import async_playwright
from datetime import datetime, timedelta, timezone
DHAKA_TZ = timezone(timedelta(hours=6))
from collections import Counter
from database import SessionLocal, Category, Product, PriceHistory, init_db

BASE_URL = "https://www.metromartonline.com"

# Expanded categories list based on user discovery
CATEGORIES = [
    {"name": "Dairy", "url": f"{BASE_URL}/allproductslist?q=Dairy"},
    {"name": "Snacks", "url": f"{BASE_URL}/allproductslist?q=Snacks"},
    {"name": "Books", "url": f"{BASE_URL}/allproductslist?q=Books"},
    {"name": "Groceries", "url": f"{BASE_URL}/allproductslist?q=Groceries"},
    {"name": "Cycle", "url": f"{BASE_URL}/allproductslist?q=Cycle"},
    {"name": "Grain", "url": f"{BASE_URL}/allproductslist?q=Grain"},
    {"name": "Drinking Water", "url": f"{BASE_URL}/allproductslist?q=Drinking%20Water"},
    {"name": "Condiments", "url": f"{BASE_URL}/allproductslist?q=Condiments"},
    {"name": "Bakery", "url": f"{BASE_URL}/allproductslist?q=Bakery"},
    {"name": "Electricals", "url": f"{BASE_URL}/allproductslist?q=Electricals"},
    {"name": "Health Care & Cleaning Supplies", "url": f"{BASE_URL}/allproductslist?q=Health%20Care%20%26%20Cleaning%20Supplies"},
    {"name": "Fruit Drinks", "url": f"{BASE_URL}/allproductslist?q=Fruit%20Drinks"},
    {"name": "Cleaning Supplies", "url": f"{BASE_URL}/allproductslist?q=Cleaning%20Supplies"},
    {"name": "Beverage", "url": f"{BASE_URL}/allproductslist?q=Beverage"},
    {"name": "Rain Protection", "url": f"{BASE_URL}/allproductslist?q=Rain%20Protection"},
    {"name": "Others", "url": f"{BASE_URL}/allproductslist?q=Others"},
    {"name": "Spice & Masala", "url": f"{BASE_URL}/allproductslist?q=Spice%20%26%20Masala"},
    {"name": "Beauty & Personal Care", "url": f"{BASE_URL}/allproductslist?q=Beauty%20%26%20Personal%20Care"},
    {"name": "Ramadan Deals", "url": f"{BASE_URL}/allproductslist?q=Ramadan%20Deals"},
    {"name": "Rechargeable Fan", "url": f"{BASE_URL}/allproductslist?q=Rechargeable%20Fan"}
]

async def scrape_products_in_category(page, category_url):
    print(f"\n[Scraping Category] {category_url}")
    try:
        # Increase timeout for potential slow responses
        await page.goto(category_url, wait_until="networkidle", timeout=90000)
        # Check if items exist, otherwise skip early
        try:
            await page.wait_for_selector('img[alt]', timeout=20000)
        except:
            print(f" -> No immediate items found in {category_url}. Moving on.")
            return []
    except Exception as e:
        print(f" -> Access failed for {category_url}: {e}")
        return []

    print(" -> Expanding list via 'Load More'...")
    load_more_attempts = 0
    max_load_more = 100 
    
    while load_more_attempts < max_load_more:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)
        try:
            # More robust 'Load More' detection
            load_more_btn = await page.query_selector('button:has-text("Load More")')
            if load_more_btn and await load_more_btn.is_visible():
                await load_more_btn.click()
                print(f"   [+] Clicked Load More ({load_more_attempts + 1})", end='\r')
                await asyncio.sleep(3)
                load_more_attempts += 1
            else:
                # One last wait and check for slower loading buttons
                await asyncio.sleep(2)
                load_more_btn = await page.query_selector('button:has-text("Load More")')
                if not load_more_btn or not await load_more_btn.is_visible():
                    break
        except Exception: 
            break
            
    cards = await page.query_selector_all('a[href].w-full')
    valid_cards = []
    for card in cards:
        img = await card.query_selector('img')
        price = await card.query_selector('span:has-text("৳")')
        if img and price: valid_cards.append(card)

    print(f"\n -> Extraction: Found {len(valid_cards)} product units.")
    products = []
    for card in valid_cards:
        try:
            img_el = await card.query_selector('img')
            name = await img_el.get_attribute('alt') if img_el else "N/A"
            image_url = await img_el.get_attribute('src') if img_el else ""
            price_el = await card.query_selector('span:has-text("৳")')
            if not price_el: continue
            price_text = await price_el.inner_text()
            price_match = re.search(r'৳\s*([\d,.]+)', price_text)
            actual_price = float(price_match.group(1).replace(',', '')) if price_match else 0.0
            unit_el = await card.query_selector('span.flex-1.text-inherit')
            unit = await unit_el.inner_text() if unit_el else "N/A"
            
            if name == "N/A" or actual_price == 0: continue
            
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
        except Exception: continue
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
