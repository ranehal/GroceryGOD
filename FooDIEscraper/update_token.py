"""Token + sxsrf updater. 
Usage:
  python update_token.py              # Interactive: paste token + refresh + sxsrf
  python update_token.py --har FILE   # Auto-extract everything from a .har file
"""
import sys, json, base64
from pathlib import Path

DATA = Path(__file__).parent / "data"


def show_token_info(label: str, token: str):
    try:
        payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        import time
        remaining = payload["exp"] - int(time.time())
        status = f"valid ({remaining}s left)" if remaining > 0 else "EXPIRED"
        print(f"  {label}: {status} | jti={payload['jti'][:8]}...")
    except Exception as e:
        print(f"  {label}: invalid — {e}")


def extract_from_har(har_path: str):
    """Auto-extract token, refresh token, and initial sxsrf from a HAR file."""
    import time as _time

    with open(har_path, encoding="utf-8") as f:
        har = json.load(f)

    entries = har.get("log", {}).get("entries", [])

    # Find the earliest API request (sorted by startedDateTime)
    api_entries = []
    for entry in entries:
        url = entry.get("request", {}).get("url", "")
        if "api.foodibd.com" not in url or "image-resize" in url:
            continue
        api_entries.append(entry)
    api_entries.sort(key=lambda e: e.get("startedDateTime", ""))

    if not api_entries:
        print("ERROR: No api.foodibd.com requests found in HAR")
        sys.exit(1)

    # Extract JWT from authorization header
    token = None
    refresh = None
    sxsrf = None

    for entry in api_entries:
        for h in entry["request"].get("headers", []):
            if h.get("name", "").lower() == "authorization" and not token:
                t = h["value"].replace("Bearer ", "")
                if t.startswith("eyJ"):
                    token = t
            if h.get("name", "").lower() == "sxsrf" and not sxsrf:
                # Verify it decodes to valid JSON
                try:
                    v = h["value"]
                    for _ in range(5):
                        try:
                            inner = json.loads(v)
                            break
                        except (json.JSONDecodeError, ValueError):
                            v = base64.b64decode(v).decode("utf-8", errors="replace")
                    if "expires" in inner and "sign" in inner:
                        sxsrf = h["value"]
                except Exception:
                    pass
        if token and sxsrf:
            break

    # Check refresh token in POST bodies
    for entry in entries:
        body_text = entry.get("request", {}).get("postData", {}).get("text", "")
        if "refreshToken" in body_text and "RefreshToken" in entry.get("request", {}).get("url", ""):
            try:
                body = json.loads(body_text)
                rt = body.get("refreshToken")
                if rt:
                    refresh = rt
            except Exception:
                pass

    # Show what we found
    print(f"\nFound in {Path(har_path).name}:")
    if token:
        show_token_info("JWT token", token)
    else:
        print("  JWT token: NOT FOUND")
    if refresh:
        print(f"  Refresh token: {refresh[:30]}...")
    else:
        print("  Refresh token: NOT FOUND (look for RefreshToken request body in Reqable)")
    if sxsrf:
        try:
            v = sxsrf
            for _ in range(4):
                v = base64.b64decode(v).decode("utf-8", errors="replace")
            inner = json.loads(v)
            print(f"  sxsrf: expires={inner['expires']}, random={inner['random']}")
        except Exception:
            print(f"  sxsrf: extracted ({len(sxsrf)} chars)")
    else:
        print("  sxsrf: NOT FOUND")

    # Save
    DATA.mkdir(parents=True, exist_ok=True)
    if token:
        (DATA / "token.txt").write_text(token)
    if refresh:
        (DATA / "refresh_token.txt").write_text(refresh)
    if sxsrf:
        (DATA / "sxsrf.txt").write_text(sxsrf)

    print(f"\nSaved to {DATA}/")
    print("Run: python scraper.py")


def main():
    DATA.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) > 2 and sys.argv[1] == "--har":
        extract_from_har(sys.argv[2])
        return

    print("=== FoodiBD Token + sxsrf Updater ===\n")
    print("Paste from Reqable (or use --har FILE to auto-extract)\n")

    token = input("JWT token (eyJ..., or Enter to skip): ").strip()
    refresh = input("Refresh token (or Enter to skip): ").strip()
    sxsrf_val = input("Initial sxsrf (base64, or Enter to skip): ").strip()

    if token:
        if not token.startswith("eyJ"):
            print("WARNING: Token doesn't start with 'eyJ', skipping")
            token = None
        else:
            (DATA / "token.txt").write_text(token)
            print("  Saved token.txt")

    if refresh:
        (DATA / "refresh_token.txt").write_text(refresh)
        print("  Saved refresh_token.txt")

    if sxsrf_val:
        (DATA / "sxsrf.txt").write_text(sxsrf_val)
        print("  Saved sxsrf.txt")

    if token:
        show_token_info("Access token", token)

    print("\nRun: python scraper.py")


if __name__ == "__main__":
    main()
