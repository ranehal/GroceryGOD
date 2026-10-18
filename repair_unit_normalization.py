"""Recompute per-unit normalized prices across the already-committed datasets.

Why this exists
---------------
Pack-count product names were multiplied even without a multiplication sign, so
"Golden Harvest Chicken Spring Roll 14Pcs 300gm" was normalized as
14 x 300gm = 4.2 kg and advertised "59.5 Tk/kg" instead of the real
250 Tk / 0.3 kg = 833.33 Tk/kg. The parsers (aggregator.py, swapnoTRACKER/*) are
fixed; this one-off script rewrites the datasets that are already in the repo so
the live dashboard stops serving the old numbers before the next Kaggle cycle
regenerates everything.

The repair is surgical: a row is rewritten only when the fixed parser disagrees
with the frozen pre-fix parser (that is, the bug actually applies to that name).
Merely stale-but-unrelated values are left alone.

What it rewrites (in place)
---------------------------
* products_free.parquet / products.parquet   -> unit_type, normalized_price,
                                                min/max/avg_price
* atl.parquet / atl_preview.json             -> same fields + sparkline series
* history_free.parquet, history.parquet,
  history_<store>.parquet,
  premium/history_archive.parquet            -> normalized_price per row
* swapnoTRACKER/data.json                    -> unit, unit_type, normalized_price
* products.parquet.enc, premium/history_archive.parquet.enc.*,
  swapnoTRACKER/data.json.enc                -> deterministic AES-GCM re-encrypt

Usage
-----
    python repair_unit_normalization.py --dry-run   # report only
    python repair_unit_normalization.py             # rewrite everything
"""
import glob
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aggregator as agg

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
DRY_RUN = '--dry-run' in sys.argv

import duckdb

PREMIUM_KEY = os.environ.get('GOD_PREMIUM_KEY', 'assalamualaikum').strip()
STORES = ['chaldal', 'foodi', 'meenabazar', 'metromart', 'othoba', 'shotejbazar', 'shwapno', 'unimart']

PRODUCT_FILES = ['products_free.parquet', 'products.parquet']
HISTORY_FILES = ['history_free.parquet', 'history.parquet', 'premium/history_archive.parquet'] + \
                [f'history_{s}.parquet' for s in STORES]

_con = duckdb.connect()

# Stores whose aggregator loader calls the parser with the name only.
NAME_ONLY_STORES = {'shwapno', 'othoba'}


