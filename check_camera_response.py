#!/usr/bin/env python3
"""
Check Camera Response Format
Examine what the iDrive Arkansas API actually returns
"""

import requests
import json
import time

def check_camera_response(camera_id: str):
    """Check what the camera API returns"""
    print(f"Checking camera {camera_id} response format...")
    
    timestamp = int(time.time())
    url = f"https://actis.idrivearkansas.com/index.php/api/cameras/image?camera={camera_id}&t={timestamp}"
    
    try:
        response = requests.get(url, timeout=10)
        
        print(f"  Status Code: {response.status_code}")
        print(f"  Content-Type: {response.headers.get('content-type', 'unknown')}")
        print(f"  Content-Length: {len(response.content)}")
        
        # Check if it's actually binary image data
        content_type = response.headers.get('content-type', '')
        if 'image' in content_type.lower() or len(response.content) > 100000:
            print("  Response appears to be binary image data")
            print(f"  File size: {len(response.content)} bytes")
            
            # Check for common image headers
            if response.content.startswith(b'\xff\xd8\xff'):
                print("  Format: JPEG (detected by magic bytes)")
            elif response.content.startswith(b'\x89PNG'):
                print("  Format: PNG (detected by magic bytes)")
            elif response.content.startswith(b'GIF'):
                print("  Format: GIF (detected by magic bytes)")
            else:
                print("  Format: Unknown binary format")
                
            # Save a sample image
            filename = f"camera_{camera_id}_sample.jpg"
            with open(filename, 'wb') as f:
                f.write(response.content)
            print(f"  Saved sample image: {filename}")
            
        else:
            # Try to parse as JSON
            try:
                json_data = response.json()
                print(f"  JSON Response Keys: {list(json_data.keys())}")
                print(f"  Full JSON: {json.dumps(json_data, indent=2)[:500]}...")
                
            except json.JSONDecodeError:
                print("  Response is not valid JSON")
                print(f"  Raw content preview: {response.content[:100]}...")
            
    except requests.RequestException as e:
        print(f"  Error: {e}")

def main():
    """Check a few cameras to understand the response format"""
    print("Checking iDrive Arkansas API Response Format")
    print("=" * 60)
    
    # Test a few cameras
    cameras = ["349", "350", "351"]
    
    for camera_id in cameras:
        check_camera_response(camera_id)
        print()

if __name__ == "__main__":
    main()
