import json
import os

def cleanup_json(path, prefix):
    if not os.path.exists(path): return
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    clean_data = {}
    for k, v in data.items():
        if k.startswith(prefix):
            clean_data[k] = v
            
    for k, v in data.items():
        if not k.startswith(prefix):
            prefixed_k = f"{prefix}{k}"
            if prefixed_k not in clean_data:
                v['id'] = prefixed_k
                clean_data[prefixed_k] = v
            else:
                unique_h = {h['date']: h for h in clean_data[prefixed_k].get('history', [])}
                for h in v.get('history', []):
                    if h['date'] not in unique_h:
                        unique_h[h['date']] = h
                clean_data[prefixed_k]['history'] = sorted(unique_h.values(), key=lambda x: x['date'])
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(clean_data, f, indent=2)
    print(f"Cleaned {path}. Unique items: {len(clean_data)}")

if __name__ == "__main__":
    cleanup_json("swapnoTRACKER/data.json", "sh_")
    cleanup_json("ShotejTRACKER/data.json", "sj_")
    cleanup_json("unimartTRACKER/data.json", "uni_")
