import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

def safe_load_json(filepath, default=None):
    if default is None: default = {}
    if not os.path.exists(filepath) and os.path.exists(filepath + '.enc'):
        try:
            import hashlib
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            KEY = os.environ.get('GOD_PREMIUM_KEY', 'assalamualaikum').strip()
            with open(filepath + '.enc', 'rb') as ef:
                enc_data = ef.read()
            if enc_data[:4] == b'GGE1':
                salt, iv, ct = enc_data[4:20], enc_data[20:32], enc_data[32:]
                kdf = hashlib.pbkdf2_hmac('sha256', KEY.encode('utf-8'), salt, 250000, dklen=32)
                content = AESGCM(kdf).decrypt(iv, ct, None).decode('utf-8', errors='ignore')
                return json.loads(content)
        except Exception:
            pass
    if not os.path.exists(filepath): return default
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read().strip()
    if not content: return default
    try:
        return json.loads(content)
    except Exception as e:
        print(f"[JSON Recovery] Truncation in {os.path.basename(filepath)} ({e}). Repairing...")
        last_close = content.rfind('}')
        while last_close > 0:
            candidate = content[:last_close+1]
            if candidate.count('{') > candidate.count('}'):
                candidate += '}' * (candidate.count('{') - candidate.count('}'))
            try:
                return json.loads(candidate)
            except Exception:
                last_close = content.rfind('}', 0, last_close)
        return default

def clean_disk_space():
    print("[Aggregator] Cleaning temporary files & caches to free disk space...")
    import glob, shutil
    for pattern in ['*.tmp', '*.bak', '/root/.cache/pip/*']:
        for p in glob.glob(pattern):
            try:
                if os.path.isfile(p): os.remove(p)
                elif os.path.isdir(p): shutil.rmtree(p, ignore_errors=True)
            except: pass

import platform
import json
# High-Performance, Atomic Chunking Aggregator
import sqlite3
import os
import re
from collections import defaultdict
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

