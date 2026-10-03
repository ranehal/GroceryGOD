#!/usr/bin/env python3
"""
Shwapno Dynamic Deal & Promotional Pin Engine
---------------------------------------------
Dynamically discovers live promotional deals, campaign banners, and discount events
from Shwapno (e.g. /deals, /Hot-Deals, /Himalaya-3, /great-savings-3, /weekend-fresh-deal),
resolves their internal 24-character MongoDB Deal IDs from Next.js server-rendered metadata,
and synchronizes swapnoTRACKER/categories.json under the PINNED DEALS group.

Unlike standard categories which use /api/category/products, deal campaigns use:
  https://www.shwapno.com/api/deals/products?id={deal_id}&pageNumber={page}
"""

import os
import sys
import json
import re
import ssl
import urllib.request
import urllib.error
import logging

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

logger = logging.getLogger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CATEGORIES_FILE = os.path.join(CURRENT_DIR, 'categories.json')
BASE_URL = 'https://www.shwapno.com'
DEALS_HUB_URL = f'{BASE_URL}/deals'
HOME_URL = f'{BASE_URL}/'

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Cookie': '_ds_=65f008e64119aecf652223f1; _nc_=false; _mo_=false;',
    'DarkstoreId': '65f008e64119aecf652223f1',
    'Referer': 'https://www.shwapno.com/'
}

# Authoritative user-mandated promotional deal URLs with their known resolved fallback IDs
MANDATED_DEALS = [
    {
        "name": "Hot Deals",
        "url": "https://www.shwapno.com/Hot-Deals",
        "id": "66d9913ce159d315bfa55ada",
        "type": "deal",
        "enabled": True
    },
    {
        "name": "A Place For Your Grocery Needs 5",
        "url": "https://www.shwapno.com/A-Place-For-Your-Grocery-Needs-5",
        "id": "662a35d5d965db51765fa97d",
        "type": "deal",
        "enabled": True
    },
    {
        "name": "Great Savings 3",
        "url": "https://www.shwapno.com/great-savings-3",
        "id": "6625f755c73e4d62ca771441",
        "type": "deal",
        "enabled": True
    },
    {
        "name": "Deals On Unilever",
        "url": "https://www.shwapno.com/deals-on-unilever",
        "id": "661e41d6366a4503f1b54ee5",
        "type": "deal",
        "enabled": True
    },
    {
        "name": "Himalaya 3",
        "url": "https://www.shwapno.com/Himalaya-3",
        "id": "6a61edb61b630f8cacf342e6",
        "type": "deal",
        "enabled": True
    },
    {
        "name": "Deals On Toys Household Items",
        "url": "https://www.shwapno.com/deals-on-toys-household-items",
        "id": "661e3dfb366a4503f1b19391",
        "type": "deal",
        "enabled": True
    },
    {
        "name": "Weekend Fresh Deal",
        "url": "https://www.shwapno.com/weekend-fresh-deal",
        "id": "662123ad6068f8347ebab3ad",
        "type": "deal",
        "enabled": True
    }
]

def fetch_html(url, timeout=12):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        logger.warning(f"Could not fetch {url}: {e}")
        return None

def extract_deal_id_and_title(slug, html_text):
    """
    Extracts the internal 24-character hex deal ID and clean title from Next.js server-rendered HTML.
    Breadcrumb JSON schema: {"items":[{"id":"home","name":"Home","seName":"/"},{"id":"<hex_id>","name":"<title>"...}]}
    """
    if not html_text:
        return None, None
        
    clean = html_text.replace('\\"', '"').replace('\\\\', '\\')
    
    # 1. Look for breadcrumb target right after 'home'
    bc_match = re.findall(r'\{"id":"home"[^\}]+\},\{"id":"([0-9a-f]{24})","name":"([^"]+)"', clean)
    if bc_match:
        deal_id, deal_name = bc_match[0]
        # Clean unicode escapes in title
        try:
            deal_name = json.loads(f'"{deal_name}"')
        except Exception:
            pass
        return deal_id, deal_name.strip()
        
    # 2. Look for any 24-char hex ID paired with name
    matches = re.findall(r'\{"id":"([0-9a-f]{24})","name":"([^"]+)"', clean)
    candidates = [m for m in matches if m[1] != "Home"]
    if candidates:
        deal_id, deal_name = candidates[0]
        return deal_id, deal_name.strip()
        
    return None, None

