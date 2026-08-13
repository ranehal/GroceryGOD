import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
"""
FoodiBD Scraper - Async product scraper with price history tracking.
Usage: python scraper.py [--token JWT_TOKEN]
"""

import asyncio

import random
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

import base64
import json
import logging
import os
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import yaml
from pyarrow import parquet, Table, schema, field, string, float64, int64, bool_, timestamp
import sqlite3

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE = Path(__file__).parent
with open(BASE / "config.yaml") as f:
    CFG = yaml.safe_load(f)

SHOP = CFG["shop"]
API = CFG["api"]
SCRAPE = CFG["scraping"]
CATEGORIES = CFG["categories"]
OUT = CFG["output"]

# Ensure dirs exist
for d in [OUT["parquet_dir"], OUT["logs_dir"], BASE / "data"]:
    (BASE / d).mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LASTRUN_LOG = BASE / OUT["logs_dir"] / "lastrun.log"
LASTRUN_LOG.parent.mkdir(parents=True, exist_ok=True)

# Force UTF-8 on Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LASTRUN_LOG, mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("scraper")
for noisy in ("httpx", "httpcore", "hpack", "h2", "httpcore.http2"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Parquet schema for price history
# ---------------------------------------------------------------------------
PRICE_SCHEMA = schema([
    field("product_id", int64()),
    field("name", string()),
    field("sku", string()),
    field("category_id", int64()),
    field("category_name", string()),
    field("uom", string()),
    field("base_price", float64()),
    field("discount", float64()),
    field("is_discount_in_perc", bool_()),
    field("discounted_price", float64()),
    field("has_stock", bool_()),
    field("image_path", string()),
    field("branch_id", int64()),
    field("scraped_at", timestamp("ns")),
    field("delivery_time", string()),
])

PRODUCTS_SCHEMA = schema([
    field("product_id", int64()),
    field("name", string()),
    field("sku", string()),
    field("category_id", int64()),
    field("category_name", string()),
    field("uom", string()),
    field("base_price", float64()),
    field("discount", float64()),
    field("is_discount_in_perc", bool_()),
    field("discounted_price", float64()),
    field("has_stock", bool_()),
    field("max_qty_per_order", int64()),
    field("image_path", string()),
    field("branch_id", int64()),
    field("variations_json", string()),
    field("policy_json", string()),
    field("last_updated", timestamp("ns")),
])


# ---------------------------------------------------------------------------
# SQLite setup
# ---------------------------------------------------------------------------
def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY,
            name TEXT, sku TEXT, category_id INTEGER, category_name TEXT,
            uom TEXT, base_price REAL, discount REAL, is_discount_in_perc INTEGER,
            discounted_price REAL, has_stock INTEGER, max_qty_per_order INTEGER,
            image_path TEXT, branch_id INTEGER, variations_json TEXT, policy_json TEXT,
            last_updated TEXT
        );
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER, name TEXT, sku TEXT, category_id INTEGER,
            category_name TEXT, uom TEXT, base_price REAL, discount REAL,
            is_discount_in_perc INTEGER, discounted_price REAL, has_stock INTEGER,
            image_path TEXT, branch_id INTEGER, scraped_at TEXT, delivery_time TEXT
        );
        CREATE TABLE IF NOT EXISTS products_extra (
            branch_id INTEGER PRIMARY KEY, data TEXT
        );
        CREATE TABLE IF NOT EXISTS scrape_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT, finished_at TEXT, products_scraped INTEGER,
            categories_scraped INTEGER, status TEXT, error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ph_product ON price_history(product_id);
        CREATE INDEX IF NOT EXISTS idx_ph_scraped ON price_history(scraped_at);
        CREATE INDEX IF NOT EXISTS idx_ph_category ON price_history(category_id);
        CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Resume state
# ---------------------------------------------------------------------------
def load_resume() -> dict:
    p = BASE / OUT["resume_state_path"]
    if p.exists():
        return json.loads(p.read_text())
    return {"completed_categories": [], "last_page": {}, "total_products": 0}


