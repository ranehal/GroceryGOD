import re
import json
import asyncio
import datetime
from playwright.async_api import async_playwright

# Configuration
DATA_FILE = "data.js"
CAT_FILE = "categories.json"
CAT_JS_FILE = "categories.js"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
CONCURRENCY_LIMIT = 3

def normalize_price(price_text, unit_text):
    """
    Converts price to 'per 1kg' or 'per 1L' if applicable.
    Returns: (normalized_price, normalized_unit_label)
    """
    try:
        # Clean inputs
        price = float(re.sub(r'[^\d.]', '', str(price_text)))
        unit_text = unit_text.lower().strip()
        
        # Regex to find quantity and unit
        match = re.search(r'(\d+(\.\d+)?)\s*(kg|gm|g|ltr|liter|l|ml|pcs|piece|each|dzn|dozen)', unit_text)
        if not match:
            return price, unit_text # Cannot normalize

        qty = float(match.group(1))
        unit = match.group(3)

        # Weight Normalization
        if unit in ['gm', 'g']:
            return (price / qty) * 1000, "1 kg"
        elif unit == 'kg':
            return price / qty, "1 kg"
        
        # Volume Normalization
        elif unit == 'ml':
            return (price / qty) * 1000, "1 L"
        elif unit in ['ltr', 'liter', 'l']:
            return price / qty, "1 L"

        # Count Normalization (Keep as is usually, or normalize to 1 pc if needed)
        elif unit in ['dzn', 'dozen']:
            return price / (qty * 12), "1 pc"
        elif unit in ['pcs', 'piece', 'each']:
             if qty > 1:
                 return price / qty, "1 pc"
             return price, "1 pc"

        return price, unit_text

    except Exception as e:
        return price_text, unit_text

async def discover_categories(page):
    print("Discovering categories...")
    discovered = {}
    
    def slugify(text):
        text = text.lower().strip()
        text = text.replace(' & ', '-')
        text = text.replace('&', '-')
        text = text.replace(' ', '-')
        text = re.sub(r'[^a-z0-9\-]', '', text)
        return text

    try:
        await page.wait_for_selector('.level-0', timeout=15000)
        top_items = await page.query_selector_all('.level-0 > li')
        
        for item in top_items:
            try:
                name_el = await item.query_selector('.category-name')
                if not name_el: continue
                name = (await name_el.inner_text()).strip()
                slug = slugify(name)
                
                if slug not in discovered:
                    discovered[slug] = {"name": name, "url": f"https://chaldal.com/{slug}", "active": True}
                
                subs = await item.query_selector_all('.level-1 > li')
                if not subs:
                    await item.hover()
                    await asyncio.sleep(0.5)
                    subs = await item.query_selector_all('.level-1 > li')
                
                for sub in subs:
                    sub_name_el = await sub.query_selector('.category-name')
                    if sub_name_el:
                        sub_name = (await sub_name_el.inner_text()).strip()
                        sub_slug = slugify(sub_name)
                        if sub_slug not in discovered:
                            discovered[sub_slug] = {"name": sub_name, "url": f"https://chaldal.com/{sub_slug}", "active": True}
            except: continue
    except Exception as e:
        print(f"Discovery error: {e}")
        
    if len(discovered) < 5:
        print("Menu discovery yielded few results. Using fallback link scrape...")
        links = await page.query_selector_all('a')
        for link in links:
             href = await link.get_attribute('href')
             if href and '/product' not in href and len(href) > 2 and not href.startswith('#'):
                 name = (await link.inner_text()).strip()
                 if name:
                     slug = href.strip('/').lower()
                     if slug not in discovered and 'chaldal.com' not in slug:
                         discovered[slug] = {"name": name, "url": f"https://chaldal.com{href}", "active": True}

    return discovered

