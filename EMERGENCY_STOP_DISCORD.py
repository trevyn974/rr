#!/usr/bin/env python3
"""
EMERGENCY STOP DISCORD SPAM
This script immediately stops all Discord webhook notifications
"""

import requests
import json
import os

def emergency_stop_discord():
    """Emergency stop all Discord notifications"""
    print("🚨 EMERGENCY STOPPING DISCORD SPAM 🚨")
    print("=" * 50)
    
    # Method 1: Try to stop via web server API
    try:
        print("1. Attempting to stop via web server API...")
        response = requests.post('http://127.0.0.1:5000/api/discord/stop-spam', timeout=5)
        if response.status_code == 200:
            print("✅ Web server API stop successful")
        else:
            print(f"❌ Web server API failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Web server API error: {e}")
    
    # Method 2: Clear sent incidents file
    try:
        print("\n2. Clearing sent incidents cache...")
        if os.path.exists("sent_incidents.json"):
            with open("sent_incidents.json", "w") as f:
                json.dump({
                    "sent_incidents": [],
                    "last_updated": "EMERGENCY_STOP",
                    "note": "EMERGENCY STOP - All incidents cleared"
                }, f, indent=2)
            print("✅ Sent incidents cache cleared")
        else:
            print("ℹ️  No sent incidents file found")
    except Exception as e:
        print(f"❌ Error clearing cache: {e}")
    
    # Method 3: Set ultra-strict rate limits
    try:
        print("\n3. Setting ultra-strict rate limits...")
        data = {
            "min_interval": 86400,  # 24 hours between notifications
            "max_per_hour": 0       # 0 notifications per hour
        }
        
        response = requests.post('http://127.0.0.1:5000/api/discord/rate-limits', 
                               json=data, timeout=5)
        if response.status_code == 200:
            print("✅ Ultra-strict rate limits set")
        else:
            print(f"❌ Rate limits failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Rate limits error: {e}")
    
    # Method 4: Disable Discord completely
    try:
        print("\n4. Disabling Discord completely...")
        response = requests.post('http://127.0.0.1:5000/api/discord/toggle', timeout=5)
        if response.status_code == 200:
            print("✅ Discord disabled")
        else:
            print(f"❌ Discord disable failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Discord disable error: {e}")
    
    print("\n" + "=" * 50)
    print("🚨 EMERGENCY STOP COMPLETE 🚨")
    print("Discord webhooks should now be completely disabled")
    print("If spam continues, restart the CAD system")

if __name__ == "__main__":
    emergency_stop_discord()
