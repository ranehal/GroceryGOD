"""Decrypt all .enc files in the repo back to plaintext for pipeline use."""
import os, glob, hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

BASE = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get('GOD_PREMIUM_KEY', 'assalamualaikum').strip()
ITERATIONS = 250000

def decrypt(data, passphrase):
    if data[:4] != b'GGE1':
        raise ValueError('Bad magic bytes')
    salt, iv, ct = data[4:20], data[20:32], data[32:]
    key = hashlib.pbkdf2_hmac('sha256', passphrase.encode(), salt, ITERATIONS, dklen=32)
    return AESGCM(key).decrypt(iv, ct, None)

enc_files = glob.glob(os.path.join(BASE, '**', '*.enc'), recursive=True)

print(f"[DECRYPT] Found {len(enc_files)} encrypted files")
decrypted = 0
for enc_path in enc_files:
    try:
        with open(enc_path, 'rb') as f:
            data = f.read()
        plain = decrypt(data, KEY)
        out_path = enc_path[:-4]  # strip .enc
        with open(out_path, 'wb') as f:
            f.write(plain)
        os.remove(enc_path)
        decrypted += 1
        rel = os.path.relpath(enc_path, BASE)
        print(f"  {rel} -> {rel[:-4]} ({len(plain)/1024:.0f}KB)")
    except Exception as e:
        print(f"  ERROR {enc_path}: {e}")

print(f"[DECRYPT] Done: {decrypted}/{len(enc_files)} files decrypted")
