import os
from datetime import timezone, timedelta
from datetime import datetime, date
import asyncio
from collections import Counter
import json
import re
import logging
import time
import urllib.parse
import aiohttp

# Custom DHAKA timezone
DHAKA_TZ = timezone(timedelta(hours=6))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# Complete Location Sequence
# Selector: #main-header > div.z-50.bg-main > div > div.relative.z-[99].ml-auto.hidden.min-w-[180px].max-w-[220px].cursor-pointer.md:block.xl:ml-10.\32 xl:ml-auto > span
# Locations:
#   1. Dhaka, Banasree Block C (Primary)
#   2. Khilgaon Nobabi More
#   3. Khilgaon Chowdhury para
#   4. Khilgaon
#   5. Bashabo
STORE_LOCATIONS = [
    {
        "area": "Banasree Block C",
        "district": "Dhaka",
        "stateProvinceId": "65eb61bd452e887cd78e240d",
        "cityId": "65ed4befe30f25b233e5f48d",
        "areaId": "686f4fdee45b27590891fd90",
        "darkStoreId": "65f008e64119aecf652223f1",
        "darkStoreName": "Banasree "
    },
    {
        "area": "Khilgaon Nobabi More",
        "district": "Dhaka",
        "stateProvinceId": "65eb61bd452e887cd78e240d",
        "cityId": "65ed4e91e30f25b233e60142",
        "areaId": "65efdfc34119aecf6521af15",
        "darkStoreId": "65f00cbe101d9be04a6c4d02",
        "darkStoreName": "Sky View"
    },
    {
        "area": "Khilgaon Chowdhury para",
        "district": "Dhaka",
        "stateProvinceId": "65eb61bd452e887cd78e240d",
        "cityId": "65ed4e91e30f25b233e60142",
        "areaId": "65efdfec4119aecf6521b08d",
        "darkStoreId": "65f00cbe101d9be04a6c4d02",
        "darkStoreName": "Sky View"
    },
    {
        "area": "Khilgaon",
        "district": "Dhaka",
        "stateProvinceId": "65eb61bd452e887cd78e240d",
        "cityId": "65ed4e91e30f25b233e60142",
        "areaId": "65efe0004119aecf6521b1c2",
        "darkStoreId": "65f00cbe101d9be04a6c4d02",
        "darkStoreName": "Sky View"
    },
    {
        "area": "Bashabo",
        "district": "Dhaka",
        "stateProvinceId": "65eb61bd452e887cd78e240d",
        "cityId": "65ed4d0ee30f25b233e5f67b",
        "areaId": "65ed55bf452e887cd78e601f",
        "darkStoreId": "65f00a36101d9be04a6c429a",
        "darkStoreName": "Central Basabo 2"
    }
]

BANASREE_LOCATION = STORE_LOCATIONS[0]
DARKSTORE_COOKIE = f"_ds_={BANASREE_LOCATION['darkStoreId']}; _nc_=false; _mo_=false;"

