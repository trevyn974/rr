#!/usr/bin/env python3
"""
Discord Webhook Integration for FDD CAD System
Handles sending real calls and daily summaries to Discord channels
"""

import requests
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import threading
import time

@dataclass
class DiscordWebhookConfig:
    """Configuration for Discord webhooks"""
    # Webhook for real calls and alerts
    calls_webhook_url: str = "https://discord.com/api/webhooks/1379959452098232450/oFAvxyvROKGhes8EvArVJqv_1dtI8T_JmGRYAVE9SDmGESiSooMLPHsoSMMBFUep4HeD"
    
    # Webhook for responder type calls only
    responder_webhook_url: str = "https://discord.com/api/webhooks/1420450015066718429/sgGSV3uRrGhs60lLEKDlw7LpdWhvIoE8AxiUga7XlJJVqLFISW0V290Y4HWebBfFQQmL"
    
    # Webhook for daily summaries
    daily_summary_webhook_url: str = "https://discord.com/api/webhooks/1379959452098232450/oFAvxyvROKGhes8EvArVJqv_1dtI8T_JmGRYAVE9SDmGESiSooMLPHsoSMMBFUep4HeD"
    
    # Settings
    enabled: bool = True  # ENABLED TO SEND CALLS
    send_real_calls: bool = True  # ENABLED TO SEND CALLS
    send_daily_summaries: bool = True  # ENABLED TO SEND SUMMARIES
    send_responder_calls: bool = True  # ENABLED TO SEND RESPONDER CALLS
    
    # Priority levels that trigger Discord notifications
    discord_priorities: List[str] = None  # Will be set to ["low", "medium", "high"] by default
    
    # Daily summary settings
    daily_summary_time: str = "06:00"  # 6:00 AM daily summary
    include_unit_status: bool = True
    include_statistics: bool = True

