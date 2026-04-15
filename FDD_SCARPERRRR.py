#!/usr/bin/env python3
"""
FDD CAD Scraper - Fire Department Dispatch Computer-Aided Dispatch Scraper
A modular scraper system for monitoring fire department dispatch data
"""

import base64
import hashlib
import json
import requests
import datetime
import math
import time
import threading
from urllib import request
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from prodict import Prodict


class Unit(Prodict):
    UnitID: str
    PulsePointDispatchStatus: str
    UnitClearedDateTime: datetime.datetime


class Incident(Prodict):
    ID: int
    AgencyID: any
    Latitude: float
    Longitude: float
    PublicLocaiton: int
    PulsePointIncidentCallType: str
    IsShareable: bool
    AlarmLevel: int
    CallReceivedDateTime: datetime.datetime
    ClosedDateTime: datetime.datetime
    FullDisplayAddress: str
    MedicalEmergencyDisplayAddress: str
    AddressTruncated: int
    Unit: List[Unit]
    StreetNumber: int
    CommonPlaceName: any
    uid: str
    incident_type: str
    significant_locations: List[str]
    coords: Tuple[float, float]
    agency_name: str
    
    def init(self):
        self.CallReceivedDateTime = datetime.datetime(year=1990, month=1, day=1)


class Incidents(Prodict):
    alerts: any
    active: List[Incident]
    recent: List[Incident]
    
    def init(self):
        self.active = []
        self.recent = []


