"""
Othoba Combined Scraper Orchestrator.
Runs both Web scraper and Mobile App API scraper,
combines items picking lowest price, and writes last_run_log.txt & Telegram summary.
"""
import os
import sys
import json
import subprocess
import requests
import re
from datetime import datetime, timezone, timedelta

DHAKA_TZ = timezone(timedelta(hours=6))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

def tg_send(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_notification": False}, timeout=10)
    except Exception as e:
        print(f"[Telegram Error] {e}")

import threading
_print_lock = threading.Lock()

def _run_script_live(script_path, cwd):
    if not os.path.exists(script_path):
        print(f"[Orchestrator] Warning: {script_path} not found.")
        return
    print(f"[Orchestrator] Running {os.path.basename(script_path)} live...")
    try:
        proc = subprocess.Popen([sys.executable, "-u", script_path], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            with _print_lock:
                sys.stdout.write(line)
                sys.stdout.flush()
        proc.wait(timeout=1800)
    except Exception as e:
        print(f"[Orchestrator] Error running {os.path.basename(script_path)}: {e}")

def run_scrapers():
    dir_path = os.path.dirname(os.path.abspath(__file__))
    web_script = os.path.join(dir_path, "scraper_web.py")
    app_script = os.path.join(dir_path, "scraper_app.py")

    web_count = 0
    app_count = 0

    print("\n[Othoba] Launching Web & App API Scrapers simultaneously in PARALLEL...")
    t_web = threading.Thread(target=_run_script_live, args=(web_script, dir_path), daemon=True)
    t_app = threading.Thread(target=_run_script_live, args=(app_script, dir_path), daemon=True)
    
    t_web.start()
    t_app.start()
    
    t_web.join()
    t_app.join()

        # Read Web & App datasets from all possible locations
    candidate_files = [
        os.path.join(dir_path, "othoba_products.json"),
        os.path.join(dir_path, "frontend", "othoba_products.json"),
        os.path.join(dir_path, "data", "othoba_products.json")
    ]
    web_products = {}
    app_products = {}

    for cf in candidate_files:
        if os.path.exists(cf):
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    items = list(data.values()) if isinstance(data, dict) and "products" not in data else (data if isinstance(data, list) else data.get("products", []))
                    for p in items:
                        name_key = re.sub(r'\W+', '', p.get("name", "")).lower()
                        if not name_key: continue
                        web_products[name_key] = p
            except Exception as _e:
                print(f"[Othoba] Error reading {os.path.basename(cf)}: {_e}")

    # Fallback to reading othoba_tracker.db if present
    db_path = os.path.join(dir_path, "othoba_tracker.db")
    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, category_name FROM products")
            for r in cursor.fetchall():
                name_key = re.sub(r'\W+', '', r["name"]).lower()
                if not name_key: continue
                web_products[name_key] = {"id": r["id"], "name": r["name"], "category": r["category_name"], "price": 0.0}
            conn.close()
        except Exception as _dbe:
            print(f"[Othoba] DB read notice: {_dbe}")

    web_count = len(web_products)
    app_count = len(app_products)

    # Combine picking lowest price
    all_keys = set(web_products.keys()) | set(app_products.keys())
    combined_products = []
    cat_counts = {}

    for k in all_keys:
        w_p = web_products.get(k)
        a_p = app_products.get(k)
        if w_p and a_p:
            w_price = float(w_p.get("price") or w_p.get("actual_price") or 0)
            a_price = float(a_p.get("price") or a_p.get("actual_price") or 0)
            chosen = w_p if (w_price > 0 and w_price <= a_price) or a_price == 0 else a_p
        elif w_p:
            chosen = w_p
        else:
            chosen = a_p

        combined_products.append(chosen)
        cat_name = chosen.get("category", "General")
        cat_counts[cat_name] = cat_counts.get(cat_name, 0) + 1

    combined_count = len(combined_products)

    # Save last_run_log.txt
    now_str = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    log_path = os.path.join(dir_path, "last_run_log.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Last Run: {now_str}\n")
        f.write("-" * 30 + "\n")
        f.write(f"Total Scraped: {combined_count}\n")
        f.write(f"Web Scraped: {web_count}\n")
        f.write(f"App API Scraped: {app_count}\n")
        f.write(f"Combined Unique: {combined_count}\n")
        f.write("-" * 30 + "\n")
        f.write("Categories:\n")
        for cat, count in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            f.write(f"- {cat}: {count}\n")
        if len(cat_counts) > 10:
            f.write(f"... and {len(cat_counts) - 10} more.\n")

    print(f"\n==================================================")
    print(f"Othoba Combined Stats -> Web: {web_count}, App: {app_count}, Combined Unique: {combined_count}")
    print(f"==================================================\n")

    tg_report = (
        f"🛒 <b>Othoba Scraper Complete</b>\n"
        f"🌐 Web Scraped: <b>{web_count}</b> items\n"
        f"📱 App API Scraped: <b>{app_count}</b> items\n"
        f"⚡ <b>Combined Unique (Lowest Price): {combined_count}</b> items"
    )
    tg_send(tg_report)

if __name__ == "__main__":
    run_scrapers()
