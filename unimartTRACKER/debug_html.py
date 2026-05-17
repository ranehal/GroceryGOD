import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Fetching Unimart Dairy category...")
        await page.goto("https://www.unimart.online/category/dairy", wait_until="networkidle")
        await asyncio.sleep(5)
        content = await page.content()
        with open("unimart_debug.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("HTML dumped to unimart_debug.html")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
