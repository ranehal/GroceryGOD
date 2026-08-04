import platform
import json
# High-Performance, Atomic Chunking Aggregator
import sqlite3
import os
import re
from datetime import datetime, timedelta, timezone

# Paths to data sources (Relative to GroceryGOD root)
if platform.system() == 'Windows':
    SHWAPNO_DATA = r'C:\PROJECTS\shopno\data.json'
else:
    SHWAPNO_DATA = '/kaggle/working/shopno/data.json'
if not os.path.exists(SHWAPNO_DATA):
    SHWAPNO_DATA = 'swapnoTRACKER/data.json'
CHALDAL_DATA = 'chaldalTRACKER/data.js'
MEENA_DB = 'MEENAtracker/meenatracker.db'
if platform.system() == 'Windows':
    OTHOBA_DB = r'C:\PROJECTS\othoba\othoba_tracker.db'
else:
    OTHOBA_DB = '/kaggle/working/othoba/othoba_tracker.db'
if not os.path.exists(OTHOBA_DB):
    OTHOBA_DB = 'othobaTRACKER/othoba_tracker.db'
METRO_DB = 'metroTRACKER/metro_tracker.db'
UNIMART_DATA = 'unimartTRACKER/data.json'
SHOTEJ_DATA = 'ShotejTRACKER/data.json'
FOODI_DB = 'FooDIEscraper/data/scraper.db'


DHAKA_TZ = timezone(timedelta(hours=6))

# --- SECURITY & ROBUSTNESS CONSTANTS ---
MAX_FILE_SIZE_MB = 45 # Safely under GitHub's 50MB warning and 100MB hard limit
MAX_CHUNK_ITEMS = 5000 # Smaller chunks for better atomicity and reliability

def parse_unit_and_calculate(name, unit_str, price):
    text = ((unit_str or "") + " " + name).lower()
    mult_match = re.search(r'(\d+(\.\d+)?)\s*(kg|gm|gram|g|ml|ltr|l)\s*[xX*]\s*(\d+)', text)
    if mult_match:
        val = float(mult_match.group(1))
        unit = mult_match.group(3)
        count = float(mult_match.group(4))
        total_val = val * count
        if total_val == 0: return 'kg', price
        if unit in ['gm', 'gram', 'g', 'ml']:
            u_type = 'kg' if unit != 'ml' else 'liter'
            return u_type, (price / total_val) * 1000
        else:
            u_type = 'kg' if unit == 'kg' else 'liter'
            return u_type, (price / total_val)

    text = re.sub(r'\(?[±\+]\s*\d+\s*(gm|g|kg|ml|ltr|l)?\)?', '', text)
    weight_match = re.search(r'(\d+(\.\d+)?)\s*(kg|gm|gram|g)\b', text)
    if weight_match:
        val = float(weight_match.group(1))
        unit = weight_match.group(3)
        if val == 0: return 'kg', price
        return 'kg', (price / val) if unit == 'kg' else (price / val) * 1000

    volume_match = re.search(r'(\d+(\.\d+)?)\s*(ltr|liter|l|ml)\b', text)
    if volume_match:
        val = float(volume_match.group(1))
        unit = volume_match.group(3)
        if val == 0: return 'liter', price
        return 'liter', (price / val) if unit in ['ltr', 'liter', 'l'] else (price / val) * 1000

    if any(x in text for x in ['pc', 'piece', 'hali', 'dozen', 'pkt', 'pack', 'each', 'bottle', 'can', 'box']):
        return 'piece', price
    return 'kg', price

