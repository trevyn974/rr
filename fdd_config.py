#!/usr/bin/env python3
"""
FDD CAD Configuration Management
Handles configuration for the Fire Department Dispatch scraper
"""

import json
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class LocationFilter:
    """Filter configuration for incident types"""
    allow_list: List[str] = field(default_factory=list)
    block_list: List[str] = field(default_factory=list)
    
    def is_allowed(self, incident_type: str) -> bool:
        """Check if an incident type is allowed"""
        if incident_type in self.block_list:
            return False
        if incident_type in self.allow_list:
            return True
        if "*" in self.block_list:
            return incident_type in self.allow_list
        return len(self.allow_list) == 0  # Allow all if no filters set


@dataclass
class MonitoringLocation:
    """Configuration for a location to monitor"""
    name: str
    address: str
    latitude: float = 0.0
    longitude: float = 0.0
    radius_meters: float = 1000.0
    importance_level: int = 1
    enabled: bool = True
    filters: LocationFilter = field(default_factory=LocationFilter)
    
    @property
    def coords(self) -> tuple[float, float]:
        return (self.latitude, self.longitude)


@dataclass
class FDDConfig:
    """Main configuration for FDD CAD scraper"""
    # Monitoring settings
    scan_interval_seconds: int = 60
    default_radius_meters: float = 1000.0
    
    # Agencies to monitor
    agencies: List[str] = field(default_factory=list)
    
    # Locations to monitor
    locations: List[MonitoringLocation] = field(default_factory=list)
    
    # Global filters
    global_filters: LocationFilter = field(default_factory=LocationFilter)
    
    # Notification settings
    notifications_enabled: bool = True
    notification_methods: List[str] = field(default_factory=lambda: ["console"])
    
    # Data storage
    data_retention_days: int = 30
    save_to_database: bool = False
    
    def add_agency(self, agency_id: str):
        """Add an agency to monitor"""
        if agency_id not in self.agencies:
            self.agencies.append(agency_id)
    
    def add_location(self, location: MonitoringLocation):
        """Add a monitoring location"""
        self.locations.append(location)
    
    def get_location_by_name(self, name: str) -> Optional[MonitoringLocation]:
        """Get location by name"""
        for location in self.locations:
            if location.name.lower() == name.lower():
                return location
        return None


class ConfigManager:
    """Manages configuration loading and saving"""
    
    def __init__(self, config_file: str = "fdd_config.json"):
        self.config_file = config_file
        self.config = FDDConfig()
    
    def load_config(self) -> FDDConfig:
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                self._parse_config_data(data)
            except Exception as e:
                print(f"Error loading config: {e}")
                print("Using default configuration")
        else:
            print(f"Config file {self.config_file} not found, using defaults")
        
        return self.config
    
    def save_config(self):
        """Save configuration to file"""
        try:
            data = self._config_to_dict()
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"Configuration saved to {self.config_file}")
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def _parse_config_data(self, data: Dict):
        """Parse configuration data from JSON"""
        self.config.scan_interval_seconds = data.get("scan_interval_seconds", 60)
        self.config.default_radius_meters = data.get("default_radius_meters", 1000.0)
        self.config.agencies = data.get("agencies", [])
        self.config.notifications_enabled = data.get("notifications_enabled", True)
        self.config.notification_methods = data.get("notification_methods", ["console"])
        self.config.data_retention_days = data.get("data_retention_days", 30)
        self.config.save_to_database = data.get("save_to_database", False)
        
        # Parse global filters
        global_filters_data = data.get("global_filters", {})
        self.config.global_filters = LocationFilter(
            allow_list=global_filters_data.get("allow_list", []),
            block_list=global_filters_data.get("block_list", [])
        )
        
        # Parse locations
        locations_data = data.get("locations", [])
        for loc_data in locations_data:
            filters_data = loc_data.get("filters", {})
            filters = LocationFilter(
                allow_list=filters_data.get("allow_list", []),
                block_list=filters_data.get("block_list", [])
            )
            
            location = MonitoringLocation(
                name=loc_data["name"],
                address=loc_data["address"],
                latitude=loc_data.get("latitude", 0.0),
                longitude=loc_data.get("longitude", 0.0),
                radius_meters=loc_data.get("radius_meters", 1000.0),
                importance_level=loc_data.get("importance_level", 1),
                enabled=loc_data.get("enabled", True),
                filters=filters
            )
            self.config.add_location(location)
    
    def _config_to_dict(self) -> Dict:
        """Convert configuration to dictionary for JSON serialization"""
        return {
            "scan_interval_seconds": self.config.scan_interval_seconds,
            "default_radius_meters": self.config.default_radius_meters,
            "agencies": self.config.agencies,
            "notifications_enabled": self.config.notifications_enabled,
            "notification_methods": self.config.notification_methods,
            "data_retention_days": self.config.data_retention_days,
            "save_to_database": self.config.save_to_database,
            "global_filters": {
                "allow_list": self.config.global_filters.allow_list,
                "block_list": self.config.global_filters.block_list
            },
            "locations": [
                {
                    "name": loc.name,
                    "address": loc.address,
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                    "radius_meters": loc.radius_meters,
                    "importance_level": loc.importance_level,
                    "enabled": loc.enabled,
                    "filters": {
                        "allow_list": loc.filters.allow_list,
                        "block_list": loc.filters.block_list
                    }
                }
                for loc in self.config.locations
            ]
        }


def create_default_config() -> FDDConfig:
    """Create a default configuration"""
    config = FDDConfig()
    
    # Add some default agencies
    config.add_agency("001")  # Portland Fire & Rescue
    config.add_agency("002")  # Seattle Fire Department
    config.add_agency("4600")  # Rogers Fire Department
    
    # Add default monitoring locations
    portland_location = MonitoringLocation(
        name="Downtown Portland",
        address="Portland, OR",
        latitude=45.5152,
        longitude=-122.6784,
        radius_meters=5000.0,
        importance_level=1
    )
    config.add_location(portland_location)
    
    rogers_location = MonitoringLocation(
        name="Rogers Arkansas",
        address="Rogers, AR",
        latitude=36.3320,
        longitude=-94.1185,
        radius_meters=5000.0,
        importance_level=1
    )
    config.add_location(rogers_location)
    
    return config


if __name__ == "__main__":
    # Test configuration management
    config_manager = ConfigManager()
    config = config_manager.load_config()
    
    print("FDD CAD Configuration")
    print("=" * 30)
    print(f"Scan interval: {config.scan_interval_seconds} seconds")
    print(f"Default radius: {config.default_radius_meters} meters")
    print(f"Agencies: {config.agencies}")
    print(f"Locations: {len(config.locations)}")
    
    for location in config.locations:
        print(f"  - {location.name}: {location.address}")
        print(f"    Radius: {location.radius_meters}m, Enabled: {location.enabled}")