def verify_deal_api(deal_id):
    """Verifies that the deal ID successfully returns live products from Shwapno deals API."""
    if not deal_id:
        return False, 0
    url = f"https://www.shwapno.com/api/deals/products?id={deal_id}&pageNumber=1"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8, context=SSL_CTX) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                products = data.get('products', [])
                total = data.get('totalProducts', len(products))
                return True, total
    except Exception:
        pass
    return False, 0

def discover_deals_from_web():
    """
    Crawls https://www.shwapno.com/deals and https://www.shwapno.com/
    to discover all active deal banners and promotional slugs.
    """
    discovered = {}
    
    # 1. Crawl /deals hub
    deals_html = fetch_html(DEALS_HUB_URL)
    if deals_html:
        clean = deals_html.replace('\\"', '"').replace('\\\\', '\\')
        anchors = re.findall(r'<a[^>]*href="(/[^"]+)"[^>]*>(.*?)</a>', clean, re.DOTALL)
        for href, inner in anchors:
            slug = href.strip('/')
            # Filter for promo slugs (skip standard technical links or deep sub-paths)
            if '/' not in slug and slug and not any(x in slug.lower() for x in [
                '_next', 'api', 'cart', 'login', 'account', 'faq', 'about', 'contact',
                'terms', 'privacy', 'helpline', 'shippinginfo', 'our-outlets', 'tac'
            ]):
                img_alt = re.findall(r'alt="([^"]+)"', inner)
                clean_text = re.sub(r'<[^>]+>', '', inner).strip()
                label = clean_text or (img_alt[0] if img_alt else "") or slug.replace('-', ' ').title()
                label = re.sub(r'^Picture of\s+', '', label, flags=re.I).strip()
                
                # Check if it has deal-like name or pattern
                if any(k in slug.lower() or k in label.lower() for k in [
                    'deal', 'saving', 'offer', 'fest', 'discount', 'need', 'hot', 'fresh', 'unilever', 'himalaya'
                ]):
                    discovered[slug] = label

    # 2. Also check homepage banners
    home_html = fetch_html(HOME_URL)
    if home_html:
        clean = home_html.replace('\\"', '"').replace('\\\\', '\\')
        banner_links = re.findall(r'href="(/[a-zA-Z0-9_\-]+)"', clean)
        for href in banner_links:
            slug = href.strip('/')
            if any(k in slug.lower() for k in ['deal', 'saving', 'offer', 'fest', 'discount', 'himalaya', 'unilever', 'special']):
                if slug not in discovered:
                    discovered[slug] = slug.replace('-', ' ').title()

    # Always ensure user-mandated deals are checked
    for d in MANDATED_DEALS:
        slug = d['url'].split('/')[-1]
        if slug not in discovered:
            discovered[slug] = d['name']

    return discovered

