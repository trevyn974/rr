#!/usr/bin/env python3
"""
Super simple test - no external dependencies
"""

import http.server
import socketserver
import json
from urllib.parse import parse_qs
import sys

PORT = 5000

class TestHandler(http.server.BaseHTTPRequestHandler):
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            
            print("\n" + "=" * 70)
            print("🚨 INCIDENT RECEIVED!")
            print("=" * 70)
            print(f"ID: {data.get('id')}")
            print(f"Type: {data.get('type')}")
            print(f"Address: {data.get('address')}")
            print(f"Units: {data.get('units')}")
            print("=" * 70 + "\n")
            
            response = {
                "status": "received",
                "id": data.get('id')
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"Error: {e}")
            self.send_response(500)
            self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        html = b"<h1>Active Alert Test Server</h1><p>Server is running!</p>"
        self.wfile.write(html)
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

try:
    with socketserver.TCPServer(("", PORT), TestHandler) as httpd:
        print("=" * 70)
        print("SIMPLE TEST SERVER")
        print("=" * 70)
        print(f"Server running on http://localhost:{PORT}")
        print(f"Webhook: http://localhost:{PORT}/active-alert/webhook")
        print("=" * 70)
        print("\nPress Ctrl+C to stop\n")
        httpd.serve_forever()
        
except KeyboardInterrupt:
    print("\n\nServer stopped")
except OSError as e:
    if "address already in use" in str(e).lower():
        print("\n❌ ERROR: Port 5000 is already in use!")
        print("\n💡 FIX: Either:")
        print("   1. Close whatever is using port 5000")
        print("   2. Or change PORT = 5000 to PORT = 5001 in this script")
    else:
        print(f"\n❌ ERROR: {e}")
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()