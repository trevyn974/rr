#!/usr/bin/env python3
"""
System Verification Tool
Check if the CAD system is running correctly and all components are working
"""

import requests
import time
from datetime import datetime

def check_web_server():
    """Check if web server is running"""
    try:
        response = requests.get('http://127.0.0.1:125/api/status', timeout=5)
        if response.status_code == 200:
            data = response.json()
            print("✓ Web Server: ONLINE")
            print(f"  - System Running: {data.get('system_running', False)}")
            print(f"  - Active Incidents: {data.get('active_incidents', 0)}")
            print(f"  - Recent Incidents: {data.get('recent_incidents', 0)}")
            print(f"  - Last Update: {data.get('last_update', 'Never')}")
            return True
        else:
            print(f"✗ Web Server: ERROR (HTTP {response.status_code})")
            return False
    except Exception as e:
        print(f"✗ Web Server: OFFLINE ({e})")
        return False

def check_incidents():
    """Check if incidents are being fetched"""
    try:
        response = requests.get('http://127.0.0.1:125/api/incidents', timeout=5)
        if response.status_code == 200:
            data = response.json()
            active = len(data.get('active', []))
            recent = len(data.get('recent', []))
            print(f"✓ Incidents API: WORKING")
            print(f"  - Active: {active}")
            print(f"  - Recent: {recent}")
            print(f"  - Last Update: {data.get('last_update', 'Never')}")
            return True
        else:
            print(f"✗ Incidents API: ERROR (HTTP {response.status_code})")
            return False
    except Exception as e:
        print(f"✗ Incidents API: FAILED ({e})")
        return False

def check_units():
    """Check if unit status is working"""
    try:
        response = requests.get('http://127.0.0.1:125/api/units', timeout=5)
        if response.status_code == 200:
            data = response.json()
            units = len(data.get('units', []))
            print(f"✓ Units API: WORKING")
            print(f"  - Total Units: {units}")
            return True
        else:
            print(f"✗ Units API: ERROR (HTTP {response.status_code})")
            return False
    except Exception as e:
        print(f"✗ Units API: FAILED ({e})")
        return False

def check_health():
    """Check system health endpoint"""
    try:
        response = requests.get('http://127.0.0.1:125/api/health', timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Health Check: PASSED")
            print(f"  - Server Status: {data.get('status', 'Unknown')}")
            print(f"  - CAD Initialized: {data.get('cad_system_initialized', False)}")
            return True
        else:
            print(f"✗ Health Check: FAILED (HTTP {response.status_code})")
            return False
    except Exception as e:
        print(f"✗ Health Check: FAILED ({e})")
        return False

def verify_system():
    """Run all verification checks"""
    print("=" * 60)
    print("CAD SYSTEM VERIFICATION")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    results = []
    
    print("1. Checking Web Server...")
    results.append(("Web Server", check_web_server()))
    print()
    
    print("2. Checking Health Endpoint...")
    results.append(("Health", check_health()))
    print()
    
    print("3. Checking Incidents API...")
    results.append(("Incidents", check_incidents()))
    print()
    
    print("4. Checking Units API...")
    results.append(("Units", check_units()))
    print()
    
    print("=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{name:20} {status}")
        if not result:
            all_passed = False
    
    print()
    if all_passed:
        print("✓ ALL CHECKS PASSED - System is running correctly!")
        print()
        print("WHAT TO LOOK FOR WHEN YOU RETURN:")
        print("  - Look for [HEALTH] messages every ~5 minutes")
        print("  - Look for [WATCHDOG] messages every 10 minutes")
        print("  - Look for [ALERT] NEW INCIDENT messages when incidents occur")
        print("  - Look for [CLOSED] messages when incidents close")
        print("  - Check web interface at http://127.0.0.1:125")
    else:
        print("✗ SOME CHECKS FAILED - Review errors above")
        print()
        print("TROUBLESHOOTING:")
        print("  1. Make sure the system is running (python start_cad.py)")
        print("  2. Check if port 125 is available")
        print("  3. Review console output for errors")
    
    print("=" * 60)
    return all_passed

if __name__ == "__main__":
    verify_system()


