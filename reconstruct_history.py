import json
import sqlite3
import os
import re

def load_chunked_js(prefix):
    """Dynamically reconstructs full data by reading manifest and all parts."""
    manifest_path = f"{prefix}_manifest.js"
    if not os.path.exists(manifest_path):
        print(f"  [!] Manifest {manifest_path} not found.")
        return {}
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        content = f.read()
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match: return {}
        manifest = json.loads(match.group(0))
        total_chunks = manifest.get('metadata', {}).get('total_chunks', 1)
        print(f"  [+] Manifest found for {prefix}: {total_chunks} chunks expected.")

    all_data = {}
    for i in range(1, total_chunks + 1):
        path = f"{prefix}_data_part{i}.js"
        if not os.path.exists(path):
            print(f"  [!] Chunk {path} missing!")
            continue
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try:
                    chunk = json.loads(match.group(0))
                    all_data.update(chunk)
                except: pass
    print(f"  [+] Total items loaded for {prefix}: {len(all_data)}")
    return all_data

def reconstruct_meena():
    print("Reconstructing Meena Bazar...")
    data = load_chunked_js("meenabazar")
    if not data: return
    db_path = 'MEENAtracker/backend/meenatracker.db'
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # PRECISE SCHEMA
    cur.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name VARCHAR UNIQUE, url VARCHAR, is_custom BOOLEAN)")
    cur.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, external_id VARCHAR UNIQUE, name VARCHAR, unit VARCHAR, unit_type VARCHAR, image_url VARCHAR, category_id INTEGER, is_favorite BOOLEAN)")
    cur.execute("CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY, product_id INTEGER, actual_price FLOAT, unit_price FLOAT, scraped_at DATETIME)")
    
    cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", ("General",))
    cur.execute("SELECT id FROM categories WHERE name = ?", ("General",))
    gen_cat_id = cur.fetchone()[0]

    for pid, p in data.items():
        base_id = pid[3:] if pid.startswith('mb_') else pid
        cat_id = gen_cat_id
        if p.get('category'):
            cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (p['category'],))
            cur.execute("SELECT id FROM categories WHERE name = ?", (p['category'],))
            cat_id = cur.fetchone()[0]

        cur.execute("INSERT OR IGNORE INTO products (external_id, name, unit, unit_type, image_url, category_id, is_favorite) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (base_id, p['name'], p.get('unit'), p.get('unit_type'), p['image'], cat_id, 0))
        cur.execute("SELECT id FROM products WHERE external_id = ?", (base_id,))
        db_pid = cur.fetchone()[0]
        for h in p.get('history', []):
            cur.execute("INSERT OR IGNORE INTO price_history (product_id, actual_price, unit_price, scraped_at) VALUES (?, ?, ?, ?)",
                        (db_pid, h['price'], h.get('normalized_price', h['price']), h['date'] + " 00:00:00"))
    conn.commit()
    conn.close()

def reconstruct_othoba():
    print("Reconstructing Othoba...")
    data = load_chunked_js("othoba")
    if not data: return
    db_path = 'othobaTRACKER/backend/othoba_tracker.db'
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # PRECISE SCHEMA matching models.py
    cur.execute("CREATE TABLE IF NOT EXISTS products (id VARCHAR PRIMARY KEY, name VARCHAR, sku VARCHAR, vendor_name VARCHAR, category_name VARCHAR, image_url VARCHAR, extracted_unit_type VARCHAR, extracted_unit_value FLOAT)")
    cur.execute("CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY, product_id VARCHAR, timestamp DATETIME, price_amount FLOAT, is_out_of_stock BOOLEAN)")
    
    for pid, p in data.items():
        base_id = pid[3:] if pid.startswith('ot_') else pid
        u_val = 1.0; u_type = "piece"
        try:
            m = re.match(r'(\d+\.?\d*)\s*(.*)', p.get('unit', ''))
            if m: u_val = float(m.group(1)); u_type = m.group(2)
        except: pass

        cur.execute("INSERT OR IGNORE INTO products (id, name, sku, category_name, image_url, extracted_unit_type, extracted_unit_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (base_id, p['name'], base_id, p['category'], p['image'], u_type, u_val))
        for h in p.get('history', []):
            cur.execute("INSERT OR IGNORE INTO price_history (product_id, price_amount, timestamp, is_out_of_stock) VALUES (?, ?, ?, ?)",
                        (base_id, h['price'], h['date'] + " 00:00:00", 0))
    conn.commit()
    conn.close()

def reconstruct_json(dest_path, prefix, base_prefix):
    print(f"Reconstructing {dest_path}...")
    data = load_chunked_js(prefix)
    if not data: return
    clean_data = {}
    for pid, p in data.items():
        base_id = pid[len(base_prefix):] if pid.startswith(base_prefix) else pid
        clean_data[base_id] = p
    
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, 'w', encoding='utf-8') as f:
        json.dump(clean_data, f, separators=(',', ':'))

def reconstruct_metromart():
    print("Reconstructing Metro Mart...")
    data = load_chunked_js("metromart")
    if not data: return
    db_path = 'metroTRACKER/backend/metro_tracker.db'
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name VARCHAR UNIQUE, url VARCHAR)")
    cur.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, external_id VARCHAR UNIQUE, name VARCHAR, unit VARCHAR, unit_type VARCHAR, image_url VARCHAR, category_id INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY, product_id INTEGER, actual_price FLOAT, unit_price FLOAT, scraped_at DATETIME)")
    
    cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", ("General",))
    cur.execute("SELECT id FROM categories WHERE name = ?", ("General",))
    gen_cat_id = cur.fetchone()[0]

    for pid, p in data.items():
        base_id = pid[3:] if pid.startswith('mt_') else pid
        cat_id = gen_cat_id
        if p.get('category'):
            cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (p['category'],))
            cur.execute("SELECT id FROM categories WHERE name = ?", (p['category'],))
            cat_id = cur.fetchone()[0]

        cur.execute("INSERT OR IGNORE INTO products (external_id, name, unit, unit_type, image_url, category_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (base_id, p['name'], p.get('unit'), p.get('unit_type'), p['image'], cat_id))
        cur.execute("SELECT id FROM products WHERE external_id = ?", (base_id,))
        db_pid = cur.fetchone()[0]
        for h in p.get('history', []):
            cur.execute("INSERT OR IGNORE INTO price_history (product_id, actual_price, unit_price, scraped_at) VALUES (?, ?, ?, ?)",
                        (db_pid, h['price'], h.get('normalized_price', h['price']), h['date'] + " 00:00:00"))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    reconstruct_meena()
    reconstruct_othoba()
    reconstruct_metromart()
    reconstruct_json("swapnoTRACKER/data.json", "shwapno", "sh_")
    reconstruct_json("unimartTRACKER/data.json", "unimart", "uni_")
    reconstruct_json("ShotejTRACKER/data.json", "shotejbazar", "sj_")
    
    print("Reconstructing Chaldal...")
    ch_data = load_chunked_js("chaldal")
    if ch_data:
        clean_ch = { (k[3:] if k.startswith('ch_') else k): v for k, v in ch_data.items() }
        os.makedirs("PRICETRACKER", exist_ok=True)
        with open("PRICETRACKER/data.js", "w", encoding='utf-8') as f:
            f.write(f"window.PRODUCT_DATA = {json.dumps(clean_ch, separators=(',', ':'))};")
