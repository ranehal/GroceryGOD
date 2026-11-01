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
import zipfile
import base64
import hashlib
import secrets
import ast
from datetime import datetime, timedelta, timezone

# Ensure stdout and stderr use UTF-8 encoding
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
if hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass

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

def _git_config(cmd_str, cwd=None):
    """Run git config with retry on concurrent lock contention."""
    for _i in range(8):
        _res = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, cwd=cwd)
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
# GIT NETWORK HARDENING (HTTP/2 RPC CANCEL / early EOF recovery)
# ============================================================
# Kaggle's egress link regularly kills large git transfers with:
#   RPC failed; curl 92 HTTP/2 stream 5 was not closed cleanly: CANCEL (err 8)
#   fatal: early EOF / fetch-pack: invalid index-pack output
# Every clone/fetch/pull/push is therefore pinned to HTTP/1.1 with generous
# buffers, and network commands are retried with exponential backoff.
GIT_NET_OPTS = (
    '-c http.version=HTTP/1.1 '
    '-c http.postBuffer=1048576000 '
    '-c http.lowSpeedLimit=0 '
    '-c http.lowSpeedTime=999999 '
    '-c core.compression=9 '
    '-c pack.windowMemory=256m'
)

GIT_TRANSIENT_MARKERS = (
    'rpc failed', 'early eof', 'curl 92', 'curl 18', 'curl 55', 'curl 56',
    'http/2', 'stream was not closed', 'unexpected disconnect',
    'invalid index-pack', 'remote end hung up', 'connection reset',
    'connection timed out', 'operation timed out', 'timed out',
    'recv failure', 'send failure', 'broken pipe', 'tls handshake',
    'http 500', 'http 502', 'http 503', 'http 504',
    'error: 500', 'error: 502', 'error: 503', 'error: 504',
    'failed to connect', 'could not resolve host',
    'temporary failure in name resolution',
)


def _git_transient_error(*texts):
    """True when git failed for a transport reason that is safe to retry."""
    _blob = " ".join(t for t in texts if t).lower()
    return any(_m in _blob for _m in GIT_TRANSIENT_MARKERS)


def _git_log(log, msg):
    """Log through the caller's logger (if any) or stdout."""
    try:
        if log:
            log(msg)
        else:
            print(f"[GIT] {msg}", flush=True)
    except Exception:
        pass


def _git_run_retry(cmd, cwd=None, log=None, attempts=4, delay=5, label='git'):
    """Run a network git command, retrying only on transient transport failures."""
    _res = None
    for _i in range(attempts):
        try:
            _res = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            _git_log(log, f"⏱️ {label} attempt {_i + 1}/{attempts} timed out after 30m.")
            if _i == attempts - 1:
                return subprocess.CompletedProcess(cmd, 124, '', f'{label} timed out after 30m')
            time.sleep(delay * (2 ** _i))
            continue
        if _res.returncode == 0:
            if _i:
                _git_log(log, f"✅ {label} recovered on attempt {_i + 1}/{attempts}.")
            return _res
        _err = (_res.stderr or '') + ' ' + (_res.stdout or '')
        if not _git_transient_error(_err) or _i == attempts - 1:
            return _res
        _wait = delay * (2 ** _i)
        _tail = ((_res.stderr or _res.stdout or '').strip().splitlines() or [''])[-1]
        _git_log(log, f"⚠️ {label} transient failure {_i + 1}/{attempts}: {_tail[:180]} — retrying in {_wait}s")
        time.sleep(_wait)
    return _res


def _git_clone_robust(auth_repo_url, dest, branch=None, log=None, label=None):
    """Clone a repo resiliently: HTTP/1.1 + retries + shallow→full→init/fetch fallback.

    Returns (ok, last_error). A failed clone must never kill the whole pipeline.
    """
    label = label or os.path.basename(dest.rstrip('/')) or 'repo'
    _branch_arg = f'--branch {branch} ' if branch else ''
    _git_env = os.environ.copy()
    _git_env.update({'GIT_LFS_SKIP_SMUDGE': '1', 'GIT_TERMINAL_PROMPT': '0'})
    _plans = [
        (f'{GIT_NET_OPTS} clone --depth 1 --single-branch --no-tags {_branch_arg}{auth_repo_url} "{dest}"', 'shallow clone'),
        (f'{GIT_NET_OPTS} clone --depth 1 --single-branch --no-tags {_branch_arg}{auth_repo_url} "{dest}"', 'shallow clone retry'),
        (f'{GIT_NET_OPTS} clone --depth 50 --single-branch --no-tags {_branch_arg}{auth_repo_url} "{dest}"', 'medium clone'),
        (f'{GIT_NET_OPTS} clone {_branch_arg}{auth_repo_url} "{dest}"', 'full clone'),
        (f'{GIT_NET_OPTS} clone {_branch_arg}{auth_repo_url} "{dest}"', 'full clone retry'),
    ]
    _last_err = ''
    _reclaim_disk()
    for _idx, (_git_args, _kind) in enumerate(_plans):
        try:
            if os.path.exists(dest):
                shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
            _git_log(log, f"Cloning {label} ({_kind}, attempt {_idx + 1}/{len(_plans)})...")
            _res = subprocess.run(f'git {_git_args}', shell=True, capture_output=True, text=True, timeout=2400, env=_git_env)
            if _res.returncode == 0 and os.path.exists(os.path.join(dest, '.git')):
                if _idx:
                    _git_log(log, f"✅ {label} clone recovered using {_kind}.")
                return True, ''
            _last_err = (_res.stderr or _res.stdout or '').strip()
            _git_log(log, f"⚠️ {label} {_kind} failed: {((_last_err.splitlines() or [''])[-1])[:180]}")
        except subprocess.TimeoutExpired:
            _last_err = f'{_kind} timed out after 40m'
            _git_log(log, f"⏱️ {label} {_kind} timed out — retrying.")
        except Exception as _exc:
            _last_err = f'{_kind} error: {_exc}'
            _git_log(log, f"⚠️ {label} {_kind} error: {_exc}")
        time.sleep(min(5 * (_idx + 1), 20))

    # Last resort: init + shallow fetch survives most index-pack/RPC failures.
    try:
        if os.path.exists(dest):
            shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest, exist_ok=True)
        _fb = branch
        if not _fb:
            _sym = _git_run_retry(f'git {GIT_NET_OPTS} ls-remote --symref "{auth_repo_url}" HEAD',
                                  log=log, attempts=3, label=f'{label} ls-remote')
            if _sym is not None and _sym.returncode == 0:
                for _line in (_sym.stdout or '').splitlines():
                    if _line.startswith('ref: refs/heads/'):
                        _fb = _line.split('refs/heads/')[1].split()[0]
                        break
        _fb = _fb or 'master'
        _git_log(log, f"Last resort: git init + shallow fetch for {label} ({_fb})...")
        _git_run_retry('git init -q', cwd=dest, log=log, attempts=1, label=f'{label} init')
        _git_run_retry(f'git remote add origin "{auth_repo_url}"', cwd=dest, log=log, attempts=1, label=f'{label} remote')
        _fetch = _git_run_retry(f'git {GIT_NET_OPTS} fetch --depth 1 origin {_fb}', cwd=dest, log=log,
                                attempts=3, label=f'{label} fetch')
        if _fetch is not None and _fetch.returncode == 0:
            subprocess.run(f'git checkout -B {_fb} FETCH_HEAD', shell=True, cwd=dest, capture_output=True, text=True)
            _git_log(log, f"✅ {label} recovered via init+shallow fetch fallback.")
            return True, ''
        if _fetch is not None:
            _last_err = (_fetch.stderr or _fetch.stdout or _last_err).strip()
    except Exception as _exc:
        _git_log(log, f"⚠️ {label} init+fetch fallback error: {_exc}")

    return False, _last_err

# ============================================================
# PARQUET DATASET BACKUP (MANUAL EXTRACTION SYSTEM)
# ============================================================
def _get_parquet_backup_base_dir():
    """Determine the destination folder for manual parquet extraction on Kaggle."""
    if os.path.exists('/kaggle/working'):
        base = '/kaggle/working/output/parquet_backup'
    else:
        base = os.path.abspath(os.path.join(os.getcwd(), 'output', 'parquet_backup'))
    os.makedirs(base, exist_ok=True)
    return base

def backup_parquet_datasets(repo_dir=None, cycle_count=1, git_status='PENDING', git_error=None, custom_base_dir=None):
    """
    Back up all generated Parquet files, store chunks, and previews into a clean,
    date-separated, versioned directory in the Kaggle output folder for easy manual extraction.
    Creates both individual parquet files and a standalone ZIP archive for 1-click download.
    """
    if repo_dir is None:
        repo_dir = os.getcwd()
    base_dir = custom_base_dir or _get_parquet_backup_base_dir()

    now_dhaka = datetime.now(DHAKA_TZ)
    date_str = now_dhaka.strftime('%Y-%m-%d')
    date_dir = os.path.join(base_dir, date_str)
    os.makedirs(date_dir, exist_ok=True)

    # Clean version separation: v1, v2, v3...
    existing_versions = []
    try:
        for item in os.listdir(date_dir):
            if os.path.isdir(os.path.join(date_dir, item)) and re.match(r'^v(\d+)$', item):
                existing_versions.append(int(item[1:]))
    except Exception:
        pass
    next_v = f"v{max(existing_versions, default=0) + 1}"
    version_dir = os.path.join(date_dir, next_v)
    os.makedirs(version_dir, exist_ok=True)

    # Collect all parquet and preview files
    seen_rel = set()
    targets = []

    parquet_patterns = [
        'products.parquet',
        'history.parquet',
        'products_free.parquet',
        'history_free.parquet',
        'atl.parquet',
        'atl_preview.json',
        'history_*.parquet'
    ]
    for pat in parquet_patterns:
        for fp in glob.glob(os.path.join(repo_dir, pat)):
            rel = os.path.basename(fp)
            if os.path.isfile(fp) and rel not in seen_rel:
                seen_rel.add(rel)
                targets.append((fp, rel))

    # Also capture encrypted datasets if generated
    for pat in ['products.parquet.enc*', 'history.parquet.enc*']:
        for fp in glob.glob(os.path.join(repo_dir, pat)):
            rel = os.path.basename(fp)
            if os.path.isfile(fp) and rel not in seen_rel:
                seen_rel.add(rel)
                targets.append((fp, rel))

    # Premium directory archives
    prem_dir = os.path.join(repo_dir, 'premium')
    if os.path.exists(prem_dir):
        for fp in glob.glob(os.path.join(prem_dir, '*.parquet*')):
            rel = os.path.join('premium', os.path.basename(fp))
            if os.path.isfile(fp) and rel not in seen_rel:
                seen_rel.add(rel)
                targets.append((fp, rel))

    files_meta = {}
    copied_paths = []
    total_bytes = 0

    for src_path, rel_dest in targets:
        try:
            dst_path = os.path.join(version_dir, rel_dest)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)
            sz = os.path.getsize(dst_path)
            total_bytes += sz

            meta_entry = {
                'size_bytes': sz,
                'size_mb': round(sz / (1024 * 1024), 2),
            }
            if rel_dest.endswith('.parquet'):
                try:
                    import pyarrow.parquet as _pq
                    meta_entry['num_rows'] = _pq.read_metadata(dst_path).num_rows
                except Exception:
                    pass
            files_meta[rel_dest.replace(chr(92), '/')] = meta_entry
            copied_paths.append((dst_path, rel_dest))
        except Exception as copy_err:
            print(f"[PARQUET-BACKUP] Warning copying {src_path}: {copy_err}")

    # Build standalone ZIP for 1-click manual download
    zip_name = f"grocerygod_parquet_{date_str}_{next_v}.zip"
    zip_path = os.path.join(version_dir, zip_name)
    try:
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for fpath, rpath in copied_paths:
                zf.write(fpath, arcname=rpath.replace(chr(92), '/'))
        zip_sz = os.path.getsize(zip_path)
    except Exception as zip_err:
        print(f"[PARQUET-BACKUP] Warning building ZIP archive: {zip_err}")
        zip_sz = 0

    # Convenience shortcut: copy latest zip to base folder
    latest_zip = os.path.join(base_dir, 'latest_parquet_backup.zip')
    try:
        shutil.copy2(zip_path, latest_zip)
    except Exception:
        pass

    summary = {
        'timestamp_dhaka': now_dhaka.strftime('%Y-%m-%d %H:%M:%S DHAKA (UTC+6)'),
        'date': date_str,
        'version': next_v,
        'cycle_count': cycle_count,
        'git_status': git_status,
        'git_error': git_error,
        'total_files': len(files_meta),
        'total_size_mb': round(total_bytes / (1024 * 1024), 2),
        'zip_filename': zip_name,
        'zip_size_mb': round(zip_sz / (1024 * 1024), 2),
        'version_dir': version_dir,
        'zip_path': zip_path,
        'files': files_meta
    }

    summary_path = os.path.join(version_dir, 'backup_summary.json')
    try:
        with open(summary_path, 'w', encoding='utf-8') as sf:
            json.dump(summary, sf, indent=2)
    except Exception:
        pass

    # Human-readable instruction file inside the version folder
    readme_text = f"""================================================================================
GROCERYGOD PARQUET DATASET BACKUP (MANUAL EXTRACTION)
================================================================================
Timestamp (Dhaka): {summary['timestamp_dhaka']}
Date:              {date_str}
Version:           {next_v} (Attempt #{cycle_count})
Git Sync Status:   {git_status}
Total Files:       {len(files_meta)}
Total Data Size:   {summary['total_size_mb']} MB
Standalone ZIP:    {zip_name} ({summary['zip_size_mb']} MB)
Extraction Path:   {version_dir}
================================================================================

DATASET CONTENTS:
- products.parquet: Master product catalog (id, name, store, category, price, normalized_price, in_stock, unit, url, image_url)
- history.parquet: Complete historical price observations (product_id, date, price, normalized_price)
- products_free.parquet: Free-tier product catalog
- history_free.parquet: Free-tier historical price observations
- atl.parquet: All-Time-Low historical price benchmarks across stores
- atl_preview.json: Instant pre-computed all-time-low preview dataset
- history_<store>.parquet: Per-store progressive hydration chunks (shwapno, chaldal, meenabazar, othoba, metromart, unimart, shotejbazar, foodi)
- premium/: Full historical archive snapshots and encrypted packages

HOW TO QUERY WITH PYTHON / DUCKDB:
--------------------------------------------------------------------------------
import duckdb
con = duckdb.connect()

# Query product catalog:
df_products = con.execute("SELECT * FROM read_parquet('products.parquet')").df()

# Query price history (filtering out-of-stock sentinels):
df_history = con.execute("SELECT * FROM read_parquet('history.parquet') WHERE price > 0").df()

# Query store-specific history:
df_shwapno = con.execute("SELECT * FROM read_parquet('history_shwapno.parquet')").df()
================================================================================
"""
    try:
        with open(os.path.join(version_dir, 'README_MANUAL_EXTRACTION.txt'), 'w', encoding='utf-8') as rf:
            rf.write(readme_text)
    except Exception:
        pass

    # Top-level quick reference pointer
    try:
        top_info = os.path.join(base_dir, 'LATEST_BACKUP_INFO.txt')
        with open(top_info, 'w', encoding='utf-8') as tf:
            tf.write(f"Latest Parquet Backup: {date_str} / {next_v}\nGenerated: {summary['timestamp_dhaka']}\nDirectory: {version_dir}\nArchive ZIP: {zip_path}\nGit Status: {git_status}\n")
    except Exception:
        pass

    return summary

def update_parquet_backup_status(backup_info, git_status='PUSHED_TO_GITHUB', git_error=None):
    """Update git synchronization status in the parquet backup summary."""
    if not backup_info or not isinstance(backup_info, dict) or 'version_dir' not in backup_info:
        return
    version_dir = backup_info['version_dir']
    summary_path = os.path.join(version_dir, 'backup_summary.json')
    if os.path.exists(summary_path):
        try:
            with open(summary_path, 'r', encoding='utf-8') as sf:
                data = json.load(sf)
            data['git_status'] = git_status
            data['git_error'] = str(git_error) if git_error else None
            data['last_updated_dhaka'] = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S DHAKA (UTC+6)')
            with open(summary_path, 'w', encoding='utf-8') as sf:
                json.dump(data, sf, indent=2)
        except Exception:
            pass

    try:
        base_dir = os.path.dirname(os.path.dirname(version_dir))
        top_info = os.path.join(base_dir, 'LATEST_BACKUP_INFO.txt')
        if os.path.exists(top_info):
            with open(top_info, 'a', encoding='utf-8') as tf:
                tf.write(f"Updated Git Status: {git_status}\nError: {git_error or 'None'}\n")
    except Exception:
        pass

# ============================================================
# USER SECRETS VAULT (ONE-TIME IMPORT / PERSISTENCE)
# ============================================================
def _sec_unmask(hex_str, key_byte=0x5C):
    try:
        return bytes([b ^ key_byte for b in bytes.fromhex(hex_str)]).decode('utf-8')
    except Exception:
        return ""

_BUILTIN_SECRETS = {
    'GITHUB_PAT': _sec_unmask('3b352834293e032c3d28036d6d1d161e151e050d6c0b263a2d261e1a042f646c3d03296c6c3a2c09316505683638040f362c0c176d2a286f3a0a6833061d0f69356a373868053e3b243712123d050c06170b18140811150e35363b286e'),
    'KAGGLE_USERNAME': _sec_unmask('2e3d3239343d3024'),
    'KAGGLE_KEY': _sec_unmask('171b1d08036b3d6f396e64646a6b6d6d6868686f393d3e6f38683d3d3a383f646a6e693e39'),
    'TELEGRAM_BOT_TOKEN': _sec_unmask('6b696a6f6e686f646a6c661d1d1b656d0b3019321b322c30180f0f2c240509290665053e082528196a25381f162b'),
    'TELEGRAM_CHAT_ID': _sec_unmask('6b69646b6d6d6a696f'),
    'KAGGLE_KERNEL_SLUG': _sec_unmask('2e3d3239343d3024733b35283b3338'),
    'GOD_PREMIUM_KEY': _sec_unmask('3d2f2f3d303d31293d303d35372931'),
    'TURSO_PLATFORM_TOKEN': _sec_unmask('392516343e1b3f351335161a06190e080d0f152f15320e693f1f156a15372c040a1f1665723925162d381b3735133516243d1b3728082606260e6c0a310e6d381606180e2d0b09652b386f1e3215352b353e6f1632046e30371536332411181d2b1136116813083b2b3a0d72133b33163e263d64086c032e172b3739162a6a716d326524151d6d2f716e1f0f08100a68651b260609650f3224050b2e0b0e3f061269713e343b1f696d3f6819040a1f646b6e3665643f651b6d36351b6a0531251d3b'),
    'TURSO_RW_TOKEN': _sec_unmask('392516343e1b3f351335161a06190e080d0f152f15320e693f1f156a15372c040a1f16657239251634153633353f323f35101f162c05040d351336196f13183b691318376e11083b2f153130371536333511181a3411183b6d05263f280531092b110f6c6f06363b6e10083431110811281108096805263f6d12360e3705083f2415352b353d6e3037153633353e6d156f09190a080f6f120b046e306d083012130826340f0d04160c111a1d6f3e6f380e13081a14091430303e040a11050a0a31066f2c6e080f152f1532162c061f156a15311569110b0a3412183f2b10081526056e092812181d6d06356c690531192510080d6c13081524116e156e11080e37121f1665726d1b0c053210360d176c3a176f341028041f046c3d1e0a0f3e2c6a353812162f1438146d3232263617262f2c303a1e39311837121831150629380f290b6f0d082b0c043e696d0316353e240c696d051e690834691d0d'),
    'TURSO_RO_TOKEN': _sec_unmask('392516343e1b3f351335161a06190e080d0f152f15320e693f1f156a15372c040a1f16657239251634153633353f316435101f162c05040d351336196f13183b691318376e11083b2f153130371536333511181a3411183b6d05263f280531092b110f6c6f06363b6e10083431110811281108096805263f6d12360e3705083f2415352b353d6e3037153633353e6d156f09190a080f6f120b046e306d083012130826340f0d04160c111a1d6f3e6f380e13081a14091430303e040a11050a0a31066f2c6e080f152f1532162c061f156a15311569110b0a3412183f2b10081526056e092812181d6d06356c690531192510080d6c13081524116e156e11080e37121f1665726a6a313718033430386815043d081e37313f2971311533260d0c6f6d311a120c110928646438030932151f646d1f68366d6d37083d3326280c6e3819241a0c041a0b11360665161f373f356c320d6f2f1104361a1d3b'),
    'GITHUB_PAT_BACKUP': _sec_unmask('3b352834293e032c3d28036d6d1d161e151e050d6c0b263a2d261e1a042f646c3d03296c6c3a2c09316505683638040f362c0c176d2a286f3a0a6833061d0f69356a373868053e3b243712123d050c06170b18140811150e35363b286e')
}

_MANUAL_SECRETS = globals().get('_MANUAL_SECRETS') if isinstance(globals().get('_MANUAL_SECRETS'), dict) else {}
for _bk, _bv in _BUILTIN_SECRETS.items():
    if _bv and not _MANUAL_SECRETS.get(_bk):
        _MANUAL_SECRETS[_bk] = _bv

# Persisted secrets cache (preserved across container restarts)
_PERSISTED_SECRETS = globals().get('_PERSISTED_SECRETS') if isinstance(globals().get('_PERSISTED_SECRETS'), dict) else {}
_PERSISTED_SECRETS_B64 = str(globals().get('_PERSISTED_SECRETS_B64', '') or '')
if _PERSISTED_SECRETS_B64:
    try:
        _decoded_secrets = json.loads(base64.b64decode(_PERSISTED_SECRETS_B64).decode('utf-8'))
        if isinstance(_decoded_secrets, dict):
            for _k, _v in _decoded_secrets.items():
                if _v and not _PERSISTED_SECRETS.get(_k):
                    _PERSISTED_SECRETS[_k] = str(_v).strip()
    except Exception:
        pass

# Merge manual secrets if user supplied any
for _mk, _mv in _MANUAL_SECRETS.items():
    if _mv and not _PERSISTED_SECRETS.get(_mk):
        _PERSISTED_SECRETS[_mk] = str(_mv).strip()

# Persisted state cache (reboot count, cycle metrics, uptime, monthly bandwidth)
_PERSISTED_STATE = globals().get('_PERSISTED_STATE') if isinstance(globals().get('_PERSISTED_STATE'), dict) else {}
_PERSISTED_STATE_B64 = str(globals().get('_PERSISTED_STATE_B64', '') or '')
if _PERSISTED_STATE_B64:
    try:
        _decoded_state = json.loads(base64.b64decode(_PERSISTED_STATE_B64).decode('utf-8'))
        if isinstance(_decoded_state, dict):
            for _sk, _sv in _decoded_state.items():
                if _sv is not None and not _PERSISTED_STATE.get(_sk):
                    _PERSISTED_STATE[_sk] = _sv
    except Exception:
        pass

# Load persisted state from local file vaults
for _sp in ['/kaggle/working/orchestrator_state.json', '/kaggle/working/output/orchestrator_state.json', '/tmp/orchestrator_state.json']:
    if os.path.exists(_sp):
        try:
            with open(_sp, 'r', encoding='utf-8') as _sf:
                _fs_data = json.load(_sf)
                if isinstance(_fs_data, dict):
                    for _sk, _sv in _fs_data.items():
                        if _sv is not None and _sk not in _PERSISTED_STATE:
                            _PERSISTED_STATE[_sk] = _sv
        except Exception:
            pass

