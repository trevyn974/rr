#!/usr/bin/env python3
"""
FDD CAD Setup Helper
Interactive setup tool for configuring the Fire Department Dispatch scraper
"""

import json
import os
from cmd import Cmd
from fdd_cad_scraper import FDDCADScraper
from fdd_config import ConfigManager, MonitoringLocation, LocationFilter


class FDDSetup(Cmd):
    """Interactive setup command interface for FDD CAD scraper"""
    
    intro = """
FDD CAD Scraper Setup
====================
Welcome to the Fire Department Dispatch CAD scraper setup.
This tool will help you configure agencies and locations to monitor.

Type 'help' for available commands or 'quit' to exit.
"""
    
    prompt = "FDD> "
    
    def __init__(self):
        super().__init__()
        self.scraper = FDDCADScraper()
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()
        
        # Get available agencies
        self.available_agencies = self.scraper.list_agencies()
    
    def do_agencies(self, args):
        """List all available fire department agencies"""
        print("\nAvailable Fire Department Agencies:")
        print("-" * 40)
        
        if not self.available_agencies:
            print("No agencies found. Check your connection or API configuration.")
            return
        
        for i, agency_name in enumerate(self.available_agencies, 1):
            print(f"{i:2d}. {agency_name}")
        
        print(f"\nCurrently monitoring: {len(self.config.agencies)} agencies")
        if self.config.agencies:
            print("Monitored agencies:")
            for agency_id in self.config.agencies:
                agency = self.scraper.get_agency_by_name(agency_id)
                if agency:
                    print(f"  - {agency['agencyname']} (ID: {agency_id})")
    
    def do_add_agency(self, agency_name):
        """Add an agency to monitor
        Usage: add_agency <agency_name_or_id>
        """
        if not agency_name:
            print("Please specify an agency name or ID")
            return
        
        # Try to find the agency
        agency = self.scraper.get_agency_by_name(agency_name)
        if not agency:
            print(f"Agency '{agency_name}' not found")
            print("Use 'agencies' command to see available agencies")
            return
        
        agency_id = agency['agencyid']
        if agency_id in self.config.agencies:
            print(f"Agency {agency['agencyname']} is already being monitored")
            return
        
        self.config.add_agency(agency_id)
        self.config_manager.save_config()
        print(f"Added agency: {agency['agencyname']} (ID: {agency_id})")
    
    def do_remove_agency(self, agency_name):
        """Remove an agency from monitoring
        Usage: remove_agency <agency_name_or_id>
        """
        if not agency_name:
            print("Please specify an agency name or ID")
            return
        
        # Find the agency
        agency = self.scraper.get_agency_by_name(agency_name)
        if not agency:
            print(f"Agency '{agency_name}' not found")
            return
        
        agency_id = agency['agencyid']
        if agency_id not in self.config.agencies:
            print(f"Agency {agency['agencyname']} is not being monitored")
            return
        
        self.config.agencies.remove(agency_id)
        self.config_manager.save_config()
        print(f"Removed agency: {agency['agencyname']}")
    
    def do_locations(self, args):
        """List all monitoring locations"""
        print("\nMonitoring Locations:")
        print("-" * 30)
        
        if not self.config.locations:
            print("No locations configured")
            return
        
        for i, location in enumerate(self.config.locations, 1):
            status = "ENABLED" if location.enabled else "DISABLED"
            print(f"{i:2d}. {location.name} - {status}")
            print(f"    Address: {location.address}")
            print(f"    Radius: {location.radius_meters}m")
            print(f"    Importance: {location.importance_level}")
            print()
    
    def do_add_location(self, args):
        """Add a monitoring location
        Usage: add_location
        """
        print("\nAdding new monitoring location:")
        
        name = input("Location name: ").strip()
        if not name:
            print("Location name is required")
            return
        
        address = input("Address: ").strip()
        if not address:
            print("Address is required")
            return
        
        # Get radius
        radius_input = input(f"Radius in meters (default {self.config.default_radius_meters}): ").strip()
        try:
            radius = float(radius_input) if radius_input else self.config.default_radius_meters
        except ValueError:
            print("Invalid radius, using default")
            radius = self.config.default_radius_meters
        
        # Get importance level
        importance_input = input("Importance level 1-5 (default 1): ").strip()
        try:
            importance = int(importance_input) if importance_input else 1
            importance = max(1, min(5, importance))  # Clamp between 1-5
        except ValueError:
            print("Invalid importance level, using default")
            importance = 1
        
        # Create location
        location = MonitoringLocation(
            name=name,
            address=address,
            radius_meters=radius,
            importance_level=importance
        )
        
        self.config.add_location(location)
        self.config_manager.save_config()
        print(f"Added location: {name}")
    
    def do_remove_location(self, location_name):
        """Remove a monitoring location
        Usage: remove_location <location_name>
        """
        if not location_name:
            print("Please specify a location name")
            return
        
        location = self.config.get_location_by_name(location_name)
        if not location:
            print(f"Location '{location_name}' not found")
            return
        
        self.config.locations.remove(location)
        self.config_manager.save_config()
        print(f"Removed location: {location_name}")
    
    def do_test_agency(self, agency_name):
        """Test connection to an agency and show recent incidents
        Usage: test_agency <agency_name_or_id>
        """
        if not agency_name:
            print("Please specify an agency name or ID")
            return
        
        agency = self.scraper.get_agency_by_name(agency_name)
        if not agency:
            print(f"Agency '{agency_name}' not found")
            return
        
        print(f"\nTesting connection to {agency['agencyname']}...")
        
        try:
            incidents = self.scraper.get_incidents(agency['agencyid'])
            
            print(f"Active incidents: {len(incidents.active)}")
            print(f"Recent incidents: {len(incidents.recent)}")
            
            if incidents.active:
                print("\nActive incidents:")
                for incident in incidents.active:
                    print(f"  - {incident.incident_type}")
                    print(f"    Address: {incident.FullDisplayAddress}")
                    print(f"    Time: {incident.CallReceivedDateTime}")
                    if incident.Unit:
                        print(f"    Units: {[unit.UnitID for unit in incident.Unit]}")
                    print()
            
            if incidents.recent:
                print("Recent incidents:")
                for incident in incidents.recent:
                    print(f"  - {incident.incident_type} at {incident.FullDisplayAddress}")
            
        except Exception as e:
            print(f"Error testing agency: {e}")
    
    def do_config(self, args):
        """Show current configuration"""
        print("\nCurrent Configuration:")
        print("-" * 25)
        print(f"Scan interval: {self.config.scan_interval_seconds} seconds")
        print(f"Default radius: {self.config.default_radius_meters} meters")
        print(f"Notifications: {'Enabled' if self.config.notifications_enabled else 'Disabled'}")
        print(f"Data retention: {self.config.data_retention_days} days")
        print(f"Save to database: {'Yes' if self.config.save_to_database else 'No'}")
        print(f"Agencies: {len(self.config.agencies)}")
        print(f"Locations: {len(self.config.locations)}")
    
    def do_save(self, args):
        """Save current configuration"""
        self.config_manager.save_config()
        print("Configuration saved")
    
    def do_quit(self, args):
        """Exit the setup tool"""
        print("Goodbye!")
        return True
    
    def do_exit(self, args):
        """Exit the setup tool"""
        return self.do_quit(args)
    
    def do_EOF(self, args):
        """Handle Ctrl+D"""
        return self.do_quit(args)
    
    def complete_add_agency(self, text, line, begidx, endidx):
        """Auto-complete for add_agency command"""
        if not text:
            return self.available_agencies[:]
        else:
            return [agency for agency in self.available_agencies 
                   if agency.lower().startswith(text.lower())]
    
    def complete_remove_agency(self, text, line, begidx, endidx):
        """Auto-complete for remove_agency command"""
        if not text:
            return [agency['agencyname'] for agency in self.config.agencies 
                   if self.scraper.get_agency_by_name(agency)]
        else:
            return [agency['agencyname'] for agency in self.config.agencies 
                   if self.scraper.get_agency_by_name(agency) and 
                   agency['agencyname'].lower().startswith(text.lower())]
    
    def complete_test_agency(self, text, line, begidx, endidx):
        """Auto-complete for test_agency command"""
        return self.complete_add_agency(text, line, begidx, endidx)


def main():
    """Main function to run the setup tool"""
    print("Starting FDD CAD Scraper Setup...")
    
    try:
        setup = FDDSetup()
        setup.cmdloop()
    except KeyboardInterrupt:
        print("\nSetup interrupted by user")
    except Exception as e:
        print(f"Setup error: {e}")


if __name__ == "__main__":
    main()
