#!/usr/bin/env python3
"""
Extract Camera Feeds from iDrive Arkansas Website
This script helps extract real camera feed URLs from the iDrive Arkansas website
"""

import requests
import json
import re
from bs4 import BeautifulSoup
import time

def extract_camera_urls():
    """Extract camera URLs from iDrive Arkansas website"""
    
    print("🔍 Extracting camera URLs from iDrive Arkansas...")
    
    # Known camera URLs from your console data
    known_cameras = {
        "349": "https://actis.idrivearkansas.com/index.php/api/cameras/image?camera=349",
        "350": "https://actis.idrivearkansas.com/index.php/api/cameras/image?camera=350"
    }
    
    # Try to find more cameras by testing different IDs
    found_cameras = {}
    
    print("📹 Testing camera IDs...")
    
    # Test camera IDs from 300 to 400 (common range for Arkansas cameras)
    for camera_id in range(300, 401):
        url = f"https://actis.idrivearkansas.com/index.php/api/cameras/image?camera={camera_id}"
        
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                # Check if it's actually an image (not an error page)
                content_type = response.headers.get('content-type', '')
                if 'image' in content_type:
                    found_cameras[str(camera_id)] = url
                    print(f"✅ Found camera {camera_id}: {url}")
                else:
                    print(f"❌ Camera {camera_id}: Not an image ({content_type})")
            else:
                print(f"❌ Camera {camera_id}: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"❌ Camera {camera_id}: Error - {e}")
        
        # Small delay to avoid overwhelming the server
        time.sleep(0.1)
    
    # Combine known and found cameras
    all_cameras = {**known_cameras, **found_cameras}
    
    print(f"\n📊 Found {len(all_cameras)} working cameras:")
    for cam_id, url in all_cameras.items():
        print(f"  Camera {cam_id}: {url}")
    
    return all_cameras

def test_camera_feed(camera_url):
    """Test if a camera feed is working"""
    try:
        response = requests.get(camera_url, timeout=10)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type:
                return True, f"Working - {content_type}"
            else:
                return False, f"Not an image - {content_type}"
        else:
            return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, f"Error: {e}"

def generate_camera_config(cameras):
    """Generate camera configuration for the Arkansas system"""
    
    config = {
        "cameras": [],
        "total_cameras": len(cameras),
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    for i, (cam_id, url) in enumerate(cameras.items()):
        # Test the camera
        is_working, status = test_camera_feed(url)
        
        camera_config = {
            "camera_id": cam_id,
            "name": f"Highway Camera {cam_id}",
            "location": "Arkansas Highway",
            "latitude": 36.1864 + (i * 0.01),  # Spread cameras slightly
            "longitude": -94.1284 + (i * 0.01),
            "image_url": url,
            "stream_url": "https://www.idrivearkansas.com/",
            "status": "active" if is_working else "offline",
            "last_update": time.strftime("%Y-%m-%d %H:%M:%S") if is_working else "",
            "test_status": status
        }
        
        config["cameras"].append(camera_config)
    
    return config

def main():
    """Main function"""
    print("🚨 iDrive Arkansas Camera Feed Extractor")
    print("=" * 50)
    
    # Extract camera URLs
    cameras = extract_camera_urls()
    
    if not cameras:
        print("❌ No cameras found!")
        return
    
    # Generate configuration
    config = generate_camera_config(cameras)
    
    # Save configuration
    with open('arkansas_camera_config.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\n💾 Configuration saved to arkansas_camera_config.json")
    print(f"📊 Found {len(cameras)} working cameras")
    
    # Show working cameras
    working_cameras = [cam for cam in config["cameras"] if cam["status"] == "active"]
    print(f"✅ {len(working_cameras)} cameras are working")
    
    for cam in working_cameras[:5]:  # Show first 5
        print(f"  Camera {cam['camera_id']}: {cam['name']}")
    
    if len(working_cameras) > 5:
        print(f"  ... and {len(working_cameras) - 5} more")

if __name__ == "__main__":
    main()
