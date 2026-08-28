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
import re
import concurrent.futures
import platform
import glob
from datetime import datetime, timedelta, timezone

# Dhaka Timezone
DHAKA_TZ = timezone(timedelta(hours=6))

try:
    import fcntl
except ImportError:
    fcntl = None

def _with_lock(lock_key, fn, timeout=900):
    """Serialize a critical section across parallel processes (git config, apt/playwright installs)."""
    if fcntl is not None:
        _fd = os.open(f"/tmp/{lock_key}.lck", os.O_CREAT | os.O_RDWR, 0o600)
        _deadline = time.time() + timeout
        try:
            while True:
                try:
                    fcntl.flock(_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.time() > _deadline:
                        break
                    time.sleep(5)
            return fn()
        finally:
            try: fcntl.flock(_fd, fcntl.LOCK_UN)
            except OSError: pass
            os.close(_fd)
    return fn()

def _git_config(cmd_str):
    """Run git config with retry on concurrent lock contention."""
    for _i in range(8):
        _res = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
        if "could not lock" in ((_res.stderr or "") + (_res.stdout or "")).lower():
            time.sleep(4)
            continue
        return _res
    return _res

def _reclaim_disk(force=False):
    """Free disk space before large clones. Returns free GB after cleanup."""
    try:
        _free_before = shutil.disk_usage('/kaggle/working').free / (1024 ** 3)
        if not force and _free_before >= 3.0:
            return _free_before
        print(f"[DISK] Free space {_free_before:.2f} GB — reclaiming disk...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "cache", "purge"], capture_output=True, text=True)
        except Exception: pass
        for _sh in [
            'rm -rf /root/.cache/pip 2>/dev/null',
            'rm -rf /var/lib/apt/lists/* 2>/dev/null',
            'find /kaggle/working -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null',
            'find /kaggle/working -name "*.pyc" -delete 2>/dev/null',
            'find /kaggle/working -name "_scraper_error_*.log" -delete 2>/dev/null',
        ]:
            try: subprocess.run(_sh, shell=True, capture_output=True, text=True)
            except Exception: pass
        _free_after = shutil.disk_usage('/kaggle/working').free / (1024 ** 3)
        print(f"[DISK] After cleanup: {_free_after:.2f} GB free.")
        return _free_after
    except Exception as e:
        print(f"[DISK] Cleanup warning: {e}")
        return 0.0

# ============================================================
# INITIALIZATION & SECRETS
# ============================================================
_PERSISTED_SECRETS = {}

def get_secret_safe(key, default=""):
    # 1. Try Kaggle UserSecretsClient (UI attached)
    try:
        from kaggle_secrets import UserSecretsClient
        val = UserSecretsClient().get_secret(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    except Exception:
        pass

    # 2. Try OS Environment
    val = os.environ.get(key)
    if val is not None and str(val).strip():
        return str(val).strip()

    # 3. Try Injected Persisted Secrets (auto-propagated across container restarts)
    if isinstance(globals().get('_PERSISTED_SECRETS'), dict):
        val = _PERSISTED_SECRETS.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()

    # 4. Try attached Kaggle Dataset fallback (e.g. /kaggle/input/**/secrets*.json or vault)
    try:
        import glob
        for f in glob.glob('/kaggle/input/**/secrets*.json', recursive=True) + glob.glob('/kaggle/input/**/vault*.json', recursive=True):
            with open(f, 'r', encoding='utf-8') as jf:
                data = json.load(jf)
                if key in data and data[key]:
                    return str(data[key]).strip()
    except Exception:
        pass

    return default

GITHUB_PAT = get_secret_safe('GITHUB_PAT')
os.environ['KAGGLE_USERNAME'] = get_secret_safe('KAGGLE_USERNAME')
os.environ['KAGGLE_KEY'] = get_secret_safe('KAGGLE_KEY')
TELEGRAM_BOT_TOKEN = get_secret_safe("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret_safe("TELEGRAM_CHAT_ID")
os.environ["TELEGRAM_BOT_TOKEN"] = TELEGRAM_BOT_TOKEN or ""
os.environ["TELEGRAM_CHAT_ID"] = TELEGRAM_CHAT_ID or ""
KAGGLE_KERNEL_SLUG = get_secret_safe("KAGGLE_KERNEL_SLUG", "ranehalx/gitgod")
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

        # Persist active runtime secrets into the payload notebook so the self-booted container has them
        active_secrets = {
            'GITHUB_PAT': GITHUB_PAT or '',
            'KAGGLE_USERNAME': os.environ.get('KAGGLE_USERNAME', ''),
            'KAGGLE_KEY': os.environ.get('KAGGLE_KEY', ''),
            'TELEGRAM_BOT_TOKEN': os.environ.get('TELEGRAM_BOT_TOKEN', ''),
            'TELEGRAM_CHAT_ID': os.environ.get('TELEGRAM_CHAT_ID', ''),
            'KAGGLE_KERNEL_SLUG': KAGGLE_KERNEL_SLUG or 'ranehalx/gitgod',
            'GOD_PREMIUM_KEY': os.environ.get('GOD_PREMIUM_KEY', 'assalamualaikum')
        }

        try:
            with open(code_filename, 'r', encoding='utf-8') as nbf:
                nb_data = json.load(nbf)

            injected = False
            for cell in nb_data.get('cells', []):
                if cell.get('cell_type') == 'code':
                    lines = cell.get('source', [])
                    new_lines = []
                    for l in lines:
                        if l.startswith('_PERSISTED_SECRETS ='):
                            new_lines.append(f"_PERSISTED_SECRETS = {json.dumps(active_secrets)}\n")
                            injected = True
                        else:
                            new_lines.append(l)
                    if not injected:
                        new_lines.insert(0, f"_PERSISTED_SECRETS = {json.dumps(active_secrets)}\n")
                        injected = True
                    cell['source'] = new_lines
                    break

            with open(code_filename, 'w', encoding='utf-8') as nbf:
                json.dump(nb_data, nbf, indent=1)
            print(f"[SYSTEM] Successfully baked active secrets into payload {code_filename} for seamless self-boot.")
        except Exception as _sec_err:
            print(f"[SYSTEM] Warning: Could not bake secrets into notebook payload: {_sec_err}")

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
                return False
    # ONE-TIME INITIALIZATIONS
    os.chdir('/kaggle/working')
    try:
        log.info('🚀 GroceryGOD Environment Booting Up...')
        get_ips()
        with Step('Environment Sync', '📦'):
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", "playwright", "httpx", "beautifulsoup4", "lxml", "sqlalchemy", "aiosqlite", "requests", "pyarrow"], check=True)
            except Exception as _pip_err:
                log.warning(f"pip install failed (non-fatal): {_pip_err}")

            def _env_sync():
                _pw_ok = False
                for _cmd in ([sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
                             [sys.executable, "-m", "playwright", "install", "chromium"]):
                    try:
                        _r = subprocess.run(_cmd, capture_output=True, text=True)
                        if _r.returncode == 0:
                            _pw_ok = True
                            break
                        log.warning(f"playwright install failed: {(_r.stderr or '')[:300]}")
                    except Exception as _pw_err:
                        log.warning(f"playwright install error: {_pw_err}")
                if not _pw_ok:
                    log.warning("Chromium install failed (non-fatal). Playwright-based scrapers may crash.")
                subprocess.run('apt-get update -y -q 2>/dev/null', shell=True)
                try:
                    subprocess.run(['apt-get', 'install', '-y', '-q', 'sqlite3'], check=True)
                except Exception as _sq_err:
                    log.warning(f"sqlite3 install failed (non-fatal): {_sq_err}")

            _with_lock('playwright-install', _env_sync)
    except Exception as e:
        log.error("Environment Setup Failed. Terminating GroceryGOD loop thread.")
        return

    # SINGLE RUN PIPELINE (NO INFINITE LOOP)
    cycle_count = 1
    os.chdir('/kaggle/working')
    
    try:
        log.info(f'🚀 GroceryGOD Pipeline — STARTED (Simultaneous Parallel)')
        with Step('Configuration & Git Setup', '⚙️'):
            if not github_pat:
                raise RuntimeError("GITHUB_PAT is missing or empty. Git operations will fail.")

            def _setup_git_config():
                _git_config('git config --global user.email "ranehal@users.noreply.github.com"')
                _git_config('git config --global user.name "ranehal"')

                cred_path = os.path.expanduser('~/.git-credentials')
                with open(cred_path, 'w') as f:
                    f.write(f"https://ranehal:{github_pat}@github.com\nhttps://{github_pat}@github.com\n")
                _git_config('git config --global credential.helper store')
            _with_lock('git-config', _setup_git_config)

            REPO_URL = 'https://github.com/ranehal/GroceryGOD.git'
            auth_grocery_url = f"https://ranehal:{github_pat}@github.com/ranehal/GroceryGOD.git"

            if os.path.exists('GroceryGOD/.git/index.lock'):
                subprocess.run('rm -f GroceryGOD/.git/index.lock', shell=True)

            if not os.path.exists('GroceryGOD'):
                _reclaim_disk(force=True)
                clone_res = subprocess.run(f'GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --single-branch --branch master --no-tags {auth_grocery_url} GroceryGOD', shell=True, capture_output=True, text=True)
                if clone_res.returncode != 0:
                    error_msg = f"Git Clone Failed! Auth issue or repo missing.\nSTDERR: {clone_res.stderr}"
                    log.error(error_msg)
                    raise RuntimeError(error_msg)

            os.chdir('GroceryGOD')
            subprocess.run(f'git remote set-url origin {auth_grocery_url}', shell=True)
            
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

            SCRAPER_TIMEOUT = 45 * 60
            PARALLEL_MAX_WORKERS = 8
            ####################################################PARALLEL_MAX_WORKERS = 8
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
                            
                            # Check cloudflare block in stderr
                            err_text = ''.join(p['stderr_capture'][-20:]).lower()
                            if 'cloudflare' in err_text or 'ip block' in err_text or '403 forbidden' in err_text:
                                p['proc'].kill()
                                p['crashed'] = True
                                log.error(f"{label}:{p['name']} BLOCKED (Cloudflare/IP).")
                                
                    _now = time.time()
                    _elapsed = _now - t0

                    if all_done or time.time() > deadline:
                        break
                    time.sleep(5)
                
                for p in procs:
                    if p['proc'].poll() is None:
                        p['proc'].kill()
                        p['timed_out'] = True
                        log.error(f"{label}:{p['name']} TIMED OUT (Hard deadline).")
                    p['t_stdout'].join(timeout=5)
                    p['t_stderr'].join(timeout=5)
                    total_lines += p['stdout_count'][0]
                    if p['timed_out']:
                        all_ok = False; status_res = "timeout"
                    elif p['crashed'] or p['proc'].returncode != 0:
                        all_ok = False; status_res = "crashed"

                elapsed = time.time() - t0
                stats_msg = ", ".join([f"{p['name']}: {p['stdout_count'][0]} lines" for p in procs])
                if all_ok:
                    log.info(f"✅ {label} — {_fmt_dur(elapsed)} ({stats_msg})")
                else:
                    log.warning(f"⚠️ {label} finished with errors — {_fmt_dur(elapsed)} ({stats_msg})")

                return label, all_ok, total_lines, status_res

            with Step('History Reconstruction', '📄'):
                try:
                    subprocess.run([sys.executable, 'reconstruct_history.py'], check=True)
                    log.info("History successfully reconstructed from GitHub chunks.")
                except Exception as e:
                    log.error(f"History reconstruction failed: {e}. Proceeding with fresh start risk...")

            with Step('Market Scrapers (Parallel)', '🛸'):
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
                    ('ShotejBazar', 'ShotejTRACKER')
                ]
                results = [None] * len(scrapers)
                log.info(f"Launching {len(scrapers)} scrapers in parallel (timeout={SCRAPER_TIMEOUT//60}m each)")

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

                log.info(f"SCRAPER RESULTS: {_ok_count}/{len(results)} OK")
                for r in results:
                    _label, _ok, _lines, _status = r
                    _emoji = _status_emoji.get(_status, "?")
                    log.info(f'{_emoji} {_label} - {_lines} lines [{_status}]')

                log.info("Pushing all scraper data to GitHub...")
                try:
                    subprocess.run('git add .', shell=True)
                    _now = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')
                    subprocess.run(f'git commit -m "parallel scrapers {_now} ({_ok_count}/{len(results)} OK)"', shell=True)
                    subprocess.run('git pull origin master --rebase -X ours', shell=True, capture_output=True)
                    subprocess.run('git push origin HEAD:master --force', shell=True, capture_output=True)
                    log.info("Combined scraper data pushed to GitHub successfully")
                except Exception as push_err:
                    log.warning(f"Failed to push scraper data: {push_err}")

            with Step('GODdata Aggregator', '🧬'):
                # Sync Foodi DB from sub-repo if present
                _foodi_sub = '/kaggle/working/FooDIE-mart-Analytics/data/scraper.db' if platform.system() != 'Windows' else r'C:\PROJECTS\Foodie\FooDIE-mart-Analytics\data\scraper.db'
                if os.path.exists(_foodi_sub):
                    try:
                        os.makedirs('FooDIEscraper/data', exist_ok=True)
                        shutil.copy2(_foodi_sub, 'FooDIEscraper/data/scraper.db')
                        log.info('Synced FooDIE scraper.db from FooDIE-mart-Analytics')
                    except Exception as _fe:
                        log.warning(f'Failed to sync FooDIE db: {_fe}')

                _agg_env = os.environ.copy()
                _agg_proc = subprocess.Popen([sys.executable, 'aggregator.py'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=_agg_env)
                for _agg_line in _agg_proc.stdout:
                    log.info(f'[aggregator] {_agg_line.rstrip()}')
                _agg_proc.wait()
                if _agg_proc.returncode != 0:
                    log.error(f'Aggregator failed with code {_agg_proc.returncode}')
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
                    _pq_files = sorted(glob.glob('history_*.parquet')) + ['products.parquet', 'history.parquet', 'products_free.parquet', 'history_free.parquet', 'atl.parquet', 'premium/history_archive.parquet.enc']
                    for pf in _pq_files:
                        if os.path.exists(pf):
                            sz_mb = os.path.getsize(pf) / (1024*1024)
                            log.info(f'  {pf}: {sz_mb:.1f} MB')
                except subprocess.CalledProcessError as e:
                    log.error(f'Parquet conversion failed with code {e.returncode}')

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
                            else:
                                log.error(f'Key rotation failed: {res.stderr[:500]}')
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
                    for pat in ['*_data_part*.js']:
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

            with Step('GitHub Push Guard', '🛡️'):
                _guard_script = os.path.join(os.getcwd(), 'guardrail.py')
                if not os.path.exists(_guard_script):
                    _guard_code = """import os, sys, subprocess
MAX_FILE_SIZE_MB = 98
VITAL_FILES = ['aggregator.py', 'reconstruct_history.py', 'script.js', 'index.html', 'style.css']
def check_lfs():
    for f in VITAL_FILES:
        if os.path.exists(f):
            with open(f, 'rb') as fh:
                if b'version https://git-lfs.github.com' in fh.read(100):
                    print(f"❌ FATAL: {f} is an LFS pointer!")
                    return False
    return True
def check_sizes():
    try:
        files = subprocess.check_output(['git', 'ls-files'], text=True).splitlines()
        files += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], text=True).splitlines()
    except Exception:
        files = [os.path.join(r, f) for r, d, fs in os.walk('.') if '.git' not in r for f in fs]
    large = []
    for fp in set(files):
        if not os.path.exists(fp) or fp.endswith('.db') or os.path.isdir(fp): continue
        sz = os.path.getsize(fp) / (1024 * 1024)
        if sz > MAX_FILE_SIZE_MB:
            large.append((fp, sz))
    if large:
        for fp, sz in large:
            print(f"❌ FATAL: {fp} is {sz:.2f}MB (> {MAX_FILE_SIZE_MB}MB)")
        return False
    return True
if __name__ == '__main__':
    if not check_lfs() or not check_sizes():
        sys.exit(1)
    print("✅ GUARD: All systems compliant.")
"""
                    with open(_guard_script, 'w', encoding='utf-8') as gf:
                        gf.write(_guard_code)

                res_guard = subprocess.run([sys.executable, _guard_script], capture_output=True, text=True)
                if res_guard.returncode != 0:
                    guard_err = (res_guard.stderr or "").strip()
                    guard_out = (res_guard.stdout or "").strip()
                    log.warning(f"Guardrail script returned {res_guard.returncode}:\nSTDOUT: {guard_out}\nSTDERR: {guard_err}")
                    # Run inline validation to ensure hard compliance
                    MAX_MB = 98
                    for vf in ['aggregator.py', 'reconstruct_history.py', 'script.js', 'index.html', 'style.css']:
                        if os.path.exists(vf):
                            with open(vf, 'rb') as vfh:
                                if b'version https://git-lfs.github.com' in vfh.read(100):
                                    raise RuntimeError(f"LFS pointer detected in vital file {vf}!")
                    try:
                        f_list = subprocess.check_output(['git', 'ls-files'], text=True).splitlines()
                        f_list += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], text=True).splitlines()
                    except Exception:
                        f_list = [os.path.join(r, f) for r, d, fs in os.walk('.') if '.git' not in r for f in fs]
                    for fp in set(f_list):
                        if not os.path.exists(fp) or fp.endswith('.db') or os.path.isdir(fp): continue
                        sz_mb = os.path.getsize(fp) / (1024 * 1024)
                        if sz_mb > MAX_MB:
                            raise RuntimeError(f"File {fp} ({sz_mb:.2f}MB) exceeds GitHub 100MB limit!")
                    log.info("🛡️ Inline guardrail verification passed.")
                else:
                    log.info(f"🛡️ {(res_guard.stdout or '').strip()}")
                
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
                
                # Clean up any nested sub-repo directories that might have been cloned in the wrong folder
                try:
                    for _item in os.listdir('.'):
                        if os.path.isdir(_item) and _item != '.git':
                            if os.path.exists(os.path.join(_item, '.git')):
                                log.warning(f"Removing stray nested git repository from GroceryGOD: {_item}")
                                shutil.rmtree(_item, ignore_errors=True)
                except Exception as _ce:
                    log.warning(f"Nested repo cleanup notice: {_ce}")

                subprocess.run('git add .', shell=True)
                now = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')
                subprocess.run(f'git commit -m "attempt #{cycle_count} if this works ill get some sleep frfr: {now}"', shell=True)
                
                push_success = False
                auth_push_urls = [
                    f"https://ranehal:{github_pat}@github.com/ranehal/GroceryGOD.git",
                    f"https://{github_pat}@github.com/ranehal/GroceryGOD.git"
                ]
                for _auth_u in auth_push_urls:
                    subprocess.run('git remote remove origin', shell=True, capture_output=True)
                    subprocess.run(f'git remote add origin {_auth_u}', shell=True, capture_output=True)
                    subprocess.run(f'git remote set-url origin {_auth_u}', shell=True, capture_output=True)
                    for attempt in range(2):
                        log.info(f"Push attempt {attempt+1}...")
                        subprocess.run('git pull origin master --rebase -X ours', shell=True, capture_output=True)
                        push_res = subprocess.run('git push origin HEAD:master --force', shell=True, capture_output=True, text=True)
                        if push_res.returncode == 0:
                            push_success = True
                            break
                        # Fallback: push directly to auth URL
                        push_res = subprocess.run(f'git push {_auth_u} HEAD:master --force', shell=True, capture_output=True, text=True)
                        if push_res.returncode == 0:
                            push_success = True
                            break
                        log.warning(f"Push attempt {attempt+1} failed. Error: {push_res.stderr[:200]}")
                        time.sleep(3)
                    if push_success: break
                
                if not push_success:
                    git_status = subprocess.run('git status', shell=True, capture_output=True, text=True).stdout
                    error_msg = f"Git push failed after 3 attempts!\nGit Status:\n{git_status[:300]}\nStderr: {push_res.stderr[:300]}"
                    log.error(error_msg)
                    raise RuntimeError(error_msg)

                _agg_s = _read_aggregator_summary()
                if _agg_s:
                    if len(_agg_s) > 3900:
                        _chunks = _agg_s.split("\n\n")
                        _curr = ""
                        for _c in _chunks:
                            if len(_curr) + len(_c) + 2 > 3900:
                                tg_send(_curr.strip())
                                _curr = _c + "\n\n"
                            else:
                                _curr += _c + "\n\n"
                        if _curr.strip():
                            tg_send(_curr.strip())
                    else:
                        tg_send(_agg_s)

            # Collect & send detailed cycle report
            try:
                _report = []
                _report.append("=== GroceryGOD CYCLE REPORT (Cycle {}) ===".format(cycle_count))
                _report.append("Date: {}".format(datetime.now(DHAKA_TZ).strftime("%Y-%m-%d %H:%M:%S DHAKA")))
                try: _report.append("Kaggle IP: {}".format(requests.get('https://api.ipify.org', timeout=5).text))
                except: _report.append("Kaggle IP: unknown")
                _report.append("")

                # Scraper diagnostics from last_run_log.txt
                _scraper_dirs = [("Shwapno", "swapnoTRACKER"), ("Chaldal", "PRICETRACKER"), ("Meena Bazar", "MEENAtracker"),
                                 ("Othoba", "othobaTRACKER"), ("Unimart", "unimartTRACKER"),
                                 ("Metro Mart", "metroTRACKER"), ("ShotejBazar", "ShotejTRACKER")]
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
            except Exception as _re:
                log.warning(f"Failed to send detailed cycle report: {_re}")


    except Exception as e:
        safe_tb = html.escape(traceback.format_exc()[-500:])
        err_msg = f"💥 <b>GroceryGOD CRITICAL FAILURE!</b>\nError: {html.escape(str(e))}\n<pre>{safe_tb}</pre>"
        print(err_msg)
        tg_send(err_msg)
    
    log.info("✅ GroceryGOD Sequence Finished.")

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
    print(f"🚀 [gitw] Execution Completed. Run Count: {run_count} ({now.strftime('%Y-%m-%d %H:%M:%S')})")

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

def _extract_scraper_counts(text):
    """Best-effort parse of product counts from a scraper's output."""
    counts = {}
    _t = re.search(r'\((\d+)\s*total products\)', text, re.IGNORECASE)
    if not _t:
        _t = re.search(r'Total [Scraped|Products]*:\s*(\d+)', text, re.IGNORECASE)
    if _t: counts['total'] = int(_t.group(1))
    _s = re.search(r'Scraped\s+(\d+)\s+unique products', text, re.IGNORECASE)
    if not _s:
        _s = re.search(r'Unique Products:\s*(\d+)', text, re.IGNORECASE)
    if not _s:
        _s = re.search(r'Scraped\s+(\d+)\s+products', text, re.IGNORECASE)
    if _s: counts['scraped'] = int(_s.group(1))
    return counts

def _extract_repo_price_stats(repo_dir, stdout_text=""):
    """Extract price change metrics and stock stats across sub-repo databases, JSONs, or history snapshots."""
    import glob, os, json, re
    stats = {
        'total': 0, 'in_stock': 0, 'out_of_stock': 0,
        'new_items': 0, 'price_up': 0, 'price_down': 0, 'price_same': 0,
        'back_in_stock': 0, 'went_oos': 0
    }
    if not repo_dir or not os.path.exists(repo_dir):
        return stats

    def _cmp_price(curr, prev):
        c = float(curr or 0)
        p = float(prev or 0)
        if c > 0 and p > 0:
            if c > p: return 'up'
            elif c < p: return 'down'
            else: return 'same'
        elif c <= 0 and p > 0:
            return 'went_oos'
        elif c > 0 and p <= 0:
            return 'restocked'
        return None

    def _process_hist_map(product_histories, curr_prices=None):
        stats['total'] = len(product_histories)
        for pid, h in product_histories.items():
            if isinstance(h, dict):
                dates = sorted(h.keys())
                curr_p = float(h[dates[-1]]) if dates else 0
                if curr_prices and pid in curr_prices:
                    curr_p = float(curr_prices[pid] or 0)
                if curr_p > 0: stats['in_stock'] += 1
                else: stats['out_of_stock'] += 1

                if len(dates) <= 1:
                    stats['new_items'] += 1
                else:
                    res = _cmp_price(curr_p, h[dates[-2]])
                    if res == 'up': stats['price_up'] += 1
                    elif res == 'down': stats['price_down'] += 1
                    elif res == 'same': stats['price_same'] += 1
                    elif res == 'went_oos': stats['went_oos'] += 1
                    elif res == 'restocked': stats['back_in_stock'] += 1
            elif isinstance(h, list):
                if not h: continue
                def _get_p(item):
                    if isinstance(item, dict): return float(item.get('price') or item.get('price_amount') or item.get('p') or 0)
                    try: return float(item)
                    except: return 0
                curr_p = _get_p(h[-1])
                if curr_prices and pid in curr_prices:
                    curr_p = float(curr_prices[pid] or 0)
                if curr_p > 0: stats['in_stock'] += 1
                else: stats['out_of_stock'] += 1

                if len(h) <= 1:
                    stats['new_items'] += 1
                else:
                    prev_p = _get_p(h[-2])
                    res = _cmp_price(curr_p, prev_p)
                    if res == 'up': stats['price_up'] += 1
                    elif res == 'down': stats['price_down'] += 1
                    elif res == 'same': stats['price_same'] += 1
                    elif res == 'went_oos': stats['went_oos'] += 1
                    elif res == 'restocked': stats['back_in_stock'] += 1

    # 1. SQLite DBs
    try:
        import sqlite3
        dbs = glob.glob(os.path.join(repo_dir, '**', '*.db'), recursive=True)
        for db in dbs:
            if any(x in db for x in ['.git', 'node_modules']): continue
            try:
                conn = sqlite3.connect(db)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                if 'price_history' in tables and ('products' in tables or 'dishes' in tables or 'items' in tables):
                    prod_table = 'products' if 'products' in tables else ('dishes' if 'dishes' in tables else 'items')
                    p_col = 'product_id' if 'product_id' in [col[1] for col in c.execute("PRAGMA table_info(price_history)").fetchall()] else 'dish_id'
                    cols = [col[1] for col in c.execute("PRAGMA table_info(price_history)").fetchall()]
                    price_col = 'price_amount' if 'price_amount' in cols else ('price' if 'price' in cols else cols[1])
                    time_col = 'timestamp' if 'timestamp' in cols else ('date' if 'date' in cols else cols[-1])
                    
                    rows = c.execute(f"SELECT {p_col}, {price_col}, {time_col} FROM price_history ORDER BY {time_col} ASC").fetchall()
                    by_pid = {}
                    for r in rows:
                        pid = str(r[0])
                        if pid not in by_pid: by_pid[pid] = []
                        by_pid[pid].append(float(r[1] or 0))
                    
                    if by_pid:
                        _process_hist_map(by_pid)
                        conn.close()
                        return stats
                conn.close()
            except Exception:
                pass
    except Exception:
        pass

    # 2. Check for separate history.json or price_history.json
    h_candidates = [
        os.path.join(repo_dir, 'data', 'price_history.json'),
        os.path.join(repo_dir, 'data', 'history.json')
    ]
    h_file = next((f for f in h_candidates if os.path.exists(f)), None)
    if h_file:
        try:
            with open(h_file, 'r', encoding='utf-8') as fh:
                h_data = json.load(fh)
            if isinstance(h_data, dict):
                _process_hist_map(h_data)
                return stats
        except Exception:
            pass

    # 3. Check JSON files with embedded history/price_history
    json_files = (
        glob.glob(os.path.join(repo_dir, 'frontend', '*.json')) +
        glob.glob(os.path.join(repo_dir, 'data', '*.json')) +
        glob.glob(os.path.join(repo_dir, '*.json'))
    )
    for jf in json_files:
        if any(x in jf for x in ['package', 'tsconfig', 'category', 'banner', 'init_meta', 'manifest', 'meta.json']): continue
        try:
            with open(jf, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            items = []
            if isinstance(data, dict):
                if 'products' in data and isinstance(data['products'], list):
                    items = data['products']
                else:
                    items = list(data.values()) if all(isinstance(v, dict) for v in data.values()) else []
            elif isinstance(data, list):
                items = data

            if items and isinstance(items[0], dict):
                by_pid = {}
                for it in items:
                    pid = str(it.get('id') or it.get('name') or len(by_pid))
                    h = it.get('price_history') or it.get('history')
                    curr = it.get('current_price') or it.get('price') or it.get('actual_price') or 0
                    if isinstance(h, (dict, list)):
                        by_pid[pid] = h
                    else:
                        by_pid[pid] = [curr]
                if by_pid:
                    _process_hist_map(by_pid)
                    if stats['total'] > 0:
                        return stats
        except Exception:
            pass

    # 4. Check historical snapshot diffs in history/ folder
    hist_dir = os.path.join(repo_dir, 'history')
    if not os.path.exists(hist_dir):
        hist_dir = os.path.join(repo_dir, 'frontend', 'history')
    if os.path.exists(hist_dir):
        snap_files = sorted(glob.glob(os.path.join(hist_dir, '*.json')))
        if len(snap_files) >= 1:
            try:
                with open(snap_files[-1], 'r', encoding='utf-8') as fh:
                    latest = json.load(fh)
                prev = {}
                if len(snap_files) >= 2:
                    with open(snap_files[-2], 'r', encoding='utf-8') as fh:
                        prev = json.load(fh)
                
                def _to_map(data):
                    m = {}
                    if isinstance(data, dict):
                        for k, v in data.items():
                            if isinstance(v, dict):
                                m[k] = float(v.get('current_price') or v.get('price') or 0)
                            else:
                                try: m[k] = float(v)
                                except: pass
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                pid = str(item.get('id') or item.get('name'))
                                m[pid] = float(item.get('current_price') or item.get('price') or 0)
                    return m
                
                curr_map = _to_map(latest)
                prev_map = _to_map(prev)
                stats['total'] = len(curr_map)
                for pid, cp in curr_map.items():
                    if cp > 0: stats['in_stock'] += 1
                    else: stats['out_of_stock'] += 1
                    if pid not in prev_map:
                        stats['new_items'] += 1
                    else:
                        res = _cmp_price(cp, prev_map[pid])
                        if res == 'up': stats['price_up'] += 1
                        elif res == 'down': stats['price_down'] += 1
                        elif res == 'same': stats['price_same'] += 1
                        elif res == 'went_oos': stats['went_oos'] += 1
                        elif res == 'restocked': stats['back_in_stock'] += 1
                return stats
            except Exception:
                pass

    return stats

def _send_p14_summary(results_store, repo_list):
    """Send ONE consolidated Telegram summary after all scheduled repos finish.
    Per repo: scrape time, counts, price change up/dn/same %, stock metrics, url + detailed error log if any; then aggregator summary."""
    def tg_send(text, silent=False):
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.strip() == "": return
        TG_API = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'
        try:
            requests.post(f'{TG_API}/sendMessage', json={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML', 'disable_notification': silent}, timeout=15)
        except: pass

    file_results = {}
    try:
        import glob as _glob
        for _f in _glob.glob('/tmp/p14_result_*.json'):
            try:
                with open(_f, 'r', encoding='utf-8') as fh:
                    _r = json.load(fh)
                if isinstance(_r, dict):
                    if _r.get('label'): file_results[_r['label']] = _r
                    if _r.get('slug'): file_results[_r['slug']] = _r
                    if _r.get('repo'): file_results[_r['repo']] = _r
                    if _r.get('label'):
                        _norm = re.sub(r'[^a-z0-9]+', '', _r['label'].lower())
                        file_results[_norm] = _r
            except Exception:
                pass
    except Exception:
        pass

    lines = ["📊 <b>Scheduled Repos (p14) — Finished</b>"]
    ok = fail = 0
    for label, url in repo_list:
        clean_lbl = label.strip()
        slug = re.sub(r'[^a-z0-9]+', '_', clean_lbl.lower()).strip('_')
        norm = re.sub(r'[^a-z0-9]+', '', clean_lbl.lower())
        repo_name = url.strip('/').split('/')[-1]

        rec = (
            file_results.get(clean_lbl)
            or file_results.get(label)
            or file_results.get(slug)
            or file_results.get(norm)
            or file_results.get(repo_name)
        )
        if not rec and results_store is not None:
            try:
                rec = results_store.get(clean_lbl) or results_store.get(slug) or results_store.get(label) or {}
            except Exception:
                pass

        if not rec:
            _direct_file = f"/tmp/p14_result_{slug}.json"
            if os.path.exists(_direct_file):
                try:
                    with open(_direct_file, 'r', encoding='utf-8') as fh:
                        rec = json.load(fh)
                except Exception:
                    pass

        if not rec:
            _log_file = f"/tmp/p14_log_{slug}.log"
            _log_tail = ""
            if os.path.exists(_log_file):
                try:
                    with open(_log_file, 'r', encoding='utf-8') as lf:
                        _log_tail = lf.read().strip()[-300:]
                except Exception:
                    pass
            rec = {
                'status': 'failed',
                'elapsed': 0,
                'error': _log_tail or 'No execution log or result found',
                'url': url
            }

        if rec.get('status') == 'ok':
            ok += 1
            elapsed = int(rec.get('elapsed', 0))
            _m, _s = divmod(elapsed, 60)
            st = rec.get('price_stats') or {}
            total = st.get('total') or (rec.get('counts') or {}).get('total') or (rec.get('counts') or {}).get('scraped') or 0
            
            def _pct(v):
                return f"({(v / total * 100):.1f}%)" if total > 0 else "(0.0%)"

            header_line = f"✅ <b>{clean_lbl}</b> — {_m}m {_s}s"
            if total > 0:
                header_line += f" | {total:,} items"
            header_line += f" — {rec.get('url') or url}"
            lines.append(header_line)

            in_stock = st.get('in_stock', 0)
            oos = st.get('out_of_stock', 0)
            if in_stock > 0 or oos > 0:
                lines.append(f"   ├ 🟢 In Stock: {in_stock:,} {_pct(in_stock)} | 🔴 Out of Stock: {oos:,} {_pct(oos)}")
            
            new_cnt = st.get('new_items', 0)
            if new_cnt > 0:
                lines.append(f"   ├ 🆕 New Items: {new_cnt:,} {_pct(new_cnt)}")
            
            up_cnt = st.get('price_up', 0)
            dn_cnt = st.get('price_down', 0)
            same_cnt = st.get('price_same', 0)
            p_parts = []
            if up_cnt > 0: p_parts.append(f"🔺 {up_cnt:,} {_pct(up_cnt)} up")
            if dn_cnt > 0: p_parts.append(f"🔻 {dn_cnt:,} {_pct(dn_cnt)} down")
            if same_cnt > 0: p_parts.append(f"⏸️ {same_cnt:,} {_pct(same_cnt)} same")
            if p_parts:
                lines.append(f"   ├ 🏷️ Prices: " + " | ".join(p_parts))
            
            restocked = st.get('back_in_stock', 0)
            went_oos = st.get('went_oos', 0)
            s_parts = []
            if restocked > 0: s_parts.append(f"🟢 {restocked:,} {_pct(restocked)} restocked")
            if went_oos > 0: s_parts.append(f"🔴 {went_oos:,} {_pct(went_oos)} went OOS")
            if s_parts:
                lines.append(f"   ├ 🔄 Stock Movements: " + " | ".join(s_parts))
        else:
            fail += 1
            elapsed = int(rec.get('elapsed', 0))
            _m, _s = divmod(elapsed, 60)
            lines.append(f"❌ {clean_lbl} — FAILED after {_m}m {_s}s")
            err = rec.get('error') or 'Process exited with error'
            lines.append(f"<pre>{html.escape(str(err)[:800])}</pre>")
            tb = rec.get('error_tb')
            if tb and tb.strip():
                lines.append(f"<pre>{html.escape(tb)[:600]}</pre>")

    lines.insert(1, f"✅ OK: {ok} | ❌ Failed: {fail} | Total: {len(repo_list)}")

    agg_summary = _read_aggregator_summary()
    if not agg_summary:
        print("⏳ Aggregator not finished yet — waiting up to 20 min for its summary...")
        for _ in range(60):
            time.sleep(20)
            agg_summary = _read_aggregator_summary()
            if agg_summary:
                break
    if agg_summary:
        lines.append("")
        lines.append(agg_summary)
    else:
        lines.append("")
        lines.append("📊 <b>Aggregator Summary</b>\n(aggregator summary not available yet)")

    full_message = "\n".join(lines)
    try:
        with open("/tmp/p14_summary.log", "w", encoding="utf-8") as _pf:
            _pf.write(full_message)
        print("Scheduled repos summary logged locally to /tmp/p14_summary.log")
    except Exception as _log_err:
        print(f"Warning: Failed to log p14 summary locally: {_log_err}")

def _read_aggregator_summary():
    """Read the aggregator.py summary from its shared output file (empty string if absent)."""
    try:
        _p = '/tmp/aggregator_summary.txt'
        if os.path.exists(_p):
            with open(_p, 'r', encoding='utf-8', errors='replace') as f:
                return f.read().strip()
    except Exception:
        pass
    return ""

def run_scheduled_repo(repo_url, script_name, label, github_pat, results_store=None):
    clean_label = label.strip()
    slug = re.sub(r'[^a-z0-9]+', '_', clean_label.lower()).strip('_')
    repo_name = repo_url.split('/')[-1].replace('.git', '')
    repo_page_url = f"https://ranehal.github.io/{repo_name}/"
    log_file = f"/tmp/p14_log_{slug}.log"
    _p14_file = f"/tmp/p14_result_{slug}.json"
    _t0 = time.time()

    def _log(msg):
        ts = datetime.now(DHAKA_TZ).strftime('%H:%M:%S')
        line = f"[{ts} | {clean_label}] {msg}"
        print(line)
        try:
            with open(log_file, "a", encoding="utf-8") as lf:
                lf.write(line + "\n")
        except Exception:
            pass

    _log("Process Started.")

    _p14_record = {
        'label': clean_label,
        'slug': slug,
        'repo': repo_name,
        'status': 'running',
        'elapsed': 0,
        'error': '',
        'error_tb': '',
        'url': repo_page_url,
        'counts': {}
    }

    def _store_result():
        _p14_record['label'] = clean_label
        _p14_record['slug'] = slug
        _p14_record['repo'] = repo_name
        try:
            _tmp = _p14_file + f".{os.getpid()}.tmp"
            with open(_tmp, 'w', encoding='utf-8') as _f:
                json.dump(_p14_record, _f)
            os.replace(_tmp, _p14_file)
        except Exception as _fe:
            _log(f"Warning: Failed to write result file {_p14_file}: {_fe}")
        if results_store is not None:
            try:
                results_store[clean_label] = _p14_record
                results_store[slug] = _p14_record
            except Exception:
                pass

    _p14_record.update(status='failed', error='Process started but died prematurely', elapsed=0)
    _store_result()

    if not github_pat or github_pat.strip() == "":
        err_pat = f"GITHUB_PAT is missing or empty for {clean_label}. Git push will fail."
        _log(f"❌ {err_pat}")
        _p14_record.update(status='failed', error=err_pat, elapsed=0)
        _store_result()
        return

    repo_dir = os.path.join('/kaggle/working', repo_name)
    os.makedirs('/kaggle/working', exist_ok=True)
    os.chdir('/kaggle/working')
    auth_repo_url = f"https://ranehal:{github_pat}@github.com/ranehal/{repo_name}.git"

    try:
        def _setup_git_config():
            _git_config('git config user.email "ranehal@users.noreply.github.com"')
            _git_config('git config user.name "ranehal"')
            cred_path = os.path.expanduser('~/.git-credentials')
            with open(cred_path, 'w') as f:
                f.write(f"https://ranehal:{github_pat}@github.com\nhttps://{github_pat}@github.com\n")
            _git_config('git config --global credential.helper store')
        _with_lock('git-config', _setup_git_config)

        if not os.path.exists(repo_dir):
            _reclaim_disk()
            _log(f"Cloning {repo_name} into {repo_dir}...")
            clone_res = subprocess.run(f'git clone {auth_repo_url} {repo_dir}', shell=True, capture_output=True, text=True)
            if clone_res.returncode != 0:
                raise RuntimeError(f"Git clone failed: {clone_res.stderr}")

        os.chdir(repo_dir)
        _with_lock('git-config', lambda: (_git_config('git config user.email "ranehal@users.noreply.github.com"'), _git_config('git config user.name "ranehal"')))
        subprocess.run('git remote remove origin', shell=True, capture_output=True)
        subprocess.run(f'git remote add origin {auth_repo_url}', shell=True, capture_output=True)
        subprocess.run(f'git remote set-url origin {auth_repo_url}', shell=True, capture_output=True)

        subprocess.run('git clean -fd', shell=True)
        subprocess.run('git fetch --all', shell=True)
        branch_res = subprocess.run('git symbolic-ref refs/remotes/origin/HEAD', shell=True, capture_output=True, text=True)
        default_branch = branch_res.stdout.strip().split('/')[-1] if branch_res.returncode == 0 else ''
        if not default_branch or default_branch == 'HEAD':
            check_main = subprocess.run('git rev-parse --verify origin/main', shell=True, capture_output=True)
            default_branch = 'main' if check_main.returncode == 0 else 'master'
        subprocess.run(f'git reset --hard origin/{default_branch}', shell=True)

        if os.path.exists('requirements.txt'):
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=False)

        # Low-disk preflight: /kaggle/working disk-full (Errno 28) silently breaks
        # Chromium installs and DB writes, causing random asyncio/playwright crashes.
        try:
            import glob as _glob
            _du = shutil.disk_usage(os.getcwd())
            _free_gb = _du.free / (1024 ** 3)
            if _free_gb < 2.0:
                _log(f"WARNING: low disk space ({_free_gb:.2f} GB free). Clearing __pycache__ + stale run artifacts...")
                for _p in _glob.glob(os.path.join(os.getcwd(), "**", "__pycache__"), recursive=True):
                    shutil.rmtree(_p, ignore_errors=True)
                for _pat in ("**/*.pyc", "**/_scraper_error_*.log", "**/last_run_log.txt"):
                    for _p in _glob.glob(os.path.join(os.getcwd(), _pat), recursive=True):
                        try: os.remove(_p)
                        except Exception: pass
                _du2 = shutil.disk_usage(os.getcwd())
                _log(f"After cleanup: {_du2.free / (1024 ** 3):.2f} GB free.")
        except Exception as _du_err:
            _log(f"Disk check warning: {_du_err}")

        # Auto-install essential scraping dependencies if missing
        _deps_to_check = ['playwright', 'httpx', 'requests', 'bs4', 'lxml']
        for _dep in _deps_to_check:
            try:
                __import__(_dep)
            except ImportError:
                _pkg = 'beautifulsoup4' if _dep == 'bs4' else _dep
                _log(f"Auto-installing missing dependency: {_pkg}...")
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", _pkg], check=False)
        
        # Verify Playwright Chromium browser binary without blocking apt locks unless actually missing
        try:
            import platform as _platform
            def _pw_install():
                _dry = subprocess.run([sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"], capture_output=True, text=True)
                _dry_out = ((_dry.stdout or "") + (_dry.stderr or ""))
                if "already installed" in _dry_out.lower() or os.path.isdir('/root/.cache/ms-playwright'):
                    return
                _install_cmds = [[sys.executable, "-m", "playwright", "install", "chromium"]]
                if _platform.system() == "Linux":
                    _install_cmds.insert(0, [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"])
                for _cmd in _install_cmds:
                    _res = subprocess.run(_cmd, capture_output=True, text=True)
                    if _res.returncode == 0:
                        break
            _with_lock('playwright-install', _pw_install)
        except Exception as _pw_err:
            _log(f"Playwright setup warning: {_pw_err}")

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
                    _log(f"❌ {err_msg}")
                    _p14_record.update(status='failed', error=err_msg, elapsed=int(time.time() - _t0))
                    _store_result()
                    return
            _log(f"Target script auto-resolved to: {script_name}")

        # Auto-patch Cat NoneType error safety with indentation preservation
        if os.path.exists(script_name):
            try:
                import re as _re
                with open(script_name, 'r', encoding='utf-8') as sf:
                    s_code = sf.read()
                if 'for prod in cat.get("products", []):' in s_code and 'isinstance(cat, dict)' not in s_code:
                    _log(f"Auto-patching cat dict-type safety in {script_name}...")
                    pattern = r'([ \t]*)for prod in cat\.get\("products", \[\]\):'
                    m = _re.search(pattern, s_code)
                    if m:
                        indent = m.group(1)
                        replacement = f'{indent}if not cat or not isinstance(cat, dict): continue\n{indent}for prod in cat.get("products", []):'
                        s_code = _re.sub(pattern, replacement, s_code, count=1)
                        with open(script_name, 'w', encoding='utf-8') as sf:
                            sf.write(s_code)
            except Exception as patch_err:
                _log(f"Script patch warning: {patch_err}")

        script_abs_path = os.path.abspath(script_name)
        script_dir = os.path.dirname(script_abs_path)
        script_file = os.path.basename(script_abs_path)

        max_script_retries = 3
        res = None
        for _attempt in range(1, max_script_retries + 1):
            _log(f"Executing {script_file} in {script_dir} (attempt {_attempt}/{max_script_retries})...")
            t_exec0 = time.time()
            my_env = os.environ.copy()
            my_env["PYTHONPATH"] = f"{script_dir}{os.pathsep}{os.getcwd()}{os.pathsep}{my_env.get('PYTHONPATH', '')}"
            my_env["PYTHONUNBUFFERED"] = "1"
            my_env["PYTHONIOENCODING"] = "utf-8"
            res = subprocess.run([sys.executable, "-u", script_file], cwd=script_dir, capture_output=True, text=True, timeout=3600, env=my_env)
            exec_elapsed = time.time() - t_exec0
            if res.returncode == 0:
                break
            _err_log = os.path.join(os.getcwd(), f"_scraper_error_{_attempt}.log")
            try:
                with open(_err_log, "w", encoding="utf-8") as _ef:
                    _ef.write((res.stderr or "") + "\n--- STDOUT TAIL ---\n" + (res.stdout or "")[-2000:])
            except Exception:
                pass
            safe_err = (res.stderr or "").strip()[:5000]
            if not safe_err:
                safe_err = (res.stdout or "").strip()[-5000:]
            if _attempt == max_script_retries:
                raise RuntimeError(f"Script {script_name} failed (rc={res.returncode}):\n{safe_err}")
            _log(f"Attempt {_attempt} failed (rc={res.returncode}), retrying in 10s... {safe_err[:200]}")
            time.sleep(10)

        _log(f"Finished execution in {int(time.time() - _t0)}s. Pushing to GitHub as ranehal...")
        _with_lock('git-config', lambda: (_git_config('git config user.name "ranehal"'), _git_config('git config user.email "ranehal@users.noreply.github.com"')))
        subprocess.run(f"git remote set-url origin https://ranehal:{github_pat}@github.com/ranehal/{repo_name}.git", shell=True)
        subprocess.run('find . -name "_scraper_error_*.log" -delete', shell=True)
        subprocess.run('git add .', shell=True)
        now_str = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')
        subprocess.run(f'git commit -m "if this works ill get some sleep frfr {now_str}"', shell=True)

        push_success = False
        auth_user_urls = [
            f"https://ranehal:{github_pat}@github.com/ranehal/{repo_name}.git",
            f"https://{github_pat}@github.com/ranehal/{repo_name}.git"
        ]
        for auth_u in auth_user_urls:
            user_n = "ranehal"
            subprocess.run('git remote remove origin', shell=True, capture_output=True)
            subprocess.run(f'git remote add origin {auth_u}', shell=True, capture_output=True)
            subprocess.run(f'git remote set-url origin {auth_u}', shell=True, capture_output=True)
            _with_lock('git-config', lambda: (_git_config(f'git config user.name "{user_n}"'), _git_config(f'git config user.email "{user_n}@users.noreply.github.com"')))
            for attempt in range(2):
                subprocess.run(f'git pull origin {default_branch} --rebase -X ours -q', shell=True, capture_output=True)
                push_res = subprocess.run(f'git push origin HEAD:{default_branch} --force', shell=True, capture_output=True, text=True)
                if push_res.returncode == 0:
                    push_success = True
                    break
                # Direct URL push fallback
                push_res = subprocess.run(f'git push {auth_u} HEAD:{default_branch} --force', shell=True, capture_output=True, text=True)
                if push_res.returncode == 0:
                    push_success = True
                    break
                time.sleep(3)
            if push_success: break

        if not push_success:
            raise RuntimeError(f"Git push failed: {push_res.stderr[:300]}")

        _p14_record.update(status='ok', elapsed=int(time.time() - _t0), error='', url=repo_page_url)
        _p14_record['price_stats'] = _extract_repo_price_stats(os.getcwd(), (res.stdout or "") + (res.stderr or "") if res else "")
        if res is not None:
            _p14_record['counts'] = _extract_scraper_counts((res.stdout or "") + (res.stderr or ""))
        _store_result()
        _log(f"✅ Successfully completed and pushed in {int(time.time() - _t0)}s!")
    except Exception as e:
        safe_tb = html.escape(traceback.format_exc()[-500:])
        err_str = str(e)
        _log(f"❌ Error: {err_str}")
        _p14_record.update(status='failed', error=err_str, error_tb=safe_tb, elapsed=int(time.time() - _t0), url=repo_page_url)
        _store_result()

def run_all_scheduled_repos(repos, github_pat, results_store=None):
    """Execute scheduled sub-repos with controlled concurrency (2 workers) to prevent Kaggle OOM / fork crashes."""
    print(f"🚀 [Scheduled Repos] Launching sub-repos executor (max 2 parallel workers across {len(repos)} repos)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(run_scheduled_repo, repo_url, script_name, label, github_pat, results_store): label
            for repo_url, script_name, label in repos
        }
        for future in concurrent.futures.as_completed(futures):
            lbl = futures[future]
            try:
                future.result()
                print(f"✅ [Scheduled Repos] Finished: {lbl}")
            except Exception as exc:
                print(f"❌ [Scheduled Repos] Exception in {lbl}: {exc}")
    print("🟢 [Scheduled Repos] All scheduled sub-repos completed.")

# MASTER ORCHESTRATOR LOOP
# ============================================================
if __name__ == '__main__':
    run_preflight_checks()
    
    print("🚀 Launching BOTH pipelines in Parallel...")
    
    _manager = multiprocessing.Manager()
    _p14_results = _manager.dict()
    try:
        import glob as _glob
        for _f in _glob.glob('/tmp/p14_result_*.json'):
            try: os.remove(_f)
            except Exception: pass
        for _f in _glob.glob('/tmp/p14_log_*.log'):
            try: os.remove(_f)
            except Exception: pass
    except Exception:
        pass

    _scheduled_repos = [
        ('https://github.com/ranehal/FooDIE-RESTaurant-Analytics.git', 'scrape_menus.py', 'FooDIE Restaurant Analytics'),
        ('https://github.com/ranehal/FoodPANDA-RESTaurant-ANALytics.git', 'scrape_menus.py', 'FoodPANDA Restaurant Analytics'),
        ('https://github.com/ranehal/FooDIE-mart-Analytics.git', 'scraper.py', 'FooDIE Mart Analytics'),
        ('https://github.com/ranehal/SHWAPNO-analylics.git', 'scraper.py', 'Shwapno Analytics'),
        ('https://github.com/ranehal/Othoba-analytics.git', 'scraper.py', 'Othoba Analytics'),
        ('https://github.com/ranehal/CARTup-analytics.git', 'scraper.py', 'CARTup Analytics'),
        ('https://github.com/ranehal/CHALdal-analytics.git', 'scraper.py', 'Chaldal Analytics'),
        ('https://github.com/ranehal/COOKup-analytics.git', 'scraper.py', 'COOKup Analytics'),
        ('https://github.com/ranehal/PICAboo-analytics.git', 'scraper.py', 'PICAboo Analytics'),
        ('https://github.com/ranehal/DARAZ-analytics.git', 'scraper.py', 'DARAZ Analytics'),
        ('https://github.com/ranehal/MEEnaBAzar-analylics.git', 'scraper.py', 'Meena Bazar Analytics'),
        ('https://github.com/ranehal/sharedeal.git', 'scraper.py', 'ShareDeal Analytics'),
    ]
    _repo_pages = [f"https://ranehal.github.io/{u.split('/')[-1].replace('.git','')}/" for u, _, _ in _scheduled_repos]

    p1 = multiprocessing.Process(target=run_grocery_god, args=(GITHUB_PAT,))
    p2 = multiprocessing.Process(target=run_gitw)
    p3 = multiprocessing.Process(target=run_all_scheduled_repos, args=(_scheduled_repos, GITHUB_PAT, _p14_results))
    
    p2.start()
    print("⏳ Sleeping 10 minutes (600s) before starting p1 & p3 to sync Kaggle Netherlands/UTC time with Dhaka date...")
    for _i in range(10, 0, -1):
        print(f"⏳ [{11 - _i}/10 min] Waiting {_i * 60}s for Dhaka time sync (p2 gitw running in background)...")
        time.sleep(60)
    p1.start()
    p3.start()
    
    start_time = time.time()
    timeout_seconds = 11 * 3600  # 11 hours safety timeout (well under Kaggle 12h cell limit)
    _p14_done = False

    while time.time() - start_time < timeout_seconds:
        if not any(p.is_alive() for p in [p1, p2, p3]):
            print("\n✅ All parallel pipelines finished ahead of schedule!")
            break
        if not _p14_done and not p3.is_alive():
            _p14_done = True
            print("🟢 Scheduled repos (p3) finished. Logging consolidated summary locally...")
            _send_p14_summary(_p14_results, list(zip([lbl for _, _, lbl in _scheduled_repos], _repo_pages)))
        time.sleep(30)
    else:
        print("\n⏳ Safety time limit threshold reached (11h). Initiating nuclear teardown & Kaggle restart...")

    if not _p14_done:
        _p14_done = True
        print("🟢 Ensuring consolidated scheduled repos summary is generated before restart...")
        _send_p14_summary(_p14_results, list(zip([lbl for _, _, lbl in _scheduled_repos], _repo_pages)))

    print("☢️ Executing Nuclear Teardown of orphaned child processes...")
    os.system("pkill -9 -f chromium")
    os.system("pkill -9 -f scraper.py")
    for i in range(1, 35):
        os.system(f"pkill -9 -f {i}.py")

    for p in [p1, p2, p3]:
        if p.is_alive():
            p.terminate()
            p.join(timeout=5)
    
    time.sleep(5)
    print("\n🔄 Triggering next cycle...")
    for _n, _p in [("GroceryGOD (p1)", p1), ("gitw (p2)", p2), ("Scheduled Repos (p3)", p3)]:
        s = "OK" if _p.exitcode == 0 else f"rc={_p.exitcode}" if _p.exitcode is not None else "alive"
        print(f"[{_n}]: {s}")
    
    trigger_self_restart()