def clean_tolerance(text):
    if not text:
        return ""
    tol_indicator = r'(?:\((?:[±\u00b1]|\+/-\s*|\+-\s*|[+\-]\s*\d+)\s*\)?|\b(?:[±\u00b1]|\+/-\s*|\+-\s*))'
    t = re.sub(
        r'(\d+(?:\.\d+)?)\s*(kg|gm|gram|g|ml|ltr|liter|l)?\s*' + tol_indicator + r'\s*\d*(?:\.\d+)?\s*(kg|gm|gram|g|ml|ltr|liter|l)?\)?',
        lambda m: f"{m.group(1)} {m.group(2) or m.group(3) or ''}",
        text,
        flags=re.IGNORECASE
    )
    t = re.sub(r'\(?(?:[±\u00b1]|\+/-\s*|\+-\s*)\s*\d+(?:\.\d+)?\s*(?:kg|gm|gram|g|ml|ltr|liter|l)?\)?', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\(?(?:[±\u00b1]|\+/-\s*|\+-\s*)\)?', '', t)
    return t

def get_clean_display_unit(name, raw_unit):
    raw_str = str(raw_unit or '').strip()
    name_clean = clean_tolerance(name or "").strip()
    m_name = re.search(r'(\d+(\.\d+)?\s*(?:kg|gm|gram|g|ml|ltr|liter|l))\b', name_clean, re.IGNORECASE)
    if m_name:
        extracted = m_name.group(1).strip()
        if not raw_str or raw_str.lower() in ['n/a', 'each', 'piece', '1 piece', 'none', 'null', '']:
            return extracted
        m_raw = re.search(r'(\d+(\.\d+)?)\s*(?:kg|gm|gram|g|ml|ltr|liter|l)', raw_str, re.IGNORECASE)
        if m_raw:
            val_raw = float(m_raw.group(1))
            val_name = float(re.search(r'\d+(\.\d+)?', extracted).group())
            if val_raw != val_name and (name and ('±' in name or '(+)' in name or '(±)' in name or '+/-' in name)):
                return extracted
    return raw_str or 'N/A'

def parse_promotion(full_text):
    word_num = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
    multiplier = 1.0
    extra_free_weight_gm = 0.0
    extra_free_volume_ml = 0.0

    # 1. Check for Free Extra Weight/Volume notation like:
    # 500gm + 100gm Free, 500gm (100gm Free), + 50gm Free, with 50gm Free
    plus_free = re.search(r'(?:\+|\bplus\b|\bwith\b)\s*(\d+(?:\.\d+)?)\s*(kg|gm|gram|g|ml|ltr|liter|l)\s*(?:free|extra)?\b', full_text, re.IGNORECASE)
    if plus_free:
        f_val = float(plus_free.group(1))
        f_unit = plus_free.group(2).lower()
        if f_unit in ['gm', 'gram', 'g']:
            extra_free_weight_gm += f_val
        elif f_unit == 'kg':
            extra_free_weight_gm += f_val * 1000
        elif f_unit == 'ml':
            extra_free_volume_ml += f_val
        elif f_unit in ['ltr', 'liter', 'l']:
            extra_free_volume_ml += f_val * 1000

    # 2. Check for Buy X Get Ygm Free / Buy X Get Yml Free (Weight/Volume free)
    # e.g., Buy1 Get85gm Free, Buy 1 Get 85 gm Free, Buy 2 Get 300gm Free, Buy 1 Get Orange 250gm Free, Buy 2 Get 300gm S.Toast Free
    bg_weight = re.search(
        r'\bbuy\s*(\d+|one|two|three|four|five|six)?\s*(?:pcs?|packs?|pads?|bottles?|t\s*brush)?\s*(?:and|&)?\s*get\s*(?:[a-zA-Z\.\-]+\s*){0,3}?(\d+(?:\.\d+)?)\s*(kg|gm|gram|g|ml|ltr|liter|l)\s*(?:[a-zA-Z\.\-]+\s*){0,3}(?:free|extra)\b',
        full_text,
        re.IGNORECASE
    )
    if bg_weight:
        b_str = bg_weight.group(1)
        b_val = float(word_num.get(b_str.lower(), b_str) if b_str else 1)
        f_val = float(bg_weight.group(2))
        f_unit = bg_weight.group(3).lower()
        multiplier = b_val
        if f_unit in ['gm', 'gram', 'g']:
            extra_free_weight_gm += f_val
        elif f_unit == 'kg':
            extra_free_weight_gm += f_val * 1000
        elif f_unit == 'ml':
            extra_free_volume_ml += f_val
        elif f_unit in ['ltr', 'liter', 'l']:
            extra_free_volume_ml += f_val * 1000
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    # 3. Check for Buy X Get Y Free (Count multiplier)
    # e.g., Buy 1 Get 1 Free, Buy1 Get1 Free, Buy 2 Get 1, Buy2 Get1, B2G1, B1G1, B6G2, BOGO
    bg_count = re.search(
        r'\bbuy\s*(\d+|one|two|three|four|five|six)\s*(?:pcs?|packs?|pads?|bottles?|t\s*brush)?\s*(?:and|&)?\s*get\s*(\d+|one|two|three|four|five|six)\s*(?:pcs?|packs?|pads?|bottles?|t\s*brush)?\s*(?:free|combo|item|\b)',
        full_text,
        re.IGNORECASE
    )
    if bg_count:
        b_str = bg_count.group(1).lower()
        g_str = bg_count.group(2).lower()
        b_val = float(word_num.get(b_str, b_str))
        g_val = float(word_num.get(g_str, g_str))
        multiplier = b_val + g_val
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    # Shorthand B2G1, B1G1, B6G2
    b_short = re.search(r'\bb(\d+)g(\d+)\b', full_text, re.IGNORECASE)
    if b_short:
        multiplier = float(b_short.group(1)) + float(b_short.group(2))
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    if re.search(r'\bbogo\b', full_text, re.IGNORECASE):
        multiplier = 2.0
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    # 4. Check for Buy X Save Y Tk / Buy X Only Y Tk / Buy X For Y Tk / Buy X at Y Tk / Save Y Tk (Buy X)
    b_save = re.search(
        r'\bbuy\s*(\d+|one|two|three|four|five|six)\s*(?:pcs?|packs?|pads?|bottles?)?\s*(?:save|only|for|at|\btk\b|\bbdt\b|\btk\.\b|\b\d+\s*tk\b)',
        full_text,
        re.IGNORECASE
    )
    if b_save:
        b_str = b_save.group(1).lower()
        multiplier = float(word_num.get(b_str, b_str))
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    b_save_rev = re.search(
        r'(?:save|only|for|at)\s*(?:tk\b|\bbdt\b|tk\.\b|\b\d+\s*tk\b|\d+)\s*(?:[a-zA-Z0-9\s\.\-]{0,15}?)\(?\s*buy\s*(\d+|one|two|three|four|five|six)',
        full_text,
        re.IGNORECASE
    )
    if b_save_rev:
        b_str = b_save_rev.group(1).lower()
        multiplier = float(word_num.get(b_str, b_str))
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    # 5. Pack of X / Combo of X / Combo Pack (Buy X...)
    b_pack = re.search(r'\b(?:pack\s*of|combo\s*of|pack\s*x|combo\s*x)\s*(\d+)\b', full_text, re.IGNORECASE)
    if b_pack:
        multiplier = float(b_pack.group(1))
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    b_combo = re.search(r'combo\s*pack\s*\(?\s*buy\s*(\d+)', full_text, re.IGNORECASE)
    if b_combo:
        multiplier = float(b_combo.group(1))
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    return max(1.0, multiplier), extra_free_weight_gm, extra_free_volume_ml

def parse_unit_and_calculate(name, unit_str, price):
    if price is None:
        price = 0.0
    price = float(price)
    if price <= 0:
        return 'piece', price

    name_clean = clean_tolerance(name or "").lower()
    unit_clean = clean_tolerance(unit_str or "").lower()
    full_text = f"{unit_clean} {name_clean}".strip()

    multiplier, extra_free_weight_gm, extra_free_volume_ml = parse_promotion(full_text)

    for t_src in [name_clean, unit_clean]:
        mult_match1 = re.search(r'(\d+(\.\d+)?)\s*(kg|gm|gram|g|ml|ltr|l)\s*[xX*]\s*(\d+)', t_src)
        if mult_match1:
            val = float(mult_match1.group(1))
            unit = mult_match1.group(3)
            count = float(mult_match1.group(4))
            total_val = (val * count * multiplier)
            if unit in ['gm', 'gram', 'g']:
                total_gm = total_val + extra_free_weight_gm
                return 'kg', (price / total_gm) * 1000 if total_gm > 0 else price
            elif unit == 'kg':
                total_kg = total_val + (extra_free_weight_gm / 1000.0)
                return 'kg', price / total_kg if total_kg > 0 else price
            elif unit == 'ml':
                total_ml = total_val + extra_free_volume_ml
                return 'liter', (price / total_ml) * 1000 if total_ml > 0 else price
            else:
                total_l = total_val + (extra_free_volume_ml / 1000.0)
                return 'liter', price / total_l if total_l > 0 else price

        mult_match2 = re.search(r'(\d+)\s*(?:p|pcs?|packs?|x|\*)\s*[xX*]?\s*(\d+(\.\d+)?)\s*(kg|gm|gram|g|ml|ltr|l)\b', t_src)
        if mult_match2:
            count = float(mult_match2.group(1))
            val = float(mult_match2.group(2))
            unit = mult_match2.group(4)
            total_val = (val * count * multiplier)
            if unit in ['gm', 'gram', 'g']:
                total_gm = total_val + extra_free_weight_gm
                return 'kg', (price / total_gm) * 1000 if total_gm > 0 else price
            elif unit == 'kg':
                total_kg = total_val + (extra_free_weight_gm / 1000.0)
                return 'kg', price / total_kg if total_kg > 0 else price
            elif unit == 'ml':
                total_ml = total_val + extra_free_volume_ml
                return 'liter', (price / total_ml) * 1000 if total_ml > 0 else price
            else:
                total_l = total_val + (extra_free_volume_ml / 1000.0)
                return 'liter', price / total_l if total_l > 0 else price

    for t_src in [name_clean, unit_clean]:
        weight_match = re.search(r'(\d+(\.\d+)?)\s*(kg|gm|gram|g)\b', t_src)
        if weight_match:
            val = float(weight_match.group(1))
            unit = weight_match.group(3)
            if val > 0:
                if unit in ['gm', 'gram', 'g']:
                    total_gm = (val * multiplier) + extra_free_weight_gm
                    return 'kg', (price / total_gm) * 1000 if total_gm > 0 else price
                else:
                    total_kg = (val * multiplier) + (extra_free_weight_gm / 1000.0)
                    return 'kg', (price / total_kg) if total_kg > 0 else price

        volume_match = re.search(r'(\d+(\.\d+)?)\s*(ltr|liter|l|ml)\b', t_src)
        if volume_match:
            val = float(volume_match.group(1))
            unit = volume_match.group(3)
            if val > 0:
                if unit == 'ml':
                    total_ml = (val * multiplier) + extra_free_volume_ml
                    return 'liter', (price / total_ml) * 1000 if total_ml > 0 else price
                else:
                    total_l = (val * multiplier) + (extra_free_volume_ml / 1000.0)
                    return 'liter', (price / total_l) if total_l > 0 else price

    for t_src in [name_clean, unit_clean]:
        piece_match = re.search(r'(\d+)\s*(?:pcs|pc|piece|pieces|pads|pad|hali|dozen|can|bottle|box|pkt|pack|sachet)\b', t_src)
        if piece_match:
            pcs = float(piece_match.group(1))
            if pcs > 0:
                total_pcs = pcs * multiplier
                return 'piece', price / total_pcs if total_pcs > 0 else price

    if multiplier > 1:
        return 'piece', price / multiplier

    if any(x in full_text for x in ['pc', 'piece', 'hali', 'dozen', 'pkt', 'pack', 'each', 'bottle', 'can', 'box', 'bar', 'hanger', 'sachet']):
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
        stats = {"web_scraped": 0, "app_scraped": 0, "web_selected": 0, "app_selected": 0,
                 "dropped": 0, "web": 0, "app": 0, "combined": 0}
        all_dates = []

        # 1. Load Web Data
        data = safe_load_json(SHWAPNO_DATA)
        if data:
            try:
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
                        "category": get_display_cat(p.get('category', 'General')), "unit": get_clean_display_unit(p.get('name', ''), p.get('unit', 'N/A')), "unit_type": u_type,
                        "current_price": curr_p, "normalized_price": norm_p,
                        "image": p.get('image'), "url": p.get('url'), "history": new_history, "first_seen": first_seen,
                        "_src": "web"
                    }
                    stats["web_scraped"] += 1
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
                    
                    stats["app_scraped"] += 1
                    final_pid = f"sh_{p.get('id')}"
                    
                    hist_dict = p.get('price_history', {})
                    unique_hist = {}
                    for d_str, price_val in hist_dict.items():
                        _, h_norm = parse_unit_and_calculate(p.get('name', ''), p.get('unit', ''), price_val)
                        unique_hist[d_str] = {"date": d_str, "price": price_val, "normalized_price": h_norm}

                    # Check for collision with existing web data
                    if name_key in products_by_name:
                        existing = products_by_name[name_key]
                        e_curr = existing.get('current_price', 0) or 0
                        # Merge history from existing item
                        for eh in existing.get('history', []):
                            if eh.get('date') and eh['date'] not in unique_hist:
                                unique_hist[eh['date']] = eh

                        # If existing web item has a valid lower price, keep web item but update history
                        if e_curr > 0 and (curr_p <= 0 or e_curr <= curr_p):
                            existing_hist = sorted(unique_hist.values(), key=lambda x: x['date'])
                            existing['history'] = existing_hist
                            if existing_hist:
                                existing['first_seen'] = existing_hist[0]['date']
                            stats["dropped"] += 1
                            continue
                            
                    new_history = sorted(unique_hist.values(), key=lambda x: x['date'])
                    for h in new_history: all_dates.append(h['date'])
                    first_seen = new_history[0]['date'] if new_history else datetime.now(DHAKA_TZ).strftime("%Y-%m-%d")
                    
                    url = p.get('url', '')
                    if url and not url.startswith('http'):
                        url = f"https://www.shwapno.com/{url}"

                    products_by_name[name_key] = {
                        "id": final_pid, "name": p.get('name'), "store": "shwapno",
                        "category": get_display_cat(p.get('category', 'General')), "unit": get_clean_display_unit(p.get('name', ''), p.get('unit', 'N/A')), "unit_type": u_type,
                        "current_price": curr_p, "normalized_price": norm_p,
                        "image": p.get('image'), "url": url, "history": new_history, "first_seen": first_seen,
                        "_src": "app"
                    }
                stats["app_selected"] = sum(1 for v in products_by_name.values() if v.get("_src") == "app")
            except Exception as e:
                print(f"Error loading Shwapno App data: {e}")

        products = {v["id"]: v for v in products_by_name.values()}
        stats["web_selected"] = len([v for v in products_by_name.values() if v.get("_src") == "web"])
        stats["app_selected"] = sum(1 for v in products_by_name.values() if v.get("_src") == "app")
        stats["combined"] = len(products)
        for v in products.values(): v.pop("_src", None)
        stats["web"] = stats["web_scraped"]; stats["app"] = stats["app_scraped"]
        print(f"Shwapno Stats -> Web scraped: {stats['web_scraped']}, Web selected: {stats['web_selected']}, "
              f"App scraped: {stats['app_scraped']}, App selected: {stats['app_selected']}, "
              f"Dropped: {stats['dropped']}, Combined Unique: {stats['combined']}")

        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error processing Shwapno: {e}")
        return None, None