@dataclass
class Geofence:
    """Geographic boundary for monitoring incidents"""
    name: str
    center_lat: float
    center_lon: float
    radius_miles: float
    polygon_points: List[Tuple[float, float]] = None  # For custom shapes
    color: str = "#FF0000"  # Red by default
    
    def contains_point(self, lat: float, lon: float) -> bool:
        """Check if a point is within the geofence"""
        if self.polygon_points:
            return self._point_in_polygon(lat, lon, self.polygon_points)
        else:
            # Circular geofence
            distance = self._calculate_distance(
                self.center_lat, self.center_lon, lat, lon
            )
            return distance <= self.radius_miles
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in miles using Haversine formula"""
        R = 3959  # Earth's radius in miles
        
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = (math.sin(dlat/2) * math.sin(dlat/2) + 
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
             math.sin(dlon/2) * math.sin(dlon/2))
        
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    
    def _point_in_polygon(self, lat: float, lon: float, polygon: List[Tuple[float, float]]) -> bool:
        """Ray casting algorithm for point-in-polygon test"""
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if lat > min(p1y, p2y):
                if lat <= max(p1y, p2y):
                    if lon <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (lat - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or lon <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside


@dataclass
class GeofencedIncident:
    """Incident data with geofence information"""
    incident: Incident
    geofence_name: str
    distance_from_center: float
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


class FDDCADScraper:
    """Main scraper class for Fire Department Dispatch CAD data"""
    
    def __init__(self):
        self.agencies = {}
        self.incident_types = {}
        self.geofences = {}
        self.geofenced_incidents = []
        self.monitoring_active = False
        self.monitoring_thread = None
        
        # Circuit breaker for API failures
        self.circuit_breaker = {
            'failure_count': 0,
            'last_failure_time': None,
            'is_open': False,
            'failure_threshold': 5,  # Open circuit after 5 consecutive failures
            'recovery_timeout': 300  # 5 minutes before trying again
        }
        
        # Fallback data cache
        self.fallback_data = {}
        self.fallback_data_age = {}
        self.fallback_max_age = 1800  # 30 minutes
        
        self._load_incident_types()
        self._load_agencies()
    
    def _is_circuit_breaker_open(self):
        """Check if circuit breaker is open"""
        if not self.circuit_breaker['is_open']:
            return False
        
        # Check if enough time has passed to try again
        if self.circuit_breaker['last_failure_time']:
            time_since_failure = time.time() - self.circuit_breaker['last_failure_time']
            if time_since_failure > self.circuit_breaker['recovery_timeout']:
                print("🔄 Circuit breaker: Attempting recovery after timeout")
                self.circuit_breaker['is_open'] = False
                self.circuit_breaker['failure_count'] = 0
                return False
        
        return True
    
    def _record_api_success(self):
        """Record successful API call"""
        self.circuit_breaker['failure_count'] = 0
        self.circuit_breaker['is_open'] = False
        self.circuit_breaker['last_failure_time'] = None
    
    def _record_api_failure(self):
        """Record failed API call"""
        self.circuit_breaker['failure_count'] += 1
        self.circuit_breaker['last_failure_time'] = time.time()
        
        if self.circuit_breaker['failure_count'] >= self.circuit_breaker['failure_threshold']:
            self.circuit_breaker['is_open'] = True
            print(f"⚠️ Circuit breaker OPEN: {self.circuit_breaker['failure_count']} consecutive failures")
            print(f"⚠️ Will retry in {self.circuit_breaker['recovery_timeout']} seconds")
    
    def _get_fallback_data(self, agency_id):
        """Get fallback data if available and not too old"""
        if agency_id in self.fallback_data:
            data_age = time.time() - self.fallback_data_age.get(agency_id, 0)
            if data_age < self.fallback_max_age:
                print(f"[FALLBACK] Using fallback data for agency {agency_id} (age: {data_age:.0f}s)")
                return self.fallback_data[agency_id]
            else:
                print(f"[FALLBACK] Fallback data for agency {agency_id} is too old (age: {data_age:.0f}s)")
        return {}
    
    def _store_fallback_data(self, agency_id, data):
        """Store data as fallback for future use"""
        self.fallback_data[agency_id] = data
        self.fallback_data_age[agency_id] = time.time()
        print(f"[STORED] Stored fallback data for agency {agency_id}")
    
    def _load_incident_types(self):
        """Load incident type mappings from JSON file"""
        try:
            with open("incident_types.json", 'r', encoding='utf-8') as f:
                self.incident_types = json.loads(f.read())
        except Exception as e:
            print(f"Error loading incident types: {e}")
            # Fallback to basic incident types
            self.incident_types = {
                "FIRE": "Structure Fire",
                "MED": "Medical Emergency", 
                "MVA": "Motor Vehicle Accident",
                "HAZMAT": "Hazardous Materials",
                "RESCUE": "Rescue Operation",
                "ALARM": "Fire Alarm",
                "SMOKE": "Smoke Investigation",
                "GAS": "Gas Leak",
                "WIRES": "Downed Power Lines",
                "WATER": "Water Emergency",
                "TREE": "Tree Down",
                "LOCKOUT": "Lockout Service",
                "FALSE": "False Alarm",
                "UNKNOWN": "Unknown Emergency"
            }
    
    def _load_agencies(self):
        """Load available fire department agencies from real API"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://web.pulsepoint.org/',
                'Origin': 'https://web.pulsepoint.org'
            }
            
            # Use the real working API endpoint from browser console
            url = "https://api.pulsepoint.org/v1/webapp?resource=agencies&agencyid=04600"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                agencies_data = response.json()
                print(f"Successfully loaded agencies from real API: {url}")
                
                # Process the agencies data
                if isinstance(agencies_data, list):
                    for agency in agencies_data:
                        if 'agencyid' in agency:
                            self.agencies[agency['agencyid']] = agency
                elif isinstance(agencies_data, dict) and 'agencies' in agencies_data:
                    for agency in agencies_data['agencies']:
                        if 'agencyid' in agency:
                            self.agencies[agency['agencyid']] = agency
                
                print(f"Loaded {len(self.agencies)} agencies from real PulsePoint API")
            else:
                raise Exception(f"API returned status code: {response.status_code}")
                
        except Exception as e:
            print(f"Error loading agencies from real API: {e}")
            print("Using fallback agencies with real agency ID from browser storage...")
            # Fallback to known agencies - using the real agency ID 04600 from browser storage
            self.agencies = {
                "04600": {
                    "agencyid": "04600",
                    "agencyname": "Rogers Fire Department",
                    "agency_initials": "RFD",
                    "short_agencyname": "Rogers Fire",
                    "latitude": 36.3320,
                    "longitude": -94.1185,
                    "state": "AR",
                    "city": "Rogers"
                },
                "4600": {
                    "agencyid": "4600",
                    "agencyname": "Rogers Fire Department",
                    "agency_initials": "RFD",
                    "short_agencyname": "Rogers Fire",
                    "latitude": 36.3320,
                    "longitude": -94.1185,
                    "state": "AR",
                    "city": "Rogers"
                }
            }
    
    def str2time(self, s):
        """Convert string timestamp to datetime object"""
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")

    def get_incidents(self, a_id) -> Incidents:
        """Get incidents for a specific agency"""
        def fix_dict(d):
            if d == 'null': return None
            if isinstance(d, dict):
                for k, v in d.items():
                    # Skip type annotation keys that cause issues
                    if k in ['__origin__', '__args__', '__module__', '__qualname__']:
                        continue
                    d[k] = fix_dict(v)
            if isinstance(d, list):
                for i, v in enumerate(d):
                    d[i] = fix_dict(v)
            return d
        
        def convert_incidents(i_list):
            if type(i_list) != list: return
            conversions = ["CallReceivedDateTime", "ClosedDateTime", "UnitClearedDateTime"]
            for i, x in enumerate(i_list):
                for c in conversions:
                    if c in x and type(x[c]) == str:
                        x[c] = self.str2time(x[c])
                if "Unit" in x:
                    convert_incidents(x["Unit"])
                if "PulsePointIncidentCallType" in x:
                    x["incident_type"] = self.incident_types.get(x["PulsePointIncidentCallType"], "Unknown")
                if "Latitude" in x:
                    x['coords'] = (float(x['Latitude']), float(x['Longitude']))
                    x['uid'] = x['ID']
        
        raw = None
        try:
            api_data = self._agency_raw_data(a_id)
            
            # Handle different response formats from the new API
            if 'incidents' in api_data:
                raw = api_data['incidents']
                print(f"[FOUND] Found incidents wrapper, extracting active/recent data")
            elif isinstance(api_data, list):
                # If the API returns a list directly, structure it properly
                raw = {
                    'active': [incident for incident in api_data if incident.get('status') == 'active'],
                    'recent': [incident for incident in api_data if incident.get('status') == 'recent']
                }
            elif isinstance(api_data, dict) and ('active' in api_data or 'recent' in api_data):
                # API already provides active/recent structure - PulsePoint separates them!
                # IMPORTANT: If PulsePoint says it's in "recent", it's CLOSED - trust the API
                raw = api_data
                
                # Convert all incidents first (both active and recent)
                if 'active' in raw and isinstance(raw['active'], list):
                    convert_incidents(raw['active'])
                if 'recent' in raw and isinstance(raw['recent'], list):
                    convert_incidents(raw['recent'])
                    # Mark all recent incidents as having ClosedDateTime (they're closed by definition)
                    for incident in raw['recent']:
                        if isinstance(incident, dict):
                            # If no ClosedDateTime, set a default one to ensure they stay in recent
                            if not incident.get('ClosedDateTime') or incident.get('ClosedDateTime') == datetime.datetime(year=1990, month=1, day=1):
                                # Use CallReceivedDateTime + 1 hour as estimated close time
                                if incident.get('CallReceivedDateTime'):
                                    call_time = incident.get('CallReceivedDateTime')
                                    if isinstance(call_time, str):
                                        call_time = self.str2time(call_time)
                                    # Estimate close time as 1 hour after call (typical for lift assists)
                                    estimated_close = call_time + datetime.timedelta(hours=1)
                                    incident['ClosedDateTime'] = estimated_close
                                    print(f"[PULSEPOINT] Recent incident {incident.get('ID', 'Unknown')} - set estimated ClosedDateTime: {estimated_close}")
                
                # IMPORTANT: Convert ClosedDateTime FIRST before checking
                # Apply additional clearing logic to "active" incidents from API
                if 'active' in raw and isinstance(raw['active'], list):
                    current_time = datetime.datetime.now()
                    still_active = []
                    moved_to_recent = []
                    for incident in raw['active']:
                        # Ensure ClosedDateTime is converted if it's a string
                        closed_time = incident.get('ClosedDateTime')
                        if closed_time and isinstance(closed_time, str):
                            try:
                                closed_time = self.str2time(closed_time)
                                incident['ClosedDateTime'] = closed_time
                            except Exception as e:
                                print(f"Error converting ClosedDateTime: {e}")
                                closed_time = None
                        
                        call_time = incident.get('CallReceivedDateTime')
                        if call_time and isinstance(call_time, str):
                            try:
                                call_time = self.str2time(call_time)
                                incident['CallReceivedDateTime'] = call_time
                            except Exception:
                                pass
                        
                        # PRIMARY CHECK: ClosedDateTime is the FIRST and MOST IMPORTANT check
                        if closed_time and closed_time != datetime.datetime(year=1990, month=1, day=1):
                            moved_to_recent.append(incident)
                            print(f"[CLOSED] Incident {incident.get('ID', 'Unknown')} has ClosedDateTime: {closed_time} - moved to recent")
                        elif call_time:
                            # Secondary checks only if no ClosedDateTime
                            incident_age_hours = (current_time - call_time).total_seconds() / 3600
                            # Medical calls older than 1 hour
                            incident_type_lower = str(incident.get('CallType', '') or incident.get('Type', '') or incident.get('incident_type', '')).lower()
                            is_medical = 'medical' in incident_type_lower or 'med' in incident_type_lower
                            if is_medical and incident_age_hours > 1.0:
                                moved_to_recent.append(incident)
                                print(f"[CLOSED] Medical incident {incident.get('ID', 'Unknown')} older than 1 hour - moved to recent")
                            elif incident_age_hours > 1.5:
                                moved_to_recent.append(incident)
                                print(f"[CLOSED] Incident {incident.get('ID', 'Unknown')} older than 1.5 hours - moved to recent")
                        else:
                            # No ClosedDateTime and no CallReceivedDateTime - keep as active (new incident)
                            still_active.append(incident)
                            print(f"[NEW] Incident {incident.get('ID', 'Unknown')} has no ClosedDateTime - keeping as active")
                    
                    # Update the raw structure
                    raw['active'] = still_active
                    if 'recent' not in raw:
                        raw['recent'] = []
                    raw['recent'].extend(moved_to_recent)
                    if moved_to_recent:
                        print(f"[CLEARED] Moved {len(moved_to_recent)} incidents from API active to recent based on ClosedDateTime")
            else:
                # Try to extract incidents from the response
                raw = api_data
            
            if raw:
                # Convert all incidents first
                try:
                    if 'active' in raw:
                        convert_incidents(raw['active'])
                    if 'recent' in raw:
                        convert_incidents(raw['recent'])
                    fix_dict(raw)
                except Exception as e:
                    print(f"Error during incident conversion: {e}")
                    # Continue without conversion
                
                # Debug: Print raw data structure
                print(f"[FOUND] Raw API data type: {type(raw)}")
                if isinstance(raw, list):
                    print(f"[FOUND] Raw list length: {len(raw)}")
                    if len(raw) > 0:
                        print(f"[FOUND] First incident keys: {list(raw[0].keys()) if raw[0] else 'Empty'}")
                        print(f"[FOUND] First incident ClosedDateTime: {raw[0].get('ClosedDateTime') if raw[0] else 'N/A'}")
                        print(f"[FOUND] First incident CallReceivedDateTime: {raw[0].get('CallReceivedDateTime') if raw[0] else 'N/A'}")
                        print(f"[FOUND] First incident incident_type: {raw[0].get('incident_type') if raw[0] else 'N/A'}")
                        print(f"[FOUND] First incident FullDisplayAddress: {raw[0].get('FullDisplayAddress') if raw[0] else 'N/A'}")
                        # Check for status fields
                        print(f"[FOUND] First incident Status: {raw[0].get('Status') if raw[0] else 'N/A'}")
                        print(f"[FOUND] First incident CallStatus: {raw[0].get('CallStatus') if raw[0] else 'N/A'}")
                        print(f"[FOUND] First incident IsCleared: {raw[0].get('IsCleared') if raw[0] else 'N/A'}")
                elif isinstance(raw, dict):
                    print(f"[FOUND] Raw dict keys: {list(raw.keys())}")
                    if 'active' in raw:
                        print(f"[FOUND] Active incidents count: {len(raw['active'])}")
                        if len(raw['active']) > 0:
                            first_active = raw['active'][0]
                            print(f"[FOUND] First active incident ClosedDateTime: {first_active.get('ClosedDateTime') if isinstance(first_active, dict) else 'N/A'}")
                            print(f"[FOUND] First active incident Status: {first_active.get('Status') if isinstance(first_active, dict) else 'N/A'}")
                    if 'recent' in raw:
                        print(f"[FOUND] Recent incidents count: {len(raw['recent'])}")
                        if len(raw['recent']) > 0:
                            first_recent = raw['recent'][0]
                            print(f"[FOUND] First recent incident ClosedDateTime: {first_recent.get('ClosedDateTime') if isinstance(first_recent, dict) else 'N/A'}")
                            print(f"[FOUND] First recent incident Status: {first_recent.get('Status') if isinstance(first_recent, dict) else 'N/A'}")
                
                # If we have a flat list of incidents, separate them by ClosedDateTime
                if isinstance(raw, list):
                    active_incidents = []
                    recent_incidents = []
                    current_time = datetime.datetime.now()
                    
                    for incident in raw:
                        # Ensure ClosedDateTime is converted if it's a string
                        closed_time = incident.get('ClosedDateTime')
                        if closed_time and isinstance(closed_time, str):
                            try:
                                closed_time = self.str2time(closed_time)
                                incident['ClosedDateTime'] = closed_time
                            except Exception as e:
                                print(f"Error converting ClosedDateTime: {e}")
                                closed_time = None
                        
                        call_time = incident.get('CallReceivedDateTime')
                        if call_time and isinstance(call_time, str):
                            try:
                                call_time = self.str2time(call_time)
                                incident['CallReceivedDateTime'] = call_time
                            except Exception:
                                pass
                        
                        incident_id = incident.get('ID', 'Unknown')
                        incident_type = incident.get('incident_type', 'Unknown')
                        address = incident.get('FullDisplayAddress', 'Unknown')
                        
                        print(f"DEBUG Incident {incident_id}: {incident_type} at {address}")
                        print(f"DEBUG   ClosedDateTime = {closed_time}, CallTime = {call_time}")
                        
                        # Determine if incident is cleared using multiple criteria
                        is_cleared = False
                        clear_reason = ""
                        
                        # PRIMARY METHOD: Check if incident has a valid ClosedDateTime (INSTANT CLEARING)
                        # This is the MOST IMPORTANT check - if ClosedDateTime exists and is valid, incident is CLOSED
                        if closed_time and closed_time != datetime.datetime(year=1990, month=1, day=1):
                            is_cleared = True
                            clear_reason = "has ClosedDateTime - INSTANT CLEAR"
                            print(f"[CLOSED] Incident {incident_id} has ClosedDateTime: {closed_time}")
                        
                        # Method 1B: Check if incident is marked as cleared in any way (INSTANT CLEARING)
                        if not is_cleared:
                            # Check for various cleared indicators - check all possible fields
                            cleared_indicators = [
                                incident.get('IsCleared', False),
                                incident.get('Cleared', False),
                                incident.get('Status') == 'Cleared',
                                incident.get('Status') == 'Closed',
                                incident.get('Status') == 'Completed',
                                incident.get('Status') == 'Dispatched',
                                incident.get('ClearedDateTime'),
                                incident.get('ClosedDateTime'),
                                incident.get('EndDateTime'),
                                incident.get('CompletionDateTime'),
                                str(incident.get('Status', '')).lower() in ['cleared', 'closed', 'completed', 'dispatched'],
                                str(incident.get('CallStatus', '')).lower() in ['cleared', 'closed', 'completed', 'dispatched'],
                            ]
                            
                            if any(cleared_indicators):
                                is_cleared = True
                                clear_reason = "marked as cleared in API - INSTANT CLEAR"
                        
                        # Method 1C: Check if incident appears in "recent" list from API (it's already closed)
                        # This is a fallback if the API separates active/recent but we're getting both
                        if not is_cleared:
                            # Check if there's a LastUpdateDateTime that's significantly older than CallReceivedDateTime
                            last_update = incident.get('LastUpdateDateTime') or incident.get('LastUpdate')
                            if last_update and call_time:
                                try:
                                    if isinstance(last_update, str):
                                        last_update_dt = datetime.datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                                    else:
                                        last_update_dt = last_update
                                    
                                    # If last update was more than 1 hour ago and call was more than 1 hour ago, likely closed
                                    time_since_update = (current_time - last_update_dt).total_seconds() / 3600
                                    time_since_call = (current_time - call_time).total_seconds() / 3600
                                    if time_since_update > 1.0 and time_since_call > 1.0:
                                        is_cleared = True
                                        clear_reason = f"no updates for {time_since_update:.1f}h - likely closed"
                                except Exception:
                                    pass
                        
                        # Method 2: Check if incident is older than 1 hour (MORE AGGRESSIVE clearing for medical calls)
                        if not is_cleared and call_time:
                            incident_age_hours = (current_time - call_time).total_seconds() / 3600
                            # Medical emergencies typically clear faster
                            incident_type_lower = str(incident.get('CallType', '') or incident.get('Type', '')).lower()
                            is_medical = 'medical' in incident_type_lower or 'med' in incident_type_lower
                            
                            if is_medical and incident_age_hours > 1.0:  # 1 hour for medical calls
                                is_cleared = True
                                clear_reason = f"medical call older than 1 hour ({incident_age_hours:.1f}h)"
                            elif incident_age_hours > 1.5:  # 1.5 hours for other calls
                                is_cleared = True
                                clear_reason = f"older than 1.5 hours ({incident_age_hours:.1f}h)"
                        
                        # Method 3: Check if incident has no units assigned and is older than 20 minutes
                        if not is_cleared and call_time and not incident.get('Unit'):
                            incident_age_minutes = (current_time - call_time).total_seconds() / 60
                            if incident_age_minutes > 20:  # 20 minutes for incidents with no units
                                is_cleared = True
                                clear_reason = f"no units assigned and older than 20 minutes ({incident_age_minutes:.0f}m)"
                        
                        # Method 4: Check if incident has been active for more than 3 hours (safety net)
                        if not is_cleared and call_time:
                            incident_age_hours = (current_time - call_time).total_seconds() / 3600
                            if incident_age_hours > 3.0:  # 3 hours maximum safety net
                                is_cleared = True
                                clear_reason = f"older than 3 hours ({incident_age_hours:.1f}h) - safety clear"
                        
                        if is_cleared:
                            recent_incidents.append(incident)
                            print(f"DEBUG -> Moved to RECENT ({clear_reason})")
                        else:
                            # No ClosedDateTime = NEW or ACTIVE incident
                            active_incidents.append(incident)
                            print(f"DEBUG -> Moved to ACTIVE (no ClosedDateTime - new/active incident)")
                            
                            # DEBUG: Show available fields for uncleared incidents
                            if len(active_incidents) <= 3:  # Only show for first few incidents to avoid spam
                                available_fields = [k for k in incident.keys() if incident.get(k) is not None]
                                print(f"DEBUG - Available fields: {available_fields}")
                    
                    raw = {
                        'active': active_incidents,
                        'recent': recent_incidents
                    }
                    print(f"DEBUG Separated incidents - Active: {len(active_incidents)}, Recent: {len(recent_incidents)}")
            
        except Exception as e:
            print(f"Error getting incidents: {e}")
            return Incidents()
        
        # Clean the raw data before creating Incidents object
        def clean_data(data):
            if isinstance(data, dict):
                cleaned = {}
                for k, v in data.items():
                    if k not in ['__origin__', '__args__', '__module__', '__qualname__']:
                        cleaned[k] = clean_data(v)
                return cleaned
            elif isinstance(data, list):
                return [clean_data(item) for item in data]
            else:
                return data
        
        # Always create incidents manually to avoid Prodict issues
        try:
            cleaned_raw = clean_data(raw)
            print(f"DEBUG Cleaned raw keys: {list(cleaned_raw.keys()) if isinstance(cleaned_raw, dict) else 'Not a dict'}")
            
            incidents = Incidents()
            if isinstance(cleaned_raw, dict):
                if 'active' in cleaned_raw:
                    incidents.active = cleaned_raw['active']
                    print(f"[SET] Set {len(incidents.active)} active incidents")
                if 'recent' in cleaned_raw:
                    incidents.recent = cleaned_raw['recent']
                    print(f"[SET] Set {len(incidents.recent)} recent incidents")
            else:
                print(f"[FOUND] Cleaned raw is not a dict: {type(cleaned_raw)}")
            
            return incidents
        except Exception as e:
            print(f"Error in manual incident creation: {e}")
            # Return empty incidents as fallback
            return Incidents()

    def _agency_raw_data(self, a_id):
        """Get raw data from PulsePoint API using the real working endpoint with retry logic and circuit breaker"""
        # Check circuit breaker first
        if self._is_circuit_breaker_open():
            print(f"⚠️ Circuit breaker is OPEN - using fallback data for agency {a_id}")
            return self._get_fallback_data(a_id)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://web.pulsepoint.org/',
            'Origin': 'https://web.pulsepoint.org'
        }
        
        # Use the real working API endpoint from browser console
        url = f"https://api.pulsepoint.org/v1/webapp?resource=incidents&agencyid={a_id}"
        
        # Retry logic with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"Fetching real data from: {url} (attempt {attempt + 1}/{max_retries})")
                
                # Increase timeout with each retry and add connection pooling
                timeout = 30 + (attempt * 10)
                
                # Create session with connection pooling for better reliability
                session = requests.Session()
                session.headers.update(headers)
                
                # Configure connection pooling
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=1,
                    pool_maxsize=1,
                    max_retries=0  # We handle retries manually
                )
                session.mount('http://', adapter)
                session.mount('https://', adapter)
                
                response = session.get(url, timeout=timeout)
                
                if response.status_code != 200:
                    print(f"API returned status code: {response.status_code}")
                    if attempt < max_retries - 1:
                        print(f"Retrying in {2 ** attempt} seconds...")
                        time.sleep(2 ** attempt)
                        continue
                    return {}
                
                data = response.json()
                print(f"Successfully got encrypted data from real PulsePoint API")
                
                # Record successful API call
                self._record_api_success()
                
                # Check if we have encrypted data that needs decryption
                if 'ct' in data and 'iv' in data and 's' in data:
                    print("Decrypting data...")
                    decrypted_data = self._decrypt_agency_data(data)
                    # Store as fallback data
                    self._store_fallback_data(a_id, decrypted_data)
                    return decrypted_data
                else:
                    # Data is already decrypted
                    # Store as fallback data
                    self._store_fallback_data(a_id, data)
                    return data
                    
            except requests.exceptions.Timeout as e:
                print(f"Timeout error for agency {a_id} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {2 ** attempt} seconds...")
                    time.sleep(2 ** attempt)
                    continue
                else:
                    print(f"All retry attempts failed for agency {a_id}")
                    self._record_api_failure()
                    return {}
                    
            except requests.exceptions.ConnectionError as e:
                print(f"Connection error for agency {a_id} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {2 ** attempt} seconds...")
                    time.sleep(2 ** attempt)
                    continue
                else:
                    print(f"All retry attempts failed for agency {a_id}")
                    self._record_api_failure()
                    return {}
                    
            except Exception as e:
                print(f"Error getting data for agency {a_id} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {2 ** attempt} seconds...")
                    time.sleep(2 ** attempt)
                    continue
                else:
                    print(f"All retry attempts failed for agency {a_id}")
                    self._record_api_failure()
                    return {}
        
        return {}
    
    def _decrypt_agency_data(self, encrypted_data):
        """Decrypt agency data using PulsePoint's AES decryption"""
        try:
            ct = base64.b64decode(encrypted_data.get("ct"))
            iv = bytes.fromhex(encrypted_data.get("iv"))
            salt = bytes.fromhex(encrypted_data.get("s"))
            
            # Build the password using PulsePoint's algorithm
            t = ""
            e = "CommonIncidents"
            t += e[13] + e[1] + e[2] + "brady" + "5" + "r" + e.lower()[6] + e[5] + "gs"
            
            # Calculate key from password
            hasher = hashlib.md5()
            key = b''
            block = None
            while len(key) < 32:
                if block:
                    hasher.update(block)
                hasher.update(t.encode())
                hasher.update(salt)
                block = hasher.digest()
                hasher = hashlib.md5()
                key += block
            
            # Create cipher and decrypt
            backend = default_backend()
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
            decryptor = cipher.decryptor()
            decrypted = decryptor.update(ct) + decryptor.finalize()
            
            # Clean up the decrypted data
            decrypted_str = decrypted[1:decrypted.rindex(b'"')].decode()
            decrypted_str = decrypted_str.replace(r'\"', r'"')
            
            print("Successfully decrypted data")
            return json.loads(decrypted_str)
        except Exception as e:
            print(f"Decryption error: {e}")
            return {}
    
    def get_agency(self, name) -> dict:
        """Find agency by name or initials"""
        # First try to find in loaded agencies
        for i, x in self.agencies.items():
            options = ["ID", "agency_initials", "agencyname", "short_agencyname"]
            for o in options:
                if o in x and str(x[o]).lower() == str(name).lower(): 
                    return x
        
        # If not found and it looks like an agency ID, create a temporary agency entry
        if str(name).isdigit() or str(name).startswith('0'):
            print(f"Creating temporary agency entry for ID: {name}")
            temp_agency = {
                "agencyid": str(name),
                "agencyname": f"Agency {name}",
                "agency_initials": f"A{name}",
                "short_agencyname": f"Agency {name}",
                "latitude": 0.0,
                "longitude": 0.0,
                "state": "",
                "city": ""
            }
            # Add to agencies for future use
            self.agencies[str(name)] = temp_agency
            return temp_agency
        
        print(f"FAILED TO FIND AGENCY \"{name}\". Looking for the closest match!")
        for i, x in self.agencies.items():
            options = ["ID", "agency_initials", "agencyname", "short_agencyname"]
            for o in options:
                if o in x and (str(x[o]).lower() in str(name).lower() or str(name).lower() in str(x[o]).lower()): 
                    print(f"Using \"{x['agencyname']}\" instead!")
                    return x
        return None

    def get_agency_by_name(self, name: str) -> Optional[Dict]:
        """Find agency by name or initials (alias for get_agency)"""
        return self.get_agency(name)
    
    def list_agencies(self) -> List[str]:
        """Get list of available agency names"""
        return [agency["agencyname"] for agency in self.agencies.values()]
    
    def find_agencies_by_location(self, city=None, state=None):
        """Find agencies by city and/or state"""
        results = []
        for agency in self.agencies.values():
            match = True
            if city and city.lower() not in agency.get("city", "").lower():
                match = False
            if state and state.upper() not in agency.get("state", "").upper():
                match = False
            if match:
                results.append(agency)
        return results
    
    def add_agency_from_browser_storage(self, agency_id, agency_name="Unknown Agency"):
        """Add an agency from browser storage data"""
        self.agencies[agency_id] = {
            "agencyid": agency_id,
            "agencyname": agency_name,
            "agency_initials": agency_name.split()[0][:3].upper() if agency_name else "UNK",
            "short_agencyname": agency_name,
            "latitude": 0.0,
            "longitude": 0.0,
            "state": "",
            "city": ""
        }
        print(f"Added agency from browser storage: {agency_name} (ID: {agency_id})")
    
    def parse_browser_storage_feeds(self, storage_data):
        """Parse browser storage feeds data to extract agency IDs"""
        try:
            import json
            feeds = json.loads(storage_data)
            agency_ids = set()
            
            for feed in feeds:
                if 's' in feed:  # 's' contains the agency IDs
                    # Format: "${config.agencyId},04600" or just "04600"
                    agency_string = feed['s']
                    # Extract agency IDs (remove ${config.agencyId} and split by comma)
                    agency_string = agency_string.replace('${config.agencyId},', '').replace('${config.agencyId}', '')
                    for agency_id in agency_string.split(','):
                        agency_id = agency_id.strip()
                        if agency_id and agency_id.isdigit():
                            agency_ids.add(agency_id)
            
            return list(agency_ids)
        except Exception as e:
            print(f"Error parsing browser storage: {e}")
            return []
    
    # Geofencing Methods
    def add_geofence(self, name: str, center_lat: float, center_lon: float, 
                     radius_miles: float = None, polygon_points: List[Tuple[float, float]] = None,
                     color: str = "#FF0000"):
        """Add a geofence for monitoring"""
        geofence = Geofence(
            name=name,
            center_lat=center_lat,
            center_lon=center_lon,
            radius_miles=radius_miles,
            polygon_points=polygon_points,
            color=color
        )
        self.geofences[name] = geofence
        print(f"Added geofence: {name}")
    
    def add_city_geofence(self, city_name: str, center_lat: float, center_lon: float, 
                          radius_miles: float = 10, color: str = "#FF0000"):
        """Quickly add a circular geofence for a city"""
        self.add_geofence(f"{city_name}_city", center_lat, center_lon, radius_miles, color=color)
    
    def add_custom_polygon_geofence(self, name: str, polygon_points: List[Tuple[float, float]], 
                                   color: str = "#FF0000"):
        """Add a custom polygon geofence (e.g., for specific neighborhoods)"""
        # Calculate center point
        center_lat = sum(point[0] for point in polygon_points) / len(polygon_points)
        center_lon = sum(point[1] for point in polygon_points) / len(polygon_points)
        
        self.add_geofence(name, center_lat, center_lon, polygon_points=polygon_points, color=color)
    
    def get_geofenced_incidents(self, agency_id: str) -> List[GeofencedIncident]:
        """Get incidents that fall within any geofence"""
        all_incidents = self.get_incidents(agency_id)
        geofenced_incidents = []
        
        for incident in all_incidents.active + all_incidents.recent:
            if hasattr(incident, 'coords') and incident.coords:
                lat, lon = incident.coords
                
                for geofence_name, geofence in self.geofences.items():
                    if geofence.contains_point(lat, lon):
                        distance = geofence._calculate_distance(
                            geofence.center_lat, geofence.center_lon, lat, lon
                        )
                        geofenced_incident = GeofencedIncident(
                            incident=incident,
                            geofence_name=geofence_name,
                            distance_from_center=distance
                        )
                        geofenced_incidents.append(geofenced_incident)
                        break  # Only add to one geofence
        
        return geofenced_incidents
    
    def monitor_geofenced_incidents(self, agency_id: str, callback=None):
        """Monitor incidents in geofenced areas with optional callback"""
        geofenced_incidents = self.get_geofenced_incidents(agency_id)
        
        if callback:
            for incident_data in geofenced_incidents:
                callback(incident_data)
        
        return geofenced_incidents
    
    def get_incidents_by_geofence(self, agency_id: str) -> dict:
        """Group incidents by geofence"""
        geofenced_incidents = self.get_geofenced_incidents(agency_id)
        incidents_by_geofence = {}
        
        for incident_data in geofenced_incidents:
            geofence_name = incident_data.geofence_name
            if geofence_name not in incidents_by_geofence:
                incidents_by_geofence[geofence_name] = []
            incidents_by_geofence[geofence_name].append(incident_data)
        
        return incidents_by_geofence
    
    def start_continuous_monitoring(self, agency_id: str, callback=None, interval_seconds: int = 30):
        """Start continuous monitoring in a separate thread"""
        if self.monitoring_active:
            print("Monitoring already active!")
            return
        
        self.monitoring_active = True
        
        def monitor_loop():
            while self.monitoring_active:
                try:
                    incidents = self.monitor_geofenced_incidents(agency_id, callback)
                    time.sleep(interval_seconds)
                except Exception as e:
                    print(f"Error in monitoring loop: {e}")
                    time.sleep(interval_seconds)
        
        self.monitoring_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitoring_thread.start()
        print(f"Started continuous monitoring for agency {agency_id}")
    
    def stop_continuous_monitoring(self):
        """Stop continuous monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        print("Stopped continuous monitoring")
    
    def generate_map_html(self, agency_id: str, output_file: str = "geofenced_map.html"):
        """Generate an HTML map showing geofences and incidents"""
        geofenced_incidents = self.get_geofenced_incidents(agency_id)
        
        # Group incidents by geofence
        incidents_by_geofence = self.get_incidents_by_geofence(agency_id)
        
        # Calculate map center
        if geofenced_incidents:
            all_lats = [inc.incident.coords[0] for inc in geofenced_incidents]
            all_lons = [inc.incident.coords[1] for inc in geofenced_incidents]
            center_lat = sum(all_lats) / len(all_lats)
            center_lon = sum(all_lons) / len(all_lons)
        else:
            # Default to first geofence center or Rogers, AR
            if self.geofences:
                first_geofence = list(self.geofences.values())[0]
                center_lat = first_geofence.center_lat
                center_lon = first_geofence.center_lon
            else:
                center_lat, center_lon = 36.3320, -94.1185  # Rogers, AR
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>FDD CAD Geofenced Incidents Map</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; padding: 0; font-family: Arial, sans-serif; }}
        #map {{ height: 100vh; width: 100%; }}
        .incident-popup {{ max-width: 300px; }}
        .incident-type {{ font-weight: bold; color: #d32f2f; }}
        .incident-address {{ margin: 5px 0; }}
        .incident-time {{ color: #666; font-size: 0.9em; }}
        .geofence-legend {{ position: absolute; top: 10px; right: 10px; background: white; padding: 10px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); z-index: 1000; }}
        .legend-item {{ margin: 5px 0; }}
        .legend-color {{ display: inline-block; width: 20px; height: 15px; margin-right: 8px; vertical-align: middle; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="geofence-legend">
        <h3>Geofences</h3>
        <div id="legend-content"></div>
    </div>

    <script>
        // Initialize map
        const map = L.map('map').setView([{center_lat}, {center_lon}], 12);
        
        // Add tile layer
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);
        
        // Geofences data
        const geofences = {json.dumps({name: {
            'center_lat': gf.center_lat,
            'center_lon': gf.center_lon,
            'radius_miles': gf.radius_miles,
            'color': gf.color,
            'polygon_points': gf.polygon_points
        } for name, gf in self.geofences.items()})};
        
        // Incidents data
        const incidents = {json.dumps([{
            'lat': inc.incident.coords[0],
            'lon': inc.incident.coords[1],
            'type': inc.incident.incident_type,
            'address': inc.incident.FullDisplayAddress,
            'time': inc.incident.CallReceivedDateTime.isoformat() if hasattr(inc.incident.CallReceivedDateTime, 'isoformat') else str(inc.incident.CallReceivedDateTime),
            'geofence': inc.geofence_name,
            'distance': round(inc.distance_from_center, 2)
        } for inc in geofenced_incidents])};
        
        // Add geofences to map
        Object.entries(geofences).forEach(([name, gf]) => {{
            if (gf.polygon_points) {{
                // Custom polygon geofence
                const polygon = L.polygon(gf.polygon_points, {{
                    color: gf.color,
                    weight: 2,
                    fillColor: gf.color,
                    fillOpacity: 0.2
                }}).addTo(map);
                polygon.bindPopup(`<b>${{name}}</b><br>Custom Area`);
            }} else {{
                // Circular geofence
                const circle = L.circle([gf.center_lat, gf.center_lon], {{
                    radius: gf.radius_miles * 1609.34, // Convert miles to meters
                    color: gf.color,
                    weight: 2,
                    fillColor: gf.color,
                    fillOpacity: 0.2
                }}).addTo(map);
                circle.bindPopup(`<b>${{name}}</b><br>Radius: ${{gf.radius_miles}} miles`);
            }}
        }});
        
        // Add incidents to map
        incidents.forEach(incident => {{
            const marker = L.circleMarker([incident.lat, incident.lon], {{
                radius: 8,
                fillColor: '#ff0000',
                color: '#000',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.8
            }}).addTo(map);
            
            marker.bindPopup(`
                <div class="incident-popup">
                    <div class="incident-type">${{incident.type}}</div>
                    <div class="incident-address">${{incident.address}}</div>
                    <div class="incident-time">${{incident.time}}</div>
                    <div><strong>Geofence:</strong> ${{incident.geofence}}</div>
                    <div><strong>Distance:</strong> ${{incident.distance}} miles</div>
                </div>
            `);
        }});
        
        // Update legend
        const legendContent = document.getElementById('legend-content');
        Object.entries(geofences).forEach(([name, gf]) => {{
            const legendItem = document.createElement('div');
            legendItem.className = 'legend-item';
            legendItem.innerHTML = `
                <span class="legend-color" style="background-color: ${{gf.color}};"></span>
                ${{name}}
            `;
            legendContent.appendChild(legendItem);
        }});
        
        // Auto-refresh every 30 seconds
        setInterval(() => {{
            location.reload();
        }}, 30000);
        
        console.log('Map loaded with', incidents.length, 'incidents in', Object.keys(geofences).length, 'geofences');
    </script>
</body>
</html>
        """
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Map generated: {output_file}")
        return output_file


