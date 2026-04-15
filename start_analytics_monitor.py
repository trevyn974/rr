#!/usr/bin/env python3
"""
Start both the incident monitor and analytics server
"""

import threading
import time
from simple_incident_monitor import SimpleIncidentMonitor, AGENCY_ID
from call_analytics_server import run_server

def start_analytics_server():
    """Start analytics server in separate thread"""
    try:
        run_server(host='0.0.0.0', port=5001)
    except Exception as e:
        print(f"[ERROR] Analytics server error: {e}")

def main():
    print("=" * 60)
    print("Starting Incident Monitor + Analytics Dashboard")
    print("=" * 60)
    print()
    
    # Start analytics server in background thread
    analytics_thread = threading.Thread(target=start_analytics_server, daemon=True)
    analytics_thread.start()
    print("[START] Analytics server starting on http://0.0.0.0:5001")
    print("[INFO] Access dashboard at: http://localhost:5001")
    print("[INFO] Or from other devices: http://YOUR_IP:5001")
    print()
    
    # Give server a moment to start
    time.sleep(2)
    
    # Start monitor
    monitor = SimpleIncidentMonitor(AGENCY_ID)
    
    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\n[STOP] Stopping both services...")
    except Exception as e:
        print(f"[FATAL] Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()




