import asyncio
import json
import re
import datetime
import os
import random
import logging
from playwright.async_api import async_playwright

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler("scraper.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DATA_FILE = 'data.json'
CATEGORIES_FILE = 'categories.json'

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
]

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(data):
    # Save as JSON for both backend and frontend use
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def load_categories():
    if os.path.exists(CATEGORIES_FILE):
        with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"groups": [], "custom": []}

def flatten_categories(category_data):
    all_categories = []
    for group in category_data.get('groups', []):
        for cat in group.get('categories', []):
            all_categories.append(cat)
    return all_categories

def normalize_unit(name, price_str):
    name_lower = name.lower()
    price = float(re.sub(r'[^\d.]', '', price_str))
    
    kg_pattern = r'(\d+(?:\.\d+)?)\s*(kg|gm|g)\b'
    l_pattern = r'(\d+(?:\.\d+)?)\s*(l|ml|ltr)\b'
    
    kg_match = re.search(kg_pattern, name_lower)
    l_match = re.search(l_pattern, name_lower)
    
    quantity_display = "Per Piece"; norm_price = price; unit_type = "piece"
    
    if kg_match or l_match:
        if kg_match:
            base_val = float(kg_match.group(1))
            unit = kg_match.group(2)
            is_kg = True
        else:
            base_val = float(l_match.group(1))
            unit = l_match.group(2)
            is_kg = False
            
        val = base_val
        if unit in ['gm', 'g', 'ml']: val /= 1000.0
        
        # Check for Buy X Get Y Free offers
        buy_match = re.search(r'buy\s*(\d+)', name_lower)
        get_match = re.search(r'get\s*(?:.*?\s+)?(\d+(?:\.\d+)?)\s*(kg|gm|g|ml|l|ltr)?.*?\s*free', name_lower)
        
        if buy_match and get_match:
            buy_qty = float(buy_match.group(1))
            get_val = float(get_match.group(1))
            get_unit = get_match.group(2)
            
            if get_unit:
                # Free quantity has a specified unit (e.g., 500gm)
                free_val = get_val
                if get_unit in ['gm', 'g', 'ml']: free_val /= 1000.0
                val = (buy_qty * val) + free_val
            else:
                # Free quantity is in terms of items (e.g., Get 1 Free)
                val = (buy_qty + get_val) * val
                
        if val > 0:
            norm_price = price / val
            if is_kg:
                quantity_display = f"{val} kg" if val >= 1 else f"{int(val*1000)} gm"
                unit_type = "kg"
            else:
                quantity_display = f"{val} L" if val >= 1 else f"{int(val*1000)} ml"
                unit_type = "liter"
                
    return quantity_display, round(norm_price, 2), unit_type

async def scrape_category(sem, browser, category, current_data):
    async with sem:
        ua = random.choice(USER_AGENTS)
        context = await browser.new_context(user_agent=ua, viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        
        logger.info(f"Scraping: {category['name']} ({category['url']})")
        try:
            # Wait between categories to avoid detection
            await asyncio.sleep(random.uniform(3, 7))
            
            response = await page.goto(category['url'], wait_until="load", timeout=120000)
            
            if response.status == 403:
                logger.warning(f"  [!] 403 Forbidden for {category['name']}")
                return False
            
            # Additional scroll to ensure lazy loading items appear
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1.5)
            
            items = await page.query_selector_all('.product-box')
            logger.info(f"  [+] Found {len(items)} items in {category['name']}")
            
            if len(items) == 0:
                # Check for empty state vs blocked state
                content = await page.content()
                if "403 Forbidden" in content or "Cloudflare" in content:
                    logger.error(f"  [!] Blocked by Cloudflare for {category['name']}")
                    return False

            today_str = datetime.date.today().isoformat()
            
            for item in items:
                try:
                    title_el = await item.query_selector('.product-box-title a')
                    if not title_el: continue
                    name = await title_el.inner_text()
                    url_suffix = await title_el.get_attribute('href')
                    product_url = f"https://www.shwapno.com{url_suffix}"
                    
                    img_el = await item.query_selector('img')
                    img_src = await img_el.get_attribute('src') if img_el else ""
                    
                    price_el = await item.query_selector('.product-price .active-price')
                    if not price_el: continue
                    price_text = await price_el.inner_text()
                    current_price = float(re.sub(r'[^\d.]', '', price_text))
                    
                    qty_disp, norm_price, unit_type = normalize_unit(name, price_text)
                    prod_id = re.sub(r'\W+', '', name).lower()
                    
                    if prod_id not in current_data:
                        current_data[prod_id] = {
                            "id": prod_id, "name": name, "url": product_url, 
                            "image": img_src, "category": category['name'], "history": []
                        }
                    
                    current_data[prod_id].update({
                        "current_price": current_price, "normalized_price": norm_price,
                        "unit": qty_disp, "unit_type": unit_type, "image": img_src
                    })
                    
                    history = current_data[prod_id]["history"]
                    if not history or history[-1]['date'] != today_str:
                         history.append({"date": today_str, "price": current_price, "normalized_price": norm_price})
                    elif history[-1]['date'] == today_str:
                        history[-1]['price'] = current_price
                        history[-1]['normalized_price'] = norm_price

                except: pass
            
            return True
                    
        except Exception as e:
            logger.error(f"  [X] Error scraping {category['name']}: {str(e)[:100]}")
            return False
        finally:
            await context.close()

async def main():
    data = load_data()
    category_data = load_categories()
    all_categories = flatten_categories(category_data)
    enabled_categories = [c for c in all_categories if c.get('enabled', True)]
    
    logger.info(f"Loaded {len(all_categories)} categories. {len(enabled_categories)} enabled.")

    async with async_playwright() as p:
        # Launch browser once
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        
        sem = asyncio.Semaphore(1) # SEQUENTIAL to avoid blocking
        
        results = []
        chunk_size = 5
        for i in range(0, len(enabled_categories), chunk_size):
            chunk = enabled_categories[i:i + chunk_size]
            tasks = [scrape_category(sem, browser, cat, data) for cat in chunk]
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
            results.extend(chunk_results)
            
            # Save progress often
            try:
                save_data(data)
                logger.info(f"Progress: {min(i + chunk_size, len(enabled_categories))}/{len(enabled_categories)} categories. Data saved.")
            except Exception as e:
                logger.error(f"Failed to save data progress: {e}")
            
            # Big pause between chunks
            await asyncio.sleep(random.uniform(5, 10))
        
        await browser.close()
    
    save_data(data)
    
    # Sync categories
    with open('categories.json', 'w', encoding='utf-8') as f:
        json.dump(category_data, f, indent=2)

    success_count = sum(1 for r in results if r is True)
    logger.info(f"Scraping complete! Success: {success_count}, Failed: {len(results) - success_count}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"FATAL ERROR: {str(e)}", exc_info=True)
        print(f"\n[CRITICAL] Scraper crashed: {e}")
        import traceback
        traceback.print_exc()
