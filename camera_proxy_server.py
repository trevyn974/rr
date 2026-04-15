#!/usr/bin/env python3
"""
Camera Stream Proxy Server
Bypasses CORS restrictions for iDrive Arkansas camera streams
"""

from flask import Flask, Response, request, jsonify
from flask_cors import CORS
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/proxy/camera/<camera_id>')
def proxy_camera_image(camera_id):
    """Proxy camera image requests to bypass CORS"""
    try:
        # Construct the iDrive Arkansas API URL
        url = f"https://actis.idrivearkansas.com/index.php/api/cameras/image?camera={camera_id}"
        
        # Add timestamp to force refresh
        timestamp = int(time.time())
        url += f"&t={timestamp}"
        
        # Make request to iDrive Arkansas
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Return the image with proper headers
        return Response(
            response.content,
            mimetype=response.headers.get('content-type', 'image/jpeg'),
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
        
    except requests.RequestException as e:
        logger.error(f"Error fetching camera {camera_id}: {e}")
        return jsonify({'error': 'Camera feed unavailable'}), 503

@app.route('/proxy/stream/<camera_id>')
def proxy_camera_stream(camera_id):
    """Proxy camera stream requests (if needed)"""
    try:
        # This would be for HLS streams if you can get them working
        # For now, we'll return a placeholder
        return jsonify({
            'message': 'Stream proxy not implemented yet',
            'camera_id': camera_id,
            'suggestion': 'Use image endpoint instead for now'
        })
        
    except Exception as e:
        logger.error(f"Error with stream {camera_id}: {e}")
        return jsonify({'error': 'Stream unavailable'}), 503

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'camera-proxy'})

if __name__ == '__main__':
    import time
    print("Starting Camera Proxy Server...")
    print("Access camera images at: http://localhost:5001/proxy/camera/{camera_id}")
    print("Example: http://localhost:5001/proxy/camera/349")
    app.run(host='0.0.0.0', port=5001, debug=True)



