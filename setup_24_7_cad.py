#!/usr/bin/env python3
"""
CAD System 24/7 Setup Script
Installs and configures the CAD system for reliable 24/7 operation
"""

import os
import sys
import subprocess
import json
import platform
import shutil
from pathlib import Path

class CAD24_7Setup:
    """Setup and configuration for 24/7 CAD system"""
    
    def __init__(self):
        self.system = platform.system().lower()
        self.is_admin = self._check_admin()
        self.script_dir = Path(__file__).parent.absolute()
        
    def _check_admin(self):
        """Check if running as administrator"""
        if self.system == "windows":
            try:
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin()
            except:
                return False
        else:
            return os.geteuid() == 0
    
    def _run_command(self, command, check=True):
        """Run a command and return the result"""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if check and result.returncode != 0:
                print(f"Command failed: {command}")
                print(f"Error: {result.stderr}")
                return False
            return result
        except Exception as e:
            print(f"Error running command {command}: {e}")
            return False
    
    def install_dependencies(self):
        """Install required Python packages"""
        print("Installing Python dependencies...")
        
        # Upgrade pip first
        self._run_command(f"{sys.executable} -m pip install --upgrade pip")
        
        # Install requirements
        requirements_file = self.script_dir / "cad_24_7_requirements.txt"
        if requirements_file.exists():
            result = self._run_command(f"{sys.executable} -m pip install -r {requirements_file}")
            if result:
                print("✓ Dependencies installed successfully")
                return True
            else:
                print("✗ Failed to install dependencies")
                return False
        else:
            print("✗ Requirements file not found")
            return False
    
    def create_directories(self):
        """Create necessary directories"""
        print("Creating directories...")
        
        directories = [
            "logs",
            "backups",
            "config",
            "monitoring"
        ]
        
        for directory in directories:
            dir_path = self.script_dir / directory
            dir_path.mkdir(exist_ok=True)
            print(f"✓ Created directory: {directory}")
    
    def create_config_files(self):
        """Create configuration files"""
        print("Creating configuration files...")
        
        # Monitor configuration
        monitor_config = {
            "cad_script": "cad_web_server.py",
            "check_interval": 30,
            "health_check_timeout": 10,
            "max_restarts_per_hour": 5,
            "max_health_failures": 3,
            "restart_delay": 5,
            "log_file": "logs/cad_monitor.log",
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
        
        config_file = self.script_dir / "monitor_config.json"
        with open(config_file, 'w') as f:
            json.dump(monitor_config, f, indent=4)
        print("✓ Created monitor configuration")
        
        # Error handler configuration
        error_config = {
            "log_level": "INFO",
            "log_file": "logs/cad_errors.log",
            "max_error_count": 10,
            "error_reset_time": 3600,
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
        
        error_config_file = self.script_dir / "error_handler_config.json"
        with open(error_config_file, 'w') as f:
            json.dump(error_config, f, indent=4)
        print("✓ Created error handler configuration")
    
    def setup_windows_service(self):
        """Setup Windows service (if on Windows)"""
        if self.system != "windows":
            print("Skipping Windows service setup (not on Windows)")
            return True
        
        if not self.is_admin:
            print("⚠️  Administrator privileges required for Windows service setup")
            print("   Please run this script as Administrator")
            return False
        
        print("Setting up Windows service...")
        
        # Install pywin32 if not already installed
        try:
            import win32serviceutil
        except ImportError:
            print("Installing pywin32...")
            result = self._run_command(f"{sys.executable} -m pip install pywin32")
            if not result:
                print("✗ Failed to install pywin32")
                return False
        
        # Install the service
        service_script = self.script_dir / "cad_service_wrapper.py"
        if service_script.exists():
            result = self._run_command(f"{sys.executable} {service_script} install")
            if result:
                print("✓ Windows service installed")
                return True
            else:
                print("✗ Failed to install Windows service")
                return False
        else:
            print("✗ Service wrapper script not found")
            return False
    
    def create_startup_scripts(self):
        """Create startup scripts for different platforms"""
        print("Creating startup scripts...")
        
        if self.system == "windows":
            # Create Windows batch file
            batch_content = f"""@echo off
cd /d "{self.script_dir}"
python start_cad_24_7.py
pause
"""
            batch_file = self.script_dir / "start_cad_24_7.bat"
            with open(batch_file, 'w') as f:
                f.write(batch_content)
            print("✓ Created Windows startup script")
            
            # Create PowerShell script
            ps_content = f"""# CAD System 24/7 Startup Script
Set-Location "{self.script_dir}"
python start_cad_24_7.py
"""
            ps_file = self.script_dir / "start_cad_24_7.ps1"
            with open(ps_file, 'w') as f:
                f.write(ps_content)
            print("✓ Created PowerShell startup script")
            
        else:
            # Create Linux/Mac shell script
            shell_content = f"""#!/bin/bash
cd "{self.script_dir}"
python3 start_cad_24_7.py
"""
            shell_file = self.script_dir / "start_cad_24_7.sh"
            with open(shell_file, 'w') as f:
                f.write(shell_content)
            os.chmod(shell_file, 0o755)
            print("✓ Created shell startup script")
    
    def create_systemd_service(self):
        """Create systemd service for Linux"""
        if self.system != "linux":
            print("Skipping systemd service setup (not on Linux)")
            return True
        
        if not self.is_admin:
            print("⚠️  Root privileges required for systemd service setup")
            return False
        
        print("Creating systemd service...")
        
        service_content = f"""[Unit]
Description=FDD CAD System 24/7
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={self.script_dir}
ExecStart={sys.executable} {self.script_dir}/start_cad_24_7.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
        
        service_file = Path("/etc/systemd/system/fdd-cad.service")
        try:
            with open(service_file, 'w') as f:
                f.write(service_content)
            
            # Reload systemd and enable service
            self._run_command("systemctl daemon-reload")
            self._run_command("systemctl enable fdd-cad.service")
            
            print("✓ Systemd service created and enabled")
            return True
        except Exception as e:
            print(f"✗ Failed to create systemd service: {e}")
            return False
    
    def setup_firewall_rules(self):
        """Setup firewall rules for the CAD system"""
        print("Setting up firewall rules...")
        
        if self.system == "windows":
            # Windows firewall
            if self.is_admin:
                self._run_command("netsh advfirewall firewall add rule name=\"FDD CAD System\" dir=in action=allow protocol=TCP localport=5000")
                print("✓ Windows firewall rule added")
            else:
                print("⚠️  Administrator privileges required for firewall setup")
        else:
            # Linux firewall
            if self.is_admin:
                self._run_command("ufw allow 5000/tcp")
                print("✓ Linux firewall rule added")
            else:
                print("⚠️  Root privileges required for firewall setup")
    
    def create_backup_script(self):
        """Create backup script for configuration and data"""
        print("Creating backup script...")
        
        backup_script = f"""#!/usr/bin/env python3
import os
import shutil
import datetime
from pathlib import Path

def backup_cad_system():
    script_dir = Path("{self.script_dir}")
    backup_dir = script_dir / "backups" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Files to backup
    files_to_backup = [
        "cad_system.py",
        "cad_web_server.py",
        "fdd_cad_scraper.py",
        "discord_webhook.py",
        "*.json",
        "*.db",
        "logs/"
    ]
    
    for pattern in files_to_backup:
        for file_path in script_dir.glob(pattern):
            if file_path.is_file():
                dest = backup_dir / file_path.name
                shutil.copy2(file_path, dest)
            elif file_path.is_dir():
                dest = backup_dir / file_path.name
                shutil.copytree(file_path, dest)
    
    print(f"Backup created: {{backup_dir}}")

if __name__ == "__main__":
    backup_cad_system()
"""
        
        backup_file = self.script_dir / "backup_cad_system.py"
        with open(backup_file, 'w') as f:
            f.write(backup_script)
        
        if self.system != "windows":
            os.chmod(backup_file, 0o755)
        
        print("✓ Backup script created")
    
    def run_setup(self):
        """Run the complete setup process"""
        print("=" * 60)
        print("FDD CAD System 24/7 Setup")
        print("=" * 60)
        
        steps = [
            ("Installing dependencies", self.install_dependencies),
            ("Creating directories", self.create_directories),
            ("Creating configuration files", self.create_config_files),
            ("Creating startup scripts", self.create_startup_scripts),
            ("Setting up Windows service", self.setup_windows_service),
            ("Creating systemd service", self.create_systemd_service),
            ("Setting up firewall rules", self.setup_firewall_rules),
            ("Creating backup script", self.create_backup_script),
        ]
        
        success_count = 0
        for step_name, step_func in steps:
            print(f"\n{step_name}...")
            try:
                if step_func():
                    success_count += 1
                    print(f"✓ {step_name} completed")
                else:
                    print(f"✗ {step_name} failed")
            except Exception as e:
                print(f"✗ {step_name} failed: {e}")
        
        print("\n" + "=" * 60)
        print(f"Setup completed: {success_count}/{len(steps)} steps successful")
        
        if success_count == len(steps):
            print("\n🎉 CAD System 24/7 setup completed successfully!")
            print("\nNext steps:")
            print("1. Configure your notification settings in the config files")
            print("2. Test the system: python start_cad_24_7.py")
            print("3. For Windows: Use the PowerShell script to manage the service")
            print("4. For Linux: Use systemctl to manage the service")
        else:
            print("\n⚠️  Some setup steps failed. Please check the errors above.")
        
        return success_count == len(steps)

def main():
    """Main function"""
    setup = CAD24_7Setup()
    setup.run_setup()

if __name__ == "__main__":
    main()