def init_delivery_slot(location):
    import urllib.request, ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        payload = json.dumps({
            "stateProvinceId": location["stateProvinceId"],
            "cityId": location["cityId"],
            "areaId": location["areaId"]
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://www.shwapno.com/api/delivery-slot/set?set",
            data=payload,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Content-Type": "application/json",
                "Referer": "https://www.shwapno.com/",
                "Origin": "https://www.shwapno.com"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            logger.info("Locked delivery slot to %s (Darkstore: %s)", location['area'], location['darkStoreId'])
            return True
    except Exception as e:
        logger.warning("Could not pre-init delivery slot for %s: %s (will enforce via _ds_ cookie)", location['area'], e)
        return False

def init_banasree_slot():
    return init_delivery_slot(BANASREE_LOCATION)

def get_store_headers(location):
    ds_id = location['darkStoreId']
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.shwapno.com/',
        'Cookie': f"_ds_={ds_id}; _nc_=false; _mo_=false;",
        'DarkstoreId': ds_id,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin'
    }

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

def update_product_entry(current_data, prod, cat_name, cat_id, today_str, store_loc_name, is_pinned=False):
    name = prod.get('name', '').strip()
    if not name:
        return None
    seName = prod.get('seName', '')
    product_url = f"https://www.shwapno.com/{seName}?lang=en" if seName else ""
    
    pic = prod.get('picture', {})
    img_src = pic.get('largeDeviceUrl', {}).get('imageUrl') or pic.get('smallDeviceUrl', {}).get('imageUrl') or ""
    
    price_info = prod.get('price', {})
    current_price = price_info.get('priceValue', 0.0)
    discount_amount = price_info.get('discountAmountValue', 0.0)
    
    if current_price <= 0:
        return None
        
    original_price = current_price + discount_amount if discount_amount > 0 else None
    discount = None
    if original_price and original_price > current_price:
        discount = f"{int(((original_price - current_price) / original_price) * 100)}%"
        
    qty_disp, norm_price, unit_type = normalize_unit(name, str(current_price))
    prod_id = re.sub(r'\W+', '', name).lower()
    
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
        "unit": qty_disp, "unit_type": unit_type, "image": img_src, "url": product_url,
        "in_stock": True, "is_out_of_stock": False,
        "store_location": store_loc_name,
        "sku": prod.get('sku') or current_data[prod_id].get('sku', '')
    })
    if cat_id:
        current_data[prod_id]["category_id"] = cat_id
        
    history = current_data[prod_id]["history"]
    if not history or history[-1]['date'] != today_str:
        history.append({"date": today_str, "price": current_price, "normalized_price": norm_price, "original_price": original_price, "discount": discount})
    elif history[-1]['date'] == today_str:
        history[-1]['price'] = current_price
        history[-1]['normalized_price'] = norm_price
        history[-1]['original_price'] = original_price
        history[-1]['discount'] = discount
        
    return prod_id

async def scrape_category_api(session, category, current_data, summary, pinned_names, today_str, seen_today):
    cat_id = category.get('id')
    cat_name = category['name']
    is_pinned = cat_name in pinned_names
    
    if not cat_id:
        logger.info(f"Scraping: {cat_name} - Skipped (No ID)")
        return True
        
    logger.info(f"Scraping: {cat_name} (API ID: {cat_id})")
    extracted = 0
    page_idx = 1
    
    headers = get_store_headers(BANASREE_LOCATION)
    while True:
        api_url = f"https://www.shwapno.com/api/category/products?lang=en&id={cat_id}&pageNumber={page_idx}"
        try:
            async with session.get(api_url, headers=headers) as r:
                if r.status != 200:
                    logger.warning(f"  [X] API returned {r.status} on {cat_name} page {page_idx}")
                    break
                
                data = await r.json()
                products = data.get('products', [])
                if not products:
                    break
                    
                for prod in products:
                    res_id = update_product_entry(current_data, prod, cat_name, cat_id, today_str, BANASREE_LOCATION['area'], is_pinned)
                    if res_id:
                        seen_today.add(res_id)
                        summary['total'] += 1
                        summary['categories'][cat_name] += 1
                        extracted += 1
                
                if not data.get('hasNextPage'):
                    break
                page_idx += 1
                
        except Exception as e:
            logger.error(f"  [X] Failed API fetch for {cat_name}: {e}")
            break
            
    logger.info(f"    [+] Extracted {extracted} items from {cat_name}")
    return True

