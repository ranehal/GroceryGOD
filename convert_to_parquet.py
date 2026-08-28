"""Convert JS data files to Parquet. Generates free (full-history) + premium (full) datasets."""
import json, os, re, glob, time
from datetime import datetime, timedelta, timezone
import pyarrow as pa
import pyarrow.parquet as pq
import duckdb

STORES = ['shwapno','chaldal','meenabazar','othoba','metromart','unimart','shotejbazar','foodi']
BASE = os.path.dirname(os.path.abspath(__file__))
DHAKA_TZ = timezone(timedelta(hours=6))
FREE_HISTORY_DAYS = 365

t0 = time.time()
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
            img_val = p.get('image', '')
            if isinstance(img_val, dict): img_val = img_val.get('url', '') or img_val.get('src', '')
            url_val = p.get('url', '')
            if isinstance(url_val, dict): url_val = url_val.get('href', '') or url_val.get('url', '')

            history = p.get('history', [])
            valid_dates = [str(h['date'])[:10] for h in history if h.get('date') and str(h['date']).startswith('2026-')]
            
            first_seen = min(valid_dates) if valid_dates else str(p.get('first_seen', '') or '')
            last_seen = max(valid_dates) if valid_dates else str(p.get('last_seen', '') or '')
            if not first_seen and last_seen: first_seen = last_seen
            if not last_seen and first_seen: last_seen = first_seen

            curr_p = float(p.get('current_price', 0) or 0)
            norm_p = float(p.get('normalized_price', 0) or 0)
            
            in_stock = bool(curr_p > 0 and p.get('in_stock', True) is not False)
            is_out_of_stock = bool(not in_stock)

            product_rows.append({
                'id': str(p.get('id', '') or ''),
                'name': str(p.get('name', '') or ''),
                'store': str(p.get('store', '') or ''),
                'category': str(p.get('category', '') or ''),
                'unit': str(p.get('unit', '') or ''),
                'unit_type': str(p.get('unit_type', '') or ''),
                'current_price': curr_p,
                'normalized_price': norm_p,
                'image': str(img_val or ''),
                'url': str(url_val or ''),
                'first_seen': str(first_seen or ''),
                'last_seen': str(last_seen or ''),
                'in_stock': in_stock,
                'is_out_of_stock': is_out_of_stock,
            })
            seen = set()
            for h in history:
                d = str(h['date'])[:10]
                if d not in seen and d.startswith('2026-'):
                    seen.add(d)
                    h_price = float(h.get('price', 0) or 0)
                    h_norm = float(h.get('normalized_price', h_price) or h_price)
                    if h_price <= 0 or h.get('is_out_of_stock') is True:
                        h_price = -1.0
                        h_norm = -1.0
                    history_rows.append({
                        'product_id': pid, 'date': d,
                        'price': h_price,
                        'normalized_price': h_norm
                    })
        print(f"  {os.path.basename(f)}: {len(data)} products")

print(f"Total scraped: {len(product_rows)} products, {len(history_rows)} new history rows in {time.time()-t0:.2f}s")

con = duckdb.connect()

schema = pa.schema([
    ('product_id', pa.string()),
    ('date', pa.string()),
    ('price', pa.float64()),
    ('normalized_price', pa.float64()),
])

new_hist_table = pa.Table.from_pylist(history_rows, schema=schema)
con.register('new_hist', new_hist_table)

sources = ['SELECT product_id, date, price, normalized_price FROM new_hist']

premium_key = os.environ.get('GOD_PREMIUM_KEY', 'assalamualaikum').strip()
archive_path = os.path.join(BASE, 'premium', 'history_archive.parquet.enc')
arch_plain = os.path.join(BASE, 'premium', 'history_archive.parquet')

if os.path.exists(archive_path) and premium_key and not os.path.exists(arch_plain):
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
            with open(arch_plain, 'wb') as f:
                f.write(plaintext)
    except Exception as e:
        print(f"Error decrypting archive: {e}")

if os.path.exists(arch_plain):
    con.execute(f"CREATE VIEW arch_view AS SELECT product_id, date, price, normalized_price FROM read_parquet('{arch_plain.replace(chr(92), "/")}');")
    sources.append("SELECT product_id, date, price, normalized_price FROM arch_view")

unenc_hist = os.path.join(BASE, 'history.parquet')
if os.path.exists(unenc_hist):
    con.execute(f"CREATE VIEW unenc_view AS SELECT product_id, date, price, normalized_price FROM read_parquet('{unenc_hist.replace(chr(92), "/")}');")
    sources.append("SELECT product_id, date, price, normalized_price FROM unenc_view")

union_sql = " UNION ALL ".join(sources)
merge_sql = f"""
    CREATE TABLE full_history AS
    SELECT DISTINCT product_id, date, price, normalized_price
    FROM ({union_sql})
    WHERE date IS NOT NULL AND date LIKE '2026-%';
"""
con.execute(merge_sql)
total_hist_count = con.execute("SELECT COUNT(*) FROM full_history;").fetchone()[0]
print(f"Merged full history total: {total_hist_count:,} rows in {time.time()-t0:.2f}s")

# Write history.parquet
con.execute(f"COPY full_history TO '{os.path.join(BASE, 'history.parquet').replace(chr(92), "/")}' (FORMAT PARQUET, COMPRESSION 'ZSTD');")

