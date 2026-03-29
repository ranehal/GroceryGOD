import json
import sqlite3
import os
import re
from datetime import datetime

# Paths to data sources
SHWAPNO_DATA = '../swapnoTRACKER/data.json'
CHALDAL_DATA = '../PRICETRACKER/data.js'
MEENA_DB = '../MEENAtracker/backend/meenatracker.db'
DAILY_DB = '../DAILYtrackker/backend/dailytracker.db'

def parse_unit_and_calculate(name, unit_str, price):
    """
    Returns (unit_type, normalized_price)
    Detects gm, ml, kg, ltr and calculates price per 1kg/1L.
    Handles tolerance patterns like 350(±50)gm as 350gm.
    """
    # Clean text: remove tolerance patterns like (±50), ±50, (+10), etc.
    text = (name + " " + (unit_str or "")).lower()
    text = re.sub(r'\(?[±\+\-]\d+\s*(gm|g|kg|ml|ltr|l)?\)?', '', text)
    
    # Weight patterns (kg, gm, g)
    weight_match = re.search(r'(\d+(\.\d+)?)\s*(kg|gm|gram|g)\b', text)
    if weight_match:
        val = float(weight_match.group(1))
        unit = weight_match.group(3)
        if unit == 'kg':
            return 'kg', price / val if val > 0 else price
        else: # gm, g, gram
            return 'kg', (price / val) * 1000 if val > 0 else price

    # Volume patterns (ltr, liter, l, ml)
    volume_match = re.search(r'(\d+(\.\d+)?)\s*(ltr|liter|l|ml)\b', text)
    if volume_match:
        val = float(volume_match.group(1))
        unit = volume_match.group(3)
        if unit in ['ltr', 'liter', 'l']:
            return 'liter', price / val if val > 0 else price
        else: # ml
            return 'liter', (price / val) * 1000 if val > 0 else price

    # Piece patterns
    if any(x in text for x in ['pc', 'piece', 'hali', 'dozen', 'pkt', 'pack', 'each', 'bottle', 'can', 'box']):
        return 'piece', price
        
    return 'kg', price # Default fallback

def load_shwapno():
    print("Processing Shwapno...")
    if not os.path.exists(SHWAPNO_DATA): return None
    with open(SHWAPNO_DATA, 'r', encoding='utf-8') as f:
        data = json.load(f)
    products = {}
    all_dates = []
    for pid, p in data.items():
        if pid in ['metadata', 'products']: continue
        hist = p.get('history', [])
        curr_p = hist[-1].get('price', 0) if hist else 0
        u_type, norm_p = parse_unit_and_calculate(p.get('name', ''), "", curr_p)
        
        # Update history with recalculated normalized prices
        new_history = []
        for h in hist:
            _, h_norm = parse_unit_and_calculate(p.get('name', ''), "", h.get('price', 0))
            new_history.append({
                "date": h.get('date'),
                "price": h.get('price'),
                "normalized_price": h_norm
            })
            if h.get('date'): all_dates.append(h['date'])

        products[f"sh_{pid}"] = {
            "id": f"sh_{pid}", "name": p.get('name'), "store": "shwapno",
            "category": p.get('category', 'General'), "unit": "N/A",
            "unit_type": u_type,
            "current_price": curr_p,
            "normalized_price": norm_p,
            "image": p.get('image'), "history": new_history
        }
    
    date_info = f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"
    return products, date_info

def load_chaldal():
    print("Processing Chaldal...")
    if not os.path.exists(CHALDAL_DATA): return None, None
    with open(CHALDAL_DATA, 'r', encoding='utf-8') as f:
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
            new_history.append({
                "date": h.get('date'),
                "price": h.get('price'),
                "normalized_price": h_norm
            })
            if h.get('date'): all_dates.append(h['date'])
            
        curr_p = p.get('current_price', 0)
        u_type, norm_p = parse_unit_and_calculate(p.get('name', ''), p.get('current_unit', ''), curr_p)

        products[f"ch_{pid}"] = {
            "id": f"ch_{pid}", "name": p.get('name'), "store": "chaldal",
            "category": p.get('category', 'General'), "unit": p.get('current_unit'),
            "unit_type": u_type,
            "current_price": curr_p,
            "normalized_price": norm_p,
            "image": p.get('image'), "history": new_history
        }
    date_info = f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"
    return products, date_info

def load_sqlite(db_path, store_name, prefix):
    print(f"Processing {store_name}...")
    if not os.path.exists(db_path): return None, None
    conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    cats = {row['id']: row['name'] for row in cursor.fetchall()}
    cursor.execute("SELECT id, external_id, name, unit, unit_type, image_url, category_id FROM products")
    db_p = cursor.fetchall()
    products = {}
    all_dates = []
    for p in db_p:
        cursor.execute("SELECT actual_price, unit_price, scraped_at FROM price_history WHERE product_id = ? ORDER BY scraped_at ASC", (p['id'],))
        db_h = cursor.fetchall()
        
        new_history = []
        for h in db_h:
            date_str = h['scraped_at'].split('T')[0].split(' ')[0]
            _, h_norm = parse_unit_and_calculate(p['name'], p['unit'], h['actual_price'])
            new_history.append({
                "date": date_str,
                "price": h['actual_price'],
                "normalized_price": h_norm
            })
            all_dates.append(date_str)
            
        if not new_history: continue
        
        curr_p = new_history[-1]['price']
        u_type, norm_p = parse_unit_and_calculate(p['name'], p['unit'], curr_p)

        products[f"{prefix}_{p['external_id'] or p['id']}"] = {
            "id": f"{prefix}_{p['external_id'] or p['id']}", "name": p['name'], "store": store_name,
            "category": cats.get(p['category_id'], 'General'), "unit": p['unit'],
            "unit_type": u_type,
            "current_price": curr_p,
            "normalized_price": norm_p,
            "image": p['image_url'], "history": new_history
        }
    conn.close()
    date_info = f"{min(all_dates)} to {max(all_dates)}" if all_dates else "N/A"
    return products, date_info

def save_store_data(name, data_tuple):
    products, date_range = data_tuple
    if not products: return
    data = {
        "metadata": {
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            "total": len(products),
            "date_range": date_range
        },
        "products": products
    }
    js_path = f"{name}_data.js"
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(f"window.{name}Data = {json.dumps(data)};")
    print(f"Saved {name:15} | Items: {len(products):5} | Range: {date_range}")

def main():
    print("\n" + "="*70)
    print("GODDATA AGGREGATOR // Calculated Unit Price Engine")
    print("="*70)
    save_store_data("shwapno", load_shwapno())
    save_store_data("chaldal", load_chaldal())
    save_store_data("meenabazar", load_sqlite(MEENA_DB, "meenabazar", "mb"))
    save_store_data("dailyshopping", load_sqlite(DAILY_DB, "dailyshopping", "ds"))
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
