"""Switch platform for Eway Charger."""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, get_device_model, get_device_name
from .coordinator import EwayChargerCoordinator
from .ct_coordinator import EwayCTCoordinator
from .smart_plug_coordinator import EwaySmartPlugCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    # Set up charger switch for charger devices
    if coordinator.device_type == "charger":
        entities.append(EwayChargerSwitch(coordinator))
        _LOGGER.debug("Added charger switch for device type: %s", coordinator.device_type)

    # Set up CT anti-backflow switch for CT devices
    elif coordinator.device_type == "ct":
        entities.append(EwayCTAntiBackflowSwitch(coordinator))
        _LOGGER.debug("Added CT anti-backflow switch for device type: %s", coordinator.device_type)

    # Set up smart plug switch for smart plug devices
    elif coordinator.device_type == "smart_plug":
        entities.append(EwaySmartPlugSwitch(coordinator))
        _LOGGER.debug("Added smart plug switch for device type: %s", coordinator.device_type)

    else:
        _LOGGER.debug(
            "No switches available for device type: %s", coordinator.device_type
        )
        return

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
    def device_info(self) -> DeviceInfo | None:
        """Return device information."""
        # For energy storage devices, use device serial number as identifier if device_id is empty
        # For charger devices, use device_id as usual
        if (
            self.coordinator.device_type == "energy_storage"
            and not self.coordinator.device_id
        ):
            device_identifier = self.coordinator.device_sn or ""
            device_name = get_device_name(
                self.coordinator.device_type, self.coordinator.device_sn or ""
            )
        else:
            device_identifier = self.coordinator.device_id
            device_name = get_device_name(
                self.coordinator.device_type, self.coordinator.device_id
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
        except (ConnectionError, ValueError, OSError) as exc:
            _LOGGER.error("Failed to start charging: %s", exc)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            await self.coordinator.async_stop_charging()
            _LOGGER.info("Stopped charging for device %s", self.coordinator.device_id)
        except (ConnectionError, ValueError, OSError) as exc:
            _LOGGER.error("Failed to stop charging: %s", exc)
            raise


class EwayCTAntiBackflowSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity for CT Device Anti-backflow."""

    def __init__(self, coordinator: EwayCTCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_sn or coordinator.host}_anti_backflow_switch"
        self._attr_translation_key = "anti_backflow"
        self._attr_icon = "mdi:arrow-left-bold"
        self._last_operation_time = 0
        self._operation_cooldown = 2.0  # 2 seconds cooldown between operations

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information."""
        # Use consistent device identifier with CT coordinator
        device_identifier = self.coordinator.device_sn or self.coordinator.host
        device_name = get_device_name("ct", device_identifier)

        return {
            "identifiers": {(DOMAIN, device_identifier)},
            "name": device_name,
            "manufacturer": MANUFACTURER,
            "model": get_device_model("ct"),
            "sw_version": self._get_firmware_version(),
            "serial_number": self.coordinator.device_sn,
        }

    def _get_firmware_version(self) -> str:
        """Get firmware version from CT coordinator data."""
        if not self.coordinator.data:
            return "Unknown"
        return str(self.coordinator.data.get("calibration", "Unknown"))

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.connected and super().available

    @property
    def is_on(self) -> bool:
        """Return True if anti-backflow is enabled."""
        anti_backflow_status = self.coordinator.get_anti_backflow_status()
        if anti_backflow_status is None:
            # Default to False when status is unknown
            return False
        return anti_backflow_status

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the anti-backflow switch on (enable anti-backflow)."""
        current_time = time.time()
        if current_time - self._last_operation_time < self._operation_cooldown:
            _LOGGER.warning(
                "Anti-backflow operation ignored due to cooldown (%.1fs remaining)",
                self._operation_cooldown - (current_time - self._last_operation_time)
            )
            return

        self._last_operation_time = current_time

        try:
            success = await self.coordinator.async_set_anti_backflow(True)
            if success:
                _LOGGER.info(
                    "Enabled anti-backflow for CT device %s",
                    self.coordinator.device_sn or self.coordinator.host
                )
                # State is already updated in async_set_anti_backflow, no need to refresh
                self.async_write_ha_state()
            else:
                _LOGGER.error(
                    "Failed to enable anti-backflow for CT device %s",
                    self.coordinator.device_sn or self.coordinator.host
                )
                raise ValueError("Failed to enable anti-backflow")
        except Exception as exc:
            _LOGGER.error("Failed to enable anti-backflow: %s", exc)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the anti-backflow switch off (disable anti-backflow)."""
        current_time = time.time()
        if current_time - self._last_operation_time < self._operation_cooldown:
            _LOGGER.warning(
                "Anti-backflow operation ignored due to cooldown (%.1fs remaining)",
                self._operation_cooldown - (current_time - self._last_operation_time)
            )
            return

        self._last_operation_time = current_time

        try:
            success = await self.coordinator.async_set_anti_backflow(False)
            if success:
                _LOGGER.info(
                    "Disabled anti-backflow for CT device %s",
                    self.coordinator.device_sn or self.coordinator.host
                )
                # State is already updated in async_set_anti_backflow, no need to refresh
                self.async_write_ha_state()
            else:
                _LOGGER.error(
                    "Failed to disable anti-backflow for CT device %s",
                    self.coordinator.device_sn or self.coordinator.host
                )
                raise ValueError("Failed to disable anti-backflow")
        except Exception as exc:
            _LOGGER.error("Failed to disable anti-backflow: %s", exc)
            raise


class EwaySmartPlugSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity for Eway Smart Plug."""

    def __init__(self, coordinator: EwaySmartPlugCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{coordinator.device_sn}_smart_plug_switch"
        self._attr_translation_key = "smart_plug_switch"
        self._attr_icon = "mdi:power-socket"

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.device_sn)},
            "manufacturer": MANUFACTURER,
            "model": get_device_model("smart_plug"),
            "sw_version": None,
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        if self.coordinator.data:
            switch_state = self.coordinator.data.get("switch_state")
            if switch_state is not None:
                return bool(switch_state)
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            success = await self.coordinator.async_set_switch_state(True)
            if success:
                _LOGGER.info("Turned on smart plug %s", self.coordinator.device_id)
                # Request immediate update to reflect the change
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to turn on smart plug %s", self.coordinator.device_id)
                raise ValueError("Failed to turn on smart plug")
        except Exception as exc:
            _LOGGER.error("Failed to turn on smart plug: %s", exc)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            success = await self.coordinator.async_set_switch_state(False)
            if success:
                _LOGGER.info("Turned off smart plug %s", self.coordinator.device_id)
                # Request immediate update to reflect the change
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to turn off smart plug %s", self.coordinator.device_id)
                raise ValueError("Failed to turn off smart plug")
        except Exception as exc:
            _LOGGER.error("Failed to turn off smart plug: %s", exc)
            raise
