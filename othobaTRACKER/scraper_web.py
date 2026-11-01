import os

import random
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import asyncio
import datetime
import html
import tempfile
import time
from collections import Counter
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from models import Product, PriceHistory
from utils import parse_unit
from database import SessionLocal, init_db

CONCURRENCY_LIMIT = 10
semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

# Othoba renders product cards with JavaScript. A page that has finished
# downloading but has not rendered yet is NOT a geo-block, so the probe below
# waits for these selectors before deciding anything.
PRODUCT_SELECTOR = (
    'div.product-wrap, div.product-item, div.item-box, '
    '.product-item-container'
)
# Title markers are safe to search in the title only. Body markers are
# challenge-specific; never treat a normal page that merely references a
# Cloudflare CDN asset as blocked.
TITLE_BLOCK_MARKERS = (
    'attention required',
    'cloudflare',
    'just a moment',
    'access denied',
)
BODY_BLOCK_MARKERS = (
    'you have been blocked',
    'enable javascript and cookies',
    'cf-error',
    'cf-challenge',
    'challenge-platform',
    'error 1020',
    'not available in your country',
    'not available in your region',
    'geo-block',
    'geoblock',
    'request blocked',
    'sorry, you have been blocked',
)


def get_ts():
    return datetime.datetime.now(DHAKA_TZ).strftime("%H:%M:%S")


def _product_wraps(soup):
    return (
        soup.select('div.product-wrap')
        or soup.select('div.product-item')
        or soup.select('div.item-box')
        or soup.select('.product-item-container')
    )


def send_text_alert(message):
    """Send a plain-text diagnostic first; screenshots are optional extras."""
    print(f"[ALERT] {message.replace(chr(10), ' | ')[:600]}")
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id:
        return False
    try:
        import requests
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message[:3900],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        return response.status_code == 200
    except Exception as ex:
        print(f"[ERROR] Failed to send text alert: {ex}")
        return False


def _probe_text(prefix, state, note=""):
    title = html.escape(str(state.get("title", ""))[:120])
    url = html.escape(str(state.get("url", "")))
    status = state.get("status")
    wraps = state.get("wraps", 0)
    content_len = state.get("content_len", 0)
    error = html.escape(str(state.get("error", ""))[:300])
    lines = [
        f"<b>{html.escape(prefix)}</b>",
        f"URL: <code>{url}</code>",
        f"Title: {title}",
        f"HTTP: {status if status is not None else 'n/a'} | "
        f"Product cards: {wraps} | HTML: {content_len} chars",
    ]
    if error:
        lines.append(f"Error: {error}")
    if note:
        lines.append(html.escape(note))
    return "\n".join(lines)