def load_shwapno():
    print("Processing Shwapno...")
    try:
        pinned_names = []
        cats_file = 'swapnoTRACKER/categories.json'
        if os.path.exists(cats_file):
            try:
                with open(cats_file, 'r', encoding='utf-8') as cf:
                    cats_data = json.load(cf)
                    pinned_group = next((g for g in cats_data.get('groups', []) if g.get('id') == 'pinned_deals'), None)
                    if pinned_group: pinned_names = [c['name'] for c in pinned_group['categories']]
            except: pass

        def get_display_cat(raw_cat):
            raw_clean = raw_cat.strip().lower()
            for pn in pinned_names:
                if pn.strip().lower() == raw_clean: return f"\ud83d\udccc {pn}"
            for pn in pinned_names:
                pn_clean = pn.strip().lower()
                s_pn = re.sub(r'\W+', '', pn_clean)
                s_raw = re.sub(r'\W+', '', raw_clean)
                if s_pn in s_raw or s_raw in s_pn: return f"\ud83d\udccc {pn}"
            return raw_cat

        products_by_name = {}
        stats = {"web": 0, "app": 0, "combined": 0}
        all_dates = []

        # 1. Load Web Data
        if os.path.exists(SHWAPNO_DATA):
            try:
                with open(SHWAPNO_DATA, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for pid, p in data.items():
                    if pid in ['metadata', 'products']: continue
                    name_key = re.sub(r'\W+', '', p.get('name', '')).lower()
                    if not name_key: continue
                    
                    final_pid = pid if pid.startswith("sh_") else f"sh_{pid}"
                    hist = p.get('history', [])
                    curr_p = hist[-1].get('price', 0) if hist else 0
                    u_type, norm_p = parse_unit_and_calculate(p.get('name', ''), "", curr_p)
                    
                    unique_hist = {}
                    for h in hist:
                        if h.get('date'):
                            _, h_norm = parse_unit_and_calculate(p.get('name', ''), "", h.get('price', 0))
                            unique_hist[h['date']] = {"date": h['date'], "price": h.get('price', 0), "normalized_price": h_norm}
                    
                    new_history = sorted(unique_hist.values(), key=lambda x: x['date'])
                    for h in new_history: all_dates.append(h['date'])
                    first_seen = new_history[0]['date'] if new_history else datetime.now(DHAKA_TZ).strftime("%Y-%m-%d")
                        
                    products_by_name[name_key] = {
                        "id": final_pid, "name": p.get('name'), "store": "shwapno",
                        "category": get_display_cat(p.get('category', 'General')), "unit": p.get('unit', 'N/A'), "unit_type": u_type,
                        "current_price": curr_p, "normalized_price": norm_p,
                        "image": p.get('image'), "url": p.get('url'), "history": new_history, "first_seen": first_seen
                    }
                    stats["web"] += 1
            except Exception as e:
                print(f"Error loading Shwapno web data: {e}")

        # 2. Load App Data
        if platform.system() == 'Windows':
            app_data_path = r'C:\PROJECTS\shopno\frontend\shwapno_products.json'
        else:
            app_data_path = '/kaggle/working/shopno/frontend/shwapno_products.json'
        if not os.path.exists(app_data_path):
            app_data_path = 'swapnoTRACKER/frontend/shwapno_products.json'
        if os.path.exists(app_data_path):
            try:
                with open(app_data_path, 'r', encoding='utf-8') as f:
                    app_data = json.load(f)
                for p in app_data:
                    name_key = re.sub(r'\W+', '', p.get('name', '')).lower()
                    if not name_key: continue
                    
                    curr_p = p.get('current_price', 0)
                    u_type, norm_p = parse_unit_and_calculate(p.get('name', ''), p.get('unit', ''), curr_p)
                    
                    # Check for collision
                    if name_key in products_by_name:
                        existing = products_by_name[name_key]
                        if curr_p >= existing['current_price']:
                            continue
                            
                    final_pid = f"sh_{p.get('id')}"
                    
                    hist_dict = p.get('price_history', {})
                    unique_hist = {}
                    for d_str, price_val in hist_dict.items():
                        _, h_norm = parse_unit_and_calculate(p.get('name', ''), p.get('unit', ''), price_val)
                        unique_hist[d_str] = {"date": d_str, "price": price_val, "normalized_price": h_norm}
                        
                    new_history = sorted(unique_hist.values(), key=lambda x: x['date'])
                    for h in new_history: all_dates.append(h['date'])
                    first_seen = new_history[0]['date'] if new_history else datetime.now(DHAKA_TZ).strftime("%Y-%m-%d")
                    
                    url = p.get('url', '')
                    if url and not url.startswith('http'):
                        url = f"https://www.shwapno.com/{url}"

                    products_by_name[name_key] = {
                        "id": final_pid, "name": p.get('name'), "store": "shwapno",
                        "category": get_display_cat(p.get('category', 'General')), "unit": p.get('unit', 'N/A'), "unit_type": u_type,
                        "current_price": curr_p, "normalized_price": norm_p,
                        "image": p.get('image'), "url": url, "history": new_history, "first_seen": first_seen
                    }
                    stats["app"] += 1
            except Exception as e:
                print(f"Error loading Shwapno App data: {e}")

        products = {v["id"]: v for v in products_by_name.values()}
        stats["combined"] = len(products)
        print(f"Shwapno Stats -> Web: {stats['web']}, App: {stats['app']}, Combined Unique: {stats['combined']}")

        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error processing Shwapno: {e}")
        return None, None

def load_chaldal():
    print("Processing Chaldal...")
    target_chaldal = CHALDAL_DATA
    if not os.path.exists(target_chaldal):
        for candidate in ['chaldalTRACKER/data.js', 'chaldalTRACKER/data/products.json', 'chaldalTRACKER/chaldal_products.json', 'chaldalTRACKER/data.json']:
            if os.path.exists(candidate):
                target_chaldal = candidate
                break
    if not os.path.exists(target_chaldal):
        stats={"web":0, "app":0, "combined":0}
        print(f"Chaldal Stats -> Web: {stats.get('web', 0)}, App: {stats.get('app', 0)}, Combined Unique: {stats.get('combined', 0)}")
        return {}, "N/A", stats
    try:
        with open(target_chaldal, 'r', encoding='utf-8') as f:
            content = f.read()
        start, end = content.find('{'), content.rfind('}') + 1
        if start == -1 or end == 0: return None, None
        data = json.loads(content[start:end])
        products = {}
        all_dates = []
        for pid, p in data.items():
            if pid in ['metadata', 'products']: continue
            source_history = p.get('history', [])
            new_history = []
            for h in source_history:
                _, h_norm = parse_unit_and_calculate(p.get('name', ''), p.get('current_unit', ''), h.get('price', 0))
                new_history.append({"date": h.get('date'), "price": h.get('price'), "normalized_price": h_norm})
                if h.get('date'): all_dates.append(h['date'])
            curr_p = p.get('current_price', 0)
            u_type, norm_p = parse_unit_and_calculate(p.get('name', ''), p.get('current_unit', ''), curr_p)
            products[f"ch_{pid}"] = {
                "id": f"ch_{pid}", "name": p.get('name'), "store": "chaldal",
                "category": p.get('category', 'General'), "unit": p.get('current_unit'), "unit_type": u_type,
                "current_price": curr_p, "normalized_price": norm_p,
                "image": p.get('image'), "history": new_history
            }
        stats = {"web": len(products), "app": 0, "combined": len(products)}
        print(f"Chaldal Stats -> Web: {stats['web']}, App: {stats['app']}, Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error processing Chaldal: {e}")
        return None, None

def load_meenabazar():
    print("Processing Meena Bazar...")
    if not os.path.exists(MEENA_DB): stats={"web":0, "app":0, "combined":0}; print(f"Meenabazar Stats -> Web: {stats.get('web', 0)}, App: {stats.get('app', 0)}, Combined Unique: {stats.get('combined', 0)}"); return {}, "N/A", stats
    try:
        conn = sqlite3.connect(MEENA_DB); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM categories")
        cats = {row['id']: row['name'] for row in cursor.fetchall()}
        cursor.execute("SELECT id, external_id, name, unit, unit_type, image_url, category_id FROM products")
        db_p = cursor.fetchall()
        cursor.execute("SELECT product_id, actual_price, scraped_at FROM price_history ORDER BY scraped_at ASC")
        all_history = {}
        for row in cursor.fetchall():
            pid = row['product_id']
            if pid not in all_history: all_history[pid] = []
            all_history[pid].append(row)
        products = {}
        all_dates = []
        for p in db_p:
            db_h = all_history.get(p['id'], [])
            if not db_h: continue
            new_history = []
            for h in db_h:
                raw_date = h['scraped_at']
                date_str = raw_date.split('T')[0].split(' ')[0] if isinstance(raw_date, str) else raw_date.strftime("%Y-%m-%d")
                _, h_norm = parse_unit_and_calculate(p['name'], p['unit'], h['actual_price'])
                new_history.append({"date": date_str, "price": h['actual_price'], "normalized_price": h_norm})
                all_dates.append(date_str)
            curr_p = new_history[-1]['price']
            u_type, norm_p = parse_unit_and_calculate(p['name'], p['unit'], curr_p)
            products[f"mb_{p['external_id'] or p['id']}"] = {
                "id": f"mb_{p['external_id'] or p['id']}", "name": p['name'], "store": "meenabazar",
                "category": cats.get(p['category_id'], 'General'), "unit": p['unit'], "unit_type": u_type,
                "current_price": curr_p, "normalized_price": norm_p,
                "image": p['image_url'], "history": new_history
            }
        conn.close()
        stats = {"web": len(products), "app": 0, "combined": len(products)}
        print(f"Meenabazar Stats -> Web: {stats['web']}, App: {stats['app']}, Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error Meena Bazar: {e}")
        return None, None

def load_othoba():
    print("Processing Othoba...")
    try:
        products_by_name = {}
        stats = {"web": 0, "app": 0, "combined": 0}
        all_dates = []

        def process_json_file(filepath, source_type):
            if not os.path.exists(filepath): return
            try:
                import json, re, platform
                from datetime import datetime
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for p in data:
                    name_key = re.sub(r'\W+', '', p.get('name', '')).lower()
                    if not name_key: continue
                    
                    stats[source_type] += 1
                    curr_p = p.get('current_price', 0)
                    u_type, norm_p = parse_unit_and_calculate(p.get('name', ''), p.get('unit', ''), curr_p)
                    
                    if name_key in products_by_name:
                        existing = products_by_name[name_key]
                        if curr_p >= existing['current_price']:
                            continue
                            
                    final_pid = p.get('id')
                    if not final_pid.startswith('ot_'): final_pid = f"ot_{final_pid}"
                    
                    hist_dict = p.get('price_history', {})
                    unique_hist = {}
                    
                    # Some json versions might have history as array
                    raw_history = p.get('history', [])
                    if isinstance(raw_history, list) and len(raw_history) > 0:
                        for h in raw_history:
                            d_str = h.get('date')
                            price_val = h.get('price')
                            _, h_norm = parse_unit_and_calculate(p.get('name', ''), p.get('unit', ''), price_val)
                            unique_hist[d_str] = {"date": d_str, "price": price_val, "normalized_price": h_norm}
                    else:
                        for d_str, price_val in hist_dict.items():
                            _, h_norm = parse_unit_and_calculate(p.get('name', ''), p.get('unit', ''), price_val)
                            unique_hist[d_str] = {"date": d_str, "price": price_val, "normalized_price": h_norm}
                        
                    new_history = sorted(unique_hist.values(), key=lambda x: x['date'])
                    for h in new_history: all_dates.append(h['date'])
                    
                    first_seen = p.get('first_seen')
                    if not first_seen:
                        first_seen = new_history[0]['date'] if new_history else datetime.now(DHAKA_TZ).strftime("%Y-%m-%d")

                    products_by_name[name_key] = {
                        "id": final_pid, "name": p.get('name'), "store": "othoba",
                        "category": p.get('category', 'General'), "unit": p.get('unit', 'N/A'), "unit_type": u_type,
                        "current_price": curr_p, "normalized_price": norm_p,
                        "image": p.get('image'), "history": new_history, "first_seen": first_seen
                    }
            except Exception as e:
                print(f"Error loading Othoba {source_type} data from {filepath}: {e}")

        # 1. Load Web Data
        if platform.system() == 'Windows':
            web_path = r'C:\PROJECTS\othoba\frontend\othoba_products.json'
        else:
            web_path = '/kaggle/working/othoba/frontend/othoba_products.json'
        if not os.path.exists(web_path):
            web_path = 'othobaTRACKER/frontend/othoba_products.json'
        process_json_file(web_path, 'web')

        # 2. Load App Data
        app_path = r'C:\PROJECTS\othoba\othoba_products.json' if platform.system() == 'Windows' else '/kaggle/working/othoba/othoba_products.json'
        if not os.path.exists(app_path):
            app_path = 'othobaTRACKER/othoba_products.json'
        process_json_file(app_path, 'app')

        products = {v["id"]: v for v in products_by_name.values()}
        stats["combined"] = len(products)
        print(f"Othoba Stats -> Web: {stats['web']}, App: {stats['app']}, Combined Unique: {stats['combined']}")

        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error Othoba: {e}")
        return None, None

def load_metromart():
    print("Processing Metro Mart...")
    if not os.path.exists(METRO_DB): stats={"web":0, "app":0, "combined":0}; print(f"Metromart Stats -> Web: {stats.get('web', 0)}, App: {stats.get('app', 0)}, Combined Unique: {stats.get('combined', 0)}"); return {}, "N/A", stats
    try:
        conn = sqlite3.connect(METRO_DB); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM categories"); cats = {row['id']: row['name'] for row in cursor.fetchall()}
        cursor.execute("SELECT id, external_id, name, unit, unit_type, image_url, category_id FROM products")
        db_p = cursor.fetchall()
        cursor.execute("SELECT product_id, actual_price, scraped_at FROM price_history ORDER BY scraped_at ASC")
        all_history = {}
        for row in cursor.fetchall():
            pid = row['product_id']
            if pid not in all_history: all_history[pid] = []
            all_history[pid].append(row)
        products = {}
        all_dates = []
        for p in db_p:
            db_h = all_history.get(p['id'], [])
            if not db_h: continue
            new_history = []
            for h in db_h:
                raw_date = h['scraped_at']
                date_str = raw_date.split('T')[0].split(' ')[0] if isinstance(raw_date, str) else raw_date.strftime("%Y-%m-%d")
                _, h_norm = parse_unit_and_calculate(p['name'], p['unit'], h['actual_price'])
                new_history.append({"date": date_str, "price": h['actual_price'], "normalized_price": h_norm})
                all_dates.append(date_str)
            curr_p = new_history[-1]['price']
            u_type, norm_p = parse_unit_and_calculate(p['name'], p['unit'], curr_p)
            img = p['image_url']
            if img and img.startswith('/'): img = "https://www.metromartonline.com" + img
            products[f"mt_{p['external_id'] or p['id']}"] = {
                "id": f"mt_{p['external_id'] or p['id']}", "name": p['name'], "store": "metromart",
                "category": cats.get(p['category_id'], 'General'), "unit": p['unit'], "unit_type": u_type,
                "current_price": curr_p, "normalized_price": norm_p, "image": img, "history": new_history
            }
        conn.close()
        stats = {"web": len(products), "app": 0, "combined": len(products)}
        print(f"Metromart Stats -> Web: {stats['web']}, App: {stats['app']}, Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error Metro Mart: {e}")
        return None, None

def load_unimart():
    print("Processing Unimart...")
    if not os.path.exists(UNIMART_DATA): stats={"web":0, "app":0, "combined":0}; print(f"Unimart Stats -> Web: {stats.get('web', 0)}, App: {stats.get('app', 0)}, Combined Unique: {stats.get('combined', 0)}"); return {}, "N/A", stats
    try:
        with open(UNIMART_DATA, 'r', encoding='utf-8') as f: data = json.load(f)
        products = {}; all_dates = []
        for pid, p in data.items():
            p_id = f"un_{pid}" if not pid.startswith("un_") else pid
            hist = p.get('history', [])
            curr_p = p.get('current_price', 0)
            u_type, norm_p = parse_unit_and_calculate(p.get('name', ''), p.get('unit', ''), curr_p)
            
            unique_hist = {}
            if p_id in products:
                for h in products[p_id]['history']: unique_hist[h['date']] = h

            for h in hist:
                if h.get('date'):
                    _, h_norm = parse_unit_and_calculate(p.get('name', ''), p.get('unit', ''), h.get('price', 0))
                    unique_hist[h['date']] = {"date": h.get('date'), "price": h.get('price'), "normalized_price": h_norm}
                    all_dates.append(h['date'])
            
            new_history = sorted(unique_hist.values(), key=lambda x: x['date'])
            products[p_id] = {
                "id": p_id, "name": p.get('name'), "store": "unimart",
                "category": p.get('category', 'General'), "unit": p.get('unit'), "unit_type": u_type,
                "current_price": curr_p, "normalized_price": norm_p, "image": p.get('image'), "history": new_history
            }
        stats = {"web": len(products), "app": 0, "combined": len(products)}
        print(f"Unimart Stats -> Web: {stats['web']}, App: {stats['app']}, Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error Unimart: {e}"); return None, None

def load_shotejbazar():
    print("Processing ShotejBazar...")
    if not os.path.exists(SHOTEJ_DATA): stats={"web":0, "app":0, "combined":0}; print(f"Shotejbazar Stats -> Web: {stats.get('web', 0)}, App: {stats.get('app', 0)}, Combined Unique: {stats.get('combined', 0)}"); return {}, "N/A", stats
    try:
        with open(SHOTEJ_DATA, 'r', encoding='utf-8') as f: data = json.load(f)
        products = {}; all_dates = []
        for pid, p in data.items():
            p_id = f"sj_{pid}" if not pid.startswith("sj_") else pid
            hist = p.get('history', [])
            curr_p = p.get('current_price', 0)
            u_type, norm_p = parse_unit_and_calculate(p.get('name', ''), p.get('unit', ''), curr_p)
            
            unique_hist = {}
            if p_id in products:
                for h in products[p_id]['history']: unique_hist[h['date']] = h

            for h in hist:
                if h.get('date'):
                    _, h_norm = parse_unit_and_calculate(p.get('name', ''), p.get('unit', ''), h.get('price', 0))
                    unique_hist[h['date']] = {"date": h.get('date'), "price": h.get('price'), "normalized_price": h_norm}
                    all_dates.append(h['date'])

            new_history = sorted(unique_hist.values(), key=lambda x: x['date'])
            first_seen = new_history[0]['date'] if new_history else datetime.now(DHAKA_TZ).strftime("%Y-%m-%d")
            products[p_id] = {
                "id": p_id, "name": p.get('name'), "store": "shotejbazar",
                "category": p.get('category', 'General'), "unit": p.get('unit'), "unit_type": u_type,
                "current_price": curr_p, "normalized_price": norm_p, "image": p.get('image'), "history": new_history, "first_seen": first_seen
            }
        stats = {"web": len(products), "app": 0, "combined": len(products)}
        print(f"Shotejbazar Stats -> Web: {stats['web']}, App: {stats['app']}, Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error ShotejBazar: {e}"); return None, None

def load_foodi():
    print("Processing Foodi...")
    if not os.path.exists(FOODI_DB): stats={"web":0, "app":0, "combined":0}; print(f"Foodi Stats -> Web: {stats.get('web', 0)}, App: {stats.get('app', 0)}, Combined Unique: {stats.get('combined', 0)}"); return {}, "N/A", stats
    try:
        conn = sqlite3.connect(FOODI_DB); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        cursor.execute("SELECT product_id, name, uom, category_name, discounted_price, image_path FROM products")
        db_p = cursor.fetchall()
        cursor.execute("SELECT product_id, discounted_price, scraped_at FROM price_history ORDER BY scraped_at ASC")
        all_history = {}
        for row in cursor.fetchall():
            pid = row['product_id']
            if pid not in all_history: all_history[pid] = []
            all_history[pid].append(row)
        products = {}
        all_dates = []
        for p in db_p:
            db_h = all_history.get(p['product_id'], [])
            if not db_h: continue
            new_history = []
            unit_str = p['uom'] or ''
            for h in db_h:
                raw_date = h['scraped_at']
                date_str = raw_date.split('T')[0].split(' ')[0] if isinstance(raw_date, str) else raw_date.strftime("%Y-%m-%d")
                _, h_norm = parse_unit_and_calculate(p['name'], unit_str, h['discounted_price'])
                new_history.append({"date": date_str, "price": h['discounted_price'], "normalized_price": h_norm})
                all_dates.append(date_str)
            curr_p = new_history[-1]['price']
            u_type, norm_p = parse_unit_and_calculate(p['name'], unit_str, curr_p)
            img = p['image_path']
            if img:
                if not img.startswith('http'):
                    img = "https://s3.ap-southeast-1.amazonaws.com/cdn.foodibd.com" + (img if img.startswith('/') else '/' + img)

            p_id = f"fd_{p['product_id']}"
            first_seen = new_history[0]['date'] if new_history else datetime.now(DHAKA_TZ).strftime("%Y-%m-%d")
            products[p_id] = {
                "id": p_id, "name": p['name'], "store": "foodi",
                "category": p['category_name'] or 'General', "unit": unit_str, "unit_type": u_type,
                "current_price": curr_p, "normalized_price": norm_p, "image": img, "history": new_history, "first_seen": first_seen
            }
        conn.close()
        stats = {"web": len(products), "app": 0, "combined": len(products)}
        print(f"Foodi Stats -> Web: {stats['web']}, App: {stats['app']}, Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error Foodi: {e}"); return None, None

# --- ATOMIC CHUNKING ENGINE ---
def save_store_data(name, data_tuple):
    if not data_tuple: return None
    
    scraper_stats = None
    if len(data_tuple) == 3:
        products, date_range, scraper_stats = data_tuple
    else:
        products, date_range = data_tuple
        
    if not products:
        summary = f"📦 <b>{name.title()}</b>: 0 items"
        if scraper_stats:
            summary += f"\n   ├ Web: {scraper_stats.get('web', 0)} | App: {scraper_stats.get('app', 0)} | Combined Unique: {scraper_stats.get('combined', 0)}"
        print(f"Saved {name:15} | Items:     0 | Chunks:  0 | Safe Under {MAX_FILE_SIZE_MB}MB")
        return summary

    
    total_items = len(products)
    last_update = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    product_items = sorted(products.items())
    
    # 1. Atomic Size Calculation
    # We dynamically adjust chunk size to stay under MAX_FILE_SIZE_MB
    # Initial estimate: MAX_CHUNK_ITEMS
    current_chunk_size = MAX_CHUNK_ITEMS
    
    # Pre-clean existing files to avoid ghosts
    for f in os.listdir('.'):
        if f.startswith(f"{name}_data_part") and f.endswith(".js"):
            os.remove(f)

    temp_chunks = []
    chunk_idx = 0
    while chunk_idx * current_chunk_size < total_items:
        start = chunk_idx * current_chunk_size
        end = (chunk_idx + 1) * current_chunk_size
        chunk_dict = dict(product_items[start:end])
        
        # Test serialization size
        test_json = json.dumps(chunk_dict, separators=(',', ':'))
        size_mb = len(test_json) / (1024 * 1024)
        
        # If too big, cut chunk size in half and retry this chunk
        if size_mb > MAX_FILE_SIZE_MB:
            print(f"  [!] Chunk {chunk_idx+1} too large ({size_mb:.2f}MB). Shrinking size...")
            current_chunk_size = max(1000, current_chunk_size // 2)
            continue 
            
        temp_chunks.append(chunk_dict)
        chunk_idx += 1

    total_chunks = len(temp_chunks)
    
    # 2. Save Manifest
    manifest_meta = {
        "last_update": last_update, "total": total_items,
        "date_range": date_range, "total_chunks": total_chunks, "chunk_size": current_chunk_size
    }
    if scraper_stats:
        manifest_meta["scraper_stats"] = scraper_stats
        
    manifest = {
        "metadata": manifest_meta
    }
    with open(f"{name}_manifest.js", 'w', encoding='utf-8') as f:
        f.write(f"window.{name}Manifest = {json.dumps(manifest, separators=(',', ':'))};")
    
    # 3. Save Validated Chunks
    for i, chunk in enumerate(temp_chunks):
        with open(f"{name}_data_part{i+1}.js", 'w', encoding='utf-8') as f:
            f.write(f"window.{name}_part{i+1} = {json.dumps(chunk, separators=(',', ':'))};")
            
    summary = f"📦 <b>{name.title()}</b>: {total_items} items ({total_chunks} chunks)"
    if scraper_stats:
        summary += f"\n   ├ Web: {scraper_stats.get('web', 0)} | App: {scraper_stats.get('app', 0)} | Combined Unique: {scraper_stats.get('combined', 0)}"
        
    print(f"Saved {name:15} | Items: {total_items:5} | Chunks: {total_chunks:2} | Safe Under {MAX_FILE_SIZE_MB}MB")
    return summary

def main():
    print("\n" + "="*70 + "\nGODDATA AGGREGATOR // Atomic Zero-Fail Engine\n" + "="*70)
    summaries = []
    
    for store_name, loader in [
        ("shwapno", load_shwapno),
        ("chaldal", load_chaldal),
        ("meenabazar", load_meenabazar),
        ("othoba", load_othoba),
        ("metromart", load_metromart),
        ("unimart", load_unimart),
        ("shotejbazar", load_shotejbazar),
        ("foodi", load_foodi)
    ]:
        res = save_store_data(store_name, loader())
        if res: summaries.append(res)
        
    print("="*70 + "\n")
    
    # Telegram Notification
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat and summaries:
        import requests
        msg = "📊 <b>Aggregator Complete</b>\n\n" + "\n".join(summaries)
        try:
            requests.post(f"https://api.telegram.org/bot{tg_token}/sendMessage", 
                          json={"chat_id": tg_chat, "text": msg, "parse_mode": "HTML"}, timeout=10)
            print("Telegram summary sent.")
        except Exception as e:
            print(f"Failed to send Telegram summary: {e}")

if __name__ == "__main__": main()

