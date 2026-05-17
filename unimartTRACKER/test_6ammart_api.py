import requests
import json

def test_6ammart_api():
    base_url = "https://myadmin.unimart.online/api/v1/"
    # Testing category ID 3
    cid = 3
    endpoints = [
        f"items/latest?category_id={cid}&limit=10&offset=1",
        f"categories/items/{cid}?limit=10&offset=1",
        f"products/items/{cid}",
        f"categories/products/{cid}"
    ]
    
    for ep in endpoints:
        url = base_url + ep
        print(f"Testing URL: {url}")
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                print(f"Success! Captured data.")
                with open(f"unimartTRACKER/api_test_success.json", "w", encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                return # Found it
            else:
                print(f"Failed: {r.status_code}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_6ammart_api()