# --- frozen pre-fix parser (aggregator.py before the pack-count fix) ---------
# Kept verbatim so this script can tell exactly which rows the bug touched.
def _legacy_parse_unit_and_calculate(name, unit_str, price):
    if price is None:
        price = 0.0
    price = float(price)
    if price <= 0:
        return 'piece', price

    name_clean = agg.clean_tolerance(name or "").lower()
    unit_clean = agg.clean_tolerance(unit_str or "").lower()
    full_text = f"{unit_clean} {name_clean}".strip()

    multiplier, extra_free_weight_gm, extra_free_volume_ml = agg.parse_promotion(full_text)

    for t_src in [name_clean, unit_clean]:
        m1 = re.search(r'(\d+(\.\d+)?)\s*(kg|gm|gram|g|ml|ltr|l)\s*[xX*]\s*(\d+)', t_src)
        if m1:
            val, unit, count = float(m1.group(1)), m1.group(3), float(m1.group(4))
            total_val = val * count * multiplier
            if unit in ['gm', 'gram', 'g']:
                total_gm = total_val + extra_free_weight_gm
                return 'kg', (price / total_gm) * 1000 if total_gm > 0 else price
            if unit == 'kg':
                total_kg = total_val + (extra_free_weight_gm / 1000.0)
                return 'kg', price / total_kg if total_kg > 0 else price
            if unit == 'ml':
                total_ml = total_val + extra_free_volume_ml
                return 'liter', (price / total_ml) * 1000 if total_ml > 0 else price
            total_l = total_val + (extra_free_volume_ml / 1000.0)
            return 'liter', price / total_l if total_l > 0 else price

        m2 = re.search(r'(\d+)\s*(?:p|pcs?|packs?|x|\*)\s*[xX*]?\s*(\d+(\.\d+)?)\s*(kg|gm|gram|g|ml|ltr|l)\b', t_src)
        if m2:
            count, val, unit = float(m2.group(1)), float(m2.group(2)), m2.group(4)
            total_val = val * count * multiplier
            if unit in ['gm', 'gram', 'g']:
                total_gm = total_val + extra_free_weight_gm
                return 'kg', (price / total_gm) * 1000 if total_gm > 0 else price
            if unit == 'kg':
                total_kg = total_val + (extra_free_weight_gm / 1000.0)
                return 'kg', price / total_kg if total_kg > 0 else price
            if unit == 'ml':
                total_ml = total_val + extra_free_volume_ml
                return 'liter', (price / total_ml) * 1000 if total_ml > 0 else price
            total_l = total_val + (extra_free_volume_ml / 1000.0)
            return 'liter', price / total_l if total_l > 0 else price

    for t_src in [name_clean, unit_clean]:
        wm = re.search(r'(\d+(\.\d+)?)\s*(kg|gm|gram|g)\b', t_src)
        if wm:
            val, unit = float(wm.group(1)), wm.group(3)
            if val > 0:
                if unit in ['gm', 'gram', 'g']:
                    total_gm = (val * multiplier) + extra_free_weight_gm
                    return 'kg', (price / total_gm) * 1000 if total_gm > 0 else price
                total_kg = (val * multiplier) + (extra_free_weight_gm / 1000.0)
                return 'kg', (price / total_kg) if total_kg > 0 else price

        vm = re.search(r'(\d+(\.\d+)?)\s*(ltr|liter|l|ml)\b', t_src)
        if vm:
            val, unit = float(vm.group(1)), vm.group(3)
            if val > 0:
                if unit == 'ml':
                    total_ml = (val * multiplier) + extra_free_volume_ml
                    return 'liter', (price / total_ml) * 1000 if total_ml > 0 else price
                total_l = (val * multiplier) + (extra_free_volume_ml / 1000.0)
                return 'liter', (price / total_l) if total_l > 0 else price

    for t_src in [name_clean, unit_clean]:
        pm = re.search(r'(\d+)\s*(?:pcs|pc|piece|pieces|pads|pad|hali|dozen|can|bottle|box|pkt|pack|sachet)\b', t_src)
        if pm:
            pcs = float(pm.group(1))
            if pcs > 0:
                total_pcs = pcs * multiplier
                return 'piece', price / total_pcs if total_pcs > 0 else price

    if multiplier > 1:
        return 'piece', price / multiplier

    if any(x in full_text for x in ['pc', 'piece', 'hali', 'dozen', 'pkt', 'pack', 'each', 'bottle', 'can', 'box', 'bar', 'hanger', 'sachet']):
        return 'piece', price

    return 'kg', price


# --- frozen pre-fix Shwapno scraper unit parser ------------------------------
def _legacy_normalize_unit(name, current_price_str):
    name_lower = name.lower()
    qty_disp = "1 Piece"
    unit_type = "pc"
    norm_price = float(current_price_str)

    match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|gm|liter|ltr|l|ml|piece|pc|pcs|pack|pk)', name_lower)
    if match:
        val = float(match.group(1))
        u = match.group(2)
        if u in ['kg']:
            unit_type = "kg"
            norm_price = norm_price / val
        elif u in ['g', 'gm']:
            unit_type = "kg"
            norm_price = (norm_price / val) * 1000
        elif u in ['liter', 'ltr', 'l']:
            unit_type = "L"
            norm_price = norm_price / val
        elif u in ['ml']:
            unit_type = "L"
            norm_price = (norm_price / val) * 1000
        else:
            norm_price = norm_price / val
    return qty_disp, round(norm_price, 2), unit_type


# --- helpers ----------------------------------------------------------------
_factor_cache = {}


def unit_input(store, unit):
    return '' if store in NAME_ONLY_STORES else str(unit or '')


