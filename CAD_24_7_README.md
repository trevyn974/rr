# FDD CAD System - 24/7 Operation

A robust, enterprise-grade Computer-Aided Dispatch system designed to run continuously without interruption. This system includes comprehensive error handling, automatic recovery, monitoring, and multi-channel notifications.

## 🚨 Features

### Core Functionality
- **24/7 Operation**: Designed to run continuously without manual intervention
- **Automatic Recovery**: Self-healing system that recovers from failures
- **Health Monitoring**: Continuous monitoring of system health and performance
- **Circuit Breaker Pattern**: Prevents cascading failures
- **Multi-Channel Notifications**: Discord, Pushover, Email alerts
- **Comprehensive Logging**: Detailed logs for troubleshooting and analysis

### Reliability Features
- **Auto-Restart**: Automatically restarts failed components
- **Error Handling**: Sophisticated error handling with retry mechanisms
- **Resource Monitoring**: Monitors CPU, memory, and disk usage
- **Network Health Checks**: Verifies connectivity and API responses
- **Backup System**: Automatic backup of configuration and data
- **Service Management**: Windows Service and Linux systemd support

## 📋 Requirements

### System Requirements
- **Python**: 3.8 or higher
- **Operating System**: Windows 10/11, Linux, or macOS
- **Memory**: Minimum 2GB RAM (4GB recommended)
- **Disk Space**: 1GB free space
- **Network**: Internet connection for API calls and notifications

### Python Dependencies
See `cad_24_7_requirements.txt` for complete list.

## 🚀 Quick Start

### 1. Setup and Installation

```bash
# Clone or download the CAD system files
# Navigate to the CAD system directory

# Run the automated setup
python setup_24_7_cad.py
```

### 2. Configure Notifications

Edit the configuration files to set up your notifications:

**Discord Webhook** (`discord_webhook.py`):
```python
webhook_url = "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"
```

**Pushover** (Environment variables):
```bash
set PUSHOVER_USER_KEY=your_user_key
set PUSHOVER_APP_TOKEN=your_app_token
```

**Email** (`monitor_config.json`):
```json
{
  "notifications": {
    "email": {
      "enabled": true,
      "smtp_server": "smtp.gmail.com",
      "smtp_port": 587,
      "username": "your_email@gmail.com",
      "password": "your_app_password",
      "to_addresses": ["admin@yourdomain.com"]
    }
  }
}
```

### 3. Start the System

**Option A: Direct Python (for testing)**
```bash
python start_cad_24_7.py
```

**Option B: Windows Service (recommended for production)**
```powershell
# Install service (run as Administrator)
.\manage_cad_service.ps1 install

# Start service
.\manage_cad_service.ps1 start

# Check status
.\manage_cad_service.ps1 status
```

**Option C: Linux systemd (recommended for production)**
```bash
# Service is automatically installed by setup script
sudo systemctl start fdd-cad
sudo systemctl enable fdd-cad
sudo systemctl status fdd-cad
```

## 🔧 Configuration

### Monitor Configuration (`monitor_config.json`)

```json
{
  "cad_script": "cad_web_server.py",
  "check_interval": 30,
  "health_check_timeout": 10,
  "max_restarts_per_hour": 5,
  "max_health_failures": 3,
  "restart_delay": 5,
  "log_file": "logs/cad_monitor.log",
  "log_level": "INFO"
}
```

### Error Handler Configuration (`error_handler_config.json`)

```json
{
  "log_level": "INFO",
  "log_file": "logs/cad_errors.log",
  "max_error_count": 10,
  "error_reset_time": 3600,
  "circuit_breaker_threshold": 5,
  "circuit_breaker_timeout": 300,
  "max_recovery_attempts": 3
}
```

## 📊 Monitoring and Management

### Health Checks

The system performs continuous health checks:
- **Process Health**: Verifies the CAD system process is running
- **Web Interface**: Checks if the web server responds correctly
- **API Connectivity**: Tests external API connections
- **Resource Usage**: Monitors CPU, memory, and disk usage
- **Network Connectivity**: Verifies internet connectivity

### Logs

All system activity is logged to multiple files:
- `logs/cad_monitor.log` - Monitor activity
- `logs/cad_errors.log` - Error details and recovery attempts
- `logs/cad_24_7.log` - Overall system status

