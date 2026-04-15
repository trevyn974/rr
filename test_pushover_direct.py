#!/usr/bin/env python3
"""
Direct Pushover Test - Test if Pushover works with the CAD system credentials
"""

import requests
from datetime import datetime

def test_pushover_direct():
    """Test Pushover directly with CAD system credentials"""
    
    print("DIRECT PUSHOVER TEST")
    print("=" * 40)
    
    # Use the exact credentials from cad_system.py
    user_key = "u91gdp1wbvynt5wmiec45tsf79e6t5"
    app_token = "agunhyfhpg9rik3dr5uedi51vyotaw"
    
    print(f"User Key: {user_key}")
    print(f"App Token: {app_token}")
    
    # Test data - simulate a real fire call
    test_data = {
        'token': app_token,
        'user': user_key,
        'title': 'FDD ALERT - MEDIUM',
        'message': f'''Public Service
Location: 6109 W VALLEY FORGE DR, ROGERS, AR
Units: Unit E8
ID: #2307526250
Time: {datetime.now().strftime('%H:%M')}''',
        'priority': 0,  # Normal priority for MEDIUM
        'sound': 'cosmic'
    }
    
    print("\nSending test alert...")
    print("This should match exactly what the CAD system sends")
    
    try:
        response = requests.post(
            'https://api.pushover.net/1/messages.json',
            data=test_data,
            timeout=10
        )
        
        print(f"Response Status: {response.status_code}")
        print(f"Response Text: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 1:
                print("SUCCESS! Pushover alert sent!")
                print(f"Request ID: {result.get('request', 'N/A')}")
                return True
            else:
                print(f"FAILED: {result.get('errors', 'Unknown error')}")
                return False
        else:
            print(f"FAILED: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    test_pushover_direct()
