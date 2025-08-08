# Eway Charger and Energy Storage Home Assistant Integration

A comprehensive Home Assistant custom integration for monitoring and controlling Eway charging stations and energy storage systems. Supports charging management for chargers and photovoltaic generation and battery storage monitoring for energy storage devices.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Sensors](#sensors)
- [Control Functions](#control-functions)
- [Response Handling](#response-handling)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Features

### Core Functions

#### Charger Functions
- **Automatic Device Discovery**: Automatically discover Eway chargers on the network via mDNS
- **Real-time Status Monitoring**: Monitor charging status, current, connection status, etc.
- **Remote Control**: Support charging switch functionality

#### Energy Storage Functions
- **Photovoltaic Generation Monitoring**: Real-time power monitoring, daily and total generation statistics
- **Battery Storage Management**: Battery SOC, charge/discharge power, energy statistics
- **System Status Monitoring**: Energy storage system output power, protocol version, data timestamp
- **Smart Data Processing**: Automatic unit conversion (W/kWh) and precision control

#### General Functions
- **Multi-device Type Support**: Simultaneous support for chargers and energy storage devices
- **Multi-language Support**: Complete Chinese and English interface support
- **Configurable Sensors**: Users can choose to enable or disable specific sensors
- **Real-time Data Updates**: WebSocket connection ensures data real-time performance

### Supported Device Types
- **Eway CS-TFT Series Chargers**: Support charging monitoring, control and NFC management
- **Eway Energy Storage Devices**: Support photovoltaic generation, battery storage and energy management monitoring
- **Eway Devices with WebSocket Communication**: Real-time data transmission and remote control

## Installation

### Method 1: Install via HACS

1. Ensure HACS is installed
2. Add custom repository in HACS
3. Search for "Eway" and install
4. Restart Home Assistant

### Method 2: Manual Installation

1. Download the latest version of the integration files
2. Copy the `eway` folder to the `custom_components` directory
3. Restart Home Assistant
4. Add "Eway" in the integrations page

## Configuration

### Automatic Discovery Configuration

1. Go to "Configuration" > "Devices & Services"
2. Click "Add Integration"
3. Search for "Eway"
4. Select "Automatic Discovery"
5. The system will scan for devices on the network
6. Select your charger and complete the configuration

### Manual Configuration

#### Charger Device Configuration

1. Select "Manual Configuration"
2. Select device type as "Charger"
3. Enter the following information:
   - **Host Address**: Charger IP address
   - **Device ID**: Charger device ID
   - **Device Serial Number**: Charger serial number

#### Energy Storage Device Configuration

1. Select "Manual Configuration"
2. Select device type as "Energy Storage"
3. Enter the following information:
   - **Host Address**: Energy storage device IP address
   - **Device Serial Number**: Energy storage device serial number

### Sensor Configuration

After configuration, you can customize sensors:
1. Click "Configure" on the integration page
2. Select the required sensors
3. Set scan interval (recommended 30-60 seconds)
4. Save configuration

## Sensors

### Charger Sensors

#### Device Information Sensors

| Sensor ID | Chinese Name | English Name | Description |
|----------|----------|----------|------|
| `app_firmware_version` | 应用固件版本 | App Firmware Version | Application firmware version information |
| `charge_current` | 充电电流 | Charge Current | Current charging current value |
| `charge_status` | 充电状态 | Charge Status | Charger working status |
| `gun_status` | 充电枪状态 | Gun Status | Charging gun connection status |
| `pile_status` | 充电桩状态 | Pile Status | Device overall operating status |
| `mcb_firmware_version` | MCB固件版本 | MCB Firmware Version | MCB control board firmware version |
| `net_firmware_version` | 网络固件版本 | Net Firmware Version | Network module firmware version |
| `net_source` | 网络来源 | Net Source | Network connection type |
| `wifi_ssid` | WiFi SSID | WiFi SSID | Currently connected WiFi network name |
| `work_charge_time` | 总充电时长 | Work Charge Time | Cumulative charging time |
| `work_this_time` | 本次充电时长 | Work This Time | Current session charging time |
| `work_total_time` | 总工作时长 | Work Total Time | Device total operating time |
| `gun_lock` | 充电枪锁状态 | Gun Lock | Charging gun lock status |
| `time_zone` | 时区 | Time Zone | Device timezone setting |

#### Binary Sensors

| Sensor ID | Chinese Name | English Name | Description |
|----------|----------|----------|------|
| `charging` | 充电中 | Charging | Whether currently charging |
| `gun_connected` | 充电枪连接 | Gun Connected | Whether charging gun is connected |
| `gun_locked` | 充电枪锁定 | Gun Locked | Whether charging gun is locked |
| `connection` | 连接状态 | Connection | Device network connection status |
| `error` | 错误状态 | Error | Whether there are errors |

### Energy Storage Device Sensors

#### System Information Sensors

| Sensor ID | Chinese Name | English Name | Unit | Description |
|----------|----------|----------|------|------|
| `storage_timestamp` | 数据更新时间 | Data Update Time | - | Energy storage data last update time |
| `storage_protocol_version` | 储能协议版本 | Energy Storage Protocol Version | - | Energy storage device communication protocol version |
| `storage_output_power` | 储能输出功率 | Energy Storage Output Power | W | Energy storage system current output power |

#### Photovoltaic Generation Sensors

| Sensor ID | Chinese Name | English Name | Unit | Precision | Description |
|----------|----------|----------|------|------|------|
| `storage_pv_power` | 储能PV功率 | Energy Storage PV Power | W | 1 decimal | Photovoltaic module current generation power |
| `storage_pv_daily_generation` | 储能PV日发电量 | Energy Storage PV Daily Generation | kWh | 2 decimals | Photovoltaic module daily cumulative generation |
| `storage_pv_total_generation` | 储能PV总发电量 | Energy Storage PV Total Generation | kWh | 2 decimals | Photovoltaic module total cumulative generation |

#### Battery Storage Sensors

| Sensor ID | Chinese Name | English Name | Unit | Precision | Description |
|----------|----------|----------|------|------|------|
| `storage_battery_power` | 储能电池功率 | Energy Storage Battery Power | W | 1 decimal | Battery current charge/discharge power (positive for charging, negative for discharging) |
| `storage_battery_soc` | 储能电池SOC | Energy Storage Battery SOC | % | 1 decimal | Battery remaining charge percentage |
| `storage_battery_daily_charge` | 储能电池日充电量 | Energy Storage Battery Daily Charge | kWh | 2 decimals | Battery daily cumulative charge |
| `storage_battery_total_charge` | 储能电池总充电量 | Energy Storage Battery Total Charge | kWh | 2 decimals | Battery total cumulative charge |
| `storage_battery_daily_discharge` | 储能电池日放电量 | Energy Storage Battery Daily Discharge | kWh | 2 decimals | Battery daily cumulative discharge |
| `storage_battery_total_discharge` | 储能电池总放电量 | Energy Storage Battery Total Discharge | kWh | 2 decimals | Battery total cumulative discharge |

### Response Sensors

| Sensor ID | Chinese Name | English Name | Description |
|----------|----------|----------|------|
| `charging_control_response` | 充电控制响应 | Charging Control Response | Charging switch control response |
| `device_error_response` | 设备错误响应 | Device Error Response | Device error status response |
| `device_status_responses` | 设备状态响应 | Device Status Responses | Device status query response |

## Control Functions

### Charging Control

#### Charging Switch Control
- **Entity Type**: Switch
- **Function**: Start/stop charging
- **Protocol**: Send control commands via `/function/get` topic

**Usage**:
1. Find the "Charging Switch" entity in Home Assistant
2. Click the switch to control charging start/stop

### Energy Storage Control

#### Storage Power Control
- **Entity Type**: Number (Slider)
- **Function**: Set energy storage device output power
- **Range**: 0-800W
- **Unit**: Watts (W)
- **Protocol**: Send control commands via `/property/get` topic

**Usage**:
1. Find the "Storage Power Control" entity in Home Assistant
2. Use the slider to set desired output power (0-800W)
3. The device will adjust its output power accordingly

**Command Format**:
```json
{
  "topic": "/{device_sn}/property/get",
  "payload": {
    "timestamp": 1740448316070,
    "messageId": "generated_uuid_without_dashes",
    "productCode": "EwayES",
    "deviceNum": "{device_sn}",
    "source": "ws",
    "property": [
      {
        "id": "workMode",
        "value": "0",
        "extend": {
          "constantPower": 500
        }
      }
    ]
  }
}
```

### Storage Device Information Query

**Entity Type**: Automatic Background Process  
**Function**: Retrieve device information and automatically set power slider initial value  
**Protocol**: Send query commands via `/info/get` topic

**Usage**:
1. Automatically triggered when power control slider loads
2. Retrieves current work mode and power settings from device
3. Sets slider to current power value if device is in constant power mode (workMode = "0")

**Query Command Format**:
```json
{
  "topic": "/{device_sn}/info/get",
  "payload": {
    "timestamp": 1740448316070,
    "messageId": "generated_uuid_without_dashes",
    "source": "ws"
  }
}
```

**Device Response Format**:
```json
{
  "topic": "/{device_sn}/info/post",
  "payload": {
    "timestamp": 1740448316070,
    "messageId": "generated_uuid_without_dashes",
    "workModeInfo": {
      "workMode": "0",
      "extend": {
        "constantPower": 500
      }
    }
  }
}
```

**Logic**:
- Only when `workMode` is "0" (string), the `constantPower` value is applied to the power slider
- This ensures the slider shows the correct current power setting when loaded
- No continuous monitoring - only queries on slider initialization

## Response Handling

### Charging Control Response
After executing charging control operations, the device returns response messages containing:
- Operation result (success/failure)
- Current charging status
- Response timestamp
- Detailed status information

### Device Status Response
Device status query responses contain:
- Gun status (gun-status)
- Charging status (charge-status)
- Pile status (pile-status)
- Detailed status values and descriptions

### Error Response Handling
When device errors occur, error responses are returned:
- Error code
- Error description
- Error occurrence time
- Error level (warning/error/critical)

## Troubleshooting

### Common Issues

#### Device Discovery Failure
1. **Check Network Connection**: Ensure Home Assistant and charger are on the same LAN
2. **Check Firewall**: Ensure mDNS port (5353) is not blocked
3. **Check Device Status**: Ensure charger is powered on and connected to network
4. **Manual Configuration**: If automatic discovery fails, try manual configuration

#### WebSocket Connection Failure
1. **Check Port**: Confirm WebSocket port (usually 80) is correct
2. **Check Device ID**: Verify device ID and serial number are correct
3. **Network Latency**: Increase connection timeout
4. **Restart Device**: Try restarting the charger device

#### Sensor Data Anomalies
1. **Check Scan Interval**: Avoid setting too short scan intervals
2. **View Logs**: Check Home Assistant logs for error information
3. **Reconfigure**: Try deleting and re-adding the integration
4. **Firmware Version**: Confirm charger firmware version compatibility

#### Control Commands Not Responding
1. **Check Permissions**: Confirm device allows remote control
2. **Network Status**: Check device network connection status
3. **Command Format**: Verify sent command format is correct
4. **Device Mode**: Confirm device is in controllable state

#### Energy Storage Device Data Anomalies
1. **Check Data Format**: Confirm energy storage device returns correct JSON data format
2. **Unit Conversion**: Verify power and energy data unit conversion is correct
3. **Data Precision**: Check sensor data decimal places display
4. **Timestamp**: Confirm data update timestamp is normal

#### Photovoltaic Generation Data Inaccuracy
1. **Weather Impact**: Consider weather conditions' impact on photovoltaic generation
2. **Device Calibration**: Check if photovoltaic components need calibration
3. **Obstruction Check**: Confirm photovoltaic panels are not obstructed
4. **Device Status**: Verify photovoltaic inverter working status

#### Battery Data Display Issues
1. **SOC Calibration**: Check battery management system SOC calibration
2. **Charge/Discharge Status**: Confirm battery charge/discharge status displays correctly
3. **Capacity Settings**: Verify battery capacity configuration is correct
4. **Temperature Impact**: Consider temperature impact on battery performance

## Development

### Project Structure
```
eway_charger/
├── __init__.py              # Integration initialization
├── config_flow.py           # Configuration flow
├── const.py                 # Constants definition
├── coordinator.py           # Data coordinator
├── device_discovery.py      # Device discovery
├── sensor.py               # Sensor entities
├── binary_sensor.py        # Binary sensors
├── switch.py               # Switch entities
├── number.py               # Number entities (power control)
├── websocket_client.py     # WebSocket client
├── translations/           # Multi-language translations
│   ├── en.json
│   └── zh.json
└── manifest.json           # Integration manifest
```

### Protocol Description

#### MQTT Topic Format
- **Property Get**: `/device_id/device_sn/property/get`
- **Property Response**: `/device_id/device_sn/property/post`
- **Function Control**: `/device_id/device_sn/function/get`
- **Function Response**: `/device_id/device_sn/function/post`

#### WebSocket Message Format
```json
{
  "topic": "/device_id/device_sn/property/get",
  "payload": {
    "id": "command_id",
    "value": "command_value",
    "remark": "command_remark",
    "userId": ""
  }
}
```

### Extension Development

#### Adding New Sensors
1. Define sensor configuration in `const.py`
2. Implement sensor class in `sensor.py`
3. Add multi-language support in translation files
4. Update documentation

#### Adding New Control Functions
1. Choose appropriate entity type (switch/number/text etc.)
2. Implement control logic and protocol format
3. Add response handling logic
4. Write test cases

### Version History

#### v0.1.0
- Initial release
- Basic device discovery and connection functionality
- Core sensor support

#### v0.2.0 - Energy Storage Support
- **New Energy Storage Device Type Support**: Complete energy storage device monitoring functionality
- **Photovoltaic Generation Monitoring**: Real-time power, daily generation, total generation sensors
- **Battery Storage Management**: Battery power, SOC, charge/discharge monitoring
- **Data Processing Enhancement**: Automatic unit conversion (W/kWh) and precision control
- **Multi-language Support**: Chinese and English translations for energy storage sensors
- **Configuration Flow Optimization**: Support for automatic discovery and manual configuration of energy storage devices
- **Dashboard Templates**: Provide energy storage system monitoring card configuration examples
- **Automation Templates**: Battery management and photovoltaic generation automation examples
- **Test Validation**: Complete energy storage functionality test suite

#### v0.2.1 - Energy Storage Power Control
- **Storage Power Control**: Added number entity for controlling energy storage device output power
- **Slider Interface**: 0-800W power control with intuitive slider interface in Home Assistant
- **Protocol Implementation**: Complete WebSocket command protocol for power setting
- **Multi-language Support**: Added Chinese and English translations for power control entity
- **Documentation Update**: Added detailed usage instructions and command format examples

#### v0.2.2 - Device Information Query
- **Automatic Device Info Retrieval**: Added background process to query device information on slider load
- **Smart Initial Value Setting**: Power slider automatically sets to current device power when workMode is "0"
- **Info Protocol Implementation**: Complete `/info/get` and `/info/post` topic protocol support
- **Enhanced User Experience**: Slider shows actual device state instead of default zero value
- **Optimized Data Handling**: Improved device info response processing and workMode validation

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Contributing

Issues and Pull Requests are welcome to improve this project.

## Support

If you encounter problems during use, please:
1. Check the troubleshooting section of this documentation
2. Check known issues in GitHub Issues
3. Submit a new Issue describing your problem

---

**Note**: This integration is only compatible with Eway charger devices that support the corresponding protocols. Please confirm your device model and firmware version compatibility before use.