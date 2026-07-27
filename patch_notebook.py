"""Patch gitgod.ipynb to inline decrypt/encrypt logic instead of subprocess calls."""
import json, os

NB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gitgod.ipynb')

with open(NB_PATH, 'r', encoding='utf-8') as f:
    nb = json.load(f)

cell = nb['cells'][1]
old_source = cell['source']
new_source = []
i = 0
while i < len(old_source):
    line = old_source[i]

    # --- PATCH DECRYPT ---
    if 'subprocess.run([sys.executable, \'decrypt_repo.py\']' in line:
        print(f'  Patching decrypt subprocess call at line {i}')
        new_source.extend([
            "                    import re as _re, glob as _glob, hashlib as _hashlib\n",
            "                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM\n",
            "                    _KEY = os.environ.get('GOD_PREMIUM_KEY', '').strip()\n",
            "                    if not _KEY: raise RuntimeError('GOD_PREMIUM_KEY not set')\n",
            "                    _ITER = 250000\n",
            "                    def _dec(data, pw):\n",
            "                        if data[:4] != b'GGE1': raise ValueError('Bad magic')\n",
            "                        s, iv, ct = data[4:20], data[20:32], data[32:]\n",
            "                        k = _hashlib.pbkdf2_hmac('sha256', pw.encode(), s, _ITER, dklen=32)\n",
            "                        return AESGCM(k).decrypt(iv, ct, None)\n",
            "                    _cwd = os.getcwd()\n",
            "                    _chunks = _glob.glob(os.path.join(_cwd, '**', '*.enc.[0-9][0-9][0-9]'), recursive=True)\n",
            "                    _groups = {}\n",
            "                    for cf in _chunks:\n",
            "                        m = _re.match(r'(.+)\\.enc\\.([0-9]{3})$', cf)\n",
            "                        if m: _groups.setdefault(m.group(1)+'.enc', []).append(cf)\n",
            "                    for base, parts in _groups.items():\n",
            "                        parts.sort()\n",
            "                        log.info(f'  Reassembling {len(parts)} chunks -> {os.path.basename(base)}')\n",
            "                        with open(base, 'wb') as out:\n",
            "                            for p in parts:\n",
            "                                with open(p, 'rb') as f: out.write(f.read())\n",
            "                                os.remove(p)\n",
            "                        os.remove(base)\n",
            "                    _enc_files = _glob.glob(os.path.join(_cwd, '**', '*.enc'), recursive=True)\n",
            "                    log.info(f'  Found {len(_enc_files)} encrypted files')\n",
            "                    _dc = 0\n",
            "                    for ep in _enc_files:\n",
            "                        try:\n",
            "                            with open(ep, 'rb') as f: d = f.read()\n",
            "                            plain = _dec(d, _KEY)\n",
            "                            with open(ep[:-4], 'wb') as f: f.write(plain)\n",
            "                            os.remove(ep)\n",
            "                            _dc += 1\n",
            "                            log.info(f'  {os.path.relpath(ep, _cwd)} -> decrypted ({len(plain)//1024}KB)')\n",
            "                        except Exception as ex:\n",
            "                            log.error(f'  ERROR {os.path.basename(ep)}: {ex}')\n",
            "                    log.info(f'  Decrypted {_dc}/{len(_enc_files)} files')\n",
        ])
        i += 1
        continue

    # --- PATCH ENCRYPT ---
    if 'subprocess.run([sys.executable, \'encrypt_repo.py\']' in line:
        print(f'  Patching encrypt subprocess call at line {i}')
        new_source.extend([
            "                    import glob as _glob, secrets as _secrets, hashlib as _hashlib\n",
            "                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM\n",
            "                    _KEY = os.environ.get('GOD_PREMIUM_KEY', '').strip()\n",
            "                    if not _KEY: raise RuntimeError('GOD_PREMIUM_KEY not set')\n",
            "                    _ITER = 250000\n",
            "                    _SPLIT = 40 * 1024 * 1024\n",
            "                    def _enc(data, pw):\n",
            "                        salt, iv = _secrets.token_bytes(16), _secrets.token_bytes(12)\n",
            "                        k = _hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, _ITER, dklen=32)\n",
            "                        ct = AESGCM(k).encrypt(iv, data, None)\n",
            "                        return b'GGE1' + salt + iv + ct\n",
            "                    def _write_enc(path, data):\n",
            "                        if len(data) <= _SPLIT:\n",
            "                            with open(path, 'wb') as f: f.write(data)\n",
            "                            return [path]\n",
            "                        if os.path.exists(path): os.remove(path)\n",
            "                        cp = []\n",
            "                        for i in range(0, len(data), _SPLIT):\n",
            "                            idx = i // _SPLIT\n",
            "                            cp.append(f'{path}.{idx:03d}')\n",
            "                            with open(cp[-1], 'wb') as f: f.write(data[i:i+_SPLIT])\n",
            "                        return cp\n",
            "                    _cwd = os.getcwd()\n",
            "                    _targets = []\n",
            "                    for pat in ['*_data_part*.js', '*_manifest.js']:\n",
            "                        _targets.extend(_glob.glob(os.path.join(_cwd, pat)))\n",
            "                    for tf in ['PRICETRACKER/data.js', 'swapnoTRACKER/data.json', 'unimartTRACKER/data.json', 'ShotejTRACKER/data.json', 'data.json', 'data.js']:\n",
            "                        p = os.path.join(_cwd, tf)\n",
            "                        if os.path.exists(p): _targets.append(p)\n",
            "                    for d in ['swapnoTRACKER', 'PRICETRACKER', 'MEENAtracker/backend', 'othobaTRACKER/backend', 'metroTRACKER/backend', 'unimartTRACKER', 'ShotejTRACKER']:\n",
            "                        p = os.path.join(_cwd, d, 'scraper.py')\n",
            "                        if os.path.exists(p): _targets.append(p)\n",
            "                    for dbf in _glob.glob(os.path.join(_cwd, '**', '*.db'), recursive=True):\n",
            "                        _targets.append(dbf)\n",
            "                    for pq in ['products.parquet', 'history.parquet']:\n",
            "                        p = os.path.join(_cwd, pq)\n",
            "                        if os.path.exists(p): _targets.append(p)\n",
            "                    pa = os.path.join(_cwd, 'premium', 'history_archive.parquet')\n",
            "                    if os.path.exists(pa): _targets.append(pa)\n",
            "                    _targets = [t for t in _targets if os.path.exists(t) and not t.endswith('.enc')]\n",
            "                    log.info(f'  Encrypting {len(_targets)} files')\n",
            "                    _ec = 0\n",
            "                    for tp in _targets:\n",
            "                        try:\n",
            "                            with open(tp, 'rb') as f: data = f.read()\n",
            "                            ed = _enc(data, _KEY)\n",
            "                            ep = tp + '.enc'\n",
            "                            for old in _glob.glob(ep + '.*'): os.remove(old)\n",
            "                            cps = _write_enc(ep, ed)\n",
            "                            _ec += 1\n",
            "                            rel = os.path.relpath(tp, _cwd)\n",
            "                            if len(cps) == 1:\n",
            "                                log.info(f'  {rel} -> .enc ({len(ed)//1024}KB)')\n",
            "                            else:\n",
            "                                log.info(f'  {rel} -> .enc ({len(ed)//1024}KB, {len(cps)} chunks)')\n",
            "                            os.remove(tp)\n",
            "                        except Exception as ex:\n",
            "                            log.error(f'  ERROR {os.path.basename(tp)}: {ex}')\n",
            "                    log.info(f'  Encrypted {_ec}/{len(_targets)} files')\n",
        ])
        i += 1
        continue

    # --- PATCH SCRAPER RUNNER TIMEOUT & ERROR HANDLING ---
    if "res = subprocess.run([sys.executable, 'scraper.py']" in line and "except subprocess.TimeoutExpired" not in "".join(old_source[max(0, i-2):min(len(old_source), i+3)]):
        print(f'  Patching scraper runner at line {i}')
        new_source.extend([
            "                my_env = os.environ.copy()\n",
            "                try:\n",
            "                    res = subprocess.run([sys.executable, 'scraper.py'], cwd=full_path, capture_output=True, text=True, timeout=1800, env=my_env)\n",
            "                except subprocess.TimeoutExpired:\n",
            "                    elapsed = time.time() - t0\n",
            "                    log.error(f\"🚨 {label} TIMED OUT after {_fmt_dur(elapsed)}!\")\n",
            "                    tg_send(f'❌ <b>{label}</b> TIMED OUT after {_fmt_dur(elapsed)}!', silent=True)\n",
            "                    return label, False\n",
            "                except Exception as run_err:\n",
            "                    elapsed = time.time() - t0\n",
            "                    log.error(f\"🚨 {label} EXCEPTION: {run_err}\")\n",
            "                    tg_send(f'❌ <b>{label}</b> FAILED after {_fmt_dur(elapsed)}!\\n<pre>{html.escape(str(run_err))}</pre>', silent=True)\n",
            "                    return label, False\n",
            "                elapsed = time.time() - t0\n",
        ])
        if i + 1 < len(old_source) and "elapsed = time.time() - t0" in old_source[i+1]:
            i += 1
        i += 1
        continue

    # Fix CalledProcessError handler: e.stderr[:500] -> str(e)[:500]
    if 'CalledProcessError as e' in line:
        new_source.append(line.replace('e.stderr[:500]', 'str(e)[:500]'))
        i += 1
        continue

    new_source.append(line)
    i += 1

cell['source'] = new_source

with open(NB_PATH, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print('Done: notebook patched successfully')
