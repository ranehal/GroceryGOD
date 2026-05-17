import asyncio
from playwright.async_api import async_playwright
import json
import os

async def run():
    if not os.path.exists("unimartTRACKER"):
        os.makedirs("unimartTRACKER")
        
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Fetching Unimart categories...")
        await page.goto("https://www.unimart.online/categories", wait_until="networkidle")
        
        # Extract category links
        links = await page.query_selector_all('a[href*="/category/"]')
        categories = []
        for link in links:
            name = await link.inner_text()
            url = await link.get_attribute('href')
            if name.strip() and url:
                full_url = url if url.startswith('http') else f"https://www.unimart.online{url}"
                categories.append({"name": name.strip(), "url": full_url, "enabled": True})
        
        # Deduplicate
        unique_cats = {}
        for c in categories:
            if c['name'] not in unique_cats:
                unique_cats[c['name']] = c
        
        result = {"groups": [{"name": "All Categories", "categories": list(unique_cats.values())}], "custom": []}
        
        with open("unimartTRACKER/categories.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        
        print(f"Extracted {len(unique_cats)} categories to unimartTRACKER/categories.json")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
