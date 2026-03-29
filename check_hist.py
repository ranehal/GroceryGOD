import json
import os

def check():
    if not os.path.exists('data.json'):
        print("data.json not found")
        return
    with open('data.json', 'r', encoding='utf-8') as f:
        d = json.load(f)
    products = d.get('products', {})
    
    sh_items = [v for k,v in products.items() if k.startswith('sh_')]
    ch_items = [v for k,v in products.items() if k.startswith('ch_')]
    
    print(f"Total Shwapno items: {len(sh_items)}")
    hist_lengths_sh = [len(p.get('history', [])) for p in sh_items]
    if hist_lengths_sh:
        print(f"Shwapno history - Max: {max(hist_lengths_sh)}, Avg: {sum(hist_lengths_sh)/len(hist_lengths_sh):.1f}")
        
    print(f"Total Chaldal items: {len(ch_items)}")
    hist_lengths_ch = [len(p.get('history', [])) for p in ch_items]
    if hist_lengths_ch:
        print(f"Chaldal history - Max: {max(hist_lengths_ch)}, Avg: {sum(hist_lengths_ch)/len(hist_lengths_ch):.1f}")
        
    # Check specific item mentioned earlier
    if 'ch_fulkopi_cauliflower__each' in products:
        p = products['ch_fulkopi_cauliflower__each']
        print(f"Fulkopi history: {len(p.get('history', []))}")

if __name__ == '__main__':
    check()
