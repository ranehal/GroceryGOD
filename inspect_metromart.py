import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("Navigating to https://www.metromartonline.com/categories ...")
        await page.goto("https://www.metromartonline.com/categories", wait_until="networkidle")
        
        # Get all category links
        cat_links = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('a')).map(a => ({
                text: a.innerText.trim(),
                href: a.href
            })).filter(l => l.href.includes('/shop?category='));
        }''')
        
        print("\n--- Category Links ---")
        for link in cat_links:
            print(f"{link['text']}: {link['href']}")
            
        print("\nTrying search for 'dairy'...")
        await page.goto("https://www.metromartonline.com/shop?q=dairy", wait_until="networkidle")
        
        # Check if products are listed
        products = await page.query_selector_all('a[href*="/product/"]')
        print(f"Found {len(products)} products for 'dairy' search.")
        
        print("\nChecking for 'Load More' button...")
        load_more_btn = await page.query_selector('button:has-text("Load More")')
        if load_more_btn:
            print("Found 'Load More' button.")
        else:
            print("Did NOT find 'Load More' button.")
            
        # Scroll to bottom and check if more products appear or if it's infinite scroll
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)
        new_products = await page.query_selector_all('a[href*="/product/"]')
        print(f"Products after scroll: {len(new_products)}")

            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
