#!/usr/bin/env python3
"""
Enhanced Fire Department CAD System
Modern Computer-Aided Dispatch with advanced scraping and Getac-style interface
"""

import asyncio
import json
import time
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import requests
from flask import Flask, render_template, jsonify, request
import webbrowser
from pathlib import Path

# Import our core modules
from fdd_cad_scraper import FDDCADScraper, Incident, Unit
from directions_service import DirectionsService, RouteInfo
from ai_predictor import AIPredictor, CallPrediction

@dataclass
class CADAlert:
    """CAD Alert for new incidents"""
    incident_id: str
    incident_type: str
    address: str
    priority: str
    timestamp: datetime
    acknowledged: bool = False
    units_assigned: List[str] = None

@dataclass
class Station:
    """Fire Station information"""
    station_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    units: List[str]
    status: str = "Available"

@dataclass
class ResponseProtocol:
    """Fire Department Response Protocol"""
    incident_type: str
    required_units: List[str]
    response_time_target: int  # minutes
    special_instructions: str
    priority_level: int  # 1-5, 1 being highest

class EnhancedFireCAD:
    """Enhanced Fire Department CAD System with modern features"""
    
    def __init__(self, config_file: str = "cad_config.json"):
        self.config = self._load_config(config_file)
        self.scraper = FDDCADScraper()
        self.directions_service = DirectionsService()
        self.ai_predictor = AIPredictor()
        
        # Core data
        self.active_incidents: List[Incident] = []
        self.recent_incidents: List[Incident] = []
        self.alerts: List[CADAlert] = []
        self.stations: Dict[str, Station] = {}
        self.response_protocols: Dict[str, ResponseProtocol] = {}
        
        # System state
        self.monitoring = False
        self.last_update = None
        self.connection_status = "Disconnected"
        
        # Initialize system
        self._load_stations()
        self._load_response_protocols()
        self._setup_web_interface()
        
        print("🚨 Enhanced Fire CAD System initialized")
        print(f"📍 Monitoring agencies: {list(self.config.get('agencies', []))}")
    
    def _load_config(self, config_file: str) -> Dict:
        """Load configuration from file"""
        default_config = {
            "agencies": ["04600"],  # Rogers Fire Department
            "refresh_interval": 30,
            "max_incidents": 50,
            "auto_refresh": True,
            "sound_alerts": True,
            "tts_enabled": True,
            "theme": "dark",
            "your_location": "Rogers, AR",
            "web_port": 5000,
            "web_host": "127.0.0.1"
        }
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    default_config.update(config)
            except Exception as e:
                print(f"Error loading config: {e}")
        
        return default_config
    
    def _load_stations(self):
        """Load fire station information"""
        try:
            with open("station_units.json", 'r') as f:
                station_data = json.load(f)
                
            for station_info in station_data:
                # Extract unit names from assignments
                units = [unit['name'] for unit in station_info.get('assignments', [])]
                
                station = Station(
                    station_id=station_info['id'],
                    name=station_info['name'],
                    address=f"Rogers, AR",  # Default address
                    latitude=36.3320,  # Default coordinates for Rogers
                    longitude=-94.1185,
                    units=units
                )
                self.stations[station.station_id] = station
                
        except Exception as e:
            print(f"Error loading stations: {e}")
            # Create default station
            self.stations["1"] = Station(
                station_id="1",
                name="Rogers Fire Station 1",
                address="Rogers, AR",
                latitude=36.3320,
                longitude=-94.1185,
                units=["E1", "L1", "R1"]
            )
    
    def _load_response_protocols(self):
        """Load fire department response protocols"""
        protocols = {
            "Structure Fire": ResponseProtocol(
                incident_type="Structure Fire",
                required_units=["Engine", "Ladder", "Rescue", "Command"],
                response_time_target=4,
                special_instructions="Full response, establish command, size-up required",
                priority_level=1
            ),
            "Medical Emergency": ResponseProtocol(
                incident_type="Medical Emergency",
                required_units=["Engine", "Ambulance"],
                response_time_target=6,
                special_instructions="Medical response, patient assessment",
                priority_level=2
            ),
            "Traffic Collision": ResponseProtocol(
                incident_type="Traffic Collision",
                required_units=["Engine", "Rescue"],
                response_time_target=5,
                special_instructions="Traffic control, extrication if needed",
                priority_level=2
            ),
            "Hazardous Materials": ResponseProtocol(
                incident_type="Hazardous Materials",
                required_units=["Hazmat", "Engine", "Command"],
                response_time_target=8,
                special_instructions="Hazmat response, establish hot zone",
                priority_level=1
            ),
            "Rescue Operation": ResponseProtocol(
                incident_type="Rescue Operation",
                required_units=["Rescue", "Engine", "Command"],
                response_time_target=6,
                special_instructions="Technical rescue, safety officer required",
                priority_level=1
            )
        }
        
        self.response_protocols = protocols
    
    def _setup_web_interface(self):
        """Setup Flask web interface"""
        self.app = Flask(__name__)
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            return render_template('enhanced_cad.html')
        
        @self.app.route('/test')
        def test():
            return "CAD System is working!"
        
        @self.app.route('/api/status')
        def api_status():
            try:
                return jsonify({
                    "status": self.connection_status,
                    "monitoring": self.monitoring,
                    "last_update": self.last_update.isoformat() if self.last_update else None,
                    "active_incidents": len(self.active_incidents),
                    "recent_incidents": len(self.recent_incidents),
                    "alerts": len([a for a in self.alerts if not a.acknowledged])
                })
            except Exception as e:
                print(f"Error in status API: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/incidents')
        def api_incidents():
            try:
                active_data = [self._incident_to_dict(inc) for inc in self.active_incidents]
                recent_data = [self._incident_to_dict(inc) for inc in self.recent_incidents[-10:]]
                
                print(f"🔍 API returning: {len(active_data)} active, {len(recent_data)} recent incidents")
                if recent_data:
                    print(f"🔍 First recent incident: {recent_data[0]}")
                
                return jsonify({
                    "active": active_data,
                    "recent": recent_data
                })
            except Exception as e:
                print(f"Error in incidents API: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/alerts')
        def api_alerts():
            return jsonify([asdict(alert) for alert in self.alerts if not alert.acknowledged])
        
        @self.app.route('/api/stations')
        def api_stations():
            return jsonify([asdict(station) for station in self.stations.values()])
        
        @self.app.route('/api/refresh', methods=['POST'])
        def api_refresh():
            self.scan_agencies()
            return jsonify({"status": "success"})
        
        @self.app.route('/api/alerts/<alert_id>/acknowledge', methods=['POST'])
        def api_acknowledge_alert(alert_id):
            for alert in self.alerts:
                if alert.incident_id == alert_id:
                    alert.acknowledged = True
                    break
            return jsonify({"status": "success"})
    
    def _incident_to_dict(self, incident: Incident) -> Dict:
        """Convert incident to dictionary for JSON serialization"""
        try:
            # Handle different incident object types
            incident_id = getattr(incident, 'ID', getattr(incident, 'id', 'unknown'))
            incident_type = getattr(incident, 'incident_type', getattr(incident, 'PulsePointIncidentCallType', 'Unknown'))
            address = getattr(incident, 'FullDisplayAddress', getattr(incident, 'address', 'Unknown Address'))
            latitude = getattr(incident, 'Latitude', getattr(incident, 'latitude', 0.0))
            longitude = getattr(incident, 'Longitude', getattr(incident, 'longitude', 0.0))
            
            # Handle call time
            call_time = getattr(incident, 'CallReceivedDateTime', None)
            if call_time and hasattr(call_time, 'isoformat'):
                call_time_str = call_time.isoformat()
            else:
                call_time_str = str(call_time) if call_time else "Unknown"
            
            # Handle units
            units = []
            incident_units = getattr(incident, 'Unit', None)
            if incident_units:
                if isinstance(incident_units, list):
                    units = [getattr(unit, 'UnitID', str(unit)) for unit in incident_units if unit]
                else:
                    units = [str(incident_units)]
            
            # Handle closed time
            closed_time = getattr(incident, 'ClosedDateTime', None)
            status = "Active" if not closed_time else "Closed"
            
            return {
                "id": str(incident_id),
                "incident_type": str(incident_type),
                "address": str(address),
                "latitude": float(latitude) if latitude else 0.0,
                "longitude": float(longitude) if longitude else 0.0,
                "call_time": call_time_str,
                "units": units,
                "priority": self._get_incident_priority(incident),
                "status": status
            }
        except Exception as e:
            print(f"Error converting incident to dict: {e}")
            return {
                "id": "error",
                "incident_type": "Error",
                "address": "Error processing incident",
                "latitude": 0.0,
                "longitude": 0.0,
                "call_time": "Unknown",
                "units": [],
                "priority": "Low",
                "status": "Error"
            }
    
    def _get_incident_priority(self, incident: Incident) -> str:
        """Determine incident priority based on type"""
        try:
            high_priority = ["Structure Fire", "Hazardous Materials", "Rescue Operation"]
            medium_priority = ["Medical Emergency", "Traffic Collision", "Fire Alarm"]
            
            incident_type = getattr(incident, 'incident_type', getattr(incident, 'PulsePointIncidentCallType', 'Unknown'))
            
            if incident_type in high_priority:
                return "High"
            elif incident_type in medium_priority:
                return "Medium"
            else:
                return "Low"
        except Exception as e:
            print(f"Error determining priority: {e}")
            return "Low"
    
    def add_agency(self, agency_id: str):
        """Add agency to monitor"""
        try:
            # The scraper doesn't have add_agency method, just track in config
            if agency_id not in self.config.get('agencies', []):
                self.config['agencies'].append(agency_id)
            print(f"✅ Added agency: {agency_id}")
        except Exception as e:
            print(f"❌ Error adding agency {agency_id}: {e}")
    
    def remove_agency(self, agency_id: str):
        """Remove agency from monitoring"""
        try:
            if agency_id in self.config.get('agencies', []):
                self.config['agencies'].remove(agency_id)
            print(f"✅ Removed agency: {agency_id}")
        except Exception as e:
            print(f"❌ Error removing agency {agency_id}: {e}")
    
    def scan_agencies(self):
        """Scan all configured agencies for new incidents"""
        try:
            self.connection_status = "Connected"
            self.last_update = datetime.now()
            
            # Get incidents from scraper
            all_incidents = []
            for agency_id in self.config.get('agencies', []):
                try:
                    incidents = self.scraper.get_incidents(agency_id)
                    if incidents:
                        # Handle both active and recent incidents
                        if hasattr(incidents, 'active') and incidents.active:
                            all_incidents.extend(incidents.active)
                            print(f"✅ Added {len(incidents.active)} active incidents")
                        if hasattr(incidents, 'recent') and incidents.recent:
                            all_incidents.extend(incidents.recent)
                            print(f"✅ Added {len(incidents.recent)} recent incidents")
                except Exception as e:
                    print(f"❌ Error getting incidents for agency {agency_id}: {e}")
                    continue
            
            # Process incidents
            self._process_incidents(all_incidents)
            
        except Exception as e:
            print(f"❌ Error scanning agencies: {e}")
            self.connection_status = "Error"
    
    def _process_incidents(self, incidents: List[Incident]):
        """Process and categorize incidents"""
        current_time = datetime.now()
        
        # Separate active and recent incidents
        active = []
        recent = []
        
        for incident in incidents:
            if not incident.ClosedDateTime:
                active.append(incident)
            elif (current_time - incident.ClosedDateTime).total_seconds() < 3600:  # Last hour
                recent.append(incident)
        
        # Check for new incidents
        existing_ids = {inc.ID for inc in self.active_incidents}
        new_incidents = [inc for inc in active if inc.ID not in existing_ids]
        
        # Update incident lists
        self.active_incidents = active
        self.recent_incidents = recent[-20:]  # Keep last 20 recent incidents
        
        # Create alerts for new incidents
        for incident in new_incidents:
            self._create_alert(incident)
    
    def _create_alert(self, incident: Incident):
        """Create alert for new incident"""
        alert = CADAlert(
            incident_id=str(incident.ID),
            incident_type=incident.incident_type,
            address=incident.FullDisplayAddress,
            priority=self._get_incident_priority(incident),
            timestamp=datetime.now(),
            units_assigned=[unit.UnitID for unit in incident.Unit] if incident.Unit else []
        )
        
        self.alerts.append(alert)
        
        # Print alert
        print(f"🚨 NEW INCIDENT: {alert.incident_type}")
        print(f"📍 Location: {alert.address}")
        print(f"⚡ Priority: {alert.priority}")
        print(f"🚑 Units: {', '.join(alert.units_assigned) if alert.units_assigned else 'None'}")
        print("-" * 50)
        
        # Sound alert if enabled
        if self.config.get('sound_alerts', True):
            self._play_alert_sound(alert.priority)
    
    def _play_alert_sound(self, priority: str):
        """Play alert sound based on priority"""
        try:
            if priority == "High":
                # High priority sound
                print("🔊 Playing high priority alert sound")
            elif priority == "Medium":
                # Medium priority sound
                print("🔊 Playing medium priority alert sound")
            else:
                # Low priority sound
                print("🔊 Playing low priority alert sound")
        except Exception as e:
            print(f"Error playing alert sound: {e}")
    
    def get_route_to_incident(self, incident: Incident) -> Optional[RouteInfo]:
        """Get route to incident scene"""
        try:
            return self.directions_service.get_emergency_route(
                self.config.get('your_location', 'Rogers, AR'),
                incident.FullDisplayAddress
            )
        except Exception as e:
            print(f"Error getting route: {e}")
            return None
    
    def get_response_protocol(self, incident_type: str) -> Optional[ResponseProtocol]:
        """Get response protocol for incident type"""
        return self.response_protocols.get(incident_type)
    
    def start_monitoring(self):
        """Start monitoring agencies"""
        if self.monitoring:
            print("⚠️ Monitoring already active")
            return
        
        self.monitoring = True
        print("🚨 Starting incident monitoring...")
        
        # Initial scan
        self.scan_agencies()
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                self.scan_agencies()
                time.sleep(self.config.get('refresh_interval', 30))
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                time.sleep(10)
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring = False
        print("🛑 Monitoring stopped")
    
    def start_web_interface(self):
        """Start web interface"""
        try:
            port = self.config.get('web_port', 5000)
            host = self.config.get('web_host', '127.0.0.1')
            
            print(f"🌐 Starting web interface at http://{host}:{port}")
            
            # Open browser
            webbrowser.open(f"http://{host}:{port}")
            
            # Start Flask app
            self.app.run(host=host, port=port, debug=True, use_reloader=False)
            
        except Exception as e:
            print(f"Error starting web interface: {e}")

def main():
    """Main function"""
    print("🚨 Enhanced Fire Department CAD System")
    print("=" * 50)
    
    # Create CAD system
    cad = EnhancedFireCAD()
    
    # Add Rogers Fire Department
    cad.add_agency("04600")
    
    # Start monitoring
    cad.start_monitoring()
    
    try:
        # Start web interface
        cad.start_web_interface()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down CAD system...")
        cad.stop_monitoring()

if __name__ == "__main__":
    main()
