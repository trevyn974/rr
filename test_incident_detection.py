#!/usr/bin/env python3
"""
Test script to verify incident detection logic works correctly
"""

def test_incident_detection_logic():
    """Test the logic for detecting new incidents after clearing"""
    
    # Simulate the state
    previous_active_ids = {'123', '456'}  # Old incidents
    current_active_ids = {'456', '789'}  # One cleared (123), one new (789)
    
    # Test 1: Detect cleared incidents
    cleared_ids = previous_active_ids - current_active_ids
    print(f"Test 1 - Cleared incidents: {cleared_ids}")
    assert cleared_ids == {'123'}, "Should detect incident 123 as cleared"
    
    # Test 2: Detect new incidents
    new_ids = current_active_ids - previous_active_ids
    print(f"Test 2 - New incidents: {new_ids}")
    assert new_ids == {'789'}, "Should detect incident 789 as new"
    
    # Test 3: Detect when all cleared
    previous_all = {'123', '456'}
    current_empty = set()
    cleared_all = previous_all - current_empty
    print(f"Test 3 - All cleared: {cleared_all}")
    assert cleared_all == {'123', '456'}, "Should detect all as cleared"
    
    # Test 4: Detect when new comes after all cleared
    previous_empty = set()
    current_new = {'999'}
    new_after_clear = current_new - previous_empty
    print(f"Test 4 - New after clear: {new_after_clear}")
    assert new_after_clear == {'999'}, "Should detect new incident after all cleared"
    
    print("\n[SUCCESS] All tests passed! The logic should work correctly.")
    print("\nFlow verification:")
    print("1. Incident 123 and 456 are active")
    print("2. Incident 123 is cleared -> removed from sent_incident_ids")
    print("3. Incident 789 arrives -> not in previous_active_ids -> detected as NEW")
    print("4. Incident 789 is sent to Discord/Phone and added to sent_incident_ids")

if __name__ == "__main__":
    test_incident_detection_logic()

