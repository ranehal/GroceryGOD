import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
from datetime import datetime, date, timezone, timedelta
import asyncio
from collections import Counter
import json
import re
import os
import random
import logging
from playwright.async_api import async_playwright

DHAKA_TZ = timezone(timedelta(hours=6))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler("scraper.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DATA_FILE = 'data.json'
CATEGORIES_FILE = 'categories.json'

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def load_categories():
    if os.path.exists(CATEGORIES_FILE):
        with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"groups": [], "custom": []}

def load_pinned_names():
    cats = load_categories()
    pinned = next((g for g in cats.get('groups', []) if g.get('id') == 'pinned_deals'), None)
    if pinned:
        return [c['name'] for c in pinned['categories']]
    return []

def flatten_categories(category_data):
    all_categories = []
    for group in category_data.get('groups', []):
        for cat in group.get('categories', []):
            all_categories.append(cat)
    return all_categories

def normalize_unit(name, price_str):
    name_lower = name.lower()
    price = float(re.sub(r'[^\d.]', '', price_str))
    
    kg_pattern = r'(\d+(?:\.\d+)?)\s*(kg|gm|gram|g)\b'
    l_pattern = r'(\d+(?:\.\d+)?)\s*(l|ml|ltr|liter)\b'
    
    kg_match = re.search(kg_pattern, name_lower)
    l_match = re.search(l_pattern, name_lower)
    
    quantity_display = "Per Piece"; norm_price = price; unit_type = "piece"
    
    if kg_match or l_match:
        if kg_match:
            base_val = float(kg_match.group(1))
            unit = kg_match.group(2)
            is_kg = True
        else:
            base_val = float(l_match.group(1))
            unit = l_match.group(2)
            is_kg = False
            
        val = base_val
        if unit in ['gm', 'g', 'gram', 'ml']: val /= 1000.0
        
        if val > 0:
            norm_price = price / val
            if is_kg:
                quantity_display = f"{val} kg" if val >= 1 else f"{int(val*1000)} gm"
                unit_type = "kg"
            else:
                quantity_display = f"{val} L" if val >= 1 else f"{int(val*1000)} ml"
                unit_type = "liter"
                
    return quantity_display, round(norm_price, 2), unit_type

def parse_price_value(text):
    match = re.search(r'(\d+(?:,\d{3})*(?:\.\d+)?)', str(text or '').replace('৳', ''))
    return float(match.group(1).replace(',', '')) if match else None

