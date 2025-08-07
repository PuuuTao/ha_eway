"""Binary sensor platform for Eway Charger."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, get_device_model, get_device_name
from .coordinator import EwayChargerCoordinator

# Binary sensor configurations
BINARY_SENSOR_CONFIGS = {
    "charging": {
        "translation_key": "charging",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "icon": "mdi:ev-station",
        "enabled_by_default": True,
    },
    "gun_connected": {
        "translation_key": "gun_connected",
        "device_class": BinarySensorDeviceClass.PLUG,
        "icon": "mdi:power-plug",
        "enabled_by_default": True,
    },
    "gun_locked": {
        "translation_key": "gun_locked",
        "device_class": BinarySensorDeviceClass.LOCK,
        "icon": "mdi:lock",
        "enabled_by_default": True,
    },
    "nfc_enabled": {
        "translation_key": "nfc_enabled",
        "device_class": None,
        "icon": "mdi:nfc",
        "enabled_by_default": False,
    },
    "connection": {
        "translation_key": "connection",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "icon": "mdi:wifi",
        "enabled_by_default": True,
    },
    "error": {
        "translation_key": "error",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "icon": "mdi:alert-circle",
        "enabled_by_default": True,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Only set up charger binary sensors for charger devices
    if coordinator.device_type != "charger":
        _LOGGER.debug("Skipping charger binary sensors for device type: %s", coordinator.device_type)
        return

    # Only set up charger binary sensors for charger devices
    device_type = config_entry.data.get("device_type", "charger")
    if device_type != "charger":
        # Skip charger binary sensors for non-charger devices
        return

    # Get enabled sensors from config entry options
    enabled_sensors = config_entry.options.get("enabled_sensors", [])

    entities = []

    for sensor_key, config in BINARY_SENSOR_CONFIGS.items():
        # Check if sensor is enabled (with or without binary_ prefix)
        binary_key = f"binary_{sensor_key}"
        is_enabled = (
            enabled_sensors
            and (sensor_key in enabled_sensors or binary_key in enabled_sensors)
        ) or (not enabled_sensors and config.get("enabled_by_default", False))

        if is_enabled:
            entities.append(
                EwayChargerBinarySensorEntity(coordinator, sensor_key, config)
            )

    async_add_entities(entities)


class EwayChargerBinarySensorEntity(CoordinatorEntity, BinarySensorEntity):
    """Base class for Eway Charger binary sensor entities."""

    def __init__(
        self,
        coordinator: EwayChargerCoordinator,
        sensor_key: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._config = config
        self._attr_unique_id = f"{coordinator.device_id}_{sensor_key}"
        self._attr_translation_key = config.get("translation_key")
        self._attr_icon = config.get("icon")
        self._attr_device_class = config.get("device_class")
        self._attr_has_entity_name = True  # Enable entity name

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        # For energy storage devices, use device serial number as identifier if device_id is empty
        # For charger devices, use device_id as usual
        if self.coordinator.device_type == "energy_storage" and not self.coordinator.device_id:
            device_identifier = self.coordinator.device_sn or ""
            device_name = get_device_name(self.coordinator.device_type, self.coordinator.device_sn or "")
        else:
            device_identifier = self.coordinator.device_id
            device_name = get_device_name(self.coordinator.device_type, self.coordinator.device_id)

        return {
            "identifiers": {(DOMAIN, device_identifier)},
            "name": device_name,
            "manufacturer": MANUFACTURER,
            "model": get_device_model(self.coordinator.device_type),
            "sw_version": self._get_firmware_version(),
            "serial_number": self.coordinator.device_sn,
        }

    def _get_device_info_value(self, key: str) -> Any:
        """Get value from device info data."""
        if not self.coordinator.data:
            return None

        # First try to get from device_info (processed data)
        device_info = self.coordinator.data.get("device_info", {})
        if isinstance(device_info, dict) and key in device_info:
            return device_info.get(key)

        # Fallback to raw payload data
        if "payload" in self.coordinator.data:
            payload = self.coordinator.data["payload"]
            # Handle both dict and list payload formats
            if isinstance(payload, dict):
                return payload.get(key)
            elif isinstance(payload, list):
                # For list payloads, search through items for the key
                for item in payload:
                    if isinstance(item, dict) and key in item:
                        return item.get(key)

        return None

    def _get_firmware_version(self) -> str:
        """Get firmware version based on device type."""
        if self.coordinator.device_type == "charger":
            # For charger devices, use appFirmVer
            app_version = self._get_device_info_value("app_firmware_version")
            if app_version:
                return str(app_version)
        elif self.coordinator.device_type == "energy_storage":
            # For energy storage devices, use protocolVer
            protocol_version = self._get_device_info_value("protocol_version")
            if protocol_version:
                return str(protocol_version)

        # Fallback to "Unknown" if no version available
        return "Unknown"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Connection sensor should always be available to show connection status
        if self._sensor_key == "connection":
            return True
        return self.coordinator.connected and super().available

    @property
    def is_on(self) -> bool | None:
        """Return True if the binary sensor is on."""
        if self._sensor_key == "charging":
            charge_status = self._get_device_info_value("chargeStatus")
            return charge_status == 1  # 1: charging
        if self._sensor_key == "gun_connected":
            gun_status = self._get_device_info_value("gunStatus")
            return gun_status == 1  # 1: plug in
        if self._sensor_key == "gun_locked":
            gun_lock = self._get_device_info_value("gunLock")
            return gun_lock == 1  # 1: lock
        if self._sensor_key == "nfc_enabled":
            nfc_enable = self._get_device_info_value("nfcEnable")
            return nfc_enable == 0  # 0: enable
        if self._sensor_key == "connection":
            return self.coordinator.connected
        if self._sensor_key == "error":
            err_code = self._get_device_info_value("errCode")
            return bool(err_code and len(err_code) > 0)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self._sensor_key == "error":
            err_code = self._get_device_info_value("errCode")
            if err_code and len(err_code) > 0:
                return {
                    "error_codes": err_code,
                    "error_count": len(err_code),
                }
        return None