### Status Commands

**Windows PowerShell:**
```powershell
# Check service status
.\manage_cad_service.ps1 status

# View recent logs
.\manage_cad_service.ps1 logs

# Restart service
.\manage_cad_service.ps1 restart
```

**Linux:**
```bash
# Check service status
sudo systemctl status fdd-cad

# View logs
sudo journalctl -u fdd-cad -f

# Restart service
sudo systemctl restart fdd-cad
```

## 🔔 Notifications

### Discord Notifications
- System startup/shutdown
- Error alerts
- Recovery notifications
- Health status updates

### Pushover Notifications
- Critical errors (high priority)
- System status changes
- Recovery confirmations

### Email Notifications
- Detailed error reports
- System status summaries
- Configuration change alerts

## 🛠️ Troubleshooting

### Common Issues

**1. Service Won't Start**
```bash
# Check logs
.\manage_cad_service.ps1 logs

# Verify configuration
python -c "import json; print(json.load(open('monitor_config.json')))"
```

**2. High Memory Usage**
- Check for memory leaks in logs
- Restart the service
- Verify system resources

**3. API Connection Issues**
- Check internet connectivity
- Verify API endpoints are accessible
- Check firewall settings

**4. Notification Failures**
- Verify webhook URLs and tokens
- Check network connectivity
- Review notification configuration

### Recovery Procedures

**Automatic Recovery:**
- System automatically restarts failed components
- Circuit breakers prevent cascading failures
- Health checks ensure system stability

**Manual Recovery:**
```bash
# Stop the service
.\manage_cad_service.ps1 stop

# Check for issues
.\manage_cad_service.ps1 logs

# Restart the service
.\manage_cad_service.ps1 start
```

## 📈 Performance Optimization

### Resource Management
- Automatic cleanup of old logs
- Memory usage monitoring
- CPU usage optimization
- Disk space management

### Network Optimization
- Connection pooling
- Request timeout handling
- Retry mechanisms with backoff
- Circuit breaker pattern

## 🔒 Security Considerations

### Access Control
- Service runs with appropriate privileges
- Configuration files are protected
- Log files contain sensitive information

### Network Security
- Firewall rules for port 5000
- Secure API communications
- Encrypted notification channels

## 📝 Maintenance

### Regular Tasks
- Monitor log files for errors
- Check system resource usage
- Verify notification delivery
- Update configuration as needed

### Backup Procedures
```bash
# Manual backup
python backup_cad_system.py

# Automatic backups are created in logs/backups/
```

## 🆘 Support

### Getting Help
1. Check the logs first: `.\manage_cad_service.ps1 logs`
2. Review configuration files
3. Check system resources
4. Verify network connectivity

### Emergency Procedures
1. **System Down**: Check service status and restart
2. **High Error Rate**: Review logs and check external APIs
3. **Resource Issues**: Restart service and check system resources
4. **Notification Failures**: Verify configuration and network

## 📋 File Structure

```
CAD System Directory/
├── cad_web_server.py          # Main web server
├── cad_system.py              # Core CAD system
├── cad_system_monitor.py      # 24/7 monitor
├── enhanced_error_handler.py  # Error handling
├── start_cad_24_7.py          # Startup script
├── setup_24_7_cad.py          # Setup script
├── manage_cad_service.ps1     # Windows management
├── cad_service_wrapper.py     # Windows service
├── monitor_config.json        # Monitor configuration
├── error_handler_config.json  # Error handler config
├── logs/                      # Log files
├── backups/                   # Backup files
└── README files
```

## 🎯 Best Practices

1. **Regular Monitoring**: Check logs and status regularly
2. **Configuration Management**: Keep configuration files backed up
3. **Resource Monitoring**: Monitor system resources
4. **Notification Testing**: Test notifications regularly
5. **Update Management**: Keep dependencies updated
6. **Security Updates**: Apply security patches promptly

---

**⚠️ Important**: This system is designed for production use. Always test in a safe environment first and ensure you have proper backups before deploying to production.

**🔧 Support**: For technical support, check the logs first and review this documentation. The system includes comprehensive error handling and recovery mechanisms.
