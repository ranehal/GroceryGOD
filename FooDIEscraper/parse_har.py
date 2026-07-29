import json
import sys
import io
from urllib.parse import urlparse, parse_qs

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HAR_PATH = r"C:\PROJECTS\FoodPANDA\perseus-productanalytics.deliveryhero.net_2026_07_25_00_46_35.har"
TARGET_DOMAIN = "reviews-api-bd.fd-api.com"
MAX_RESP_CHARS = 5000

def read_har(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def decode_response_body(entry):
    resp = entry["response"]
    content = resp.get("content", {})
    text = content.get("text", "")
    encoding = content.get("encoding", "")
    if encoding == "base64":
        import base64
        try:
            text = base64.b64decode(text).decode("utf-8", errors="replace")
        except Exception:
            pass
    return text

def extract_headers(headers_list):
    return {h["name"].lower(): h["value"] for h in headers_list}

def extract_key_headers(req_headers):
    keys = ["authorization", "r-sig", "eks", "rts", "app-version", "device-id",
            "user-agent", "x-fp-api-key", "x-country", "x-city", "x-lang",
            "x-pandora-instance", "x-platform", "x-request-id", "cookie",
            "content-type", "accept", "x-client-id"]
    return {k: req_headers[k] for k in keys if k in req_headers}

def main():
    har = read_har(HAR_PATH)
    entries = har["log"]["entries"]

    target_entries = []
    for entry in entries:
        url = entry["request"]["url"]
        parsed = urlparse(url)
        if TARGET_DOMAIN in parsed.hostname or TARGET_DOMAIN in url:
            target_entries.append(entry)

    print(f"{'='*80}")
    print(f"TOTAL HAR ENTRIES: {len(entries)}")
    print(f"ENTRIES MATCHING '{TARGET_DOMAIN}': {len(target_entries)}")
    print(f"{'='*80}\n")

    if not target_entries:
        print("No matching entries found. Let me check what domains ARE in the HAR...")
        domains = set()
        for entry in entries:
            try:
                h = urlparse(entry["request"]["url"]).hostname
                if h:
                    domains.add(h)
            except:
                pass
        for d in sorted(domains):
            print(f"  {d}")
        return

    # Classify entries
    listing_entries = []
    graphql_entries = []
    other_entries = []

    listing_keywords = [
        "restaurant", "vendor", "store", "shop", "listing", "discovery",
        "feed", "home", "search", "nearby", "all_restaurants", "allRestaurants",
        "catalog", "browse", "category", "collection", "recommend",
        "popular", "trending", "nearby_restaurants", "vendorList"
    ]

    for entry in target_entries:
        url = entry["request"]["url"]
        method = entry["request"]["method"]
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        body_text = ""
        if method == "POST":
            post_data = entry["request"].get("postData", {})
            body_text = post_data.get("text", "")

        # Check if GraphQL
        is_graphql = "graphql" in path_lower or "graphql" in body_text.lower()

        # Check if listing endpoint
        is_listing = False
        for kw in listing_keywords:
            if kw.lower() in path_lower or kw.lower() in url.lower() or kw.lower() in body_text.lower():
                is_listing = True
                break

        if is_listing:
            listing_entries.append(entry)
        if is_graphql:
            graphql_entries.append(entry)
        if not is_listing and not is_graphql:
            other_entries.append(entry)

    print(f"LISTING/Discovery entries: {len(listing_entries)}")
    print(f"GraphQL entries: {len(graphql_entries)}")
    print(f"Other entries: {len(other_entries)}")
    print(f"{'='*80}\n")

    # ---- PRINT ALL UNIQUE URL PATTERNS ----
    all_urls = set()
    for entry in target_entries:
        url = entry["request"]["url"]
        parsed = urlparse(url)
        # Normalize: strip query params for pattern
        all_urls.add(f"{entry['request']['method']} {parsed.path}")

    print("ALL UNIQUE ENDPOINT PATTERNS:")
    for u in sorted(all_urls):
        print(f"  {u}")
    print(f"{'='*80}\n")

    # ---- PRINT LISTING ENTRIES IN DETAIL ----
    print("\n" + "="*80)
    print("RESTAURANT LISTING / DISCOVERY ENDPOINTS (DETAILED)")
    print("="*80 + "\n")

    for idx, entry in enumerate(listing_entries):
        url = entry["request"]["url"]
        method = entry["request"]["method"]
        status = entry["response"]["status"]
        parsed = urlparse(url)
        req_headers = extract_headers(entry["request"]["headers"])
        key_hdrs = extract_key_headers(req_headers)

        print(f"\n--- LISTING ENTRY #{idx+1} ---")
        print(f"URL: {url}")
        print(f"PATH: {parsed.path}")
        print(f"METHOD: {method}")
        print(f"STATUS: {status}")

        if method == "POST":
            post_data = entry["request"].get("postData", {})
            body_text = post_data.get("text", "")
            mime = post_data.get("mimeType", "")
            print(f"POST MIME: {mime}")
            if body_text:
                try:
                    body_json = json.loads(body_text)
                    print(f"REQUEST BODY (JSON):")
                    print(json.dumps(body_json, indent=2)[:3000])
                except:
                    print(f"REQUEST BODY (raw): {body_text[:3000]}")

        # Query params
        qs = parse_qs(parsed.query)
        if qs:
            print(f"QUERY PARAMS: {json.dumps(qs, indent=2)}")

        print(f"\nKEY REQUEST HEADERS:")
        print(json.dumps(key_hdrs, indent=2))

        # Response body
        resp_text = decode_response_body(entry)
        if resp_text:
            print(f"\nRESPONSE BODY (first {MAX_RESP_CHARS} chars):")
            print(resp_text[:MAX_RESP_CHARS])
        print()

    # ---- GRAPHQL ENTRIES ----
    print("\n" + "="*80)
    print("GRAPHQL ENTRIES")
    print("="*80 + "\n")

    graphql_count = 0
    for idx, entry in enumerate(graphql_entries):
        url = entry["request"]["url"]
        method = entry["request"]["method"]
        status = entry["response"]["status"]
        parsed = urlparse(url)
        req_headers = extract_headers(entry["request"]["headers"])

        print(f"\n--- GRAPHQL ENTRY #{idx+1} ---")
        print(f"URL: {url}")
        print(f"METHOD: {method}")
        print(f"STATUS: {status}")

        # Print key headers
        key_hdrs = extract_key_headers(req_headers)
        print(f"KEY REQUEST HEADERS:")
        print(json.dumps(key_hdrs, indent=2))

        if method == "POST":
            post_data = entry["request"].get("postData", {})
            body_text = post_data.get("text", "")
            if body_text:
                try:
                    body_json = json.loads(body_text)
                    op_name = body_json.get("operationName", "N/A")
                    sha = body_json.get("sha256Hash", body_json.get("extensions", {}).get("persistedQuery", {}).get("sha256Hash", "N/A"))
                    print(f"OPERATION NAME: {op_name}")
                    print(f"SHA256 HASH: {sha}")
                    print(f"VARIABLES:")
                    print(json.dumps(body_json.get("variables", {}), indent=2))
                except:
                    print(f"REQUEST BODY: {body_text[:1000]}")

        resp_text = decode_response_body(entry)
        if resp_text:
            print(f"\nFULL RESPONSE (first {MAX_RESP_CHARS} chars):")
            print(resp_text[:MAX_RESP_CHARS])
        print()

        graphql_count += 1

    # ---- OTHER ENTRIES (brief) ----
    if other_entries:
        print("\n" + "="*80)
        print("OTHER (non-listing, non-graphql) ENTRIES (summary)")
        print("="*80 + "\n")
        for idx, entry in enumerate(other_entries[:20]):
            url = entry["request"]["url"]
            method = entry["request"]["method"]
            status = entry["response"]["status"]
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            print(f"  #{idx+1} {method} {parsed.path}  status={status}  params={list(qs.keys())}")

    # ---- PAGINATION ANALYSIS ----
    print("\n" + "="*80)
    print("PAGINATION PARAMETERS ANALYSIS")
    print("="*80 + "\n")

    pagination_keywords = ["offset", "page", "limit", "per_page", "perpage", "cursor",
                           "after", "before", "skip", "take", "start", "from", "size",
                           "next", "first", "last", "max_id", "min_id"]

    for idx, entry in enumerate(target_entries):
        url = entry["request"]["url"]
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        body_text = ""
        if entry["request"]["method"] == "POST":
            post_data = entry["request"].get("postData", {})
            body_text = post_data.get("text", "")

        # Check query params
        found_params = {k: v for k, v in qs.items() if any(pk in k.lower() for pk in pagination_keywords)}
        # Check body
        body_pagination = {}
        if body_text:
            try:
                body_json = json.loads(body_text)
                if isinstance(body_json, dict):
                    for k, v in body_json.items():
                        if any(pk in k.lower() for pk in pagination_keywords):
                            body_pagination[k] = v
                    # Also check variables
                    vars_ = body_json.get("variables", {})
                    if isinstance(vars_, dict):
                        for k, v in vars_.items():
                            if any(pk in k.lower() for pk in pagination_keywords):
                                body_pagination[f"variables.{k}"] = v
            except:
                pass

        if found_params or body_pagination:
            path = parsed.path
            print(f"  {entry['request']['method']} {path}")
            if found_params:
                print(f"    Query: {json.dumps(found_params, indent=4)}")
            if body_pagination:
                print(f"    Body:  {json.dumps(body_pagination, indent=4)}")

    # ---- SUMMARY: operation names + sha256 ----
    print("\n" + "="*80)
    print("SUMMARY: ALL GRAPHQL OPERATION NAMES AND SHA256 HASHES")
    print("="*80 + "\n")

    seen_ops = set()
    for entry in graphql_entries:
        if entry["request"]["method"] == "POST":
            post_data = entry["request"].get("postData", {})
            body_text = post_data.get("text", "")
            if body_text:
                try:
                    body_json = json.loads(body_text)
                    op_name = body_json.get("operationName", "N/A")
                    sha = body_json.get("sha256Hash", body_json.get("extensions", {}).get("persistedQuery", {}).get("sha256Hash", "N/A"))
                    key = f"{op_name}:{sha}"
                    if key not in seen_ops:
                        seen_ops.add(key)
                        print(f"  Operation: {op_name}")
                        print(f"  SHA256:    {sha}")
                        print(f"  Variables: {json.dumps(body_json.get('variables', {}), indent=4)}")
                        print()
                except:
                    pass

if __name__ == "__main__":
    main()
