import multiprocessing
import subprocess
import sys
import time
import os
import threading
import requests
import socket
import logging
import traceback
import json
import html
import shutil
import concurrent.futures
from datetime import datetime, timedelta, timezone

# Dhaka Timezone
DHAKA_TZ = timezone(timedelta(hours=6))

# ============================================================
# INITIALIZATION & SECRETS
# ============================================================
def get_secret_safe(key, default=""):
    try:
        from kaggle_secrets import UserSecretsClient
        val = UserSecretsClient().get_secret(key)
        return val if val else default
    except:
        return os.environ.get(key, default)

GITHUB_PAT = get_secret_safe('GITHUB_PAT')
os.environ['KAGGLE_USERNAME'] = get_secret_safe('KAGGLE_USERNAME')
os.environ['KAGGLE_KEY'] = get_secret_safe('KAGGLE_KEY')
TELEGRAM_BOT_TOKEN = get_secret_safe("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret_safe("TELEGRAM_CHAT_ID")
os.environ["TELEGRAM_BOT_TOKEN"] = TELEGRAM_BOT_TOKEN or ""
os.environ["TELEGRAM_CHAT_ID"] = TELEGRAM_CHAT_ID or ""
KAGGLE_KERNEL_SLUG = get_secret_safe("KAGGLE_KERNEL_SLUG")
os.environ['GOD_PREMIUM_KEY'] = get_secret_safe('GOD_PREMIUM_KEY', 'assalamualaikum')

def run_preflight_checks():
    print("\n" + "="*50)
    print("🛫 PRE-FLIGHT SECRETS CHECK")
    print("="*50)
    missing = []
    if not GITHUB_PAT: missing.append("GITHUB_PAT")
    if not os.environ['KAGGLE_USERNAME']: missing.append("KAGGLE_USERNAME")
    if not os.environ['KAGGLE_KEY']: missing.append("KAGGLE_KEY")
    if not KAGGLE_KERNEL_SLUG: missing.append("KAGGLE_KERNEL_SLUG")
    
    if missing:
        print(f"🚨 CRITICAL WARNING: The following secrets are missing or empty: {', '.join(missing)}")
        print("🚨 Scrapers WILL fail to push to GitHub, and the script WILL fail to self-restart.")
        print("🚨 Please stop the kernel, go to Add-ons > Secrets, attach them, and run again.\n")
    else:
        print("✅ All core secrets found. Systems nominal.\n")

# ============================================================
# SELF-RESTART FUNCTION
# ============================================================
def trigger_self_restart():
    print("\n[SYSTEM] Initiating Kaggle Self-Restart...")
    def _tg(msg):
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "": return
        try:
            requests.post(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage', json={'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'HTML'}, timeout=10)
        except: pass

    try:
        if not KAGGLE_KERNEL_SLUG:
            err = "❌ Error: KAGGLE_KERNEL_SLUG not found in secrets. Cannot restart."
            print(err)
            _tg(err)
            return

        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "kaggle"], check=True)

        kaggle_config = {"username": os.environ['KAGGLE_USERNAME'], "key": os.environ['KAGGLE_KEY']}
        os.makedirs(os.path.expanduser('~/.kaggle'), exist_ok=True)
        with open(os.path.expanduser('~/.kaggle/kaggle.json'), 'w') as f:
            json.dump(kaggle_config, f)
        os.chmod(os.path.expanduser('~/.kaggle/kaggle.json'), 0o600)

        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()

        restart_dir = '/tmp/restart_payload'
        if os.path.exists(restart_dir):
            shutil.rmtree(restart_dir)
        os.makedirs(restart_dir, exist_ok=True)
        os.chdir(restart_dir)

        print(f"[SYSTEM] Pulling kernel metadata for {KAGGLE_KERNEL_SLUG}...")
        api.kernels_pull(KAGGLE_KERNEL_SLUG, path='.', metadata=True)

        if not os.path.exists('kernel-metadata.json'):
            raise RuntimeError("Failed to pull kernel-metadata.json.")

        with open('kernel-metadata.json', 'r') as f:
            meta = json.load(f)
        code_filename = meta.get('code_file', 'notebook.ipynb')

        if os.path.exists('/kaggle/notebook_source.ipynb'):
            print(f"[SYSTEM] Syncing live notebook source into payload file: {code_filename}")
            shutil.copy('/kaggle/notebook_source.ipynb', code_filename)
        else:
            print("[SYSTEM] Live source location unavailable. Defaulting to server sync pull configuration.")

        print("[SYSTEM] Pushing kernel payload to trigger next loop container...")
        api.kernels_push('.')
        
        success_msg = "✅ <b>Kaggle Restart Triggered Successfully!</b>\nNew container should spawn shortly."
        print(success_msg)
        _tg(success_msg)

        time.sleep(10)
        os._exit(0)
    except Exception as e:
        safe_tb = html.escape(traceback.format_exc()[-500:])
        err_msg = f"❌ <b>Kaggle Restart Failed!</b>\nError: {html.escape(str(e))}\n<pre>{safe_tb}</pre>"
        print(err_msg)
        _tg(err_msg)

