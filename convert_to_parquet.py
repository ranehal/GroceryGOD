"""Convert JS data files to Parquet. Products + history in one file."""
import json, os, re, glob
import pyarrow as pa
import pyarrow.parquet as pq

STORES = ['shwapno','chaldal','meenabazar','othoba','metromart','unimart','shotejbazar']
BASE = os.path.dirname(os.path.abspath(__file__))

product_rows = []
history_rows = []

for store in STORES:
    for f in sorted(glob.glob(os.path.join(BASE, f'{store}_data_part*.js'))):
        with open(f, 'r', encoding='utf-8') as fh:
            content = fh.read()
        match = re.search(r'=\s*(\{.*\})\s*;?\s*$', content, re.DOTALL)
        if not match:
            continue
        data = json.loads(match.group(1))
        for pid, p in data.items():
            product_rows.append({
                'id': p['id'], 'name': p['name'], 'store': p['store'],
                'category': p['category'], 'unit': p.get('unit', ''),
                'unit_type': p.get('unit_type', ''), 'current_price': p.get('current_price', 0),
                'normalized_price': p.get('normalized_price', 0), 'image': p.get('image', ''),
                'url': p.get('url', ''), 'first_seen': p.get('first_seen', '')
            })
            for h in p.get('history', []):
                history_rows.append({
                    'product_id': pid, 'date': h['date'],
                    'price': h['price'], 'normalized_price': h['normalized_price']
                })
        print(f"  {os.path.basename(f)}: {len(data)} products")

print(f"\nTotal: {len(product_rows)} products, {len(history_rows)} history rows")

prod_table = pa.Table.from_pylist(product_rows)
hist_table = pa.Table.from_pylist(history_rows)

pq.write_table(prod_table, os.path.join(BASE, 'products.parquet'), compression='zstd')
pq.write_table(hist_table, os.path.join(BASE, 'history.parquet'), compression='zstd')

p_size = os.path.getsize(os.path.join(BASE, 'products.parquet'))
h_size = os.path.getsize(os.path.join(BASE, 'history.parquet'))
print(f"products.parquet: {p_size/1024/1024:.1f} MB")
print(f"history.parquet:  {h_size/1024/1024:.1f} MB")
print(f"Total: {(p_size+h_size)/1024/1024:.1f} MB")
