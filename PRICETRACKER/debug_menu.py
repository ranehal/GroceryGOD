from playwright.sync_api import sync_playwright

def dump_menu_html():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating...")
        page.goto("https://chaldal.com/", timeout=60000)
        
        try:
            # Wait for the menu to appear
            page.wait_for_selector('.category-menu', timeout=20000)
        except:
            print("Timeout waiting for .category-menu, dumping body...")
        
        # Select the side menu container
        # Based on previous snippets, it might be .category-menu or .level-0
        try:
            menu_html = page.inner_html('.category-menu') # Common class
        except:
            try:
                menu_html = page.inner_html('.level-0')
            except:
                menu_html = page.inner_html('body') # Fallback
                
        with open("menu_dump.html", "w", encoding="utf-8") as f:
            f.write(menu_html)
            
        print("Menu HTML dumped to menu_dump.html")
        browser.close()

if __name__ == "__main__":
    dump_menu_html()