def norm_factor(name, store, unit):
    """Normalized price per 1 taka (the parser is linear in price), or None."""
    key = (name, store, unit_input(store, unit))
    if key not in _factor_cache:
        _, norm = agg.parse_unit_and_calculate(name, key[2], 1.0)
        _factor_cache[key] = norm if norm > 0 else None
    return _factor_cache[key]


def correction(name, store, unit, price, stored_norm, stored_type):
    """(new_norm, new_type, ratio) for one product row; ratio is None when unaffected."""
    price = float(price or 0)
    stored_norm = float(stored_norm or 0)
    if price <= 0:
        return stored_norm, stored_type, None
    u = unit_input(store, unit)
    old_type, old_norm = _legacy_parse_unit_and_calculate(name, u, price)
    new_type, new_norm = agg.parse_unit_and_calculate(name, u, price)
    if old_type == new_type and abs(old_norm - new_norm) <= 0.005:
        return stored_norm, stored_type, None
    ratio = (new_norm / old_norm) if (old_norm > 0 and new_norm > 0) else None
    return round(new_norm, 6), new_type, ratio


def read_parquet(path):
    return _con.execute(f"SELECT * FROM read_parquet('{path}')").df()


def write_parquet(df, path):
    if DRY_RUN:
        return
    tmp = path + '.tmp.parquet'
    _con.register('_rep', df)
    _con.execute(f"COPY _rep TO '{tmp}' (FORMAT PARQUET, COMPRESSION 'ZSTD')")
    _con.unregister('_rep')
    os.replace(tmp, path)


def affected_products():
    """id -> (factor, unit_type) for every product the parser fix changes."""
    out = {}
    for f in reversed(PRODUCT_FILES):
        if not os.path.exists(f):
            continue
        df = read_parquet(f)
        for pid, name, store, unit, price, norm, u_type in zip(
                df['id'], df['name'], df['store'], df['unit'],
                df['current_price'], df['normalized_price'], df['unit_type']):
            new_norm, new_type, ratio = correction(name, store, unit, price, norm, u_type)
            if ratio is not None or new_type != u_type:
                out[pid] = (norm_factor(name, store, unit), new_type)
    return out


def history_aggregates():
    """min/max/avg per-unit price per product, exactly like convert_to_parquet."""
    rows = _con.execute("""
        SELECT product_id,
               MIN(CASE WHEN price > 0 AND normalized_price > 0 THEN normalized_price END) AS min_price,
               MAX(CASE WHEN price > 0 AND normalized_price > 0 THEN normalized_price END) AS max_price,
               AVG(CASE WHEN price > 0 AND normalized_price > 0 THEN normalized_price END) AS avg_price
        FROM read_parquet('history_free.parquet')
        GROUP BY product_id
    """).fetchall()
    return {pid: {'min_price': mn, 'max_price': mx, 'avg_price': av} for pid, mn, mx, av in rows}


def repair_history_file(path, affected):
    if not os.path.exists(path):
        print(f'  skip {path} (missing)')
        return
    df = read_parquet(path)
    corrected = 0
    new_values = []
    for pid, price, old in zip(df['product_id'], df['price'], df['normalized_price']):
        old = float(old)
        factor = affected.get(pid, (None, None))[0]
        if factor is None or float(price) <= 0:
            new_values.append(old)  # untouched product or the -1.0 out-of-stock sentinel
            continue
        new = round(float(price) * factor, 6)
        if abs(new - old) > 0.005:
            corrected += 1
        new_values.append(new)
    df['normalized_price'] = new_values
    print(f'  {path}: {len(df):,} rows, {corrected:,} normalized values corrected')
    write_parquet(df, path)


