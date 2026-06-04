import json
import sqlite3
import os
import re
import subprocess

COMMIT = '4f8d925'

def load_chunked_js_from_git(commit, prefix):
    """Reconstructs full data by reading manifest and all parts from a git commit."""
    manifest_path = f"{prefix}_manifest.js"
    try:
        manifest_content = subprocess.check_output(['git', 'show', f'{commit}:{manifest_path}'], stderr=subprocess.DEVNULL).decode('utf-8')
        match = re.search(r'\{.*\}', manifest_content, re.DOTALL)
        if not match: return {}
        manifest = json.loads(match.group(0))
        total_chunks = manifest.get('metadata', {}).get('total_chunks', 1)
        print(f"  [+] Manifest found in {commit} for {prefix}: {total_chunks} chunks expected.")
    except:
        print(f"  [!] Manifest for {prefix} not found in {commit}.")
        return {}

    all_data = {}
    for i in range(1, total_chunks + 1):
        path = f"{prefix}_data_part{i}.js"
        try:
            content = subprocess.check_output(['git', 'show', f'{commit}:{path}'], stderr=subprocess.DEVNULL).decode('utf-8')
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                chunk = json.loads(match.group(0))
                all_data.update(chunk)
        except:
            print(f"  [!] Chunk {path} missing in {commit}!")
    
    print(f"  [+] Total items loaded from {commit} for {prefix}: {len(all_data)}")
    return all_data

def load_chunked_js_local(prefix):
    """Reconstructs full data by reading local manifest and all parts."""
    manifest_path = f"{prefix}_manifest.js"
    if not os.path.exists(manifest_path): return {}
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        content = f.read()
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match: return {}
        manifest = json.loads(match.group(0))
        total_chunks = manifest.get('metadata', {}).get('total_chunks', 1)

    all_data = {}
    for i in range(1, total_chunks + 1):
        path = f"{prefix}_data_part{i}.js"
        if not os.path.exists(path): continue
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try:
                    chunk = json.loads(match.group(0))
                    all_data.update(chunk)
                except: pass
    return all_data

def merge_histories(h1, h2):
    unique = {h['date']: h for h in h1}
    for h in h2:
        if h['date'] not in unique:
            unique[h['date']] = h
    return sorted(unique.values(), key=lambda x: x['date'])

def recover_json_store(path, git_prefix, key_prefix):
    print(f"Recovering {path}...")
    current = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            current = json.load(f)
    
    historical = load_chunked_js_from_git(COMMIT, git_prefix)
    
    merged = {}
    # First, normalize current keys and merge
    for k, v in current.items():
        norm_k = k[len(key_prefix):] if k.startswith(key_prefix) else k
        if norm_k not in merged:
            merged[norm_k] = v
        else:
            merged[norm_k]['history'] = merge_histories(merged[norm_k].get('history', []), v.get('history', []))
    
    # Then merge historical
    for k, v in historical.items():
        norm_k = k[len(key_prefix):] if k.startswith(key_prefix) else k
        if norm_k not in merged:
            v['id'] = norm_k # Store as unprefixed in data.json
            merged[norm_k] = v
        else:
            merged[norm_k]['history'] = merge_histories(merged[norm_k].get('history', []), v.get('history', []))
            for field in ['name', 'image', 'unit', 'category', 'url']:
                if not merged[norm_k].get(field) and v.get(field):
                    merged[norm_k][field] = v[field]

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2)
    print(f"  [+] {path} recovered. Total items: {len(merged)}")

def recover_metromart():
    print("Recovering Metro Mart...")
    db_path = 'metroTRACKER/backend/metro_tracker.db'
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    local_data = load_chunked_js_local("metromart")
    git_data = load_chunked_js_from_git(COMMIT, "metromart")
    
    merged = {}
    for k, v in local_data.items():
        norm_k = k[3:] if k.startswith("mt_") else k
        merged[norm_k] = v
    for k, v in git_data.items():
        norm_k = k[3:] if k.startswith("mt_") else k
        if norm_k not in merged:
            merged[norm_k] = v
        else:
            merged[norm_k]['history'] = merge_histories(merged[norm_k].get('history', []), v.get('history', []))

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name VARCHAR UNIQUE, url VARCHAR)")
    cur.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, external_id VARCHAR UNIQUE, name VARCHAR, unit VARCHAR, unit_type VARCHAR, image_url VARCHAR, category_id INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY, product_id INTEGER, actual_price FLOAT, unit_price FLOAT, scraped_at DATETIME)")
    
    cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", ("General",))
    cur.execute("SELECT id FROM categories WHERE name = ?", ("General",))
    gen_cat_id = cur.fetchone()[0]

    for eid, p in merged.items():
        cat_id = gen_cat_id
        if p.get('category'):
            cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (p['category'],))
            cur.execute("SELECT id FROM categories WHERE name = ?", (p['category'],))
            cat_id = cur.fetchone()[0]

        cur.execute("INSERT OR IGNORE INTO products (external_id, name, unit, unit_type, image_url, category_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (eid, p['name'], p.get('unit'), p.get('unit_type'), p['image'], cat_id))
        cur.execute("SELECT id FROM products WHERE external_id = ?", (eid,))
        db_pid = cur.fetchone()[0]
        
        for h in p.get('history', []):
            cur.execute("INSERT OR IGNORE INTO price_history (product_id, actual_price, unit_price, scraped_at) VALUES (?, ?, ?, ?)",
                        (db_pid, h['price'], h.get('normalized_price', h['price']), h['date'] + " 00:00:00"))
    
    conn.commit()
    conn.close()
    print(f"  [+] Metro Mart database reconstructed. Total items: {len(merged)}")

if __name__ == "__main__":
    recover_json_store("swapnoTRACKER/data.json", "shwapno", "sh_")
    recover_json_store("ShotejTRACKER/data.json", "shotejbazar", "sj_")
    recover_json_store("unimartTRACKER/data.json", "unimart", "uni_")
    recover_metromart()
    print("\nRecovery complete.")
