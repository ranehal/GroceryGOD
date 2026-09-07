import sys
getattr(sys.stdout, "reconfigure", lambda **kw: None)(encoding="utf-8", errors="replace")
getattr(sys.stderr, "reconfigure", lambda **kw: None)(encoding="utf-8", errors="replace")

"""
Turso Cloud Database Synchronization Engine for GroceryGOD.
Maintains live, high-speed distributed SQLite database on Turso.
Used by Kaggle orchestrator cron and local workflows.
"""
import os, json, time, glob, urllib.request, urllib.error

# Default credentials and configuration
DEFAULT_PLATFORM_TOKEN = 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJxaGktTzZzR0VmR1dJZDRqWU9wd3BnIiwib3JnX2lkIjoxMDAwMjM4OTgwfQ.OgoJbza8T0_rKwkeJv6-1n9xIA1s-2CSTLV49GzZU9SnxYWrWRcZN5-bhgC51c4EXVC872j98c9G1jiG6YmyAg'
DEFAULT_HOSTNAME = 'grocerygod-ranehal.aws-ap-south-1.turso.io'
DEFAULT_ORG = 'ranehal'
DEFAULT_DB_NAME = 'grocerygod'
DEFAULT_RW_TOKEN = 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODg4MjA4MjgsImlkIjoiMDFhMDdlMDctOWUwMS03YzcyLTkxYjMtNTk4NWY0N2MxMDU0Iiwia2lkIjoib1I3UEVTS3NWX2l1TlNOTzhSQXJPMFA3b3dROTFHUHllbXVMYVVmZ3p2TSIsInJpZCI6IjEyM2I0NDdhLTgxZDItNDM2OC04YjllLTk0MjBkNDViMTY4YSJ9.g0mom8Va2i_D3IeyMbrvvoEsy12cJ2x5D1kmAFNga0YokOg2JzDIuyvBmZ7iIGZ3WPME5snBClS8mcDZSl9YCw'
DEFAULT_RO_TOKEN = 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicm8iLCJpYXQiOjE3ODg4MjA4MzIsImlkIjoiMDFhMDdlMDctOWUwMS03YzcyLTkxYjMtNTk4NWY0N2MxMDU0Iiwia2lkIjoib1I3UEVTS3NWX2l1TlNOTzhSQXJPMFA3b3dROTFHUHllbXVMYVVmZ3p2TSIsInJpZCI6IjEyM2I0NDdhLTgxZDItNDM2OC04YjllLTk0MjBkNDViMTY4YSJ9.gvbV00Mppp9YSM23-2isFSWsgGDhZnuMRL6xow0pUsSRiH_LWJMFpqdwAC4rPjcbPVG0u3S62V-BRjV8352FCA'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_config():
    config_file = os.path.join(BASE_DIR, 'turso_tokens.json')
    cfg = {
        'platform_token': os.environ.get('TURSO_PLATFORM_TOKEN', DEFAULT_PLATFORM_TOKEN).strip(),
        'hostname': os.environ.get('TURSO_HOSTNAME', DEFAULT_HOSTNAME).strip(),
        'org': os.environ.get('TURSO_ORG', DEFAULT_ORG).strip(),
        'db_name': os.environ.get('TURSO_DB_NAME', DEFAULT_DB_NAME).strip(),
        'rw_token': os.environ.get('TURSO_RW_TOKEN', DEFAULT_RW_TOKEN).strip(),
        'ro_token': os.environ.get('TURSO_RO_TOKEN', DEFAULT_RO_TOKEN).strip(),
    }
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                for k, v in saved.items():
                    if v and not os.environ.get(f'TURSO_{k.upper()}'):
                        cfg[k] = v
        except Exception:
            pass
    return cfg

def turso_pipeline(cfg, statements, timeout=60, retries=3):
    url = f"https://{cfg['hostname']}/v2/pipeline"
    req_body = {
        'requests': statements + [{'type': 'close'}]
    }
    data = json.dumps(req_body).encode('utf-8')
    headers = {
        'Authorization': f"Bearer {cfg['rw_token']}",
        'Content-Type': 'application/json',
        'Connection': 'close'
    }
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * attempt)
    raise last_err

def to_turso_arg(val):
    if val is None:
        return {'type': 'null'}
    if isinstance(val, bool):
        return {'type': 'integer', 'value': '1' if val else '0'}
    if isinstance(val, int):
        return {'type': 'integer', 'value': str(val)}
    if isinstance(val, float):
        return {'type': 'float', 'value': float(val)}
    return {'type': 'text', 'value': str(val)}

