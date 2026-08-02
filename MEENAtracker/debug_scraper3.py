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
        
        try:
            # Let's try to type into the delivery area search
            print("Trying to type into delivery area...")
            await page.fill('input[placeholder="Type your delivery area"]', 'Dhanmondi')
            await asyncio.sleep(2)
            
            # Press enter or click the first result
            print("Pressing enter or clicking result...")
            await page.keyboard.press('Enter')
            await asyncio.sleep(2)
            
            # Sometimes there's a list we need to click
            items = await page.query_selector_all('.ant-select-item-option-content')
            if items:
                print("Clicking first location option...")
                await items[0].click()
                await asyncio.sleep(5)
                
            app_thumbs = await page.query_selector_all('app-thumb')
            print(f"Found {len(app_thumbs)} 'app-thumb' elements after selecting area.")
            
        except Exception as e:
            print(f"Error handling modal: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_fish_category())
