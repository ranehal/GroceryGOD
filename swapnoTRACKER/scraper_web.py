import os
from datetime import timezone, timedelta
from datetime import datetime, date
import asyncio
from collections import Counter
import json
import re
import logging
import time
import aiohttp

# Custom DHAKA timezone
DHAKA_TZ = timezone(timedelta(hours=6))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add file handler for history
fh = logging.FileHandler('scraper.log', encoding='utf-8')
fh.setLevel(logging.INFO)
fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
logger.addHandler(fh)

def normalize_unit(name, current_price_str):
    name_lower = name.lower()
    qty_disp = "1 Piece"
    unit_type = "pc"
    norm_price = float(current_price_str)
    
    match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|gm|liter|ltr|l|ml|piece|pc|pcs|pack|pk)', name_lower)
    if match:
        val = float(match.group(1))
        u = match.group(2)
        if u in ['kg']:
            qty_disp = f"{val} kg"
            unit_type = "kg"
            norm_price = norm_price / val
        elif u in ['g', 'gm']:
            qty_disp = f"{val} gm"
            unit_type = "kg"
            norm_price = (norm_price / val) * 1000
        elif u in ['liter', 'ltr', 'l']:
            qty_disp = f"{val} L"
            unit_type = "L"
            norm_price = norm_price / val
        elif u in ['ml']:
            qty_disp = f"{val} ml"
            unit_type = "L"
            norm_price = (norm_price / val) * 1000
        else:
            qty_disp = f"{val} {u}"
            unit_type = "pc"
            norm_price = norm_price / val
    else:
        if 'rice' in name_lower and not any(x in name_lower for x in ['spice', 'cake', 'cracker']):
            unit_type = "kg"
            qty_disp = "1 kg (assumed)"
    
    return qty_disp, round(norm_price, 2), unit_type

def load_data():
    if os.path.exists('data.json'):
        with open('data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_categories():
    with open('categories.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def flatten_categories(data):
    cats = []
    for group in data.get('groups', []):
        cats.extend(group.get('categories', []))
    return cats

def load_pinned_names():
    try:
        from dynamic_pins import PINNED_CATEGORIES
        return [c['name'] for c in PINNED_CATEGORIES]
    except:
        return []

async def scrape_category_api(session, category, current_data, summary, pinned_names, today_str):
    cat_id = category.get('id')
    cat_name = category['name']
    is_pinned = cat_name in pinned_names
    
    if not cat_id:
        logger.info(f"Scraping: {cat_name} - Skipped (No ID)")
        return True
        
    logger.info(f"Scraping: {cat_name} (API ID: {cat_id})")
    extracted = 0
    page_idx = 1
    
    while True:
        api_url = f"https://www.shwapno.com/api/category/products?lang=en&id={cat_id}&pageNumber={page_idx}"
        try:
            async with session.get(api_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}) as r:
                if r.status != 200:
                    logger.warning(f"  [X] API returned {r.status} on {cat_name} page {page_idx}")
                    break
                
                data = await r.json()
                products = data.get('products', [])
                if not products:
                    break
                    
                for prod in products:
                    name = prod.get('name', '').strip()
                    seName = prod.get('seName', '')
                    product_url = f"https://www.shwapno.com/{seName}?lang=en" if seName else ""
                    
                    pic = prod.get('picture', {})
                    img_src = pic.get('largeDeviceUrl', {}).get('imageUrl') or pic.get('smallDeviceUrl', {}).get('imageUrl') or ""
                    
                    price_info = prod.get('price', {})
                    current_price = price_info.get('priceValue', 0.0)
                    discount_amount = price_info.get('discountAmountValue', 0.0)
                    
                    if current_price <= 0:
                        continue
                        
                    original_price = current_price + discount_amount if discount_amount > 0 else None
                    discount = None
                    if original_price and original_price > current_price:
                        discount = f"{int(((original_price - current_price) / original_price) * 100)}%"
                        
                    qty_disp, norm_price, unit_type = normalize_unit(name, str(current_price))
                    prod_id = re.sub(r'\W+', '', name).lower()
                    
                    summary['total'] += 1
                    summary['categories'][cat_name] += 1
                    
                    if prod_id not in current_data:
                        current_data[prod_id] = {
                            "id": prod_id, "name": name, "url": product_url, 
                            "image": img_src, "category": cat_name, "history": []
                        }
                    elif is_pinned:
                        current_data[prod_id]["category"] = cat_name
                        
                    current_data[prod_id].update({
                        "current_price": current_price, "normalized_price": norm_price,
                        "original_price": original_price, "discount": discount,
                        "unit": qty_disp, "unit_type": unit_type, "image": img_src, "url": product_url
                    })
                    
                    history = current_data[prod_id]["history"]
                    if not history or history[-1]['date'] != today_str:
                        history.append({"date": today_str, "price": current_price, "normalized_price": norm_price, "original_price": original_price, "discount": discount})
                    elif history[-1]['date'] == today_str:
                        history[-1]['price'] = current_price
                        history[-1]['normalized_price'] = norm_price
                        history[-1]['original_price'] = original_price
                        history[-1]['discount'] = discount
                
                extracted += len(products)
                if not data.get('hasNextPage'):
                    break
                page_idx += 1
                
        except Exception as e:
            logger.error(f"  [X] Failed API fetch for {cat_name}: {e}")
            break
            
    logger.info(f"    [+] Extracted {extracted} items from {cat_name}")
    return True

async def main():
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    data = load_data()
    category_data = load_categories()
    pinned_names = load_pinned_names()
    enabled_categories = [c for c in flatten_categories(category_data) if c.get('enabled', True)]
    
    logger.info(f"Started Scraper API: {len(enabled_categories)} categories, {len(pinned_names)} pinned.")
    today_str = datetime.now(DHAKA_TZ).date().isoformat()
    
    async with aiohttp.ClientSession() as session:
        pinned_cats = [c for c in enabled_categories if c['name'] in pinned_names]
        other_cats = [c for c in enabled_categories if c['name'] not in pinned_names]
        queue = pinned_cats + other_cats
        
        # Scrape 10 categories concurrently
        sem = asyncio.Semaphore(10)
        async def scrape_with_sem(cat):
            async with sem:
                return await scrape_category_api(session, cat, data, summary, pinned_names, today_str)
                
        tasks = [scrape_with_sem(cat) for cat in queue]
        await asyncio.gather(*tasks)
        
    save_data(data)
    save_last_run_log(summary)
    logger.info("Shwapno Scraper Complete.")

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