# ============================================================
# PIPELINE 1: GROCERYGOD (CONTINUOUS LOOP)
# ============================================================
def run_grocery_god(github_pat):
    print("[GroceryGOD] Process Started.")

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s | %(levelname)-8s | [GroceryGOD] %(message)s', handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler('/tmp/grocerygod_run.log', mode='w')])
    log = logging.getLogger('GroceryGOD')

    def _fmt_dur(seconds): return str(timedelta(seconds=int(seconds)))

    def tg_send(text, silent=False):
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.strip() == "": return
        TG_API = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'
        try: 
            requests.post(f'{TG_API}/sendMessage', json={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML', 'disable_notification': silent}, timeout=15)
        except: pass


    def tg_send_file(file_path, caption=""):
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.strip() == "": return
        try:
            with open(file_path, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument", files={"document": f}, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:200]}, timeout=120)
        except: pass

    def get_ips():
        try:
            public_ip = requests.get('https://api.ipify.org', timeout=10).text
            shops = {
                'Shwapno': 'www.shwapno.com',
                'Chaldal': 'chaldal.com',
                'MeenaBazar': 'meenabazaronline.com',
                'Othoba': 'www.othoba.com',
                'Unimart': 'unimart.online',
                'MetroMart': 'www.metromartonline.com',
                'ShotejBazar': 'shotejbazar.com'
            }
            shop_ips = []
            for name, host in shops.items():
                try: shop_ips.append(f"{name}: {socket.gethostbyname(host)}")
                except: shop_ips.append(f"{name}: Failed")

            report = f"📡 <b>Kaggle Scraper IP:</b> {public_ip}\n\n"
            report += "<b>Shop Server IPs:</b>\n" + "\n".join(shop_ips)
            # disabled IP report spam
        except Exception as e:
            log.error(f"IP Reporting failed: {e}")

    class Step:
        def __init__(self, name, emoji='⚙️', notify=True):
            self.name, self.emoji, self.notify = name, emoji, notify
        def __enter__(self):
            self._t0 = time.time()
            log.info(f'{self.emoji}  [{self.name}] — STARTED')
            # disabled start telegram spam
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            elapsed = time.time() - self._t0
            if exc_type is None:
                log.info(f'✅  [{self.name}] — OK ({_fmt_dur(elapsed)})')
                # disabled step complete telegram spam
            else:
                safe_tb = html.escape(traceback.format_exc()[-1000:])
                log.error(f'❌  [{self.name}] — FAILED\n{traceback.format_exc()}')
                if self.notify: tg_send(f'❌ <b>{self.name}</b> — FAILED\n<pre>{safe_tb}</pre>')
                return False
    # ONE-TIME INITIALIZATIONS
    os.chdir('/kaggle/working')
    try:
        tg_send('🚀 <b>GroceryGOD Environment Booting Up...</b>')
        get_ips()
        with Step('Environment Sync', '📦'):
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "playwright", "httpx", "beautifulsoup4", "lxml", "sqlalchemy", "aiosqlite", "requests", "pyarrow"], check=True)
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"], check=True)
            subprocess.run('apt-get update -y -q 2>/dev/null', shell=True)
            subprocess.run(['apt-get', 'install', '-y', '-q', 'sqlite3'], check=True)
    except Exception as e:
        log.error("Environment Setup Failed. Terminating GroceryGOD loop thread.")
        return

    # INFINITE LOOP PIPELINE
    cycle_count = 1
    while True:
        os.chdir('/kaggle/working')
        
        try:
            tg_send(f'🚀 <b>GroceryGOD Pipeline — CYCLE {cycle_count} STARTED (Simultaneous Parallel)</b>')
            with Step('Configuration & Git Setup', '⚙️'):
                if not github_pat:
                    raise RuntimeError("GITHUB_PAT is missing or empty. Git operations will fail.")
                    
                subprocess.run('git config --global user.email "educational.purpose37@gmail.com"', shell=True)
                subprocess.run('git config --global user.name "ranx-x"', shell=True)

                cred_path = os.path.expanduser('~/.git-credentials')
                with open(cred_path, 'w') as f:
                    f.write(f"https://ranehal:{github_pat}@github.com\nhttps://ranx-x:{github_pat}@github.com\nhttps://{github_pat}@github.com\n")
                subprocess.run('git config --global credential.helper store', shell=True)

                REPO_URL = 'https://github.com/ranx-x/GroceryGOD.git'

                if os.path.exists('GroceryGOD/.git/index.lock'):
                    subprocess.run('rm -f GroceryGOD/.git/index.lock', shell=True)

                if not os.path.exists('GroceryGOD'):
                    clone_res = subprocess.run(f'GIT_LFS_SKIP_SMUDGE=1 git clone {REPO_URL}', shell=True, capture_output=True, text=True)
                    if clone_res.returncode != 0:
                        error_msg = f"Git Clone Failed! Auth issue or repo missing.\nSTDERR: {clone_res.stderr}"
                        log.error(error_msg)
                        raise RuntimeError(error_msg)

                os.chdir('GroceryGOD')
                
                log.info("🔄 Forcing sync with latest GitHub master...")
                subprocess.run('git clean -fd', shell=True)
                subprocess.run('git fetch --all', shell=True)
                subprocess.run('git reset --hard origin/master', shell=True)

                log.info("🗑️ Purging LFS pointers to prevent SQLite corruption...")
                subprocess.run('find . -name "*.db" -type f -delete', shell=True)

            with Step('Repo Decryption', '🔓'):
                try:
                    import re as _re, glob as _glob, hashlib as _hashlib
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                    _KEY = os.environ.get('GOD_PREMIUM_KEY', '').strip()
                    if not _KEY: raise RuntimeError('GOD_PREMIUM_KEY not set')
                    _ITER = 250000
                    def _dec(data, pw):
                        if data[:4] != b'GGE1': raise ValueError('Bad magic')
                        s, iv, ct = data[4:20], data[20:32], data[32:]
                        k = _hashlib.pbkdf2_hmac('sha256', pw.encode(), s, _ITER, dklen=32)
                        return AESGCM(k).decrypt(iv, ct, None)
                    _cwd = os.getcwd()
                    _chunks = _glob.glob(os.path.join(_cwd, '**', '*.enc.[0-9][0-9][0-9]'), recursive=True)
                    _groups = {}
                    for cf in _chunks:
                        m = _re.match(r'(.+)\.enc\.([0-9]{3})$', cf)
                        if m: _groups.setdefault(m.group(1)+'.enc', []).append(cf)
                    for base, parts in _groups.items():
                        parts.sort()
                        log.info(f'  Reassembling {len(parts)} chunks -> {os.path.basename(base)}')
                        with open(base, 'wb') as out:
                            for p in parts:
                                with open(p, 'rb') as f: out.write(f.read())
                                os.remove(p)
                        os.remove(base)
                    _enc_files = _glob.glob(os.path.join(_cwd, '**', '*.enc'), recursive=True)
                    log.info(f'  Found {len(_enc_files)} encrypted files')
                    _dc = 0
                    for ep in _enc_files:
                        try:
                            with open(ep, 'rb') as f: d = f.read()
                            plain = _dec(d, _KEY)
                            with open(ep[:-4], 'wb') as f: f.write(plain)
                            os.remove(ep)
                            _dc += 1
                            log.info(f'  {os.path.relpath(ep, _cwd)} -> decrypted ({len(plain)//1024}KB)')
                        except Exception as ex:
                            log.error(f'  ERROR {os.path.basename(ep)}: {ex}')
                    log.info(f'  Decrypted {_dc}/{len(_enc_files)} files')
                except subprocess.CalledProcessError as e:
                    log.error(f'Decryption failed: {e.stderr[:500]}')
                    tg_send(f'⚠️ <b>Repo Decryption</b> — failed (non-fatal)', silent=True)

            SCRAPER_TIMEOUT = 30 * 60
            PARALLEL_MAX_WORKERS = 5
            ####################################################PARALLEL_MAX_WORKERS = 5
            def run_scraper(scraper_info):
                label, path = scraper_info
                log.info(f'Starting {label}...')
                t0 = time.time()
                full_path = os.path.join(os.getcwd(), path)
                import glob
                main_scraper = os.path.join(full_path, 'scraper.py')
                if os.path.exists(main_scraper):
                    script_targets = [main_scraper]
                else:
                    script_targets = glob.glob(os.path.join(full_path, 'scraper*.py'))
                
                if not script_targets:
                    error_msg = f"No scraper scripts found in {full_path}"
                    log.error(f"X {error_msg}")
                    tg_send(f'X <b>{label}</b> - {error_msg}', silent=True)
                    return label, False, 0, "missing"

                my_env = os.environ.copy()
                my_env["PYTHONUNBUFFERED"] = "1"
                my_env["PYTHONIOENCODING"] = "utf-8"
                my_env["GIT_TERMINAL_PROMPT"] = "0"
                total_lines = 0
                all_ok = True
                status_res = "ok"
                procs = []
                threads = []
                
                for script_target in script_targets:
                    try:
                        with open(script_target, 'r', encoding='utf-8') as f: code = f.read()
                        if 'DHAKA_TZ =' not in code:
                            patch = "import os\nfrom datetime import timezone, timedelta\nDHAKA_TZ = timezone(timedelta(hours=6))\n"
                            with open(script_target, 'w', encoding='utf-8') as f: f.write(patch + code)
                    except: pass

                    script_name = os.path.basename(script_target)
                    proc = subprocess.Popen([sys.executable, "-u", script_name], cwd=full_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=my_env, bufsize=1)
                    
                    stderr_capture = []
                    stdout_count = [0]
                    last_alive = [time.time()]
                    
                    def _read_stream(p, s_name, stream, is_stderr, capture, count, alive):
                        try:
                            for line in stream:
                                alive[0] = time.time()
                                if is_stderr:
                                    capture.append(line)
                                    log.warning(f'[{label}:{s_name} err] {line.rstrip()}')
                                else:
                                    count[0] += 1
                                    log.info(f'[{label}:{s_name}] {line.rstrip()}')
                        except: pass

                    t_stdout = threading.Thread(target=_read_stream, args=(proc, script_name, proc.stdout, False, stderr_capture, stdout_count, last_alive), daemon=True)
                    t_stderr = threading.Thread(target=_read_stream, args=(proc, script_name, proc.stderr, True, stderr_capture, stdout_count, last_alive), daemon=True)
                    t_stdout.start()
                    t_stderr.start()
                    
                    procs.append({
                        'proc': proc, 'name': script_name, 't_stdout': t_stdout, 't_stderr': t_stderr,
                        'stderr_capture': stderr_capture, 'stdout_count': stdout_count, 'last_alive': last_alive, 'timed_out': False, 'crashed': False
                    })
                
                # Monitor all procs
                deadline = time.time() + SCRAPER_TIMEOUT
                _last_10m_tg = None
                while True:
                    all_done = True
                    for p in procs:
                        if p['proc'].poll() is None:
                            all_done = False
                            _now = time.time()
                            # Intelligent stop: 10 mins without output
                            if _now - p['last_alive'][0] > 600:
                                p['proc'].kill()
                                p['timed_out'] = True
                                log.error(f"{label}:{p['name']} TIMED OUT (No output for 10m).")
                                tg_send(f"TIMEOUT <b>{label}:{p['name']}</b> (No output 10m).", silent=True)
                            
                            # Check cloudflare block in stderr
                            err_text = ''.join(p['stderr_capture'][-20:]).lower()
                            if 'cloudflare' in err_text or 'ip block' in err_text or '403 forbidden' in err_text:
                                p['proc'].kill()
                                p['crashed'] = True
                                log.error(f"{label}:{p['name']} BLOCKED (Cloudflare/IP).")
                                tg_send(f"BLOCKED <b>{label}:{p['name']}</b> (Cloudflare/IP issue).", silent=True)
                                
                    _now = time.time()
                    _elapsed = _now - t0
                    if _elapsed >= 1800:
                        if _last_10m_tg is None or (_now - _last_10m_tg) >= 600:
                            total_so_far = sum(p['stdout_count'][0] for p in procs)
                            proc_stats = "\n".join([f" • {p['name']}: {p['stdout_count'][0]} lines ({'running' if p['proc'].poll() is None else 'finished'})" for p in procs])
                            status_msg = f"⏳ <b>{label}</b> Status Update — Running for {_fmt_dur(_elapsed)}\nTotal lines: {total_so_far}\n{proc_stats}"
                            log.info(f"[{label}] Sending 10-min TG status report ({_fmt_dur(_elapsed)} elapsed)...")
                            tg_send(status_msg, silent=True)
                            _last_10m_tg = _now

                    if all_done or time.time() > deadline:
                        break
                    time.sleep(5)
                
                for p in procs:
                    if p['proc'].poll() is None:
                        p['proc'].kill()
                        p['timed_out'] = True
                        tg_send(f"TIMEOUT <b>{label}:{p['name']}</b> (Hard deadline).", silent=True)
                    p['t_stdout'].join(timeout=5)
                    p['t_stderr'].join(timeout=5)
                    total_lines += p['stdout_count'][0]
                    if p['timed_out']:
                        all_ok = False; status_res = "timeout"
                    elif p['crashed'] or p['proc'].returncode != 0:
                        all_ok = False; status_res = "crashed"

                elapsed = time.time() - t0
                
                # Combine stats
                stats_msg = "\n".join([f" - {p['name']}: {p['stdout_count'][0]} lines" for p in procs])
                if all_ok:
                    tg_msg = f"✅ 🟢 <b>{label}</b> — {_fmt_dur(elapsed)}\n{stats_msg}"
                else:
                    tg_msg = f"⚠️ <b>{label}</b> finished with errors — {_fmt_dur(elapsed)}\n{stats_msg}"

                tg_send(tg_msg, silent=False)
                return label, all_ok, total_lines, status_res

            with Step('History Reconstruction', '📄'):
                try:
                    subprocess.run([sys.executable, 'reconstruct_history.py'], check=True)
                    log.info("History successfully reconstructed from GitHub chunks.")
                except Exception as e:
                    log.error(f"History reconstruction failed: {e}. Proceeding with fresh start risk...")

            with Step('Market Scrapers (Parallel)', '🛸'):
                import platform, os, subprocess
                if platform.system() == 'Windows':
                    shopno_dir = r'C:\PROJECTS\shopno'
                    othoba_dir = r'C:\PROJECTS\othoba'
                else:
                    shopno_dir = '/kaggle/working/shopno'
                    othoba_dir = '/kaggle/working/othoba'
                if not os.path.exists(shopno_dir):
                    subprocess.run(f'git clone https://github.com/ranehal/SHWAPNO-analylics.git "{shopno_dir}"', shell=True)
                if not os.path.exists(othoba_dir):
                    subprocess.run(f'git clone https://github.com/ranehal/Othoba-analytics.git "{othoba_dir}"', shell=True)
                
                scrapers = [
                    ('Shwapno', 'swapnoTRACKER'), 
                    ('Othoba', 'othobaTRACKER'), 
                    ('Chaldal', 'chaldalTRACKER'), 
                    ('Meena Bazar', 'MEENAtracker'), 
                    ('Unimart', 'unimartTRACKER'), 
                    ('Metro Mart', 'metroTRACKER'), 
                    ('ShotejBazar', 'ShotejTRACKER'), 
                    ('FooDIE', 'FooDIEscraper')
                ]
                results = [None] * len(scrapers)
                log.info(f"Launching {len(scrapers)} scrapers in parallel (timeout={SCRAPER_TIMEOUT//3600}h each)")

                def _run_wrapper(idx, info):
                    return idx, run_scraper(info)

                log.info(f'Running scrapers in PARALLEL with {PARALLEL_MAX_WORKERS} workers...')
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL_MAX_WORKERS) as executor:
                    futures = {executor.submit(_run_wrapper, idx, s): idx for idx, s in enumerate(scrapers)}
                    for future in concurrent.futures.as_completed(futures):
                        idx = futures[future]
                        try:
                            results[idx] = future.result()[1]
                        except Exception as e:
                            log.error(f'Parallel execution error for scraper {scrapers[idx][0]}: {e}')
                            results[idx] = (scrapers[idx][0], False, 0, "exception")

                log.info("=== SCRAPER RESULTS SUMMARY ===\n" + "-"*60)
                _all_ok = True
                _status_emoji = {"ok": "OK", "timeout": "TIMEOUT", "crashed": "CRASH", "exception": "EXCEPTION", "missing": "MISSING"}
                for r in results:
                    _label, _ok, _lines, _status = r[0], r[1], r[2], r[3]
                    _emoji = _status_emoji.get(_status, "?")
                    log.info(f'  {_emoji} {_label} - lines={_lines} status={_status}')
                    if not _ok:
                        _all_ok = False
                log.info("-"*60)
                _ok_count = sum(1 for r in results if r[1])
                log.info(f'Result: {_ok_count}/{len(results)} scrapers OK')
                if not _all_ok:
                    _failed = [(r[0], r[3]) for r in results if not r[1]]
                    log.info(f'Failed: {_failed}')

                tg_send(f"SCRAPER RESULTS: {_ok_count}/{len(results)} OK", silent=True)
                for r in results:
                    _label, _ok, _lines, _status = r
                    _emoji = _status_emoji.get(_status, "?")
                    tg_send(f'{_emoji} {_label} - {_lines} lines [{_status}]', silent=True)

                log.info("Pushing all scraper data to GitHub...")
                tg_send("Pushing combined scraper data to GitHub...", silent=True)
                try:
                    subprocess.run('git add .', shell=True)
                    _now = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')
                    subprocess.run(f'git commit -m "parallel scrapers {_now} ({_ok_count}/{len(results)} OK)"', shell=True)
                    subprocess.run('git pull origin master --rebase -X ours', shell=True, capture_output=True)
                    subprocess.run('git push origin HEAD:master --force', shell=True, capture_output=True)
                    log.info("Combined scraper data pushed to GitHub successfully")
                    tg_send('Combined scraper data pushed to GitHub', silent=True)
                except Exception as push_err:
                    log.warning(f"Failed to push scraper data: {push_err}")

            with Step('GODdata Aggregator', '🧬'):
                _agg_env = os.environ.copy()
                _agg_proc = subprocess.Popen([sys.executable, 'aggregator.py'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=_agg_env)
                for _agg_line in _agg_proc.stdout:
                    log.info(f'[aggregator] {_agg_line.rstrip()}')
                _agg_proc.wait()
                if _agg_proc.returncode != 0:
                    log.error(f'Aggregator failed with code {_agg_proc.returncode}')
                    tg_send(f'⚠️ <b>Aggregator</b> failed (rc={_agg_proc.returncode})', silent=True)
                else:
                    log.info('Aggregator completed successfully')
                
                try:
                    count_file = 'run_count.txt'
                    run_count = 1
                    if os.path.exists(count_file):
                        with open(count_file, 'r') as f:
                            run_count = int(f.read().strip()) + 1
                    with open(count_file, 'w') as f:
                        f.write(str(run_count))
                    log.info(f"🔄 Persistent Run count updated to {run_count}")
                except Exception as e:
                    log.warning(f"Failed to update run count: {e}")

            with Step('Parquet Conversion', '📊'):
                try:
                    _pq_env = os.environ.copy()
                    _pq_proc = subprocess.Popen([sys.executable, 'convert_to_parquet.py'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=_pq_env)
                    for _pq_line in _pq_proc.stdout:
                        log.info(f'[parquet] {_pq_line.rstrip()}')
                    _pq_proc.wait()
                    if _pq_proc.returncode != 0:
                        raise subprocess.CalledProcessError(_pq_proc.returncode, 'convert_to_parquet.py')
                    for pf in ['products.parquet', 'history.parquet', 'products_free.parquet', 'history_free.parquet', 'premium/history_archive.parquet.enc']:
                        if os.path.exists(pf):
                            sz_mb = os.path.getsize(pf) / (1024*1024)
                            log.info(f'  {pf}: {sz_mb:.1f} MB')
                except subprocess.CalledProcessError as e:
                    log.error(f'Parquet conversion failed with code {e.returncode}')
                    tg_send(f'⚠️ <b>Parquet Conversion</b> — failed (non-fatal)', silent=True)

            with Step('Premium Key Rotation', '🔐'):
                new_key = get_secret_safe('GOD_PREMIUM_KEY_UPDATE', '')
                if new_key:
                    old_key = os.environ.get('GOD_PREMIUM_KEY', '')
                    enc_file = 'premium/history_archive.parquet.enc'
                    if old_key and os.path.exists(enc_file):
                        try:
                            res = subprocess.run([sys.executable, 'update_premium_key.py', old_key, new_key], capture_output=True, text=True, env=os.environ.copy())
                            if res.returncode == 0:
                                os.environ['GOD_PREMIUM_KEY'] = new_key
                                log.info('Premium key rotated successfully.')
                                tg_send('🔐 <b>Premium key rotated</b> — archive re-encrypted.')
                            else:
                                log.error(f'Key rotation failed: {res.stderr[:500]}')
                                tg_send(f'⚠️ <b>Premium key rotation failed</b>\n<pre>{html.escape(res.stderr[:300])}</pre>')
                        except Exception as e:
                            log.error(f'Key rotation error: {e}')
                    else:
                        log.info('Skipping key rotation: no old key or archive not found.')
                else:
                    log.info('No GOD_PREMIUM_KEY_UPDATE set — skipping key rotation.')

            with Step('Repo Encryption', '🔒'):
                try:
                    import glob as _glob, secrets as _secrets, hashlib as _hashlib
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                    _KEY = os.environ.get('GOD_PREMIUM_KEY', '').strip()
                    if not _KEY: raise RuntimeError('GOD_PREMIUM_KEY not set')
                    _ITER = 250000
                    _SPLIT = 40 * 1024 * 1024
                    def _enc(data, pw):
                        salt, iv = _secrets.token_bytes(16), _secrets.token_bytes(12)
                        k = _hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, _ITER, dklen=32)
                        ct = AESGCM(k).encrypt(iv, data, None)
                        return b'GGE1' + salt + iv + ct
                    def _write_enc(path, data):
                        if len(data) <= _SPLIT:
                            with open(path, 'wb') as f: f.write(data)
                            return [path]
                        if os.path.exists(path): os.remove(path)
                        cp = []
                        for i in range(0, len(data), _SPLIT):
                            idx = i // _SPLIT
                            cp.append(f'{path}.{idx:03d}')
                            with open(cp[-1], 'wb') as f: f.write(data[i:i+_SPLIT])
                        return cp
                    _cwd = os.getcwd()
                    _targets = []
                    for pat in ['*_data_part*.js', '*_manifest.js']:
                        _targets.extend(_glob.glob(os.path.join(_cwd, pat)))
                    for tf in ['PRICETRACKER/data.js', 'swapnoTRACKER/data.json', 'unimartTRACKER/data.json', 'ShotejTRACKER/data.json', 'data.json', 'data.js']:
                        p = os.path.join(_cwd, tf)
                        if os.path.exists(p): _targets.append(p)
                    for d in ['swapnoTRACKER', 'PRICETRACKER', 'MEENAtracker/backend', 'othobaTRACKER/backend', 'metroTRACKER/backend', 'unimartTRACKER', 'ShotejTRACKER']:
                        p = os.path.join(_cwd, d, 'scraper.py')
                        if os.path.exists(p): _targets.append(p)
                    for dbf in _glob.glob(os.path.join(_cwd, '**', '*.db'), recursive=True):
                        _targets.append(dbf)
                    for pq in ['products.parquet', 'history.parquet']:
                        p = os.path.join(_cwd, pq)
                        if os.path.exists(p): _targets.append(p)
                    pa = os.path.join(_cwd, 'premium', 'history_archive.parquet')
                    if os.path.exists(pa): _targets.append(pa)
                    _targets = [t for t in _targets if os.path.exists(t) and not t.endswith('.enc')]
                    log.info(f'  Encrypting {len(_targets)} files')
                    _ec = 0
                    for tp in _targets:
                        try:
                            with open(tp, 'rb') as f: data = f.read()
                            ed = _enc(data, _KEY)
                            ep = tp + '.enc'
                            for old in _glob.glob(ep + '.*'): os.remove(old)
                            cps = _write_enc(ep, ed)
                            _ec += 1
                            rel = os.path.relpath(tp, _cwd)
                            if len(cps) == 1:
                                log.info(f'  {rel} -> .enc ({len(ed)//1024}KB)')
                            else:
                                log.info(f'  {rel} -> .enc ({len(ed)//1024}KB, {len(cps)} chunks)')
                            os.remove(tp)
                        except Exception as ex:
                            log.error(f'  ERROR {os.path.basename(tp)}: {ex}')
                    log.info(f'  Encrypted {_ec}/{len(_targets)} files')
                except subprocess.CalledProcessError as e:
                    log.error(f'Encryption failed: {e.stderr[:500]}')
                    tg_send(f'⚠️ <b>Repo Encryption</b> — failed (non-fatal)', silent=True)

            with Step('GitHub Push Guard', '🛡️'):
                subprocess.run([sys.executable, 'guardrail.py'], check=True)
                
                # 🛡️ FIX: NUCLEAR LFS PROTECTION SYSTEM
                # Tearing down Git LFS completely locally to bypass GitHub's budget blocks
                log.info("🛡️ Deactivating local Git LFS configurations to bypass account budget lock...")
                subprocess.run('git lfs uninstall --local', shell=True)
                if os.path.exists('.git/hooks/pre-push'):
                    try: os.remove('.git/hooks/pre-push')
                    except: pass

                # Stripping any wildcard LFS rules from .gitattributes to treat data as normal files
                if os.path.exists('.gitattributes'):
                    try:
                        with open('.gitattributes', 'r') as f:
                            lines = f.readlines()
                        clean_lines = [l for l in lines if 'filter=lfs' not in l.lower() or '.db' in l.lower()]
                        with open('.gitattributes', 'w') as f:
                            f.writelines(clean_lines)
                    except: pass
                
                subprocess.run('git add .', shell=True)
                now = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')
                subprocess.run(f'git commit -m "attempt #{cycle_count} if this works ill get some sleep frfr: {now}"', shell=True)
                
                push_success = False
                for attempt in range(3):
                    log.info(f"Push attempt {attempt+1}...")
                    subprocess.run('git pull origin master --rebase -X ours', shell=True)
                    push_res = subprocess.run('git push origin HEAD:master --force', shell=True, capture_output=True, text=True)
                    
                    if push_res.returncode == 0:
                        push_success = True
                        break
                    else:
                        log.warning(f"Push attempt {attempt+1} failed. Error: {push_res.stderr}")
                        time.sleep(10)
                
                if not push_success:
                    git_status = subprocess.run('git status', shell=True, capture_output=True, text=True).stdout
                    error_msg = f"Git push failed after 3 attempts!\nGit Status:\n{git_status[:300]}\nStderr: {push_res.stderr[:300]}"
                    log.error(error_msg)
                    raise RuntimeError(error_msg)

                tg_send(f'🚀 <b>GitHub Push Successful (Cycle {cycle_count})!</b>\n🌐 Live at https://ranx-x.github.io/GroceryGOD')

            # Collect & send detailed cycle report
            try:
                _report = []
                _report.append("=== GroceryGOD CYCLE REPORT (Cycle {}) ===".format(cycle_count))
                _report.append("Date: {}".format(datetime.now(DHAKA_TZ).strftime("%Y-%m-%d %H:%M:%S DHAKA")))
                try: _report.append("Kaggle IP: {}".format(requests.get('https://api.ipify.org', timeout=5).text))
                except: _report.append("Kaggle IP: unknown")
                _report.append("")

                # Scraper diagnostics from last_run_log.txt
                _scraper_dirs = [("Shwapno", "swapnoTRACKER"), ("Chaldal", "PRICETRACKER"), ("Meena Bazar", "MEENAtracker/backend"),
                                 ("Othoba", "othobaTRACKER/backend"), ("Unimart", "unimartTRACKER"),
                                 ("Metro Mart", "metroTRACKER/backend"), ("ShotejBazar", "ShotejTRACKER")]
                for _sn, _sd in _scraper_dirs:
                    _lf = os.path.join(os.getcwd(), _sd, "last_run_log.txt")
                    if os.path.exists(_lf):
                        try:
                            with open(_lf, "r", encoding="utf-8") as _fh:
                                _log_txt = _fh.read()
                            if _log_txt.strip():
                                _report.append(f"[{_sn}] last_run_log.txt:")
                                _report.append(_log_txt.strip()[:1500])
                                _report.append("---")
                        except: pass

                # Appended main log (last 300 lines)
                _main_log = "/tmp/grocerygod_run.log"
                if os.path.exists(_main_log):
                    try:
                        with open(_main_log, "r", encoding="utf-8") as _fh:
                            _all_lines = _fh.readlines()
                        _report.append("=== MAIN LOG (last 300 lines) ===")
                        _report.extend(l.rstrip() for l in _all_lines[-300:])
                    except: pass

                _report_path = "/tmp/grocerygod_cycle_report.txt"
                with open(_report_path, "w", encoding="utf-8") as _fh:
                    _fh.write("\n".join(_report))
                tg_send_file(_report_path, f"📊 Cycle {cycle_count} Report")
            except Exception as _re:
                log.warning(f"Failed to send detailed cycle report: {_re}")


        except Exception as e:
            safe_tb = html.escape(traceback.format_exc()[-500:])
            err_msg = f"💥 <b>GroceryGOD CRITICAL FAILURE (Cycle {cycle_count})!</b>\nError: {html.escape(str(e))}\n<pre>{safe_tb}</pre>"
            print(err_msg)
            tg_send(err_msg)
        
        log.info(f"✅ Cycle {cycle_count} Sequence Finished. Sleeping for 8 hours...")
        #####################################################################################_sleep_end = time.time() + 8*3600
        _sleep_end = time.time() + 8*3600
        while time.time() < _sleep_end:
            _remaining = int(_sleep_end - time.time())
            _hrs = _remaining // 3600
            _mins = (_remaining % 3600) // 60
            if _remaining % 600 < 60:
                log.info(f'💤 Sleeping... {_hrs}h {_mins}m remaining (Cycle {cycle_count})')
            time.sleep(min(300, _remaining))
        cycle_count += 1

# ============================================================
# PIPELINE 2: GITWW
# ============================================================
def run_gitw():
    print("[gitw] Process Started.")

    subprocess.run('git clone https://github.com/ranehal/gitww.git', shell=True)
    subprocess.run('unzip -o -P "ran.ragibahnafnehal2@gmail.com" gitww/gitw.dll', shell=True)
    
    if os.path.exists('gitw'):
        os.chdir('gitw')

    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=True)
    
    processes = []
    my_env = os.environ.copy()
    for i in range(1, 35):
        p = subprocess.Popen([sys.executable, f"{i}.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=my_env)
        processes.append((i, p))
        
    for i, p in processes:
        p.wait()
        
    run_count = "Unknown"
    count_path = '/kaggle/working/GroceryGOD/run_count.txt'
    if os.path.exists(count_path):
        try:
            with open(count_path, 'r') as f:
                run_count = f.read().strip()
        except: pass
        
    now = datetime.now(DHAKA_TZ)
    msg = f"🚀 <b>gitw Execution Completed Early!</b>\n🔄 Run Count: {run_count}\n📅 Date: {now.strftime('%Y-%m-%d')}\n🕒 Time: {now.strftime('%H:%M:%S')}"
    try: 
        if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != "":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})
    except: pass

