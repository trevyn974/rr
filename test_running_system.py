#!/usr/bin/env python3
"""
Test the currently running CAD system's Pushover capability
"""

import requests
import json

def test_running_system():
    """Test if the running CAD system can send Pushover alerts"""
    
    print("TESTING RUNNING CAD SYSTEM")
    print("=" * 40)
    
    try:
        # Test the system status
        response = requests.get('http://127.0.0.1:5000/api/status', timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print("System Status:")
            print(f"  Running: {data.get('system_running', 'Unknown')}")
            print(f"  Pushover Enabled: {data.get('pushover_enabled', 'Unknown')}")
            print(f"  Discord Enabled: {data.get('discord_enabled', 'Unknown')}")
            print(f"  SMS Enabled: {data.get('sms_enabled', 'Unknown')}")
            print(f"  TTS Enabled: {data.get('tts_enabled', 'Unknown')}")
            
            # Test Pushover directly
            print("\nTesting Pushover...")
            pushover_response = requests.post('http://127.0.0.1:5000/api/test_pushover', timeout=10)
            
            if pushover_response.status_code == 200:
                print("Pushover test sent successfully!")
                print("Check your phone for the test alert")
            else:
                print(f"Pushover test failed: {pushover_response.status_code}")
                print(f"Response: {pushover_response.text}")
            
            # Test with real data
            print("\nTesting Pushover with real data...")
            real_data_response = requests.post('http://127.0.0.1:5000/api/test_pushover_real', timeout=10)
            
            if real_data_response.status_code == 200:
                print("Real data Pushover test sent!")
                print("Check your phone for the real data test alert")
            else:
                print(f"Real data test failed: {real_data_response.status_code}")
                print(f"Response: {real_data_response.text}")
                
        else:
            print(f"Failed to get system status: {response.status_code}")
            
    except Exception as e:
        print(f"Error testing system: {e}")

if __name__ == "__main__":
    test_running_system()