async def scrape_page(page, url, page_num):
    sep = '&' if '?' in url else '?'
    target = f"{url}{sep}pageSize=80&pageNumber={page_num}"
    try:
        await page.goto(target, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_selector(PRODUCT_SELECTOR, timeout=12000)
        except Exception:
            pass
        try:
            await page.wait_for_selector('ins.new-price:not(:empty)', timeout=5000)
        except Exception:
            pass
        await asyncio.sleep(0.4)

        title = await page.title()
        content = await page.content()
        title_lower = title.lower()
        body_lower = content[:120000].lower()
        if (
            any(marker in title_lower for marker in TITLE_BLOCK_MARKERS)
            or any(marker in body_lower for marker in BODY_BLOCK_MARKERS)
        ):
            print(f"[ERROR] Blocked by Cloudflare/WAF on {url} (title={title[:80]})")
            return [], 0

        soup = BeautifulSoup(content, 'lxml')
        wraps = _product_wraps(soup)

        if not wraps:
            print(
                f"[WARN] {target}: 0 product cards after wait "
                f"(page loaded, title={title[:80]}); not treating as geo-block."
            )
            return [], 0

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
            price_el = wrap.select_one(f'#price_{p_id}') or wrap.select_one('.price.actual-price') or wrap.select_one('[id^="price_"]') or wrap.select_one('.new-price')
            if price_el:
                clean = re.sub(r'[^\d.]', '', price_el.text.replace(',', ''))
                if clean: price = float(clean)

            vendor_el = wrap.select_one('input.dl-vendor-name') or wrap.select_one('.vendor-name')
            vendor = vendor_el.get('value') if vendor_el and vendor_el.name == 'input' else (vendor_el.text.strip() if vendor_el else "Independent")

            category_el = wrap.select_one('input.dl-category-name')
            category = category_el.get('value') if category_el else url.split('/')[-1]

            img = wrap.select_one('.product-media img.prdImg') or wrap.select_one('.product-media img') or wrap.select_one('.picture img')
            img_url = ""
            if img:
                img_url = img.get('data-src') or img.get('src') or img.get('data-lazy-src') or ""
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
        retried_first = False
        db = SessionLocal()
        try:
            while True:
                items, count = await scrape_page(page, url, pn)
                if not items:
                    if pn == 1 and not retried_first:
                        retried_first = True
                        print(f"[WARN] Sector {idx}: first page returned 0 items; retrying once...")
                        await asyncio.sleep(3)
                        continue
                    break

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


async def capture_and_send_ss(page, caption="", text_message=None):
    """Send text first, then a best-effort screenshot with a hard timeout.

    A stuck screenshot must never block the scraper or hide the diagnostic.
    The PNG lives in the temp directory and is deleted afterwards so it can
    never be committed to the repo.
    """
    if text_message:
        send_text_alert(text_message)

    ss_path = os.path.join(
        tempfile.gettempdir(), f"othoba_error_{int(time.time())}.png"
    )
    try:
        await asyncio.wait_for(
            page.screenshot(path=ss_path, full_page=False, timeout=10000),
            timeout=15,
        )
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        if bot_token and chat_id and os.path.getsize(ss_path) > 0:
            import requests
            with open(ss_path, 'rb') as f:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                    files={"photo": f},
                    data={"chat_id": chat_id, "caption": caption[:200]},
                    timeout=30,
                )
    except Exception as ex:
        print(f"[ERROR] Screenshot skipped/failed: {ex}")
    finally:
        try:
            if os.path.exists(ss_path):
                os.remove(ss_path)
        except Exception:
            pass


async def inspect_page(page, url, timeout_ms=20000):
    """Return a diagnostic dict for one Othoba page."""
    state = {
        "url": url,
        "title": "",
        "status": None,
        "wraps": 0,
        "content_len": 0,
        "blocked": False,
        "loaded": False,
        "error": "",
    }
    try:
        response = await page.goto(
            url, wait_until="domcontentloaded", timeout=timeout_ms
        )
        state["status"] = response.status if response else None
    except Exception as ex:
        state["error"] = str(ex)[:200]
        return state

    try:
        await page.wait_for_selector(PRODUCT_SELECTOR, timeout=12000)
    except Exception:
        pass
    try:
        await page.wait_for_selector('ins.new-price:not(:empty)', timeout=5000)
    except Exception:
        pass
    await asyncio.sleep(0.4)

    try:
        state["title"] = await page.title()
    except Exception:
        pass
    try:
        content = await page.content()
        state["content_len"] = len(content)
        title_lower = state["title"].lower()
        body_lower = content[:200000].lower()
        state["wraps"] = len(_product_wraps(BeautifulSoup(content, 'lxml')))
        state["blocked"] = (
            any(marker in title_lower for marker in TITLE_BLOCK_MARKERS)
            or any(marker in body_lower for marker in BODY_BLOCK_MARKERS)
        )
        if state["status"] in (401, 403, 429, 451, 503):
            state["blocked"] = True
        state["loaded"] = ("othoba" in body_lower) or state["wraps"] > 0
    except Exception as ex:
        state["error"] = str(ex)[:200]
    return state


