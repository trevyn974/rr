#!/usr/bin/env python3
"""
Test script to verify phone notifications are working
"""

from cad_system import CADSystem, CADConfig

def test_phone_notifications():
    """Test phone notifications"""
    print("Testing FDD CAD System Phone Notifications")
    print("=" * 50)
    
    # Create CAD system with configuration
    config = CADConfig(
        pushover_enabled=True,
        pushover_user_key="u91gdp1wbvynt5wmiec45tsf79e6t5",
        pushover_app_token="agunhyfhpg9rik3dr5uedi51vyotaw",
        pushover_priorities=["critical", "high", "medium"]
    )
    
    cad = CADSystem(config)
    
    # Test phone notification
    print("\n1. Testing basic phone notification...")
    success = cad.test_phone_notification()
    
    if success:
        print("PASS: Phone notification test PASSED")
    else:
        print("FAIL: Phone notification test FAILED")
    
    # Test system alert
    print("\n2. Testing system alert...")
    success = cad.test_pushover_system_alert()
    
    if success:
        print("PASS: System alert test PASSED")
    else:
        print("FAIL: System alert test FAILED")
    
    # Test Pushover connection
    print("\n3. Testing Pushover connection...")
    success = cad.test_pushover()
    
    if success:
        print("PASS: Pushover connection test PASSED")
    else:
        print("FAIL: Pushover connection test FAILED")
    
    print("\n" + "=" * 50)
    print("Phone notification testing complete!")
    print("Check your phone for notifications.")

if __name__ == "__main__":
    test_phone_notifications()
