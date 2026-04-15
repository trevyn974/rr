#!/usr/bin/env python3
"""
Enhanced Error Handler for CAD System
Provides comprehensive error handling, recovery, and logging
"""

import logging
import traceback
import time
import threading
import requests
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class ErrorHandler:
    """Enhanced error handling and recovery system"""
    
    def __init__(self, config_file: str = "error_handler_config.json"):
        self.config_file = config_file
        self.config = self._load_config()
        self.error_counts: Dict[str, int] = {}
        self.last_errors: Dict[str, datetime] = {}
        self.circuit_breakers: Dict[str, Dict] = {}
        self.recovery_attempts: Dict[str, int] = {}
        self.max_recovery_attempts = 3
        self.circuit_breaker_threshold = 5
        self.circuit_breaker_timeout = 300  # 5 minutes
        
        # Setup logging
        self._setup_logging()
        
        # Load notification settings
        self._load_notification_config()
    
    def _load_config(self) -> Dict:
        """Load error handler configuration"""
        default_config = {
            "log_level": "INFO",
            "log_file": "cad_errors.log",
            "max_error_count": 10,
            "error_reset_time": 3600,  # 1 hour
            "circuit_breaker_threshold": 5,
            "circuit_breaker_timeout": 300,
            "max_recovery_attempts": 3,
            "recovery_delay": 5,
            "notifications": {
                "enabled": True,
                "critical_errors": True,
                "error_threshold": 5,
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
            print(f"Error loading error handler config: {e}")
            return default_config
    
    def _setup_logging(self):
        """Setup error logging"""
        log_level = getattr(logging, self.config.get('log_level', 'INFO').upper())
        
        # Create error logger
        self.error_logger = logging.getLogger('cad_errors')
        self.error_logger.setLevel(log_level)
        
        # File handler for errors
        file_handler = logging.FileHandler(self.config.get('log_file', 'cad_errors.log'))
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler for critical errors
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.ERROR)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.error_logger.addHandler(file_handler)
        self.error_logger.addHandler(console_handler)
    
    def _load_notification_config(self):
        """Load notification configuration"""
        try:
            # Load Discord webhook from existing config
            if os.path.exists("discord_webhook.py"):
                with open("discord_webhook.py", 'r') as f:
                    content = f.read()
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
            self.error_logger.warning(f"Could not load notification config: {e}")
    
    def handle_error(self, error: Exception, context: str = "", 
                    recovery_func: Optional[Callable] = None, 
                    critical: bool = False) -> bool:
        """Handle an error with logging, counting, and recovery"""
        error_type = type(error).__name__
        error_key = f"{context}_{error_type}"
        
        # Log the error
        self.error_logger.error(
            f"Error in {context}: {error_type}: {str(error)}",
            exc_info=True
        )
        
        # Update error counts
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        self.last_errors[error_key] = datetime.now()
        
        # Check circuit breaker
        if self._is_circuit_breaker_open(error_key):
            self.error_logger.warning(f"Circuit breaker open for {error_key}")
            return False
        
        # Send notifications for critical errors or high error counts
        if critical or self.error_counts[error_key] >= self.config['notifications']['error_threshold']:
            self._send_error_notification(error, context, critical)
        
        # Attempt recovery if function provided
        if recovery_func and self.recovery_attempts.get(error_key, 0) < self.max_recovery_attempts:
            try:
                self.recovery_attempts[error_key] = self.recovery_attempts.get(error_key, 0) + 1
                self.error_logger.info(f"Attempting recovery for {context} (attempt {self.recovery_attempts[error_key]})")
                
                result = recovery_func()
                if result:
                    self.error_logger.info(f"Recovery successful for {context}")
                    self.recovery_attempts[error_key] = 0
                    return True
                else:
                    self.error_logger.warning(f"Recovery failed for {context}")
            except Exception as recovery_error:
                self.error_logger.error(f"Recovery error for {context}: {recovery_error}")
        
        # Open circuit breaker if threshold exceeded
        if self.error_counts[error_key] >= self.circuit_breaker_threshold:
            self._open_circuit_breaker(error_key)
        
        return False
    
    def _is_circuit_breaker_open(self, error_key: str) -> bool:
        """Check if circuit breaker is open for an error type"""
        if error_key not in self.circuit_breakers:
            return False
        
        breaker = self.circuit_breakers[error_key]
        if breaker['state'] == 'open':
            # Check if timeout has passed
            if datetime.now() - breaker['opened_at'] > timedelta(seconds=self.circuit_breaker_timeout):
                # Try to close the circuit breaker
                breaker['state'] = 'half-open'
                breaker['attempts'] = 0
                self.error_logger.info(f"Circuit breaker half-open for {error_key}")
                return False
            return True
        
        return False
    
    def _open_circuit_breaker(self, error_key: str):
        """Open circuit breaker for an error type"""
        self.circuit_breakers[error_key] = {
            'state': 'open',
            'opened_at': datetime.now(),
            'attempts': 0
        }
        self.error_logger.warning(f"Circuit breaker opened for {error_key}")
    
    def _send_error_notification(self, error: Exception, context: str, critical: bool):
        """Send error notification via configured channels"""
        if not self.config['notifications']['enabled']:
            return
        
        error_type = type(error).__name__
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        title = f"CAD System {'CRITICAL' if critical else 'ERROR'}"
        message = f"[{timestamp}] {context}: {error_type}: {str(error)}"
        
        # Discord notification
        if self.config['notifications']['discord']['enabled']:
            self._send_discord_error_notification(title, message, critical)
        
        # Pushover notification
        if self.config['notifications']['pushover']['enabled']:
            priority = 2 if critical else 0
            self._send_pushover_error_notification(title, message, priority)
        
        # Email notification
        if self.config['notifications']['email']['enabled']:
            self._send_email_error_notification(title, message, critical)
    
    def _send_discord_error_notification(self, title: str, message: str, critical: bool):
        """Send Discord error notification"""
        try:
            webhook_url = self.config['notifications']['discord']['webhook_url']
            if not webhook_url:
                return
            
            color = 0xff0000 if critical else 0xffaa00
            data = {
                "embeds": [{
                    "title": title,
                    "description": message,
                    "color": color,
                    "timestamp": datetime.now().isoformat(),
                    "footer": {"text": "CAD System Error Handler"}
                }]
            }
            
            response = requests.post(webhook_url, json=data, timeout=10)
            if response.status_code != 204:
                self.error_logger.warning(f"Discord error notification failed: {response.status_code}")
                
        except Exception as e:
            self.error_logger.error(f"Discord error notification error: {e}")
    
    def _send_pushover_error_notification(self, title: str, message: str, priority: int):
        """Send Pushover error notification"""
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
            if response.status_code != 200:
                self.error_logger.warning(f"Pushover error notification failed: {response.status_code}")
                
        except Exception as e:
            self.error_logger.error(f"Pushover error notification error: {e}")
    
    def _send_email_error_notification(self, title: str, message: str, critical: bool):
        """Send email error notification"""
        try:
            email_config = self.config['notifications']['email']
            if not email_config['enabled'] or not email_config['to_addresses']:
                return
            
            msg = MIMEMultipart()
            msg['From'] = email_config['username']
            msg['To'] = ', '.join(email_config['to_addresses'])
            msg['Subject'] = f"CAD System - {title}"
            
            body = f"{message}\n\nTraceback:\n{traceback.format_exc()}"
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'])
            server.starttls()
            server.login(email_config['username'], email_config['password'])
            server.send_message(msg)
            server.quit()
            
        except Exception as e:
            self.error_logger.error(f"Email error notification error: {e}")
    
    def retry_with_backoff(self, func: Callable, max_retries: int = 3, 
                          backoff_factor: float = 2.0, exceptions: tuple = (Exception,)):
        """Decorator for retrying functions with exponential backoff"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        self.error_logger.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                        raise e
                    
                    wait_time = backoff_factor ** attempt
                    self.error_logger.warning(f"Function {func.__name__} failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
            
            raise last_exception
        
        return wrapper
    
    def safe_execute(self, func: Callable, *args, context: str = "", 
                    recovery_func: Optional[Callable] = None, 
                    critical: bool = False, **kwargs) -> Any:
        """Safely execute a function with error handling"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.handle_error(e, context, recovery_func, critical)
            return None
    
    def cleanup_old_errors(self):
        """Clean up old error data"""
        cutoff_time = datetime.now() - timedelta(seconds=self.config['error_reset_time'])
        
        # Remove old error counts
        keys_to_remove = []
        for error_key, last_error in self.last_errors.items():
            if last_error < cutoff_time:
                keys_to_remove.append(error_key)
        
        for key in keys_to_remove:
            self.error_counts.pop(key, None)
            self.last_errors.pop(key, None)
            self.recovery_attempts.pop(key, None)
            self.circuit_breakers.pop(key, None)
        
        if keys_to_remove:
            self.error_logger.info(f"Cleaned up {len(keys_to_remove)} old error entries")
    
    def get_error_summary(self) -> Dict:
        """Get summary of current error state"""
        return {
            'error_counts': self.error_counts,
            'circuit_breakers': self.circuit_breakers,
            'recovery_attempts': self.recovery_attempts,
            'total_errors': sum(self.error_counts.values()),
            'open_circuit_breakers': len([cb for cb in self.circuit_breakers.values() if cb['state'] == 'open'])
        }

# Global error handler instance
error_handler = ErrorHandler()

def handle_error(error: Exception, context: str = "", 
                recovery_func: Optional[Callable] = None, 
                critical: bool = False) -> bool:
    """Global error handling function"""
    return error_handler.handle_error(error, context, recovery_func, critical)

def safe_execute(func: Callable, *args, context: str = "", 
                recovery_func: Optional[Callable] = None, 
                critical: bool = False, **kwargs) -> Any:
    """Global safe execution function"""
    return error_handler.safe_execute(func, *args, context=context, 
                                    recovery_func=recovery_func, critical=critical, **kwargs)

def retry_with_backoff(max_retries: int = 3, backoff_factor: float = 2.0, 
                      exceptions: tuple = (Exception,)):
    """Global retry decorator"""
    return error_handler.retry_with_backoff(max_retries, backoff_factor, exceptions)
