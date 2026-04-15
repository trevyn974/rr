#!/usr/bin/env python3
"""
Immediate spam stop script
"""

import requests
import json

def stop_spam_immediately():
    """Stop Discord spam immediately"""
    print("STOPPING DISCORD SPAM NOW...")
    
    try:
        # Stop Discord completely
        response = requests.post('http://127.0.0.1:5000/api/discord/stop-spam', timeout=5)
        print(f"Stop spam response: {response.status_code}")
        
        # Set very strict rate limits
        data = {
            "min_interval": 3600,  # 1 hour between notifications
            "max_per_hour": 1      # Only 1 notification per hour
        }
        
        response = requests.post('http://127.0.0.1:5000/api/discord/rate-limits', 
                               json=data, timeout=5)
        print(f"Rate limits response: {response.status_code}")
        
        # Clear all caches
        response = requests.post('http://127.0.0.1:5000/api/discord/clear-cache', timeout=5)
        print(f"Clear cache response: {response.status_code}")
        
        print("SPAM STOPPED!")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    stop_spam_immediately()