async def scrape_category(browser, cat_entry, products_data, semaphore, timestamp, today_date):
    async with semaphore:
        url = cat_entry['url']
        cat_name = cat_entry['name']
        print(f"Scraping: {cat_name}...")
        
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        
        try:
            await page.goto(url, timeout=90000, wait_until="domcontentloaded")
            
            # Scroll to load all items
            last_height = await page.evaluate("document.body.scrollHeight")
            for _ in range(15): # Max 15 scrolls to prevent infinite loops
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1.5)
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == last_height: break
                last_height = new_height

            await page.wait_for_selector('.nameTextWithEllipsis', timeout=20000)
            
            product_cards = await page.query_selector_all('.product, .productV2')
            if not product_cards:
                 # Fallback extraction if class names changed
                 names = await page.query_selector_all('.nameTextWithEllipsis')
                 product_cards = []
                 for n in names:
                     parent = await n.evaluate_handle("el => el.closest('.product') || el.closest('.productV2') || el.parentElement.parentElement.parentElement")
                     if parent: product_cards.append(parent)

            for card in product_cards:
                try:
                    name_el = await card.query_selector('.nameTextWithEllipsis')
                    if not name_el: continue
                    name = (await name_el.inner_text()).strip()
                    
                    img_el = await card.query_selector('.imageWrapperWrapper img, img')
                    img_src = await img_el.get_attribute('src') if img_el else ""
                    
                    price_el = await card.query_selector('.productV2discountedPrice span, .price span, .price')
                    if not price_el: continue
                    price_text = await price_el.inner_text()
                    
                    unit_el = await card.query_selector('.subText span, .quantity')
                    unit_text = (await unit_el.inner_text()).strip() if unit_el else "1 unit"

                    price_match = re.search(r'([\d,]+(\.\d+)?)', str(price_text))
                    if price_match:
                        price_val = float(price_match.group(1).replace(',', ''))
                    else:
                        price_val = float(re.sub(r'[^\d.]', '', str(price_text).replace('৳', '')) or 0)

                    norm_price, norm_unit = normalize_price(price_val, unit_text)
                    prod_id = re.sub(r'\W+', '_', name + "_" + unit_text).lower()

                    # Shared dict update (Async safe)
                    if prod_id not in products_data:
                        products_data[prod_id] = {
                            "id": prod_id, "name": name, "image": img_src,
                            "category": cat_name,
                            "current_price": price_val, "current_unit": unit_text, "history": []
                        }
                    else:
                        products_data[prod_id]["category"] = cat_name

                    history = products_data[prod_id]["history"]
                    if not history or history[-1]['date'] != today_date:
                         history.append({
                            "date": today_date, "timestamp": timestamp,
                            "price": price_val, "unit": unit_text,
                            "norm_price": round(norm_price, 2), "norm_unit": norm_unit
                        })
                    else:
                        if history[-1]['price'] != price_val:
                            history[-1]['price'] = price_val
                            history[-1]['norm_price'] = round(norm_price, 2)
                            history[-1]['timestamp'] = timestamp

                    products_data[prod_id]['current_price'] = price_val
                    products_data[prod_id]['current_unit'] = unit_text
                    products_data[prod_id]['norm_price_display'] = f"{round(norm_price, 2)} / {norm_unit}"

                except: continue
                
            print(f"Completed: {cat_name} ({len(product_cards)} items)")
        except Exception as e:
            print(f"Error scraping {cat_name}: {e}")
        finally:
            await context.close()

async def main():
    async with async_playwright() as p:
        # 1. Headless Mode
        browser = await p.chromium.launch(headless=True)
        
        # --- Discovery Phase ---
        print("Running Category Discovery...")
        discovery_context = await browser.new_context(user_agent=USER_AGENT)
        discovery_page = await discovery_context.new_page()
        await discovery_page.goto("https://chaldal.com/", timeout=60000)
        await asyncio.sleep(3)
        
        new_cats_map = await discover_categories(discovery_page)
        await discovery_context.close()

        # Merge Categories
        existing_cats = []
        try:
            with open(CAT_FILE, 'r') as f:
                existing_cats = json.load(f)
        except: pass
        
        existing_urls = {c['url']: c for c in existing_cats}
        final_cats = list(existing_cats)
        
        new_count = 0
        for cat_id, cat_data in new_cats_map.items():
            if cat_data['url'] not in existing_urls:
                final_cats.append(cat_data)
                new_count += 1
        
        with open(CAT_FILE, 'w') as f:
            json.dump(final_cats, f, indent=2)
        with open(CAT_JS_FILE, 'w', encoding='utf-8') as f:
            f.write(f"window.CATEGORY_DATA = {json.dumps(final_cats, indent=2)};")
        print(f"Discovery complete. {new_count} new categories found.")

        # --- Scraping Phase ---
        products_data = {}
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                json_str = content.replace('window.PRODUCT_DATA = ', '').rstrip(';')
                products_data = json.loads(json_str)
        except: pass

        timestamp = datetime.datetime.now().isoformat()
        today_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Concurrency & Semaphore Control
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        tasks = []
        
        active_categories = [c for c in final_cats if c.get('active', True)]
        print(f"Starting concurrent scrape of {len(active_categories)} categories...")

        for cat_entry in active_categories:
            tasks.append(scrape_category(browser, cat_entry, products_data, semaphore, timestamp, today_date))
        
        await asyncio.gather(*tasks)
        await browser.close()

        # Final Save
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            f.write(f"window.PRODUCT_DATA = {json.dumps(products_data, indent=2)};")
        
        print(f"Scraping finished. Total products in database: {len(products_data)}")

if __name__ == "__main__":
    asyncio.run(main())
