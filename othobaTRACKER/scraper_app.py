"""Othoba API Scraper v2 — reverse-engineered from HAR capture"""
import json, re, os, sys, time, urllib.request, urllib.error, gzip, ssl

import random
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

API = 'https://app.othoba.com/api-frontend'
TOKEN = '11CZ+eanknvgRupFlOA0Eg'
HEADERS = {
    'authorization': TOKEN, 'accept': 'application/json',
    'content-type': 'application/json-patch+json', 'accept-encoding': 'gzip'
}
OUT_DIR = os.path.join(os.path.dirname(__file__), 'frontend')
MAX_PAGES = 50
PAGE_SIZE = 20
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

def parse_price(pp, key):
    v = pp.get(key)
    if not v: return None
    s = str(v).replace(',', '').strip()
    m = re.search(r'[\d.]+', s)
    return float(m.group()) if m else None

def req(path, data=None):
    h = {**HEADERS, 'user-agent': random.choice(USER_AGENTS)}
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(API + path, data=body, headers=h, method='POST' if data else 'GET')
    with urllib.request.urlopen(r, timeout=20, context=SSL_CTX) as resp:
        raw = resp.read()
        if resp.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        return json.loads(raw.decode('utf-8'))

def parse_unit(name, price):
    t = name.lower()
    t = re.sub(r'\(?[+\-\u00b1]\d+\s*(gm|g|kg|ml|ltr|l)?\)?', '', t)
    m = re.search(r'(\d+(\.\d+)?)\s*(kg|gm|gram|g)\b', t)
    if m:
        v = float(m.group(1))
        return 'kg', (price / v * 1000) if m.group(3) in ('gm','gram','g') else (price / v if v else price)
    m = re.search(r'(\d+(\.\d+)?)\s*(ltr|liter|l|ml)\b', t)
    if m:
        v = float(m.group(1))
        return 'liter', (price / v * 1000) if m.group(3) == 'ml' else (price / v if v else price)
    if any(x in t for x in ['pc','piece','hali','dozen','pkt','pack','each','bottle','can','box']):
        return 'piece', price
    return 'kg', price

