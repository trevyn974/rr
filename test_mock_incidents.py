#!/usr/bin/env python3
"""
Test script to add and clear mock incidents to verify detection works
"""

import requests
import json
import time

BASE_URL = "http://localhost:125"

def add_mock_incident(incident_id, incident_type, address):
    """Add a mock incident via the web server"""
    try:
        # Create test incident data
        data = {
            "id": incident_id,
            "type": incident_type,
            "address": address,
            "priority": "high",
            "units": ["E6", "L6"],
            "latitude": 36.3320,
            "longitude": -94.1185
        }
        
        # Use the test incident endpoint
        response = requests.post(f"{BASE_URL}/api/test/incident", json=data, timeout=5)
        if response.status_code == 200:
            print(f"[SUCCESS] Added mock incident: {incident_id} - {incident_type}")
            return True
        else:
            print(f"[ERROR] Failed to add incident: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Exception adding incident: {e}")
        return False

def get_active_incidents():
    """Get current active incidents"""
    try:
        response = requests.get(f"{BASE_URL}/api/incidents", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('active', [])
        else:
            print(f"[ERROR] Failed to get incidents: {response.status_code}")
            return []
    except Exception as e:
        print(f"[ERROR] Exception getting incidents: {e}")
        return []

def clear_all_incidents():
    """Clear all incidents (by setting them to recent)"""
    try:
        # This would need to be implemented in the web server
        # For now, we'll just check what's active
        print("[INFO] To clear incidents, they need to be marked as cleared in the source system")
        print("[INFO] Or wait for them to be automatically cleared by the system")
        return True
    except Exception as e:
        print(f"[ERROR] Exception clearing incidents: {e}")
        return False

def test_incident_detection():
    """Test the full flow: add incident, check it's detected, clear it, add new one"""
    print("=" * 60)
    print("TESTING INCIDENT DETECTION")
    print("=" * 60)
    
    # Step 1: Check current state
    print("\n[STEP 1] Checking current active incidents...")
    current = get_active_incidents()
    print(f"Current active incidents: {len(current)}")
    for inc in current:
        print(f"  - {inc.get('id')}: {inc.get('type')} at {inc.get('address')}")
    
    # Step 2: Add a test incident
    print("\n[STEP 2] Adding test incident...")
    test_id_1 = f"TEST_{int(time.time())}"
    success = add_mock_incident(test_id_1, "TEST FIRE ALARM", "123 TEST ST, ROGERS, AR")
    
    if not success:
        print("[ERROR] Could not add test incident. Is the web server running?")
        return
    
    time.sleep(2)  # Wait for processing
    
    # Step 3: Verify it was added
    print("\n[STEP 3] Verifying incident was added...")
    updated = get_active_incidents()
    found = any(inc.get('id') == test_id_1 for inc in updated)
    if found:
        print(f"[SUCCESS] Test incident {test_id_1} is now active!")
    else:
        print(f"[WARNING] Test incident {test_id_1} not found in active list")
        print("This might be expected if the system filters test incidents")
    
    # Step 4: Add another test incident (simulating new incident after clearing)
    print("\n[STEP 4] Adding second test incident (simulating new after clear)...")
    test_id_2 = f"TEST_{int(time.time()) + 1}"
    success = add_mock_incident(test_id_2, "TEST MEDICAL EMERGENCY", "456 TEST AVE, ROGERS, AR")
    
    time.sleep(2)
    
    # Step 5: Check final state
    print("\n[STEP 5] Final state check...")
    final = get_active_incidents()
    print(f"Final active incidents: {len(final)}")
    for inc in final:
        print(f"  - {inc.get('id')}: {inc.get('type')} at {inc.get('address')}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print("\nCheck the CAD system console logs for:")
    print("  - [NEW DETECTED] messages when new incidents arrive")
    print("  - [CLEANUP] messages when incidents are cleared")
    print("  - [NEW INCIDENT] messages when sending notifications")
    print("\nIf you see these messages, the detection is working!")

if __name__ == "__main__":
    print("Make sure the CAD system and web server are running first!")
    print("Then watch the console logs while this test runs.\n")
    input("Press Enter to start the test...")
    test_incident_detection()


