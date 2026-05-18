import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        page = await context.new_page()
        
        for url in ["https://www.shwapno.com/deals", "https://www.shwapno.com/buy-save-more-2"]:
            print(f"\n--- Checking {url} ---")
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(5)
            
            # Check for any elements with common product-related strings in class
            elements = await page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('*').forEach(el => {
                    const cls = el.className || '';
                    if (typeof cls === 'string' && (cls.includes('product') || cls.includes('item') || cls.includes('box'))) {
                        results.push({tag: el.tagName, class: cls, text: el.innerText.substring(0, 30)});
                    }
                });
                return results.slice(0, 20);
            }""")
            print("Sample product-like elements:")
            for e in elements:
                print(f"[{e['tag']}] {e['class']} | '{e['text']}'")
                
            # Specifically check for any <a> or <div> that might be a card
            cards = await page.query_selector_all('div[class*="product"], div[class*="item"]')
            print(f"Total potential cards: {len(cards)}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