# Free tier cutoff (full 365 days / all 2026 data back to Feb 15)
cutoff = (datetime.now(DHAKA_TZ) - timedelta(days=FREE_HISTORY_DAYS)).strftime('%Y-%m-%d')
con.execute(f"""
    COPY (SELECT * FROM full_history WHERE date >= '{cutoff}') 
    TO '{os.path.join(BASE, 'history_free.parquet').replace(chr(92), "/")}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
""")
free_count = con.execute(f"SELECT COUNT(*) FROM full_history WHERE date >= '{cutoff}';").fetchone()[0]
print(f"Free tier written: {free_count:,} rows (cutoff={cutoff})")

# Products table
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
    ('last_seen', pa.string()),
    ('in_stock', pa.bool_()),
    ('is_out_of_stock', pa.bool_()),
])
new_prod_table = pa.Table.from_pylist(product_rows, schema=prod_schema)
con.register('new_prods', new_prod_table)

prod_sql = """
    CREATE TABLE merged_products AS 
    SELECT 
        p.*,
        COALESCE(h.hist_count, 0)::INTEGER as hist_count,
        COALESCE(h.min_price, p.normalized_price)::DOUBLE as min_price,
        COALESCE(h.max_price, p.normalized_price)::DOUBLE as max_price,
        COALESCE(h.avg_price, p.normalized_price)::DOUBLE as avg_price
    FROM new_prods p
    LEFT JOIN (
        SELECT 
            product_id,
            COUNT(*)::INTEGER as hist_count,
            MIN(CASE WHEN price > 0 THEN normalized_price END) as min_price,
            MAX(CASE WHEN price > 0 THEN normalized_price END) as max_price,
            AVG(CASE WHEN price > 0 THEN normalized_price END) as avg_price
        FROM full_history
        GROUP BY product_id
    ) h ON p.id = h.product_id;
"""
con.execute(prod_sql)
prod_count = con.execute("SELECT COUNT(*) FROM merged_products;").fetchone()[0]
print(f"Merged products total: {prod_count:,} products (enriched with 6-month min/max/avg stats)")

con.execute(f"COPY merged_products TO '{os.path.join(BASE, 'products.parquet').replace(chr(92), '/')}' (FORMAT PARQUET, COMPRESSION 'ZSTD');")
con.execute(f"COPY merged_products TO '{os.path.join(BASE, 'products_free.parquet').replace(chr(92), '/')}' (FORMAT PARQUET, COMPRESSION 'ZSTD');")

# Export per-store history chunks for progressive background hydration
STORE_SLUGS = ['shwapno', 'chaldal', 'meenabazar', 'othoba', 'metromart', 'unimart', 'shotejbazar', 'foodi']
print("Exporting per-store history chunks for progressive hydration...")
for s in STORE_SLUGS:
    chunk_path = os.path.join(BASE, f"history_{s}.parquet").replace(chr(92), "/")
    con.execute(f"""
        COPY (
            SELECT h.product_id, h.date, h.price, h.normalized_price
            FROM full_history h
            JOIN merged_products p ON h.product_id = p.id
            WHERE p.store = '{s}' AND h.date >= '{cutoff}'
        ) TO '{chunk_path}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
    """)
    cnt = con.execute(f"SELECT COUNT(*) FROM read_parquet('{chunk_path}');").fetchone()[0]
    sz_mb = os.path.getsize(chunk_path) / (1024 * 1024)
    print(f"  history_{s}.parquet: {cnt:,} records ({sz_mb:.1f} MB)")

# Update premium archive parquet & encrypted files
archive_dir = os.path.join(BASE, 'premium')
os.makedirs(archive_dir, exist_ok=True)
arch_target = os.path.join(archive_dir, 'history_archive.parquet')
con.execute(f"COPY full_history TO '{arch_target.replace(chr(92), "/")}' (FORMAT PARQUET, COMPRESSION 'ZSTD');")

if premium_key:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import hashlib, secrets
    for p_name in ['products.parquet', 'history.parquet']:
        p_file = os.path.join(BASE, p_name)
        with open(p_file, 'rb') as f:
            pt = f.read()
        salt = secrets.token_bytes(16)
        iv = secrets.token_bytes(12)
        kdf = hashlib.pbkdf2_hmac('sha256', premium_key.encode('utf-8'), salt, 250000, dklen=32)
        ct = AESGCM(kdf).encrypt(iv, pt, None)
        with open(p_file + '.enc', 'wb') as ef:
            ef.write(b'GGE1' + salt + iv + ct)
        print(f"Re-encrypted {p_name}.enc")
    
    with open(arch_target, 'rb') as f:
        pt = f.read()
    salt = secrets.token_bytes(16)
    iv = secrets.token_bytes(12)
    kdf = hashlib.pbkdf2_hmac('sha256', premium_key.encode('utf-8'), salt, 250000, dklen=32)
    ct = AESGCM(kdf).encrypt(iv, pt, None)
    with open(arch_target + '.enc', 'wb') as ef:
        ef.write(b'GGE1' + salt + iv + ct)
    print(f"Re-encrypted premium/history_archive.parquet.enc")

print(f"\nAll Parquet datasets and encryptions generated successfully in {time.time()-t0:.2f}s!")
