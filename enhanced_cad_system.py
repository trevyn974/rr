#!/usr/bin/env python3
"""
Enhanced CAD System with Directions and AI Prediction
Integrates fastest directions and smart learning AI for optimal fire response filming
"""

import asyncio
import json
import time
import os
import subprocess
import platform
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
from dataclasses import dataclass, asdict

# Import our enhanced modules
from cad_system import CADSystem, CADConfig, CADAlert
from directions_service import DirectionsService, RouteInfo
from ai_predictor import AIPredictor, CallPrediction, PeakTimeAnalysis, HotZoneAnalysis

@dataclass
class FilmingOpportunity:
    """Opportunity for filming fire response"""
    incident_id: str
    incident_type: str
    address: str
    predicted_arrival_time: datetime
    route_to_scene: RouteInfo
    route_to_station: RouteInfo
    probability_score: float
    filming_recommendation: str
    safety_notes: str

class EnhancedCADSystem(CADSystem):
    """Enhanced CAD system with directions and AI prediction"""
    
    def __init__(self, config: CADConfig = None, your_location: str = "Rogers, AR"):
        super().__init__(config)
        
        # Initialize enhanced services
        self.directions_service = DirectionsService()
        self.ai_predictor = AIPredictor()
        self.your_location = your_location
        
        # Filming tracking
        self.filming_opportunities: List[FilmingOpportunity] = []
        self.video_logs: List[Dict] = []
        
        print("🚨 Enhanced CAD System initialized with directions and AI prediction")
        print(f"📍 Your location: {your_location}")
    
    def get_route_to_call(self, incident_address: str, departure_time: datetime = None) -> Optional[RouteInfo]:
        """Get fastest route to an incident scene"""
        try:
            route = self.directions_service.get_emergency_route(
                self.your_location, 
                incident_address, 
                departure_time
            )
            
            if route:
                print(f"🗺️ Route to call: {route.distance_miles:.1f} miles, {route.emergency_duration_minutes:.1f} minutes")
                print(f"🚦 Traffic: {route.traffic_conditions}")
                print(f"⏰ Arrival: {route.emergency_arrival_time.strftime('%H:%M:%S')}")
            
            return route
            
        except Exception as e:
            print(f"Error getting route to call: {e}")
            return None
    
    def get_route_to_station(self, station_id: str) -> Optional[RouteInfo]:
        """Get route to a specific fire station"""
        try:
            route = self.directions_service.get_route_to_station(self.your_location, station_id)
            
            if route:
                print(f"🏢 Route to Station {station_id}: {route.distance_miles:.1f} miles, {route.emergency_duration_minutes:.1f} minutes")
            
            return route
            
        except Exception as e:
            print(f"Error getting route to station: {e}")
            return None
    
    def analyze_filming_opportunity(self, incident) -> Optional[FilmingOpportunity]:
        """Analyze if an incident is worth filming"""
        try:
            # Get route to scene
            route_to_scene = self.get_route_to_call(incident.FullDisplayAddress)
            if not route_to_scene:
                return None
            
            # Determine which station is responding
            responding_station = self._get_responding_station(incident)
            route_to_station = None
            
            if responding_station:
                route_to_station = self.get_route_to_station(responding_station)
            
            # Calculate probability score
            probability_score = self._calculate_filming_probability(incident, route_to_scene)
            
            # Generate recommendations
            filming_recommendation = self._generate_filming_recommendation(incident, route_to_scene, probability_score)
            safety_notes = self._generate_safety_notes(incident, route_to_scene)
            
            opportunity = FilmingOpportunity(
                incident_id=incident.ID,
                incident_type=incident.incident_type,
                address=incident.FullDisplayAddress,
                predicted_arrival_time=route_to_scene.emergency_arrival_time,
                route_to_scene=route_to_scene,
                route_to_station=route_to_station,
                probability_score=probability_score,
                filming_recommendation=filming_recommendation,
                safety_notes=safety_notes
            )
            
            self.filming_opportunities.append(opportunity)
            
            # Log incident for AI training
            self._log_incident_for_ai(incident)
            
            return opportunity
            
        except Exception as e:
            print(f"Error analyzing filming opportunity: {e}")
            return None
    
    def get_ai_predictions(self) -> Dict:
        """Get AI predictions for optimal filming"""
        try:
            recommendations = self.ai_predictor.get_filming_recommendations()
            
            print("🤖 AI Filming Recommendations:")
            print(f"📊 Strategy: {recommendations['recommendation']}")
            
            if recommendations['immediate_opportunities']:
                print("🎯 Immediate Opportunities:")
                for opp in recommendations['immediate_opportunities'][:3]:
                    print(f"  - {opp.incident_type} in {opp.location_zone} at {opp.time_window} ({opp.probability:.0%} chance)")
            
            if recommendations['best_zones']:
                print("🔥 Best Zones:")
                for zone in recommendations['best_zones'][:3]:
                    print(f"  - {zone.zone_name}: {zone.call_frequency:.1f} calls/day")
            
            if recommendations['peak_times']:
                print("⏰ Peak Times:")
                for peak in recommendations['peak_times'][:3]:
                    print(f"  - {peak.day_of_week} at {peak.hour:02d}:00 ({peak.call_count} calls)")
            
            return recommendations
            
        except Exception as e:
            print(f"Error getting AI predictions: {e}")
            return {}
    
    def get_smart_positioning_advice(self) -> str:
        """Get advice on where to position for filming"""
        try:
            predictions = self.ai_predictor.predict_next_call(4)  # Next 4 hours
            hot_zones = self.ai_predictor.analyze_hot_zones()
            
            if not predictions and not hot_zones:
                return "No strong patterns detected. Monitor system for real-time alerts."
            
            advice_parts = []
            
            # High probability calls
            high_prob_calls = [p for p in predictions if p.probability > 0.4]
            if high_prob_calls:
                top_call = high_prob_calls[0]
                advice_parts.append(f"🎯 HIGH PROBABILITY: {top_call.incident_type} in {top_call.location_zone} at {top_call.time_window} ({top_call.probability:.0%} chance)")
            
            # Best zones
            if hot_zones:
                best_zone = hot_zones[0]
                advice_parts.append(f"🔥 BEST ZONE: {best_zone.zone_name} area (avg {best_zone.call_frequency:.1f} calls/day)")
            
            # Peak times
            peak_times = self.ai_predictor.analyze_peak_times()
            if peak_times:
                best_time = peak_times[0]
                advice_parts.append(f"⏰ PEAK TIME: {best_time.day_of_week} at {best_time.hour:02d}:00 ({best_time.call_count} calls)")
            
            return " | ".join(advice_parts)
            
        except Exception as e:
            print(f"Error getting positioning advice: {e}")
            return "Error getting positioning advice"
    
    def log_video_success(self, incident_id: str, video_data: Dict):
        """Log successful video recording"""
        try:
            self.ai_predictor.log_video_success(incident_id, video_data)
            self.video_logs.append({
                "incident_id": incident_id,
                "timestamp": datetime.now(),
                "data": video_data
            })
            
            print(f"📹 Video success logged for incident {incident_id}")
            
        except Exception as e:
            print(f"Error logging video success: {e}")
    
    def get_filming_stats(self) -> Dict:
        """Get statistics about filming success"""
        try:
            total_opportunities = len(self.filming_opportunities)
            successful_videos = len(self.video_logs)
            
            # Calculate success rate
            success_rate = (successful_videos / total_opportunities * 100) if total_opportunities > 0 else 0
            
            # Get recent opportunities
            recent_opportunities = self.filming_opportunities[-10:] if self.filming_opportunities else []
            
            stats = {
                "total_opportunities": total_opportunities,
                "successful_videos": successful_videos,
                "success_rate": success_rate,
                "recent_opportunities": [asdict(opp) for opp in recent_opportunities],
                "ai_recommendations": self.get_ai_predictions()
            }
            
            return stats
            
        except Exception as e:
            print(f"Error getting filming stats: {e}")
            return {}
    
    def _get_responding_station(self, incident) -> Optional[str]:
        """Determine which station is responding to an incident"""
        try:
            if not incident.Unit:
                return None
            
            # Get unit IDs
            unit_ids = []
            if isinstance(incident.Unit, list):
                for unit in incident.Unit:
                    if hasattr(unit, 'UnitID'):
                        unit_ids.append(unit.UnitID)
            elif isinstance(incident.Unit, str):
                unit_ids.append(incident.Unit)
            
            # Map units to stations
            for unit_id in unit_ids:
                station = self.get_unit_station(unit_id)
                if station:
                    # Extract station number from station name
                    if "STATION" in station:
                        station_num = station.split()[-1]
                        return station_num
            
            return None
            
        except Exception as e:
            print(f"Error determining responding station: {e}")
            return None
    
    def _calculate_filming_probability(self, incident, route: RouteInfo) -> float:
        """Calculate probability that filming will be successful"""
        try:
            base_score = 0.5
            
            # Distance factor (closer = better)
            if route.distance_miles <= 2.0:
                base_score += 0.3
            elif route.distance_miles <= 5.0:
                base_score += 0.2
            elif route.distance_miles <= 10.0:
                base_score += 0.1
            
            # Time factor (faster arrival = better)
            if route.emergency_duration_minutes <= 5.0:
                base_score += 0.2
            elif route.emergency_duration_minutes <= 10.0:
                base_score += 0.1
            
            # Incident type factor
            high_interest_types = ["Structure Fire", "Hazardous Materials", "Rescue Operation"]
            if incident.incident_type in high_interest_types:
                base_score += 0.2
            
            # Traffic factor
            if route.traffic_conditions == "Clear":
                base_score += 0.1
            elif route.traffic_conditions == "Heavy Traffic":
                base_score -= 0.1
            
            return min(max(base_score, 0.0), 1.0)
            
        except Exception as e:
            print(f"Error calculating filming probability: {e}")
            return 0.5
    
    def _generate_filming_recommendation(self, incident, route: RouteInfo, probability: float) -> str:
        """Generate filming recommendation"""
        try:
            if probability >= 0.8:
                return f"EXCELLENT opportunity! {route.emergency_duration_minutes:.1f} min to scene. High visual potential."
            elif probability >= 0.6:
                return f"GOOD opportunity. {route.emergency_duration_minutes:.1f} min to scene. Worth filming."
            elif probability >= 0.4:
                return f"MODERATE opportunity. {route.emergency_duration_minutes:.1f} min to scene. Consider filming."
            else:
                return f"LOW opportunity. {route.emergency_duration_minutes:.1f} min to scene. May not be worth it."
                
        except Exception as e:
            print(f"Error generating filming recommendation: {e}")
            return "Unable to generate recommendation"
    
    def _generate_safety_notes(self, incident, route: RouteInfo) -> str:
        """Generate safety notes for filming"""
        try:
            notes = []
            
            # Distance safety
            if route.distance_miles > 10.0:
                notes.append("Long distance - ensure fuel and safety equipment")
            
            # Traffic safety
            if route.traffic_conditions == "Heavy Traffic":
                notes.append("Heavy traffic - drive safely, don't rush")
            
            # Incident type safety
            if incident.incident_type in ["Hazardous Materials", "Structure Fire"]:
                notes.append("High-risk incident - maintain safe distance")
            
            # Time safety
            if route.emergency_duration_minutes > 15.0:
                notes.append("Long response time - incident may be resolved before arrival")
            
            return " | ".join(notes) if notes else "Standard safety precautions apply"
            
        except Exception as e:
            print(f"Error generating safety notes: {e}")
            return "Safety notes unavailable"
    
    def _log_incident_for_ai(self, incident):
        """Log incident data for AI training"""
        try:
            incident_data = {
                "id": incident.ID,
                "incident_type": incident.incident_type,
                "address": incident.FullDisplayAddress,
                "latitude": getattr(incident, 'Latitude', None),
                "longitude": getattr(incident, 'Longitude', None),
                "call_time": incident.CallReceivedDateTime.isoformat() if hasattr(incident.CallReceivedDateTime, 'isoformat') else str(incident.CallReceivedDateTime),
                "response_time": 0,  # Could be calculated if needed
                "units": [unit.UnitID for unit in incident.Unit] if incident.Unit else []
            }
            
            self.ai_predictor.log_incident(incident_data)
            
        except Exception as e:
            print(f"Error logging incident for AI: {e}")
    
    def enhanced_announce_new_incident(self, incident):
        """Enhanced incident announcement with filming analysis"""
        try:
            # Standard announcement
            self.announce_new_incident(incident)
            
            # Analyze filming opportunity
            opportunity = self.analyze_filming_opportunity(incident)
            
            if opportunity:
                print(f"🎬 FILMING OPPORTUNITY: {opportunity.filming_recommendation}")
                print(f"📍 Route: {opportunity.route_to_scene.distance_miles:.1f} miles, {opportunity.route_to_scene.emergency_duration_minutes:.1f} minutes")
                print(f"⏰ Arrival: {opportunity.predicted_arrival_time.strftime('%H:%M:%S')}")
                print(f"🎯 Score: {opportunity.probability_score:.0%}")
                print(f"⚠️ Safety: {opportunity.safety_notes}")
                
                # TTS announcement for high-probability opportunities
                if opportunity.probability_score >= 0.7:
                    tts_message = f"High filming opportunity. {opportunity.incident_type} at {opportunity.route_to_scene.distance_miles:.1f} miles. Estimated arrival in {opportunity.route_to_scene.emergency_duration_minutes:.0f} minutes."
                    self._speak_text(tts_message)
            
        except Exception as e:
            print(f"Error in enhanced incident announcement: {e}")
            # Fallback to standard announcement
            self.announce_new_incident(incident)

