#!/usr/bin/env python3
"""
Call Analytics & Prediction Server
Provides web interface for call prediction, analytics, and visualization
"""

from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import math
from typing import List, Dict, Tuple
from fdd_cad_scraper import FDDCADScraper, Incident

app = Flask(__name__)
CORS(app)

# Database setup
DB_FILE = 'call_history.db'

def init_database():
    """Initialize SQLite database for storing call history"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY,
            incident_id TEXT UNIQUE,
            incident_type TEXT,
            address TEXT,
            city TEXT,
            zip_code TEXT,
            latitude REAL,
            longitude REAL,
            call_time TIMESTAMP,
            units TEXT,
            alarm_level INTEGER,
            closed_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_call_time ON incidents(call_time)
    ''')
    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_incident_type ON incidents(incident_type)
    ''')
    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_location ON incidents(latitude, longitude)
    ''')
    conn.commit()
    conn.close()

def save_incident(incident: Incident):
    """Save incident to database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Extract units
        units_str = ""
        if hasattr(incident, 'Unit') and incident.Unit:
            if isinstance(incident.Unit, list):
                units_str = ", ".join([u.UnitID if hasattr(u, 'UnitID') else str(u) for u in incident.Unit])
            else:
                units_str = str(incident.Unit)
        
        # Extract city and zip from address
        city = ""
        zip_code = ""
        if incident.FullDisplayAddress:
            parts = incident.FullDisplayAddress.split(',')
            if len(parts) > 1:
                city = parts[-2].strip() if len(parts) > 2 else parts[-1].strip()
                # Try to extract zip
                import re
                zip_match = re.search(r'\b(\d{5})\b', incident.FullDisplayAddress)
                if zip_match:
                    zip_code = zip_match.group(1)
        
        c.execute('''
            INSERT OR REPLACE INTO incidents 
            (incident_id, incident_type, address, city, zip_code, latitude, longitude, 
             call_time, units, alarm_level, closed_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(incident.ID),
            incident.incident_type,
            incident.FullDisplayAddress,
            city,
            zip_code,
            incident.Latitude,
            incident.Longitude,
            incident.CallReceivedDateTime.isoformat() if incident.CallReceivedDateTime else None,
            units_str,
            incident.AlarmLevel if hasattr(incident, 'AlarmLevel') else None,
            incident.ClosedDateTime.isoformat() if hasattr(incident, 'ClosedDateTime') and incident.ClosedDateTime else None
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Error saving incident: {e}")

def get_historical_incidents(days: int = 30) -> List[Dict]:
    """Get historical incidents from database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        c.execute('''
            SELECT * FROM incidents 
            WHERE call_time >= ?
            ORDER BY call_time DESC
        ''', (cutoff,))
        
        columns = [desc[0] for desc in c.description]
        incidents = []
        for row in c.fetchall():
            incidents.append(dict(zip(columns, row)))
        conn.close()
        return incidents
    except Exception as e:
        print(f"[ERROR] Error getting historical incidents: {e}")
        return []

class CallPredictor:
    """Predicts likely call locations and patterns"""
    
    def __init__(self):
        self.scraper = FDDCADScraper()
    
    def analyze_time_patterns(self, incidents: List[Dict]) -> Dict:
        """Analyze time-based patterns"""
        hourly_counts = defaultdict(int)
        daily_counts = defaultdict(int)
        day_of_week_counts = defaultdict(int)
        
        for inc in incidents:
            try:
                call_time = datetime.fromisoformat(inc['call_time'])
                hour = call_time.hour
                day = call_time.day
                weekday = call_time.strftime('%A')
                
                hourly_counts[hour] += 1
                daily_counts[day] += 1
                day_of_week_counts[weekday] += 1
            except:
                continue
        
        return {
            'hourly': dict(hourly_counts),
            'daily': dict(daily_counts),
            'day_of_week': dict(day_of_week_counts),
            'peak_hour': max(hourly_counts.items(), key=lambda x: x[1])[0] if hourly_counts else None,
            'peak_day': max(day_of_week_counts.items(), key=lambda x: x[1])[0] if day_of_week_counts else None
        }
    
    def analyze_location_patterns(self, incidents: List[Dict]) -> Dict:
        """Analyze location-based patterns and create hotspots"""
        location_counts = defaultdict(int)
        zip_counts = defaultdict(int)
        city_counts = defaultdict(int)
        
        # Group by rounded coordinates (0.01 degree ~ 1km)
        for inc in incidents:
            if inc.get('latitude') and inc.get('longitude'):
                # Round to 0.01 degrees for clustering
                lat_rounded = round(inc['latitude'], 2)
                lon_rounded = round(inc['longitude'], 2)
                location_counts[(lat_rounded, lon_rounded)] += 1
            
            if inc.get('zip_code'):
                zip_counts[inc['zip_code']] += 1
            if inc.get('city'):
                city_counts[inc['city']] += 1
        
        # Get top hotspots
        top_locations = sorted(location_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        hotspots = []
        for (lat, lon), count in top_locations:
            hotspots.append({
                'latitude': lat,
                'longitude': lon,
                'count': count,
                'radius': min(count * 0.5, 2.0)  # Radius based on frequency
            })
        
        return {
            'hotspots': hotspots,
            'top_zips': dict(Counter(zip_counts).most_common(10)),
            'top_cities': dict(Counter(city_counts).most_common(10))
        }
    
    def analyze_incident_types(self, incidents: List[Dict]) -> Dict:
        """Analyze incident type patterns"""
        type_counts = Counter([inc.get('incident_type', 'Unknown') for inc in incidents])
        
        return {
            'by_type': dict(type_counts.most_common(20)),
            'total_types': len(type_counts),
            'most_common': type_counts.most_common(1)[0] if type_counts else None
        }
    
    def predict_next_likely_locations(self, incidents: List[Dict], num_predictions: int = 5) -> List[Dict]:
        """Predict most likely locations for next call"""
        # Get recent incidents (last 7 days)
        recent_cutoff = datetime.now() - timedelta(days=7)
        recent = [inc for inc in incidents 
                  if inc.get('call_time') and 
                  datetime.fromisoformat(inc['call_time']) >= recent_cutoff]
        
        if not recent:
            recent = incidents[:50]  # Fallback to most recent 50
        
        # Analyze location patterns
        location_weights = defaultdict(float)
        current_hour = datetime.now().hour
        
        for inc in recent:
            if inc.get('latitude') and inc.get('longitude'):
                lat_rounded = round(inc['latitude'], 2)
                lon_rounded = round(inc['longitude'], 2)
                
                # Weight by recency and time similarity
                try:
                    call_time = datetime.fromisoformat(inc['call_time'])
                    days_ago = (datetime.now() - call_time).days
                    recency_weight = 1.0 / (1.0 + days_ago * 0.1)  # More recent = higher weight
                    
                    hour_diff = abs(call_time.hour - current_hour)
                    time_weight = 1.0 / (1.0 + hour_diff * 0.2)  # Similar time = higher weight
                    
                    location_weights[(lat_rounded, lon_rounded)] += recency_weight * time_weight
                except:
                    location_weights[(lat_rounded, lon_rounded)] += 0.5
        
        # Get top predictions
        top_predictions = sorted(location_weights.items(), key=lambda x: x[1], reverse=True)[:num_predictions]
        
        predictions = []
        for (lat, lon), confidence in top_predictions:
            # Find example incident at this location
            example = next((inc for inc in recent 
                          if inc.get('latitude') and inc.get('longitude') and
                          round(inc['latitude'], 2) == lat and round(inc['longitude'], 2) == lon), None)
            
            predictions.append({
                'latitude': lat,
                'longitude': lon,
                'confidence': min(confidence * 10, 100),  # Scale to 0-100
                'address': example.get('address', 'Unknown') if example else 'Unknown',
                'city': example.get('city', '') if example else '',
                'reason': f"Recent activity: {int(confidence * 10)} calls in this area"
            })
        
        return predictions
    
    def predict_next_likely_time(self, incidents: List[Dict]) -> Dict:
        """Predict most likely time for next call"""
        time_patterns = self.analyze_time_patterns(incidents)
        
        current_hour = datetime.now().hour
        current_day = datetime.now().strftime('%A')
        
        # Get hourly distribution
        hourly = time_patterns.get('hourly', {})
        if not hourly:
            return {'next_hour': None, 'confidence': 0}
        
        # Find peak hours (next few hours)
        next_hours = []
        for hour in range(24):
            hour_key = (current_hour + hour) % 24
            count = hourly.get(hour_key, 0)
            if count > 0:
                next_hours.append({
                    'hour': hour_key,
                    'count': count,
                    'confidence': min(count * 5, 100)
                })
        
        next_hours.sort(key=lambda x: x['count'], reverse=True)
        
        return {
            'next_hour': next_hours[0]['hour'] if next_hours else None,
            'next_hour_confidence': next_hours[0]['confidence'] if next_hours else 0,
            'top_hours': next_hours[:5],
            'peak_hour': time_patterns.get('peak_hour'),
            'peak_day': time_patterns.get('peak_day')
        }

# Global instances
predictor = CallPredictor()
monitor_instance = None  # Will be set by integration

def set_monitor_instance(monitor):
    """Set the monitor instance for integration"""
    global monitor_instance
    monitor_instance = monitor

# API Routes
@app.route('/')
def index():
    """Serve the analytics dashboard"""
    return render_template_string(ANALYTICS_DASHBOARD_HTML)

@app.route('/api/stats')
def get_stats():
    """Get overall statistics"""
    incidents = get_historical_incidents(30)
    
    stats = {
        'total_calls_30d': len(incidents),
        'active_calls': len([inc for inc in incidents if not inc.get('closed_time')]),
        'calls_today': len([inc for inc in incidents 
                          if inc.get('call_time') and 
                          datetime.fromisoformat(inc['call_time']).date() == datetime.now().date()]),
        'calls_this_week': len([inc for inc in incidents 
                               if inc.get('call_time') and 
                               (datetime.now() - datetime.fromisoformat(inc['call_time'])).days <= 7]),
        'avg_calls_per_day': len(incidents) / 30 if incidents else 0
    }
    
    return jsonify(stats)

@app.route('/api/time-patterns')
def get_time_patterns():
    """Get time-based patterns"""
    incidents = get_historical_incidents(30)
    patterns = predictor.analyze_time_patterns(incidents)
    return jsonify(patterns)

@app.route('/api/location-patterns')
def get_location_patterns():
    """Get location-based patterns and hotspots"""
    incidents = get_historical_incidents(30)
    patterns = predictor.analyze_location_patterns(incidents)
    return jsonify(patterns)

@app.route('/api/incident-types')
def get_incident_types():
    """Get incident type analysis"""
    incidents = get_historical_incidents(30)
    analysis = predictor.analyze_incident_types(incidents)
    return jsonify(analysis)

@app.route('/api/predictions/locations')
def get_location_predictions():
    """Get predicted next call locations"""
    incidents = get_historical_incidents(30)
    predictions = predictor.predict_next_likely_locations(incidents, 10)
    return jsonify({'predictions': predictions})

@app.route('/api/predictions/time')
def get_time_predictions():
    """Get predicted next call time"""
    incidents = get_historical_incidents(30)
    predictions = predictor.predict_next_likely_time(incidents)
    return jsonify(predictions)

@app.route('/api/current-incidents')
def get_current_incidents():
    """Get current active incidents"""
    if monitor_instance and hasattr(monitor_instance, 'scraper'):
        try:
            incidents = monitor_instance.scraper.get_incidents("04600")
            if incidents and hasattr(incidents, 'active'):
                active = []
                for inc in incidents.active:
                    active.append({
                        'id': str(inc.ID),
                        'type': inc.incident_type,
                        'address': inc.FullDisplayAddress,
                        'latitude': inc.Latitude,
                        'longitude': inc.Longitude,
                        'time': inc.CallReceivedDateTime.isoformat() if inc.CallReceivedDateTime else None
                    })
                return jsonify({'active': active})
        except Exception as e:
            print(f"[ERROR] Error getting current incidents: {e}")
    
    return jsonify({'active': []})

@app.route('/api/historical')
def get_historical():
    """Get historical incidents"""
    days = request.args.get('days', 30, type=int)
    incidents = get_historical_incidents(days)
    return jsonify({'incidents': incidents})

def run_server(host='0.0.0.0', port=5001):
    """Run the analytics server"""
    init_database()
    print(f"[ANALYTICS] Starting analytics server on http://{host}:{port}")
    print(f"[ANALYTICS] Access dashboard at http://localhost:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)

# HTML Dashboard Template
ANALYTICS_DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Call Analytics & Prediction Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://maps.googleapis.com/maps/api/js?key=YOUR_API_KEY&libraries=visualization"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            padding: 20px;
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
        #map {
            height: 500px;
            width: 100%;
            border-radius: 10px;
        }
        .prediction-card {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 10px;
            border-left: 4px solid #667eea;
        }
        .prediction-card h4 {
            color: #667eea;
            margin-bottom: 5px;
        }
        .confidence-bar {
            background: #e0e0e0;
            height: 20px;
            border-radius: 10px;
            margin-top: 10px;
            overflow: hidden;
        }
        .confidence-fill {
            background: linear-gradient(90deg, #667eea, #764ba2);
            height: 100%;
            transition: width 0.3s;
        }
        .chart-container {
            position: relative;
            height: 300px;
            margin-top: 20px;
        }
        .loading {
            text-align: center;
            padding: 20px;
            color: #666;
        }
        .refresh-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1em;
            margin-bottom: 20px;
        }
        .refresh-btn:hover {
            background: #5568d3;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔥 Call Analytics & Prediction Dashboard</h1>
            <p>Real-time call analysis, predictions, and insights</p>
            <button class="refresh-btn" onclick="loadAllData()">🔄 Refresh Data</button>
        </div>

        <div class="stats-grid" id="stats-grid">
            <div class="stat-card">
                <h3 id="total-calls">-</h3>
                <p>Total Calls (30 days)</p>
            </div>
            <div class="stat-card">
                <h3 id="calls-today">-</h3>
                <p>Calls Today</p>
            </div>
            <div class="stat-card">
                <h3 id="calls-week">-</h3>
                <p>Calls This Week</p>
            </div>
            <div class="stat-card">
                <h3 id="avg-daily">-</h3>
                <p>Avg Calls/Day</p>
            </div>
        </div>

        <div class="section">
            <h2>📍 Predicted Next Call Locations</h2>
            <div id="predictions-container" class="loading">Loading predictions...</div>
        </div>

        <div class="section">
            <h2>🗺️ Call Heatmap & Hotspots</h2>
            <div id="map"></div>
        </div>

        <div class="section">
            <h2>📊 Time Patterns</h2>
            <div class="chart-container">
                <canvas id="time-chart"></canvas>
            </div>
        </div>

        <div class="section">
            <h2>📈 Incident Types</h2>
            <div class="chart-container">
                <canvas id="type-chart"></canvas>
            </div>
        </div>

        <div class="section">
            <h2>⏰ Time Predictions</h2>
            <div id="time-predictions" class="loading">Loading time predictions...</div>
        </div>
    </div>

    <script>
        let map, heatmap;
        let timeChart, typeChart;

        async function loadAllData() {
            await Promise.all([
                loadStats(),
                loadPredictions(),
                loadTimePatterns(),
                loadIncidentTypes(),
                loadTimePredictions(),
                loadMap()
            ]);
        }

        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                document.getElementById('total-calls').textContent = data.total_calls_30d || 0;
                document.getElementById('calls-today').textContent = data.calls_today || 0;
                document.getElementById('calls-week').textContent = data.calls_this_week || 0;
                document.getElementById('avg-daily').textContent = data.avg_calls_per_day?.toFixed(1) || 0;
            } catch (e) {
                console.error('Error loading stats:', e);
            }
        }

        async function loadPredictions() {
            try {
                const res = await fetch('/api/predictions/locations');
                const data = await res.json();
                const container = document.getElementById('predictions-container');
                
                if (data.predictions && data.predictions.length > 0) {
                    container.innerHTML = data.predictions.map(pred => `
                        <div class="prediction-card">
                            <h4>${pred.address}</h4>
                            <p>${pred.city || ''} | Confidence: ${pred.confidence.toFixed(1)}%</p>
                            <p style="color: #666; font-size: 0.9em;">${pred.reason}</p>
                            <div class="confidence-bar">
                                <div class="confidence-fill" style="width: ${pred.confidence}%"></div>
                            </div>
                        </div>
                    `).join('');
                } else {
                    container.innerHTML = '<p>No predictions available. Need more historical data.</p>';
                }
            } catch (e) {
                console.error('Error loading predictions:', e);
            }
        }

        async function loadTimePatterns() {
            try {
                const res = await fetch('/api/time-patterns');
                const data = await res.json();
                
                const ctx = document.getElementById('time-chart').getContext('2d');
                if (timeChart) timeChart.destroy();
                
                const hours = Array.from({length: 24}, (_, i) => i);
                const counts = hours.map(h => data.hourly[h] || 0);
                
                timeChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: hours.map(h => h + ':00'),
                        datasets: [{
                            label: 'Calls by Hour',
                            data: counts,
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102, 126, 234, 0.1)',
                            tension: 0.4
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
            } catch (e) {
                console.error('Error loading time patterns:', e);
            }
        }

        async function loadIncidentTypes() {
            try {
                const res = await fetch('/api/incident-types');
                const data = await res.json();
                
                const ctx = document.getElementById('type-chart').getContext('2d');
                if (typeChart) typeChart.destroy();
                
                const types = Object.keys(data.by_type || {});
                const counts = Object.values(data.by_type || {});
                
                typeChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: types,
                        datasets: [{
                            label: 'Calls',
                            data: counts,
                            backgroundColor: '#667eea'
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
            } catch (e) {
                console.error('Error loading incident types:', e);
            }
        }

        async function loadTimePredictions() {
            try {
                const res = await fetch('/api/predictions/time');
                const data = await res.json();
                const container = document.getElementById('time-predictions');
                
                let html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">';
                if (data.next_hour !== null) {
                    html += `<div class="prediction-card">
                        <h4>Next Likely Hour</h4>
                        <h3>${data.next_hour}:00</h3>
                        <p>Confidence: ${data.next_hour_confidence.toFixed(1)}%</p>
                    </div>`;
                }
                if (data.peak_hour !== null) {
                    html += `<div class="prediction-card">
                        <h4>Peak Hour (Historical)</h4>
                        <h3>${data.peak_hour}:00</h3>
                    </div>`;
                }
                if (data.peak_day) {
                    html += `<div class="prediction-card">
                        <h4>Peak Day</h4>
                        <h3>${data.peak_day}</h3>
                    </div>`;
                }
                html += '</div>';
                container.innerHTML = html;
            } catch (e) {
                console.error('Error loading time predictions:', e);
            }
        }

        async function loadMap() {
            try {
                // Initialize map centered on Rogers, AR
                if (!map) {
                    map = new google.maps.Map(document.getElementById('map'), {
                        center: { lat: 36.3320, lng: -94.1185 },
                        zoom: 12,
                        mapTypeId: 'roadmap'
                    });
                }

                // Load location patterns
                const res = await fetch('/api/location-patterns');
                const data = await res.json();
                
                // Add heatmap data
                const heatmapData = [];
                if (data.hotspots) {
                    data.hotspots.forEach(hotspot => {
                        for (let i = 0; i < hotspot.count; i++) {
                            // Add slight randomization for visualization
                            heatmapData.push(new google.maps.LatLng(
                                hotspot.latitude + (Math.random() - 0.5) * 0.01,
                                hotspot.longitude + (Math.random() - 0.5) * 0.01
                            ));
                        }
                    });
                }

                // Load current incidents
                const currentRes = await fetch('/api/current-incidents');
                const currentData = await currentRes.json();
                
                currentData.active.forEach(inc => {
                    if (inc.latitude && inc.longitude) {
                        new google.maps.Marker({
                            position: { lat: inc.latitude, lng: inc.longitude },
                            map: map,
                            title: inc.type + ' - ' + inc.address,
                            icon: {
                                url: 'http://maps.google.com/mapfiles/ms/icons/red-dot.png'
                            }
                        });
                    }
                });

                // Create heatmap
                if (heatmapData.length > 0) {
                    if (heatmap) {
                        heatmap.setData(heatmapData);
                    } else {
                        heatmap = new google.maps.visualization.HeatmapLayer({
                            data: heatmapData,
                            map: map
                        });
                    }
                }
            } catch (e) {
                console.error('Error loading map:', e);
                document.getElementById('map').innerHTML = '<p style="padding: 20px;">Map loading error. Google Maps API key may be required.</p>';
            }
        }

        // Initial load
        loadAllData();
        
        // Auto-refresh every 30 seconds
        setInterval(loadAllData, 30000);
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    init_database()
    run_server()