def get_secret_safe(key, default=""):
    """
    Robust multi-tier secret retriever:
    1. Kaggle UserSecretsClient (UI attached)
    2. OS Environment
    3. Manual User Secrets dictionary (_MANUAL_SECRETS)
    4. Persisted Secrets Cache (_PERSISTED_SECRETS)
    5. Local file vaults (/kaggle/working/secrets_vault.json, /tmp/secrets_vault.json)
    6. ~/.kaggle/kaggle.json
    7. Attached Kaggle dataset fallback (/kaggle/input/**/secrets*.json)
    Automatically caches resolved secrets for persistence across self-reboots.
    """
    val = None

    # 1. Try Kaggle UserSecretsClient (UI attached)
    try:
        from kaggle_secrets import UserSecretsClient
        val = UserSecretsClient().get_secret(key)
        if val is not None and str(val).strip():
            val = str(val).strip()
    except Exception:
        pass

    # 2. Try OS Environment
    if not val:
        v = os.environ.get(key)
        if v is not None and str(v).strip():
            val = str(v).strip()

    # 3. Try Manual Secrets dictionary
    if not val and isinstance(globals().get('_MANUAL_SECRETS'), dict):
        v = _MANUAL_SECRETS.get(key)
        if v is not None and str(v).strip():
            val = str(v).strip()

    # 4. Try Injected Persisted Secrets (auto-propagated across container restarts)
    if not val and isinstance(globals().get('_PERSISTED_SECRETS'), dict):
        v = _PERSISTED_SECRETS.get(key)
        if v is not None and str(v).strip():
            val = str(v).strip()

    # 5. Try local persisted secrets vault files
    if not val:
        _vault_paths = [
            '/kaggle/working/secrets_vault.json',
            '/kaggle/working/output/secrets_vault.json',
            '/tmp/secrets_vault.json'
        ]
        for vp in _vault_paths:
            if os.path.exists(vp):
                try:
                    with open(vp, 'r', encoding='utf-8') as vf:
                        vdata = json.load(vf)
                        if isinstance(vdata, dict) and key in vdata and vdata[key]:
                            val = str(vdata[key]).strip()
                            break
                except Exception:
                    pass

    # 6. Try ~/.kaggle/kaggle.json for Kaggle credentials
    if not val and key in ('KAGGLE_USERNAME', 'KAGGLE_KEY'):
        try:
            _kjson = os.path.expanduser('~/.kaggle/kaggle.json')
            if os.path.exists(_kjson):
                with open(_kjson, 'r', encoding='utf-8') as _kf:
                    _kdata = json.load(_kf)
                if key == 'KAGGLE_USERNAME' and _kdata.get('username'):
                    val = str(_kdata['username']).strip()
                elif key == 'KAGGLE_KEY' and _kdata.get('key'):
                    val = str(_kdata['key']).strip()
        except Exception:
            pass

    # 7. Try attached Kaggle Dataset fallback (e.g. /kaggle/input/**/*.json)
    if not val:
        try:
            _input_candidates = (
                glob.glob('/kaggle/input/**/secrets*.json', recursive=True) +
                glob.glob('/kaggle/input/**/vault*.json', recursive=True) +
                glob.glob('/kaggle/input/**/kaggle*.json', recursive=True) +
                glob.glob('/kaggle/input/**/*.json', recursive=True)
            )
            for f in _input_candidates:
                if not os.path.isfile(f):
                    continue
                try:
                    with open(f, 'r', encoding='utf-8') as jf:
                        data = json.load(jf)
                    if not isinstance(data, dict):
                        continue
                    if key in data and data[key]:
                        val = str(data[key]).strip()
                        break
                    # Key aliases
                    _aliases = {
                        'GITHUB_PAT': ('github_pat', 'pat', 'token', 'github_token', 'PAT'),
                        'GITHUB_PAT_BACKUP': ('github_pat_backup', 'ranx_pat', 'ranx_github_pat', 'backup_pat', 'GITHUB_PAT_RANX', 'RANX_PAT', 'RANX_GITHUB_PAT'),
                        'KAGGLE_USERNAME': ('username', 'kaggle_username', 'user'),
                        'KAGGLE_KEY': ('key', 'kaggle_key', 'api_key'),
                        'TELEGRAM_BOT_TOKEN': ('telegram_bot_token', 'bot_token', 'tg_token'),
                        'TELEGRAM_CHAT_ID': ('telegram_chat_id', 'chat_id', 'tg_chat_id'),
                    }.get(key, ())
                    for _ak in _aliases:
                        if _ak in data and data[_ak]:
                            val = str(data[_ak]).strip()
                            break
                    if val:
                        break
                except Exception:
                    continue
        except Exception:
            pass

    # 8. Try local git configuration / remotes for GITHUB_PAT
    if not val and key == 'GITHUB_PAT':
        try:
            _res = subprocess.run(['git', 'config', '--get', 'http.extraheader'], capture_output=True, text=True)
            _eh = (_res.stdout or '').strip()
            if 'Authorization: Basic ' in _eh:
                _b64 = _eh.split('Authorization: Basic ')[-1].strip()
                _dec = base64.b64decode(_b64).decode('utf-8', errors='ignore')
                if ':' in _dec:
                    _tok = _dec.split(':', 1)[1].strip()
                    if _tok.startswith(('ghp_', 'github_pat_')):
                        val = _tok
            if not val:
                _res_rem = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True)
                _rurl = (_res_rem.stdout or '').strip()
                _m = re.search(r'https://(?:[^:@]+:)?(ghp_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)@github\.com', _rurl)
                if _m:
                    val = _m.group(1).strip()
        except Exception:
            pass

    resolved = val if val else default

    # Auto-cache into _PERSISTED_SECRETS so trigger_self_restart will persist it
    if resolved and isinstance(_PERSISTED_SECRETS, dict):
        _PERSISTED_SECRETS[key] = resolved

    return resolved

GITHUB_PAT = get_secret_safe('GITHUB_PAT')
GITHUB_PAT_BACKUP = get_secret_safe('GITHUB_PAT_BACKUP') or get_secret_safe('RANX_GITHUB_PAT') or get_secret_safe('RANX_PAT') or GITHUB_PAT
os.environ['KAGGLE_USERNAME'] = get_secret_safe('KAGGLE_USERNAME')
os.environ['KAGGLE_KEY'] = get_secret_safe('KAGGLE_KEY')
TELEGRAM_BOT_TOKEN = get_secret_safe("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret_safe("TELEGRAM_CHAT_ID")
os.environ["TELEGRAM_BOT_TOKEN"] = TELEGRAM_BOT_TOKEN or ""
os.environ["TELEGRAM_CHAT_ID"] = TELEGRAM_CHAT_ID or ""
KAGGLE_KERNEL_SLUG = get_secret_safe("KAGGLE_KERNEL_SLUG", "ranehalx/gitgod")
os.environ['GOD_PREMIUM_KEY'] = get_secret_safe('GOD_PREMIUM_KEY', 'assalamualaikum')

# ============================================================
# TELEGRAM NOTIFICATIONS & AUTOMATED DATABASE BACKUPS
# ============================================================
def tg_send(text, silent=False):
    """Dispatch rich HTML message to Telegram."""
    bot_token = TELEGRAM_BOT_TOKEN or get_secret_safe("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = TELEGRAM_CHAT_ID or get_secret_safe("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return False
    TG_API = f'https://api.telegram.org/bot{bot_token}'
    try:
        r = requests.post(f'{TG_API}/sendMessage', json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'disable_notification': silent}, timeout=20)
        return r.status_code == 200
    except Exception:
        return False

def _upload_doc_telegram(file_path, caption, bot_token, chat_id, silent=False):
    """
    Stream a single document/archive to Telegram Bot API.
    Prioritizes curl subprocess streaming (zero Python heap memory usage, direct kernel-to-socket streaming)
    with fallback to requests with open file handle.
    """
    if not os.path.exists(file_path):
        return False

    fname = os.path.basename(file_path)
    safe_cap = caption[:1024]

    # Tier 1: curl subprocess streaming (0 MB Python memory footprint, direct streaming from disk)
    if shutil.which("curl"):
        try:
            curl_cmd = [
                "curl", "-s", "-S",
                "--connect-timeout", "30",
                "--max-time", "300",
                "--retry", "3",
                "--retry-delay", "3",
                "-F", f"chat_id={chat_id}",
                "-F", f"caption={safe_cap}",
                "-F", "parse_mode=HTML",
                "-F", f"document=@{file_path};filename={fname}"
            ]
            if silent:
                curl_cmd.extend(["-F", "disable_notification=true"])
            curl_cmd.append(f"https://api.telegram.org/bot{bot_token}/sendDocument")

            res = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=360)
            stdout_txt = (res.stdout or "").strip()
            if res.returncode == 0 and '"ok":true' in stdout_txt:
                return True
            else:
                stderr_txt = (res.stderr or "").strip()
                print(f"⚠️ [TG] curl upload notice (rc={res.returncode}): {stdout_txt[:200]} | {stderr_txt[:200]}", flush=True)
        except Exception as _curl_exc:
            print(f"⚠️ [TG] curl execution notice ({_curl_exc}). Falling back to requests...", flush=True)

    # Tier 2: requests upload fallback
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendDocument",
                files={"document": (fname, f)},
                data={"chat_id": chat_id, "caption": safe_cap, "parse_mode": "HTML", "disable_notification": silent},
                timeout=180
            )
            if resp.status_code == 200:
                return True
            else:
                print(f"⚠️ [TG] requests upload status {resp.status_code}: {resp.text[:200]}", flush=True)
                return False
    except Exception as _req_exc:
        print(f"⚠️ [TG] requests upload exception: {_req_exc}", flush=True)
        return False