def save_resume(state: dict):
    (BASE / OUT["resume_state_path"]).write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------
def extract_token_from_har(har_path: Path) -> Optional[str]:
    """Auto-extract JWT Bearer token from a .har file."""
    try:
        with open(har_path, encoding="utf-8") as f:
            har = json.load(f)
        for entry in har.get("log", {}).get("entries", []):
            if "/products/search" in entry.get("request", {}).get("url", ""):
                for h in entry["request"].get("headers", []):
                    if h.get("name", "").lower() == "authorization":
                        token = h["value"].replace("Bearer ", "")
                        if token.startswith("eyJ"):
                            return token
    except Exception:
        pass
    return None


def extract_sxsrf_from_har(har_path: Path) -> Optional[str]:
    """Extract initial sxsrf from a .har file (the double-base64 encoded server token)."""
    try:
        with open(har_path, encoding="utf-8") as f:
            har = json.load(f)
        # Find the earliest API request with a valid sxsrf
        earliest = None
        earliest_time = None
        for entry in har.get("log", {}).get("entries", []):
            url = entry.get("request", {}).get("url", "")
            if "api.foodibd.com" not in url or "image-resize" in url:
                continue
            started = entry.get("startedDateTime", "")
            sxsrf_h = None
            for h in entry["request"].get("headers", []):
                if h.get("name", "").lower() == "sxsrf":
                    sxsrf_h = h["value"]
                    break
            if not sxsrf_h:
                continue
            # Verify it decodes to valid JSON with expires/sign/random
            try:
                v = sxsrf_h
                for _ in range(5):
                    try:
                        inner = json.loads(v)
                        if "expires" in inner and "sign" in inner:
                            if earliest_time is None or started < earliest_time:
                                earliest_time = started
                                earliest = sxsrf_h
                        break
                    except (json.JSONDecodeError, ValueError):
                        v = base64.b64decode(v).decode("utf-8", errors="replace")
            except Exception:
                continue
        return earliest
    except Exception:
        pass
    return None


def double_base64_encode(value: str) -> str:
    """Double-base64 encode a string (matching xg.b.c() in the APK)."""
    step1 = base64.b64encode(value.encode("utf-8")).decode("utf-8")
    return base64.b64encode(step1.encode("utf-8")).decode("utf-8")


def double_base64_decode(value: str) -> Optional[str]:
    """Try to double-base64 decode a string back to its original value."""
    try:
        step1 = base64.b64decode(value).decode("utf-8", errors="replace")
        return base64.b64decode(step1).decode("utf-8", errors="replace")
    except Exception:
        return None


def extract_cf_ray_from_response(resp) -> Optional[str]:
    """Extract cf-ray-status-id-tn from response and return double-base64 encoded sxsrf.

    The APK's xg.b.c() does Base64(Base64(value)) — the stored sxsrf_token is
    double-base64 of the raw cf-ray-status-id-tn header value.
    """
    cf_raw = resp.headers.get("cf-ray-status-id-tn", "")
    if not cf_raw:
        return None
    return double_base64_encode(cf_raw)


def get_token(cli_token: Optional[str] = None) -> str:
    if API.get("guest_mode"):
        return ""
    if cli_token:
        return cli_token
    env = os.environ.get("FOODIBD_TOKEN")
    if env:
        return env
    token_file = BASE / "data" / "token.txt"
    if token_file.exists() and token_file.read_text().strip():
        return token_file.read_text().strip()
    # Auto-extract from any .har file in project root
    for har_file in BASE.glob("*.har"):
        token = extract_token_from_har(har_file)
        if token:
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(token)
            log.info(f"Auto-extracted token from {har_file.name}")
            return token
    log.warning("No JWT token found. Continuing in public guest mode."); return ""


