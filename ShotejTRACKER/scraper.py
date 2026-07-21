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
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
from datetime import datetime, date, timezone, timedelta
import asyncio
from collections import Counter
import json
import re
import os
import random
import logging
from playwright.async_api import async_playwright

DHAKA_TZ = timezone(timedelta(hours=6))

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
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(data):
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

def parse_box_weight(description, name):
    # Match patterns like "40gm X 20pcs" or "500g * 10"
    text = (description + " " + name).lower()
    
    # Try to find multiplier pattern: VALUE UNIT x COUNT
    # Matches: 40gm x 20pcs, 35gm X 20pcs, 500g * 10, etc.
    multiplier_match = re.search(r'(\d+(?:\.\d+)?)\s*(gm|g|kg|ml|l|ltr|pcs?)\s*[xX*]\s*(\d+)', text)
    
    if multiplier_match:
        val = float(multiplier_match.group(1))
        unit = multiplier_match.group(2)
        count = float(multiplier_match.group(3))
        
        total_val = val * count
        
        # Standardize units
        if unit in ['gm', 'g', 'ml']:
            total_val /= 1000.0
            std_unit = 'kg' if unit in ['gm', 'g'] else 'liter'
        elif unit in ['kg', 'l', 'ltr']:
            std_unit = 'kg' if unit == 'kg' else 'liter'
        else:
            std_unit = 'piece'
            
        return total_val, std_unit, f"{int(val) if val.is_integer() else val}{unit} x {int(count)}"

    # Fallback to standard normalization if no multiplier found
    # (Simplified version of the one in aggregator.py)
    kg_match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|gm|g)\b', text)
    l_match = re.search(r'(\d+(?:\.\d+)?)\s*(l|ml|ltr)\b', text)
    
    if kg_match:
        v = float(kg_match.group(1))
        u = kg_match.group(2)
        return (v / 1000.0 if u in ['gm', 'g'] else v), 'kg', f"{v}{u}"
    if l_match:
        v = float(l_match.group(1))
        u = l_match.group(2)
        return (v / 1000.0 if u == 'ml' else v), 'liter', f"{v}{u}"
        
    return 1.0, 'piece', '1 unit'

async def scrape_category(sem, browser, category, current_data, summary):
    async with sem:
        context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
        page = await context.new_page()
        
        logger.info(f"Scraping: {category['name']} ({category['url']})")
        try:
            await page.goto(category['url'], wait_until="networkidle", timeout=60000)
            
            # Infinite Scroll Implementation
            last_height = await page.evaluate("document.body.scrollHeight")
            while True:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(3) # Wait for JS to load more items
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            # Extract basic info from list
            cards = await page.query_selector_all('.wd-product')
            logger.info(f"  [+] Found {len(cards)} items in grid. Starting extraction...")

            today_str = date.today().isoformat()
            
            for card in cards:
                try:
                    title_el = await card.query_selector('.wd-entities-title a')
                    if not title_el: continue
                    name = await title_el.inner_text()
                    product_url = await title_el.get_attribute('href')
                    
                    # Price Extraction: Prioritize Sale Price (ins) over Original Price (del)
                    price_el = await card.query_selector('.price ins .woocommerce-Price-amount')
                    if not price_el:
                        price_el = await card.query_selector('.price .woocommerce-Price-amount')
                    
                    if not price_el: continue
                    price_text = await price_el.inner_text()
                    current_price = float(re.sub(r'[^\d.]', '', price_text))
                    
                    img_el = await card.query_selector('.wd-product-thumb img')
                    img_src = await img_el.get_attribute('src') if img_el else ""

                    prod_id = "sj_" + re.sub(r'\W+', '', name).lower()
                    
                    total_weight, unit_type, qty_label = parse_box_weight("", name)
                    norm_price = current_price / total_weight if total_weight > 0 else current_price

                    summary['total'] += 1
                    summary['categories'][category['name']] += 1
                    if prod_id not in current_data:
                        current_data[prod_id] = {
                            "id": prod_id, "name": name, "store": "shotejbazar",
                            "image": img_src, "category": category['name'], "history": []
                        }
                    
                    current_data[prod_id].update({
                        "current_price": current_price, "normalized_price": round(norm_price, 2),
                        "unit": qty_label, "unit_type": unit_type, "url": product_url
                    })
                    
                    history = current_data[prod_id]["history"]
                    if not history or history[-1]['date'] != today_str:
                         history.append({"date": today_str, "price": current_price, "normalized_price": round(norm_price, 2)})
                    elif history[-1]['date'] == today_str:
                        history[-1]['price'] = current_price
                        history[-1]['normalized_price'] = round(norm_price, 2)

                except Exception as e:
                    logger.error(f"    [!] Error on product: {e}")
                    continue

            return True
        except Exception as e:
            logger.error(f"  [X] Error: {e}")
            return False
        finally:
            await context.close()

async def main():
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    data = load_data()
    category_data = load_categories()
    enabled_categories = [c for c in flatten_categories(category_data) if c.get('enabled', True)]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        sem = asyncio.Semaphore(1) 
        for cat in enabled_categories:
            await scrape_category(sem, browser, cat, data, summary)
            save_data(data) # Save after each category
            
        await browser.close()
    
    save_last_run_log(summary)
    logger.info("ShotejBazar scraping complete.")

def save_last_run_log(summary):
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
