"""Decrypt premium/history_archive.parquet.enc into history_archive.parquet (readable)."""
import os, sys, hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import pyarrow.parquet as pq

BASE = os.path.dirname(os.path.abspath(__file__))
ENC_PATH = os.path.join(BASE, 'premium', 'history_archive.parquet.enc')
OUT_PATH = os.path.join(BASE, 'history_archive.parquet')

key = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('GOD_PREMIUM_KEY', '')

if not key:
    print("ERROR: No key provided. Pass key as argument or set GOD_PREMIUM_KEY env var.")
    sys.exit(1)

with open(ENC_PATH, 'rb') as f:
    data = f.read()

magic = data[:4]
if magic != b'GGE1':
    print(f"ERROR: Bad magic bytes: {magic} (expected GGE1)")
    sys.exit(1)

salt = data[4:20]
iv = data[20:32]
ciphertext = data[32:]

kdf = hashlib.pbkdf2_hmac('sha256', key.encode('utf-8'), salt, 250000, dklen=32)
aesgcm = AESGCM(kdf)
plaintext = aesgcm.decrypt(iv, ciphertext, None)

with open(OUT_PATH, 'wb') as f:
    f.write(plaintext)

table = pq.read_table(OUT_PATH)
print(f"Decrypted: {OUT_PATH} ({len(plaintext)/1024/1024:.1f} MB, {table.num_rows} rows)")