def load_chaldal():
    print("Processing Chaldal...")
    target_chaldal = CHALDAL_DATA
    if not os.path.exists(target_chaldal):
        for candidate in ['chaldalTRACKER/data.js', 'chaldalTRACKER/chaldal_products.json', 'chaldalTRACKER/data.json']:
            if os.path.exists(candidate):
                target_chaldal = candidate
                break
    try:
        products_by_name = {}
        all_dates = []

        def add_product(name_key, product, source):
            if not name_key: return
            if name_key in products_by_name:
                existing = products_by_name[name_key]
                e_curr = existing.get('current_price', 0) or 0
                p_curr = product.get('current_price', 0) or 0
                
                # Merge histories across web & app
                unique_h = {h['date']: h for h in existing.get('history', []) if h.get('date')}
                for h in product.get('history', []):
                    if h.get('date') and h['date'] not in unique_h:
                        unique_h[h['date']] = h
                merged_h = sorted(unique_h.values(), key=lambda x: x['date'])
                
                if e_curr > 0 and (p_curr <= 0 or e_curr <= p_curr):
                    existing['history'] = merged_h
                    stats["dropped"] += 1
                    return
                product['history'] = merged_h
            products_by_name[name_key] = product

        stats = {"web_scraped": 0, "app_scraped": 0, "web_selected": 0, "app_selected": 0,
                 "dropped": 0, "web": 0, "app": 0, "combined": 0}

        # 1. Load Web data (data.js) if present
        if os.path.exists(target_chaldal):
            try:
                with open(target_chaldal, 'r', encoding='utf-8') as f:
                    content = f.read()
                start, end = content.find('{'), content.rfind('}') + 1
                if start != -1 and end != 0:
                    data = json.loads(content[start:end])
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
                        name_key = re.sub(r'\W+', '', p.get('name', '')).lower()
                        if not name_key: continue
                        stats["web_scraped"] += 1
                        add_product(name_key, {
                            "id": f"ch_{pid}", "name": p.get('name'), "store": "chaldal",
                            "category": p.get('category', 'General'), "unit": get_clean_display_unit(p.get('name', ''), p.get('current_unit')), "unit_type": u_type,
                            "current_price": curr_p, "normalized_price": norm_p,
                            "image": p.get('image'), "history": new_history, "_src": "web"
                        }, "web")
            except Exception as e:
                print(f"Error loading Chaldal web data: {e}")

        # 2. Load App API data (chaldalTRACKER/data/products.json + price_history.json)
        app_prod_path = os.path.join('chaldalTRACKER', 'data', 'products.json')
        app_hist_path = os.path.join('chaldalTRACKER', 'data', 'price_history.json')
        if not os.path.exists(app_prod_path):
            app_prod_path = os.path.join(target_chaldal, '..', '..', 'data', 'products.json') if target_chaldal.startswith('chaldalTRACKER') else app_prod_path
        if os.path.exists(app_prod_path):
            try:
                with open(app_prod_path, 'r', encoding='utf-8') as f:
                    app_data = json.load(f)
                app_history = {}
                if os.path.exists(app_hist_path):
                    with open(app_hist_path, 'r', encoding='utf-8') as f:
                        app_history = json.load(f)
                for pid, p in app_data.items():
                    name_key = re.sub(r'\W+', '', p.get('name', '')).lower()
                    if not name_key: continue
                    stats["app_scraped"] += 1
                    curr_p = p.get('price', 0) or 0
                    u_type, norm_p = parse_unit_and_calculate(p.get('name', ''), '', curr_p)
                    new_history = []
                    for h in app_history.get(str(pid), []) or app_history.get(pid, []):
                        d_str = h.get('d')
                        price_val = h.get('p')
                        if d_str:
                            _, h_norm = parse_unit_and_calculate(p.get('name', ''), '', price_val)
                            new_history.append({"date": d_str, "price": price_val, "normalized_price": h_norm})
                            all_dates.append(d_str)
                    if not new_history:
                        new_history = [{"date": datetime.now(DHAKA_TZ).strftime("%Y-%m-%d"), "price": curr_p, "normalized_price": norm_p}]
                    img = p.get('imageUrl') or p.get('image_url') or ''
                    add_product(name_key, {
                        "id": f"ch_a_{pid}", "name": p.get('name'), "store": "chaldal",
                        "category": p.get('category', 'General'), "unit": get_clean_display_unit(p.get('name', ''), ''), "unit_type": u_type,
                        "current_price": curr_p, "normalized_price": norm_p,
                        "image": img, "history": new_history, "_src": "app"
                    }, "app")
            except Exception as e:
                print(f"Error loading Chaldal App data: {e}")

        products = {v["id"]: v for v in products_by_name.values()}
        stats["web_selected"] = len([v for v in products_by_name.values() if v.get("_src") == "web"])
        stats["app_selected"] = sum(1 for v in products_by_name.values() if v.get("_src") == "app")
        stats["combined"] = len(products)
        stats["web"] = stats["web_scraped"]; stats["app"] = stats["app_scraped"]
        for v in products.values(): v.pop("_src", None)
        print(f"Chaldal Stats -> Web scraped: {stats['web_scraped']}, Web selected: {stats['web_selected']}, "
              f"App scraped: {stats['app_scraped']}, App selected: {stats['app_selected']}, "
              f"Dropped: {stats['dropped']}, Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error processing Chaldal: {e}")
        return None, None