def run_tests():
    """Run offline tests (no API). Use: python FDD_SCARPERRRR.py --test"""
    import sys

    passed = 0
    failed = 0

    def ok(name):
        nonlocal passed
        passed += 1
        print(f"  [OK] {name}")

    def fail(name, msg):
        nonlocal failed
        failed += 1
        print(f"  [FAIL] {name}: {msg}")

    print("FDD Scraper – offline tests")
    print("-" * 50)

    # ----- str2time -----
    scraper = FDDCADScraper()
    try:
        t = scraper.str2time("2024-01-15T14:30:00Z")
        if t.year == 2024 and t.month == 1 and t.day == 15 and t.hour == 14 and t.minute == 30:
            ok("str2time parses ISO timestamp")
        else:
            fail("str2time", f"wrong datetime: {t}")
    except Exception as e:
        fail("str2time", str(e))

    # ----- Geofence circular (distance + contains_point) -----
    try:
        geofence = Geofence(name="test", center_lat=36.3320, center_lon=-94.1185, radius_miles=5.0)
        dist = geofence._calculate_distance(36.3320, -94.1185, 36.34, -94.12)
        if 0 < dist < 2:
            ok("Geofence circular distance (miles)")
        else:
            fail("Geofence distance", f"expected ~0.5–1.5 miles, got {dist}")
        if geofence.contains_point(36.3320, -94.1185):
            ok("Geofence contains center")
        else:
            fail("Geofence contains center", "center should be inside")
        if geofence.contains_point(36.34, -94.12):
            ok("Geofence contains point inside radius")
        else:
            fail("Geofence contains point", "point inside 5 mi should be inside")
        far_lat, far_lon = 35.0, -95.0
        if not geofence.contains_point(far_lat, far_lon):
            ok("Geofence excludes point outside radius")
        else:
            fail("Geofence excludes point", "point far away should be outside")
    except Exception as e:
        fail("Geofence circular", str(e))

    # ----- Geofence polygon -----
    try:
        square = [(36.33, -94.12), (36.33, -94.10), (36.35, -94.10), (36.35, -94.12)]
        poly_geofence = Geofence(name="poly", center_lat=36.34, center_lon=-94.11, radius_miles=1.0, polygon_points=square)
        if poly_geofence.contains_point(36.34, -94.11):
            ok("Geofence polygon contains point inside")
        else:
            fail("Geofence polygon contains", "center of square should be inside")
        if not poly_geofence.contains_point(36.32, -94.11):
            ok("Geofence polygon excludes point outside")
        else:
            fail("Geofence polygon excludes", "point south of square should be outside")
    except Exception as e:
        fail("Geofence polygon", str(e))

    # ----- get_incidents with mock API (no network) -----
    try:
        mock_active = [
            {
                "ID": 9001,
                "Latitude": 36.33,
                "Longitude": -94.12,
                "FullDisplayAddress": "123 Main St, Rogers, AR",
                "PulsePointIncidentCallType": "FIRE",
                "CallReceivedDateTime": "2024-03-01T12:00:00Z",
                "ClosedDateTime": "1990-01-01T00:00:00Z",
                "Unit": [{"UnitID": "E1", "PulsePointDispatchStatus": "Dispatched", "UnitClearedDateTime": "1990-01-01T00:00:00Z"}],
            }
        ]
        mock_recent = [
            {
                "ID": 9000,
                "Latitude": 36.33,
                "Longitude": -94.11,
                "FullDisplayAddress": "456 Oak Ave, Rogers, AR",
                "PulsePointIncidentCallType": "MED",
                "CallReceivedDateTime": "2024-02-28T10:00:00Z",
                "ClosedDateTime": "2024-02-28T11:00:00Z",
                "Unit": [],
            }
        ]
        original_raw = scraper._agency_raw_data
        scraper._agency_raw_data = lambda a_id: {"active": mock_active, "recent": mock_recent}
        incidents = scraper.get_incidents("04600")
        scraper._agency_raw_data = original_raw

        if len(incidents.active) >= 1 and len(incidents.recent) >= 1:
            ok("get_incidents mock: active and recent counts")
        else:
            fail("get_incidents mock", f"active={len(incidents.active)} recent={len(incidents.recent)}")
        first_active = incidents.active[0] if incidents.active else None
        if first_active and getattr(first_active, "incident_type", None):
            ok("get_incidents mock: incident_type set from PulsePointIncidentCallType")
        else:
            fail("get_incidents mock", "incident_type not set on first active")
        if first_active and getattr(first_active, "coords", None):
            ok("get_incidents mock: coords set")
        else:
            fail("get_incidents mock", "coords not set")
    except Exception as e:
        fail("get_incidents mock", str(e))

    print("-" * 50)
    print(f"Done: {passed} passed, {failed} failed")
    return failed == 0


