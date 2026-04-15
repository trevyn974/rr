#!/usr/bin/env python3
"""
Enhanced Fire CAD System Startup Script
Launches the modern Computer-Aided Dispatch system
"""

import sys
import os
import subprocess
import webbrowser
import time
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    required_packages = [
        'flask', 'requests', 'cryptography', 'prodict'
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
        
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', 
                *missing_packages
            ])
            print("✅ Dependencies installed successfully!")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error installing dependencies: {e}")
            return False
    
    return True

def main():
    """Main startup function"""
    print("🚨 Enhanced Fire Department CAD System")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not os.path.exists('enhanced_fire_cad.py'):
        print("❌ Error: enhanced_fire_cad.py not found!")
        print("   Make sure you're running this from the correct directory.")
        return
    
    # Check dependencies
    if not check_dependencies():
        print("❌ Failed to install dependencies. Exiting.")
        return
    
    print("✅ Dependencies check passed!")
    print("🚀 Starting Enhanced CAD System...")
    
    try:
        # Import and run the enhanced CAD system
        from enhanced_fire_cad import main as cad_main
        cad_main()
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all required files are present.")
    except KeyboardInterrupt:
        print("\n🛑 Shutting down Enhanced CAD System...")
    except Exception as e:
        print(f"❌ Error starting CAD system: {e}")

if __name__ == "__main__":
    main()
