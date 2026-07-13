import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import requests
import json
import os
import re
import datetime
DHAKA_TZ = datetime.timezone(datetime.timedelta(hours=6))
import logging
from collections import Counter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler("scraper.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Correctly determine base directory for the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'data.json')
LOG_FILE = os.path.join(BASE_DIR, 'last_run_log.txt')

BASE_API_URL = "https://myadmin.unimart.online/api/v1/"
HEADERS = {
    "moduleid": "1",
    "zoneid": "[1]",
    "x-localization": "en",
    "latitude": "23.03142275998142",
    "longitude": "90.33365821000189",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
}

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'))

def save_last_run_log(summary):
    with open(LOG_FILE, "w", encoding='utf-8') as f:
        f.write(f"Last Run: {datetime.datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("-" * 30 + "\n")
        f.write(f"Total Scraped: {summary['total']}\n")
        f.write(f"New Items: {summary['new']}\n")
        f.write("-" * 30 + "\n")
        f.write("Categories:\n")
        for cat, count in sorted(summary['categories'].items(), key=lambda x: x[1], reverse=True)[:10]:
            f.write(f"- {cat}: {count}\n")
        if len(summary['categories']) > 10:
            f.write(f"... and {len(summary['categories']) - 10} more.")

def normalize_unimart_unit(name, price):
    name_lower = name.lower()
    kg_match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|gm|gram|g)\b', name_lower)
    l_match = re.search(r'(\d+(?:\.\d+)?)\s*(ltr|liter|l|ml)\b', name_lower)
    
    unit_type = "piece"
    total_val = 1.0
    qty_label = "1 unit"

    if kg_match:
        val = float(kg_match.group(1))
        unit = kg_match.group(2)
        total_val = val / 1000.0 if unit in ['gm', 'gram', 'g'] else val
        unit_type = "kg"
        qty_label = f"{val}{unit}"
    elif l_match:
        val = float(l_match.group(1))
        unit = l_match.group(2)
        total_val = val / 1000.0 if unit == 'ml' else val
        unit_type = "liter"
        qty_label = f"{val}{unit}"
        
    norm_price = price / total_val if total_val > 0 else price
    return qty_label, round(norm_price, 2), unit_type

def scrape_unimart():
    data = load_data()
    today_str = datetime.date.today().isoformat()
    
    summary = {
        'total': 0,
        'new': 0,
        'categories': Counter()
    }
    
    logger.info("Starting Unimart bulk scrape...")
    
    # We use multiple search queries to ensure we cover the entire inventory
    search_queries = ["a", "e", "i", "o", "u", "s", "t", "m", "p", "c"]
    
    for query in search_queries:
        logger.info(f"Searching for '{query}'...")
        offset = 0
        limit = 100
        while True:
            url = f"{BASE_API_URL}items/search?name={query}&limit={limit}&offset={offset}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                if r.status_code != 200:
                    logger.error(f"  [!] API Error: {r.status_code}")
                    break
                
                res = r.json()
                products = res.get('products', [])
                if not products:
                    break
                
                logger.info(f"  [+] Fetched {len(products)} products (Query: {query}, Offset: {offset})")
                
                for p in products:
                    p_id = f"uni_{p['id']}"
                    p_name = p['name']
                    p_price = float(p['price'])
                    
                    # Apply discount
                    discount = float(p.get('discount', 0))
                    if discount > 0:
                        if p.get('discount_type') == 'amount':
                            p_price -= discount
                        else:
                            p_price *= (1 - discount/100.0)

                    qty_label, norm_price, u_type = normalize_unimart_unit(p_name, p_price)
                    
                    category = "General"
                    if p.get('category_ids'):
                        category = p['category_ids'][-1].get('name', 'General')

                    summary['total'] += 1
                    summary['categories'][category] += 1

                    if p_id not in data:
                        img_url = p.get('image_full_url', "")
                        data[p_id] = {
                            "id": p_id, "name": p_name, "store": "unimart",
                            "image": img_url, "category": category, "history": []
                        }
                        summary['new'] += 1
                    
                    data[p_id].update({
                        "current_price": p_price, "normalized_price": norm_price,
                        "unit": qty_label, "unit_type": u_type
                    })
                    
                    history = data[p_id]["history"]
                    if not history or history[-1]['date'] != today_str:
                         history.append({"date": today_str, "price": p_price, "normalized_price": norm_price})
                    elif history[-1]['date'] == today_str:
                        history[-1]['price'] = p_price
                        history[-1]['normalized_price'] = norm_price
                
                if len(products) < limit:
                    break
                offset += len(products)
                
            except Exception as e:
                logger.error(f"Error fetching offset {offset}: {e}")
                break
        
        save_data(data) # Partial save per query
    
    save_last_run_log(summary)
    logger.info(f"Unimart bulk scrape complete. Total items: {summary['total']}, New: {summary['new']}")

if __name__ == "__main__":
    scrape_unimart()