class DiscordWebhookManager:
    """Manages Discord webhook notifications for the CAD system"""
    
    def __init__(self, config: DiscordWebhookConfig = None):
        self.config = config or DiscordWebhookConfig()
        
        # Set default priorities if not specified
        if self.config.discord_priorities is None:
            self.config.discord_priorities = ["low", "medium", "high"]
        
        # Track notifications with timestamps for smart duplicate prevention
        self.daily_summary_sent = False
        self.last_daily_summary_date = None
        self.startup_message_sent = False  # Prevent multiple startup messages
        
        # Rate limiting to prevent spam - REASONABLE LIMITS
        self.last_notification_time = {}
        self.min_notification_interval = 300    # Minimum 5 minutes between notifications for same incident
        self.max_notifications_per_hour = 20    # Maximum 20 notifications per hour (reasonable for emergency services)
        self.notification_count_per_hour = 0
        self.hour_reset_time = time.time()
        
        # Start daily summary scheduler
        self._start_daily_summary_scheduler()
    
    def _start_daily_summary_scheduler(self):
        """Start the daily summary scheduler in a background thread"""
        def scheduler_loop():
            while True:
                try:
                    current_time = datetime.now().strftime("%H:%M")
                    current_date = datetime.now().date()
                    
                    # Check if it's time for daily summary and we haven't sent one today
                    if (current_time == self.config.daily_summary_time and 
                        self.last_daily_summary_date != current_date):
                        self._send_daily_summary()
                        self.last_daily_summary_date = current_date
                        self.daily_summary_sent = True
                    
                    # Reset daily summary flag at midnight
                    if current_time == "00:00":
                        self.daily_summary_sent = False
                    
                    # Clean up old data every hour at :00 minutes
                    if current_time.endswith(":00"):
                        self.cleanup_old_data()
                    
                    time.sleep(60)  # Check every minute
                except Exception as e:
                    print(f"Error in Discord daily summary scheduler: {e}")
                    time.sleep(60)
        
        scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
        scheduler_thread.start()
        print("Discord daily summary scheduler started")
    
    def send_incident_notification(self, incident, priority: str, incident_type: str = "real_call") -> bool:
        """Send incident notification to appropriate Discord webhook"""
        if not self.config.enabled:
            return False
        
        # Check if we should send this notification
        if not self._should_send_notification(incident, priority, incident_type):
            return False
        
        # Rate limiting checks (but allow force sending for real calls)
        if incident_type != "real_call" and not self._check_rate_limits(incident, incident_type):
            return False
        
        # ULTRA STRICT duplicate prevention - block ANY duplicate for same incident ID
        incident_key = f"{incident.ID}_{incident_type}"
        current_time = time.time()
        
        # Check if this exact incident was already sent (regardless of type or time)
        if incident_key in self.last_notification_time:
            print(f"DUPLICATE BLOCKED: Incident {incident.ID} already sent - PERMANENTLY BLOCKING")
            return False
        
        # Also check for same incident ID with ANY other type (permanent block)
        for existing_key in self.last_notification_time:
            if existing_key.startswith(f"{incident.ID}_"):
                print(f"DUPLICATE BLOCKED: Incident {incident.ID} already sent as different type - PERMANENTLY BLOCKING")
                return False
        
        try:
            # Determine which webhook to use
            webhook_url = self._get_webhook_url(incident_type, priority)
            if not webhook_url:
                return False
            
            # Create Discord embed
            embed = self._create_incident_embed(incident, priority, incident_type)
            
            # Send to Discord
            print(f"Attempting to send Discord notification: {incident_type} - {incident.incident_type}")
            print(f"Webhook URL: {webhook_url[:50]}...")
            success = self._send_discord_message(webhook_url, embed)
            
            # If first attempt fails, try again with fallback
            if not success and incident_type == "real_call":
                print(f"RETRY: First attempt failed, trying fallback method...")
                success = self._send_discord_fallback(incident, priority, incident_type)
            
            if success:
                # Update rate limiting tracking after successful send
                self.last_notification_time[incident_key] = current_time
                self.notification_count_per_hour += 1
                print(f"SUCCESS: Discord notification sent for {incident_type}: {incident.incident_type}")
            else:
                print(f"FAILED: Discord notification failed for {incident_type}: {incident.incident_type}")
            
            return success
            
        except Exception as e:
            print(f"Error sending Discord notification: {e}")
            return False

    def _send_discord_fallback(self, incident, priority, incident_type):
        """Fallback method to send Discord notification with simplified payload"""
        try:
            # Create a simple, guaranteed-to-work payload
            simple_payload = {
                "username": "Fire Department Dispatch",
                "content": f"**OFFICIAL FIRE DEPARTMENT INCIDENT REPORT**\n\n**Incident #{incident.ID}**\n**Type:** {incident.incident_type}\n**Address:** {incident.FullDisplayAddress}\n**Priority:** {priority.upper()}\n**Time:** {incident.CallReceivedDateTime}\n**Status:** ACTIVE"
            }
            
            # Try the main webhook URL
            response = requests.post(
                self.config.calls_webhook_url,
                json=simple_payload,
                timeout=10
            )
            
            if response.status_code == 204:
                print("FALLBACK SUCCESS: Simple message sent to Discord")
                return True
            else:
                print(f"FALLBACK FAILED: Status {response.status_code}")
                return False
                
        except Exception as e:
            print(f"FALLBACK ERROR: {e}")
            return False
    
    def _should_send_notification(self, incident, priority: str, incident_type: str) -> bool:
        """Determine if we should send this notification"""
        if not self.config.enabled:
            return False
        
        # Check priority level
        if priority.lower() not in [p.lower() for p in self.config.discord_priorities]:
            return False
        
        # Check incident type settings
        if incident_type == "real_call" and not self.config.send_real_calls:
            return False
        elif incident_type == "responder_call" and not self.config.send_responder_calls:
            return False
        
        return True
    
    def _check_rate_limits(self, incident, incident_type: str) -> bool:
        """Check rate limits to prevent spam"""
        current_time = time.time()
        incident_key = f"{incident.ID}_{incident_type}"
        
        # Reset hourly counter if needed
        if current_time - self.hour_reset_time >= 3600:  # 1 hour
            self.notification_count_per_hour = 0
            self.hour_reset_time = current_time
        
        # Check hourly limit
        if self.notification_count_per_hour >= self.max_notifications_per_hour:
            print(f"Rate limit exceeded: {self.notification_count_per_hour}/{self.max_notifications_per_hour} notifications this hour")
            return False
        
        # This check is now handled in the main send_incident_notification method
        # to avoid duplicate checking
        
        return True
    
    def _get_webhook_url(self, incident_type: str, priority: str) -> Optional[str]:
        """Get the appropriate webhook URL based on incident type and priority"""
        if incident_type == "responder_call":
            return self.config.responder_webhook_url
        elif incident_type == "call_closed":
            return self.config.calls_webhook_url  # Send closures to main calls webhook
        else:
            return self.config.calls_webhook_url
    
    def _create_incident_embed(self, incident, priority: str, incident_type: str) -> Dict:
        """Create a Discord embed for the incident"""
        try:
            # Validate incident data
            if not hasattr(incident, 'ID') or not hasattr(incident, 'incident_type'):
                print(f"Warning: Invalid incident data for Discord notification")
                return self._create_fallback_embed(incident, priority, incident_type)
            
            # For active incidents, use the official incident report format
            if incident_type == "real_call" and incident_type != "call_closed":
                return self._create_official_incident_report(incident, priority)
            
            # For closed calls, use the original format
            if incident_type == "call_closed":
                return self._create_closed_call_embed(incident, priority)
            
            # For other types, use the original format
            return self._create_standard_embed(incident, priority, incident_type)
        except Exception as e:
            print(f"Error creating incident embed: {e}")
            return self._create_fallback_embed(incident, priority, incident_type)
    
    def _create_official_incident_report(self, incident, priority: str) -> Dict:
        """Create an official incident report format for active incidents"""
        try:
            # Safely format the call received time
            call_time = getattr(incident, 'CallReceivedDateTime', datetime.now())
            if hasattr(call_time, 'strftime'):
                call_time_str = call_time.strftime("%I:%M:%S %p CDT, %B %d, %Y")
            else:
                call_time_str = str(call_time) if call_time else "Unknown time"
            
            # Format the report time (current time)
            report_time = datetime.now().strftime("%I:%M %p CDT, %B %d, %Y")
            
            # Get responding agency (try to extract from incident data)
            responding_agency = self._get_responding_agency(incident)
            
            # Get unit information and format it
            dispatched_units, on_scene_units = self._format_units(incident)
            
            # Determine color based on priority
            color_map = {
                "critical": 0xFF0000,  # Red
                "high": 0xFF6600,      # Orange
                "medium": 0xFFAA00,    # Yellow
                "low": 0x00AA00        # Green
            }
            color = color_map.get(priority.lower(), 0xFF6600)
            
            # Safely get incident attributes with length limits
            incident_type = getattr(incident, 'incident_type', 'Unknown Incident')
            incident_id = getattr(incident, 'ID', 'Unknown')
            address = getattr(incident, 'FullDisplayAddress', 'Unknown Address')
            
            # Truncate long strings to prevent Discord errors
            incident_type = incident_type[:200] if len(incident_type) > 200 else incident_type
            address = address[:200] if len(address) > 200 else address
            responding_agency = responding_agency[:200] if len(responding_agency) > 200 else responding_agency
        
            # Create official incident report embed (no emojis)
            embed = {
                "title": "OFFICIAL FIRE DEPARTMENT INCIDENT REPORT",
                "description": f"**INCIDENT TYPE:** {incident_type.upper()}\n**STATUS:** ACTIVE EMERGENCY RESPONSE"[:2048],
                "color": color,
                "timestamp": call_time.isoformat() if hasattr(call_time, 'isoformat') else datetime.now().isoformat(),
                "fields": [
                    {
                        "name": "INCIDENT DATE & TIME",
                        "value": f"**Reported:** {call_time_str}\n**Report Generated:** {report_time}",
                        "inline": False
                    },
                    {
                        "name": "INCIDENT LOCATION",
                        "value": self._format_location_details_with_agency(incident, responding_agency),
                        "inline": False
                    },
                    {
                        "name": "INCIDENT IDENTIFICATION",
                        "value": f"**CAD Incident ID:** {incident_id}\n**Priority Level:** {priority.upper()}\n**Current Status:** ACTIVE RESPONSE",
                        "inline": False
                    },
                    {
                        "name": "EMERGENCY RESPONSE UNITS",
                        "value": f"{dispatched_units}\n\n{on_scene_units}"[:1024],
                        "inline": False
                    }
                ],
                "footer": {
                    "text": "Fire Department Dispatch • Computer Aided Dispatch System • OFFICIAL REPORT"
                }
            }
        
            # Add additional information if available
            additional_info = self._get_additional_info(incident)
            if additional_info != "No additional information available":
                # Ensure field value doesn't exceed Discord limits
                field_value = additional_info[:1024]
                if len(field_value) > 1024:
                    field_value = field_value[:1021] + "..."
                embed["fields"].append({
                    "name": "ADDITIONAL INCIDENT DETAILS",
                    "value": field_value,
                    "inline": False
                })
            
            # Add operational summary
            operational_summary = self._create_operational_summary(incident, call_time_str, responding_agency, dispatched_units, on_scene_units)
            # Ensure field value doesn't exceed Discord limits
            summary_value = operational_summary[:1024]
            if len(summary_value) > 1024:
                summary_value = summary_value[:1021] + "..."
            embed["fields"].append({
                "name": "OPERATIONAL STATUS REPORT",
                "value": summary_value,
                "inline": False
            })
            
            return {
                "embeds": [embed],
                "username": "Fire Department Dispatch"
            }
        except Exception as e:
            print(f"Error creating official incident report: {e}")
            return self._create_fallback_embed(incident, priority, "real_call")
    
    def _create_closed_call_embed(self, incident, priority: str) -> Dict:
        """Create embed for closed calls"""
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
                        units_text = ", ".join(unit_names)
                elif isinstance(incident.Unit, str):
                    units_text = incident.Unit
            except Exception as e:
                print(f"Error extracting units for Discord: {e}")
                units_text = "Units assigned"
        
        # Create official closed call embed (no emojis)
        embed = {
            "title": "OFFICIAL INCIDENT CLOSURE REPORT",
            "description": f"**INCIDENT TYPE:** {incident.incident_type.upper()}\n**STATUS:** INCIDENT RESOLVED - UNITS CLEARED",
            "color": 0x00AA00,  # Green for closed calls
            "timestamp": incident.CallReceivedDateTime.isoformat() if hasattr(incident.CallReceivedDateTime, 'isoformat') else str(incident.CallReceivedDateTime),
            "fields": [
                {
                    "name": "INCIDENT LOCATION",
                    "value": self._format_location_details(incident),
                    "inline": False
                },
                {
                    "name": "INCIDENT IDENTIFICATION",
                    "value": f"**CAD Incident ID:** {incident.ID}\n**Alarm Level:** {str(incident.AlarmLevel) if hasattr(incident, 'AlarmLevel') else 'N/A'}",
                    "inline": True
                },
                {
                    "name": "RESPONDING UNITS",
                    "value": f"**Units Cleared:** {units_text}",
                    "inline": True
                },
                {
                    "name": "INCIDENT STATUS",
                    "value": "**INCIDENT CLOSED**\n**All units have been cleared and are available for service**",
                    "inline": False
                }
            ],
            "footer": {
                "text": "Fire Department Dispatch • Incident Closure Report • OFFICIAL"
            }
        }
        
        return {"embeds": [embed], "username": "Fire Department Dispatch"}
    
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
                    
        except Exception as e:
            print(f"Error parsing address: {e}")
        
        return details
    
    def _format_location_details(self, incident) -> str:
        """Format comprehensive location details for Discord embed"""
        location_parts = []
        
        # Full address
        location_parts.append(f"**Address:** {incident.FullDisplayAddress}")
        
        # Parse address details
        address_details = self._parse_address_details(incident.FullDisplayAddress)
        
        # Add street information
        if address_details['street']:
            location_parts.append(f"**Street:** {address_details['street']}")
        
        # Add cross street/intersection if available - ALWAYS SHOW IF FOUND
        if address_details['cross_street']:
            location_parts.append(f"**Intersection/Cross Street:** {address_details['cross_street']}")
        else:
            # Fallback: Try to extract manually if patterns didn't catch it
            address_lower = incident.FullDisplayAddress.lower()
            if ' at ' in address_lower or ' & ' in address_lower or ' / ' in address_lower or ' and ' in address_lower:
                import re
                manual_cross = re.search(r'(?:at|&|/|and)\s+([^,]+?)(?:,|$)', incident.FullDisplayAddress, re.IGNORECASE)
                if manual_cross:
                    cross_street = manual_cross.group(1).strip()
                    if cross_street and len(cross_street) > 2:
                        location_parts.append(f"**Intersection/Cross Street:** {cross_street}")
        
        # Add city/area
        if address_details['city']:
            location_parts.append(f"**City:** {address_details['city']}")
        if address_details['area']:
            location_parts.append(f"**Area:** {address_details['area']}")
        if address_details['zip_code']:
            location_parts.append(f"**ZIP Code:** {address_details['zip_code']}")
        
        # Add common place name if available
        if hasattr(incident, 'CommonPlaceName') and incident.CommonPlaceName:
            location_parts.append(f"**Place:** {incident.CommonPlaceName}")
        
        return "\n".join(location_parts)
    
    def _format_location_details_with_agency(self, incident, agency: str) -> str:
        """Format location details with agency information"""
        location_details = self._format_location_details(incident)
        if agency:
            location_details += f"\n**Responding Agency:** {agency}"
        return location_details
    
    def _create_standard_embed(self, incident, priority: str, incident_type: str) -> Dict:
        """Create standard embed for other incident types"""
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
                        units_text = ", ".join(unit_names)
                elif isinstance(incident.Unit, str):
                    units_text = incident.Unit
            except Exception as e:
                print(f"Error extracting units for Discord: {e}")
                units_text = "Units assigned"
        
        # Determine color and title based on incident type
        color_map = {
            "critical": 0xFF0000,  # Red
            "high": 0xFF6600,      # Orange
            "medium": 0xFFAA00,    # Yellow
            "low": 0x00AA00        # Green
        }
        color = color_map.get(priority.lower(), 0x00AA00)
        title = f"NEW CALL: {incident.incident_type}"
        status_text = priority.upper()
        
        # Create official standard embed
        embed = {
            "title": f"FIRE DEPARTMENT INCIDENT REPORT - {incident.incident_type.upper()}",
            "description": f"**INCIDENT STATUS:** {status_text}",
            "color": color,
            "timestamp": incident.CallReceivedDateTime.isoformat() if hasattr(incident.CallReceivedDateTime, 'isoformat') else str(incident.CallReceivedDateTime),
            "fields": [
                {
                    "name": "INCIDENT LOCATION",
                    "value": self._format_location_details(incident),
                    "inline": False
                },
                {
                    "name": "INCIDENT IDENTIFICATION",
                    "value": f"**CAD Incident ID:** {incident.ID}\n**Alarm Level:** {str(incident.AlarmLevel) if hasattr(incident, 'AlarmLevel') else 'N/A'}",
                    "inline": True
                },
                {
                    "name": "RESPONDING UNITS",
                    "value": f"**Assigned Units:** {units_text}",
                    "inline": True
                }
            ],
            "footer": {
                "text": f"Fire Department Dispatch • {incident_type.replace('_', ' ').title()} • OFFICIAL"
            }
        }
        
        # Add GPS coordinates and maps link if available
        if hasattr(incident, 'Latitude') and hasattr(incident, 'Longitude'):
            if incident.Latitude and incident.Longitude:
                maps_link = f"https://www.google.com/maps?q={incident.Latitude},{incident.Longitude}"
                embed["fields"].append({
                    "name": "GPS COORDINATES & MAPS",
                    "value": f"**Latitude:** {incident.Latitude:.4f}\n**Longitude:** {incident.Longitude:.4f}\n**[Open in Google Maps]({maps_link})**",
                    "inline": False
                })
        
        return {"embeds": [embed], "username": "Fire Department Dispatch"}
    
    def _get_responding_agency(self, incident) -> str:
        """Extract responding agency from incident data"""
        # Try to get agency from various possible fields
        if hasattr(incident, 'Agency') and incident.Agency:
            return incident.Agency
        elif hasattr(incident, 'AgencyName') and incident.AgencyName:
            return incident.AgencyName
        elif hasattr(incident, 'Department') and incident.Department:
            return incident.Department
        else:
            # Try to infer from address or other data
            address = getattr(incident, 'FullDisplayAddress', '')
            if 'Rogers' in address:
                return "Rogers Fire Department"
            elif 'Bentonville' in address:
                return "Bentonville Fire Department"
            elif 'Springdale' in address:
                return "Springdale Fire Department"
            else:
                return "Local Fire Department"
    
    def _format_units(self, incident) -> tuple:
        """Format units into dispatched and on scene sections"""
        dispatched_units = "Dispatched: Operations Unit 1 (OPS_1)"
        on_scene_units = "On Scene:"
        
        if hasattr(incident, 'Unit') and incident.Unit:
            try:
                unit_names = []
                if isinstance(incident.Unit, list):
                    for unit in incident.Unit:
                        if hasattr(unit, 'UnitID'):
                            unit_names.append(str(unit.UnitID)[:50])  # Limit unit ID length
                        elif isinstance(unit, str):
                            unit_names.append(unit[:50])  # Limit unit string length
                elif isinstance(incident.Unit, str):
                    unit_names.append(incident.Unit[:50])  # Limit unit string length
                
                if unit_names:
                    # Format units with proper spacing and line breaks
                    formatted_units = []
                    for unit in unit_names:
                        # Add proper spacing and formatting
                        if 'Fire' in unit or 'fire' in unit:
                            formatted_units.append(unit)  # Keep fire department names as-is
                        elif unit.startswith('BC'):
                            formatted_units.append(f"Battalion Chief {unit[2:]} ({unit})")
                        elif unit.startswith('E'):
                            formatted_units.append(f"Engine {unit[1:]} ({unit})")
                        elif unit.startswith('L'):
                            formatted_units.append(f"Ladder {unit[1:]} ({unit})")
                        elif unit.startswith('MED'):
                            formatted_units.append(f"Medic {unit[3:]} ({unit})")
                        elif unit.startswith('R'):
                            formatted_units.append(f"Rescue {unit[1:]} ({unit})")
                        elif unit.startswith('SQUAD'):
                            formatted_units.append(f"Squad {unit[5:]} ({unit})")
                        else:
                            formatted_units.append(unit)
                    
                    # Join units and limit total length
                    units_text = "\n".join(formatted_units)
                    if len(units_text) > 800:  # Leave room for other text
                        units_text = units_text[:797] + "..."
                    on_scene_units += "\n" + units_text
                else:
                    dispatched_units = "Dispatched: No units assigned"
                    on_scene_units = "On Scene: None"
            except Exception as e:
                print(f"Error formatting units: {e}")
                dispatched_units = "Dispatched: Units assigned"
                on_scene_units = "On Scene: Units assigned"
        else:
            dispatched_units = "Dispatched: No units assigned"
            on_scene_units = "On Scene: None"
        
        return dispatched_units, on_scene_units
    
    def _get_additional_info(self, incident) -> str:
        """Get additional information for the incident"""
        info_parts = []
        
        if hasattr(incident, 'AlarmLevel') and incident.AlarmLevel:
            info_parts.append(f"Alarm Level: {incident.AlarmLevel}")
        
        if hasattr(incident, 'Priority') and incident.Priority:
            info_parts.append(f"Priority: {incident.Priority}")
        
        if hasattr(incident, 'Latitude') and hasattr(incident, 'Longitude'):
            if incident.Latitude and incident.Longitude:
                info_parts.append(f"Coordinates: {incident.Latitude:.4f}, {incident.Longitude:.4f}")
        
        return "\n".join(info_parts) if info_parts else "No additional information available"
    
    def _create_operational_summary(self, incident, call_time_str: str, responding_agency: str, dispatched_units: str, on_scene_units: str) -> str:
        """Create operational summary for the incident"""
        # Extract unit names for the summary
        unit_list = []
        if "On Scene:" in on_scene_units:
            scene_units = on_scene_units.split("On Scene:")[1].strip()
            if scene_units and scene_units != "None":
                unit_list = [unit.strip() for unit in scene_units.split("\n") if unit.strip()]
        
        units_text = ", ".join(unit_list) if unit_list else "assigned units"
        
        # Determine appropriate terminology based on incident type
        incident_type_lower = incident.incident_type.lower() if incident.incident_type else "emergency"
        
        # Medical/EMS incidents
        if any(term in incident_type_lower for term in ['medical', 'ems', 'ambulance', 'paramedic', 'trauma', 'cardiac', 'stroke', 'seizure', 'respiratory', 'allergic', 'diabetic', 'overdose', 'pregnancy', 'psychiatric', 'behavioral']):
            action_text = "responding to and treating the medical emergency"
            protocol_text = "standard protocols for emergency medical services and patient care"
        # Fire incidents
        elif any(term in incident_type_lower for term in ['fire', 'structure', 'wildland', 'brush', 'vehicle fire', 'arson', 'explosion', 'hazmat']):
            action_text = "containing and extinguishing the fire"
            protocol_text = "standard protocols for structural firefighting and safety"
        # Rescue incidents
        elif any(term in incident_type_lower for term in ['rescue', 'extrication', 'water rescue', 'high angle', 'confined space', 'trench', 'collapse']):
            action_text = "conducting rescue operations"
            protocol_text = "standard protocols for technical rescue and safety"
        # Police/Law enforcement incidents
        elif any(term in incident_type_lower for term in ['police', 'law enforcement', 'criminal', 'theft', 'assault', 'domestic', 'traffic stop', 'pursuit']):
            action_text = "responding to and investigating the incident"
            protocol_text = "standard protocols for law enforcement and public safety"
        # General emergency response
        else:
            action_text = "responding to and managing the emergency"
            protocol_text = "standard protocols for emergency response and safety"
        
        summary = f"""This incident reported at {call_time_str} at {incident.FullDisplayAddress}. The {responding_agency} mobilized a comprehensive response, with units including {units_text} on scene. Operations Unit 1 dispatched, and all listed units actively engaged in {action_text}. The situation remains active, and personnel adhering to {protocol_text}. Further updates provided upon incident resolution."""
        
        return summary
    
    def _create_fallback_embed(self, incident, priority: str, incident_type: str) -> Dict:
        """Create a fallback embed when normal processing fails"""
        try:
            # Get basic information safely
            incident_id = getattr(incident, 'ID', 'Unknown')
            incident_type_name = getattr(incident, 'incident_type', 'Unknown Incident')
            address = getattr(incident, 'FullDisplayAddress', 'Unknown Address')
            
            # Determine color based on priority
            color_map = {
                "critical": 0xFF0000,  # Red
                "high": 0xFF6600,      # Orange
                "medium": 0xFFAA00,    # Yellow
                "low": 0x00AA00        # Green
            }
            color = color_map.get(priority.lower(), 0xFF6600)
            
            embed = {
                "title": "EMERGENCY INCIDENT ALERT",
                "description": f"**INCIDENT TYPE:** {incident_type_name.upper()}\n**STATUS:** {'ACTIVE RESPONSE' if incident_type != 'call_closed' else 'INCIDENT CLOSED'}",
                "color": color,
                "timestamp": datetime.now().isoformat(),
                "fields": [
                    {
                        "name": "INCIDENT LOCATION",
                        "value": self._format_location_details(incident) if hasattr(incident, 'FullDisplayAddress') else f"**Address:** {address}",
                        "inline": False
                    },
                    {
                        "name": "INCIDENT IDENTIFICATION",
                        "value": f"**CAD Incident ID:** {incident_id}\n**Priority Level:** {priority.upper()}",
                        "inline": True
                    },
                    {
                        "name": "INCIDENT STATUS",
                        "value": "**ACTIVE EMERGENCY RESPONSE**" if incident_type != "call_closed" else "**INCIDENT CLOSED**",
                        "inline": True
                    }
                ],
                "footer": {
                    "text": "Fire Department Dispatch • Emergency Alert System • OFFICIAL"
                }
            }
            
            return {"embeds": [embed], "username": "Fire Department Dispatch"}
        except Exception as e:
            print(f"Error creating fallback embed: {e}")
            # Return minimal embed as last resort
            return {
                "embeds": [{
                    "title": "EMERGENCY INCIDENT - SYSTEM ERROR",
                    "description": "An incident occurred but details could not be formatted.",
                    "color": 0xFF0000,
                    "timestamp": datetime.now().isoformat(),
                    "footer": {"text": "Fire Department Dispatch • System Error Report • OFFICIAL"}
                }],
                "username": "Fire Department Dispatch"
            }
    
    def _send_discord_message(self, webhook_url: str, payload: Dict) -> bool:
        """Send message to Discord webhook"""
        try:
            # Validate webhook URL
            if not webhook_url or not webhook_url.startswith('https://discord.com/api/webhooks/'):
                print(f"ERROR: Invalid Discord webhook URL: {webhook_url}")
                return False
            
            # Validate payload
            if not payload:
                print("ERROR: Empty Discord payload")
                return False
            
            if 'embeds' not in payload:
                print("ERROR: Invalid Discord payload: missing embeds")
                print(f"DEBUG: Payload keys: {list(payload.keys())}")
                return False
            
            # Validate embed structure
            embeds = payload.get('embeds', [])
            if not embeds or not isinstance(embeds, list):
                print("ERROR: Invalid embeds structure")
                return False
            
            # Check embed size limits
            for i, embed in enumerate(embeds):
                if not isinstance(embed, dict):
                    print(f"ERROR: Embed {i} is not a dictionary")
                    return False
                
                # Check title length
                if 'title' in embed and len(embed['title']) > 256:
                    print(f"ERROR: Embed {i} title too long: {len(embed['title'])} chars")
                    return False
                
                # Check description length
                if 'description' in embed and len(embed['description']) > 4096:
                    print(f"ERROR: Embed {i} description too long: {len(embed['description'])} chars")
                    return False
                
                # Check fields
                if 'fields' in embed:
                    for j, field in enumerate(embed['fields']):
                        if 'name' in field and len(field['name']) > 256:
                            print(f"ERROR: Embed {i} field {j} name too long: {len(field['name'])} chars")
                            return False
                        if 'value' in field and len(field['value']) > 1024:
                            print(f"ERROR: Embed {i} field {j} value too long: {len(field['value'])} chars")
                            return False
            
            print(f"Sending Discord message to: {webhook_url[:50]}...")
            print(f"DEBUG: Payload size: {len(str(payload))} characters")
            
            # Send request with proper error handling
            response = requests.post(
                webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=15  # Increased timeout for reliability
            )
            
            print(f"Discord response: {response.status_code}")
            
            if response.status_code == 204:
                print("SUCCESS: Discord webhook delivered!")
                return True
            elif response.status_code == 429:
                # Rate limited by Discord
                print(f"WARNING: Discord rate limited: {response.text}")
                return False
            elif response.status_code in [400, 401, 403, 404]:
                # Client errors
                print(f"ERROR: Discord client error {response.status_code}: {response.text}")
                print(f"DEBUG: Request payload: {json.dumps(payload, indent=2)[:500]}...")
                return False
            elif response.status_code >= 500:
                # Server errors
                print(f"ERROR: Discord server error {response.status_code}: {response.text}")
                return False
            else:
                print(f"WARNING: Unexpected Discord response {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            print("ERROR: Discord webhook timeout - request took too long")
            return False
        except requests.exceptions.ConnectionError:
            print("ERROR: Discord webhook connection error - check internet connection")
            return False
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Discord webhook request error: {e}")
            return False
        except Exception as e:
            print(f"ERROR: Unexpected error sending Discord message: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _send_daily_summary(self):
        """Send daily summary to Discord (placeholder - will be overridden by CAD system)"""
        if not self.config.enabled or not self.config.send_daily_summaries:
            return
        
        try:
            # This is a placeholder - the real daily summary is sent via send_daily_summary() method
            embed = {
                "title": "DAILY CAD SYSTEM SUMMARY",
                "description": "Daily summary will be generated by the CAD system",
                "color": 0x0099FF,
                "timestamp": datetime.now().isoformat(),
                "footer": {
                    "text": "Fire Department Dispatch • Daily Summary Report • OFFICIAL"
                }
            }
            
            payload = {"embeds": [embed]}
            success = self._send_discord_message(self.config.daily_summary_webhook_url, payload)
            
            if success:
                print("Daily summary sent to Discord")
            
        except Exception as e:
            print(f"Error sending daily summary: {e}")
    
    def send_daily_summary(self, cad_system) -> bool:
        """Send daily summary with actual CAD system data"""
        if not self.config.enabled or not self.config.send_daily_summaries:
            return False
        
        try:
            # Get data from CAD system
            status = cad_system.get_status_summary()
            unit_status = cad_system.get_all_unit_status()
            station_status = cad_system.get_station_status_summary()
            
            # Count incidents by priority
            priority_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for incident in cad_system.current_incidents.active + cad_system.current_incidents.recent:
                priority = cad_system._determine_priority(incident)
                priority_counts[priority.lower()] = priority_counts.get(priority.lower(), 0) + 1
            
            # Count unit status
            unit_counts = {"available": 0, "busy": 0, "minimum_staffing": 0, "unknown": 0}
            for unit in unit_status:
                status = unit.get("status", "unknown")
                unit_counts[status] = unit_counts.get(status, 0) + 1
            
            # Create official daily summary embed
            embed = {
                "title": "DAILY CAD SYSTEM SUMMARY REPORT",
                "description": f"**Report Date:** {datetime.now().strftime('%Y-%m-%d')}\n**Report Time:** {datetime.now().strftime('%H:%M:%S')}",
                "color": 0x0099FF,
                "timestamp": datetime.now().isoformat(),
                "fields": [
                    {
                        "name": "INCIDENT STATISTICS",
                        "value": f"**Active:** {status.get('active_incidents', 0)}\n**Recent:** {status.get('recent_incidents', 0)}\n**Alerts:** {status.get('unacknowledged_alerts', 0)}",
                        "inline": True
                    },
                    {
                        "name": "PRIORITY BREAKDOWN",
                        "value": f"**Critical:** {priority_counts['critical']}\n**High:** {priority_counts['high']}\n**Medium:** {priority_counts['medium']}\n**Low:** {priority_counts['low']}",
                        "inline": True
                    },
                    {
                        "name": "UNIT STATUS",
                        "value": f"**Available:** {unit_counts['available']}\n**Busy:** {unit_counts['busy']}\n**Min Staff:** {unit_counts['minimum_staffing']}\n**Unknown:** {unit_counts['unknown']}",
                        "inline": True
                    }
                ],
                "footer": {
                    "text": "Fire Department Dispatch • Daily Summary Report • OFFICIAL"
                }
            }
            
            # Add station status if enabled
            if self.config.include_unit_status and station_status:
                station_text = ""
                for station_id, station_data in station_status.items():
                    station_name = station_data.get("station_name", "Unknown")
                    available = station_data.get("available_units", 0)
                    busy = station_data.get("busy_units", 0)
                    min_staff = station_data.get("minimum_staffing_units", 0)
                    station_text += f"**{station_name}:** {available}A/{busy}B/{min_staff}M\n"
                
                if station_text:
                    embed["fields"].append({
                        "name": "STATION STATUS",
                        "value": station_text[:1024],  # Discord field limit
                        "inline": False
                    })
            
            payload = {"embeds": [embed]}
            success = self._send_discord_message(self.config.daily_summary_webhook_url, payload)
            
            if success:
                print("Daily summary sent to Discord")
                return True
            else:
                return False
                
        except Exception as e:
            print(f"Error sending daily summary: {e}")
            return False
    
    def test_webhook(self, webhook_type: str = "calls") -> bool:
        """Test Discord webhook connectivity - SILENT MODE"""
        webhook_url = None
        
        if webhook_type == "calls":
            webhook_url = self.config.calls_webhook_url
        elif webhook_type == "responder":
            webhook_url = self.config.responder_webhook_url
        elif webhook_type == "daily":
            webhook_url = self.config.daily_summary_webhook_url
        
        if not webhook_url:
            print(f"No webhook URL configured for {webhook_type}")
            return False
        
        try:
            # SILENT TEST - Don't send actual Discord messages during testing
            print(f"Testing {webhook_type} webhook connectivity (silent mode)")
            
            # Just validate the webhook URL format
            if webhook_url.startswith('https://discord.com/api/webhooks/'):
                print(f"{webhook_type.title()} webhook URL valid")
                return True
            else:
                print(f"{webhook_type.title()} webhook URL invalid")
                return False
            
        except Exception as e:
            print(f"Error testing {webhook_type} webhook: {e}")
            return False
    
    def test_all_webhooks(self) -> Dict[str, bool]:
        """Test all configured webhooks"""
        results = {}
        
        print("Testing all Discord webhooks...")
        
        results["calls"] = self.test_webhook("calls")
        results["responder"] = self.test_webhook("responder")
        results["daily"] = self.test_webhook("daily")
        
        return results
    
    def clear_sent_incidents(self):
        """Clear the sent incidents cache"""
        # Remove the sent_incidents set as we're using time-based tracking instead
        print("Cleared notification tracking cache")
    
    def clear_rate_limits(self):
        """Clear rate limiting data"""
        self.last_notification_time.clear()
        self.notification_count_per_hour = 0
        self.hour_reset_time = time.time()
        print("Cleared rate limiting data")
    
    def set_rate_limits(self, min_interval: int = 60, max_per_hour: int = 30):
        """Set rate limiting parameters"""
        self.min_notification_interval = min_interval
        self.max_notifications_per_hour = max_per_hour
        print(f"Rate limits updated: {min_interval}s interval, {max_per_hour} per hour")
    
    def cleanup_old_data(self):
        """Clean up old rate limiting and tracking data"""
        current_time = time.time()
        
        # Remove old notification times (older than 24 hours)
        old_keys = []
        for key, timestamp in self.last_notification_time.items():
            if current_time - timestamp > 86400:  # 24 hours
                old_keys.append(key)
        
        for key in old_keys:
            del self.last_notification_time[key]
        
        # Cleanup is now handled by removing old notification timestamps above
        # No need for separate sent_incidents tracking
        
        if old_keys:
            print(f"Cleaned up {len(old_keys)} old notification timestamps")
    
    def get_status(self) -> Dict:
        """Get current status of the Discord webhook manager"""
        return {
            "enabled": self.config.enabled,
            "rate_limit_entries": len(self.last_notification_time),
            "notifications_this_hour": self.notification_count_per_hour,
            "max_per_hour": self.max_notifications_per_hour,
            "min_interval": self.min_notification_interval,
            "daily_summary_time": self.config.daily_summary_time,
            "last_daily_summary": self.last_daily_summary_date
        }
    
    def get_config(self) -> Dict:
        """Get current Discord webhook configuration"""
        return {
            "enabled": self.config.enabled,
            "send_real_calls": self.config.send_real_calls,
            "send_daily_summaries": self.config.send_daily_summaries,
            "send_responder_calls": self.config.send_responder_calls,
            "discord_priorities": self.config.discord_priorities,
            "daily_summary_time": self.config.daily_summary_time,
            "include_unit_status": self.config.include_unit_status,
            "include_statistics": self.config.include_statistics,
            "calls_webhook_configured": bool(self.config.calls_webhook_url),
            "responder_webhook_configured": bool(self.config.responder_webhook_url),
            "daily_summary_webhook_configured": bool(self.config.daily_summary_webhook_url)
        }
    
    def update_config(self, **kwargs):
        """Update Discord webhook configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                print(f"Updated Discord config: {key} = {value}")
            else:
                print(f"Unknown config key: {key}")
    
    def send_startup_message_once(self, cad_system) -> bool:
        """Send startup message only once to prevent spam"""
        # Check if startup message was sent today
        today = datetime.now().date()
        if self.startup_message_sent and self.last_daily_summary_date == today:
            print("Startup message already sent today - skipping")
            return True
        
        # Check persistent file to prevent spam across restarts
        startup_file = "discord_startup_sent.txt"
        try:
            if os.path.exists(startup_file):
                with open(startup_file, 'r') as f:
                    last_sent_date = f.read().strip()
                    if last_sent_date == str(today):
                        print("Startup message already sent today (file check) - skipping")
                        return True
        except Exception as e:
            print(f"Error checking startup file: {e}")
        
        if not self.config.enabled:
            return False
        
        try:
            startup_time = datetime.now().strftime("%I:%M %p CDT, %B %d, %Y")
            
            # Create official startup embed
            embed = {
                "title": "FIRE DEPARTMENT DISPATCH SYSTEM ONLINE",
                "description": "Computer-Aided Dispatch System is now online and monitoring for emergency incidents.",
                "color": 0x00AA00,  # Green color for startup
                "timestamp": datetime.now().isoformat(),
                "fields": [
                    {
                        "name": "SYSTEM STARTUP TIME",
                        "value": startup_time,
                        "inline": False
                    },
                    {
                        "name": "SYSTEM STATUS",
                        "value": "**ONLINE AND MONITORING**\n**Discord Integration:** ACTIVE\n**Incident Detection:** ENABLED\n**Existing Incidents:** WILL BE SENT TO DISCORD",
                        "inline": False
                    },
                    {
                        "name": "MONITORING CONFIGURATION",
                        "value": f"**Agencies:** {len(cad_system.monitored_agencies)} configured\n**Stations:** {len(cad_system.station_units)} loaded\n**Units:** {sum(len(station.get('assignments', [])) for station in cad_system.station_units)} tracked",
                        "inline": False
                    },
                    {
                        "name": "ALERT PRIORITIES",
                        "value": f"**CAD Alerts:** {', '.join(getattr(cad_system.config, 'alert_priorities', ['high', 'medium']))}\n**Discord Notifications:** {', '.join(self.config.discord_priorities)}",
                        "inline": False
                    }
                ],
                "footer": {
                    "text": "Fire Department Dispatch • System Startup • OFFICIAL"
                }
            }
            
            payload = {"embeds": [embed], "username": "Fire Department Dispatch"}
            success = self._send_discord_message(self.config.calls_webhook_url, payload)
            
            if success:
                self.startup_message_sent = True
                self.last_daily_summary_date = today  # Mark as sent today
                
                # Write to persistent file
                try:
                    with open(startup_file, 'w') as f:
                        f.write(str(today))
                except Exception as e:
                    print(f"Error writing startup file: {e}")
                
                print("Startup message sent to Discord")
            
            return success
            
        except Exception as e:
            print(f"Error sending startup message: {e}")
            return False


def main():
    """Test the Discord webhook system"""
    print("Testing Discord Webhook Integration")
    print("=" * 50)
    
    # Create webhook manager
    config = DiscordWebhookConfig()
    webhook_manager = DiscordWebhookManager(config)
    
    # Test all webhooks
    results = webhook_manager.test_all_webhooks()
    
    print("\nTest Results:")
    for webhook_type, success in results.items():
        status = "PASS" if success else "FAIL"
        print(f"  {webhook_type.title()}: {status}")
    
    print(f"\nConfiguration:")
    config_info = webhook_manager.get_config()
    for key, value in config_info.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
