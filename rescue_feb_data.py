"""
Rescue all historical data from February, March, April 2026 git commits and merge into history.parquet & history_free.parquet.
"""
import subprocess
import json
import os
import pyarrow as pa
import pyarrow.parquet as pq

BASE = os.path.dirname(os.path.abspath(__file__))

print("[RESCUE] Scanning git commit history for Feb/Mar/Apr 2026 datasets...")

proc = subprocess.run(['git', 'log', '--format=%H %cd', '--date=short'], capture_output=True, text=True)
commits = proc.stdout.strip().split('\n')

feb_mar_commits = [c.split(' ')[0] for c in commits if any(m in c.split(' ')[1] for m in ['2026-02', '2026-03', '2026-04'])]

print(f"[RESCUE] Found {len(feb_mar_commits)} commits in Feb/Mar/Apr 2026.")

existing_history = []
if os.path.exists(os.path.join(BASE, 'history.parquet')):
    table = pq.read_table(os.path.join(BASE, 'history.parquet'))
    existing_history = table.to_pylist()

seen = set((r['product_id'], r['date']) for r in existing_history)
rescued_count = 0

for idx, sha in enumerate(feb_mar_commits, 1):
    print(f"  [{idx}/{len(feb_mar_commits)}] Inspecting commit {sha[:7]}...")
    p = subprocess.run(['git', 'show', f'{sha}:data.json'], capture_output=True)
    if p.returncode == 0:
        try:
            raw = p.stdout.decode('utf-8', errors='ignore')
            obj = json.loads(raw)
            prods = obj.get('products', obj) if isinstance(obj, dict) else {}
            if isinstance(prods, dict):
                for pid, pdata in prods.items():
                    if isinstance(pdata, dict):
                        prefix = ""
                        store = pdata.get('store', '')
                        if store == 'shwapno' and not pid.startswith('sh_'): prefix = 'sh_'
                        elif store == 'chaldal' and not pid.startswith('ch_'): prefix = 'ch_'
                        elif store == 'meenabazar' and not pid.startswith('mb_'): prefix = 'mb_'
                        elif store == 'othoba' and not pid.startswith('ot_'): prefix = 'ot_'
                        
                        full_pid = prefix + pid
                        
                        for h in pdata.get('history', []):
                            if isinstance(h, dict) and 'date' in h:
                                d = h['date'][:10]
                                price = float(h.get('price', 0) or 0)
                                norm_price = float(h.get('normalized_price', price) or price)
                                if (full_pid, d) not in seen:
                                    seen.add((full_pid, d))
                                    existing_history.append({
                                        'product_id': full_pid,
                                        'date': d,
                                        'price': price,
                                        'normalized_price': norm_price
                                    })
                                    rescued_count += 1
        except Exception as e:
            pass

print(f"\n[RESCUE] Successfully rescued {rescued_count} new historical rows from Feb/Mar/Apr 2026!")
print(f"[RESCUE] Total combined history rows: {len(existing_history)}")

schema = pa.schema([
    ('product_id', pa.string()),
    ('date', pa.string()),
    ('price', pa.float64()),
    ('normalized_price', pa.float64()),
])

hist_table = pa.Table.from_pylist(existing_history, schema=schema)
pq.write_table(hist_table, os.path.join(BASE, 'history.parquet'), compression='zstd')
pq.write_table(hist_table, os.path.join(BASE, 'history_free.parquet'), compression='zstd')

h_size = os.path.getsize(os.path.join(BASE, 'history.parquet'))
print(f"[RESCUE] Updated history.parquet: {len(existing_history):,} rows ({h_size/1024/1024:.2f} MB)")
