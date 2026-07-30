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

CONCURRENCY_LIMIT = 10
semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

def get_ts():
    return datetime.datetime.now(DHAKA_TZ).strftime("%H:%M:%S")

async def scrape_page(page, url, page_num):
    sep = '&' if '?' in url else '?'
    target = f"{url}{sep}pageSize=80&pageNumber={page_num}"
    try:
        await page.goto(target, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(0.5)
        
        title = await page.title()
        if "Attention Required" in title or "Cloudflare" in title or "Just a moment" in title:
            print(f"[ERROR] Blocked by Cloudflare/WAF on {url}")
            return [], 0
            
        content = await page.content()
        soup = BeautifulSoup(content, 'lxml')
        
        wraps = soup.select('div.product-wrap') or soup.select('div.product-item') or soup.select('div.item-box') or soup.select('.product-item-container')
        
        data = []
        for i, wrap in enumerate(wraps):
            p_id = (
                wrap.get('data-productid') or 
                (wrap.select_one('input.dl-product-id').get('value') if wrap.select_one('input.dl-product-id') else None) or
                (wrap.select_one('[id^="price_"]').get('id').split('_')[-1] if wrap.select_one('[id^="price_"]') else None) or
                (wrap.select_one('.new-price').get('id').split('_')[-1] if wrap.select_one('.new-price') and wrap.select_one('.new-price').get('id') else f"g_{page_num}_{i}")
            )
            
            name_el = wrap.select_one('.product-name a') or wrap.select_one('.title a') or wrap.select_one('h2.product-title a')
            name = name_el.text.strip() if name_el else "Unknown"
            
            price = 0.0
            price_el = wrap.select_one(f'#price_{p_id}') or wrap.select_one('[id^="price_"]') or wrap.select_one('.new-price') or wrap.select_one('.price.actual-price')
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

async def sector_worker(context, url, idx, total, summary, existing_pids, existing_ph):
    async with semaphore:
        page = await context.new_page()
        await page.route('**/*', lambda r: r.abort() if r.request.resource_type in ['image', 'stylesheet', 'font', 'media'] else r.continue_())
        pn = 1
        total_indexed = 0
        db = SessionLocal()
        try:
            while True:
                items, count = await scrape_page(page, url, pn)
                if not items: break
                
                now = datetime.datetime.now(DHAKA_TZ).replace(tzinfo=None)
                new_products = []
                new_histories = []
                
                for d in items:
                    if d['id'] not in existing_pids:
                        p = Product(id=d['id'], name=d['name'], vendor_name=d['vendor'], category_name=d['category'], image_url=d['img'], extracted_unit_type=d['ut'], extracted_unit_value=d['uv'])
                        new_products.append(p)
                        existing_pids.add(d['id'])
                        summary['new'] += 1
                        
                    if d['price'] > 0 and d['id'] not in existing_ph:
                        new_histories.append(PriceHistory(product_id=d['id'], price_amount=d['price'], timestamp=now))
                        existing_ph.add(d['id'])
                    
                    summary['total'] += 1
                    summary['categories'][d['category']] += 1

                if new_products:
                    db.bulk_save_objects(new_products)
                if new_histories:
                    db.bulk_save_objects(new_histories)
                db.commit()
                
                total_indexed += len(items)
                if count < 80: break
                pn += 1
                if pn > 5: break
        except Exception as e:
            print(f"[ERROR] Exception in sector {idx}: {e}")
        finally:
            await page.close()
            db.close()
        print(f"[{get_ts()}] [OK] Sector {idx}/{total} Finished. {total_indexed} items.")

import time

async def capture_and_send_ss(page, caption=""):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ss_path = os.path.join(base_dir, f"error_{int(time.time())}.png")
        await page.screenshot(path=ss_path, full_page=False)
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        if bot_token and chat_id:
            import requests
            with open(ss_path, 'rb') as f:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                    files={"photo": f},
                    data={"chat_id": chat_id, "caption": caption[:200]},
                    timeout=30
                )
    except Exception as ex:
        print(f"[ERROR] Failed to capture/send browser screenshot: {ex}")

async def check_geo_block(browser, test_url):
    page = await browser.new_page()
    try:
        await page.goto(test_url, wait_until="domcontentloaded", timeout=12000)
        title = await page.title()
        content = await page.content()
        soup = BeautifulSoup(content, 'lxml')
        wraps = soup.select('div.product-wrap') or soup.select('div.product-item')
        if "Attention Required" in title or "Cloudflare" in title or "Just a moment" in title or len(wraps) == 0:
            await capture_and_send_ss(page, f"Othoba Geo-Block/Stuck Screenshot ({title[:50]})")
            return True
        return False
    except Exception as e:
        await capture_and_send_ss(page, f"Othoba Load Exception ({str(e)[:50]})")
        return True
    finally:
        await page.close()


async def main():
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    init_db()
    if not os.path.exists('urls.txt'): return
    with open('urls.txt', 'r') as f: urls = [l.strip() for l in f if l.strip()]

    # Pre-fetch existing IDs for fast in-memory lookup across sectors
    db = SessionLocal()
    existing_pids = set(r[0] for r in db.query(Product.id).all())
    today_date = datetime.datetime.now(DHAKA_TZ).date()
    from sqlalchemy import Date as SaDate
    existing_ph = set(r[0] for r in db.query(PriceHistory.product_id).filter(PriceHistory.timestamp.cast(SaDate) == today_date).all())
    db.close()

    proxy_server = os.environ.get('SCRAPER_PROXY') or os.environ.get('HTTP_PROXY')
    launch_kwargs = {'headless': True}
    if proxy_server:
        launch_kwargs['proxy'] = {'server': proxy_server}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9,bn;q=0.8',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1'
            }
        )

        # Early Geo-block Check on non-BD IP
        if urls:
            is_blocked = await check_geo_block(context, urls[0])
            if is_blocked:
                print("[WARN] Othoba site blocked or returning 0 items on non-BD IP (Cloudflare/WAF Geo-Lock). Exiting early to prevent 3hr timeout.")
                save_last_run_log(summary)
                await browser.close()
                return

        tasks = [sector_worker(context, url, i+1, len(urls), summary, existing_pids, existing_ph) for i, url in enumerate(urls)]
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
