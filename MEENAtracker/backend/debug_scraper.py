import asyncio
from playwright.async_api import async_playwright

async def debug_fish_category():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating to Fish category...")
        await page.goto("https://meenabazaronline.com/category/fish", wait_until="networkidle", timeout=60000)
        
        print("Waiting 10 seconds for Angular to render...")
        await asyncio.sleep(10)
        
        # Check if there are ANY products
        app_thumbs = await page.query_selector_all('app-thumb')
        print(f"Found {len(app_thumbs)} 'app-thumb' elements.")
        
        if len(app_thumbs) == 0:
            print("Checking alternative selectors...")
            products = await page.query_selector_all('.product-thumb')
            print(f"Found {len(products)} '.product-thumb' elements.")
            
            print("\nPage text snippet:")
            body_text = await page.inner_text("body")
            print(body_text[:1000])  # Print the first 1000 chars to see what's on the screen
            
            # Save screenshot for visual debugging
            await page.screenshot(path="fish_debug.png", full_page=True)
            print("\nSaved screenshot to fish_debug.png")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_fish_category())
