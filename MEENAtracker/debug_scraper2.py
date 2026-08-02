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
        
        # Try to find and dismiss the delivery area modal
        try:
            print("Looking for delivery area modal...")
            # We will try to click the backdrop or a close button
            # Let's try to evaluate some JS to find the modal and close it
            await page.evaluate("""() => {
                const closeBtn = document.querySelector('.ant-modal-close');
                if (closeBtn) {
                    console.log('Found close btn');
                    closeBtn.click();
                } else {
                    console.log('No close btn found');
                }
            }""")
            
            await asyncio.sleep(5)
            
            app_thumbs = await page.query_selector_all('app-thumb')
            print(f"Found {len(app_thumbs)} 'app-thumb' elements after attempting to close modal.")
            
        except Exception as e:
            print(f"Error handling modal: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_fish_category())
