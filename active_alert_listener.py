#!/usr/bin/env python3
"""
Simple Incident Monitor - Pushover Only
Monitors PulsePoint for new incidents and sends Pushover notifications only.
No web interface, no Discord, just simple incident monitoring.
Runs 24/7 with automatic error recovery and watchdog monitoring.
"""

import json
import math
import requests
import time
import datetime
import threading
import traceback
import os
from typing import Set, List, Dict, Any, Optional, Tuple
from fdd_cad_scraper import FDDCADScraper, Incident

# Prefer env vars so keys are not committed; fallbacks keep local dev working
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY", "u91gdp1wbvynt5wmiec45tsf79e6t5")
PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN", "agunhyfhpg9rik3dr5uedi51vyotaw")
PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
# Min seconds between full HTML map rewrites (JSON always updates; reduces I/O bursts)
MAP_FULL_REGEN_MIN_SEC = float(os.getenv("MAP_FULL_REGEN_MIN_SEC", "20"))

# Active Alert webhook (set via environment variable if available)
ACTIVE_ALERT_WEBHOOK_URL = os.getenv("ACTIVE_ALERT_WEBHOOK_URL", "http://localhost:7000/active-alert/webhook")

# Monitoring Configuration
AGENCY_ID = "04600"  # Rogers Fire Department
SPRINGDALE_AGENCY_ID = "00067"  # Springdale Fire Department (PulsePoint)
AGENCY_IDS = [AGENCY_ID, SPRINGDALE_AGENCY_ID]  # Rogers + Springdale
CHECK_INTERVAL = 0  # Check continuously (no delay)

# Hotspot map: history file and max points to keep
HOTSPOT_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "incident_hotspots.json")
HOTSPOT_MAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "incident_hotspot_map.html")
HOTSPOT_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "incident_hotspot_data.json")
HOTSPOT_MAX_POINTS = 2000  # 10x more history for richer heat and trends
# Time decay: half-life in days (recent incidents weigh more)
HOTSPOT_HALF_LIFE_DAYS = 10
# Dedupe: ignore same location+type within this many seconds (avoid double-counting)
HOTSPOT_DEDUPE_SECONDS = 300
# Incident type weights for hotspot score (higher = hotter in heat layer / ranking)
TYPE_WEIGHTS = {
    "Fire": 1.9,
    "Structure Fire": 2.0,
    "Vehicle Fire": 1.6,
    "Medical": 1.3,
    "EMS": 1.3,
    "Rescue": 1.5,
    "Hazmat": 1.7,
    "Gas Leak": 1.6,
    "MVC": 1.25,
    "Vehicle Accident": 1.25,
    "Alarm": 1.0,
    "Lockout": 0.5,
    "Public Service": 0.6,
    "Carbon Monoxide": 1.6,
    "Smoke Investigation": 1.5,
    "Water Rescue": 1.5,
    "Unknown": 1.0,
}
# Clustering: grid step in degrees (~0.003 ≈ 330m). Set to None to use DBSCAN only.
HOTSPOT_GRID_DEG = 0.003
# DBSCAN: max distance (km) for points in same cluster. Used if grid is None or for hybrid.
HOTSPOT_DBSCAN_EPS_KM = 0.35
# Min points to form a DBSCAN cluster
HOTSPOT_DBSCAN_MIN_SAMPLES = 2
# Heat layer: default radius (px) and blur for Leaflet heat
HOTSPOT_HEAT_RADIUS = 45
HOTSPOT_HEAT_BLUR = 35
# Group by normalized address first (same address = one hotspot)
HOTSPOT_GROUP_BY_ADDRESS = True

# Rogers fire stations for hotspot map (lat, lng, name). Geocoded from official addresses.
STATION_LOCATIONS = [
    (36.334596, -94.115642, "Rogers Fire Department — 201 N 1st St"),
    (36.370200, -94.104200, "Rogers Fire Station #3 — Airport (Carter Field / 3615 W Etris Dr)"),
    (36.341235, -94.154132, "Rogers Fire Station #4 — 2424 W Olive St"),
    (36.280384, -94.170590, "Rogers Fire Station #6 — 5801 S Bellview Rd"),
    (36.294700, -94.118000, "Rogers Fire Station #7 — 3400 S 1st St"),
]
# Radius (mi) to consider a cluster "in" a station's area for "calls by station" totals. Cluster assigned to nearest station.
STATION_ZONE_RADIUS_MI = 6
# Clusters farther than this from every station are "under-served" (coverage gap).
STATION_UNDERSERVED_RADIUS_MI = 10

# Code3Chasers / chaser: your location, radius, and response-time rules.
CHASER_CONFIG = {
    "lat": 36.2731803358098,
    "lng": -94.16901029090904,
    "radius_miles": 15,
    "name": "Code3Chasers",
    "address": "6113 S 37th St, Rogers, AR 72758",
    "avg_speed_mph": 35,
    "eta_factor": 1.4,
    "response_window_min": 20,   # calls often still active this long — "make it in time" if you arrive before this
    "close_enough_mi": 6,        # under this distance = "close enough — go"
    "make_it_eta_max": 14,       # max drive time (min) to say "you'll make it in time"
}

# Spotter / fire-spotter coverage zones (AI coverage areas). Who covers which area.
# Code3Chasers: Rogers + Lowell. NWA Emergency Vehicles: Springdale + Lowell (shared).
SPOTTER_COVERAGE_ZONES = [
    {"zone": "Rogers", "lat": 36.333, "lng": -94.126, "radius_mi": 6, "spotters": ["Code3Chasers"], "color": "#22c55e"},
    {"zone": "Springdale", "lat": 36.187, "lng": -94.129, "radius_mi": 6, "spotters": ["NWA Emergency Vehicles"], "color": "#3b82f6"},
    {"zone": "Lowell", "lat": 36.255, "lng": -94.128, "radius_mi": 4, "spotters": ["Code3Chasers", "NWA Emergency Vehicles"], "color": "#eab308"},
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two points in km (WGS84)."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_iso_to_utc_timestamp(iso: str) -> Optional[float]:
    """Parse ISO datetime to UTC timestamp (seconds since epoch), or None."""
    if not iso or not isinstance(iso, str):
        return None
    try:
        s = iso.strip()
        if s and not s.endswith("Z") and "+" not in s:
            s = s + "Z"
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None) - (dt.utcoffset() or datetime.timedelta(0))
        return dt.timestamp()
    except Exception:
        return None


def _time_decay_weight(received_at_iso: str, half_life_days: float) -> float:
    """Weight for recency: 0.5^(days_ago / half_life). Older = smaller weight."""
    try:
        s = (received_at_iso or "").strip()
        if not s:
            return 1.0
        if not s.endswith("Z") and "+" not in s:
            s = s + "Z"
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None) - dt.utcoffset() if dt.utcoffset() else dt.replace(tzinfo=None)
        now = datetime.datetime.utcnow()
        days_ago = max(0.0, (now - dt).total_seconds() / 86400.0)
        return 0.5 ** (days_ago / max(0.01, half_life_days))
    except Exception:
        return 1.0