def execute_batch_sql(cfg, sql_stmts, batch_size=500):
    total = len(sql_stmts)
    if total == 0:
        return 0
    executed = 0
    for i in range(0, total, batch_size):
        batch = sql_stmts[i:i+batch_size]
        requests = [{'type': 'execute', 'stmt': s} for s in batch]
        res = turso_pipeline(cfg, requests, timeout=90)
        errs = [r for r in res.get('results', []) if r.get('type') == 'error']
        if errs:
            raise RuntimeError(f"Turso batch error: {errs[0]}")
        executed += len(batch)
    return executed

def build_local_optimized_db(db_path='grocerygod_optimized.db'):
    import duckdb, sqlite3
    t0 = time.time()
    if os.path.exists(db_path):
        try: os.remove(db_path)
        except Exception: pass

    con_duck = duckdb.connect()
    con_sqlite = sqlite3.connect(db_path)
    con_sqlite.execute('PRAGMA page_size = 4096;')
    con_sqlite.execute('PRAGMA journal_mode = WAL;')
    con_sqlite.execute('PRAGMA synchronous = OFF;')

    con_sqlite.execute('''
    CREATE TABLE products (
        id TEXT PRIMARY KEY,
        name TEXT,
        store TEXT,
        category TEXT,
        unit TEXT,
        unit_type TEXT,
        current_price REAL,
        normalized_price REAL,
        image TEXT,
        url TEXT,
        first_seen TEXT,
        last_seen TEXT,
        in_stock INTEGER,
        is_out_of_stock INTEGER,
        hist_count INTEGER,
        min_price REAL,
        max_price REAL,
        avg_price REAL
    );
    ''')

    prods = con_duck.execute('''
        SELECT id, name, store, category, unit, unit_type, current_price, normalized_price, 
               image, url, first_seen, last_seen, 
               CAST(in_stock AS INTEGER), CAST(is_out_of_stock AS INTEGER),
               hist_count, min_price, max_price, avg_price
        FROM read_parquet('products_free.parquet')
    ''').fetchall()
    con_sqlite.executemany('INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', prods)
    con_sqlite.commit()

    con_sqlite.execute('''
    CREATE TABLE atl_deals (
        id TEXT PRIMARY KEY,
        name TEXT,
        store TEXT,
        category TEXT,
        unit TEXT,
        unit_type TEXT,
        current_price REAL,
        normalized_price REAL,
        image TEXT,
        url TEXT,
        first_seen TEXT,
        last_seen TEXT,
        in_stock INTEGER,
        is_out_of_stock INTEGER,
        hist_count INTEGER,
        min_price REAL,
        max_price REAL,
        avg_price REAL
    );
    ''')
    atl_rows = con_duck.execute('''
        SELECT id, name, store, category, unit, unit_type, current_price, normalized_price, 
               image, url, first_seen, last_seen, 
               CAST(in_stock AS INTEGER), CAST(is_out_of_stock AS INTEGER),
               hist_count, min_price, max_price, avg_price
        FROM read_parquet('atl.parquet')
    ''').fetchall()
    con_sqlite.executemany('INSERT INTO atl_deals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', atl_rows)
    con_sqlite.commit()

    con_sqlite.execute('''
    CREATE TABLE history (
        product_id TEXT,
        date TEXT,
        price REAL,
        normalized_price REAL,
        PRIMARY KEY (product_id, date)
    ) WITHOUT ROWID;
    ''')

    reader = con_duck.execute('''
        SELECT product_id, date, price, normalized_price
        FROM read_parquet('history_free.parquet')
    ''')
    while True:
        batch = reader.fetchmany(500000)
        if not batch: break
        con_sqlite.executemany('INSERT OR REPLACE INTO history VALUES (?,?,?,?)', batch)
        con_sqlite.commit()

    con_sqlite.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);')
    meta_manifests = {}
    for mf in glob.glob(os.path.join(BASE_DIR, '*_manifest.js')):
        s = os.path.basename(mf).replace('_manifest.js', '')
        try:
            with open(mf, 'r', encoding='utf-8') as f:
                c = f.read()
            m = c[c.find('{'):c.rfind('}')+1]
            meta_manifests[s] = json.loads(m).get('metadata', {})
        except Exception:
            pass
    con_sqlite.execute('INSERT INTO metadata VALUES (?, ?)', ('stores', json.dumps(meta_manifests)))
    con_sqlite.execute('INSERT INTO metadata VALUES (?, ?)', ('last_update', time.strftime('%Y-%m-%d %H:%M:%S')))
    con_sqlite.commit()

    con_sqlite.execute('CREATE INDEX idx_products_store ON products(store);')
    con_sqlite.execute('CREATE INDEX idx_products_cat ON products(category);')
    con_sqlite.execute('CREATE INDEX idx_products_instock ON products(in_stock);')
    con_sqlite.execute('CREATE INDEX idx_products_price ON products(normalized_price);')
    con_sqlite.execute('CREATE INDEX idx_atl_store ON atl_deals(store);')
    con_sqlite.commit()

    con_sqlite.execute('PRAGMA wal_checkpoint(TRUNCATE);')
    con_sqlite.close()
    return os.path.getsize(db_path)

