import asyncio
import re
from playwright.async_api import async_playwright
from datetime import datetime, timezone
from database import async_session, Category, Product, PriceHistory, init_db
from sqlalchemy.future import select

BASE_URL = "https://www.metromartonline.com"

CATEGORIES = [
    {"name": "Dairy", "url": f"{BASE_URL}/allproductslist?q=Dairy"},
    {"name": "Snacks", "url": f"{BASE_URL}/allproductslist?q=Snacks"},
    {"name": "Groceries", "url": f"{BASE_URL}/allproductslist?q=Groceries"},
    {"name": "Grain", "url": f"{BASE_URL}/allproductslist?q=Grain"},
    {"name": "Drinking Water", "url": f"{BASE_URL}/allproductslist?q=Drinking%20Water"},
    {"name": "Condiments", "url": f"{BASE_URL}/allproductslist?q=Condiments"},
    {"name": "Bakery", "url": f"{BASE_URL}/allproductslist?q=Bakery"},
    {"name": "Spice & Masala", "url": f"{BASE_URL}/allproductslist?q=Spice%20%26%20Masala"},
    {"name": "Beauty & Personal Care", "url": f"{BASE_URL}/allproductslist?q=Beauty%20%26%20Personal%20Care"},
    {"name": "Cleaning Supplies", "url": f"{BASE_URL}/allproductslist?q=Cleaning%20Supplies"},
    {"name": "Beverage", "url": f"{BASE_URL}/allproductslist?q=Beverage"}
]

async def scrape_products_in_category(page, category_url):
    print(f"\n[Scraping Category] {category_url}")
    try:
        await page.goto(category_url, wait_until="networkidle", timeout=60000)
        # Wait for the initial grid to load
        await page.wait_for_selector('img[alt]', timeout=30000)
    except Exception as e:
        print(f"No products found or timeout in {category_url}: {e}")
        return []

    # Handle "Load More" pagination with explicit scrolling
    print(" -> Expanding list via 'Load More'...")
    load_more_attempts = 0
    max_load_more = 100 
    
    while load_more_attempts < max_load_more:
        # Scroll to bottom to ensure Load More button is triggered/visible
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)
        
        try:
            # Look for button that contains "Load More" text
            load_more_btn = await page.query_selector('button:has-text("Load More")')
            if load_more_btn and await load_more_btn.is_visible():
                print(f"    - Click {load_more_attempts + 1}...")
                await load_more_btn.click()
                await asyncio.sleep(3) # Wait for network/rendering
                load_more_attempts += 1
            else:
                # Button might be hidden or replaced by loading spinner
                # Check if we can find it again after a short wait
                await asyncio.sleep(2)
                load_more_btn = await page.query_selector('button:has-text("Load More")')
                if not load_more_btn:
                    break
        except Exception:
            break
            
    # Extract product data
    # Cards are usually <a> tags wrapping a complex div structure
    # Based on Metro/item.html, they have shadow-small rounded-small and specific gradients
    cards = await page.query_selector_all('a[href].w-full')
    
    # Filter to only keep those that look like product cards (have an image and price)
    valid_cards = []
    for card in cards:
        img = await card.query_selector('img')
        price = await card.query_selector('span:has-text("৳")')
        if img and price:
            valid_cards.append(card)

    print(f" -> Extraction: Found {len(valid_cards)} product units.")
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

            # Unit detection - Look for gm, kg, ml, ltr patterns in the card text
            card_text = await card.inner_text()
            # Try to find unit in the specific span first
            unit_el = await card.query_selector('span.flex-1.text-inherit')
            unit = await unit_el.inner_text() if unit_el else "N/A"

            if name == "N/A" or actual_price == 0: continue

            # Normalization logic
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
                "external_id": external_id,
                "name": name,
                "unit": unit,
                "actual_price": actual_price,
                "unit_price": round(unit_price, 2),
                "unit_type": unit_type,
                "image_url": image_url,
                "scraped_at": datetime.now(timezone.utc)
            })
        except Exception:
            continue

    return products

async def save_to_db(category_name, category_url, products):
    async with async_session() as session:
        try:
            # Get or create category
            result = await session.execute(select(Category).filter_by(name=category_name))
            db_cat = result.scalars().first()
            if not db_cat:
                db_cat = Category(name=category_name, url=category_url)
                session.add(db_cat)
                await session.flush()

            for p in products:
                # Get or create product
                result = await session.execute(select(Product).filter_by(external_id=p['external_id']))
                db_p = result.scalars().first()
                if not db_p:
                    db_p = Product(
                        external_id=p['external_id'],
                        name=p['name'],
                        unit=p['unit'],
                        unit_type=p['unit_type'],
                        image_url=p['image_url'],
                        category_id=db_cat.id
                    )
                    session.add(db_p)
                    await session.flush()

                # Add price history (using naive UTC)
                history = PriceHistory(
                    product_id=db_p.id,
                    actual_price=p['actual_price'],
                    unit_price=p['unit_price'],
                    scraped_at=p['scraped_at'].replace(tzinfo=None)
                )
                session.add(history)
            
            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f" [!] Database Error in {category_name}: {e}")
            raise e

async def main():
    await init_db()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        for cat in CATEGORIES:
            products = await scrape_products_in_category(page, cat['url'])
            if products:
                await save_to_db(cat['name'], cat['url'], products)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
