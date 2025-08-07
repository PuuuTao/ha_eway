"""Constants for the Eway Charger integration."""

# Domain
DOMAIN = "eway"

# Default values
DEFAULT_PORT = 8888
DEFAULT_SCAN_INTERVAL = 30

# WebSocket connection settings
WS_CONNECT_TIMEOUT = 10
WS_PING_INTERVAL = 30
WS_PING_TIMEOUT = 10
WS_CLOSE_TIMEOUT = 10

# Device info
MANUFACTURER = "Eway"
MODEL_CHARGER = "Smart Charger"
MODEL_STORAGE = "Energy Storage"

def get_device_model(device_type: str) -> str:
    """Get device model based on device type."""
    if device_type == "energy_storage":
        return MODEL_STORAGE
    return MODEL_CHARGER

def get_device_name(device_type: str, device_id: str) -> str:
    """Get device name based on device type and device ID."""
    if device_type == "energy_storage":
        return f"Energy Storage {device_id}"
    return f"Eway Charger {device_id}"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_SN = "device_sn"