def repair_products_file(path, aggs):
    if not os.path.exists(path):
        print(f'  skip {path} (missing)')
        return
    df = read_parquet(path)
    norm, types, ratios = [], [], []
    corrected = 0
    for name, store, unit, price, old_norm, old_type in zip(
            df['name'], df['store'], df['unit'], df['current_price'],
            df['normalized_price'], df['unit_type']):
        new_norm, new_type, ratio = correction(name, store, unit, price, old_norm, old_type)
        if ratio is not None or new_type != old_type:
            corrected += 1
        norm.append(new_norm)
        types.append(new_type)
        ratios.append(ratio)
    df['normalized_price'] = norm
    df['unit_type'] = types

    # min/max/avg come from the repaired history, exactly like convert_to_parquet
    for col in ('min_price', 'max_price', 'avg_price'):
        updated = []
        for pid, value, ratio, new_norm in zip(df['id'], df[col], ratios, norm):
            agg_val = aggs.get(pid, {}).get(col)
            if agg_val is not None:
                updated.append(float(agg_val))
            elif value is not None and ratio:
                updated.append(round(float(value) * ratio, 6))
            elif value is not None:
                updated.append(float(value))
            else:
                updated.append(float(new_norm))
        df[col] = updated
    print(f'  {path}: {len(df):,} products, {corrected:,} corrected')
    write_parquet(df, path)


def repair_atl_file(path, aggs):
    if not os.path.exists(path):
        print(f'  skip {path} (missing)')
        return
    df = read_parquet(path)
    norm, types, ratios = [], [], []
    corrected = 0
    for name, store, unit, price, old_norm, old_type in zip(
            df['name'], df['store'], df['unit'], df['current_price'],
            df['normalized_price'], df['unit_type']):
        new_norm, new_type, ratio = correction(name, store, unit, price, old_norm, old_type)
        if ratio is not None or new_type != old_type:
            corrected += 1
        norm.append(new_norm)
        types.append(new_type)
        ratios.append(ratio)
    df['normalized_price'] = norm
    df['unit_type'] = types

    for col in ('min_price', 'max_price', 'avg_price'):
        df[col] = [
            float(aggs[pid][col]) if pid in aggs and aggs[pid][col] is not None
            else (round(float(v) * r, 6) if (v is not None and r) else v)
            for pid, v, r in zip(df['id'], df[col], ratios)
        ]
    for col in ('sparkline', 'sparkline_all'):
        if col not in df.columns:
            continue
        series_out = []
        for raw, r in zip(df[col], ratios):
            if not raw or not r:
                series_out.append(raw)
                continue
            try:
                values = json.loads(raw)
            except Exception:
                series_out.append(raw)
                continue
            series_out.append(json.dumps([None if v is None else round(v * r, 2) for v in values]))
        df[col] = series_out
    print(f'  {path}: {len(df):,} ATL deals, {corrected:,} corrected')
    write_parquet(df, path)


def repair_atl_preview(path):
    if not os.path.exists(path):
        print(f'  skip {path} (missing)')
        return
    with open(path, 'r', encoding='utf-8') as f:
        items = json.load(f)
    corrected = 0
    for item in items:
        new_norm, new_type, ratio = correction(
            item.get('name'), item.get('store'), item.get('unit'),
            item.get('current_price'), item.get('normalized_price'), item.get('unit_type'))
        if ratio is None and new_type == item.get('unit_type'):
            continue
        item['normalized_price'] = new_norm
        item['unit_type'] = new_type
        if ratio:
            for key in ('min_price', 'max_price', 'avg_price'):
                if item.get(key):
                    item[key] = round(float(item[key]) * ratio, 6)
            if item.get('sparkline'):
                try:
                    item['sparkline'] = json.dumps(
                        [None if v is None else round(v * ratio, 2) for v in json.loads(item['sparkline'])])
                except Exception:
                    pass
        corrected += 1
    if not DRY_RUN:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(items, f, separators=(',', ':'), ensure_ascii=False)
    print(f'  {path}: {corrected:,} preview deals corrected')


