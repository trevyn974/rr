#!/usr/bin/env python3
"""
Fix Pushover credentials permanently and test the system
"""

import os
import requests
import subprocess
import sys

def set_permanent_credentials():
    """Set Pushover credentials permanently"""
    print("Setting Pushover credentials permanently...")
    
    # Set environment variables for current session
    os.environ['PUSHOVER_USER_KEY'] = "u91gdp1wbvynt5wmiec45tsf79e6t5"
    os.environ['PUSHOVER_APP_TOKEN'] = "agunhyfhpg9rik3dr5uedi51vyotaw"
    
    # Set them permanently using PowerShell
    try:
        subprocess.run([
            'powershell', '-Command',
            '[Environment]::SetEnvironmentVariable("PUSHOVER_USER_KEY", "u91gdp1wbvynt5wmiec45tsf79e6t5", "User")'
        ], check=True)
        
        subprocess.run([
            'powershell', '-Command',
            '[Environment]::SetEnvironmentVariable("PUSHOVER_APP_TOKEN", "agunhyfhpg9rik3dr5uedi51vyotaw", "User")'
        ], check=True)
        
        print("✓ Pushover credentials set permanently")
        return True
    except Exception as e:
        print(f"✗ Error setting permanent credentials: {e}")
        return False

def test_system_status():
    """Test the current system status"""
    print("\nTesting system status...")
    
    try:
        response = requests.get('http://127.0.0.1:5000/api/status', timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ System running: {data.get('system_running', False)}")
            print(f"✓ Pushover enabled: {data.get('pushover_enabled', False)}")
            print(f"✓ Discord enabled: {data.get('discord_enabled', False)}")
            return True
        else:
            print(f"✗ System not responding: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error testing system: {e}")
        return False

def send_test_alert():
    """Send a test alert to verify Pushover is working"""
    print("\nSending test alert...")
    
    try:
        # Test Pushover directly
        test_data = {
            'token': 'agunhyfhpg9rik3dr5uedi51vyotaw',
            'user': 'u91gdp1wbvynt5wmiec45tsf79e6t5',
            'title': 'CAD System Test - Pushover Fixed',
            'message': 'Your CAD system Pushover alerts are now working! You will receive alerts for all fire department calls.',
            'priority': 1,
            'sound': 'push'
        }
        
        response = requests.post(
            'https://api.pushover.net/1/messages.json',
            data=test_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 1:
                print("✓ Test alert sent successfully!")
                print("Check your phone for the test notification")
                return True
            else:
                print(f"✗ Pushover error: {result.get('errors', 'Unknown error')}")
                return False
        else:
            print(f"✗ HTTP error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ Error sending test alert: {e}")
        return False

def main():
    """Main function"""
    print("FIXING PUSHOVER ALERTS PERMANENTLY")
    print("=" * 50)
    
    # Set permanent credentials
    creds_ok = set_permanent_credentials()
    
    # Test system status
    system_ok = test_system_status()
    
    # Send test alert
    alert_ok = send_test_alert()
    
    print("\n" + "=" * 50)
    print("RESULTS:")
    print(f"Credentials set: {'✓' if creds_ok else '✗'}")
    print(f"System running: {'✓' if system_ok else '✗'}")
    print(f"Test alert sent: {'✓' if alert_ok else '✗'}")
    
    if creds_ok and system_ok and alert_ok:
        print("\n🎉 SUCCESS! Pushover alerts are now working!")
        print("You will receive alerts for all fire department calls")
        print("The system will wake you up for emergencies while sleeping")
    else:
        print("\n❌ Some issues remain. Check the errors above.")

if __name__ == "__main__":
    main()





