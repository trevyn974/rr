#!/usr/bin/env python3
"""
Console Commands for Arkansas Camera System
Provides easy console commands to extract and test camera feeds
"""

import requests
import json
import time
from datetime import datetime

def test_single_camera(camera_id):
    """Test a single camera by ID"""
    url = f"https://actis.idrivearkansas.com/index.php/api/cameras/image?camera={camera_id}"
    
    print(f"🔍 Testing Camera {camera_id}...")
    print(f"URL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'Unknown')}")
        print(f"Content-Length: {len(response.content)} bytes")
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type:
                print("✅ Camera is working!")
                return True
            else:
                print("❌ Not an image")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_multiple_cameras(start_id, end_id):
    """Test multiple cameras in a range"""
    print(f"🔍 Testing cameras {start_id} to {end_id}...")
    
    working_cameras = []
    
    for camera_id in range(start_id, end_id + 1):
        url = f"https://actis.idrivearkansas.com/index.php/api/cameras/image?camera={camera_id}"
        
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'image' in content_type:
                    working_cameras.append(camera_id)
                    print(f"✅ Camera {camera_id}: Working")
                else:
                    print(f"❌ Camera {camera_id}: Not an image")
            else:
                print(f"❌ Camera {camera_id}: HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ Camera {camera_id}: Error")
        
        time.sleep(0.1)  # Small delay
    
    print(f"\n📊 Found {len(working_cameras)} working cameras: {working_cameras}")
    return working_cameras

def get_camera_data_json():
    """Get camera data in JSON format"""
    try:
        response = requests.get("http://localhost:5000/api/camera-data")
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def send_dispatch_console(message, priority="normal"):
    """Send dispatch message from console"""
    try:
        data = {
            "message": message,
            "priority": priority
        }
        
        response = requests.post(
            "http://localhost:5000/api/send-dispatch",
            json=data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print("✅ Dispatch message sent successfully!")
                return True
            else:
                print(f"❌ Failed to send message: {result.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending dispatch: {e}")
        return False

def main():
    """Main console interface"""
    print("🚨 Arkansas Camera System Console Commands")
    print("=" * 50)
    
    while True:
        print("\nAvailable Commands:")
        print("1. Test single camera (e.g., 349)")
        print("2. Test camera range (e.g., 300-400)")
        print("3. Get system data (JSON)")
        print("4. Send dispatch message")
        print("5. Test known cameras (349, 350)")
        print("6. Exit")
        
        choice = input("\nEnter command (1-6): ").strip()
        
        if choice == "1":
            camera_id = input("Enter camera ID: ").strip()
            if camera_id.isdigit():
                test_single_camera(int(camera_id))
            else:
                print("❌ Invalid camera ID")
        
        elif choice == "2":
            try:
                start = int(input("Start camera ID: "))
                end = int(input("End camera ID: "))
                test_multiple_cameras(start, end)
            except ValueError:
                print("❌ Invalid range")
        
        elif choice == "3":
            data = get_camera_data_json()
            print("\n📊 System Data:")
            print(json.dumps(data, indent=2))
        
        elif choice == "4":
            message = input("Enter dispatch message: ").strip()
            if message:
                priority = input("Priority (normal/medium/high): ").strip().lower()
                if priority not in ["normal", "medium", "high"]:
                    priority = "normal"
                send_dispatch_console(message, priority)
            else:
                print("❌ Message cannot be empty")
        
        elif choice == "5":
            print("🔍 Testing known cameras...")
            test_single_camera(349)
            print()
            test_single_camera(350)
        
        elif choice == "6":
            print("👋 Goodbye!")
            break
        
        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    main()