def load_meenabazar():
    print("Processing Meena Bazar...")
    if not os.path.exists(MEENA_DB): stats={"web_scraped":0,"app_scraped":0,"web_selected":0,"app_selected":0,"dropped":0,"web":0,"app":0,"combined":0}; print(f"Meenabazar Stats -> Web scraped: 0, Web selected: 0, App scraped: 0, App selected: 0, Combined Unique: 0"); return {}, "N/A", stats
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
        products_by_name = {}
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
            pid = f"mb_{p['external_id'] or p['id']}"
            prod_obj = {
                "id": pid, "name": p['name'], "store": "meenabazar",
                "category": cats.get(p['category_id'], 'General'), "unit": get_clean_display_unit(p['name'], p['unit']), "unit_type": u_type,
                "current_price": curr_p, "normalized_price": norm_p,
                "image": p['image_url'], "history": new_history, "_src": "web"
            }
            products[pid] = prod_obj
            name_key = re.sub(r'\W+', '', p['name'] or '').lower()
            if name_key:
                products_by_name[name_key] = prod_obj
        conn.close()
        app_count = 0
        cat_path = 'MEENAtracker/catalog.json'
        cat_data = {}
        if os.path.exists(cat_path):
            try:
                with open(cat_path, 'r', encoding='utf-8') as cf:
                    cat_data = json.load(cf)
                    for p in cat_data.get("products", []):
                        name_key = re.sub(r'\W+', '', p.get('name', '')).lower()
                        curr_p = float(p.get('price', 0) or 0)
                        u_type, norm_p = parse_unit_and_calculate(p.get('name', ''), '', curr_p)
                        today_str = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d")
                        app_hist = [{"date": today_str, "price": curr_p, "normalized_price": norm_p}]
                        
                        if name_key and name_key in products_by_name:
                            existing = products_by_name[name_key]
                            e_curr = existing.get('current_price', 0) or 0
                            # Merge history
                            unique_h = {h['date']: h for h in existing.get('history', []) if h.get('date')}
                            if today_str not in unique_h and curr_p > 0:
                                unique_h[today_str] = app_hist[0]
                            existing['history'] = sorted(unique_h.values(), key=lambda x: x['date'])
                            if curr_p > 0 and (e_curr <= 0 or curr_p < e_curr):
                                existing['current_price'] = curr_p
                                existing['normalized_price'] = norm_p
                                existing['_src'] = 'app'
                            continue

                        pid = f"mb_a_{p.get('id')}"
                        app_count += 1
                        new_prod = {
                            "id": pid, "name": p.get('name'), "store": "meenabazar",
                            "category": p.get('category', 'General') if isinstance(p.get('category'), str) else 'General',
                            "unit": get_clean_display_unit(p.get('name', ''), 'N/A'), "unit_type": u_type,
                            "current_price": curr_p, "normalized_price": norm_p,
                            "image": p.get('image', ''), "history": app_hist,
                            "source": "app", "_src": "app"
                        }
                        products[pid] = new_prod
                        if name_key:
                            products_by_name[name_key] = new_prod
            except Exception as _ce:
                print(f"Meena Bazar catalog.json notice: {_ce}")

        web_scraped = len(db_p)
        app_scraped = len(cat_data.get("products", [])) if os.path.exists(cat_path) else 0
        stats = {"web_scraped": web_scraped, "app_scraped": app_scraped,
                 "web_selected": sum(1 for v in products.values() if v.get("_src") == "web"),
                 "app_selected": sum(1 for v in products.values() if v.get("_src") == "app"),
                 "dropped": (web_scraped + app_scraped) - len(products),
                 "web": web_scraped, "app": app_scraped, "combined": len(products)}
        for v in products.values(): v.pop("_src", None)
        print(f"Meenabazar Stats -> Web scraped: {stats['web_scraped']}, Web selected: {stats['web_selected']}, "
              f"App scraped: {stats['app_scraped']}, App selected: {stats['app_selected']}, "
              f"Dropped: {stats['dropped']}, Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error Meena Bazar: {e}")
        return None, None

def is_othoba_grocery_category(cat_name):
    if not cat_name: return False
    cl = str(cat_name).lower().strip()
    non_grocery = ['mother', 'baby', 'toy', 'beauty', 'care', 'cosmetic', 'pharmacy', 'medicine', 'pet', 'fashion', 'cloth', 'shoe', 'electronics', 'automotive', 'stationery', 'book', 'furniture', 'table', 'pad', 'freezer', 'home appliance', 'garden', 'tool', 'watch', 'phone', 'gadget', 'soil', 'fertilizer', 'cleaner', 'toilet', 'detergent', 'dishwash', 'floor', 'glass', 'umbrella', 'fan', 'tv', 'refrigerator', 'light', 'lamp', 'camera', 'laptop', 'cable', 'modem', 'router', 'drill', 'saw', 'paint', 'pipe', 'lock']
    if any(ex in cl for ex in non_grocery):
        return False
    grocery_kw = [
        'daily-bazar', 'daily bazar', 'daily-shopping', 'daily shopping', 'food-grocery', 'food & grocery', 'grocery', 'bogo', 'mega-discount', 'monthly-grocery',
        'grocery-staples', 'bakery-breakfast', 'daily-cooking', 'spice-herb', 'baking', 'dairy-chilled-eggs', 'eggs', 'milk',
        'cheese', 'yogurt', 'butter', 'laban', 'borhani', 'ghee', 'meat', 'fish', 'vegetable', 'fruit', 'snack', 'sweetmeat',
        'bakery-snacks', 'beverage', 'tea', 'coffee', 'rice', 'dal', 'oil', 'spice', 'quick-commerce', 'mithai', 'flour', 'noodles', 'bazar'
    ]
    return any(k in cl for k in grocery_kw)

