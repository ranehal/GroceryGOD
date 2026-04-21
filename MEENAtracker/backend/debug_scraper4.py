import asyncio
from playwright.async_api import async_playwright

async def debug_fish_category():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating to Fish category...")
        await page.goto("https://meenabazaronline.com/category/fish", wait_until="networkidle", timeout=60000)
        
        print("Waiting 5 seconds...")
        await asyncio.sleep(5)
        
        inputs = await page.query_selector_all('input')
        for inp in inputs:
            placeholder = await inp.get_attribute('placeholder')
            class_name = await inp.get_attribute('class')
            print(f"Input placeholder: {placeholder}, class: {class_name}")
            
        print("\nChecking for any button that might be a location selector:")
        buttons = await page.query_selector_all('button')
        for btn in buttons:
            text = await btn.inner_text()
            if text and 'area' in text.lower() or 'location' in text.lower():
                print(f"Found button with text: {text.strip()}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_fish_category())
