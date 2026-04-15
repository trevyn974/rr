#!/usr/bin/env python3
"""
Startup script for Arkansas Traffic Camera System
"""

import sys
import os
import subprocess
import time

def check_dependencies():
    """Check if required dependencies are installed"""
    required_packages = [
        'flask',
        'flask_cors',
        'requests',
        'pillow'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n📦 Installing missing packages...")
        
        for package in missing_packages:
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                print(f"✅ Installed {package}")
            except subprocess.CalledProcessError:
                print(f"❌ Failed to install {package}")
                return False
    
    return True

def main():
    """Main startup function"""
    print("🚨 Arkansas Traffic Camera System")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        print("❌ Failed to install dependencies. Please install manually:")
        print("   pip install flask flask_cors requests pillow")
        return
    
    print("✅ Dependencies checked")
    
    # Import and start the system
    try:
        from arkansas_cam_system import app, initialize_camera_system
        
        print("🚀 Starting Arkansas Traffic Camera System...")
        print("📡 Web interface will be available at: http://localhost:5000")
        print("🔗 Discord webhook integration enabled")
        print("📹 Monitoring 5 traffic cameras from iDrive Arkansas")
        print("\nPress Ctrl+C to stop the system")
        print("=" * 50)
        
        # Initialize the camera system
        initialize_camera_system()
        
        # Start the web server
        app.run(host='0.0.0.0', port=5000, debug=False)
        
    except KeyboardInterrupt:
        print("\n🛑 System stopped by user")
    except Exception as e:
        print(f"❌ Error starting system: {e}")
        print("Please check the error message above and try again")

if __name__ == "__main__":
    main()
