"""
Shwapno Combined Scraper Orchestrator.
Runs both Web scraper and Mobile App API scraper,
combines items picking lowest valid active price, and writes last_run_log.txt & Telegram summary.
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

    print("\n[Shwapno] Launching Web & App API Scrapers simultaneously in PARALLEL...")
    t_web = threading.Thread(target=_run_script_live, args=(web_script, dir_path), daemon=True)
    t_app = threading.Thread(target=_run_script_live, args=(app_script, dir_path), daemon=True)
    
    t_web.start()
    t_app.start()
    
    t_web.join()
    t_app.join()

    # 1. Read Web dataset (check data.json first, then shwapno_products.json)
    web_products = {}
    for candidate in [os.path.join(dir_path, "data.json"), os.path.join(dir_path, "shwapno_products.json")]:
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    w_data = json.load(f)
                    items_list = w_data.values() if isinstance(w_data, dict) else (w_data.get("products", []) if isinstance(w_data, dict) else w_data)
                    for p in items_list:
                        if not isinstance(p, dict): continue
                        name_key = re.sub(r'\W+', '', p.get("name", "")).lower()
                        if not name_key: continue
                        web_products[name_key] = p
                if web_products:
                    web_count = len(web_products)
                    break
            except Exception as e:
                print(f"[Shwapno] Read web_file ({candidate}) error: {e}")

    # 2. Read App dataset
    app_file = os.path.join(dir_path, "frontend", "shwapno_products.json")
    app_products = {}
    if os.path.exists(app_file):
        try:
            with open(app_file, "r", encoding="utf-8") as f:
                a_data = json.load(f)
                items_list = a_data.values() if isinstance(a_data, dict) else (a_data.get("products", []) if isinstance(a_data, dict) else a_data)
                for p in items_list:
                    if not isinstance(p, dict): continue
                    name_key = re.sub(r'\W+', '', p.get("name", "")).lower()
                    if not name_key: continue
                    app_products[name_key] = p
            app_count = len(app_products)
        except Exception as e:
            print(f"[Shwapno] Read app_file error: {e}")

    # 3. Combine picking lowest valid active price
    all_keys = set(web_products.keys()) | set(app_products.keys())
    combined_dict = {}
    cat_counts = {}

    for k in all_keys:
        w_p = web_products.get(k)
        a_p = app_products.get(k)
        if w_p and a_p:
            w_price = float(w_p.get("current_price") or w_p.get("price") or 0)
            a_price = float(a_p.get("current_price") or a_p.get("price") or 0)
            if w_price > 0 and a_price > 0:
                chosen = w_p if w_price <= a_price else a_p
            elif w_price > 0:
                chosen = w_p
            else:
                chosen = a_p
        elif w_p:
            chosen = w_p
        else:
            chosen = a_p

        pid = chosen.get("id") or k
        combined_dict[pid] = chosen
        cat_name = chosen.get("category", "General")
        cat_counts[cat_name] = cat_counts.get(cat_name, 0) + 1

    combined_count = len(combined_dict)

    # Save combined results to data.json so aggregator picks up full dataset
    data_json_path = os.path.join(dir_path, "data.json")
    try:
        with open(data_json_path, "w", encoding="utf-8") as f:
            json.dump(combined_dict, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Shwapno] Save data.json error: {e}")

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
    print(f"Shwapno Combined Stats -> Web: {web_count}, App: {app_count}, Combined Unique: {combined_count}")
    print(f"==================================================\n")

    tg_report = (
        f"🛍️ <b>Shwapno Scraper Complete</b>\n"
        f"🌐 Web Scraped: <b>{web_count}</b> items\n"
        f"📱 App API Scraped: <b>{app_count}</b> items\n"
        f"⚡ <b>Combined Unique (Lowest Price): {combined_count}</b> items"
    )
    tg_send(tg_report)

if __name__ == "__main__":
    run_scrapers()
