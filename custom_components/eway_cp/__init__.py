"""The Eway Charger integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import CONF_DEVICE_ID, CONF_DEVICE_SN, CONF_HOST, CONF_PORT, DOMAIN
from .coordinator import EwayChargerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Eway Charger component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eway Charger from a config entry."""
    # Check if this is an auto-discovery setup
    auto_discover = entry.data.get("auto_discover", False)
    device_type = entry.data.get("device_type", "charger")

    if auto_discover:
        # Initialize coordinator with auto-discovery enabled
        coordinator = EwayChargerCoordinator(
            hass,
            host=entry.data.get(CONF_HOST),
            port=entry.data.get(CONF_PORT),
            device_id=entry.data.get(CONF_DEVICE_ID),
            device_sn=entry.data.get(CONF_DEVICE_SN),
            auto_discover=True,
            device_type=device_type,
        )
    else:
        # Initialize coordinator with manual configuration
        coordinator = EwayChargerCoordinator(
            hass,
            host=entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],
            device_id=entry.data.get(CONF_DEVICE_ID),
            device_sn=entry.data.get(CONF_DEVICE_SN),
            auto_discover=False,
            device_type=device_type,
        )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.warning("🔋 Device type: %s", coordinator.device_type)
    _LOGGER.warning("🔋 Standard platforms setup completed for device type: %s", coordinator.device_type)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Unload standard platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
