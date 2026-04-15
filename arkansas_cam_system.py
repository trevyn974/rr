#!/usr/bin/env python3
"""
Arkansas Traffic Camera Monitoring System
Integrates iDrive Arkansas traffic cameras with Discord webhooks and dispatch layout
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
class CameraConfig:
    """Configuration for traffic cameras"""
    camera_id: str
    name: str
    location: str
    latitude: float
    longitude: float
    image_url: str
    stream_url: str
    status: str = "active"
    last_update: str = ""

@dataclass
class ArkansasCamConfig:
    """Configuration for Arkansas camera system"""
    refresh_interval: int = 30  # seconds
    max_cameras: int = 5
    auto_refresh: bool = True
    discord_enabled: bool = True
    theme: str = "dark"
    
    # Discord webhook settings
    discord_webhook_url: str = "https://discord.com/api/webhooks/1379959452098232450/oFAvxyvROKGhes8EvArVJqv_1dtI8T_JmGRYAVE9SDmGESiSooMLPHsoSMMBFUep4HeD"
    
    # Camera alert settings
    alert_on_camera_offline: bool = True
    alert_on_traffic_incident: bool = True
    
    # iDrive Arkansas API settings
    idrive_base_url: str = "https://actis.idrivearkansas.com/index.php/api/cameras"
    idrive_image_url: str = "https://actis.idrivearkansas.com/index.php/api/cameras/image"

class ArkansasCameraSystem:
    """Main system for monitoring Arkansas traffic cameras"""
    
    def __init__(self, config: ArkansasCamConfig = None):
        self.config = config or ArkansasCamConfig()
        self.cameras: Dict[str, CameraConfig] = {}
        self.running = False
        self.last_alert_time = {}
        
        # Initialize cameras based on the provided data
        self._initialize_cameras()
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_cameras, daemon=True)
        
    def _initialize_cameras(self):
        """Initialize camera configurations from iDrive Arkansas data"""
        # Camera 349 - based on the provided data
        self.cameras["349"] = CameraConfig(
            camera_id="349",
            name="Highway Camera 349",
            location="Arkansas Highway",
            latitude=36.1864,  # Approximate Arkansas coordinates
            longitude=-94.1284,
            image_url="https://actis.idrivearkansas.com/index.php/api/cameras/image?camera=349",
            stream_url="https://actis.idrivearkansas.com/index.php/api/cameras/stream?camera=349",
            status="active"
        )
        
        # Camera 350 - based on the provided data
        self.cameras["350"] = CameraConfig(
            camera_id="350",
            name="Highway Camera 350",
            location="Arkansas Highway",
            latitude=36.1864,
            longitude=-94.1284,
            image_url="https://actis.idrivearkansas.com/index.php/api/cameras/image?camera=350",
            stream_url="https://actis.idrivearkansas.com/index.php/api/cameras/stream?camera=350",
            status="active"
        )
        
        # Add 3 more cameras for the 5-box layout
        for i in range(351, 354):
            self.cameras[str(i)] = CameraConfig(
                camera_id=str(i),
                name=f"Highway Camera {i}",
                location="Arkansas Highway",
                latitude=36.1864 + (i - 349) * 0.01,
                longitude=-94.1284 + (i - 349) * 0.01,
                image_url=f"https://actis.idrivearkansas.com/index.php/api/cameras/image?camera={i}",
                stream_url=f"https://actis.idrivearkansas.com/index.php/api/cameras/stream?camera={i}",
                status="active"
            )
    
    def start_monitoring(self):
        """Start the camera monitoring system"""
        if not self.running:
            self.running = True
            self.monitor_thread.start()
            logger.info("Arkansas camera monitoring started")
    
    def stop_monitoring(self):
        """Stop the camera monitoring system"""
        self.running = False
        logger.info("Arkansas camera monitoring stopped")
    
    def _monitor_cameras(self):
        """Monitor camera status and send alerts"""
        while self.running:
            try:
                for camera_id, camera in self.cameras.items():
                    self._check_camera_status(camera)
                time.sleep(self.config.refresh_interval)
            except Exception as e:
                logger.error(f"Error in camera monitoring: {e}")
                time.sleep(5)
    
    def _check_camera_status(self, camera: CameraConfig):
        """Check individual camera status"""
        try:
            # Try to fetch camera image to check if it's online
            response = requests.get(camera.image_url, timeout=10)
            if response.status_code == 200:
                camera.status = "active"
                camera.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                camera.status = "offline"
                self._send_camera_alert(camera, "offline")
        except Exception as e:
            camera.status = "offline"
            logger.warning(f"Camera {camera.camera_id} is offline: {e}")
            self._send_camera_alert(camera, "offline")
    
    def _send_camera_alert(self, camera: CameraConfig, alert_type: str):
        """Send Discord alert for camera issues"""
        if not self.config.discord_enabled:
            return
            
        # Rate limit alerts (max 1 per camera per 5 minutes)
        now = time.time()
        last_alert = self.last_alert_time.get(camera.camera_id, 0)
        if now - last_alert < 300:  # 5 minutes
            return
            
        self.last_alert_time[camera.camera_id] = now
        
        try:
            if alert_type == "offline":
                message = {
                    "content": f"🚨 **Camera Alert** - {camera.name}",
                    "embeds": [{
                        "title": "Camera Offline",
                        "description": f"Camera {camera.camera_id} at {camera.location} is currently offline",
                        "color": 16711680,  # Red
                        "fields": [
                            {"name": "Camera ID", "value": camera.camera_id, "inline": True},
                            {"name": "Location", "value": camera.location, "inline": True},
                            {"name": "Status", "value": "Offline", "inline": True}
                        ],
                        "timestamp": datetime.now().isoformat(),
                        "footer": {"text": "Arkansas Traffic Camera System"}
                    }]
                }
            else:
                message = {
                    "content": f"🚨 **Traffic Alert** - {camera.name}",
                    "embeds": [{
                        "title": "Traffic Incident Detected",
                        "description": f"Potential traffic incident detected on camera {camera.camera_id}",
                        "color": 16776960,  # Yellow
                        "fields": [
                            {"name": "Camera ID", "value": camera.camera_id, "inline": True},
                            {"name": "Location", "value": camera.location, "inline": True},
                            {"name": "Status", "value": "Incident Detected", "inline": True}
                        ],
                        "timestamp": datetime.now().isoformat(),
                        "footer": {"text": "Arkansas Traffic Camera System"}
                    }]
                }
            
            response = requests.post(self.config.discord_webhook_url, json=message)
            if response.status_code == 204:
                logger.info(f"Discord alert sent for camera {camera.camera_id}")
            else:
                logger.error(f"Failed to send Discord alert: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending Discord alert: {e}")
    
    def get_camera_data(self) -> Dict:
        """Get current camera data for web interface"""
        return {
            "cameras": [asdict(camera) for camera in self.cameras.values()],
            "system_status": "running" if self.running else "stopped",
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_cameras": len(self.cameras),
            "active_cameras": len([c for c in self.cameras.values() if c.status == "active"])
        }
    
    def send_dispatch_message(self, message: str, priority: str = "normal"):
        """Send a dispatch message to Discord"""
        if not self.config.discord_enabled:
            return False
            
        try:
            color = 65280 if priority == "high" else 3447003 if priority == "medium" else 16776960
            
            discord_message = {
                "content": f"📡 **Dispatch Message**",
                "embeds": [{
                    "title": f"Priority: {priority.upper()}",
                    "description": message,
                    "color": color,
                    "timestamp": datetime.now().isoformat(),
                    "footer": {"text": "Arkansas Traffic Camera Dispatch"}
                }]
            }
            
            response = requests.post(self.config.discord_webhook_url, json=discord_message)
            return response.status_code == 204
            
        except Exception as e:
            logger.error(f"Error sending dispatch message: {e}")
            return False

# Flask web application
app = Flask(__name__)
CORS(app)

# Global camera system instance
camera_system = None

def initialize_camera_system():
    """Initialize the camera monitoring system"""
    global camera_system
    config = ArkansasCamConfig(
        refresh_interval=30,
        discord_enabled=True,
        theme="dark"
    )
    camera_system = ArkansasCameraSystem(config)
    camera_system.start_monitoring()

# Web interface HTML template
WEB_INTERFACE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Arkansas Traffic Camera System</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
            color: #ffffff;
            min-height: 100vh;
        }
        
        .header {
            background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
            padding: 20px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
        }
        
        .header p {
            font-size: 1.2em;
            opacity: 0.9;
        }
        
        .controls {
            background: #2d2d2d;
            padding: 20px;
            display: flex;
            justify-content: center;
            gap: 20px;
            flex-wrap: wrap;
        }
        
        .control-group {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        
        .control-group label {
            font-weight: bold;
            color: #ffffff;
        }
        
        .control-group input, .control-group select, .control-group textarea {
            padding: 10px;
            border: 2px solid #444;
            border-radius: 5px;
            background: #1a1a1a;
            color: #ffffff;
            font-size: 14px;
        }
        
        .control-group input:focus, .control-group select:focus, .control-group textarea:focus {
            outline: none;
            border-color: #4a90e2;
        }
        
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            transition: all 0.3s ease;
        }
        
        .btn-primary {
            background: linear-gradient(45deg, #4a90e2, #357abd);
            color: white;
        }
        
        .btn-primary:hover {
            background: linear-gradient(45deg, #357abd, #2c5aa0);
            transform: translateY(-2px);
        }
        
        .btn-danger {
            background: linear-gradient(45deg, #e74c3c, #c0392b);
            color: white;
        }
        
        .btn-danger:hover {
            background: linear-gradient(45deg, #c0392b, #a93226);
            transform: translateY(-2px);
        }
        
        .camera-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            padding: 20px;
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .camera-box {
            background: #2d2d2d;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.3);
            transition: transform 0.3s ease;
        }
        
        .camera-box:hover {
            transform: translateY(-5px);
        }
        
        .camera-header {
            background: linear-gradient(90deg, #34495e, #2c3e50);
            padding: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .camera-title {
            font-size: 1.2em;
            font-weight: bold;
        }
        
        .camera-status {
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 0.9em;
            font-weight: bold;
        }
        
        .status-active {
            background: #27ae60;
            color: white;
        }
        
        .status-offline {
            background: #e74c3c;
            color: white;
        }
        
        .camera-content {
            padding: 15px;
        }
        
        .camera-image {
            width: 100%;
            height: 200px;
            object-fit: cover;
            border-radius: 5px;
            background: #1a1a1a;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #666;
            font-size: 1.1em;
        }
        
        .camera-info {
            margin-top: 15px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        
        .info-item {
            background: #1a1a1a;
            padding: 10px;
            border-radius: 5px;
        }
        
        .info-label {
            font-size: 0.9em;
            color: #888;
            margin-bottom: 5px;
        }
        
        .info-value {
            font-size: 1.1em;
            font-weight: bold;
        }
        
        .system-status {
            background: #2d2d2d;
            margin: 20px;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 10px;
        }
        
        .status-running {
            background: #27ae60;
        }
        
        .status-stopped {
            background: #e74c3c;
        }
        
        .refresh-btn {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #4a90e2;
            color: white;
            border: none;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            font-size: 24px;
            cursor: pointer;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
            transition: all 0.3s ease;
        }
        
        .refresh-btn:hover {
            background: #357abd;
            transform: scale(1.1);
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #4a90e2;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .message-area {
            background: #2d2d2d;
            margin: 20px;
            padding: 20px;
            border-radius: 10px;
        }
        
        .message-area h3 {
            margin-bottom: 15px;
            color: #4a90e2;
        }
        
        .message-input {
            width: 100%;
            padding: 15px;
            border: 2px solid #444;
            border-radius: 5px;
            background: #1a1a1a;
            color: #ffffff;
            font-size: 16px;
            resize: vertical;
            min-height: 100px;
        }
        
        .priority-select {
            margin: 10px 0;
            padding: 10px;
            border: 2px solid #444;
            border-radius: 5px;
            background: #1a1a1a;
            color: #ffffff;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚨 Arkansas Traffic Camera System</h1>
        <p>Real-time Highway Monitoring & Dispatch Center</p>
    </div>
    
    <div class="controls">
        <div class="control-group">
            <label>System Status</label>
            <div id="system-status">
                <span class="status-indicator status-running"></span>
                <span>Monitoring Active</span>
            </div>
        </div>
        
        <div class="control-group">
            <label>Active Cameras</label>
            <div id="active-cameras">0 / 5</div>
        </div>
        
        <div class="control-group">
            <label>Last Update</label>
            <div id="last-update">Loading...</div>
        </div>
    </div>
    
    <div class="message-area">
        <h3>📡 Dispatch Message Center</h3>
        <textarea id="dispatch-message" class="message-input" placeholder="Enter dispatch message here..."></textarea>
        <select id="priority-select" class="priority-select">
            <option value="normal">Normal Priority</option>
            <option value="medium">Medium Priority</option>
            <option value="high">High Priority</option>
        </select>
        <button class="btn btn-primary" onclick="sendDispatchMessage()">Send Dispatch Message</button>
    </div>
    
    <div class="camera-grid" id="camera-grid">
        <!-- Camera boxes will be populated here -->
    </div>
    
    <button class="refresh-btn" onclick="refreshData()" title="Refresh Data">
        🔄
    </button>
    
    <script>
        let refreshInterval;
        
        function refreshData() {
            fetch('/api/camera-data')
                .then(response => response.json())
                .then(data => {
                    updateSystemStatus(data);
                    updateCameraGrid(data.cameras);
                })
                .catch(error => {
                    console.error('Error fetching data:', error);
                });
        }
        
        function updateSystemStatus(data) {
            document.getElementById('active-cameras').textContent = `${data.active_cameras} / ${data.total_cameras}`;
            document.getElementById('last-update').textContent = data.last_update;
            
            const statusIndicator = document.querySelector('.status-indicator');
            if (data.system_status === 'running') {
                statusIndicator.className = 'status-indicator status-running';
                statusIndicator.nextElementSibling.textContent = 'Monitoring Active';
            } else {
                statusIndicator.className = 'status-indicator status-stopped';
                statusIndicator.nextElementSibling.textContent = 'System Stopped';
            }
        }
        
         function updateCameraGrid(cameras) {
             const grid = document.getElementById('camera-grid');
             grid.innerHTML = '';
             
             cameras.forEach(camera => {
                 const cameraBox = document.createElement('div');
                 cameraBox.className = 'camera-box';
                 cameraBox.innerHTML = `
                     <div class="camera-header">
                         <div class="camera-title">${camera.name}</div>
                         <div class="camera-status status-${camera.status}">${camera.status.toUpperCase()}</div>
                     </div>
                     <div class="camera-content">
                         <div class="camera-image">
                             <img id="img-${camera.camera_id}" 
                                  src="/api/camera/${camera.camera_id}/image?t=${Date.now()}" 
                                  alt="Camera ${camera.camera_id}" 
                                  style="width: 100%; height: 100%; object-fit: cover; background: #1a1a1a;"
                                  onerror="handleImageError(this, '${camera.camera_id}')">
                             <div id="offline-${camera.camera_id}" style="display: none; width: 100%; height: 100%; align-items: center; justify-content: center; color: #666;">
                                 Camera Offline
                             </div>
                         </div>
                        <div class="camera-info">
                            <div class="info-item">
                                <div class="info-label">Camera ID</div>
                                <div class="info-value">${camera.camera_id}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Location</div>
                                <div class="info-value">${camera.location}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Coordinates</div>
                                <div class="info-value">${camera.latitude.toFixed(4)}, ${camera.longitude.toFixed(4)}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Last Update</div>
                                <div class="info-value">${camera.last_update || 'Never'}</div>
                            </div>
                        </div>
                    </div>
                `;
                grid.appendChild(cameraBox);
            });
        }
        
         function handleImageError(imgElement, cameraId) {
             console.log(`Image failed for camera ${cameraId}`);
             imgElement.style.display = 'none';
             const offlineElement = document.getElementById(`offline-${cameraId}`);
             if (offlineElement) {
                 offlineElement.style.display = 'flex';
             }
         }
         
         function startLiveImageRefresh() {
             // Refresh all camera images every 2 seconds for live effect
             setInterval(() => {
                 const cameras = document.querySelectorAll('[id^="img-"]');
                 cameras.forEach(img => {
                     const cameraId = img.id.replace('img-', '');
                     
                     // Add loading indicator
                     img.style.opacity = '0.7';
                     
                     // Force refresh with multiple parameters to bypass cache
                     const timestamp = Date.now();
                     const random = Math.random();
                     img.src = `/api/camera/${cameraId}/image?t=${timestamp}&r=${random}&v=${Math.floor(timestamp/1000)}`;
                     
                     // Reset opacity when image loads
                     img.onload = function() {
                         this.style.opacity = '1';
                     };
                 });
             }, 2000);
         }
         
         function sendDispatchMessage() {
             const message = document.getElementById('dispatch-message').value;
             const priority = document.getElementById('priority-select').value;
             
             if (!message.trim()) {
                 alert('Please enter a message');
                 return;
             }
             
             fetch('/api/send-dispatch', {
                 method: 'POST',
                 headers: {
                     'Content-Type': 'application/json',
                 },
                 body: JSON.stringify({
                     message: message,
                     priority: priority
                 })
             })
             .then(response => response.json())
             .then(data => {
                 if (data.success) {
                     alert('Dispatch message sent successfully!');
                     document.getElementById('dispatch-message').value = '';
                 } else {
                     alert('Failed to send dispatch message: ' + data.error);
                 }
             })
             .catch(error => {
                 console.error('Error:', error);
                 alert('Error sending dispatch message');
             });
         }
        
        // Auto-refresh every 30 seconds
        function startAutoRefresh() {
            refreshInterval = setInterval(refreshData, 30000);
        }
        
         // Initialize
         document.addEventListener('DOMContentLoaded', function() {
             refreshData();
             startAutoRefresh();
             startLiveImageRefresh();
         });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Main web interface"""
    return render_template_string(WEB_INTERFACE_HTML)