def load_othoba():
    print("Processing Othoba (Grocery Categories Only)...")
    try:
        products_by_name = {}
        stats = {"web_scraped": 0, "app_scraped": 0, "web_selected": 0, "app_selected": 0,
                 "dropped": 0, "web": 0, "app": 0, "combined": 0}
        all_dates = []

        def process_json_file(filepath, source_type):
            if not os.path.exists(filepath): return
            try:
                import json, re, platform
                from datetime import datetime
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for p in data:
                    cat = p.get('category') or p.get('category_path') or ''
                    if not is_othoba_grocery_category(cat):
                        continue

                    name_key = re.sub(r'\W+', '', p.get('name', '')).lower()
                    if not name_key: continue
                    
                    stats[source_type + "_scraped"] += 1
                    curr_p = p.get('current_price', 0)
                    u_type, norm_p = parse_unit_and_calculate(p.get('name', ''), p.get('unit', ''), curr_p)
                    
                    hist_dict = p.get('price_history', {})
                    unique_hist = {}
                    
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

                    if name_key in products_by_name:
                        existing = products_by_name[name_key]
                        e_curr = existing.get('current_price', 0) or 0
                        for eh in existing.get('history', []):
                            if eh.get('date') and eh['date'] not in unique_hist:
                                unique_hist[eh['date']] = eh
                        if e_curr > 0 and (curr_p <= 0 or e_curr <= curr_p):
                            existing_hist = sorted(unique_hist.values(), key=lambda x: x['date'])
                            existing['history'] = existing_hist
                            stats["dropped"] += 1
                            continue
                            
                    final_pid = p.get('id')
                    if not final_pid.startswith('ot_'): final_pid = f"ot_{final_pid}"
                        
                    new_history = sorted(unique_hist.values(), key=lambda x: x['date'])
                    if not new_history:
                        today_str = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d")
                        new_history = [{"date": today_str, "price": curr_p, "normalized_price": norm_p}]
                    for h in new_history:
                        if h.get('date'): all_dates.append(h['date'])
                    
                    first_seen = p.get('first_seen')
                    if not first_seen:
                        first_seen = new_history[0]['date'] if new_history else datetime.now(DHAKA_TZ).strftime("%Y-%m-%d")

                    products_by_name[name_key] = {
                        "id": final_pid, "name": p.get('name'), "store": "othoba",
                        "category": cat or 'Grocery', "unit": get_clean_display_unit(p.get('name', ''), p.get('unit', 'N/A')), "unit_type": u_type,
                        "current_price": curr_p, "normalized_price": norm_p,
                        "image": p.get('image'), "history": new_history, "first_seen": first_seen,
                        "_src": source_type
                    }
            except Exception as e:
                print(f"Error loading Othoba {source_type} data from {filepath}: {e}")

        def add_product(name_key, product, source):
            if not name_key: return
            if name_key in products_by_name:
                existing = products_by_name[name_key]
                e_curr = existing.get('current_price', 0) or 0
                p_curr = product.get('current_price', 0) or 0
                
                # Merge histories across web & app
                unique_h = {h['date']: h for h in existing.get('history', []) if h.get('date')}
                for h in product.get('history', []):
                    if h.get('date') and h['date'] not in unique_h:
                        unique_h[h['date']] = h
                merged_h = sorted(unique_h.values(), key=lambda x: x['date'])
                
                if e_curr > 0 and (p_curr <= 0 or e_curr <= p_curr):
                    existing['history'] = merged_h
                    stats["dropped"] += 1
                    return
                product['history'] = merged_h
            products_by_name[name_key] = product

        # 1. Load Web Data (website scraper DB, decrypted from .db.enc at runtime)
        web_db_candidates = ['othobaTRACKER/othoba_tracker.db']
        web_db = next((p for p in web_db_candidates if os.path.exists(p)), None)
        if web_db:
            try:
                conn = sqlite3.connect(web_db)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT product_id, timestamp, price_amount FROM price_history ORDER BY timestamp ASC")
                all_hist_by_pid = defaultdict(list)
                for hrow in cursor.fetchall():
                    all_hist_by_pid[hrow["product_id"]].append(hrow)

                cursor.execute("SELECT id, name, category_name, image_url FROM products")
                for r in cursor.fetchall():
                    cat = r["category_name"] or 'General'
                    if not is_othoba_grocery_category(cat):
                        continue

                    name_key = re.sub(r'\W+', '', r["name"] or "").lower()
                    if not name_key: continue
                    hist_rows = all_hist_by_pid.get(r["id"], [])
                    price = float(hist_rows[-1]["price_amount"]) if hist_rows else 0
                    u_type, norm_p = parse_unit_and_calculate(r["name"] or "", '', price)
                    unique_hist = {}
                    for hrow in hist_rows:
                        d_str = str(hrow["timestamp"])[:10]
                        unique_hist[d_str] = {"date": d_str, "price": float(hrow["price_amount"] or 0), "normalized_price": norm_p}
                    new_history = sorted(unique_hist.values(), key=lambda x: x['date'])
                    if not new_history:
                        today_str = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d")
                        new_history = [{"date": today_str, "price": price, "normalized_price": norm_p}]
                    for h in new_history:
                        if h.get('date'): all_dates.append(h['date'])
                    stats["web_scraped"] += 1
                    add_product(name_key, {
                        "id": f"ot_{r['id']}", "name": r["name"], "store": "othoba",
                        "category": cat, "unit": get_clean_display_unit(r["name"], 'N/A'), "unit_type": u_type,
                        "current_price": price, "normalized_price": norm_p,
                        "image": r["image_url"] or '', "history": new_history, "first_seen": datetime.now(DHAKA_TZ).strftime("%Y-%m-%d"),
                        "_src": "web"
                    }, "web")
                conn.close()
                print(f"[Othoba] Web data loaded from DB: {stats['web_scraped']} products")
            except Exception as e:
                print(f"Error reading Othoba DB: {e}")

        # 1b. JSON fallback as web if DB missing/empty
        if stats["web_scraped"] == 0:
            web_path = 'othobaTRACKER/frontend/othoba_products.json'
            process_json_file(web_path, 'web')

        # 2. Load App Data (mobile app API scraper JSON)
        app_path = 'othobaTRACKER/frontend/othoba_products.json'
        process_json_file(app_path, 'app')

        products = {v["id"]: v for v in products_by_name.values()}
        stats["web_selected"] = sum(1 for v in products_by_name.values() if v.get("_src") == "web")
        stats["app_selected"] = sum(1 for v in products_by_name.values() if v.get("_src") == "app")
        for v in products.values(): v.pop("_src", None)
        stats["combined"] = len(products)
        stats["web"] = stats["web_scraped"]; stats["app"] = stats["app_scraped"]
        print(f"Othoba Stats -> Web scraped: {stats['web_scraped']}, Web selected: {stats['web_selected']}, "
              f"App scraped: {stats['app_scraped']}, App selected: {stats['app_selected']}, "
              f"Dropped: {stats['dropped']}, Combined Unique: {stats['combined']}")

        valid_dates = [d for d in all_dates if d and isinstance(d, str) and len(d) == 10]
        return products, (f"{min(valid_dates)} to {max(valid_dates)}" if valid_dates else "N/A"), stats
    except Exception as e:
        print(f"Error Othoba: {e}")
        return None, None

