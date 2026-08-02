"""Convert JS data files to Parquet. Generates free (3-day) + premium (full) datasets."""
import json, os, re, glob
from datetime import datetime, timedelta, timezone
import pyarrow as pa
import pyarrow.parquet as pq

STORES = ['shwapno','chaldal','meenabazar','othoba','metromart','unimart','shotejbazar','foodi']
BASE = os.path.dirname(os.path.abspath(__file__))
DHAKA_TZ = timezone(timedelta(hours=6))
FREE_HISTORY_DAYS = 3

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
            seen = set()
            for h in p.get('history', []):
                d = h['date'][:10]
                if d not in seen:
                    seen.add(d)
                    history_rows.append({
                        'product_id': pid, 'date': d,
                        'price': h['price'], 'normalized_price': h['normalized_price']
                    })
        print(f"  {os.path.basename(f)}: {len(data)} products")

print(f"\nTotal scraped: {len(product_rows)} products, {len(history_rows)} history rows")

premium_key = os.environ.get('GOD_PREMIUM_KEY', 'assalamualaikum').strip()
archive_path = os.path.join(BASE, 'premium', 'history_archive.parquet.enc')

if os.path.exists(archive_path) and premium_key:
    try:
        import hashlib
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        with open(archive_path, 'rb') as f:
            enc_data = f.read()
        if enc_data[:4] == b'GGE1':
            salt, iv, ct = enc_data[4:20], enc_data[20:32], enc_data[32:]
            kdf = hashlib.pbkdf2_hmac('sha256', premium_key.encode('utf-8'), salt, 250000, dklen=32)
            aesgcm = AESGCM(kdf)
            plaintext = aesgcm.decrypt(iv, ct, None)
            reader = pa.BufferReader(plaintext)
            old_table = pq.read_table(reader)
            old_rows = old_table.to_pylist()
            
            seen = set((r['product_id'], r['date']) for r in history_rows)
            for r in old_rows:
                if (r['product_id'], r['date']) not in seen:
                    history_rows.append(r)
                    seen.add((r['product_id'], r['date']))
            print(f"Merged {len(old_rows)} old rows from archive. New history total: {len(history_rows)}")
    except Exception as e:
        print(f"Error loading history archive: {e}")


schema = pa.schema([
    ('product_id', pa.string()),
    ('date', pa.string()),
    ('price', pa.float64()),
    ('normalized_price', pa.float64()),
])

# --- Full datasets ---
hist_table = pa.Table.from_pylist(history_rows, schema=schema)
prod_table = pa.Table.from_pylist(product_rows)

pq.write_table(prod_table, os.path.join(BASE, 'products.parquet'), compression='zstd')
pq.write_table(hist_table, os.path.join(BASE, 'history.parquet'), compression='zstd')

# --- Free tier: all products + last 3 days of history ---
cutoff = (datetime.now(DHAKA_TZ) - timedelta(days=FREE_HISTORY_DAYS)).strftime('%Y-%m-%d')
free_hist_rows = [r for r in history_rows if r['date'] >= cutoff]

free_hist_table = pa.Table.from_pylist(free_hist_rows, schema=schema)
pq.write_table(free_hist_table, os.path.join(BASE, 'history_free.parquet'), compression='zstd')
pq.write_table(prod_table, os.path.join(BASE, 'products_free.parquet'), compression='zstd')

print(f"Free tier: {len(free_hist_rows)} history rows (cutoff={cutoff})")

# --- Premium archive: older history, encrypted with GGE1 ---
old_hist_rows = [r for r in history_rows if r['date'] < cutoff]

premium_key = os.environ.get('GOD_PREMIUM_KEY', 'assalamualaikum').strip()

if old_hist_rows and premium_key:
    import hashlib, secrets
    old_hist_table = pa.Table.from_pylist(old_hist_rows, schema=schema)
    buf = pa.BufferOutputStream()
    pq.write_table(old_hist_table, buf, compression='zstd')
    plaintext = buf.getvalue().to_pybytes()

    salt = secrets.token_bytes(16)
    iv = secrets.token_bytes(12)
    kdf = hashlib.pbkdf2_hmac('sha256', premium_key.encode('utf-8'), salt, 250000, dklen=32)

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(kdf)
    ciphertext = aesgcm.encrypt(iv, plaintext, None)

    enc_data = b'GGE1' + salt + iv + ciphertext
    premium_dir = os.path.join(BASE, 'premium')
    os.makedirs(premium_dir, exist_ok=True)
    with open(os.path.join(premium_dir, 'history_archive.parquet.enc'), 'wb') as ef:
        ef.write(enc_data)
    print(f"Premium archive: {len(old_hist_rows)} rows encrypted ({len(enc_data)/1024/1024:.1f} MB)")
elif old_hist_rows:
    print(f"WARNING: {len(old_hist_rows)} premium rows but no GOD_PREMIUM_KEY — skipping encryption")
else:
    print("No premium rows to encrypt (all data within free window)")

p_size = os.path.getsize(os.path.join(BASE, 'products.parquet'))
h_size = os.path.getsize(os.path.join(BASE, 'history.parquet'))
hf_size = os.path.getsize(os.path.join(BASE, 'history_free.parquet'))
pf_size = os.path.getsize(os.path.join(BASE, 'products_free.parquet'))
print(f"\nproducts.parquet:      {p_size/1024/1024:.1f} MB")
print(f"history.parquet:       {h_size/1024/1024:.1f} MB")
print(f"products_free.parquet: {pf_size/1024/1024:.1f} MB")
print(f"history_free.parquet:  {hf_size/1024/1024:.1f} MB")
print(f"Total: {(p_size+h_size+pf_size+hf_size)/1024/1024:.1f} MB")
