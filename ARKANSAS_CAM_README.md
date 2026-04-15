# Arkansas Traffic Camera System

A comprehensive traffic camera monitoring system that integrates with iDrive Arkansas traffic cameras and Discord webhooks for real-time highway monitoring and dispatch operations.

## Features

### 📹 Camera Monitoring
- **5-Box Camera Layout**: Monitor up to 5 traffic cameras simultaneously
- **Real-time Updates**: Automatic refresh every 30 seconds
- **Camera Status Tracking**: Monitor online/offline status of each camera
- **iDrive Arkansas Integration**: Direct integration with Arkansas DOT traffic cameras

### 📡 Discord Integration
- **Real-time Alerts**: Automatic Discord notifications when cameras go offline
- **Dispatch Messaging**: Send priority-based dispatch messages to Discord
- **Traffic Incident Alerts**: Notifications for potential traffic incidents
- **Rate Limiting**: Prevents spam with intelligent alert throttling

### 🎨 Modern Web Interface
- **Dark Theme**: Professional dark mode interface [[memory:8771106]]
- **Responsive Design**: Works on desktop and mobile devices
- **Real-time Status**: Live system status and camera health monitoring
- **No Animations**: Clean, professional interface without distracting animations [[memory:8771109]]

## Camera Configuration

The system is pre-configured with 5 Arkansas traffic cameras:

1. **Camera 349**: Highway Camera 349
2. **Camera 350**: Highway Camera 350  
3. **Camera 351**: Highway Camera 351
4. **Camera 352**: Highway Camera 352
5. **Camera 353**: Highway Camera 353

All cameras are configured to pull images from the iDrive Arkansas API:
- Base URL: `https://actis.idrivearkansas.com/index.php/api/cameras`
- Image URL: `https://actis.idrivearkansas.com/index.php/api/cameras/image?camera={ID}`

## Discord Webhook Configuration

The system uses your existing Discord webhook for notifications:
- **Webhook URL**: `https://discord.com/api/webhooks/1379959452098232450/oFAvxyvROKGhes8EvArVJqv_1dtI8T_JmGRYAVE9SDmGESiSooMLPHsoSMMBFUep4HeD`

### Alert Types
- **Camera Offline**: Red alert when a camera becomes unavailable
- **Traffic Incident**: Yellow alert for potential traffic issues
- **Dispatch Messages**: Custom priority-based messages

## Installation & Setup

### Quick Start
```bash
# Run the startup script (installs dependencies automatically)
python start_arkansas_cam.py
```

### Manual Installation
```bash
# Install dependencies
pip install -r arkansas_requirements.txt

# Run the system
python arkansas_cam_system.py
```

## Usage

### Web Interface
1. Open your browser to `http://localhost:5000`
2. View all 5 cameras in the grid layout
3. Monitor camera status and health
4. Send dispatch messages through the interface

### Dispatch Messaging
1. Enter your message in the "Dispatch Message Center"
2. Select priority level (Normal, Medium, High)
3. Click "Send Dispatch Message"
4. Message will be sent to Discord with appropriate formatting

### Camera Monitoring
- **Green Status**: Camera is online and functioning
- **Red Status**: Camera is offline or experiencing issues
- **Auto-refresh**: System automatically updates every 30 seconds
- **Manual Refresh**: Click the refresh button for immediate update

## API Endpoints

### GET `/api/camera-data`
Returns current camera data and system status.

### POST `/api/send-dispatch`
Send a dispatch message to Discord.
```json
{
    "message": "Your dispatch message here",
    "priority": "high"
}
```

### GET `/api/camera/<camera_id>/image`
Get the current image from a specific camera.

## Configuration

### Camera System Settings
```python
@dataclass
class ArkansasCamConfig:
    refresh_interval: int = 30  # seconds
    max_cameras: int = 5
    auto_refresh: bool = True
    discord_enabled: bool = True
    theme: str = "dark"
    
    # Discord webhook settings
    discord_webhook_url: str = "YOUR_WEBHOOK_URL"
    
    # Alert settings
    alert_on_camera_offline: bool = True
    alert_on_traffic_incident: bool = True
```

## Troubleshooting

### Camera Images Not Loading
- Check if the iDrive Arkansas API is accessible
- Verify camera IDs are correct
- Check network connectivity

### Discord Messages Not Sending
- Verify webhook URL is correct
- Check Discord webhook permissions
- Ensure rate limiting isn't blocking messages

### System Not Starting
- Install all required dependencies
- Check Python version (3.7+ required)
- Verify port 5000 is available

## Technical Details

### Architecture
- **Backend**: Flask web server with threading for camera monitoring
- **Frontend**: HTML/CSS/JavaScript with responsive design
- **Integration**: iDrive Arkansas API + Discord webhooks
- **Monitoring**: Background thread for continuous camera status checking

### Performance
- **Refresh Rate**: 30-second intervals (configurable)
- **Rate Limiting**: 5-minute cooldown between camera alerts
- **Memory Usage**: Minimal footprint with efficient image handling
- **Network**: Optimized requests with timeout handling

## Security Notes

- Discord webhook URL is included in the code - consider using environment variables for production
- Camera images are cached temporarily for performance
- No authentication required for web interface (add if needed for production)

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Verify all dependencies are installed
3. Check the console output for error messages
4. Ensure network connectivity to iDrive Arkansas and Discord

## License

This system is designed for emergency services and traffic monitoring use. Please ensure compliance with local regulations and Arkansas DOT terms of service.
