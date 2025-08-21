"""Config flow for Eway Charger integration."""

from __future__ import annotations

from collections import OrderedDict
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .binary_sensor import BINARY_SENSOR_CONFIGS
from .const import CONF_DEVICE_ID, CONF_DEVICE_SN, DOMAIN
from .coordinator import (
    EwayChargerCoordinator,
    EwayCTCoordinator,
    EwaySmartPlugCoordinator,
)
from .sensor import SENSOR_CONFIGS, SMART_PLUG_SENSOR_CONFIGS, STORAGE_SENSOR_CONFIGS
from .websocket_client import EwayWebSocketClient

_LOGGER = logging.getLogger(__name__)

DISCOVERED_DEVICES: list[dict[str, Any]] = []

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_DEVICE_ID, default=""): str,
        vol.Optional(CONF_DEVICE_SN, default=""): str,
    }
)

STEP_ENERGY_STORAGE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(
            CONF_DEVICE_SN
        ): str,  # Energy storage only needs SN, port is fixed to 80
    }
)

STEP_CT_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_DEVICE_SN, default=""): str,  # CT device SN is optional
    }
)

STEP_SMART_PLUG_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(
            CONF_DEVICE_SN, default=""
        ): str,  # Smart plug device SN is optional
    }
)

STEP_DISCOVERY_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("device"): str,
        vol.Optional(CONF_DEVICE_ID, default=""): str,
        vol.Optional(CONF_DEVICE_SN, default=""): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    client = EwayWebSocketClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        device_id=data.get(CONF_DEVICE_ID, ""),
        device_sn=data.get(CONF_DEVICE_SN, ""),
    )

    try:
        # Test connection
        await client.connect()
        await client.disconnect()
    except (ConnectionError, OSError, TimeoutError) as exc:
        _LOGGER.error("Failed to connect to Eway Charger: %s", exc)
        raise CannotConnect from exc

    # Return info that you want to store in the config entry.
    return {"title": f"Eway Charger ({data[CONF_HOST]})"}


async def validate_energy_storage_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the energy storage input allows us to connect.

    Data has the keys from STEP_ENERGY_STORAGE_DATA_SCHEMA with values provided by the user.
    """
    client = EwayWebSocketClient(
        host=data[CONF_HOST],
        port=80,  # Energy storage devices use fixed port 80
        device_id="",  # Energy storage devices don't have device_id
        device_sn=data[CONF_DEVICE_SN],
    )

    try:
        # Test connection
        await client.connect()
        await client.disconnect()
    except (ConnectionError, OSError, TimeoutError) as exc:
        _LOGGER.error("Failed to connect to Eway Energy Storage: %s", exc)
        raise CannotConnect from exc

    # Return info that you want to store in the config entry.
    return {"title": f"Eway Energy Storage ({data[CONF_HOST]})"}


async def validate_ct_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the CT device input allows us to connect.

    Data has the keys from STEP_CT_DATA_SCHEMA with values provided by the user.
    """

    def _raise_cannot_connect(exc: Exception | None = None) -> None:
        """Raise CannotConnect consistently."""
        if exc is None:
            raise CannotConnect("Failed to connect to CT device")
        raise CannotConnect from exc

    coordinator = EwayCTCoordinator(
        hass=hass,
        host=data[CONF_HOST],
        device_sn=data.get(CONF_DEVICE_SN, ""),
    )

    try:
        # Test connection
        if not await coordinator.test_connection():
            _raise_cannot_connect()
    except Exception as exc:
        _LOGGER.error("Failed to connect to Eway CT Device: %s", exc)
        raise CannotConnect from exc
    finally:
        await coordinator.async_shutdown()

    # Return info that you want to store in the config entry.
    return {"title": f"Eway CT Device ({data[CONF_HOST]})"}


