"""Encrypt all sensitive repo files (JS data, JSON, DB, scraper .py) with GGE1 before git push."""
import os, glob, hashlib, secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

BASE = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get('GOD_PREMIUM_KEY', 'assalamualaikum').strip()
ITERATIONS = 250000

def encrypt(plaintext, passphrase):
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac('sha256', passphrase.encode(), salt, ITERATIONS, dklen=32)
    ct = AESGCM(key).encrypt(iv, plaintext, None)
    return b'GGE1' + salt + iv + ct

# --- Targets ---
targets = []

# JS data chunks + manifests (all stores)
for pattern in ['*_data_part*.js', '*_manifest.js']:
    targets.extend(glob.glob(os.path.join(BASE, pattern)))

# Raw data files
targets.append(os.path.join(BASE, 'PRICETRACKER', 'data.js'))
targets.append(os.path.join(BASE, 'swapnoTRACKER', 'data.json'))
targets.append(os.path.join(BASE, 'unimartTRACKER', 'data.json'))
targets.append(os.path.join(BASE, 'ShotejTRACKER', 'data.json'))
targets.append(os.path.join(BASE, 'data.json'))
targets.append(os.path.join(BASE, 'data.js'))

# Scraper scripts
for d in ['swapnoTRACKER', 'PRICETRACKER', 'MEENAtracker/backend', 'othobaTRACKER/backend',
          'metroTRACKER/backend', 'unimartTRACKER', 'ShotejTRACKER']:
    p = os.path.join(BASE, d, 'scraper.py')
    if os.path.exists(p):
        targets.append(p)

# SQLite databases
for pattern in ['**/*.db']:
    targets.extend(glob.glob(os.path.join(BASE, pattern), recursive=True))

# Full parquet datasets (free variants stay plain — frontend needs them)
targets.append(os.path.join(BASE, 'products.parquet'))
targets.append(os.path.join(BASE, 'history.parquet'))

# Premium archive (already encrypted, skip re-encrypt)
targets = [t for t in targets if os.path.exists(t) and not t.endswith('.enc')
           and 'history_archive.parquet.enc' not in t]

print(f"[ENCRYPT] Found {len(targets)} files to encrypt")
encrypted = 0
for path in targets:
    try:
        with open(path, 'rb') as f:
            data = f.read()
        enc = encrypt(data, KEY)
        enc_path = path + '.enc'
        with open(enc_path, 'wb') as f:
            f.write(enc)
        os.remove(path)
        encrypted += 1
        rel = os.path.relpath(path, BASE)
        print(f"  {rel} -> {rel}.enc ({len(enc)/1024:.0f}KB)")
    except Exception as e:
        print(f"  ERROR {path}: {e}")

print(f"[ENCRYPT] Done: {encrypted}/{len(targets)} files encrypted")
