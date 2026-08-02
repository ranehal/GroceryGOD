from flask import Flask, request, jsonify, send_from_directory
import json
import os
import subprocess
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_url_path=None, static_folder=None)

DATA_FILE = os.path.join(BASE_DIR, 'data.js')
CONFIG_FILE = os.path.join(BASE_DIR, 'categories.json')

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(BASE_DIR, path)

@app.route('/api/categories', methods=['GET'])
def get_categories():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify([])

@app.route('/api/categories', methods=['POST'])
def update_category():
    data = request.json
    action = data.get('action')
    
    with open(CONFIG_FILE, 'r+') as f:
        categories = json.load(f)
        
        if action == 'add':
            new_cat = {
                "name": data['name'],
                "url": data['url'],
                "active": True
            }
            categories.append(new_cat)
        
        elif action == 'toggle':
            for cat in categories:
                if cat['url'] == data['url']:
                    cat['active'] = not cat['active']
                    break
        
        elif action == 'reorder':
            # Expecting full list of names or URLs in new order
            new_order = data.get('order', [])
            if new_order:
                # Map existing by URL
                cat_map = {c['url']: c for c in categories}
                new_cats = []
                for url in new_order:
                    if url in cat_map:
                        new_cats.append(cat_map[url])
                        del cat_map[url] # Remove processed
                # Append any remaining (new ones?)
                new_cats.extend(cat_map.values())
                categories = new_cats

        elif action == 'delete':
             categories = [c for c in categories if c['url'] != data['url']]

        f.seek(0)
        json.dump(categories, f, indent=2)
        f.truncate()
        
    return jsonify({"status": "success", "categories": categories})

@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    def run_scraper():
        subprocess.run(["python", "scraper.py"])
    
    thread = threading.Thread(target=run_scraper)
    thread.start()
    return jsonify({"status": "started"})

if __name__ == '__main__':
    print("Server running at http://localhost:5000")
    app.run(port=5000, debug=True)