def main():
    """Main function to run the enhanced CAD system"""
    print("🚨 Enhanced FDD CAD System - With Directions & AI Prediction")
    print("=" * 70)
    
    # Create enhanced CAD system
    config = CADConfig(
        refresh_interval=30,
        max_incidents_display=25,
        auto_refresh=True,
        sound_alerts=True,
        tts_enabled=True,
        theme="dark"
    )
    
    # Initialize with your location
    your_location = "Rogers, AR"  # Change this to your actual location
    cad = EnhancedCADSystem(config, your_location)
    
    # Add Rogers Fire Department
    cad.add_agency("04600")
    
    # Start monitoring
    cad.start_monitoring()
    
    try:
        print(f"\n🎬 Enhanced CAD System running from {your_location}")
        print("Press Ctrl+C to stop")
        
        # Show AI recommendations on startup
        print("\n🤖 Getting AI recommendations...")
        recommendations = cad.get_ai_predictions()
        
        print("\n📊 Smart positioning advice:")
        advice = cad.get_smart_positioning_advice()
        print(advice)
        
        while True:
            time.sleep(10)
            
            # Display status
            status = cad.get_status_summary()
            print(f"\n📊 CAD Status: {status['active_incidents']} active, "
                  f"{status['recent_incidents']} recent, "
                  f"{status['unacknowledged_alerts']} unacknowledged alerts")
            
            # Show filming opportunities
            if cad.filming_opportunities:
                recent_opp = cad.filming_opportunities[-1]
                print(f"🎬 Latest opportunity: {recent_opp.incident_type} - {recent_opp.filming_recommendation}")
    
    except KeyboardInterrupt:
        print("\n\nStopping Enhanced CAD System...")
        cad.stop_monitoring()
        
        # Show final stats
        stats = cad.get_filming_stats()
        print(f"\n📹 Filming Stats:")
        print(f"Total opportunities: {stats['total_opportunities']}")
        print(f"Successful videos: {stats['successful_videos']}")
        print(f"Success rate: {stats['success_rate']:.1f}%")
        
        print("Enhanced CAD System stopped.")

if __name__ == "__main__":
    main()