# ============================================================


def format_clean_status(label, elapsed, line_count, tail_lines, summary_log=None):
    if summary_log and len(summary_log.strip()) > 10:
        return f"✅ 🟢 <b>{label}</b> — Completed in {int(elapsed)}s ({line_count} lines)\n\n{summary_log}"
    
    combined_raw = "\n".join(tail_lines)
    
    # Extract totals & scraped counts
    total_match = re.search(r'\((\d+)\s*total products\)', combined_raw, re.IGNORECASE) or re.search(r'Total [Scraped|Products]*:\s*(\d+)', combined_raw, re.IGNORECASE)
    scraped_match = re.search(r'Scraped\s+(\d+)\s+unique products', combined_raw, re.IGNORECASE) or re.search(r'Unique Products:\s*(\d+)', combined_raw, re.IGNORECASE)
    
    total_str = f"{int(total_match.group(1)):,} total" if total_match else None
    scraped_str = f"{int(scraped_match.group(1)):,} unique" if scraped_match else None
    
    # Filter out zero product noise lines (: 0 products)
    filtered_lines = []
    for l in tail_lines:
        line_s = l.strip()
        if not line_s: continue
        if line_s.endswith(': 0 products') or ': 0 products in' in line_s: continue
        filtered_lines.append(line_s)
        
    clean_tail = "\n".join(filtered_lines[-6:])
    
    msg = f"✅ 🟢 <b>{label}</b> — Completed in {int(elapsed)}s ({line_count} lines)"
    if total_str or scraped_str:
        msg += "\n------------------------------"
        if total_str: msg += f"\n📦 Master Catalog: {total_str}"
        if scraped_str: msg += f"\n⚡ Scraped Items: {scraped_str}"
        msg += "\n------------------------------"
    if clean_tail:
        msg += f"\n<pre>{html.escape(clean_tail)}</pre>"
        
    return msg

