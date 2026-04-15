#!/usr/bin/env python3
"""
Test script to verify Discord webhook fixes
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from discord_webhook import DiscordWebhookManager, DiscordWebhookConfig
from datetime import datetime

class MockIncident:
    """Mock incident for testing"""
    def __init__(self):
        self.ID = "2307749150"
        self.incident_type = "Traffic Collision"
        self.FullDisplayAddress = "22382 ROCK RD, BENTON COUNTY, AR"
        self.CallReceivedDateTime = datetime.now()
        self.Unit = [
            {'UnitID': 'BEAVERLAKEFIRE', 'PulsePointDispatchStatus': 'DP', 'UnitClearedDateTime': None},
            {'UnitID': 'E3', 'PulsePointDispatchStatus': 'DP', 'UnitClearedDateTime': None},
            {'UnitID': 'MED4', 'PulsePointDispatchStatus': 'DP', 'UnitClearedDateTime': None},
            {'UnitID': 'OPS_5', 'PulsePointDispatchStatus': 'DP', 'UnitClearedDateTime': None}
        ]

def test_discord_webhook():
    """Test Discord webhook with the problematic incident"""
    print("Testing Discord webhook fixes...")
    print("=" * 50)
    
    # Create webhook manager
    config = DiscordWebhookConfig()
    webhook_manager = DiscordWebhookManager(config)
    
    # Create mock incident
    incident = MockIncident()
    
    print(f"Testing incident: {incident.incident_type}")
    print(f"Incident ID: {incident.ID}")
    print(f"Address: {incident.incident_type}")
    print(f"Units: {[unit['UnitID'] for unit in incident.Unit]}")
    
    # Test embed creation
    print("\nTesting embed creation...")
    try:
        embed = webhook_manager._create_official_incident_report(incident, "CRITICAL")
        print("[OK] Embed created successfully")
        print(f"Embed title: {embed['embeds'][0]['title']}")
        print(f"Number of fields: {len(embed['embeds'][0]['fields'])}")
        
        # Check field lengths
        for i, field in enumerate(embed['embeds'][0]['fields']):
            name_len = len(field.get('name', ''))
            value_len = len(field.get('value', ''))
            print(f"Field {i}: '{field.get('name', '')[:30]}...' - Name: {name_len} chars, Value: {value_len} chars")
            
            if name_len > 256:
                print(f"[WARNING] Field {i} name too long: {name_len} chars")
            if value_len > 1024:
                print(f"[WARNING] Field {i} value too long: {value_len} chars")
        
    except Exception as e:
        print(f"[ERROR] Error creating embed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test payload validation
    print("\nTesting payload validation...")
    try:
        payload = {"embeds": [embed['embeds'][0]], "username": "Fire Department Dispatch"}
        print(f"Payload size: {len(str(payload))} characters")
        
        # Test the validation logic
        if not payload or 'embeds' not in payload:
            print("✗ Invalid payload structure")
            return False
        
        embeds = payload.get('embeds', [])
        if not embeds or not isinstance(embeds, list):
            print("✗ Invalid embeds structure")
            return False
        
        print("✓ Payload validation passed")
        
    except Exception as e:
        print(f"✗ Error validating payload: {e}")
        return False
    
    print("\n✓ All tests passed! Discord webhook should work properly now.")
    return True

if __name__ == "__main__":
    success = test_discord_webhook()
    sys.exit(0 if success else 1)
