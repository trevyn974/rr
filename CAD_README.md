# FDD CAD System - Fire Department Computer-Aided Dispatch

A modern, real-time Computer-Aided Dispatch (CAD) system for monitoring fire department emergency calls and incidents.

## 🚨 Features

### **Real-time Monitoring**
- Live incident tracking from PulsePoint API
- Automatic data refresh every 30 seconds
- Real-time alerts for new incidents
- Multi-agency monitoring support

### **Modern Web Interface**
- Dark theme optimized for dispatch centers
- Responsive design for desktop and mobile
- Priority-based incident categorization
- Interactive incident details

### **Incident Management**
- Active incident monitoring
- Recent incident history
- Priority classification (High/Medium/Low)
- Unit assignment tracking
- Geographic location data

### **Alert System**
- New incident notifications
- Priority-based alerting
- Acknowledgment system
- Visual and audio alerts

## 🛠️ Installation

### **Prerequisites**
- Python 3.8 or higher
- pip package manager

### **Quick Start**
1. **Install dependencies:**
   ```bash
   pip install -r cad_requirements.txt
   ```

2. **Start the CAD system:**
   ```bash
   python start_cad.py
   ```

3. **Access the interface:**
   - Open your browser to `http://127.0.0.1:5000`
   - The system will automatically open in your default browser

## 📁 System Components

### **Core Files**
- `cad_system.py` - Main CAD system logic and monitoring
- `cad_web_server.py` - Flask web server and API endpoints
- `cad_web_interface.html` - Modern web interface
- `start_cad.py` - Easy startup script

### **Integration Files**
- `fdd_cad_scraper.py` - PulsePoint API integration (existing)
- `cad_requirements.txt` - Python dependencies

## 🔧 Configuration

### **CAD System Settings**
Edit `cad_system.py` to modify:
- Refresh interval (default: 30 seconds)
- Maximum incidents display (default: 50)
- Auto-refresh enabled/disabled
- Sound alerts on/off
- Theme selection (dark/light)

### **Agency Management**
Add/remove agencies to monitor:
```python
cad_system.add_agency("04600")  # Rogers Fire Department
cad_system.remove_agency("04600")
```

## 🌐 Web Interface

### **Main Dashboard**
- **Active Incidents**: Currently ongoing emergencies
- **Recent Incidents**: Recently closed calls
- **Alert Panel**: New incidents requiring attention
- **Status Bar**: System status and connection info

### **Incident Display**
- **Priority Colors**: 
  - 🔴 High Priority (Structure Fire, Hazmat, Rescue)
  - 🟡 Medium Priority (Medical, Traffic, Fire Alarm)
  - 🟢 Low Priority (Public Service, Alarms)

### **Interactive Features**
- Click incidents for detailed view
- Acknowledge alerts
- Manual refresh button
- Real-time status updates

## 🔌 API Endpoints

### **Status & Data**
- `GET /api/status` - System status
- `GET /api/incidents` - Current incidents
- `GET /api/alerts` - Active alerts
- `POST /api/refresh` - Manual refresh

### **Agency Management**
- `GET /api/agencies` - List monitored agencies
- `POST /api/agencies` - Add new agency
- `DELETE /api/agencies/<id>` - Remove agency

### **Alert Management**
- `POST /api/alerts/<id>/acknowledge` - Acknowledge alert

### **Data Export**
- `GET /api/export` - Export incidents data

## 🚀 Usage Examples

### **Start Monitoring Rogers Fire Department**
```python
from cad_system import CADSystem, CADConfig

# Create CAD system
config = CADConfig(refresh_interval=30)
cad = CADSystem(config)

# Add agency
cad.add_agency("04600")  # Rogers Fire Department

# Start monitoring
cad.start_monitoring()
```

### **Get Current Incidents**
```python
# Get incidents for specific agency
incidents = cad.get_incidents_for_agency("04600")

print(f"Active: {len(incidents.active)}")
print(f"Recent: {len(incidents.recent)}")

for incident in incidents.active:
    print(f"- {incident.incident_type} at {incident.FullDisplayAddress}")
```

### **Check Alerts**
```python
# Get unacknowledged alerts
alerts = cad.get_unacknowledged_alerts()

for alert in alerts:
    print(f"🚨 {alert.incident_type} at {alert.address}")
```

## 🔒 Security Features

- **API Rate Limiting**: Prevents abuse
- **CORS Protection**: Secure cross-origin requests
- **Input Validation**: Sanitized user inputs
- **Error Handling**: Graceful error recovery

## 📊 Data Sources

### **PulsePoint Integration**
- Real-time incident data
- Agency information
- Unit assignments
- Geographic coordinates

### **Incident Types**
- Medical Emergency
- Traffic Collision
- Fire Alarm
- Structure Fire
- Hazardous Materials
- Rescue Operations
- Public Service

## 🎯 Performance

- **Refresh Rate**: 30-second intervals
- **Response Time**: < 2 seconds for API calls
- **Memory Usage**: Optimized for 24/7 operation
- **Concurrent Users**: Supports multiple operators

## 🛠️ Troubleshooting

### **Common Issues**

**Connection Errors:**
- Check internet connection
- Verify PulsePoint API availability
- Check firewall settings

**Missing Dependencies:**
```bash
pip install -r cad_requirements.txt
```

**Port Already in Use:**
- Change port in `start_cad.py`
- Kill existing processes on port 5000

### **Debug Mode**
Run with debug enabled:
```bash
python cad_web_server.py
```

## 📈 Future Enhancements

- **Map Integration**: Interactive incident mapping
- **Mobile App**: Native mobile interface
- **Database Storage**: Incident history persistence
- **Multi-tenant Support**: Multiple dispatch centers
- **Advanced Analytics**: Incident pattern analysis
- **Integration APIs**: Third-party system integration

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Check the troubleshooting section
- Review API documentation
- Test with the provided examples

---

**FDD CAD System** - Professional fire department dispatch monitoring