def run_scheduled_repo(repo_url, script_name, label, github_pat):

    print(f"[{label}] Process Started.")

    def tg_send(text, silent=False):
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.strip() == "": return
        TG_API = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'
        try:
            requests.post(f'{TG_API}/sendMessage', json={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML', 'disable_notification': silent}, timeout=15)
        except: pass

    if not github_pat or github_pat.strip() == "":
        err_pat = f"GITHUB_PAT is missing or empty for {label}. Git push will fail."
        print(f"❌ [{label}] {err_pat}")
        tg_send(f"❌ <b>{label}</b> — {err_pat}")
        return

    tg_send(f"🚀 <b>{label}</b> — Run Started")
    os.chdir('/kaggle/working')
    repo_name = repo_url.split('/')[-1].replace('.git', '')
    auth_repo_url = f"https://ranehal:{github_pat}@github.com/ranehal/{repo_name}.git"

    try:
        subprocess.run('git config user.email "ranehal@users.noreply.github.com"', shell=True)
        subprocess.run('git config user.name "ranehal"', shell=True)
        cred_path = os.path.expanduser('~/.git-credentials')
        with open(cred_path, 'w') as f:
            f.write(f"https://ranehal:{github_pat}@github.com\nhttps://ranx-x:{github_pat}@github.com\nhttps://{github_pat}@github.com\n")
        subprocess.run('git config --global credential.helper store', shell=True)

        if not os.path.exists(repo_name):
            print(f"[{label}] Cloning {repo_name}...")
            clone_res = subprocess.run(f'git clone {auth_repo_url}', shell=True, capture_output=True, text=True)
            if clone_res.returncode != 0:
                raise RuntimeError(f"Git clone failed: {clone_res.stderr}")

        os.chdir(repo_name)
        subprocess.run('git config user.email "educational.purpose37@gmail.com"', shell=True)
        subprocess.run('git config user.name "ranx-x"', shell=True)
        subprocess.run(f'git remote set-url origin {auth_repo_url}', shell=True)

        subprocess.run('git clean -fd', shell=True)
        subprocess.run('git fetch --all', shell=True)
        branch_res = subprocess.run('git symbolic-ref refs/remotes/origin/HEAD', shell=True, capture_output=True, text=True)
        default_branch = branch_res.stdout.strip().split('/')[-1] if branch_res.returncode == 0 else 'main'
        subprocess.run(f'git reset --hard origin/{default_branch}', shell=True)

        if os.path.exists('requirements.txt'):
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=False)

        # Auto-install essential scraping dependencies if missing
        _deps_to_check = ['playwright', 'httpx', 'requests', 'bs4', 'lxml']
        for _dep in _deps_to_check:
            try:
                __import__(_dep)
            except ImportError:
                _pkg = 'beautifulsoup4' if _dep == 'bs4' else _dep
                print(f"[{label}] Auto-installing missing dependency: {_pkg}...")
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", _pkg], check=False)
        
        # Ensure Playwright Chromium browser binary is always installed
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False, capture_output=True)
        except: pass

        # Auto-detect script name recursively if expected script_name does not exist
        if not os.path.exists(script_name):
            import glob
            exact_matches = glob.glob(f'**/{script_name}', recursive=True)
            if exact_matches:
                script_name = exact_matches[0]
            else:
                py_files = [f for f in glob.glob('**/*.py', recursive=True) if not os.path.basename(f).startswith('__') and os.path.basename(f) != 'setup.py']
                preferred = [f for f in py_files if any(k in f.lower() for k in ['scraper', 'main', 'run', 'meena', 'app', 'web'])]
                if preferred:
                    script_name = preferred[0]
                elif py_files:
                    script_name = py_files[0]
                else:
                    err_msg = f"No executable python script found in {repo_name} (expected '{script_name}')."
                    print(f"❌ [{label}] {err_msg}")
                    tg_send(f"⚠️ <b>{label}</b> — {err_msg}", silent=True)
                    return
            print(f"[{label}] Target script auto-resolved to: {script_name}")

        # Auto-patch Cat NoneType error safety with indentation preservation
        if os.path.exists(script_name):
            try:
                import re as _re
                with open(script_name, 'r', encoding='utf-8') as sf:
                    s_code = sf.read()
                if 'for prod in cat.get("products", []):' in s_code and 'isinstance(cat, dict)' not in s_code:
                    print(f"[{label}] Auto-patching cat dict-type safety in {script_name}...")
                    pattern = r'([ \t]*)for prod in cat\.get\("products", \[\]\):'
                    m = _re.search(pattern, s_code)
                    if m:
                        indent = m.group(1)
                        replacement = f'{indent}if not cat or not isinstance(cat, dict): continue\n{indent}for prod in cat.get("products", []):'
                        s_code = _re.sub(pattern, replacement, s_code, count=1)
                        with open(script_name, 'w', encoding='utf-8') as sf:
                            sf.write(s_code)
            except Exception as patch_err:
                print(f"[{label}] Script patch warning: {patch_err}")

        script_abs_path = os.path.abspath(script_name)
        script_dir = os.path.dirname(script_abs_path)
        script_file = os.path.basename(script_abs_path)

        max_script_retries = 3
        for _attempt in range(1, max_script_retries + 1):
            print(f"[{label}] Executing {script_file} in {script_dir} (attempt {_attempt}/{max_script_retries})...")
            t0 = time.time()
            my_env = os.environ.copy()
            my_env["PYTHONPATH"] = f"{script_dir}{os.pathsep}{os.getcwd()}{os.pathsep}{my_env.get('PYTHONPATH', '')}"
            my_env["PYTHONUNBUFFERED"] = "1"
            my_env["PYTHONIOENCODING"] = "utf-8"
            res = subprocess.run([sys.executable, "-u", script_file], cwd=script_dir, capture_output=True, text=True, timeout=5*18000, env=my_env)
            elapsed = time.time() - t0
            if res.returncode == 0:
                break
            safe_err = html.escape(res.stderr[:500])
            if _attempt == max_script_retries:
                raise RuntimeError(f"Script {script_name} failed in {script_dir}:\n{safe_err}")
            print(f"[WARN] {label} attempt {_attempt} failed (rc={res.returncode}), retrying...\n{safe_err[:200]}")
            time.sleep(10)

        print(f"[{label}] Finished in {int(elapsed)}s. Pushing to GitHub as ranehal...")
        subprocess.run(f"git remote set-url origin https://ranehal:{github_pat}@github.com/ranehal/{repo_name}.git", shell=True)
        subprocess.run('git config user.name "ranehal"', shell=True)
        subprocess.run('git config user.email "ranehal@users.noreply.github.com"', shell=True)
        subprocess.run('git add .', shell=True)
        now_str = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')
        subprocess.run(f'git commit -m "if this works ill get some sleep frfr {now_str}"', shell=True)

        push_success = False
        auth_user_urls = [
            f"https://ranehal:{github_pat}@github.com/ranehal/{repo_name}.git",
            f"https://ranx-x:{github_pat}@github.com/ranehal/{repo_name}.git",
            f"https://{github_pat}@github.com/ranehal/{repo_name}.git"
        ]
        for auth_u in auth_user_urls:
            user_n = "ranehal" if "ranehal" in auth_u else "ranx-x"
            subprocess.run(f'git remote set-url origin {auth_u}', shell=True)
            subprocess.run(f'git config user.name "{user_n}"', shell=True)
            subprocess.run(f'git config user.email "{user_n}@users.noreply.github.com"', shell=True)
            for attempt in range(2):
                subprocess.run(f'git pull origin {default_branch} --rebase -X ours -q', shell=True, capture_output=True)
                push_res = subprocess.run(f'git push origin HEAD:{default_branch} --force', shell=True, capture_output=True, text=True)
                if push_res.returncode == 0:
                    push_success = True
                    break
                time.sleep(3)
            if push_success: break

        if not push_success:
            raise RuntimeError(f"Git push failed: {push_res.stderr[:300]}")

        tg_send(f"✅ <b>{label}</b> — Completed in {int(elapsed)}s! Pushed to GitHub.")
    except Exception as e:
        safe_tb = html.escape(traceback.format_exc()[-500:])
        err_msg = f"❌ <b>{label} FAILED!</b>\nError: {html.escape(str(e))}\n<pre>{safe_tb}</pre>"
        print(err_msg)
        tg_send(err_msg)

