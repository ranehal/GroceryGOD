"""
Meena Bazar Combined Scraper Orchestrator.
Runs both Web scraper (Playwright) and Mobile App API scraper,
combines items by picking the lowest price for duplicate items,
and outputs statistics to console, SQLite DB, and Telegram.
"""
import os
import sys
import json
import sqlite3
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

def _run_script_live(script_path, cwd):
    if not os.path.exists(script_path):
        print(f"[Orchestrator] Warning: {script_path} not found.")
        return
    print(f"[Orchestrator] Running {os.path.basename(script_path)} live...")
    try:
        proc = subprocess.Popen([sys.executable, script_path], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
        proc.wait(timeout=1800)
    except Exception as e:
        print(f"[Orchestrator] Error running {os.path.basename(script_path)}: {e}")

def run_scrapers():
    dir_path = os.path.dirname(os.path.abspath(__file__))
    web_script = os.path.join(dir_path, "scraper_web.py")
    app_script = os.path.join(dir_path, "scraper_app.py")

    web_items = 0
    app_items = 0

    print("\n[MEENAtracker] Launching Web Scraper (Playwright)...")
    try:
        _run_script_live(web_script, dir_path)
    except Exception as e:
        print(f"[MEENAtracker] Web scraper error/timeout: {e}")

    print("\n[MEENAtracker] Launching Mobile App API Scraper...")
    try:
        _run_script_live(app_script, dir_path)
    except Exception as e:
        print(f"[MEENAtracker] App API scraper error/timeout: {e}")

    # Process & Combine DB / JSON data
    db_path = os.path.join(dir_path, "meenatracker.db")
    catalog_path = os.path.join(dir_path, "catalog.json")

    web_products = {}
    app_products = {}
    combined_products = {}

    # Load App data from catalog.json
    if os.path.exists(catalog_path):
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                cat_data = json.load(f)
                for p in cat_data.get("products", []):
                    name_key = re.sub(r'\W+', '', p.get("name", "")).lower()
                    if not name_key: continue
                    app_products[name_key] = {
                        "id": f"mb_{p.get('id')}",
                        "name": p.get("name"),
                        "price": float(p.get("price", 0)),
                        "source": "app"
                    }
            app_items = len(app_products)
        except Exception as e:
            print(f"[MEENAtracker] Failed to parse catalog.json: {e}")

    # Load Web data from SQLite DB if present
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM products")
            rows = cursor.fetchall()
            for r in rows:
                name_key = re.sub(r'\W+', '', r["name"]).lower()
                if not name_key: continue
                cursor.execute("SELECT actual_price FROM price_history WHERE product_id=? ORDER BY scraped_at DESC LIMIT 1", (r["id"],))
                ph = cursor.fetchone()
                price = float(ph["actual_price"]) if ph else 0.0
                web_products[name_key] = {
                    "id": f"mb_w_{r['id']}",
                    "name": r["name"],
                    "price": price,
                    "source": "web"
                }
            web_items = len(web_products)
            conn.close()
        except Exception as e:
            print(f"[MEENAtracker] DB Read error: {e}")

    # Merge picking lowest price
    all_keys = set(web_products.keys()) | set(app_products.keys())
    for k in all_keys:
        w_item = web_products.get(k)
        a_item = app_products.get(k)
        if w_item and a_item:
            # Pick lowest price
            chosen = w_item if w_item["price"] <= a_item["price"] else a_item
            combined_products[k] = chosen
        elif w_item:
            combined_products[k] = w_item
        else:
            combined_products[k] = a_item

    combined_count = len(combined_products)
    stats_msg = f"Meenabazar Stats -> Web: {web_items}, App: {app_items}, Combined Unique: {combined_count}"
    print(f"\n==================================================")
    print(stats_msg)
    print(f"==================================================\n")

    # Send Telegram notification
    tg_report = (
        f"🛒 <b>Meena Bazar Scraper Complete</b>\n"
        f"🌐 Web Scraped: <b>{web_items}</b> items\n"
        f"📱 App API Scraped: <b>{app_items}</b> items\n"
        f"⚡ <b>Combined Unique (Lowest Price): {combined_count}</b> items"
    )
    tg_send(tg_report)

    # Write summary log
    log_file = os.path.join(dir_path, "last_run_log.txt")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(stats_msg + "\n" + tg_report + "\n")

if __name__ == "__main__":
    run_scrapers()