async def validate_smart_plug_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the smart plug device input allows us to connect.

    Data has the keys from STEP_SMART_PLUG_DATA_SCHEMA with values provided by the user.
    """

    def _raise_cannot_connect(exc: Exception | None = None) -> None:
        """Raise a CannotConnect exception consistently."""
        if exc is None:
            raise CannotConnect("Failed to connect to Smart Plug device")
        raise CannotConnect from exc

    coordinator = EwaySmartPlugCoordinator(
        hass=hass,
        host=data[CONF_HOST],
        device_sn=data.get(CONF_DEVICE_SN, ""),
    )

    try:
        # Test connection
        if not await coordinator.test_connection():
            _raise_cannot_connect()
    except Exception as exc:
        _LOGGER.error("Failed to connect to Eway Smart Plug Device: %s", exc)
        raise CannotConnect from exc
    finally:
        await coordinator.async_shutdown()

    # Return info that you want to store in the config entry.
    return {"title": f"Eway Smart Plug ({data[CONF_HOST]})"}


class EwayConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Eway Charger."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return EwayOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._discovery_info: dict[str, Any] = {}

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> config_entries.ConfigFlowResult:
        """Handle zeroconf discovery."""
        _LOGGER.warning(
            "🎯 ZEROCONF method called! Discovered device: %s", discovery_info
        )
        # Extract device information from discovery_info
        host = discovery_info.host
        port = discovery_info.port
        name = discovery_info.name
        props = discovery_info.properties  # Note: this is a bytes-to-str dict

        _LOGGER.debug(
            "Zeroconf discovery: host=%s, port=%s, name=%s, props=%s",
            host,
            port,
            name,
            props,
        )

        if not host or not name:
            _LOGGER.warning("❌ Zeroconf discovery info incomplete: %s", discovery_info)
            return self.async_abort(reason="incomplete_discovery_info")

        # Check if it's an Eway device (charger, energy storage, CT, or smart plug)
        if not name.startswith(
            ("EwayCS-TFT", "EwayEnergyStorage", "EwayCT", "EwayPlug")
        ):
            _LOGGER.warning("Skipping non-Eway device: %s", name)
            return self.async_abort(reason="not_eway_device")

        # Parse device ID, SN and device type
        device_id = "unknown"
        device_sn = "unknown"
        device_type = "unknown"

        try:
            # Parse device name format
            if "._http._tcp.local." in name:
                name_part = name.replace("._http._tcp.local.", "")
            else:
                name_part = name

            if name_part.startswith("EwayCS-TFT-"):
                # Charger device: EwayCS-TFT-{device_id}_{device_sn}
                remaining = name_part[len("EwayCS-TFT-") :]
                if "_" in remaining:
                    device_id, device_sn = remaining.split("_", 1)
                    device_id = device_id.strip()
                    device_sn = device_sn.strip()
                device_type = "charger"
            elif name_part.startswith("EwayEnergyStorage-"):
                # Energy storage device: EwayEnergyStorage-{sn}
                remaining = name_part[len("EwayEnergyStorage-") :]
                device_sn = remaining.strip()
                device_id = ""  # Energy storage devices don't have device_id
                device_type = "energy_storage"
            elif name_part.startswith("EwayCT-"):
                # CT device: EwayCT-{sn}
                remaining = name_part[len("EwayCT-") :]
                device_sn = remaining.strip()
                device_id = ""  # CT devices don't have device_id
                device_type = "ct"
            elif name_part.startswith("EwayPlug-"):
                # Smart plug device: EwayPlug-{sn}
                remaining = name_part[len("EwayPlug-") :]
                device_sn = remaining.strip()
                device_id = ""  # Smart plug devices don't have device_id
                device_type = "smart_plug"
        except (ValueError, AttributeError, IndexError) as exc:
            _LOGGER.warning("Failed to parse device name: %s", exc)

        # Create unique identifier for duplicate checking
        unique_id = f"{host}_{port}_{device_id}"

        # Check if this device is already configured
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})

        # Store discovery information
        self._discovery_info = {
            "host": host,
            "port": port,
            "name": name,
            "device_id": device_id,
            "device_sn": device_sn,
            "device_type": device_type,
        }

        # Set context
        self.context["title_placeholders"] = {
            "name": name,
            "host": host,
            "port": port,
        }

        _LOGGER.warning(
            "✅ Discovered Eway device (%s): %s (%s:%d)", device_type, name, host, port
        )

        # Filter duplicate devices (same host)
        if any(
            dev["host"] == host and dev["port"] == port for dev in DISCOVERED_DEVICES
        ):
            return self.async_abort(reason="already_discovered")

        _LOGGER.info(
            "✅ Discovered device, showing in Home Assistant Discovered: %s", name
        )

        # Save device information to cache for manual selection option
        if not any(
            dev["host"] == host and dev["port"] == port for dev in DISCOVERED_DEVICES
        ):
            DISCOVERED_DEVICES.append(
                {
                    "host": host,
                    "port": port,
                    "name": name,
                    "device_id": device_id,
                    "device_sn": device_sn,
                    "device_type": device_type,
                }
            )

        # Show the device in Home Assistant's Discovered page
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle a confirmation flow initiated by zeroconf."""
        device_type = self._discovery_info.get("device_type", "unknown")
        _LOGGER.warning(
            "✅ Discovered Eway %s device, proceeding to next step", device_type
        )
        if user_input is not None:
            # User confirmed adding device
            # Use different ports based on device type
            if self._discovery_info["device_type"] == "energy_storage":
                port = 80  # Energy storage devices use port 80
            elif self._discovery_info["device_type"] == "ct":
                port = 80  # CT devices use port 80
            elif self._discovery_info["device_type"] == "smart_plug":
                port = 80  # Smart plug devices use port 80
            else:
                port = 8888  # Charger devices use port 8888
            # Prepare config data based on device type
            if self._discovery_info["device_type"] in [
                "energy_storage",
                "ct",
                "smart_plug",
            ]:
                # Energy storage and CT devices don't use device ID
                config_data = {
                    CONF_HOST: self._discovery_info["host"],
                    CONF_PORT: port,
                    CONF_DEVICE_ID: "",  # These devices don't have device ID
                    CONF_DEVICE_SN: user_input.get(
                        CONF_DEVICE_SN, self._discovery_info["device_sn"]
                    ),
                    "device_type": self._discovery_info["device_type"],
                    "auto_discover": True,
                }
            else:
                # Charger devices use both device ID and SN
                config_data = {
                    CONF_HOST: self._discovery_info["host"],
                    CONF_PORT: port,
                    CONF_DEVICE_ID: user_input.get(
                        CONF_DEVICE_ID, self._discovery_info["device_id"]
                    ),
                    CONF_DEVICE_SN: user_input.get(
                        CONF_DEVICE_SN, self._discovery_info["device_sn"]
                    ),
                    "device_type": self._discovery_info["device_type"],
                    "auto_discover": True,
                }

            try:
                # Validate connection based on device type
                if self._discovery_info["device_type"] == "energy_storage":
                    _ = await validate_energy_storage_input(self.hass, config_data)
                elif self._discovery_info["device_type"] == "ct":
                    _ = await validate_ct_input(self.hass, config_data)
                elif self._discovery_info["device_type"] == "smart_plug":
                    _ = await validate_smart_plug_input(self.hass, config_data)
                else:
                    _ = await validate_input(self.hass, config_data)
                _LOGGER.warning("✅ Zeroconf device validation successful")

                device_type_name = (
                    "Charger"
                    if self._discovery_info["device_type"] == "charger"
                    else "Energy Storage"
                    if self._discovery_info["device_type"] == "energy_storage"
                    else "CT"
                    if self._discovery_info["device_type"] == "ct"
                    else "Smart Plug"
                )
                return self.async_create_entry(
                    title=f"Eway {device_type_name} ({self._discovery_info['name']})",
                    data=config_data,
                )
            except CannotConnect:
                _LOGGER.warning("❌ Cannot connect to Zeroconf discovered device")
                return self.async_abort(reason="cannot_connect")
            except Exception:
                _LOGGER.exception(
                    "❌ Exception occurred while validating Zeroconf device"
                )
                return self.async_abort(reason="unknown")

        # Show confirmation form - different schema based on device type
        if self._discovery_info["device_type"] in [
            "energy_storage",
            "ct",
            "smart_plug",
        ]:
            # Energy storage and CT devices don't need device ID
            discovery_schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_DEVICE_SN,
                        default=self._discovery_info.get("device_sn", ""),
                    ): str,
                }
            )
        else:
            # Charger devices need both device ID and SN
            discovery_schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_DEVICE_ID,
                        default=self._discovery_info.get("device_id", ""),
                    ): str,
                    vol.Optional(
                        CONF_DEVICE_SN,
                        default=self._discovery_info.get("device_sn", ""),
                    ): str,
                }
            )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=discovery_schema,
            description_placeholders={
                "name": self._discovery_info["name"],
                "host": self._discovery_info["host"],
                "port": self._discovery_info["port"],
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step - device type selection."""
        if user_input is not None:
            if user_input["device_type"] == "charger":
                return await self.async_step_charger()
            if user_input["device_type"] == "energy_storage":
                return await self.async_step_energy_storage()
            if user_input["device_type"] == "ct":
                return await self.async_step_ct()
            if user_input["device_type"] == "smart_plug":
                return await self.async_step_smart_plug()

        # Show device type selection form
        device_type_schema = vol.Schema(
            {
                vol.Required("device_type"): vol.In(
                    ["charger", "energy_storage", "ct", "smart_plug"]
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=device_type_schema,
            description_placeholders={},
        )

    async def async_step_charger(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle charger configuration step - choose configuration method."""
        if user_input is not None:
            config_method = user_input.get("config_method", "")

            if config_method == "manual":
                return await self.async_step_manual()
            if config_method == "discovered":
                return await self.async_step_discovery()

        # Prepare configuration method options
        config_method_options = ["manual"]
        if DISCOVERED_DEVICES:
            config_method_options.append("discovered")

        # Build form schema
        data_schema = vol.Schema(
            {
                vol.Required("config_method"): vol.In(config_method_options),
            }
        )

        return self.async_show_form(
            step_id="charger",
            data_schema=data_schema,
            description_placeholders={},
        )

    async def async_step_discovery(
        self, discovery_info: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle discovered devices selection."""
        if discovery_info is not None:
            selected_device = discovery_info.get("discovered_device", "")

            # Find the selected device
            for dev in DISCOVERED_DEVICES:
                key = f"{dev['host']}:{dev['port']}"
                if selected_device == key:
                    self._discovery_info = dev
                    return await self.async_step_zeroconf_confirm()

            return self.async_abort(reason="device_not_found")

        # Filter devices based on current context (charger only)
        charger_devices = [
            dev for dev in DISCOVERED_DEVICES if dev.get("device_type") == "charger"
        ]

        # Check if there are discovered charger devices
        if not charger_devices:
            return self.async_abort(reason="no_devices_found")

        # Prepare discovered device options (charger only)
        discovered_device_options = OrderedDict()

        for dev in charger_devices:
            key = f"{dev['host']}:{dev['port']}"

            # Extract the main part of device name
            device_name = dev["name"]
            if "._http._tcp.local." in device_name:
                device_name = device_name.replace("._http._tcp.local.", "")

            # Determine device type and format display name
            device_type = dev.get("device_type", "unknown")
            if device_type == "charger":
                # For charger: show the part before first underscore
                if "_" in device_name:
                    display_name = device_name.split("_")[0]
                else:
                    display_name = device_name
                label = f"Charger: {display_name}"
            elif device_type == "energy_storage":
                # For energy storage: show the full name
                label = f"Energy Storage: {device_name}"
            else:
                # Fallback for unknown types
                label = device_name

            discovered_device_options[key] = label

        # Build form schema
        data_schema = vol.Schema(
            {
                vol.Required("discovered_device"): vol.In(discovered_device_options),
            }
        )

        return self.async_show_form(
            step_id="discovery",
            data_schema=data_schema,
            description_placeholders={},
        )

    async def async_step_energy_storage(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle energy storage configuration step - choose configuration method."""
        if user_input is not None:
            config_method = user_input.get("config_method", "")

            if config_method == "manual":
                return await self.async_step_manual_energy_storage()
            if config_method == "discovered":
                return await self.async_step_discovery_energy_storage()

        # Prepare configuration method options
        config_method_options = ["manual"]
        # Check if there are any discovered energy storage devices
        energy_storage_devices = [
            dev
            for dev in DISCOVERED_DEVICES
            if dev.get("device_type") == "energy_storage"
        ]
        if energy_storage_devices:
            config_method_options.append("discovered")

        # Build form schema
        data_schema = vol.Schema(
            {
                vol.Required("config_method"): vol.In(config_method_options),
            }
        )

        return self.async_show_form(
            step_id="energy_storage",
            data_schema=data_schema,
            description_placeholders={},
        )

    async def async_step_ct(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle CT configuration step - choose configuration method."""
        if user_input is not None:
            config_method = user_input.get("config_method", "")

            if config_method == "manual":
                return await self.async_step_manual_ct()
            if config_method == "discovered":
                return await self.async_step_discovery_ct()

        # Prepare configuration method options
        config_method_options = ["manual"]
        # Check if there are any discovered CT devices
        ct_devices = [
            dev for dev in DISCOVERED_DEVICES if dev.get("device_type") == "ct"
        ]
        if ct_devices:
            config_method_options.append("discovered")

        # Build form schema
        data_schema = vol.Schema(
            {
                vol.Required("config_method"): vol.In(config_method_options),
            }
        )

        return self.async_show_form(
            step_id="ct",
            data_schema=data_schema,
            description_placeholders={},
        )

        # if user_input is not None:
        #     # User made a selection, redirect to the chosen step
        #     if user_input["config_method"] == "manual":
        #         return await self.async_step_manual()
        #     elif user_input["config_method"] == "discovery":
        #         return await self.async_step_zeroconf_confirm()
        #         #return await self.async_step_wait_for_discovery()

        # # Show form to choose between manual config and auto discovery
        # config_method_schema = vol.Schema({
        #     vol.Required("config_method", default="discovery"): vol.In({
        #         "manual": "Manual Configuration",
        #         "discovery": "Device Discovery"
        #     })
        # })

        # return self.async_show_form(
        #     step_id="user",
        #     data_schema=config_method_schema,
        #     description_placeholders={}
        # )

    async def async_step_wait_for_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Inform user to power on device and wait for discovery."""
        return self.async_show_form(
            step_id="wait_for_discovery",
            description_placeholders={
                "info": "Please power on your device. It will appear automatically when discovered on the network."
            },
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle manual configuration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                # Add device_type and fixed port to the data
                user_input["device_type"] = "charger"
                user_input[CONF_PORT] = 8888  # Charger devices use fixed port 8888
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="manual", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_manual_energy_storage(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle manual energy storage configuration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                # Add device_type and fixed port to the data
                user_input["device_type"] = "energy_storage"
                user_input[CONF_PORT] = 80  # Energy storage devices use fixed port 80
                info = await validate_energy_storage_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="manual_energy_storage",
            data_schema=STEP_ENERGY_STORAGE_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_discovery_energy_storage(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle discovered energy storage devices selection."""
        if user_input is not None:
            selected_device = user_input.get("discovered_device", "")

            # Find the selected device
            for dev in DISCOVERED_DEVICES:
                key = f"{dev['host']}:{dev['port']}"
                if selected_device == key:
                    self._discovery_info = dev
                    return await self.async_step_zeroconf_confirm()

            return self.async_abort(reason="device_not_found")

        # Filter devices based on current context (energy storage only)
        storage_devices = [
            dev
            for dev in DISCOVERED_DEVICES
            if dev.get("device_type") == "energy_storage"
        ]

        # Check if there are discovered storage devices
        if not storage_devices:
            return self.async_abort(reason="no_devices_found")

        # Prepare discovered device options (energy storage only)
        discovered_device_options = OrderedDict()

        for dev in storage_devices:
            key = f"{dev['host']}:{dev['port']}"

            # Extract the main part of device name
            device_name = dev["name"]
            if "._http._tcp.local." in device_name:
                device_name = device_name.replace("._http._tcp.local.", "")

            # For energy storage: show the full name
            label = f"Energy Storage: {device_name}"

            discovered_device_options[key] = label

        # Build form schema
        data_schema = vol.Schema(
            {
                vol.Required("discovered_device"): vol.In(discovered_device_options),
            }
        )

        return self.async_show_form(
            step_id="discovery_energy_storage",
            data_schema=data_schema,
            description_placeholders={},
        )

    async def async_step_manual_ct(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle manual CT configuration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                # Add device_type and device_id to the data
                user_input["device_type"] = "ct"
                user_input[CONF_DEVICE_ID] = ""  # CT devices don't have device_id
                info = await validate_ct_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="manual_ct",
            data_schema=STEP_CT_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_smart_plug(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle smart plug configuration step - choose configuration method."""
        if user_input is not None:
            config_method = user_input.get("config_method", "")

            if config_method == "manual":
                return await self.async_step_manual_smart_plug()
            if config_method == "discovered":
                return await self.async_step_discovery_smart_plug()

        # Prepare configuration method options
        config_method_options = ["manual"]
        # Check if there are any discovered smart plug devices
        smart_plug_devices = [
            dev for dev in DISCOVERED_DEVICES if dev.get("device_type") == "smart_plug"
        ]
        if smart_plug_devices:
            config_method_options.append("discovered")

        # Build form schema
        data_schema = vol.Schema(
            {
                vol.Required("config_method"): vol.In(config_method_options),
            }
        )

        return self.async_show_form(
            step_id="smart_plug",
            data_schema=data_schema,
            description_placeholders={},
        )

    async def async_step_manual_smart_plug(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle manual smart plug configuration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                # Add device_type and device_id to the data
                user_input["device_type"] = "smart_plug"
                user_input[CONF_DEVICE_ID] = (
                    ""  # Smart plug devices don't have device_id
                )
                info = await validate_smart_plug_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="manual_smart_plug",
            data_schema=STEP_SMART_PLUG_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_discovery_smart_plug(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle discovered smart plug devices selection."""
        if user_input is not None:
            selected_device = user_input.get("discovered_device", "")

            # Find the selected device
            for dev in DISCOVERED_DEVICES:
                key = f"{dev['host']}:{dev['port']}"
                if selected_device == key:
                    self._discovery_info = dev
                    return await self.async_step_zeroconf_confirm()

            return self.async_abort(reason="device_not_found")

        # Filter devices based on current context (smart plug only)
        smart_plug_devices = [
            dev for dev in DISCOVERED_DEVICES if dev.get("device_type") == "smart_plug"
        ]

        # Check if there are discovered smart plug devices
        if not smart_plug_devices:
            return self.async_abort(reason="no_devices_found")

        # Prepare discovered device options (smart plug only)
        discovered_device_options = OrderedDict()

        for dev in smart_plug_devices:
            key = f"{dev['host']}:{dev['port']}"

            # Extract the main part of device name
            device_name = dev["name"]
            if "._http._tcp.local." in device_name:
                device_name = device_name.replace("._http._tcp.local.", "")

            # For smart plug: show the full name
            label = f"Smart Plug: {device_name}"
            discovered_device_options[key] = label

        # Build form schema
        data_schema = vol.Schema(
            {
                vol.Required("discovered_device"): vol.In(discovered_device_options),
            }
        )

        return self.async_show_form(
            step_id="discovery_smart_plug",
            data_schema=data_schema,
            description_placeholders={},
        )

    async def async_step_discovery_ct(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle discovered CT devices selection."""
        if user_input is not None:
            selected_device = user_input.get("discovered_device", "")

            # Find the selected device
            for dev in DISCOVERED_DEVICES:
                key = f"{dev['host']}:{dev['port']}"
                if selected_device == key:
                    self._discovery_info = dev
                    return await self.async_step_zeroconf_confirm()

            return self.async_abort(reason="device_not_found")

        # Filter devices based on current context (CT only)
        ct_devices = [
            dev for dev in DISCOVERED_DEVICES if dev.get("device_type") == "ct"
        ]

        # Check if there are discovered CT devices
        if not ct_devices:
            return self.async_abort(reason="no_devices_found")

        # Prepare discovered device options (CT only)
        discovered_device_options = OrderedDict()

        for dev in ct_devices:
            key = f"{dev['host']}:{dev['port']}"

            # Extract the main part of device name
            device_name = dev["name"]
            if "._http._tcp.local." in device_name:
                device_name = device_name.replace("._http._tcp.local.", "")

            # For CT: show the full name
            label = f"CT: {device_name}"

            discovered_device_options[key] = label

        # Build form schema
        data_schema = vol.Schema(
            {
                vol.Required("discovered_device"): vol.In(discovered_device_options),
            }
        )

        return self.async_show_form(
            step_id="discovery_ct",
            data_schema=data_schema,
            description_placeholders={},
        )


class EwayOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Eway Charger."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get device type from config entry
        device_type = self.config_entry.data.get("device_type", "charger")

        if device_type == "energy_storage":
            # Handle energy storage device options
            return await self._handle_energy_storage_options(user_input)
        if device_type == "ct":
            # Handle CT device options (similar to energy storage for now)
            return await self._handle_energy_storage_options(user_input)
        if device_type == "smart_plug":
            # Handle smart plug device options
            return await self._handle_smart_plug_options(user_input)

        # Handle charger device options
        return await self._handle_charger_options(user_input)

    async def _handle_charger_options(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle charger device options."""
        # Get current enabled sensors or default to enabled_by_default sensors
        current_enabled = self.config_entry.options.get("enabled_sensors", [])
        if not current_enabled:
            current_enabled = [
                key
                for key, config in SENSOR_CONFIGS.items()
                if config.get("enabled_by_default", False)
            ] + [
                f"binary_{key}"
                for key, config in BINARY_SENSOR_CONFIGS.items()
                if config.get("enabled_by_default", False)
            ]

        # Create sensor selection options
        sensor_options = {}

        # Add regular sensors
        for sensor_key, config in SENSOR_CONFIGS.items():
            sensor_options[sensor_key] = (
                f"{config['name']} ({'Default' if config['enabled_by_default'] else 'Optional'})"
            )

        # Add binary sensors
        for sensor_key, config in BINARY_SENSOR_CONFIGS.items():
            sensor_options[f"binary_{sensor_key}"] = (
                f"Binary: {config.get('translation_key', sensor_key).replace('_', ' ').title()} ({'Default' if config.get('enabled_by_default', False) else 'Optional'})"
            )

        options_schema = vol.Schema(
            {
                vol.Optional(
                    "enabled_sensors",
                    default=current_enabled,
                ): cv.multi_select(sensor_options),
                vol.Optional(
                    "scan_interval",
                    default=self.config_entry.options.get("scan_interval", 30),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            description_placeholders={"device_type": "充电桩"},
        )

    async def _handle_energy_storage_options(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle energy storage device options."""

        # Get current enabled storage sensors or default to all sensors
        current_enabled = self.config_entry.options.get("enabled_storage_sensors", [])
        if not current_enabled:
            current_enabled = list(STORAGE_SENSOR_CONFIGS.keys())

        # Create storage sensor selection options
        sensor_options = {}

        # Add storage sensors
        for sensor_key, config in STORAGE_SENSOR_CONFIGS.items():
            sensor_options[sensor_key] = (
                f"{config['name']} ({'Default' if config.get('enabled_by_default', True) else 'Optional'})"
            )

        options_schema = vol.Schema(
            {
                vol.Optional(
                    "enabled_storage_sensors",
                    default=current_enabled,
                ): cv.multi_select(sensor_options),
                vol.Optional(
                    "scan_interval",
                    default=self.config_entry.options.get("scan_interval", 30),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            description_placeholders={"device_type": "储能设备"},
        )

    async def _handle_smart_plug_options(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle smart plug device options."""

        # Get current enabled smart plug sensors or default to all sensors
        current_enabled = self.config_entry.options.get(
            "enabled_smart_plug_sensors", []
        )
        if not current_enabled:
            current_enabled = list(SMART_PLUG_SENSOR_CONFIGS.keys())

        # Create smart plug sensor selection options
        sensor_options = {}

        # Add smart plug sensors
        for sensor_key, config in SMART_PLUG_SENSOR_CONFIGS.items():
            sensor_options[sensor_key] = (
                f"{config['name']} ({'Default' if config.get('enabled_by_default', True) else 'Optional'})"
            )

        options_schema = vol.Schema(
            {
                vol.Optional(
                    "enabled_smart_plug_sensors",
                    default=current_enabled,
                ): cv.multi_select(sensor_options),
                vol.Optional(
                    "scan_interval",
                    default=self.config_entry.options.get("scan_interval", 30),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            description_placeholders={"device_type": "智能插座"},
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
