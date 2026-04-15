#!/usr/bin/env python3
"""
Working Camera Integration for CAD System
Handles iDrive Arkansas cameras with proper image handling
"""

import asyncio
import json
import time
import os
import requests
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from flask import Flask, render_template_string, jsonify, request, send_file
from flask_cors import CORS
import base64
import io
from PIL import Image
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class CameraFeed:
    """Camera feed configuration"""
    camera_id: str
    name: str
    location: str
    latitude: float
    longitude: float
    image_url: str
    status: str = "unknown"
    last_update: datetime = None
    error_count: int = 0
    max_errors: int = 5
    last_image_data: bytes = None

class WorkingCameraIntegration:
    """Working camera integration for CAD system"""
    
    def __init__(self):
        self.cameras: Dict[str, CameraFeed] = {}
        self.running = False
        self.cache_duration = 30  # seconds
        self.image_cache = {}  # Cache for images
        
        # Initialize known cameras
        self._initialize_cameras()
        
    def _initialize_cameras(self):
        """Initialize cameras based on console output data"""
        camera_data = [
            {"id": "347", "name": "Highway 347", "lat": 36.1864, "lon": -94.1284},
            {"id": "348", "name": "Highway 348", "lat": 36.1864, "lon": -94.1284},
            {"id": "349", "name": "Highway 349", "lat": 36.1864, "lon": -94.1284},
            {"id": "350", "name": "Highway 350", "lat": 36.1864, "lon": -94.1284},
            {"id": "351", "name": "Highway 351", "lat": 36.1864, "lon": -94.1284},
            {"id": "364", "name": "Highway 364", "lat": 36.1864, "lon": -94.1284},
            {"id": "372", "name": "Highway 372", "lat": 36.1864, "lon": -94.1284},
            {"id": "373", "name": "Highway 373", "lat": 36.1864, "lon": -94.1284},
        ]
        
        for cam in camera_data:
            self.cameras[cam["id"]] = CameraFeed(
                camera_id=cam["id"],
                name=cam["name"],
                location=f"Arkansas Highway {cam['id']}",
                latitude=cam["lat"],
                longitude=cam["lon"],
                image_url=f"https://actis.idrivearkansas.com/index.php/api/cameras/image?camera={cam['id']}",
                status="unknown"
            )
    
    def get_camera_image(self, camera_id: str, force_refresh: bool = False) -> Optional[bytes]:
        """Get camera image data with caching"""
        if camera_id not in self.cameras:
            return None
            
        camera = self.cameras[camera_id]
        
        # Check cache first
        if not force_refresh and camera_id in self.image_cache:
            cached_data, timestamp = self.image_cache[camera_id]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            # Add timestamp to force refresh
            timestamp = int(time.time())
            url = f"{camera.image_url}&t={timestamp}"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # Verify it's actually image data
            if len(response.content) > 10000:  # Reasonable image size
                # Update cache
                self.image_cache[camera_id] = (response.content, time.time())
                
                # Update camera status
                camera.status = "online"
                camera.last_update = datetime.now()
                camera.error_count = 0
                camera.last_image_data = response.content
                
                return response.content
            else:
                raise ValueError("Response too small to be a valid image")
                
        except Exception as e:
            logger.error(f"Error fetching camera {camera_id}: {e}")
            camera.status = "offline"
            camera.error_count += 1
            
            if camera.error_count >= camera.max_errors:
                camera.status = "error"
            
            return None
    
    def get_camera_status(self) -> Dict:
        """Get status of all cameras"""
        status = {
            "total_cameras": len(self.cameras),
            "online_cameras": 0,
            "offline_cameras": 0,
            "error_cameras": 0,
            "camera_details": {}
        }
        
        for camera_id, camera in self.cameras.items():
            # Test camera if not recently tested
            if (camera.last_update is None or 
                (datetime.now() - camera.last_update).seconds > 60):
                self.get_camera_image(camera_id)
            
            if camera.status == "online":
                status["online_cameras"] += 1
            elif camera.status == "offline":
                status["offline_cameras"] += 1
            elif camera.status == "error":
                status["error_cameras"] += 1
            
            status["camera_details"][camera_id] = {
                "name": camera.name,
                "location": camera.location,
                "status": camera.status,
                "last_update": camera.last_update.isoformat() if camera.last_update else None,
                "error_count": camera.error_count,
                "has_image": camera.last_image_data is not None
            }
        
        return status
    
    def generate_camera_html(self) -> str:
        """Generate HTML for camera display"""
        status = self.get_camera_status()
        
        # Build HTML with proper string formatting
        online_cameras = status["online_cameras"]
        offline_cameras = status["offline_cameras"]
        error_cameras = status["error_cameras"]
        
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Arkansas Traffic Cameras - CAD Integration</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    background: #1a1a1a;
                    color: #ffffff;
                    margin: 0;
                    padding: 20px;
                }}
                .header {{
                    background: #2d2d2d;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                }}
                .status-summary {{
                    display: flex;
                    gap: 20px;
                    margin: 10px 0;
                }}
                .status-item {{
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                .status-online {{ background: #00ff00; color: #000; }}
                .status-offline {{ background: #ff8c00; color: #000; }}
                .status-error {{ background: #ff0000; color: #fff; }}
                .camera-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 20px;
                    margin-top: 20px;
                }}
                .camera-card {{
                    background: #2d2d2d;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    padding: 15px;
                    text-align: center;
                }}
                .camera-image {{
                    max-width: 100%;
                    height: 200px;
                    object-fit: cover;
                    border-radius: 4px;
                    margin-bottom: 10px;
                    background: #333;
                }}
                .camera-status {{
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                    margin: 5px 0;
                }}
                .refresh-btn {{
                    background: #0078d4;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 4px;
                    cursor: pointer;
                    margin: 10px;
                }}
                .refresh-btn:hover {{ background: #106ebe; }}
                .loading {{
                    color: #ff8c00;
                    font-style: italic;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Arkansas Traffic Cameras - CAD Integration</h1>
                <div class="status-summary">
                    <div class="status-item status-online">Online: {online_cameras}</div>
                    <div class="status-item status-offline">Offline: {offline_cameras}</div>
                    <div class="status-item status-error">Errors: {error_cameras}</div>
                </div>
                <button class="refresh-btn" onclick="refreshAllCameras()">Refresh All Cameras</button>
                <button class="refresh-btn" onclick="location.reload()">Reload Page</button>
            </div>
            <div class="camera-grid">
        """
        
        for camera_id, details in status["camera_details"].items():
            status_class = f"status-{details['status']}"
            image_url = f"/camera_image/{camera_id}"
            
            html += f"""
                <div class="camera-card">
                    <h3>{details['name']}</h3>
                    <p>{details['location']}</p>
                    <img src="{image_url}" 
                         class="camera-image" 
                         alt="Camera {camera_id}"
                         onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjMzMzIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkNhbWVyYSBVbmF2YWlsYWJsZTwvdGV4dD48L3N2Zz4='"
                         onload="this.style.display='block'"
                         onerror="this.style.display='block'">
                    <div class="camera-status {status_class}">
                        {details['status'].upper()}
                    </div>
                    <p><small>Last Update: {details['last_update'] or 'Never'}</small></p>
                    <p><small>Errors: {details['error_count']}</small></p>
                    <button class="refresh-btn" onclick="refreshCamera('{camera_id}')">Refresh</button>
                </div>
            """
        
        html += """
            </div>
            <script>
                function refreshCamera(cameraId) {
                    const img = document.querySelector(`img[alt="Camera ${cameraId}"]`);
                    if (img) {
                        img.src = `/camera_image/${cameraId}?t=${Date.now()}`;
                    }
                }
                
                function refreshAllCameras() {
                    const images = document.querySelectorAll('.camera-image');
                    const timestamp = Date.now();
                    images.forEach(img => {
                        const currentSrc = img.src;
                        const baseUrl = currentSrc.split('?')[0];
                        img.src = `${baseUrl}?t=${timestamp}`;
                    });
                }
                
                // Auto-refresh every 30 seconds
                setInterval(refreshAllCameras, 30000);
            </script>
        </body>
        </html>
        """
        
        return html

# Flask app for serving camera images
app = Flask(__name__)
CORS(app)

# Global camera integration instance
camera_integration = WorkingCameraIntegration()

@app.route('/')
def index():
    """Main camera display page"""
    return camera_integration.generate_camera_html()

@app.route('/camera_image/<camera_id>')
def get_camera_image(camera_id):
    """Get camera image"""
    image_data = camera_integration.get_camera_image(camera_id, force_refresh=True)
    
    if image_data:
        return send_file(
            io.BytesIO(image_data),
            mimetype='image/png',
            as_attachment=False
        )
    else:
        # Return a placeholder image
        placeholder = io.BytesIO()
        img = Image.new('RGB', (300, 200), color='#333333')
        img.save(placeholder, format='PNG')
        placeholder.seek(0)
        return send_file(placeholder, mimetype='image/png')

@app.route('/api/camera_status')
def api_camera_status():
    """API endpoint for camera status"""
    return jsonify(camera_integration.get_camera_status())

@app.route('/api/refresh_camera/<camera_id>')
def api_refresh_camera(camera_id):
    """API endpoint to refresh a specific camera"""
    image_data = camera_integration.get_camera_image(camera_id, force_refresh=True)
    return jsonify({
        "camera_id": camera_id,
        "success": image_data is not None,
        "timestamp": datetime.now().isoformat()
    })

def main():
    """Main function to run the camera integration server"""
    print("Starting Arkansas Camera Integration Server...")
    print("=" * 60)
    print("Access the camera interface at: http://localhost:5002")
    print("API endpoints:")
    print("  GET /api/camera_status - Get all camera status")
    print("  GET /api/refresh_camera/<id> - Refresh specific camera")
    print("  GET /camera_image/<id> - Get camera image")
    print("=" * 60)
    
    # Test all cameras on startup
    status = camera_integration.get_camera_status()
    print(f"Camera Status: {status['online_cameras']}/{status['total_cameras']} online")
    
    app.run(host='0.0.0.0', port=5002, debug=True)

if __name__ == "__main__":
    main()
