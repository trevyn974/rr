#!/usr/bin/env python3
"""
CAD System 24/7 Startup Script
Ensures the CAD system runs reliably around the clock
"""

import os
import sys
import time
import subprocess
import threading
import signal
import psutil
from datetime import datetime
from cad_system_monitor import CADSystemMonitor
from enhanced_error_handler import error_handler

class CAD24_7Manager:
    """Manages the CAD system for 24/7 operation"""
    
    def __init__(self):
        self.monitor = None
        self.running = False
        self.startup_time = datetime.now()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Check system requirements
        self._check_requirements()
        
        # Initialize monitor
        self.monitor = CADSystemMonitor()
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        self.running = False
        if self.monitor:
            self.monitor.stop_monitoring()
        sys.exit(0)
    
    def _check_requirements(self):
        """Check system requirements and dependencies"""
        print("Checking system requirements...")
        
        # Check Python version
        if sys.version_info < (3, 8):
            print("ERROR: Python 3.8 or higher is required")
            sys.exit(1)
        
        # Check required packages
        required_packages = [
            'flask', 'requests', 'psutil', 'pyttsx3'
        ]
        
        missing_packages = []
        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                missing_packages.append(package)
        
        if missing_packages:
            print(f"ERROR: Missing required packages: {', '.join(missing_packages)}")
            print("Install them with: pip install " + " ".join(missing_packages))
            sys.exit(1)
        
        # Check if we're in the right directory
        required_files = [
            'cad_web_server.py',
            'cad_system.py',
            'fdd_cad_scraper.py'
        ]
        
        missing_files = []
        for file in required_files:
            if not os.path.exists(file):
                missing_files.append(file)
        
        if missing_files:
            print(f"ERROR: Missing required files: {', '.join(missing_files)}")
            print("Make sure you're running this script from the CAD system directory")
            sys.exit(1)
        
        print("+ System requirements check passed")
    
    def _check_system_resources(self):
        """Check system resources and warn if low"""
        try:
            # Check memory usage
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                print(f"WARNING: High memory usage: {memory.percent}%")
            
            # Check disk space
            disk = psutil.disk_usage('.')
            if disk.percent > 90:
                print(f"WARNING: Low disk space: {disk.percent}% used")
            
            # Check CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > 90:
                print(f"WARNING: High CPU usage: {cpu_percent}%")
                
        except Exception as e:
            print(f"Warning: Could not check system resources: {e}")
    
    def _setup_logging(self):
        """Setup comprehensive logging"""
        import logging
        
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Setup main logger
        logger = logging.getLogger('cad_24_7')
        logger.setLevel(logging.INFO)
        
        # File handler
        file_handler = logging.FileHandler('logs/cad_24_7.log')
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    def _create_startup_banner(self):
        """Create startup banner"""
        banner = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                        FDD CAD SYSTEM - 24/7 OPERATION                      ║
║                                                                              ║
║  🚨 Fire Department Dispatch Computer-Aided Dispatch System                 ║
║  🔄 Automatic Monitoring & Recovery                                         ║
║  📊 Real-time Incident Tracking                                             ║
║  🔔 Multi-channel Notifications                                             ║
║                                                                              ║
║  Starting at: {startup_time}                                    ║
║  Web Interface: http://127.0.0.1:5000                                       ║
║  Press Ctrl+C to stop                                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
        """.format(startup_time=self.startup_time.strftime("%Y-%m-%d %H:%M:%S"))
        
        print(banner)
    
    def _send_startup_notification(self):
        """Send startup notification"""
        try:
            startup_time = self.startup_time.strftime("%Y-%m-%d %H:%M:%S")
            message = f"FDD CAD System started successfully at {startup_time}"
            
            # Send via error handler (which has notification capabilities)
            error_handler._send_error_notification(
                Exception("System Startup"), 
                "CAD System 24/7 Manager", 
                False
            )
            
        except Exception as e:
            print(f"Warning: Could not send startup notification: {e}")
    
    def _monitor_system_health(self):
        """Monitor overall system health"""
        while self.running:
            try:
                # Check system resources
                self._check_system_resources()
                
                # Cleanup old error data
                error_handler.cleanup_old_errors()
                
                # Wait before next check
                time.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                print(f"Health monitor error: {e}")
                time.sleep(60)  # Wait 1 minute on error
    
    def start(self):
        """Start the 24/7 CAD system"""
        self._create_startup_banner()
        
        # Setup logging
        logger = self._setup_logging()
        logger.info("Starting CAD System 24/7 Manager")
        
        # Send startup notification
        self._send_startup_notification()
        
        # Start system health monitoring
        health_thread = threading.Thread(target=self._monitor_system_health, daemon=True)
        health_thread.start()
        
        # Start the CAD system monitor
        self.running = True
        try:
            self.monitor.start_monitoring()
            
            # Keep main thread alive
            while self.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nShutdown requested by user")
        except Exception as e:
            logger.error(f"Fatal error in 24/7 manager: {e}")
            error_handler.handle_error(e, "CAD 24/7 Manager", critical=True)
        finally:
            self.stop()
    
    def stop(self):
        """Stop the 24/7 CAD system"""
        print("Stopping CAD System 24/7 Manager...")
        self.running = False
        
        if self.monitor:
            self.monitor.stop_monitoring()
        
        print("CAD System 24/7 Manager stopped")

def main():
    """Main function"""
    try:
        manager = CAD24_7Manager()
        manager.start()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
