import json
import os
import sys
import re

# Try to import pandas
try:
    import pandas as pd
except ImportError:
    print("Error: pandas is not installed. Please run 'pip install pandas openpyxl xlsxwriter'.")
    sys.exit(1)

# Read data.js
DATA_FILE = 'data.js'
if not os.path.exists(DATA_FILE):
    print(f"Error: {DATA_FILE} not found.")
    sys.exit(1)

print(f"Reading {DATA_FILE}...")
with open(DATA_FILE, 'r', encoding='utf-8') as f:
    content = f.read()
    # Strip JS prefix/suffix: window.PRODUCT_DATA = { ... };
    start = content.find('{')
    end = content.rfind('}') + 1
    
    if start == -1 or end == 0:
        print("Error: Could not parse data.js content.")
        sys.exit(1)
    
    json_str = content[start:end]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        sys.exit(1)

products = list(data.values())
print(f"Found {len(products)} products.")

rows = []
for p in products:
    price = float(p.get('current_price', 0))
    unit = str(p.get('current_unit', '')).lower().strip()
    img_url = p.get('image', '')
    
    # Normalize Price
    qty = 1.0
    match = re.match(r'^(\d+(\.\d+)?)\s*([a-z]+)', unit)
    if match:
        qty = float(match.group(1))
        u_str = match.group(3)
        if u_str in ['g', 'gm', 'gms', 'gram', 'ml', 'milli']:
            qty /= 1000.0
        elif u_str in ['dz', 'dozen']:
            qty *= 12
        elif u_str in ['hali']:
            qty *= 4
    elif 'gm' in unit or 'g' in unit: 
         # Rough estimation if number missing but unit implies weight
         qty = 0.001 # Assume 1g if ambiguous? Rare.
    
    if qty == 0: qty = 1
    norm_price = price / qty
    
    row = {
        'ID': p.get('id'),
        'Name': p.get('name'),
        'Category': p.get('category'),
        'Price': price,
        'Unit': p.get('current_unit'),
        'Norm Price (1 Unit)': round(norm_price, 2),
        'Image': f'=IMAGE("{img_url}")', # Excel Formula
        'Link': p.get('url'),
        'History Entries': len(p.get('history', []))
    }
    rows.append(row)

df = pd.DataFrame(rows)

OUTPUT_FILE = 'pricetracker_data.xlsx'
try:
    # Use XlsxWriter to support formulas/images if needed, but default openpyxl supports formulas if strings start with =
    # However, pandas usually escapes strings.
    # We'll use specific engine logic if pandas fails to write formulas.
    # Actually, pandas to_excel writes strings. User needs to enable content or formula.
    # Excel 365 renders =IMAGE(...) automatically.
    
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"Success! Exported to {OUTPUT_FILE}")
except Exception as e:
    print(f"Excel export failed: {e}")
    # Fallback
    df.to_csv('pricetracker_data.csv', index=False)
    print("Saved as CSV instead.")
