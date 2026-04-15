#!/usr/bin/env python3
"""
CAD System Monitor - 24/7 Reliability Manager
Monitors the CAD system and automatically restarts it if it fails
"""

import subprocess
import time
import psutil
import requests
import json
import logging
import os
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class CADSystemMonitor:
    """Monitors and maintains the CAD system 24/7"""
    
    def __init__(self, config_file: str = "monitor_config.json"):
        self.config_file = config_file
        self.config = self._load_config()
        self.cad_process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.running = False
        self.restart_count = 0
        self.last_restart = None
        self.health_check_failures = 0
        self.max_health_failures = 3
        self.max_restarts_per_hour = 5
        
        # Setup logging
        self._setup_logging()
        
        # Load notification settings
        self._load_notification_config()
        
    def _load_config(self) -> Dict:
        """Load monitor configuration"""
        default_config = {
            "cad_script": "cad_web_server.py",
            "check_interval": 30,  # seconds
            "health_check_timeout": 10,  # seconds
            "max_restarts_per_hour": 5,
            "max_health_failures": 3,
            "restart_delay": 5,  # seconds between restart attempts
            "log_file": "cad_monitor.log",
            "log_level": "INFO",
            "notifications": {
                "enabled": True,
                "email": {
                    "enabled": False,
                    "smtp_server": "",
                    "smtp_port": 587,
                    "username": "",
                    "password": "",
                    "to_addresses": []
                },
                "discord": {
                    "enabled": True,
                    "webhook_url": ""
                },
                "pushover": {
                    "enabled": True,
                    "user_key": "",
                    "app_token": ""
                }
            }
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults
                    for key, value in default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            else:
                # Create default config file
                with open(self.config_file, 'w') as f:
                    json.dump(default_config, f, indent=4)
                return default_config
        except Exception as e:
            print(f"Error loading config: {e}")
            return default_config
    
    def _setup_logging(self):
        """Setup logging for the monitor"""
        log_level = getattr(logging, self.config.get('log_level', 'INFO').upper())
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config.get('log_file', 'cad_monitor.log')),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _load_notification_config(self):
        """Load notification configuration from environment or config"""
        # Try to load from existing CAD system configs
        try:
            # Load Discord webhook from existing config
            if os.path.exists("discord_webhook.py"):
                with open("discord_webhook.py", 'r') as f:
                    content = f.read()
                    # Extract webhook URL (basic parsing)
                    import re
                    webhook_match = re.search(r'webhook_url\s*=\s*["\']([^"\']+)["\']', content)
                    if webhook_match:
                        self.config['notifications']['discord']['webhook_url'] = webhook_match.group(1)
            
            # Load Pushover config from environment
            pushover_user = os.getenv('PUSHOVER_USER_KEY')
            pushover_token = os.getenv('PUSHOVER_APP_TOKEN')
            if pushover_user and pushover_token:
                self.config['notifications']['pushover']['user_key'] = pushover_user
                self.config['notifications']['pushover']['app_token'] = pushover_token
                
        except Exception as e:
            self.logger.warning(f"Could not load notification config: {e}")
    
    def start_cad_system(self) -> bool:
        """Start the CAD system"""
        try:
            if self.cad_process and self.cad_process.poll() is None:
                self.logger.warning("CAD system is already running")
                return True
            
            self.logger.info("Starting CAD system...")
            
            # Start the CAD web server
            self.cad_process = subprocess.Popen(
                [sys.executable, self.config['cad_script']],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Wait a moment for startup
            time.sleep(5)
            
            if self.cad_process.poll() is None:
                self.logger.info("CAD system started successfully")
                self.restart_count += 1
                self.last_restart = datetime.now()
                self._send_notification("CAD System Started", "The CAD system has been started successfully.")
                return True
            else:
                stdout, stderr = self.cad_process.communicate()
                self.logger.error(f"CAD system failed to start. STDOUT: {stdout}, STDERR: {stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting CAD system: {e}")
            return False
    
    def stop_cad_system(self):
        """Stop the CAD system gracefully"""
        try:
            if self.cad_process and self.cad_process.poll() is None:
                self.logger.info("Stopping CAD system...")
                
                # Try graceful shutdown first
                self.cad_process.terminate()
                
                # Wait for graceful shutdown
                try:
                    self.cad_process.wait(timeout=10)
                    self.logger.info("CAD system stopped gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    self.logger.warning("Graceful shutdown failed, force killing...")
                    self.cad_process.kill()
                    self.cad_process.wait()
                    self.logger.info("CAD system force stopped")
                
                self._send_notification("CAD System Stopped", "The CAD system has been stopped.")
                
        except Exception as e:
            self.logger.error(f"Error stopping CAD system: {e}")
    
    def is_cad_system_running(self) -> bool:
        """Check if CAD system process is running"""
        if not self.cad_process:
            return False
        return self.cad_process.poll() is None
    
    def health_check(self) -> bool:
        """Perform health check on the CAD system"""
        try:
            # Check if process is running
            if not self.is_cad_system_running():
                self.logger.warning("CAD system process is not running")
                return False
            
            # Check if web server is responding
            try:
                response = requests.get(
                    'http://127.0.0.1:5000/api/status',
                    timeout=self.config['health_check_timeout']
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('system_running', False):
                        self.health_check_failures = 0
                        return True
                    else:
                        self.logger.warning("CAD system reports not running")
                        return False
                else:
                    self.logger.warning(f"Health check returned status {response.status_code}")
                    return False
                    
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Health check failed: {e}")
                return False
                
        except Exception as e:
            self.logger.error(f"Health check error: {e}")
            return False
    
    def should_restart(self) -> bool:
        """Determine if we should restart the system"""
        # Check restart rate limiting
        if self.last_restart:
            time_since_restart = datetime.now() - self.last_restart
            if time_since_restart < timedelta(hours=1):
                if self.restart_count >= self.config['max_restarts_per_hour']:
                    self.logger.error("Maximum restarts per hour exceeded")
                    return False
        
        return True
    
    def restart_cad_system(self) -> bool:
        """Restart the CAD system"""
        if not self.should_restart():
            self.logger.error("Restart blocked due to rate limiting")
            return False
        
        self.logger.info("Restarting CAD system...")
        
        # Stop current instance
        self.stop_cad_system()
        
        # Wait before restart
        time.sleep(self.config['restart_delay'])
        
        # Start new instance
        success = self.start_cad_system()
        
        if success:
            self.logger.info("CAD system restarted successfully")
            self._send_notification(
                "CAD System Restarted", 
                f"The CAD system has been restarted (restart #{self.restart_count})"
            )
        else:
            self.logger.error("Failed to restart CAD system")
            self._send_notification(
                "CAD System Restart Failed", 
                "The CAD system failed to restart and may need manual intervention."
            )
        
        return success
    
    def _send_notification(self, title: str, message: str, priority: int = 0):
        """Send notification via configured channels"""
        if not self.config['notifications']['enabled']:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_message = f"[{timestamp}] {message}"
        
        # Discord notification
        if self.config['notifications']['discord']['enabled']:
            self._send_discord_notification(title, full_message)
        
        # Pushover notification
        if self.config['notifications']['pushover']['enabled']:
            self._send_pushover_notification(title, full_message, priority)
        
        # Email notification
        if self.config['notifications']['email']['enabled']:
            self._send_email_notification(title, full_message)
    
    def _send_discord_notification(self, title: str, message: str):
        """Send Discord notification"""
        try:
            webhook_url = self.config['notifications']['discord']['webhook_url']
            if not webhook_url:
                return
            
            data = {
                "embeds": [{
                    "title": title,
                    "description": message,
                    "color": 0x00ff00 if "Started" in title or "Success" in message else 0xff0000,
                    "timestamp": datetime.now().isoformat(),
                    "footer": {"text": "CAD System Monitor"}
                }]
            }
            
            response = requests.post(webhook_url, json=data, timeout=10)
            if response.status_code == 204:
                self.logger.info("Discord notification sent")
            else:
                self.logger.warning(f"Discord notification failed: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"Discord notification error: {e}")
    
    def _send_pushover_notification(self, title: str, message: str, priority: int = 0):
        """Send Pushover notification"""
        try:
            user_key = self.config['notifications']['pushover']['user_key']
            app_token = self.config['notifications']['pushover']['app_token']
            
            if not user_key or not app_token:
                return
            
            data = {
                'token': app_token,
                'user': user_key,
                'title': title,
                'message': message,
                'priority': priority
            }
            
            response = requests.post('https://api.pushover.net/1/messages.json', data=data, timeout=10)
            if response.status_code == 200:
                self.logger.info("Pushover notification sent")
            else:
                self.logger.warning(f"Pushover notification failed: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"Pushover notification error: {e}")
    
    def _send_email_notification(self, title: str, message: str):
        """Send email notification"""
        try:
            email_config = self.config['notifications']['email']
            if not email_config['enabled'] or not email_config['to_addresses']:
                return
            
            msg = MIMEMultipart()
            msg['From'] = email_config['username']
            msg['To'] = ', '.join(email_config['to_addresses'])
            msg['Subject'] = f"CAD System Monitor - {title}"
            
            msg.attach(MIMEText(message, 'plain'))
            
            server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'])
            server.starttls()
            server.login(email_config['username'], email_config['password'])
            server.send_message(msg)
            server.quit()
            
            self.logger.info("Email notification sent")
            
        except Exception as e:
            self.logger.error(f"Email notification error: {e}")
    
    def monitor_loop(self):
        """Main monitoring loop"""
        self.logger.info("Starting CAD system monitor...")
        self.running = True
        
        # Start the CAD system initially
        if not self.start_cad_system():
            self.logger.error("Failed to start CAD system initially")
            return
        
        while self.running:
            try:
                # Perform health check
                if not self.health_check():
                    self.health_check_failures += 1
                    self.logger.warning(f"Health check failed ({self.health_check_failures}/{self.max_health_failures})")
                    
                    if self.health_check_failures >= self.max_health_failures:
                        self.logger.error("Maximum health check failures reached, restarting system...")
                        if self.restart_cad_system():
                            self.health_check_failures = 0
                        else:
                            self.logger.error("Failed to restart system, will retry on next check")
                else:
                    self.health_check_failures = 0
                
                # Wait for next check
                time.sleep(self.config['check_interval'])
                
            except KeyboardInterrupt:
                self.logger.info("Monitor stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Monitor loop error: {e}")
                time.sleep(5)  # Short delay before retry
        
        # Cleanup
        self.stop_cad_system()
        self.logger.info("CAD system monitor stopped")
    
    def start_monitoring(self):
        """Start monitoring in a separate thread"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.logger.warning("Monitor is already running")
            return
        
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("Monitor thread started")
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10)
        self.stop_cad_system()
        self.logger.info("Monitoring stopped")

def main():
    """Main function"""
    monitor = CADSystemMonitor()
    
    try:
        # Start monitoring
        monitor.start_monitoring()
        
        # Keep main thread alive
        while monitor.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down monitor...")
        monitor.stop_monitoring()
    except Exception as e:
        print(f"Monitor error: {e}")
        monitor.stop_monitoring()

if __name__ == "__main__":
    main()