async def rescrape_oos_across_stores(session, oos_prod_ids, current_data, today_str):
    """
    Groups OOS products from Banasree Block C and re-scrapes them across fallback locations:
      1. Khilgaon Nobabi More
      2. Khilgaon Chowdhury para
      3. Khilgaon
      4. Bashabo
    Tries each location until a live price is found; otherwise confirms as Out of Stock.
    """
    if not oos_prod_ids:
        return
        
    remaining_oos = set(oos_prod_ids)
    fallback_locations = STORE_LOCATIONS[1:]
    logger.info(f"Grouped {len(remaining_oos)} OOS items from Banasree Block C. Initiating cross-store fallback search...")

    recovered_total = 0

    for loc in fallback_locations:
        if not remaining_oos:
            break
            
        area_name = loc["area"]
        darkstore_name = loc["darkStoreName"]
        logger.info(f"Checking {len(remaining_oos)} OOS products in '{area_name}' (Darkstore: {darkstore_name})...")
        
        # Initialize delivery slot for this store
        init_delivery_slot(loc)
        headers = get_store_headers(loc)
        
        # Phase 1: Batch-check via categories of remaining OOS products
        cat_to_pids = {}
        for pid in list(remaining_oos):
            p_cat_id = current_data[pid].get('category_id')
            if p_cat_id:
                cat_to_pids.setdefault(p_cat_id, []).append(pid)
                
        for cat_id, pids in cat_to_pids.items():
            if not any(pid in remaining_oos for pid in pids):
                continue
            cat_name = current_data[pids[0]].get('category', 'Category')
            page_idx = 1
            while True:
                api_url = f"https://www.shwapno.com/api/category/products?lang=en&id={cat_id}&pageNumber={page_idx}"
                try:
                    async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as r:
                        if r.status != 200:
                            break
                        data = await r.json()
                        products = data.get('products', [])
                        if not products:
                            break
                        for prod in products:
                            res_id = update_product_entry(current_data, prod, cat_name, cat_id, today_str, area_name)
                            if res_id and res_id in remaining_oos:
                                remaining_oos.remove(res_id)
                                recovered_total += 1
                                logger.info(f"  [+] Recovered live price in {area_name}: {current_data[res_id]['name']} -> {current_data[res_id]['current_price']} Tk")
                        if not data.get('hasNextPage'):
                            break
                        page_idx += 1
                except Exception as e:
                    logger.debug(f"Category check error ({cat_id} in {area_name}): {e}")
                    break

        # Phase 2: For items without category_id or not found in category pagination, search by SKU or name
        for pid in list(remaining_oos):
            p = current_data[pid]
            sku = p.get('sku')
            query = sku if sku else p.get('name')
            if not query:
                continue
            search_url = f"https://www.shwapno.com/api/search?q={urllib.parse.quote(str(query))}"
            try:
                async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        search_prods = data.get('products', [])
                        for item in search_prods:
                            prod = item.get('product')
                            if not prod:
                                continue
                            p_name = prod.get('name', '').strip()
                            item_pid = re.sub(r'\W+', '', p_name).lower()
                            item_sku = str(prod.get('sku', ''))
                            if (sku and item_sku == str(sku)) or item_pid == pid:
                                res_id = update_product_entry(current_data, prod, p.get('category', ''), p.get('category_id'), today_str, area_name)
                                if res_id and res_id in remaining_oos:
                                    remaining_oos.remove(res_id)
                                    recovered_total += 1
                                    logger.info(f"  [+] Recovered live price via search in {area_name}: {p_name} -> {current_data[res_id]['current_price']} Tk")
                                    break
            except Exception as e:
                logger.debug(f"Search check error ({query} in {area_name}): {e}")

    # Mark all items that STILL could not be found with a live price across ANY location as definitively Out Of Stock
    for pid in remaining_oos:
        current_data[pid]["in_stock"] = False
        current_data[pid]["is_out_of_stock"] = True
        # NOTE: Do NOT erase current_price or normalized_price so frontend cards still show last known price!

    logger.info(f"Cross-store OOS rescraping complete: {recovered_total} items recovered live across fallback stores. {len(remaining_oos)} items confirmed Out of Stock.")

async def main():
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    data = load_data()
    category_data = load_categories()
    pinned_names = load_pinned_names()
    enabled_categories = [c for c in flatten_categories(category_data) if c.get('enabled', True)]
    
    logger.info(f"Started Scraper API: {len(enabled_categories)} categories, {len(pinned_names)} pinned.")
    today_str = datetime.now(DHAKA_TZ).date().isoformat()
    init_banasree_slot()
    
    seen_today = set()

    async with aiohttp.ClientSession() as session:
        pinned_cats = [c for c in enabled_categories if c['name'] in pinned_names]
        other_cats = [c for c in enabled_categories if c['name'] not in pinned_names]
        queue = pinned_cats + other_cats
        
        # Scrape 10 categories concurrently for Banasree Block C
        sem = asyncio.Semaphore(10)
        async def scrape_with_sem(cat):
            async with sem:
                return await scrape_category_api(session, cat, data, summary, pinned_names, today_str, seen_today)
                
        tasks = [scrape_with_sem(cat) for cat in queue]
        await asyncio.gather(*tasks)
        
        # Group OOS products and rescrape them across other store locations
        oos_prod_ids = [pid for pid in data if pid not in seen_today]
        if oos_prod_ids:
            await rescrape_oos_across_stores(session, oos_prod_ids, data, today_str)
        
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