class SimpleIncidentMonitor:
    """Simple monitor that only sends Pushover notifications for new incidents"""
    
    def __init__(self, agency_ids: Optional[List[str]] = None):
        if agency_ids is None:
            agency_ids = [AGENCY_ID]
        self.agency_ids = [agency_ids] if isinstance(agency_ids, str) else list(agency_ids)
        self.scraper = FDDCADScraper()
        self.sent_incident_ids: Set[int] = set()
        self.running = True
        self.monitor_thread = None
        self.watchdog_thread = None
        self.last_successful_check = None
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10
        self.hotspot_history: List[dict] = []
        self._history_lock = threading.Lock()
        self._http = requests.Session()
        self._http.headers.update({"User-Agent": "NWA-IncidentMonitor/2.1"})
        self._last_full_map_ts = 0.0
        self._map_regen_due = False
        self._load_hotspot_history()

    def _flush_deferred_map(self) -> None:
        """Write full HTML map if debounced regen was skipped."""
        if not self._map_regen_due:
            return
        if time.time() - self._last_full_map_ts < MAP_FULL_REGEN_MIN_SEC:
            return
        self._map_regen_due = False
        try:
            pl = self._compute_hotspot_payload()
            self.generate_hotspot_map(payload=pl)
            self._last_full_map_ts = time.time()
            print("[HOTSPOT] Deferred full map HTML written")
        except Exception as e:
            print(f"[HOTSPOT] Deferred map failed: {e}")

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
                            break
                
        except Exception as e:
            print(f"[WARNING] Error parsing address: {e}")
        
        return details
    
    def send_pushover_notification(self, incident: Incident) -> bool:
        """Send a Pushover notification for an incident"""
        try:
            # ALL incidents sent as CRITICAL to phone for maximum visibility
            pushover_priority = 2  # Emergency priority (CRITICAL)
            pushover_sound = "siren"  # Emergency sound
            
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
                    print(f"[WARNING] Error extracting units for Pushover: {e}")
                    units_text = "Units assigned"
            
            # Create professional title and message - ALL incidents shown as CRITICAL for phone
            title = f"FIRE DEPARTMENT DISPATCH - CRITICAL ALERT"
            
            # Parse address details
            address_details = self._parse_address_details(incident.FullDisplayAddress)
            
            # Format time with date
            call_time = incident.CallReceivedDateTime
            if call_time and call_time != datetime.datetime(year=1990, month=1, day=1):
                call_time_str = call_time.strftime('%I:%M %p')
                call_date = call_time.strftime('%m/%d/%Y')
                call_datetime = call_time
            else:
                now = datetime.datetime.now()
                call_time_str = now.strftime('%I:%M %p')
                call_date = now.strftime('%m/%d/%Y')
                call_datetime = now
            
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
            
            # Add street number if available
            if hasattr(incident, 'StreetNumber') and incident.StreetNumber:
                message_parts.append(f"Street Number: {incident.StreetNumber}")
            
            # Add significant locations/landmarks if available
            if hasattr(incident, 'significant_locations') and incident.significant_locations:
                if isinstance(incident.significant_locations, list) and len(incident.significant_locations) > 0:
                    landmarks = ", ".join(incident.significant_locations)
                    message_parts.append(f"Nearby Landmarks: {landmarks}")
            
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
            message_parts.append(f"Call Received: {call_time_str} on {call_date}")
            
            # Add incident age/duration if available
            try:
                incident_age = (datetime.datetime.now() - call_datetime).total_seconds() / 60  # minutes
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
            
            # Send to Pushover
            data = {
                'token': PUSHOVER_APP_TOKEN,
                'user': PUSHOVER_USER_KEY,
                'title': title,
                'message': message,
                'priority': pushover_priority,
                'sound': pushover_sound
            }
            
            # Emergency priority requires expire and retry
            data['expire'] = 3600  # Expire after 1 hour
            data['retry'] = 30     # Retry every 30 seconds
            
            response = self._http.post(PUSHOVER_API_URL, data=data, timeout=12)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 1:
                    print(f"[✓] Pushover notification sent: {incident.incident_type} at {incident.FullDisplayAddress}")
                    return True
                else:
                    print(f"[✗] Pushover failed: {result.get('errors', 'Unknown error')}")
                    return False
            else:
                print(f"[✗] Pushover failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"[ERROR] Error sending Pushover notification: {e}")
            import traceback
            traceback.print_exc()
            return False

    def send_active_alert_webhook(self, incident: Incident) -> bool:
        """Forward incident to Active Alert webhook endpoint."""
        if not ACTIVE_ALERT_WEBHOOK_URL:
            print("[ACTIVE ALERT] Skipping; webhook URL not configured")
            return False

        payload = {
            "id": incident.ID,
            "type": getattr(incident, "incident_type", ""),
            "address": getattr(incident, "FullDisplayAddress", ""),
            "received_at": (
                incident.CallReceivedDateTime.isoformat()
                if getattr(incident, "CallReceivedDateTime", None)
                else datetime.datetime.utcnow().isoformat()
            ),
            "units": [
                getattr(unit, "UnitID", str(unit))
                for unit in getattr(incident, "Unit", []) or []
            ],
        }

        try:
            response = self._http.post(
                ACTIVE_ALERT_WEBHOOK_URL,
                json=payload,
                timeout=12,
            )
            if response.status_code // 100 == 2:
                print(f"[ACTIVE ALERT] Sent incident {incident.ID} to webhook")
                return True
            print(
                f"[ACTIVE ALERT] Failed for incident {incident.ID}: HTTP {response.status_code}"
            )
            return False
        except Exception as error:
            print(f"[ACTIVE ALERT] Error sending incident {incident.ID}: {error}")
            traceback.print_exc()
            return False

    def _load_hotspot_history(self) -> None:
        """Load incident locations from disk for hotspot map."""
        if not os.path.isfile(HOTSPOT_HISTORY_FILE):
            return
        try:
            with open(HOTSPOT_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._history_lock:
                self.hotspot_history = data.get("incidents", [])[-HOTSPOT_MAX_POINTS:]
        except Exception as e:
            print(f"[HOTSPOT] Could not load history: {e}")

    def _save_hotspot_history(self) -> None:
        """Persist hotspot history to disk."""
        try:
            with self._history_lock:
                snap = list(self.hotspot_history)
            with open(HOTSPOT_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump({"incidents": snap}, f, indent=0)
        except Exception as e:
            print(f"[HOTSPOT] Could not save history: {e}")

    def _append_hotspot(self, incident: Incident) -> None:
        """Record incident location for hotspot map (if lat/lng available). Dedupe same location+type within HOTSPOT_DEDUPE_SECONDS."""
        lat = getattr(incident, "Latitude", None)
        lng = getattr(incident, "Longitude", None)
        if lat is None or lng is None:
            return
        inc_type = getattr(incident, "incident_type", "") or ""
        try:
            received = getattr(incident, "CallReceivedDateTime", None)
            if received:
                if received.tzinfo is None:
                    received_str = received.isoformat() + "Z"
                else:
                    received_str = received.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
            else:
                received_str = datetime.datetime.utcnow().isoformat().replace("+00:00", "") + "Z"
        except Exception:
            received_str = datetime.datetime.utcnow().isoformat().replace("+00:00", "") + "Z"
        ts = _parse_iso_to_utc_timestamp(received_str)
        cutoff = (ts or 0) - HOTSPOT_DEDUPE_SECONDS
        agency = ""
        if hasattr(incident, "Agency") and incident.Agency:
            agency = str(incident.Agency).strip()[:80]
        with self._history_lock:
            for p in reversed(self.hotspot_history):
                if p.get("lat") is None or p.get("lng") is None:
                    continue
                if abs(float(p["lat"]) - float(lat)) < 1e-5 and abs(float(p["lng"]) - float(lng)) < 1e-5:
                    if (p.get("type") or "").strip() == inc_type.strip():
                        pt = _parse_iso_to_utc_timestamp(p.get("received_at") or "")
                        if pt is not None and pt >= cutoff:
                            return
                if ts and (p.get("received_at") or ""):
                    pt = _parse_iso_to_utc_timestamp(p.get("received_at") or "")
                    if pt is not None and pt < cutoff:
                        break
            self.hotspot_history.append({
                "lat": float(lat),
                "lng": float(lng),
                "type": inc_type,
                "address": getattr(incident, "FullDisplayAddress", ""),
                "received_at": received_str,
                "id": getattr(incident, "ID", None),
                "agency": agency,
            })
            if len(self.hotspot_history) > HOTSPOT_MAX_POINTS:
                self.hotspot_history = self.hotspot_history[-HOTSPOT_MAX_POINTS:]
        self._save_hotspot_history()

    def _cluster_hotspots_by_area(self, grid_deg: float = None):
        """Group incidents into area grid cells. Same/similar location = one cell with higher count."""
        grid_deg = grid_deg if grid_deg is not None else (HOTSPOT_GRID_DEG or 0.003)
        cells = {}
        for p in self.hotspot_history:
            lat, lng = float(p["lat"]), float(p["lng"])
            key = (round(lat / grid_deg) * grid_deg, round(lng / grid_deg) * grid_deg)
            if key not in cells:
                cells[key] = {"lat": key[0] + grid_deg / 2, "lng": key[1] + grid_deg / 2, "count": 0, "incidents": []}
            cells[key]["count"] += 1
            cells[key]["incidents"].append(p)
        return list(cells.values())

    @staticmethod
    def _normalize_address(addr: str) -> str:
        """Normalize address for grouping (same place = same key)."""
        if not addr or not isinstance(addr, str):
            return ""
        import re
        s = addr.strip().upper()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r",\s*", ",", s)
        s = re.sub(r"\b(NORTH|N|SOUTH|S|EAST|E|WEST|W)\b", lambda m: {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}.get(m.group(1), m.group(1)[0]), s)
        return s[:120]

    def _cluster_by_address(self) -> List[dict]:
        """Group incidents by normalized address; centroid = mean lat/lng for that address."""
        by_addr: Dict[str, dict] = {}
        for p in self.hotspot_history:
            addr = (p.get("address") or "").strip() or (f"{p['lat']:.5f},{p['lng']:.5f}")
            key = self._normalize_address(addr)
            if not key:
                key = f"{float(p['lat']):.5f},{float(p['lng']):.5f}"
            if key not in by_addr:
                by_addr[key] = {"lat": 0.0, "lng": 0.0, "count": 0, "incidents": [], "address": addr}
            by_addr[key]["count"] += 1
            by_addr[key]["incidents"].append(p)
            by_addr[key]["lat"] += float(p["lat"])
            by_addr[key]["lng"] += float(p["lng"])
        out = []
        for v in by_addr.values():
            n = v["count"]
            v["lat"] = v["lat"] / n
            v["lng"] = v["lng"] / n
            out.append(v)
        return out

    def _cluster_hotspots_dbscan(self, eps_km: float = None, min_samples: int = None) -> List[dict]:
        """Distance-based clustering: merge points within eps_km; min_samples to keep a cluster."""
        eps_km = eps_km if eps_km is not None else HOTSPOT_DBSCAN_EPS_KM
        min_samples = min_samples if min_samples is not None else HOTSPOT_DBSCAN_MIN_SAMPLES
        points = [
            (float(p["lat"]), float(p["lng"]), p)
            for p in self.hotspot_history
        ]
        if not points:
            return []
        clusters: List[dict] = []
        used = [False] * len(points)

        for i, (lat, lng, p) in enumerate(points):
            if used[i]:
                continue
            group = [p]
            used[i] = True
            stack = [(lat, lng)]
            while stack:
                cx, cy = stack.pop()
                for j, (lat2, lng2, p2) in enumerate(points):
                    if used[j]:
                        continue
                    if _haversine_km(cx, cy, lat2, lng2) <= eps_km:
                        used[j] = True
                        group.append(p2)
                        stack.append((lat2, lng2))
            if len(group) >= min_samples or not clusters:
                mean_lat = sum(float(x["lat"]) for x in group) / len(group)
                mean_lng = sum(float(x["lng"]) for x in group) / len(group)
                clusters.append({"lat": mean_lat, "lng": mean_lng, "count": len(group), "incidents": group})
            else:
                for p2 in group:
                    best = None
                    best_d = float("inf")
                    for c in clusters:
                        d = _haversine_km(c["lat"], c["lng"], float(p2["lat"]), float(p2["lng"]))
                        if d < best_d:
                            best_d, best = d, c
                    if best is not None and best_d <= eps_km:
                        best["incidents"].append(p2)
                        best["count"] += 1
                        best["lat"] = sum(float(x["lat"]) for x in best["incidents"]) / best["count"]
                        best["lng"] = sum(float(x["lng"]) for x in best["incidents"]) / best["count"]
                    else:
                        clusters.append({"lat": float(p2["lat"]), "lng": float(p2["lng"]), "count": 1, "incidents": [p2]})
        return clusters

    def _cluster_hotspots_adaptive(self) -> List[dict]:
        """Cluster using address grouping (if enabled) then grid or DBSCAN. Returns list of cluster dicts."""
        if HOTSPOT_GROUP_BY_ADDRESS and self.hotspot_history:
            base = self._cluster_by_address()
            if not HOTSPOT_GRID_DEG:
                merged = self._merge_clusters_by_distance(base, HOTSPOT_DBSCAN_EPS_KM)
                return merged
            grid_deg = HOTSPOT_GRID_DEG
            cells = {}
            for c in base:
                lat, lng = c["lat"], c["lng"]
                key = (round(lat / grid_deg) * grid_deg, round(lng / grid_deg) * grid_deg)
                if key not in cells:
                    cells[key] = {"lat": key[0] + grid_deg / 2, "lng": key[1] + grid_deg / 2, "count": 0, "incidents": []}
                cells[key]["count"] += c["count"]
                cells[key]["incidents"].extend(c["incidents"])
            return list(cells.values())
        if HOTSPOT_GRID_DEG:
            return self._cluster_hotspots_by_area(HOTSPOT_GRID_DEG)
        return self._cluster_hotspots_dbscan()

    def _merge_clusters_by_distance(self, clusters: List[dict], eps_km: float) -> List[dict]:
        """Merge clusters whose centroids are within eps_km."""
        if not clusters or eps_km <= 0:
            return clusters
        merged: List[dict] = []
        for c in clusters:
            lat, lng = c["lat"], c["lng"]
            found = False
            for m in merged:
                if _haversine_km(m["lat"], m["lng"], lat, lng) <= eps_km:
                    n = m["count"] + c["count"]
                    m["lat"] = (m["lat"] * m["count"] + lat * c["count"]) / n
                    m["lng"] = (m["lng"] * m["count"] + lng * c["count"]) / n
                    m["count"] = n
                    m["incidents"].extend(c["incidents"])
                    found = True
                    break
            if not found:
                merged.append({"lat": lat, "lng": lng, "count": c["count"], "incidents": list(c["incidents"])})
        return merged

    def _compute_cluster_weights(self, clusters: List[dict]) -> None:
        """In-place: add weighted_score, trend (last_24h, previous_24h), quality, tier, last_24h_score, last_7d_score."""
        now_utc = datetime.datetime.utcnow()
        now_ts = now_utc.timestamp()
        half_life = max(0.01, HOTSPOT_HALF_LIFE_DAYS)
        cutoff_24h = now_ts - 86400
        cutoff_48h = now_ts - 172800
        cutoff_7d = now_ts - 7 * 86400

        for c in clusters:
            total_weight = 0.0
            last_24h = 0
            previous_24h = 0
            score_24h = 0.0
            score_7d = 0.0
            for i in c.get("incidents", []):
                w_time = _time_decay_weight(i.get("received_at") or "", half_life)
                inc_type = (i.get("type") or "Unknown").strip()
                w_type = TYPE_WEIGHTS.get(inc_type, TYPE_WEIGHTS.get("Unknown", 1.0))
                total_weight += w_time * w_type
                ts = _parse_iso_to_utc_timestamp(i.get("received_at") or "")
                if ts is not None:
                    if ts >= cutoff_24h:
                        last_24h += 1
                        score_24h += w_type * _time_decay_weight(i.get("received_at") or "", 0.5)
                    elif cutoff_48h <= ts < cutoff_24h:
                        previous_24h += 1
                    if ts >= cutoff_7d:
                        score_7d += w_type * _time_decay_weight(i.get("received_at") or "", 2.0)
            c["weighted_score"] = round(total_weight, 2)
            c["count"] = len(c.get("incidents", []))
            c["last_24h"] = last_24h
            c["previous_24h"] = previous_24h
            c["last_24h_score"] = round(score_24h, 2)
            c["last_7d_score"] = round(score_7d, 2)
            if c["count"] >= 5 and (last_24h >= 2 or total_weight >= 5):
                c["quality"] = "strong"
            elif c["count"] >= 2 or last_24h >= 1:
                c["quality"] = "medium"
            else:
                c["quality"] = "weak"
            # Tier for UI: critical = very recent + high type weight; high/medium/low by score
            newest_ts = max(
                (_parse_iso_to_utc_timestamp(i.get("received_at") or "") or 0.0)
                for i in c.get("incidents", [])
            ) if c.get("incidents") else 0
            mins_ago = (now_ts - newest_ts) / 60.0 if newest_ts else 9999
            if mins_ago <= 30 and total_weight >= 2:
                c["tier"] = "critical"
            elif total_weight >= 8 or (last_24h >= 3 and total_weight >= 4):
                c["tier"] = "high"
            elif total_weight >= 3 or last_24h >= 1:
                c["tier"] = "medium"
            else:
                c["tier"] = "low"

    def _station_rankings(self, clusters: List[dict], within_hours: Optional[float] = None) -> List[dict]:
        """Rank stations by total weighted activity in their zone. If within_hours set, only count incidents in that window."""
        radius_km = STATION_ZONE_RADIUS_MI * 1.60934
        now_ts = datetime.datetime.utcnow().timestamp()
        cutoff_ts = (now_ts - within_hours * 3600) if within_hours else 0.0

        result = []
        for lat_s, lng_s, name in STATION_LOCATIONS:
            total_count = 0
            total_weight = 0.0
            for c in clusters:
                d_km = _haversine_km(lat_s, lng_s, c["lat"], c["lng"])
                if d_km > radius_km:
                    continue
                if within_hours and cutoff_ts > 0:
                    recent = sum(1 for i in c.get("incidents", []) if (_parse_iso_to_utc_timestamp(i.get("received_at") or "") or 0) >= cutoff_ts)
                    w = sum(
                        (_time_decay_weight(i.get("received_at") or "", 1.0) * TYPE_WEIGHTS.get((i.get("type") or "Unknown").strip(), 1.0)
                         for i in c.get("incidents", []) if (_parse_iso_to_utc_timestamp(i.get("received_at") or "") or 0) >= cutoff_ts)
                    )
                    total_count += recent
                    total_weight += round(w, 2)
                else:
                    total_count += c.get("count", 0)
                    total_weight += c.get("weighted_score", c.get("count", 0))
            result.append({"name": name, "count": total_count, "weighted_score": round(total_weight, 2)})
        result.sort(key=lambda x: (-x["weighted_score"], -x["count"]))
        for i, r in enumerate(result):
            r["rank"] = i + 1
        return result

    def _hot_streets(self, incidents: List[dict], top_n: int = 15) -> List[dict]:
        """Group incidents by street (first segment of address before comma). Return top streets with count and centroid."""
        import re
        by_street: Dict[str, dict] = {}
        for i in incidents:
            addr = (i.get("address") or "").strip()
            street = (addr.split(",")[0].strip() if "," in addr else addr) or "Unknown"
            street = re.sub(r"^\d+\s+", "", street)[:80]
            if not street:
                street = "Unknown"
            if street not in by_street:
                by_street[street] = {"street": street, "count": 0, "lat": 0.0, "lng": 0.0, "incidents": []}
            by_street[street]["count"] += 1
            by_street[street]["lat"] += float(i.get("lat", 0))
            by_street[street]["lng"] += float(i.get("lng", 0))
            by_street[street]["incidents"].append(i)
        for v in by_street.values():
            n = v["count"]
            v["lat"] = v["lat"] / n
            v["lng"] = v["lng"] / n
        out = sorted(by_street.values(), key=lambda x: (-x["count"], x["street"]))[:top_n]
        for o in out:
            del o["incidents"]
        return out

    def _under_served_clusters(self, clusters: List[dict]) -> List[dict]:
        """Clusters whose centroid is farther than STATION_UNDERSERVED_RADIUS_MI from every station. Include closest station name and distance."""
        radius_km = STATION_UNDERSERVED_RADIUS_MI * 1.60934
        out = []
        for c in clusters:
            best_mi = float("inf")
            best_name = ""
            for s in STATION_LOCATIONS:
                d_km = _haversine_km(s[0], s[1], c["lat"], c["lng"])
                d_mi = d_km / 1.60934
                if d_mi < best_mi:
                    best_mi = d_mi
                    best_name = s[2] if len(s) > 2 else ""
            if best_mi > (STATION_UNDERSERVED_RADIUS_MI):
                c_copy = {k: v for k, v in c.items() if k != "incidents"}
                c_copy["min_station_km"] = round(best_mi * 1.60934, 2)
                c_copy["min_station_mi"] = round(best_mi, 2)
                c_copy["closest_station_name"] = best_name
                c_copy["closest_station_mi"] = round(best_mi, 2)
                out.append(c_copy)
        return out[:20]

    def _staging_suggestion(self, likely_next: List[dict], top_n: int = 3) -> Optional[dict]:
        """Suggested single point to cover top likely-next areas (weighted centroid)."""
        if not likely_next:
            return None
        top = likely_next[:top_n]
        total_w = sum(c.get("likely_score", 1) for c in top)
        if total_w <= 0:
            return None
        lat = sum(c["lat"] * c.get("likely_score", 1) for c in top) / total_w
        lng = sum(c["lng"] * c.get("likely_score", 1) for c in top) / total_w
        return {"lat": round(lat, 5), "lng": round(lng, 5), "label": "Suggested stage (covers top likely-next)"}

    def _station_trend(self, rankings_all: List[dict], rankings_7d: List[dict]) -> List[dict]:
        """Per-station: current rank vs rank in last 7d (for 'moved from #X to #Y')."""
        by_name_all = {r["name"]: r["rank"] for r in rankings_all}
        by_name_7d = {r["name"]: r["rank"] for r in rankings_7d}
        out = []
        for r in rankings_all:
            name = r["name"]
            rank_now = r["rank"]
            rank_7d = by_name_7d.get(name)
            if rank_7d is None:
                trend = "new"
            elif rank_7d > rank_now:
                trend = "up"
            elif rank_7d < rank_now:
                trend = "down"
            else:
                trend = "same"
            out.append({**r, "rank_7d": rank_7d, "trend": trend})
        return out

    def _likely_next_areas(self, clusters: List[dict], top_n: int = 5) -> List[dict]:
        """Score areas by recency + time-of-day/day-of-week alignment and recent trend (last 48h vs baseline)."""
        utc = datetime.timezone.utc
        now = datetime.datetime.now(utc)
        recent_cutoff_48h = now - datetime.timedelta(hours=48)
        recent_cutoff_7d = now - datetime.timedelta(days=7)
        current_hour = now.hour
        current_dow = now.weekday()

        def parse_iso(iso: str) -> Optional[datetime.datetime]:
            if not iso:
                return None
            try:
                s = (iso or "").strip()
                if s and not s.endswith("Z") and "+" not in s:
                    s = s + "Z"
                dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=utc)
                return dt
            except Exception:
                return None

        def dt_naive_utc(dt: datetime.datetime) -> datetime.datetime:
            """Normalize to naive UTC for hour/dow (for baseline counts)."""
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None) - (dt.utcoffset() or datetime.timedelta(0))
            return dt

        hour_dow_counts: Dict[Tuple[int, int], int] = {}
        for p in self.hotspot_history:
            dt = parse_iso(p.get("received_at") or "")
            if dt:
                key = (dt_naive_utc(dt).hour, dt_naive_utc(dt).weekday())
                hour_dow_counts[key] = hour_dow_counts.get(key, 0) + 1
        baseline = hour_dow_counts.get((current_hour, current_dow), 0) + 1

        scored = []
        for c in clusters:
            incidents = c.get("incidents", [])
            recent_48 = [i for i in incidents if parse_iso(i.get("received_at")) and parse_iso(i.get("received_at")) >= recent_cutoff_48h]
            recent_7d = [i for i in incidents if parse_iso(i.get("received_at")) and parse_iso(i.get("received_at")) >= recent_cutoff_7d]
            score_recent = len(recent_48) * 2.0 + len(recent_7d) * 0.5
            same_hour_dow = sum(
                1
                for i in incidents
                if (lambda t: t and dt_naive_utc(t).hour == current_hour and dt_naive_utc(t).weekday() == current_dow)(parse_iso(i.get("received_at")))
            )
            score_temporal = (same_hour_dow + 1) / (baseline + 1)
            weighted = c.get("weighted_score", c.get("count", 0))
            score = score_recent + score_temporal * (weighted * 0.1)
            scored.append({**c, "likely_score": round(score, 2), "recent_48h": len(recent_48), "recent_7d": len(recent_7d)})
        scored.sort(key=lambda x: (-x["likely_score"], -x["weighted_score"]))
        top = scored[:top_n]
        scores = [x["likely_score"] for x in top]
        max_s = max(scores) if scores else 0
        for i, item in enumerate(top):
            s = item["likely_score"]
            if max_s and s >= max_s * 0.8:
                item["confidence"] = "high"
            elif max_s and s >= max_s * 0.4:
                item["confidence"] = "medium"
            else:
                item["confidence"] = "low"
        return top

    def _clusters_filtered_by_hours(self, clusters: List[dict], hours: float) -> List[dict]:
        """Return clusters containing only incidents from the last `hours` (shallow copy with filtered incidents)."""
        now_ts = datetime.datetime.utcnow().timestamp()
        cutoff = now_ts - hours * 3600
        out = []
        for c in clusters:
            incs = [i for i in c.get("incidents", []) if (_parse_iso_to_utc_timestamp(i.get("received_at") or "") or 0) >= cutoff]
            if not incs:
                continue
            lat = sum(float(i.get("lat", 0)) for i in incs) / len(incs)
            lng = sum(float(i.get("lng", 0)) for i in incs) / len(incs)
            w = sum(
                _time_decay_weight(i.get("received_at") or "", 1.0) * TYPE_WEIGHTS.get((i.get("type") or "Unknown").strip(), 1.0)
                for i in incs
            )
            out.append({"lat": lat, "lng": lng, "count": len(incs), "weighted_score": round(w, 2), "incidents": incs})
        return out

    def _baseline_calls_this_hour_dow(self) -> int:
        """Total calls in history that fall on current hour and day-of-week (for 'busier than usual')."""
        utc = datetime.timezone.utc
        now = datetime.datetime.now(utc)
        h, dow = now.hour, now.weekday()
        count = 0
        for p in self.hotspot_history:
            ts = _parse_iso_to_utc_timestamp(p.get("received_at") or "")
            if ts is None:
                continue
            dt = datetime.datetime.fromtimestamp(ts, tz=utc)
            if dt.hour == h and dt.weekday() == dow:
                count += 1
        return count

    def _local_tz(self):
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo("America/Chicago")
        except Exception:
            return datetime.timezone.utc

    def _compute_insights(self) -> Dict[str, Any]:
        """Velocity, peak hours (Central), repeat addresses, agency mix, night share."""
        now_ts = datetime.datetime.utcnow().timestamp()
        cut_24 = now_ts - 86400
        cut_48 = now_ts - 172800
        cut_7d = now_ts - 7 * 86400
        cut_14d = now_ts - 14 * 86400
        c_24 = c_prev = c_7d = w0 = w1 = 0
        hour_counts = [0] * 24
        dow_counts = [0] * 7
        addr_counts: Dict[str, int] = {}
        agency_counts: Dict[str, int] = {}
        night = day = 0  # night 22-06 local
        tz = self._local_tz()
        for p in self.hotspot_history:
            ts = _parse_iso_to_utc_timestamp(p.get("received_at") or "")
            if ts is None:
                continue
            if ts >= cut_24:
                c_24 += 1
            elif cut_48 <= ts < cut_24:
                c_prev += 1
            if ts >= cut_7d:
                c_7d += 1
            if cut_7d <= ts < now_ts:
                w0 += 1
            elif cut_14d <= ts < cut_7d:
                w1 += 1
            try:
                dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).astimezone(tz)
                hour_counts[dt.hour] += 1
                dow_counts[dt.weekday()] += 1
                if 22 <= dt.hour or dt.hour < 6:
                    night += 1
                else:
                    day += 1
            except Exception:
                pass
            addr = (p.get("address") or "").strip()
            if len(addr) > 5:
                addr_counts[addr] = addr_counts.get(addr, 0) + 1
            ag = (p.get("agency") or "").strip()
            if ag:
                agency_counts[ag] = agency_counts.get(ag, 0) + 1
        peak_h = max(range(24), key=lambda h: hour_counts[h]) if self.hotspot_history else 0
        best_2h = (0, 0)
        for h in range(24):
            s = hour_counts[h] + hour_counts[(h + 1) % 24]
            if s > best_2h[0]:
                best_2h = (s, h)
        hr_labels = ["12a", "1a", "2a", "3a", "4a", "5a", "6a", "7a", "8a", "9a", "10a", "11a", "12p", "1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p", "9p", "10p", "11p"]
        w_start = best_2h[1]
        w_end = (w_start + 2) % 24
        window_label = f"{hr_labels[w_start]}–{hr_labels[w_end]} CT"
        vel = round(100.0 * (c_24 - c_prev) / max(c_prev, 1), 1) if c_prev else (100.0 if c_24 else 0.0)
        repeat_top = sorted(addr_counts.items(), key=lambda x: -x[1])[:10]
        repeat_top = [{"address": a, "count": n} for a, n in repeat_top if n >= 2][:8]
        agency_top = sorted(agency_counts.items(), key=lambda x: -x[1])[:6]
        agency_top = [{"name": n, "count": c} for n, c in agency_top]
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        peak_dow = max(range(7), key=lambda d: dow_counts[d]) if sum(dow_counts) else 0
        night_pct = round(100.0 * night / max(night + day, 1), 1)
        week_vel = round(100.0 * (w0 - w1) / max(w1, 1), 1) if w1 else (100.0 if w0 else 0.0)
        hl = []
        if c_24 >= 8:
            hl.append(f"Heavy day: {c_24} runs in 24h")
        elif c_24 >= 1:
            hl.append(f"{c_24} dispatch{'es' if c_24 != 1 else ''} last 24h")
        if vel >= 25:
            hl.append(f"↑{vel}% vs prior day")
        elif vel <= -25 and c_prev:
            hl.append(f"Quieter ({vel}%)")
        if week_vel >= 20 and w1:
            hl.append(f"Busy week (+{week_vel}% vs prior)")
        elif abs(week_vel) >= 15 and w1:
            hl.append(f"Week {week_vel:+.0f}% vs last week")
        if not hl:
            hl.append(f"{len(self.hotspot_history)} incidents on record · peak {hr_labels[peak_h]} CT")
        summary_headline = " · ".join(hl[:3])
        return {
            "calls_last_24h": c_24,
            "calls_prev_24h": c_prev,
            "calls_last_7d": c_7d,
            "calls_this_week": w0,
            "calls_prior_week": w1,
            "week_vs_prior_pct": week_vel,
            "velocity_vs_prior_24h_pct": vel,
            "summary_headline": summary_headline,
            "peak_hour_ct": peak_h,
            "peak_hour_label": hr_labels[peak_h] + " CT",
            "busiest_2h_window": window_label,
            "busiest_2h_count": best_2h[0],
            "busiest_day": day_names[peak_dow],
            "night_share_pct": night_pct,
            "repeat_hotspots": repeat_top,
            "agency_breakdown": agency_top,
        }

    def _point_heat_data(self, max_points: int = 1200) -> List[List[float]]:
        """Per-incident heat triples [lat, lng, intensity] for smooth point heat on map."""
        half_life = max(0.01, HOTSPOT_HALF_LIFE_DAYS)
        now_ts = datetime.datetime.utcnow().timestamp()
        out: List[List[float]] = []
        for p in self.hotspot_history[-max_points:]:
            try:
                ts = _parse_iso_to_utc_timestamp(p.get("received_at") or "")
                if ts is None:
                    ts = now_ts
                w = _time_decay_weight(p.get("received_at") or "", half_life)
                t = (p.get("type") or "Unknown").strip()
                w *= TYPE_WEIGHTS.get(t, 1.0)
                out.append([float(p["lat"]), float(p["lng"]), round(w, 3), int(ts * 1000), t])
            except Exception:
                continue
        return out

    def _compute_hotspot_payload(self) -> Dict[str, Any]:
        """Build full payload: clusters, station_rankings, likely_next, hot_streets, staging, trend, meta."""
        clusters = self._cluster_hotspots_adaptive()
        self._compute_cluster_weights(clusters)
        station_rankings = self._station_rankings(clusters)
        clusters_7d = self._clusters_filtered_by_hours(clusters, 7 * 24)
        station_rankings_7d = self._station_rankings(clusters_7d) if clusters_7d else []
        station_trend = self._station_trend(station_rankings, station_rankings_7d) if station_rankings_7d else station_rankings
        station_rankings_recent_4h = self._station_rankings(clusters, within_hours=4)
        station_rankings_1h = self._station_rankings(clusters, within_hours=1)
        likely_next = self._likely_next_areas(clusters, top_n=5)
        unique_types = sorted(
            set((i.get("type") or "Unknown") for c in clusters for i in c.get("incidents", [])),
            key=lambda t: t.upper(),
        )
        all_incidents_for_streets = []
        for c in clusters:
            for i in c.get("incidents", []):
                all_incidents_for_streets.append({**i, "lat": c["lat"], "lng": c["lng"]})
        hot_streets = self._hot_streets(all_incidents_for_streets, top_n=15)
        under_served = self._under_served_clusters(clusters)
        staging_suggestion = self._staging_suggestion(likely_next)
        if staging_suggestion and likely_next:
            staging_suggestion["confidence"] = (likely_next[0].get("confidence", "medium") if likely_next else "medium")
        baseline_hour_dow = self._baseline_calls_this_hour_dow()
        insights = self._compute_insights()
        point_heat = self._point_heat_data()
        return {
            "clusters": clusters,
            "station_rankings": station_rankings,
            "station_rankings_recent_4h": station_rankings_recent_4h,
            "station_rankings_1h": station_rankings_1h,
            "station_trend": station_trend,
            "likely_next": likely_next,
            "hot_streets": hot_streets,
            "under_served_clusters": under_served,
            "staging_suggestion": staging_suggestion,
            "meta": {
                "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
                "half_life_days": HOTSPOT_HALF_LIFE_DAYS,
                "type_weights": TYPE_WEIGHTS,
                "total_incidents": len(self.hotspot_history),
                "baseline_calls_this_hour_dow": baseline_hour_dow,
                "heat_radius": HOTSPOT_HEAT_RADIUS,
                "heat_blur": HOTSPOT_HEAT_BLUR,
                "summary_headline": (insights.get("summary_headline") or "")[:200],
            },
            "unique_types": unique_types,
            "insights": insights,
            "point_heat": point_heat,
        }

    def _save_hotspot_data_json(self, payload: Dict[str, Any]) -> None:
        """Write incident_hotspot_data.json for live map refresh."""
        try:
            with open(HOTSPOT_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=0)
        except Exception as e:
            print(f"[HOTSPOT] Could not save data JSON: {e}")

    def generate_hotspot_map(self, output_path: str = None, payload: Dict[str, Any] = None) -> str:
        """Generate a standalone HTML file with area-based heatmap and filters. Uses payload if provided else computes it."""
        path = output_path or HOTSPOT_MAP_FILE
        if payload is None:
            payload = self._compute_hotspot_payload()
        self._save_hotspot_data_json(payload)
        clusters = payload["clusters"]
        unique_types = payload.get("unique_types", [])
        station_rankings = payload.get("station_rankings", [])
        station_rankings_recent_4h = payload.get("station_rankings_recent_4h", [])
        station_rankings_1h = payload.get("station_rankings_1h", [])
        station_trend = payload.get("station_trend", [])
        likely_next = payload.get("likely_next", [])
        hot_streets = payload.get("hot_streets", [])
        under_served_clusters = payload.get("under_served_clusters", [])
        staging_suggestion = payload.get("staging_suggestion")
        meta = payload.get("meta", {})
        stations = [{"lat": s[0], "lng": s[1], "name": s[2]} for s in STATION_LOCATIONS]
        chaser_js = json.dumps(CHASER_CONFIG)
        station_zone_radius = STATION_ZONE_RADIUS_MI
        clusters_js = json.dumps(clusters)
        types_js = json.dumps(unique_types)
        stations_js = json.dumps(stations)
        station_rankings_js = json.dumps(station_rankings)
        station_rankings_recent_4h_js = json.dumps(station_rankings_recent_4h)
        station_rankings_1h_js = json.dumps(station_rankings_1h)
        station_trend_js = json.dumps(station_trend)
        likely_next_js = json.dumps(likely_next)
        hot_streets_js = json.dumps(hot_streets)
        under_served_js = json.dumps(under_served_clusters)
        staging_suggestion_js = json.dumps(staging_suggestion) if staging_suggestion else "null"
        meta_js = json.dumps(meta)
        coverage_zones_js = json.dumps(SPOTTER_COVERAGE_ZONES)
        insights_js = json.dumps(payload.get("insights", {}))
        point_heat_js = json.dumps(payload.get("point_heat", []))
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#0a0a0c">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <title>NWA Dispatch Hotspots</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&family=Syne:wght@600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: 'DM Sans', system-ui, sans-serif; background: #0a0a0c; color: #e8e8ec; -webkit-font-smoothing: antialiased; }}
        #map {{ height: 100vh; width: 100%; background: #0a0a0c; }}
        .map-hud {{
            position: fixed; bottom: max(20px, env(safe-area-inset-bottom)); right: max(16px, env(safe-area-inset-right));
            z-index: 500; max-width: min(320px, calc(100vw - 32px));
            background: linear-gradient(145deg, rgba(18,18,22,0.96), rgba(12,12,16,0.98));
            border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 12px 16px;
            box-shadow: 0 12px 40px rgba(0,0,0,0.55), 0 0 0 1px rgba(249,115,22,0.12);
            pointer-events: none;
        }}
        .map-hud .hud-title {{ font-family: Syne, sans-serif; font-weight: 700; font-size: 13px; color: #fff; letter-spacing: -0.02em; margin-bottom: 4px; }}
        .map-hud .hud-line {{ font-size: 11px; color: #94a3b8; line-height: 1.45; }}
        .map-hud .hud-line strong {{ color: #f97316; font-weight: 600; }}
        .map-hud .hud-zoom {{ font-size: 10px; color: #64748b; margin-top: 6px; font-variant-numeric: tabular-nums; }}
        .toast {{
            position: fixed; bottom: 100px; left: 50%; transform: translateX(-50%) translateY(20px);
            z-index: 2000; padding: 12px 20px; border-radius: 10px; font-size: 13px; font-weight: 500;
            background: rgba(34,197,94,0.95); color: #fff; box-shadow: 0 8px 32px rgba(0,0,0,0.4);
            opacity: 0; transition: opacity 0.25s, transform 0.25s; pointer-events: none; max-width: 90vw;
        }}
        .toast.show {{ opacity: 1; transform: translateX(-50%) translateY(0); }}
        .toast.err {{ background: rgba(239,68,68,0.95); }}
        .help-backdrop {{
            display: none; position: fixed; inset: 0; z-index: 3000; background: rgba(0,0,0,0.65);
            align-items: center; justify-content: center; padding: 20px;
        }}
        .help-backdrop.open {{ display: flex; }}
        .help-modal {{
            background: #141418; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 20px 24px;
            max-width: 400px; max-height: 80vh; overflow-y: auto; box-shadow: 0 24px 64px rgba(0,0,0,0.5);
        }}
        .help-modal h2 {{ font-family: Syne, sans-serif; margin: 0 0 12px 0; font-size: 18px; color: #fff; }}
        .help-modal kbd {{ display: inline-block; padding: 2px 8px; border-radius: 4px; background: #2a2a30; font-size: 11px; margin-right: 6px; }}
        .help-modal p {{ margin: 8px 0; font-size: 12px; color: #a1a1aa; line-height: 1.5; }}
        .btn-help-fab {{
            position: fixed; bottom: max(20px, env(safe-area-inset-bottom)); left: max(16px, env(safe-area-inset-left));
            z-index: 499; width: 44px; height: 44px; border-radius: 50%; border: 1px solid rgba(255,255,255,0.12);
            background: rgba(18,18,22,0.92); color: #a78bfa; font-size: 18px; font-weight: 700; cursor: pointer;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center;
        }}
        .btn-help-fab:hover {{ background: rgba(59,130,246,0.2); color: #c4b5fd; }}
        @media (prefers-reduced-motion: reduce) {{
            * {{ animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }}
        }}
        .panel {{
            position: absolute; top: 12px; left: 12px; z-index: 1000; max-height: calc(100vh - 24px); overflow-y: auto;
            background: rgba(22,22,22,0.97); padding: 16px 20px; border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.06);
            min-width: 280px;
        }}
        .panel-header {{ margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.08); }}
        .panel h1 {{ margin: 0 0 4px 0; font-family: Syne, sans-serif; font-size: 17px; font-weight: 700; color: #fff; letter-spacing: -0.03em; }}
        .panel .subtitle {{ font-size: 11px; color: #737373; margin-bottom: 10px; line-height: 1.4; }}
        .panel .stat {{ font-size: 13px; color: #a3a3a3; margin: 4px 0; }}
        .panel .stat strong {{ color: #fafafa; }}
        .panel-card {{ margin-top: 12px; padding: 12px 14px; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid rgba(255,255,255,0.06); }}
        .panel-card h3 {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: #737373; margin: 0 0 8px 0; }}
        .filter-group {{ margin-top: 12px; }}
        .filter-group label {{ font-size: 11px; color: #737373; display: block; margin-bottom: 6px; }}
        .time-presets {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }}
        .time-presets button {{ padding: 6px 12px; font-size: 11px; border-radius: 6px; background: #2a2a2a; color: #e5e5e5; border: 1px solid #404040; cursor: pointer; }}
        .time-presets button:hover {{ background: #333; border-color: #525252; }}
        .time-presets button.active {{ background: #3b82f6; border-color: #3b82f6; color: #fff; }}
        .type-checks {{ max-height: 100px; overflow-y: auto; display: flex; flex-wrap: wrap; gap: 6px 10px; font-size: 11px; }}
        .type-checks label {{ margin: 0; cursor: pointer; white-space: nowrap; }}
        .heat-legend {{ margin-top: 12px; }}
        .heat-legend .legend-label {{ font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: #525252; margin-bottom: 6px; }}
        .heat-legend .legend-bar-wrap {{ display: flex; align-items: center; gap: 8px; }}
        .heat-bar {{ height: 10px; flex: 1; border-radius: 5px; background: linear-gradient(90deg, #22c55e 0%, #eab308 35%, #f97316 70%, #ef4444 100%); }}
        .heat-legend .legend-caps {{ font-size: 10px; color: #525252; }}
        .heat-legend .legend-tiers {{ display: flex; justify-content: space-between; margin-top: 4px; font-size: 9px; color: #404040; }}
        .top-n {{ margin-top: 12px; }}
        .top-n h3 {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: #737373; margin: 0 0 8px 0; }}
        .top-n-item {{ font-size: 11px; padding: 8px 10px; margin: 5px 0; background: rgba(255,255,255,0.04); border-radius: 6px; cursor: pointer; border-left: 3px solid #404040; }}
        .top-n-item:hover {{ background: rgba(59,130,246,0.15); border-left-color: #3b82f6; }}
        .top-n-item .count {{ color: #f97316; font-weight: 600; }}
        .top-n-item .addr {{ color: #a3a3a3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; margin-top: 2px; }}
        .density-badge {{ display: inline-block; font-size: 9px; font-weight: 600; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; margin-left: 6px; }}
        .density-badge.high {{ background: rgba(239,68,68,0.25); color: #fca5a5; }}
        .density-badge.medium {{ background: rgba(249,115,22,0.25); color: #fdba74; }}
        .density-badge.low {{ background: rgba(34,197,94,0.2); color: #86efac; }}
        .density-badge.critical {{ background: rgba(239,68,68,0.4); color: #fff; animation: pulse-badge 1.5s ease-in-out infinite; }}
        @keyframes pulse-badge {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.85; }} }}
        .nearest-item {{ font-size: 11px; padding: 6px 8px; margin: 4px 0; background: rgba(255,255,255,0.04); border-radius: 6px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
        .nearest-item:hover {{ background: rgba(59,130,246,0.15); }}
        .nearest-item .nearest-dist {{ color: #22c55e; font-weight: 600; font-size: 10px; white-space: nowrap; }}
        .nearest-item .nearest-addr {{ color: #a3a3a3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }}
        .btn {{ margin-top: 8px; padding: 6px 12px; font-size: 12px; border-radius: 4px; background: #404040; color: #e5e5e5; border: 1px solid #525252; cursor: pointer; width: 100%; }}
        .btn:hover {{ background: #525252; }}
        .toggle {{ margin-top: 8px; display: flex; align-items: center; gap: 6px; font-size: 12px; color: #a3a3a3; cursor: pointer; user-select: none; }}
        .toggle input {{ accent-color: #3b82f6; }}
        .panel .updated {{ font-size: 11px; color: #525252; margin-top: 8px; }}
        .leaflet-popup-content-wrapper {{ background: #262626; color: #e5e5e5; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.06); }}
        .leaflet-popup-tip {{ background: #262626; }}
        .popup-title {{ font-weight: 600; color: #f97316; font-size: 13px; margin-bottom: 6px; }}
        .leaflet-popup-content-wrapper .density-badge {{ font-size: 9px; padding: 2px 6px; }}
        .popup-count {{ font-size: 11px; color: #a3a3a3; margin-bottom: 8px; }}
        .popup-item {{ font-size: 12px; color: #d4d4d4; margin: 6px 0; padding-left: 8px; border-left: 2px solid #525252; }}
        .popup-item .type {{ color: #f97316; }}
        .popup-item .addr {{ color: #a3a3a3; }}
        .popup-item .time {{ color: #737373; font-size: 11px; }}
        .chaser-section {{ margin-top: 12px; padding: 12px; background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.3); border-radius: 8px; }}
        .chaser-section h3 {{ font-size: 13px; margin: 0 0 8px 0; color: #22c55e; font-weight: 600; }}
        .chaser-you {{ font-size: 11px; color: #a3a3a3; margin-bottom: 8px; line-height: 1.4; }}
        .chaser-summary {{ font-size: 12px; margin-bottom: 8px; color: #e5e5e5; }}
        .chaser-summary strong {{ color: #22c55e; }}
        .chaser-in-radius {{ font-size: 11px; padding: 8px 10px; margin: 6px 0; background: rgba(0,0,0,0.3); border-radius: 6px; cursor: pointer; border-left: 4px solid #22c55e; }}
        .chaser-in-radius:hover {{ background: rgba(34,197,94,0.15); }}
        .chaser-in-radius .row1 {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 4px; }}
        .chaser-in-radius .type {{ color: #f97316; font-weight: 600; }}
        .chaser-in-radius .dist {{ color: #22c55e; white-space: nowrap; }}
        .chaser-in-radius .addr {{ color: #a3a3a3; display: block; margin-bottom: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .chaser-in-radius .chaser-time {{ font-size: 10px; color: #737373; margin-bottom: 6px; }}
        .chaser-in-radius .row2 {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
        .chaser-maps {{ font-size: 10px; color: #3b82f6; text-decoration: none; }}
        .chaser-maps:hover {{ text-decoration: underline; }}
        .chaser-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; }}
        .chaser-badge.go {{ background: #22c55e; color: #fff; }}
        .chaser-badge.close {{ background: #0d9488; color: #fff; }}
        .chaser-badge.maybe {{ background: #eab308; color: #000; }}
        .chaser-badge.historic {{ background: #525252; color: #a3a3a3; }}
        .chaser-response {{ font-size: 11px; color: #a3a3a3; margin-bottom: 6px; }}
        .chaser-response strong {{ color: #22c55e; }}
        .btn-chaser {{ margin-top: 8px; padding: 6px 12px; font-size: 12px; border-radius: 4px; background: #22c55e; color: #fff; border: none; cursor: pointer; width: 100%; font-weight: 600; }}
        .btn-chaser:hover {{ background: #16a34a; }}
        .chaser-radius-row {{ display: flex; align-items: center; gap: 8px; margin: 8px 0; flex-wrap: wrap; }}
        .chaser-radius-row label {{ font-size: 12px; color: #a3a3a3; white-space: nowrap; }}
        .chaser-radius-row input[type="number"] {{ width: 72px; padding: 6px 8px; font-size: 12px; border-radius: 4px; border: 1px solid #525252; background: #262626; color: #e5e5e5; }}
        .popup-chaser {{ margin-top: 8px; padding-top: 6px; border-top: 1px solid #404040; font-size: 12px; color: #22c55e; }}
        .type-breakdown {{ font-size: 11px; color: #a3a3a3; margin-top: 4px; max-height: 80px; overflow-y: auto; }}
        .type-breakdown span {{ display: inline-block; margin: 2px 6px 2px 0; }}
        .recent-activity {{ margin-top: 8px; }}
        .recent-activity h3 {{ font-size: 12px; margin: 0 0 6px 0; color: #a3a3a3; }}
        .recent-item {{ font-size: 10px; padding: 4px 6px; margin: 3px 0; background: rgba(255,255,255,0.04); border-radius: 4px; cursor: pointer; border-left: 3px solid #525252; }}
        .recent-item:hover {{ background: rgba(255,255,255,0.08); }}
        .recent-item .rtype {{ color: #f97316; }}
        .recent-item .raddr {{ color: #737373; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .station-row {{ font-size: 11px; padding: 4px 6px; margin: 2px 0; display: flex; justify-content: space-between; }}
        .station-row span:last-child {{ color: #22c55e; font-weight: 600; }}
        .hottest-station-card {{ margin-top: 12px; padding: 12px; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); border-radius: 8px; }}
        .hottest-station-card h3 {{ color: #fca5a5; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; margin: 0 0 8px 0; }}
        .station-rank-row {{ font-size: 11px; padding: 6px 8px; margin: 4px 0; display: flex; justify-content: space-between; align-items: center; gap: 8px; border-radius: 6px; border-left: 3px solid #404040; }}
        .station-rank-row.rank-1 {{ border-left-color: #ef4444; background: rgba(239,68,68,0.1); }}
        .station-rank-row.rank-2 {{ border-left-color: #f97316; background: rgba(249,115,22,0.08); }}
        .station-rank-row.rank-3 {{ border-left-color: #eab308; }}
        .station-rank-row .rank-num {{ font-weight: 700; color: #737373; min-width: 18px; }}
        .station-rank-row .station-name {{ color: #a3a3a3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }}
        .station-rank-row .station-score {{ color: #f97316; font-weight: 600; white-space: nowrap; }}
        .busiest {{ font-size: 11px; color: #f97316; margin: 6px 0; padding: 6px; background: rgba(249,115,22,0.1); border-radius: 4px; }}
        .map-buttons {{ display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }}
        .map-buttons .btn {{ margin: 0; flex: 1; min-width: 80px; }}
        .type-breakdown-row {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 11px; }}
        .type-breakdown-row .type-name {{ color: #a3a3a3; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .type-breakdown-row .type-count {{ color: #22c55e; font-weight: 600; flex-shrink: 0; }}
        .type-breakdown-row .type-bar-wrap {{ flex: 1; height: 6px; background: #333; border-radius: 3px; overflow: hidden; max-width: 80px; }}
        .type-breakdown-row .type-bar {{ height: 100%; background: #3b82f6; border-radius: 3px; }}
        .busiest-addr-item {{ font-size: 11px; padding: 5px 8px; margin: 3px 0; background: rgba(255,255,255,0.04); border-radius: 4px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 8px; border-left: 3px solid #404040; }}
        .busiest-addr-item:hover {{ background: rgba(59,130,246,0.15); border-left-color: #3b82f6; }}
        .busiest-addr-item .addr-text {{ color: #a3a3a3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }}
        .busiest-addr-item .addr-count {{ color: #f97316; font-weight: 600; flex-shrink: 0; }}
        .staging-point {{ padding: 10px 0; }}
        .staging-point .staging-desc {{ font-size: 12px; color: #e2e8f0; margin-bottom: 4px; }}
        .staging-point .staging-coords {{ font-size: 11px; color: #94a3b8; font-family: ui-monospace, monospace; margin-bottom: 6px; }}
        .staging-point .staging-dist {{ font-size: 11px; color: #22c55e; margin-bottom: 10px; }}
        .staging-point .btn-staging {{ width: 100%; padding: 8px 12px; font-size: 12px; font-weight: 600; border-radius: 6px; background: #3b82f6; color: #fff; border: none; cursor: pointer; }}
        .staging-point .btn-staging:hover {{ background: #2563eb; }}
        .busiest-hour-item {{ font-size: 11px; padding: 4px 0; display: flex; align-items: center; gap: 8px; }}
        .busiest-hour-item .hour-label {{ color: #737373; width: 48px; flex-shrink: 0; }}
        .busiest-hour-item .hour-bar-wrap {{ flex: 1; height: 8px; background: #333; border-radius: 4px; overflow: hidden; max-width: 100px; }}
        .busiest-hour-item .hour-bar {{ height: 100%; background: #f97316; border-radius: 4px; }}
        .busiest-hour-item .hour-count {{ color: #22c55e; font-weight: 600; font-size: 10px; width: 28px; text-align: right; }}
        .busiest-day-row {{ font-size: 11px; padding: 4px 8px; margin: 2px 0; display: flex; justify-content: space-between; align-items: center; }}
        .busiest-day-row .day-name {{ color: #737373; }}
        .busiest-day-row .day-count {{ color: #f97316; font-weight: 600; }}
        .likely-next-item {{ font-size: 11px; padding: 6px 8px; margin: 4px 0; background: rgba(34,197,94,0.08); border-radius: 6px; cursor: pointer; border-left: 3px solid #22c55e; }}
        .likely-next-item:hover {{ background: rgba(34,197,94,0.18); }}
        .likely-next-item .likely-addr {{ color: #e5e5e5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }}
        .likely-next-item .likely-meta {{ font-size: 10px; color: #737373; margin-top: 2px; }}
        .likely-next-item .likely-score {{ color: #22c55e; font-weight: 600; font-size: 10px; }}
        .tight-cluster-stat {{ font-size: 11px; color: #a3a3a3; margin-top: 4px; }}
        .tight-cluster-stat strong {{ color: #f97316; }}
        .panel-section {{ margin-top: 10px; }}
        .panel-section summary {{ cursor: pointer; font-size: 12px; font-weight: 600; color: #a3a3a3; padding: 6px 0; list-style: none; display: flex; align-items: center; gap: 6px; user-select: none; }}
        .panel-section summary::-webkit-details-marker {{ display: none; }}
        .panel-section summary::before {{ content: '▶'; font-size: 10px; transition: transform 0.2s; }}
        .panel-section[open] summary::before {{ transform: rotate(90deg); }}
        .panel-section .section-body {{ padding-left: 14px; margin-top: 4px; }}
        .heat-intensity-row {{ display: flex; align-items: center; gap: 10px; margin: 8px 0; flex-wrap: wrap; }}
        .heat-intensity-row label {{ font-size: 11px; color: #737373; min-width: 90px; }}
        .heat-intensity-row input[type="range"] {{ flex: 1; min-width: 80px; accent-color: #f97316; }}
        .heat-intensity-row .heat-value {{ font-size: 11px; color: #f97316; font-weight: 600; width: 36px; text-align: right; }}
        .leaflet-control-layers {{ border-radius: 8px !important; overflow: hidden; }}
        .leaflet-control-layers label {{ font-size: 11px; }}
        .marker-pulse {{ animation: marker-pulse 1.2s ease-in-out infinite; }}
        @keyframes marker-pulse {{ 0%,100% {{ transform: scale(1); opacity: 0.95; }} 50% {{ transform: scale(1.08); opacity: 1; }} }}
        #togglePanel {{ position: fixed; top: 12px; left: 12px; z-index: 1001; width: 40px; height: 40px; border-radius: 10px; border: 1px solid #404040; background: rgba(22,22,22,0.95); color: #e5e5e5; font-size: 18px; cursor: pointer; display: none; align-items: center; justify-content: center; box-shadow: 0 4px 16px rgba(0,0,0,0.4); }}
        .panel-hidden .panel {{ transform: translateX(calc(-100% - 24px)); opacity: 0; pointer-events: none; }}
        .panel-hidden #togglePanel {{ display: flex !important; left: 12px; }}
        @media (max-width: 768px) {{
            #togglePanel {{ display: none; }}
            .panel-hidden #togglePanel {{ display: flex !important; }}
            .panel {{ max-width: calc(100vw - 24px); }}
        }}
        .insights-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 10px; margin-top: 8px; }}
        .insights-grid .cell {{ background: rgba(255,255,255,0.05); padding: 6px 8px; border-radius: 6px; border-left: 3px solid #3b82f6; }}
        .insights-grid .cell strong {{ display: block; color: #fafafa; font-size: 12px; }}
        .insights-grid .cell span {{ color: #737373; }}
        #addressSearch {{ width: 100%; padding: 8px 10px; margin-top: 6px; border-radius: 6px; border: 1px solid #404040; background: #262626; color: #e5e5e5; font-size: 12px; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="map-hud" id="mapHud" aria-live="polite">
        <div class="hud-title">Live view</div>
        <div class="hud-line" id="hudMain">—</div>
        <div class="hud-line" id="hudHeadline" style="margin-top:6px;color:#cbd5e1;font-size:10px;"></div>
        <div class="hud-zoom" id="hudZoom">Zoom —</div>
    </div>
    <button type="button" class="btn-help-fab" id="btnHelp" title="Shortcuts" aria-label="Keyboard shortcuts">?</button>
    <div class="help-backdrop" id="helpBackdrop" role="dialog" aria-modal="true" aria-labelledby="helpTitle">
        <div class="help-modal">
            <h2 id="helpTitle">Shortcuts</h2>
            <p><kbd>F</kbd> Fit all hotspots</p>
            <p><kbd>R</kbd> Fit your chase radius</p>
            <p><kbd>B</kbd> Toggle dark / satellite</p>
            <p><kbd>?</kbd> This panel · <kbd>Esc</kbd> close</p>
            <button type="button" class="btn" id="helpClose" style="margin-top:12px;">Close</button>
        </div>
    </div>
    <div class="toast" id="toast" role="status"></div>
    <button type="button" id="togglePanel" title="Show panel" aria-label="Show side panel">☰</button>
    <div class="panel" id="sidePanel">
        <div class="panel-header">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;"><h1 style="margin:0;">Incident hotspots</h1><button type="button" id="minimizePanel" title="Hide panel" aria-label="Hide side panel" style="flex-shrink:0;width:32px;height:32px;border-radius:6px;border:1px solid #404040;background:#2a2a2a;color:#a3a3a3;cursor:pointer;font-size:18px;line-height:1;">−</button></div>
            <p class="subtitle">Density by area · hotter = more calls. Like Active911-style hotspot view.</p>
            <p class="stat"><strong id="totalCalls">0</strong> calls · <strong id="areaCount">0</strong> hotspot areas</p>
            <p class="tight-cluster-stat" id="tightClusterStat"></p>
            <div class="busiest" id="busiestArea"></div>
            <div id="busierThanUsual" style="display:none; margin-top:8px; padding:8px; background:rgba(249,115,22,0.15); border-radius:6px; font-size:11px; color:#fdba74;"></div>
        </div>
        <div class="panel-card" id="insightsCard" style="border-left:3px solid #06b6d4;">
            <h3>📊 Intelligence</h3>
            <p id="insightsHeadline" style="font-size:12px;color:#fb923c;font-weight:600;line-height:1.4;margin:0 0 10px 0;"></p>
            <div class="insights-grid" id="insightsGrid"></div>
            <div id="repeatHotspotsList" style="margin-top:10px;font-size:10px;"></div>
            <div id="agencyBreakdown" style="margin-top:8px;font-size:10px;color:#737373;"></div>
        </div>
        <div class="panel-card filter-group">
            <h3>Search & filter</h3>
            <input type="search" id="addressSearch" placeholder="Filter by street, address, or type…" autocomplete="off" aria-label="Filter hotspots">
            <label class="toggle" style="margin-top:8px;"><input type="checkbox" id="recentOnly"> Only areas with call in last 25 min</label>
        </div>
        <div class="panel-card filter-group">
            <h3>Alert type breakdown</h3>
            <div class="type-breakdown" id="typeBreakdown"></div>
        </div>
        <div class="panel-card filter-group">
            <h3>Time range</h3>
            <div class="time-presets">
                <button type="button" data-hours="2">2h</button>
                <button type="button" data-hours="6">6h</button>
                <button type="button" data-hours="24">24h</button>
                <button type="button" data-days="7">7d</button>
                <button type="button" data-days="30">30d</button>
                <button type="button" data-days="90">90d</button>
                <button type="button" data-days="-1">All</button>
            </div>
        </div>
        <div class="panel-card filter-group">
            <h3>Incident type</h3>
            <div class="type-presets" style="margin-bottom:8px;display:flex;flex-wrap:wrap;gap:6px;">
                <button type="button" class="btn-type-preset" data-preset="fire">Fire</button>
                <button type="button" class="btn-type-preset" data-preset="medical">Medical</button>
                <button type="button" class="btn-type-preset" data-preset="mvc">MVC</button>
                <button type="button" class="btn-type-preset" data-preset="all">All</button>
            </div>
            <div class="type-checks" id="typeChecks"></div>
        </div>
        <div class="panel-card heat-legend">
            <div class="legend-label">Incident density</div>
            <div class="legend-bar-wrap">
                <span class="legend-caps">Low</span><div class="heat-bar" id="heatBar"></div><span class="legend-caps">High</span>
            </div>
            <div class="legend-tiers"><span>1–3</span><span>4–9</span><span>10+</span></div>
        </div>
        <div class="heat-intensity-row"><label>Heat intensity</label><input type="range" id="heatIntensity" min="0.3" max="2" step="0.1" value="1" title="Multiply heat visibility"><span class="heat-value" id="heatIntensityValue">1.0</span></div>
        <label class="toggle"><input type="checkbox" id="recencyWeight"> Weight heat by recency (recent calls = hotter)</label>
        <label class="toggle"><input type="checkbox" id="gradientAlt"> Blue–purple gradient</label>
        <label class="toggle"><input type="checkbox" id="showMarkers" checked> Area markers</label>
        <label class="toggle"><input type="checkbox" id="showPointHeat" checked> Per-call heat overlay (smooth density)</label>
        <label class="toggle"><input type="checkbox" id="hideClusterHeat"> Hide area heat (markers + point heat only)</label>
        <label class="toggle"><input type="checkbox" id="showStation" checked> Show stations</label>
        <button type="button" class="btn" id="useGeoNearest" style="margin-top:6px;background:#1e3a5f;border-color:#3b82f6;">📍 Use my GPS for “nearest” list</button>
        <div class="panel-card top-n">
            <h3>5 nearest to you</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#525252">Click to fly to hotspot (like Active911 nearest markers)</p>
            <div id="nearestList"></div>
        </div>
        <div class="chaser-section">
            <h3>📍 {CHASER_CONFIG["name"]}</h3>
            <p class="chaser-you" id="chaserAddress">—</p>
            <p class="chaser-summary"><strong id="chaserInRadius">0</strong> in your radius · <span id="chaserClosest">—</span></p>
            <div class="chaser-radius-row">
                <label for="chaserRadiusInput">Coverage radius (mi):</label>
                <input type="number" id="chaserRadiusInput" min="1" max="50" step="0.5" value="{CHASER_CONFIG["radius_miles"]}" title="Your chase/coverage radius in miles (saved in browser)">
            </div>
            <label class="toggle"><input type="checkbox" id="showChaserRadius" checked> Show my radius on map</label>
            <button type="button" class="btn-chaser" id="centerOnMe">Center map on me</button>
            <div id="chaserRadiusList" style="margin-top:10px"></div>
        </div>
        <div class="panel-card" style="border-left:3px solid #94a3b8;">
            <h3>🗺️ Spotter coverage zones</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#94a3b8">Who covers Rogers, Springdale, Lowell</p>
            <label class="toggle"><input type="checkbox" id="showCoverageZones" checked> Show zones on map</label>
            <div id="coverageZonesList" style="margin-top:8px"></div>
        </div>
        <div class="heat-intensity-row"><label>Auto-refresh</label><select id="autoRefreshInterval" title="Refresh data interval" style="flex:1;padding:6px 8px;border-radius:4px;border:1px solid #525252;background:#262626;color:#e5e5e5;font-size:11px;"><option value="0">Off</option><option value="15">15s</option><option value="30" selected>30s</option><option value="60">60s</option></select></div>
        <div class="panel-card top-n station-totals">
            <h3>Calls by station area</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#525252">Closest station gets the count</p>
            <div id="stationTotalsList"></div>
        </div>
        <div class="panel-card hottest-station-card">
            <h3>🔥 Hottest station zones</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#525252">By weighted activity (recency + type)</p>
            <div id="stationRankingsList"></div>
        </div>
        <div class="panel-card" style="border-left:3px solid #22c55e;">
            <h3>⚡ Hottest right now (last 4h)</h3>
            <div id="stationRankingsRecentList"></div>
        </div>
        <div class="panel-card" style="border-left:3px solid #a855f7;">
            <h3>🔥 Last 1 hour</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#525252">Real-time busiest station zones</p>
            <div id="stationRankings1hList"></div>
        </div>
        <div class="panel-card">
            <h3>🛣️ Hot streets</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#525252">Same street = one row · click to zoom</p>
            <div id="hotStreetsList"></div>
        </div>
        <div class="panel-card top-n">
            <h3>Likely next call areas</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#525252">Time-of-day + day-of-week + recent trend (48h/7d)</p>
            <div id="likelyNextList"></div>
        </div>
        <div class="panel-card top-n">
            <h3>Top 5 hotspot areas</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#525252">Most calls · click to zoom</p>
            <div id="topNList"></div>
        </div>
        <div class="panel-card staging-card" id="stagingPanel" style="display:none; border-left:3px solid #3b82f6;">
            <h3>📍 Where to stage</h3>
            <p class="subtitle" style="margin:0 0 8px 0;font-size:10px;color:#94a3b8">Best single point to cover the next predicted calls</p>
            <div id="stagingSuggestionContent"></div>
        </div>
        <div class="panel-card" id="underServedPanel" style="display:none; border-left:3px solid #eab308;">
            <h3>⚠️ Under-served areas</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#525252">Far from all stations · coverage gaps</p>
            <div id="underServedList"></div>
        </div>
        <div class="panel-card">
            <h3>Busiest addresses</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#525252">Top addresses · repeat spots (2+ calls) = calls close together · click to zoom</p>
            <div id="busiestAddressesList"></div>
        </div>
        <div class="panel-card">
            <h3>Busiest hours</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#525252">Calls by hour of day (local)</p>
            <div id="busiestHoursList"></div>
        </div>
        <div class="panel-card">
            <h3>Busiest days</h3>
            <p class="subtitle" style="margin:0 0 6px 0;font-size:10px;color:#525252">Calls by day of week</p>
            <div id="busiestDaysList"></div>
        </div>
        <div class="panel-card recent-activity">
            <h3>Last 10 calls</h3>
            <div id="recentActivityList"></div>
        </div>
        <div class="map-buttons">
            <button type="button" class="btn" id="fitAll" aria-label="Fit map to show all hotspots">Fit all</button>
            <button type="button" class="btn" id="fitMyRadius" aria-label="Fit map to your chase radius">Fit my radius</button>
        </div>
        <button type="button" class="btn" id="exportCsv" aria-label="Export filtered incidents as CSV">Export CSV</button>
        <button type="button" class="btn" id="exportGeojson">Export GeoJSON</button>
        <button type="button" class="btn" id="copyMapLink" title="Copy URL with current view and filters">Copy map link</button>
        <p class="updated" id="updated">—</p>
        <p class="updated" id="liveNote" style="font-size:10px;color:#525252">Auto-refresh above · F=fit all · R=fit radius · B=basemap</p>
    </div>
    <script>
        let allClusters = {clusters_js};
        const allTypes = {types_js};
        const stations = {stations_js};
        const chaser = {chaser_js};
        let stationRankings = {station_rankings_js};
        let stationRankingsRecent4h = {station_rankings_recent_4h_js};
        let stationRankings1h = {station_rankings_1h_js};
        let stationTrend = {station_trend_js};
        let serverLikelyNext = {likely_next_js};
        let hotStreets = {hot_streets_js};
        let underServedClusters = {under_served_js};
        let stagingSuggestion = {staging_suggestion_js};
        const coverageZones = {coverage_zones_js};
        const hotspotMeta = {meta_js};
        let insights = {insights_js};
        let pointHeatRaw = {point_heat_js};
        const defaultCenter = [36.332, -94.1185];
        const defaultZoom = 11;
        const HOTSPOT_DATA_URL = 'incident_hotspot_data.json';
        let currentTimeWindow = {{ type: 'all', value: -1 }};
        const GRADIENTS = {{
            default: {{ 0.2: '#22c55e', 0.45: '#eab308', 0.7: '#f97316', 1: '#ef4444' }},
            alt: {{ 0.2: '#60a5fa', 0.5: '#818cf8', 0.8: '#a855f7', 1: '#c026d3' }}
        }};
        let map, heatLayer, heatPointLayer, markersLayer, stationLayer, chaserLayer, stagingLayer, coverageZonesLayer, baseDark, baseSat;
        let selectedTypes = new Set(allTypes);
        let refreshTimer = null;
        let stationTotals = {{}};

        function haversineMi(lat1, lon1, lat2, lon2) {{
            const R = 3959;
            const dLat = (lat2 - lat1) * Math.PI / 180;
            const dLon = (lon2 - lon1) * Math.PI / 180;
            const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180) * Math.sin(dLon/2)**2;
            return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        }}
        function chaserDist(cluster) {{ return haversineMi(chaser.lat, chaser.lng, cluster.lat, cluster.lng); }}
        function chaserEtaMin(distMi) {{ return Math.round((distMi / (chaser.avg_speed_mph || 35)) * 60); }}
        function chaserEtaReal(distMi) {{ const raw = (distMi / (chaser.avg_speed_mph || 35)) * 60; return Math.round(raw * (chaser.eta_factor || 1.4)); }}
        function inChaserRadius(cluster) {{ return chaserDist(cluster) <= (chaser.radius_miles || 15); }}
        function parseCallTime(iso) {{
            if (!iso) return null;
            let s = String(iso).trim();
            if (s && !s.endsWith('Z') && s.indexOf('+') === -1) s = s + 'Z';
            return new Date(s);
        }}
        function callAgeMin(iso) {{
            const d = parseCallTime(iso);
            return d && !isNaN(d.getTime()) ? Math.round((Date.now() - d.getTime()) / 60000) : 999;
        }}
        function formatLocalTime(iso) {{
            const d = parseCallTime(iso);
            return d && !isNaN(d.getTime()) ? d.toLocaleString(undefined, {{ hour: 'numeric', minute: '2-digit', hour12: true, timeZoneName: 'short' }}) : '—';
        }}
        function newestCallAgeMin(cluster) {{
            const times = (cluster.incidents || []).map(i => i.received_at ? parseCallTime(i.received_at).getTime() : 0).filter(Boolean);
            if (!times.length) return 999;
            return Math.round((Date.now() - Math.max(...times)) / 60000);
        }}
        function newestReceivedAt(cluster) {{
            const withTime = (cluster.incidents || []).filter(i => i.received_at).map(i => ({{ t: parseCallTime(i.received_at).getTime(), iso: i.received_at }}));
            if (!withTime.length) return null;
            return withTime.sort((a,b) => b.t - a.t)[0].iso;
        }}
        const responseWindow = chaser.response_window_min != null ? chaser.response_window_min : 20;
        const closeEnoughMi = chaser.close_enough_mi != null ? chaser.close_enough_mi : 6;
        const makeItEtaMax = chaser.make_it_eta_max != null ? chaser.make_it_eta_max : 14;
        const stationZoneRadiusMi = {station_zone_radius};
        function makeItInTime(c) {{ return c.etaReal <= makeItEtaMax && c.ageMin <= responseWindow; }}
        function closeEnough(c) {{ return c.dist <= closeEnoughMi; }}
        function densityTier(count) {{ return count >= 10 ? {{ tier: 'high', label: 'High' }} : count >= 4 ? {{ tier: 'medium', label: 'Medium' }} : {{ tier: 'low', label: 'Low' }}; }}
        function distToStation(cluster, s) {{ return haversineMi(cluster.lat, cluster.lng, s.lat, s.lng); }}
        function nearestStation(cluster) {{
            if (!stations.length) return null;
            let best = {{ name: stations[0].name, dist: distToStation(cluster, stations[0]) }};
            stations.forEach(s => {{ const d = distToStation(cluster, s); if (d < best.dist) best = {{ name: s.name, dist: d }}; }});
            return best;
        }}
        function buildStationTotals(clusterList) {{
            const totals = {{}};
            stations.forEach(s => totals[s.name] = 0);
            clusterList.forEach(c => {{
                const near = nearestStation(c);
                if (near) totals[near.name] = (totals[near.name] || 0) + c.count;
            }});
            return totals;
        }}

        function getTimeCut() {{
            const now = Date.now();
            if (currentTimeWindow.type === 'all' || currentTimeWindow.value < 0) return 0;
            if (currentTimeWindow.type === 'hours') return now - currentTimeWindow.value * 3600000;
            return now - currentTimeWindow.value * 24 * 3600000;
        }}
        function getFilteredClusters() {{
            const cut = getTimeCut();
            let list = allClusters.map(c => {{
                const incidents = (c.incidents || []).filter(i => {{
                    const okType = selectedTypes.has(i.type || 'Unknown');
                    const t = i.received_at ? new Date(i.received_at).getTime() : 0;
                    return okType && t >= cut;
                }});
                if (incidents.length === 0) return null;
                const lat = c.lat, lng = c.lng;
                const weighted = c.weighted_score != null ? (c.weighted_score * incidents.length / Math.max(c.count || 1, 1)) : incidents.length;
                return {{ lat, lng, count: incidents.length, incidents, weighted_score: Math.round(weighted * 100) / 100, last_24h: c.last_24h, previous_24h: c.previous_24h, quality: c.quality, tier: c.tier, last_24h_score: c.last_24h_score, last_7d_score: c.last_7d_score }};
            }}).filter(Boolean);
            const qEl = document.getElementById('addressSearch');
            const q = (qEl && qEl.value || '').trim().toLowerCase();
            if (q) list = list.filter(c => (c.incidents || []).some(i => ((i.address || '') + ' ' + (i.type || '')).toLowerCase().includes(q)));
            if (document.getElementById('recentOnly') && document.getElementById('recentOnly').checked)
                list = list.filter(c => newestCallAgeMin(c) <= 25);
            return list;
        }}

        function renderInsights() {{
            const el = document.getElementById('insightsGrid');
            const ag = document.getElementById('agencyBreakdown');
            const hl = document.getElementById('insightsHeadline');
            const repEl = document.getElementById('repeatHotspotsList');
            if (hl) hl.textContent = (insights && insights.summary_headline) || (hotspotMeta && hotspotMeta.summary_headline) || '';
            if (!el) return;
            if (!insights || insights.calls_last_24h == null) {{ el.innerHTML = '<p class="stat">—</p>'; if (ag) ag.innerHTML = ''; if (repEl) repEl.innerHTML = ''; return; }}
            const v = insights.velocity_vs_prior_24h_pct || 0;
            const velBorder = v > 15 ? '#22c55e' : v < -15 ? '#ef4444' : '#3b82f6';
            const wv = insights.week_vs_prior_pct;
            const wkCell = (wv != null && insights.calls_prior_week) ? '<div class="cell"><strong>' + (wv > 0 ? '+' : '') + wv + '%</strong><span>this week vs last</span></div>' : '';
            el.innerHTML = '<div class="cell"><strong>' + insights.calls_last_24h + '</strong><span>calls last 24h</span></div>' +
                '<div class="cell" style="border-left-color:' + velBorder + '"><strong>' + (v > 0 ? '+' : '') + v + '%</strong><span>vs prior 24h</span></div>' +
                wkCell +
                '<div class="cell"><strong>' + (insights.peak_hour_label || '—') + '</strong><span>peak hour (CT)</span></div>' +
                '<div class="cell"><strong>' + (insights.busiest_2h_window || '—') + '</strong><span>busiest 2h span</span></div>' +
                '<div class="cell"><strong>' + (insights.busiest_day || '—') + '</strong><span>busiest weekday</span></div>' +
                '<div class="cell"><strong>' + (insights.night_share_pct || 0) + '%</strong><span>night calls (10p–6a)</span></div>';
            if (repEl && insights.repeat_hotspots && insights.repeat_hotspots.length) {{
                repEl.innerHTML = '<span style="color:#737373">Repeat addresses · tap to filter:</span> ' +
                    insights.repeat_hotspots.slice(0, 6).map(r => '<button type="button" class="repeat-chip" data-q="' + String(r.address || '').replace(/"/g, '&quot;').substring(0, 80) + '" style="margin:3px 4px 0 0;padding:4px 8px;font-size:10px;border-radius:6px;border:1px solid #404040;background:#2a2a30;color:#e5e5e5;cursor:pointer;max-width:100%;text-align:left">' +
                    (r.address || '').substring(0, 36) + (r.address && r.address.length > 36 ? '…' : '') + ' <strong style="color:#f97316">' + r.count + '×</strong></button>').join('');
                repEl.querySelectorAll('.repeat-chip').forEach(btn => {{
                    btn.addEventListener('click', () => {{
                        const inp = document.getElementById('addressSearch');
                        if (inp) {{ inp.value = btn.getAttribute('data-q') || ''; applyFilters(); inp.focus(); showToast('Filtered to repeat address'); }}
                    }});
                }});
            }} else if (repEl) repEl.innerHTML = '';
            if (ag && insights.agency_breakdown && insights.agency_breakdown.length)
                ag.innerHTML = '<strong style="color:#a3a3a3">Agencies:</strong> ' + insights.agency_breakdown.map(a => (a.name || '').substring(0, 28) + ' (' + a.count + ')').join(' · ');
            else if (ag) ag.innerHTML = '';
        }}
        function showToast(msg, isErr) {{
            const t = document.getElementById('toast');
            if (!t) return;
            t.textContent = msg;
            t.className = 'toast' + (isErr ? ' err' : '') + ' show';
            clearTimeout(window.__toastTimer);
            window.__toastTimer = setTimeout(() => {{ t.classList.remove('show'); }}, 2600);
        }}
        function refLatLng() {{
            if (window.__geoLat != null && window.__geoLng != null) return {{ lat: window.__geoLat, lng: window.__geoLng }};
            if (chaser && chaser.lat != null) return {{ lat: chaser.lat, lng: chaser.lng }};
            return null;
        }}
        function distFromRef(cluster) {{
            const r = refLatLng();
            if (!r) return 999;
            return haversineMi(r.lat, r.lng, cluster.lat, cluster.lng);
        }}
        function applyFilters() {{
            renderInsights();
            const filtered = getFilteredClusters();
            stationTotals = buildStationTotals(filtered);
            const recencyWeight = document.getElementById('recencyWeight').checked;
            const areaHeat = recencyWeight && filtered.some(c => c.weighted_score != null)
                ? filtered.map(c => [c.lat, c.lng, c.weighted_score || c.count])
                : filtered.map(c => [c.lat, c.lng, c.count]);
            const maxIntensity = areaHeat.length ? Math.max(...areaHeat.map(p => p[2]), 0.01) : 1;
            const useAlt = document.getElementById('gradientAlt').checked;
            const grad = useAlt ? GRADIENTS.alt : GRADIENTS.default;
            document.getElementById('heatBar').style.background = useAlt
                ? 'linear-gradient(90deg, #60a5fa 0%, #818cf8 50%, #a855f7 100%)'
                : 'linear-gradient(90deg, #22c55e 0%, #eab308 35%, #f97316 70%, #ef4444 100%)';
            if (heatLayer) map.removeLayer(heatLayer);
            heatLayer = null;
            if (heatPointLayer) map.removeLayer(heatPointLayer);
            heatPointLayer = null;
            const zf = map && map.getZoom ? Math.max(0.62, Math.min(1.5, 1 + (map.getZoom() - 11) * 0.065)) : 1;
            const heatRadius = ((hotspotMeta && hotspotMeta.heat_radius) || 45) * zf;
            const heatBlur = ((hotspotMeta && hotspotMeta.heat_blur) || 35) * zf;
            const heatIntensity = typeof window.__heatIntensity === 'number' ? Math.max(0.2, Math.min(2, window.__heatIntensity)) : 1;
            const hideClusterHeat = document.getElementById('hideClusterHeat') && document.getElementById('hideClusterHeat').checked;
            if (!hideClusterHeat && areaHeat.length > 0) {{
                heatLayer = L.heatLayer(areaHeat.map(p => [p[0], p[1], (p[2] || 0) * heatIntensity]), {{
                    radius: heatRadius, blur: heatBlur, maxZoom: 16, minOpacity: 0.35, max: maxIntensity * heatIntensity, gradient: grad
                }}).addTo(map);
            }}
            const showPointHeat = document.getElementById('showPointHeat') && document.getElementById('showPointHeat').checked;
            if (showPointHeat && pointHeatRaw && pointHeatRaw.length) {{
                const cutMs = getTimeCut();
                const pts = pointHeatRaw.filter(pt => (pt[3] || 0) >= cutMs).filter(pt => selectedTypes.has(pt[4] || 'Unknown')).map(pt => [pt[0], pt[1], (pt[2] || 0.5) * heatIntensity * 0.85]);
                if (pts.length > 0) {{
                    const maxP = Math.max(...pts.map(p => p[2]), 0.01);
                    heatPointLayer = L.heatLayer(pts, {{ radius: 32 * zf, blur: 26 * zf, maxZoom: 17, minOpacity: 0.25, max: maxP, gradient: grad }}).addTo(map);
                }}
            }}
            const tightCount = filtered.filter(c => c.count >= 2).length;
            const tightEl = document.getElementById('tightClusterStat');
            tightEl.innerHTML = tightCount > 0 ? '<strong>' + tightCount + '</strong> areas with 2+ calls (calls close together)' : '';
            const cut = getTimeCut();
            const serverLikelyFiltered = (serverLikelyNext || []).filter(c => {{
                const incidents = c.incidents || [];
                const inRange = incidents.some(i => i.received_at && new Date(i.received_at).getTime() >= cut);
                return inRange || cut === 0;
            }});
            const likelyScored = serverLikelyFiltered.length > 0 ? serverLikelyFiltered.slice(0, 5) : filtered.map(c => {{
                const ageMin = newestCallAgeMin(c);
                const score = (c.weighted_score || c.count) * (1 / (1 + ageMin / 720));
                return {{ ...c, ageMin, score, likely_score: score }};
            }}).sort((a, b) => (b.likely_score || b.score || 0) - (a.likely_score || a.score || 0)).slice(0, 5);
            const likelyEl = document.getElementById('likelyNextList');
            likelyEl.innerHTML = likelyScored.length ? likelyScored.map(c => {{
                const addr = (c.incidents && c.incidents[0] && c.incidents[0].address) || (c.lat.toFixed(4) + ', ' + c.lng.toFixed(4));
                const ageMin = c.ageMin != null ? c.ageMin : newestCallAgeMin(c);
                const lastStr = ageMin < 60 ? ageMin + ' min ago' : (ageMin < 1440 ? Math.round(ageMin/60) + ' hr ago' : Math.round(ageMin/1440) + ' day ago');
                const meta = (c.recent_48h != null && c.recent_7d != null) ? ' (48h: ' + c.recent_48h + ', 7d: ' + c.recent_7d + ')' : '';
                const conf = c.confidence || '';
                const confBadge = conf ? '<span class="density-badge ' + (conf === 'high' ? 'high' : conf === 'medium' ? 'medium' : 'low') + '" style="margin-left:6px">' + conf + '</span>' : '';
                return `<div class="likely-next-item" data-lat="${{c.lat}}" data-lng="${{c.lng}}"><span class="likely-addr" title="${{addr}}">${{addr}}</span>${{confBadge}}<span class="likely-meta">${{c.count}} call${{c.count !== 1 ? 's' : ''}} · last ${{lastStr}}${{meta}}</span></div>`;
            }}).join('') : '<p class="stat">No data</p>';
            likelyEl.querySelectorAll('.likely-next-item').forEach(el => {{
                el.addEventListener('click', () => map.flyTo([+el.dataset.lat, +el.dataset.lng], 15));
            }});
            const rankListEl = document.getElementById('stationRankingsList');
            const trendByName = (stationTrend && Array.isArray(stationTrend)) ? Object.fromEntries(stationTrend.map(r => [r.name, r])) : {{}};
            if (rankListEl && stationRankings && stationRankings.length) {{
                rankListEl.innerHTML = stationRankings.slice(0, 8).map((r, i) => {{
                    const rankClass = r.rank === 1 ? 'rank-1' : r.rank === 2 ? 'rank-2' : r.rank === 3 ? 'rank-3' : '';
                    const shortName = (r.name || '').length > 32 ? (r.name || '').substring(0, 29) + '...' : (r.name || '');
                    const tr = trendByName[r.name];
                    const trendStr = tr && tr.rank_7d != null && tr.trend === 'up' ? ' ↑ from #' + tr.rank_7d : (tr && tr.trend === 'down' ? ' ↓' : '');
                    return `<div class="station-rank-row ${{rankClass}}"><span class="rank-num">#${{r.rank}}</span><span class="station-name" title="${{(r.name || '').replace(/"/g, '&quot;')}}">${{shortName.replace(/"/g, '&quot;')}}${{trendStr}}</span><span class="station-score">${{r.weighted_score != null ? r.weighted_score : r.count}}</span></div>`;
                }}).join('');
            }} else if (rankListEl) rankListEl.innerHTML = '<p class="stat">No station data</p>';
            const recent4hEl = document.getElementById('stationRankingsRecentList');
            if (recent4hEl && stationRankingsRecent4h && stationRankingsRecent4h.length) {{
                recent4hEl.innerHTML = stationRankingsRecent4h.slice(0, 5).map((r, i) => {{
                    const shortName = (r.name || '').length > 28 ? (r.name || '').substring(0, 25) + '...' : (r.name || '');
                    return `<div class="station-rank-row ${{r.rank === 1 ? 'rank-1' : ''}}"><span class="rank-num">#${{r.rank}}</span><span class="station-name" title="${{r.name}}">${{shortName}}</span><span class="station-score">${{r.weighted_score != null ? r.weighted_score : r.count}}</span></div>`;
                }}).join('');
            }} else if (recent4hEl) recent4hEl.innerHTML = '<p class="stat">No calls in last 4h</p>';
            const rank1hEl = document.getElementById('stationRankings1hList');
            if (rank1hEl && stationRankings1h && stationRankings1h.length) {{
                rank1hEl.innerHTML = stationRankings1h.slice(0, 5).map((r, i) => {{
                    const shortName = (r.name || '').length > 28 ? (r.name || '').substring(0, 25) + '...' : (r.name || '');
                    return `<div class="station-rank-row ${{r.rank === 1 ? 'rank-1' : ''}}"><span class="rank-num">#${{r.rank}}</span><span class="station-name" title="${{r.name}}">${{shortName}}</span><span class="station-score">${{r.weighted_score != null ? r.weighted_score : r.count}}</span></div>`;
                }}).join('');
            }} else if (rank1hEl) rank1hEl.innerHTML = '<p class="stat">No calls in last 1h</p>';
            const hotStreetsEl = document.getElementById('hotStreetsList');
            if (hotStreetsEl && hotStreets && hotStreets.length) {{
                hotStreetsEl.innerHTML = hotStreets.slice(0, 10).map(s => `<div class="busiest-addr-item" data-lat="${{s.lat}}" data-lng="${{s.lng}}" title="${{s.street}}"><span class="addr-text">${{s.street}}</span><span class="addr-count">${{s.count}}</span></div>`).join('');
                hotStreetsEl.querySelectorAll('.busiest-addr-item').forEach(el => {{ el.addEventListener('click', () => map.flyTo([+el.dataset.lat, +el.dataset.lng], 15)); }});
            }} else if (hotStreetsEl) hotStreetsEl.innerHTML = '<p class="stat">No street data</p>';
            const underServedEl = document.getElementById('underServedList');
            const underServedPanel = document.getElementById('underServedPanel');
            if (underServedClusters && underServedClusters.length && underServedEl && underServedPanel) {{
                underServedPanel.style.display = 'block';
                underServedEl.innerHTML = underServedClusters.slice(0, 8).map(u => {{
                    const closest = u.closest_station_name ? ' · Closest: ' + (u.closest_station_name.length > 25 ? u.closest_station_name.substring(0,22) + '...' : u.closest_station_name) + ' (' + (u.closest_station_mi != null ? u.closest_station_mi : u.min_station_mi) + ' mi)' : '';
                    return `<div class="busiest-addr-item" data-lat="${{u.lat}}" data-lng="${{u.lng}}"><span class="addr-text">${{u.min_station_mi}} mi from stations${{closest}} · ${{u.count}} call${{u.count !== 1 ? 's' : ''}}</span><span class="addr-count">${{u.count}}</span></div>`;
                }}).join('');
                underServedEl.querySelectorAll('.busiest-addr-item').forEach(el => {{ el.addEventListener('click', () => map.flyTo([+el.dataset.lat, +el.dataset.lng], 12)); }});
            }} else if (underServedPanel) underServedPanel.style.display = 'none';
            const stagingPanel = document.getElementById('stagingPanel');
            const stagingContent = document.getElementById('stagingSuggestionContent');
            if (stagingSuggestion && stagingPanel && stagingContent) {{
                stagingPanel.style.display = 'block';
                const distMi = chaser && chaser.lat != null ? haversineMi(chaser.lat, chaser.lng, stagingSuggestion.lat, stagingSuggestion.lng) : null;
                const distLine = distMi != null ? '~' + distMi.toFixed(1) + ' mi from you' : '';
                const coords = stagingSuggestion.lat.toFixed(4) + ', ' + stagingSuggestion.lng.toFixed(4);
                const conf = (stagingSuggestion.confidence || 'medium');
                stagingContent.innerHTML = '<div class="staging-point" data-lat="' + stagingSuggestion.lat + '" data-lng="' + stagingSuggestion.lng + '">' +
                    '<div class="staging-desc">Center of top 3 likely-next areas <span class="density-badge ' + conf + '">' + conf + '</span></div>' +
                    '<div class="staging-coords">' + coords + '</div>' +
                    (distLine ? '<div class="staging-dist">' + distLine + '</div>' : '') +
                    '<button type="button" class="btn-staging">Fly to staging point</button></div>';
                stagingContent.querySelector('.btn-staging').addEventListener('click', () => map.flyTo([stagingSuggestion.lat, stagingSuggestion.lng], 14));
                if (stagingLayer) map.removeLayer(stagingLayer);
                stagingLayer = L.layerGroup();
                const popupHtml = '<strong>Where to stage</strong><br>Center of top 3 likely-next areas<br>' + coords + (distLine ? '<br>' + distLine : '');
                L.circleMarker([stagingSuggestion.lat, stagingSuggestion.lng], {{ radius: 12, fillColor: '#3b82f6', color: '#fff', weight: 2, fillOpacity: 0.9 }}).bindPopup(popupHtml).addTo(stagingLayer);
                stagingLayer.addTo(map);
            }} else if (stagingPanel) stagingPanel.style.display = 'none';
            const busierEl = document.getElementById('busierThanUsual');
            if (busierEl && currentTimeWindow.type === 'hours' && currentTimeWindow.value === 2) {{
                const total = filtered.reduce((s, c) => s + c.count, 0);
                const baseline = (hotspotMeta && hotspotMeta.baseline_calls_this_hour_dow) || 0;
                if (baseline > 0 && total > baseline) {{
                    busierEl.style.display = 'block';
                    busierEl.textContent = 'Busier than usual: ' + total + ' calls in last 2h (typical for this hour/weekday: ' + baseline + ')';
                }} else busierEl.style.display = 'none';
            }} else if (busierEl) busierEl.style.display = 'none';
            if (markersLayer) map.removeLayer(markersLayer);
            markersLayer = null;
            if (document.getElementById('showMarkers').checked && filtered.length > 0) {{
                window.__filteredForExport = filtered;
                markersLayer = L.layerGroup();
                filtered.forEach((c, idx) => {{
                    const ageMin = newestCallAgeMin(c);
                    const isPulse = (c.tier === 'critical') || (ageMin <= 30 && c.count >= 1);
                    const m = L.circleMarker([c.lat, c.lng], {{
                        radius: Math.min(12, 5 + Math.min(c.count, 8)),
                        fillColor: c.tier === 'critical' ? '#ef4444' : (c.count > 1 ? '#ef4444' : '#f97316'),
                        color: '#fff', weight: isPulse ? 2.5 : 1.5, opacity: 1, fillOpacity: 0.9
                    }});
                    m.bindPopup(popupContent(c, idx), {{ maxWidth: 320 }});
                    markersLayer.addLayer(m);
                }});
                markersLayer.addTo(map);
            }}
            const total = filtered.reduce((s, c) => s + c.count, 0);
            document.getElementById('totalCalls').textContent = total;
            document.getElementById('areaCount').textContent = filtered.length;
            const nearest5 = refLatLng() ? [...filtered].map(c => ({{ ...c, dist: distFromRef(c) }})).sort((a, b) => a.dist - b.dist).slice(0, 5) : [];
            const nearestEl = document.getElementById('nearestList');
            const geoNote = window.__geoLat != null ? ' (GPS)' : '';
            nearestEl.innerHTML = nearest5.length ? nearest5.map((c, i) => {{
                const addr = (c.incidents[0] && c.incidents[0].address) || (c.lat.toFixed(4) + ', ' + c.lng.toFixed(4));
                return `<div class="nearest-item" data-lat="${{c.lat}}" data-lng="${{c.lng}}"><span class="nearest-addr" title="${{addr}}">${{addr}}</span><span class="nearest-dist">${{c.dist.toFixed(1)}} mi${{geoNote}}</span></div>`;
            }}).join('') : '<p class="stat">Enable GPS or set chaser location</p>';
            nearestEl.querySelectorAll('.nearest-item').forEach(el => {{
                el.addEventListener('click', () => map.flyTo([+el.dataset.lat, +el.dataset.lng], 15));
            }});
            const top5 = [...filtered].sort((a, b) => (b.last_24h_score != null ? b.last_24h_score : b.count) - (a.last_24h_score != null ? a.last_24h_score : a.count)).slice(0, 5);
            const listEl = document.getElementById('topNList');
            const tierLabel = (c) => c.tier === 'critical' ? 'Critical' : (c.tier === 'high' ? 'High' : (c.tier === 'medium' ? 'Medium' : 'Low'));
            listEl.innerHTML = top5.map((c, i) => {{
                const addr = (c.incidents[0] && c.incidents[0].address) || (c.lat + ', ' + c.lng);
                const tier = c.tier || densityTier(c.count).tier;
                const label = c.tier ? tierLabel(c) : densityTier(c.count).label;
                return `<div class="top-n-item" data-lat="${{c.lat}}" data-lng="${{c.lng}}"><span class="count">#${{i+1}} ${{c.count}} call${{c.count !== 1 ? 's' : ''}}</span><span class="density-badge ${{tier}}">${{label}}</span><span class="addr">${{addr}}</span></div>`;
            }}).join('') || '<p class="stat">No areas in range</p>';
            listEl.querySelectorAll('.top-n-item').forEach(el => {{
                el.addEventListener('click', () => map.flyTo([+el.dataset.lat, +el.dataset.lng], 15));
            }});
            const stationListEl = document.getElementById('stationTotalsList');
            const stationRows = stations.map(s => ({{ name: s.name, count: stationTotals[s.name] || 0 }})).filter(r => r.count > 0).sort((a, b) => b.count - a.count);
            stationListEl.innerHTML = stationRows.length ? stationRows.map(r => `<div class="station-row"><span>${{r.name}}</span><span>${{r.count}} call${{r.count !== 1 ? 's' : ''}}</span></div>`).join('') : '<p class="stat">No calls in station areas</p>';
            const typeCounts = {{}};
            filtered.forEach(c => (c.incidents || []).forEach(i => {{ const t = i.type || 'Unknown'; typeCounts[t] = (typeCounts[t] || 0) + 1; }}));
            const typeBreakdownEl = document.getElementById('typeBreakdown');
            const typeEntries = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);
            const maxTypeCount = typeEntries.length ? Math.max(...typeEntries.map(([, n]) => n), 1) : 1;
            typeBreakdownEl.innerHTML = typeEntries.map(([t, n]) => {{
                const barPct = Math.round(100 * n / maxTypeCount);
                return `<div class="type-breakdown-row"><span class="type-name" title="${{t}}">${{t}}</span><span class="type-count">${{n}}</span><div class="type-bar-wrap"><div class="type-bar" style="width:${{barPct}}%"></div></div></div>`;
            }}).join('') || '<p class="stat">—</p>';
            const allIncidents = [];
            filtered.forEach(c => (c.incidents || []).forEach(i => allIncidents.push({{ ...i, lat: c.lat, lng: c.lng }})));
            const addrCounts = {{}};
            const addrFirst = {{}};
            allIncidents.forEach(i => {{
                const addr = (i.address && String(i.address).trim()) || (i.lat + ', ' + i.lng);
                addrCounts[addr] = (addrCounts[addr] || 0) + 1;
                if (!addrFirst[addr]) addrFirst[addr] = {{ lat: i.lat, lng: i.lng }};
            }});
            const busiestAddrs = Object.entries(addrCounts).map(([addr, count]) => ({{ addr, count, lat: addrFirst[addr].lat, lng: addrFirst[addr].lng }})).sort((a, b) => b.count - a.count).slice(0, 8);
            const busiestAddrEl = document.getElementById('busiestAddressesList');
            busiestAddrEl.innerHTML = busiestAddrs.length ? busiestAddrs.map(a => `<div class="busiest-addr-item" data-lat="${{a.lat}}" data-lng="${{a.lng}}" title="${{a.addr}}"><span class="addr-text">${{a.addr}}</span><span class="addr-count">${{a.count}}</span></div>`).join('') : '<p class="stat">No data</p>';
            busiestAddrEl.querySelectorAll('.busiest-addr-item').forEach(el => {{
                el.addEventListener('click', () => map.flyTo([+el.dataset.lat, +el.dataset.lng], 15));
            }});
            const hourCounts = Array(24).fill(0);
            allIncidents.forEach(i => {{
                if (i.received_at) {{ const d = parseCallTime(i.received_at); if (d && !isNaN(d.getTime())) hourCounts[d.getHours()]++; }}
            }});
            const maxHourCount = Math.max(...hourCounts, 1);
            const hourLabels = ['12a','1a','2a','3a','4a','5a','6a','7a','8a','9a','10a','11a','12p','1p','2p','3p','4p','5p','6p','7p','8p','9p','10p','11p'];
            const busiestHoursEl = document.getElementById('busiestHoursList');
            busiestHoursEl.innerHTML = hourCounts.map((count, h) => {{
                const barPct = Math.round(100 * count / maxHourCount);
                return `<div class="busiest-hour-item"><span class="hour-label">${{hourLabels[h]}}</span><div class="hour-bar-wrap"><div class="hour-bar" style="width:${{barPct}}%"></div></div><span class="hour-count">${{count}}</span></div>`;
            }}).join('');
            const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
            const dayCounts = [0,0,0,0,0,0,0];
            allIncidents.forEach(i => {{
                if (i.received_at) {{ const d = parseCallTime(i.received_at); if (d && !isNaN(d.getTime())) dayCounts[d.getDay()]++; }}
            }});
            const busiestDaysEl = document.getElementById('busiestDaysList');
            busiestDaysEl.innerHTML = dayCounts.map((count, day) => `<div class="busiest-day-row"><span class="day-name">${{dayNames[day]}}</span><span class="day-count">${{count}}</span></div>`).join('');
            const recent = allIncidents.filter(i => i.received_at).sort((a, b) => parseCallTime(b.received_at).getTime() - parseCallTime(a.received_at).getTime()).slice(0, 10);
            const recentEl = document.getElementById('recentActivityList');
            recentEl.innerHTML = recent.length ? recent.map(i => {{
                const addr = i.address || (i.lat + ', ' + i.lng);
                const t = i.type || 'Incident';
                const timeStr = formatLocalTime(i.received_at) + ' · ' + callAgeMin(i.received_at) + ' min ago';
                return `<div class="recent-item" data-lat="${{i.lat}}" data-lng="${{i.lng}}"><span class="rtype">${{t}}</span> · <span class="raddr">${{addr}}</span><br><span class="time">${{timeStr}}</span></div>`;
            }}).join('') : '<p class="stat">No recent calls</p>';
            recentEl.querySelectorAll('.recent-item').forEach(el => {{
                el.addEventListener('click', () => map.flyTo([+el.dataset.lat, +el.dataset.lng], 15));
            }});
            const busiestEl = document.getElementById('busiestArea');
            if (top5.length > 0) {{
                const b = top5[0];
                const addr = (b.incidents[0] && b.incidents[0].address) || (b.lat.toFixed(4) + ', ' + b.lng.toFixed(4));
                const near = nearestStation(b);
                const stLine = near ? ' · Nearest: ' + near.name + ' (' + near.dist.toFixed(1) + ' mi)' : '';
                busiestEl.innerHTML = 'Busiest area: <strong>' + b.count + ' call' + (b.count !== 1 ? 's' : '') + '</strong> at ' + addr + stLine + '.';
                busiestEl.style.display = 'block';
            }} else {{ busiestEl.innerHTML = ''; busiestEl.style.display = 'none'; }}
            const inRadiusRaw = filtered.filter(inChaserRadius).map(c => ({{ ...c, dist: chaserDist(c), eta: chaserEtaMin(chaserDist(c)), etaReal: chaserEtaReal(chaserDist(c)), ageMin: newestCallAgeMin(c), receivedAt: newestReceivedAt(c) }}));
            const makeIt = inRadiusRaw.filter(c => makeItInTime(c));
            const close = inRadiusRaw.filter(c => !makeItInTime(c) && closeEnough(c));
            const maybe = inRadiusRaw.filter(c => !makeItInTime(c) && !closeEnough(c) && c.ageMin <= 25);
            const rest = inRadiusRaw.filter(c => !makeItInTime(c) && !closeEnough(c) && c.ageMin > 25);
            const inRadius = [...makeIt.sort((a,b) => a.etaReal - b.etaReal), ...close.sort((a,b) => a.dist - b.dist), ...maybe.sort((a,b) => a.ageMin - b.ageMin), ...rest.sort((a,b) => a.dist - b.dist)];
            document.getElementById('chaserInRadius').textContent = inRadius.length;
            const closest = inRadius[0];
            let summary = '';
            if (inRadius.length === 0) summary = '—';
            else {{
                const parts = [];
                if (makeIt.length) parts.push(makeIt.length + " you'll make it");
                if (close.length) parts.push(close.length + ' close enough — go');
                parts.push('Closest: ' + closest.dist.toFixed(1) + ' mi, ~' + closest.etaReal + ' min');
                summary = parts.join(' · ');
            }}
            document.getElementById('chaserClosest').textContent = summary;
            const chaserListEl = document.getElementById('chaserRadiusList');
            const mapsUrl = (lat, lng) => 'https://www.google.com/maps/dir/?api=1&destination=' + lat + ',' + lng;
            chaserListEl.innerHTML = inRadius.slice(0, 10).map(c => {{
                const addr = (c.incidents[0] && c.incidents[0].address) || (c.lat + ', ' + c.lng);
                const type = (c.incidents[0] && c.incidents[0].type) || 'Call';
                const timeStr = c.receivedAt ? formatLocalTime(c.receivedAt) + ' · ' + c.ageMin + ' min ago' : c.ageMin + ' min ago';
                let badge = '';
                let responseLine = '';
                if (makeItInTime(c)) {{
                    badge = '<span class="chaser-badge go">You\\'ll make it</span>';
                    responseLine = '~' + c.etaReal + ' min away · Call ' + c.ageMin + ' min ago → <strong>You\\'ll make it in time</strong>';
                }} else if (closeEnough(c)) {{
                    badge = '<span class="chaser-badge close">Close — go</span>';
                    responseLine = c.dist.toFixed(1) + ' mi · <strong>Close enough — go</strong>';
                }} else if (c.ageMin <= 25) {{
                    badge = '<span class="chaser-badge maybe">Maybe in time</span>';
                    responseLine = '~' + c.etaReal + ' min · Call ' + c.ageMin + ' min ago';
                }} else {{
                    badge = '<span class="chaser-badge historic">' + c.ageMin + ' min ago</span>';
                    responseLine = '~' + c.etaReal + ' min · Call ' + c.ageMin + ' min ago';
                }}
                return `<div class="chaser-in-radius" data-lat="${{c.lat}}" data-lng="${{c.lng}}"><div class="row1"><span class="type">${{type}}</span><span class="dist">${{c.dist.toFixed(1)}} mi · ~${{c.etaReal}} min</span></div><span class="addr">${{addr}}</span><div class="chaser-time">${{timeStr}}</div><div class="chaser-response">${{responseLine}}</div><div class="row2">${{badge}} <a href="${{mapsUrl(c.lat, c.lng)}}" target="_blank" rel="noopener" class="chaser-maps">Open in Maps</a></div></div>`;
            }}).join('') || '<p class="stat">No calls in your radius. Increase radius or wait for new calls.</p>';
            chaserListEl.querySelectorAll('.chaser-in-radius').forEach(el => {{
                el.addEventListener('click', (e) => {{ if (!e.target.closest('a')) map.flyTo([+el.dataset.lat, +el.dataset.lng], 15); }});
            }});
            const hudM = document.getElementById('hudMain');
            const hudH = document.getElementById('hudHeadline');
            const hudZ = document.getElementById('hudZoom');
            const tot = filtered.reduce((s, c) => s + c.count, 0);
            if (hudM) hudM.innerHTML = '<strong>' + tot + '</strong> calls in view · <strong>' + filtered.length + '</strong> areas';
            if (hudH) hudH.textContent = (hotspotMeta && hotspotMeta.summary_headline) || (insights && insights.summary_headline) || '';
            if (hudZ && map) hudZ.textContent = 'Zoom ' + map.getZoom().toFixed(1) + ' · heat scales with zoom';
        }}

        function popupContent(cluster, clusterIndex) {{
            const list = (cluster.incidents || []).map(i => {{
                const t = i.type || 'Incident';
                const addr = i.address || '—';
                const received = i.received_at ? formatLocalTime(i.received_at) : '—';
                const age = i.received_at ? callAgeMin(i.received_at) : '';
                const timeStr = age !== '' ? received + ' · ' + age + ' min ago' : received;
                return `<div class="popup-item"><span class="type">${{t}}</span><br><span class="addr">${{addr}}</span><br><span class="time">${{timeStr}}</span></div>`;
            }}).join('');
            const st = nearestStation(cluster);
            const stCount = st ? (stationTotals[st.name] || 0) : 0;
            let stationLine = '';
            if (st) stationLine = '<div class="popup-chaser">Closest station: ' + st.name + ' (' + st.dist.toFixed(1) + ' mi). ' + stCount + ' calls in this station area.</div>';
            const dist = chaserDist(cluster);
            const etaReal = chaserEtaReal(dist);
            const inRad = inChaserRadius(cluster);
            const ageMin = newestCallAgeMin(cluster);
            const makeIt = inRad && ageMin <= 12 ? 'GO NOW — likely in time' : (inRad && ageMin <= 25 ? 'Maybe in time' : '');
            const mapsUrl = 'https://www.google.com/maps/dir/?api=1&destination=' + cluster.lat + ',' + cluster.lng;
            let chaserLine = `<div class="popup-chaser">${{dist.toFixed(1)}} mi from you · ~${{etaReal}} min drive (est.)</div>`;
            if (inRad) chaserLine += `<div class="popup-chaser">✓ In your chase radius</div>`;
            if (makeIt) chaserLine += `<div class="popup-chaser" style="color:#eab308">${{makeIt}}</div>`;
            chaserLine += `<div class="popup-chaser"><a href="${{mapsUrl}}" target="_blank" rel="noopener" style="color:#3b82f6">Google Maps</a> · <a href="http://maps.apple.com/?daddr=${{cluster.lat}},${{cluster.lng}}" style="color:#3b82f6">Apple Maps</a></div>`;
            const tier = cluster.tier || densityTier(cluster.count).tier;
            const tierLabel = cluster.tier === 'critical' ? 'Critical' : (cluster.tier === 'high' ? 'High' : (cluster.tier === 'medium' ? 'Medium' : 'Low'));
            const scoreLine = cluster.weighted_score != null ? ' <span style="color:#737373">(weighted ' + cluster.weighted_score + ')</span>' : '';
            const score24 = cluster.last_24h_score != null ? ' <span style="color:#737373">24h: ' + cluster.last_24h_score + '</span>' : '';
            const score7 = cluster.last_7d_score != null ? ' <span style="color:#737373">7d: ' + cluster.last_7d_score + '</span>' : '';
            const quality = cluster.quality || '';
            const qualityBadge = quality ? ' <span class="density-badge ' + quality + '">' + quality + '</span>' : '';
            const tierBadge = ' <span class="density-badge ' + tier + '">' + tierLabel + '</span>';
            const trendLine = (cluster.last_24h != null && cluster.previous_24h != null) ? '<div class="popup-chaser">Trend: Last 24h <strong>' + cluster.last_24h + '</strong> · Previous 24h ' + cluster.previous_24h + '</div>' : '';
            const typeCounts = {{}};
            (cluster.incidents || []).forEach(i => {{ const t = i.type || 'Unknown'; typeCounts[t] = (typeCounts[t] || 0) + 1; }});
            const total = cluster.incidents ? cluster.incidents.length : 0;
            const typeMix = total ? Object.entries(typeCounts).sort((a,b) => b[1] - a[1]).map(([t,n]) => Math.round(100 * n / total) + '% ' + t).join(', ') : '';
            const typeMixLine = typeMix ? '<div class="popup-chaser">Type mix: ' + typeMix + '</div>' : '';
            const exportBtn = (typeof clusterIndex === 'number' && window.__filteredForExport) ? '<button type="button" class="btn" style="margin-top:8px;width:100%" data-cluster-idx="' + clusterIndex + '">Export this hotspot (CSV)</button>' : '';
            const NEARBY_RADIUS_MI = 0.5;
            let totalInRadius = cluster.count;
            let others = [];
            let areaLine = '';
            if (window.__filteredForExport && window.__filteredForExport.length) {{
                others = window.__filteredForExport
                    .map((c, i) => ({{ c, i, d: haversineMi(cluster.lat, cluster.lng, c.lat, c.lng) }}))
                    .filter(x => x.d <= NEARBY_RADIUS_MI && x.d > 0);
                totalInRadius = cluster.count + others.reduce((s, x) => s + x.c.count, 0);
                if (totalInRadius > cluster.count) {{
                    areaLine = '<div class="popup-chaser" style="background:rgba(59,130,246,0.12);padding:8px;border-radius:6px;margin:8px 0;border-left:3px solid #3b82f6">';
                    areaLine += '<strong>Within ' + NEARBY_RADIUS_MI + ' mi:</strong> ' + totalInRadius + ' calls total in this area (this spot + ' + others.length + ' nearby hotspot' + (others.length !== 1 ? 's' : '') + ').</div>';
                    if (others.length > 0) {{
                        areaLine += '<div class="popup-chaser" style="font-size:11px;color:#a3a3a3">Nearby: ' + others.slice(0, 5).map(x => x.d.toFixed(2) + ' mi · ' + x.c.count + ' call' + (x.c.count !== 1 ? 's' : '')).join(' · ') + '</div>';
                    }}
                }}
            }}
            const titleText = cluster.count === 1
                ? (totalInRadius > 1 ? '1 call at this spot · ' + (totalInRadius - 1) + ' more within ' + NEARBY_RADIUS_MI + ' mi' : '1 call at this area')
                : cluster.count + ' calls at this area (calls close together)';
            const areaTier = densityTier(totalInRadius);
            const countText = totalInRadius > cluster.count
                ? cluster.count + ' here + ' + (totalInRadius - cluster.count) + ' nearby = <strong>' + totalInRadius + ' in area</strong>'
                : cluster.count + ' call' + (cluster.count !== 1 ? 's' : '');
            const tierLine = '<div class="popup-count">Activity: <span class="density-badge ' + areaTier.tier + '">' + areaTier.label + '</span>' + tierBadge + ' (' + countText + ')' + scoreLine + score24 + score7 + qualityBadge + '</div>';
            return `<div class="popup-title">${{titleText}}</div>${{tierLine}}${{areaLine}}${{trendLine}}${{typeMixLine}}${{list}}${{stationLine}}${{chaserLine}}${{exportBtn}}`;
        }}
        function exportClusterCsvByIndex(idx) {{
            const list = window.__filteredForExport;
            if (!list || !list[idx]) return;
            const c = list[idx];
            const rows = (c.incidents || []).map(i => [(i.type||''), (i.address||''), (i.received_at||''), c.lat, c.lng]);
            const csv = 'type,address,received_at,lat,lng\\n' + rows.map(r => r.map(x => '"' + String(x).replace(/"/g, '""') + '"').join(',')).join('\\n');
            const a = document.createElement('a');
            a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
            a.download = 'hotspot_' + c.lat.toFixed(4) + '_' + c.lng.toFixed(4) + '_' + new Date().toISOString().slice(0,10) + '.csv';
            a.click();
        }}

        function exportCsv() {{
            const filtered = getFilteredClusters();
            const rows = [];
            filtered.forEach(c => (c.incidents || []).forEach(i => rows.push([(i.type||''), (i.address||''), (i.received_at||''), i.lat, i.lng])));
            const header = 'type,address,received_at,lat,lng';
            const csv = header + '\\n' + rows.map(r => r.map(x => `"${{String(x).replace(/"/g, '""')}}"`).join(',')).join('\\n');
            const a = document.createElement('a');
            a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
            a.download = 'incident_hotspots_' + new Date().toISOString().slice(0,10) + '.csv';
            a.click();
        }}

        function exportGeojson() {{
            const filtered = getFilteredClusters();
            const features = [];
            filtered.forEach(c => (c.incidents || []).forEach(i => {{
                features.push({{ type: 'Feature', geometry: {{ type: 'Point', coordinates: [i.lng, i.lat] }}, properties: {{ type: i.type, address: i.address, received_at: i.received_at }} }});
            }}));
            const geojson = {{ type: 'FeatureCollection', features }};
            const a = document.createElement('a');
            a.href = 'data:application/geo+json;charset=utf-8,' + encodeURIComponent(JSON.stringify(geojson, null, 2));
            a.download = 'incident_hotspots_' + new Date().toISOString().slice(0,10) + '.geojson';
            a.click();
        }}

        map = L.map('map', {{ zoomControl: false }}).setView(defaultCenter, defaultZoom);
        L.control.zoom({{ position: 'topright' }}).addTo(map);
        baseDark = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap © CARTO', subdomains: 'abcd', maxZoom: 20
        }});
        baseSat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            attribution: 'Tiles © Esri', maxZoom: 19
        }});
        baseDark.addTo(map);
        L.control.layers({{ 'Dark map': baseDark, 'Satellite': baseSat }}, {{}}, {{ collapsed: true, position: 'topright' }}).addTo(map);
        document.querySelectorAll('.time-presets button').forEach(btn => {{
            btn.addEventListener('click', () => {{
                document.querySelectorAll('.time-presets button').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                if (btn.dataset.hours !== undefined) {{
                    currentTimeWindow = {{ type: 'hours', value: parseInt(btn.dataset.hours, 10) || 2 }};
                }} else {{
                    const d = parseInt(btn.dataset.days, 10);
                    currentTimeWindow = d < 0 ? {{ type: 'all', value: -1 }} : {{ type: 'days', value: d }};
                }}
                applyFilters();
            }});
        }});
        const allTimeBtn = document.querySelector('.time-presets button[data-days="-1"]');
        if (allTimeBtn) allTimeBtn.classList.add('active');
        const typeChecks = document.getElementById('typeChecks');
        allTypes.forEach(t => {{
            const label = document.createElement('label');
            const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
            label.innerHTML = `<input type="checkbox" checked data-type="${{esc(t)}}"> ${{esc(t)}}`;
            label.querySelector('input').addEventListener('change', () => {{
                selectedTypes = new Set([...document.querySelectorAll('#typeChecks input:checked')].map(x => x.dataset.type));
                applyFilters();
            }});
            typeChecks.appendChild(label);
        }});
        const typePresets = {{ fire: ['Fire', 'Structure Fire', 'Vehicle Fire'], medical: ['Medical', 'EMS'], mvc: ['MVC', 'Vehicle Accident'] }};
        document.querySelectorAll('.btn-type-preset').forEach(btn => {{
            btn.addEventListener('click', () => {{
                const preset = btn.dataset.preset;
                if (preset === 'all') {{
                    typeChecks.querySelectorAll('input').forEach(cb => cb.checked = true);
                }} else {{
                    const types = typePresets[preset] || [];
                    typeChecks.querySelectorAll('input').forEach(cb => {{
                        cb.checked = types.some(t => t.toLowerCase() === (cb.dataset.type || '').toLowerCase()) || types.length === 0;
                    }});
                    if (types.length && !typeChecks.querySelector('input:checked')) typeChecks.querySelectorAll('input').forEach(cb => cb.checked = true);
                }}
                selectedTypes = new Set([...document.querySelectorAll('#typeChecks input:checked')].map(x => x.dataset.type));
                applyFilters();
            }});
        }});
        document.getElementById('recencyWeight').addEventListener('change', applyFilters);
        document.getElementById('gradientAlt').addEventListener('change', applyFilters);
        document.getElementById('showMarkers').addEventListener('change', applyFilters);
        const sph = document.getElementById('showPointHeat');
        const hch = document.getElementById('hideClusterHeat');
        if (sph) sph.addEventListener('change', applyFilters);
        if (hch) hch.addEventListener('change', applyFilters);
        const addrSearch = document.getElementById('addressSearch');
        let searchT = null;
        if (addrSearch) {{
            addrSearch.addEventListener('input', () => {{ clearTimeout(searchT); searchT = setTimeout(applyFilters, 200); }});
            addrSearch.addEventListener('search', applyFilters);
        }}
        const recentOnlyCb = document.getElementById('recentOnly');
        if (recentOnlyCb) recentOnlyCb.addEventListener('change', applyFilters);
        let geoMarkerLayer = null;
        document.getElementById('useGeoNearest') && document.getElementById('useGeoNearest').addEventListener('click', function() {{
            if (!navigator.geolocation) {{ alert('Geolocation not supported'); return; }}
            navigator.geolocation.getCurrentPosition(function(pos) {{
                window.__geoLat = pos.coords.latitude;
                window.__geoLng = pos.coords.longitude;
                if (geoMarkerLayer) map.removeLayer(geoMarkerLayer);
                geoMarkerLayer = L.layerGroup();
                L.circleMarker([window.__geoLat, window.__geoLng], {{ radius: 11, fillColor: '#3b82f6', color: '#fff', weight: 2, fillOpacity: 0.95 }}).bindPopup('Your GPS position (nearest list)').addTo(geoMarkerLayer);
                geoMarkerLayer.addTo(map);
                applyFilters();
            }}, function() {{ alert('Could not get location — check browser permissions'); }}, {{ enableHighAccuracy: true, timeout: 15000 }});
        }});
        document.getElementById('minimizePanel') && document.getElementById('minimizePanel').addEventListener('click', function() {{
            document.body.classList.add('panel-hidden');
        }});
        document.getElementById('togglePanel') && document.getElementById('togglePanel').addEventListener('click', function() {{
            document.body.classList.remove('panel-hidden');
        }});
        function updateStationLayer(show) {{
            if (stationLayer) map.removeLayer(stationLayer);
            stationLayer = null;
            if (show && stations.length > 0) {{
                stationLayer = L.layerGroup();
                stations.forEach(s => {{
                    const m = L.circleMarker([s.lat, s.lng], {{ radius: 10, fillColor: '#3b82f6', color: '#fff', weight: 2, fillOpacity: 0.9 }});
                    m.bindPopup(s.name || 'Station');
                    stationLayer.addLayer(m);
                }});
                stationLayer.addTo(map);
            }}
        }}
        document.getElementById('showStation').addEventListener('change', e => updateStationLayer(e.target.checked));
        updateStationLayer(document.getElementById('showStation').checked);
        function updateChaserLayer(show) {{
            if (chaserLayer) map.removeLayer(chaserLayer);
            chaserLayer = null;
            if (show && chaser && chaser.lat != null) {{
                chaserLayer = L.layerGroup();
                const radiusM = (chaser.radius_miles || 15) * 1609.34;
                L.circle([chaser.lat, chaser.lng], {{ radius: radiusM, color: '#22c55e', weight: 3, fillOpacity: 0.12, fillColor: '#22c55e', dashArray: '8,8' }}).addTo(chaserLayer);
                const you = L.circleMarker([chaser.lat, chaser.lng], {{ radius: 14, fillColor: '#22c55e', color: '#fff', weight: 3, fillOpacity: 1 }});
                you.bindPopup('<strong>' + (chaser.name || 'You') + '</strong>' + (chaser.address ? '<br>' + chaser.address : '') + '<br>Chase radius: ' + (chaser.radius_miles || 15) + ' mi');
                chaserLayer.addLayer(you);
                chaserLayer.addTo(map);
            }}
        }}
        document.getElementById('showChaserRadius').addEventListener('change', e => updateChaserLayer(e.target.checked));
        updateChaserLayer(document.getElementById('showChaserRadius').checked);
        function updateCoverageZonesLayer(show) {{
            if (coverageZonesLayer) map.removeLayer(coverageZonesLayer);
            coverageZonesLayer = null;
            if (show && coverageZones && coverageZones.length > 0) {{
                coverageZonesLayer = L.layerGroup();
                coverageZones.forEach(z => {{
                    const radiusM = (z.radius_mi || 5) * 1609.34;
                    const color = z.color || '#94a3b8';
                    const circle = L.circle([z.lat, z.lng], {{ radius: radiusM, color: color, weight: 2, fillOpacity: 0.08, fillColor: color }});
                    const spotters = (z.spotters || []).join(' + ');
                    circle.bindPopup('<strong>' + (z.zone || 'Zone') + '</strong><br>' + spotters);
                    coverageZonesLayer.addLayer(circle);
                }});
                coverageZonesLayer.addTo(map);
            }}
        }}
        document.getElementById('showCoverageZones').addEventListener('change', e => updateCoverageZonesLayer(e.target.checked));
        updateCoverageZonesLayer(document.getElementById('showCoverageZones').checked);
        const coverageZonesListEl = document.getElementById('coverageZonesList');
        if (coverageZonesListEl && coverageZones && coverageZones.length) {{
            coverageZonesListEl.innerHTML = coverageZones.map(z => {{
                const spotters = (z.spotters || []).join(' + ');
                const color = z.color || '#94a3b8';
                return '<div style="font-size:11px;padding:6px 8px;margin:4px 0;border-radius:6px;border-left:4px solid ' + color + ';background:rgba(255,255,255,0.04)">' +
                    '<strong>' + (z.zone || '') + '</strong> — ' + spotters + '</div>';
            }}).join('');
        }}
        if (chaser && chaser.address) document.getElementById('chaserAddress').textContent = chaser.address;
        (function applySavedRadius() {{
            const saved = localStorage.getItem('chaser_radius_miles');
            if (saved !== null) {{
                const num = parseFloat(saved);
                if (!isNaN(num) && num >= 1 && num <= 50) {{
                    chaser.radius_miles = num;
                    const inp = document.getElementById('chaserRadiusInput');
                    if (inp) inp.value = num;
                }}
            }}
        }})();
        document.getElementById('chaserRadiusInput').addEventListener('change', function() {{
            let val = parseFloat(this.value);
            if (isNaN(val) || val < 1) val = 1;
            if (val > 50) val = 50;
            this.value = val;
            chaser.radius_miles = val;
            try {{ localStorage.setItem('chaser_radius_miles', String(val)); }} catch (e) {{}}
            updateChaserLayer(document.getElementById('showChaserRadius').checked);
            applyFilters();
        }});
        document.getElementById('chaserRadiusInput').addEventListener('input', function() {{
            let val = parseFloat(this.value);
            if (!isNaN(val) && val >= 1 && val <= 50) {{
                chaser.radius_miles = val;
                try {{ localStorage.setItem('chaser_radius_miles', String(val)); }} catch (e) {{}}
                updateChaserLayer(document.getElementById('showChaserRadius').checked);
                applyFilters();
            }}
        }});
        document.getElementById('centerOnMe').addEventListener('click', () => {{
            if (chaser && chaser.lat != null) {{
                map.flyTo([chaser.lat, chaser.lng], 12);
                updateChaserLayer(true);
                if (!document.getElementById('showChaserRadius').checked) document.getElementById('showChaserRadius').checked = true;
            }}
        }});
        function fetchLiveHotspotData() {{
            fetch(HOTSPOT_DATA_URL).then(r => r.ok ? r.json() : null).then(data => {{
                if (data && data.clusters) {{
                    allClusters = data.clusters;
                    if (data.station_rankings) stationRankings = data.station_rankings;
                    if (data.station_rankings_recent_4h) stationRankingsRecent4h = data.station_rankings_recent_4h;
                    if (data.station_rankings_1h) stationRankings1h = data.station_rankings_1h;
                    if (data.station_trend) stationTrend = data.station_trend;
                    if (data.likely_next) serverLikelyNext = data.likely_next;
                    if (data.hot_streets) hotStreets = data.hot_streets;
                    if (data.under_served_clusters) underServedClusters = data.under_served_clusters;
                    if (data.staging_suggestion !== undefined) stagingSuggestion = data.staging_suggestion;
                    if (data.meta) {{
                        if (data.meta.generated_at) hotspotMeta.generated_at = data.meta.generated_at;
                        if (data.meta.baseline_calls_this_hour_dow != null) hotspotMeta.baseline_calls_this_hour_dow = data.meta.baseline_calls_this_hour_dow;
                        if (data.meta.heat_radius != null) hotspotMeta.heat_radius = data.meta.heat_radius;
                        if (data.meta.heat_blur != null) hotspotMeta.heat_blur = data.meta.heat_blur;
                        if (data.meta.summary_headline) hotspotMeta.summary_headline = data.meta.summary_headline;
                    }}
                    if (data.insights) insights = data.insights;
                    if (data.point_heat && Array.isArray(data.point_heat)) pointHeatRaw = data.point_heat;
                    applyFilters();
                    if (data.meta && data.meta.generated_at) document.getElementById('updated').textContent = 'Updated ' + new Date(data.meta.generated_at).toLocaleString();
                }}
            }}).catch(() => {{}});
        }}
        document.getElementById('heatIntensity').addEventListener('input', function() {{
            const v = parseFloat(this.value) || 1;
            window.__heatIntensity = v;
            document.getElementById('heatIntensityValue').textContent = v.toFixed(1);
            applyFilters();
        }});
        document.getElementById('heatIntensity').addEventListener('change', function() {{
            const v = parseFloat(this.value) || 1;
            try {{ localStorage.setItem('heat_intensity', String(v)); }} catch(e) {{}}
        }});
        (function() {{ const s = localStorage.getItem('heat_intensity'); if (s) {{ const v = parseFloat(s); if (!isNaN(v) && v >= 0.3 && v <= 2) {{ document.getElementById('heatIntensity').value = v; document.getElementById('heatIntensityValue').textContent = v.toFixed(1); window.__heatIntensity = v; }} }} }})();
        document.getElementById('autoRefreshInterval').addEventListener('change', function() {{
            const sec = parseInt(this.value, 10) || 0;
            if (refreshTimer) {{ clearInterval(refreshTimer); refreshTimer = null; }}
            if (sec > 0) {{
                refreshTimer = setInterval(fetchLiveHotspotData, sec * 1000);
                fetchLiveHotspotData();
            }}
            try {{ localStorage.setItem('auto_refresh_sec', String(sec)); }} catch(e) {{}}
        }});
        (function() {{ const s = localStorage.getItem('auto_refresh_sec'); if (s) {{ const v = parseInt(s,10); const sel = document.getElementById('autoRefreshInterval'); if (v === 15 || v === 30 || v === 60) {{ sel.value = v; if (v > 0) {{ refreshTimer = setInterval(fetchLiveHotspotData, v * 1000); fetchLiveHotspotData(); }} }} }} }})();
        document.getElementById('fitAll').addEventListener('click', () => {{
            const filtered = getFilteredClusters();
            if (filtered.length === 0) return;
            const bounds = L.latLngBounds(filtered.map(c => [c.lat, c.lng]));
            if (chaser && chaser.lat != null) bounds.extend([chaser.lat, chaser.lng]);
            map.fitBounds(bounds, {{ padding: [24, 24], maxZoom: 14 }});
        }});
        document.getElementById('fitMyRadius').addEventListener('click', () => {{
            if (!chaser || chaser.lat == null) return;
            const r = (chaser.radius_miles || 15) * 1609.34;
            const circle = L.circle([chaser.lat, chaser.lng], {{ radius: r }});
            map.fitBounds(circle.getBounds(), {{ padding: [40, 40], maxZoom: 12 }});
        }});
        document.addEventListener('keydown', function(e) {{
            const tag = e.target && e.target.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (e.target && e.target.isContentEditable)) return;
            if (e.key === 'f' || e.key === 'F') {{ e.preventDefault(); document.getElementById('fitAll').click(); }}
            if (e.key === 'r' || e.key === 'R') {{ e.preventDefault(); document.getElementById('fitMyRadius').click(); }}
            if (e.key === 'b' || e.key === 'B') {{
                e.preventDefault();
                if (baseDark && baseSat && map) {{
                    if (map.hasLayer(baseDark)) {{ map.removeLayer(baseDark); baseSat.addTo(map); showToast('Satellite basemap'); }}
                    else {{ map.removeLayer(baseSat); baseDark.addTo(map); showToast('Dark basemap'); }}
                }}
            }}
            if (e.key === '?' || (e.shiftKey && e.key === '/')) {{
                e.preventDefault();
                document.getElementById('helpBackdrop') && document.getElementById('helpBackdrop').classList.add('open');
            }}
            if (e.key === 'Escape') document.getElementById('helpBackdrop') && document.getElementById('helpBackdrop').classList.remove('open');
        }});
        document.getElementById('btnHelp') && document.getElementById('btnHelp').addEventListener('click', () => document.getElementById('helpBackdrop').classList.add('open'));
        document.getElementById('helpClose') && document.getElementById('helpClose').addEventListener('click', () => document.getElementById('helpBackdrop').classList.remove('open'));
        document.getElementById('helpBackdrop') && document.getElementById('helpBackdrop').addEventListener('click', (e) => {{ if (e.target.id === 'helpBackdrop') e.target.classList.remove('open'); }});
        let __zoomApplyT = null;
        map.on('zoomend', () => {{ clearTimeout(__zoomApplyT); __zoomApplyT = setTimeout(applyFilters, 100); }});
        document.getElementById('exportCsv').addEventListener('click', exportCsv);
        document.getElementById('exportGeojson').addEventListener('click', exportGeojson);
        document.addEventListener('click', function(e) {{
            if (e.target && e.target.getAttribute && e.target.getAttribute('data-cluster-idx') !== null) {{
                exportClusterCsvByIndex(parseInt(e.target.getAttribute('data-cluster-idx'), 10));
            }}
        }});
        document.getElementById('copyMapLink').addEventListener('click', function() {{
            const c = map.getCenter();
            const z = map.getZoom();
            const params = new URLSearchParams();
            params.set('lat', c.lat.toFixed(5));
            params.set('lng', c.lng.toFixed(5));
            params.set('zoom', String(z));
            if (currentTimeWindow.type === 'hours') params.set('hours', String(currentTimeWindow.value));
            else if (currentTimeWindow.type === 'days' && currentTimeWindow.value > 0) params.set('days', String(currentTimeWindow.value));
            if (selectedTypes.size > 0 && selectedTypes.size < allTypes.length) params.set('types', [...selectedTypes].join(','));
            const url = location.href.split('?')[0] + '?' + params.toString();
            navigator.clipboard.writeText(url).then(() => showToast('Map link copied')).catch(() => showToast('Copy failed', true));
        }});
        (function applyUrlParams() {{
            const params = new URLSearchParams(location.search);
            const lat = params.get('lat');
            const lng = params.get('lng');
            const zoom = params.get('zoom');
            if (lat != null && lng != null && !isNaN(parseFloat(lat)) && !isNaN(parseFloat(lng))) {{
                map.setView([parseFloat(lat), parseFloat(lng)], zoom ? Math.min(18, Math.max(1, parseInt(zoom, 10))) : defaultZoom);
            }}
            const hours = params.get('hours');
            const days = params.get('days');
            if (hours != null && hours !== '') {{
                const h = parseInt(hours, 10);
                if (h === 2 || h === 6 || h === 24) {{
                    currentTimeWindow = {{ type: 'hours', value: h }};
                    document.querySelectorAll('.time-presets button').forEach(b => b.classList.remove('active'));
                    const btn = document.querySelector('.time-presets button[data-hours="' + h + '"]');
                    if (btn) btn.classList.add('active');
                }}
            }} else if (days != null && days !== '') {{
                const d = parseInt(days, 10);
                currentTimeWindow = d < 0 ? {{ type: 'all', value: -1 }} : {{ type: 'days', value: d }};
                document.querySelectorAll('.time-presets button').forEach(b => b.classList.remove('active'));
                const btn = document.querySelector('.time-presets button[data-days="' + d + '"]');
                if (btn) btn.classList.add('active');
            }}
            const typesParam = params.get('types');
            if (typesParam && typesParam.length) {{
                const want = new Set(typesParam.split(',').map(t => t.trim()).filter(Boolean));
                typeChecks.querySelectorAll('input').forEach(cb => {{ cb.checked = want.has(cb.dataset.type); }});
                selectedTypes = new Set([...document.querySelectorAll('#typeChecks input:checked')].map(x => x.dataset.type));
            }}
        }})();
        applyFilters();
        setInterval(applyFilters, 60000);
        (function() {{
            const params = new URLSearchParams(location.search);
            if (params.has('lat') && params.has('lng')) return;
            const filtered = getFilteredClusters();
            let lats = filtered.map(c => c.lat);
            let lngs = filtered.map(c => c.lng);
            if (chaser && chaser.lat != null) {{ lats = lats.concat(chaser.lat); lngs = lngs.concat(chaser.lng); }}
            if (lats.length > 0) {{
                map.fitBounds(L.latLngBounds([[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]]), {{ padding: [50, 50], maxZoom: 14 }});
            }}
        }})();
        document.getElementById('updated').textContent = 'Updated ' + new Date().toLocaleString();
    </script>
</body>
</html>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"[HOTSPOT] Map written: {path}")
        self._last_full_map_ts = time.time()
        self._map_regen_due = False
        return path
    
    def check_for_new_incidents(self):
        """Check for new incidents and send notifications (all configured agencies)."""
        try:
            active_incidents: List[Incident] = []
            for a_id in self.agency_ids:
                incidents = self.scraper.get_incidents(a_id)
                if incidents and hasattr(incidents, 'active') and incidents.active:
                    active_incidents.extend(incidents.active)
            seen_ids: Set[int] = set()
            unique_incidents: List[Incident] = []
            for inc in active_incidents:
                if inc.ID not in seen_ids:
                    seen_ids.add(inc.ID)
                    unique_incidents.append(inc)
            active_incidents = unique_incidents

            if not active_incidents:
                self.consecutive_errors = 0
                self.last_successful_check = datetime.datetime.now()
                return

            print(f"[DEBUG] Found {len(active_incidents)} active incidents")
            
            # Check each active incident
            for incident in active_incidents:
                incident_id = incident.ID
                
                # Skip if we've already sent this incident
                if incident_id in self.sent_incident_ids:
                    continue
                
                # Check if incident should be cleared (has ClosedDateTime)
                if hasattr(incident, 'ClosedDateTime') and incident.ClosedDateTime:
                    if incident.ClosedDateTime != datetime.datetime(year=1990, month=1, day=1):
                        # This incident is closed, skip it
                        print(f"[SKIP] Incident {incident_id} is closed (ClosedDateTime: {incident.ClosedDateTime})")
                        continue
                
                # This is a new incident - mark as sent IMMEDIATELY to prevent duplicates
                print(f"[NEW] New incident detected: {incident_id} - {incident.incident_type} at {incident.FullDisplayAddress}")
                self.sent_incident_ids.add(incident_id)
                self._append_hotspot(incident)
                payload = self._compute_hotspot_payload()
                now_m = time.time()
                if now_m - self._last_full_map_ts >= MAP_FULL_REGEN_MIN_SEC:
                    self.generate_hotspot_map(payload=payload)
                    self._last_full_map_ts = now_m
                    self._map_regen_due = False
                else:
                    self._save_hotspot_data_json(payload)
                    self._map_regen_due = True
                    print(f"[HOTSPOT] JSON updated; full HTML map in ≤{MAP_FULL_REGEN_MIN_SEC:.0f}s")

                # Now send notification
                pushover_sent = self.send_pushover_notification(incident)
                active_alert_sent = self.send_active_alert_webhook(incident)

                if pushover_sent:
                    print(f"[✓] Pushover notification sent for incident {incident_id}")
                else:
                    print(f"[✗] Failed to send Pushover for incident {incident_id}")

                if active_alert_sent:
                    print(f"[✓] Active Alert webhook sent for incident {incident_id}")
                else:
                    print(f"[✗] Failed to send Active Alert webhook for incident {incident_id}")
            
            # Clean up: Remove incident IDs that are no longer active
            current_active_ids = {inc.ID for inc in active_incidents}
            removed_ids = self.sent_incident_ids - current_active_ids
            if removed_ids:
                print(f"[CLEANUP] Removing {len(removed_ids)} cleared incidents from sent list")
                self.sent_incident_ids -= removed_ids
            
            # Mark successful check
            self.consecutive_errors = 0
            self.last_successful_check = datetime.datetime.now()
                
        except requests.exceptions.RequestException as e:
            self.consecutive_errors += 1
            print(f"[ERROR] Network error checking for incidents (error #{self.consecutive_errors}): {e}")
            if self.consecutive_errors >= self.max_consecutive_errors:
                print(f"[WARNING] {self.consecutive_errors} consecutive errors - will continue trying...")
        except Exception as e:
            self.consecutive_errors += 1
            print(f"[ERROR] Error checking for incidents (error #{self.consecutive_errors}): {e}")
            traceback.print_exc()
            # Continue running despite errors
    
    def _monitor_loop(self):
        """Main monitoring loop - runs in separate thread"""
        iteration = 0
        while self.running:
            try:
                iteration += 1
                print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] Check #{iteration}")
                
                self.check_for_new_incidents()
                self._flush_deferred_map()

                # Health check every 10 iterations
                if iteration % 10 == 0:
                    print(f"[HEALTH] System running - {len(self.sent_incident_ids)} incidents tracked")
                    if self.last_successful_check:
                        time_since_success = (datetime.datetime.now() - self.last_successful_check).total_seconds()
                        print(f"[HEALTH] Last successful check: {int(time_since_success)} seconds ago")
                
                # Minimal delay to prevent 100% CPU and race conditions
                # Even with CHECK_INTERVAL=0, we need a tiny delay to prevent duplicate detections
                time.sleep(0.1)
                    
            except KeyboardInterrupt:
                print("\n[STOP] Stopping monitor...")
                self.running = False
                break
            except Exception as e:
                print(f"[ERROR] Unexpected error in monitor loop: {e}")
                traceback.print_exc()
                # Continue running despite errors - wait a bit longer before retry
                time.sleep(10)
        
        print("\n[STOP] Monitor loop stopped.")
    
    def _watchdog(self):
        """Watchdog thread that monitors the main loop and restarts if needed"""
        print("[WATCHDOG] Watchdog thread started")
        check_count = 0
        
        while self.running:
            try:
                time.sleep(60)  # Check every minute
                check_count += 1
                
                # Check if monitor thread is still alive
                if self.monitor_thread and not self.monitor_thread.is_alive():
                    print(f"[WATCHDOG] WARNING: Monitor thread died! Restarting...")
                    self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=False, name="IncidentMonitor")
                    self.monitor_thread.start()
                    print(f"[WATCHDOG] Monitor thread restarted")
                
                # Log watchdog status every 10 minutes
                if check_count % 10 == 0:
                    status = "ALIVE" if (self.monitor_thread and self.monitor_thread.is_alive()) else "DEAD"
                    print(f"[WATCHDOG] Status check - Monitor thread: {status}")
                    if self.last_successful_check:
                        time_since = (datetime.datetime.now() - self.last_successful_check).total_seconds()
                        if time_since > 300:  # 5 minutes
                            print(f"[WATCHDOG] WARNING: No successful check in {int(time_since)} seconds")
                
            except Exception as e:
                print(f"[WATCHDOG] Error in watchdog: {e}")
                traceback.print_exc()
                # Continue watchdog even on errors
                time.sleep(30)
        
        print("[WATCHDOG] Watchdog stopped")
    
    def run(self):
        """Start the monitoring system with watchdog"""
        print("=" * 60)
        print("Simple Incident Monitor - Pushover Only")
        print("24/7 Operation with Auto-Recovery")
        print("=" * 60)
        print(f"Monitoring Agencies: {', '.join(self.agency_ids)}")
        print(f"Check Interval: {CHECK_INTERVAL} seconds")
        print(f"Pushover User: {PUSHOVER_USER_KEY[:10]}...")
        print("=" * 60)
        print("Press Ctrl+C to stop")
        print()
        
        # Start monitor thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=False, name="IncidentMonitor")
        self.monitor_thread.start()
        print("[START] Monitor thread started")
        
        # Start watchdog thread
        self.watchdog_thread = threading.Thread(target=self._watchdog, daemon=True, name="Watchdog")
        self.watchdog_thread.start()
        print("[START] Watchdog thread started")
        
        try:
            # Keep main thread alive and wait for monitor thread
            while self.running and self.monitor_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[STOP] Stopping monitor...")
            self.running = False
            
            # Wait for threads to finish
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5)
            if self.watchdog_thread:
                self.watchdog_thread.join(timeout=2)
        
        print("\n[STOP] Monitor stopped.")


def main():
    """Main entry point"""
    import sys
    argv = sys.argv[1:] if len(sys.argv) > 1 else []

    if "--help" in argv or "-h" in argv:
        print("Usage: python active_alert_listener.py [option]")
        print("  (no option)     Run monitor; JSON updates every new incident; HTML map debounced")
        print("  --generate-map  Write incident_hotspot_map.html + JSON from history and exit")
        print("  --test-call     Test Pushover + one hotspot + map, then exit")
        print("Env: PUSHOVER_USER_KEY, PUSHOVER_APP_TOKEN, MAP_FULL_REGEN_MIN_SEC (default 20), ACTIVE_ALERT_WEBHOOK_URL")
        return

    if "--generate-map" in argv:
        monitor = SimpleIncidentMonitor(AGENCY_IDS)
        path = monitor.generate_hotspot_map()
        print(f"Map written: {path}")
        print(f"Open in browser: file:///{path.replace(os.sep, '/')}")
        return

    if "--test-call" in argv:
        monitor = SimpleIncidentMonitor(AGENCY_IDS)
        fake = type("Incident", (), {
            "ID": 0,
            "Latitude": 36.3320,
            "Longitude": -94.1185,
            "incident_type": "TEST ALERT",
            "FullDisplayAddress": "123 Test St, Rogers, AR (test call)",
            "CallReceivedDateTime": datetime.datetime.utcnow(),
        })()
        monitor._append_hotspot(fake)
        monitor.generate_hotspot_map()
        ok = monitor.send_pushover_notification(fake)
        print(f"Test Pushover: {'sent' if ok else 'failed'}")
        print(f"Hotspot map: {HOTSPOT_MAP_FILE}")
        return

    monitor = SimpleIncidentMonitor(AGENCY_IDS)
    monitor.generate_hotspot_map()
    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted by user")
    except Exception as e:
        print(f"[FATAL] Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