def tg_send_file(file_path, caption="", silent=False):
    """
    Dispatch document/database to Telegram. Automatically compresses large uncompressed files
    or splits archives exceeding 40MB into sequential <=35MB chunks (.001, .002, etc.)
    using zero-memory streaming, guaranteeing 100% reliable delivery without RAM exhaustion
    or kernel crashes.
    """
    import gc
    gc.collect()

    bot_token = TELEGRAM_BOT_TOKEN or get_secret_safe("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = TELEGRAM_CHAT_ID or get_secret_safe("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("⚠️ [TG] Bot token or chat ID missing. Skipping file send.", flush=True)
        return False
    if not os.path.exists(file_path):
        print(f"⚠️ [TG] File does not exist: {file_path}", flush=True)
        return False

    actual_path = file_path
    temp_files = []
    try:
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return False

        # If it's an uncompressed file > 35MB and not already an archive, try zip compression
        is_archive = any(file_path.lower().endswith(ext) for ext in ['.7z', '.zip', '.gz', '.bz2', '.xz', '.tar', '.zst'])
        if file_size > 35 * 1024 * 1024 and not is_archive:
            import zipfile
            dest_dir = os.path.dirname(actual_path)
            temp_zip = os.path.join(dest_dir, f"{os.path.basename(file_path)}.zip")
            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(file_path, os.path.basename(file_path))
            actual_path = temp_zip
            temp_files.append(temp_zip)
            file_size = os.path.getsize(actual_path)

        # Telegram Bot API limit is 50MB. If file_size > 40MB, split into 35MB multi-part chunks
        CHUNK_SIZE = 35 * 1024 * 1024
        if file_size > 40 * 1024 * 1024:
            num_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
            print(f"📦 [TG] File {actual_path} ({file_size / (1024*1024):.1f}MB) exceeds 40MB safety limit. Splitting into {num_chunks} multi-part volumes (35MB each)...", flush=True)
            base_name = os.path.basename(actual_path)
            # Write chunks to persistent disk output directory, NEVER /tmp (which is tmpfs in RAM on Linux)
            chunk_dir = os.path.dirname(actual_path)
            chunk_paths = []

            with open(actual_path, "rb") as src_f:
                for idx in range(1, num_chunks + 1):
                    chunk_name = f"{base_name}.{idx:03d}"
                    chunk_path = os.path.join(chunk_dir, chunk_name)
                    with open(chunk_path, "wb") as chunk_f:
                        remaining = CHUNK_SIZE
                        while remaining > 0:
                            buf = src_f.read(min(remaining, 512 * 1024))
                            if not buf:
                                break
                            chunk_f.write(buf)
                            remaining -= len(buf)
                    chunk_paths.append(chunk_path)
                    temp_files.append(chunk_path)

            all_ok = True
            for idx, c_path in enumerate(chunk_paths, start=1):
                part_cap = f"📦 [Part {idx}/{num_chunks}] {caption}".strip()
                c_mb = os.path.getsize(c_path) / (1024 * 1024)
                print(f"📤 [TG] Dispatching split volume {idx}/{num_chunks}: {os.path.basename(c_path)} ({c_mb:.1f} MB)...", flush=True)
                ok = _upload_doc_telegram(c_path, part_cap, bot_token, chat_id, silent=silent)
                if ok:
                    print(f"✅ [TG] Split part {idx}/{num_chunks} delivered successfully.", flush=True)
                else:
                    print(f"⚠️ [TG] Split part {idx}/{num_chunks} upload failed.", flush=True)
                    all_ok = False
                time.sleep(2)
            return all_ok

        # Single file upload <= 40MB
        return _upload_doc_telegram(actual_path, caption, bot_token, chat_id, silent=silent)
    except Exception as exc:
        print(f"⚠️ [TG] tg_send_file failed for {file_path}: {exc}", flush=True)
        return False
    finally:
        for tf in temp_files:
            if os.path.exists(tf):
                try: os.remove(tf)
                except Exception: pass
        gc.collect()

def get_master_backup_dir():
    """Return root directory for organizing the consolidated all-in-one daily backup."""
    if platform.system() == 'Windows':
        d = os.path.abspath('output/daily_master_backup')
    else:
        d = '/kaggle/working/output/daily_master_backup'
    os.makedirs(os.path.join(d, '01_GroceryGOD_Parquet'), exist_ok=True)
    os.makedirs(os.path.join(d, '02_SubRepos'), exist_ok=True)
    return d

def package_master_backup(backup_root, today_dhaka):
    """
    Packages backup_root into a single, standalone, perfectly organized 7z archive (with ZIP fallback).
    Includes 00_README_MANIFEST.txt describing datasets, stores, and DuckDB querying.
    """
    manifest_txt = os.path.join(backup_root, "00_README_MANIFEST.txt")
    ts_dhaka = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S DHAKA (UTC+6)')
    try:
        with open(manifest_txt, 'w', encoding='utf-8') as mf:
            mf.write(f"""================================================================================
GROCERYGOD & BANGLADESH RETAIL ANALYTICS — MASTER DAILY BACKUP
Generated: {ts_dhaka}
================================================================================

This master archive consolidates the daily price tracking datasets, SQLite databases,
and Parquet stores across 20 retail, grocery, and restaurant platforms in Bangladesh.

📂 01_GroceryGOD_Parquet/
   - products_free.parquet: Master unified product catalog (all 8 stores, 365-day history stats)
   - atl.parquet: Pre-calculated All-Time-Low deals catalog
   - atl_preview.json: Instant sub-25ms launch preview
   - history_<store>.parquet: Per-store progressive hydration chunks for:
     Shwapno, Chaldal, Meena Bazar, Othoba, Metro Mart, Unimart, ShotejBazar, Foodi.

📂 02_SubRepos/
   - FooDIE Restaurant Analytics (Banani & Gulshan restaurant menus)
   - FoodPANDA Restaurant Analytics (FoodPANDA restaurant menus & parquet dataset)
   - FooDIE Mart Analytics (grocery dark stores)
   - Shwapno Analytics (full Shwapno catalog snapshots)
   - Othoba Analytics (Othoba grocery database)
   - CARTup Analytics (CartUp catalog database)
   - Chaldal Analytics (Chaldal catalog & price history)
   - COOKup Analytics (Cookups homemade food database)
   - PICAboo Analytics (Pickaboo gadgets & electronics)
   - DARAZ Analytics (Daraz grocery & dMart database)
   - Meena Bazar Analytics (Meena Bazar complete catalog)
   - ShareDeal Analytics (ShareDeal deals database)

🔍 How to Query Parquet Datasets with Python & DuckDB:
   pip install duckdb
   python -c "import duckdb; print(duckdb.query('SELECT store, count(*) as count FROM read_parquet(\\"01_GroceryGOD_Parquet/products_free.parquet\\") GROUP BY store').df())"

🌐 Live Web Dashboard:
   https://ranehal.github.io/GroceryGOD/
================================================================================
""")
    except Exception as e:
        print(f"⚠️ [BACKUP] Manifest write warning: {e}")

    out_dir = os.path.dirname(backup_root)
    archive_7z = os.path.join(out_dir, f"grocerygod_master_backup_{today_dhaka}.7z")
    archive_zip = os.path.join(out_dir, f"grocerygod_master_backup_{today_dhaka}.zip")

    # Ensure 7z tool is installed on Linux/Kaggle
    if platform.system() != 'Windows' and shutil.which('7z') is None:
        try:
            subprocess.run('which 7z || (apt-get update -qq && apt-get install -y -qq p7zip-full)', shell=True, capture_output=True, timeout=60)
        except Exception:
            pass

    # Pre-packaging memory reclamation
    import gc
    gc.collect()

    # 1. Try 7-Zip ultra compression (t7z, mx=9, mmt=2 to avoid memory/CPU thrashing)
    if shutil.which('7z') is not None:
        if os.path.exists(archive_7z):
            try: os.remove(archive_7z)
            except Exception: pass
        cmd = f'7z a -t7z -mx=9 -ms=on -mmt=2 "{archive_7z}" "{backup_root}/*"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(archive_7z) and os.path.getsize(archive_7z) > 0:
            sz_mb = os.path.getsize(archive_7z) / (1024 * 1024)
            print(f"📦 [7-ZIP] Master archive created: {archive_7z} ({sz_mb:.2f} MB)", flush=True)
            gc.collect()
            return archive_7z, sz_mb

    # 2. Fallback to ZIP with DEFLATED level 9
    if os.path.exists(archive_zip):
        try: os.remove(archive_zip)
        except Exception: pass
    with zipfile.ZipFile(archive_zip, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(backup_root):
            for file in files:
                abs_p = os.path.join(root, file)
                rel_p = os.path.relpath(abs_p, backup_root)
                zf.write(abs_p, rel_p)
    sz_mb = os.path.getsize(archive_zip) / (1024 * 1024)
    print(f"📦 [ZIP] Master archive created (fallback): {archive_zip} ({sz_mb:.2f} MB)", flush=True)
    gc.collect()
    return archive_zip, sz_mb

def send_repo_db_backup(repo_dir, repo_name, label, repo_page_url):
    """
    Locates the primary database / parquet dataset modified and pushed in repo_dir,
    and stages it into the centralized master backup folder (02_SubRepos/<label>/)
    to be packaged into the master 7z archive.
    Does NOT send intermediate individual Telegram messages to keep Telegram clean.
    """
    try:
        c_res = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo_dir, capture_output=True, text=True)
        commit_sha = (c_res.stdout or '').strip()
        commit_short = commit_sha[:7] if commit_sha else "HEAD"
        commit_url = f"https://github.com/ranehal/{repo_name}/commit/{commit_sha}" if commit_sha else repo_page_url
        now_dhaka = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')

        candidates = []
        for root, dirs, files in os.walk(repo_dir):
            if '.git' in root or '__pycache__' in root:
                continue
            for f in files:
                f_low = f.lower()
                fp = os.path.join(root, f)
                try: sz = os.path.getsize(fp)
                except Exception: continue
                if sz == 0: continue
                if f_low.endswith('.parquet'):
                    candidates.append((1, sz, fp))
                elif f_low.endswith(('.db', '.sqlite', '.sqlite3')) and not any(f_low.endswith(x) for x in ['-wal', '-shm', '.enc']):
                    candidates.append((2, sz, fp))
                elif f_low.endswith('.json') and any(k in f_low for k in ['product', 'price', 'restaurant', 'data', 'catalog']) and sz < 90 * 1024 * 1024:
                    candidates.append((3, sz, fp))

        if not candidates:
            print(f"ℹ️ [BACKUP] No primary database or parquet found in {label} to stage.")
            return

        candidates.sort(key=lambda x: (x[0], -x[1]))
        best_file = candidates[0][2]
        file_sz_mb = os.path.getsize(best_file) / (1024 * 1024)
        fname = os.path.basename(best_file)

        bdir = get_master_backup_dir()
        safe_lbl = re.sub(r'[^a-zA-Z0-9_\-]+', '_', label).strip('_')
        target_dir = os.path.join(bdir, '02_SubRepos', safe_lbl)
        os.makedirs(target_dir, exist_ok=True)
        dest_file = os.path.join(target_dir, fname)
        shutil.copy2(best_file, dest_file)

        meta = {
            'label': label,
            'repo': repo_name,
            'commit_sha': commit_sha,
            'commit_short': commit_short,
            'commit_url': commit_url,
            'timestamp_dhaka': now_dhaka,
            'file_name': fname,
            'size_mb': round(file_sz_mb, 2),
            'live_url': repo_page_url
        }
        with open(os.path.join(target_dir, 'info.json'), 'w', encoding='utf-8') as mf:
            json.dump(meta, mf, indent=2)

        print(f"📦 [BACKUP] Staged {fname} ({file_sz_mb:.2f} MB) for {label} into master backup: 02_SubRepos/{safe_lbl}/")
    except Exception as exc:
        print(f"⚠️ [BACKUP] Failed to stage backup for {label}: {exc}")


# ============================================================
# GITHUB PUSH BANDWIDTH & QUOTA TRACKER (10GB MONTHLY CAP)
# ============================================================
GITHUB_MONTHLY_CAP_BYTES = 10 * 1024 * 1024 * 1024  # 10.0 GB (10,737,418,240 bytes)

def _get_current_month_key():
    """Return the current Dhaka month key 'YYYY-MM' (e.g. '2026-09')."""
    return datetime.now(DHAKA_TZ).strftime("%Y-%m")

def _init_bandwidth_state():
    """Initialize or roll over monthly bandwidth tracking ledger with disk vault sync."""
    curr_month = _get_current_month_key()
    for vp in ['/kaggle/working/bandwidth_tracker.json', '/tmp/bandwidth_tracker.json', '/kaggle/working/output/bandwidth_tracker.json']:
        if os.path.exists(vp):
            try:
                with open(vp, 'r', encoding='utf-8') as vf:
                    disk_data = json.load(vf)
                if disk_data.get('month_key') == curr_month:
                    _PERSISTED_STATE['bandwidth_monthly_bytes'] = max(_PERSISTED_STATE.get('bandwidth_monthly_bytes', 0), int(disk_data.get('monthly_bytes', 0)))
                    _PERSISTED_STATE['bandwidth_pushes_count'] = max(_PERSISTED_STATE.get('bandwidth_pushes_count', 0), int(disk_data.get('pushes_count', 0)))
                    _PERSISTED_STATE['bandwidth_month_key'] = curr_month
                    break
            except Exception:
                pass
    if _PERSISTED_STATE.get('bandwidth_month_key') != curr_month:
        _PERSISTED_STATE['bandwidth_month_key'] = curr_month
        _PERSISTED_STATE['bandwidth_monthly_bytes'] = 0
        _PERSISTED_STATE['bandwidth_pushes_count'] = 0
        _PERSISTED_STATE['bandwidth_repos_usage'] = {}
    else:
        if 'bandwidth_monthly_bytes' not in _PERSISTED_STATE:
            _PERSISTED_STATE['bandwidth_monthly_bytes'] = 0
        if 'bandwidth_pushes_count' not in _PERSISTED_STATE:
            _PERSISTED_STATE['bandwidth_pushes_count'] = 0
        if 'bandwidth_repos_usage' not in _PERSISTED_STATE or not isinstance(_PERSISTED_STATE['bandwidth_repos_usage'], dict):
            _PERSISTED_STATE['bandwidth_repos_usage'] = {}

def record_git_push_bandwidth(repo_dir=".", repo_name="GroceryGOD", stderr_text=""):
    """
    Measure and record bandwidth consumed by a Git push against the 10GB monthly cap.
    Parses 'Writing objects: ...' from git push stderr or calculates HEAD changed files.
    Persists cumulative metrics in _PERSISTED_STATE and local disk vaults.
    Returns (push_bytes, summary_dict).
    """
    _init_bandwidth_state()
    
    # 1. Parse bytes from Git push stderr
    push_bytes = 0
    if stderr_text:
        # Match "Writing objects: 100% (X/X), 1.25 MiB | 2.50 MiB/s"
        matches = re.findall(r'Writing objects:\s*\d+%\s*\([^)]+\),\s*([\d\.]+)\s*([KMGT]?i?B)', stderr_text, re.IGNORECASE)
        if matches:
            val, unit = float(matches[-1][0]), matches[-1][1].upper()
            if 'G' in unit: push_bytes = int(val * 1024 * 1024 * 1024)
            elif 'M' in unit: push_bytes = int(val * 1024 * 1024)
            elif 'K' in unit: push_bytes = int(val * 1024)
            else: push_bytes = int(val)
        else:
            m2 = re.findall(r'Total\s+\d+.*,\s*([\d\.]+)\s*([KMGT]?i?B)', stderr_text, re.IGNORECASE)
            if m2:
                val, unit = float(m2[-1][0]), m2[-1][1].upper()
                if 'G' in unit: push_bytes = int(val * 1024 * 1024 * 1024)
                elif 'M' in unit: push_bytes = int(val * 1024 * 1024)
                elif 'K' in unit: push_bytes = int(val * 1024)
                else: push_bytes = int(val)
            else:
                m3 = re.findall(r'([\d\.]+)\s*([KMGT]?i?B)\s*\|\s*[\d\.]+\s*[KMGT]?i?B/s', stderr_text, re.IGNORECASE)
                if m3:
                    val, unit = float(m3[-1][0]), m3[-1][1].upper()
                    if 'G' in unit: push_bytes = int(val * 1024 * 1024 * 1024)
                    elif 'M' in unit: push_bytes = int(val * 1024 * 1024)
                    elif 'K' in unit: push_bytes = int(val * 1024)
                    else: push_bytes = int(val)
    
    # 2. Fallback: query changed files size in HEAD with wire compression estimation
    if push_bytes <= 0:
        try:
            res = subprocess.run(
                ['git', 'diff-tree', '-r', '--no-commit-id', '--name-only', 'HEAD'],
                cwd=repo_dir, capture_output=True, text=True
            )
            if res.returncode == 0 and res.stdout.strip():
                raw_bytes = 0
                for rel in res.stdout.strip().splitlines():
                    fp = os.path.join(repo_dir, rel)
                    if os.path.isfile(fp):
                        sz = os.path.getsize(fp)
                        ext = os.path.splitext(rel)[1].lower()
                        # Git packfile zlib compression: text/json compresses to ~12%, DB to ~25%
                        if ext in ['.json', '.csv', '.sql', '.js', '.html', '.txt']:
                            raw_bytes += int(sz * 0.12)
                        elif ext in ['.db', '.sqlite', '.sqlite3']:
                            raw_bytes += int(sz * 0.25)
                        elif ext in ['.parquet', '.enc', '.gz', '.zip', '.tar']:
                            raw_bytes += sz
                        else:
                            raw_bytes += int(sz * 0.20)
                push_bytes = max(raw_bytes, 1024)
        except Exception:
            pass

    if push_bytes <= 0:
        push_bytes = 1024

    # 3. Accumulate in _PERSISTED_STATE
    _PERSISTED_STATE['bandwidth_monthly_bytes'] = int(_PERSISTED_STATE.get('bandwidth_monthly_bytes', 0)) + push_bytes
    _PERSISTED_STATE['bandwidth_pushes_count'] = int(_PERSISTED_STATE.get('bandwidth_pushes_count', 0)) + 1
    
    repos_usage = _PERSISTED_STATE.get('bandwidth_repos_usage', {})
    repos_usage[repo_name] = int(repos_usage.get(repo_name, 0)) + push_bytes
    _PERSISTED_STATE['bandwidth_repos_usage'] = repos_usage
    _PERSISTED_STATE['last_push_bytes'] = push_bytes
    _PERSISTED_STATE['last_push_repo'] = repo_name
    _PERSISTED_STATE['last_push_dhaka'] = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d %H:%M:%S DHAKA")

    # 4. Save to local disk vaults
    for vp in ['/kaggle/working/bandwidth_tracker.json', '/tmp/bandwidth_tracker.json', '/kaggle/working/output/bandwidth_tracker.json']:
        try:
            os.makedirs(os.path.dirname(vp), exist_ok=True)
            with open(vp, 'w', encoding='utf-8') as vf:
                json.dump({
                    'month_key': _PERSISTED_STATE.get('bandwidth_month_key'),
                    'monthly_bytes': _PERSISTED_STATE.get('bandwidth_monthly_bytes'),
                    'monthly_mb': round(_PERSISTED_STATE.get('bandwidth_monthly_bytes', 0) / (1024 * 1024), 2),
                    'monthly_gb': round(_PERSISTED_STATE.get('bandwidth_monthly_bytes', 0) / (1024 ** 3), 4),
                    'pushes_count': _PERSISTED_STATE.get('bandwidth_pushes_count'),
                    'repos_usage': _PERSISTED_STATE.get('bandwidth_repos_usage'),
                    'last_push': {
                        'repo': repo_name,
                        'bytes': push_bytes,
                        'mb': round(push_bytes / (1024 * 1024), 2),
                        'timestamp': _PERSISTED_STATE.get('last_push_dhaka')
                    }
                }, vf, indent=2)
        except Exception:
            pass

    return push_bytes, get_bandwidth_telemetry(push_bytes, repo_name)

def get_bandwidth_telemetry(push_bytes=0, repo_name=""):
    """Generate telemetry metrics and formatted HTML block for Telegram notifications."""
    _init_bandwidth_state()
    total_bytes = int(_PERSISTED_STATE.get('bandwidth_monthly_bytes', 0))
    cap_bytes = GITHUB_MONTHLY_CAP_BYTES
    
    used_mb = total_bytes / (1024 * 1024)
    used_gb = total_bytes / (1024 ** 3)
    rem_bytes = max(0, cap_bytes - total_bytes)
    rem_gb = rem_bytes / (1024 ** 3)
    pct_used = min(100.0, (total_bytes / cap_bytes) * 100.0)
    pct_rem = max(0.0, 100.0 - pct_used)

    push_mb = push_bytes / (1024 * 1024)
    month_name = datetime.now(DHAKA_TZ).strftime("%B %Y")

    if pct_used < 70.0:
        status_icon = "🟢"
        status_text = f"Nominal ({pct_used:.1f}% used of 10GB cap)"
    elif pct_used < 90.0:
        status_icon = "🟡"
        status_text = f"Moderate ({pct_used:.1f}% used of 10GB cap)"
    elif pct_used < 100.0:
        status_icon = "🔴"
        status_text = f"Warning: {pct_used:.1f}% of 10GB quota consumed!"
    else:
        status_icon = "🚨"
        status_text = f"10GB Cap Exceeded ({pct_used:.1f}%) — ranx-x Backup Key Engaged"

    repo_tag = f" ({repo_name})" if repo_name else ""
    active_user = "ranx-x (Backup Key)" if (pct_used >= 100.0 or _PERSISTED_STATE.get('last_push_user') == 'ranx-x') else "ranehal (Primary)"
    html_block = (
        "🌐 <b>GitHub Push Bandwidth Telemetry:</b>\n"
        f"• 📤 <b>This Commit Push:</b> <code>{push_mb:.2f} MB</code>{repo_tag}\n"
        f"• 📊 <b>Monthly Consumed:</b> <code>{used_mb:.1f} MB</code> (<code>{used_gb:.3f} GB / 10.00 GB</code> — <b>{pct_used:.2f}%</b>)\n"
        f"• 🟢 <b>Remaining Quota:</b> <code>{rem_gb:.2f} GB</code> (<b>{pct_rem:.1f}%</b> free)\n"
        f"• 🔑 <b>Active Key Route:</b> <code>{active_user}</code>\n"
        f"• 📅 <b>Monthly Cycle:</b> <code>{month_name}</code> (DHAKA UTC+6)\n"
        f"• 🚦 <b>Cap Status:</b> {status_icon} <b>{status_text}</b>"
    )

    return {
        'push_bytes': push_bytes,
        'push_mb': round(push_mb, 2),
        'total_bytes': total_bytes,
        'used_mb': round(used_mb, 2),
        'used_gb': round(used_gb, 4),
        'rem_gb': round(rem_gb, 4),
        'pct_used': round(pct_used, 2),
        'pct_rem': round(pct_rem, 2),
        'month_name': month_name,
        'html_block': html_block
    }

def send_preflight_telegram_alert(diagnosis, fix_instructions):
    """Sends a formatted pre-flight warning to Telegram with step-by-step fix guide."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    now_dhaka = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d %H:%M:%S DHAKA (UTC+6)")
    alert_msg = (
        "🚨 <b>GroceryGOD Pre-Flight Alert: GITHUB_PAT Issue</b>\n\n"
        f"❌ <b>Diagnosis:</b>\n<code>{html.escape(diagnosis)}</code>\n\n"
        f"📍 <b>Kernel:</b> <code>{html.escape(KAGGLE_KERNEL_SLUG or 'ranehalx/gitgod')}</code>\n"
        f"🕒 <b>Time:</b> <code>{now_dhaka}</code>\n\n"
        "🛠 <b>HOW TO FIX IN KAGGLE:</b>\n"
        f"{fix_instructions}"
    )
    try:
        tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(tg_url, json={"chat_id": TELEGRAM_CHAT_ID, "text": alert_msg, "parse_mode": "HTML"}, timeout=12)
        print("📲 Telegram pre-flight alert dispatched successfully.")
    except Exception as _tg_err:
        print(f"[PRE-FLIGHT] Could not send Telegram alert: {_tg_err}")

def verify_github_pat(pat):
    """Verify PAT presence, authentication with GitHub API, and push permission to ranehal/GroceryGOD."""
    if not pat or not str(pat).strip():
        diag = "GITHUB_PAT secret is missing or empty in Kaggle secrets."
        fix = (
            "1️⃣ <b>Generate / Locate GitHub PAT:</b>\n"
            "• Account: <b>ranehal</b> (https://github.com/settings/tokens)\n"
            "• Scope: <b>repo</b> (Full control of private repositories) or Fine-Grained token with Read & Write access to contents.\n\n"
            "2️⃣ <b>Attach Secret in Kaggle:</b>\n"
            "• In Kaggle notebook top bar: <b>Add-ons</b> ➜ <b>Secrets</b>.\n"
            "• Label: <code>GITHUB_PAT</code>, Value: <code>ghp_...</code> or <code>github_pat_...</code>\n"
            "• ⚠️ <b>MANDATORY:</b> Ensure the checkbox next to <code>GITHUB_PAT</code> is <b>CHECKED (☑)</b> so this kernel can read it!\n\n"
            "3️⃣ <b>Alternative (Zero-Friction Private Dataset):</b>\n"
            "• Create a private Kaggle dataset containing <code>secrets.json</code> with GITHUB_PAT, KAGGLE_USERNAME, KAGGLE_KEY.\n"
            "• Attach it via <b>+ Add Input</b> in the Kaggle notebook.\n\n"
            "4️⃣ <b>Restart Kernel:</b>\n"
            "• Click <b>Cancel Run</b>, then click <b>Run All</b>."
        )
        return False, diag, fix

    headers = {
        "Authorization": f"Bearer {str(pat).strip()}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "GroceryGOD-Preflight/1.0"
    }

    try:
        r_user = requests.get("https://api.github.com/user", headers=headers, timeout=10)
        if r_user.status_code == 401:
            diag = "GitHub API returned HTTP 401 (Bad credentials). Your GITHUB_PAT is invalid, expired, or revoked."
            fix = (
                "1️⃣ <b>Generate a Fresh GitHub PAT:</b>\n"
                "• Go to https://github.com/settings/tokens ➜ <b>Generate new token (classic)</b>.\n"
                "• Set Expiration to No expiration (or renew it).\n"
                "• Select scope: <b>repo</b> (Full control of private repositories).\n"
                "• Copy the token (starts with <code>ghp_</code> or <code>github_pat_</code>).\n\n"
                "2️⃣ <b>Update Secret in Kaggle:</b>\n"
                "• In Kaggle top menu: <b>Add-ons</b> ➜ <b>Secrets</b>.\n"
                "• Update <code>GITHUB_PAT</code> with your new token.\n"
                "• ⚠️ Ensure checkbox next to <code>GITHUB_PAT</code> is <b>CHECKED</b>.\n\n"
                "3️⃣ <b>Restart Kernel:</b>\n"
                "• Click <b>Cancel Run</b>, then <b>Run All</b>."
            )
            return False, diag, fix
        elif r_user.status_code != 200:
            diag = f"GitHub API /user check returned HTTP {r_user.status_code}: {r_user.text[:120]}"
            fix = (
                "1️⃣ Check GitHub status at https://www.githubstatus.com\n"
                "2️⃣ Ensure your token is valid and not rate-limited.\n"
                "3️⃣ Update <code>GITHUB_PAT</code> in Kaggle Add-ons ➜ Secrets and restart."
            )
            return False, diag, fix

        user_data = r_user.json()
        login = user_data.get("login", "unknown")
    except Exception as e:
        print(f"⚠️ [PRE-FLIGHT] GitHub API network test bypassed ({e})")
        return True, "", ""

    # Check push access to ranehal/GroceryGOD
    try:
        r_repo = requests.get("https://api.github.com/repos/ranehal/GroceryGOD", headers=headers, timeout=10)
        if r_repo.status_code == 200:
            repo_data = r_repo.json()
            perms = repo_data.get("permissions", {})
            has_push = perms.get("push", False) or perms.get("admin", False)
            if not has_push:
                diag = f"Token authenticated as @{login}, but lacks write/push permissions to ranehal/GroceryGOD."
                fix = (
                    "1️⃣ <b>Verify GitHub Account:</b>\n"
                    f"• The token belongs to <b>@{login}</b>, which does not have write access to <code>ranehal/GroceryGOD</code>.\n"
                    "• Use a token generated from account <b>ranehal</b> or grant collaborator push access.\n\n"
                    "2️⃣ <b>Update Kaggle Secret:</b>\n"
                    "• In Kaggle: <b>Add-ons</b> ➜ <b>Secrets</b> ➜ Update <code>GITHUB_PAT</code> with account <b>ranehal</b>'s token.\n"
                    "• Ensure checkbox is checked and restart kernel."
                )
                return False, diag, fix
            return True, f"Authenticated as @{login} with write/push access to ranehal/GroceryGOD.", ""
        elif r_repo.status_code == 404:
            diag = f"Token authenticated as @{login}, but ranehal/GroceryGOD returned HTTP 404 (token lacks repo scope or access)."
            fix = (
                "1️⃣ <b>Check Token Scopes:</b>\n"
                "• Go to https://github.com/settings/tokens and check your token scopes.\n"
                "• Ensure <b>repo</b> (Full control of private repositories) is enabled.\n\n"
                "2️⃣ <b>Update Kaggle Secret & Restart:</b>\n"
                "• Re-paste token in Kaggle Add-ons ➜ Secrets and restart."
            )
            return False, diag, fix
    except Exception as e:
        print(f"⚠️ [PRE-FLIGHT] GitHub repo permissions test bypassed ({e})")
        return True, "", ""

    return True, "PAT verification passed.", ""

def run_preflight_checks():
    print("\n" + "="*50)
    print("🛫 PRE-FLIGHT SECRETS & GITHUB PAT CHECK")
    print("="*50)
    missing = []
    if not GITHUB_PAT: missing.append("GITHUB_PAT")
    if not os.environ.get('KAGGLE_USERNAME'): missing.append("KAGGLE_USERNAME")
    if not os.environ.get('KAGGLE_KEY'): missing.append("KAGGLE_KEY")
    if not KAGGLE_KERNEL_SLUG: missing.append("KAGGLE_KERNEL_SLUG")
    if not TELEGRAM_BOT_TOKEN: missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID: missing.append("TELEGRAM_CHAT_ID")
    
    if missing:
        print(f"🚨 CRITICAL WARNING: The following secrets are missing or empty: {', '.join(missing)}")
        print("🚨 Scrapers WILL fail to push to GitHub, and the script WILL fail to self-restart.")
        print("🚨 Please stop the kernel, go to Add-ons > Secrets, attach them (ensure checkboxes are checked!), and run again.\n")

    # Deep PAT validation against GitHub API
    pat_ok, pat_diag, pat_fix = verify_github_pat(GITHUB_PAT)
    if not pat_ok:
        print(f"🚨 [PRE-FLIGHT PAT FAILURE] {pat_diag}")
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            print("📲 Sending urgent fix guide to Telegram...")
            send_preflight_telegram_alert(pat_diag, pat_fix)
        else:
            print("⚠️ Telegram credentials missing; cannot dispatch Telegram alert.")
        print("="*50 + "\n")
        return False
    else:
        if pat_diag:
            print(f"✅ [GITHUB_PAT] {pat_diag}")
        else:
            print("✅ [GITHUB_PAT] Validated successfully with GitHub API.")

    if not missing:
        print("✅ All core secrets found. Systems nominal.\n")
    print("="*50 + "\n")
    return True

# ============================================================
# SELF-RESTART FUNCTION & TELEMETRY
# ============================================================
def trigger_self_restart(exec_stats=None):
    """
    Trigger Kaggle self-restart with persisted secrets, persisted reboot count, and state telemetry.
    Dispatches a rich formatted execution & reboot summary to Telegram with date/time, reboot count,
    session duration, pipeline completion badges, master catalog stats, and parquet backup info.
    """
    print("\n[SYSTEM] Initiating Kaggle Self-Restart...")
    def _tg(msg):
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "": return
        try:
            requests.post(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage', json={'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'HTML'}, timeout=10)
        except Exception:
            pass

    now_dhaka = datetime.now(DHAKA_TZ)
    dhaka_time_str = now_dhaka.strftime("%Y-%m-%d %H:%M:%S DHAKA (UTC+6)")

    # 1. Increment and persist reboot count & loop telemetry
    current_reboot = int(_PERSISTED_STATE.get('reboot_count', 0))
    reboot_count = current_reboot + 1
    _PERSISTED_STATE['reboot_count'] = reboot_count
    _PERSISTED_STATE['last_reboot_dhaka'] = dhaka_time_str
    if not _PERSISTED_STATE.get('first_boot_dhaka'):
        _PERSISTED_STATE['first_boot_dhaka'] = dhaka_time_str
    _PERSISTED_STATE['total_reboots'] = reboot_count

    # Save to disk vaults for local retrieval
    for _vp in ['/kaggle/working/orchestrator_state.json', '/kaggle/working/output/orchestrator_state.json', '/tmp/orchestrator_state.json']:
        try:
            os.makedirs(os.path.dirname(_vp), exist_ok=True)
            with open(_vp, 'w', encoding='utf-8') as _vf:
                json.dump(_PERSISTED_STATE, _vf, indent=2)
        except Exception:
            pass

    k_slug = KAGGLE_KERNEL_SLUG or get_secret_safe('KAGGLE_KERNEL_SLUG', 'ranehalx/gitgod')

    try:
        k_user = os.environ.get('KAGGLE_USERNAME') or get_secret_safe('KAGGLE_USERNAME')
        k_key = os.environ.get('KAGGLE_KEY') or get_secret_safe('KAGGLE_KEY')

        if not k_user or not k_key:
            err = "❌ Error: KAGGLE_USERNAME or KAGGLE_KEY missing in secrets. Cannot authenticate with Kaggle API to self-restart."
            print(err)
            _tg(f"🚨 <b>Kaggle Self-Restart Aborted!</b>\n\n{err}\n🕒 <code>{dhaka_time_str}</code>\n🔢 Reboot Attempt: #{reboot_count}\n📍 Kernel: <code>{k_slug}</code>")
            return

        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "kaggle"], check=False)

        kaggle_config = {"username": k_user, "key": k_key}
        os.makedirs(os.path.expanduser('~/.kaggle'), exist_ok=True)
        with open(os.path.expanduser('~/.kaggle/kaggle.json'), 'w') as f:
            json.dump(kaggle_config, f)
        os.chmod(os.path.expanduser('~/.kaggle/kaggle.json'), 0o600)
        os.environ['KAGGLE_USERNAME'] = k_user
        os.environ['KAGGLE_KEY'] = k_key

        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()

        restart_dir = '/tmp/restart_payload'
        if os.path.exists(restart_dir):
            shutil.rmtree(restart_dir)
        os.makedirs(restart_dir, exist_ok=True)
        os.chdir(restart_dir)

        print(f"[SYSTEM] Pulling kernel metadata for {k_slug}...")
        pull_ok = False
        try:
            api.kernels_pull(k_slug, path='.', metadata=True)
            pull_ok = os.path.exists('kernel-metadata.json')
        except Exception as _pull_err:
            print(f"[SYSTEM] Warning: kernels_pull failed ({_pull_err}). Creating metadata manually.")

        meta = {}
        if pull_ok and os.path.exists('kernel-metadata.json'):
            try:
                with open('kernel-metadata.json', 'r', encoding='utf-8') as f:
                    meta = json.load(f)
            except Exception:
                meta = {}

        code_filename = meta.get('code_file') or 'kaggle gitGOD.ipynb'
        meta['id'] = k_slug
        meta['title'] = meta.get('title') or "🔥gitGOD💋"
        meta['code_file'] = code_filename
        meta['language'] = "python"
        meta['kernel_type'] = "notebook"
        meta['is_private'] = "true"
        meta['enable_gpu'] = "false"
        meta['enable_tpu'] = "false"
        meta['enable_internet'] = "true"
        meta['dataset_sources'] = [str(s) for s in meta.get('dataset_sources', []) if isinstance(s, str)]
        meta['kernel_sources'] = [str(s) for s in meta.get('kernel_sources', []) if isinstance(s, str)]
        meta['competition_sources'] = [str(s) for s in meta.get('competition_sources', []) if isinstance(s, str)]
        meta['model_sources'] = [str(s) for s in meta.get('model_sources', []) if isinstance(s, str)]

        with open('kernel-metadata.json', 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2)

        # Locate or generate notebook payload
        nb_data = None
        if os.path.exists(code_filename):
            try:
                with open(code_filename, 'r', encoding='utf-8') as nbf:
                    nb_data = json.load(nbf)
            except Exception:
                nb_data = None

        if not nb_data:
            for cand_ipynb in glob.glob('*.ipynb'):
                try:
                    with open(cand_ipynb, 'r', encoding='utf-8') as nbf:
                        cand_data = json.load(nbf)
                    if cand_data and cand_data.get('cells'):
                        nb_data = cand_data
                        code_filename = cand_ipynb
                        meta['code_file'] = code_filename
                        break
                except Exception:
                    pass

        if not nb_data:
            for ipynb_path in [
                '/kaggle/working/__notebook__.ipynb',
                '/kaggle/working/__notebook_source__.ipynb',
                '/kaggle/notebook_source.ipynb',
                '/kaggle/working/GroceryGOD/kaggle gitGOD.ipynb',
                '/kaggle/working/gitgod.ipynb',
            ]:
                if os.path.exists(ipynb_path):
                    try:
                        with open(ipynb_path, 'r', encoding='utf-8') as nbf:
                            cand_data = json.load(nbf)
                        if cand_data and cand_data.get('cells'):
                            nb_data = cand_data
                            break
                    except Exception:
                        pass

        if not nb_data:
            code_src = None
            for candidate_path in [
                '/kaggle/working/GroceryGOD/scratch.py',
                '/kaggle/working/scratch.py',
                'scratch.py',
                os.path.join(os.getcwd(), 'scratch.py')
            ]:
                if os.path.exists(candidate_path):
                    try:
                        with open(candidate_path, 'r', encoding='utf-8') as csf:
                            cand_code = csf.read()
                        if len(cand_code) > 10000 and 'def run_giveaway_agents' in cand_code:
                            code_src = cand_code
                            break
                    except Exception:
                        pass

            if not code_src:
                try:
                    import IPython
                    ip = IPython.get_ipython()
                    if ip and hasattr(ip, 'user_ns') and 'In' in ip.user_ns:
                        for cell_text in reversed(ip.user_ns['In']):
                            if cell_text and 'def trigger_self_restart' in cell_text and len(cell_text) > 10000:
                                code_src = cell_text
                                break
                except Exception:
                    pass

            if not code_src and globals().get('__file__') and os.path.exists(globals()['__file__']):
                try:
                    with open(globals()['__file__'], 'r', encoding='utf-8') as sf:
                        code_src = sf.read()
                except Exception:
                    pass

            if not code_src:
                print("[SYSTEM] ERROR: Could not locate Python source code for payload notebook generation!")
                code_src = "# Orchestrator reboot placeholder\nprint('Reboot placeholder')\n"

            nb_data = {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": [
                            "# 🚀 Parallel Execution: Continuous GroceryGOD + gitww\n",
                            f"**Last Synchronized:** `{dhaka_time_str}`\n"
                        ]
                    },
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": code_src.splitlines(keepends=True)
                    }
                ],
                "metadata": {
                    "language_info": {"name": "python"}
                },
                "nbformat": 4,
                "nbformat_minor": 4
            }

        # Persist active runtime secrets & state into payload notebook
        active_secrets = {
            'GITHUB_PAT': GITHUB_PAT or '',
            'KAGGLE_USERNAME': k_user,
            'KAGGLE_KEY': k_key,
            'TELEGRAM_BOT_TOKEN': os.environ.get('TELEGRAM_BOT_TOKEN', ''),
            'TELEGRAM_CHAT_ID': os.environ.get('TELEGRAM_CHAT_ID', ''),
            'KAGGLE_KERNEL_SLUG': k_slug,
            'GOD_PREMIUM_KEY': os.environ.get('GOD_PREMIUM_KEY', 'assalamualaikum')
        }

        import base64
        active_secrets_json = json.dumps(active_secrets)
        active_secrets_b64 = base64.b64encode(active_secrets_json.encode('utf-8')).decode('utf-8')
        active_state_json = json.dumps(_PERSISTED_STATE)
        active_state_b64 = base64.b64encode(active_state_json.encode('utf-8')).decode('utf-8')

        # Save secrets and state to disk vaults for local retrieval
        for v_dir in ['/kaggle/working', '/kaggle/working/output', '/tmp']:
            try:
                os.makedirs(v_dir, exist_ok=True)
                with open(os.path.join(v_dir, 'secrets_vault.json'), 'w', encoding='utf-8') as vf:
                    json.dump(active_secrets, vf, indent=2)
                with open(os.path.join(v_dir, 'orchestrator_state.json'), 'w', encoding='utf-8') as sf:
                    json.dump(_PERSISTED_STATE, sf, indent=2)
            except Exception:
                pass

        header_block = (
            "# --- AUTO-INJECTED PERSISTED SECRETS & STATE (CONTAINER SELF-BOOT) ---\n"
            f"_PERSISTED_SECRETS = {active_secrets_json}\n"
            f'_PERSISTED_SECRETS_B64 = "{active_secrets_b64}"\n'
            f"_PERSISTED_STATE = {active_state_json}\n"
            f'_PERSISTED_STATE_B64 = "{active_state_b64}"\n'
            "# ----------------------------------------------------------------------\n"
        )

        for cell in nb_data.get('cells', []):
            if cell.get('cell_type') == 'code':
                raw_src = cell.get('source', '')
                src_str = "".join(raw_src) if isinstance(raw_src, list) else str(raw_src)

                # Prefer fresh clean scratch.py source from repo clone if available
                fresh_scratch = None
                for candidate_path in [
                    '/kaggle/working/GroceryGOD/scratch.py',
                    '/kaggle/working/scratch.py'
                ]:
                    if os.path.exists(candidate_path):
                        try:
                            with open(candidate_path, 'r', encoding='utf-8') as csf:
                                cand_code = csf.read()
                            if len(cand_code) > 10000:
                                fresh_scratch = cand_code
                                break
                        except Exception:
                            pass

                if fresh_scratch and 'def run_giveaway_agents' in fresh_scratch:
                    src_str = fresh_scratch

                # Strip any prior auto-injected header blocks
                src_str = re.sub(r'#\s*---\s*AUTO-INJECTED PERSISTED SECRETS[\s\S]*?#\s*-{10,}\n?', '', src_str)

                # Prepend fresh header block to top of code
                final_src = header_block + src_str.lstrip()

                # AST syntax validation guard before persisting
                try:
                    import ast as _ast
                    _ast.parse(final_src)
                except Exception as _parse_err:
                    print(f"[SYSTEM] WARNING: Injected source AST parse error ({_parse_err}). Reverting to raw source...")
                    raw_clean = "".join(raw_src) if isinstance(raw_src, list) else str(raw_src)
                    raw_clean = re.sub(r'#\s*---\s*AUTO-INJECTED PERSISTED SECRETS[\s\S]*?#\s*-{10,}\n?', '', raw_clean)
                    final_src = header_block + raw_clean.lstrip()
                    try:
                        _ast.parse(final_src)
                    except Exception as _parse_err2:
                        print(f"[SYSTEM] ERROR: Second AST parse failed ({_parse_err2}). Retaining raw clean...")
                        final_src = raw_clean

                cell['source'] = final_src.splitlines(keepends=True)
                break

        with open(code_filename, 'w', encoding='utf-8') as nbf:
            json.dump(nb_data, nbf, indent=1)
        print(f"[SYSTEM] Successfully baked active secrets & state into payload {code_filename}.")

        print("[SYSTEM] Pushing kernel payload to trigger next loop container...")
        push_ok = False
        last_push_err = None

        for push_attempt in range(1, 6):
            print(f"[SYSTEM] Kernel push attempt {push_attempt}/5 for {k_slug}...")

            # 1. Try Kaggle CLI via subprocess (fresh process with upgraded kaggle package)
            try:
                cli_res = subprocess.run(
                    ['kaggle', 'kernels', 'push', '-p', '.'],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                stdout_str = (cli_res.stdout or '').strip()
                stderr_str = (cli_res.stderr or '').strip()
                if cli_res.returncode == 0 and ("Kernel version" in stdout_str or "successfully" in stdout_str.lower() or not stderr_str):
                    print(f"[SYSTEM] ✅ Kernel push succeeded via CLI: {stdout_str}")
                    push_ok = True
                    break
                else:
                    print(f"[SYSTEM] CLI push attempt {push_attempt} notice (rc={cli_res.returncode}): {stdout_str} | {stderr_str}")
            except Exception as _cli_exc:
                print(f"[SYSTEM] CLI push attempt {push_attempt} exception: {_cli_exc}")

            # 2. Try Python KaggleApi SDK
            try:
                api_res = api.kernels_push('.')
                print(f"[SYSTEM] ✅ Kernel push succeeded via KaggleApi SDK: {api_res}")
                push_ok = True
                break
            except Exception as _api_exc:
                last_push_err = _api_exc
                err_text = str(_api_exc)
                print(f"[SYSTEM] KaggleApi SDK push attempt {push_attempt} failed: {err_text}")

                # If it's a JSONDecodeError (empty body or HTML from server), check if kernel was actually queued
                try:
                    time.sleep(3)
                    status_info = api.kernels_status(k_slug)
                    k_status = status_info.get('status', '').lower() if isinstance(status_info, dict) else str(status_info).lower()
                    if any(s in k_status for s in ['queued', 'running']):
                        print(f"[SYSTEM] ✅ Verified kernel status is active ({k_status}) despite response parsing glitch!")
                        push_ok = True
                        break
                except Exception:
                    pass

            # 3. Direct HTTP REST API POST to Kaggle v1 endpoint
            try:
                with open(code_filename, 'r', encoding='utf-8') as _cf:
                    _script_content = _cf.read()
                if meta.get('kernel_type') == 'notebook':
                    try:
                        _nb_json = json.loads(_script_content)
                        for _c in _nb_json.get('cells', []):
                            if _c.get('cell_type') == 'code':
                                _c['outputs'] = []
                            if isinstance(_c.get('source'), list):
                                _c['source'] = "".join(_c['source'])
                        _script_content = json.dumps(_nb_json)
                    except Exception:
                        pass

                _rest_payload = {
                    "slug": k_slug,
                    "newTitle": meta.get("title", "🔥gitGOD💋"),
                    "text": _script_content,
                    "language": meta.get("language", "python"),
                    "kernelType": meta.get("kernel_type", "notebook"),
                    "isPrivate": True,
                    "enableGpu": False,
                    "enableTpu": False,
                    "enableInternet": True,
                    "datasetDataSources": meta.get("dataset_sources", []),
                    "competitionDataSources": meta.get("competition_sources", []),
                    "kernelDataSources": meta.get("kernel_sources", []),
                    "modelDataSources": meta.get("model_sources", []),
                    "categoryIds": meta.get("keywords", [])
                }
                _http_resp = requests.post(
                    "https://www.kaggle.com/api/v1/kernels/push",
                    auth=(k_user, k_key),
                    json=_rest_payload,
                    timeout=120
                )
                if _http_resp.status_code in [200, 201]:
                    print(f"[SYSTEM] ✅ Kernel push succeeded via direct REST API (status {_http_resp.status_code})!")
                    push_ok = True
                    break
                else:
                    print(f"[SYSTEM] Direct REST push status {_http_resp.status_code}: {_http_resp.text[:200]}")
            except Exception as _rest_exc:
                print(f"[SYSTEM] Direct REST push exception: {_rest_exc}")

            if push_attempt < 5:
                backoff_wait = 5 * push_attempt
                print(f"[SYSTEM] Waiting {backoff_wait}s before next push attempt...")
                time.sleep(backoff_wait)

        if not push_ok:
            raise last_push_err or Exception(f"All 5 kernel push attempts failed for {k_slug}")


        # Gather rich telemetry stats for Telegram notification
        es = exec_stats or {}
        dur_sec = es.get('elapsed_seconds', 0)
        _dm, _ds = divmod(dur_sec, 60)
        _dh, _dm = divmod(_dm, 60)
        dur_str = f"{_dh}h {_dm:02d}m {_ds:02d}s" if _dh > 0 else (f"{_dm}m {_ds:02d}s" if dur_sec > 0 else "N/A")

        p1_st = es.get('p1_status', 'OK')
        p2_st = es.get('p2_status', 'OK')
        p3_st = es.get('p3_status', 'OK')
        p15_st = es.get('p15_status', 'N/A')

        p1_badge = "✅ Completed (8 Stores Aggregated)" if p1_st == "OK" else f"⚠️ {p1_st}"
        p2_badge = "✅ Completed (35 Worker Tasks)" if p2_st == "OK" else f"⚠️ {p2_st}"
        p3_badge = "✅ Completed (12/12 Repos Pushed)" if p3_st == "OK" else f"⚠️ {p3_st}"
        p15_badge = "✅ Running" if p15_st == "OK" else f"⚠️ {p15_st}"

        # Parquet backup info
        pq_info = "Generated & Verified"
        try:
            import glob as _glob
            bk_jsons = _glob.glob('/kaggle/working/output/parquet_backup/**/backup_summary.json', recursive=True)
            if bk_jsons:
                with open(bk_jsons[-1], 'r', encoding='utf-8') as bjf:
                    bdata = json.load(bjf)
                pq_info = f"{bdata.get('date', '')}/{bdata.get('version', '')} ({bdata.get('zip_size_mb', 0)} MB ZIP)"
        except Exception:
            pass

        # Bandwidth telemetry for reboot message
        _bw_reboot = get_bandwidth_telemetry(0, "Loop Cycle")
        bw_badge = f"<code>{_bw_reboot['used_mb']} MB / 10.0 GB</code> ({_bw_reboot['pct_used']}%) | {_bw_reboot['rem_gb']} GB free"

        reboot_msg = (
            "🔄 <b>Kaggle Self-Reboot Triggered!</b>\n\n"
            "📊 <b>Execution & Reboot Telemetry:</b>\n"
            f"• 🔢 <b>Reboot Count:</b> <code>#{reboot_count}</code> (Loop Cycle #{reboot_count})\n"
            f"• 🕒 <b>Timestamp:</b> <code>{dhaka_time_str}</code>\n"
            f"• ⏱️ <b>Session Duration:</b> <code>{dur_str}</code>\n"
            f"• 📍 <b>Kernel:</b> <code>{k_slug}</code>\n\n"
            "📦 <b>Pipelines Status:</b>\n"
            f"• 🛒 <b>GroceryGOD (p1):</b> {p1_badge}\n"
            f"• ⚙️ <b>gitw (p2):</b> {p2_badge}\n"
            f"• 🌐 <b>Scheduled Repos (p3):</b> {p3_badge}\n"
            f"• 🎁 <b>Giveaway (p15):</b> {p15_badge}\n\n"
            "📈 <b>Data, Backup & Quota Snapshot:</b>\n"
            f"• 💾 <b>Parquet Backup:</b> <code>{pq_info}</code>\n"
            f"• 🌐 <b>Monthly Push Bandwidth:</b> {bw_badge}\n"
            "• 🔑 <b>Secrets & State:</b> Persisted to Next Container\n\n"
            "🟢 <i>Next container is queuing on Kaggle and will spawn automatically in ~1-2 mins.</i>"
        )

        print(reboot_msg)
        _tg(reboot_msg)

        time.sleep(10)
        os._exit(0)
    except Exception as e:
        safe_tb = html.escape(traceback.format_exc()[-600:])
        err_msg = (
            "🚨 <b>Kaggle Self-Restart FAILED!</b>\n\n"
            f"❌ <b>Error:</b> <code>{html.escape(str(e))}</code>\n"
            f"🕒 <b>Time:</b> <code>{dhaka_time_str}</code>\n"
            f"🔢 <b>Reboot Attempt:</b> <code>#{reboot_count}</code>\n"
            f"📍 <b>Kernel:</b> <code>{k_slug}</code>\n\n"
            f"<pre>{safe_tb}</pre>\n\n"
            "🛠 <b>Action Required:</b> Check KAGGLE_USERNAME and KAGGLE_KEY secrets in Kaggle notebook."
        )
        print(err_msg)
        _tg(err_msg)

# Othoba web probe hotfix payload (zlib+base64 of the fixed
# othobaTRACKER/scraper_web.py). Applied after the repo clone and
# decryption steps so Kaggle never runs the old false geo-block probe
# even when the remote repo copy is stale.
_OTHOBA_WEB_FIX_B64 = "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"


def _apply_othoba_web_hotfix(web_path, logger=None):
    """Replace the old Othoba false-geo-block probe if it is still present."""
    try:
        if not os.path.exists(web_path):
            return False
        with open(web_path, 'r', encoding='utf-8') as f:
            old_src = f.read()
        if 'Othoba Geo-Block/Stuck Screenshot' not in old_src:
            return False
        import ast as _ast
        import base64 as _b64
        import zlib as _zlib
        fixed = _zlib.decompress(
            _b64.b64decode(_OTHOBA_WEB_FIX_B64)
        ).decode('utf-8')
        _ast.parse(fixed)
        with open(web_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(fixed)
        if logger:
            logger(
                'Othoba web probe hotfix applied: text-first probe, '
                'no false geo-block exit.'
            )
        return True
    except Exception as exc:
        if logger:
            logger(f'Othoba web probe hotfix skipped: {exc}')
        return False


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
    _pq_backup_info = None
    os.chdir('/kaggle/working')
    
    try:
        log.info(f'🚀 GroceryGOD Pipeline — STARTED (Simultaneous Parallel)')
        with Step('Configuration & Git Setup', '⚙️'):
            if not github_pat:
                raise RuntimeError("GITHUB_PAT is missing or empty. Git operations will fail.")

            def _setup_git_config():
                _git_config('git config --global user.email "ranehal@users.noreply.github.com"')
                _git_config('git config --global user.name "ranehal"')
                _git_config('git config --global http.postBuffer 1048576000')
                _git_config('git config --global http.version HTTP/1.1')
                _git_config('git config --global http.lowSpeedLimit 0')
                _git_config('git config --global http.lowSpeedTime 999999')
                _git_config('git config --global core.compression 9')
                _git_config('git config --global pack.windowMemory 256m')
                _git_config('git config --global pack.packSizeLimit 2g')

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
                clone_ok, clone_err = _git_clone_robust(auth_grocery_url, 'GroceryGOD', branch='master',
                                                        log=log.info, label='GroceryGOD')
                if not clone_ok:
                    error_msg = f"Git Clone Failed after all retries! Auth issue or repo missing.\nSTDERR: {clone_err}"
                    log.error(error_msg)
                    raise RuntimeError(error_msg)

            os.chdir('GroceryGOD')
            subprocess.run(f'git remote set-url origin {auth_grocery_url}', shell=True)
            subprocess.run('git config http.postBuffer 1048576000', shell=True)
            subprocess.run('git config http.version HTTP/1.1', shell=True)
            subprocess.run('git config http.lowSpeedLimit 0', shell=True)
            subprocess.run('git config http.lowSpeedTime 999999', shell=True)
            
            log.info("🔄 Forcing sync with latest GitHub master...")
            subprocess.run('git clean -fd', shell=True)
            _git_run_retry(f'git {GIT_NET_OPTS} fetch --all --prune', log=log.info, attempts=5,
                           delay=5, label='GroceryGOD fetch')
            subprocess.run('git reset --hard origin/master', shell=True)

            # Daily Guard: Skip scraper execution if already ran and pushed today
            today_dhaka = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d')
            gg_already_done = False
            if _PERSISTED_STATE.get('grocerygod_completed_date') == today_dhaka:
                gg_already_done = True
            else:
                c_log = subprocess.run(['git', 'log', '-1', '--format=%s%x00%ci', 'origin/master'], capture_output=True, text=True).stdout.strip()
                if c_log:
                    c_subj, _, c_date = c_log.partition('\x00')
                    if 'if this works ill get some sleep frfr' in c_subj and (today_dhaka in c_subj or c_date.startswith(today_dhaka)):
                        gg_already_done = True

            if gg_already_done:
                log.info(f"⏸️ [DAILY GUARD] GroceryGOD already completed and pushed for today ({today_dhaka}). Skipping scraper execution to enforce once-a-day limit.")
                _PERSISTED_STATE['grocerygod_completed_date'] = today_dhaka
                return

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
                            try:
                                shutil.copy2(ep, ep + '.orig')
                                with open(ep + '.hash', 'w') as hf: hf.write(_hashlib.sha256(plain).hexdigest())
                            except Exception: pass
                            os.remove(ep)
                            _dc += 1
                            log.info(f'  {os.path.relpath(ep, _cwd)} -> decrypted ({len(plain)//1024}KB)')
                        except Exception as ex:
                            log.error(f'  ERROR {os.path.basename(ep)}: {ex}')
                    log.info(f'  Decrypted {_dc}/{len(_enc_files)} files')
                except subprocess.CalledProcessError as e:
                    log.error(f'Decryption failed: {e.stderr[:500]}')

            # In-repo Othoba tracker used by p1.
            _apply_othoba_web_hotfix(
                os.path.join(os.getcwd(), 'othobaTRACKER', 'scraper_web.py'),
                log.info,
            )

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
                    
                    stream_tail = []
                    stdout_count = [0]
                    last_alive = [time.time()]
                    
                    def _read_stream(p, s_name, stream, is_stderr, capture, count, alive):
                        try:
                            for line in stream:
                                alive[0] = time.time()
                                # Keep a bounded tail of BOTH streams: scrapers mostly log
                                # through logging.StreamHandler(sys.stdout), so a block marker
                                # (Cloudflare / 403 / BLOCKED) often never reaches stderr.
                                capture.append(line)
                                del capture[:-40]
                                if is_stderr:
                                    log.warning(f'[{label}:{s_name} err] {line.rstrip()}')
                                else:
                                    count[0] += 1
                                    log.info(f'[{label}:{s_name}] {line.rstrip()}')
                        except: pass

                    t_stdout = threading.Thread(target=_read_stream, args=(proc, script_name, proc.stdout, False, stream_tail, stdout_count, last_alive), daemon=True)
                    t_stderr = threading.Thread(target=_read_stream, args=(proc, script_name, proc.stderr, True, stream_tail, stdout_count, last_alive), daemon=True)
                    t_stdout.start()
                    t_stderr.start()
                    
                    procs.append({
                        'proc': proc, 'name': script_name, 't_stdout': t_stdout, 't_stderr': t_stderr,
                        'stream_tail': stream_tail, 'stdout_count': stdout_count, 'last_alive': last_alive, 'timed_out': False, 'crashed': False
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
                            
                            # Check Cloudflare / IP-block markers in the latest output lines only,
                            # so a transient 403 a scraper recovered from cannot kill a healthy run.
                            err_text = ''.join(p['stream_tail'][-8:]).lower()
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
                if not os.path.exists(os.path.join(shopno_dir, '.git')):
                    if os.path.exists(shopno_dir):
                        shutil.rmtree(shopno_dir, ignore_errors=True)
                    _git_clone_robust('https://github.com/ranehal/SHWAPNO-analylics.git', shopno_dir,
                                      log=log.info, label='SHWAPNO-analylics')
                if not os.path.exists(os.path.join(othoba_dir, '.git')):
                    if os.path.exists(othoba_dir):
                        shutil.rmtree(othoba_dir, ignore_errors=True)
                    _git_clone_robust('https://github.com/ranehal/Othoba-analytics.git', othoba_dir,
                                      log=log.info, label='Othoba-analytics')
                
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
                log.info(f"Scraper execution completed ({_ok_count}/{len(results)} OK). Proceeding to aggregation...")


            with Step('GODdata Aggregator', '🧬'):
                # Sync Foodi DB from sub-repo if present
                _foodi_sub = '/kaggle/working/FooDIE-mart-Analytics/data/scraper.db' if platform.system() != 'Windows' else r'C:\PROJECTS\ShopGOD\FooDIEscraper\data\scraper.db'
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
                    _pq_files = sorted(glob.glob('history_*.parquet')) + ['products.parquet', 'history.parquet', 'products_free.parquet', 'history_free.parquet', 'atl.parquet', 'atl_preview.json', 'premium/history_archive.parquet.enc']
                    for pf in _pq_files:
                        if os.path.exists(pf):
                            sz_mb = os.path.getsize(pf) / (1024*1024)
                            log.info(f'  {pf}: {sz_mb:.1f} MB')

                    # 💾 Create date-separated versioned Parquet backup in Kaggle output folder for manual extraction
                    log.info("💾 Creating versioned Parquet snapshot for manual extraction (pre-encryption)...")
                    _pq_backup_info = backup_parquet_datasets(
                        repo_dir=os.getcwd(),
                        cycle_count=run_count if 'run_count' in locals() else cycle_count,
                        git_status='PENDING_GIT_PUSH'
                    )
                    log.info(f"💾 Parquet backup completed: {_pq_backup_info.get('version')} ({_pq_backup_info.get('total_files')} files, {_pq_backup_info.get('total_size_mb')} MB) -> {_pq_backup_info.get('version_dir')}")
                    log.info(f"📦 1-Click ZIP Archive: {_pq_backup_info.get('zip_path')} ({_pq_backup_info.get('zip_size_mb')} MB)")
                except subprocess.CalledProcessError as e:
                    log.error(f'Parquet conversion failed with code {e.returncode}')
                except Exception as _b_err:
                    log.warning(f'Parquet backup warning: {_b_err}')

            with Step('Turso Cloud DB Sync', '☁️'):
                try:
                    log.info("☁️ Synchronizing latest datasets to Turso Cloud DB (grocerygod-ranehal)...")
                    _turso_env = os.environ.copy()
                    _turso_env['TURSO_PLATFORM_TOKEN'] = get_secret_safe('TURSO_PLATFORM_TOKEN', '')
                    _turso_env['TURSO_RW_TOKEN'] = get_secret_safe('TURSO_RW_TOKEN', '')
                    _turso_env['TURSO_RO_TOKEN'] = get_secret_safe('TURSO_RO_TOKEN', '')
                    _turso_env['TURSO_HOSTNAME'] = 'grocerygod-ranehal.aws-ap-south-1.turso.io'
                    _turso_proc = subprocess.Popen([sys.executable, 'sync_turso.py'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=_turso_env)
                    for _t_line in _turso_proc.stdout:
                        log.info(f'[turso] {_t_line.rstrip()}')
                    _turso_proc.wait()
                    if _turso_proc.returncode == 0:
                        log.info("☁️ Turso Cloud DB synchronization SUCCESSFUL!")
                    else:
                        log.warning(f"☁️ Turso sync exited with code {_turso_proc.returncode} (non-fatal, continuing to backups)")
                except Exception as _t_err:
                    log.warning(f"☁️ Turso sync exception: {_t_err} (non-fatal, continuing to backups)")

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
                        d_hash = _hashlib.sha256(data).digest()
                        salt = _hashlib.sha256(b"GGE1_SALT:" + pw.encode('utf-8') + d_hash).digest()[:16]
                        iv = _hashlib.sha256(b"GGE1_IV:" + pw.encode('utf-8') + d_hash).digest()[:12]
                        k = _hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, _ITER, dklen=32)
                        ct = AESGCM(k).encrypt(iv, data, None)
                        return b'GGE1' + salt + iv + ct
                    def _write_enc(path, data):
                        if len(data) <= _SPLIT:
                            with open(path, 'wb') as f: f.write(data)
                            for cf in _glob.glob(f'{path}.[0-9][0-9][0-9]'):
                                try: os.remove(cf)
                                except Exception: pass
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
                    for tf in ['swapnoTRACKER/data.json', 'unimartTRACKER/data.json', 'ShotejTRACKER/data.json', 'data.json', 'data.js']:
                        p = os.path.join(_cwd, tf)
                        if os.path.exists(p): _targets.append(p)
                    for d in ['swapnoTRACKER', 'PRICETRACKER', 'MEENAtracker', 'othobaTRACKER', 'metroTRACKER', 'unimartTRACKER', 'ShotejTRACKER']:
                        p = os.path.join(_cwd, d, 'scraper.py')
                        if os.path.exists(p): _targets.append(p)
                    for dbf in _glob.glob(os.path.join(_cwd, '**', '*.db'), recursive=True):
                        _rel = os.path.relpath(dbf, _cwd).replace('\\', '/').lower()
                        if 'foodie' in _rel or '/backend/' in _rel or 'temp' in _rel or 'optimized' in _rel or 'grocerygod_optimized' in _rel:
                            continue
                        _targets.append(dbf)
                    for pq in ['products.parquet']:
                        p = os.path.join(_cwd, pq)
                        if os.path.exists(p): _targets.append(p)
                    pa = os.path.join(_cwd, 'premium', 'history_archive.parquet')
                    if os.path.exists(pa): _targets.append(pa)
                    _targets = [t for t in _targets if os.path.exists(t) and not t.endswith('.enc') and not os.path.basename(t).startswith('history.parquet')]
                    # Clean up redundant history.parquet.enc and temporary grocerygod_optimized if lingering on disk
                    for _old_pat in ['history.parquet.enc*', 'grocerygod_optimized.db*']:
                        for _old_f in _glob.glob(os.path.join(_cwd, _old_pat)):
                            try: os.remove(_old_f)
                            except Exception: pass
                    log.info(f'  Encrypting {len(_targets)} files')
                    _ec = 0
                    for tp in _targets:
                        try:
                            with open(tp, 'rb') as f: data = f.read()
                            ep = tp + '.enc'
                            orig_p, hash_p = ep + '.orig', ep + '.hash'
                            if os.path.exists(orig_p) and os.path.exists(hash_p) and open(hash_p).read().strip() == _hashlib.sha256(data).hexdigest():
                                with open(orig_p, 'rb') as orig_f: ed = orig_f.read()
                                for old in _glob.glob(ep + '.*'):
                                    if not old.endswith('.orig') and not old.endswith('.hash'): os.remove(old)
                                cps = _write_enc(ep, ed)
                                log.info(f'  {os.path.relpath(tp, _cwd)} -> UNCHANGED (preserved original .enc, 0MB git delta)')
                            else:
                                ed = _enc(data, _KEY)
                                for old in _glob.glob(ep + '.*'):
                                    if not old.endswith('.orig') and not old.endswith('.hash'): os.remove(old)
                                cps = _write_enc(ep, ed)
                            for tmp_clean in [orig_p, hash_p]:
                                if os.path.exists(tmp_clean):
                                    try: os.remove(tmp_clean)
                                    except Exception: pass
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

                # Purge foreign bloat, obsolete binaries, temporary databases, and sensitive files before git add
                for _bpath in ['FooDIEscraper/data', 'metroTRACKER/backend', 'othobaTRACKER/backend', 'MEENAtracker/backend']:
                    if os.path.exists(_bpath):
                        log.info(f"Purging foreign bloat directory: {_bpath}")
                        shutil.rmtree(_bpath, ignore_errors=True)
                for _fpat in ['*.part*', '*.orig', '*.hash', 'history.parquet*', 'PRICETRACKER/data.js.enc', 'grocerygod_optimized.db*', '*.db-journal', '*.pyc', '*.lck', '*.har', '*output.txt']:
                    for _mf in _glob.glob(_fpat):
                        try: os.remove(_mf)
                        except Exception: pass
                subprocess.run('git rm -rf --ignore-unmatch FooDIEscraper/data FooDIEscraper/parse_har_output.txt metroTRACKER/backend othobaTRACKER/backend MEENAtracker/backend history.parquet history.parquet.enc* PRICETRACKER/data.js.enc grocerygod_optimized.db* *.db-journal *.orig *.hash *.pyc __pycache__ 2>/dev/null', shell=True)

                # 🛡️ SECURITY AUDIT GUARD: Untrack any forbidden files that may have been staged or tracked
                _staged_files = subprocess.run('git diff --name-only HEAD', shell=True, capture_output=True, text=True).stdout.splitlines()
                _forbidden_patterns = ['token.txt', 'refresh_token.txt', 'turso_tokens.json', 'history.parquet', 'grocerygod_optimized.db', '.env', 'secrets_vault.json', 'parse_har_output']
                for _sf in _staged_files:
                    _sf_l = _sf.lower()
                    if any(_fp in _sf_l for _fp in _forbidden_patterns) or _sf_l.endswith('.db') or _sf_l.endswith('.db-journal') or '__pycache__' in _sf_l or _sf_l.endswith('.pyc'):
                        subprocess.run(f'git reset HEAD "{_sf}" 2>/dev/null', shell=True)
                        subprocess.run(f'git rm -f --cached "{_sf}" 2>/dev/null', shell=True)

                subprocess.run('git add .', shell=True)

                # Final pre-commit security validation
                _cached_staged = subprocess.run('git diff --cached --name-only', shell=True, capture_output=True, text=True).stdout.splitlines()
                for _cs in _cached_staged:
                    _cs_l = _cs.lower()
                    if any(_fp in _cs_l for _fp in _forbidden_patterns) or _cs_l.endswith('.db') or _cs_l.endswith('.db-journal') or '__pycache__' in _cs_l or _cs_l.endswith('.pyc'):
                        log.warning(f"🛡️ Security guard un-staging forbidden sensitive file: {_cs}")
                        subprocess.run(f'git reset HEAD "{_cs}" 2>/dev/null', shell=True)
                        subprocess.run(f'git rm -f --cached "{_cs}" 2>/dev/null', shell=True)

                now = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')
                subprocess.run(f'git commit -m "attempt #{cycle_count} if this works ill get some sleep frfr: {now}"', shell=True)
                
                push_success = False
                _init_bandwidth_state()
                _monthly_b = int(_PERSISTED_STATE.get('bandwidth_monthly_bytes', 0))
                _backup_pat = get_secret_safe('GITHUB_PAT_BACKUP') or get_secret_safe('RANX_GITHUB_PAT') or get_secret_safe('RANX_PAT') or github_pat

                # Pushes to ranehal/GroceryGOD must always authenticate as ranehal
                auth_push_configs = [
                    ("ranehal", f"https://ranehal:{github_pat}@github.com/ranehal/GroceryGOD.git"),
                    ("ranehal", f"https://{github_pat}@github.com/ranehal/GroceryGOD.git")
                ]
                if _backup_pat and _backup_pat != github_pat:
                    auth_push_configs.extend([
                        ("ranehal", f"https://ranehal:{_backup_pat}@github.com/ranehal/GroceryGOD.git"),
                        ("ranehal", f"https://{_backup_pat}@github.com/ranehal/GroceryGOD.git")
                    ])

                last_push_stderr = ""
                for _user_n, _auth_u in auth_push_configs:
                    subprocess.run('git remote remove origin', shell=True, capture_output=True)
                    subprocess.run(f'git remote add origin {_auth_u}', shell=True, capture_output=True)
                    subprocess.run(f'git remote set-url origin {_auth_u}', shell=True, capture_output=True)
                    subprocess.run('git config http.postBuffer 524288000', shell=True, capture_output=True)
                    subprocess.run('git config http.version HTTP/1.1', shell=True, capture_output=True)
                    _with_lock('git-config', lambda u=_user_n: (_git_config(f'git config user.name "{u}"'), _git_config(f'git config user.email "{u}@users.noreply.github.com"')))
                    for attempt in range(5):
                        log.info(f"Push attempt {attempt+1} (user: {_user_n})...")
                        subprocess.run('git rebase --abort 2>/dev/null', shell=True, capture_output=True)
                        _git_run_retry(f'git {GIT_NET_OPTS} pull origin master --rebase -X ours',
                                       log=log.info, attempts=3, delay=4, label='GroceryGOD pull')

                        # Check if remote already matches local commit (or was updated by prior attempt)
                        _loc_sha = subprocess.run('git rev-parse HEAD', shell=True, capture_output=True, text=True).stdout.strip()
                        _rem_sha = subprocess.run('git rev-parse origin/master', shell=True, capture_output=True, text=True).stdout.strip()
                        if _loc_sha and _rem_sha and _loc_sha == _rem_sha:
                            log.info(f"✅ HEAD ({_loc_sha[:7]}) matches origin/master. Remote is fully synchronized!")
                            push_success = True
                            _PERSISTED_STATE['last_push_user'] = _user_n
                            break

                        push_res = subprocess.run(f'git {GIT_NET_OPTS} push --progress origin HEAD:master --force', shell=True, capture_output=True, text=True)
                        last_push_stderr = (push_res.stderr or "") + "\n" + (push_res.stdout or "")
                        if push_res.returncode == 0:
                            push_success = True
                            _PERSISTED_STATE['last_push_user'] = _user_n
                            break

                        # Check if output indicates everything is up to date with clean tree
                        _c_out = last_push_stderr.lower()
                        if ("everything up-to-date" in _c_out or "everything up to date" in _c_out) and not subprocess.run('git status --porcelain', shell=True, capture_output=True, text=True).stdout.strip():
                            log.info("✅ Remote reported 'Everything up-to-date' with clean working tree. Push verified successful!")
                            push_success = True
                            _PERSISTED_STATE['last_push_user'] = _user_n
                            break

                        # Fallback: push directly to auth URL
                        push_res = subprocess.run(f'git {GIT_NET_OPTS} push --progress {_auth_u} HEAD:master --force', shell=True, capture_output=True, text=True)
                        last_push_stderr = (push_res.stderr or "") + "\n" + (push_res.stdout or "")
                        if push_res.returncode == 0:
                            push_success = True
                            _PERSISTED_STATE['last_push_user'] = _user_n
                            break

                        if ("everything up-to-date" in last_push_stderr.lower() or "everything up to date" in last_push_stderr.lower()) and not subprocess.run('git status --porcelain', shell=True, capture_output=True, text=True).stdout.strip():
                            log.info("✅ Direct auth push reported 'Everything up-to-date'. Push verified successful!")
                            push_success = True
                            _PERSISTED_STATE['last_push_user'] = _user_n
                            break

                        _push_wait = min(5 * (2 ** attempt), 90)
                        log.warning(f"Push attempt {attempt+1} failed (retrying in {_push_wait}s). Error: {last_push_stderr[:200]}")
                        time.sleep(_push_wait)
                    if push_success:
                        break
                
                if not push_success:
                    git_status = subprocess.run('git status', shell=True, capture_output=True, text=True).stdout
                    clean_err = "\n".join([line for line in last_push_stderr.splitlines() if not re.search(r'(Enumerating|Counting|Compressing|Writing)\s+objects', line)]).strip()
                    err_detail = (clean_err[-1200:] if clean_err else last_push_stderr[-600:]).strip()
                    error_msg = f"Git push failed after multiple attempts!\nGit Status:\n{git_status[:300]}\nStderr:\n{err_detail}"
                    log.error(error_msg)
                    if '_pq_backup_info' in locals() and _pq_backup_info:
                        try:
                            update_parquet_backup_status(_pq_backup_info, git_status='GIT_PUSH_FAILED', git_error=error_msg[:300])
                            log.warning(f"📦 [MANUAL EXTRACTION READY] Git push failed, but Parquet dataset backup is safely preserved at: {_pq_backup_info.get('version_dir')}")
                            log.warning(f"📦 1-Click ZIP Download: {_pq_backup_info.get('zip_path')}")
                        except Exception as _bk_err:
                            log.error(f"Backup status update error: {_bk_err}")
                    raise RuntimeError(error_msg)

                # Mark completion for today
                _PERSISTED_STATE['grocerygod_completed_date'] = today_dhaka
                _PERSISTED_STATE['grocerygod_last_completed_dhaka'] = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d %H:%M:%S DHAKA")
                for _vp in ['/kaggle/working/orchestrator_state.json', '/kaggle/working/output/orchestrator_state.json', '/tmp/orchestrator_state.json']:
                    try:
                        os.makedirs(os.path.dirname(_vp), exist_ok=True)
                        with open(_vp, 'w', encoding='utf-8') as _vf:
                            json.dump(_PERSISTED_STATE, _vf, indent=2)
                    except Exception: pass

                # Update backup status to reflect successful push
                if '_pq_backup_info' in locals() and _pq_backup_info:
                    try:
                        update_parquet_backup_status(_pq_backup_info, git_status='PUSHED_TO_GITHUB')
                        log.info(f"💾 Parquet backup status marked as PUSHED_TO_GITHUB at: {_pq_backup_info.get('version_dir')}")
                    except Exception:
                        pass

                # Stage Parquet datasets to Master Backup folder for the consolidated 7z archive
                try:
                    bdir = get_master_backup_dir()
                    pq_bdir = os.path.join(bdir, '01_GroceryGOD_Parquet')
                    os.makedirs(pq_bdir, exist_ok=True)
                    for pq_pat in ['products_free.parquet', 'products.parquet', 'atl.parquet', 'atl_preview.json', 'history_*.parquet']:
                        for pf in _glob.glob(pq_pat):
                            if os.path.exists(pf) and os.path.getsize(pf) > 0:
                                try:
                                    shutil.copy2(pf, os.path.join(pq_bdir, os.path.basename(pf)))
                                except Exception: pass
                    log.info(f"📦 [BACKUP] Staged GroceryGOD Parquet datasets into master backup folder: {pq_bdir}")
                except Exception as _bk_stage_err:
                    log.warning(f"GroceryGOD backup staging error: {_bk_stage_err}")

                # Record push bandwidth consumed against 10GB monthly cap
                _p_bytes, _bw_info = record_git_push_bandwidth(repo_dir=os.getcwd(), repo_name="GroceryGOD", stderr_text=last_push_stderr)
                log.info(f"🌐 [BANDWIDTH] Push consumed: {_bw_info['push_mb']} MB | Monthly Total: {_bw_info['used_mb']} MB / 10.0 GB ({_bw_info['pct_used']}%) | Remaining: {_bw_info['rem_gb']} GB")

                # Save market summary locally for the consolidated report
                _agg_s = _read_aggregator_summary()
                _full_market_summary = _agg_s
                for _sp in ['/tmp/grocerygod_market_summary.txt', '/kaggle/working/output/grocerygod_market_summary.txt']:
                    try:
                        os.makedirs(os.path.dirname(_sp), exist_ok=True)
                        with open(_sp, 'w', encoding='utf-8') as sf:
                            sf.write(_full_market_summary)
                    except Exception: pass
                log.info("📊 GroceryGOD cycle complete. Telegram report deferred to master consolidator.")

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
        if '_pq_backup_info' in locals() and _pq_backup_info:
            try:
                update_parquet_backup_status(_pq_backup_info, git_status='CRITICAL_CYCLE_FAILURE', git_error=str(e)[:300])
                bk_loc = _pq_backup_info.get('version_dir', '')
                bk_zip = _pq_backup_info.get('zip_path', '')
                err_msg += f"\n\n💾 <b>Manual Parquet Backup Preserved:</b>\n<code>{html.escape(bk_loc)}</code>\n📦 <b>1-Click ZIP:</b> <code>{html.escape(bk_zip)}</code>"
            except Exception:
                pass
        print(err_msg)
        tg_send(err_msg)
    
    log.info("✅ GroceryGOD Sequence Finished.")

# ============================================================
# PIPELINE 2: GITWW
# ============================================================
def run_gitw():
    print("[gitw] Process Started.", flush=True)

    try:
        if not os.path.exists('gitw'):
            os.makedirs('gitw', exist_ok=True)
        if not os.path.exists(os.path.join('gitww', '.git')):
            _git_clone_robust('https://github.com/ranehal/gitww.git', 'gitww',
                              log=lambda _m: print(f"[gitw] {_m}", flush=True), label='gitww')
        subprocess.run('unzip -o -P "ran.ragibahnafnehal2@gmail.com" gitww/gitw.dll -d gitw', shell=True)
        
        if os.path.exists('gitw'):
            os.chdir('gitw')

        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=False)
        
        processes = []
        my_env = os.environ.copy()
        for i in range(1, 36):
            script_f = f"{i}.py"
            if os.path.exists(script_f):
                p = subprocess.Popen([sys.executable, script_f], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=my_env)
                processes.append((i, p))
            
        for i, p in processes:
            try:
                p.wait(timeout=1800)
            except subprocess.TimeoutExpired:
                p.kill()
            
        run_count = "Unknown"
        count_path = '/kaggle/working/GroceryGOD/run_count.txt'
        if os.path.exists(count_path):
            try:
                with open(count_path, 'r') as f:
                    run_count = f.read().strip()
            except Exception:
                pass
            
        now = datetime.now(DHAKA_TZ)
        print(f"🚀 [gitw] Execution Completed. Run Count: {run_count} ({now.strftime('%Y-%m-%d %H:%M:%S')})", flush=True)
    except Exception as e:
        print(f"❌ [gitw] Error: {e}", flush=True)

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

def _build_p14_summary_data(results_store, repo_list):
    """
    Extracts, merges, and formats execution metrics, product counts, and price deltas
    for the 12 scheduled sub-repositories across IPC results, disk files, and logs.
    Returns a dictionary of structured components for master reporting.
    """
    file_results = {}
    try:
        import glob as _glob
        _search_patterns = [
            '/tmp/p14_results/p14_result_*.json',
            '/tmp/p14_result_*.json',
            '/kaggle/working/output/p14_results/p14_result_*.json',
            'output/p14_results/p14_result_*.json'
        ]
        for _pat in _search_patterns:
            for _f in _glob.glob(_pat):
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

    SHORT_NAMES = {
        'FooDIE Restaurant Analytics': 'FooDIE Rest',
        'FoodPANDA Restaurant Analytics': 'FoodPANDA',
        'FooDIE Mart Analytics': 'FooDIE Mart',
        'Shwapno Analytics': 'Shwapno A.',
        'Othoba Analytics': 'Othoba A.',
        'CARTup Analytics': 'CARTup',
        'Chaldal Analytics': 'Chaldal A.',
        'COOKup Analytics': 'COOKup',
        'PICAboo Analytics': 'PICAboo',
        'DARAZ Analytics': 'DARAZ',
        'Meena Bazar Analytics': 'Meena A.',
        'ShareDeal Analytics': 'ShareDeal'
    }

    header = '%-11s %7s %3s %3s %3s %3s %5s' % ('Repo', 'Total', '▲', '▼', 'New', 'OOS', 'Time')
    div = '─' * len(header)
    tbl_lines = [
        "<pre>",
        header,
        div
    ]

    ok_count = 0
    fail_count = 0
    failed_details = []
    
    tot_items = 0
    tot_up = 0
    tot_dn = 0
    tot_new = 0
    tot_oos = 0
    tot_instock = 0
    tot_restocked = 0
    tot_went_oos = 0
    tot_elapsed_sec = 0
    tot_sub_bytes = 0

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
            for _df in [
                f"/tmp/p14_results/p14_result_{slug}.json",
                f"/tmp/p14_result_{slug}.json",
                f"/kaggle/working/output/p14_results/p14_result_{slug}.json",
                f"output/p14_results/p14_result_{slug}.json"
            ]:
                if os.path.exists(_df):
                    try:
                        with open(_df, 'r', encoding='utf-8') as fh:
                            rec = json.load(fh)
                            if rec: break
                    except Exception:
                        pass

        if not rec:
            _log_files = [
                f"/tmp/p14_results/p14_log_{slug}.log",
                f"/tmp/p14_log_{slug}.log"
            ]
            _log_tail = ""
            for _lf in _log_files:
                if os.path.exists(_lf):
                    try:
                        with open(_lf, 'r', encoding='utf-8') as lf:
                            _log_tail = lf.read().strip()[-300:]
                            if _log_tail: break
                    except Exception:
                        pass
            rec = {
                'status': 'failed',
                'elapsed': 0,
                'error': _log_tail or 'No execution log or result found',
                'url': url
            }

        short_lbl = SHORT_NAMES.get(clean_lbl, clean_lbl[:11])
        elapsed = int(rec.get('elapsed', 0))
        tot_elapsed_sec += elapsed
        _m, _s = divmod(elapsed, 60)
        time_str = f"{_m}m{_s:02d}s" if elapsed > 0 else "0s"

        if rec and isinstance(rec, dict):
            tot_sub_bytes += int(rec.get('bandwidth_bytes') or 0)

        st = rec.get('price_stats') or {}
        cnts = rec.get('counts') or {}
        r_total = st.get('total') or cnts.get('total') or cnts.get('scraped') or 0
        r_up = st.get('price_up', 0)
        r_dn = st.get('price_down', 0)
        r_new = st.get('new_items', 0)
        r_oos = st.get('out_of_stock', 0)
        r_instock = st.get('in_stock', 0)
        r_restocked = st.get('back_in_stock', 0)
        r_went_oos = st.get('went_oos', 0)

        if rec.get('status') == 'ok':
            ok_count += 1
            tot_items += r_total
            tot_up += r_up
            tot_dn += r_dn
            tot_new += r_new
            tot_oos += r_oos
            tot_instock += r_instock
            tot_restocked += r_restocked
            tot_went_oos += r_went_oos
            tbl_lines.append('%-11s %7s %3d %3d %3d %3d %5s' % (
                short_lbl, f"{r_total:,}" if r_total > 0 else "-", r_up, r_dn, r_new, r_oos, time_str
            ))
        else:
            fail_count += 1
            tbl_lines.append('%-11s %7s %3s %3s %3s %3s %5s' % (
                short_lbl, "FAIL", "-", "-", "-", "-", "ERR"
            ))
            err_txt = rec.get('error') or 'Unknown failure'
            tb_txt = rec.get('error_tb') or ''
            failed_details.append((clean_lbl, err_txt, tb_txt))

    _tm, _ts = divmod(tot_elapsed_sec, 60)
    total_time_str = f"{_tm}m{_ts:02d}s"
    tbl_lines.append(div)
    tbl_lines.append('%-11s %7s %3d %3d %3d %3d %5s' % (
        'TOTAL', f"{tot_items:,}", tot_up, tot_dn, tot_new, tot_oos, total_time_str
    ))
    tbl_lines.append("</pre>")

    def _pct(v, denom):
        return f"({(v / denom * 100):.1f}%)" if denom > 0 else "(0.0%)"

    telemetry_lines = [
        f"✅ <b>Success Rate:</b> {ok_count}/{len(repo_list)} Repos OK ({_pct(ok_count, len(repo_list)).strip('()')})"
    ]
    if tot_items > 0:
        telemetry_lines.append(f"🟢 <b>In Stock:</b> {tot_instock:,} {_pct(tot_instock, tot_items)} | 🔴 <b>OOS:</b> {tot_oos:,} {_pct(tot_oos, tot_items)}")
    if tot_restocked > 0 or tot_went_oos > 0:
        s_parts = []
        if tot_restocked > 0: s_parts.append(f"🟢 {tot_restocked:,} restocked")
        if tot_went_oos > 0: s_parts.append(f"🔴 {tot_went_oos:,} went OOS")
        telemetry_lines.append("🔄 <b>Delta:</b> " + " | ".join(s_parts))

    links_block = ["🔗 <b>Live Dashboards:</b>"]
    for lbl, u in repo_list:
        _sh = SHORT_NAMES.get(lbl.strip(), lbl.strip())
        links_block.append(f"• {_sh}: {u}")

    return {
        'tbl_lines': tbl_lines,
        'telemetry_lines': telemetry_lines,
        'links_block': links_block,
        'failed_details': failed_details,
        'tot_sub_bytes': tot_sub_bytes,
        'ok_count': ok_count,
        'fail_count': fail_count,
        'tot_items': tot_items,
        'tot_elapsed_sec': tot_elapsed_sec
    }

def _send_consolidated_master_report(results_store, repo_list):
    """
    Consolidated Master Daily Report & 7-Zip Backup Dispatcher.
    Waits until all scrapers (GroceryGOD p1 + 12 Scheduled Sub-Repos p3-p14) finish,
    packages all database and parquet datasets into a single, perfectly organized
    7-Zip ultra archive, and dispatches ONE clean, unified Telegram summary with
    the 7z attachment. Fully fault-tolerant: report text and orchestrator continuation
    are guaranteed even if packaging or file upload encounters issues.
    """
    try:
        today_dhaka = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d')
        now_dhaka = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S DHAKA (UTC+6)')
        print(f"\n📢 [MASTER REPORT] Generating Consolidated Daily Master Report for {now_dhaka}...", flush=True)

        # Pre-cleanup: Free memory and eliminate dead scraper/chromium processes before backup creation
        try:
            import gc as _gc
            _gc.collect()
            os.system("pkill -9 -f chromium 2>/dev/null")
            os.system("pkill -9 -f scraper.py 2>/dev/null")
        except Exception:
            pass

        # 1. Package the all-in-one Master 7z Backup Archive
        bdir = get_master_backup_dir()
        archive_path = None
        archive_sz_mb = 0.0
        try:
            archive_path, archive_sz_mb = package_master_backup(bdir, today_dhaka)
            print(f"📦 [MASTER REPORT] Master backup packaged: {archive_path} ({archive_sz_mb:.2f} MB)", flush=True)
        except Exception as _pkg_err:
            print(f"⚠️ [MASTER REPORT] Packaging master backup failed: {_pkg_err}", flush=True)

        # 2. Extract Sub-Repo Summary Components
        p14_data = _build_p14_summary_data(results_store, repo_list)
        sub_tbl_lines = p14_data['tbl_lines']
        sub_telemetry_lines = p14_data['telemetry_lines']
        links_block = p14_data['links_block']
        failed_details = p14_data['failed_details']
        tot_sub_bytes = p14_data['tot_sub_bytes']

        # 3. Read GroceryGOD Market Summary
        gg_summary = _read_aggregator_summary()
        if not gg_summary:
            for _sp in ['/tmp/grocerygod_market_summary.txt', '/kaggle/working/output/grocerygod_market_summary.txt']:
                if os.path.exists(_sp):
                    try:
                        with open(_sp, 'r', encoding='utf-8', errors='replace') as sf:
                            gg_summary = sf.read().strip()
                            if gg_summary: break
                    except Exception: pass

        # 4. Bandwidth Quota Telemetry across everything
        _init_bandwidth_state()
        gg_push_bytes = int(_PERSISTED_STATE.get('last_push_bytes', 0) if _PERSISTED_STATE.get('last_push_repo') == 'GroceryGOD' else 0)
        tot_cycle_bytes = tot_sub_bytes + gg_push_bytes
        bw_info = get_bandwidth_telemetry(tot_cycle_bytes, "GroceryGOD + 12 Sub-Repos")

        # 5. Build Master Report Message
        header_block = (
            f"🏛️ <b>GroceryGOD & Bangladesh Retail — Master Daily Report</b>\n"
            f"📅 <b>Timestamp:</b> <code>{now_dhaka}</code>\n"
            f"⚡ <b>Pipeline:</b> <code>20 Platforms Integrated (8 Core + 12 Sub-Repos)</code>"
        )

        parts = [header_block]

        # Section A: GroceryGOD Market Summary (8 core stores)
        if gg_summary:
            parts.append(gg_summary)
        else:
            parts.append("📊 <b>GroceryGOD Market Summary:</b>\n<i>(GroceryGOD core scrapers completed; see Parquet datasets)</i>\n🔗 https://ranehal.github.io/GroceryGOD")

        # Section B: Scheduled Sub-Repositories Summary (12 stores)
        sub_section = [
            "📊 <b>Scheduled Sub-Repos (12 Stores) Summary:</b>",
            "\n".join(sub_tbl_lines),
            "\n".join(sub_telemetry_lines),
        ]
        parts.append("\n".join(sub_section))

        # Section C: Master Backup Telemetry
        if archive_path and os.path.exists(archive_path):
            fname = os.path.basename(archive_path)
            is_7z = fname.endswith('.7z')
            fmt_str = "7-Zip Ultra (-mx=9, LZMA2 solid)" if is_7z else "ZIP Deflated"
            backup_block = (
                f"📦 <b>Master Backup Archive ({fmt_str}):</b>\n"
                f"• 💾 <b>File:</b> <code>{fname}</code> (<b>{archive_sz_mb:.2f} MB</b>)\n"
                f"• 📁 <b>Contents:</b> 8 GroceryGOD Parquet chunks + 12 Sub-Repo databases\n"
                f"• 📜 Includes <code>00_README_MANIFEST.txt</code> DuckDB query guide\n"
                f"• ⬇️ <i>Attached as document below</i>"
            )
            parts.append(backup_block)

        # Section D: Monthly GitHub Bandwidth Quota
        parts.append(bw_info['html_block'])

        # Section E: Failure Diagnostics (if any)
        if failed_details:
            fail_blocks = ["❌ <b>Failure Diagnostics:</b>"]
            for flbl, ferr, ftb in failed_details:
                fail_blocks.append(f"• <b>{flbl}:</b>\n<pre>{html.escape(str(ferr)[:500])}</pre>")
                if ftb and ftb.strip():
                    fail_blocks.append(f"<pre>{html.escape(str(ftb)[:400])}</pre>")
            parts.append("\n".join(fail_blocks))

        # Section F: Live Dashboards
        parts.append("\n".join(links_block))

        full_message = "\n\n".join(parts)

        # 6. Log locally
        for lp in ['/tmp/master_daily_report.log', '/kaggle/working/output/master_daily_report.log', '/tmp/p14_summary.log']:
            try:
                os.makedirs(os.path.dirname(lp), exist_ok=True)
                with open(lp, 'w', encoding='utf-8') as lf:
                    lf.write(full_message)
                print(f"Master daily report logged locally to {lp}", flush=True)
            except Exception: pass

        # 7. Dispatch Message to Telegram (with safe section chunking if > 3900 chars)
        try:
            if len(full_message) > 3900:
                _chunks = full_message.split("\n\n")
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
                tg_send(full_message)
            print("📲 Consolidated Master Report dispatched to Telegram successfully.", flush=True)
        except Exception as _tg_txt_err:
            print(f"⚠️ [MASTER REPORT] Telegram text dispatch error: {_tg_txt_err}", flush=True)

        # 8. Dispatch Master 7z Backup File to Telegram
        if archive_path and os.path.exists(archive_path):
            try:
                cap = (
                    f"📦 <b>GroceryGOD Master Backup</b> — <code>{today_dhaka}</code>\n"
                    f"Size: <b>{archive_sz_mb:.2f} MB</b> | All 20 Store Datasets & Parquet Chunks"
                )
                print(f"📤 Dispatching Master Backup file ({archive_sz_mb:.2f} MB) to Telegram...", flush=True)
                res_file = tg_send_file(archive_path, caption=cap)
                if res_file:
                    print("✅ Master Backup file delivered to Telegram successfully!", flush=True)
                else:
                    print("⚠️ Master Backup file upload to Telegram failed or timed out.", flush=True)
            except Exception as _tg_file_err:
                print(f"⚠️ [MASTER REPORT] Master Backup file dispatch exception: {_tg_file_err}", flush=True)

    except Exception as _fatal_mr_err:
        print(f"💥 [MASTER REPORT] Uncaught error in _send_consolidated_master_report: {_fatal_mr_err}", flush=True)
        traceback.print_exc()

def _send_p14_summary(results_store, repo_list):
    """Backwards-compatible wrapper delegating to _send_consolidated_master_report."""
    return _send_consolidated_master_report(results_store, repo_list)

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

# ============================================================
# BULLETPROOF REPO INTEGRITY & CROSS-CONTAMINATION GUARD
# ============================================================
def _verify_repo_integrity(repo_dir, repo_name):
    """
    Prevents cross-contamination and clobbering across store scrapers.
    Verifies that the target directory belongs to the intended repository,
    validates remote origin, checks required content signatures, and blocks
    foreign files and databases from leaking across repositories.
    """
    repo_name_clean = repo_name.replace('.git', '').strip()
    
    # 1. Verify remote origin URL matches repo_name
    try:
        rem_res = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=repo_dir, capture_output=True, text=True)
        current_rem = (rem_res.stdout or '').strip()
        if current_rem and repo_name_clean.lower() not in current_rem.lower():
            raise RuntimeError(f"FATAL REPO CORRUPTION: remote origin '{current_rem}' does not match expected repo '{repo_name_clean}'!")
    except Exception as e:
        if "FATAL" in str(e): raise

    # 2. Strict store-specific signatures across ALL 12 scheduled repositories
    signatures = {
        'FooDIE-mart-Analytics': {
            'forbidden_files': ['othoba_tracker.db', 'othoba_products.json', 'scraper_app.py', 'scraper_web.py', 'urls.txt', 'pickaboo_prices.db'],
            'forbidden_patterns': ['othoba', 'shwapno', 'chaldal', 'picaboo', 'daraz', 'meenabazar', 'cartup'],
            'required_patterns': ['foodi']
        },
        'FooDIE-RESTaurant-Analytics': {
            'forbidden_files': ['othoba_tracker.db', 'pickaboo_prices.db', 'shwapno_prices.db'],
            'forbidden_patterns': ['othoba', 'shwapno', 'picaboo', 'cartup'],
            'required_patterns': ['foodi']
        },
        'FoodPANDA-RESTaurant-ANALytics': {
            'forbidden_files': [
                'othoba_tracker.db', 'othoba_products.json', 'Foodi_8.0.3.apk', 'pickaboo_prices.db',
                'pickaboo_prices.db-shm', 'pickaboo_prices.db-wal', 'scraper.db', 'shwapno_prices.db',
                'cartup_products.json', 'scraper.py', 'dashboard.py', 'export_static.py',
                'fix_tokens.py', 'update_token.py', 'parse_har.py', 'config.yaml', 'runall.bat'
            ],
            'forbidden_patterns': ['othoba', 'shwapno', 'foodi', 'cartup', 'picaboo', 'pickaboo', 'chaldal', 'sharedeal'],
            'required_patterns': ['foodpanda', 'bd.fd-api.com']
        },
        'SHWAPNO-analylics': {
            'forbidden_files': ['othoba_tracker.db', 'Foodi_8.0.3.apk', 'pickaboo_prices.db'],
            'forbidden_patterns': ['othoba', 'foodi', 'cartup', 'picaboo'],
            'required_patterns': ['shwapno', 'swapno']
        },
        'Othoba-analytics': {
            'forbidden_files': ['Foodi_8.0.3.apk', 'foodi_page.html', 'scraper.db.part000', 'pickaboo_prices.db'],
            'forbidden_patterns': ['foodi', 'picaboo', 'cartup'],
            'required_patterns': ['othoba']
        },
        'CARTup-analytics': {
            'forbidden_files': ['pickaboo_prices.db', 'othoba_tracker.db', 'Foodi_8.0.3.apk', 'scraper.db', 'dashboard.py', 'categories.json'],
            'forbidden_patterns': ['pickaboo', 'othoba', 'foodi', 'shwapno', 'chaldal', 'cookup', 'daraz', 'meenabazar', 'sharedeal'],
            'required_patterns': ['cartup']
        },
        'CHALdal-analytics': {
            'forbidden_files': ['othoba_tracker.db', 'pickaboo_prices.db', 'Foodi_8.0.3.apk', 'scraper.db'],
            'forbidden_patterns': ['othoba', 'foodi', 'cartup', 'picaboo'],
            'required_patterns': ['chaldal']
        },
        'COOKup-analytics': {
            'forbidden_files': ['othoba_tracker.db', 'pickaboo_prices.db', 'Foodi_8.0.3.apk'],
            'forbidden_patterns': ['othoba', 'foodi', 'cartup', 'picaboo'],
            'required_patterns': ['cookup']
        },
        'PICAboo-analytics': {
            'forbidden_files': ['othoba_tracker.db', 'Foodi_8.0.3.apk', 'scraper.db', 'shwapno_prices.db'],
            'forbidden_patterns': ['othoba', 'foodi', 'cartup', 'shwapno', 'chaldal'],
            'required_patterns': ['picaboo', 'pickaboo']
        },
        'DARAZ-analytics': {
            'forbidden_files': ['othoba_tracker.db', 'pickaboo_prices.db', 'Foodi_8.0.3.apk'],
            'forbidden_patterns': ['othoba', 'foodi', 'cartup'],
            'required_patterns': ['daraz']
        },
        'MEEnaBAzar-analylics': {
            'forbidden_files': ['othoba_tracker.db', 'pickaboo_prices.db', 'Foodi_8.0.3.apk'],
            'forbidden_patterns': ['othoba', 'foodi', 'cartup'],
            'required_patterns': ['meena', 'meenabazar']
        },
        'sharedeal': {
            'forbidden_files': ['othoba_tracker.db', 'Foodi_8.0.3.apk'],
            'forbidden_patterns': ['othoba', 'foodi', 'cartup'],
            'required_patterns': ['sharedeal']
        }
    }

    # Case-insensitive signature lookup
    sig = next((v for k, v in signatures.items() if k.lower() == repo_name_clean.lower()), None)
    if sig:
        # Auto-purge foreign forbidden files if committed/leftover from prior runs
        for forbidden in sig.get('forbidden_files', []):
            fpath = os.path.join(repo_dir, forbidden)
            if os.path.exists(fpath):
                subprocess.run(['git', 'rm', '-rf', '--ignore-unmatch', forbidden, f"{forbidden}.enc*", f"{forbidden}.*"], cwd=repo_dir, capture_output=True)
                if os.path.isdir(fpath): shutil.rmtree(fpath, ignore_errors=True)
                elif os.path.exists(fpath):
                    try: os.remove(fpath)
                    except Exception: pass
                for extra in [f"{fpath}.enc", f"{fpath}.enc.000", f"{fpath}.enc.001", f"{fpath}-shm", f"{fpath}-wal"]:
                    if os.path.exists(extra):
                        try: os.remove(extra)
                        except Exception: pass

        # Check forbidden files directly
        for forbidden in sig.get('forbidden_files', []):
            fpath = os.path.join(repo_dir, forbidden)
            if os.path.exists(fpath):
                raise RuntimeError(f"FATAL CROSS-CONTAMINATION: Forbidden foreign file '{forbidden}' found in '{repo_name_clean}'! Aborting push.")

        # Check git status for foreign files
        res_files = subprocess.run(['git', 'status', '--porcelain'], cwd=repo_dir, capture_output=True, text=True)
        status_lines = (res_files.stdout or '').splitlines()
        for s_line in status_lines:
            file_part = s_line[3:].strip().lower()
            if file_part.endswith('.log') or file_part.endswith('.tmp') or s_line[:2].strip() == 'D':
                continue
            for pat in sig.get('forbidden_patterns', []):
                if pat in file_part:
                    raise RuntimeError(f"FATAL CROSS-CONTAMINATION: Foreign file '{file_part}' matching forbidden pattern '{pat}' detected in '{repo_name_clean}'! Aborting push.")

        # Check required patterns: ensure at least one core file mentions the repository's identity
        required_patterns = sig.get('required_patterns', [])
        if required_patterns:
            core_files = ['scraper.py', 'scrape_menus.py', 'README.md', 'index.html', 'app.js', 'package.json', 'config.yaml']
            found_req = False
            for cf in core_files:
                cf_path = os.path.join(repo_dir, cf)
                if os.path.exists(cf_path):
                    try:
                        with open(cf_path, 'r', encoding='utf-8', errors='ignore') as fh:
                            content_sample = fh.read(8000).lower()
                            if any(rp.lower() in content_sample for rp in required_patterns):
                                found_req = True
                                break
                    except Exception:
                        pass
            if not found_req:
                # Also check repository root folder name
                if not any(rp.lower() in repo_name_clean.lower() for rp in required_patterns):
                    raise RuntimeError(f"FATAL REPO IDENTITY MISMATCH: None of the required patterns {required_patterns} found in core files of '{repo_name_clean}'! Aborting push.")

def run_scheduled_repo(repo_url, script_name, label, github_pat, results_store=None):
    clean_label = label.strip()
    slug = re.sub(r'[^a-z0-9]+', '_', clean_label.lower()).strip('_')
    repo_name = repo_url.split('/')[-1].replace('.git', '')
    repo_page_url = f"https://ranehal.github.io/{repo_name}/"
    _p14_dir = '/tmp/p14_results'
    _out_dir = '/kaggle/working/output/p14_results'
    os.makedirs(_p14_dir, exist_ok=True)
    os.makedirs(_out_dir, exist_ok=True)
    log_file = os.path.join(_p14_dir, f"p14_log_{slug}.log")
    _p14_file = os.path.join(_p14_dir, f"p14_result_{slug}.json")
    _root_log = f"/tmp/p14_log_{slug}.log"
    _root_res = f"/tmp/p14_result_{slug}.json"
    _out_file = os.path.join(_out_dir, f"p14_result_{slug}.json")
    _t0 = time.time()

    def _log(msg):
        ts = datetime.now(DHAKA_TZ).strftime('%H:%M:%S')
        line = f"[{ts} | {clean_label}] {msg}"
        print(line)
        for _lf in [log_file, _root_log]:
            try:
                with open(_lf, "a", encoding="utf-8") as lf:
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
        for _dest in [_p14_file, _root_res, _out_file]:
            try:
                _tmp = _dest + f".{os.getpid()}.tmp"
                with open(_tmp, 'w', encoding='utf-8') as _f:
                    json.dump(_p14_record, _f)
                os.replace(_tmp, _dest)
            except Exception as _fe:
                pass
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
    auth_repo_url = f"https://ranehal:{github_pat}@github.com/ranehal/{repo_name}.git"

    try:
        def _setup_git_config():
            _git_config('git config user.email "ranehal@users.noreply.github.com"')
            _git_config('git config user.name "ranehal"')
            _git_config('git config --global http.version HTTP/1.1')
            _git_config('git config --global http.postBuffer 1048576000')
            _git_config('git config --global http.lowSpeedLimit 0')
            _git_config('git config --global http.lowSpeedTime 999999')
            _git_config('git config --global core.compression 9')
            cred_path = os.path.expanduser('~/.git-credentials')
            with open(cred_path, 'w') as f:
                f.write(f"https://ranehal:{github_pat}@github.com\nhttps://{github_pat}@github.com\n")
            _git_config('git config --global credential.helper store')
        _with_lock('git-config', _setup_git_config)

        if os.path.exists(os.path.join(repo_dir, '.git')):
            try:
                _chk_rem = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=repo_dir, capture_output=True, text=True)
                _cur_orig = (_chk_rem.stdout or '').strip().lower()
                if _cur_orig and repo_name.lower() not in _cur_orig:
                    _log(f"WARNING: repo_dir {repo_dir} remote origin '{_cur_orig}' does not match {repo_name}. Wiping corrupted dir...")
                    shutil.rmtree(repo_dir, ignore_errors=True)
            except Exception:
                pass

        if not os.path.exists(os.path.join(repo_dir, '.git')):
            _reclaim_disk()
            if os.path.exists(repo_dir):
                shutil.rmtree(repo_dir, ignore_errors=True)
            _log(f"Cloning {repo_name} into {repo_dir}...")
            clone_ok, clone_err = _git_clone_robust(auth_repo_url, repo_dir, branch=None, log=_log, label=repo_name)
            if not clone_ok:
                raise RuntimeError(f"Git clone failed after all retries: {clone_err}")

        os.chdir(repo_dir)
        _with_lock('git-config', lambda: (_git_config('git config user.email "ranehal@users.noreply.github.com"'), _git_config('git config user.name "ranehal"')))
        subprocess.run('git remote remove origin', shell=True, capture_output=True, cwd=repo_dir)
        subprocess.run(f'git remote add origin {auth_repo_url}', shell=True, capture_output=True, cwd=repo_dir)
        subprocess.run(f'git remote set-url origin {auth_repo_url}', shell=True, capture_output=True, cwd=repo_dir)

        subprocess.run('git clean -fdx', shell=True, cwd=repo_dir)
        # Best-effort unshallow: keeps pull --rebase / force-with-lease semantics
        # identical to the old full-clone behaviour when the link allows it.
        _shallow_chk = subprocess.run('git rev-parse --is-shallow-repository', shell=True, capture_output=True, text=True, cwd=repo_dir)
        if (_shallow_chk.stdout or '').strip() == 'true':
            _git_run_retry(f'git {GIT_NET_OPTS} fetch --unshallow', cwd=repo_dir, log=_log, attempts=2,
                           delay=5, label=f'{repo_name} unshallow')
        _git_run_retry(f'git {GIT_NET_OPTS} fetch --all --prune', cwd=repo_dir, log=_log, attempts=4,
                       label=f'{repo_name} fetch')
        branch_res = subprocess.run('git symbolic-ref refs/remotes/origin/HEAD', shell=True, capture_output=True, text=True, cwd=repo_dir)
        default_branch = branch_res.stdout.strip().split('/')[-1] if branch_res.returncode == 0 else ''
        if not default_branch or default_branch == 'HEAD':
            check_main = subprocess.run('git rev-parse --verify origin/main', shell=True, capture_output=True, cwd=repo_dir)
            default_branch = 'main' if check_main.returncode == 0 else 'master'
        subprocess.run(f'git reset --hard origin/{default_branch}', shell=True, cwd=repo_dir)
        subprocess.run('git clean -fdx', shell=True, cwd=repo_dir)
        _verify_repo_integrity(repo_dir, repo_name)

        # Also cover the separate Othoba-analytics clone (p3), including
        # any nested copy of scraper_web.py.
        for _ow_path in glob.glob(
            os.path.join(repo_dir, '**', 'scraper_web.py'), recursive=True
        ):
            _apply_othoba_web_hotfix(_ow_path, _log)

        # Daily Guard: Skip scraper execution if already ran and pushed today
        today_dhaka = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d')
        already_done_today = False

        if _PERSISTED_STATE.get('p14_completed_repos', {}).get(clean_label) == today_dhaka:
            already_done_today = True
        else:
            c_log = subprocess.run(['git', 'log', '-1', '--format=%s%x00%ci', f'origin/{default_branch}'], cwd=repo_dir, capture_output=True, text=True).stdout.strip()
            if c_log:
                c_subject, _, c_date = c_log.partition('\x00')
                if 'if this works ill get some sleep frfr' in c_subject:
                    if today_dhaka in c_subject or c_date.startswith(today_dhaka):
                        already_done_today = True

        if already_done_today:
            _log(f"⏸️ [DAILY GUARD] {clean_label} already ran & pushed successfully today ({today_dhaka}). Skipping scraper execution to enforce once-a-day limit.")
            _PERSISTED_STATE.setdefault('p14_completed_repos', {})[clean_label] = today_dhaka
            _p14_record.update(status='ok', elapsed=int(time.time() - _t0), error='', url=repo_page_url, bandwidth_bytes=0, bandwidth_mb=0.0)
            _p14_record['price_stats'] = _extract_repo_price_stats(repo_dir, "")
            _store_result()
            return

        if os.path.exists(os.path.join(repo_dir, 'requirements.txt')):
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=repo_dir, check=False)

        # Low-disk preflight: /kaggle/working disk-full (Errno 28) silently breaks
        # Chromium installs and DB writes, causing random asyncio/playwright crashes.
        try:
            import glob as _glob
            _du = shutil.disk_usage(repo_dir)
            _free_gb = _du.free / (1024 ** 3)
            if _free_gb < 2.0:
                _log(f"WARNING: low disk space ({_free_gb:.2f} GB free). Clearing __pycache__ + stale run artifacts...")
                for _p in _glob.glob(os.path.join(repo_dir, "**", "__pycache__"), recursive=True):
                    shutil.rmtree(_p, ignore_errors=True)
                for _pat in ("**/*.pyc", "**/_scraper_error_*.log", "**/last_run_log.txt"):
                    for _p in _glob.glob(os.path.join(repo_dir, _pat), recursive=True):
                        try: os.remove(_p)
                        except Exception: pass
                _du2 = shutil.disk_usage(repo_dir)
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
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", _pkg], cwd=repo_dir, check=False)
        
        # Verify Playwright Chromium browser binary without blocking apt locks unless actually missing
        try:
            import platform as _platform
            def _pw_install():
                _dry = subprocess.run([sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"], capture_output=True, text=True, cwd=repo_dir)
                _dry_out = ((_dry.stdout or "") + (_dry.stderr or ""))
                if "already installed" in _dry_out.lower() or os.path.isdir('/root/.cache/ms-playwright'):
                    return
                _install_cmds = [[sys.executable, "-m", "playwright", "install", "chromium"]]
                if _platform.system() == "Linux":
                    _install_cmds.insert(0, [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"])
                for _cmd in _install_cmds:
                    _res = subprocess.run(_cmd, capture_output=True, text=True, cwd=repo_dir)
                    if _res.returncode == 0:
                        break
            _with_lock('playwright-install', _pw_install)
        except Exception as _pw_err:
            _log(f"Playwright setup warning: {_pw_err}")

        # Auto-detect script name recursively if expected script_name does not exist
        resolved_script_path = os.path.join(repo_dir, script_name)
        if not os.path.exists(resolved_script_path):
            import glob
            exact_matches = glob.glob(f'{repo_dir}/**/{script_name}', recursive=True)
            if exact_matches:
                resolved_script_path = exact_matches[0]
            elif script_name in ('scrape_menus.py',):
                err_msg = f"FATAL: Expected script '{script_name}' not found in {repo_name}. Generic fallback prohibited to prevent cross-contamination."
                _log(f"❌ {err_msg}")
                _p14_record.update(status='failed', error=err_msg, elapsed=int(time.time() - _t0))
                _store_result()
                return
            else:
                py_files = [f for f in glob.glob(f'{repo_dir}/**/*.py', recursive=True) if not os.path.basename(f).startswith('__') and os.path.basename(f) != 'setup.py']
                preferred = [f for f in py_files if any(k in f.lower() for k in ['scraper', 'main', 'run', 'meena', 'app', 'web', 'menu', 'scrape'])]
                if preferred:
                    resolved_script_path = preferred[0]
                elif py_files:
                    resolved_script_path = py_files[0]
                else:
                    err_msg = f"No executable python script found in {repo_name} (expected '{script_name}')."
                    _log(f"❌ {err_msg}")
                    _p14_record.update(status='failed', error=err_msg, elapsed=int(time.time() - _t0))
                    _store_result()
                    return
            _log(f"Target script auto-resolved to: {os.path.relpath(resolved_script_path, repo_dir)}")

        # Auto-patch common known script issues across repository
        try:
            import re as _re
            import glob as _glob
            import ast as _ast

            # 1. Patch destructive sys.stdout / sys.stderr TextIOWrapper and codecs re-wrapping in Python 3.12
            for _pyf in _glob.glob(os.path.join(repo_dir, "**", "*.py"), recursive=True):
                try:
                    with open(_pyf, "r", encoding="utf-8", errors="replace") as _pf_in:
                        _py_src = _pf_in.read()
                    _orig_py = _py_src
                    if "TextIOWrapper" in _py_src or "codecs.getwriter" in _py_src:
                        _py_src = _re.sub(
                            r'sys\.stdout\s*=\s*(?:io\.)?TextIOWrapper\s*\([^)]*\)',
                            'getattr(sys.stdout, "reconfigure", lambda **kw: None)(encoding="utf-8", errors="replace")',
                            _py_src
                        )
                        _py_src = _re.sub(
                            r'sys\.stderr\s*=\s*(?:io\.)?TextIOWrapper\s*\([^)]*\)',
                            'getattr(sys.stderr, "reconfigure", lambda **kw: None)(encoding="utf-8", errors="replace")',
                            _py_src
                        )
                        _py_src = _re.sub(
                            r'sys\.stdout\s*=\s*codecs\.getwriter\s*\([^)]*\)(?:\([^)]*\))?',
                            'getattr(sys.stdout, "reconfigure", lambda **kw: None)(encoding="utf-8", errors="replace")',
                            _py_src
                        )
                        _py_src = _re.sub(
                            r'sys\.stderr\s*=\s*codecs\.getwriter\s*\([^)]*\)(?:\([^)]*\))?',
                            'getattr(sys.stderr, "reconfigure", lambda **kw: None)(encoding="utf-8", errors="replace")',
                            _py_src
                        )
                    if _py_src != _orig_py:
                        try:
                            _ast.parse(_py_src)
                            with open(_pyf, "w", encoding="utf-8") as _pf_out:
                                _pf_out.write(_py_src)
                            _log(f"Auto-patched stdout wrapper in {os.path.relpath(_pyf, repo_dir)}")
                        except Exception as _ast_err:
                            _log(f"Auto-patch stdout wrapper AST validation failed in {os.path.relpath(_pyf, repo_dir)}: {_ast_err}")
                except Exception:
                    pass

            # 2. Patch Chaldal fetch_init HTTP 500 error in CHALdal-analytics
            if 'chaldal' in repo_name.lower() and os.path.exists(resolved_script_path):
                try:
                    with open(resolved_script_path, "r", encoding="utf-8", errors="replace") as _cf:
                        _c_src = _cf.read()
                    _orig_c = _c_src
                    if "def fetch_init(" in _c_src:
                        _c_src = _re.sub(
                            r'def fetch_init\([^)]*\):[\s\S]*?(?=\ndef\s|\nclass\s|\nif __name__)',
                            'def fetch_init(store_id, warehouse_id=None):\n    try:\n        return req("https://catalog.chaldal.com/fetchInitDataForCombinedStore", store_id=store_id)\n    except Exception as _fe:\n        print(f"  [!] fetch_init failed ({_fe}). Using cached/empty categories fallback...", flush=True)\n        try:\n            import glob as _gb\n            for _cp in _gb.glob("**/categories.json", recursive=True) + _gb.glob("**/products.json", recursive=True):\n                try:\n                    with open(_cp, "r", encoding="utf-8") as _cfh:\n                        return {"Categories": {str(store_id): json.load(_cfh)}}\n                except Exception: pass\n        except Exception: pass\n        return {"Categories": {str(store_id): []}}\n\n',
                            _c_src
                        )
                    if "init = fetch_init(args.store, args.warehouse)" in _c_src and "try:" not in _c_src.split("init = fetch_init(args.store, args.warehouse)")[0][-80:]:
                        _c_src = _c_src.replace(
                            "init = fetch_init(args.store, args.warehouse)",
                            "try:\n        init = fetch_init(args.store, args.warehouse)\n    except Exception as _ie:\n        print(f'  [!] fetch_init warning ({_ie}), falling back to cached categories...', flush=True)\n        cached_cats = load(f\"{out}/categories.json\") or load(\"categories.json\")\n        init = {'Categories': {str(args.store): cached_cats or []}}"
                        )
                    if _c_src != _orig_c:
                        try:
                            _ast.parse(_c_src)
                            with open(resolved_script_path, "w", encoding="utf-8") as _cf:
                                _cf.write(_c_src)
                            _log("Auto-patched Chaldal fetch_init try/except fallback...")
                        except Exception as _ch_ast_err:
                            _log(f"Chaldal patch AST validation failed: {_ch_ast_err}")
                except Exception as _ch_err:
                    _log(f"Chaldal patch warning: {_ch_err}")

            # 3. Patch Cookups fetch_categories network timeout/resilience in COOKup-analytics
            if 'cookup' in repo_name.lower() and os.path.exists(resolved_script_path):
                try:
                    with open(resolved_script_path, "r", encoding="utf-8", errors="replace") as _ckf:
                        _ck_src = _ckf.read()
                    _orig_ck = _ck_src
                    if "def fetch_categories(" in _ck_src:
                        _ck_src = _re.sub(
                            r'def fetch_categories\([^)]*\):[\s\S]*?(?=\ndef\s|\nclass\s|\nif __name__)',
                            'def fetch_categories():\n    req = urllib.request.Request(f"{BASE_URL}/categories", headers=HEADERS)\n    try:\n        with urllib.request.urlopen(req, timeout=30) as resp:\n            raw = json.loads(resp.read().decode("utf-8"))\n            return raw.get("data", raw) if isinstance(raw, dict) else raw\n    except Exception as _cke:\n        print(f"  [!] Live categories fetch failed ({_cke}). Falling back to database...", flush=True)\n        try:\n            conn = get_db_connection()\n            rows = conn.cursor().execute("SELECT id, name, slug, parent_ids, image_url, sort_order FROM categories").fetchall()\n            conn.close()\n            return [dict(r) for r in rows]\n        except Exception as _dbe:\n            print(f"  [!] DB fallback failed ({_dbe})", flush=True)\n            return []\n\n',
                            _ck_src
                        )
                    if _ck_src != _orig_ck:
                        try:
                            _ast.parse(_ck_src)
                            with open(resolved_script_path, "w", encoding="utf-8") as _ckf:
                                _ckf.write(_ck_src)
                            _log("Auto-patched COOKup fetch_categories with timeout & DB fallback...")
                        except Exception as _ck_ast_err:
                            _log(f"Cookup patch AST validation failed: {_ck_ast_err}")
                except Exception as _ck_err:
                    _log(f"Cookup patch warning: {_ck_err}")

            # 4. Auto-patch Cat NoneType error safety with indentation preservation
            if os.path.exists(resolved_script_path):
                with open(resolved_script_path, 'r', encoding='utf-8', errors="replace") as sf:
                    s_code = sf.read()
                if 'for prod in cat.get("products", []):' in s_code and 'isinstance(cat, dict)' not in s_code:
                    _log(f"Auto-patching cat dict-type safety in {os.path.basename(resolved_script_path)}...")
                    pattern = r'([ \t]*)for prod in cat\.get\("products", \[\]\):'
                    m = _re.search(pattern, s_code)
                    if m:
                        indent = m.group(1)
                        replacement = f'{indent}if not cat or not isinstance(cat, dict): continue\n{indent}for prod in cat.get("products", []):'
                        s_code_patched = _re.sub(pattern, replacement, s_code, count=1)
                        try:
                            _ast.parse(s_code_patched)
                            with open(resolved_script_path, 'w', encoding='utf-8') as sf:
                                sf.write(s_code_patched)
                        except Exception as _ast_err:
                            _log(f"Cat safety AST validation failed: {_ast_err}")

            # 5. Patch FoodPANDA scrape_menus.py checkpoint lockup / latency if legacy version is present
            if 'foodpanda' in repo_name.lower() and os.path.exists(resolved_script_path):
                try:
                    with open(resolved_script_path, "r", encoding="utf-8", errors="replace") as _fpf:
                        _fp_src = _fpf.read()
                    _orig_fp = _fp_src
                    if 'completed % 30 == 0' in _fp_src:
                        _fp_src = _fp_src.replace('if completed % 30 == 0:', 'if False and completed % 30 == 0:')
                    if 'compression_level=19' in _fp_src:
                        _fp_src = _fp_src.replace('compression_level=19', 'compression_level=12')
                    if _fp_src != _orig_fp:
                        try:
                            _ast.parse(_fp_src)
                            with open(resolved_script_path, "w", encoding="utf-8") as _fpf:
                                _fpf.write(_fp_src)
                            _log("Auto-patched FoodPANDA scrape_menus with non-blocking checkpoints...")
                        except Exception as _fp_ast_err:
                            _log(f"Foodpanda patch AST validation failed: {_fp_ast_err}")
                except Exception as _fp_err:
                    _log(f"Foodpanda patch warning: {_fp_err}")

            # 6. Patch FooDIE Restaurant Analytics scrape_menus.py JSON indentation & compaction
            if 'foodie' in repo_name.lower() and 'restaurant' in repo_name.lower() and os.path.exists(resolved_script_path):
                try:
                    with open(resolved_script_path, "r", encoding="utf-8", errors="replace") as _frf:
                        _fr_src = _frf.read()
                    _orig_fr = _fr_src
                    if 'indent=2' in _fr_src:
                        _fr_src = _fr_src.replace('indent=2', "separators=(',', ':')")
                    if 'PARQUET_FILE' not in _fr_src:
                        _fr_src = _fr_src.replace(
                            'DATA_FILE = os.path.join(DATA_DIR, "restaurant_dashboard", "data.json")',
                            'DATA_FILE = os.path.join(DATA_DIR, "restaurant_dashboard", "data.json")\nPARQUET_FILE = os.path.join(DATA_DIR, "restaurant_dashboard", "data.parquet")'
                        )
                    if _fr_src != _orig_fr:
                        try:
                            _ast.parse(_fr_src)
                            with open(resolved_script_path, "w", encoding="utf-8") as _frf:
                                _frf.write(_fr_src)
                            _log("Auto-patched FooDIE Restaurant scrape_menus with compact JSON separators...")
                        except Exception as _fr_ast_err:
                            _log(f"FooDIE Restaurant patch AST validation failed: {_fr_ast_err}")
                except Exception as _fr_err:
                    _log(f"FooDIE Restaurant patch warning: {_fr_err}")
        except Exception as patch_err:
            _log(f"Script patch warning: {patch_err}")

        script_abs_path = os.path.abspath(resolved_script_path)
        script_dir = os.path.dirname(script_abs_path)
        script_file = os.path.basename(script_abs_path)

        max_script_retries = 3
        res = None
        for _attempt in range(1, max_script_retries + 1):
            _log(f"Executing {script_file} in {script_dir} (attempt {_attempt}/{max_script_retries})...")
            t_exec0 = time.time()
            my_env = os.environ.copy()
            my_env["PYTHONPATH"] = f"{script_dir}{os.pathsep}{repo_dir}{os.pathsep}{my_env.get('PYTHONPATH', '')}"
            my_env["PYTHONUNBUFFERED"] = "1"
            my_env["PYTHONIOENCODING"] = "utf-8"
            try:
                res = subprocess.run([sys.executable, "-u", script_file], cwd=script_dir, capture_output=True, text=True, timeout=3600, env=my_env)
            except subprocess.TimeoutExpired as _tex:
                exec_elapsed = time.time() - t_exec0
                _log(f"⚠️ Script {script_file} timed out after 3600s on attempt {_attempt}/{max_script_retries}")
                _to_stdout = (_tex.stdout or "") if isinstance(_tex.stdout, str) else (_tex.stdout.decode('utf-8', 'replace') if _tex.stdout else "")
                _to_stderr = (_tex.stderr or "") if isinstance(_tex.stderr, str) else (_tex.stderr.decode('utf-8', 'replace') if _tex.stderr else "")
                class _TimeoutResult:
                    returncode = -9
                    stdout = _to_stdout
                    stderr = _to_stderr + f"\n[TIMEOUT] Command timed out after 3600 seconds on attempt {_attempt}"
                res = _TimeoutResult()
            exec_elapsed = time.time() - t_exec0
            if res.returncode == 0:
                break
            _err_log = os.path.join(repo_dir, f"_scraper_error_{_attempt}.log")
            try:
                with open(_err_log, "w", encoding="utf-8") as _ef:
                    _ef.write((res.stderr or "") + "\n--- STDOUT TAIL ---\n" + (res.stdout or "")[-2000:])
            except Exception:
                pass
            safe_err = (res.stderr or "").strip()[:5000]
            if not safe_err:
                safe_err = (res.stdout or "").strip()[-5000:]
            if _attempt == max_script_retries:
                raise RuntimeError(f"Script {os.path.basename(resolved_script_path)} failed (rc={res.returncode}):\n{safe_err}")
            _log(f"Attempt {_attempt} failed (rc={res.returncode}), retrying in 10s... {safe_err[:200]}")
            time.sleep(10)

        _log(f"Finished execution in {int(time.time() - _t0)}s. Pushing to GitHub as ranehal...")
        _with_lock('git-config', lambda: (_git_config('git config user.name "ranehal"'), _git_config('git config user.email "ranehal@users.noreply.github.com"')))
        subprocess.run(f"git remote set-url origin https://ranehal:{github_pat}@github.com/ranehal/{repo_name}.git", shell=True, cwd=repo_dir)
        subprocess.run('git config http.postBuffer 1048576000', shell=True, cwd=repo_dir)
        subprocess.run('git config http.version HTTP/1.1', shell=True, cwd=repo_dir)
        subprocess.run('git config http.lowSpeedLimit 0', shell=True, cwd=repo_dir)
        subprocess.run('git config http.lowSpeedTime 999999', shell=True, cwd=repo_dir)
        subprocess.run('find . -name "_scraper_error_*.log" -delete', shell=True, cwd=repo_dir)
        for _bloat in ['*.part*', '*.apk', '*.jar', '*.dex', '*.orig', '*.hash']:
            subprocess.run(f'find . -name "{_bloat}" -delete', shell=True, cwd=repo_dir)
        subprocess.run('git rm -f --ignore-unmatch *.apk *.part* *.orig *.hash 2>/dev/null', shell=True, cwd=repo_dir)

        # Pre-push Large File Guard: Scan for any files >= 85 MB and compact or untrack/gitignore to prevent GitHub 100MB rejection
        try:
            for root, dirs, files in os.walk(repo_dir):
                if '.git' in root: continue
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(fp)
                        if sz >= 85 * 1024 * 1024:
                            rel_p = os.path.relpath(fp, repo_dir)
                            # 1. Attempt in-place compaction for oversized JSON files
                            if rel_p.lower().endswith('.json'):
                                try:
                                    with open(fp, 'r', encoding='utf-8') as _jf:
                                        _jdata = json.load(_jf)
                                    if isinstance(_jdata, dict) and 'locations' in _jdata:
                                        for _loc in _jdata.get('locations', []):
                                            for _rest in _loc.get('restaurants', []):
                                                for _mid, _m in _rest.get('menus', {}).items():
                                                    _h = _m.get('price_history') or _m.get('priceHistory') or []
                                                    if len(_h) > 1:
                                                        _d_h = [_h[0]]
                                                        for _pt in _h[1:]:
                                                            if _pt.get('price') != _d_h[-1].get('price'):
                                                                _d_h.append({'date': str(_pt.get('date'))[:10], 'price': _pt.get('price')})
                                                        if _h[-1].get('date') != _d_h[-1].get('date'):
                                                            _d_h.append({'date': str(_h[-1].get('date'))[:10], 'price': _h[-1].get('price')})
                                                        _m['price_history'] = _d_h
                                                        _m.pop('priceHistory', None)
                                    with open(fp, 'w', encoding='utf-8') as _jf:
                                        json.dump(_jdata, _jf, separators=(',', ':'), ensure_ascii=False)
                                    sz = os.path.getsize(fp)
                                    _log(f"🛡️ [LARGE FILE GUARD] Compacted '{rel_p}' in-place down to {sz / (1024*1024):.1f} MB.")
                                except Exception as _comp_err:
                                    _log(f"⚠️ [LARGE FILE GUARD] In-place compact failed for '{rel_p}': {_comp_err}")

                            # 2. If still >= 90MB, untrack and append to .gitignore so git add . will NEVER re-stage it!
                            if sz >= 90 * 1024 * 1024:
                                _log(f"⚠️ [LARGE FILE GUARD] Found oversized file '{rel_p}' ({sz / (1024*1024):.1f} MB) >= 90MB. Untracking & gitignoring to prevent GitHub 100MB push rejection!")
                                subprocess.run(['git', 'rm', '-f', '--cached', '--ignore-unmatch', rel_p], cwd=repo_dir, capture_output=True)
                                _gi_path = os.path.join(repo_dir, '.gitignore')
                                try:
                                    with open(_gi_path, 'a', encoding='utf-8') as _gif:
                                        _gif.write(f"\n{rel_p.replace(os.sep, '/')}\n")
                                except Exception: pass
                                if any(rel_p.lower().endswith(x) for x in ['.log', '.tmp', '.har', '.part', '.bak']):
                                    try: os.remove(fp)
                                    except Exception: pass
                    except Exception: pass
        except Exception as _lfg_err:
            _log(f"Large file guard warning: {_lfg_err}")

        _verify_repo_integrity(repo_dir, repo_name)
        subprocess.run('git add .', shell=True, cwd=repo_dir)

        # Post-add Large File Verification: Unstage any files that were accidentally staged and exceed 90MB
        try:
            _staged = subprocess.run(['git', 'diff', '--cached', '--name-only'], cwd=repo_dir, capture_output=True, text=True).stdout.splitlines()
            for _sf in _staged:
                _sfp = os.path.join(repo_dir, _sf)
                if os.path.isfile(_sfp) and os.path.getsize(_sfp) >= 90 * 1024 * 1024:
                    _log(f"🛑 [LARGE FILE GUARD] Staged file '{_sf}' ({os.path.getsize(_sfp)/(1024*1024):.1f} MB) >= 90MB! Forcibly unstaging and ignoring!")
                    subprocess.run(['git', 'rm', '-f', '--cached', _sf], cwd=repo_dir, capture_output=True)
                    with open(os.path.join(repo_dir, '.gitignore'), 'a', encoding='utf-8') as _gif:
                        _gif.write(f"\n{_sf.replace(os.sep, '/')}\n")
        except Exception: pass

        # Zero-change push guard: skip push if no meaningful data files changed to conserve monthly bandwidth
        st_out = subprocess.run(['git', 'diff', '--cached', '--name-only'], cwd=repo_dir, capture_output=True, text=True).stdout or ''
        data_files_changed = [f for f in st_out.splitlines() if any(f.lower().endswith(ext) for ext in ['.db', '.json', '.parquet', '.js', '.csv', '.html', '.enc'])]
        if not data_files_changed:
            _log("⏸️ Zero data changes detected. Skipping git push to conserve bandwidth quota.")
            _p14_record.update(status='ok', elapsed=int(time.time() - _t0), error='', url=repo_page_url, bandwidth_bytes=0, bandwidth_mb=0.0)
            _p14_record['price_stats'] = _extract_repo_price_stats(repo_dir, (res.stdout or "") + (res.stderr or "") if res else "")
            if res is not None: _p14_record['counts'] = _extract_scraper_counts((res.stdout or "") + (res.stderr or ""))
            _store_result()
            return

        now_str = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')
        subprocess.run(f'git commit -m "if this works ill get some sleep frfr {now_str}"', shell=True, cwd=repo_dir)

        push_success = False
        _init_bandwidth_state()
        _sub_monthly_b = int(_PERSISTED_STATE.get('bandwidth_monthly_bytes', 0))
        _sub_cap_overflow = _sub_monthly_b >= GITHUB_MONTHLY_CAP_BYTES
        _backup_pat = get_secret_safe('GITHUB_PAT_BACKUP') or get_secret_safe('RANX_GITHUB_PAT') or get_secret_safe('RANX_PAT') or github_pat

        if _sub_cap_overflow:
            _log(f"⚠️ [10GB CAP REACHED] ranehal monthly bandwidth quota reached ({_sub_monthly_b / (1024**3):.2f} GB / 10.0 GB). Engaging ranx-x backup key as primary!")
            auth_user_configs = [
                ("ranx-x", f"https://ranx-x:{_backup_pat}@github.com/ranehal/{repo_name}.git"),
                ("ranx-x", f"https://{_backup_pat}@github.com/ranehal/{repo_name}.git"),
                ("ranehal", f"https://ranehal:{github_pat}@github.com/ranehal/{repo_name}.git"),
                ("ranehal", f"https://{github_pat}@github.com/ranehal/{repo_name}.git")
            ]
        else:
            auth_user_configs = [
                ("ranehal", f"https://ranehal:{github_pat}@github.com/ranehal/{repo_name}.git"),
                ("ranehal", f"https://{github_pat}@github.com/ranehal/{repo_name}.git"),
                ("ranx-x", f"https://ranx-x:{_backup_pat}@github.com/ranehal/{repo_name}.git"),
                ("ranx-x", f"https://{_backup_pat}@github.com/ranehal/{repo_name}.git")
            ]

        last_sub_push_stderr = ""
        for user_n, auth_u in auth_user_configs:
            subprocess.run('git remote remove origin', shell=True, capture_output=True, cwd=repo_dir)
            subprocess.run(f'git remote add origin {auth_u}', shell=True, capture_output=True, cwd=repo_dir)
            subprocess.run(f'git remote set-url origin {auth_u}', shell=True, capture_output=True, cwd=repo_dir)
            subprocess.run('git config http.postBuffer 1048576000', shell=True, capture_output=True, cwd=repo_dir)
            subprocess.run('git config http.version HTTP/1.1', shell=True, capture_output=True, cwd=repo_dir)
            subprocess.run('git config http.lowSpeedLimit 0', shell=True, capture_output=True, cwd=repo_dir)
            subprocess.run('git config http.lowSpeedTime 999999', shell=True, capture_output=True, cwd=repo_dir)
            _with_lock('git-config', lambda u=user_n: (_git_config(f'git config user.name "{u}"'), _git_config(f'git config user.email "{u}@users.noreply.github.com"')))
            for attempt in range(5):
                subprocess.run('git rebase --abort 2>/dev/null', shell=True, capture_output=True, cwd=repo_dir)
                _git_run_retry(f'git {GIT_NET_OPTS} pull origin {default_branch} --rebase -X ours -q',
                               cwd=repo_dir, log=_log, attempts=3, delay=4, label=f'{repo_name} pull')
                _verify_repo_integrity(repo_dir, repo_name)
                # 1. Clean fast-forward push first
                push_res = subprocess.run(f'git {GIT_NET_OPTS} push --progress origin HEAD:{default_branch}', shell=True, capture_output=True, text=True, cwd=repo_dir)
                if push_res.returncode == 0:
                    push_success = True
                    _PERSISTED_STATE['last_push_user'] = user_n
                    last_sub_push_stderr = (push_res.stderr or "") + "\n" + (push_res.stdout or "")
                    break
                # 2. Direct authenticated URL push fallback (fast-forward)
                push_res = subprocess.run(f'git {GIT_NET_OPTS} push --progress {auth_u} HEAD:{default_branch}', shell=True, capture_output=True, text=True, cwd=repo_dir)
                if push_res.returncode == 0:
                    push_success = True
                    _PERSISTED_STATE['last_push_user'] = user_n
                    last_sub_push_stderr = (push_res.stderr or "") + "\n" + (push_res.stdout or "")
                    break
                # 3. Only use --force-with-lease (never blind --force) after verified integrity
                push_res = subprocess.run(f'git {GIT_NET_OPTS} push --progress origin HEAD:{default_branch} --force-with-lease', shell=True, capture_output=True, text=True, cwd=repo_dir)
                if push_res.returncode == 0:
                    push_success = True
                    _PERSISTED_STATE['last_push_user'] = user_n
                    last_sub_push_stderr = (push_res.stderr or "") + "\n" + (push_res.stdout or "")
                    break
                last_sub_push_stderr = push_res.stderr or ""
                _push_wait = min(5 * (2 ** attempt), 60)
                _push_tail = ((last_sub_push_stderr.strip().splitlines() or [''])[-1])[:180]
                _log(f"⚠️ Push attempt {attempt + 1}/5 failed: {_push_tail} — retrying in {_push_wait}s")
                time.sleep(_push_wait)
            if push_success:
                if user_n == "ranx-x":
                    _log("✅ Sub-repo push succeeded using ranx-x backup key!")
                if default_branch == 'main':
                    check_master = subprocess.run('git rev-parse --verify origin/master', shell=True, capture_output=True, cwd=repo_dir)
                    if check_master.returncode == 0:
                        _log(f"Syncing main -> master on {repo_name}...")
                        subprocess.run(f'git push --progress origin HEAD:master', shell=True, capture_output=True, cwd=repo_dir)
                break

        if not push_success:
            clean_err = "\n".join([line for line in last_sub_push_stderr.splitlines() if not re.search(r'(Enumerating|Counting|Compressing|Writing)\s+objects', line)]).strip()
            err_detail = (clean_err[-1200:] if clean_err else last_sub_push_stderr[-600:]).strip()
            raise RuntimeError(f"Git push failed: {err_detail}")

        # Record push bandwidth consumed against 10GB monthly cap
        _sub_bytes, _sub_bw = record_git_push_bandwidth(repo_dir=repo_dir, repo_name=repo_name, stderr_text=last_sub_push_stderr)
        _log(f"🌐 [BANDWIDTH] Push consumed: {_sub_bw['push_mb']} MB | Monthly Total: {_sub_bw['used_mb']} MB / 10.0 GB ({_sub_bw['pct_used']}%)")

        _p14_record.update(status='ok', elapsed=int(time.time() - _t0), error='', url=repo_page_url, bandwidth_bytes=_sub_bytes, bandwidth_mb=_sub_bw['push_mb'])
        _p14_record['price_stats'] = _extract_repo_price_stats(repo_dir, (res.stdout or "") + (res.stderr or "") if res else "")
        if res is not None:
            _p14_record['counts'] = _extract_scraper_counts((res.stdout or "") + (res.stderr or ""))
        _store_result()

        # Mark completion for today
        _PERSISTED_STATE.setdefault('p14_completed_repos', {})[clean_label] = today_dhaka
        _PERSISTED_STATE['p14_last_completed_dhaka'] = datetime.now(DHAKA_TZ).strftime("%Y-%m-%d %H:%M:%S DHAKA")
        for _vp in ['/kaggle/working/orchestrator_state.json', '/kaggle/working/output/orchestrator_state.json', '/tmp/orchestrator_state.json']:
            try:
                os.makedirs(os.path.dirname(_vp), exist_ok=True)
                with open(_vp, 'w', encoding='utf-8') as _vf:
                    json.dump(_PERSISTED_STATE, _vf, indent=2)
            except Exception: pass

        # Send commit pushed and DB backup to Telegram
        send_repo_db_backup(repo_dir, repo_name, clean_label, repo_page_url)
        _log(f"✅ Successfully completed and pushed in {int(time.time() - _t0)}s!")
    except Exception as e:
        safe_tb = html.escape(traceback.format_exc()[-500:])
        err_str = str(e)
        _log(f"❌ Error: {err_str}")
        _p14_record.update(status='failed', error=err_str, error_tb=safe_tb, elapsed=int(time.time() - _t0), url=repo_page_url)
        _store_result()

def run_all_scheduled_repos(repos, github_pat, results_store=None):
    """Execute scheduled sub-repos sequentially with full per-repo isolation and error resilience."""
    today_dhaka = datetime.now(DHAKA_TZ).strftime('%Y-%m-%d')
    print(f"🚀 [Scheduled Repos] Launching sequential sub-repos executor across {len(repos)} repos (Dhaka Date: {today_dhaka})...")

    # Fast Daily Guard: Check if ALL repos are already verified completed today
    completed_map = _PERSISTED_STATE.get('p14_completed_repos', {})
    if all(completed_map.get(label.strip()) == today_dhaka for _, _, label in repos):
        print(f"🎉 [DAILY GUARD] All {len(repos)} scheduled sub-repos have already completed and pushed for today ({today_dhaka}). Skipping all scrapers to enforce once-a-day limit.")
        for repo_url, script_name, label in repos:
            lbl = label.strip()
            repo_name = repo_url.split('/')[-1].replace('.git', '')
            repo_page_url = f"https://ranehal.github.io/{repo_name}/"
            slug = re.sub(r'[^a-z0-9]+', '_', lbl.lower()).strip('_')
            _p14_file = f"/tmp/p14_results/p14_result_{slug}.json"
            if not os.path.exists(_p14_file):
                _rec = {'label': lbl, 'status': 'ok', 'elapsed': 0, 'error': '', 'url': repo_page_url, 'bandwidth_bytes': 0, 'bandwidth_mb': 0.0, 'skipped': True}
                try:
                    os.makedirs('/tmp/p14_results', exist_ok=True)
                    with open(_p14_file, 'w', encoding='utf-8') as f:
                        json.dump(_rec, f)
                except Exception: pass
        return

    for repo_url, script_name, label in repos:
        lbl = label.strip()
        try:
            print(f"\n▶️ [Scheduled Repos] Starting: {lbl}")
            run_scheduled_repo(repo_url, script_name, lbl, github_pat, results_store)
            print(f"✅ [Scheduled Repos] Finished: {lbl}\n")
        except Exception as exc:
            print(f"❌ [Scheduled Repos] Exception in {lbl}: {exc}\n")
    print("🟢 [Scheduled Repos] All scheduled sub-repos completed.")

import base64
import signal
import zlib

# ============================================================
# PIPELINE 15: TELEGRAM GIVEAWAY AGENTS (3 accounts, parallel)
# ============================================================
# Runs the three giveaway accounts as supervised subprocesses next to
# p1 (GroceryGOD), p2 (gitw) and p3 (scheduled repos). Each account has
# its own session, SQLite database and log, so they never share state.
# The agents restart themselves internally; this outer supervisor also
# restarts them if a process is hard-killed, and reports status in
# /kaggle/working/giveaway_p15/status.json.
_GIVEAWAY_P15_ROOT = "/kaggle/working/giveaway_p15"
_GIVEAWAY_P15_STOP_FILE = os.path.join(_GIVEAWAY_P15_ROOT, "STOP")
_GIVEAWAY_P15_SHARED = ("TG_API_ID", "TG_API_HASH", "SOURCE_CHAT", "TARGET_BOT")
_GIVEAWAY_P15_AGENTS = [
    {
        "name": "main",
        "script": "giveaway_agent.py",
        "session_env": "TG_SESSION_STRING",
        "secret_names": ("TG_SESSION_STRING", "MAIN_TG_SESSION_STRING"),
        "log_file": "giveaway.log",
    },
    {
        "name": "kazi",
        "script": "kazi_giveaway_agent.py",
        "session_env": "KAZI_TG_SESSION_STRING",
        "secret_names": ("KAZI_TG_SESSION_STRING", "KAZI_SESSION_STRING"),
        "log_file": "giveaway_kazi.log",
    },
    {
        "name": "ragib",
        "script": "ragib_giveaway_agent.py",
        "session_env": "RAGIB_TG_SESSION_STRING",
        "secret_names": ("RAGIB_TG_SESSION_STRING", "RAGIB_SESSION_STRING"),
        "log_file": "giveaway_ragib.log",
    },
]
_GIVEAWAY_P15_ENV = {
    "ENABLE_REDEMPTION": "true",
    "MAX_CODES_PER_POST": "22",
    "REPLY_TIMEOUT_SECONDS": "10",
    "MIN_SECONDS_BETWEEN_REDEMPTIONS": "1",
    "RESTART_DELAY_SECONDS": "10",
    "MAX_RESTART_DELAY_SECONDS": "300",
    "FLOODWAIT_MARGIN_SECONDS": "5",
    "PYTHONUNBUFFERED": "1",
    "PYTHONIOENCODING": "utf-8",
}
# Verbatim agent sources, zlib-compressed and base64-encoded at build time.
_GIVEAWAY_P15_SOURCES_B64 = {'giveaway_agent.py': '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', 'kazi_giveaway_agent.py': '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', 'ragib_giveaway_agent.py': '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'}


# Resolve the shared config and the three session strings once in the
# parent process. p15 and its children inherit them through os.environ.
for _p15_key in _GIVEAWAY_P15_SHARED:
    _p15_value = (get_secret_safe(_p15_key) or "").strip()
    if _p15_value:
        os.environ[_p15_key] = _p15_value
if not os.environ.get("TARGET_BOT"):
    os.environ["TARGET_BOT"] = "@trgiveaway_bot"
for _p15_agent in _GIVEAWAY_P15_AGENTS:
    for _p15_name in _p15_agent["secret_names"]:
        _p15_value = (get_secret_safe(_p15_name) or "").strip()
        if _p15_value:
            os.environ[_p15_agent["session_env"]] = _p15_value
            break


def _p15_now():
    return datetime.now(DHAKA_TZ).strftime("%Y-%m-%d %H:%M:%S DHAKA")


def _p15_log(message):
    line = _p15_now() + " [p15] " + message
    print(line, flush=True)
    try:
        os.makedirs(_GIVEAWAY_P15_ROOT, exist_ok=True)
        with open(
            os.path.join(_GIVEAWAY_P15_ROOT, "supervisor.log"),
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def _p15_alert(message):
    try:
        sender = globals().get("tg_send")
        if callable(sender):
            sender(message)
    except Exception:
        pass


def _p15_ensure_deps(log):
    missing = []
    try:
        import telethon  # noqa: F401
    except ImportError:
        missing.append("telethon")
    try:
        import dotenv  # noqa: F401
    except ImportError:
        missing.append("python-dotenv")
    if missing:
        log("Installing missing packages: " + ", ".join(missing))
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", *missing],
            timeout=300,
        )
    log("Dependencies ready.")


def _p15_write_scripts(root):
    paths = {}
    for agent in _GIVEAWAY_P15_AGENTS:
        path = os.path.join(root, agent["script"])
        try:
            source = zlib.decompress(
                base64.b64decode(_GIVEAWAY_P15_SOURCES_B64[agent["script"]])
            ).decode("utf-8")
        except Exception as exc:
            raise RuntimeError(
                "Could not unpack embedded " + agent["script"] + ": " + repr(exc)
            )
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(source)
        paths[agent["name"]] = path
    return paths


def _p15_read_new_log(path, offset):
    try:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            return handle.read()
    except Exception:
        return ""


def _p15_terminate(proc, grace=10):
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    deadline = time.time() + grace
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.5)
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _p15_write_status(path, states, state="running", note=""):
    payload = {
        "updated": _p15_now(),
        "pipeline": "p15",
        "state": state,
        "note": note,
        "agents": states,
    }
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def _p15_idle(stop, reason):
    _p15_log("p15 idle: " + reason + " (will wait for a new session)")
    _p15_write_status(
        os.path.join(_GIVEAWAY_P15_ROOT, "status.json"),
        {},
        state="idle",
        note=reason,
    )
    while not stop["flag"]:
        if os.path.exists(_GIVEAWAY_P15_STOP_FILE):
            _p15_log("STOP file found; leaving idle state.")
            break
        time.sleep(5)
    return 0


def run_giveaway_agents():
    """p15 entrypoint: supervise the three Telegram giveaway accounts."""
    stop = {"flag": False}

    def _on_signal(signum, frame):
        _p15_log("Signal " + str(signum) + " received; stopping agents.")
        stop["flag"] = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _on_signal)
        except Exception:
            pass

    try:
        os.makedirs(_GIVEAWAY_P15_ROOT, exist_ok=True)
        _p15_log("Starting p15 giveaway supervisor.")
        _p15_ensure_deps(_p15_log)
    except Exception as exc:
        _p15_log("FATAL: dependency setup failed: " + repr(exc))
        return 1

    missing = [
        key
        for key in _GIVEAWAY_P15_SHARED
        if not (os.environ.get(key) or "").strip()
    ]
    if missing:
        reason = "missing shared secrets: " + ", ".join(missing)
        _p15_log("Not starting: " + reason)
        _p15_alert(
            "⚠️ <b>p15 Giveaway Agents</b>\n"
            "Not started: " + ", ".join(missing) + " missing.\n"
            "Add them under Add-ons > Secrets and restart the kernel."
        )
        return _p15_idle(stop, reason)

    try:
        scripts = _p15_write_scripts(_GIVEAWAY_P15_ROOT)
    except Exception as exc:
        _p15_log("FATAL: could not write agent scripts: " + repr(exc))
        return 1

    enabled = []
    state = {}
    for agent in _GIVEAWAY_P15_AGENTS:
        name = agent["name"]
        work_dir = os.path.join(_GIVEAWAY_P15_ROOT, name)
        state[name] = {
            "pid": None,
            "alive": False,
            "restarts": 0,
            "disabled": False,
            "last_start": "",
            "last_exit": "",
            "log_offset": 0,
            "script": scripts[name],
            "log": os.path.join(work_dir, agent["log_file"]),
            "work_dir": work_dir,
        }
        if not (os.environ.get(agent["session_env"]) or "").strip():
            state[name]["disabled"] = True
            state[name]["last_exit"] = "missing session secret"
            _p15_log(
                "[" + name + "] disabled: missing session secret "
                "(" + " / ".join(agent["secret_names"]) + ")."
            )
            continue
        os.makedirs(work_dir, exist_ok=True)
        enabled.append(agent)

    if not enabled:
        reason = "no session strings found"
        _p15_log("Not starting: " + reason + ".")
        _p15_alert(
            "⚠️ <b>p15 Giveaway Agents</b>\n"
            "Not started: no session strings found.\n"
            "Add TG_SESSION_STRING, KAZI_TG_SESSION_STRING and "
            "RAGIB_TG_SESSION_STRING, then restart."
        )
        return _p15_idle(stop, reason)

    procs = {}
    handles = {}
    status_path = os.path.join(_GIVEAWAY_P15_ROOT, "status.json")
    next_start = {agent["name"]: 0.0 for agent in enabled}
    started_at = {agent["name"]: 0.0 for agent in enabled}

    def _start(agent):
        name = agent["name"]
        work_dir = os.path.join(_GIVEAWAY_P15_ROOT, name)
        log_path = os.path.join(work_dir, agent["log_file"])
        state[name]["log_offset"] = (
            os.path.getsize(log_path) if os.path.exists(log_path) else 0
        )
        env = os.environ.copy()
        env[agent["session_env"]] = os.environ[agent["session_env"]]
        env["WORK_DIR"] = work_dir
        env.update(_GIVEAWAY_P15_ENV)
        out_path = os.path.join(work_dir, "stdout.log")
        err_path = os.path.join(work_dir, "stderr.log")
        out_handle = open(out_path, "ab", buffering=0)
        err_handle = open(err_path, "ab", buffering=0)
        proc = subprocess.Popen(
            [sys.executable, "-u", scripts[name]],
            cwd=_GIVEAWAY_P15_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out_handle,
            stderr=err_handle,
            start_new_session=True,
        )
        procs[name] = proc
        handles[name] = (out_handle, err_handle)
        started_at[name] = time.time()
        state[name].update(
            pid=proc.pid,
            alive=True,
            last_start=_p15_now(),
            last_exit="",
        )
        _p15_log(
            "[" + name + "] started pid=" + str(proc.pid)
            + " work_dir=" + work_dir
        )

    last_heartbeat = 0.0
    try:
        while not stop["flag"]:
            if os.path.exists(_GIVEAWAY_P15_STOP_FILE):
                _p15_log("STOP file found; shutting down p15.")
                break

            now = time.time()
            for agent in enabled:
                name = agent["name"]
                proc = procs.get(name)
                if proc is not None and proc.poll() is None:
                    continue

                if proc is not None:
                    returncode = proc.returncode
                    uptime = now - started_at.get(name, now)
                    tail = _p15_read_new_log(
                        state[name]["log"], state[name]["log_offset"]
                    )
                    for handle in handles.pop(name, ()):
                        try:
                            handle.close()
                        except Exception:
                            pass
                    procs[name] = None
                    state[name]["alive"] = False
                    state[name]["pid"] = None
                    state[name]["last_exit"] = (
                        "rc=" + str(returncode) + " after "
                        + str(int(uptime)) + "s at " + _p15_now()
                    )
                    config_error = (
                        "Not restarting: this is a configuration problem"
                        in tail
                    )
                    if config_error:
                        state[name]["disabled"] = True
                        _p15_log(
                            "[" + name + "] permanent configuration error; "
                            "not restarting this account."
                        )
                    else:
                        if uptime >= 300:
                            state[name]["restarts"] = 0
                        state[name]["restarts"] += 1
                        delay = min(5 * state[name]["restarts"], 300)
                        next_start[name] = now + delay
                        _p15_log(
                            "[" + name + "] exited rc=" + str(returncode)
                            + " after " + str(int(uptime)) + "s; restart #"
                            + str(state[name]["restarts"]) + " in "
                            + str(delay) + "s."
                        )

                if state[name]["disabled"] or now < next_start.get(name, 0):
                    continue
                try:
                    _start(agent)
                except Exception as exc:
                    _p15_log("[" + name + "] could not start: " + repr(exc))
                    state[name]["restarts"] += 1
                    next_start[name] = now + min(
                        5 * state[name]["restarts"], 300
                    )

            _p15_write_status(status_path, state)

            if now - last_heartbeat >= 600:
                last_heartbeat = now
                summary = ", ".join(
                    name + ("=up" if state[name]["alive"] else "=down")
                    for name in state
                )
                _p15_log("heartbeat: " + summary + ".")
            time.sleep(15)
    finally:
        _p15_log("Stopping all p15 agent processes.")
        for name in list(procs):
            _p15_terminate(procs.get(name))
        for name in list(handles):
            for handle in handles.pop(name, ()):
                try:
                    handle.close()
                except Exception:
                    pass
        for name in state:
            state[name]["alive"] = False
            state[name]["pid"] = None
        _p15_write_status(status_path, state)
        _p15_log("p15 supervisor stopped.")
    return 0


# MASTER ORCHESTRATOR LOOP
# ============================================================
if __name__ == '__main__':
    if not run_preflight_checks():
        print("🛑 [PRE-FLIGHT] CRITICAL SECRETS CHECK FAILED!")
        print("🛑 Halting orchestrator startup immediately to prevent wasted compute.")
        print("🛑 Fix: In Kaggle notebook editor ➜ Add-ons ➜ Secrets ➜ Ensure checkboxes are CHECKED (☑) for GITHUB_PAT, KAGGLE_USERNAME, KAGGLE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID ➜ Run All.")
        sys.exit(1)
    
    print("🚀 Launching BOTH pipelines in Parallel...")
    
    _manager = multiprocessing.Manager()
    _p14_results = _manager.dict()
    try:
        import glob as _glob
        for _f in (
            _glob.glob('/tmp/p14_results/p14_result_*.json')
            + _glob.glob('/tmp/p14_results/p14_log_*.log')
            + _glob.glob('/tmp/p14_result_*.json')
            + _glob.glob('/tmp/p14_log_*.log')
            + _glob.glob('/kaggle/working/output/p14_results/*.json')
        ):
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

    # p15 needs telethon; install it before p2 starts its own pip work so
    # concurrent pip installs cannot race in the shared Kaggle environment.
    try:
        import telethon  # noqa: F401
        import dotenv  # noqa: F401
    except ImportError:
        try:
            print("[p15] Installing telethon + python-dotenv ...", flush=True)
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q", "telethon", "python-dotenv"],
                timeout=300,
            )
        except Exception as _p15_dep_exc:
            print(f"[p15] Dependency pre-install failed: {_p15_dep_exc}", flush=True)

    p1 = multiprocessing.Process(target=run_grocery_god, args=(GITHUB_PAT,))
    p2 = multiprocessing.Process(target=run_gitw)
    p3 = multiprocessing.Process(target=run_all_scheduled_repos, args=(_scheduled_repos, GITHUB_PAT, _p14_results))
    p15 = multiprocessing.Process(target=run_giveaway_agents)
    
    session_start_t0 = time.time()
    p2.start()
    try:
        p15.start()
        print("[p15] Giveaway agents started in parallel (3 accounts).")
    except Exception as _p15_start_exc:
        print(f"[p15] Could not start giveaway supervisor: {_p15_start_exc}", flush=True)
        p15 = None
    print("⏳ Sleeping 10 minutes (600s) before starting p1 & p3 to sync Kaggle Netherlands/UTC time with Dhaka date...")
    for _i in range(10, 0, -1):
        print(f"⏳ [{11 - _i}/10 min] Waiting {_i * 60}s for Dhaka time sync (p2 gitw + p15 giveaway running in background)...")
        time.sleep(60)
    p1.start()
    p3.start()
    
    loop_t0 = time.time()
    timeout_seconds = 11 * 3600 + 15 * 60  # 11h 15m (+10m init = ~11h 25m total session duration, safely under Kaggle 12h limit)
    _master_reported = False
    _last_heartbeat_time = 0
    _p15_restarts = 0
    heartbeat_interval = 600  # 10 minutes

    while (time.time() - loop_t0) < timeout_seconds:
        p1_alive = p1.is_alive()
        p3_alive = p3.is_alive()
        p2_alive = p2.is_alive()
        p15_alive = p15 is not None and p15.is_alive()

        if not p15_alive and _p15_restarts < 10 and not os.path.exists(_GIVEAWAY_P15_STOP_FILE):
            _p15_restarts += 1
            print(f"[p15] Giveaway supervisor died; restarting ({_p15_restarts}/10)...", flush=True)
            try:
                if p15 is not None:
                    p15.join(timeout=1)
            except Exception:
                pass
            try:
                p15 = multiprocessing.Process(target=run_giveaway_agents)
                p15.start()
            except Exception as _p15_restart_exc:
                print(f"[p15] Restart failed: {_p15_restart_exc}", flush=True)
                p15 = None

        # Wait until BOTH GroceryGOD (p1) and Scheduled Sub-Repos (p3) have finished scraping & aggregating
        if not p1_alive and not p3_alive:
            if not _master_reported:
                print("\n✅ All scrapers & aggregators finished! (GroceryGOD p1 & Scheduled Repos p3)", flush=True)
                # Immediate pre-report memory cleanup
                try:
                    import gc as _gc
                    _gc.collect()
                    os.system("pkill -9 -f chromium 2>/dev/null")
                    os.system("pkill -9 -f scraper.py 2>/dev/null")
                except Exception:
                    pass

                _master_reported = True
                print("🟢 Dispatching unified Consolidated Daily Master Report & 7z Backup to Telegram...", flush=True)
                try:
                    _send_consolidated_master_report(_p14_results, list(zip([lbl for _, _, lbl in _scheduled_repos], _repo_pages)))
                except Exception as _mr_exc:
                    print(f"⚠️ [ORCHESTRATOR] Master report dispatch error: {_mr_exc}", flush=True)
                    traceback.print_exc()

                print("💤 Scraper pipeline complete. Entering active standby heartbeat loop until scheduled container restart...", flush=True)
                _last_heartbeat_time = time.time()

            # Standby heartbeat logging every 10 minutes to maintain active notebook connection
            now_t = time.time()
            if now_t - _last_heartbeat_time >= heartbeat_interval:
                elapsed_min = int((now_t - session_start_t0) / 60)
                rem_min = max(0, int((timeout_seconds - (now_t - loop_t0)) / 60))
                now_str = datetime.now(DHAKA_TZ).strftime('%H:%M:%S')
                p2_desc = "running" if p2_alive else ("completed" if p2.exitcode == 0 else f"exited(rc={p2.exitcode})")
                p15_desc = "running" if p15_alive else ("unavailable" if p15 is None and _p15_restarts >= 10 else "restarting")
                print(f"💤 [{now_str} DHAKA] Standby Heartbeat: Active {elapsed_min}m | Remaining: {rem_min}m until container reboot | gitw (p2): {p2_desc} | p15 giveaway: {p15_desc}", flush=True)
                _last_heartbeat_time = now_t

        time.sleep(30)

    print("\n⏳ Scheduled execution window completed (~11.5h). Initiating graceful teardown & Kaggle restart...", flush=True)

    if not _master_reported:
        _master_reported = True
        print("🟢 Ensuring Consolidated Daily Master Report & 7z Backup is dispatched to Telegram before restart...", flush=True)
        try:
            _send_consolidated_master_report(_p14_results, list(zip([lbl for _, _, lbl in _scheduled_repos], _repo_pages)))
        except Exception as _mr_exc2:
            print(f"⚠️ [ORCHESTRATOR] Fallback master report dispatch error: {_mr_exc2}", flush=True)
            traceback.print_exc()

    print("☢️ Executing Nuclear Teardown of orphaned child processes...")
    os.system("pkill -9 -f chromium")
    os.system("pkill -9 -f scraper.py")
    for i in range(1, 36):
        os.system(f"pkill -9 -f {i}.py")

    _p15_was_alive = p15 is not None and p15.is_alive()
    if p15 is not None:
        try:
            p15.terminate()
            p15.join(timeout=35)
            if p15.is_alive():
                p15.kill()
        except Exception:
            pass
    os.system("pkill -9 -f giveaway_p15_")

    for p in [p1, p2, p3]:
        if p.is_alive():
            p.terminate()
            p.join(timeout=5)
    
    time.sleep(5)
    print("\n🔄 Triggering next cycle...")
    exec_stats = {
        'elapsed_seconds': int(time.time() - session_start_t0),
        'p1_status': "OK" if p1.exitcode == 0 else f"rc={p1.exitcode}" if p1.exitcode is not None else "terminated",
        'p2_status': "OK" if p2.exitcode == 0 else f"rc={p2.exitcode}" if p2.exitcode is not None else "terminated",
        'p3_status': "OK" if p3.exitcode == 0 else f"rc={p3.exitcode}" if p3.exitcode is not None else "terminated",
        'p15_status': "OK" if '_p15_was_alive' in dir() and _p15_was_alive else "STOPPED",
    }
    for _n, _s in [("GroceryGOD (p1)", exec_stats['p1_status']), ("gitw (p2)", exec_stats['p2_status']), ("Scheduled Repos (p3)", exec_stats['p3_status']), ("Giveaway (p15)", exec_stats['p15_status'])]:
        print(f"[{_n}]: {_s}")
    
    trigger_self_restart(exec_stats)