def load_metromart():
    print("Processing Metro Mart...")
    if not os.path.exists(METRO_DB): stats={"web_scraped":0,"app_scraped":0,"web_selected":0,"app_selected":0,"dropped":0,"web":0,"app":0,"combined":0}; print(f"Metromart Stats -> Web scraped: 0, Web selected: 0, App scraped: 0, App selected: 0, Combined Unique: 0"); return {}, "N/A", stats
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
                "category": cats.get(p['category_id'], 'General'), "unit": get_clean_display_unit(p['name'], p['unit']), "unit_type": u_type,
                "current_price": curr_p, "normalized_price": norm_p, "image": img, "history": new_history
            }
        conn.close()
        stats = {"web_scraped": len(products), "app_scraped": 0, "web_selected": len(products),
                 "app_selected": 0, "dropped": 0, "web": len(products), "app": 0, "combined": len(products)}
        print(f"Metromart Stats -> Web scraped: {stats['web_scraped']}, Web selected: {stats['web_selected']}, "
              f"App scraped: 0, App selected: 0, Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error Metro Mart: {e}")
        return None, None

def load_unimart():
    print("Processing Unimart...")
    if not os.path.exists(UNIMART_DATA): stats={"web_scraped":0,"app_scraped":0,"web_selected":0,"app_selected":0,"dropped":0,"web":0,"app":0,"combined":0}; print(f"Unimart Stats -> Web scraped: 0, Web selected: 0, App scraped: 0, App selected: 0, Combined Unique: 0"); return {}, "N/A", stats
    try:
        data = safe_load_json(UNIMART_DATA)
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
                "category": p.get('category', 'General'), "unit": get_clean_display_unit(p.get('name', ''), p.get('unit')), "unit_type": u_type,
                "current_price": curr_p, "normalized_price": norm_p, "image": p.get('image'), "history": new_history
            }
        stats = {"web_scraped": len(products), "app_scraped": 0, "web_selected": len(products),
                 "app_selected": 0, "dropped": 0, "web": len(products), "app": 0, "combined": len(products)}
        print(f"Unimart Stats -> Web scraped: {stats['web_scraped']}, Web selected: {stats['web_selected']}, "
              f"App scraped: 0, App selected: 0, Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error Unimart: {e}"); return None, None

def load_shotejbazar():
    print("Processing ShotejBazar...")
    if not os.path.exists(SHOTEJ_DATA): stats={"web_scraped":0,"app_scraped":0,"web_selected":0,"app_selected":0,"dropped":0,"web":0,"app":0,"combined":0}; print(f"Shotejbazar Stats -> Web scraped: 0, Web selected: 0, App scraped: 0, App selected: 0, Combined Unique: 0"); return {}, "N/A", stats
    try:
        data = safe_load_json(SHOTEJ_DATA)
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
                "category": p.get('category', 'General'), "unit": get_clean_display_unit(p.get('name', ''), p.get('unit')), "unit_type": u_type,
                "current_price": curr_p, "normalized_price": norm_p, "image": p.get('image'), "history": new_history, "first_seen": first_seen
            }
        stats = {"web_scraped": len(products), "app_scraped": 0, "web_selected": len(products),
                 "app_selected": 0, "dropped": 0, "web": len(products), "app": 0, "combined": len(products)}
        print(f"Shotejbazar Stats -> Web scraped: {stats['web_scraped']}, Web selected: {stats['web_selected']}, "
              f"App scraped: 0, App selected: 0, Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error ShotejBazar: {e}"); return None, None