def scrape_category(cat_id, cat_name, parent_name, seen_ids, lock):
    products = []; page = 1; total_pages = 1
    cat_path = f'{parent_name} > {cat_name}' if parent_name else cat_name
    while page <= total_pages:
        body = {"DiscountIds":[0],"FirstItem":0,"HasNextPage":True,"HasPreviousPage":False,
                "IsEmi":0,"IsOthobaCetified":0,"LastItem":0,"ManufacturerIds":[0],"OrderBy":0,
                "PageNumber":page,"PageSize":PAGE_SIZE,"Price":"ea e","RatingFilterIds":[0],
                "SpecificationOptionIds":[0],"TotalItems":0,"TotalPages":0,"VendorIds":[0],
                "view_mode":"exercitation sint"}
        try:
            data = req(f'/Catalog/GetCategoryProducts/{cat_id}', body)
            cm = data.get('catalog_products_model') or data
            pf = cm.get('paging_filtering_model') or cm
            total_pages = min(pf.get('total_pages', 1) or 1, MAX_PAGES)
            for p in cm.get('products', []):
                pid = p.get('id')
                with lock:
                    if pid in seen_ids: continue
                    seen_ids.add(pid)
                pp = p.get('product_price', {})
                img = p.get('default_picture_model', {})
                price = parse_price(pp, 'price') or 0
                ut, np_ = parse_unit(p.get('name',''), price)
                products.append({
                    'id': f'ot_{pid}', 'name': p.get('name',''),
                    'store': 'othoba',
                    'category': cat_name,
                    'category_path': cat_path,
                    'unit': p.get('sku',''), 'unit_type': ut,
                    'current_price': price,
                    'normalized_price': np_,
                    'image': img.get('image_url',''), 'url': '',
                    'first_seen': datetime.now().strftime('%Y-%m-%d'),
                    'old_price': parse_price(pp, 'old_price'),
                    'discount_text': pp.get('discount_display_text') or '',
                    'rating': p.get('review_overview_model',{}).get('rating_value'),
                    'sold': p.get('product_total_sold_quantity_model',{}).get('TotalQuantity',0)
                })
            page += 1
        except Exception as e:
            break
    if products:
        print(f'  [OK] {cat_path:45s} {len(products):4d} products')
        sys.stdout.flush()
    return products

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print('Othoba API Scraper v2\n')

    print('[1/3] Fetching catalog root...')
    sys.stdout.flush()
    try:
        root = req('/Catalog/GetCatalogRoot')
    except Exception as e:
        print(f'[FAIL] {e}')
        sys.exit(1)

    ALLOWED_GROCERY_KEYWORDS = ['daily bazar', 'grocery', 'food', 'bogo', 'mega discount', 'quick commerce', 'cooking', 'staple', 'bakery', 'dairy', 'egg', 'meat', 'fish', 'produce', 'vegetable', 'fruit', 'snack', 'beverage', 'tea', 'coffee', 'sweet', 'mithai', 'oil', 'rice', 'spice']
    EXCLUDED_KEYWORDS = ['mother', 'baby', 'toy', 'beauty', 'care', 'cosmetic', 'pharmacy', 'medicine', 'pet', 'fashion', 'cloth', 'shoe', 'electronics', 'automotive', 'stationery', 'book', 'furniture', 'table', 'pad', 'freezer', 'home appliance', 'garden']

    cats = []
    for top in root:
        top_name = top.get('name', '').strip()
        top_lower = top_name.lower()
        subs = top.get('sub_categories', [])
        if subs:
            for sub in subs:
                sub_name = sub.get('name', '').strip()
                sub_lower = sub_name.lower()
                # Check if sub or parent is grocery related and not in excluded non-food
                is_grocery = any(k in top_lower or k in sub_lower for k in ALLOWED_GROCERY_KEYWORDS)
                is_excluded = any(ex in sub_lower for ex in EXCLUDED_KEYWORDS)
                if is_grocery and not is_excluded:
                    sid = sub.get('id')
                    if sid:
                        cats.append({'id': sid, 'name': sub_name, 'parent': top_name})
        else:
            is_grocery = any(k in top_lower for k in ALLOWED_GROCERY_KEYWORDS)
            is_excluded = any(ex in top_lower for ex in EXCLUDED_KEYWORDS)
            if is_grocery and not is_excluded:
                tid = top.get('id')
                if tid:
                    cats.append({'id': tid, 'name': top_name, 'parent': ''})
    print(f'       {len(cats)} grocery leaf categories found\n')

    print('[2/3] Scraping products...')
    sys.stdout.flush()
    all_products = []; seen_ids = set(); lock = Lock()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(scrape_category, c['id'], c['name'], c['parent'], seen_ids, lock): c for c in cats}
        for f in as_completed(futures):
            all_products.extend(f.result())

    print(f'\n       Total unique: {len(all_products)} products\n')

    print('[3/3] Saving...')
    fpath = os.path.join(OUT_DIR, 'othoba_products.json')
    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(all_products, f, indent=2, ensure_ascii=False)
    print(f'       -> {fpath} ({len(all_products)} products)')

    dpath = os.path.join(OUT_DIR, 'othoba_data.js')
    with open(dpath, 'w', encoding='utf-8') as f:
        f.write(f'window.othoba_data = {json.dumps(all_products, ensure_ascii=False)};')
    print(f'       -> {dpath}')

    prices = [p['current_price'] for p in all_products if p['current_price']]
    discs = sum(1 for p in all_products if p.get('old_price'))
    print(f'\n       Products: {len(all_products)}  |  Discounts: {discs}')
    if prices: print(f'       Price: {min(prices):.0f} - {max(prices):.0f} Tk')

if __name__ == '__main__':
    main()
