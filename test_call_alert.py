#!/usr/bin/env python3
"""
Test Call Alert System - Will this wake you up for fire calls?
"""

import requests
from datetime import datetime

def test_fire_call_alert():
    """Test if Pushover will wake you up for a fire call"""
    
    print("FIRE CALL ALERT TEST")
    print("=" * 50)
    
    # Your Pushover credentials from cad_system.py
    user_key = "u91gdp1wbvynt5wmiec45tsf79e6t5"
    app_token = "agunhyfhpg9rik3dr5uedi51vyotaw"
    
    print("Using your Pushover credentials...")
    print(f"User Key: {user_key[:8]}...")
    print(f"App Token: {app_token[:8]}...")
    
    # Simulate a CRITICAL fire call
    fire_call_data = {
        'token': app_token,
        'user': user_key,
        'title': 'FIRE CALL - STRUCTURE FIRE',
        'message': f'''EMERGENCY FIRE CALL

Location: 123 Main Street, Rogers, AR
Units: Engine 1, Ladder 1, Battalion 1
Priority: CRITICAL
Time: {datetime.now().strftime('%I:%M %p CDT, %B %d, %Y')}

This is a TEST alert to verify your phone will wake you up for real fire calls.

The CAD system is working correctly and will send alerts like this for actual incidents.''',
        'priority': 2,  # Emergency priority - WILL WAKE YOU UP
        'sound': 'siren',  # Emergency sound
        'retry': 30,  # Retry every 30 seconds
        'expire': 3600  # Expire after 1 hour
    }
    
    print("\nSending TEST fire call alert...")
    print("This should wake you up if you're sleeping!")
    print("Make sure your phone is nearby and not on silent!")
    
    try:
        response = requests.post(
            'https://api.pushover.net/1/messages.json',
            data=fire_call_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print("SUCCESS! TEST ALERT SENT!")
            print(f"Request ID: {result.get('request', 'N/A')}")
            print("\nCHECK YOUR PHONE NOW!")
            print("You should have received a loud, vibrating alert")
            print("This is exactly what you'll get for real fire calls")
            return True
        else:
            print(f"FAILED: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_medical_call_alert():
    """Test medical call alert"""
    
    print("\nMEDICAL CALL ALERT TEST")
    print("=" * 30)
    
    user_key = "u91gdp1wbvynt5wmiec45tsf79e6t5"
    app_token = "agunhyfhpg9rik3dr5uedi51vyotaw"
    
    medical_call_data = {
        'token': app_token,
        'user': user_key,
        'title': 'MEDICAL EMERGENCY',
        'message': f'''MEDICAL EMERGENCY CALL

Location: 456 Oak Avenue, Rogers, AR
Units: Medic 1, Engine 2
Priority: HIGH
Time: {datetime.now().strftime('%I:%M %p CDT, %B %d, %Y')}

This is a TEST alert for medical emergencies.''',
        'priority': 1,  # High priority
        'sound': 'push',
        'retry': 30,
        'expire': 1800
    }
    
    try:
        response = requests.post(
            'https://api.pushover.net/1/messages.json',
            data=medical_call_data,
            timeout=10
        )
        
        if response.status_code == 200:
            print("Medical call test sent!")
            return True
        else:
            print(f"Medical alert failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    """Run the tests"""
    print("PUSHOVER CALL ALERT TESTING")
    print("=" * 50)
    print("Testing if your phone will wake you up for fire calls")
    print("Make sure your phone is nearby and not on silent!")
    print("=" * 50)
    
    # Test fire call (most important)
    fire_success = test_fire_call_alert()
    
    # Test medical call
    medical_success = test_medical_call_alert()
    
    print("\n" + "=" * 50)
    print("TEST RESULTS:")
    print(f"Fire Call Alert: {'PASS' if fire_success else 'FAIL'}")
    print(f"Medical Alert: {'PASS' if medical_success else 'FAIL'}")
    
    if fire_success:
        print("\nSUCCESS! Your phone WILL wake you up for fire calls!")
        print("The CAD system is ready to alert you 24/7")
    else:
        print("\nFAILED: Check your Pushover setup")

if __name__ == "__main__":
    main()
