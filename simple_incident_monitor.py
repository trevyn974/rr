#!/usr/bin/env python3
"""
Simple Incident Monitor - Pushover Only
Monitors PulsePoint for new incidents and sends Pushover notifications only.
No web interface, no Discord, just simple incident monitoring.
Runs 24/7 with automatic error recovery and watchdog monitoring.
"""

import requests
import time
import datetime
import threading
import traceback
import os
from typing import Set
from fdd_cad_scraper import FDDCADScraper, Incident

PUSHOVER_USER_KEY = "u91gdp1wbvynt5wmiec45tsf79e6t5"
PUSHOVER_APP_TOKEN = "agunhyfhpg9rik3dr5uedi51vyotaw"
PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"

# Active Alert webhook (set via environment variable if available)
ACTIVE_ALERT_WEBHOOK_URL = os.getenv("ACTIVE_ALERT_WEBHOOK_URL", "http://localhost:7000/active-alert/webhook")

# Monitoring Configuration
AGENCY_ID = "04600"  # Rogers Fire Department
CHECK_INTERVAL = 0  # Check continuously (no delay)


class SimpleIncidentMonitor:
    """Simple monitor that only sends Pushover notifications for new incidents"""
    
    def __init__(self, agency_id: str):
        self.agency_id = agency_id
        self.scraper = FDDCADScraper()
        self.sent_incident_ids: Set[int] = set()
        self.running = True
        self.monitor_thread = None
        self.watchdog_thread = None
        self.last_successful_check = None
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10
        
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
            
            response = requests.post(PUSHOVER_API_URL, data=data, timeout=10)
            
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
            response = requests.post(
                ACTIVE_ALERT_WEBHOOK_URL,
                json=payload,
                timeout=10,
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
    
    def check_for_new_incidents(self):
        """Check for new incidents and send notifications"""
        try:
            # Get incidents from PulsePoint
            incidents = self.scraper.get_incidents(self.agency_id)
            
            if not incidents or not hasattr(incidents, 'active'):
                print(f"[DEBUG] No incidents data returned")
                self.consecutive_errors = 0  # Reset error count on successful API call
                self.last_successful_check = datetime.datetime.now()
                return
            
            active_incidents = incidents.active or []
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
        print(f"Monitoring Agency: {self.agency_id}")
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
    monitor = SimpleIncidentMonitor(AGENCY_ID)
    
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