@app.route('/api/camera-data')
def get_camera_data():
    """Get current camera data"""
    if camera_system:
        return jsonify(camera_system.get_camera_data())
    return jsonify({"error": "Camera system not initialized"}), 500

@app.route('/api/send-dispatch', methods=['POST'])
def send_dispatch():
    """Send dispatch message"""
    if not camera_system:
        return jsonify({"error": "Camera system not initialized"}), 500
    
    data = request.get_json()
    message = data.get('message', '')
    priority = data.get('priority', 'normal')
    
    if not message:
        return jsonify({"error": "Message is required"}), 400
    
    success = camera_system.send_dispatch_message(message, priority)
    
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Failed to send message"}), 500

@app.route('/favicon.ico')
def favicon():
    """Handle favicon requests"""
    return '', 204

@app.route('/api/camera/<camera_id>/image')
def get_camera_image(camera_id):
    """Get camera image with caching"""
    if not camera_system or camera_id not in camera_system.cameras:
        return jsonify({"error": "Camera not found"}), 404
    
    camera = camera_system.cameras[camera_id]
    
    try:
        # Try multiple URL formats
        urls_to_try = [
            f"{camera.image_url}&t={int(time.time())}",
            f"{camera.image_url}?t={int(time.time())}",
            camera.image_url
        ]
        
        for url in urls_to_try:
            try:
                # Add cache busting parameters
                cache_buster = int(time.time() * 1000)
                if '?' in url:
                    url_with_cache = f"{url}&cb={cache_buster}&nocache=1"
                else:
                    url_with_cache = f"{url}?cb={cache_buster}&nocache=1"
                
                response = requests.get(url_with_cache, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache'
                })
                
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    
                    # Check if it's an image or if content looks like an image
                    if ('image' in content_type or 
                        response.content.startswith(b'\xff\xd8\xff') or  # JPEG
                        response.content.startswith(b'\x89PNG') or       # PNG
                        response.content.startswith(b'GIF8') or          # GIF
                        response.content.startswith(b'RIFF') or          # WebP
                        response.content.startswith(b'\x00\x00\x00\x20ftyp') or  # MP4
                        len(response.content) > 10000):  # Large content likely an image
                        
                        # Determine correct content type based on file signature
                        if response.content.startswith(b'\x89PNG'):
                            content_type = 'image/png'
                        elif response.content.startswith(b'\xff\xd8\xff'):
                            content_type = 'image/jpeg'
                        elif response.content.startswith(b'GIF8'):
                            content_type = 'image/gif'
                        elif response.content.startswith(b'RIFF'):
                            content_type = 'image/webp'
                        else:
                            content_type = 'image/jpeg'  # Default fallback
                        
                        return response.content, 200, {
                            'Content-Type': content_type,
                            'Cache-Control': 'no-cache, no-store, must-revalidate',
                            'Pragma': 'no-cache',
                            'Expires': '0'
                        }
                    else:
                        # Log what we got instead of an image
                        logger.warning(f"Camera {camera_id} returned non-image content: {content_type[:50]}")
                        continue
                        
            except Exception as e:
                logger.warning(f"Error with URL {url}: {e}")
                continue
        
        # If no URL worked, return a placeholder image
        return create_placeholder_image(camera_id), 200, {
            'Content-Type': 'image/svg+xml',
            'Cache-Control': 'no-cache, no-store, must-revalidate'
        }
        
    except Exception as e:
        logger.error(f"Error fetching camera {camera_id} image: {e}")
        return create_placeholder_image(camera_id), 200, {
            'Content-Type': 'image/svg+xml',
            'Cache-Control': 'no-cache, no-store, must-revalidate'
        }

