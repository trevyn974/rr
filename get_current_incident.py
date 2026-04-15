#!/usr/bin/env python3
"""
Get the current REAL active incident from web server and send to Discord
"""

import sys
import os
import requests
import json
from datetime import datetime

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from discord_webhook import DiscordWebhookManager, DiscordWebhookConfig

def get_current_real_incident():
    """Get current real active incident and send to Discord"""
    print("Getting CURRENT Real Active Incident")
    print("=" * 50)
    
    try:
        # Get incidents from web server
        print("Fetching current incidents from web server...")
        response = requests.get('http://localhost:5000/api/incidents', timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            active_incidents = data.get('active', [])
            recent_incidents = data.get('recent', [])
            
            print(f"Current status:")
            print(f"  Active incidents: {len(active_incidents)}")
            print(f"  Recent incidents: {len(recent_incidents)}")
            
            if active_incidents:
                print("\nCURRENT ACTIVE INCIDENTS:")
                for i, incident in enumerate(active_incidents):
                    print(f"  {i+1}. {incident.get('type', 'Unknown')} - {incident.get('address', 'Unknown')} (ID: {incident.get('id', 'Unknown')})")
                
                # Send the first active incident to Discord
                incident = active_incidents[0]
                print(f"\nSending CURRENT real incident to Discord:")
                print(f"  Type: {incident.get('type', 'Unknown')}")
                print(f"  Address: {incident.get('address', 'Unknown')}")
                print(f"  ID: {incident.get('id', 'Unknown')}")
                print(f"  Units: {incident.get('units', [])}")
                
                # Create Discord webhook manager
                config = DiscordWebhookConfig()
                webhook_manager = DiscordWebhookManager(config)
                
                # Clear rate limits to ensure it sends
                webhook_manager.clear_rate_limits()
                webhook_manager.clear_sent_incidents()
                
                # Create a mock incident object from the real data
                from dataclasses import dataclass
                from typing import List, Optional
                
                @dataclass
                class MockUnit:
                    UnitID: str
                
                @dataclass
                class MockIncident:
                    ID: int
                    incident_type: str
                    FullDisplayAddress: str
                    CallReceivedDateTime: datetime
                    Unit: Optional[List[MockUnit]] = None
                    AlarmLevel: Optional[int] = None
                    Latitude: Optional[float] = None
                    Longitude: Optional[float] = None
                    Agency: Optional[str] = None
                
                # Convert web server incident to mock incident
                units = []
                if incident.get('units'):
                    for unit in incident.get('units', []):
                        units.append(MockUnit(unit))
                
                mock_incident = MockIncident(
                    ID=int(incident.get('id', 0)),
                    incident_type=incident.get('type', 'Unknown Incident'),
                    FullDisplayAddress=incident.get('address', 'Unknown Address'),
                    CallReceivedDateTime=datetime.now(),
                    Unit=units if units else None,
                    AlarmLevel=incident.get('alarm_level', 1),
                    Latitude=incident.get('latitude'),
                    Longitude=incident.get('longitude'),
                    Agency="Rogers Fire Department"
                )
                
                # Send to Discord
                success = webhook_manager.send_incident_notification(mock_incident, "high", "real_call")
                
                if success:
                    print("SUCCESS: CURRENT real active incident sent to Discord!")
                    print("Check your Discord channel for the official incident report.")
                else:
                    print("FAILED: Could not send current incident to Discord.")
                
                return success
            else:
                print("No active incidents currently found.")
                return False
        else:
            print(f"Error: Web server returned status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Error getting current incidents: {e}")
        return False

if __name__ == "__main__":
    get_current_real_incident()
