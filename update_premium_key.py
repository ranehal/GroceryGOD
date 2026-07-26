"""Re-encrypt premium history_archive.parquet.enc with a new passphrase."""
import os, sys, hashlib, secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

BASE = os.path.dirname(os.path.abspath(__file__))
ENC_PATH = os.path.join(BASE, 'premium', 'history_archive.parquet.enc')

def decrypt(data, passphrase):
    if data[:4] != b'GGE1': raise ValueError('Bad magic')
    salt, iv, ct = data[4:20], data[20:32], data[32:]
    key = hashlib.pbkdf2_hmac('sha256', passphrase.encode(), salt, 250000, dklen=32)
    return AESGCM(key).decrypt(iv, ct, None)

def encrypt(plaintext, passphrase):
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac('sha256', passphrase.encode(), salt, 250000, dklen=32)
    return b'GGE1' + salt + iv + AESGCM(key).encrypt(iv, plaintext, None)

if len(sys.argv) < 3:
    print("Usage: python update_premium_key.py <old_key> <new_key>")
    sys.exit(1)

old_key, new_key = sys.argv[1], sys.argv[2]

if not os.path.exists(ENC_PATH):
    print(f"ERROR: {ENC_PATH} not found.")
    sys.exit(1)

with open(ENC_PATH, 'rb') as f:
    enc_data = f.read()

print(f"Decrypting with old key ({len(enc_data)} bytes)...")
plain = decrypt(enc_data, old_key)
print(f"Re-encrypting with new key ({len(plain)} bytes plaintext)...")
new_enc = encrypt(plain, new_key)

with open(ENC_PATH, 'wb') as f:
    f.write(new_enc)

print(f"DONE. Updated {ENC_PATH} ({len(new_enc)} bytes)")
