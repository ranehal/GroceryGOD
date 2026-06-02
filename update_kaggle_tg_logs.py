import json
import os

file_path = 'gitgod_kaggle_scraper.ipynb'
with open(file_path, 'r', encoding='utf-8') as f:
    d = json.load(f)

src = d['cells'][1]['source']

# 1. Update run_scraper to read and send log
old_run_scraper = """    def run_scraper(scraper_info):
        label, path = scraper_info
        log.info(f'\u25b6\ufe0f Starting {label}...')
        t0 = time.time()
        full_path = os.path.join(os.getcwd(), path)

        if not os.path.exists(os.path.join(full_path, 'scraper.py')):
            error_msg = f"File 'scraper.py' missing in {full_path}"
            log.error(f"\u274c {error_msg}")
            tg_send(f'\u274c <b>{label}</b> \u2014 {error_msg}', silent=True)
            return label, False

        my_env = os.environ.copy()
        res = subprocess.run([sys.executable, 'scraper.py'], cwd=full_path, capture_output=True, text=True, timeout=36000, env=my_env)
        elapsed = time.time() - t0

        if res.returncode != 0:
            log.error(f"\ud83d\udea8 {label} FAILED! STDERR:\\n{res.stderr[:1000]}")
            tg_send(f'\u274c <b>{label}</b> FAILED in {_fmt_dur(elapsed)}!\\n<pre>{res.stderr[:500]}</pre>', silent=True)
            return label, False

        log.info(f'   \u2705 {label} finished in {_fmt_dur(elapsed)}')
        tg_send(f'\u2705 <b>{label}</b> \u2014 {_fmt_dur(elapsed)}', silent=True)
        return label, True"""

new_run_scraper = """    def run_scraper(scraper_info):
        label, path = scraper_info
        log.info(f'\u25b6\ufe0f Starting {label}...')
        t0 = time.time()
        full_path = os.path.join(os.getcwd(), path)

        if not os.path.exists(os.path.join(full_path, 'scraper.py')):
            error_msg = f"File 'scraper.py' missing in {full_path}"
            log.error(f"\u274c {error_msg}")
            tg_send(f'\u274c <b>{label}</b> \u2014 {error_msg}', silent=True)
            return label, False

        my_env = os.environ.copy()
        res = subprocess.run([sys.executable, 'scraper.py'], cwd=full_path, capture_output=True, text=True, timeout=36000, env=my_env)
        elapsed = time.time() - t0

        if res.returncode != 0:
            log.error(f"\ud83d\udea8 {label} FAILED! STDERR:\\n{res.stderr[:1000]}")
            tg_send(f'\u274c <b>{label}</b> FAILED in {_fmt_dur(elapsed)}!\\n<pre>{res.stderr[:500]}</pre>', silent=True)
            return label, False

        # Read last_run_log.txt if exists
        summary_log = ""
        log_file = os.path.join(full_path, "last_run_log.txt")
        if os.path.exists(log_file):
            with open(log_file, "r", encoding='utf-8') as f:
                summary_log = "\\n" + f.read()

        log.info(f'   \u2705 {label} finished in {_fmt_dur(elapsed)}')
        tg_send(f'\u2705 <b>{label}</b> \u2014 {_fmt_dur(elapsed)}{summary_log}', silent=True)
        return label, True"""

src = src.replace(old_run_scraper, new_run_scraper)
d['cells'][1]['source'] = src

with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=1)
