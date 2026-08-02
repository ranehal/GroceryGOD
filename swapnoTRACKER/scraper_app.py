import json, re, os, time, urllib.request, urllib.error, gzip, ssl

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

OUT_DIR = os.path.join(os.path.dirname(__file__), 'frontend')
ROOT_DIR = os.path.dirname(__file__)

API = 'https://store-api.shwapno.com/en/api'
HEADERS = {
    "User-Agent": random.choice(USER_AGENTS),
    "Accept": "application/json",
    "client-type": "App",
    "customer": "fbbbb451-a780-4101-88e0-aad799e60f83",
    "app-secret": "Ak2T/rk/AcGPU6V7yoYGB6YQDUSg2xrYO+3u7UMY2SI=",
    "accept-encoding": "gzip",
    "device-type": "Mobile",
    "content-type": "application/json",
    "appdevicetoken": "5bf1686f-6b02-45f8-95ef-3c4ed88a0dfa",
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

MAX_WORKERS = 8
MAX_PAGES_PER_CAT = 50
seen_ids = set()
seen_lock = Lock()
all_products = []
products_lock = Lock()

def req(path):
    h = dict(HEADERS)
    url = API + path
    r = urllib.request.Request(url, headers=h, method='GET')
    try:
        with urllib.request.urlopen(r, timeout=20, context=SSL_CTX) as resp:
            raw = resp.read()
            if raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            return json.loads(raw.decode('utf-8'))
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None

def parse_unit(name, unit, uom_type, uom_options, price_value):
    t = name.lower()
    unit_lower = (unit or '').lower()

    if uom_type == 20 and uom_options:
        opt = uom_options[0]
        opt_name = opt.get('name', '').lower()
        opt_price = opt.get('price', {})
        actual_price = opt_price.get('unitPriceValue') or opt_price.get('priceValue') or price_value
        m_weight = re.search(r'(\d+(\.\d+)?)\s*(kg|gm|g)', opt_name)
        if m_weight:
            v = float(m_weight.group(1))
            unit_type = m_weight.group(3)
            if unit_type in ('gm', 'g'):
                return 'kg', actual_price / v * 1000, actual_price
            else:
                return 'kg', actual_price / v, actual_price
        if 'pc' in opt_name or 'piece' in opt_name:
            return 'piece', actual_price, actual_price
        return 'kg', actual_price, actual_price

    t_clean = re.sub(r'\(?[+\-\u00b1]\d+\s*(gm|g|kg|ml|ltr|l)?\)?', '', t)

    m = re.search(r'(\d+(\.\d+)?)\s*(kg|gm|gram|g)\b', t_clean)
    if m:
        v = float(m.group(1))
        unit_type = m.group(3)
        if unit_type in ('gm', 'gram', 'g'):
            return 'kg', price_value / v * 1000, price_value
        else:
            return 'kg', price_value / v, price_value

    m = re.search(r'(\d+(\.\d+)?)\s*(ltr|liter|l|ml)\b', t_clean)
    if m:
        v = float(m.group(1))
        if m.group(3) == 'ml':
            return 'liter', price_value / v * 1000, price_value
        else:
            return 'liter', price_value / v, price_value

    if uom_type == 10:
        return 'piece', price_value, price_value

    discrete_keywords = ['pc', 'piece', 'hali', 'dozen', 'pkt', 'pack', 'each', 'bottle', 'can', 'box']
    if any(x in t_clean for x in discrete_keywords):
        return 'piece', price_value, price_value

    if unit_lower in ('kg', 'kilogram'):
        return 'kg', price_value, price_value

    return 'piece', price_value, price_value

def scrape_category(cat_id, cat_name, parent_name):
    page = 1
    local_products = []
    today = datetime.now().strftime('%Y-%m-%d')
    while page <= MAX_PAGES_PER_CAT:
        path = f'/catalog/getcategoryproducts/{cat_id}?PageNumber={page}'
        resp = req(path)
        if resp is None:
            break
        data = resp.get('data')
        if not data:
            break
        products = data.get('products', [])
        if not products:
            break
        for p in products:
            pid = p.get('id', '')
            if not pid:
                continue
            with seen_lock:
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)

            price_obj = p.get('price', {})
            price_value = price_obj.get('priceValue', 0) or 0
            old_price_value = price_obj.get('oldPriceValue')
            if old_price_value == 0:
                old_price_value = None

            unit_str = p.get('unit', '')
            uom_type = p.get('uomType', 10)
            uom_options = p.get('uomOptions', [])

            if not unit_str and uom_type == 20 and uom_options:
                unit_str = uom_options[0].get('name', '')
            if not unit_str:
                unit_str = p.get('sku', '')

            norm_unit, norm_price, display_price = parse_unit(
                p.get('name', ''), unit_str, uom_type, uom_options, price_value
            )

            picture = p.get('picture', {})
            image_url = ''
            if picture:
                large = picture.get('largeDeviceUrl', {})
                image_url = large.get('imageUrl', '')

            discount_text = ''
            if old_price_value and old_price_value > price_value:
                pct = round((old_price_value - price_value) / old_price_value * 100)
                discount_text = f'{pct}% OFF'

            product = {
                'id': pid,
                'name': p.get('name', ''),
                'store': 'shwapno',
                'category': cat_name,
                'category_path': f'{parent_name} > {cat_name}',
                'unit': unit_str or p.get('sku', ''),
                'unit_type': norm_unit,
                'current_price': price_value,
                'normalized_price': round(norm_price, 2),
                'display_price': display_price,
                'old_price': old_price_value,
                'discount_text': discount_text,
                'image': image_url,
                'url': p.get('seName', ''),
                'rating': p.get('ratingAverage', 0),
                'total_reviews': p.get('totalReviews', 0),
                'is_best_seller': p.get('isBestSeller', False),
                'is_new': p.get('isNew', False),
                'uom_type': uom_type,
                'stock': p.get('stock', ''),
                'first_seen': today,
                'last_seen': today,
                'price_history': {today: price_value},
                'hist_count': 1
            }
            local_products.append(product)

        total_pages = data.get('totalPages', 1)
        page += 1
        if page > total_pages:
            break

    return local_products

