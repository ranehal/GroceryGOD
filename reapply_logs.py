import os

scrapers = [
    'MEENAtracker/backend/scraper.py',
    'PRICETRACKER/scraper.py',
    'ShotejTRACKER/scraper.py',
    'metroTRACKER/backend/scraper.py',
    'othobaTRACKER/backend/scraper.py',
    'swapnoTRACKER/scraper.py',
    'unimartTRACKER/scraper.py'
]

# Standard logging helper to inject
LOG_HELPER = """
def save_last_run_log(summary):
    import os
    from datetime import datetime, timedelta, timezone
    DHAKA_TZ = timezone(timedelta(hours=6))

    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base_dir, "last_run_log.txt")
    with open(log_path, "w", encoding='utf-8') as f:
        f.write(f"Last Run: {datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')}\\n")
        f.write("-" * 30 + "\\n")
        f.write(f"Total Scraped: {summary['total']}\\n")
        f.write(f"New Items: {summary.get('new', 'N/A')}\\n")
        f.write("-" * 30 + "\\n")
        f.write("Categories:\\n")
        for cat, count in sorted(summary['categories'].items(), key=lambda x: x[1], reverse=True)[:10]:
            f.write(f"- {cat}: {count}\\n")
        if len(summary['categories']) > 10:
            f.write(f"... and {len(summary['categories']) - 10} more.")
"""

# I will manually verify and apply to ensure precision this time.
# But for now, I'll provide the user with the most important one: the Kaggle Notebook update
# which they need to copy-paste.

def update_file(path, search, replace):
    if not os.path.exists(path): return
    with open(path, 'r', encoding='utf-8') as f:
        src = f.read()
    if search in src:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(src.replace(search, replace))
        print(f"Updated {path}")

# Example for Chaldal
update_file('PRICETRACKER/scraper.py', 
            'print(f"Scraping finished. Total products: {len(products_data)}")', 
            'save_last_run_log(summary)\n        print(f"Scraping finished. Total products: {len(products_data)}")')
