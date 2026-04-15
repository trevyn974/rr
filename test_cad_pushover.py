#!/usr/bin/env python3
"""
Test CAD System Pushover Integration
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from cad_system import CADSystem, CADConfig, PushoverManager
from fdd_cad_scraper import Incident
from datetime import datetime

def test_cad_pushover():
    """Test CAD system Pushover integration"""
    
    print("CAD SYSTEM PUSHOVER TEST")
    print("=" * 40)
    
    # Create CAD config with Pushover enabled
    config = CADConfig(
        pushover_enabled=True,
        pushover_user_key="u91gdp1wbvynt5wmiec45tsf79e6t5",
        pushover_app_token="agunhyfhpg9rik3dr5uedi51vyotaw",
        pushover_priorities=["critical", "high", "medium"]
    )
    
    print(f"Pushover enabled: {config.pushover_enabled}")
    print(f"Pushover priorities: {config.pushover_priorities}")
    
    # Create CAD system
    cad_system = CADSystem(config)
    
    print(f"Pushover manager initialized: {cad_system.pushover_manager is not None}")
    
    if cad_system.pushover_manager:
        print("Testing Pushover manager...")
        success = cad_system.pushover_manager.test_connection()
        print(f"Pushover test result: {success}")
        
        # Test incident alert
        print("\nTesting incident alert...")
        
        # Create a mock incident similar to the real one
        class MockIncident:
            def __init__(self):
                self.incident_type = "Public Service"
                self.FullDisplayAddress = "6109 W VALLEY FORGE DR, ROGERS, AR"
                self.ID = "2307526250"
                self.CallReceivedDateTime = datetime.now()
                self.Unit = [{"UnitID": "E8", "PulsePointDispatchStatus": "DP", "UnitClearedDateTime": None}]
        
        mock_incident = MockIncident()
        priority = "MEDIUM"
        
        print(f"Incident type: {mock_incident.incident_type}")
        print(f"Priority: {priority}")
        print(f"Priority in allowed list: {priority.lower() in [p.lower() for p in config.pushover_priorities]}")
        
        # Test the incident alert
        success = cad_system.pushover_manager.send_incident_alert(mock_incident, priority)
        print(f"Incident alert result: {success}")
        
    else:
        print("ERROR: Pushover manager not initialized!")

if __name__ == "__main__":
    test_cad_pushover()



