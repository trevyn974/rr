#!/usr/bin/env python3
"""
FDD CAD Web Server - Flask-based web server for the CAD system
Provides REST API endpoints for the web interface
"""

from flask import Flask, jsonify, render_template_string, request, send_from_directory
from flask_cors import CORS
import json
import threading
import time
from datetime import datetime
from dataclasses import asdict
from cad_system import CADSystem, CADConfig
from fdd_cad_scraper import FDDCADScraper
from discord_webhook import DiscordWebhookConfig
import os

app = Flask(__name__)
CORS(app)

# Configure Flask for better stability
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

# Add error handlers to prevent server crashes
@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors gracefully"""
    print(f"[ERROR] Internal server error: {error}")
    return jsonify({"error": "Internal server error", "message": str(error)}), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(Exception)
def handle_exception(e):
    """Handle all unhandled exceptions"""
    print(f"[ERROR] Unhandled exception: {e}")
    import traceback
    traceback.print_exc()
    return jsonify({"error": "An error occurred", "message": str(e)}), 500

# Global CAD system instance
cad_system = None
pulsepoint_scraper = None

def initialize_cad_system():
    """Initialize the CAD system"""
    global cad_system, pulsepoint_scraper
    config = CADConfig(
        refresh_interval=15,
        max_incidents_display=50,
        auto_refresh=True,
        sound_alerts=True,
        theme="dark",
        sms_enabled=True,
        sms_phone_number="4795059422",
        sms_priorities=["critical", "high"],
        discord_enabled=True,
        discord_webhook_config=DiscordWebhookConfig()
    )
    cad_system = CADSystem(config)
    
    # Initialize PulsePoint scraper for map data
    pulsepoint_scraper = FDDCADScraper()
    
    # Add Rogers Fire Department (from your test)
    cad_system.add_agency("04600")
    
    # Set up default geofences for map
    pulsepoint_scraper.add_city_geofence("Rogers", 36.3320, -94.1185, 15, "#FF0000")
    pulsepoint_scraper.add_city_geofence("Fayetteville", 36.0626, -94.1574, 20, "#0000FF")
    
    # Start monitoring
    cad_system.start_monitoring()
    print("CAD System initialized and monitoring started")
    print("PulsePoint scraper initialized with geofencing")

@app.route('/')
def index():
    """Serve the main CAD interface"""
    try:
        with open('cad_web_interface.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        return "CAD interface file not found", 404

@app.route('/pulsepoint-map')
def pulsepoint_map():
    """Serve the PulsePoint map interface"""
    try:
        with open('pulsepoint_map_interface.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        return "PulsePoint map interface file not found", 404

@app.route('/live-map')
def live_map():
    """Serve the live incidents map interface"""
    try:
        with open('live_incidents_map.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        return "Live incidents map file not found", 404

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files like images, CSS, JS, etc."""
    try:
        return send_from_directory('.', filename)
    except FileNotFoundError:
        return f"File {filename} not found", 404

@app.route('/api/health')
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "cad_system_initialized": cad_system is not None
    })

