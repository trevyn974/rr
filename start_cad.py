#!/usr/bin/env python3
"""
FDD CAD System Startup Script
Easy way to start the complete CAD system
"""

import sys
import os
import subprocess
import time
import webbrowser
from threading import Timer

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import flask
        import flask_cors
        import requests
        import cryptography
        import prodict
        print("[SUCCESS] All dependencies are installed")
        return True
    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e}")
        print("Please install dependencies with: pip install -r cad_requirements.txt")
        return False

def open_browser():
    """Open the CAD interface in the default browser"""
    webbrowser.open('http://127.0.0.1:125')

def main():
    """Main startup function"""
    print("[ALERT] FDD CAD System - Fire Department Computer-Aided Dispatch")
    print("=" * 60)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    print("\n[COMPONENTS] Starting CAD System Components:")
    print("  • CAD Core System")
    print("  • Web Server")
    print("  • Real-time Monitoring")
    print("  • Web Interface")
    
    # Open browser after a short delay
    Timer(3.0, open_browser).start()
    
    print("\n[WEB] CAD Interface will open in your browser at: http://127.0.0.1:125")
    print("[MONITORING] Monitoring Rogers Fire Department (Agency ID: 04600)")
    print("\nPress Ctrl+C to stop the system")
    print("-" * 60)
    
    try:
        # Import and run the web server
        from cad_web_server import run_server
        run_server(host='127.0.0.1', port=125, debug=False)
    except KeyboardInterrupt:
        print("\n\n[STOPPED] CAD System stopped by user")
    except Exception as e:
        print(f"\n[ERROR] Error starting CAD system: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
