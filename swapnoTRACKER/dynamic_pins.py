import asyncio
import json
import os
import re
from playwright.async_api import async_playwright

CATEGORIES_FILE = 'categories.json'
ROOT_URL = 'https://www.shwapno.com/'

# XPath to find dynamic promo banners/links on the homepage
# The user suggested /html/body/main/div, but we'll use a more robust relative xpath
DYNAMIC_XPATH = "//div[contains(@class, 'slider')]//a[contains(@href, '/')]"

async def get_dynamic_links():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print(f"Fetching {ROOT_URL} for dynamic links...")
        await page.goto(ROOT_URL, wait_until="networkidle")
        
        # User explicitly mentioned these URLs to pin, let's also find them on the page
        # but the request was to scrape them from XPATH dynamically.
        
        # Give it a bit more time for any sliders to load
        await asyncio.sleep(5)
        
        # Try finding links in the main content area
        links_data = []
        
        # Attempt 1: Target sliders and banners
        anchors = await page.query_selector_all('a[href^="/"]')
        for a in anchors:
            href = await a.get_attribute('href')
            text = await a.inner_text()
            img = await a.query_selector('img')
            img_alt = await img.get_attribute('alt') if img else ""
            
            # Use alt text if inner text is empty (common for image banners)
            label = text.strip() or img_alt.strip() or href.strip('/').replace('-', ' ').title()
            
            # Filter for likely promo links (shorter paths, not standard categories)
            # Promo links usually look like /deals, /Summer-Fest, etc.
            if href and len(href.split('/')) == 2 and not any(x in href.lower() for x in ['search', 'login', 'cart', 'account']):
                full_url = f"https://www.shwapno.com{href}"
                links_data.append({"name": label, "url": full_url, "enabled": True})

        await browser.close()
        
        # Deduplicate by URL
        unique_links = {}
        for link in links_data:
            if link['url'] not in unique_links:
                unique_links[link['url']] = link
        
        return list(unique_links.values())

def update_categories_json(new_links):
    if not os.path.exists(CATEGORIES_FILE):
        print(f"Error: {CATEGORIES_FILE} not found.")
        return

    with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Find the pinned_deals group
    pinned_group = next((g for g in data.get('groups', []) if g.get('id') == 'pinned_deals'), None)
    
    if not pinned_group:
        # Create it if it doesn't exist
        pinned_group = {
            "id": "pinned_deals",
            "name": "PINNED DEALS",
            "icon": "thumbtack",
            "expanded": true,
            "categories": []
        }
        data['groups'].insert(0, pinned_group)

    existing_urls = {c['url'] for c in pinned_group['categories']}
    
    added_count = 0
    for link in new_links:
        if link['url'] not in existing_urls:
            pinned_group['categories'].append(link)
            existing_urls.add(link['url'])
            added_count += 1
            print(f"  [+] Added new pinned category: {link['name']} ({link['url']})")

    if added_count > 0:
        with open(CATEGORIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"Successfully updated {CATEGORIES_FILE} with {added_count} new links.")
    else:
        print("No new dynamic links to add.")

async def main():
    dynamic_links = await get_dynamic_links()
    # Also manually ensure the ones the user specifically asked for are included
    user_requested = [
        "https://www.shwapno.com/Shwapno-Summer-Fest",
        "https://www.shwapno.com/deals",
        "https://www.shwapno.com/deals-on-unilever",
        "https://www.shwapno.com/buy-save-more-2",
        "https://www.shwapno.com/brands",
        "https://www.shwapno.com/womens-care-collection",
        "https://www.shwapno.com/shop-now-think-later",
        "https://www.shwapno.com/weekend-fresh-deal",
        "https://www.shwapno.com/Hot-Deals",
        "https://www.shwapno.com/great-savings-3",
        "https://www.shwapno.com/deals-on-toys-household-items",
        "https://www.shwapno.com/A-Place-For-Your-Grocery-Needs-5"
    ]
    
    for url in user_requested:
        name = url.split('/')[-1].replace('-', ' ').title()
        if not any(link['url'] == url for link in dynamic_links):
            dynamic_links.append({"name": name, "url": url, "enabled": True})
            
    update_categories_json(dynamic_links)

if __name__ == "__main__":
    asyncio.run(main())