def get_initial_sxsrf() -> str:
    """Load initial sxsrf from data/sxsrf.txt or auto-extract from HAR files."""
    sxsrf_file = BASE / "data" / "sxsrf.txt"
    if sxsrf_file.exists() and sxsrf_file.read_text().strip():
        return sxsrf_file.read_text().strip()
    # Auto-extract from any .har file
    for har_file in BASE.glob("*.har"):
        sxsrf = extract_sxsrf_from_har(har_file)
        if sxsrf:
            sxsrf_file.parent.mkdir(parents=True, exist_ok=True)
            sxsrf_file.write_text(sxsrf)
            log.info(f"Auto-extracted initial sxsrf from {har_file.name}")
            return sxsrf
    log.warning("No initial sxsrf found. First request may fail - capture a fresh session in Reqable and save to data/sxsrf.txt")
    return ""


def get_refresh_token() -> str:
    p = BASE / "data" / "refresh_token.txt"
    return p.read_text().strip() if p.exists() else ""


def get_device_id() -> str:
    p = BASE / "data" / "device_id.txt"
    if p.exists():
        return p.read_text().strip()
    # Extract from JWT payload
    token_file = BASE / "data" / "token.txt"
    if token_file.exists():
        try:
            payload_b64 = token_file.read_text().strip().split(".")[1]
            payload = json.loads(__import__("base64").urlsafe_b64decode(payload_b64 + "=="))
            return payload.get("DeviceId", "")
        except Exception:
            pass
    return "1b5a4567bbcb95d4"


