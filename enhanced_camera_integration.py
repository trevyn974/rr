#!/usr/bin/env python3
"""
Enhanced Camera Integration for CAD System
Handles iDrive Arkansas cameras with CORS workarounds and fallbacks
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
from flask import Flask, render_template_string, jsonify, request
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

class EnhancedCameraIntegration:
    """Enhanced camera integration with CORS workarounds"""
    
    def __init__(self):
        self.cameras: Dict[str, CameraFeed] = {}
        self.running = False
        self.proxy_enabled = True
        self.proxy_url = "http://localhost:5001"  # Local proxy server
        
        # Initialize known cameras from your console output
        self._initialize_cameras()
        
    def _initialize_cameras(self):
        """Initialize cameras based on the console output data"""
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
    
    def get_camera_image_url(self, camera_id: str, use_proxy: bool = True) -> str:
        """Get camera image URL with CORS workaround"""
        if use_proxy and self.proxy_enabled:
            return f"{self.proxy_url}/proxy/camera/{camera_id}"
        else:
            # Direct URL with timestamp to force refresh
            timestamp = int(time.time())
            return f"https://actis.idrivearkansas.com/index.php/api/cameras/image?camera={camera_id}&t={timestamp}"
    
    def test_camera_access(self, camera_id: str) -> Dict:
        """Test if camera is accessible"""
        try:
            # Try direct access first
            direct_url = self.get_camera_image_url(camera_id, use_proxy=False)
            response = requests.get(direct_url, timeout=10)
            
            if response.status_code == 200:
                return {
                    "accessible": True,
                    "method": "direct",
                    "url": direct_url,
                    "status_code": response.status_code
                }
            else:
                return {
                    "accessible": False,
                    "method": "direct",
                    "error": f"HTTP {response.status_code}",
                    "url": direct_url
                }
                
        except requests.RequestException as e:
            # Try proxy if direct fails
            if self.proxy_enabled:
                try:
                    proxy_url = self.get_camera_image_url(camera_id, use_proxy=True)
                    response = requests.get(proxy_url, timeout=10)
                    
                    if response.status_code == 200:
                        return {
                            "accessible": True,
                            "method": "proxy",
                            "url": proxy_url,
                            "status_code": response.status_code
                        }
                except requests.RequestException as proxy_error:
                    return {
                        "accessible": False,
                        "method": "both_failed",
                        "error": f"Direct: {e}, Proxy: {proxy_error}",
                        "url": direct_url
                    }
            
            return {
                "accessible": False,
                "method": "direct_failed",
                "error": str(e),
                "url": direct_url
            }
    
    def get_camera_status(self) -> Dict:
        """Get status of all cameras"""
        status = {
            "total_cameras": len(self.cameras),
            "accessible_cameras": 0,
            "camera_details": {}
        }
        
        for camera_id, camera in self.cameras.items():
            test_result = self.test_camera_access(camera_id)
            camera.status = "online" if test_result["accessible"] else "offline"
            camera.last_update = datetime.now()
            
            if test_result["accessible"]:
                status["accessible_cameras"] += 1
            
            status["camera_details"][camera_id] = {
                "name": camera.name,
                "location": camera.location,
                "status": camera.status,
                "accessible": test_result["accessible"],
                "method": test_result.get("method", "unknown"),
                "url": test_result.get("url", ""),
                "error": test_result.get("error", "")
            }
        
        return status
    
    def generate_camera_html(self) -> str:
        """Generate HTML for camera display"""
        status = self.get_camera_status()
        
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Arkansas Traffic Cameras - CAD Integration</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    background: #1a1a1a;
                    color: #ffffff;
                    margin: 0;
                    padding: 20px;
                }
                .camera-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 20px;
                    margin-top: 20px;
                }
                .camera-card {
                    background: #2d2d2d;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    padding: 15px;
                    text-align: center;
                }
                .camera-image {
                    max-width: 100%;
                    height: 200px;
                    object-fit: cover;
                    border-radius: 4px;
                    margin-bottom: 10px;
                }
                .camera-status {
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                }
                .status-online { background: #00ff00; color: #000; }
                .status-offline { background: #ff0000; color: #fff; }
                .refresh-btn {
                    background: #0078d4;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 4px;
                    cursor: pointer;
                    margin: 10px;
                }
                .refresh-btn:hover { background: #106ebe; }
            </style>
        </head>
        <body>
            <h1>Arkansas Traffic Cameras</h1>
            <p>Accessible: {accessible_cameras}/{total_cameras} cameras</p>
            <button class="refresh-btn" onclick="refreshCameras()">Refresh All</button>
            <div class="camera-grid">
        """.format(
            accessible_cameras=status["accessible_cameras"],
            total_cameras=status["total_cameras"]
        )
        
        for camera_id, details in status["camera_details"].items():
            image_url = self.get_camera_image_url(camera_id)
            status_class = "status-online" if details["accessible"] else "status-offline"
            
            html += f"""
                <div class="camera-card">
                    <h3>{details['name']}</h3>
                    <p>{details['location']}</p>
                    <img src="{image_url}" 
                         class="camera-image" 
                         alt="Camera {camera_id}"
                         onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjMzMzIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkNhbWVyYSBVbmF2YWlsYWJsZTwvdGV4dD48L3N2Zz4='">
                    <div class="camera-status {status_class}">
                        {details['status'].upper()}
                    </div>
                    <p><small>Method: {details['method']}</small></p>
            """
            
            if not details["accessible"]:
                html += f"<p><small>Error: {details['error']}</small></p>"
            
            html += "</div>"
        
        html += """
            </div>
            <script>
                function refreshCameras() {
                    location.reload();
                }
                
                // Auto-refresh every 30 seconds
                setInterval(refreshCameras, 30000);
            </script>
        </body>
        </html>
        """
        
        return html

def main():
    """Main function to test camera integration"""
    integration = EnhancedCameraIntegration()
    
    print("Testing Arkansas Camera Integration...")
    print("=" * 50)
    
    # Test all cameras
    status = integration.get_camera_status()
    
    print(f"Total cameras: {status['total_cameras']}")
    print(f"Accessible cameras: {status['accessible_cameras']}")
    print()
    
    for camera_id, details in status["camera_details"].items():
        print(f"Camera {camera_id} ({details['name']}):")
        print(f"  Status: {details['status']}")
        print(f"  Method: {details['method']}")
        print(f"  URL: {details['url']}")
        if not details["accessible"]:
            print(f"  Error: {details['error']}")
        print()
    
    # Generate HTML file
    html_content = integration.generate_camera_html()
    with open("arkansas_cameras.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print("Generated arkansas_cameras.html - open in browser to view cameras")

if __name__ == "__main__":
    main()