def sync_dynamic_deals():
    """
    Main dynamic discovery and synchronization function.
    Resolves deal IDs, verifies live products, updates categories.json,
    and returns list of active pinned deal definitions.
    """
    print("[DYNAMIC PINS] Discovering live promotional deals from Shwapno...")
    deal_slugs = discover_deals_from_web()
    print(f"[DYNAMIC PINS] Identified {len(deal_slugs)} potential promotional candidates.")
    
    active_deals = []
    mandated_slug_map = {d['url'].split('/')[-1].lower(): d for d in MANDATED_DEALS}
    
    for slug, raw_title in deal_slugs.items():
        slug_lower = slug.lower()
        full_url = f"{BASE_URL}/{slug}"
        
        # Check if we have pre-known deal metadata
        pre = mandated_slug_map.get(slug_lower)
        deal_id = pre['id'] if pre else None
        deal_name = pre['name'] if pre else raw_title
        
        # If ID not pre-known or to verify freshness, fetch page
        html = fetch_html(full_url)
        if html:
            extracted_id, extracted_name = extract_deal_id_and_title(slug, html)
            if extracted_id:
                deal_id = extracted_id
                if extracted_name and not pre:
                    deal_name = extracted_name
        
        if not deal_id and pre:
            deal_id = pre['id']
            
        if deal_id:
            # Verify that the deal API returns live items
            ok, total = verify_deal_api(deal_id)
            if ok:
                print(f"  [+] Active Deal: {deal_name} ({slug}) -> ID: {deal_id} ({total} live items)")
                active_deals.append({
                    "name": deal_name,
                    "url": full_url,
                    "id": deal_id,
                    "type": "deal",
                    "enabled": True
                })
            else:
                print(f"  [-] Deal {deal_name} ({slug}) returned 0 items on API, skipping.")
        else:
            print(f"  [?] Could not resolve Deal ID for {slug}, skipping.")

    # Guarantee all 7 user-mandated deals are present if any network transient occurred
    active_urls = {d['url'] for d in active_deals}
    for md in MANDATED_DEALS:
        if md['url'] not in active_urls:
            active_deals.append(md)
            print(f"  [+] Injected mandated deal fallback: {md['name']} ({md['id']})")

    # Update categories.json
    update_categories_json(active_deals)
    return active_deals

def update_categories_json(active_deals):
    if not os.path.exists(CATEGORIES_FILE):
        logger.error(f"Cannot update categories: {CATEGORIES_FILE} not found.")
        return

    try:
        with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read {CATEGORIES_FILE}: {e}")
        return

    # Find or create pinned_deals group
    groups = data.get('groups', [])
    pinned_group = next((g for g in groups if g.get('id') == 'pinned_deals'), None)
    
    if not pinned_group:
        pinned_group = {
            "id": "pinned_deals",
            "name": "PINNED DEALS",
            "icon": "thumbtack",
            "expanded": True,
            "categories": []
        }
        groups.insert(0, pinned_group)
    else:
        # Move pinned_deals to index 0 so it's always top of sidebar
        groups.remove(pinned_group)
        groups.insert(0, pinned_group)

    # Index active deals by URL
    active_by_url = {d['url']: d for d in active_deals}
    
    # Update existing categories in pinned_group or add new
    updated_categories = []
    seen_urls = set()

    # First add all active deals in order
    for d in active_deals:
        updated_categories.append(d)
        seen_urls.add(d['url'])

    # Then check any previous categories in pinned_group that weren't in active_deals
    for c in pinned_group.get('categories', []):
        url = c.get('url', '')
        if url and url not in seen_urls:
            # Mark dead/expired campaigns as disabled
            c['enabled'] = False
            updated_categories.append(c)
            seen_urls.add(url)

    pinned_group['categories'] = updated_categories
    pinned_group['expanded'] = True

    # Persist updated categories.json
    with open(CATEGORIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    print(f"[DYNAMIC PINS] Successfully updated {CATEGORIES_FILE} ({len(active_deals)} active deals pinned).")

# Global export of pinned categories for imports
try:
    if os.path.exists(CATEGORIES_FILE):
        with open(CATEGORIES_FILE, 'r', encoding='utf-8') as _cf:
            _cdata = json.load(_cf)
            _pg = next((g for g in _cdata.get('groups', []) if g.get('id') == 'pinned_deals'), None)
            if _pg:
                PINNED_CATEGORIES = [c for c in _pg.get('categories', []) if c.get('enabled', True)]
            else:
                PINNED_CATEGORIES = MANDATED_DEALS
    else:
        PINNED_CATEGORIES = MANDATED_DEALS
except Exception:
    PINNED_CATEGORIES = MANDATED_DEALS

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    sync_dynamic_deals()
