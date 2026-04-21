import asyncio
import datetime
import re
import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from models import Product, PriceHistory
from utils import parse_unit
from database import SessionLocal, init_db

CONCURRENCY_LIMIT = 3 # Lowered slightly for stability
semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

def get_ts():
    return datetime.datetime.now().strftime("%H:%M:%S")

async def scrape_page(page, url, page_num):
    sep = '&' if '?' in url else '?'
    target = f"{url}{sep}pageSize=80&pageNumber={page_num}"
    try:
        # Wait for full load and extra rendering time
        await page.goto(target, wait_until="load", timeout=45000)
        await asyncio.sleep(3)
        
        # Incremental scroll for lazy loaders
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(0.5)
            
        title = await page.title()
        if "Attention Required" in title or "Cloudflare" in title:
            print(f"[ERROR] Blocked by Cloudflare on {url}")
            return [], 0
            
        content = await page.content()
        soup = BeautifulSoup(content, 'lxml')
        
        # Expanded selectors for Othoba's various layouts
        wraps = soup.select('div.product-wrap') or soup.select('div.product-item') or soup.select('div.item-box') or soup.select('.product-item-container')
        
        data = []
        for i, wrap in enumerate(wraps):
            # Dynamic ID detection
            p_id = (
                wrap.get('data-productid') or 
                (wrap.select_one('input.dl-product-id').get('value') if wrap.select_one('input.dl-product-id') else None) or
                (wrap.select_one('.new-price').get('id').split('_')[-1] if wrap.select_one('.new-price') and wrap.select_one('.new-price').get('id') else f"g_{page_num}_{i}")
            )
            
            # Robust name detection
            name_el = wrap.select_one('.product-name a') or wrap.select_one('.title a') or wrap.select_one('h2.product-title a')
            name = name_el.text.strip() if name_el else "Unknown"
            
            # Multi-selector price parsing
            price = 0.0
            price_el = wrap.select_one(f'#price_{p_id}') or wrap.select_one('.new-price') or wrap.select_one('.price.actual-price')
            if price_el:
                clean = re.sub(r'[^\d.]', '', price_el.text.replace(',', ''))
                if clean: price = float(clean)

            # Vendor and Category data layer detection
            vendor_el = wrap.select_one('input.dl-vendor-name') or wrap.select_one('.vendor-name')
            vendor = vendor_el.get('value') if vendor_el and vendor_el.name == 'input' else (vendor_el.text.strip() if vendor_el else "Independent")
            
            category_el = wrap.select_one('input.dl-category-name')
            category = category_el.get('value') if category_el else url.split('/')[-1]
            
            # Image source detection including lazy loading attributes
            img = wrap.select_one('.product-media img') or wrap.select_one('.picture img')
            img_url = ""
            if img:
                img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or ""
                if img_url.startswith('//'): img_url = "https:" + img_url
            
            ut, uv = parse_unit(name)
            data.append({'id': p_id, 'name': name, 'vendor': vendor, 'category': category, 'img': img_url, 'price': price, 'ut': ut, 'uv': uv})
        
        return data, len(wraps)
    except Exception as e:
        print(f"[ERROR] Scrape failed for {url}: {str(e)[:100]}")
        return [], 0

async def sector_worker(context, url, idx, total):
    async with semaphore:
        page = await context.new_page()
        pn = 1
        total_indexed = 0
        db = SessionLocal()
        while True:
            print(f"[{get_ts()}] [S {idx}/{total}] [P {pn}] Scanning sector...")
            items, count = await scrape_page(page, url, pn)
            if not items: break
            
            for d in items:
                p = db.query(Product).filter(Product.id == d['id']).first()
                if not p:
                    p = Product(id=d['id'], name=d['name'], vendor_name=d['vendor'], category_name=d['category'], image_url=d['img'], extracted_unit_type=d['ut'], extracted_unit_value=d['uv'])
                    db.add(p)
                if d['price'] > 0:
                    db.add(PriceHistory(product_id=d['id'], price_amount=d['price'], timestamp=datetime.datetime.now(datetime.timezone.utc)))
            db.commit()
            total_indexed += len(items)
            # Some pages have fewer than 80 but more than 0 items
            if count == 0: break
            pn += 1
            if pn > 10: break
        await page.close()
        db.close()
        print(f"[{get_ts()}] [OK] Sector {idx} Finished. {total_indexed} items.")

async def main():
    init_db()
    if not os.path.exists('urls.txt'): return
    with open('urls.txt', 'r') as f: urls = [l.strip() for l in f if l.strip()]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Standard desktop User-Agent to prevent basic headless detection
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        tasks = [sector_worker(context, url, i+1, len(urls)) for i, url in enumerate(urls)]
        await asyncio.gather(*tasks)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
