# FDD CAD Scraper

A Fire Department Dispatch Computer-Aided Dispatch scraper system for monitoring emergency incidents and dispatch data.

## Features

- **Real-time Monitoring**: Continuously monitors fire department dispatch systems
- **Location-based Filtering**: Monitor specific geographic areas with configurable radius
- **Incident Type Filtering**: Filter incidents by type (fire, medical, rescue, etc.)
- **Multi-Agency Support**: Monitor multiple fire departments simultaneously
- **Configurable Notifications**: Console notifications with extensible notification system
- **Easy Setup**: Interactive setup tool for configuration

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run Setup**:
   ```bash
   python fdd_setup.py
   ```

3. **Start Monitoring**:
   ```bash
   python fdd_monitor.py
   ```

## Configuration

The system uses a JSON configuration file (`fdd_config.json`) that can be created and modified using the setup tool or manually.

### Configuration Options

- **Scan Interval**: How often to check for new incidents (seconds)
- **Agencies**: List of fire department agencies to monitor
- **Locations**: Geographic areas to monitor with radius settings
- **Filters**: Incident type allow/block lists
- **Notifications**: Notification methods and settings

### Example Configuration

```json
{
  "scan_interval_seconds": 60,
  "default_radius_meters": 1000.0,
  "agencies": ["001", "002"],
  "locations": [
    {
      "name": "Downtown Portland",
      "address": "Portland, OR",
      "latitude": 45.5152,
      "longitude": -122.6784,
      "radius_meters": 5000.0,
      "importance_level": 1,
      "enabled": true,
      "filters": {
        "allow_list": ["FIRE", "MED", "HAZMAT"],
        "block_list": ["FALSE"]
      }
    }
  ],
  "global_filters": {
    "allow_list": [],
    "block_list": ["FALSE"]
  },
  "notifications_enabled": true,
  "notification_methods": ["console"],
  "data_retention_days": 30,
  "save_to_database": false
}
```

## Usage

### Setup Tool

The interactive setup tool (`fdd_setup.py`) provides commands to:

- `agencies` - List available fire departments
- `add_agency <name>` - Add an agency to monitor
- `remove_agency <name>` - Remove an agency
- `locations` - List monitoring locations
- `add_location` - Add a new monitoring location
- `remove_location <name>` - Remove a location
- `test_agency <name>` - Test connection to an agency
- `config` - Show current configuration
- `save` - Save configuration
- `quit` - Exit setup

### Monitoring

The main monitor (`fdd_monitor.py`) runs continuously and:

- Scans configured agencies at regular intervals
- Filters incidents based on location and type
- Sends notifications for relevant incidents
- Logs activity and errors

### Test Mode

Run a single scan without continuous monitoring:

```bash
python fdd_monitor.py --test
```

## Architecture

### Core Components

- **FDDCADScraper**: Main scraping engine for dispatch data
- **ConfigManager**: Configuration loading and saving
- **IncidentProcessor**: Filters and processes incidents
- **NotificationManager**: Handles notifications
- **FDDMonitor**: Main monitoring application

### Data Structures

- **DispatchIncident**: Represents a single emergency incident
- **DispatchUnit**: Represents a dispatched unit (fire truck, ambulance)
- **MonitoringLocation**: Geographic area to monitor
- **LocationFilter**: Incident type filtering rules

## Customization

### Adding New Incident Types

Modify the `incident_types` dictionary in `fdd_cad_scraper.py`:

```python
self.incident_types = {
    "FIRE": "Structure Fire",
    "MED": "Medical Emergency",
    "CUSTOM": "Custom Incident Type",
    # Add more types as needed
}
```

### Adding Notification Methods

Extend the `NotificationManager` class to add new notification methods:

```python
def _email_notification(self, incident_data):
    # Implement email notification
    pass

def _sms_notification(self, incident_data):
    # Implement SMS notification
    pass
```

### Database Integration

To save incidents to a database, modify the `FDDMonitor` class to include database operations in the `_scan_agencies` method.

## Troubleshooting

### Common Issues

1. **No agencies found**: Check your internet connection and API configuration
2. **No incidents detected**: Verify agency IDs and location coordinates
3. **Configuration errors**: Use the setup tool to validate configuration

### Debug Mode

Enable debug output by modifying the logging level in the monitor application.

## License

This project is provided as-is for educational and monitoring purposes. Ensure compliance with local laws and regulations when monitoring emergency services data.

## Contributing

This is a standalone scraper system. For modifications:

1. Fork the repository
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## Disclaimer

This tool is for monitoring and informational purposes only. Always follow local laws and regulations regarding emergency services monitoring. Do not interfere with emergency operations or dispatch systems.