def main():
    """Main function for testing the scraper with geofencing and map features"""
    scraper = FDDCADScraper()
    
    print("FDD CAD Scraper - Fire Department Dispatch Monitor with Geofencing")
    print("=" * 70)
    
    # Set up geofences
    print("\nSetting up geofences...")
    scraper.add_city_geofence("Rogers", 36.3320, -94.1185, 15, "#FF0000")  # Red
    scraper.add_city_geofence("Fayetteville", 36.0626, -94.1574, 20, "#0000FF")  # Blue
    
    # Add custom polygon geofence for downtown area
    downtown_rogers = [
        (36.3320, -94.1185),  # Center
        (36.3400, -94.1100),  # Northeast
        (36.3400, -94.1270),  # Southeast  
        (36.3240, -94.1270),  # Southwest
        (36.3240, -94.1100)   # Northwest
    ]
    scraper.add_custom_polygon_geofence("Downtown_Rogers", downtown_rogers, "#00FF00")  # Green
    
    print(f"Added {len(scraper.geofences)} geofences")
    
    # List available agencies
    agencies = scraper.list_agencies()
    print(f"\nAvailable agencies: {', '.join(agencies[:5])}...")  # Show first 5
    
    # Test with Rogers Fire Department
    rogers_agencies = scraper.find_agencies_by_location(city="Rogers", state="AR")
    if rogers_agencies:
        agency = rogers_agencies[0]
        agency_id = agency['agencyid']
        print(f"\nTesting with: {agency['agencyname']} (ID: {agency_id})")
        
        # Get all incidents
        incidents = scraper.get_incidents(agency_id)
        print(f"Total active incidents: {len(incidents.active)}")
        print(f"Total recent incidents: {len(incidents.recent)}")
        
        # Get geofenced incidents
        geofenced_incidents = scraper.get_geofenced_incidents(agency_id)
        print(f"\nGeofenced incidents: {len(geofenced_incidents)}")
        
        if geofenced_incidents:
            print("\nIncidents in geofenced areas:")
            for geof_incident in geofenced_incidents:
                incident = geof_incident.incident
                print(f"  🚨 {incident.incident_type} in {geof_incident.geofence_name}")
                print(f"     Address: {incident.FullDisplayAddress}")
                print(f"     Distance from center: {geof_incident.distance_from_center:.2f} miles")
                print(f"     Time: {incident.CallReceivedDateTime}")
                if incident.Unit:
                    print(f"     Units: {[unit.UnitID for unit in incident.Unit]}")
                print()
        else:
            print("No incidents currently in geofenced areas")
        
        # Group incidents by geofence
        incidents_by_geofence = scraper.get_incidents_by_geofence(agency_id)
        print(f"\nIncidents by geofence:")
        for geofence_name, incidents_list in incidents_by_geofence.items():
            print(f"  {geofence_name}: {len(incidents_list)} incidents")
        
        # Generate interactive map
        print(f"\nGenerating interactive map...")
        map_file = scraper.generate_map_html(agency_id, "geofenced_incidents_map.html")
        print(f"Map saved as: {map_file}")
        print("Open this file in your browser to see the live map with geofences and incidents!")
        
        # Demo continuous monitoring (optional)
        print(f"\nStarting continuous monitoring demo (30 seconds)...")
        def incident_alert(geof_incident):
            print(f"🚨 NEW ALERT: {geof_incident.incident.incident_type} in {geof_incident.geofence_name}")
        
        scraper.start_continuous_monitoring(agency_id, incident_alert, 10)
        time.sleep(30)  # Monitor for 30 seconds
        scraper.stop_continuous_monitoring()
        
    else:
        print("No Rogers agencies found, testing with first available agency")
        if agencies:
            test_agency = scraper.get_agency_by_name(agencies[0])
            if test_agency:
                agency_id = test_agency['agencyid']
                print(f"\nTesting with agency: {test_agency['agencyname']} (ID: {agency_id})")
                incidents = scraper.get_incidents(agency_id)
                
                print(f"Active incidents: {len(incidents.active)}")
                print(f"Recent incidents: {len(incidents.recent)}")
                
                # Generate map even without specific geofences
                map_file = scraper.generate_map_html(agency_id, "incidents_map.html")
                print(f"Map saved as: {map_file}")
                
                for incident in incidents.active:
                    print(f"  - {incident.incident_type} at {incident.FullDisplayAddress}")
                    print(f"    Time: {incident.CallReceivedDateTime}")
                    if incident.Unit:
                        print(f"    Units: {[unit.UnitID for unit in incident.Unit]}")


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        success = run_tests()
        sys.exit(0 if success else 1)
    main()