async def probe_othoba(context, urls):
    """Probe Othoba and return one of: 'ok', 'empty', 'blocked', 'unreachable'.

    'empty' means the pages loaded normally but rendered zero cards. That is
    NOT a geo-block and must not stop the scrape; sector workers get a chance
    to retry. 'blocked' is reserved for explicit WAF/geo markers or HTTP
    401/403/429/451/503. 'unreachable' means every probe failed to load.
    """
    if isinstance(urls, str):
        urls = [urls]
    probes = []
    seen = set()
    for raw_url in urls[:6]:
        probe_url = (raw_url or "").strip()
        if not probe_url or probe_url in seen:
            continue
        seen.add(probe_url)
        probes.append(probe_url)
        if len(probes) >= 3:
            break

    if not probes:
        return "empty"

    results = []
    for probe_url in probes:
        page = None
        try:
            page = await context.new_page()
            await page.route(
                '**/*',
                lambda r: r.abort() if r.request.resource_type in ['image', 'stylesheet', 'font', 'media'] else r.continue_(),
            )
            state = await inspect_page(page, probe_url)
            results.append(state)
            print(
                f"[PROBE] {probe_url} -> HTTP {state.get('status')} | "
                f"cards={state.get('wraps')} | blocked={state.get('blocked')} | "
                f"title={str(state.get('title'))[:80]}"
            )
            if state.get("blocked"):
                await capture_and_send_ss(
                    page,
                    f"Othoba Blocked (HTTP {state.get('status')}, "
                    f"{str(state.get('title'))[:40]})",
                    _probe_text(
                        "Othoba web probe: BLOCKED",
                        state,
                        "Explicit WAF/geo markers or HTTP 401/403/429/451/503 "
                        "detected. Exiting early to avoid a long timeout.",
                    ),
                )
                return "blocked"
            if state.get("wraps", 0) > 0:
                return "ok"
        except Exception as ex:
            results.append({
                "url": probe_url,
                "wraps": 0,
                "blocked": False,
                "loaded": False,
                "error": str(ex)[:200],
            })
            print(f"[PROBE] {probe_url} -> exception: {str(ex)[:120]}")
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass

    loaded = [r for r in results if r.get("loaded")]
    if loaded:
        send_text_alert(
            _probe_text(
                "Othoba page loaded but returned 0 products - NOT a geo-block",
                loaded[0],
                "Continuing to sector workers. This is normally delayed "
                "JavaScript rendering or an empty category; no screenshot "
                "was sent.",
            )
        )
        print(
            "[WARN] Othoba probe loaded normally with 0 cards; continuing "
            "instead of exiting."
        )
        return "empty"

    state = results[-1] if results else {"url": probes[0]}
    send_text_alert(
        _probe_text(
            "Othoba probe: UNREACHABLE",
            state,
            "All probe URLs failed to load. Check Kaggle egress/network; "
            "exiting early to avoid a 45-minute timeout.",
        )
    )
    print("[WARN] Othoba probe could not load any URL; exiting early.")
    return "unreachable"


async def check_geo_block(context, test_url):
    """Backward-compatible bool wrapper for older callers.

    New code should use probe_othoba() for the tri-state result.
    """
    result = await probe_othoba(context, test_url)
    return result in ("blocked", "unreachable")


async def main():
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    init_db()
    urls_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'urls.txt')
    if not os.path.exists(urls_file):
        urls_file = 'urls.txt'
    if not os.path.exists(urls_file): return
    with open(urls_file, 'r', encoding='utf-8') as f: urls = [l.strip() for l in f if l.strip()]

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
            user_agent=random.choice(USER_AGENTS),
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

        # Early probe: only real blocks stop the run. A normally loaded page
        # with zero cards is retried by the sector workers instead.
        if urls:
            probe_status = await probe_othoba(context, urls)
            if probe_status in ("blocked", "unreachable"):
                print(
                    f"[WARN] Othoba probe={probe_status}; exiting early to "
                    "prevent a long timeout."
                )
                save_last_run_log(summary)
                await browser.close()
                return
            if probe_status == "empty":
                print(
                    "[WARN] Othoba probe found 0 products on loaded pages; "
                    "continuing to sector workers."
                )

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
