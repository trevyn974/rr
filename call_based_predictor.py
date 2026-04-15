#!/usr/bin/env python3
"""
Call-Based Predictor
Predicts future calls based solely on historical call patterns.
Uses only call timing and frequency data - no external factors.
Gets real active and recent calls from FDDCADScraper.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict
import statistics
import math
from fdd_cad_scraper import FDDCADScraper, Incident
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS


@dataclass
class CallPrediction:
    """Prediction for next call"""
    predicted_time: datetime
    confidence: float
    reasoning: str
    expected_interval_minutes: float
    time_until_prediction_minutes: float
    prediction_interval_start: Optional[datetime] = None
    prediction_interval_end: Optional[datetime] = None
    best_case_time: Optional[datetime] = None
    worst_case_time: Optional[datetime] = None
    predicted_incident_type: Optional[str] = None
    day_of_week_pattern: Optional[str] = None
    seasonal_factor: Optional[str] = None


@dataclass
class CallPattern:
    """Pattern extracted from call history"""
    pattern_type: str
    value: any
    frequency: int
    average_interval_minutes: float


class CallBasedPredictor:
    """Predicts calls based only on historical call data"""
    
    def __init__(self, db_path: str = "call_history.db", agency_id: str = "04600"):
        self.db_path = db_path
        self.agency_id = agency_id
        self.scraper = FDDCADScraper()
        self._init_database()
    
    def _init_database(self):
        """Initialize database tables (creates connection per operation for thread safety)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create predictions tracking table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS predictions_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_time TIMESTAMP,
                    predicted_time TIMESTAMP,
                    predicted_interval_minutes REAL,
                    confidence REAL,
                    actual_call_time TIMESTAMP,
                    actual_interval_minutes REAL,
                    accuracy_minutes REAL,
                    was_accurate BOOLEAN,
                    within_15_min BOOLEAN,
                    within_30_min BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create confidence trends table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS confidence_trends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP,
                    confidence REAL,
                    prediction_interval REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_prediction_time ON predictions_log(prediction_time)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_confidence_timestamp ON confidence_trends(timestamp)
            ''')
            
            conn.commit()
            conn.close()
            print(f"✅ Database initialized: {self.db_path}")
        except Exception as e:
            print(f"❌ Database initialization error: {e}")
    
    def _get_db_connection(self):
        """Get a new database connection (thread-safe)"""
        return sqlite3.connect(self.db_path)
    
    def _incident_to_dict(self, incident: Incident) -> Dict:
        """Convert Incident object to dictionary format"""
        call_time = incident.CallReceivedDateTime
        if call_time and hasattr(call_time, 'replace'):
            # Remove timezone if present
            if hasattr(call_time, 'tzinfo') and call_time.tzinfo:
                call_time = call_time.replace(tzinfo=None)
        
        # Check if incident is active (not closed)
        is_active = True
        if hasattr(incident, 'ClosedDateTime') and incident.ClosedDateTime:
            default_date = datetime(year=1990, month=1, day=1)
            if incident.ClosedDateTime != default_date:
                is_active = False
        
        return {
            'incident_id': str(incident.ID),
            'incident_type': incident.incident_type if hasattr(incident, 'incident_type') else getattr(incident, 'PulsePointIncidentCallType', 'Unknown'),
            'call_time': call_time,
            'latitude': incident.Latitude if hasattr(incident, 'Latitude') else None,
            'longitude': incident.Longitude if hasattr(incident, 'Longitude') else None,
            'address': incident.FullDisplayAddress if hasattr(incident, 'FullDisplayAddress') else '',
            'is_active': is_active
        }
    
    def get_active_calls(self) -> List[Dict]:
        """Get active calls from FDDCADScraper"""
        try:
            incidents = self.scraper.get_incidents(self.agency_id)
            if not incidents or not hasattr(incidents, 'active'):
                return []
            
            active_calls = []
            for incident in incidents.active or []:
                call_dict = self._incident_to_dict(incident)
                call_dict['is_active'] = True
                active_calls.append(call_dict)
            
            return active_calls
        except Exception as e:
            print(f"[ERROR] Error getting active calls: {e}")
            return []
    
    def get_recent_calls(self) -> List[Dict]:
        """Get recent (closed) calls from FDDCADScraper"""
        try:
            incidents = self.scraper.get_incidents(self.agency_id)
            if not incidents or not hasattr(incidents, 'recent'):
                return []
            
            recent_calls = []
            for incident in incidents.recent or []:
                call_dict = self._incident_to_dict(incident)
                call_dict['is_active'] = False
                recent_calls.append(call_dict)
            
            return recent_calls
        except Exception as e:
            print(f"[ERROR] Error getting recent calls: {e}")
            return []
    
    def get_database_calls(self, days: Optional[int] = None) -> List[Dict]:
        """Get historical calls from database"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            if days:
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                cursor.execute('''
                    SELECT incident_id, incident_type, call_time, latitude, longitude, address
                    FROM incidents 
                    WHERE call_time >= ?
                    ORDER BY call_time ASC
                ''', (cutoff,))
            else:
                cursor.execute('''
                    SELECT incident_id, incident_type, call_time, latitude, longitude, address
                    FROM incidents 
                    ORDER BY call_time ASC
                ''')
            
            columns = [desc[0] for desc in cursor.description]
            calls = []
            for row in cursor.fetchall():
                call_dict = dict(zip(columns, row))
                # Parse call_time to datetime
                if call_dict.get('call_time'):
                    try:
                        call_dict['call_time'] = datetime.fromisoformat(call_dict['call_time'].replace('Z', '+00:00'))
                        if call_dict['call_time'].tzinfo:
                            call_dict['call_time'] = call_dict['call_time'].replace(tzinfo=None)
                        call_dict['is_active'] = False  # Database calls are historical
                    except:
                        continue
                calls.append(call_dict)
            
            conn.close()
            return calls
        except Exception as e:
            print(f"[ERROR] Error getting database calls: {e}")
            return []
    
    def get_all_calls(self, days: Optional[int] = None, include_active: bool = True, include_recent: bool = True) -> List[Dict]:
        """Get all calls: active, recent, and from database"""
        all_calls = []
        
        # Get active calls from scraper
        if include_active:
            active_calls = self.get_active_calls()
            all_calls.extend(active_calls)
            print(f"[INFO] Found {len(active_calls)} active calls")
        
        # Get recent calls from scraper
        if include_recent:
            recent_calls = self.get_recent_calls()
            all_calls.extend(recent_calls)
            print(f"[INFO] Found {len(recent_calls)} recent calls")
        
        # Get historical calls from database
        db_calls = self.get_database_calls(days=days)
        all_calls.extend(db_calls)
        print(f"[INFO] Found {len(db_calls)} database calls")
        
        # Remove duplicates based on incident_id
        seen_ids = set()
        unique_calls = []
        for call in all_calls:
            call_id = call.get('incident_id')
            if call_id and call_id not in seen_ids:
                seen_ids.add(call_id)
                unique_calls.append(call)
            elif not call_id:
                # Include calls without ID (shouldn't happen but be safe)
                unique_calls.append(call)
        
        # Sort by call_time
        unique_calls.sort(key=lambda x: x.get('call_time', datetime.min))
        
        print(f"[INFO] Total unique calls: {len(unique_calls)}")
        return unique_calls
    
    def analyze_call_intervals(self, calls: List[Dict]) -> Dict:
        """Analyze time intervals between calls"""
        if len(calls) < 2:
            return {
                'average_interval_minutes': 0,
                'median_interval_minutes': 0,
                'min_interval_minutes': 0,
                'max_interval_minutes': 0,
                'recent_average_minutes': 0,
                'intervals': []
            }
        
        intervals = []
        for i in range(1, len(calls)):
            if calls[i].get('call_time') and calls[i-1].get('call_time'):
                try:
                    interval = (calls[i]['call_time'] - calls[i-1]['call_time']).total_seconds() / 60
                    if interval > 0 and interval < 10080:  # Filter out negative and >7 days
                        intervals.append(interval)
                except:
                    continue
        
        if not intervals:
            return {
                'average_interval_minutes': 0,
                'median_interval_minutes': 0,
                'min_interval_minutes': 0,
                'max_interval_minutes': 0,
                'recent_average_minutes': 0,
                'intervals': []
            }
        
        # Calculate recent average (last 20% of intervals)
        recent_count = max(1, len(intervals) // 5)
        recent_intervals = intervals[-recent_count:]
        
        return {
            'average_interval_minutes': statistics.mean(intervals),
            'median_interval_minutes': statistics.median(intervals),
            'min_interval_minutes': min(intervals),
            'max_interval_minutes': max(intervals),
            'recent_average_minutes': statistics.mean(recent_intervals) if recent_intervals else statistics.mean(intervals),
            'intervals': intervals
        }
    
    def analyze_hourly_patterns(self, calls: List[Dict]) -> Dict:
        """Analyze call patterns by hour of day"""
        hourly_counts = defaultdict(int)
        hourly_calls = defaultdict(list)
        
        for call in calls:
            if call.get('call_time'):
                hour = call['call_time'].hour
                hourly_counts[hour] += 1
                hourly_calls[hour].append(call['call_time'])
        
        # Calculate average intervals per hour
        hourly_intervals = {}
        for hour, call_times in hourly_calls.items():
            if len(call_times) > 1:
                intervals = []
                for i in range(1, len(call_times)):
                    interval = (call_times[i] - call_times[i-1]).total_seconds() / 60
                    if interval > 0:
                        intervals.append(interval)
                if intervals:
                    hourly_intervals[hour] = statistics.mean(intervals)
        
        peak_hour = max(hourly_counts.items(), key=lambda x: x[1])[0] if hourly_counts else None
        
        return {
            'hourly_counts': dict(hourly_counts),
            'hourly_intervals': hourly_intervals,
            'peak_hour': peak_hour,
            'total_by_hour': sum(hourly_counts.values())
        }
    
    def analyze_daily_patterns(self, calls: List[Dict]) -> Dict:
        """Analyze call patterns by day of week"""
        daily_counts = defaultdict(int)
        daily_calls = defaultdict(list)
        
        for call in calls:
            if call.get('call_time'):
                day = call['call_time'].strftime('%A')
                daily_counts[day] += 1
                daily_calls[day].append(call['call_time'])
        
        # Calculate average intervals per day
        daily_intervals = {}
        for day, call_times in daily_calls.items():
            if len(call_times) > 1:
                intervals = []
                for i in range(1, len(call_times)):
                    interval = (call_times[i] - call_times[i-1]).total_seconds() / 60
                    if interval > 0:
                        intervals.append(interval)
                if intervals:
                    daily_intervals[day] = statistics.mean(intervals)
        
        peak_day = max(daily_counts.items(), key=lambda x: x[1])[0] if daily_counts else None
        
        return {
            'daily_counts': dict(daily_counts),
            'daily_intervals': daily_intervals,
            'peak_day': peak_day
        }
    
    def analyze_recent_frequency(self, calls: List[Dict], hours: int = 24) -> Dict:
        """Analyze call frequency in recent time period"""
        if not calls:
            return {
                'calls_in_period': 0,
                'average_interval_minutes': 0,
                'calls_per_hour': 0
            }
        
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_calls = [c for c in calls if c.get('call_time') and c['call_time'] >= cutoff]
        
        if len(recent_calls) < 2:
            return {
                'calls_in_period': len(recent_calls),
                'average_interval_minutes': 0,
                'calls_per_hour': len(recent_calls) / hours if hours > 0 else 0
            }
        
        intervals = []
        for i in range(1, len(recent_calls)):
            if recent_calls[i].get('call_time') and recent_calls[i-1].get('call_time'):
                interval = (recent_calls[i]['call_time'] - recent_calls[i-1]['call_time']).total_seconds() / 60
                if interval > 0:
                    intervals.append(interval)
        
        avg_interval = statistics.mean(intervals) if intervals else 0
        
        return {
            'calls_in_period': len(recent_calls),
            'average_interval_minutes': avg_interval,
            'calls_per_hour': len(recent_calls) / hours if hours > 0 else 0
        }
    
    def predict_next_call(self, lookback_days: int = 30) -> Optional[CallPrediction]:
        """Predict when the next call will occur based on historical patterns"""
        current_time = datetime.now()
        
        # Get the MOST RECENT call from active/recent (real-time), not database
        active_calls = self.get_active_calls()
        recent_calls = self.get_recent_calls()
        
        # Combine and find the absolute most recent call
        all_recent = active_calls + recent_calls
        if all_recent:
            all_recent_sorted = sorted([c for c in all_recent if c.get('call_time')], 
                                     key=lambda x: x['call_time'], reverse=True)
            if all_recent_sorted:
                last_call_time = all_recent_sorted[0]['call_time']
            else:
                last_call_time = None
        else:
            last_call_time = None
        
        # Fallback to database if no active/recent calls
        if not last_call_time:
            calls = self.get_all_calls(days=lookback_days)
            if len(calls) < 2:
                return None
            recent_calls_db = sorted([c for c in calls if c.get('call_time')], 
                                  key=lambda x: x['call_time'], reverse=True)
            if not recent_calls_db:
                return None
            last_call_time = recent_calls_db[0]['call_time']
        else:
            # Get all calls for analysis (including database for patterns)
            calls = self.get_all_calls(days=lookback_days)
            if len(calls) < 2:
                return None
        
        time_since_last_call = (current_time - last_call_time).total_seconds() / 60 if last_call_time else 0
        
        # Analyze patterns
        interval_analysis = self.analyze_call_intervals(calls)
        hourly_patterns = self.analyze_hourly_patterns(calls)
        daily_patterns = self.analyze_daily_patterns(calls)
        recent_24h = self.analyze_recent_frequency(calls, hours=24)
        recent_7d = self.analyze_recent_frequency(calls, hours=168)
        
        # Initialize expected intervals and weights
        expected_intervals = []
        weights = []
        
        # Get actual intervals from the most recent calls (last 5-10 calls) - HIGHEST PRIORITY
        recent_call_intervals = []
        if len(calls) >= 2:
            recent_sorted = sorted([c for c in calls if c.get('call_time')], 
                                 key=lambda x: x['call_time'], reverse=True)
            # Get intervals from last 10 calls
            for i in range(1, min(11, len(recent_sorted))):
                if recent_sorted[i-1].get('call_time') and recent_sorted[i].get('call_time'):
                    interval = (recent_sorted[i-1]['call_time'] - recent_sorted[i]['call_time']).total_seconds() / 60
                    if interval > 0 and interval < 180:  # Valid interval, less than 3 hours
                        recent_call_intervals.append(interval)
        
        # Factor 0: Most recent actual intervals (HIGHEST WEIGHT - most accurate)
        if recent_call_intervals:
            # Use last 3-5 intervals for very recent pattern
            most_recent_intervals = recent_call_intervals[:5]
            if len(most_recent_intervals) >= 3:
                most_recent_avg = statistics.mean(most_recent_intervals)
                # If recent intervals are consistently short, use this very heavily
                if most_recent_avg < 45:  # Less than 45 minutes average
                    expected_intervals.append(most_recent_avg * 0.8)  # Use 80% of actual recent average
                    weights.append(6.0)  # Highest weight - actual recent data
                elif most_recent_avg < 60:
                    expected_intervals.append(most_recent_avg * 0.85)
                    weights.append(5.0)
                else:
                    expected_intervals.append(most_recent_avg * 0.9)
                    weights.append(4.0)
        
        # Factor 1: Recent average (high weight, especially if very recent)
        if interval_analysis['recent_average_minutes'] > 0:
            recent_avg = interval_analysis['recent_average_minutes']
            # If recent average is very short, weight it heavily
            if recent_avg < 20:  # Less than 20 minutes - very active
                expected_intervals.append(recent_avg * 0.85)
                weights.append(4.0)
            elif recent_avg < 30:  # Less than 30 minutes
                expected_intervals.append(recent_avg * 0.9)
                weights.append(3.5)
            else:
                expected_intervals.append(recent_avg * 0.95)
                weights.append(2.5)
        
        # Factor 2: Recent 24h average (high weight if active)
        if recent_24h['average_interval_minutes'] > 0:
            recent_24h_avg = recent_24h['average_interval_minutes']
            # If there are many recent calls, heavily weight this and be more aggressive
            if recent_24h['calls_in_period'] > 20:
                expected_intervals.append(recent_24h_avg * 0.6)  # Very aggressive for high activity
                weights.append(4.0)  # Highest weight
            elif recent_24h['calls_in_period'] > 15:
                expected_intervals.append(recent_24h_avg * 0.7)
                weights.append(3.5)
            elif recent_24h['calls_in_period'] > 10:
                expected_intervals.append(recent_24h_avg * 0.75)
                weights.append(3.0)
            elif recent_24h['calls_in_period'] > 5:
                expected_intervals.append(recent_24h_avg * 0.85)
                weights.append(2.5)
            else:
                expected_intervals.append(recent_24h_avg * 1.0)
                weights.append(1.5)
        
        # Factor 3: Current hour pattern
        current_hour = current_time.hour
        if current_hour in hourly_patterns['hourly_intervals']:
            expected_intervals.append(hourly_patterns['hourly_intervals'][current_hour] * 0.95)
            weights.append(1.0)
        
        # Factor 4: Overall average (lower weight)
        if interval_analysis['average_interval_minutes'] > 0:
            expected_intervals.append(interval_analysis['average_interval_minutes'] * 0.7)
            weights.append(0.5)
        
        # Factor 5: Recent 7d average (lowest weight)
        if recent_7d['average_interval_minutes'] > 0:
            expected_intervals.append(recent_7d['average_interval_minutes'] * 0.8)
            weights.append(0.3)
        
        # Calculate weighted average
        if not expected_intervals:
            return None
        
        if len(weights) == len(expected_intervals):
            # Weighted average
            total_weight = sum(weights)
            expected_interval = sum(val * weight for val, weight in zip(expected_intervals, weights)) / total_weight
        else:
            # Fallback to simple average
            expected_interval = statistics.mean(expected_intervals)
        
        # Adjust for current hour if it's a peak hour
        if current_hour == hourly_patterns.get('peak_hour'):
            expected_interval *= 0.75  # Peak hours = shorter intervals
        
        # Adjust for current day if it's a peak day
        current_day = current_time.strftime('%A')
        if current_day == daily_patterns.get('peak_day'):
            expected_interval *= 0.8  # Peak days = shorter intervals
        
        # Additional adjustments based on recent activity patterns
        # If there's very high recent activity, be extremely aggressive
        if recent_24h['calls_in_period'] > 25:
            expected_interval *= 0.45  # Extremely active = very short intervals
        elif recent_24h['calls_in_period'] > 20:
            expected_interval *= 0.5  # Very active period = much shorter intervals
        elif recent_24h['calls_in_period'] > 15:
            expected_interval *= 0.55  # Very active period = shorter intervals
        elif recent_24h['calls_in_period'] > 10:
            expected_interval *= 0.6  # Active period = shorter intervals
        
        # Use actual recent intervals if available (most accurate predictor)
        if recent_call_intervals and len(recent_call_intervals) >= 3:
            # If we have good recent interval data, blend it with calculated
            recent_median = statistics.median(recent_call_intervals[:5])
            if recent_median < expected_interval:
                # Recent data suggests shorter interval - trust it more (70% weight)
                expected_interval = (expected_interval * 0.3) + (recent_median * 0.7)
            elif recent_median < expected_interval * 1.2:
                # Recent data is close - blend it (50/50)
                expected_interval = (expected_interval * 0.5) + (recent_median * 0.5)
        
        # If time since last call is already longer than expected interval, predict shorter
        if time_since_last_call > expected_interval * 0.7:
            # We're already past when a call "should" have come, predict sooner
            expected_interval *= 0.65
        
        # Cap maximum prediction time at 60 minutes (more realistic and accurate)
        max_interval = 60
        if expected_interval > max_interval:
            expected_interval = max_interval
        
        # Cap minimum prediction time at 2 minutes (to avoid unrealistic predictions)
        min_interval = 2
        if expected_interval < min_interval:
            expected_interval = min_interval
        
        # Calculate predicted time - ALWAYS base on current time for real predictions
        # This ensures predictions are always "from now" not "from last call"
        predicted_time = current_time + timedelta(minutes=expected_interval)
        
        # Ensure prediction is never in the past
        if predicted_time < current_time:
            predicted_time = current_time + timedelta(minutes=expected_interval)
        
        # Hard cap: never predict more than 2 hours ahead
        time_until_predicted = (predicted_time - current_time).total_seconds() / 60
        if time_until_predicted > 120:  # More than 2 hours
            predicted_time = current_time + timedelta(minutes=min(expected_interval, 120))
            time_until_predicted = min(expected_interval, 120)
        
        # Calculate confidence based on data quality and prediction reliability
        confidence = 0.4  # Base confidence (more conservative)
        
        # More data = higher confidence
        if len(calls) > 100:
            confidence += 0.25
        elif len(calls) > 50:
            confidence += 0.15
        elif len(calls) > 20:
            confidence += 0.1
        elif len(calls) > 10:
            confidence += 0.05
        
        # Recent activity = higher confidence (more recent data = more reliable)
        if recent_24h['calls_in_period'] > 20:
            confidence += 0.2  # Very high recent activity = very reliable
        elif recent_24h['calls_in_period'] > 10:
            confidence += 0.15
        elif recent_24h['calls_in_period'] > 5:
            confidence += 0.1
        elif recent_24h['calls_in_period'] > 2:
            confidence += 0.05
        
        # Actual recent intervals available = much higher confidence
        if recent_call_intervals and len(recent_call_intervals) >= 5:
            confidence += 0.15  # Real recent data is most reliable
        elif recent_call_intervals and len(recent_call_intervals) >= 3:
            confidence += 0.1
        
        # Consistent patterns = higher confidence
        if interval_analysis['intervals']:
            interval_std = statistics.stdev(interval_analysis['intervals']) if len(interval_analysis['intervals']) > 1 else 0
            interval_mean = interval_analysis['average_interval_minutes']
            if interval_mean > 0:
                coefficient_of_variation = interval_std / interval_mean
                if coefficient_of_variation < 0.4:  # Very low variation = very consistent
                    confidence += 0.15
                elif coefficient_of_variation < 0.6:  # Low variation = consistent
                    confidence += 0.1
        
        confidence = min(confidence, 0.95)  # Cap at 95%
        
        # Build reasoning
        reasoning_parts = []
        reasoning_parts.append(f"Based on {len(calls)} historical calls")
        reasoning_parts.append(f"Average interval: {interval_analysis['average_interval_minutes']:.1f} min")
        reasoning_parts.append(f"Recent average: {interval_analysis['recent_average_minutes']:.1f} min")
        
        if recent_24h['calls_in_period'] > 0:
            reasoning_parts.append(f"Recent activity: {recent_24h['calls_in_period']} calls in last 24h")
        
        if hourly_patterns.get('peak_hour') is not None:
            reasoning_parts.append(f"Peak hour: {hourly_patterns['peak_hour']}:00")
        
        if daily_patterns.get('peak_day'):
            reasoning_parts.append(f"Peak day: {daily_patterns['peak_day']}")
        
        reasoning = " | ".join(reasoning_parts)
        
        # Calculate time until prediction (always from current time)
        time_until = (predicted_time - current_time).total_seconds() / 60
        
        # Ensure time_until is never negative and matches expected_interval
        if time_until < 0:
            time_until = expected_interval
        if time_until > 120:  # Cap at 2 hours
            time_until = min(expected_interval, 120)
        
        # Calculate prediction interval (likely range)
        # Use recent intervals for more accurate range if available
        if recent_call_intervals and len(recent_call_intervals) > 1:
            interval_std = statistics.stdev(recent_call_intervals[:10])  # Last 10 intervals
        elif interval_analysis['intervals'] and len(interval_analysis['intervals']) > 1:
            interval_std = statistics.stdev(interval_analysis['intervals'])
        else:
            interval_std = expected_interval * 0.25  # 25% of expected if no data
        
        # Use smaller range for more accurate predictions (60% confidence interval)
        interval_range = min(interval_std * 0.6, expected_interval * 0.4)  # Cap at 40% of expected
        
        prediction_interval_start = predicted_time - timedelta(minutes=interval_range)
        prediction_interval_end = predicted_time + timedelta(minutes=interval_range)
        
        # Ensure interval doesn't go into the past
        if prediction_interval_start < current_time:
            prediction_interval_start = current_time + timedelta(minutes=expected_interval * 0.5)
        
        # Calculate best/worst case scenarios (relative to current time for real predictions)
        best_case_interval = expected_interval * 0.7  # 30% faster
        worst_case_interval = expected_interval * 1.5  # 50% slower
        best_case_time = current_time + timedelta(minutes=best_case_interval)
        worst_case_time = current_time + timedelta(minutes=worst_case_interval)
        
        # Ensure best/worst case are reasonable (not too short, not too long)
        if best_case_interval < 3:  # Minimum 3 minutes
            best_case_time = current_time + timedelta(minutes=3)
        if worst_case_interval > 180:  # Maximum 3 hours
            worst_case_time = current_time + timedelta(minutes=180)
        
        # Predict incident type
        incident_type_counts = Counter([c.get('incident_type', 'Unknown') for c in calls])
        most_common_type = incident_type_counts.most_common(1)[0][0] if incident_type_counts else None
        
        # Get seasonal factor
        current_month = current_time.month
        season = self._get_season(current_month)
        seasonal_factor = self._analyze_seasonal_trends(calls, season)
        
        # Get day of week pattern
        day_pattern = daily_patterns.get('peak_day')
        
        # Log prediction for accuracy tracking
        self._log_prediction(predicted_time, expected_interval, confidence)
        
        return CallPrediction(
            predicted_time=predicted_time,
            confidence=confidence,
            reasoning=reasoning,
            expected_interval_minutes=expected_interval,
            time_until_prediction_minutes=time_until,
            prediction_interval_start=prediction_interval_start,
            prediction_interval_end=prediction_interval_end,
            best_case_time=best_case_time,
            worst_case_time=worst_case_time,
            predicted_incident_type=most_common_type,
            day_of_week_pattern=day_pattern,
            seasonal_factor=seasonal_factor
        )
    
    def get_call_statistics(self, days: int = 30) -> Dict:
        """Get comprehensive call statistics"""
        calls = self.get_all_calls(days=days)
        
        if not calls:
            return {
                'total_calls': 0,
                'error': 'No call data available'
            }
        
        interval_analysis = self.analyze_call_intervals(calls)
        hourly_patterns = self.analyze_hourly_patterns(calls)
        daily_patterns = self.analyze_daily_patterns(calls)
        recent_24h = self.analyze_recent_frequency(calls, hours=24)
        recent_7d = self.analyze_recent_frequency(calls, hours=168)
        
        # Get most recent call
        recent_calls = sorted([c for c in calls if c.get('call_time')], 
                            key=lambda x: x['call_time'], reverse=True)
        last_call = recent_calls[0] if recent_calls else None
        
        time_since_last = None
        if last_call and last_call.get('call_time'):
            time_since_last = (datetime.now() - last_call['call_time']).total_seconds() / 60
        
        return {
            'total_calls': len(calls),
            'last_call_time': last_call['call_time'].isoformat() if last_call and last_call.get('call_time') else None,
            'time_since_last_call_minutes': time_since_last,
            'interval_analysis': interval_analysis,
            'hourly_patterns': hourly_patterns,
            'daily_patterns': daily_patterns,
            'recent_24h': recent_24h,
            'recent_7d': recent_7d
        }
    
    def get_prediction_summary(self, lookback_days: int = 30) -> Dict:
        """Get prediction with supporting statistics"""
        prediction = self.predict_next_call(lookback_days=lookback_days)
        statistics = self.get_call_statistics(days=lookback_days)
        
        return {
            'prediction': {
                'predicted_time': prediction.predicted_time.isoformat() if prediction else None,
                'confidence': prediction.confidence if prediction else 0,
                'reasoning': prediction.reasoning if prediction else "Insufficient data",
                'expected_interval_minutes': prediction.expected_interval_minutes if prediction else 0,
                'time_until_prediction_minutes': prediction.time_until_prediction_minutes if prediction else 0,
                'time_until_prediction_human': self._format_time_minutes(prediction.time_until_prediction_minutes) if prediction else "N/A"
            },
            'statistics': statistics
        }
    
    def _format_time_minutes(self, minutes: float) -> str:
        """Format minutes into human-readable time"""
        if minutes < 60:
            return f"{int(minutes)} minutes"
        elif minutes < 1440:
            hours = int(minutes / 60)
            mins = int(minutes % 60)
            return f"{hours}h {mins}m"
        else:
            days = int(minutes / 1440)
            hours = int((minutes % 1440) / 60)
            return f"{days}d {hours}h"
    
    def _get_season(self, month: int) -> str:
        """Get season from month"""
        if month in [12, 1, 2]:
            return "winter"
        elif month in [3, 4, 5]:
            return "spring"
        elif month in [6, 7, 8]:
            return "summer"
        else:
            return "fall"
    
    def _analyze_seasonal_trends(self, calls: List[Dict], current_season: str) -> str:
        """Analyze seasonal call patterns"""
        seasonal_counts = defaultdict(int)
        for call in calls:
            if call.get('call_time'):
                month = call['call_time'].month
                season = self._get_season(month)
                seasonal_counts[season] += 1
        
        if not seasonal_counts:
            return "No seasonal data"
        
        total = sum(seasonal_counts.values())
        current_count = seasonal_counts.get(current_season, 0)
        current_percentage = (current_count / total * 100) if total > 0 else 0
        
        peak_season = max(seasonal_counts.items(), key=lambda x: x[1])[0]
        
        if current_season == peak_season:
            return f"Peak season ({current_percentage:.1f}% of calls)"
        else:
            return f"Normal season ({current_percentage:.1f}% of calls, peak: {peak_season})"
    
    def _log_prediction(self, predicted_time: datetime, predicted_interval: float, confidence: float):
        """Log prediction for accuracy tracking"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO predictions_log 
                (prediction_time, predicted_time, predicted_interval_minutes, confidence)
                VALUES (?, ?, ?, ?)
            ''', (datetime.now(), predicted_time, predicted_interval, confidence))
            
            # Also log confidence trend
            cursor.execute('''
                INSERT INTO confidence_trends 
                (timestamp, confidence, prediction_interval)
                VALUES (?, ?, ?)
            ''', (datetime.now(), confidence, predicted_interval))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[ERROR] Error logging prediction: {e}")
    
    def validate_predictions(self):
        """Validate recent predictions against actual calls"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            # Get unvalidated predictions from last 12 hours
            cutoff = datetime.now() - timedelta(hours=12)
            cursor.execute('''
                SELECT id, prediction_time, predicted_time, predicted_interval_minutes
                FROM predictions_log
                WHERE prediction_time >= ? AND actual_call_time IS NULL
            ''', (cutoff,))
            
            predictions = cursor.fetchall()
            
            # Get all calls from last 12 hours
            calls = self.get_all_calls(days=1)
            call_times = [c['call_time'] for c in calls if c.get('call_time')]
            
            for pred_id, pred_time_str, predicted_time_str, pred_interval in predictions:
                try:
                    pred_time = datetime.fromisoformat(pred_time_str)
                    predicted_time = datetime.fromisoformat(predicted_time_str)
                    
                    # Find closest actual call after prediction was made
                    closest_call = None
                    min_diff = float('inf')
                    
                    for call_time in call_times:
                        if call_time > pred_time:  # Call happened after prediction
                            diff = abs((call_time - predicted_time).total_seconds() / 60)
                            if diff < min_diff:
                                min_diff = diff
                                closest_call = call_time
                    
                    if closest_call:
                        actual_interval = (closest_call - pred_time).total_seconds() / 60
                        accuracy = min_diff
                        within_15 = accuracy <= 15
                        within_30 = accuracy <= 30
                        was_accurate = accuracy <= pred_interval * 0.3  # Within 30% of predicted interval
                        
                        cursor.execute('''
                            UPDATE predictions_log
                            SET actual_call_time = ?,
                                actual_interval_minutes = ?,
                                accuracy_minutes = ?,
                                was_accurate = ?,
                                within_15_min = ?,
                                within_30_min = ?
                            WHERE id = ?
                        ''', (closest_call.isoformat(), actual_interval, accuracy, was_accurate, within_15, within_30, pred_id))
                except Exception as inner_e:
                    print(f"[ERROR] Error validating prediction {pred_id}: {inner_e}")
                    continue
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[ERROR] Error validating predictions: {e}")
    
    def get_prediction_accuracy(self, days: int = 30) -> Dict:
        """Get prediction accuracy metrics"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cutoff = datetime.now() - timedelta(days=days)
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN was_accurate = 1 THEN 1 ELSE 0 END) as accurate,
                    SUM(CASE WHEN within_15_min = 1 THEN 1 ELSE 0 END) as within_15,
                    SUM(CASE WHEN within_30_min = 1 THEN 1 ELSE 0 END) as within_30,
                    AVG(accuracy_minutes) as avg_accuracy,
                    AVG(confidence) as avg_confidence
                FROM predictions_log
                WHERE prediction_time >= ? AND actual_call_time IS NOT NULL
            ''', (cutoff,))
            
            result = cursor.fetchone()
            if not result or result[0] == 0:
                return {
                    'total_predictions': 0,
                    'validated_predictions': 0,
                    'accuracy_rate': 0,
                    'within_15_min_rate': 0,
                    'within_30_min_rate': 0,
                    'avg_accuracy_minutes': 0,
                    'avg_confidence': 0
                }
            
            total, accurate, within_15, within_30, avg_accuracy, avg_confidence = result
            
            return {
                'total_predictions': total,
                'validated_predictions': total,
                'accuracy_rate': (accurate / total * 100) if total > 0 else 0,
                'within_15_min_rate': (within_15 / total * 100) if total > 0 else 0,
                'within_30_min_rate': (within_30 / total * 100) if total > 0 else 0,
                'avg_accuracy_minutes': avg_accuracy or 0,
                'avg_confidence': avg_confidence or 0
            }
        except Exception as e:
            print(f"[ERROR] Error getting accuracy: {e}")
            return {}
        finally:
            if 'conn' in locals():
                conn.close()
    
    def get_confidence_trends(self, days: int = 30) -> List[Dict]:
        """Get confidence trends over time"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cutoff = datetime.now() - timedelta(days=days)
            cursor.execute('''
                SELECT timestamp, confidence, prediction_interval
                FROM confidence_trends
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
            ''', (cutoff,))
            
            trends = []
            for row in cursor.fetchall():
                trends.append({
                    'timestamp': row[0],
                    'confidence': row[1],
                    'prediction_interval': row[2]
                })
            
            conn.close()
            return trends
        except Exception as e:
            print(f"[ERROR] Error getting confidence trends: {e}")
            return []
    
    def analyze_incident_types(self, calls: List[Dict]) -> Dict:
        """Analyze incident type patterns and predict next type"""
        type_counts = Counter([c.get('incident_type', 'Unknown') for c in calls])
        type_by_hour = defaultdict(lambda: defaultdict(int))
        type_by_day = defaultdict(lambda: defaultdict(int))
        
        for call in calls:
            if call.get('call_time'):
                hour = call['call_time'].hour
                day = call['call_time'].strftime('%A')
                incident_type = call.get('incident_type', 'Unknown')
                type_by_hour[incident_type][hour] += 1
                type_by_day[incident_type][day] += 1
        
        # Predict next incident type based on current time
        current_time = datetime.now()
        current_hour = current_time.hour
        current_day = current_time.strftime('%A')
        
        type_scores = {}
        for incident_type, counts in type_by_hour.items():
            score = counts.get(current_hour, 0) * 2  # Weight hour more
            score += type_by_day[incident_type].get(current_day, 0)
            score += type_counts[incident_type] * 0.1  # Overall frequency
            type_scores[incident_type] = score
        
        predicted_type = max(type_scores.items(), key=lambda x: x[1])[0] if type_scores else None
        
        return {
            'type_counts': dict(type_counts.most_common(10)),
            'predicted_next_type': predicted_type,
            'type_by_hour': {k: dict(v) for k, v in type_by_hour.items()},
            'type_by_day': {k: dict(v) for k, v in type_by_day.items()}
        }
    
    def analyze_response_times(self, calls: List[Dict]) -> Dict:
        """Analyze response time patterns (if available)"""
        # This would require response time data in the calls
        # For now, analyze time between call received and closed
        response_times = []
        
        for call in calls:
            # If we have call_time and can estimate response, calculate it
            # This is a placeholder - actual implementation would need response time data
            pass
        
        if not response_times:
            return {
                'avg_response_time': 0,
                'median_response_time': 0,
                'response_times_by_type': {}
            }
        
        return {
            'avg_response_time': statistics.mean(response_times),
            'median_response_time': statistics.median(response_times),
            'min_response_time': min(response_times),
            'max_response_time': max(response_times),
            'response_times_by_type': {}
        }


# Flask Web Server Setup
app = Flask(__name__)
CORS(app)
predictor_instance = None
update_thread = None
running = True
cached_data = {
    'prediction': None,
    'statistics': None,
    'active_calls': [],
    'recent_calls': [],
    'last_update': None
}

def init_predictor(agency_id: str = "04600"):
    """Initialize predictor instance"""
    global predictor_instance
    predictor_instance = CallBasedPredictor(agency_id=agency_id)
    return predictor_instance

def update_data_continuously(update_interval: int = 30):
    """Continuously update prediction data in background"""
    global cached_data, running, predictor_instance
    
    print(f"[BACKGROUND] Starting continuous update thread (interval: {update_interval}s)")
    
    while running:
        try:
            if predictor_instance:
                # Validate old predictions first
                predictor_instance.validate_predictions()
                
                # Update prediction
                prediction = predictor_instance.predict_next_call(lookback_days=30)
                if prediction:
                    cached_data['prediction'] = {
                        'predicted_time': prediction.predicted_time.isoformat(),
                        'confidence': prediction.confidence,
                        'reasoning': prediction.reasoning,
                        'expected_interval_minutes': prediction.expected_interval_minutes,
                        'time_until_prediction_minutes': prediction.time_until_prediction_minutes,
                        'time_until_prediction_human': predictor_instance._format_time_minutes(prediction.time_until_prediction_minutes),
                        'prediction_interval_start': prediction.prediction_interval_start.isoformat() if prediction.prediction_interval_start else None,
                        'prediction_interval_end': prediction.prediction_interval_end.isoformat() if prediction.prediction_interval_end else None,
                        'best_case_time': prediction.best_case_time.isoformat() if prediction.best_case_time else None,
                        'worst_case_time': prediction.worst_case_time.isoformat() if prediction.worst_case_time else None,
                        'predicted_incident_type': prediction.predicted_incident_type,
                        'day_of_week_pattern': prediction.day_of_week_pattern,
                        'seasonal_factor': prediction.seasonal_factor
                    }
                
                # Update statistics
                stats = predictor_instance.get_call_statistics(days=30)
                cached_data['statistics'] = stats
                
                # Update active calls
                active_calls = predictor_instance.get_active_calls()
                for call in active_calls:
                    if call.get('call_time') and isinstance(call['call_time'], datetime):
                        call['call_time'] = call['call_time'].isoformat()
                cached_data['active_calls'] = active_calls
                
                # Update recent calls
                recent_calls = predictor_instance.get_recent_calls()
                for call in recent_calls:
                    if call.get('call_time') and isinstance(call['call_time'], datetime):
                        call['call_time'] = call['call_time'].isoformat()
                cached_data['recent_calls'] = recent_calls
                
                cached_data['last_update'] = datetime.now().isoformat()
                
                print(f"[BACKGROUND] Data updated at {datetime.now().strftime('%H:%M:%S')} - Active: {len(active_calls)}, Recent: {len(recent_calls)}")
            
            import time
            time.sleep(update_interval)
        except Exception as e:
            print(f"[BACKGROUND] Error updating data: {e}")
            import time
            time.sleep(update_interval)

@app.route('/')
def index():
    """Serve the prediction dashboard"""
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/prediction')
def get_prediction():
    """Get next call prediction (from cache)"""
    try:
        if cached_data.get('prediction'):
            return jsonify(cached_data['prediction'])
        elif predictor_instance:
            # Fallback to live if cache empty
            prediction = predictor_instance.predict_next_call(lookback_days=30)
            if prediction:
                return jsonify({
                    "predicted_time": prediction.predicted_time.isoformat(),
                    "confidence": prediction.confidence,
                    "reasoning": prediction.reasoning,
                    "expected_interval_minutes": prediction.expected_interval_minutes,
                    "time_until_prediction_minutes": prediction.time_until_prediction_minutes,
                    "time_until_prediction_human": predictor_instance._format_time_minutes(prediction.time_until_prediction_minutes)
                })
        return jsonify({"error": "Insufficient data for prediction"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/statistics')
def get_statistics():
    """Get call statistics (from cache)"""
    try:
        if cached_data.get('statistics'):
            return jsonify(cached_data['statistics'])
        elif predictor_instance:
            # Fallback to live if cache empty
            stats = predictor_instance.get_call_statistics(days=30)
            return jsonify(stats)
        return jsonify({"error": "Predictor not initialized"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/active-calls')
def get_active_calls():
    """Get active calls (from cache)"""
    try:
        if cached_data.get('active_calls') is not None:
            return jsonify({"calls": cached_data['active_calls']})
        elif predictor_instance:
            # Fallback to live if cache empty
            active_calls = predictor_instance.get_active_calls()
            for call in active_calls:
                if call.get('call_time') and isinstance(call['call_time'], datetime):
                    call['call_time'] = call['call_time'].isoformat()
            return jsonify({"calls": active_calls})
        return jsonify({"error": "Predictor not initialized"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/recent-calls')
def get_recent_calls():
    """Get recent calls (from cache)"""
    try:
        if cached_data.get('recent_calls') is not None:
            return jsonify({"calls": cached_data['recent_calls']})
        elif predictor_instance:
            # Fallback to live if cache empty
            recent_calls = predictor_instance.get_recent_calls()
            for call in recent_calls:
                if call.get('call_time') and isinstance(call['call_time'], datetime):
                    call['call_time'] = call['call_time'].isoformat()
            return jsonify({"calls": recent_calls})
        return jsonify({"error": "Predictor not initialized"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/status')
def get_status():
    """Get server status and last update time"""
    return jsonify({
        "running": running,
        "last_update": cached_data.get('last_update'),
        "has_prediction": cached_data.get('prediction') is not None,
        "active_calls_count": len(cached_data.get('active_calls', [])),
        "recent_calls_count": len(cached_data.get('recent_calls', []))
    })

@app.route('/api/summary')
def get_summary():
    """Get complete prediction summary"""
    try:
        if not predictor_instance:
            return jsonify({"error": "Predictor not initialized"}), 500
        
        summary = predictor_instance.get_prediction_summary(lookback_days=30)
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/accuracy')
def get_accuracy():
    """Get prediction accuracy metrics"""
    try:
        if not predictor_instance:
            return jsonify({"error": "Predictor not initialized"}), 500
        
        accuracy = predictor_instance.get_prediction_accuracy(days=30)
        return jsonify(accuracy)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/confidence-trends')
def get_confidence_trends():
    """Get confidence trends over time"""
    try:
        if not predictor_instance:
            return jsonify({"error": "Predictor not initialized"}), 500
        
        trends = predictor_instance.get_confidence_trends(days=30)
        return jsonify({"trends": trends})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/incident-types')
def get_incident_types():
    """Get incident type analysis and predictions"""
    try:
        if not predictor_instance:
            return jsonify({"error": "Predictor not initialized"}), 500
        
        calls = predictor_instance.get_all_calls(days=30)
        analysis = predictor_instance.analyze_incident_types(calls)
        return jsonify(analysis)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/response-times')
def get_response_times():
    """Get response time analysis"""
    try:
        if not predictor_instance:
            return jsonify({"error": "Predictor not initialized"}), 500
        
        calls = predictor_instance.get_all_calls(days=30)
        analysis = predictor_instance.analyze_response_times(calls)
        return jsonify(analysis)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/validate-predictions')
def validate_predictions():
    """Manually trigger prediction validation"""
    try:
        if not predictor_instance:
            return jsonify({"error": "Predictor not initialized"}), 500
        
        predictor_instance.validate_predictions()
        return jsonify({"status": "success", "message": "Predictions validated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_server(host='127.0.0.1', port=5002, agency_id='04600', update_interval=30):
    """Run the web server with continuous background updates"""
    global update_thread, running
    
    init_predictor(agency_id=agency_id)
    
    # Start background update thread
    import threading
    running = True
    update_thread = threading.Thread(target=update_data_continuously, args=(update_interval,), daemon=True)
    update_thread.start()
    
    # Do initial update
    print("[INIT] Performing initial data update...")
    try:
        prediction = predictor_instance.predict_next_call(lookback_days=30)
        if prediction:
            cached_data['prediction'] = {
                'predicted_time': prediction.predicted_time.isoformat(),
                'confidence': prediction.confidence,
                'reasoning': prediction.reasoning,
                'expected_interval_minutes': prediction.expected_interval_minutes,
                'time_until_prediction_minutes': prediction.time_until_prediction_minutes,
                'time_until_prediction_human': predictor_instance._format_time_minutes(prediction.time_until_prediction_minutes),
                'prediction_interval_start': prediction.prediction_interval_start.isoformat() if prediction.prediction_interval_start else None,
                'prediction_interval_end': prediction.prediction_interval_end.isoformat() if prediction.prediction_interval_end else None,
                'best_case_time': prediction.best_case_time.isoformat() if prediction.best_case_time else None,
                'worst_case_time': prediction.worst_case_time.isoformat() if prediction.worst_case_time else None,
                'predicted_incident_type': prediction.predicted_incident_type,
                'day_of_week_pattern': prediction.day_of_week_pattern,
                'seasonal_factor': prediction.seasonal_factor
            }
        cached_data['statistics'] = predictor_instance.get_call_statistics(days=30)
        active_calls = predictor_instance.get_active_calls()
        for call in active_calls:
            if call.get('call_time') and isinstance(call['call_time'], datetime):
                call['call_time'] = call['call_time'].isoformat()
        cached_data['active_calls'] = active_calls
        recent_calls = predictor_instance.get_recent_calls()
        for call in recent_calls:
            if call.get('call_time') and isinstance(call['call_time'], datetime):
                call['call_time'] = call['call_time'].isoformat()
        cached_data['recent_calls'] = recent_calls
        cached_data['last_update'] = datetime.now().isoformat()
        print("[INIT] Initial data update complete")
    except Exception as e:
        print(f"[INIT] Error in initial update: {e}")
    
    print("=" * 60)
    print("Call-Based Predictor Web Server")
    print("=" * 60)
    print(f"🌐 Server starting on http://{host}:{port}")
    print(f"📊 Dashboard: http://{host}:{port}/")
    print(f"🔮 API: http://{host}:{port}/api/prediction")
    print(f"🔄 Background updates every {update_interval} seconds")
    print("=" * 60)
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    try:
        app.run(host=host, port=port, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down...")
        running = False
        if update_thread:
            update_thread.join(timeout=2)
        print("[STOP] Server stopped")

# HTML Dashboard Template
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Call-Based Predictor Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            padding: 20px;
            min-height: 100vh;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .header {
            background: white;
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        .header h1 {
            color: #667eea;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            text-align: center;
        }
        .stat-card h3 {
            color: #667eea;
            font-size: 2em;
            margin-bottom: 10px;
        }
        .stat-card p {
            color: #666;
            font-size: 0.9em;
        }
        .section {
            background: white;
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .section h2 {
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.8em;
        }
        .prediction-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        .prediction-card h3 {
            font-size: 1.5em;
            margin-bottom: 15px;
        }
        .prediction-card .predicted-time {
            font-size: 2.5em;
            font-weight: bold;
            margin: 15px 0;
        }
        .prediction-card .confidence {
            font-size: 1.2em;
            margin: 10px 0;
        }
        .confidence-bar {
            background: rgba(255,255,255,0.3);
            height: 30px;
            border-radius: 15px;
            margin-top: 15px;
            overflow: hidden;
        }
        .confidence-fill {
            background: rgba(255,255,255,0.9);
            height: 100%;
            transition: width 0.5s;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #667eea;
            font-weight: bold;
        }
        .calls-list {
            max-height: 400px;
            overflow-y: auto;
        }
        .call-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 10px;
            border-left: 4px solid #667eea;
        }
        .call-item.active {
            border-left-color: #e74c3c;
        }
        .call-item h4 {
            color: #667eea;
            margin-bottom: 5px;
        }
        .call-item.active h4 {
            color: #e74c3c;
        }
        .refresh-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            margin-bottom: 20px;
            transition: background 0.3s;
        }
        .refresh-btn:hover {
            background: #5568d3;
        }
        .loading {
            text-align: center;
            padding: 20px;
            color: #666;
        }
        .chart-container {
            position: relative;
            height: 300px;
            margin-top: 20px;
        }
        .reasoning {
            background: rgba(255,255,255,0.2);
            padding: 15px;
            border-radius: 10px;
            margin-top: 15px;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔮 Call-Based Predictor Dashboard</h1>
            <p>Real-time call prediction based on historical patterns</p>
            <button class="refresh-btn" onclick="loadAllData()">🔄 Refresh Data</button>
        </div>

        <div class="stats-grid" id="stats-grid">
            <div class="stat-card">
                <h3 id="total-calls">-</h3>
                <p>Total Calls (30 days)</p>
            </div>
            <div class="stat-card">
                <h3 id="active-calls">-</h3>
                <p>Active Calls</p>
            </div>
            <div class="stat-card">
                <h3 id="recent-calls">-</h3>
                <p>Recent Calls</p>
            </div>
            <div class="stat-card">
                <h3 id="avg-interval">-</h3>
                <p>Avg Interval (min)</p>
            </div>
        </div>

        <div class="section">
            <h2>🔮 Next Call Prediction</h2>
            <div id="prediction-container" class="loading">Loading prediction...</div>
        </div>

        <div class="section">
            <h2>🔥 Active Calls</h2>
            <div id="active-calls-container" class="loading">Loading active calls...</div>
        </div>

        <div class="section">
            <h2>📋 Recent Calls</h2>
            <div id="recent-calls-container" class="loading">Loading recent calls...</div>
        </div>

        <div class="section">
            <h2>📊 Hourly Call Patterns</h2>
            <div class="chart-container">
                <canvas id="hourly-chart"></canvas>
            </div>
        </div>

        <div class="section">
            <h2>🎯 Prediction Accuracy</h2>
            <div id="accuracy-container" class="loading">Loading accuracy metrics...</div>
        </div>

        <div class="section">
            <h2>📈 Confidence Trends</h2>
            <div class="chart-container">
                <canvas id="confidence-chart"></canvas>
            </div>
        </div>

        <div class="section">
            <h2>🚨 Incident Type Predictions</h2>
            <div id="incident-types-container" class="loading">Loading incident types...</div>
        </div>
    </div>

    <script>
        let hourlyChart, confidenceChart;

        async function loadAllData() {
            await Promise.all([
                loadPrediction(),
                loadStatistics(),
                loadActiveCalls(),
                loadRecentCalls(),
                loadAccuracy(),
                loadConfidenceTrends(),
                loadIncidentTypes()
            ]);
        }

        async function loadPrediction() {
            try {
                const res = await fetch('/api/prediction');
                const data = await res.json();
                const container = document.getElementById('prediction-container');
                
                if (data.error) {
                    container.innerHTML = `<p style="color: #e74c3c;">${data.error}</p>`;
                    return;
                }
                
                const predictedTime = new Date(data.predicted_time);
                const confidencePercent = (data.confidence * 100).toFixed(1);
                
                let intervalHtml = '';
                if (data.prediction_interval_start && data.prediction_interval_end) {
                    const intervalStart = new Date(data.prediction_interval_start);
                    const intervalEnd = new Date(data.prediction_interval_end);
                    intervalHtml = `
                        <div style="margin-top: 15px; padding: 10px; background: rgba(255,255,255,0.2); border-radius: 8px;">
                            <strong>Prediction Interval:</strong> ${intervalStart.toLocaleTimeString()} - ${intervalEnd.toLocaleTimeString()}
                        </div>
                    `;
                }
                
                let scenariosHtml = '';
                if (data.best_case_time && data.worst_case_time) {
                    const bestCase = new Date(data.best_case_time);
                    const worstCase = new Date(data.worst_case_time);
                    scenariosHtml = `
                        <div style="margin-top: 15px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                            <div style="padding: 10px; background: rgba(46, 204, 113, 0.3); border-radius: 8px;">
                                <strong>Best Case:</strong><br>${bestCase.toLocaleTimeString()}
                            </div>
                            <div style="padding: 10px; background: rgba(231, 76, 60, 0.3); border-radius: 8px;">
                                <strong>Worst Case:</strong><br>${worstCase.toLocaleTimeString()}
                            </div>
                        </div>
                    `;
                }
                
                let incidentTypeHtml = '';
                if (data.predicted_incident_type) {
                    incidentTypeHtml = `
                        <div style="margin-top: 15px; padding: 10px; background: rgba(255,255,255,0.2); border-radius: 8px;">
                            <strong>Predicted Incident Type:</strong> ${data.predicted_incident_type}
                        </div>
                    `;
                }
                
                let patternsHtml = '';
                if (data.day_of_week_pattern || data.seasonal_factor) {
                    patternsHtml = `
                        <div style="margin-top: 15px; padding: 10px; background: rgba(255,255,255,0.2); border-radius: 8px; font-size: 0.9em;">
                            ${data.day_of_week_pattern ? `<strong>Peak Day:</strong> ${data.day_of_week_pattern}<br>` : ''}
                            ${data.seasonal_factor ? `<strong>Seasonal Factor:</strong> ${data.seasonal_factor}` : ''}
                        </div>
                    `;
                }
                
                container.innerHTML = `
                    <div class="prediction-card">
                        <h3>Predicted Next Call</h3>
                        <div class="predicted-time">${predictedTime.toLocaleString()}</div>
                        <div class="confidence">Confidence: ${confidencePercent}%</div>
                        <div class="confidence-bar">
                            <div class="confidence-fill" style="width: ${confidencePercent}%">${confidencePercent}%</div>
                        </div>
                        <div style="margin-top: 15px; font-size: 1.1em; font-weight: bold;">
                            ⏱️ Time to Next Call: ${data.time_until_prediction_human}
                        </div>
                        ${intervalHtml}
                        ${scenariosHtml}
                        ${incidentTypeHtml}
                        ${patternsHtml}
                        <div class="reasoning" style="margin-top: 15px;">
                            <strong>Reasoning:</strong> ${data.reasoning}
                        </div>
                        <div style="margin-top: 15px; font-size: 0.9em;">
                            Expected interval: ${data.expected_interval_minutes.toFixed(1)} minutes
                        </div>
                    </div>
                `;
            } catch (e) {
                console.error('Error loading prediction:', e);
                document.getElementById('prediction-container').innerHTML = '<p style="color: #e74c3c;">Error loading prediction</p>';
            }
        }
        
        async function loadAccuracy() {
            try {
                const res = await fetch('/api/accuracy');
                const data = await res.json();
                const container = document.getElementById('accuracy-container');
                
                if (!data || data.total_predictions === 0 || data.validated_predictions === 0) {
                    container.innerHTML = '<p>No validated predictions yet. Check back after predictions are validated.</p>';
                    return;
                }
                
                // Safely handle undefined values
                const accuracyRate = (data.accuracy_rate || 0).toFixed(1);
                const within15Rate = (data.within_15_min_rate || 0).toFixed(1);
                const within30Rate = (data.within_30_min_rate || 0).toFixed(1);
                const avgAccuracy = (data.avg_accuracy_minutes || 0).toFixed(1);
                const avgConfidence = ((data.avg_confidence || 0) * 100).toFixed(1);
                const totalPredictions = data.total_predictions || 0;
                
                container.innerHTML = `
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                        <div class="stat-card">
                            <h3>${accuracyRate}%</h3>
                            <p>Overall Accuracy</p>
                        </div>
                        <div class="stat-card">
                            <h3>${within15Rate}%</h3>
                            <p>Within 15 Minutes</p>
                        </div>
                        <div class="stat-card">
                            <h3>${within30Rate}%</h3>
                            <p>Within 30 Minutes</p>
                        </div>
                        <div class="stat-card">
                            <h3>${avgAccuracy}</h3>
                            <p>Avg Error (minutes)</p>
                        </div>
                        <div class="stat-card">
                            <h3>${totalPredictions}</h3>
                            <p>Validated Predictions</p>
                        </div>
                        <div class="stat-card">
                            <h3>${avgConfidence}%</h3>
                            <p>Avg Confidence</p>
                        </div>
                    </div>
                `;
            } catch (e) {
                console.error('Error loading accuracy:', e);
                const container = document.getElementById('accuracy-container');
                if (container) {
                    container.innerHTML = '<p style="color: #e74c3c;">Error loading accuracy data</p>';
                }
            }
        }
        
        async function loadConfidenceTrends() {
            try {
                const res = await fetch('/api/confidence-trends');
                const data = await res.json();
                const ctx = document.getElementById('confidence-chart');
                
                if (!ctx) {
                    return;
                }
                
                if (!data.trends || data.trends.length === 0) {
                    ctx.parentElement.innerHTML = '<p>No confidence trend data yet. Data will appear as predictions are made.</p>';
                    return;
                }
                
                if (confidenceChart) confidenceChart.destroy();
                
                const labels = data.trends.map(t => new Date(t.timestamp).toLocaleString());
                const confidences = data.trends.map(t => (t.confidence || 0) * 100);
                
                confidenceChart = new Chart(ctx.getContext('2d'), {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Confidence %',
                            data: confidences,
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102, 126, 234, 0.1)',
                            tension: 0.4,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                max: 100
                            }
                        }
                    }
                });
            } catch (e) {
                console.error('Error loading confidence trends:', e);
                const ctx = document.getElementById('confidence-chart');
                if (ctx && ctx.parentElement) {
                    ctx.parentElement.innerHTML = '<p style="color: #e74c3c;">Error loading confidence trends</p>';
                }
            }
        }
        
        async function loadIncidentTypes() {
            try {
                const res = await fetch('/api/incident-types');
                const data = await res.json();
                const container = document.getElementById('incident-types-container');
                
                if (!container) {
                    return;
                }
                
                if (!data || !data.type_counts || Object.keys(data.type_counts).length === 0) {
                    container.innerHTML = '<p>No incident type data available yet.</p>';
                    return;
                }
                
                let typesHtml = '<div style="margin-bottom: 20px;"><h3>Predicted Next Type: <span style="color: #667eea; font-size: 1.2em;">' + (data.predicted_next_type || 'Unknown') + '</span></h3></div>';
                typesHtml += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px;">';
                
                const sortedTypes = Object.entries(data.type_counts).sort((a, b) => b[1] - a[1]);
                for (const [type, count] of sortedTypes.slice(0, 10)) {
                    typesHtml += `
                        <div style="padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #667eea;">
                            <strong>${type}</strong><br>
                            <span style="color: #666;">${count} calls</span>
                        </div>
                    `;
                }
                typesHtml += '</div>';
                
                container.innerHTML = typesHtml;
            } catch (e) {
                console.error('Error loading incident types:', e);
                const container = document.getElementById('incident-types-container');
                if (container) {
                    container.innerHTML = '<p style="color: #e74c3c;">Error loading incident types</p>';
                }
            }
        }

        async function loadStatistics() {
            try {
                const res = await fetch('/api/statistics');
                const data = await res.json();
                
                document.getElementById('total-calls').textContent = data.total_calls || 0;
                document.getElementById('avg-interval').textContent = 
                    data.interval_analysis?.average_interval_minutes?.toFixed(1) || '-';
                
                // Load hourly chart
                if (data.hourly_patterns && data.hourly_patterns.hourly_counts) {
                    const ctx = document.getElementById('hourly-chart').getContext('2d');
                    if (hourlyChart) hourlyChart.destroy();
                    
                    const hours = Array.from({length: 24}, (_, i) => i);
                    const counts = hours.map(h => data.hourly_patterns.hourly_counts[h] || 0);
                    
                    hourlyChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: hours.map(h => h + ':00'),
                            datasets: [{
                                label: 'Calls by Hour',
                                data: counts,
                                borderColor: '#667eea',
                                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                                tension: 0.4,
                                fill: true
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: { display: false }
                            }
                        }
                    });
                }
            } catch (e) {
                console.error('Error loading statistics:', e);
            }
        }

        async function loadActiveCalls() {
            try {
                const res = await fetch('/api/active-calls');
                const data = await res.json();
                const container = document.getElementById('active-calls-container');
                
                document.getElementById('active-calls').textContent = data.calls?.length || 0;
                
                if (data.calls && data.calls.length > 0) {
                    container.innerHTML = `
                        <div class="calls-list">
                            ${data.calls.map(call => `
                                <div class="call-item active">
                                    <h4>${call.incident_type || 'Unknown'}</h4>
                                    <p><strong>Address:</strong> ${call.address || 'Unknown'}</p>
                                    <p><strong>Time:</strong> ${new Date(call.call_time).toLocaleString()}</p>
                                </div>
                            `).join('')}
                        </div>
                    `;
                } else {
                    container.innerHTML = '<p>No active calls</p>';
                }
            } catch (e) {
                console.error('Error loading active calls:', e);
                document.getElementById('active-calls-container').innerHTML = '<p style="color: #e74c3c;">Error loading active calls</p>';
            }
        }

        async function loadRecentCalls() {
            try {
                const res = await fetch('/api/recent-calls');
                const data = await res.json();
                const container = document.getElementById('recent-calls-container');
                
                document.getElementById('recent-calls').textContent = data.calls?.length || 0;
                
                if (data.calls && data.calls.length > 0) {
                    container.innerHTML = `
                        <div class="calls-list">
                            ${data.calls.slice(0, 10).map(call => `
                                <div class="call-item">
                                    <h4>${call.incident_type || 'Unknown'}</h4>
                                    <p><strong>Address:</strong> ${call.address || 'Unknown'}</p>
                                    <p><strong>Time:</strong> ${new Date(call.call_time).toLocaleString()}</p>
                                </div>
                            `).join('')}
                        </div>
                    `;
                } else {
                    container.innerHTML = '<p>No recent calls</p>';
                }
            } catch (e) {
                console.error('Error loading recent calls:', e);
                document.getElementById('recent-calls-container').innerHTML = '<p style="color: #e74c3c;">Error loading recent calls</p>';
            }
        }

        // Initial load
        loadAllData();
        
        // Auto-refresh every 10 seconds for real-time updates
        setInterval(loadAllData, 10000);
        
        // Show last update time
        async function updateLastUpdateTime() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                if (data.last_update) {
                    const updateTime = new Date(data.last_update);
                    const timeStr = updateTime.toLocaleTimeString();
                    const statusEl = document.querySelector('.header p');
                    if (statusEl) {
                        statusEl.textContent = `Real-time call prediction based on historical patterns | Last update: ${timeStr}`;
                    }
                }
            } catch (e) {
                console.error('Error getting status:', e);
            }
        }
        
        // Update status every 5 seconds
        setInterval(updateLastUpdateTime, 5000);
        updateLastUpdateTime();
    </script>
</body>
</html>
'''

