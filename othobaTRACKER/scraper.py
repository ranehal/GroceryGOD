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

def run_scrapers():
    dir_path = os.path.dirname(os.path.abspath(__file__))
    web_script = os.path.join(dir_path, "scraper_web.py")
    app_script = os.path.join(dir_path, "scraper_app.py")

    web_count = 0
    app_count = 0

    print("\n[Othoba] Launching Web Scraper...")
    try:
        _run_script_live(web_script, dir_path)
    except Exception as e:
        print(f"[Othoba] Web scraper error: {e}")

    print("\n[Othoba] Launching App API Scraper...")
    try:
        _run_script_live(app_script, dir_path)
    except Exception as e:
        print(f"[Othoba] App API scraper error: {e}")

    # Read Web dataset
    web_file = os.path.join(dir_path, "frontend", "othoba_products.json")
    web_products = {}
    if os.path.exists(web_file):
        try:
            with open(web_file, "r", encoding="utf-8") as f:
                w_data = json.load(f)
                items = w_data if isinstance(w_data, list) else w_data.get("products", [])
                for p in items:
                    name_key = re.sub(r'\W+', '', p.get("name", "")).lower()
                    if not name_key: continue
                    web_products[name_key] = p
            web_count = len(web_products)
        except Exception as e:
            print(f"[Othoba] Read web_file error: {e}")

    # Read App dataset
    app_file = os.path.join(dir_path, "othoba_products.json")
    app_products = {}
    if os.path.exists(app_file):
        try:
            with open(app_file, "r", encoding="utf-8") as f:
                a_data = json.load(f)
                items = a_data if isinstance(a_data, list) else a_data.get("products", [])
                for p in items:
                    name_key = re.sub(r'\W+', '', p.get("name", "")).lower()
                    if not name_key: continue
                    app_products[name_key] = p
            app_count = len(app_products)
        except Exception as e:
            print(f"[Othoba] Read app_file error: {e}")

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
