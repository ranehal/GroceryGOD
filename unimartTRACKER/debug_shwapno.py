import asyncio
from playwright.async_api import async_playwright

async def debug_shwapno_deals():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        url = "https://www.shwapno.com/deals"
        print(f"Visiting {url}...")
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(5)
        
        # Check standard selector
        items = await page.query_selector_all('.product-box')
        print(f"Standard .product-box items: {len(items)}")
        
        # Check user's XPath
        xpath = "/html/body/main/div"
        container = await page.query_selector(f"xpath={xpath}")
        if container:
            items_in_xpath = await container.query_selector_all('.product-box')
            print(f"Items inside XPath {xpath}: {len(items_in_xpath)}")
        else:
            print(f"XPath {xpath} not found!")

        # Check for any other product-like containers
        products = await page.query_selector_all('div[class*="product"]')
        print(f"Divs with 'product' in class: {len(products)}")
        
        # Check for tabs on Buy Save More
        url2 = "https://www.shwapno.com/buy-save-more-2"
        print(f"\nVisiting {url2}...")
        await page.goto(url2, wait_until="networkidle")
        await asyncio.sleep(5)
        tabs = await page.query_selector_all('.category-tab-list .category-tab, .category-tab-list div, .nav-tabs li a')
        print(f"Found {len(tabs)} tabs.")
        for t in tabs:
            text = await t.inner_text()
            if text.strip():
                print(f"  - Tab: '{text.strip()}'")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_shwapno_deals())
