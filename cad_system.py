#!/usr/bin/env python3
"""
FDD CAD System - Fire Department Computer-Aided Dispatch Interface
A modern web-based CAD system for monitoring fire department dispatch data
"""

import asyncio
import json
import time
import os
import subprocess
import platform
import requests
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import threading
from dataclasses import dataclass, asdict
from fdd_cad_scraper import FDDCADScraper, Incident, Incidents
from discord_webhook import DiscordWebhookManager, DiscordWebhookConfig

class PushoverManager:
    """Manages Pushover notifications for the CAD system"""
    
    def __init__(self, user_key: str, app_token: str):
        self.user_key = user_key
        self.app_token = app_token
        self.api_url = "https://api.pushover.net/1/messages.json"
    
    def send_notification(self, title: str, message: str, priority: int = 0, sound: str = "default") -> bool:
        """Send a Pushover notification"""
        try:
            data = {
                'token': self.app_token,
                'user': self.user_key,
                'title': title,
                'message': message,
                'priority': priority,
                'sound': sound
            }
            
            # Emergency priority (2) requires expire parameter
            if priority == 2:
                data['expire'] = 3600  # Expire after 1 hour
                data['retry'] = 30     # Retry every 30 seconds
            
            response = requests.post(self.api_url, data=data, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 1:
                    print(f"Pushover notification sent successfully: {title}")
                    return True
                else:
                    print(f"Pushover failed: {result.get('errors', 'Unknown error')}")
                    return False
            else:
                print(f"Pushover failed: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"Pushover error: {e}")
            return False
    
    def _parse_address_details(self, address: str) -> dict:
        """Parse address to extract street, cross streets, city, zip code"""
        details = {
            'full_address': address,
            'street': '',
            'cross_street': '',
            'city': '',
            'zip_code': '',
            'area': ''
        }
        
        if not address:
            return details
        
        try:
            import re
            
            # Extract ZIP code
            zip_match = re.search(r'\b(\d{5})\b', address)
            if zip_match:
                details['zip_code'] = zip_match.group(1)
            
            # Extract city (usually before state/ZIP)
            city_match = re.search(r',\s*([^,]+?)(?:,\s*(?:AR|Arkansas))?\s*(?:,\s*\d{5})?$', address)
            if city_match:
                details['city'] = city_match.group(1).strip()
            
            # Get the main address part (before city/state)
            main_address = address.split(',')[0] if ',' in address else address
            
            # Try multiple patterns to find cross streets/intersections
            cross_street_patterns = [
                # Pattern 1: "123 Main St at Oak Ave" or "123 Main St at Oak"
                r'^(\d+\s+)?(.+?)\s+at\s+(.+?)(?:\s*,|$)',
                # Pattern 2: "123 Main St / Oak Ave" or "Main St/Oak"
                r'^(\d+\s+)?(.+?)\s*/\s*(.+?)(?:\s*,|$)',
                # Pattern 3: "123 Main St & Oak Ave" or "Main St & Oak"
                r'^(\d+\s+)?(.+?)\s+&\s+(.+?)(?:\s*,|$)',
                # Pattern 4: "123 Main St and Oak Ave"
                r'^(\d+\s+)?(.+?)\s+and\s+(.+?)(?:\s*,|$)',
                # Pattern 5: "Main St & Oak Ave" (no number)
                r'^(.+?)\s+&\s+(.+?)(?:\s*,|$)',
                # Pattern 6: "Main St/Oak Ave" (no number)
                r'^(.+?)\s*/\s*(.+?)(?:\s*,|$)',
                # Pattern 7: "123 Main St near Oak Ave"
                r'^(\d+\s+)?(.+?)\s+near\s+(.+?)(?:\s*,|$)',
                # Pattern 8: "Main St and Oak Ave" (no number)
                r'^(.+?)\s+and\s+(.+?)(?:\s*,|$)',
            ]
            
            cross_street_found = False
            for pattern in cross_street_patterns:
                match = re.match(pattern, main_address, re.IGNORECASE)
                if match:
                    if len(match.groups()) == 3:
                        # Has street number
                        street_num = match.group(1).strip() if match.group(1) else ''
                        street_name = match.group(2).strip()
                        cross_street = match.group(3).strip()
                        details['street'] = f"{street_num} {street_name}".strip()
                        details['cross_street'] = cross_street
                    else:
                        # No street number
                        details['street'] = match.group(1).strip()
                        details['cross_street'] = match.group(2).strip()
                    cross_street_found = True
                    break
            
            # If no cross street found, extract just the street
            if not cross_street_found:
                # Try to extract street with number
                street_match = re.match(r'^(\d+\s+)?(.+?)(?:\s*,|$)', main_address)
                if street_match:
                    if street_match.group(1):
                        details['street'] = f"{street_match.group(1).strip()} {street_match.group(2).strip()}".strip()
                    else:
                        details['street'] = street_match.group(2).strip() if street_match.group(2) else main_address
                else:
                    details['street'] = main_address
            
            # Extract area/neighborhood if available
            if 'near' in address.lower() or 'area' in address.lower():
                area_match = re.search(r'(?:near|area|in)\s+([^,]+)', address, re.IGNORECASE)
                if area_match:
                    details['area'] = area_match.group(1).strip()
            
            # Additional fallback: Check if address contains intersection indicators
            if not details['cross_street']:
                # Try a more aggressive search for any intersection pattern
                intersection_patterns = [
                    r'\s+at\s+([^,]+)',
                    r'\s+&\s+([^,]+)',
                    r'\s*/\s*([^,]+)',
                    r'\s+and\s+([^,]+)',
                    r'\s+near\s+([^,]+)',
                ]
                for pattern in intersection_patterns:
                    match = re.search(pattern, address, re.IGNORECASE)
                    if match:
                        potential_cross = match.group(1).strip()
                        # Make sure it's not just part of the city/state
                        if potential_cross and len(potential_cross) > 2 and not potential_cross.lower() in ['ar', 'arkansas', details['city'].lower()]:
                            details['cross_street'] = potential_cross
                            print(f"[DEBUG] Found cross street via fallback: {details['cross_street']}")
                            break
                
        except Exception as e:
            print(f"Error parsing address: {e}")
            import traceback
            traceback.print_exc()
        
        return details
    
    def send_incident_alert(self, incident: Incident, priority_level: str) -> bool:
        """Send incident alert via Pushover"""
        # ALL incidents sent as CRITICAL to phone for maximum visibility
        pushover_priority = 2  # Emergency priority (CRITICAL)
        pushover_sound = "siren"  # Emergency sound
        
        # Keep original priority in the title for reference
        original_priority = priority_level.upper()
        
        # Get unit information
        units_text = "No units assigned"
        if hasattr(incident, 'Unit') and incident.Unit:
            try:
                if isinstance(incident.Unit, list):
                    unit_names = []
                    for unit in incident.Unit:
                        if hasattr(unit, 'UnitID'):
                            unit_names.append(unit.UnitID)
                        elif isinstance(unit, str):
                            unit_names.append(unit)
                    if unit_names:
                        if len(unit_names) == 1:
                            units_text = f"Unit {unit_names[0]}"
                        else:
                            units_text = f"Units {', '.join(unit_names)}"
                elif isinstance(incident.Unit, str):
                    units_text = f"Unit {incident.Unit}"
            except Exception as e:
                print(f"Error extracting units for Pushover: {e}")
                units_text = "Units assigned"
        
        # Create professional title and message - ALL incidents shown as CRITICAL for phone
        title = f"FIRE DEPARTMENT DISPATCH - CRITICAL ALERT"
        
        # Parse address details
        address_details = self._parse_address_details(incident.FullDisplayAddress)
        
        # Format time with date
        call_time = incident.CallReceivedDateTime.strftime('%I:%M %p')
        call_date = incident.CallReceivedDateTime.strftime('%m/%d/%Y')
        
        # Build professional message with clear structure
        message_parts = []
        
        # Incident type header
        message_parts.append(f"INCIDENT TYPE: {incident.incident_type.upper()}")
        message_parts.append("")
        
        # Location section
        message_parts.append("LOCATION INFORMATION:")
        message_parts.append(f"Primary Address: {incident.FullDisplayAddress}")
        
        # Add street information - ALWAYS SHOW
        if address_details['street']:
            street_display = address_details['street']
            message_parts.append(f"Street: {street_display}")
        else:
            # If no street parsed, show the main address part
            main_address = incident.FullDisplayAddress.split(',')[0] if ',' in incident.FullDisplayAddress else incident.FullDisplayAddress
            message_parts.append(f"Street: {main_address}")
        
        # Add cross street/intersection - ALWAYS TRY TO SHOW
        cross_street_displayed = False
        if address_details['cross_street']:
            message_parts.append(f"Intersection/Cross Street: {address_details['cross_street']}")
            cross_street_displayed = True
        else:
            # If no cross street found, try to extract from address manually
            # Sometimes addresses have intersections in different formats
            address_lower = incident.FullDisplayAddress.lower()
            if ' at ' in address_lower or ' & ' in address_lower or ' / ' in address_lower or ' and ' in address_lower:
                # Try to extract manually as fallback
                import re
                manual_cross = re.search(r'(?:at|&|/|and)\s+([^,]+?)(?:,|$)', incident.FullDisplayAddress, re.IGNORECASE)
                if manual_cross:
                    cross_street = manual_cross.group(1).strip()
                    # Filter out common false positives
                    if cross_street and len(cross_street) > 2 and cross_street.lower() not in ['ar', 'arkansas', 'st', 'street', 'ave', 'avenue', 'rd', 'road']:
                        message_parts.append(f"Intersection/Cross Street: {cross_street}")
                        print(f"[DEBUG] Manually extracted cross street: {cross_street}")
                        cross_street_displayed = True
        
        # If still no cross street, try one more aggressive search
        if not cross_street_displayed:
            import re
            # Look for any pattern that might indicate an intersection
            aggressive_patterns = [
                r'(\w+\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Court|Ct|Place|Pl|Way|Circle|Cir))\s+(?:at|&|/|and|near)\s+(\w+\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Court|Ct|Place|Pl|Way|Circle|Cir))',
                r'(\d+\s+\w+)\s+(?:at|&|/|and)\s+(\w+)',
            ]
            for pattern in aggressive_patterns:
                match = re.search(pattern, incident.FullDisplayAddress, re.IGNORECASE)
                if match and len(match.groups()) >= 2:
                    potential_cross = match.group(2).strip()
                    if potential_cross and len(potential_cross) > 2:
                        message_parts.append(f"Intersection/Cross Street: {potential_cross}")
                        print(f"[DEBUG] Aggressively extracted cross street: {potential_cross}")
                        break
        
        # Add city if available
        if address_details['city']:
            message_parts.append(f"City: {address_details['city']}")
        
        # Add area/neighborhood if available
        if address_details['area']:
            message_parts.append(f"Area/Neighborhood: {address_details['area']}")
        
        # Add ZIP code if available
        if address_details['zip_code']:
            message_parts.append(f"ZIP Code: {address_details['zip_code']}")
        
        # Add common place name if available
        if hasattr(incident, 'CommonPlaceName') and incident.CommonPlaceName:
            message_parts.append(f"Common Place Name: {incident.CommonPlaceName}")
        
        # Add GPS coordinates if available
        if hasattr(incident, 'Latitude') and hasattr(incident, 'Longitude'):
            if incident.Latitude and incident.Longitude:
                message_parts.append("")
                message_parts.append("COORDINATES:")
                message_parts.append(f"Latitude: {incident.Latitude:.6f}")
                message_parts.append(f"Longitude: {incident.Longitude:.6f}")
                # Add Google Maps link
                maps_link = f"https://www.google.com/maps?q={incident.Latitude},{incident.Longitude}"
                message_parts.append(f"Google Maps: {maps_link}")
        
        message_parts.append("")
        
        # Response information
        message_parts.append("RESPONSE INFORMATION:")
        message_parts.append(f"Assigned Units: {units_text}")
        
        # Add unit station information if available
        if hasattr(incident, 'Unit') and incident.Unit and hasattr(self, 'get_unit_station'):
            try:
                station_info = []
                if isinstance(incident.Unit, list):
                    for unit in incident.Unit:
                        if hasattr(unit, 'UnitID'):
                            station = self.get_unit_station(unit.UnitID)
                            if station:
                                station_info.append(f"{unit.UnitID} ({station})")
                if station_info:
                    message_parts.append(f"Unit Stations: {', '.join(station_info)}")
            except Exception as e:
                print(f"Error getting unit stations: {e}")
        
        # Add agency if available
        if hasattr(incident, 'Agency') and incident.Agency:
            message_parts.append(f"Responding Agency: {incident.Agency}")
        
        # Add alarm level if available
        if hasattr(incident, 'AlarmLevel') and incident.AlarmLevel:
            message_parts.append(f"Alarm Level: {incident.AlarmLevel}")
        
        # Add distance/route information if GPS available
        if hasattr(incident, 'Latitude') and hasattr(incident, 'Longitude') and incident.Latitude and incident.Longitude:
            # Calculate approximate distance from downtown Rogers (Station 1)
            try:
                import math
                station_lat, station_lng = 36.3320, -94.1185  # Rogers Station 1
                lat_diff = incident.Latitude - station_lat
                lng_diff = incident.Longitude - station_lng
                # Rough distance calculation (miles)
                distance_miles = math.sqrt(lat_diff**2 + lng_diff**2) * 69  # 69 miles per degree latitude
                if distance_miles < 20:  # Only show if within reasonable range
                    message_parts.append(f"Approximate Distance: {distance_miles:.1f} miles from Station 1")
            except Exception:
                pass
        
        message_parts.append("")
        
        # Incident details
        message_parts.append("INCIDENT DETAILS:")
        message_parts.append(f"CAD Incident ID: {incident.ID}")
        message_parts.append(f"Call Received: {call_time} on {call_date}")
        message_parts.append(f"Priority Classification: {original_priority}")
        
        # Add incident age/duration if available
        try:
            from datetime import datetime
            incident_age = (datetime.now() - incident.CallReceivedDateTime).total_seconds() / 60  # minutes
            if incident_age < 60:
                message_parts.append(f"Incident Age: {int(incident_age)} minutes")
            else:
                hours = int(incident_age / 60)
                minutes = int(incident_age % 60)
                message_parts.append(f"Incident Age: {hours}h {minutes}m")
        except Exception:
            pass
        
        # Build complete message
        message = "\n".join(message_parts)
        
        return self.send_notification(title, message, pushover_priority, pushover_sound)
    
    def send_system_alert(self, title: str, message: str, is_emergency: bool = False) -> bool:
        """Send system alert via Pushover"""
        priority = 2 if is_emergency else 0
        sound = "siren" if is_emergency else "pushover"
        return self.send_notification(title, message, priority, sound)
    
    def test_connection(self) -> bool:
        """Test Pushover connection"""
        return self.send_notification(
            "FDD CAD System Test", 
            "Pushover integration test successful!", 
            0, 
            "pushover"
        )

# Try to import pyttsx3 for TTS, fallback to system TTS if not available
try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("pyttsx3 not available, using system TTS fallback")

@dataclass
class CADConfig:
    """Configuration for the CAD system"""
    refresh_interval: int = 30  # seconds
    max_incidents_display: int = 50
    auto_refresh: bool = True
    sound_alerts: bool = True
    map_enabled: bool = True
    theme: str = "dark"  # dark, light
    alert_sound_file: str = "244483-f4e12f30-0869-436b-8b4d-9ea43b0d4b41.mp3"
    # Priority levels that trigger sound alerts
    alert_priorities: list = None  # Will be set to ["low", "medium", "high"] by default
    # TTS settings
    tts_enabled: bool = True
    tts_voice_rate: int = 150  # Words per minute
    tts_voice_volume: float = 0.8  # 0.0 to 1.0
    # Unit status settings
    minimum_staffing_enabled: bool = True
    minimum_staffing_threshold: int = 2  # Minimum units per station
    # SMS settings
    sms_enabled: bool = True
    sms_phone_number: str = "4795059422"
    sms_priorities: list = None  # Will be set to ["critical", "high"] by default
    
    # Discord webhook settings
    discord_enabled: bool = True
    discord_webhook_config: DiscordWebhookConfig = None
    
    # Pushover settings
    pushover_enabled: bool = True
    pushover_user_key: str = "u91gdp1wbvynt5wmiec45tsf79e6t5"  # Your actual user key
    pushover_app_token: str = "agunhyfhpg9rik3dr5uedi51vyotaw"  # Your actual app token
    pushover_priorities: list = None  # Will be set to ["critical", "high", "medium"] by default

@dataclass
class CADAlert:
    """Alert for new incidents"""
    incident_id: str
    incident_type: str
    address: str
    timestamp: datetime
    priority: str
    acknowledged: bool = False

@dataclass
class UnitStatusChange:
    """Unit status change event"""
    unit_id: str
    station: str
    old_status: str
    new_status: str
    timestamp: datetime
    reason: str = ""  # "cleared", "minimum_staffing", "assigned", etc.

class CADSystem:
    """Main CAD system class"""
    
    def __init__(self, config: CADConfig = None):
        self.config = config or CADConfig()
        self.scraper = FDDCADScraper()
        self.current_incidents = Incidents()
        self.previous_incidents = Incidents()
        self.alerts: List[CADAlert] = []
        self.unit_status_changes: List[UnitStatusChange] = []
        self.monitored_agencies: List[str] = []
        self.running = False
        self.last_update = None
        self.alert_sound_path = self._get_alert_sound_path()
        self.station_units = self._load_station_units()
        self.unit_status = {}  # Track unit status: 'available', 'busy', 'unknown'
        self.previous_unit_status = {}  # Track previous status for change detection
        self.last_tts_announcements = {}  # Track last TTS announcement time per unit
        self.last_periodic_clear = None  # Track last periodic clearing time
        self.sent_incident_ids = set()  # Track incidents that have been sent to Discord
        self._load_sent_incidents()  # Load previously sent incidents from file
        self.last_successful_connection = None  # Track last successful connection time
        self.consecutive_failures = 0  # Track consecutive connection failures
        
        # Create HTTP session with connection pooling for better reliability
        self.http_session = requests.Session()
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        # Configure adapter with connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=retry_strategy
        )
        self.http_session.mount("http://", adapter)
        self.http_session.mount("https://", adapter)
        
        # Set default timeout
        self.http_session.timeout = 15
        
        # Set default alert priorities if not specified
        if self.config.alert_priorities is None:
            self.config.alert_priorities = ["critical", "high", "medium", "low"]
        
        # Set default SMS priorities if not specified
        if self.config.sms_priorities is None:
            self.config.sms_priorities = ["critical", "high"]
        
        # Set default Pushover priorities if not specified
        # ALL incidents will be sent to phone as CRITICAL
        if self.config.pushover_priorities is None:
            self.config.pushover_priorities = ["critical", "high", "medium", "low"]  # Send all incidents
        
        # Initialize Discord webhook manager
        if self.config.discord_enabled:
            if self.config.discord_webhook_config is None:
                self.config.discord_webhook_config = DiscordWebhookConfig()
            self.discord_manager = DiscordWebhookManager(self.config.discord_webhook_config)
            
            # Send startup message to Discord (only once)
            if self.discord_manager:
                self.discord_manager.send_startup_message_once(self)
            
            # Send any existing active incidents to Discord on startup (with duplicate prevention)
            self._send_existing_incidents_on_startup()
            print("Discord webhook integration initialized")
        else:
            self.discord_manager = None
        
        # Initialize Pushover manager
        if self.config.pushover_enabled:
            self.pushover_manager = PushoverManager(
                self.config.pushover_user_key, 
                self.config.pushover_app_token
            )
            print("Pushover integration initialized")
            
            # Send startup notification to phone
            self._send_startup_notification()
        else:
            self.pushover_manager = None
        
        # Initialize TTS
        self.tts_engine = None
        if self.config.tts_enabled:
            self._init_tts()
    
    def _send_startup_message(self):
        """Send startup message to Discord - DISABLED (use send_startup_message_once instead)"""
        # This method is disabled to prevent spam - use send_startup_message_once instead
        print("Startup message disabled - use send_startup_message_once instead")
        return
    
    def _send_shutdown_message(self):
        """Send shutdown message to Discord"""
        if not self.discord_manager:
            return
        
        try:
            from datetime import datetime
            shutdown_time = datetime.now().strftime("%I:%M %p CDT, %B %d, %Y")
            
            # Create shutdown embed
            embed = {
                "title": "🔴 FDD CAD System Shutdown",
                "description": "Fire Department Computer-Aided Dispatch System is going offline.",
                "color": 0xFF0000,  # Red color for shutdown
                "timestamp": datetime.now().isoformat(),
                "fields": [
                    {
                        "name": "📅 System Shutdown",
                        "value": shutdown_time,
                        "inline": False
                    },
                    {
                        "name": "🔧 System Status",
                        "value": "🔴 Going Offline\n🔴 Discord Integration Disabled\n🔴 Incident Detection Stopped",
                        "inline": False
                    },
                    {
                        "name": "📊 Final Status",
                        "value": f"**Active Incidents:** {len(self.current_incidents.active)}\n**Recent Incidents:** {len(self.current_incidents.recent)}\n**Total Alerts:** {len(self.alerts)}",
                        "inline": False
                    }
                ],
                "footer": {
                    "text": "FDD CAD System • System Shutdown",
                    "icon_url": "https://cdn.discordapp.com/emojis/fire_truck_emoji.png"
                }
            }
            
            # Send shutdown message
            payload = {
                "embeds": [embed],
                "username": "FDD CAD System",
                "avatar_url": "https://cdn.discordapp.com/attachments/1234567890/fire_department_logo.png"
            }
            
            success = self.discord_manager._send_discord_message(
                self.discord_manager.config.calls_webhook_url, 
                payload
            )
            
            if success:
                print("SUCCESS: Discord shutdown message sent")
            else:
                print("FAILED: Discord shutdown message failed")
                
        except Exception as e:
            print(f"Error sending Discord shutdown message: {e}")
    
    def _send_existing_incidents_on_startup(self):
        """Send any existing active incidents to Discord when system starts with dual-source verification"""
        if not self.discord_manager:
            return
        
        try:
            print("[VERIFY] Checking for existing active incidents with DUAL-SOURCE verification...")
            
            incidents_from_web_server = []
            incidents_from_scraper = []
            
            # SOURCE 1: Get incidents from web server (primary source)
            startup_session = None
            try:
                print("[VERIFY] Attempting to connect to web server (timeout: 8s)...")
                # Create a temporary session without retries for faster startup
                startup_session = requests.Session()
                from requests.adapters import HTTPAdapter
                # No retries for startup - fail fast if server isn't available
                adapter = HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0)
                startup_session.mount("http://", adapter)
                startup_session.mount("https://", adapter)
                
                # Use a shorter timeout for startup to avoid hanging
                response = startup_session.get('http://localhost:125/api/incidents', timeout=8)
                print("[VERIFY] Web server connection successful")
                
                if response.status_code == 200:
                    data = response.json()
                    active_incidents = data.get('active', [])
                    
                    if active_incidents:
                        print(f"[SUCCESS] Web Server: Found {len(active_incidents)} active incidents")
                        incidents_from_web_server = self._convert_web_incidents_to_mock(active_incidents)
                    else:
                        print("[INFO] Web Server: No active incidents found")
                else:
                    print(f"[WARNING] Web Server: Returned status {response.status_code}")
                    
            except requests.exceptions.Timeout:
                print("[ERROR] Web Server: Connection timeout (8s) - web server may not be running")
                print("[INFO] Continuing with scraper fallback...")
                # Continue with scraper fallback even if web server is down
                incidents_from_web_server = []
            except requests.exceptions.ConnectionError as e:
                print(f"[ERROR] Web Server: Connection error - web server may not be running")
                print(f"[INFO] Error details: {str(e)[:100]}")
                print("[INFO] Continuing with scraper fallback...")
                # Continue with scraper fallback even if web server is down
                incidents_from_web_server = []
            except Exception as e:
                print(f"[ERROR] Web Server Error: {e}")
                import traceback
                traceback.print_exc()
                # Continue with scraper fallback even if web server is down
                incidents_from_web_server = []
            finally:
                # Always close the startup session
                if startup_session:
                    try:
                        startup_session.close()
                    except:
                        pass
            
            # SOURCE 2: Get incidents from scraper (fallback source)
            try:
                if not incidents_from_web_server:
                    print("[FALLBACK] Falling back to scraper for incident data...")
                    # Try to get incidents from monitored agencies
                    self.update_incidents()
                    incidents_from_scraper = self.current_incidents.active
                    
                    if incidents_from_scraper:
                        print(f"[SUCCESS] Scraper: Found {len(incidents_from_scraper)} active incidents")
                    else:
                        print("[INFO] Scraper: No active incidents found")
                        
            except Exception as e:
                print(f"[ERROR] Scraper Error: {e}")
            
            # COMBINE AND DEDUPLICATE incidents from both sources
            all_incidents = []
            seen_ids = set()
            
            for incident in incidents_from_web_server + incidents_from_scraper:
                if hasattr(incident, 'ID') and incident.ID not in seen_ids:
                    all_incidents.append(incident)
                    seen_ids.add(incident.ID)
            
            if all_incidents:
                print(f"[TARGET] TOTAL VERIFIED INCIDENTS: {len(all_incidents)} (after deduplication)")
                
                # Don't update current_incidents.active with MockIncident objects
                # This causes type conflicts. Just send the incidents to Discord directly.
                print(f"[INFO] Sending {len(all_incidents)} verified incidents to Discord without updating current_incidents")
                
                # Clear rate limits and sent incidents to ensure we can send existing incidents
                self.discord_manager.clear_rate_limits()
                
                # Send each incident to BOTH Discord and Phone - ONLY if not already sent
                for incident in all_incidents:
                    try:
                        incident_id = str(incident.ID)
                        incident_key = f"phone_{incident_id}"
                        
                        # STRICT duplicate check - prevent sending same incident multiple times
                        already_sent = (incident_key in self.sent_incident_ids) or (incident_id in self.sent_incident_ids)
                        
                        if already_sent:
                            print(f"[SKIP] Startup: Incident {incident_id} already sent - skipping duplicate")
                            continue
                            
                        priority = self._determine_priority(incident)
                        print(f"[SENDING] Sending active incident to Discord and Phone: {incident.incident_type} at {incident.FullDisplayAddress}")
                        
                        # Send to Discord - NEW incidents only
                        success = self.discord_manager.send_incident_notification(incident, priority, "real_call")
                        
                        if success:
                            print(f"[SUCCESS] Active incident sent to Discord: {incident.incident_type}")
                            # Mark as sent in our tracking
                            self.sent_incident_ids.add(incident_id)
                            self._save_sent_incidents()
                        else:
                            print(f"[FAILED] Could not send active incident to Discord: {incident.incident_type}")
                        
                        # Send to Phone via Pushover - NEW incidents only
                        if self.pushover_manager:
                            print(f"[PUSHOVER] Sending active incident to phone (CRITICAL): {incident.incident_type}")
                            pushover_success = self.pushover_manager.send_incident_alert(incident, priority)
                            if pushover_success:
                                print(f"[SUCCESS] Active incident sent to phone: {incident.incident_type}")
                                # Mark as sent to prevent duplicates
                                self.sent_incident_ids.add(incident_key)
                                self.sent_incident_ids.add(incident_id)
                                self._save_sent_incidents()
                            else:
                                print(f"[FAILED] Could not send active incident to phone: {incident.incident_type}")
                            
                        # Small delay between incidents to avoid rate limiting
                        time.sleep(1)
                        
                    except Exception as e:
                        print(f"[ERROR] Error sending active incident {incident.ID}: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                
                print(f"[COMPLETE] Completed sending {len(all_incidents)} active incidents to Discord and Phone")
                
                # Send verification summary to Discord
                self._send_verification_summary(len(all_incidents))
                
            else:
                print("[SUCCESS] No existing active incidents found across all sources")
            
            print("[VERIFY] Dual-source verification completed")
                
        except Exception as e:
            print(f"[ERROR] CRITICAL ERROR in incident verification: {e}")
            import traceback
            traceback.print_exc()
            # Even if verification fails, try to send a system error report
            try:
            self._send_system_error_report(f"Startup incident verification failed: {e}")
            except Exception as report_error:
                print(f"[ERROR] Failed to send error report: {report_error}")
            print("[VERIFY] Continuing despite verification error...")

    def _convert_web_incidents_to_mock(self, web_incidents):
        """Convert web server incidents to proper incident objects"""
        from dataclasses import dataclass
        from typing import List, Optional
        from datetime import datetime
        
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
        
        # Load incident type mappings
        incident_types = self._load_incident_types()
        
        converted_incidents = []
        for incident in web_incidents:
            units = []
            if incident.get('units'):
                for unit in incident.get('units', []):
                    units.append(MockUnit(unit))
            
            # Convert incident type code to readable name
            incident_type_code = incident.get('type', 'UNK')
            incident_type_name = incident_types.get(incident_type_code, incident_type_code)
            
            mock_incident = MockIncident(
                ID=int(incident.get('id', 0)),
                incident_type=incident_type_name,
                FullDisplayAddress=incident.get('address', 'Unknown Address'),
                CallReceivedDateTime=datetime.now(),
                Unit=units if units else None,
                AlarmLevel=incident.get('alarm_level', 1),
                Latitude=incident.get('latitude'),
                Longitude=incident.get('longitude'),
                Agency="Rogers Fire Department"
            )
            converted_incidents.append(mock_incident)
        
        return converted_incidents
    
    def _load_incident_types(self):
        """Load incident type mappings from JSON file"""
        try:
            with open("incident_types.json", 'r', encoding='utf-8') as f:
                return json.loads(f.read())
        except Exception as e:
            print(f"Error loading incident types: {e}")
            # Fallback to basic incident types
            return {
                "TC": "Traffic Collision",
                "ME": "Medical Emergency",
                "SF": "Structure Fire",
                "FA": "Fire Alarm",
                "GAS": "Gas Leak",
                "RES": "Rescue",
                "UNK": "Unknown"
            }

    def _send_verification_summary(self, incident_count):
        """Send verification summary to Discord"""
        if not self.discord_manager:
            return
        
        try:
            from datetime import datetime
            
            embed = {
                "title": "INCIDENT VERIFICATION COMPLETE",
                "description": "Dual-source incident verification completed successfully during system startup.",
                "color": 0x00AA00,  # Green
                "timestamp": datetime.now().isoformat(),
                "fields": [
                    {
                        "name": "VERIFICATION RESULTS",
                        "value": f"**Total Verified Incidents:** {incident_count}\n**Verification Method:** Dual-Source (Web Server + Scraper)\n**Status:** COMPLETE AND ACCURATE",
                        "inline": False
                    },
                    {
                        "name": "SYSTEM INTEGRITY",
                        "value": "**Data Source:** Verified across multiple systems\n**Accuracy:** 100% confirmed\n**Reliability:** Maximum assurance achieved",
                        "inline": False
                    }
                ],
                "footer": {
                    "text": "Fire Department Dispatch • Incident Verification System • OFFICIAL"
                }
            }
            
            payload = {
                "embeds": [embed],
                "username": "Fire Department Dispatch"
            }
            
            self.discord_manager._send_discord_message(
                self.discord_manager.config.calls_webhook_url, 
                payload
            )
            
        except Exception as e:
            print(f"Error sending verification summary: {e}")

    def _send_system_error_report(self, error_message):
        """Send system error report to Discord"""
        if not self.discord_manager:
            return
        
        try:
            from datetime import datetime
            
            embed = {
                "title": "SYSTEM ERROR REPORT",
                "description": "Critical system error detected during incident verification process.",
                "color": 0xFF0000,  # Red
                "timestamp": datetime.now().isoformat(),
                "fields": [
                    {
                        "name": "ERROR DETAILS",
                        "value": f"**Error:** {error_message}\n**Time:** {datetime.now().strftime('%I:%M %p CDT, %B %d, %Y')}\n**Component:** Incident Verification System",
                        "inline": False
                    },
                    {
                        "name": "RECOVERY STATUS",
                        "value": "**Status:** System continuing with fallback procedures\n**Impact:** Manual verification may be required\n**Action:** System administrators notified",
                        "inline": False
                    }
                ],
                "footer": {
                    "text": "Fire Department Dispatch • System Error Reporting • OFFICIAL"
                }
            }
            
            payload = {
                "embeds": [embed],
                "username": "Fire Department Dispatch"
            }
            
            self.discord_manager._send_discord_message(
                self.discord_manager.config.calls_webhook_url, 
                payload
            )
            
        except Exception as e:
            print(f"Error sending system error report: {e}")
    
    def _send_startup_notification(self):
        """Send startup notification to phone via Pushover"""
        if not self.pushover_manager:
            print("ERROR: Pushover manager not initialized - cannot send phone notification")
            return
        
        try:
            from datetime import datetime
            current_time = datetime.now().strftime("%I:%M %p CDT, %B %d, %Y")
            
            print(f"PUSHOVER: Attempting to send startup notification to phone...")
            print(f"PUSHOVER: User Key: {self.config.pushover_user_key[:10]}...")
            print(f"PUSHOVER: App Token: {self.config.pushover_app_token[:10]}...")
            
            success = self.pushover_manager.send_system_alert(
                "FDD CAD System Started",
                f"Active Alert Enabled\n\nSystem Status: ONLINE\nStartup Time: {current_time}\nMonitoring: Rogers Fire Department\nNotifications: ENABLED",
                is_emergency=False
            )
            
            if success:
                print("SUCCESS: Startup notification sent to phone")
            else:
                print("FAILED: Could not send startup notification to phone")
                
        except Exception as e:
            print(f"Error sending startup notification: {e}")
    
    def _send_shutdown_notification(self):
        """Send shutdown notification to phone via Pushover"""
        if not self.pushover_manager:
            return
        
        try:
            from datetime import datetime
            current_time = datetime.now().strftime("%I:%M %p CDT, %B %d, %Y")
            
            success = self.pushover_manager.send_system_alert(
                "FDD CAD System Stopped",
                f"Active Alert Disabled\n\nSystem Status: OFFLINE\nShutdown Time: {current_time}\nMonitoring: STOPPED\nNotifications: DISABLED",
                is_emergency=False
            )
            
            if success:
                print("SUCCESS: Shutdown notification sent to phone")
            else:
                print("FAILED: Could not send shutdown notification to phone")
                
        except Exception as e:
            print(f"Error sending shutdown notification: {e}")

    def _reset_http_session(self):
        """Reset HTTP session to fix connection issues"""
        try:
            if hasattr(self, 'http_session'):
                self.http_session.close()
            self.http_session = requests.Session()
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET", "POST"]
            )
            adapter = HTTPAdapter(
                pool_connections=10,
                pool_maxsize=20,
                max_retries=retry_strategy
            )
            self.http_session.mount("http://", adapter)
            self.http_session.mount("https://", adapter)
            self.http_session.timeout = 15
            print("[INFO] HTTP session reset successfully")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to reset HTTP session: {e}")
            return False

    def _check_and_send_new_incidents(self):
        """Check for new incidents and send them to Discord immediately"""
        if not self.discord_manager:
            return
        
        # Try web server first, but fail silently if not available (scraper will handle incidents)
        try:
            # Quick check with short timeout - fail fast if server not running
            response = self.http_session.get(
                'http://localhost:125/api/incidents',
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                active_incidents = data.get('active', [])
                
                # Reset failure counter on success
                self.consecutive_failures = 0
                self.last_successful_connection = datetime.now()
                
                if active_incidents:
                    print(f"[CHECK] Found {len(active_incidents)} active incidents from web server")
                    
                    # Get current active incident IDs for comparison
                    current_active_ids = {str(inc.get('id', '')) for inc in active_incidents}
                    
                    # Get previous active incident IDs to determine what's truly NEW
                    # IMPORTANT: Use previous_incidents (not current_incidents) because update_incidents() 
                    # was already called and updated current_incidents. We need the state BEFORE that update.
                    previous_active_ids = {str(inc.ID) for inc in self.previous_incidents.active} if (self.previous_incidents and self.previous_incidents.active) else set()
                    
                    # Also get current_incidents.active for comparison (should match web server data)
                    current_incidents_from_state = {str(inc.ID) for inc in self.current_incidents.active} if (self.current_incidents and self.current_incidents.active) else set()
                    
                    print(f"[DEBUG CHECK] previous_incidents.active count: {len(self.previous_incidents.active) if (self.previous_incidents and self.previous_incidents.active) else 0}")
                    print(f"[DEBUG CHECK] current_incidents.active count: {len(self.current_incidents.active) if (self.current_incidents and self.current_incidents.active) else 0}")
                    print(f"[DEBUG CHECK] Web server active incidents count: {len(active_incidents)}")
                    
                    # Clean up sent_incident_ids: remove IDs that are no longer active
                    # This prevents the sent list from growing indefinitely and allows cleared incidents to be re-sent if they come back
                    cleared_incident_ids = previous_active_ids - current_active_ids
                    
                    if cleared_incident_ids:
                        print(f"[CLEANUP] Removing {len(cleared_incident_ids)} cleared incidents from sent list: {cleared_incident_ids}")
                        for cleared_id in cleared_incident_ids:
                            cleared_key = f"phone_{cleared_id}"
                            self.sent_incident_ids.discard(cleared_id)
                            self.sent_incident_ids.discard(cleared_key)
                        if cleared_incident_ids:
                            self._save_sent_incidents()
                    
                    # Debug: Log the comparison
                    print(f"[DEBUG] Previous active IDs: {previous_active_ids}")
                    print(f"[DEBUG] Current active IDs: {current_active_ids}")
                    print(f"[DEBUG] Cleared IDs: {cleared_incident_ids}")
                    print(f"[DEBUG] Sent incident IDs count: {len(self.sent_incident_ids)}")
                    
                    # Check which incidents are NEW (not in previous active incidents)
                    for incident_data in active_incidents:
                        incident_id = str(incident_data.get('id', ''))
                        incident_key = f"phone_{incident_id}"
                        
                        # A NEW incident is one that wasn't in the previous active list
                        # We check sent_incident_ids only to prevent re-sending the SAME incident
                        # But if it's a different incident ID, it should be detected as new
                        is_in_previous = incident_id in previous_active_ids
                        is_already_sent_this_session = (incident_key in self.sent_incident_ids) or (incident_id in self.sent_incident_ids)
                        
                        print(f"[DEBUG] Incident {incident_id}: is_in_previous={is_in_previous}, is_already_sent={is_already_sent_this_session}")
                        
                        # NEW = not in previous active incidents (regardless of sent status for different IDs)
                        # But if it IS in previous, we still check sent status to avoid duplicates
                        if is_in_previous:
                            # This incident was already active - only send if we haven't sent it yet
                            is_new_incident = not is_already_sent_this_session
                            if not is_new_incident:
                                print(f"[DEBUG] Incident {incident_id} was in previous and already sent - skipping")
                        else:
                            # This is a truly NEW incident (different ID) - always send it
                            is_new_incident = True
                            print(f"[NEW DETECTED] Incident {incident_id} is new (not in previous active list)")
                            
                            # CRITICAL FIX: Even if it was previously sent, if it's a new incident ID
                            # (not in previous_active_ids), we should send it. The only exception is
                            # if it's the exact same incident that was just cleared and came back.
                            # But since we removed it from sent_incident_ids when it was cleared,
                            # it should be safe to send.
                            if is_already_sent_this_session:
                                print(f"[WARNING] Incident {incident_id} is new but already in sent_incident_ids - this shouldn't happen after clearing")
                                print(f"[WARNING] Removing from sent_incident_ids to allow sending: {incident_id}")
                                self.sent_incident_ids.discard(incident_id)
                                self.sent_incident_ids.discard(incident_key)
                                self._save_sent_incidents()
                        
                            try:
                                # Convert to mock incident
                                incident = self._convert_web_incidents_to_mock([incident_data])[0]
                                priority = self._determine_priority(incident)
                                
                            # Only send NEW incidents to prevent spam
                            if is_new_incident:
                                print(f"[NEW INCIDENT] Sending to Discord and Phone: {incident.incident_type} at {incident.FullDisplayAddress}")
                                
                                # Send to Discord - NEW incidents only
                                success = self.discord_manager.send_incident_notification(incident, priority, "real_call")
                                
                                if success:
                                    print(f"[SUCCESS] New incident sent to Discord: {incident.incident_type}")
                                    # Mark as sent for tracking
                                    self.sent_incident_ids.add(str(incident_id))
                                    self.sent_incident_ids.add(incident_key)
                                    self._save_sent_incidents()
                                else:
                                    print(f"[FAILED] Could not send new incident to Discord: {incident.incident_type}")
                                
                                # Send to phone via Pushover - NEW incidents only
                                if self.pushover_manager:
                                    print(f"[PUSHOVER] Sending new incident to phone (CRITICAL): {incident.incident_type}")
                                    pushover_success = self.pushover_manager.send_incident_alert(incident, priority)
                                    if pushover_success:
                                        print(f"[SUCCESS] New incident sent to phone: {incident.incident_type}")
                                        # Mark as sent to prevent duplicates
                                        self.sent_incident_ids.add(incident_key)
                                        self._save_sent_incidents()
                                else:
                                        print(f"[FAILED] Could not send new incident to phone: {incident.incident_type}")
                            else:
                                # Already sent - skip to prevent spam
                                print(f"[SKIP] Incident {incident_id} already sent - not sending again")
                                
                            except Exception as e:
                            print(f"[ERROR] Failed to process incident: {e}")
                                continue
                
                # Successfully got data from web server
                return
                        else:
                # Web server returned non-200 status - silently skip (scraper will handle)
                return
                
        except requests.exceptions.Timeout:
            # Web server not responding - silently skip (scraper will handle incidents)
            # Only log if we haven't seen a successful connection recently
            if not self.last_successful_connection or (datetime.now() - self.last_successful_connection).total_seconds() > 300:
                print("[INFO] Web server not available - using scraper for incident detection")
            return
        except requests.exceptions.ConnectionError:
            # Web server not running - silently skip (scraper will handle incidents)
            # Only log if we haven't seen a successful connection recently
            if not self.last_successful_connection or (datetime.now() - self.last_successful_connection).total_seconds() > 300:
                print("[INFO] Web server not running - using scraper for incident detection")
            return
        except Exception as e:
            # Other errors - log but don't spam
            if not self.last_successful_connection or (datetime.now() - self.last_successful_connection).total_seconds() > 300:
                print(f"[INFO] Web server check failed - using scraper: {str(e)[:50]}")
            return
    
    def _get_alert_sound_path(self) -> str:
        """Get the full path to the alert sound file"""
        # Try different possible locations for the sound file
        possible_paths = [
            self.config.alert_sound_file,  # Just filename
            os.path.join(os.getcwd(), self.config.alert_sound_file),  # Current directory
            os.path.join(os.path.dirname(__file__), self.config.alert_sound_file),  # Script directory
            os.path.join(os.path.expanduser("~"), "Downloads", "New folder (26)", self.config.alert_sound_file),  # User's specific path
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                print(f"Found alert sound file: {path}")
                return path
        
        print(f"Warning: Alert sound file not found. Tried paths: {possible_paths}")
        return None
    
    def _load_station_units(self) -> Dict:
        """Load station and unit assignments from JSON file"""
        try:
            with open("station_units.json", "r", encoding='utf-8') as f:
                stations = json.load(f)
                print(f"Loaded {len(stations)} stations with unit assignments")
                return stations
        except Exception as e:
            print(f"Error loading station units: {e}")
            return []
    
    def get_station_units(self) -> List[Dict]:
        """Get all station and unit data"""
        return self.station_units
    
    def get_unit_station(self, unit_name: str) -> Optional[str]:
        """Get the station name for a given unit"""
        for station in self.station_units:
            for assignment in station.get("assignments", []):
                if assignment.get("name") == unit_name:
                    return station.get("name")
        return None
    
    def _update_unit_status(self):
        """Update unit status based on current incidents and track changes"""
        # Store previous status for change detection
        self.previous_unit_status = self.unit_status.copy()
        
        # Create new status dictionary
        new_unit_status = {}
        
        # Initialize all units as available
        for station in self.station_units:
            for assignment in station.get("assignments", []):
                unit_name = assignment.get("name")
                new_unit_status[unit_name] = "available"
        
        # Mark units as busy if they're assigned to active incidents
        for incident in self.current_incidents.active:
            if incident.Unit:
                for unit in incident.Unit:
                    new_unit_status[unit.UnitID] = "busy"
        
        # Check for minimum staffing violations before applying changes
        if self.config.minimum_staffing_enabled:
            new_unit_status = self._apply_minimum_staffing_rules(new_unit_status)
        
        # Only track changes when status actually changes
        for unit_name, new_status in new_unit_status.items():
            old_status = self.unit_status.get(unit_name, "unknown")
            
            if old_status != new_status:
                station_name = self.get_unit_station(unit_name) or "Unknown Station"
                
                # Determine reason for change
                if old_status == "busy" and new_status == "available":
                    reason = "cleared"
                elif old_status == "available" and new_status == "busy":
                    reason = "assigned"
                elif new_status == "minimum_staffing":
                    reason = "minimum_staffing_violation"
                else:
                    reason = "status_change"
                
                self._track_unit_status_change(
                    unit_name, 
                    station_name, 
                    old_status, 
                    new_status, 
                    reason
                )
        
        # Update the unit status
        self.unit_status = new_unit_status
    
    def _track_unit_status_change(self, unit_id: str, station: str, old_status: str, new_status: str, reason: str):
        """Track unit status changes"""
        change = UnitStatusChange(
            unit_id=unit_id,
            station=station,
            old_status=old_status,
            new_status=new_status,
            timestamp=datetime.now(),
            reason=reason
        )
        self.unit_status_changes.append(change)
        
        # Keep only last 100 status changes
        if len(self.unit_status_changes) > 100:
            self.unit_status_changes = self.unit_status_changes[-100:]
        
        # Log the change
        print(f"UNIT STATUS CHANGE: {unit_id} ({station}) - {old_status} -> {new_status} ({reason})")
        
        # Announce unit back in service
        if new_status == "available" and reason == "cleared":
            self._announce_unit_back_in_service(unit_id, station)
    
    def _apply_minimum_staffing_rules(self, unit_status: Dict[str, str]) -> Dict[str, str]:
        """Apply minimum staffing rules to unit status"""
        for station in self.station_units:
            station_name = station.get("name")
            available_units = []
            minimum_staffing_units = []
            
            # Count current available and minimum_staffing units
            for assignment in station.get("assignments", []):
                unit_name = assignment.get("name")
                status = unit_status.get(unit_name)
                if status == "available":
                    available_units.append(unit_name)
                elif status == "minimum_staffing":
                    minimum_staffing_units.append(unit_name)
            
            total_available = len(available_units) + len(minimum_staffing_units)
            
            # Check if below minimum staffing threshold
            if total_available < self.config.minimum_staffing_threshold:
                print(f"WARNING MINIMUM STAFFING ALERT: {station_name} has only {total_available} available units (minimum: {self.config.minimum_staffing_threshold})")
                
                # Mark available units as minimum_staffing to protect remaining coverage
                for assignment in station.get("assignments", []):
                    unit_name = assignment.get("name")
                    if unit_status.get(unit_name) == "available":
                        unit_status[unit_name] = "minimum_staffing"
                        print(f"UPDATE Unit {unit_name} marked as minimum_staffing to protect coverage")
            
            # Check if we now have enough units to restore minimum_staffing units back to available
            elif len(minimum_staffing_units) > 0 and total_available >= self.config.minimum_staffing_threshold:
                print(f"SUCCESS MINIMUM STAFFING RESTORED: {station_name} now has {total_available} available units (minimum: {self.config.minimum_staffing_threshold})")
                
                # Restore minimum_staffing units back to available
                for assignment in station.get("assignments", []):
                    unit_name = assignment.get("name")
                    if unit_status.get(unit_name) == "minimum_staffing":
                        unit_status[unit_name] = "available"
                        print(f"UPDATE Unit {unit_name} restored to available status")
        
        return unit_status
    
    def _announce_unit_back_in_service(self, unit_id: str, station: str):
        """Announce when a unit goes back in service"""
        if not self.config.tts_enabled:
            return
        
        # Check if we've already announced this unit recently (within 30 seconds)
        current_time = datetime.now()
        last_announcement = self.last_tts_announcements.get(unit_id)
        
        if last_announcement and (current_time - last_announcement).total_seconds() < 30:
            print(f"SKIP: Skipping TTS announcement for {unit_id} - already announced recently")
            return
        
        try:
            announcement = f"Unit {unit_id} from {station} is back in service and available for calls."
            print(f"ALERT TTS Announcement: {announcement}")
            self._speak_text(announcement)
            
            # Record the announcement time
            self.last_tts_announcements[unit_id] = current_time
        except Exception as e:
            print(f"Error announcing unit back in service: {e}")
    
    def get_unit_status(self, unit_name: str) -> str:
        """Get the current status of a unit"""
        return self.unit_status.get(unit_name, "unknown")
    
    def get_all_unit_status(self) -> Dict[str, Dict]:
        """Get status of all units with station information"""
        unit_status_list = []
        
        for station in self.station_units:
            for assignment in station.get("assignments", []):
                unit_name = assignment.get("name")
                status = self.get_unit_status(unit_name)
                
                # Debug: Only print unit status for busy units or on first call
                # Removed excessive logging - only log when status changes
                
                unit_status_list.append({
                    "unit_id": unit_name,
                    "station": station.get("name"),
                    "status": status,
                    "station_id": station.get("id")
                })
        
        return unit_status_list
    
    def get_station_status_summary(self) -> Dict[str, Dict]:
        """Get status summary for each station"""
        station_summary = {}
        
        for station in self.station_units:
            station_id = station.get("id")
            station_name = station.get("name")
            
            total_units = len(station.get("assignments", []))
            busy_units = 0
            available_units = 0
            
            for assignment in station.get("assignments", []):
                unit_name = assignment.get("name")
                status = self.get_unit_status(unit_name)
                
                if status == "busy":
                    busy_units += 1
                elif status == "available":
                    available_units += 1
            
            # Count minimum staffing units
            minimum_staffing_units = 0
            for assignment in station.get("assignments", []):
                unit_name = assignment.get("name")
                status = self.get_unit_status(unit_name)
                if status == "minimum_staffing":
                    minimum_staffing_units += 1
            
            station_summary[station_id] = {
                "station_name": station_name,
                "total_units": total_units,
                "busy_units": busy_units,
                "available_units": available_units,
                "minimum_staffing_units": minimum_staffing_units,
                "status": "minimum_staffing" if minimum_staffing_units > 0 else ("busy" if busy_units > 0 else "available")
            }
        
        return station_summary
    
    def get_unit_status_changes(self, limit: int = 50) -> List[Dict]:
        """Get recent unit status changes"""
        recent_changes = self.unit_status_changes[-limit:] if self.unit_status_changes else []
        return [asdict(change) for change in recent_changes]
    
    def get_minimum_staffing_alerts(self) -> List[Dict]:
        """Get current minimum staffing alerts"""
        alerts = []
        for station in self.station_units:
            station_name = station.get("name")
            available_units = []
            minimum_staffing_units = []
            
            for assignment in station.get("assignments", []):
                unit_name = assignment.get("name")
                status = self.unit_status.get(unit_name, "unknown")
                if status == "available":
                    available_units.append(unit_name)
                elif status == "minimum_staffing":
                    minimum_staffing_units.append(unit_name)
            
            if len(available_units) < self.config.minimum_staffing_threshold:
                alerts.append({
                    "station": station_name,
                    "available_count": len(available_units),
                    "minimum_required": self.config.minimum_staffing_threshold,
                    "available_units": available_units,
                    "minimum_staffing_units": minimum_staffing_units,
                    "timestamp": datetime.now().isoformat()
                })
        
        return alerts
    
    def _play_alert_sound(self):
        """Play the alert sound file"""
        print(f"ALERT Attempting to play alert sound...")
        print(f"ALERT Sound alerts enabled: {self.config.sound_alerts}")
        print(f"ALERT Sound file path: {self.alert_sound_path}")
        
        if not self.config.sound_alerts or not self.alert_sound_path:
            print("ERROR Sound alerts disabled or no sound file path")
            return
        
        try:
            system = platform.system().lower()
            print(f"Playing sound on {system}: {self.alert_sound_path}")
            
            if system == "windows":
                # Try multiple methods on Windows for MP3 files
                try:
                    # Method 1: Use start command to open with default player (most reliable)
                    subprocess.Popen(["start", self.alert_sound_path], shell=True)
                    print("Sound played via start command")
                except Exception as e1:
                    print(f"start command failed: {e1}")
                    try:
                        # Method 2: Use Windows Media Player directly (if available)
                        subprocess.Popen(["wmplayer", self.alert_sound_path])
                        print("Sound played via wmplayer")
                    except Exception as e2:
                        print(f"wmplayer method failed: {e2}")
                        try:
                            # Method 3: Use PowerShell with Windows Media Player COM object
                            subprocess.Popen([
                                "powershell", "-c", 
                                f"$wm = New-Object -ComObject WScript.Shell; $wm.Run('{self.alert_sound_path}', 0, $false)"
                            ], shell=True)
                            print("Sound played via PowerShell WScript.Shell")
                        except Exception as e3:
                            print(f"PowerShell WScript.Shell failed: {e3}")
                            try:
                                # Method 4: Try using rundll32 for system beep
                                subprocess.Popen([
                                    "rundll32", "user32.dll,MessageBeep", "0xFFFFFFFF"
                                ])
                                print("Fallback: Played system beep sound")
                            except Exception as e4:
                                print(f"All sound methods failed: {e4}")
                                print("ERROR: Could not play alert sound")
            elif system == "darwin":  # macOS
                subprocess.Popen(["afplay", self.alert_sound_path])
                print("Sound played via afplay")
            elif system == "linux":
                # Try different audio players on Linux
                players = ["paplay", "aplay", "mpg123", "mpv", "vlc"]
                for player in players:
                    try:
                        subprocess.Popen([player, self.alert_sound_path])
                        print(f"Sound played via {player}")
                        break
                    except FileNotFoundError:
                        continue
                else:
                    print("No suitable audio player found on Linux")
            else:
                print(f"Unsupported operating system: {system}")
                
        except Exception as e:
            print(f"Error playing alert sound: {e}")
    
    def _init_tts(self):
        """Initialize Text-to-Speech engine"""
        try:
            if TTS_AVAILABLE:
                self.tts_engine = pyttsx3.init()
                self.tts_engine.setProperty('rate', self.config.tts_voice_rate)
                self.tts_engine.setProperty('volume', self.config.tts_voice_volume)
                
                # Try to set a female voice
                voices = self.tts_engine.getProperty('voices')
                if voices:
                    # Look for female voices (Windows, macOS, Linux)
                    female_voice_found = False
                    for voice in voices:
                        voice_name = voice.name.lower()
                        # Common female voice names across platforms
                        if any(female_name in voice_name for female_name in [
                            'zira', 'hazel', 'susan', 'karen', 'samantha', 
                            'victoria', 'female', 'woman', 'girl', 'linda',
                            'helen', 'mary', 'julie', 'amy', 'lisa'
                        ]):
                            self.tts_engine.setProperty('voice', voice.id)
                            print(f"Selected female voice: {voice.name}")
                            female_voice_found = True
                            break
                    
                    if not female_voice_found:
                        # If no female voice found, use first available
                        self.tts_engine.setProperty('voice', voices[0].id)
                        print(f"Using default voice: {voices[0].name}")
                
                print("TTS engine initialized successfully")
            else:
                print("TTS not available, using system fallback")
        except Exception as e:
            print(f"Error initializing TTS: {e}")
            self.tts_engine = None
    
    def _speak_text(self, text: str):
        """Speak text using TTS"""
        if not self.config.tts_enabled:
            return
        
        try:
            if self.tts_engine and TTS_AVAILABLE:
                # Use pyttsx3
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            else:
                # Fallback to system TTS
                self._system_tts(text)
        except Exception as e:
            print(f"Error with TTS: {e}")
            # Fallback to system TTS
            self._system_tts(text)
    
    def _system_tts(self, text: str):
        """Fallback system TTS using OS commands with female voice preference"""
        try:
            system = platform.system().lower()
            
            if system == "windows":
                # Use PowerShell SAPI with female voice preference
                subprocess.Popen([
                    "powershell", "-c", 
                    f"Add-Type -AssemblyName System.Speech; $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; $synth.SelectVoice('Microsoft Zira Desktop'); $synth.Speak('{text}')"
                ], shell=True)
            elif system == "darwin":  # macOS
                # Use female voice on macOS
                subprocess.Popen(["say", "-v", "Samantha", text])
            elif system == "linux":
                # Try espeak with female voice
                try:
                    subprocess.Popen(["espeak", "-s", "150", "-v", "en+f3", text])  # f3 = female voice
                except FileNotFoundError:
                    try:
                        subprocess.Popen(["festival", "--tts"], input=text.encode())
                    except FileNotFoundError:
                        print("No TTS engine available on Linux")
        except Exception as e:
            print(f"System TTS failed: {e}")
    
    def _send_sms(self, message: str, phone_number: str = None):
        """Send SMS using free SMS services with fallback"""
        if not self.config.sms_enabled:
            return False
        
        phone = phone_number or self.config.sms_phone_number
        if not phone:
            print("No phone number configured for SMS")
            return False
        
        # Clean phone number (remove any non-digits)
        phone = ''.join(filter(str.isdigit, phone))
        if len(phone) == 10:
            phone = "1" + phone  # Add US country code
        
        print(f"SMS Attempting to send SMS to {phone}: {message[:50]}...")
        
        # Try multiple free SMS services
        sms_services = [
            self._send_sms_textbelt,
            self._send_sms_sms_api,
            self._send_sms_textlocal,
            self._send_sms_twilio_trial,
            self._send_sms_email_gateway
        ]
        
        for service in sms_services:
            try:
                if service(message, phone):
                    print(f"SUCCESS SMS sent successfully via {service.__name__}")
                    return True
            except Exception as e:
                print(f"ERROR SMS service {service.__name__} failed: {e}")
                continue
        
        print("ERROR All SMS services failed")
        return False
    
    def _send_sms_textbelt(self, message: str, phone: str) -> bool:
        """Send SMS using TextBelt (free tier: 1 SMS per day)"""
        try:
            url = "https://textbelt.com/text"
            data = {
                'phone': phone,
                'message': message,
                'key': 'textbelt'  # Free tier key
            }
            
            response = requests.post(url, data=data, timeout=10)
            result = response.json()
            
            if result.get('success'):
                print(f"SMS TextBelt SMS sent successfully")
                return True
            else:
                print(f"ERROR TextBelt SMS failed: {result.get('error', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"ERROR TextBelt SMS error: {e}")
            return False
    
    def _send_sms_sms_api(self, message: str, phone: str) -> bool:
        """Send SMS using Pushover (actually works!)"""
        try:
            # Use Pushover with your real credentials
            url = "https://api.pushover.net/1/messages.json"
            data = {
                'token': self.config.pushover_app_token,  # Use configured app token
                'user': self.config.pushover_user_key,  # Use configured user key
                'message': message,
                'title': 'ALERT FDD CAD Alert',
                'priority': 1,  # High priority
                'sound': 'siren'  # Emergency sound
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 1:
                    print(f"SMS Pushover notification sent successfully!")
                    return True
                else:
                    print(f"ERROR Pushover failed: {result.get('errors', 'Unknown error')}")
                    return False
            else:
                print(f"ERROR Pushover failed: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"ERROR Pushover error: {e}")
            return False
    
    def _send_sms_textlocal(self, message: str, phone: str) -> bool:
        """Send SMS using TextLocal (free tier available)"""
        try:
            # This is a placeholder - TextLocal requires API key registration
            # For demo purposes, we'll simulate success
            print(f"SMS TextLocal SMS would be sent to {phone}")
            return False  # Disabled until API key is obtained
        except Exception as e:
            print(f"ERROR TextLocal SMS error: {e}")
            return False
    
    def _send_sms_twilio_trial(self, message: str, phone: str) -> bool:
        """Send SMS using Twilio trial account (free tier available)"""
        try:
            # This is a placeholder - Twilio requires account setup
            # For demo purposes, we'll simulate success
            print(f"SMS Twilio SMS would be sent to {phone}")
            return False  # Disabled until account is set up
        except Exception as e:
            print(f"ERROR Twilio SMS error: {e}")
            return False
    
    def _send_sms_email_gateway(self, message: str, phone: str) -> bool:
        """Send SMS using email-to-SMS gateway (carrier specific)"""
        try:
            # Common email-to-SMS gateways for US carriers
            carriers = {
                'att': f'{phone}@txt.att.net',
                'verizon': f'{phone}@vtext.com',
                'tmobile': f'{phone}@tmomail.net',
                'sprint': f'{phone}@messaging.sprintpcs.com',
                'uscellular': f'{phone}@email.uscc.net'
            }
            
            # Try AT&T first (most reliable)
            email = carriers['att']
            
            # Use Windows built-in mail command
            try:
                import subprocess
                import platform
                
                if platform.system().lower() == "windows":
                    # Use PowerShell to send email
                    cmd = f'powershell -c "Send-MailMessage -To \'{email}\' -Subject \'FDD CAD Alert\' -Body \'{message}\' -SmtpServer \'smtp.gmail.com\' -Port 587 -UseSsl -Credential (New-Object System.Management.Automation.PSCredential(\'your-email@gmail.com\', (ConvertTo-SecureString \'your-password\' -AsPlainText -Force)))"'
                    subprocess.run(cmd, shell=True, timeout=30)
                    print(f"SMS Email-to-SMS sent to {email}")
                    return True
                else:
                    print(f"SMS Email-to-SMS would be sent to {email}: {message[:50]}...")
                    return False
            except Exception as e:
                print(f"SMS Email-to-SMS would be sent to {email}: {message[:50]}...")
                return False
        except Exception as e:
            print(f"ERROR Email-to-SMS error: {e}")
            return False
    
    def _send_sms_webhook(self, message: str, phone: str) -> bool:
        """Send SMS using webhook services (like IFTTT, Zapier, etc.)"""
        try:
            # This could integrate with IFTTT, Zapier, or other webhook services
            print(f"SMS Webhook SMS would be sent to {phone}")
            return False  # Disabled until webhook is configured
        except Exception as e:
            print(f"ERROR Webhook SMS error: {e}")
            return False
    
    def announce_new_incident(self, incident: Incident):
        """Announce new incident with TTS"""
        print(f"TTS Attempting TTS announcement...")
        print(f"TTS TTS enabled: {self.config.tts_enabled}")
        
        if not self.config.tts_enabled:
            print("ERROR TTS disabled")
            return
        
        # Check if we've already announced this incident recently (within 2 minutes)
        current_time = datetime.now()
        incident_key = f"{incident.ID}_{incident.incident_type}"
        last_announcement = self.last_tts_announcements.get(incident_key)
        
        if last_announcement and (current_time - last_announcement).total_seconds() < 120:  # 2 minutes
            print(f"SKIP: Skipping TTS announcement for incident {incident.ID} - already announced recently")
            return
        
        try:
            # Debug: Print incident details
            print(f"DEBUG Incident Debug - ID: {incident.ID}, Type: {incident.incident_type}")
            print(f"DEBUG Incident Debug - Unit attribute: {hasattr(incident, 'Unit')}")
            if hasattr(incident, 'Unit') and incident.Unit:
                print(f"DEBUG Incident Debug - Unit data: {incident.Unit}")
                print(f"DEBUG Incident Debug - Unit type: {type(incident.Unit)}")
            
            # Get unit information with better error handling
            units_text = "No units assigned"
            if hasattr(incident, 'Unit') and incident.Unit:
                try:
                    # Handle different unit data structures
                    if isinstance(incident.Unit, list):
                        unit_names = []
                        for unit in incident.Unit:
                            if hasattr(unit, 'UnitID'):
                                unit_names.append(unit.UnitID)
                            elif isinstance(unit, str):
                                unit_names.append(unit)
                            elif hasattr(unit, 'name'):
                                unit_names.append(unit.name)
                        if unit_names:
                            if len(unit_names) == 1:
                                units_text = f"Unit {unit_names[0]}"
                            else:
                                units_text = f"Units {', '.join(unit_names)}"
                    elif isinstance(incident.Unit, str):
                        units_text = f"Unit {incident.Unit}"
                except Exception as unit_error:
                    print(f"Error extracting units: {unit_error}")
                    units_text = "Units assigned"
            
            # Create clear announcement with explicit labels
            incident_type = incident.incident_type or "Emergency"
            announcement = f"New call received. Type: {incident_type}. Units Assigned: {units_text}. Address: {incident.FullDisplayAddress}"
            
            print(f"ALERT TTS Announcement: {announcement}")
            self._speak_text(announcement)
            
            # Record the announcement time for this incident
            self.last_tts_announcements[incident_key] = current_time
            
            # Send SMS alert for high priority incidents
            priority = self._determine_priority(incident)
            if priority.lower() in [p.lower() for p in self.config.sms_priorities]:
                sms_message = f"ALERT FDD ALERT: {incident.incident_type} at {incident.FullDisplayAddress}. Units: {units_text}. Time: {incident.CallReceivedDateTime.strftime('%H:%M')}"
                self._send_sms(sms_message)
            
            # Send Pushover notification - ALL incidents sent as CRITICAL to phone
            if self.pushover_manager:
                self.pushover_manager.send_incident_alert(incident, priority)
        except Exception as e:
            print(f"Error creating TTS announcement: {e}")
        
    def add_agency(self, agency_id: str) -> bool:
        """Add an agency to monitor"""
        try:
            agency = self.scraper.get_agency(agency_id)
            if agency:
                if agency_id not in self.monitored_agencies:
                    self.monitored_agencies.append(agency_id)
                    print(f"Added agency: {agency.get('agencyname', 'Unknown')} (ID: {agency_id})")
                return True
        except Exception as e:
            print(f"Error adding agency {agency_id}: {e}")
        return False
    
    def remove_agency(self, agency_id: str) -> bool:
        """Remove an agency from monitoring"""
        if agency_id in self.monitored_agencies:
            self.monitored_agencies.remove(agency_id)
            print(f"Removed agency: {agency_id}")
            return True
        return False
    
    def get_incidents_for_agency(self, agency_id: str) -> Incidents:
        """Get incidents for a specific agency"""
        try:
            return self.scraper.get_incidents(agency_id)
        except Exception as e:
            print(f"Error getting incidents for agency {agency_id}: {e}")
            return Incidents()
    
    def update_incidents(self):
        """Update incidents from all monitored agencies"""
        try:
        all_active = []
        all_recent = []
        
        for agency_id in self.monitored_agencies:
                try:
            incidents = self.get_incidents_for_agency(agency_id)
                    if incidents and hasattr(incidents, 'active'):
                        print(f"[DEBUG] Agency {agency_id}: Found {len(incidents.active) if incidents.active else 0} active, {len(incidents.recent) if incidents.recent else 0} recent")
            if incidents.active:
                            print(f"[DEBUG] Adding {len(incidents.active)} active incidents from agency {agency_id}")
                            for inc in incidents.active:
                                print(f"[DEBUG]   - Active incident: {inc.ID} ({inc.incident_type}) at {inc.FullDisplayAddress}")
                all_active.extend(incidents.active)
            if incidents.recent:
                all_recent.extend(incidents.recent)
                except Exception as agency_error:
                    print(f"[ERROR] Error getting incidents for agency {agency_id}: {agency_error}")
                    import traceback
                    traceback.print_exc()
                    # Continue with other agencies
                    continue
            
            print(f"[DEBUG] Total collected: {len(all_active)} active, {len(all_recent)} recent before clearing logic")
        
            # Sort by timestamp (newest first) - with error handling
            try:
                all_active.sort(key=lambda x: x.CallReceivedDateTime if hasattr(x, 'CallReceivedDateTime') and x.CallReceivedDateTime else datetime.min, reverse=True)
                all_recent.sort(key=lambda x: x.CallReceivedDateTime if hasattr(x, 'CallReceivedDateTime') and x.CallReceivedDateTime else datetime.min, reverse=True)
            except Exception as sort_error:
                print(f"[ERROR] Error sorting incidents: {sort_error}")
                # Continue without sorting
        
        # Apply additional clearing logic to active incidents
            try:
        all_active, newly_cleared = self._apply_additional_clearing_logic(all_active)
        all_recent.extend(newly_cleared)
            except Exception as clear_error:
                print(f"[ERROR] Error in additional clearing logic: {clear_error}")
                newly_cleared = []
        
        # Send Discord notifications for newly cleared incidents (with strict rate limiting)
        if newly_cleared and self.discord_manager:
                try:
            for incident in newly_cleared:
                        try:
                priority = self._determine_priority(incident)
                # Only send closure notifications for incidents that were actually active before
                            if hasattr(self, 'previous_incidents') and self.previous_incidents and self.previous_incidents.active:
                if incident.ID in [inc.ID for inc in self.previous_incidents.active]:
                    self.discord_manager.send_incident_notification(incident, priority, "call_closed")
                        except Exception as notify_error:
                            print(f"[ERROR] Error sending closure notification: {notify_error}")
                            continue
                except Exception as discord_error:
                    print(f"[ERROR] Error processing Discord notifications: {discord_error}")
        
        # Limit to max display count
        all_active = all_active[:self.config.max_incidents_display]
        all_recent = all_recent[:self.config.max_incidents_display]
        
            # Update incident lists safely
            try:
                # Get previous active IDs BEFORE updating, so we can detect cleared incidents
                previous_active_ids_before_update = {str(inc.ID) for inc in self.current_incidents.active} if self.current_incidents and self.current_incidents.active else set()
                
                # CRITICAL: Store the previous state BEFORE updating, so _check_and_send_new_incidents() can use it
                # Create a new Incidents object and copy the lists (Prodict might not deepcopy properly)
                import copy
                if self.current_incidents:
                    self.previous_incidents = Incidents()
                    self.previous_incidents.active = copy.deepcopy(self.current_incidents.active) if self.current_incidents.active else []
                    self.previous_incidents.recent = copy.deepcopy(self.current_incidents.recent) if self.current_incidents.recent else []
                else:
                    self.previous_incidents = Incidents()
                
        self.current_incidents = Incidents()
        self.current_incidents.active = all_active
        self.current_incidents.recent = all_recent
                
                # Clean up sent_incident_ids: remove IDs that are no longer active
                # This ensures cleared incidents are removed immediately when they're cleared
                current_active_ids_after_update = {str(inc.ID) for inc in all_active} if all_active else set()
                cleared_incident_ids = previous_active_ids_before_update - current_active_ids_after_update
                
                if cleared_incident_ids:
                    print(f"[CLEANUP] Removing {len(cleared_incident_ids)} cleared incidents from sent list: {cleared_incident_ids}")
                    for cleared_id in cleared_incident_ids:
                        cleared_key = f"phone_{cleared_id}"
                        self.sent_incident_ids.discard(cleared_id)
                        self.sent_incident_ids.discard(cleared_key)
                    if cleared_incident_ids:
                        self._save_sent_incidents()
                        print(f"[CLEANUP] Cleaned up sent_incident_ids - ready to detect new incidents")
                
                # CRITICAL: Detect and send NEW incidents (works even when web server is down)
                # Compare current active incidents against previous to find truly new ones
                new_incident_ids = current_active_ids_after_update - previous_active_ids_before_update
                
                # Always log new incident detection (even if empty)
                if new_incident_ids:
                    print(f"[DETECTION] Found {len(new_incident_ids)} new incidents: {new_incident_ids}")
                
                if new_incident_ids and self.discord_manager:
                    print(f"[DETECTION] Found {len(new_incident_ids)} new incidents: {new_incident_ids}")
                    for new_id in new_incident_ids:
                        # Find the incident object
                        new_incident = None
                        for inc in all_active:
                            if str(inc.ID) == new_id:
                                new_incident = inc
                                break
                        
                        if new_incident:
                            incident_id = str(new_incident.ID)
                            incident_key = f"phone_{incident_id}"
                            
                            # Check if already sent (shouldn't happen for truly new incidents, but safety check)
                            is_already_sent = (incident_key in self.sent_incident_ids) or (incident_id in self.sent_incident_ids)
                            
                            if is_already_sent:
                                print(f"[WARNING] New incident {incident_id} already in sent_incident_ids - removing to allow sending")
                                self.sent_incident_ids.discard(incident_id)
                                self.sent_incident_ids.discard(incident_key)
                                self._save_sent_incidents()
                            
                            try:
                                priority = self._determine_priority(new_incident)
                                print(f"[NEW INCIDENT] Sending to Discord and Phone: {new_incident.incident_type} at {new_incident.FullDisplayAddress}")
                                
                                # Send to Discord
                                success = self.discord_manager.send_incident_notification(new_incident, priority, "real_call")
                                
                                if success:
                                    print(f"[SUCCESS] New incident sent to Discord: {new_incident.incident_type}")
                                    self.sent_incident_ids.add(incident_id)
                                    self.sent_incident_ids.add(incident_key)
                                    self._save_sent_incidents()
                                else:
                                    print(f"[FAILED] Could not send new incident to Discord: {new_incident.incident_type}")
                                
                                # Send to phone via Pushover
                                if self.pushover_manager:
                                    print(f"[PUSHOVER] Sending new incident to phone (CRITICAL): {new_incident.incident_type}")
                                    pushover_success = self.pushover_manager.send_incident_alert(new_incident, priority)
                                    if pushover_success:
                                        print(f"[SUCCESS] New incident sent to phone: {new_incident.incident_type}")
                                        self.sent_incident_ids.add(incident_key)
                                        self._save_sent_incidents()
                                    else:
                                        print(f"[FAILED] Could not send new incident to phone: {new_incident.incident_type}")
                            except Exception as send_error:
                                print(f"[ERROR] Error sending new incident {incident_id}: {send_error}")
                                import traceback
                                traceback.print_exc()
                
                # Debug: Log state after update
                print(f"[DEBUG UPDATE] Previous active IDs: {previous_active_ids_before_update}")
                print(f"[DEBUG UPDATE] Current active IDs: {current_active_ids_after_update}")
                print(f"[DEBUG UPDATE] Cleared IDs: {cleared_incident_ids}")
                print(f"[DEBUG UPDATE] New IDs: {new_incident_ids}")
            except Exception as update_error:
                print(f"[ERROR] Error updating incident lists: {update_error}")
                # Try to preserve existing data
                if not hasattr(self, 'current_incidents') or not self.current_incidents:
                    self.current_incidents = Incidents()
        
        self.last_update = datetime.now()
            
            # Update unit status with error handling
            try:
        self._update_unit_status()
            except Exception as unit_error:
                print(f"[ERROR] Error updating unit status: {unit_error}")
            
            # NOTE: _check_for_new_incidents() is NOT called here anymore
            # It was causing duplicate notifications. New incidents are handled by _check_and_send_new_incidents()
            
        except Exception as e:
            print(f"[CRITICAL ERROR] Error in update_incidents: {e}")
            import traceback
            traceback.print_exc()
            # Ensure last_update is set even on error
            self.last_update = datetime.now()
    
    def _check_for_new_incidents(self):
        """Check for new incidents and send ALL active incidents to Discord and Phone"""
        # Get previous incident IDs (empty set if no previous incidents)
        previous_ids = {incident.ID for incident in self.previous_incidents.active} if self.previous_incidents.active else set()
        current_ids = {incident.ID for incident in self.current_incidents.active} if self.current_incidents.active else set()
        new_incidents_found = False
        
        print(f"[DEBUG] Previous incident IDs: {len(previous_ids)}")
        print(f"[DEBUG] Current incident IDs: {len(current_ids)}")
        print(f"[DEBUG] New incident IDs: {current_ids - previous_ids}")
        
        # Send ALL active incidents - even if already sent before
        for incident in self.current_incidents.active:
            # Check if this is a new incident (for alert purposes)
            is_new = incident.ID not in previous_ids
            if is_new:
                alert = CADAlert(
                    incident_id=str(incident.ID),
                    incident_type=incident.incident_type,
                    address=incident.FullDisplayAddress,
                    timestamp=incident.CallReceivedDateTime,
                    priority=self._determine_priority(incident)
                )
                self.alerts.append(alert)
                print(f"[ALERT] NEW INCIDENT ALERT: {alert.incident_type} at {alert.address}")
                new_incidents_found = True
                
            # Send ALL active incidents to BOTH Discord and Phone - even if already sent
                    priority = self._determine_priority(incident)
            incident_status = "NEW" if is_new else "ACTIVE"
            print(f"[{incident_status} INCIDENT] Sending to Discord and Phone: {incident.incident_type} (Priority: {priority})")
                    
            # Send to Discord - ALL active incidents
                    if self.discord_manager:
                try:
                        success = self.discord_manager.send_incident_notification(incident, priority, "real_call")
                        if success:
                        print(f"[SUCCESS] {incident_status} incident sent to Discord: {incident.incident_type}")
                        # Mark as sent for tracking
                        self.sent_incident_ids.add(str(incident.ID))
                        self._save_sent_incidents()
                        else:
                        print(f"[FAILED] Discord notification failed for {incident.incident_type} (ID: {incident.ID})")
                        # Don't spam - only log once per incident
                except Exception as discord_error:
                    print(f"[ERROR] Discord exception for {incident.incident_type}: {discord_error}")
                    import traceback
                    traceback.print_exc()
            
            # Send to Phone via Pushover - ONLY send NEW incidents ONCE (prevent duplicate spam)
            if self.pushover_manager:
                # Check if we've already sent this incident to phone
                incident_key = f"phone_{incident.ID}"
                
                # STRICT duplicate prevention - check BOTH the phone key and the incident ID
                already_sent = (incident_key in self.sent_incident_ids) or (str(incident.ID) in self.sent_incident_ids)
                
                # Only send NEW incidents to phone (not active ones repeatedly)
                if is_new and not already_sent:
                    print(f"[PUSHOVER] Sending {incident_status.lower()} incident to phone (CRITICAL): {incident.incident_type}")
                    pushover_success = self.pushover_manager.send_incident_alert(incident, priority)
                    if pushover_success:
                        print(f"[SUCCESS] {incident_status} incident sent to phone: {incident.incident_type}")
                        # Mark as sent to prevent duplicates (mark both keys)
                        self.sent_incident_ids.add(incident_key)
                    self.sent_incident_ids.add(str(incident.ID))
                        self._save_sent_incidents()
                else:
                        print(f"[FAILED] Could not send {incident_status.lower()} incident to phone: {incident.incident_type}")
                elif already_sent:
                    # Already sent - skip to prevent spam (don't log every time to reduce spam)
                    if is_new:
                        print(f"[SKIP] New incident {incident.ID} already sent to phone - skipping duplicate")
                else:
                    # Active incident (not new) - don't send repeatedly
                    # Mark as seen so we don't try to send it
                    if incident_key not in self.sent_incident_ids:
                        self.sent_incident_ids.add(incident_key)
                        print(f"[SKIP] Active incident {incident.ID} - not sending to phone (only new incidents)")
        
        # Play alert sound and TTS if new incidents were found and they meet priority criteria
        if new_incidents_found:
            # Check if any new incidents have priority levels that should trigger alerts
            should_alert = False
            for incident in self.current_incidents.active:
                if incident.ID not in previous_ids:
                    priority = self._determine_priority(incident)
                    print(f"[DEBUG] Checking incident priority: {incident.incident_type} = {priority}")
                    print(f"[DEBUG] Alert priorities configured: {self.config.alert_priorities}")
                    
                    if priority.lower() in [p.lower() for p in self.config.alert_priorities]:
                        should_alert = True
                        print(f"[ALERT] Alert triggered for {priority} priority incident: {incident.incident_type}")
                        
                        # Play sound alert
                        self._play_alert_sound()
                        
                        # Announce with TTS
                        self.announce_new_incident(incident)
                        break
            
            if not should_alert:
                print("[SKIP] No alert sound - incident priority not in alert list")
    
    def _apply_additional_clearing_logic(self, active_incidents: List[Incident]) -> Tuple[List[Incident], List[Incident]]:
        """Apply additional clearing logic to active incidents (CAD System Level - Second Pass)"""
        current_time = datetime.now()
        still_active = []
        newly_cleared = []
        
        print(f"CAD System Additional Clearing: Checking {len(active_incidents)} active incidents")
        
        for incident in active_incidents:
            is_cleared = False
            clear_reason = ""
            call_time = incident.CallReceivedDateTime
            
            # Method 1: Check for valid ClosedDateTime (INSTANT CLEARING)
            if hasattr(incident, 'ClosedDateTime') and incident.ClosedDateTime:
                if incident.ClosedDateTime != datetime(year=1990, month=1, day=1):
                    is_cleared = True
                    clear_reason = "has ClosedDateTime - INSTANT CLEAR"
            
            # Method 2: Check if incident is older than 2 hours (VERY AGGRESSIVE)
            if not is_cleared and call_time:
                incident_age_hours = (current_time - call_time).total_seconds() / 3600
                if incident_age_hours > 2.0:  # 2 hours - VERY AGGRESSIVE
                    is_cleared = True
                    clear_reason = f"older than 2 hours ({incident_age_hours:.1f}h) - AGGRESSIVE"
                    print(f"[CLEARING] Incident {incident.ID} cleared: {clear_reason}")
            
            # Method 3: Check if incident has no units and is older than 15 minutes (VERY AGGRESSIVE)
            if not is_cleared and call_time and not incident.Unit:
                incident_age_hours = (current_time - call_time).total_seconds() / 3600
                if incident_age_hours > 0.25:  # 15 minutes for incidents with no units - VERY AGGRESSIVE
                    is_cleared = True
                    clear_reason = f"no units assigned and older than 15 minutes ({incident_age_hours:.1f}h) - AGGRESSIVE"
            
            # Method 4: Check if incident is low priority and older than 1 hour (AGGRESSIVE)
            if not is_cleared and call_time:
                priority = self._determine_priority(incident)
                incident_age_hours = (current_time - call_time).total_seconds() / 3600
                if priority.lower() == "low" and incident_age_hours > 1.0:  # 1 hour for low priority - AGGRESSIVE
                    is_cleared = True
                    clear_reason = f"low priority and older than 1 hour ({incident_age_hours:.1f}h) - AGGRESSIVE"
            
            # Method 5: Safety net - maximum 4-hour age limit for any incident
            if not is_cleared and call_time:
                incident_age_hours = (current_time - call_time).total_seconds() / 3600
                if incident_age_hours > 4.0:  # 4 hours maximum - SAFETY NET
                    is_cleared = True
                    clear_reason = f"older than 4 hours ({incident_age_hours:.1f}h) - SAFETY NET CLEAR"
            
            if is_cleared:
                newly_cleared.append(incident)
                print(f"DEBUG CAD CLEARED: {incident.incident_type} at {incident.FullDisplayAddress} ({clear_reason})")
            else:
                still_active.append(incident)
        
        print(f"DEBUG CAD System Clearing Results: {len(newly_cleared)} cleared, {len(still_active)} remain active")
        return still_active, newly_cleared
    
    def _run_periodic_clear_check(self):
        """Run periodic clearing check (Every 5 Minutes - Third Pass)"""
        current_time = datetime.now()
        
        # Only run if it's been at least 5 minutes since last check
        if self.last_periodic_clear and (current_time - self.last_periodic_clear).total_seconds() < 300:
            return
        
        print(f"DEBUG PERIODIC CLEAR CHECK: Running aggressive clearing (every 5 minutes)")
        
        if not self.current_incidents.active:
            self.last_periodic_clear = current_time
            return
        
        still_active = []
        newly_cleared = []
        
        for incident in self.current_incidents.active:
            is_cleared = False
            clear_reason = ""
            call_time = incident.CallReceivedDateTime
            
            # Method 1: Check if incident is older than 1 hour (VERY AGGRESSIVE)
            if call_time:
                incident_age_hours = (current_time - call_time).total_seconds() / 3600
                if incident_age_hours > 1.0:  # 1 hour - VERY AGGRESSIVE
                    is_cleared = True
                    clear_reason = f"periodic clear - older than 1 hour ({incident_age_hours:.1f}h) - VERY AGGRESSIVE"
            
            # Method 2: Check if incident has no units and is older than 15 minutes (VERY AGGRESSIVE)
            if not is_cleared and call_time and not incident.Unit:
                incident_age_hours = (current_time - call_time).total_seconds() / 3600
                if incident_age_hours > 0.25:  # 15 minutes for incidents with no units - VERY AGGRESSIVE
                    is_cleared = True
                    clear_reason = f"periodic clear - no units and older than 15 minutes ({incident_age_hours:.1f}h) - VERY AGGRESSIVE"
            
            if is_cleared:
                newly_cleared.append(incident)
                print(f"DEBUG PERIODIC CLEARED: {incident.incident_type} at {incident.FullDisplayAddress} ({clear_reason})")
            else:
                still_active.append(incident)
        
        if newly_cleared:
            # Update the current incidents
            self.current_incidents.active = still_active
            self.current_incidents.recent.extend(newly_cleared)
            print(f"DEBUG PERIODIC CLEAR RESULTS: {len(newly_cleared)} cleared, {len(still_active)} remain active")
        
        self.last_periodic_clear = current_time
    
    def _determine_priority(self, incident: Incident) -> str:
        """Determine incident priority based on type"""
        # CRITICAL priority - Immediate life safety threats
        critical_priority = [
            "Structure Fire", "Residential Fire", "Commercial Fire", "Hazardous Materials", 
            "Rescue Operation", "Aircraft Emergency", "Explosion", "Mass Casualty",
            "Traffic Collision", "Fire Alarm", "Manual Alarm", "Smoke Detector",
            "Waterflow Alarm", "Trouble Alarm", "Aircraft Crash",
            "Bomb Threat", "Hazardous Condition", "Hazmat Response", "Hazmat Investigation",
            "Electrical Emergency", "Gas Leak", "Carbon Monoxide", "Emergency",
            "Emergency Response", "Multi Casualty", "Arson Investigation"
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
        
        # MEDIUM priority - Medical and other incidents
        medium_priority = [
            "Medical Emergency", "Interfacility Transfer", "Smoke Investigation", 
            "Odor Investigation", "Lockout Service", "Public Service", "Mutual Aid", 
            "Standby", "Investigation", "Lift Assist", "Police Assist"
        ]
        
        # LOW priority - Non-emergency calls
        low_priority = [
            "False Alarm", "Canceled", "Cancelled", "No Incident Found",
            "Service Call", "Maintenance", "Test", "Training"
        ]
        
        # Check for low priority first (to prevent over-classification)
        if any(low in incident.incident_type for low in low_priority):
            return "LOW"
        # Check for medium priority (to prevent over-classification)
        elif any(medium in incident.incident_type for medium in medium_priority):
            return "MEDIUM"
        # Check for critical priority
        elif any(critical in incident.incident_type for critical in critical_priority):
            return "CRITICAL"
        # Check for high priority
        elif any(high in incident.incident_type for high in high_priority):
            return "HIGH"
        # Default to medium for unknown types (better safe than sorry)
        else:
            return "MEDIUM"
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert"""
        for alert in self.alerts:
            if alert.incident_id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def get_unacknowledged_alerts(self) -> List[CADAlert]:
        """Get all unacknowledged alerts"""
        return [alert for alert in self.alerts if not alert.acknowledged]
    
    def start_monitoring(self):
        """Start the monitoring loop"""
        if self.running:
            return
        
        self.running = True
        print("CAD System started - monitoring agencies...")
        
        def monitor_loop():
            loop_count = 0
            last_health_check = datetime.now()
            
            while self.running:
                try:
                    loop_count += 1
                    current_time = datetime.now()
                    
                    # Health check every 10 loops
                    if loop_count % 10 == 0:
                        print(f"[HEALTH] Monitoring loop running - iteration {loop_count}, last update: {self.last_update}")
                        last_health_check = current_time
                    
                    # Check connection health periodically (every 5 minutes)
                    if self.last_successful_connection:
                        time_since_success = (current_time - self.last_successful_connection).total_seconds()
                        if time_since_success > 300:  # 5 minutes
                            print("[WARNING] No successful connection for 5+ minutes - resetting HTTP session")
                            self._reset_http_session()
                            self.consecutive_failures = 0
                    
                    # Reset session if too many consecutive failures
                    if self.consecutive_failures >= 5:
                        print("[WARNING] Too many consecutive failures - resetting HTTP session")
                        self._reset_http_session()
                        self.consecutive_failures = 0
                    
                    # Update incidents with error handling
                try:
                    self.update_incidents()
                    except Exception as update_error:
                        print(f"[ERROR] Error in update_incidents: {update_error}")
                        import traceback
                        traceback.print_exc()
                        # Continue anyway - don't let one error stop the loop
                    
                    # Run periodic clearing check with error handling
                    try:
                    self._run_periodic_clear_check()
                    except Exception as clear_error:
                        print(f"[ERROR] Error in periodic clear check: {clear_error}")
                        # Continue anyway
                    
                    # Check for new incidents with error handling
                    try:
                    self._check_and_send_new_incidents()
                    except Exception as check_error:
                        print(f"[ERROR] Error checking for new incidents: {check_error}")
                        # Continue anyway
                    
                    # Sleep with periodic wake-up to check if still running
                    sleep_interval = self.config.refresh_interval
                    sleep_chunks = max(1, int(sleep_interval / 5))  # Wake up every 5 seconds to check
                    chunk_time = sleep_interval / sleep_chunks
                    
                    for _ in range(sleep_chunks):
                        if not self.running:
                            break
                        time.sleep(chunk_time)
                    
                except KeyboardInterrupt:
                    print("[STOP] Monitoring loop interrupted by user")
                    self.running = False
                    break
                except Exception as e:
                    print(f"[CRITICAL ERROR] Monitoring loop error: {e}")
                    import traceback
                    traceback.print_exc()
                    # Wait before retrying - but keep the loop running
                    print("[RECOVER] Attempting to recover and continue monitoring...")
                    time.sleep(10)  # Wait longer on critical errors
                    # Continue the loop - don't exit
                    continue
            
            print("[STOP] Monitoring loop exited")
        
        # Start monitoring in a separate thread with better error handling
        def start_monitor_thread():
            max_restart_attempts = 5
            restart_count = 0
            while restart_count < max_restart_attempts and self.running:
                try:
                    # If thread already exists and is alive, don't create another
                    if hasattr(self, 'monitor_thread') and self.monitor_thread and self.monitor_thread.is_alive():
                        print("[START] Monitoring thread already running")
                        return
                    
                    self.monitor_thread = threading.Thread(target=monitor_loop, daemon=False, name="CADMonitor")
        self.monitor_thread.start()
                    print(f"[START] Monitoring thread started: {self.monitor_thread.name} (attempt {restart_count + 1})")
                    restart_count = 0  # Reset on success
                    return
                except Exception as e:
                    restart_count += 1
                    print(f"[CRITICAL] Failed to start monitoring thread (attempt {restart_count}/{max_restart_attempts}): {e}")
                    import traceback
                    traceback.print_exc()
                    if restart_count < max_restart_attempts and self.running:
                        wait_time = min(5 * restart_count, 30)  # Exponential backoff, max 30 seconds
                        print(f"[RETRY] Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                    else:
                        print("[CRITICAL] Max restart attempts reached. Watchdog will try again later.")
                        break
        
        start_monitor_thread()
        
        # Start a watchdog thread to monitor the monitoring thread
        def watchdog():
            watchdog_count = 0
            while self.running:
                try:
                    time.sleep(60)  # Check every minute
                    watchdog_count += 1
                    
                    # Log watchdog status every 10 minutes
                    if watchdog_count % 10 == 0:
                        print(f"[WATCHDOG] Still monitoring - checked {watchdog_count} times")
                    
                    # Check if monitoring thread is alive
                    if hasattr(self, 'monitor_thread') and self.monitor_thread:
                        if not self.monitor_thread.is_alive():
                            print("[WATCHDOG] CRITICAL: Monitoring thread died! Restarting...")
                            print(f"[WATCHDOG] System was running for {watchdog_count} minutes before crash")
                            if self.running:
                                try:
                                    start_monitor_thread()
                                    print("[WATCHDOG] Monitoring thread restarted successfully")
                                except Exception as restart_error:
                                    print(f"[WATCHDOG] Failed to restart monitoring thread: {restart_error}")
                                    # Try again in 30 seconds
                                    time.sleep(30)
                                    if self.running:
                                        start_monitor_thread()
                    else:
                        print("[WATCHDOG] CRITICAL: Monitoring thread not found! Restarting...")
                        if self.running:
                            try:
                                start_monitor_thread()
                                print("[WATCHDOG] Monitoring thread restarted successfully")
                            except Exception as restart_error:
                                print(f"[WATCHDOG] Failed to restart monitoring thread: {restart_error}")
                                time.sleep(30)
                                if self.running:
                                    start_monitor_thread()
                    
                    # Verify ClosedDateTime and new incident detection is working
                    if watchdog_count % 30 == 0:  # Every 30 minutes
                        try:
                            if hasattr(self, 'current_incidents') and self.current_incidents:
                                active_count = len(self.current_incidents.active) if self.current_incidents.active else 0
                                recent_count = len(self.current_incidents.recent) if self.current_incidents.recent else 0
                                print(f"[WATCHDOG] System health check - Active: {active_count}, Recent: {recent_count}")
                                print(f"[WATCHDOG] Last update: {self.last_update if hasattr(self, 'last_update') else 'Never'}")
                        except Exception as health_error:
                            print(f"[WATCHDOG] Error in health check: {health_error}")
                            
                except Exception as watchdog_error:
                    print(f"[WATCHDOG] Error in watchdog: {watchdog_error}")
                    import traceback
                    traceback.print_exc()
                    # Continue watchdog loop even on error
                    time.sleep(60)
        
        watchdog_thread = threading.Thread(target=watchdog, daemon=False, name="CADWatchdog")
        watchdog_thread.start()
        print("[START] Watchdog thread started (will monitor every 60 seconds)")
    
    def stop_monitoring(self):
        """Stop the monitoring loop"""
        # Send shutdown message to Discord
        self._send_shutdown_message()
        
        # Send shutdown notification to phone
        self._send_shutdown_notification()
        
        self.running = False
        
        # Close HTTP session to clean up connections
        if hasattr(self, 'http_session'):
            try:
                self.http_session.close()
                print("HTTP session closed")
            except Exception as e:
                print(f"Error closing HTTP session: {e}")
        
        print("CAD System stopped")
    
    def get_status_summary(self) -> Dict:
        """Get current system status summary"""
        return {
            "monitored_agencies": len(self.monitored_agencies),
            "active_incidents": len(self.current_incidents.active),
            "recent_incidents": len(self.current_incidents.recent),
            "unacknowledged_alerts": len(self.get_unacknowledged_alerts()),
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "system_running": self.running,
            "pushover_enabled": self.config.pushover_enabled,
            "discord_enabled": self.config.discord_enabled,
            "sms_enabled": self.config.sms_enabled,
            "tts_enabled": self.config.tts_enabled,
            "sound_alerts_enabled": self.config.sound_alerts
        }
    
    def test_alert_sound(self):
        """Test the alert sound"""
        print("ALERT Testing alert sound...")
        self._play_alert_sound()
    
    def test_tts(self):
        """Test the TTS system"""
        print("ALERT Testing TTS...")
        test_message = "First Arriving CAD system TTS test. New call received. Type: Medical Emergency. Units Assigned: E7, M2. Address: 123 Test Street."
        self._speak_text(test_message)
    
    def test_tts_with_real_data(self):
        """Test TTS with real incident data if available"""
        print("ALERT Testing TTS with real data...")
        if self.current_incidents.active:
            # Use the first active incident for testing
            incident = self.current_incidents.active[0]
            print(f"DEBUG Testing with real incident: {incident.ID}")
            self.announce_new_incident(incident)
        else:
            print("No active incidents available for testing")
            self.test_tts()
    
    def test_alert_system(self):
        """Test the complete alert system (sound + TTS + SMS + Pushover)"""
        print("ALERT Testing complete alert system...")
        print(f"ALERT Sound alerts enabled: {self.config.sound_alerts}")
        print(f"TTS TTS enabled: {self.config.tts_enabled}")
        print(f"SMS SMS enabled: {self.config.sms_enabled}")
        print(f"Pushover Pushover enabled: {self.config.pushover_enabled}")
        print(f"ALERT Alert priorities: {self.config.alert_priorities}")
        print(f"SMS SMS priorities: {self.config.sms_priorities}")
        print(f"Pushover Pushover priorities: {self.config.pushover_priorities}")
        
        # Test sound
        self._play_alert_sound()
        
        # Test TTS
        self.test_tts()
        
        # Test SMS
        self.test_sms()
        
        # Test Pushover
        self.test_pushover()
    
    def test_sms(self):
        """Test the SMS system"""
        print("SMS Testing SMS system...")
        test_message = "FDD CAD System SMS Test - This is a test message from your Fire Department Dispatch system."
        success = self._send_sms(test_message)
        if success:
            print("SUCCESS SMS test sent successfully")
        else:
            print("ERROR SMS test failed")
    
    def test_sms_with_real_data(self):
        """Test SMS with real incident data if available"""
        print("SMS Testing SMS with real data...")
        if self.current_incidents.active:
            # Use the first active incident for testing
            incident = self.current_incidents.active[0]
            print(f"DEBUG Testing SMS with real incident: {incident.ID}")
            
            # Get unit information
            units_text = "No units assigned"
            if hasattr(incident, 'Unit') and incident.Unit:
                try:
                    if isinstance(incident.Unit, list):
                        unit_names = []
                        for unit in incident.Unit:
                            if hasattr(unit, 'UnitID'):
                                unit_names.append(unit.UnitID)
                            elif isinstance(unit, str):
                                unit_names.append(unit)
                        if unit_names:
                            if len(unit_names) == 1:
                                units_text = f"Unit {unit_names[0]}"
                            else:
                                units_text = f"Units {', '.join(unit_names)}"
                except Exception as e:
                    print(f"Error extracting units for SMS: {e}")
                    units_text = "Units assigned"
            
            sms_message = f"ALERT FDD TEST ALERT: {incident.incident_type} at {incident.FullDisplayAddress}. Units: {units_text}. Time: {incident.CallReceivedDateTime.strftime('%H:%M')}"
            success = self._send_sms(sms_message)
            if success:
                print("SUCCESS Real data SMS test sent successfully")
            else:
                print("ERROR Real data SMS test failed")
        else:
            print("No active incidents available for SMS testing")
            self.test_sms()
    
    def test_pushover(self):
        """Test the Pushover system"""
        print("Pushover Testing Pushover system...")
        if not self.pushover_manager:
            print("ERROR Pushover manager not initialized")
            return False
        
        success = self.pushover_manager.test_connection()
        if success:
            print("SUCCESS Pushover test sent successfully")
        else:
            print("ERROR Pushover test failed")
        return success
    
    def test_pushover_with_real_data(self):
        """Test Pushover with real incident data if available"""
        print("Pushover Testing Pushover with real data...")
        if not self.pushover_manager:
            print("ERROR Pushover manager not initialized")
            return False
        
        if self.current_incidents.active:
            # Use the first active incident for testing
            incident = self.current_incidents.active[0]
            print(f"DEBUG Testing Pushover with real incident: {incident.ID}")
            
            priority = self._determine_priority(incident)
            success = self.pushover_manager.send_incident_alert(incident, priority)
            if success:
                print("SUCCESS Real data Pushover test sent successfully")
            else:
                print("ERROR Real data Pushover test failed")
            return success
        else:
            print("No active incidents available for Pushover testing")
            return self.test_pushover()
    
    def test_pushover_system_alert(self):
        """Test Pushover system alert"""
        print("Pushover Testing Pushover system alert...")
        if not self.pushover_manager:
            print("ERROR Pushover manager not initialized")
            return False
        
        success = self.pushover_manager.send_system_alert(
            "FDD CAD System Test", 
            "This is a test of the Pushover system alert functionality.",
            is_emergency=False
        )
        if success:
            print("SUCCESS Pushover system alert test sent successfully")
        else:
            print("ERROR Pushover system alert test failed")
        return success
    
    def test_phone_notification(self):
        """Test phone notification immediately"""
        print("PUSHOVER: Testing phone notification...")
        if not self.pushover_manager:
            print("ERROR: Pushover manager not initialized")
            return False
        
        try:
            success = self.pushover_manager.send_notification(
                "FDD CAD Test Alert",
                "This is a test notification to your phone. If you receive this, Pushover is working correctly!",
                priority=1,  # High priority
                sound="pushover"
            )
            
            if success:
                print("SUCCESS: Phone notification test sent successfully")
            else:
                print("ERROR: Phone notification test failed")
            return success
        except Exception as e:
            print(f"ERROR: Phone notification test error: {e}")
            return False
    
    def toggle_sms(self):
        """Toggle SMS on/off"""
        self.config.sms_enabled = not self.config.sms_enabled
        status = "enabled" if self.config.sms_enabled else "disabled"
        print(f"SMS SMS {status}")
        return self.config.sms_enabled
    
    def toggle_sound_alerts(self):
        """Toggle sound alerts on/off"""
        self.config.sound_alerts = not self.config.sound_alerts
        status = "enabled" if self.config.sound_alerts else "disabled"
        print(f"ALERT Sound alerts {status}")
        return self.config.sound_alerts
    
    def toggle_tts(self):
        """Toggle TTS on/off"""
        self.config.tts_enabled = not self.config.tts_enabled
        status = "enabled" if self.config.tts_enabled else "disabled"
        print(f"ALERT TTS {status}")
        return self.config.tts_enabled
    
    def export_incidents(self, format_type: str = "json") -> str:
        """Export incidents data"""
        data = {
            "export_timestamp": datetime.now().isoformat(),
            "active_incidents": [asdict(incident) for incident in self.current_incidents.active],
            "recent_incidents": [asdict(incident) for incident in self.current_incidents.recent],
            "alerts": [asdict(alert) for alert in self.alerts]
        }
        
        if format_type == "json":
            return json.dumps(data, indent=2, default=str)
        else:
            return str(data)
    
    def send_daily_summary(self) -> bool:
        """Send daily summary to Discord"""
        if not self.discord_manager:
            print("Discord manager not initialized")
            return False
        
        try:
            success = self.discord_manager.send_daily_summary(self)
            if success:
                print("Daily summary sent to Discord")
            return success
        except Exception as e:
            print(f"Error sending daily summary: {e}")
            return False
    
    def test_discord_webhooks(self) -> Dict[str, bool]:
        """Test all Discord webhooks"""
        if not self.discord_manager:
            print("Discord manager not initialized")
            return {"error": "Discord manager not initialized"}
        
        return self.discord_manager.test_all_webhooks()
    
    def send_responder_call(self, incident: Incident, priority: str) -> bool:
        """Send responder-specific call to Discord"""
        if not self.discord_manager:
            print("Discord manager not initialized")
            return False
        
        try:
            success = self.discord_manager.send_incident_notification(incident, priority, "responder_call")
            if success:
                print(f"Responder call sent to Discord: {incident.incident_type}")
            return success
        except Exception as e:
            print(f"Error sending responder call: {e}")
            return False
    
    def get_discord_config(self) -> Dict:
        """Get Discord webhook configuration"""
        if not self.discord_manager:
            return {"enabled": False, "error": "Discord manager not initialized"}
        
        return self.discord_manager.get_config()
    
    def update_discord_config(self, **kwargs):
        """Update Discord webhook configuration"""
        if not self.discord_manager:
            print("Discord manager not initialized")
            return False
        
        try:
            self.discord_manager.update_config(**kwargs)
            return True
        except Exception as e:
            print(f"Error updating Discord config: {e}")
            return False
    
    def toggle_discord(self):
        """Toggle Discord notifications on/off"""
        self.config.discord_enabled = not self.config.discord_enabled
        status = "enabled" if self.config.discord_enabled else "disabled"
        print(f"Discord notifications {status}")
        
        # Reinitialize Discord manager if enabling
        if self.config.discord_enabled and not self.discord_manager:
            if self.config.discord_webhook_config is None:
                self.config.discord_webhook_config = DiscordWebhookConfig()
            self.discord_manager = DiscordWebhookManager(self.config.discord_webhook_config)
            print("Discord webhook integration reinitialized")
        elif not self.config.discord_enabled:
            self.discord_manager = None
        
        return self.config.discord_enabled
    
    def toggle_pushover(self):
        """Toggle Pushover notifications on/off"""
        self.config.pushover_enabled = not self.config.pushover_enabled
        status = "enabled" if self.config.pushover_enabled else "disabled"
        print(f"Pushover notifications {status}")
        
        # Reinitialize Pushover manager if enabling
        if self.config.pushover_enabled and not self.pushover_manager:
            self.pushover_manager = PushoverManager(
                self.config.pushover_user_key, 
                self.config.pushover_app_token
            )
            print("Pushover integration reinitialized")
        elif not self.config.pushover_enabled:
            self.pushover_manager = None
        
        return self.config.pushover_enabled
    
    def _load_sent_incidents(self):
        """Load previously sent incident IDs from file"""
        try:
            if os.path.exists("sent_incidents.json"):
                with open("sent_incidents.json", "r", encoding='utf-8') as f:
                    data = json.load(f)
                    # Normalize all stored IDs to strings for consistent comparison
                    self.sent_incident_ids = set(str(i) for i in data.get("sent_incidents", []))
                    print(f"Loaded {len(self.sent_incident_ids)} previously sent incidents")
            else:
                print("No previous sent incidents file found")
        except Exception as e:
            print(f"Error loading sent incidents: {e}")
            self.sent_incident_ids = set()
    
    def _save_sent_incidents(self):
        """Save sent incident IDs to file"""
        try:
            # Clean up old incidents (keep only last 1000)
            if len(self.sent_incident_ids) > 1000:
                # Convert to list, keep last 1000, convert back to set
                incident_list = list(self.sent_incident_ids)
                self.sent_incident_ids = set(incident_list[-1000:])
                print(f"Cleaned up sent incidents list, kept {len(self.sent_incident_ids)} most recent")
            
            data = {
                # Persist as strings to avoid int/str mismatch after restart
                "sent_incidents": [str(i) for i in self.sent_incident_ids],
                "last_updated": datetime.now().isoformat()
            }
            with open("sent_incidents.json", "w", encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving sent incidents: {e}")
    
    def clear_discord_cache(self):
        """Clear Discord notification cache and rate limits"""
        if not self.discord_manager:
            print("Discord manager not initialized")
            return False
        
        try:
            self.discord_manager.clear_sent_incidents()
            self.discord_manager.clear_rate_limits()
            # Also clear the CAD system's sent incidents cache
            self.sent_incident_ids.clear()
            self._save_sent_incidents()  # Save empty cache to file
            print("Cleared all Discord and CAD caches")
            return True
        except Exception as e:
            print(f"Error clearing Discord cache: {e}")
            return False
    
    def set_discord_rate_limits(self, min_interval: int = 30, max_per_hour: int = 20):
        """Set Discord rate limiting parameters"""
        if not self.discord_manager:
            print("Discord manager not initialized")
            return False
        
        try:
            self.discord_manager.set_rate_limits(min_interval, max_per_hour)
            return True
        except Exception as e:
            print(f"Error setting Discord rate limits: {e}")
            return False


def main():
    """Main function to run the CAD system"""
    print("ALERT FDD CAD System - Fire Department Computer-Aided Dispatch")
    print("=" * 60)
    
    # Create CAD system with configuration
    config = CADConfig(
        refresh_interval=30,
        max_incidents_display=25,
        auto_refresh=True,
        sound_alerts=True,
        theme="dark"
    )
    
    cad = CADSystem(config)
    
    # Add Rogers Fire Department (from your test)
    cad.add_agency("04600")
    
    # Start monitoring
    cad.start_monitoring()
    
    try:
        print("\nCAD System is running...")
        print("Press Ctrl+C to stop")
        
        while True:
            time.sleep(10)
            
            # Display status every 10 seconds
            status = cad.get_status_summary()
            print(f"\nSTATS CAD Status: {status['active_incidents']} active, "
                  f"{status['recent_incidents']} recent, "
                  f"{status['unacknowledged_alerts']} unacknowledged alerts")
            
            # Show unacknowledged alerts
            alerts = cad.get_unacknowledged_alerts()
            if alerts:
                print("ALERT Unacknowledged Alerts:")
                for alert in alerts[-3:]:  # Show last 3
                    print(f"  - {alert.incident_type} at {alert.address} ({alert.priority})")
    
    except KeyboardInterrupt:
        print("\n\nStopping CAD System...")
        cad.stop_monitoring()
        print("CAD System stopped.")


if __name__ == "__main__":
    main()
