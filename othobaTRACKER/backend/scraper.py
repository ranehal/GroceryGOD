import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import asyncio
import datetime
from collections import Counter
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from models import Product, PriceHistory
from utils import parse_unit
from database import SessionLocal, init_db

CONCURRENCY_LIMIT = 3
semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

def get_ts():
    return datetime.datetime.now(DHAKA_TZ).strftime("%H:%M:%S")

async def scrape_page(page, url, page_num):
    sep = '&' if '?' in url else '?'
    target = f"{url}{sep}pageSize=80&pageNumber={page_num}"
    try:
        await page.goto(target, wait_until="load", timeout=45000)
        await asyncio.sleep(3)
        
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(0.5)
            
        title = await page.title()
        if "Attention Required" in title or "Cloudflare" in title:
            print(f"[ERROR] Blocked by Cloudflare on {url}")
            return [], 0
            
        content = await page.content()
        soup = BeautifulSoup(content, 'lxml')
        
        wraps = soup.select('div.product-wrap') or soup.select('div.product-item') or soup.select('div.item-box') or soup.select('.product-item-container')
        
        data = []
        for i, wrap in enumerate(wraps):
            p_id = (
                wrap.get('data-productid') or 
                (wrap.select_one('input.dl-product-id').get('value') if wrap.select_one('input.dl-product-id') else None) or
                (wrap.select_one('.new-price').get('id').split('_')[-1] if wrap.select_one('.new-price') and wrap.select_one('.new-price').get('id') else f"g_{page_num}_{i}")
            )
            
            name_el = wrap.select_one('.product-name a') or wrap.select_one('.title a') or wrap.select_one('h2.product-title a')
            name = name_el.text.strip() if name_el else "Unknown"
            
            price = 0.0
            price_el = wrap.select_one(f'#price_{p_id}') or wrap.select_one('.new-price') or wrap.select_one('.price.actual-price')
            if price_el:
                clean = re.sub(r'[^\d.]', '', price_el.text.replace(',', ''))
                if clean: price = float(clean)

            vendor_el = wrap.select_one('input.dl-vendor-name') or wrap.select_one('.vendor-name')
            vendor = vendor_el.get('value') if vendor_el and vendor_el.name == 'input' else (vendor_el.text.strip() if vendor_el else "Independent")
            
            category_el = wrap.select_one('input.dl-category-name')
            category = category_el.get('value') if category_el else url.split('/')[-1]
            
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

async def sector_worker(context, url, idx, total, summary):
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
                    summary['new'] += 1
                if d['price'] > 0:
                    from sqlalchemy import Date as SaDate
                    now = datetime.datetime.now(DHAKA_TZ).replace(tzinfo=None)
                    today_date = now.date()
                    existing = db.query(PriceHistory).filter(
                        PriceHistory.product_id == d['id'],
                        PriceHistory.timestamp.cast(SaDate) == today_date
                    ).first()
                    if existing:
                        existing.price_amount = d['price']
                        existing.timestamp = now
                    else:
                        db.add(PriceHistory(product_id=d['id'], price_amount=d['price'], timestamp=now))
                
                summary['total'] += 1
                summary['categories'][d['category']] += 1

            db.commit()
            total_indexed += len(items)
            if count == 0: break
            pn += 1
            if pn > 10: break
        await page.close()
        db.close()
        print(f"[{get_ts()}] [OK] Sector {idx} Finished. {total_indexed} items.")

async def main():
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    init_db()
    if not os.path.exists('urls.txt'): return
    with open('urls.txt', 'r') as f: urls = [l.strip() for l in f if l.strip()]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={'Accept-Language': 'en-US,en;q=0.9'}
        )
        tasks = [sector_worker(context, url, i+1, len(urls), summary) for i, url in enumerate(urls)]
        await asyncio.gather(*tasks)
        save_last_run_log(summary)
        await browser.close()

def save_last_run_log(summary):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base_dir, "last_run_log.txt")
    with open(log_path, "w", encoding='utf-8') as f:
        f.write(f"Last Run: {datetime.datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("-" * 30 + "\n")
        f.write(f"Total Scraped: {summary['total']}\n")
        f.write(f"New Items: {summary.get('new', 'N/A')}\n")
        f.write("-" * 30 + "\n")
        f.write("Categories:\n")
        for cat, count in sorted(summary['categories'].items(), key=lambda x: x[1], reverse=True)[:10]:
            f.write(f"- {cat}: {count}\n")
        if len(summary['categories']) > 10:
            f.write(f"... and {len(summary['categories']) - 10} more.")

if __name__ == "__main__":
    asyncio.run(main())
