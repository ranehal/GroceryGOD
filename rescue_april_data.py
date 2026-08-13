"""
Rescue April 2026 price history from readable git commits (non-LFS).
Also captures what May data is readable (shwapno via swapnoTRACKER, chaldal via PRICETRACKER).

Sources:
  - 6a4c67d5 (2026-04-29): chaldal_data.js, meenabazar_data.js, shwapno_data.js
  - 5b7a23e6 (2026-04-28): othoba_data.js
  - 810aaec8 (2026-05-31): swapnoTRACKER/data.json  (shwapno, Feb 16 - May 31)
  - 0a1992f0 (2026-05-21): PRICETRACKER/data.js     (chaldal, May 18-21)
"""
import subprocess, json, re, os, io, hashlib
import pyarrow as pa
import pyarrow.parquet as pq
from collections import defaultdict

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None

BASE = os.path.dirname(os.path.abspath(__file__))
PREMIUM_KEY = os.environ.get('GOD_PREMIUM_KEY', 'assalamualaikum').strip()

def load_base_history():
    """Load the current full history: prefer plaintext history.parquet, else decrypt history.parquet.enc."""
    plain = os.path.join(BASE, 'history.parquet')
    if os.path.exists(plain):
        return pq.read_table(plain).to_pylist()
    enc_path = os.path.join(BASE, 'history.parquet.enc')
    if os.path.exists(enc_path) and AESGCM:
        with open(enc_path, 'rb') as f:
            enc = f.read()
        if enc[:4] == b'GGE1':
            salt, iv, ct = enc[4:20], enc[20:32], enc[32:]
            kdf = hashlib.pbkdf2_hmac('sha256', PREMIUM_KEY.encode('utf-8'), salt, 250000, dklen=32)
            pt = AESGCM(kdf).decrypt(iv, ct, None)
            return pq.read_table(io.BytesIO(pt)).to_pylist()
    return []

def load(sha, path, is_json=False):
    p = subprocess.run(['git', 'show', f'{sha}:{path}'], capture_output=True)
    if p.returncode != 0:
        return None
    raw = p.stdout.decode('utf-8', errors='ignore')
    if raw.startswith('version https://git-lfs'):
        return None
    if is_json:
        return json.loads(raw)
    m = re.search(r'=\s*(\{.*\})\s*;?\s*$', raw, re.S)
    if not m:
        return None
    return json.loads(m.group(1))

def extract(obj, prefix):
    """Extract (product_id, date, price, normalized_price) rows."""
    if 'products' in obj and isinstance(obj.get('products'), dict):
        prods = obj['products']
    elif isinstance(obj, dict):
        prods = obj
    else:
        return []
    out = []
    for pid, pd in prods.items():
        if not isinstance(pd, dict):
            continue
        hist = pd.get('history', [])
        if not hist:
            continue
        full_pid = prefix + pid if not pid.startswith(prefix) else pid
        for h in hist:
            d = str(h.get('date', ''))[:10]
            if not d or not d.startswith('2026'):
                continue
            price = float(h.get('price', 0) or 0)
            norm = float(h.get('normalized_price', price) or price)
            out.append((full_pid, d, price, norm))
    return out

SOURCES = [
    ('6a4c67d5', 'chaldal_data.js', 'ch_', False),
    ('6a4c67d5', 'meenabazar_data.js', 'mb_', False),
    ('5b7a23e6', 'othoba_data.js', 'ot_', False),
    ('6a4c67d5', 'shwapno_data.js', 'sh_', False),
    ('810aaec8', 'swapnoTRACKER/data.json', 'sh_', True),
    ('0a1992f0', 'PRICETRACKER/data.js', 'ch_', False),
]

print("[RESCUE] Loading existing history (plaintext or decrypted .enc)...")
existing_history = load_base_history()
print(f"[RESCUE] Existing: {len(existing_history):,} rows")

def load_products():
    """Load existing products parquet (plaintext or decrypted .enc)."""
    plain = os.path.join(BASE, 'products.parquet')
    if os.path.exists(plain):
        return pq.read_table(plain).to_pylist()
    enc_path = os.path.join(BASE, 'products.parquet.enc')
    if os.path.exists(enc_path) and AESGCM:
        with open(enc_path, 'rb') as f:
            enc = f.read()
        if enc[:4] == b'GGE1':
            salt, iv, ct = enc[4:20], enc[20:32], enc[32:]
            kdf = hashlib.pbkdf2_hmac('sha256', PREMIUM_KEY.encode('utf-8'), salt, 250000, dklen=32)
            pt = AESGCM(kdf).decrypt(iv, ct, None)
            return pq.read_table(io.BytesIO(pt)).to_pylist()
    return []

def extract_products(obj, prefix):
    """Extract product metadata rows from a data file."""
    if 'products' in obj and isinstance(obj.get('products'), dict):
        prods = obj['products']
    elif isinstance(obj, dict):
        prods = obj
    else:
        return []
    out = []
    for pid, pd in prods.items():
        if not isinstance(pd, dict):
            continue
        full_pid = prefix + pid if not pid.startswith(prefix) else pid
        hist = pd.get('history', [])
        first_seen = hist[0].get('date', '')[:10] if hist else ''
        img_val = pd.get('image', '')
        if isinstance(img_val, dict):
            img_val = img_val.get('url', '') or img_val.get('src', '')
        url_val = pd.get('url', '')
        if isinstance(url_val, dict):
            url_val = url_val.get('href', '') or url_val.get('url', '')
        out.append({
            'id': full_pid,
            'name': str(pd.get('name', '') or ''),
            'store': str(pd.get('store', '') or prefix.rstrip('_')),
            'category': str(pd.get('category', '') or ''),
            'unit': str(pd.get('unit', '') or ''),
            'unit_type': str(pd.get('unit_type', '') or ''),
            'current_price': float(pd.get('current_price', 0) or 0),
            'normalized_price': float(pd.get('normalized_price', 0) or 0),
            'image': str(img_val or ''),
            'url': str(url_val or ''),
            'first_seen': first_seen,
        })
    return out

