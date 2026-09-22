#!/usr/bin/env python3
"""
Shwapno Scrapling Scraper — Banasree C Location Engine
------------------------------------------------------
Automates Shwapno location selection and product scraping specifically for
Banasree Block C using Scrapling (Playwright/Stealth) and Shwapno Delivery-Slot API.

Location Parameters:
  - District (stateProvinceId): 65eb61bd452e887cd78e240d (Dhaka)
  - Thana/City (cityId):        65ed4befe30f25b233e5f48d (Rampura)
  - Area (areaId):              686f4fdee45b27590891fd90 (Banasree Block C)
  - Resolved Darkstore ID:      65f008e64119aecf652223f1 (Banasree)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import urllib.request
import ssl
from datetime import datetime, timedelta, timezone

DHAKA_TZ = timezone(timedelta(hours=6))

# Complete Location Sequence
# Selector: #main-header > div.z-50.bg-main > div > div.relative.z-[99].ml-auto.hidden.min-w-[180px].max-w-[220px].cursor-pointer.md:block.xl:ml-10.\32 xl:ml-auto > span
STORE_LOCATIONS = [
    {
        "area": "Banasree Block C",
        "district": "Dhaka",
        "stateProvinceId": "65eb61bd452e887cd78e240d",
        "cityId": "65ed4befe30f25b233e5f48d",
        "areaId": "686f4fdee45b27590891fd90",
        "darkStoreId": "65f008e64119aecf652223f1",
        "darkStoreName": "Banasree "
    },
    {
        "area": "Khilgaon Nobabi More",
        "district": "Dhaka",
        "stateProvinceId": "65eb61bd452e887cd78e240d",
        "cityId": "65ed4e91e30f25b233e60142",
        "areaId": "65efdfc34119aecf6521af15",
        "darkStoreId": "65f00cbe101d9be04a6c4d02",
        "darkStoreName": "Sky View"
    },
    {
        "area": "Khilgaon Chowdhury para",
        "district": "Dhaka",
        "stateProvinceId": "65eb61bd452e887cd78e240d",
        "cityId": "65ed4e91e30f25b233e60142",
        "areaId": "65efdfec4119aecf6521b08d",
        "darkStoreId": "65f00cbe101d9be04a6c4d02",
        "darkStoreName": "Sky View"
    },
    {
        "area": "Khilgaon",
        "district": "Dhaka",
        "stateProvinceId": "65eb61bd452e887cd78e240d",
        "cityId": "65ed4e91e30f25b233e60142",
        "areaId": "65efe0004119aecf6521b1c2",
        "darkStoreId": "65f00cbe101d9be04a6c4d02",
        "darkStoreName": "Sky View"
    },
    {
        "area": "Bashabo",
        "district": "Dhaka",
        "stateProvinceId": "65eb61bd452e887cd78e240d",
        "cityId": "65ed4d0ee30f25b233e5f67b",
        "areaId": "65ed55bf452e887cd78e601f",
        "darkStoreId": "65f00a36101d9be04a6c429a",
        "darkStoreName": "Central Basabo 2"
    }
]

BANASREE_LOCATION = STORE_LOCATIONS[0]
DARKSTORE_COOKIE = f"_ds_={BANASREE_LOCATION['darkStoreId']}; _nc_=false; _mo_=false;"

BASE_URL = "https://www.shwapno.com"
DELIVERY_SLOT_API = f"{BASE_URL}/api/delivery-slot/set?set"
CATEGORY_API = f"{BASE_URL}/api/category/products"

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def set_delivery_slot_api(location: dict) -> dict | None:
    """Configures Shwapno session directly via delivery-slot endpoint for any store location."""
    payload = json.dumps({
        "stateProvinceId": location["stateProvinceId"],
        "cityId": location["cityId"],
        "areaId": location["areaId"]
    }).encode("utf-8")

    req = urllib.request.Request(
        DELIVERY_SLOT_API,
        data=payload,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Referer": f"{BASE_URL}/",
            "Origin": BASE_URL,
            "Accept": "application/json, text/plain, */*"
        },
        method="POST"
    )

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ds_id = data.get("darkStoreId")
            ds_name = data.get("darkStoreName")
            logger.info(f"Store Darkstore locked via API -> {location['area']}: {ds_name} ({ds_id})")
            return data
    except Exception as e:
        logger.warning(f"Failed setting slot for {location['area']} via API: {e}")
        return None


def set_banasree_slot_api() -> dict | None:
    return set_delivery_slot_api(BANASREE_LOCATION)


def scrapling_select_store_form(page, target_area: str = "Banasree Block C"):
    """
    Scrapling page_action callback:
    Interacts with Shwapno's location selection modal form:
      1. Clicks location selector: #main-header ... span or #deliverySlotButton
      2. Chooses district: 'Dhaka'
      3. Chooses target area: e.g. 'Banasree Block C', 'Khilgaon Nobabi More', 'Khilgaon Chowdhury para', 'Khilgaon', 'Bashabo'
      4. Submits Done
    """
    loc_meta = next((l for l in STORE_LOCATIONS if l['area'].lower() == target_area.lower()), BANASREE_LOCATION)
    try:
        # Check if delivery slot trigger is present
        slot_btn = page.query_selector('#deliverySlotButton')
        if not slot_btn:
            slot_btn = page.query_selector('#main-header > div.z-50.bg-main > div > div.relative.z-\\[99\\].ml-auto.hidden.min-w-\\[180px\\].max-w-\\[220px\\].cursor-pointer.md\\:block.xl\\:ml-10.\\32 xl\\:ml-auto > span')
        
        if slot_btn:
            slot_btn.click()
            page.wait_for_timeout(500)

        # District Combobox
        district_input = page.wait_for_selector('input[placeholder*="district" i]', timeout=8000)
        if district_input:
            district_input.click()
            page.wait_for_timeout(300)
            dhaka_opt = page.wait_for_selector('xpath=//div[@role="option"][contains(., "Dhaka")]', timeout=6000)
            if dhaka_opt:
                dhaka_opt.click()
                page.wait_for_timeout(600)

        # Area Combobox
        area_input = page.wait_for_selector('input[placeholder*="area" i]', timeout=8000)
        if area_input:
            area_input.click()
            page.wait_for_timeout(300)
            area_opt = page.wait_for_selector(f'xpath=//div[@role="option"][contains(., "{target_area}")]', timeout=6000)
            if area_opt:
                area_opt.click()
                page.wait_for_timeout(400)

        # Done Button
        done_btn = page.wait_for_selector('button[type="submit"]:has-text("Done")', timeout=5000)
        if done_btn:
            done_btn.click()
            page.wait_for_timeout(1500)

        # Ensure cookie is explicitly set in context
        page.context.add_cookies([{
            'name': '_ds_',
            'value': loc_meta['darkStoreId'],
            'domain': '.shwapno.com',
            'path': '/'
        }])
        logger.info(f"Scrapling form successfully selected {target_area} ({loc_meta['darkStoreId']}).")
    except Exception as e:
        logger.warning(f"Scrapling form interaction notice for {target_area}: {e}")
        try:
            page.context.add_cookies([{
                'name': '_ds_',
                'value': loc_meta['darkStoreId'],
                'domain': '.shwapno.com',
                'path': '/'
            }])
        except: pass


def scrapling_select_banasree_form(page):
    return scrapling_select_store_form(page, "Banasree Block C")


def fetch_category_scrapling(category_slug: str, page_num: int = 1):
    """Fetches a category page using Scrapling StealthyFetcher with Banasree location."""
    try:
        from scrapling import DynamicFetcher
    except ImportError:
        logger.error("Scrapling is not installed.")
        return None

    cookies = [{
        'name': '_ds_',
        'value': BANASREE_LOCATION['darkStoreId'],
        'domain': '.shwapno.com',
        'path': '/'
    }]

    url = f"{BASE_URL}/{category_slug.strip('/')}?page={page_num}"
    logger.info(f"Fetching {url} via Scrapling (Banasree C Darkstore)...")
    return DynamicFetcher.fetch(
        url,
        cookies=cookies,
        page_action=scrapling_select_banasree_form,
        headless=True,
        timeout=30000
    )


def main():
    parser = argparse.ArgumentParser(description="Shwapno Scrapling Banasree C Scraper")
    parser.add_argument("--test-slot", action="store_true", help="Test delivery slot API setup")
    parser.add_argument("--category", default="food", help="Category slug to test fetch")
    args = parser.parse_args()

    slot_info = set_banasree_slot_api()
    if args.test_slot:
        print(json.dumps(slot_info, indent=2))
        return

    res = fetch_category_scrapling(args.category)
    if res:
        print(f"Fetch completed. HTTP Status: {getattr(res, 'status', 200)}")


if __name__ == "__main__":
    main()
