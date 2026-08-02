import json, re, base64, sys, os
from urllib.parse import urlparse

HAR_PATH = os.path.join(os.path.dirname(__file__), 'othoba dsu-a.shalltry.com_2026_07_30_03_56_23.har')
OUT_PATH = os.path.join(os.path.dirname(__file__), 'frontend', 'othoba_products.json')

def decode(entry):
    c = entry['response']['content']
    text = c.get('text', '')
    if c.get('encoding') == 'base64':
        return base64.b64decode(text).decode('utf-8')
    return text

def main():
    if not os.path.exists(HAR_PATH):
        print(f'[ERROR] HAR not found: {HAR_PATH}')
        sys.exit(1)

    with open(HAR_PATH, 'r', encoding='utf-8') as f:
        har = json.load(f)
    entries = har['log']['entries']
    print(f'[HAR] {len(entries)} entries loaded')

    # Extract catalog root for categories
    cats = {}
    for e in entries:
        if '/Catalog/GetCatalogRoot' in e['request']['url']:
            data = json.loads(decode(e))
            def walk(nodes, parent=''):
                for n in nodes:
                    cats[str(n.get('id',''))] = {'name': n['name'], 'parent': parent}
                    if n.get('sub_categories'):
                        walk(n['sub_categories'], n['name'])
            walk(data)

    # Extract products from all category pages
    seen_ids = set()
    products = []
    for e in entries:
        url = e['request']['url']
        if not re.search(r'/Catalog/GetCategoryProducts/\d+', url): continue
        if e['response']['status'] != 200: continue
        try:
            data = json.loads(decode(e))
            cat_model = data.get('catalog_products_model') or data
            for p in cat_model.get('products', []):
                pid = p.get('id')
                if pid in seen_ids: continue
                seen_ids.add(pid)
                pp = p.get('product_price', {})
                img = p.get('default_picture_model', {})
                cat_id = str(p.get('category_id', ''))
                cat_name = cats.get(cat_id, {}).get('name', p.get('category_name', ''))
                price = pp.get('price_value') or pp.get('price', 0) or 0
                products.append({
                    'id': f'ot_{pid}', 'name': p.get('name', ''),
                    'store': 'othoba',
                    'sku': p.get('sku', ''),
                    'current_price': price,
                    'normalized_price': price,
                    'old_price': pp.get('old_price_value'),
                    'discount_text': pp.get('discount_display_text', ''),
                    'image': img.get('image_url', ''),
                    'category': cat_name,
                    'unit_type': 'piece',
                    'sold': p.get('product_total_sold_quantity_model', {}).get('TotalQuantity', 0),
                    'in_stock': not p.get('sold_out', False),
                    'rating': p.get('review_overview_model', {}).get('rating_value'),
                    'reviews': p.get('review_overview_model', {}).get('total_reviews', 0),
                })
        except Exception as ex:
            print(f'  [SKIP] {url.split("/")[-1]}: {ex}')

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(products, f, indent=2)

    print(f'[DONE] {len(products)} products extracted to frontend/othoba_products.json')
    print(f'[STATS] Categories: {len(cats)}, Products with discount: {sum(1 for p in products if p["old_price"])}')
    prices = [p['current_price'] for p in products if p['current_price']]
    if prices: print(f'[STATS] Price range: {min(prices)}-{max(prices)} Tk')

if __name__ == '__main__':
    main()