def repair_swapno_source():
    """swapnoTRACKER/data.json is the Shwapno store of record (gitignored, re-encrypted)."""
    path = 'swapnoTRACKER/data.json'
    if not os.path.exists(path):
        print(f'  skip {path} (missing)')
        return
    sys.path.insert(0, os.path.join(BASE, 'swapnoTRACKER'))
    cwd = os.getcwd()
    try:
        os.chdir(os.path.join(BASE, 'swapnoTRACKER'))
        import scraper_web
        normalize_unit = scraper_web.normalize_unit
    except Exception as exc:
        print(f'  skip {path} (scraper_web import failed: {exc})')
        return
    finally:
        os.chdir(cwd)

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    corrected = 0
    for p in data.values():
        if not isinstance(p, dict) or not p.get('name'):
            continue
        name = p['name']
        hist = p.get('history') or []
        price = float(p.get('current_price') or 0)
        if price <= 0 and hist:
            price = float(hist[-1].get('price') or 0)
        if price <= 0:
            continue
        _, old_norm, old_type = _legacy_normalize_unit(name, str(price))
        unit_disp, new_norm, u_type = normalize_unit(name, str(price))
        if old_type == u_type and abs(old_norm - new_norm) <= 0.005:
            continue
        _, factor, _ = normalize_unit(name, '1')
        corrected += 1
        p['unit'], p['unit_type'], p['normalized_price'] = unit_disp, u_type, new_norm
        if factor:
            for h in hist:
                hp = float(h.get('price') or 0)
                if hp > 0:
                    h['normalized_price'] = round(hp * factor, 6)
    if not DRY_RUN:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    print(f'  {path}: {len(data):,} products, {corrected:,} corrected')


def enc_det(data, key_str):
    d_hash = hashlib.sha256(data).digest()
    s = hashlib.sha256(b"GGE1_SALT:" + key_str.encode('utf-8') + d_hash).digest()[:16]
    i = hashlib.sha256(b"GGE1_IV:" + key_str.encode('utf-8') + d_hash).digest()[:12]
    k = hashlib.pbkdf2_hmac('sha256', key_str.encode('utf-8'), s, 250000, dklen=32)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return b'GGE1' + s + i + AESGCM(k).encrypt(i, data, None)


def reencrypt(plain_path, enc_path, split=None):
    if not os.path.exists(plain_path):
        print(f'  skip {enc_path} ({plain_path} missing)')
        return
    with open(plain_path, 'rb') as f:
        blob = enc_det(f.read(), PREMIUM_KEY)
    if DRY_RUN:
        print(f'  would re-encrypt {enc_path} ({len(blob) / 1048576:.1f} MB)')
        return
    if split:
        for old in glob.glob(enc_path + '.[0-9][0-9][0-9]'):
            os.remove(old)
        if os.path.exists(enc_path):
            os.remove(enc_path)
        for idx, off in enumerate(range(0, len(blob), split)):
            with open(f'{enc_path}.{idx:03d}', 'wb') as f:
                f.write(blob[off:off + split])
        print(f'  re-encrypted {enc_path} -> {(len(blob) + split - 1) // split} chunks ({len(blob) / 1048576:.1f} MB)')
    else:
        with open(enc_path, 'wb') as f:
            f.write(blob)
        print(f'  re-encrypted {enc_path} ({len(blob) / 1048576:.1f} MB)')


def main():
    print(f'Repairing per-unit normalization{" (DRY RUN)" if DRY_RUN else ""}...')

    print('\n[1/5] scanning for affected products')
    affected = affected_products()
    print(f'  {len(affected):,} products need a correction')

    print('\n[2/5] history datasets')
    for path in HISTORY_FILES:
        repair_history_file(path, affected)

    print('\n[3/5] product catalogs & ATL deals')
    aggs = history_aggregates()
    for path in PRODUCT_FILES:
        repair_products_file(path, aggs)
    repair_atl_file('atl.parquet', aggs)
    repair_atl_preview('atl_preview.json')

    print('\n[4/5] Shwapno store of record')
    repair_swapno_source()

    print('\n[5/5] re-encrypting tracked ciphertext')
    reencrypt('products.parquet', 'products.parquet.enc')
    reencrypt('history_free.parquet', 'premium/history_archive.parquet.enc', split=40 * 1024 * 1024)
    reencrypt('swapnoTRACKER/data.json', 'swapnoTRACKER/data.json.enc')


if __name__ == '__main__':
    main()
