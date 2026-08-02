import json, gzip, base64, re, os, sys, ssl
from datetime import datetime

HAR_FILE = os.path.join(os.path.dirname(__file__), 'sopno dsu-a.shalltry.com_2026_07_30_04_21_11.har')
OUT_DIR = os.path.join(os.path.dirname(__file__), 'frontend')

def decode_entry(entry):
    content = entry.get('response', {}).get('content', {})
    text = content.get('text', '')
    mime = content.get('mimeType', '')
    if not text or 'json' not in mime:
        return None
    raw = text.encode('utf-8', errors='replace')
    for attempt in [
        lambda: json.loads(raw.decode('utf-8')),
        lambda: json.loads(gzip.decompress(raw).decode('utf-8')),
        lambda: json.loads(gzip.decompress(base64.b64decode(text)).decode('utf-8')),
    ]:
        try:
            return attempt()
        except Exception:
            pass
    return None

def parse_unit(name, unit, uom_type, uom_options, price_value):
    t = (name or '').lower()
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

def build_manifest(products):
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
            'User-Agent': 'shwapno.flutter.android',
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

def merge_historical_data(new_products, harvest_date):
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

            price_hist[harvest_date] = curr_price

            first_seen = old_item.get('first_seen') or harvest_date

            old_item.update(p)
            old_item['first_seen'] = first_seen
            old_item['last_seen'] = harvest_date
            old_item['price_history'] = price_hist
            old_item['hist_count'] = len(price_hist)
            merged.append(old_item)
        else:
            p['first_seen'] = harvest_date
            p['last_seen'] = harvest_date
            p['price_history'] = {harvest_date: curr_price}
            p['hist_count'] = 1
            merged.append(p)

    for pid, old_item in existing_products.items():
        if pid not in scraped_ids:
            price_hist = old_item.get('price_history') or {}
            old_item['hist_count'] = len(price_hist)
            merged.append(old_item)

    hist_dir = os.path.join(OUT_DIR, 'history')
    os.makedirs(hist_dir, exist_ok=True)
    snapshot_path = os.path.join(hist_dir, f'shwapno_products_{harvest_date}.json')
    with open(snapshot_path, 'w', encoding='utf-8') as f:
        json.dump(new_products, f, indent=2, ensure_ascii=False)
    print(f'Saved daily snapshot: {snapshot_path}')

    return merged

def main():
    print('=== HAR OFFLINE EXTRACTOR ===')
    if not os.path.exists(HAR_FILE):
        print(f'ERROR: HAR file not found at {HAR_FILE}')
        sys.exit(1)

    with open(HAR_FILE, 'r', encoding='utf-8', errors='replace') as f:
        har = json.load(f)

    entries = har.get('log', {}).get('entries', [])
    print(f'Read {len(entries)} entries from HAR file.')

    seen_ids = set()
    extracted_products = []
    harvest_date = '2026-07-30'

    for entry in entries:
        req_url = entry.get('request', {}).get('url', '')
        resp_body = decode_entry(entry)
        if not resp_body or not isinstance(resp_body, dict):
            continue

        data = resp_body.get('data')
        if not data:
            continue

        products_raw = []
        cat_name = 'General'
        parent_name = 'Store'

        if isinstance(data, dict):
            if 'products' in data:
                products_raw = data.get('products', [])
                cat_info = data.get('category', {})
                if isinstance(cat_info, dict):
                    cat_name = cat_info.get('name', cat_name)
                    parent_name = cat_info.get('parentCategoryName', parent_name)

        for p in products_raw:
            pid = p.get('id')
            if not pid or pid in seen_ids:
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

            p_cat = p.get('categoryName') or cat_name
            p_parent = p.get('parentCategoryName') or parent_name

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
                'category': p_cat,
                'category_path': f'{p_parent} > {p_cat}',
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
                'first_seen': harvest_date,
                'last_seen': harvest_date,
                'price_history': {harvest_date: price_value},
                'hist_count': 1
            }
            extracted_products.append(product)

    print(f'Extracted {len(extracted_products)} unique products from HAR capture.')

    if extracted_products:
        final_products = merge_historical_data(extracted_products, harvest_date)
        manifest = build_manifest(final_products)
        os.makedirs(OUT_DIR, exist_ok=True)

        js_manifest = 'window.shwapno_manifest = ' + json.dumps(manifest, indent=2, ensure_ascii=False) + ';\n'
        with open(os.path.join(OUT_DIR, 'shwapno_manifest.js'), 'w', encoding='utf-8') as f:
            f.write(js_manifest)
        with open(os.path.join(os.path.dirname(__file__), 'shwapno_manifest.js'), 'w', encoding='utf-8') as f:
            f.write(js_manifest)

        with open(os.path.join(OUT_DIR, 'shwapno_products.json'), 'w', encoding='utf-8') as f:
            json.dump(final_products, f, indent=2, ensure_ascii=False)

        js_data = 'window.shwapno_data = ' + json.dumps(final_products, indent=2, ensure_ascii=False) + ';\n'
        with open(os.path.join(OUT_DIR, 'shwapno_data.js'), 'w', encoding='utf-8') as f:
            f.write(js_data)

        print('Offline HAR extraction complete! Frontend files saved successfully.')
    else:
        print('No product data found in HAR.')

if __name__ == '__main__':
    main()
