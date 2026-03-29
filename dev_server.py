#!/usr/bin/env python3
import http.server
import socketserver
import os
import sys
import webbrowser
from pathlib import Path

PORT = 8888
DIRECTORY = Path(__file__).parent

class RobustHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError):
            # Suppress common Windows connection reset errors when serving large files
            pass

class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

def main():
    os.chdir(DIRECTORY)
    try:
        with ThreadingTCPServer(("", PORT), RobustHTTPRequestHandler) as httpd:
            url = f"http://localhost:{PORT}/index.html"
            print(f"🚀 GroceryGOD Robust Server: {url}")
            print("   (Threading enabled, suppressing WinError 10054)")
            webbrowser.open(url)
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()
