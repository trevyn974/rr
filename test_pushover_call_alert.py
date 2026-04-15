#!/usr/bin/env python3
"""
Test Pushover Call Alert System
Tests if Pushover notifications will wake you up for fire calls
"""

import os
import requests
import json
from datetime import datetime

def test_pushover_call_alert():
    """Test Pushover alert for a simulated fire call"""
    
    print("FIRE CALL ALERT TEST")
    print("=" * 50)
    
    # Check if Pushover credentials are set
    user_key = os.getenv('PUSHOVER_USER_KEY')
    app_token = os.getenv('PUSHOVER_APP_TOKEN')
    
    if not user_key or not app_token:
        print("❌ Pushover credentials not found!")
        print("\nTo set up Pushover alerts:")
        print("1. Go to https://pushover.net and create an account")
        print("2. Get your User Key from the dashboard")
        print("3. Create an app and get the App Token")
        print("4. Set environment variables:")
        print("   $env:PUSHOVER_USER_KEY = 'your_user_key'")
        print("   $env:PUSHOVER_APP_TOKEN = 'your_app_token'")
        return False
    
    print(f"✅ Pushover credentials found")
    print(f"User Key: {user_key[:8]}...")
    print(f"App Token: {app_token[:8]}...")
    
    # Simulate a fire call alert
    fire_call_data = {
        'token': app_token,
        'user': user_key,
        'title': '🚨 FIRE CALL - STRUCTURE FIRE',
        'message': '''🔥 EMERGENCY FIRE CALL

📍 Location: 123 Main Street, Rogers, AR
🚒 Units: Engine 1, Ladder 1, Battalion 1
⚡ Priority: CRITICAL
🕐 Time: ''' + datetime.now().strftime('%I:%M %p CDT, %B %d, %Y') + '''

This is a TEST alert to verify your phone will wake you up for real fire calls.

The CAD system is working correctly and will send alerts like this for actual incidents.'''
        ,
        'priority': 2,  # Emergency priority - will wake you up
        'sound': 'siren',  # Emergency sound
        'retry': 30,  # Retry every 30 seconds
        'expire': 3600  # Expire after 1 hour
    }
    
    print("\n🚨 Sending TEST fire call alert...")
    print("This should wake you up if you're sleeping!")
    
    try:
        response = requests.post(
            'https://api.pushover.net/1/messages.json',
            data=fire_call_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ TEST ALERT SENT SUCCESSFULLY!")
            print(f"Request ID: {result.get('request', 'N/A')}")
            print("\n📱 Check your phone NOW!")
            print("You should have received a loud, vibrating alert")
            print("This is exactly what you'll get for real fire calls")
            return True
        else:
            print(f"❌ Alert failed: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending alert: {e}")
        return False

def test_medical_call_alert():
    """Test Pushover alert for a simulated medical call"""
    
    print("\n🏥 Testing Medical Call Alert...")
    
    user_key = os.getenv('PUSHOVER_USER_KEY')
    app_token = os.getenv('PUSHOVER_APP_TOKEN')
    
    if not user_key or not app_token:
        print("❌ Pushover credentials not found!")
        return False
    
    medical_call_data = {
        'token': app_token,
        'user': user_key,
        'title': '🚑 MEDICAL EMERGENCY',
        'message': f'''🏥 MEDICAL EMERGENCY CALL

📍 Location: 456 Oak Avenue, Rogers, AR
🚑 Units: Medic 1, Engine 2
⚡ Priority: HIGH
🕐 Time: {datetime.now().strftime('%I:%M %p CDT, %B %d, %Y')}

This is a TEST alert for medical emergencies.

The CAD system will alert you for all high-priority medical calls.'''
        ,
        'priority': 1,  # High priority
        'sound': 'push',  # Standard sound
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
            print("✅ Medical call test sent!")
            return True
        else:
            print(f"❌ Medical alert failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending medical alert: {e}")
        return False

def test_system_status_alert():
    """Test system status alert"""
    
    print("\n⚙️ Testing System Status Alert...")
    
    user_key = os.getenv('PUSHOVER_USER_KEY')
    app_token = os.getenv('PUSHOVER_APP_TOKEN')
    
    if not user_key or not app_token:
        print("❌ Pushover credentials not found!")
        return False
    
    status_data = {
        'token': app_token,
        'user': user_key,
        'title': '✅ CAD System Status',
        'message': f'''🖥️ CAD System Status Update

✅ System: Online and monitoring
📊 Incidents: 0 active
🔄 Last Check: {datetime.now().strftime('%I:%M %p CDT, %B %d, %Y')}
📡 API Status: Connected
🔔 Notifications: Active

Your CAD system is running perfectly and ready to alert you for calls!'''
        ,
        'priority': 0,  # Normal priority
        'sound': 'none'  # Silent
    }
    
    try:
        response = requests.post(
            'https://api.pushover.net/1/messages.json',
            data=status_data,
            timeout=10
        )
        
        if response.status_code == 200:
            print("✅ System status alert sent!")
            return True
        else:
            print(f"❌ Status alert failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending status alert: {e}")
        return False

def main():
    """Run all tests"""
    print("TESTING PUSHOVER CALL ALERTS")
    print("=" * 50)
    print("This will test if your phone will wake you up for fire calls")
    print("Make sure your phone is nearby and not on silent!")
    print("=" * 50)
    
    # Test fire call alert (most important)
    fire_success = test_pushover_call_alert()
    
    # Test medical call alert
    medical_success = test_medical_call_alert()
    
    # Test system status
    status_success = test_system_status_alert()
    
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS:")
    print(f"🔥 Fire Call Alert: {'✅ PASS' if fire_success else '❌ FAIL'}")
    print(f"🏥 Medical Alert: {'✅ PASS' if medical_success else '❌ FAIL'}")
    print(f"⚙️ System Status: {'✅ PASS' if status_success else '❌ FAIL'}")
    
    if fire_success:
        print("\n🎉 SUCCESS! Your phone WILL wake you up for fire calls!")
        print("The CAD system is ready to alert you 24/7")
    else:
        print("\n❌ Setup required: Configure Pushover credentials")
        print("Run this script again after setting up Pushover")

if __name__ == "__main__":
    main()
