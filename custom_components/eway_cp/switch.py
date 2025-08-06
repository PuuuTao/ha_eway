"""Switch platform for Eway Charger."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, get_device_model, get_device_name
from .coordinator import EwayChargerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Only set up charger switch for charger devices
    if coordinator.device_type != "charger":
        _LOGGER.debug("Skipping charger switch for device type: %s", coordinator.device_type)
        return

    # Only set up charger switches for charger devices
    device_type = config_entry.data.get("device_type", "charger")
    if device_type != "charger":
        # Skip charger switches for non-charger devices
        return

    entities = [
        EwayChargerSwitch(coordinator),
    ]

    async_add_entities(entities)


class EwayChargerSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity for Eway Charger."""

    def __init__(self, coordinator: EwayChargerCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_charging_switch"
        self._attr_name = f"Eway Charger {coordinator.device_id} Charging"
        self._attr_icon = "mdi:ev-station"

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
        if not self.coordinator.data or "device_info" not in self.coordinator.data:
            return None
        return self.coordinator.data["device_info"].get(key)

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
        return self.coordinator.connected and super().available

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        # Check charging status from coordinator data
        charging_status = self.coordinator.data.get("charging_status")
        if charging_status == "charging":
            return True
        if charging_status in ["stopped", "completed"]:
            return False

        # Fallback to device info charge status
        device_info = self.coordinator.data.get("device_info", {})
        charge_status = device_info.get("charge_status")
        if charge_status == 1:  # 1 = charging
            return True
        if charge_status in [0, 2]:  # 0 = not charging, 2 = completed
            return False

        # Default to False (not charging) when status is unknown
        # This ensures the switch always shows as a switch, not buttons
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            await self.coordinator.async_start_charging()
            _LOGGER.info("Started charging for device %s", self.coordinator.device_id)
        except Exception as exc:
            _LOGGER.error("Failed to start charging: %s", exc)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            await self.coordinator.async_stop_charging()
            _LOGGER.info("Stopped charging for device %s", self.coordinator.device_id)
        except Exception as exc:
            _LOGGER.error("Failed to stop charging: %s", exc)
            raise
