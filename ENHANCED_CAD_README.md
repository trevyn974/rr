# 🚨 Enhanced Fire Department CAD System

A modern, professional Computer-Aided Dispatch (CAD) system designed for fire departments with advanced scraping capabilities, Getac-style interface, and comprehensive response protocols.

## ✨ Features

### **Core Functionality**
- **Real-time Incident Monitoring**: Live tracking of fire department calls and emergencies
- **Advanced Web Scraping**: Intelligent data extraction from multiple sources
- **Modern Web Interface**: Getac-inspired dark theme optimized for dispatch centers
- **Response Protocols**: Built-in fire department response procedures and guidelines
- **Station Management**: Track fire station status and unit assignments
- **Alert System**: Priority-based notifications with acknowledgment system

### **Professional Interface**
- **Getac-Style Design**: Rugged, professional appearance suitable for emergency operations
- **Dark Theme**: Optimized for 24/7 dispatch center operations
- **Responsive Layout**: Works on desktop, tablet, and mobile devices
- **Real-time Updates**: Live data refresh every 30 seconds
- **Priority Color Coding**: Visual priority indicators for different incident types

### **Advanced Features**
- **AI-Powered Predictions**: Machine learning for incident pattern analysis
- **Route Optimization**: Integration with mapping services for optimal response routing
- **Pre-arrival Instructions**: Automated guidance for responding units
- **Multi-Agency Support**: Monitor multiple fire departments simultaneously
- **Data Export**: Export incident data for analysis and reporting

## 🚀 Quick Start

### **Prerequisites**
- Python 3.8 or higher
- Internet connection for real-time data
- Modern web browser

### **Installation**

1. **Clone or download the system files**
2. **Install dependencies:**
   ```bash
   pip install -r enhanced_requirements.txt
   ```

3. **Start the system:**
   ```bash
   python start_enhanced_cad.py
   ```

4. **Access the interface:**
   - The system will automatically open in your browser
   - Default URL: `http://127.0.0.1:5000`

## 📁 System Architecture

### **Core Files**
- `enhanced_fire_cad.py` - Main CAD system with modern features
- `fdd_cad_scraper.py` - Advanced web scraping engine
- `directions_service.py` - Route optimization and mapping
- `ai_predictor.py` - Machine learning for incident prediction
- `templates/enhanced_cad.html` - Modern web interface

### **Configuration**
- `cad_config.json` - System configuration and settings
- `station_units.json` - Fire station and unit information
- `incident_types.json` - Incident type definitions

### **Supporting Files**
- `start_enhanced_cad.py` - Easy startup script
- `enhanced_requirements.txt` - Python dependencies
- `data.py` - Data structures and utilities

## 🔧 Configuration

### **Basic Settings**
Edit `cad_config.json` to customize:

```json
{
    "agencies": ["04600"],           // Fire departments to monitor
    "refresh_interval": 30,          // Update frequency (seconds)
    "your_location": "Rogers, AR",   // Your base location
    "web_port": 5000,               // Web interface port
    "sound_alerts": true,           // Enable audio alerts
    "theme": "dark"                 // Interface theme
}
```

### **Agency Management**
Add/remove fire departments:
```python
cad.add_agency("04600")    # Rogers Fire Department
cad.remove_agency("04600")
```

### **Response Protocols**
Customize response procedures in `cad_config.json`:
```json
{
    "response_protocols": {
        "Structure Fire": {
            "required_units": ["Engine", "Ladder", "Rescue"],
            "response_time_target": 4,
            "priority_level": 1
        }
    }
}
```

## 🌐 Web Interface

### **Main Dashboard**
- **Active Alerts**: Real-time emergency notifications
- **Active Incidents**: Currently ongoing emergencies
- **Recent Incidents**: Recently closed calls
- **Station Status**: Fire station and unit availability

### **Incident Management**
- **Priority Indicators**: Color-coded priority levels
- **Unit Assignments**: Track responding units
- **Location Data**: Address and coordinates
- **Timeline**: Call received and response times

### **Alert System**
- **Visual Alerts**: Prominent notification display
- **Acknowledgment**: Mark alerts as acknowledged
- **Priority Filtering**: Focus on high-priority incidents
- **Sound Alerts**: Audio notifications (configurable)

## 🔌 API Endpoints

### **Status & Data**
- `GET /api/status` - System status and connection info
- `GET /api/incidents` - Current active and recent incidents
- `GET /api/alerts` - Unacknowledged alerts
- `POST /api/refresh` - Manual data refresh

### **Management**
- `GET /api/stations` - Fire station status
- `POST /api/alerts/<id>/acknowledge` - Acknowledge alert
- `POST /api/agencies` - Add new agency
- `DELETE /api/agencies/<id>` - Remove agency

## 🚑 Response Protocols

### **Built-in Protocols**
- **Structure Fire**: Full response with command
- **Medical Emergency**: Engine and ambulance
- **Traffic Collision**: Engine and rescue
- **Hazardous Materials**: Hazmat team response
- **Rescue Operation**: Technical rescue response

### **Custom Protocols**
Add custom response procedures:
```python
protocol = ResponseProtocol(
    incident_type="Custom Emergency",
    required_units=["Engine", "Special Unit"],
    response_time_target=5,
    special_instructions="Custom response procedure",
    priority_level=2
)
```

## 📊 Data Sources

### **Primary Sources**
- **PulsePoint API**: Real-time incident data
- **Fire Department APIs**: Direct agency integration
- **Web Scraping**: Additional data sources

### **Incident Types**
- Medical Emergency
- Structure Fire
- Traffic Collision
- Fire Alarm
- Hazardous Materials
- Rescue Operation
- Public Service

## 🎯 Performance

### **System Requirements**
- **CPU**: Modern multi-core processor
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 1GB for system files
- **Network**: Stable internet connection

### **Performance Metrics**
- **Refresh Rate**: 30-second intervals
- **Response Time**: < 2 seconds for API calls
- **Memory Usage**: Optimized for 24/7 operation
- **Concurrent Users**: Supports multiple operators

## 🔒 Security Features

- **API Rate Limiting**: Prevents system abuse
- **Input Validation**: Sanitized user inputs
- **Error Handling**: Graceful error recovery
- **CORS Protection**: Secure cross-origin requests

## 🛠️ Troubleshooting

### **Common Issues**

**Connection Errors:**
- Check internet connection
- Verify PulsePoint API availability
- Check firewall settings

**Missing Dependencies:**
```bash
pip install -r enhanced_requirements.txt
```

**Port Already in Use:**
- Change port in `cad_config.json`
- Kill existing processes on port 5000

**No Incidents Displayed:**
- Verify agency IDs are correct
- Check location coordinates
- Ensure agencies are active

### **Debug Mode**
Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📈 Future Enhancements

- **Mobile App**: Native mobile interface
- **Database Integration**: Persistent data storage
- **Advanced Analytics**: Incident pattern analysis
- **Integration APIs**: Third-party system integration
- **Voice Commands**: Hands-free operation
- **Multi-tenant Support**: Multiple dispatch centers

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
- Review configuration options
- Test with provided examples
- Check system logs for errors

---

**Enhanced Fire CAD System** - Professional fire department dispatch monitoring with modern technology and Getac-style interface.

## 🚨 Emergency Use Disclaimer

This system is designed for monitoring and informational purposes. Always follow local laws and regulations regarding emergency services monitoring. Do not interfere with emergency operations or dispatch systems.
