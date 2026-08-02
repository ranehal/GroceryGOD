from playwright.sync_api import sync_playwright

def inspect_menu():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating...")
        page.goto("https://chaldal.com/")
        
        # Wait for menu
        try:
            page.wait_for_selector('ul.menu-item-list', timeout=10000)
        except:
            print("Menu list not found")
        
        # Broad Search
        links = page.query_selector_all('a')
        cats = []
        seen = set()
        
        for link in links:
            href = link.get_attribute('href')
            if not href or href.startswith('#') or href == '/': continue
            
            # Simple heuristic for categories
            if '/' in href and not 'product' in href and not 'cart' in href and not 'account' in href:
                name = link.inner_text().strip()
                if name and len(name) < 30: # Avoid long text links
                    full_url = f"https://chaldal.com{href}" if href.startswith('/') else href
                    if full_url not in seen:
                        cats.append({"name": name, "url": full_url})
                        seen.add(full_url)

        print(f"Total discovered potential categories: {len(cats)}")
        for c in cats[:10]: # Print first 10
            print(f"Found: {c['name']} -> {c['url']}")
            
        browser.close()

if __name__ == "__main__":
    inspect_menu()