def create_placeholder_image(camera_id):
    """Create a placeholder SVG image for offline cameras"""
    svg_content = f'''<svg width="400" height="200" xmlns="http://www.w3.org/2000/svg">
        <rect width="100%" height="100%" fill="#1a1a1a"/>
        <text x="50%" y="40%" text-anchor="middle" fill="#666" font-family="Arial, sans-serif" font-size="16">
            Camera {camera_id}
        </text>
        <text x="50%" y="60%" text-anchor="middle" fill="#888" font-family="Arial, sans-serif" font-size="12">
            Image Unavailable
        </text>
        <text x="50%" y="80%" text-anchor="middle" fill="#555" font-family="Arial, sans-serif" font-size="10">
            {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </text>
    </svg>'''
    return svg_content.encode('utf-8')

@app.route('/api/camera/<camera_id>/stream')
def get_camera_stream(camera_id):
    """Get camera video stream"""
    if not camera_system or camera_id not in camera_system.cameras:
        return jsonify({"error": "Camera not found"}), 404
    
    camera = camera_system.cameras[camera_id]
    
    try:
        # Try to get video stream from iDrive Arkansas
        response = requests.get(camera.stream_url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'video/mp4,video/webm,video/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }, stream=True)
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', 'video/mp4')
            return response.content, 200, {
                'Content-Type': content_type,
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Accept-Ranges': 'bytes'
            }
        else:
            # Fallback to image stream if video not available
            return get_camera_image(camera_id)
            
    except Exception as e:
        logger.error(f"Error fetching camera {camera_id} stream: {e}")
        # Fallback to image if video fails
        return get_camera_image(camera_id)

@app.route('/api/refresh-cameras')
def refresh_cameras():
    """Force refresh all cameras"""
    if camera_system:
        for camera_id, camera in camera_system.cameras.items():
            camera_system._check_camera_status(camera)
        return jsonify({"success": True, "message": "Cameras refreshed"})
    return jsonify({"error": "Camera system not initialized"}), 500

if __name__ == "__main__":
    # Initialize the camera system
    initialize_camera_system()
    
    # Start the web server
    print("Starting Arkansas Traffic Camera System...")
    print("Web interface: http://localhost:5000")
    print("Discord webhook integration enabled")
    print("Monitoring 5 traffic cameras")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