async def extract_price_info(item):
    """Extract Shwapno current/original prices without treating striked prices as current."""
    price_info = await item.evaluate("""card => {
        const normalize = text => {
            const match = String(text || '').replace(/,/g, '').match(/(\\d+(?:\\.\\d+)?)/);
            return match ? Number(match[1]) : null;
        };
        const textOf = el => (el?.innerText || el?.textContent || '').trim();

        // --- MINIMAL FIX ADDED HERE ---
        // Explicitly look for the '.active-price' class you provided first. 
        const exactActiveNode = card.querySelector('.active-price');
        if (exactActiveNode) {
            const current = normalize(textOf(exactActiveNode));
            if (current) {
                // If we found the active price, look for the old striked price
                const oldNode = card.querySelector('del, s, strike, [class*="old" i], [class*="line-through" i]');
                const original = oldNode ? normalize(textOf(oldNode)) : null;
                
                // Check for discount badge
                const discountNode = card.querySelector('[class*="discount" i], [class*="save" i]');
                const discount = discountNode ? textOf(discountNode) : ((original && original > current) ? `${Math.round(((original - current) / original) * 100)}%` : null);
                
                return { current, original: (original > current) ? original : null, discount, candidates: ['exact-active-price'] };
            }
        }
        // ------------------------------

        // Fallback to original fuzzy logic for pages/cards that don't use .active-price
        const isOldPrice = el => {
            const text = [
                el.tagName,
                el.className || '',
                el.getAttribute('aria-label') || '',
                el.getAttribute('data-testid') || '',
                el.closest('del,s,strike,[class*="old" i],[class*="regular" i],[class*="original" i],[class*="strike" i],[class*="line-through" i]') ? 'old' : ''
            ].join(' ').toLowerCase();
            const style = window.getComputedStyle(el);
            return text.includes('old') || text.includes('regular') || text.includes('original') ||
                text.includes('strike') || text.includes('line-through') || style.textDecorationLine.includes('line-through');
        };
        const isCurrentHint = el => {
            const text = [
                el.tagName,
                el.className || '',
                el.getAttribute('aria-label') || '',
                el.getAttribute('data-testid') || '',
                textOf(el.parentElement),
                textOf(el.closest('[class*="price" i]'))
            ].join(' ').toLowerCase();
            return /current|selling|sale|discount|offer|special|deal|now/.test(text);
        };
        const nodes = [...card.querySelectorAll('[class*="price" i], [data-testid*="price" i], del, s, strike')];
        const candidates = nodes.map(el => ({
            value: normalize(textOf(el)),
            text: textOf(el),
            old: isOldPrice(el),
            cls: String(el.className || ''),
            currentHint: isCurrentHint(el)
        })).filter(x => x.value !== null && x.value > 0);
        
        const currentCandidates = candidates.filter(x => !x.old);
        const oldCandidates = candidates.filter(x => x.old);
        let current = null;
        if (currentCandidates.length) {
            const active = currentCandidates.find(x => x.currentHint || /active|current|discount|sale|special/i.test(x.cls));
            current = active ? active.value : Math.min(...currentCandidates.map(x => x.value));
        }
        if (current === null) {
            return { current: null, original: null, discount: null, candidates };
        }
        const originalPool = oldCandidates.length ? oldCandidates : candidates.filter(x => x.value > current);
        const original = originalPool.length ? Math.max(...originalPool.map(x => x.value)) : null;
        const discountNode = card.querySelector('[class*="discount" i], [class*="save" i], [data-testid*="discount" i]');
        const discountText = discountNode ? textOf(discountNode) : '';
        const discount = discountText || (original && original > current ? `${Math.round(((original - current) / original) * 100)}%` : null);
        return { current, original: original && original > current ? original : null, discount, candidates };
    }""")
    current = price_info.get('current')
    if current is None:
        logger.warning("Price extraction failed. Candidates: %s", price_info.get('candidates'))
        return None
    return price_info

async def self_scrape_items(page, container_selector, category, current_data, today_str, summary, is_pinned=False):
    container = await page.query_selector(container_selector) or page
    items = await container.query_selector_all('.product-box, div[class*="product-grid-item"], .product-item-info')
    logger.info(f"    [+] Extracted {len(items)} items from current view")
    
    for item in items:
        try:
            title_el = await item.query_selector('.product-box-title a, a[class*="title"], .name a')
            if not title_el: continue
            name = (await title_el.inner_text()).strip()
            url_suffix = await title_el.get_attribute('href')
            product_url = f"https://www.shwapno.com{url_suffix}" if url_suffix.startswith('/') else url_suffix
            
            img_el = await item.query_selector('img')
            img_src = await img_el.get_attribute('src') if img_el else ""
            
            price_info = await extract_price_info(item)
            if not price_info:
                logger.warning(f"    [!] Missing current price for: {name}")
                continue
            current_price = float(price_info['current'])
            original_price = price_info.get('original')
            discount = price_info.get('discount')
            
            qty_disp, norm_price, unit_type = normalize_unit(name, str(current_price))
            prod_id = re.sub(r'\W+', '', name).lower()
            
            summary['total'] += 1
            summary['categories'][category['name']] += 1
            if prod_id not in current_data:
                current_data[prod_id] = {
                    "id": prod_id, "name": name, "url": product_url, 
                    "image": img_src, "category": category['name'], "history": []
                }
            elif is_pinned:
                current_data[prod_id]["category"] = category['name']
            
            current_data[prod_id].update({
                "current_price": current_price, "normalized_price": norm_price,
                "original_price": original_price, "discount": discount,
                "unit": qty_disp, "unit_type": unit_type, "image": img_src, "url": product_url
            })
            
            history = current_data[prod_id]["history"]
            if not history or history[-1]['date'] != today_str:
                 history.append({"date": today_str, "price": current_price, "normalized_price": norm_price, "original_price": original_price, "discount": discount})
            elif history[-1]['date'] == today_str:
                history[-1]['price'] = current_price
                history[-1]['normalized_price'] = norm_price
                history[-1]['original_price'] = original_price
                history[-1]['discount'] = discount
        except Exception as e:
            logger.warning(f"    [!] Failed item parse: {e}")

