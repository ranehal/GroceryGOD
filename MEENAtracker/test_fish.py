import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        print("Navigating to fish category...")
        await page.goto('https://meenabazaronline.com/category/fish')
        await asyncio.sleep(5)
        print("Waiting for app-thumb...")
        try:
            await page.wait_for_selector('app-thumb', timeout=5000)
            items = await page.query_selector_all('app-thumb')
            print(f"Found {len(items)} app-thumb elements!")
        except Exception as e:
            print(f"Failed to find app-thumb: {e}")
            content = await page.content()
            print("Content excerpt:", content[5000:6000])
        await browser.close()

asyncio.run(main())
