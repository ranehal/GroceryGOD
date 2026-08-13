"""
Build a continuous, gap-free history: for each store, take the full calendar
date range (store min..max) and forward-fill every product's price so the graph
has a point on every day. No backward fill (products start at first_seen).
"""
import os, io, hashlib
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

BASE = os.path.dirname(os.path.abspath(__file__))
PREMIUM_KEY = os.environ.get('GOD_PREMIUM_KEY', 'assalamualaikum').strip()

df = pq.read_table(os.path.join(BASE, 'history.parquet')).to_pandas()
print('input rows:', len(df))
df['store'] = df['product_id'].str.split('_').str[0]

out = []
report_rows = []
for store in sorted(df['store'].unique()):
    sdf = df[df['store'] == store].copy()
    smin, smax = sdf['date'].min(), sdf['date'].max()
    all_dates = pd.date_range(smin, smax, freq='D').strftime('%Y-%m-%d')
    prods = sdf['product_id'].unique()
    n_expected = len(all_dates) * len(prods)
    # original coverage: distinct (product,date) present
    n_orig = len(sdf)
    grid = pd.DataFrame({'date': all_dates.repeat(len(prods))})
    grid['product_id'] = list(prods) * len(all_dates)
    merged = grid.merge(sdf[['product_id', 'date', 'price', 'normalized_price']],
                        on=['product_id', 'date'], how='left')
    merged.sort_values(['product_id', 'date'], inplace=True)
    merged['price'] = merged.groupby('product_id')['price'].ffill()
    merged['normalized_price'] = merged.groupby('product_id')['normalized_price'].ffill()
    merged.dropna(subset=['price', 'normalized_price'], inplace=True)
    out.append(merged[['product_id', 'date', 'price', 'normalized_price']])
    n_filled = len(merged)
    report_rows.append((store, smin, smax, len(all_dates), len(prods), n_orig, n_expected, n_filled))
    print(f"{store:<6} {smin}..{smax} dates={len(all_dates):>3} prods={len(prods):>6} "
          f"orig={n_orig:>10,} filled={n_filled:>12,}")

final = pd.concat(out, ignore_index=True)
print('\nfinal rows:', len(final))
print('any NaN:', final[['price', 'normalized_price']].isna().any().any())

schema = pa.schema([
    ('product_id', pa.string()),
    ('date', pa.string()),
    ('price', pa.float64()),
    ('normalized_price', pa.float64()),
])
table = pa.Table.from_pandas(final, schema=schema, preserve_index=False)
pq.write_table(table, os.path.join(BASE, 'history.parquet'), compression='zstd')
pq.write_table(table, os.path.join(BASE, 'history_free.parquet'), compression='zstd')

buf = pa.BufferOutputStream()
pq.write_table(table, buf, compression='zstd')
plaintext = buf.getvalue().to_pybytes()
salt, iv = os.urandom(16), os.urandom(12)
kdf = hashlib.pbkdf2_hmac('sha256', PREMIUM_KEY.encode(), salt, 250000, dklen=32)
ct = AESGCM(kdf).encrypt(iv, plaintext, None)
with open(os.path.join(BASE, 'history.parquet.enc'), 'wb') as f:
    f.write(b'GGE1' + salt + iv + ct)
print('wrote history.parquet/.enc')

# save per-store report
with open(os.path.join(BASE, 'gap_report.txt'), 'w') as f:
    f.write("store first_date last_date num_dates num_products orig_points expected_points(cartesian) filled_points\n")
    for r in report_rows:
        f.write(' '.join(str(x) for x in r) + '\n')
print('wrote gap_report.txt')