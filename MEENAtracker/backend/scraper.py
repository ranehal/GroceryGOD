import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
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
from collections import Counter
import json
import re
import sys
from playwright.async_api import async_playwright
from datetime import datetime, timedelta, timezone
DHAKA_TZ = timezone(timedelta(hours=6))
from database import SessionLocal, Category, Product, PriceHistory, init_db

BASE_URL = "https://meenabazaronline.com"

def normalize_unit_price(price, name, unit_text):
    text = f"{unit_text or ''} {name or ''}".lower()
    text = re.sub(r'\(?[±\+]\s*\d+\s*(?:gm|g|kg|ml|ltr|l)?\)?', '', text)

    weight_match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|gm|gram|g)\b', text)
    if weight_match:
        weight = float(weight_match.group(1))
        unit = weight_match.group(2)
        if weight > 0:
            if unit == 'kg':
                return round(price / weight, 2), 'kg'
            return round((price / weight) * 1000, 2), 'kg'

    volume_match = re.search(r'(\d+(?:\.\d+)?)\s*(ltr|liter|l|ml)\b', text)
    if volume_match:
        volume = float(volume_match.group(1))
        unit = volume_match.group(2)
        if volume > 0:
            if unit in ['ltr', 'liter', 'l']:
                return round(price / volume, 2), 'ltr'
            return round((price / volume) * 1000, 2), 'ltr'

    if any(keyword in text for keyword in ['pc', 'piece', 'hali', 'dozen', 'pkt', 'pack', 'each', 'bottle', 'can', 'box']):
        return round(price, 2), 'piece'

    return round(price, 2), 'piece'

async def scrape_categories(page):
    """Return hardcoded categories as requested by the user."""
    print("Using hardcoded categories...")
    return [
        {"name": "Fish", "url": "https://meenabazaronline.com/category/fish"},
        {"name": "Meat", "url": "https://meenabazaronline.com/category/meat"},
        {"name": "Fruits", "url": "https://meenabazaronline.com/category/fruits"},
        {"name": "Vegetables", "url": "https://meenabazaronline.com/category/vegetables"},
        {"name": "Dairy", "url": "https://meenabazaronline.com/category/dairy"},
        {"name": "Frozen", "url": "https://meenabazaronline.com/category/frozen"},
        {"name": "Grocery", "url": "https://meenabazaronline.com/category/grocery"},
        {"name": "Personal Care", "url": "https://meenabazaronline.com/category/generalmerchandise"},
        {"name": "House Hold", "url": "https://meenabazaronline.com/category/household"},
        {"name": "Stationery", "url": "https://meenabazaronline.com/category/stationery"},
        {"name": "Apparel & Linen", "url": "https://meenabazaronline.com/category/apparel&linen"},
        {"name": "Pharmacy", "url": "https://meenabazaronline.com/category/pharmacy"},
        {"name": "Kitchen Ware", "url": "https://meenabazaronline.com/category/kitchenware"}
    ]

async def scrape_products_in_category(page, category_url):
    print(f"\n[Scraping Category] {category_url}")
    try:
        await page.goto(category_url, wait_until="networkidle", timeout=60000)
        
        # Handle Delivery Area Modal if it appears
        try:
            # Check if the modal input exists
            location_input = await page.wait_for_selector('.ant-select-selection-search-input', timeout=5000)
            if location_input:
                print(" -> Delivery Area Modal detected. Selecting location...")
                await location_input.click()
                await location_input.fill('khilgaon')
                await asyncio.sleep(2)
                await page.keyboard.press('Enter')
                await asyncio.sleep(2)
                # Click the first dropdown item if Enter didn't work
                options = await page.query_selector_all('.ant-select-item-option')
                if options:
                    await options[0].click()
                await asyncio.sleep(3)
        except Exception:
            pass # No modal appeared
            
        await page.wait_for_selector('app-thumb', timeout=30000) # Increased timeout for slow APIs
    except Exception as e:
        print(f"No products found or timeout in {category_url}: {e}")
        return []
    
    last_height = await page.evaluate("document.body.scrollHeight")
    scroll_attempts = 0
    max_scrolls = 200 # Up to 200 scrolls for very large categories (5k+ items)
    empty_scrolls = 0

    while scroll_attempts < max_scrolls:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2.5) # Wait for API response and DOM render
        
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            empty_scrolls += 1
            if empty_scrolls >= 3: # If height didn't change for 3 consecutive attempts, assume end of list
                break
        else:
            empty_scrolls = 0 # Reset if we successfully loaded more
            
        last_height = new_height
        scroll_attempts += 1

    product_elements = await page.query_selector_all('app-thumb')
    products = []
    
    for element in product_elements:
        try:
            name_el = await element.query_selector('.content a.font-medium')
            name = await name_el.inner_text() if name_el else "N/A"
            name = name.strip()
            
            unit_el = await element.query_selector('.content a.text-xs')
            unit = await unit_el.inner_text() if unit_el else "N/A"
            unit = unit.strip()
            
            price_el = await element.query_selector('.price span')
            price_text = await price_el.inner_text() if price_el else "0"
            actual_price = float(re.sub(r'[^\d.]', '', price_text))
            
            img_el = await element.query_selector('img')
            image_url = await img_el.get_attribute('src') if img_el else ""
            
            unit_price, unit_type = normalize_unit_price(actual_price, name, unit)
            external_id = f"{name}_{unit}".replace(" ", "_").lower()

            products.append({
                "external_id": external_id,
                "name": name,
                "unit": unit,
                "actual_price": actual_price,
                "unit_price": unit_price,
                "unit_type": unit_type,
                "image_url": image_url,
                "scraped_at": datetime.now(DHAKA_TZ)
            })
        except Exception as e:
            print(f" [!] Error parsing a product: {e}")
            
    return products

async def save_to_db(category_data, products_data):
    """Save scraped data to the database using synchronous session."""
    db = SessionLocal()
    try:
        db_category = db.query(Category).filter(Category.name == category_data['name']).first()
        
        if not db_category:
            db_category = Category(name=category_data['name'], url=category_data['url'])
            db.add(db_category)
            db.flush()
            
        for p_data in products_data:
            db_product = db.query(Product).filter(Product.external_id == p_data['external_id']).first()
            
            if not db_product:
                db_product = Product(
                    external_id=p_data['external_id'],
                    name=p_data['name'],
                    unit=p_data['unit'],
                    unit_type=p_data['unit_type'],
                    image_url=p_data['image_url'],
                    category_id=db_category.id
                )
                db.add(db_product)
                db.flush()
                
            history = PriceHistory(
                product_id=db_product.id,
                actual_price=p_data['actual_price'],
                unit_price=p_data['unit_price'],
                scraped_at=p_data['scraped_at'].replace(tzinfo=None)
            )
            db.add(history)
            
        db.commit()
    except Exception as e:
        db.rollback()
        print(f" [!] Meena Bazar Database Error: {e}")
        raise e
    finally:
        db.close()

async def main():
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    init_db()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        categories = await scrape_categories(page)
        
        for cat in categories: 
            all_products = await scrape_products_in_category(page, cat['url'])
            summary['total'] += len(all_products)
            summary['categories'][cat['name']] += len(all_products)
            print(f" -> Scraped {len(all_products)} products from {cat['name']}")
            await save_to_db(cat, all_products)
                
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

