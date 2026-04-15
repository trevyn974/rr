#!/usr/bin/env python3
"""
Emergency script to stop Discord spam
"""

import requests
import json

def stop_discord_spam():
    """Stop Discord notifications and clear caches"""
    print("Stopping Discord spam...")
    
    try:
        # Stop Discord notifications
        response = requests.post('http://127.0.0.1:5000/api/discord/stop-spam', timeout=10)
        if response.status_code == 200:
            print("Discord notifications stopped successfully")
            print("All caches cleared")
        else:
            print(f"Failed to stop Discord: {response.status_code}")
            print(f"Response: {response.text}")
    
    except requests.exceptions.ConnectionError:
        print("Cannot connect to CAD web server. Is it running?")
        print("Try running: python cad_web_server.py")
    except Exception as e:
        print(f"Error: {e}")

def set_strict_rate_limits():
    """Set very strict rate limits to prevent spam"""
    print("Setting strict rate limits...")
    
    try:
        data = {
            "min_interval": 300,  # 5 minutes between notifications
            "max_per_hour": 5     # Only 5 notifications per hour
        }
        
        response = requests.post('http://127.0.0.1:5000/api/discord/rate-limits', 
                               json=data, timeout=10)
        if response.status_code == 200:
            print("Strict rate limits set: 5 minutes interval, 5 per hour")
        else:
            print(f"Failed to set rate limits: {response.status_code}")
    
    except requests.exceptions.ConnectionError:
        print("Cannot connect to CAD web server. Is it running?")
    except Exception as e:
        print(f"Error: {e}")

def clear_caches():
    """Clear all Discord caches"""
    print("Clearing Discord caches...")
    
    try:
        response = requests.post('http://127.0.0.1:5000/api/discord/clear-cache', timeout=10)
        if response.status_code == 200:
            print("✅ Discord caches cleared")
        else:
            print(f"❌ Failed to clear caches: {response.status_code}")
    
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to CAD web server. Is it running?")
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    print("Discord Spam Control")
    print("=" * 30)
    
    # Option 1: Stop completely
    print("\n1. Stopping Discord notifications completely...")
    stop_discord_spam()
    
    # Option 2: Set strict limits
    print("\n2. Setting strict rate limits...")
    set_strict_rate_limits()
    
    # Option 3: Clear caches
    print("\n3. Clearing caches...")
    clear_caches()
    
    print("\n✅ Discord spam control completed!")
    print("\nTo re-enable Discord notifications:")
    print("  POST http://127.0.0.1:5000/api/discord/toggle")

if __name__ == "__main__":
    main()
