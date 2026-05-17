import requests
import json

def debug_api_response():
    base_url = "https://myadmin.unimart.online/api/v1/"
    headers = {
        "moduleid": "1",
        "zoneid": "[1]",
        "x-localization": "en",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    
    # Try with a category we KNOW has items, like 82 (UHT Milk)
    cid = 82
    url = f"{base_url}categories/items/{cid}?limit=10&offset=1"
    print(f"URL: {url}")
    r = requests.get(url, headers=headers)
    print(f"Status: {r.status_code}")
    print(f"Content: {r.text[:1000]}")

if __name__ == "__main__":
    debug_api_response()
