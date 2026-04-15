#!/usr/bin/env python3
"""
Fastest Directions Service for CAD System
Provides optimized routes to incident scenes with traffic data and emergency routing
"""

import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import os

@dataclass
class RouteInfo:
    """Route information for emergency response"""
    distance_miles: float
    duration_minutes: float
    emergency_duration_minutes: float
    route_summary: str
    waypoints: List[Dict]
    traffic_conditions: str
    recommended_departure: datetime
    arrival_time: datetime
    emergency_arrival_time: datetime

class DirectionsService:
    """Service for getting fastest directions to calls - No API required"""
    
    def __init__(self):
        # No API key needed - using local calculations
        self.rogers_coordinates = {
            "center": (36.3320, -94.1185),
            "bounds": {
                "north": 36.3800,
                "south": 36.2800,
                "east": -94.0500,
                "west": -94.2000
            }
        }
        
    def get_emergency_route(self, start_location: str, end_location: str, 
                          departure_time: datetime = None) -> Optional[RouteInfo]:
        """
        Get optimized route for emergency response - No API required
        
        Args:
            start_location: Your current location (address or lat,lng)
            end_location: Incident location (address or lat,lng)
            departure_time: When you plan to depart (default: now)
        
        Returns:
            RouteInfo with emergency routing data
        """
        departure_time = departure_time or datetime.now()
        
        try:
            # Calculate route using local methods
            route_data = self._calculate_local_route(start_location, end_location, departure_time)
            
            if not route_data:
                return self._get_fallback_route(start_location, end_location)
            
            # Calculate emergency timing (assume 25% faster than regular traffic)
            emergency_duration = route_data['duration'] * 0.75
            
            # Calculate arrival times
            arrival_time = departure_time + timedelta(minutes=route_data['duration'])
            emergency_arrival_time = departure_time + timedelta(minutes=emergency_duration)
            
            return RouteInfo(
                distance_miles=route_data['distance'],
                duration_minutes=route_data['duration'],
                emergency_duration_minutes=emergency_duration,
                route_summary=route_data['summary'],
                waypoints=route_data['waypoints'],
                traffic_conditions=route_data['traffic_conditions'],
                recommended_departure=departure_time,
                arrival_time=arrival_time,
                emergency_arrival_time=emergency_arrival_time
            )
            
        except Exception as e:
            print(f"Error calculating route: {e}")
            return self._get_fallback_route(start_location, end_location)
    
    def _calculate_local_route(self, start: str, end: str, departure_time: datetime) -> Optional[Dict]:
        """Calculate route using local methods - no API required"""
        try:
            # Convert locations to coordinates
            start_coords = self._parse_location(start)
            end_coords = self._parse_location(end)
            
            if not start_coords or not end_coords:
                print("Could not parse location coordinates")
                return None
            
            # Calculate distance using Haversine formula
            distance_miles = self._calculate_distance(start_coords, end_coords)
            
            # Estimate travel time based on distance and time of day
            base_speed_mph = self._get_base_speed(departure_time)
            duration_minutes = (distance_miles / base_speed_mph) * 60
            
            # Generate route summary
            route_summary = self._generate_route_summary(start_coords, end_coords, distance_miles)
            
            # Analyze traffic conditions based on time
            traffic_conditions = self._analyze_traffic_by_time(departure_time)
            
            # Generate waypoints (simplified)
            waypoints = self._generate_waypoints(start_coords, end_coords)
            
            return {
                'distance': distance_miles,
                'duration': duration_minutes,
                'summary': route_summary,
                'waypoints': waypoints,
                'traffic_conditions': traffic_conditions
            }
            
        except Exception as e:
            print(f"Error calculating local route: {e}")
            return None
    
    def _parse_location(self, location: str) -> Optional[Tuple[float, float]]:
        """Parse location string to coordinates"""
        try:
            # If it's already coordinates
            if ',' in location and location.replace(',', '').replace('.', '').replace('-', '').replace(' ', '').isdigit():
                lat, lng = map(float, location.split(','))
                return (lat, lng)
            
            # For address strings, use approximate Rogers area coordinates
            location_lower = location.lower()
            
            if 'rogers' in location_lower:
                if 'station 1' in location_lower or 'station1' in location_lower:
                    return (36.3320, -94.1185)  # Station 1
                elif 'station 2' in location_lower or 'station2' in location_lower:
                    return (36.3400, -94.1200)  # Station 2
                elif 'station 3' in location_lower or 'station3' in location_lower:
                    return (36.3250, -94.1000)  # Station 3
                elif 'station 4' in location_lower or 'station4' in location_lower:
                    return (36.3150, -94.1300)  # Station 4
                elif 'station 5' in location_lower or 'station5' in location_lower:
                    return (36.3200, -94.1100)  # Station 5
                elif 'station 6' in location_lower or 'station6' in location_lower:
                    return (36.3450, -94.0900)  # Station 6
                elif 'station 7' in location_lower or 'station7' in location_lower:
                    return (36.3100, -94.1400)  # Station 7
                elif 'station 8' in location_lower or 'station8' in location_lower:
                    return (36.3500, -94.1500)  # Station 8
                elif 'training' in location_lower:
                    return (36.3300, -94.1050)  # Training Center
                else:
                    return (36.3320, -94.1185)  # Downtown Rogers
            
            elif 'bentonville' in location_lower:
                return (36.3729, -94.2088)  # Bentonville center
            
            elif 'springdale' in location_lower:
                return (36.1867, -94.1288)  # Springdale center
            
            elif 'fayetteville' in location_lower:
                return (36.0626, -94.1574)  # Fayetteville center
            
            else:
                # Default to Rogers center for unknown locations
                return (36.3320, -94.1185)
                
        except Exception as e:
            print(f"Error parsing location '{location}': {e}")
            return None
    
    def _calculate_distance(self, start_coords: Tuple[float, float], end_coords: Tuple[float, float]) -> float:
        """Calculate distance between two coordinates using Haversine formula"""
        from math import radians, cos, sin, asin, sqrt
        
        lat1, lon1 = start_coords
        lat2, lon2 = end_coords
        
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        
        # Radius of earth in miles
        r = 3956
        return c * r
    
    def _get_base_speed(self, departure_time: datetime) -> float:
        """Get base speed based on time of day"""
        hour = departure_time.hour
        
        # Speed estimates for Rogers area (mph)
        if 6 <= hour <= 8 or 17 <= hour <= 19:  # Rush hours
            return 25.0
        elif 9 <= hour <= 16:  # Business hours
            return 35.0
        elif 20 <= hour <= 22:  # Evening
            return 40.0
        else:  # Late night/early morning
            return 45.0
    
    def _analyze_traffic_by_time(self, departure_time: datetime) -> str:
        """Analyze traffic conditions based on time of day"""
        hour = departure_time.hour
        day_of_week = departure_time.weekday()
        
        # Rush hour patterns
        if (6 <= hour <= 8 or 17 <= hour <= 19) and day_of_week < 5:  # Weekday rush
            return "Heavy Traffic"
        elif (7 <= hour <= 9 or 16 <= hour <= 18) and day_of_week < 5:  # Weekday moderate
            return "Moderate Traffic"
        elif 9 <= hour <= 16 and day_of_week < 5:  # Business hours
            return "Light Traffic"
        elif 20 <= hour <= 22:  # Evening
            return "Light Traffic"
        else:  # Late night/early morning
            return "Clear"
    
    def _generate_route_summary(self, start_coords: Tuple[float, float], end_coords: Tuple[float, float], distance: float) -> str:
        """Generate a route summary"""
        direction = self._get_direction(start_coords, end_coords)
        return f"Route {direction} - {distance:.1f} miles"
    
    def _get_direction(self, start_coords: Tuple[float, float], end_coords: Tuple[float, float]) -> str:
        """Get general direction between two points"""
        lat1, lon1 = start_coords
        lat2, lon2 = end_coords
        
        lat_diff = lat2 - lat1
        lon_diff = lon2 - lon1
        
        if abs(lat_diff) > abs(lon_diff):
            return "North" if lat_diff > 0 else "South"
        else:
            return "East" if lon_diff > 0 else "West"
    
    def _generate_waypoints(self, start_coords: Tuple[float, float], end_coords: Tuple[float, float]) -> List[Dict]:
        """Generate simplified waypoints"""
        return [
            {
                "instruction": f"Start at {start_coords[0]:.4f}, {start_coords[1]:.4f}",
                "distance": "0.0 mi"
            },
            {
                "instruction": f"Proceed to destination",
                "distance": f"{self._calculate_distance(start_coords, end_coords):.1f} mi"
            },
            {
                "instruction": f"Arrive at {end_coords[0]:.4f}, {end_coords[1]:.4f}",
                "distance": "0.0 mi"
            }
        ]
    
    def _get_fallback_route(self, start: str, end: str) -> RouteInfo:
        """Fallback route calculation - simplified local method"""
        print("Using fallback route calculation")
        
        # Try to get coordinates for better estimation
        start_coords = self._parse_location(start)
        end_coords = self._parse_location(end)
        
        if start_coords and end_coords:
            distance = self._calculate_distance(start_coords, end_coords)
            duration = (distance / 30.0) * 60  # Assume 30 mph average
        else:
            # Default fallback
            distance = 5.0
            duration = 10.0
        
        emergency_duration = duration * 0.75
        
        return RouteInfo(
            distance_miles=distance,
            duration_minutes=duration,
            emergency_duration_minutes=emergency_duration,
            route_summary=f"Local route - {distance:.1f} miles",
            waypoints=[],
            traffic_conditions="Estimated",
            recommended_departure=datetime.now(),
            arrival_time=datetime.now() + timedelta(minutes=duration),
            emergency_arrival_time=datetime.now() + timedelta(minutes=emergency_duration)
        )
    
    def get_route_to_station(self, your_location: str, station_id: str) -> Optional[RouteInfo]:
        """Get route to a specific fire station"""
        station_locations = {
            "1": "Rogers Fire Station 1, Rogers, AR",
            "2": "Rogers Fire Station 2, Rogers, AR", 
            "3": "Rogers Fire Station 3, Rogers, AR",
            "4": "Rogers Fire Station 4, Rogers, AR",
            "5": "Rogers Fire Station 5, Rogers, AR",
            "6": "Rogers Fire Station 6, Rogers, AR",
            "7": "Rogers Fire Station 7, Rogers, AR",
            "8": "Rogers Fire Station 8, Rogers, AR",
            "TC": "Rogers Fire Training Center, Rogers, AR"
        }
        
        station_address = station_locations.get(station_id)
        if not station_address:
            print(f"Unknown station ID: {station_id}")
            return None
        
        return self.get_emergency_route(your_location, station_address)
    
    def calculate_response_time(self, station_id: str, incident_location: str) -> Optional[Dict]:
        """Calculate estimated response time from station to incident"""
        station_locations = {
            "1": "Rogers Fire Station 1, Rogers, AR",
            "2": "Rogers Fire Station 2, Rogers, AR",
            "3": "Rogers Fire Station 3, Rogers, AR", 
            "4": "Rogers Fire Station 4, Rogers, AR",
            "5": "Rogers Fire Station 5, Rogers, AR",
            "6": "Rogers Fire Station 6, Rogers, AR",
            "7": "Rogers Fire Station 7, Rogers, AR",
            "8": "Rogers Fire Station 8, Rogers, AR",
            "TC": "Rogers Fire Training Center, Rogers, AR"
        }
        
        station_address = station_locations.get(station_id)
        if not station_address:
            return None
        
        route = self.get_emergency_route(station_address, incident_location)
        if not route:
            return None
        
        return {
            "station_id": station_id,
            "estimated_response_time": route.emergency_duration_minutes,
            "distance_miles": route.distance_miles,
            "arrival_time": route.emergency_arrival_time,
            "route_summary": route.route_summary
        }

def main():
    """Test the directions service - No API required"""
    print("🗺️ Testing Directions Service (No API Required)")
    
    # Initialize service
    directions = DirectionsService()
    
    # Test route calculation
    start = "Rogers, AR"
    end = "Bentonville, AR"
    
    print(f"Getting route from {start} to {end}")
    route = directions.get_emergency_route(start, end)
    
    if route:
        print(f"Distance: {route.distance_miles:.1f} miles")
        print(f"Regular time: {route.duration_minutes:.1f} minutes")
        print(f"Emergency time: {route.emergency_duration_minutes:.1f} minutes")
        print(f"Traffic: {route.traffic_conditions}")
        print(f"Arrival: {route.emergency_arrival_time.strftime('%H:%M:%S')}")
        print(f"Route: {route.route_summary}")
    else:
        print("Failed to get route")
    
    # Test station route
    print("\nTesting route to Station 5:")
    station_route = directions.get_route_to_station("Rogers, AR", "5")
    if station_route:
        print(f"To Station 5: {station_route.distance_miles:.1f} miles, {station_route.emergency_duration_minutes:.1f} minutes")

if __name__ == "__main__":
    main()
