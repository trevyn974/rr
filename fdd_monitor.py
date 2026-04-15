#!/usr/bin/env python3
"""
FDD CAD Monitor - Main monitoring application
Continuously monitors fire department dispatch data and processes incidents
"""

import time
import json
import datetime
from typing import List, Dict
from fdd_cad_scraper import FDDCADScraper, Incident, Incidents
from fdd_config import ConfigManager, FDDConfig, MonitoringLocation


class IncidentProcessor:
    """Processes and filters incidents based on configuration"""
    
    def __init__(self, config: FDDConfig):
        self.config = config
    
    def is_incident_relevant(self, incident: Incident, location: MonitoringLocation) -> bool:
        """Check if an incident is relevant to a monitoring location"""
        if not location.enabled:
            return False
        
        # Check if incident is within radius
        if not self._is_within_radius(incident, location):
            return False
        
        # Check global filters
        if not self.config.global_filters.is_allowed(incident.incident_type):
            return False
        
        # Check location-specific filters
        if not location.filters.is_allowed(incident.incident_type):
            return False
        
        return True
    
    def _is_within_radius(self, incident: Incident, location: MonitoringLocation) -> bool:
        """Check if incident is within the monitoring radius"""
        # Simple distance calculation (in a real implementation, you'd use proper geodetic calculations)
        lat_diff = abs(incident.latitude - location.latitude)
        lon_diff = abs(incident.longitude - location.longitude)
        
        # Rough conversion: 1 degree ≈ 111,000 meters
        distance_meters = ((lat_diff ** 2 + lon_diff ** 2) ** 0.5) * 111000
        
        return distance_meters <= location.radius_meters
    
    def process_incidents(self, incidents: Incidents) -> List[Dict]:
        """Process incidents and return relevant ones with metadata"""
        relevant_incidents = []
        
        for incident in incidents.active_incidents + incidents.recent_incidents:
            for location in self.config.locations:
                if self.is_incident_relevant(incident, location):
                    incident_data = {
                        "incident": incident,
                        "location": location,
                        "distance_meters": self._calculate_distance(incident, location),
                        "timestamp": datetime.datetime.now().isoformat()
                    }
                    relevant_incidents.append(incident_data)
        
        return relevant_incidents


class NotificationManager:
    """Manages notifications for relevant incidents"""
    
    def __init__(self, config: FDDConfig):
        self.config = config
        self.notified_incidents = set()  # Track already notified incidents
    
    def send_notification(self, incident_data: Dict):
        """Send notification for an incident"""
        incident = incident_data["incident"]
        location = incident_data["location"]
        
        # Avoid duplicate notifications
        incident_key = f"{incident.incident_id}_{location.name}"
        if incident_key in self.notified_incidents:
            return
        
        self.notified_incidents.add(incident_key)
        
        # Console notification (basic implementation)
        if "console" in self.config.notification_methods:
            self._console_notification(incident_data)
        
        # Add other notification methods here (email, SMS, push notifications, etc.)
    
    def _console_notification(self, incident_data: Dict):
        """Send console notification"""
        incident = incident_data["incident"]
        location = incident_data["location"]
        distance = incident_data["distance_meters"]
        
        print(f"\n🚨 FIRE DEPARTMENT DISPATCH ALERT 🚨")
        print(f"Location: {location.name}")
        print(f"Incident: {incident.incident_type}")
        print(f"Address: {incident.full_display_address}")
        print(f"Distance: {distance:.0f} meters")
        print(f"Time: {incident.call_received_datetime}")
        print(f"Units: {[unit.unit_id for unit in incident.units]}")
        print(f"Alarm Level: {incident.alarm_level}")
        print("-" * 50)


class FDDMonitor:
    """Main monitoring application"""
    
    def __init__(self, config_file: str = "fdd_config.json"):
        self.config_manager = ConfigManager(config_file)
        self.config = self.config_manager.load_config()
        self.scraper = FDDCADScraper()
        self.processor = IncidentProcessor(self.config)
        self.notifier = NotificationManager(self.config)
        
        self.running = False
        self.last_scan_time = 0
    
    def start_monitoring(self):
        """Start the monitoring loop"""
        print("FDD CAD Monitor Starting...")
        print(f"Monitoring {len(self.config.agencies)} agencies")
        print(f"Watching {len(self.config.locations)} locations")
        print(f"Scan interval: {self.config.scan_interval_seconds} seconds")
        print("Press Ctrl+C to stop")
        print("-" * 50)
        
        self.running = True
        
        try:
            while self.running:
                self._scan_agencies()
                time.sleep(self.config.scan_interval_seconds)
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
        except Exception as e:
            print(f"Monitoring error: {e}")
        finally:
            self.running = False
    
    def _scan_agencies(self):
        """Scan all configured agencies for new incidents"""
        current_time = time.time()
        
        for agency_id in self.config.agencies:
            try:
                # Get incidents from agency
                incidents = self.scraper.get_incidents(agency_id)
                
                if incidents.active_incidents or incidents.recent_incidents:
                    # Process incidents
                    relevant_incidents = self.processor.process_incidents(incidents)
                    
                    # Send notifications for relevant incidents
                    for incident_data in relevant_incidents:
                        self.notifier.send_notification(incident_data)
                
                # Small delay between agency scans
                time.sleep(1)
                
            except Exception as e:
                print(f"Error scanning agency {agency_id}: {e}")
        
        self.last_scan_time = current_time
    
    def stop_monitoring(self):
        """Stop the monitoring loop"""
        self.running = False
    
    def get_status(self) -> Dict:
        """Get current monitoring status"""
        return {
            "running": self.running,
            "last_scan": datetime.datetime.fromtimestamp(self.last_scan_time).isoformat(),
            "agencies_monitored": len(self.config.agencies),
            "locations_monitored": len(self.config.locations),
            "scan_interval": self.config.scan_interval_seconds
        }


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="FDD CAD Monitor - Fire Department Dispatch Monitor")
    parser.add_argument("--config", default="fdd_config.json", help="Configuration file path")
    parser.add_argument("--test", action="store_true", help="Test mode - run one scan and exit")
    
    args = parser.parse_args()
    
    # Create and start monitor
    monitor = FDDMonitor(args.config)
    
    if args.test:
        print("Running in test mode...")
        monitor._scan_agencies()
        print("Test scan completed")
    else:
        monitor.start_monitoring()


if __name__ == "__main__":
    main()