# ---------------------------------------------------------------------------
# Scraper core
# ---------------------------------------------------------------------------
class FoodiBDScraper:
    def __init__(self, token: str):
        self.token = token
        self.refresh_token = get_refresh_token()
        self.device_id = get_device_id()
        self.base_url = API["base_url"]
        self.db = init_db(BASE / OUT["sqlite_path"])
        self.resume = load_resume()
        self.now = datetime.now(DHAKA_TZ)
        self.delivery_time = self.now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        self.semaphore = asyncio.Semaphore(SCRAPE["max_concurrent_requests"])
        self.rate_limit_interval = 1.0 / SCRAPE["rate_limit_per_second"]
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()
        self.client: Optional[httpx.AsyncClient] = None
        self.all_products: list[dict] = []
        self.run_id: Optional[int] = None
        self.stats = {"categories": 0, "products": 0, "pages": 0, "errors": 0}
        self._token_invalid = False
        # sxsrf chain: server-issued rolling token
        self._sxsrf = get_initial_sxsrf()

    def _headers(self) -> dict:
        h = {
            "accept": "application/json",
            "accept-charset": "UTF-8",
            "accept-encoding": "gzip",
            "content-type": "application/json",
            "host": "api.foodibd.com",
            "origin": API["origin"],
            "user-agent": random.choice(USER_AGENTS),
            "x-requested-with": "XMLHttpRequest",
        }
        # Only include sxsrf if we have a server-issued token (never fake it)
        if self._sxsrf:
            h["sxsrf"] = self._sxsrf
        if not API.get("guest_mode") and self.token:
            h["authorization"] = f"Bearer {self.token}"
        return h

    def _update_sxsrf(self, resp):
        """Extract cf-ray-status-id-tn from response and update sxsrf chain."""
        new_sxsrf = extract_cf_ray_from_response(resp)
        if new_sxsrf:
            self._sxsrf = new_sxsrf
            # Persist to disk for next run
            sxsrf_file = BASE / "data" / "sxsrf.txt"
            sxsrf_file.parent.mkdir(parents=True, exist_ok=True)
            sxsrf_file.write_text(new_sxsrf)
            log.debug("Updated sxsrf chain from response")

    async def _refresh_token(self) -> bool:
        """Try to refresh the JWT using the refresh token endpoint."""
        if API.get("guest_mode"):
            return False
        if not self.refresh_token:
            log.error("No refresh token available. Save it to data/refresh_token.txt")
            return False

        log.info("Attempting token refresh...")
        url = f"{self.base_url}/users/api/Authentication/RefreshToken"
        body = {
            "expiredToken": self.token,
            "refreshToken": self.refresh_token,
            "deviceId": self.device_id,
        }
        try:
            await self._rate_limit()
            headers = {**self._headers()}
            resp = await self.client.request("POST", url, headers=headers, content=json.dumps(body))
            if resp.status_code != 200:
                log.error(f"Refresh failed: HTTP {resp.status_code} - {resp.text[:200]}")
                log.error("To fix: force-close FoodiBD app -> reopen -> capture RefreshToken from Reqable -> update data/token.txt + data/refresh_token.txt")
                return False
            data = resp.json()
            if not data.get("status") or not data.get("data") or not data["data"].get("isSuccess"):
                log.error(f"Refresh rejected: {data.get('message') or data.get('data',{}).get('message')}")
                return False
            new_data = data["data"]
            new_token = new_data.get("token") or new_data.get("accessToken") or new_data.get("jwt")
            new_refresh = new_data.get("refreshToken") or new_data.get("refresh_token")
            if not new_token:
                log.error(f"Refresh response missing token. Keys: {list(new_data.keys())}")
                log.debug(f"Full refresh response: {json.dumps(data, indent=2)[:500]}")
                return False
            self.token = new_token
            (BASE / "data" / "token.txt").write_text(new_token)
            log.info("Token refreshed successfully")
            if new_refresh:
                self.refresh_token = new_refresh
                (BASE / "data" / "refresh_token.txt").write_text(new_refresh)
                log.info("Refresh token updated")
            self._token_invalid = False
            return True
        except Exception as e:
            log.error(f"Refresh error: {e}")
            return False

    async def _rate_limit(self):
        async with self._lock:
            now = time.monotonic()
            wait = self.rate_limit_interval - (now - self._last_request_time)
            if wait > 0:
                log.debug(f"Rate limit: sleeping {wait:.2f}s")
                await asyncio.sleep(wait)
            self._last_request_time = time.monotonic()

    async def _request(self, method: str, url: str, **kwargs) -> Optional[dict]:
        for attempt in range(1, SCRAPE["max_retries"] + 1):
            try:
                await self._rate_limit()
                async with self.semaphore:
                    resp = await self.client.request(method, url, headers=self._headers(), **kwargs)
                    # Always update sxsrf chain from response (even on error)
                    self._update_sxsrf(resp)
                    if resp.status_code == 401:
                        # Check if this is an sxsrf failure (server returns "invalid attempt to access")
                        body_text = resp.text[:500] if resp.content else ""
                        is_sxsrf_fail = "invalid attempt to access" in body_text.lower()

                        if is_sxsrf_fail:
                            # Extract new sxsrf from cf-ray-status-id-tn and retry
                            new_sxsrf = extract_cf_ray_from_response(resp)
                            if new_sxsrf:
                                log.info(f"SXSRF refresh from 401 response on {url}")
                                self._sxsrf = new_sxsrf
                                sxsrf_file = BASE / "data" / "sxsrf.txt"
                                sxsrf_file.parent.mkdir(parents=True, exist_ok=True)
                                sxsrf_file.write_text(new_sxsrf)
                                resp = await self.client.request(method, url, headers=self._headers(), **kwargs)
                                self._update_sxsrf(resp)
                                if resp.status_code == 401:
                                    log.error(f"401 after sxsrf refresh. URL: {url}")
                                    self.stats["errors"] += 1
                                    return None
                            else:
                                log.error(f"401 but no cf-ray-status-id-tn in response. URL: {url}")
                                self.stats["errors"] += 1
                                return None
                        else:
                            # Token-based 401 — try refresh
                            log.warning(f"401 on {url} - attempting token refresh...")
                            if await self._refresh_token():
                                resp = await self.client.request(method, url, headers=self._headers(), **kwargs)
                                self._update_sxsrf(resp)
                                if resp.status_code == 401:
                                    log.error(f"401 after refresh - token still invalid. URL: {url}")
                                    self._token_invalid = True
                                    self.stats["errors"] += 1
                                    return None
                            else:
                                log.error(f"Token refresh failed. URL: {url}")
                                self._token_invalid = True
                                self.stats["errors"] += 1
                                return None
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("status") is False and "token" in data.get("message", "").lower():
                        log.error(f"Token rejected: {data.get('message')}")
                        self._token_invalid = True
                        return None
                    return data
            except httpx.HTTPStatusError as e:
                log.warning(f"HTTP {e.response.status_code} on {url} (attempt {attempt}/{SCRAPE['max_retries']})")
                if e.response.status_code == 429:
                    await asyncio.sleep(SCRAPE["retry_delay_seconds"] * attempt * 2)
                elif e.response.status_code >= 500:
                    await asyncio.sleep(SCRAPE["retry_delay_seconds"] * attempt)
                else:
                    self.stats["errors"] += 1
                    return None
            except Exception as e:
                err_type = type(e).__name__
                log.warning(f"Request error on {url}: [{err_type}] {e} (attempt {attempt}/{SCRAPE['max_retries']})")
                await asyncio.sleep(SCRAPE["retry_delay_seconds"] * attempt)
        self.stats["errors"] += 1
        return None

    async def fetch_shop_homepage(self) -> list[dict]:
        """Fetch categories from shop homepage."""
        log.info("Fetching shop homepage for categories...")
        data = await self._request(
            "GET",
            f"{self.base_url}/products/user/shop-homepage/{SHOP['id']}",
            params={
                "pageNumber": 1,
                "itemsPerPage": 20,
                "serviceType": "delivery",
                "deliveryAt": self.delivery_time,
            },
        )
        if not data:
            return CATEGORIES  # fallback to config
        cats = []
        for item in data.get("data", {}).get("items", []):
            if item.get("type") == "category":
                for child in item.get("data", {}).get("children", []):
                    cats.append({"id": child["id"], "name": child["name"]})
        if cats:
            log.info(f"Discovered {len(cats)} categories from API")
            return cats
        return CATEGORIES

    async def fetch_branch_detail(self) -> dict:
        """Fetch branch/store metadata."""
        log.info("Fetching branch details...")
        data = await self._request(
            "GET",
            f"{self.base_url}/restaurants/api/Branch/v2/GetBranchDetail",
            params={
                "branchId": SHOP["id"],
                "userLat": SHOP["latitude"],
                "userLong": SHOP["longitude"],
                "availibilityTime": self.delivery_time,
                "orderType": "delivery",
            },
        )
        if data:
            self.db.execute(
                "INSERT OR REPLACE INTO products_extra (branch_id, data) VALUES (?, ?)",
                (SHOP["id"], json.dumps(data.get("data", {}))),
            )
            self.db.commit()
        return data.get("data", {}) if data else {}

    async def search_category(self, category_id: int, category_name: str) -> list[dict]:
        """Search all products in a category with automatic pagination."""
        if self._token_invalid:
            return []
        if category_id in self.resume.get("completed_categories", []):
            log.info(f"Skipping category {category_name} (already scraped)")
            return []

        page = self.resume.get("last_page", {}).get(str(category_id), 1)
        products = []
        log.info(f"Scraping category: {category_name} (ID: {category_id}) from page {page}")

        while True:
            body = {
                "latitude": SHOP["latitude"],
                "longitude": SHOP["longitude"],
                "categoryId": category_id,
                "paging": {"page": page, "size": SCRAPE["page_size"]},
                "deliveryAt": self.delivery_time,
                "filter": {"serviceTypes": ["isDelivery"]},
            }

            data = await self._request(
                "POST",
                f"{self.base_url}/fas/api/v2/shops/{SHOP['id']}/products/search",
                content=json.dumps(body),
            )

            if not data:
                log.warning(f"Failed to fetch page {page} for {category_name}")
                self.stats["errors"] += 1
                break

            page_products = data.get("data", {}).get("products", [])
            has_more = data.get("hasMore", False)
            total = data.get("totalElements", 0)

            for p in page_products:
                products.append({
                    "product_id": p["id"],
                    "name": p["name"],
                    "sku": p["sku"],
                    "category_id": category_id,
                    "category_name": category_name,
                    "uom": p.get("uomStr", ""),
                    "base_price": float(p.get("basePrice", 0)),
                    "discount": float(p.get("discount", 0)),
                    "is_discount_in_perc": bool(p.get("isDiscountInPerc", False)),
                    "discounted_price": float(p.get("discountedPrice", 0)),
                    "has_stock": bool(p.get("hasStock", True)),
                    "max_qty_per_order": int(p.get("maxQtyPerOrder", 100)),
                    "image_path": p.get("image", ""),
                    "branch_id": SHOP["id"],
                    "variations_json": json.dumps(p.get("variations")),
                    "policy_json": json.dumps(p.get("policyAttributes")),
                })

            self.stats["pages"] += 1
            log.info(f"  Page {page}: {len(page_products)} products (total: {total}, hasMore: {has_more})")

            if not has_more or len(page_products) == 0:
                break
            page += 1
            self.resume.setdefault("last_page", {})[str(category_id)] = page
            save_resume(self.resume)

        # Mark category complete
        self.resume.setdefault("completed_categories", []).append(category_id)
        save_resume(self.resume)
        self.stats["categories"] += 1
        self.stats["products"] += len(products)
        return products

    def _upsert_products(self, products: list[dict]):
        for p in products:
            self.db.execute("""
                INSERT OR REPLACE INTO products
                (product_id, name, sku, category_id, category_name, uom, base_price,
                 discount, is_discount_in_perc, discounted_price, has_stock,
                 max_qty_per_order, image_path, branch_id, variations_json, policy_json, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p["product_id"], p["name"], p["sku"], p["category_id"], p["category_name"],
                p["uom"], p["base_price"], p["discount"], int(p["is_discount_in_perc"]),
                p["discounted_price"], int(p["has_stock"]), p["max_qty_per_order"],
                p["image_path"], p["branch_id"], p["variations_json"], p["policy_json"],
                self.now.isoformat(),
            ))

    def _insert_price_history(self, products: list[dict]):
        rows = [(
            p["product_id"], p["name"], p["sku"], p["category_id"], p["category_name"],
            p["uom"], p["base_price"], p["discount"], int(p["is_discount_in_perc"]),
            p["discounted_price"], int(p["has_stock"]), p["image_path"], p["branch_id"],
            self.now.isoformat(), self.delivery_time,
        ) for p in products]
        self.db.executemany("""
            INSERT INTO price_history
            (product_id, name, sku, category_id, category_name, uom, base_price,
             discount, is_discount_in_perc, discounted_price, has_stock, image_path,
             branch_id, scraped_at, delivery_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)

    def _save_parquet(self, products: list[dict]):
        if not products:
            return
        today = self.now.strftime("%Y-%m-%d")
        pq_dir = BASE / OUT["parquet_dir"]
        pq_dir.mkdir(parents=True, exist_ok=True)

        # Price history partition
        ph_dir = pq_dir / "price_history"
        ph_dir.mkdir(exist_ok=True)
        ph_path = ph_dir / f"date={today}.parquet"
        tbl = Table.from_pylist([{k: v for k, v in p.items() if k != "max_qty_per_order" and k != "variations_json" and k != "policy_json"} for p in products], schema=PRICE_SCHEMA)
        parquet.write_table(tbl, ph_path, compression="snappy")
        log.info(f"Wrote {len(products)} rows to {ph_path}")

        # Latest snapshot
        snap_path = pq_dir / "latest_snapshot.parquet"
        tbl2 = Table.from_pylist(products, schema=PRODUCTS_SCHEMA)
        parquet.write_table(tbl2, snap_path, compression="snappy", use_dictionary=["name", "sku", "category_name", "uom"])
        log.info(f"Wrote snapshot to {snap_path}")

    async def run(self):
        log.info("=" * 60)
        log.info("FoodiBD Scraper starting")
        log.info(f"Shop: {SHOP['name']} (ID: {SHOP['id']})")
        log.info(f"Time: {self.now.isoformat()}")
        log.info("=" * 60)

        # Record run start
        self.db.execute(
            "INSERT INTO scrape_runs (started_at, status) VALUES (?, 'running')",
            (self.now.isoformat(),),
        )
        self.db.commit()
        self.run_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]

        timeout = httpx.Timeout(SCRAPE["timeout_seconds"])
        limits = httpx.Limits(max_connections=SCRAPE["max_concurrent_requests"])
        async with httpx.AsyncClient(timeout=timeout, limits=limits, http2=True, verify=False) as client:
            self.client = client

            # Proactively check if token is expired and refresh (skip in guest mode)
            if not API.get("guest_mode") and self.token:
                try:
                    payload_b64 = self.token.split(".")[1]
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
                    remaining = payload["exp"] - int(time.time())
                    if remaining < 300:
                        log.warning(f"Token expires in {remaining}s - proactively refreshing...")
                        await self._refresh_token()
                except Exception as e:
                    log.warning(f"Could not check token expiry: {e}")

            # Fetch branch detail (metadata)
            await self.fetch_branch_detail()
            if self._token_invalid:
                log.error("ABORT: Token refresh failed. Update data/token.txt + data/refresh_token.txt and re-run.")
                self.db.execute(
                    "UPDATE scrape_runs SET finished_at=?, status='failed', error='token_expired' WHERE id=?",
                    (datetime.now(DHAKA_TZ).isoformat(), self.run_id),
                )
                self.db.commit()
                self.db.close()
                return self.stats

            # Discover categories from API
            categories = await self.fetch_shop_homepage()

            # Scrape all categories concurrently (limited by semaphore)
            tasks = [self.search_category(c["id"], c["name"]) for c in categories]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    log.error(f"Category {categories[i]['name']} failed: {result}")
                    continue
                self.all_products.extend(result)

        # Deduplicate by product_id (products can appear in multiple categories)
        seen = set()
        unique = []
        for p in self.all_products:
            if p["product_id"] not in seen:
                seen.add(p["product_id"])
                unique.append(p)
            else:
                # Update category info for duplicates
                log.debug(f"Duplicate product {p['product_id']} in category {p['category_name']}")
        self.all_products = unique

        # Persist
        self._upsert_products(self.all_products)
        self._insert_price_history(self.all_products)
        self._save_parquet(self.all_products)
        self.db.commit()

        # Update run
        self.db.execute(
            "UPDATE scrape_runs SET finished_at=?, products_scraped=?, categories_scraped=?, status='completed' WHERE id=?",
            (datetime.now(DHAKA_TZ).isoformat(), self.stats["products"], self.stats["categories"], self.run_id),
        )
        self.db.commit()

        # Clean resume for next run
        save_resume({"completed_categories": [], "last_page": {}, "total_products": self.stats["products"]})

        log.info("=" * 60)
        log.info(f"SCRAPING COMPLETE")
        log.info(f"  Categories scraped: {self.stats['categories']}")
        log.info(f"  Unique products:    {self.stats['products']}")
        log.info(f"  Total pages:        {self.stats['pages']}")
        log.info(f"  Errors:             {self.stats['errors']}")
        log.info("=" * 60)

        self.db.close()
        return self.stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="FoodiBD Product Scraper")
    parser.add_argument("--token", help="JWT Bearer token")
    args = parser.parse_args()

    token = get_token(args.token)
    scraper = FoodiBDScraper(token)
    asyncio.run(scraper.run())


if __name__ == "__main__":
    main()