@app.route('/api/status')
def get_status():
    """Get current CAD system status"""
    if not cad_system:
        print("[ERROR] CAD system not initialized when status requested")
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        status = cad_system.get_status_summary()
        
        # Add circuit breaker status
        if hasattr(cad_system.scraper, 'circuit_breaker'):
            status['circuit_breaker'] = {
                'is_open': cad_system.scraper.circuit_breaker['is_open'],
                'failure_count': cad_system.scraper.circuit_breaker['failure_count'],
                'last_failure_time': cad_system.scraper.circuit_breaker['last_failure_time'],
                'recovery_timeout': cad_system.scraper.circuit_breaker['recovery_timeout']
            }
        
        # Add fallback data status
        if hasattr(cad_system.scraper, 'fallback_data'):
            fallback_status = {}
            for agency_id, data in cad_system.scraper.fallback_data.items():
                age = time.time() - cad_system.scraper.fallback_data_age.get(agency_id, 0)
                fallback_status[agency_id] = {
                    'has_data': len(data) > 0,
                    'age_seconds': age,
                    'is_fresh': age < cad_system.scraper.fallback_max_age
                }
            status['fallback_data'] = fallback_status
        
        print(f"[STATUS] Status requested - System running: {status.get('system_running', False)}")
        return jsonify(status)
    except Exception as e:
        print(f"[ERROR] Error getting status: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/incidents')
def get_incidents():
    """Get current incidents data"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        # Convert incidents to JSON-serializable format
        active_incidents = []
        print(f"[DEBUG] API: Found {len(cad_system.current_incidents.active)} active incidents")
        for incident in cad_system.current_incidents.active:
            units_with_stations = []
            if incident.Unit:
                for unit in incident.Unit:
                    station = cad_system.get_unit_station(unit.UnitID)
                    units_with_stations.append({
                        "unit_id": unit.UnitID,
                        "station": station or "Unknown Station"
                    })
            
            active_incidents.append({
                "id": str(incident.ID),
                "type": incident.incident_type,
                "address": incident.FullDisplayAddress,
                "time": incident.CallReceivedDateTime.isoformat(),
                "priority": _determine_priority(incident.incident_type),
                "units": [unit.UnitID for unit in incident.Unit] if incident.Unit else [],
                "units_with_stations": units_with_stations,
                "latitude": incident.Latitude,
                "longitude": incident.Longitude,
                "alarm_level": incident.AlarmLevel
            })
        
        recent_incidents = []
        for incident in cad_system.current_incidents.recent:
            units_with_stations = []
            if incident.Unit:
                for unit in incident.Unit:
                    station = cad_system.get_unit_station(unit.UnitID)
                    units_with_stations.append({
                        "unit_id": unit.UnitID,
                        "station": station or "Unknown Station"
                    })
            
            recent_incidents.append({
                "id": str(incident.ID),
                "type": incident.incident_type,
                "address": incident.FullDisplayAddress,
                "time": incident.CallReceivedDateTime.isoformat(),
                "priority": _determine_priority(incident.incident_type),
                "units": [unit.UnitID for unit in incident.Unit] if incident.Unit else [],
                "units_with_stations": units_with_stations,
                "latitude": incident.Latitude,
                "longitude": incident.Longitude,
                "alarm_level": incident.AlarmLevel
            })
        
        return jsonify({
            "active": active_incidents,
            "recent": recent_incidents,
            "last_update": cad_system.last_update.isoformat() if cad_system.last_update else None
        })
    except Exception as e:
        print(f"[ERROR] Error in get_incidents endpoint: {e}")
        import traceback
        traceback.print_exc()
        # Return empty data instead of crashing
        return jsonify({
            "active": [],
            "recent": [],
            "error": str(e),
            "last_update": None
        }), 200  # Return 200 so client doesn't think server is down

@app.route('/api/alerts')
def get_alerts():
    """Get current alerts"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        alerts = []
        for alert in cad_system.alerts:
            alerts.append({
                "id": alert.incident_id,
                "type": alert.incident_type,
                "address": alert.address,
                "time": alert.timestamp.isoformat(),
                "priority": alert.priority,
                "acknowledged": alert.acknowledged
            })
        
        return jsonify(alerts)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/<alert_id>/acknowledge', methods=['POST'])
def acknowledge_alert(alert_id):
    """Acknowledge an alert"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        success = cad_system.acknowledge_alert(alert_id)
        if success:
            return jsonify({"message": "Alert acknowledged"})
        else:
            return jsonify({"error": "Alert not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/incidents/new')
def get_new_incidents():
    """Get new incidents (same as /api/incidents for now)"""
    return get_incidents()

@app.route('/api/units')
def get_units():
    """Get all units with their status"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        units = []
        unit_status_data = cad_system.get_all_unit_status()
        
        # Handle list return type (the actual return type)
        if isinstance(unit_status_data, list):
        for unit_data in unit_status_data:
                # Handle both dict and object types
                if isinstance(unit_data, dict):
            unit_name = unit_data.get("unit_id", "Unknown")
            station = unit_data.get("station", "Unknown Station")
            units.append({
                "unit_id": unit_name,
                "status": unit_data.get("status", "unknown"),
                "station": station,
                "last_update": unit_data.get("last_update", ""),
                "assigned_incident": unit_data.get("assigned_incident", None)
            })
                else:
                    # Handle object type
                    unit_name = getattr(unit_data, "unit_id", "Unknown")
                    station = getattr(unit_data, "station", "Unknown Station")
                    units.append({
                        "unit_id": unit_name,
                        "status": getattr(unit_data, "status", "unknown"),
                        "station": station,
                        "last_update": getattr(unit_data, "last_update", ""),
                        "assigned_incident": getattr(unit_data, "assigned_incident", None)
                    })
        else:
            # If it's not a list, try to convert it
            print(f"[ERROR] get_all_unit_status returned unexpected type: {type(unit_status_data)}")
            units = []
        
        return jsonify({"units": units})
    except Exception as e:
        print(f"[ERROR] Error in get_units endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "units": []}), 500

@app.route('/api/agencies', methods=['GET'])
def get_agencies():
    """Get list of monitored agencies"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        agencies = []
        for agency_id in cad_system.monitored_agencies:
            agency = cad_system.scraper.get_agency(agency_id)
            if agency:
                agencies.append({
                    "id": agency_id,
                    "name": agency.get("agencyname", "Unknown"),
                    "initials": agency.get("agency_initials", ""),
                    "city": agency.get("city", ""),
                    "state": agency.get("state", "")
                })
        
        return jsonify(agencies)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/agencies', methods=['POST'])
def add_agency():
    """Add a new agency to monitor"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        data = request.get_json()
        agency_id = data.get('agency_id')
        
        if not agency_id:
            return jsonify({"error": "agency_id is required"}), 400
        
        success = cad_system.add_agency(agency_id)
        if success:
            return jsonify({"message": f"Agency {agency_id} added successfully"})
        else:
            return jsonify({"error": f"Failed to add agency {agency_id}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/agencies/<agency_id>', methods=['DELETE'])
def remove_agency(agency_id):
    """Remove an agency from monitoring"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        success = cad_system.remove_agency(agency_id)
        if success:
            return jsonify({"message": f"Agency {agency_id} removed successfully"})
        else:
            return jsonify({"error": f"Agency {agency_id} not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/export')
def export_data():
    """Export incidents data"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        format_type = request.args.get('format', 'json')
        data = cad_system.export_incidents(format_type)
        
        if format_type == 'json':
            return jsonify(json.loads(data))
        else:
            return data
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """Manually refresh incident data"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        cad_system.update_incidents()
        return jsonify({"message": "Data refreshed successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sound/test', methods=['POST'])
def test_alert_sound():
    """Test the alert sound"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        # Debug information
        sound_path = cad_system.alert_sound_path
        sound_enabled = cad_system.config.sound_alerts
        file_exists = os.path.exists(sound_path) if sound_path else False
        
        print(f"Sound test - Path: {sound_path}, Enabled: {sound_enabled}, Exists: {file_exists}")
        
        if not sound_enabled:
            return jsonify({"error": "Sound alerts are disabled"}), 400
        
        if not sound_path or not file_exists:
            return jsonify({"error": f"Sound file not found: {sound_path}"}), 404
        
        cad_system.test_alert_sound()
        return jsonify({
            "message": "Alert sound test triggered",
            "sound_path": sound_path,
            "sound_enabled": sound_enabled,
            "file_exists": file_exists
        })
    except Exception as e:
        print(f"Sound test error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sound/status', methods=['GET'])
def get_sound_status():
    """Get sound alert status and file information"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        sound_path = cad_system.alert_sound_path
        sound_enabled = cad_system.config.sound_alerts
        file_exists = os.path.exists(sound_path) if sound_path else False
        
        return jsonify({
            "sound_alerts_enabled": sound_enabled,
            "sound_file_path": sound_path,
            "file_exists": file_exists,
            "file_size": os.path.getsize(sound_path) if file_exists else 0,
            "alert_priorities": cad_system.config.alert_priorities
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sound/priorities', methods=['POST'])
def set_alert_priorities():
    """Set which priority levels trigger sound alerts"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        data = request.get_json()
        priorities = data.get('priorities', [])
        
        if not isinstance(priorities, list):
            return jsonify({"error": "Priorities must be a list"}), 400
        
        # Validate priority values
        valid_priorities = ['high', 'medium', 'low']
        for priority in priorities:
            if priority.lower() not in valid_priorities:
                return jsonify({"error": f"Invalid priority: {priority}. Must be one of: {valid_priorities}"}), 400
        
        cad_system.config.alert_priorities = [p.lower() for p in priorities]
        return jsonify({
            "message": "Alert priorities updated",
            "alert_priorities": cad_system.config.alert_priorities
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/test/incident', methods=['POST'])
def create_test_incident():
    """Create a test incident to verify the system works"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        from datetime import datetime
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
        
        # Create a test incident
        test_incident = MockIncident(
            ID=999999,
            incident_type="TEST FIRE ALARM",
            FullDisplayAddress="123 TEST ST, ROGERS, AR",
            CallReceivedDateTime=datetime.now(),
            Unit=[MockUnit("E1"), MockUnit("L1"), MockUnit("BC1")],
            AlarmLevel=1,
            Latitude=36.3320,
            Longitude=-94.1185,
            Agency="Rogers Fire Department"
        )
        
        # Add to active incidents
        cad_system.current_incidents.active.append(test_incident)
        
        # Send to Discord if enabled
        if cad_system.discord_manager:
            priority = cad_system._determine_priority(test_incident)
            cad_system.discord_manager.send_incident_notification(test_incident, priority, "test_call")
        
        return jsonify({
            "message": "Test incident created successfully",
            "incident_id": test_incident.ID,
            "incident_type": test_incident.incident_type,
            "address": test_incident.FullDisplayAddress
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sound/toggle', methods=['POST'])
def toggle_sound_alerts():
    """Toggle sound alerts on/off"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        enabled = cad_system.toggle_sound_alerts()
        return jsonify({
            "message": f"Sound alerts {'enabled' if enabled else 'disabled'}",
            "enabled": enabled
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tts/test', methods=['POST'])
def test_tts():
    """Test the TTS system"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        cad_system.test_tts()
        return jsonify({"message": "TTS test triggered"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tts/test-real', methods=['POST'])
def test_tts_real():
    """Test the TTS system with real incident data"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        cad_system.test_tts_with_real_data()
        return jsonify({"message": "TTS test with real data triggered"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/test', methods=['POST', 'GET'])
def test_alert_system():
    """Test the complete alert system (sound + TTS)"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        cad_system.test_alert_system()
        return jsonify({"message": "Complete alert system test triggered"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tts/toggle', methods=['POST'])
def toggle_tts():
    """Toggle TTS on/off"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        enabled = cad_system.toggle_tts()
        return jsonify({
            "message": f"TTS {'enabled' if enabled else 'disabled'}",
            "enabled": enabled
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sms/test', methods=['POST'])
def test_sms():
    """Test the SMS system"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        cad_system.test_sms()
        return jsonify({"message": "SMS test triggered"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sms/test-real', methods=['POST'])
def test_sms_real():
    """Test the SMS system with real incident data"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        cad_system.test_sms_with_real_data()
        return jsonify({"message": "SMS test with real data triggered"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sms/toggle', methods=['POST'])
def toggle_sms():
    """Toggle SMS on/off"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        enabled = cad_system.toggle_sms()
        return jsonify({
            "message": f"SMS {'enabled' if enabled else 'disabled'}",
            "enabled": enabled
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sms/status', methods=['GET'])
def get_sms_status():
    """Get SMS status and configuration"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        return jsonify({
            "sms_enabled": cad_system.config.sms_enabled,
            "sms_phone_number": cad_system.config.sms_phone_number,
            "sms_priorities": cad_system.config.sms_priorities
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sms/phone', methods=['POST'])
def set_sms_phone():
    """Set SMS phone number"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        data = request.get_json()
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return jsonify({"error": "phone_number is required"}), 400
        
        # Clean phone number
        phone_number = ''.join(filter(str.isdigit, phone_number))
        if len(phone_number) == 10:
            phone_number = "1" + phone_number  # Add US country code
        
        cad_system.config.sms_phone_number = phone_number
        return jsonify({
            "message": f"SMS phone number updated to {phone_number}",
            "phone_number": phone_number
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sms/priorities', methods=['POST'])
def set_sms_priorities():
    """Set which priority levels trigger SMS alerts"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        data = request.get_json()
        priorities = data.get('priorities', [])
        
        if not isinstance(priorities, list):
            return jsonify({"error": "Priorities must be a list"}), 400
        
        # Validate priority values
        valid_priorities = ['critical', 'high', 'medium', 'low']
        for priority in priorities:
            if priority.lower() not in valid_priorities:
                return jsonify({"error": f"Invalid priority: {priority}. Must be one of: {valid_priorities}"}), 400
        
        cad_system.config.sms_priorities = [p.lower() for p in priorities]
        return jsonify({
            "message": "SMS priorities updated",
            "sms_priorities": cad_system.config.sms_priorities
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stations/units')
def get_station_units():
    """Get station and unit assignments"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        stations = cad_system.get_station_units()
        return jsonify(stations)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/units/<unit_name>/station')
def get_unit_station(unit_name):
    """Get the station for a specific unit"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        station = cad_system.get_unit_station(unit_name)
        if station:
            return jsonify({"unit": unit_name, "station": station})
        else:
            return jsonify({"error": f"Unit {unit_name} not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/units/status')
def get_all_unit_status():
    """Get status of all units"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        unit_status = cad_system.get_all_unit_status()
        return jsonify(unit_status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stations/status')
def get_station_status():
    """Get status summary for all stations"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        station_status = cad_system.get_station_status_summary()
        return jsonify(station_status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/units/<unit_name>/status')
def get_unit_status(unit_name):
    """Get the current status of a specific unit"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        status = cad_system.get_unit_status(unit_name)
        station = cad_system.get_unit_station(unit_name)
        return jsonify({
            "unit": unit_name,
            "status": status,
            "station": station or "Unknown Station"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/units/status-changes', methods=['GET'])
def get_unit_status_changes():
    """Get recent unit status changes"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        limit = request.args.get('limit', 50, type=int)
        changes = cad_system.get_unit_status_changes(limit)
        return jsonify(changes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stations/minimum-staffing', methods=['GET'])
def get_minimum_staffing_alerts():
    """Get current minimum staffing alerts"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        alerts = cad_system.get_minimum_staffing_alerts()
        return jsonify(alerts)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _determine_priority(incident_type):
    """Determine incident priority based on type"""
    # CRITICAL priority - Immediate life safety threats
    critical_priority = [
        "Structure Fire", "Hazardous Materials", "Rescue Operation", 
        "Aircraft Emergency", "Explosion", "Mass Casualty"
    ]
    
    # HIGH priority - Fire and emergency incidents requiring immediate response
    high_priority = [
        "Vegetation Fire", "Wildfire", "Brush Fire", "Grass Fire",
        "Vehicle Fire", "Trash Fire", "Dumpster Fire", "Rubbish Fire",
        "Gas Leak", "Carbon Monoxide", "Electrical Fire", "Transformer Fire",
        "Water Rescue", "Swift Water Rescue", "Confined Space Rescue",
        "High Angle Rescue", "Trench Rescue", "Collapse Rescue",
        "Active Shooter", "Bomb Threat", "Suspicious Package",
        "Power Line Down", "Gas Line Break", "Chemical Spill"
    ]
    
    # MEDIUM priority - Medical and traffic incidents
    medium_priority = [
        "Medical Emergency", "Traffic Collision", "Fire Alarm", 
        "Smoke Investigation", "Odor Investigation", "Lockout Service",
        "Public Service", "Mutual Aid", "Standby"
    ]
    
    # LOW priority - Non-emergency calls
    low_priority = [
        "False Alarm", "Canceled", "Cancelled", "No Incident Found",
        "Service Call", "Maintenance", "Test", "Training"
    ]
    
    # Check for critical priority first
    if any(critical in incident_type for critical in critical_priority):
        return "critical"
    # Check for high priority
    elif any(high in incident_type for high in high_priority):
        return "high"
    # Check for medium priority
    elif any(medium in incident_type for medium in medium_priority):
        return "medium"
    # Check for low priority
    elif any(low in incident_type for low in low_priority):
        return "low"
    # Default to medium for unknown types (better safe than sorry)
    else:
        return "medium"

# Enhanced API Endpoints

@app.route('/api/stations')
def get_stations():
    """Get station status information"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        stations = cad_system.get_station_status()
        return jsonify({name: asdict(status) for name, status in stations.items()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/unit-changes')
def get_unit_changes():
    """Get recent unit status changes"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        limit = request.args.get('limit', 50, type=int)
        changes = cad_system.get_unit_status_changes(limit)
        return jsonify([asdict(change) for change in changes])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/unacknowledged')
def get_unacknowledged_alerts():
    """Get unacknowledged alerts"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        alerts = cad_system.get_unacknowledged_alerts()
        return jsonify([asdict(alert) for alert in alerts])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/<alert_id>/acknowledge-enhanced', methods=['POST'])
def acknowledge_alert_enhanced(alert_id):
    """Acknowledge an alert (enhanced version)"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        success = cad_system.acknowledge_alert(alert_id)
        if success:
            return jsonify({"success": True, "message": "Alert acknowledged"})
        else:
            return jsonify({"success": False, "message": "Alert not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/filters', methods=['GET', 'POST'])
def manage_filters():
    """Get or set incident filters"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        if request.method == 'GET':
            return jsonify(cad_system.incident_filters)
        elif request.method == 'POST':
            data = request.get_json()
            cad_system.set_incident_filters(
                types=data.get('types'),
                priorities=data.get('priorities'),
                stations=data.get('stations')
            )
            return jsonify({"success": True, "filters": cad_system.incident_filters})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/incidents/filtered')
def get_filtered_incidents():
    """Get incidents filtered by current filter settings"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        filtered_incidents = cad_system.get_filtered_incidents()
        
        # Convert to JSON-serializable format
        active_incidents = []
        for incident in filtered_incidents.active:
            units_with_stations = []
            if incident.Unit:
                for unit in incident.Unit:
                    station = cad_system.get_unit_station(unit.UnitID)
                    units_with_stations.append({
                        "unit_id": unit.UnitID,
                        "station": station or "Unknown Station"
                    })
            
            active_incidents.append({
                "id": str(incident.ID),
                "type": incident.incident_type,
                "address": incident.FullDisplayAddress,
                "time": incident.CallReceivedDateTime.isoformat(),
                "priority": _determine_priority(incident.incident_type),
                "units": [unit.UnitID for unit in incident.Unit] if incident.Unit else [],
                "units_with_stations": units_with_stations,
                "latitude": incident.Latitude,
                "longitude": incident.Longitude,
                "alarm_level": incident.AlarmLevel
            })
        
        recent_incidents = []
        for incident in filtered_incidents.recent:
            recent_incidents.append({
                "id": str(incident.ID),
                "type": incident.incident_type,
                "address": incident.FullDisplayAddress,
                "time": incident.CallReceivedDateTime.isoformat(),
                "priority": _determine_priority(incident.incident_type),
                "closed_time": incident.ClosedDateTime.isoformat() if incident.ClosedDateTime else None,
                "units": [unit.UnitID for unit in incident.Unit] if incident.Unit else []
            })
        
        return jsonify({
            "active": active_incidents,
            "recent": recent_incidents,
            "filters": cad_system.incident_filters
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/map-data')
def get_map_data():
    """Get data for map integration"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        map_data = cad_system.get_map_data()
        return jsonify(map_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/unit-status-all')
def get_all_unit_status_simple():
    """Get current unit status (simple version)"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        return jsonify(cad_system.unit_status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# PulsePoint Map Endpoints
@app.route('/api/pulsepoint/map/test')
def test_pulsepoint_map():
    """Test endpoint to verify server is working"""
    return jsonify({
        "incidents": [
            {
                "id": "TEST001",
                "type": "Test Incident",
                "address": "123 Test St, Test City, AR",
                "latitude": 36.3320,
                "longitude": -94.1185,
                "time": datetime.now().isoformat(),
                "geofence": "Test_geofence",
                "distance": 0.5,
                "alarm_level": 1,
                "units": ["E1", "L1"]
            }
        ],
        "geofences": [
            {
                "name": "Test_geofence",
                "center_lat": 36.3320,
                "center_lon": -94.1185,
                "radius_miles": 15,
                "color": "#FF0000",
                "type": "circle"
            }
        ],
        "last_update": datetime.now().isoformat()
    })

@app.route('/api/pulsepoint/map')
def get_pulsepoint_map():
    """Get PulsePoint map data with incidents and geofences"""
    print(f"PulsePoint map endpoint called, scraper initialized: {pulsepoint_scraper is not None}")
    if not pulsepoint_scraper:
        print("ERROR: PulsePoint scraper not initialized")
        return jsonify({"error": "PulsePoint scraper not initialized"}), 500
    
    try:
        agency_id = request.args.get('agency_id', '04600')
        
        # Get geofenced incidents
        geofenced_incidents = pulsepoint_scraper.get_geofenced_incidents(agency_id)
        
        # Format incidents for map
        incidents_data = []
        for geof_incident in geofenced_incidents:
            incident = geof_incident.incident
            incidents_data.append({
                "id": str(incident.ID),
                "type": incident.incident_type,
                "address": incident.FullDisplayAddress,
                "latitude": incident.Latitude,
                "longitude": incident.Longitude,
                "time": incident.CallReceivedDateTime.isoformat() if hasattr(incident.CallReceivedDateTime, 'isoformat') else str(incident.CallReceivedDateTime),
                "geofence": geof_incident.geofence_name,
                "distance": round(geof_incident.distance_from_center, 2),
                "alarm_level": incident.AlarmLevel,
                "units": [unit.UnitID for unit in incident.Unit] if incident.Unit else []
            })
        
        # Format geofences for map
        geofences_data = []
        for name, geofence in pulsepoint_scraper.geofences.items():
            geofence_data = {
                "name": name,
                "center_lat": geofence.center_lat,
                "center_lon": geofence.center_lon,
                "color": geofence.color,
                "type": "circle" if not geofence.polygon_points else "polygon"
            }
            
            if geofence.polygon_points:
                geofence_data["polygon_points"] = geofence.polygon_points
            else:
                geofence_data["radius_miles"] = geofence.radius_miles
            
            geofences_data.append(geofence_data)
        
        result = {
            "incidents": incidents_data,
            "geofences": geofences_data,
            "last_update": datetime.now().isoformat()
        }
        print(f"Returning map data: {len(incidents_data)} incidents, {len(geofences_data)} geofences")
        return jsonify(result)
    except Exception as e:
        print(f"ERROR in get_pulsepoint_map: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/pulsepoint/geofences', methods=['GET'])
def get_geofences():
    """Get all geofences"""
    if not pulsepoint_scraper:
        return jsonify({"error": "PulsePoint scraper not initialized"}), 500
    
    try:
        geofences = []
        for name, geofence in pulsepoint_scraper.geofences.items():
            geofences.append({
                "name": name,
                "center_lat": geofence.center_lat,
                "center_lon": geofence.center_lon,
                "radius_miles": geofence.radius_miles,
                "color": geofence.color,
                "polygon_points": geofence.polygon_points
            })
        return jsonify(geofences)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/pulsepoint/geofences', methods=['POST'])
def add_geofence():
    """Add a new geofence"""
    if not pulsepoint_scraper:
        return jsonify({"error": "PulsePoint scraper not initialized"}), 500
    
    try:
        data = request.get_json()
        name = data.get('name')
        center_lat = data.get('center_lat')
        center_lon = data.get('center_lon')
        radius_miles = data.get('radius_miles')
        polygon_points = data.get('polygon_points')
        color = data.get('color', '#FF0000')
        
        if not name or not center_lat or not center_lon:
            return jsonify({"error": "Missing required fields"}), 400
        
        if polygon_points:
            pulsepoint_scraper.add_custom_polygon_geofence(name, polygon_points, color)
        else:
            if not radius_miles:
                return jsonify({"error": "Radius required for circular geofence"}), 400
            pulsepoint_scraper.add_geofence(name, center_lat, center_lon, radius_miles, color=color)
        
        return jsonify({"message": f"Geofence '{name}' added successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/pulsepoint/incidents/<agency_id>')
def get_pulsepoint_incidents(agency_id):
    """Get incidents for a specific agency with geofencing"""
    if not pulsepoint_scraper:
        return jsonify({"error": "PulsePoint scraper not initialized"}), 500
    
    try:
        # Get all incidents
        all_incidents = pulsepoint_scraper.get_incidents(agency_id)
        
        # Get geofenced incidents
        geofenced_incidents = pulsepoint_scraper.get_geofenced_incidents(agency_id)
        
        # Format all incidents
        active_incidents = []
        for incident in all_incidents.active:
            active_incidents.append({
                "id": str(incident.ID),
                "type": incident.incident_type,
                "address": incident.FullDisplayAddress,
                "latitude": incident.Latitude,
                "longitude": incident.Longitude,
                "time": incident.CallReceivedDateTime.isoformat() if hasattr(incident.CallReceivedDateTime, 'isoformat') else str(incident.CallReceivedDateTime),
                "alarm_level": incident.AlarmLevel,
                "units": [unit.UnitID for unit in incident.Unit] if incident.Unit else []
            })
        
        recent_incidents = []
        for incident in all_incidents.recent:
            recent_incidents.append({
                "id": str(incident.ID),
                "type": incident.incident_type,
                "address": incident.FullDisplayAddress,
                "latitude": incident.Latitude,
                "longitude": incident.Longitude,
                "time": incident.CallReceivedDateTime.isoformat() if hasattr(incident.CallReceivedDateTime, 'isoformat') else str(incident.CallReceivedDateTime),
                "alarm_level": incident.AlarmLevel,
                "units": [unit.UnitID for unit in incident.Unit] if incident.Unit else []
            })
        
        # Format geofenced incidents
        geofenced_data = []
        for geof_incident in geofenced_incidents:
            incident = geof_incident.incident
            geofenced_data.append({
                "id": str(incident.ID),
                "type": incident.incident_type,
                "address": incident.FullDisplayAddress,
                "latitude": incident.Latitude,
                "longitude": incident.Longitude,
                "time": incident.CallReceivedDateTime.isoformat() if hasattr(incident.CallReceivedDateTime, 'isoformat') else str(incident.CallReceivedDateTime),
                "geofence": geof_incident.geofence_name,
                "distance": round(geof_incident.distance_from_center, 2),
                "alarm_level": incident.AlarmLevel,
                "units": [unit.UnitID for unit in incident.Unit] if incident.Unit else []
            })
        
        return jsonify({
            "active": active_incidents,
            "recent": recent_incidents,
            "geofenced": geofenced_data,
            "last_update": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/pulsepoint/map/generate')
def generate_pulsepoint_map():
    """Generate and return PulsePoint map HTML"""
    if not pulsepoint_scraper:
        return jsonify({"error": "PulsePoint scraper not initialized"}), 500
    
    try:
        agency_id = request.args.get('agency_id', '04600')
        map_file = pulsepoint_scraper.generate_map_html(agency_id, "pulsepoint_live_map.html")
        
        # Read the generated map file
        with open(map_file, 'r', encoding='utf-8') as f:
            map_html = f.read()
        
        return map_html
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/force-refresh', methods=['POST'])
def force_refresh():
    """Force refresh incident data"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        cad_system.force_refresh()
        return jsonify({"message": "Data refresh initiated", "timestamp": datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/acknowledge-all', methods=['POST'])
def acknowledge_all_alerts():
    """Acknowledge all alerts"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        count = cad_system.acknowledge_all_alerts()
        return jsonify({"message": f"Acknowledged {count} alerts", "count": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/incidents/move-to-recent', methods=['POST'])
def move_old_incidents_to_recent():
    """Move old incidents to recent list"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        hours_old = request.json.get('hours_old', 2) if request.json else 2
        count = cad_system.move_old_incidents_to_recent(hours_old)
        return jsonify({"message": f"Moved {count} incidents to recent", "count": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Discord Webhook Management Endpoints

@app.route('/api/discord/status', methods=['GET'])
def get_discord_status():
    """Get Discord webhook status and configuration"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        config = cad_system.get_discord_config()
        return jsonify(config)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discord/test', methods=['POST'])
def test_discord_webhooks():
    """Test all Discord webhooks"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        results = cad_system.test_discord_webhooks()
        return jsonify({
            "message": "Discord webhook test completed",
            "results": results
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discord/test/<webhook_type>', methods=['POST'])
def test_specific_discord_webhook(webhook_type):
    """Test a specific Discord webhook"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        if not cad_system.discord_manager:
            return jsonify({"error": "Discord manager not initialized"}), 500
        
        success = cad_system.discord_manager.test_webhook(webhook_type)
        return jsonify({
            "message": f"Discord {webhook_type} webhook test {'passed' if success else 'failed'}",
            "success": success
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discord/toggle', methods=['POST'])
def toggle_discord():
    """Toggle Discord notifications on/off"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        enabled = cad_system.toggle_discord()
        return jsonify({
            "message": f"Discord notifications {'enabled' if enabled else 'disabled'}",
            "enabled": enabled
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discord/config', methods=['POST'])
def update_discord_config():
    """Update Discord webhook configuration"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No configuration data provided"}), 400
        
        success = cad_system.update_discord_config(**data)
        if success:
            return jsonify({
                "message": "Discord configuration updated successfully",
                "config": cad_system.get_discord_config()
            })
        else:
            return jsonify({"error": "Failed to update Discord configuration"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discord/daily-summary', methods=['POST'])
def send_daily_summary():
    """Send daily summary to Discord"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        success = cad_system.send_daily_summary()
        if success:
            return jsonify({"message": "Daily summary sent to Discord successfully"})
        else:
            return jsonify({"error": "Failed to send daily summary"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discord/responder-call', methods=['POST'])
def send_responder_call():
    """Send a responder call to Discord"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No incident data provided"}), 400
        
        # Find the incident by ID
        incident_id = data.get('incident_id')
        if not incident_id:
            return jsonify({"error": "incident_id is required"}), 400
        
        # Find incident in active or recent incidents
        incident = None
        for inc in cad_system.current_incidents.active + cad_system.current_incidents.recent:
            if str(inc.ID) == str(incident_id):
                incident = inc
                break
        
        if not incident:
            return jsonify({"error": "Incident not found"}), 404
        
        priority = data.get('priority', cad_system._determine_priority(incident))
        success = cad_system.send_responder_call(incident, priority)
        
        if success:
            return jsonify({"message": "Responder call sent to Discord successfully"})
        else:
            return jsonify({"error": "Failed to send responder call"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discord/clear-cache', methods=['POST'])
def clear_discord_cache():
    """Clear Discord notification cache and rate limits"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        success = cad_system.clear_discord_cache()
        if success:
            return jsonify({"message": "Discord cache and rate limits cleared"})
        else:
            return jsonify({"error": "Failed to clear Discord cache"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discord/rate-limits', methods=['POST'])
def set_discord_rate_limits():
    """Set Discord rate limiting parameters"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No rate limit data provided"}), 400
        
        min_interval = data.get('min_interval', 30)
        max_per_hour = data.get('max_per_hour', 20)
        
        success = cad_system.set_discord_rate_limits(min_interval, max_per_hour)
        if success:
            return jsonify({
                "message": "Discord rate limits updated",
                "min_interval": min_interval,
                "max_per_hour": max_per_hour
            })
        else:
            return jsonify({"error": "Failed to update Discord rate limits"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/discord/stop-spam', methods=['POST'])
def stop_discord_spam():
    """Emergency stop Discord notifications and clear all caches"""
    if not cad_system:
        return jsonify({"error": "CAD system not initialized"}), 500
    
    try:
        # Clear all caches first while discord_manager still exists
        if cad_system.discord_manager:
            cad_system.clear_discord_cache()
        
        # Disable Discord notifications
        cad_system.config.discord_enabled = False
        cad_system.discord_manager = None
        
        return jsonify({
            "message": "Discord notifications stopped and caches cleared",
            "discord_enabled": False
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_server(host='127.0.0.1', port=125, debug=False):
    """Run the Flask server"""
    print("Starting FDD CAD Web Server...")
    print(f"Server will be available at: http://{host}:{port}")
    print("Press Ctrl+C to stop the server")
    
    # Initialize CAD system BEFORE starting the web server
    print("Initializing CAD system...")
    initialize_cad_system()
    print("CAD system initialization complete!")
    
    try:
        # Configure Flask for better stability and long-running connections
        app.run(
            host=host, 
            port=port, 
            debug=debug, 
            threaded=True,
            use_reloader=False,  # Disable reloader for stability
            use_debugger=debug,
            passthrough_errors=False  # Catch all errors
        )
    except KeyboardInterrupt:
        print("\nShutting down CAD system...")
        if cad_system:
            cad_system.stop_monitoring()
        print("CAD Web Server stopped.")
    except Exception as e:
        print(f"\n[ERROR] Web server error: {e}")
        import traceback
        traceback.print_exc()
        # Try to restart the server
        print("[INFO] Attempting to restart server...")
        time.sleep(5)
        try:
            app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)
        except Exception as restart_error:
            print(f"[ERROR] Failed to restart server: {restart_error}")

if __name__ == "__main__":
    run_server(debug=True)
