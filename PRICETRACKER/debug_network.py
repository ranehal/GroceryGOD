from playwright.sync_api import sync_playwright
import json

def intercept_categories():
    discovered = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("Listening for category API calls...")
        
        # Intercept network responses
        def handle_response(response):
            try:
                if 'application/json' in response.headers.get('content-type', ''):
                    # Check if response looks like category tree
                    url = response.url
                    # Common Chaldal API endpoints? Or data.json?
                    # Let's inspect everything > 1KB
                    if response.ok:
                        body = response.json()
                        # Heuristic: Look for lists of objects with 'name' and 'slug' or 'friendlyName'
                        # Or look for 'categories' key
                        
                        # Simplest heuristic: check if body is a list and has 'name'
                        # This part requires inspection of the actual response structure.
                        # I'll just save EVERYTHING that looks promising to a file for now.
                        pass
            except: pass

        # Actually, let's just use the page variable I can inject
        # Usually Chaldal puts category data in window.initialData or similar.
        
        page.on("response", handle_response)
        page.goto("https://chaldal.com/", timeout=60000)
        
        # Wait a bit
        page.wait_for_timeout(5000)
        
        # Try to extract directly from window object if possible
        # Many React apps expose state.
        try:
            # Check for common global stores
            data = page.evaluate("() => window.__NEXT_DATA__ || window.initialData || window.__PRELOADED_STATE__")
            if data:
                print("Found global state data!")
                with open("state_dump.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
        except:
            print("No global state found.")

        browser.close()

if __name__ == "__main__":
    intercept_categories()
