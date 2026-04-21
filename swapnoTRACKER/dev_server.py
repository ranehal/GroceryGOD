#!/usr/bin/env python3
"""
Simple HTTP Server for Shwapno Price Tracker
Serves static files to avoid CORS issues when testing locally
No dependencies needed - uses built-in http.server
"""

import http.server
import socketserver
import os
import sys
import webbrowser
from pathlib import Path

# Configuration
PORT = 8000
DIRECTORY = Path(__file__).parent

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)
    
    def end_headers(self):
        # Add CORS headers for local testing
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()
    
    def log_message(self, format, *args):
        # Custom logging format with emojis
        if '200' in str(args):
            print(f"✅ {format % args}")
        elif '404' in str(args):
            print(f"❌ {format % args}")
        else:
            print(f"📄 {format % args}")

def main():
    os.chdir(DIRECTORY)
    
    try:
        with socketserver.TCPServer(("", PORT), CustomHTTPRequestHandler) as httpd:
            url = f"http://localhost:{PORT}/index.html"
            
            print("")
            print("=" * 60)
            print("🚀 Shwapno Price Tracker - Development Server")
            print("=" * 60)
            print(f"📂 Serving: {DIRECTORY}")
            print(f"🌐 Server:  http://localhost:{PORT}")
            print(f"🔗 App URL: {url}")
            print("")
            print("💡 Opening browser automatically...")
            print("   Press Ctrl+C to stop the server")
            print("=" * 60)
            print("")
            
            # Open browser automatically
            webbrowser.open(url)
            
            # Start server
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\n")
        print("=" * 60)
        print("🛑 Server stopped")
        print("=" * 60)
        sys.exit(0)
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\n❌ ERROR: Port {PORT} is already in use!")
            print(f"   Try closing other applications or use a different port.")
        else:
            print(f"\n❌ ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