def load_foodi():
    print("Processing Foodi...")
    if not os.path.exists(FOODI_DB): stats={"web_scraped":0,"app_scraped":0,"web_selected":0,"app_selected":0,"dropped":0,"web":0,"app":0,"combined":0}; print(f"Foodi Stats -> Web scraped: 0, Web selected: 0, App scraped: 0, App selected: 0, Combined Unique: 0"); return {}, "N/A", stats
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
                "category": p['category_name'] or 'General', "unit": get_clean_display_unit(p['name'], unit_str), "unit_type": u_type,
                "current_price": curr_p, "normalized_price": norm_p, "image": img, "history": new_history, "first_seen": first_seen
            }
        conn.close()
        stats = {"web_scraped": 0, "app_scraped": len(products), "web_selected": 0,
                 "app_selected": len(products), "dropped": 0, "web": 0, "app": len(products), "combined": len(products)}
        print(f"Foodi Stats -> App scraped: {stats['app_scraped']}, App selected: {stats['app_selected']}, "
              f"Combined Unique: {stats['combined']}")
        return products, (f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"), stats
    except Exception as e:
        print(f"Error Foodi: {e}"); return None, None

# --- ATOMIC CHUNKING ENGINE ---
# Which data source(s) each store actually scrapes: web-only, app-only, or both.
# foodi = app API only; metromart/unimart/shotejbazar = web only; rest = both.
STORE_SOURCES = {
    'shwapno': 'both', 'chaldal': 'both', 'meenabazar': 'both', 'othoba': 'both',
    'metromart': 'web', 'unimart': 'web', 'shotejbazar': 'web', 'foodi': 'app',
}

def save_store_data(name, data_tuple):
    if not data_tuple: return None
    
    scraper_stats = None
    if len(data_tuple) == 3:
        products, date_range, scraper_stats = data_tuple
    else:
        products, date_range = data_tuple
        
    if not products:
        summary = f"🏪 <b>{name.title()}</b>: 0 items"
        if scraper_stats:
            _mode = STORE_SOURCES.get(name, 'both')
            if _mode in ('web', 'both'):
                summary += f"\n   ├ Web: {scraper_stats.get('web_scraped', 0):,} scraped | {scraper_stats.get('web_selected', 0):,} selected"
            if _mode in ('app', 'both'):
                summary += f"\n   ├ App: {scraper_stats.get('app_scraped', 0):,} scraped | {scraper_stats.get('app_selected', 0):,} selected"
            if date_range:
                summary += f"\n   ├ 📅 Price data: {date_range}"
        print(f"Saved {name:15} | Items:     0 | Chunks:  0 | Safe Under {MAX_FILE_SIZE_MB}MB")
        return summary, {'total': 0, 'in_stock': 0, 'out_of_stock': 0, 'new_items': 0, 'price_up': 0, 'price_down': 0, 'price_same': 0, 'back_in_stock': 0, 'went_oos': 0}

    # Standardize first_seen, last_seen, and stock flags for every product
    in_stock_cnt = 0
    out_of_stock_cnt = 0
    new_items_cnt = 0
    price_up_cnt = 0
    price_down_cnt = 0
    price_same_cnt = 0
    back_in_stock_cnt = 0
    went_oos_cnt = 0

    for pid, p in products.items():
        v_hist = p.get('history', [])
        valid_dates = [str(h['date'])[:10] for h in v_hist if h.get('date')]
        if valid_dates:
            p['first_seen'] = min(valid_dates)
            p['last_seen'] = max(valid_dates)
        else:
            p['first_seen'] = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d")
            p['last_seen'] = p['first_seen']
        curr_p = float(p.get('current_price', 0) or 0)
        p['in_stock'] = bool(curr_p > 0 and p.get('in_stock', True) is not False)
        p['is_out_of_stock'] = not p['in_stock']

        if p['in_stock']:
            in_stock_cnt += 1
        else:
            out_of_stock_cnt += 1

        for h in v_hist:
            if float(h.get('price', 0) or 0) <= 0 or h.get('is_out_of_stock') is True:
                h['price'] = -1.0
                h['normalized_price'] = -1.0

        if len(v_hist) <= 1:
            new_items_cnt += 1
        else:
            curr_h_p = float(v_hist[-1].get('price', -1.0) or -1.0)
            prev_h_p = float(v_hist[-2].get('price', -1.0) or -1.0)

            if curr_h_p > 0 and prev_h_p > 0:
                if curr_h_p > prev_h_p:
                    price_up_cnt += 1
                elif curr_h_p < prev_h_p:
                    price_down_cnt += 1
                else:
                    price_same_cnt += 1
            elif curr_h_p <= 0 and prev_h_p > 0:
                went_oos_cnt += 1
            elif curr_h_p > 0 and prev_h_p <= 0:
                back_in_stock_cnt += 1

    total_items = len(products)
    last_update = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    product_items = sorted(products.items())
    
    # 1. Atomic Size-Budget Chunk Builder
    # Pre-clean existing files to avoid ghosts
    for f in os.listdir('.'):
        if f.startswith(f"{name}_data_part") and f.endswith(".js"):
            try: os.remove(f)
            except: pass

    max_bytes = int(MAX_FILE_SIZE_MB * 1024 * 1024 * 0.90)  # Safe ~40.5MB cap
    temp_chunks = []
    current_chunk = {}
    current_bytes = 2  # '{}'

    for pid, pdata in product_items:
        item_str = json.dumps({pid: pdata}, separators=(',', ':'))[1:-1]
        item_bytes = len(item_str.encode('utf-8')) + 1

        if current_chunk and (current_bytes + item_bytes > max_bytes or len(current_chunk) >= MAX_CHUNK_ITEMS):
            temp_chunks.append(current_chunk)
            current_chunk = {pid: pdata}
            current_bytes = item_bytes + 2
        else:
            current_chunk[pid] = pdata
            current_bytes += item_bytes

    if current_chunk:
        temp_chunks.append(current_chunk)

    total_chunks = len(temp_chunks)
    current_chunk_size = MAX_CHUNK_ITEMS
    
    # 2. Save Manifest
    manifest_meta = {
        "last_update": last_update, "total": total_items,
        "date_range": date_range, "total_chunks": total_chunks, "chunk_size": current_chunk_size,
        "stock_stats": {
            "in_stock": in_stock_cnt,
            "out_of_stock": out_of_stock_cnt,
            "new_items": new_items_cnt,
            "price_up": price_up_cnt,
            "price_down": price_down_cnt,
            "price_same": price_same_cnt,
            "back_in_stock": back_in_stock_cnt,
            "went_oos": went_oos_cnt
        }
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
            
    summary = f"🏪 <b>{name.upper()}</b>: {total_items:,} items ({total_chunks} chunks)"
    if scraper_stats:
        _mode = STORE_SOURCES.get(name, 'both')
        if _mode in ('web', 'both'):
            summary += f"\n   ├ Web: {scraper_stats.get('web_scraped', 0):,} scraped | {scraper_stats.get('web_selected', 0):,} selected"
        if _mode in ('app', 'both'):
            summary += f"\n   ├ App: {scraper_stats.get('app_scraped', 0):,} scraped | {scraper_stats.get('app_selected', 0):,} selected"
    def _p(val):
        return f"({(val / total_items * 100):.1f}%)" if total_items > 0 else "(0.0%)"

    summary += f"\n   ├ 🟢 In Stock: {in_stock_cnt:,} {_p(in_stock_cnt)} | 🔴 Out of Stock: {out_of_stock_cnt:,} {_p(out_of_stock_cnt)}"
    if new_items_cnt > 0:
        summary += f"\n   ├ 🆕 New Items: {new_items_cnt:,} {_p(new_items_cnt)}"
    
    price_parts = []
    if price_up_cnt > 0: price_parts.append(f"🔺 {price_up_cnt:,} {_p(price_up_cnt)} up")
    if price_down_cnt > 0: price_parts.append(f"🔻 {price_down_cnt:,} {_p(price_down_cnt)} down")
    if price_same_cnt > 0: price_parts.append(f"⏸️ {price_same_cnt:,} {_p(price_same_cnt)} same")
    if price_parts:
        summary += f"\n   ├ 🏷️ Prices: " + " | ".join(price_parts)

    stock_delta = []
    if back_in_stock_cnt > 0: stock_delta.append(f"🟢 {back_in_stock_cnt:,} {_p(back_in_stock_cnt)} restocked")
    if went_oos_cnt > 0: stock_delta.append(f"🔴 {went_oos_cnt:,} {_p(went_oos_cnt)} went OOS")
    if stock_delta:
        summary += f"\n   ├ 🔄 Stock Movements: " + " | ".join(stock_delta)

    if date_range:
        summary += f"\n   ├ 📅 Price data: {date_range}"
        
    print(f"Saved {name:15} | Items: {total_items:5} | Chunks: {total_chunks:2} | Safe Under {MAX_FILE_SIZE_MB}MB")
    return summary, {
        'total': total_items,
        'in_stock': in_stock_cnt,
        'out_of_stock': out_of_stock_cnt,
        'new_items': new_items_cnt,
        'price_up': price_up_cnt,
        'price_down': price_down_cnt,
        'price_same': price_same_cnt,
        'back_in_stock': back_in_stock_cnt,
        'went_oos': went_oos_cnt,
        'date_range': date_range,
        'scraper_stats': scraper_stats,
        'chunks': total_chunks
    }

def read_scraper_log(store_dir):
    candidates = [
        os.path.join(store_dir, 'last_run_log.txt'),
        os.path.join(store_dir, 'last_run_logs.txt'),
        os.path.join(store_dir, 'data', 'logs', 'lastrun.log'),
        os.path.join(store_dir, 'scraper.log'),
    ]
    content = None
    for log_path in candidates:
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if content and content.strip():
                    break
            except Exception:
                continue
    if content is None or not content.strip():
        return None

    def grab(pattern):
        m = re.search(pattern, content)
        return int(m.group(1)) if m else None

    stats = {}
    stats['total'] = grab(r'Total Scraped:\s*(\d+)')
    stats['web'] = grab(r'Web Scraped:\s*(\d+)')
    stats['app'] = grab(r'App API Scraped:\s*(\d+)')
    stats['new'] = grab(r'New Items:\s*(\d+)')
    stats['combined'] = grab(r'Combined Unique:\s*(\d+)')
    stats['total'] = stats['total'] or grab(r'Unique products:\s*(\d+)')
    stats['new'] = stats['new'] or grab(r'New products:\s*(\d+)')
    m = re.search(r'Stats -> Web:\s*(\d+),\s*App:\s*(\d+)', content)
    if m:
        stats['web'] = int(m.group(1)); stats['app'] = int(m.group(2))
    if stats['total'] is None and stats['web'] is not None and stats['app'] is not None:
        stats['total'] = (stats['web'] or 0) + (stats['app'] or 0)
    return stats

def print_failure_diagnostics(scraper_logs, agg_results):
    print("\n" + "="*70 + "\nSCRAPER DIAGNOSTICS // claimed vs aggregated\n" + "="*70)
    for store, log in scraper_logs.items():
        res = agg_results.get(store, {})
        claimed_total = (log.get('total') or 0) if log else None
        claimed_web = (log.get('web') or 0) if log else 0
        claimed_app = (log.get('app') or 0) if log else 0
        agg_web = res.get('web_scraped', 0)
        agg_app = res.get('app_scraped', 0)
        selected = res.get('combined', 0)
        if not log:
            print(f"⚠  {store:12} no last_run_log.txt found -> scraper may not have run")
            continue
        line = f"{store:12} claimed web={claimed_web} app={claimed_app}"
        line += f" -> agg web={agg_web} app={agg_app} selected={selected}"
        print(line)
        if claimed_total == 0:
            print(f"   ⚠ Scraper reported ZERO scraped. Aggregator fell back to prior/decrypted data.")
        elif agg_web == 0 and claimed_web > 0:
            print(f"   ⚠ Web items claimed ({claimed_web}) but aggregator read 0 -> file path/format mismatch")
        elif agg_app == 0 and claimed_app > 0:
            print(f"   ⚠ App items claimed ({claimed_app}) but aggregator read 0 -> app source not merged")
        elif selected < claimed_total:
            print(f"   ℹ {claimed_total - selected} of {claimed_total} claimed items not in final merge (dups or dropped)")
    print("="*70)

def main():
    clean_disk_space()
    print("\n" + "="*70 + "\nGODDATA AGGREGATOR // Atomic Zero-Fail Engine\n" + "="*70)
    summaries = []
    store_metrics = {}
    agg_results = {}
    
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
        data_tuple = loader()
        res_tuple = save_store_data(store_name, data_tuple)
        if isinstance(res_tuple, tuple):
            res_summary, res_stats = res_tuple
        else:
            res_summary, res_stats = res_tuple, {}
        if res_summary:
            summaries.append(res_summary)
        if res_stats:
            store_metrics[store_name] = res_stats
            
        store_res = None
        if data_tuple and len(data_tuple) == 3:
            store_res = data_tuple[2]
        agg_results[store_name] = store_res or {}
        
    print("="*70 + "\n")
    
    scraper_logs = {}
    if platform.system() == 'Windows':
        scraper_logs = {
            "shwapno": read_scraper_log('swapnoTRACKER'),
            "chaldal": read_scraper_log('chaldalTRACKER'),
            "meenabazar": read_scraper_log('MEENAtracker'),
            "othoba": read_scraper_log('othobaTRACKER'),
            "metromart": read_scraper_log('metroTRACKER'),
            "unimart": read_scraper_log('unimartTRACKER'),
            "shotejbazar": read_scraper_log('ShotejTRACKER'),
            "foodi": read_scraper_log('FooDIEscraper'),
        }
    else:
        scraper_logs = {
            "shwapno": read_scraper_log('/kaggle/working/shopno') or read_scraper_log('swapnoTRACKER'),
            "chaldal": read_scraper_log('chaldalTRACKER'),
            "meenabazar": read_scraper_log('MEENAtracker'),
            "othoba": read_scraper_log('/kaggle/working/othoba') or read_scraper_log('othobaTRACKER'),
            "metromart": read_scraper_log('metroTRACKER'),
            "unimart": read_scraper_log('unimartTRACKER'),
            "shotejbazar": read_scraper_log('ShotejTRACKER'),
            "foodi": read_scraper_log('FooDIEscraper'),
        }
    print_failure_diagnostics(scraper_logs, agg_results)
    
    # Shared summary file only (consumed by the orchestrator's consolidated p14 message — no own TG send to avoid spam)
    if summaries:
        tot_prods = sum(m.get('total', 0) for m in store_metrics.values())
        tot_in_stock = sum(m.get('in_stock', 0) for m in store_metrics.values())
        tot_oos = sum(m.get('out_of_stock', 0) for m in store_metrics.values())
        tot_new = sum(m.get('new_items', 0) for m in store_metrics.values())
        tot_up = sum(m.get('price_up', 0) for m in store_metrics.values())
        tot_down = sum(m.get('price_down', 0) for m in store_metrics.values())
        tot_same = sum(m.get('price_same', 0) for m in store_metrics.values())
        tot_restocked = sum(m.get('back_in_stock', 0) for m in store_metrics.values())
        tot_went_oos = sum(m.get('went_oos', 0) for m in store_metrics.values())

        def _mp(val):
            return f"({(val / tot_prods * 100):.1f}%)" if tot_prods > 0 else "(0.0%)"

        STORE_KEYS = [
            ("shwapno", "Shwapno"),
            ("chaldal", "Chaldal"),
            ("meenabazar", "Meena"),
            ("othoba", "Othoba"),
            ("metromart", "Metro"),
            ("unimart", "Unimart"),
            ("shotejbazar", "Shotej"),
            ("foodi", "FooDIE")
        ]

        header = '%-8s %7s %4s %4s %4s %3s' % ('Store', 'Total', '▲', '▼', 'New', 'OOS')
        div = '─' * len(header)
        tbl_lines = [
            "<pre>",
            header,
            div
        ]

        tot_up_sum = 0
        tot_down_sum = 0
        tot_new_sum = 0
        tot_oos_sum = 0

        for skey, sname in STORE_KEYS:
            sm = store_metrics.get(skey, {})
            stot = sm.get('total', 0)
            sup = sm.get('price_up', 0)
            sdn = sm.get('price_down', 0)
            snw = sm.get('new_items', 0)
            soos = sm.get('out_of_stock', 0)
            tot_up_sum += sup
            tot_down_sum += sdn
            tot_new_sum += snw
            tot_oos_sum += soos
            tbl_lines.append('%-8s %7s %4d %4d %4d %3d' % (sname, f"{stot:,}", sup, sdn, snw, soos))

        tbl_lines.append(div)
        tbl_lines.append('%-8s %7s %4d %4d %4d %3d' % ('TOTAL', f"{tot_prods:,}", tot_up_sum, tot_down_sum, tot_new_sum, tot_oos_sum))
        tbl_lines.append("</pre>")

        telemetry_lines = [
            f"🟢 <b>In Stock:</b> {tot_in_stock:,} {_mp(tot_in_stock)} | 🔴 <b>OOS:</b> {tot_oos:,} {_mp(tot_oos)}"
        ]
        if tot_restocked > 0 or tot_went_oos > 0:
            stock_move_parts = []
            if tot_restocked > 0: stock_move_parts.append(f"🟢 {tot_restocked:,} restocked")
            if tot_went_oos > 0: stock_move_parts.append(f"🔴 {tot_went_oos:,} went OOS")
            telemetry_lines.append("🔄 <b>Delta:</b> " + " | ".join(stock_move_parts))

        all_dates = [sm.get('date_range', '') for sm in store_metrics.values() if sm.get('date_range')]
        if all_dates:
            min_dates = [d.split(' to ')[0] for d in all_dates if ' to ' in d]
            max_dates = [d.split(' to ')[1] for d in all_dates if ' to ' in d]
            if min_dates and max_dates:
                telemetry_lines.append(f"📅 <b>History:</b> {min(min_dates)} to {max(max_dates)}")

        full_parts = [
            "📊 <b>GroceryGOD Market Summary</b>",
            "\n".join(tbl_lines),
            "\n".join(telemetry_lines),
            "🔗 https://ranehal.github.io/GroceryGOD"
        ]
        msg = "\n\n".join(full_parts)
        try:
            _agg_share = '/tmp/aggregator_summary.txt'
            with open(_agg_share, 'w', encoding='utf-8') as f:
                f.write(msg)
            print(f"Shared aggregator summary written: {_agg_share}")
        except Exception as e:
            print(f"Failed to write shared aggregator summary: {e}")

if __name__ == "__main__": main()