async def scrape_category(sem, browser, category, current_data, summary, pinned_names=[]):
    async with sem:
        is_pinned = category['name'] in pinned_names
        context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
        page = await context.new_page()
        
        logger.info(f"Scraping: {category['name']} ({category['url']})")
        try:
            await page.goto(category['url'], wait_until="load", timeout=120000)
            await asyncio.sleep(5) 
            
            today_str = date.today().isoformat()
            container_selector = f"xpath={category['xpath']}" if category.get('xpath') else "body"
            
            tabs = await page.query_selector_all('.category-tab-list div, .category-tab-list a, .nav-tabs li a, .category-item-title')
            valid_tabs = []
            for t in tabs:
                t_text = (await t.inner_text()).strip()
                if t_text and len(t_text) < 40:
                    valid_tabs.append(t)
            
            if len(valid_tabs) > 1:
                logger.info(f"  [+] Detected {len(valid_tabs)} tabs in {category['name']}. Deep clicking...")
                for i in range(len(valid_tabs)):
                    current_tabs = await page.query_selector_all('.category-tab-list div, .category-tab-list a, .nav-tabs li a, .category-item-title')
                    tab_name = (await valid_tabs[i].inner_text()).strip()
                    target_tab = None
                    for ct in current_tabs:
                        if (await ct.inner_text()).strip() == tab_name:
                            target_tab = ct
                            break
                    
                    if not target_tab: continue
                    
                    logger.info(f"    -> Tab {i+1}/{len(valid_tabs)}: {tab_name}")
                    try:
                        await target_tab.click()
                        await asyncio.sleep(4)
                        for _ in range(4): 
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await asyncio.sleep(1.5)
                        await self_scrape_items(page, container_selector, category, current_data, today_str, summary, is_pinned)
                    except: continue
            else:
                for _ in range(10):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1.5)
                await self_scrape_items(page, container_selector, category, current_data, today_str, summary, is_pinned)
            
            return True
        except Exception as e:
            logger.error(f"  [X] Error: {str(e)[:100]}")
            return False
        finally:
            await context.close()

async def main():
    summary = {'total': 0, 'new': 0, 'categories': Counter()}
    data = load_data()
    category_data = load_categories()
    pinned_names = load_pinned_names()
    enabled_categories = [c for c in flatten_categories(category_data) if c.get('enabled', True)]
    
    logger.info(f"Started Scraper: {len(enabled_categories)} categories, {len(pinned_names)} pinned.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        sem = asyncio.Semaphore(3) 
        
        pinned_cats = [c for c in enabled_categories if c['name'] in pinned_names]
        other_cats = [c for c in enabled_categories if c['name'] not in pinned_names]
        queue = pinned_cats + other_cats

        tasks = []
        for cat in queue:
            tasks.append(scrape_category(sem, browser, cat, data, summary, pinned_names))
        
        await asyncio.gather(*tasks)
        await browser.close()
    
    save_data(data)
    save_last_run_log(summary)
    logger.info("Shwapno Scraper Complete.")

def save_last_run_log(summary):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base_dir, "last_run_log.txt")
    with open(log_path, "w", encoding='utf-8') as f:
        f.write(f"Last Run: {datetime.now(DHAKA_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n")
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