def full_reseed_turso(cfg):
    """Rebuilds and uploads the complete database file to Turso via binary upload."""
    import subprocess
    print("[TURSO] Building optimized local SQLite database...")
    db_file = os.path.join(BASE_DIR, 'grocerygod_optimized.db')
    sz = build_local_optimized_db(db_file)
    print(f"[TURSO] Local SQLite database built: {sz / (1024*1024):.1f} MB")

    p_token = cfg['platform_token']
    org = cfg['org']
    db_name = cfg['db_name']

    # Delete existing database
    print(f"[TURSO] Recreating database {db_name} with seed type database_upload...")
    try:
        del_req = urllib.request.Request(
            f"https://api.turso.tech/v1/organizations/{org}/databases/{db_name}",
            headers={'Authorization': f"Bearer {p_token}"},
            method='DELETE'
        )
        with urllib.request.urlopen(del_req) as resp:
            pass
    except Exception as e:
        print(f"[TURSO] Notice deleting DB: {e}")

    # Create DB with database_upload seed
    create_payload = json.dumps({'name': db_name, 'group': 'default', 'seed': {'type': 'database_upload'}}).encode('utf-8')
    create_req = urllib.request.Request(
        f"https://api.turso.tech/v1/organizations/{org}/databases",
        data=create_payload,
        headers={'Authorization': f"Bearer {p_token}", 'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(create_req) as resp:
        db_info = json.loads(resp.read().decode('utf-8'))
        cfg['hostname'] = db_info['database']['Hostname']

    # Generate RW and RO tokens
    tok_req = urllib.request.Request(
        f"https://api.turso.tech/v1/organizations/{org}/databases/{db_name}/auth/tokens",
        headers={'Authorization': f"Bearer {p_token}"},
        method='POST'
    )
    with urllib.request.urlopen(tok_req) as resp:
        cfg['rw_token'] = json.loads(resp.read().decode('utf-8'))['jwt']

    ro_tok_req = urllib.request.Request(
        f"https://api.turso.tech/v1/organizations/{org}/databases/{db_name}/auth/tokens?authorization=read-only",
        headers={'Authorization': f"Bearer {p_token}"},
        method='POST'
    )
    with urllib.request.urlopen(ro_tok_req) as resp:
        cfg['ro_token'] = json.loads(resp.read().decode('utf-8'))['jwt']

    with open(os.path.join(BASE_DIR, 'turso_tokens.json'), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)

    with open(os.path.join(BASE_DIR, 'turso_manifest.js'), 'w', encoding='utf-8') as f:
        f.write(f'''// Turso Cloud Database Configuration Manifest
window.TURSO_CONFIG = {{
    hostname: "{cfg['hostname']}",
    url: "https://{cfg['hostname']}/v2/pipeline",
    ro_token: "{cfg['ro_token']}"
}};
''')

    # Binary upload
    upload_url = f"https://{cfg['hostname']}/v1/upload"
    print(f"[TURSO] Uploading database binary to {upload_url}...")
    t0 = time.time()
    
    # Try using curl for maximum upload streaming performance
    try:
        cmd = [
            'curl', '-X', 'POST', upload_url,
            '-H', f"Authorization: Bearer {cfg['rw_token']}",
            '-H', 'Content-Type: application/octet-stream',
            '--data-binary', f"@{db_file}",
            '--max-time', '600'
        ]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"curl upload failed ({p.returncode}): {p.stderr}")
        print(f"[TURSO] Database upload completed via curl in {time.time()-t0:.1f}s!")
    except Exception as curl_err:
        print(f"[TURSO] curl error ({curl_err}), falling back to urllib...")
        with open(db_file, 'rb') as f:
            data = f.read()
        up_req = urllib.request.Request(
            upload_url,
            data=data,
            headers={
                'Authorization': f"Bearer {cfg['rw_token']}",
                'Content-Type': 'application/octet-stream'
            },
            method='POST'
        )
        with urllib.request.urlopen(up_req) as resp:
            print(f"[TURSO] Database upload completed via urllib in {time.time()-t0:.1f}s!")
    return True

def incremental_sync_turso(cfg):
    """Syncs latest products, ATL deals, and recent history points to Turso."""
    import duckdb
    print("[TURSO] Running incremental sync to Turso Cloud DB...")
    t0 = time.time()
    con_duck = duckdb.connect()

    # 1. Check Turso health
    try:
        check = turso_pipeline(cfg, [{'type': 'execute', 'stmt': {'sql': 'SELECT COUNT(*) FROM products;'}}])
        if check.get('results', [{}])[0].get('type') != 'ok':
            print("[TURSO] Turso table check failed, falling back to full reseed...")
            return full_reseed_turso(cfg)
    except Exception as e:
        print(f"[TURSO] Error checking Turso ({e}), attempting full reseed...")
        return full_reseed_turso(cfg)

    # 2. Sync metadata
    meta_manifests = {}
    for mf in glob.glob(os.path.join(BASE_DIR, '*_manifest.js')):
        s = os.path.basename(mf).replace('_manifest.js', '')
        try:
            with open(mf, 'r', encoding='utf-8') as f:
                c = f.read()
            m = c[c.find('{'):c.rfind('}')+1]
            meta_manifests[s] = json.loads(m).get('metadata', {})
        except Exception:
            pass

    meta_stmts = [
        {'sql': 'INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?);',
         'args': [{'type': 'text', 'value': 'stores'}, {'type': 'text', 'value': json.dumps(meta_manifests)}]},
        {'sql': 'INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?);',
         'args': [{'type': 'text', 'value': 'last_update'}, {'type': 'text', 'value': time.strftime('%Y-%m-%d %H:%M:%S')}]}
    ]
    execute_batch_sql(cfg, meta_stmts)

    # 3. Sync ATL deals
    print("[TURSO] Syncing ATL Deals...")
    atl_rows = con_duck.execute('''
        SELECT id, name, store, category, unit, unit_type, current_price, normalized_price, 
               image, url, first_seen, last_seen, 
               CAST(in_stock AS INTEGER), CAST(is_out_of_stock AS INTEGER),
               hist_count, min_price, max_price, avg_price
        FROM read_parquet('atl.parquet')
    ''').fetchall()

    atl_stmts = [{'sql': 'DELETE FROM atl_deals;'}]
    for r in atl_rows:
        atl_stmts.append({
            'sql': 'INSERT OR REPLACE INTO atl_deals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);',
            'args': [to_turso_arg(c) for c in r]
        })
    execute_batch_sql(cfg, atl_stmts, batch_size=400)
    print(f"[TURSO] Synced {len(atl_rows)} ATL deals")

    # 4. Sync today's history points
    from datetime import datetime, timedelta, timezone
    tz_dhaka = timezone(timedelta(hours=6))
    today_dhaka = datetime.now(tz_dhaka).strftime('%Y-%m-%d')
    print(f"[TURSO] Syncing history points for recent window (>= {today_dhaka})...")
    hist_batch = con_duck.execute(f'''
        SELECT product_id, date, price, normalized_price
        FROM read_parquet('history_free.parquet')
        WHERE date >= '{today_dhaka}'
    ''').fetchall()

    if hist_batch:
        hist_stmts = []
        for h in hist_batch:
            hist_stmts.append({
                'sql': 'INSERT OR REPLACE INTO history (product_id, date, price, normalized_price) VALUES (?, ?, ?, ?);',
                'args': [to_turso_arg(c) for c in h]
            })
        execute_batch_sql(cfg, hist_stmts, batch_size=500)
        print(f"[TURSO] Synced {len(hist_batch)} history rows for {today_dhaka}")

    # 5. Sync active products
    print("[TURSO] Syncing active products...")
    prods = con_duck.execute(f'''
        SELECT id, name, store, category, unit, unit_type, current_price, normalized_price, 
               image, url, first_seen, last_seen, 
               CAST(in_stock AS INTEGER), CAST(is_out_of_stock AS INTEGER),
               hist_count, min_price, max_price, avg_price
        FROM read_parquet('products_free.parquet')
        WHERE last_seen >= '{today_dhaka}' OR in_stock = true
    ''').fetchall()

    prod_stmts = []
    for r in prods:
        prod_stmts.append({
            'sql': 'INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);',
            'args': [to_turso_arg(c) for c in r]
        })
    execute_batch_sql(cfg, prod_stmts, batch_size=400)
    print(f"[TURSO] Synced {len(prods)} products to Turso in {time.time()-t0:.1f}s")
    print(f"[TURSO] Incremental synchronization complete ({time.time()-t0:.1f}s)!")
    return True

if __name__ == '__main__':
    cfg = get_config()
    if '--incremental' in sys.argv:
        incremental_sync_turso(cfg)
    else:
        full_reseed_turso(cfg)

