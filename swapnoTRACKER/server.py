from flask import Flask, jsonify, request, send_from_directory
import subprocess
import json
import os
import threading

app = Flask(__name__, static_folder='.', static_url_path='')

CATEGORIES_FILE = 'categories.json'
SCRAPER_SCRIPT = 'scraper.py'

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

@app.route('/api/categories', methods=['GET'])
def get_categories():
    if os.path.exists(CATEGORIES_FILE):
        with open(CATEGORIES_FILE, 'r') as f:
            return jsonify(json.load(f))
    return jsonify([])

@app.route('/api/categories', methods=['POST'])
def save_categories():
    categories = request.json
    with open(CATEGORIES_FILE, 'w') as f:
        json.dump(categories, f, indent=2)
    return jsonify({"status": "success"})

def run_scraper_thread():
    # Run the scraper script
    subprocess.run(["python", SCRAPER_SCRIPT], check=True)

@app.route('/api/run-scraper', methods=['POST'])
def run_scraper():
    # Run in a separate thread to avoid blocking the server
    thread = threading.Thread(target=run_scraper_thread)
    thread.start()
    return jsonify({"status": "started", "message": "Scraper started in background"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
