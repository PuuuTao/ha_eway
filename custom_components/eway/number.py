"""Number platform for Eway Energy Storage."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
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
    """Set up the number platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Only set up storage power control for energy storage devices
    if coordinator.device_type != "energy_storage":
        _LOGGER.debug(
            "Skipping storage power control for device type: %s",
            coordinator.device_type,
        )
        return

    entities = [
        EwayStoragePowerNumber(coordinator),
    ]

    async_add_entities(entities)


class EwayStoragePowerNumber(CoordinatorEntity, NumberEntity):
    """Number entity for Eway Energy Storage power control."""

    def __init__(self, coordinator: EwayChargerCoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_sn}_storage_power_control"
        self._attr_name = f"Energy Storage {coordinator.device_sn} Power Control"
        self._attr_icon = "mdi:lightning-bolt"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 800
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "W"
        self._attr_mode = "slider"
        self._attr_device_class = NumberDeviceClass.POWER

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information."""
        # For energy storage devices, use device serial number as identifier
        device_identifier = self.coordinator.device_sn or ""
        device_name = get_device_name(
            self.coordinator.device_type, self.coordinator.device_sn or ""
        )

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
        """Get firmware version for energy storage device."""
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

    async def async_added_to_hass(self) -> None:
        """Call when entity is added to Home Assistant."""
        await super().async_added_to_hass()

        # Request device info when the entity is first loaded
        try:
            _LOGGER.info(
                "Requesting storage device info for power control initialization"
            )
            storage_info = await self.coordinator.async_get_storage_info()

            if storage_info:
                work_mode = storage_info.get("workMode")
                constant_power = storage_info.get("constantPower", 0)

                _LOGGER.info(
                    "Retrieved storage info: workMode=%s, constantPower=%s",
                    work_mode,
                    constant_power,
                )

                # Only update the slider if workMode is "0"
                if work_mode == "0":
                    _LOGGER.info(
                        "WorkMode is '0', setting slider to constantPower value: %s",
                        constant_power,
                    )
                    # Store the value in coordinator data for the slider to read
                    if not self.coordinator.data:
                        self.coordinator.data = {}
                    if "storage_info" not in self.coordinator.data:
                        self.coordinator.data["storage_info"] = {}

                    self.coordinator.data["storage_info"]["constant_power"] = (
                        constant_power
                    )
                    self.coordinator.async_set_updated_data(self.coordinator.data)
                else:
                    _LOGGER.info(
                        "WorkMode is not '0' (current: %s), keeping slider at default value",
                        work_mode,
                    )
            else:
                _LOGGER.warning("Failed to retrieve storage device info")

        except (ConnectionError, ValueError, OSError) as exc:
            _LOGGER.error(
                "Failed to get storage device info during initialization: %s", exc
            )

    @property
    def native_value(self) -> float | None:
        """Return the current power value."""
        # Try to get current power setting from storage_info
        if not self.coordinator.data:
            return 0.0

        # First try to get from storage_info (from device info response)
        storage_info = self.coordinator.data.get("storage_info", {})
        current_power = storage_info.get("constant_power")

        if current_power is not None:
            return float(current_power)

        # Fallback to storage_data (from mini data)
        storage_data = self.coordinator.data.get("storage_data", {})
        current_power = storage_data.get("constantPower")

        if current_power is not None:
            return float(current_power)

        # Default to 0 if no value available
        return 0.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the power value."""
        try:
            power_value = int(value)
            await self.coordinator.async_set_storage_power(power_value)
            _LOGGER.info(
                "Set storage power to %d W for device %s",
                power_value,
                self.coordinator.device_sn,
            )

            # Update the local value immediately for better UI responsiveness
            if not self.coordinator.data:
                self.coordinator.data = {}
            if "storage_info" not in self.coordinator.data:
                self.coordinator.data["storage_info"] = {}

            self.coordinator.data["storage_info"]["constant_power"] = power_value
            self.coordinator.async_set_updated_data(self.coordinator.data)

        except (ConnectionError, ValueError, OSError) as exc:
            _LOGGER.error("Failed to set storage power: %s", exc)
            raise