print("[RESCUE] Loading existing products parquet...")
existing_products = load_products()
existing_prod_ids = set(r['id'] for r in existing_products)
print(f"[RESCUE] Existing products: {len(existing_products):,}")

seen = set((r['product_id'], r['date']) for r in existing_history)
rescued = 0
per_source = {}

for sha, path, prefix, is_json in SOURCES:
    obj = load(sha, path, is_json)
    if obj is None:
        print(f"  {sha[:8]} {path}: UNAVAILABLE")
        continue
    rows = extract(obj, prefix)
    added = 0
    for pid, d, price, norm in rows:
        if (pid, d) not in seen:
            seen.add((pid, d))
            existing_history.append({'product_id': pid, 'date': d, 'price': price, 'normalized_price': norm})
            rescued += 1
            added += 1
    for pr in extract_products(obj, prefix):
        if pr['id'] not in existing_prod_ids:
            existing_prod_ids.add(pr['id'])
            existing_products.append(pr)
    per_source[f'{sha[:8]}:{path}'] = (len(rows), added)
    print(f"  {sha[:8]} {path} ({prefix}): {len(rows):,} rows, +{added:,} new history")

print(f"\n[RESCUE] Total new rows: {rescued:,}")
print(f"[RESCUE] Final history total: {len(existing_history):,} rows")
print(f"[RESCUE] Final product total: {len(existing_products):,}")

# Show date gaps that now close
by_date = defaultdict(int)
for r in existing_history:
    by_date[r['date']] += 1
apr = sum(v for k, v in by_date.items() if k.startswith('2026-04'))
may = sum(v for k, v in by_date.items() if k.startswith('2026-05'))
print(f"[RESCUE] April rows: {apr:,} | May rows: {may:,}")

schema = pa.schema([
    ('product_id', pa.string()),
    ('date', pa.string()),
    ('price', pa.float64()),
    ('normalized_price', pa.float64()),
])
hist_table = pa.Table.from_pylist(existing_history, schema=schema)
pq.write_table(hist_table, os.path.join(BASE, 'history.parquet'), compression='zstd')
pq.write_table(hist_table, os.path.join(BASE, 'history_free.parquet'), compression='zstd')

# Re-encrypt history.parquet.enc to stay in sync (GGE1 format)
if AESGCM and PREMIUM_KEY:
    import secrets
    buf = pa.BufferOutputStream()
    pq.write_table(hist_table, buf, compression='zstd')
    plaintext = buf.getvalue().to_pybytes()
    salt = secrets.token_bytes(16)
    iv = secrets.token_bytes(12)
    kdf = hashlib.pbkdf2_hmac('sha256', PREMIUM_KEY.encode('utf-8'), salt, 250000, dklen=32)
    ciphertext = AESGCM(kdf).encrypt(iv, plaintext, None)
    with open(os.path.join(BASE, 'history.parquet.enc'), 'wb') as ef:
        ef.write(b'GGE1' + salt + iv + ciphertext)
    print(f"[RESCUE] Re-encrypted history.parquet.enc")

print(f"[RESCUE] Wrote history.parquet + history_free.parquet: {os.path.getsize(os.path.join(BASE, 'history.parquet'))/1024/1024:.1f} MB")

# --- Products ---
prod_schema = pa.schema([
    ('id', pa.string()),
    ('name', pa.string()),
    ('store', pa.string()),
    ('category', pa.string()),
    ('unit', pa.string()),
    ('unit_type', pa.string()),
    ('current_price', pa.float64()),
    ('normalized_price', pa.float64()),
    ('image', pa.string()),
    ('url', pa.string()),
    ('first_seen', pa.string()),
])
prod_table = pa.Table.from_pylist(existing_products, schema=prod_schema)
pq.write_table(prod_table, os.path.join(BASE, 'products.parquet'), compression='zstd')
pq.write_table(prod_table, os.path.join(BASE, 'products_free.parquet'), compression='zstd')

if AESGCM and PREMIUM_KEY:
    import secrets
    buf = pa.BufferOutputStream()
    pq.write_table(prod_table, buf, compression='zstd')
    plaintext = buf.getvalue().to_pybytes()
    salt = secrets.token_bytes(16)
    iv = secrets.token_bytes(12)
    kdf = hashlib.pbkdf2_hmac('sha256', PREMIUM_KEY.encode('utf-8'), salt, 250000, dklen=32)
    ciphertext = AESGCM(kdf).encrypt(iv, plaintext, None)
    with open(os.path.join(BASE, 'products.parquet.enc'), 'wb') as ef:
        ef.write(b'GGE1' + salt + iv + ciphertext)
    print(f"[RESCUE] Re-encrypted products.parquet.enc")

print(f"[RESCUE] Wrote products.parquet + products_free.parquet: {os.path.getsize(os.path.join(BASE, 'products.parquet'))/1024/1024:.1f} MB")
