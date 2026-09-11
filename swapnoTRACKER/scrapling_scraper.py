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

# Banasree Block C Location Specifications
BANASREE_LOCATION = {
    "stateProvinceId": "65eb61bd452e887cd78e240d",
    "cityId": "65ed4befe30f25b233e5f48d",
    "areaId": "686f4fdee45b27590891fd90",
    "district": "Dhaka",
    "area": "Banasree Block C",
    "darkStoreId": "65f008e64119aecf652223f1",
    "darkStoreName": "Banasree "
}

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


def set_banasree_slot_api() -> dict | None:
    """Configures Shwapno session directly via delivery-slot endpoint."""
    payload = json.dumps({
        "stateProvinceId": BANASREE_LOCATION["stateProvinceId"],
        "cityId": BANASREE_LOCATION["cityId"],
        "areaId": BANASREE_LOCATION["areaId"]
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
            logger.info(f"Banasree Darkstore locked via API -> {ds_name} ({ds_id})")
            return data
    except Exception as e:
        logger.warning(f"Failed setting Banasree slot via API: {e}")
        return None


def scrapling_select_banasree_form(page):
    """
    Scrapling page_action callback:
    Interacts with Shwapno's location selection modal form:
    <form>
      <input placeholder="Select district" ...> -> Selects 'Dhaka'
      <input placeholder="Select area" ...> -> Selects 'Banasree Block C'
      <button type="submit">Done</button>
    </form>
    """
    try:
        # Check if delivery slot trigger is present
        slot_btn = page.query_selector('#deliverySlotButton')
        if slot_btn:
            slot_btn.click()
            page.wait_for_timeout(500)

        # District Combobox
        district_input = page.wait_for_selector('input[placeholder="Select district"]', timeout=8000)
        if district_input:
            district_input.click()
            page.wait_for_timeout(300)
            dhaka_opt = page.wait_for_selector('xpath=//div[@role="option"][contains(., "Dhaka")]', timeout=6000)
            if dhaka_opt:
                dhaka_opt.click()
                page.wait_for_timeout(600)

        # Area Combobox
        area_input = page.wait_for_selector('input[placeholder="Select area"]', timeout=8000)
        if area_input:
            area_input.click()
            page.wait_for_timeout(300)
            banasree_c_opt = page.wait_for_selector('xpath=//div[@role="option"][contains(., "Banasree Block C")]', timeout=6000)
            if banasree_c_opt:
                banasree_c_opt.click()
                page.wait_for_timeout(400)

        # Done Button
        done_btn = page.wait_for_selector('button[type="submit"]:has-text("Done")', timeout=5000)
        if done_btn:
            done_btn.click()
            page.wait_for_timeout(1500)

        # Ensure cookie is explicitly set in context
        page.context.add_cookies([{
            'name': '_ds_',
            'value': BANASREE_LOCATION['darkStoreId'],
            'domain': '.shwapno.com',
            'path': '/'
        }])
        logger.info("Scrapling form successfully selected Banasree Block C.")
    except Exception as e:
        logger.warning(f"Scrapling form interaction notice: {e}")
        # Ensure cookie is forced in browser context
        try:
            page.context.add_cookies([{
                'name': '_ds_',
                'value': BANASREE_LOCATION['darkStoreId'],
                'domain': '.shwapno.com',
                'path': '/'
            }])
        except: pass


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
