import json, urllib.request, urllib.error, ssl, gzip, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "shwapno.flutter.android",
    "Accept": "application/json",
    "client-type": "App",
    "customer": "fbbbb451-a780-4101-88e0-aad799e60f83",
    "app-secret": "Ak2T/rk/AcGPU6V7yoYGB6YQDUSg2xrYO+3u7UMY2SI=",
    "accept-encoding": "gzip",
}

def req(path):
    url = "https://store-api.shwapno.com/en/api" + path
    r = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(r, timeout=20, context=SSL_CTX) as resp:
            raw = resp.read()
            if raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}"}
    except Exception as e:
        return {"_error": str(e)}

# Load megamenutree
with open("response_store-api_shwapno_com__common_megamenutree.json") as f:
    mega = json.load(f)

def extract_leaves(items, parent=""):
    leaves = []
    for item in items:
        title = item.get("title", "")
        url = item.get("url", "")
        children = item.get("childMenuItems", [])
        if children:
            leaves.extend(extract_leaves(children, parent=title))
        else:
            leaves.append({"title": title, "url": url, "parent": parent})
    return leaves

leaves = extract_leaves(mega.get("data", []))
print(f"Checking {len(leaves)} leaf categories...\n")

# First try to batch-discover category IDs
# Hit /api/{url} for each leaf
results = []
errors = []
lock = Lock()

def check_cat(leaf):
    time.sleep(0.1)
    resp = req("/" + leaf["url"])
    if resp.get("_error"):
        # Try parent category API
        parent_path = leaf.get("parent", "").lower().replace(" ", "-")
        resp2 = req("/" + leaf["url"].lower() + "/" + parent_path)
        with lock:
            errors.append({"leaf": leaf, "error": resp["_error"]})
        return leaf["title"], leaf["url"], None, resp.get("_error", "unknown")
    
    # Extract category ID from response
    data = resp.get("data", resp)
    cat_id = None
    if isinstance(data, dict):
        cat_id = data.get("id") or data.get("categoryId") or data.get("category_id")
    
    with lock:
        results.append({"leaf": leaf, "id": cat_id, "status": "ok"})
    return leaf["title"], leaf["url"], cat_id, "ok"

with ThreadPoolExecutor(max_workers=8) as ex:
    futures = {ex.submit(check_cat, l): l for l in leaves}
    for f in as_completed(futures):
        title, url, cid, status = f.result()
        if cid:
            print(f"  OK  {title:30s} id={cid}")
        elif status == "ok":
            print(f"  ??? {title:30s} url={url} (no id in response)")

print(f"\n=== Summary ===")
print(f"Checked: {len(leaves)}, with ID: {len(results)}, errors: {len(errors)}")

# Save results
with open("category_ids.json", "w") as f:
    json.dump({"results": results, "errors": errors}, f, indent=2, ensure_ascii=False)
print("Saved category_ids.json")