def build_category_list():
    script_dir = os.path.dirname(__file__)
    ids_path = os.path.join(script_dir, 'category_ids.json')
    with open(ids_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    cats = []
    for r in data.get('results', []):
        leaf = r.get('leaf', {})
        cid = r.get('id')
        cname = leaf.get('title', '')
        pname = leaf.get('parent', '')
        if cid and cname:
            cats.append((cid, cname, pname))
    return cats

def generate_manifest(products):
    parent_sub_map = {}
    for p in products:
        path = p.get('category_path', '')
        if ' > ' in path:
            parts = path.split(' > ')
            parent = parts[0].strip() if parts[0].strip() else (parts[1].strip() if len(parts) > 1 else 'Other')
            child = parts[1].strip() if len(parts) > 1 else p.get('category', 'Other')
        else:
            parent = p.get('category', 'Other')
            child = p.get('category', 'Other')

        if parent not in parent_sub_map:
            parent_sub_map[parent] = set()
        parent_sub_map[parent].add(child)

    tree = []
    for parent, subs in sorted(parent_sub_map.items()):
        sub_list = [{'name': s, 'seName': s.lower().replace(' ', '-')} for s in sorted(subs)]
        tree.append({
            'name': parent,
            'subCategories': sub_list
        })

    manifest = {
        'store': 'Shwapno',
        'app_id': 'com.shwapno',
        'api_base': 'https://store-api.shwapno.com/en/api',
        'headers': {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'application/json',
            'client-type': 'App',
            'customer': 'fbbbb451-a780-4101-88e0-aad799e60f83',
            'app-secret': 'Ak2T/rk/AcGPU6V7yoYGB6YQDUSg2xrYO+3u7UMY2SI='
        },
        'pagination': {'PageNumber': '{n}', 'PageSize': 50},
        'category_tree': tree,
        'total_categories': len(tree),
        'total_products': len(products),
        'captured_at': datetime.now().isoformat()
    }
    return manifest

def merge_historical_data(new_products):
    today = datetime.now().strftime('%Y-%m-%d')
    json_path = os.path.join(OUT_DIR, 'shwapno_products.json')

    existing_products = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                old_list = json.load(f)
                for item in old_list:
                    if isinstance(item, dict) and 'id' in item:
                        existing_products[item['id']] = item
        except Exception as e:
            print(f'Warning: could not read existing dataset for historical merge: {e}')

    merged = []
    scraped_ids = set()

    for p in new_products:
        pid = p['id']
        scraped_ids.add(pid)
        curr_price = p['current_price']

        if pid in existing_products:
            old_item = existing_products[pid]
            price_hist = old_item.get('price_history') or {}
            if not isinstance(price_hist, dict):
                price_hist = {}

            # Append/update today's price point
            price_hist[today] = curr_price

            first_seen = old_item.get('first_seen') or today

            old_item.update(p)
            old_item['first_seen'] = first_seen
            old_item['last_seen'] = today
            old_item['price_history'] = price_hist
            old_item['hist_count'] = len(price_hist)
            merged.append(old_item)
        else:
            p['first_seen'] = today
            p['last_seen'] = today
            p['price_history'] = {today: curr_price}
            p['hist_count'] = 1
            merged.append(p)

    # Retain items seen previously that weren't in today's scrape
    for pid, old_item in existing_products.items():
        if pid not in scraped_ids:
            price_hist = old_item.get('price_history') or {}
            old_item['hist_count'] = len(price_hist)
            merged.append(old_item)

    # Save daily snapshot to history directory
    hist_dir = os.path.join(OUT_DIR, 'history')
    os.makedirs(hist_dir, exist_ok=True)
    snapshot_path = os.path.join(hist_dir, f'shwapno_products_{today}.json')
    with open(snapshot_path, 'w', encoding='utf-8') as f:
        json.dump(new_products, f, indent=2, ensure_ascii=False)
    print(f'Saved daily snapshot: {snapshot_path}')

    return merged

def main():
    start = time.time()
    cat_list = build_category_list()
    print(f'Scraping {len(cat_list)} subcategories with {MAX_WORKERS} workers...')

    futures = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for cid, cname, pname in cat_list:
            f = ex.submit(scrape_category, cid, cname, pname)
            futures[f] = (cname, pname)

        for f in as_completed(futures):
            cname, pname = futures[f]
            try:
                result = f.result()
                with products_lock:
                    all_products.extend(result)
                print(f'  {pname} > {cname}: {len(result)} products')
            except Exception as e:
                print(f'  {pname} > {cname}: ERROR - {e}')

    elapsed = time.time() - start
    print(f'\nScraped {len(all_products)} unique products in {elapsed:.1f}s')

    os.makedirs(OUT_DIR, exist_ok=True)

    # Merge daily scraped products with accumulated historical data
    final_products = merge_historical_data(all_products)

    # Save shwapno_data.js
    data_js_path = os.path.join(OUT_DIR, 'shwapno_data.js')
    with open(data_js_path, 'w', encoding='utf-8') as f:
        f.write('window.shwapno_data = ')
        json.dump(final_products, f, indent=2, ensure_ascii=False)
        f.write(';\n')
    print(f'Saved: {data_js_path}')

    # Save shwapno_products.json
    data_json_path = os.path.join(OUT_DIR, 'shwapno_products.json')
    with open(data_json_path, 'w', encoding='utf-8') as f:
        json.dump(final_products, f, indent=2, ensure_ascii=False)
    print(f'Saved master products dataset ({len(final_products)} total products): {data_json_path}')

    # Save shwapno_manifest.js
    manifest = generate_manifest(final_products)
    js_manifest = 'window.shwapno_manifest = ' + json.dumps(manifest, indent=2, ensure_ascii=False) + ';\n'
    with open(os.path.join(OUT_DIR, 'shwapno_manifest.js'), 'w', encoding='utf-8') as f:
        f.write(js_manifest)
    with open(os.path.join(ROOT_DIR, 'shwapno_manifest.js'), 'w', encoding='utf-8') as f:
        f.write(js_manifest)
    print(f'Saved: shwapno_manifest.js')

if __name__ == '__main__':
    main()
