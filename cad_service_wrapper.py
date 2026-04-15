#!/usr/bin/env python3
"""
CAD Service Wrapper - Windows Service for 24/7 CAD System
"""

import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import os
import time
import threading
from cad_system_monitor import CADSystemMonitor

class CADService(win32serviceutil.ServiceFramework):
    """Windows Service for CAD System"""
    
    _svc_name_ = "FDDCADSystem"
    _svc_display_name_ = "FDD CAD System Service"
    _svc_description_ = "Fire Department Dispatch CAD System - 24/7 Monitoring"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.monitor = None
        self.is_running = False
        
    def SvcStop(self):
        """Stop the service"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_running = False
        
        if self.monitor:
            self.monitor.stop_monitoring()
        
        servicemanager.LogInfoMsg("CAD Service stopped")
    
    def SvcDoRun(self):
        """Run the service"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        
        self.is_running = True
        
        try:
            # Change to the script directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            os.chdir(script_dir)
            
            # Initialize and start the monitor
            self.monitor = CADSystemMonitor()
            self.monitor.start_monitoring()
            
            # Wait for stop event
            while self.is_running:
                result = win32event.WaitForSingleObject(self.hWaitStop, 1000)
                if result == win32event.WAIT_OBJECT_0:
                    break
                    
        except Exception as e:
            servicemanager.LogErrorMsg(f"CAD Service error: {e}")
        finally:
            if self.monitor:
                self.monitor.stop_monitoring()

def install_service():
    """Install the service"""
    try:
        win32serviceutil.InstallService(
            CADService._svc_name_,
            CADService._svc_display_name_,
            description=CADService._svc_description_,
            startType=win32service.SERVICE_AUTO_START
        )
        print("Service installed successfully")
        print("You can start it with: net start FDDCADSystem")
    except Exception as e:
        print(f"Error installing service: {e}")

def uninstall_service():
    """Uninstall the service"""
    try:
        win32serviceutil.RemoveService(CADService._svc_name_)
        print("Service uninstalled successfully")
    except Exception as e:
        print(f"Error uninstalling service: {e}")

def start_service():
    """Start the service"""
    try:
        win32serviceutil.StartService(CADService._svc_name_)
        print("Service started successfully")
    except Exception as e:
        print(f"Error starting service: {e}")

def stop_service():
    """Stop the service"""
    try:
        win32serviceutil.StopService(CADService._svc_name_)
        print("Service stopped successfully")
    except Exception as e:
        print(f"Error stopping service: {e}")

def main():
    """Main function"""
    if len(sys.argv) == 1:
        # Run as service
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(CADService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Handle command line arguments
        command = sys.argv[1].lower()
        
        if command == 'install':
            install_service()
        elif command == 'uninstall':
            uninstall_service()
        elif command == 'start':
            start_service()
        elif command == 'stop':
            stop_service()
        elif command == 'restart':
            stop_service()
            time.sleep(2)
            start_service()
        else:
            print("Usage: python cad_service_wrapper.py [install|uninstall|start|stop|restart]")

if __name__ == '__main__':
    main()