def main():
    """Test the call-based predictor (CLI mode)"""
    print("=" * 60)
    print("Call-Based Predictor - Testing")
    print("=" * 60)
    
    predictor = CallBasedPredictor(agency_id="04600")
    
    # Get active and recent calls
    print("\n📡 Fetching real-time calls from FDDCADScraper...")
    active_calls = predictor.get_active_calls()
    recent_calls = predictor.get_recent_calls()
    
    print(f"\n🔥 Active Calls: {len(active_calls)}")
    for call in active_calls[:5]:  # Show first 5
        call_time = call.get('call_time', 'Unknown')
        if isinstance(call_time, datetime):
            call_time = call_time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"  - {call.get('incident_type', 'Unknown')} at {call.get('address', 'Unknown')} ({call_time})")
    
    print(f"\n📋 Recent Calls: {len(recent_calls)}")
    for call in recent_calls[:5]:  # Show first 5
        call_time = call.get('call_time', 'Unknown')
        if isinstance(call_time, datetime):
            call_time = call_time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"  - {call.get('incident_type', 'Unknown')} at {call.get('address', 'Unknown')} ({call_time})")
    
    # Get statistics
    print("\n📊 Call Statistics (Last 30 days):")
    stats = predictor.get_call_statistics(days=30)
    print(f"Total calls: {stats.get('total_calls', 0)}")
    
    if stats.get('last_call_time'):
        print(f"Last call: {stats['last_call_time']}")
        if stats.get('time_since_last_call_minutes'):
            print(f"Time since last call: {predictor._format_time_minutes(stats['time_since_last_call_minutes'])}")
    
    if stats.get('interval_analysis'):
        ia = stats['interval_analysis']
        print(f"\nInterval Analysis:")
        print(f"  Average: {ia.get('average_interval_minutes', 0):.1f} minutes")
        print(f"  Recent average: {ia.get('recent_average_minutes', 0):.1f} minutes")
        print(f"  Median: {ia.get('median_interval_minutes', 0):.1f} minutes")
    
    if stats.get('hourly_patterns'):
        hp = stats['hourly_patterns']
        if hp.get('peak_hour') is not None:
            print(f"\nPeak hour: {hp['peak_hour']}:00 ({hp['hourly_counts'].get(hp['peak_hour'], 0)} calls)")
    
    if stats.get('daily_patterns'):
        dp = stats['daily_patterns']
        if dp.get('peak_day'):
            print(f"Peak day: {dp['peak_day']} ({dp['daily_counts'].get(dp['peak_day'], 0)} calls)")
    
    # Get prediction
    print("\n🔮 Next Call Prediction:")
    prediction = predictor.predict_next_call(lookback_days=30)
    
    if prediction:
        print(f"Predicted time: {prediction.predicted_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Confidence: {prediction.confidence:.1%}")
        print(f"Expected interval: {prediction.expected_interval_minutes:.1f} minutes")
        print(f"Time until prediction: {predictor._format_time_minutes(prediction.time_until_prediction_minutes)}")
        print(f"\nReasoning: {prediction.reasoning}")
    else:
        print("Insufficient data for prediction (need at least 2 calls)")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--server':
        # Run as web server with continuous updates
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 5002
        agency_id = sys.argv[3] if len(sys.argv) > 3 else '04600'
        update_interval = int(sys.argv[4]) if len(sys.argv) > 4 else 30
        run_server(port=port, agency_id=agency_id, update_interval=update_interval)
    else:
        # Run as CLI
        main()

