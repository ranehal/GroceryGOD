import asyncio
from collections import Counter
import json
import re
import datetime
import os
import random
import logging
from collections import Counter
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
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def load_categories():
    if os.path.exists(CATEGORIES_FILE):
        with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"groups": [], "custom": []}

def load_pinned_names():
    cats = load_categories()
    pinned = next((g for g in cats.get('groups', []) if g.get('id') == 'pinned_deals'), None)
    if pinned:
        return [c['name'] for c in pinned['categories']]
    return []

def flatten_categories(category_data):
    all_categories = []
    for group in category_data.get('groups', []):
        for cat in group.get('categories', []):
            all_categories.append(cat)
    return all_categories

def normalize_unit(name, price_str):
    name_lower = name.lower()
    price = float(re.sub(r'[^\d.]', '', price_str))
    
    kg_pattern = r'(\d+(?:\.\d+)?)\s*(kg|gm|gram|g)\b'
    l_pattern = r'(\d+(?:\.\d+)?)\s*(l|ml|ltr|liter)\b'
    
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
        if unit in ['gm', 'g', 'gram', 'ml']: val /= 1000.0
        
        if val > 0:
            norm_price = price / val
            if is_kg:
                quantity_display = f"{val} kg" if val >= 1 else f"{int(val*1000)} gm"
                unit_type = "kg"
            else:
                quantity_display = f"{val} L" if val >= 1 else f"{int(val*1000)} ml"
                unit_type = "liter"
                
    return quantity_display, round(norm_price, 2), unit_type

async def self_scrape_items(page, container_selector, category, current_data, today_str, is_pinned=False):
    container = await page.query_selector(container_selector) or page
    # Broaden selector to capture products in different layouts
    items = await container.query_selector_all('.product-box, div[class*="product-grid-item"], .product-item-info')
    logger.info(f"    [+] Extracted {len(items)} items from current view")
    
    for item in items:
        try:
            # Flexible title/link selector
            title_el = await item.query_selector('.product-box-title a, a[class*="title"], .name a')
            if not title_el: continue
            name = (await title_el.inner_text()).strip()
            url_suffix = await title_el.get_attribute('href')
            product_url = f"https://www.shwapno.com{url_suffix}" if url_suffix.startswith('/') else url_suffix
            
            img_el = await item.query_selector('img')
            img_src = await img_el.get_attribute('src') if img_el else ""
            
            price_el = await item.query_selector('.active-price, .price, span[class*="price"]')
            if not price_el: continue
            price_text = await price_el.inner_text()
            current_price = float(re.sub(r'[^\d.]', '', price_text))
            
            qty_disp, norm_price, unit_type = normalize_unit(name, price_text)
            prod_id = re.sub(r'\W+', '', name).lower()
            
            # PINNING PRIORITY LOGIC:
            if prod_id not in current_data:
                current_data[prod_id] = {
                    "id": prod_id, "name": name, "url": product_url, 
                    "image": img_src, "category": category['name'], "history": []
                }
            elif is_pinned:
                # If product already exists but current category is a high-priority Pinned one, overwrite the category tag
                current_data[prod_id]["category"] = category['name']
            
            current_data[prod_id].update({
                "current_price": current_price, "normalized_price": norm_price,
                "unit": qty_disp, "unit_type": unit_type, "image": img_src, "url": product_url
            })
            
            history = current_data[prod_id]["history"]
            if not history or history[-1]['date'] != today_str:
                 history.append({"date": today_str, "price": current_price, "normalized_price": norm_price})
            elif history[-1]['date'] == today_str:
                history[-1]['price'] = current_price
                history[-1]['normalized_price'] = norm_price
        except: pass

async def scrape_category(sem, browser, category, current_data, pinned_names=[]):
    async with sem:
        is_pinned = category['name'] in pinned_names
        context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
        page = await context.new_page()
        
        logger.info(f"Scraping: {category['name']} ({category['url']})")
        try:
            await page.goto(category['url'], wait_until="load", timeout=120000)
            await asyncio.sleep(5) # Allow dynamic content
            
            today_str = datetime.date.today().isoformat()
            container_selector = f"xpath={category['xpath']}" if category.get('xpath') else "body"
            
            # Robust Tab Detection for "More Items" pages
            tabs = await page.query_selector_all('.category-tab-list div, .category-tab-list a, .nav-tabs li a, .category-item-title')
            valid_tabs = []
            for t in tabs:
                t_text = (await t.inner_text()).strip()
                if t_text and len(t_text) < 40:
                    valid_tabs.append(t)
            
            if len(valid_tabs) > 1:
                logger.info(f"  [+] Detected {len(valid_tabs)} tabs in {category['name']}. Deep clicking...")
                for i in range(len(valid_tabs)):
                    # Refresh tab elements to avoid detached DOM
                    current_tabs = await page.query_selector_all('.category-tab-list div, .category-tab-list a, .nav-tabs li a, .category-item-title')
                    # Match by text to be safe
                    tab_name = (await valid_tabs[i].inner_text()).strip()
                    target_tab = None
                    for ct in current_tabs:
                        if (await ct.inner_text()).strip() == tab_name:
                            target_tab = ct
                            break
                    
                    if not target_tab: continue
                    
                    logger.info(f"    -> Tab {i+1}/{len(valid_tabs)}: {tab_name}")
                    try:
                        await target_tab.click()
                        await asyncio.sleep(4)
                        for _ in range(4): # Scroll deep within tab
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await asyncio.sleep(1.5)
                        await self_scrape_items(page, container_selector, category, current_data, today_str, is_pinned)
                    except: continue
            else:
                # Standard Scroll Scrape
                for _ in range(10):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1.5)
                await self_scrape_items(page, container_selector, category, current_data, today_str, is_pinned)
            
            return True
        except Exception as e:
            logger.error(f"  [X] Error: {str(e)[:100]}")
            return False
        finally:
            await context.close()

async def main():
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    data = load_data()
    category_data = load_categories()
    pinned_names = load_pinned_names()
    enabled_categories = [c for c in flatten_categories(category_data) if c.get('enabled', True)]
    
    logger.info(f"Started Scraper: {len(enabled_categories)} categories, {len(pinned_names)} pinned.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        sem = asyncio.Semaphore(1) 
        
        # Order: Pinned Categories FIRST
        pinned_cats = [c for c in enabled_categories if c['name'] in pinned_names]
        other_cats = [c for c in enabled_categories if c['name'] not in pinned_names]
        
        queue = pinned_cats + other_cats
        for i, cat in enumerate(queue):
            logger.info(f"Progress: {i+1}/{len(queue)}")
            await scrape_category(sem, browser, cat, data, pinned_names)
            if (i+1) % 5 == 0: save_data(data) # Save every 5 cats
            
        await browser.close()
    
    save_data(data)
    save_last_run_log(summary)
    logger.info("Shwapno Scraper Complete.")

if __name__ == "__main__":
    asyncio.run(main())

def save_last_run_log(summary):
    import os
    from datetime import datetime
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base_dir, "last_run_log.txt")
    with open(log_path, "w", encoding='utf-8') as f:
        f.write(f"Last Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("-" * 30 + "\n")
        f.write(f"Total Scraped: {summary['total']}\n")
        f.write(f"New Items: {summary.get('new', 'N/A')}\n")
        f.write("-" * 30 + "\n")
        f.write("Categories:\n")
        for cat, count in sorted(summary['categories'].items(), key=lambda x: x[1], reverse=True)[:10]:
            f.write(f"- {cat}: {count}\n")
        if len(summary['categories']) > 10:
            f.write(f"... and {len(summary['categories']) - 10} more.")