# MASTER ORCHESTRATOR LOOP
# ============================================================
if __name__ == '__main__':
    run_preflight_checks()
    
    print("🚀 Launching BOTH pipelines in Parallel...")
    
    p1 = multiprocessing.Process(target=run_grocery_god, args=(GITHUB_PAT,))
    p2 = multiprocessing.Process(target=run_gitw)
    p3 = multiprocessing.Process(target=run_scheduled_repo, args=('https://github.com/ranehal/FooDIE-RESTaurant-Analytics.git', 'scrape_menus.py', ' FooDIE Restaurant Analytics', GITHUB_PAT))
    p4 = multiprocessing.Process(target=run_scheduled_repo, args=('https://github.com/ranehal/FoodPANDA-RESTaurant-ANALytics.git', 'scrape_menus.py', ' FoodPANDA Restaurant Analytics', GITHUB_PAT))
    p5 = multiprocessing.Process(target=run_scheduled_repo, args=('https://github.com/ranehal/FooDIE-mart-Analytics.git', 'scraper.py', ' FooDIE Mart Analytics', GITHUB_PAT))
    p6 = multiprocessing.Process(target=run_scheduled_repo, args=('https://github.com/ranehal/SHWAPNO-analylics.git', 'scraper.py', ' Shwapno Analytics', GITHUB_PAT))
    p7 = multiprocessing.Process(target=run_scheduled_repo, args=('https://github.com/ranehal/Othoba-analytics.git', 'scraper.py', ' Othoba Analytics', GITHUB_PAT))
    p8 = multiprocessing.Process(target=run_scheduled_repo, args=('https://github.com/ranehal/CARTup-analytics.git', 'scraper.py', ' CARTup Analytics', GITHUB_PAT))
    p9 = multiprocessing.Process(target=run_scheduled_repo, args=('https://github.com/ranehal/CHALdal-analytics.git', 'scraper.py', ' Chaldal Analytics', GITHUB_PAT))
    p10 = multiprocessing.Process(target=run_scheduled_repo, args=('https://github.com/ranehal/COOKup-analytics.git', 'scraper.py', ' COOKup Analytics', GITHUB_PAT))
    p11 = multiprocessing.Process(target=run_scheduled_repo, args=('https://github.com/ranehal/PICAboo-analytics.git', 'scraper.py', ' PICAboo Analytics', GITHUB_PAT))
    p12 = multiprocessing.Process(target=run_scheduled_repo, args=('https://github.com/ranehal/DARAZ-analytics.git', 'scraper.py', ' DARAZ Analytics', GITHUB_PAT))
    p13 = multiprocessing.Process(target=run_scheduled_repo, args=('https://github.com/ranehal/MEEnaBAzar-analylics.git', 'scraper.py', ' Meena Bazar Analytics', GITHUB_PAT))
    
    p1.start()
    p2.start()
    p3.start()
    p4.start()
    p5.start()
    p6.start()
    p7.start()
    p8.start()
    p9.start()
    p10.start()
    p11.start()
    p12.start()
    p13.start()
    
    start_time = time.time()
    timeout_seconds = (11 * 3600) + (50 * 60) 

    while time.time() - start_time < timeout_seconds:
        if not any(p.is_alive() for p in [p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13]):
            print("\n✅ Both parallel pipelines finished ahead of schedule!")
            break
        time.sleep(30)
    else:
        print("\n⏳ Time limit threshold reached (11h 30m).")
        try:
            if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != "":
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": "⏳ <b>11h 30m Time limit reached!</b>\nInitiating nuclear teardown & Kaggle restart...", "parse_mode": "HTML"})
        except: pass

    print("☢️ Executing Nuclear Teardown of orphaned child processes...")
    os.system("pkill -9 -f chromium")
    os.system("pkill -9 -f scraper.py")
    for i in range(1, 35):
        os.system(f"pkill -9 -f {i}.py")

    for p in [p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13]:
        if p.is_alive():
            p.terminate()
            p.join(timeout=5)
    
    time.sleep(5)
    print("\n🔄 Triggering next cycle...")
    # Report p3-p5 exit status
    for _n, _p in [("FooDIE Rest", p3), ("FoodPANDA Rest", p4), ("FooDIE Mart", p5), ("Shwapno Analytics", p6), ("Othoba Analytics", p7), ("CARTup", p8), ("Chaldal Analytics", p9), ("COOKup", p10), ("PICAboo", p11), ("DARAZ", p12), ("Meena Bazar Analytics", p13)]:
        s = "OK" if _p.exitcode == 0 else f"rc={_p.exitcode}" if _p.exitcode is not None else "alive"
        print(f"[p3-p5] {_n}: {s}")
    
    trigger_self_restart()

