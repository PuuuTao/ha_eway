"""Data update coordinator for Eway devices."""

from __future__ import annotations

import asyncio
import datetime
from datetime import timedelta
import json
import logging
import time
from typing import Any
import uuid

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    MODEL_CT,
    MODEL_SMART_PLUG,
)
from .device_discovery import EwayDeviceInfo
from .websocket_client import EwayWebSocketClient

_LOGGER = logging.getLogger(__name__)


class EwayChargerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Eway Charger."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str | None = None,
        port: int | None = None,
        device_id: str | None = None,
        device_sn: str | None = None,
        auto_discover: bool = True,
        device_type: str = "charger",
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self._host = host
        self._port = port
        self._device_id = device_id
        self._device_sn = device_sn
        self._auto_discover = auto_discover
        self._device_type = device_type
        self._client: EwayWebSocketClient | None = None
        self._device_data: dict[str, Any] = {}
        self._connection_lock = asyncio.Lock()
        self._discovery = None
        self._discovered_devices: dict[str, EwayDeviceInfo] = {}

        # Initialize client if host and port are provided
        # For energy storage devices, device_id can be empty
        if host and port:
            self._client = EwayWebSocketClient(
                host=host,
                port=port,
                device_id=device_id or "",
                device_sn=device_sn or "",
                message_callback=self._handle_message,
            )
        elif auto_discover:
            # Device discovery functionality has been removed
            # Auto-discovery is no longer supported
            _LOGGER.warning(
                "Auto-discovery is no longer supported. Please configure device manually"
            )

    @property
    def device_id(self) -> str:
        """Return device ID."""
        return self._device_id

    @property
    def device_sn(self) -> str:
        """Return device serial number."""
        return self._device_sn

    @property
    def host(self) -> str:
        """Return host."""
        return self._host

    @property
    def port(self) -> int:
        """Return port."""
        return self._port

    @property
    def device_type(self) -> str:
        """Return device type."""
        return self._device_type

    @property
    def connected(self) -> bool:
        """Return True if connected to device."""
        return self._client.connected if self._client else False

    @property
    def discovered_devices(self) -> dict[str, EwayDeviceInfo]:
        """Return discovered devices."""
        return self._discovered_devices.copy()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API endpoint."""
        async with self._connection_lock:
            # Auto-discovery is no longer supported
            # If no client is connected and we have discovered devices, try to connect to the first one
            if not self._client and self._discovered_devices:
                await self._try_connect_to_discovered_device()

            # If we have a client, try to connect and update data
            if self._client:
                if not self._client.connected:
                    try:
                        await self._client.connect()
                    except (ConnectionError, OSError, TimeoutError) as exc:
                        raise UpdateFailed(
                            f"Error connecting to device: {exc}"
                        ) from exc

                # Test connection with ping
                if not await self._client.ping():
                    try:
                        await self._client.disconnect()
                        await self._client.connect()
                    except (ConnectionError, OSError, TimeoutError) as exc:
                        raise UpdateFailed(
                            f"Error reconnecting to device: {exc}"
                        ) from exc

            # Request current status from device
            if self._client and self._client.connected:
                try:
                    # Actively request device info and status to ensure data is up-to-date
                    await self._client.get_device_info()
                    await self._client.get_device_status()
                    _LOGGER.debug(
                        "Requested device info and status during update cycle"
                    )
                except (ConnectionError, ValueError, OSError, TimeoutError) as exc:
                    _LOGGER.warning(
                        "Failed to request device data during update: %s",
                        exc,
                        exc_info=True,
                    )

            # Return the current data (may be updated by the requests above)
            return self._device_data.copy()

    def _handle_message(self, message: dict[str, Any] | list[Any]) -> None:
        """Handle incoming WebSocket message."""
        _LOGGER.debug("Received message from device: %s", message)

        # Handle list format messages
        if isinstance(message, list):
            _LOGGER.debug("Received list format message, processing each item")
            for item in message:
                if isinstance(item, dict):
                    self._handle_message(item)
                else:
                    _LOGGER.warning("Unexpected list item format: %s", type(item))
            return

        # Handle dict format messages (original logic)
        if not isinstance(message, dict):
            _LOGGER.warning(
                "Unexpected message format: %s, expected dict or list", type(message)
            )
            return

        topic = message.get("topic", "")

        # Check if this is a device info response
        if topic.endswith("/info/post"):
            self._handle_device_info_response(message)
        # Check if this is a charging control response
        elif topic.endswith("/function/post"):
            self._handle_charging_control_response(message)
        # Check if this is a charging session end event
        elif topic.endswith("/event/post"):
            self._handle_charging_event(message)
        # Check if this is a device basic status message
        elif topic.endswith("/property/post"):
            self._handle_device_status_message(message)
        # Check if this is a charging real-time data message
        elif topic.endswith("/monitor2/post"):
            self._handle_charging_realtime_data(message)

        # Store the raw message
        self._device_data.update(message)

        # Trigger update for all entities
        self.async_set_updated_data(self._device_data.copy())

    def _handle_device_info_response(self, message: dict[str, Any]) -> None:
        """Handle device info response message."""
        payload = message.get("payload", {})
        topic = message.get("topic", "")

        _LOGGER.info("Received device info response from topic: %s", topic)

        # Check if this is a storage device info response
        if self._device_type == "energy_storage":
            _LOGGER.info("Processing storage device info response")

            # Extract storage device specific information
            work_mode_info = payload.get("workModeInfo", {})
            work_mode = work_mode_info.get("workMode")
            extend_info = work_mode_info.get("extend", {})
            constant_power = extend_info.get("constantPower", 0)

            _LOGGER.info("Storage workModeInfo: workMode=%s, constantPower=%s", work_mode, constant_power)

            # Store storage info response for async_get_storage_info method
            if hasattr(self, '_pending_info_request'):
                self._storage_info_response = {
                    "workMode": work_mode,
                    "constantPower": constant_power,
                    "workModeInfo": work_mode_info,
                    "payload": payload
                }
                _LOGGER.info("Stored storage info response for pending request")

            # Store in device data for entities to access
            storage_info = {
                "net_protocol_ver": payload.get("netProtocolVer"),
                "mcu_protocol_ver": payload.get("mcuProtocolVer"),
                "product_code": payload.get("productCode"),
                "device_num": payload.get("deviceNum"),
                "net_firm_ver": payload.get("netFirmVer"),
                "mcu_firm_ver": payload.get("mcuFirmVer"),
                "battery_info": payload.get("batteryInfo", []),
                "wifi_info": payload.get("wifiInfo", {}),
                "device_main_data_interval": payload.get("deviceMainDataInterval"),
                "pv_data_interval": payload.get("pvDataInterval"),
                "battery_data_interval": payload.get("batteryDataInterval"),
                "soc": payload.get("soc"),
                "dod": payload.get("dod"),
                "work_mode": work_mode,
                "constant_power": constant_power,
                "work_mode_info": work_mode_info
            }

            self._device_data["storage_info"] = storage_info
            _LOGGER.info("Storage device info parsed and stored")

        else:
            # Handle charger device info response (original logic)
            device_info = {
                "app_firmware_version": payload.get("appFirmVer"),
                "mcb_firmware_version": payload.get("mcbFirmVer"),
                "net_firmware_version": payload.get("netFirmVer"),
                "ui_firmware_version": payload.get("uiFirmVer"),
                "charge_current": payload.get("chargCurrent"),
                "charge_status": payload.get("chargeStatus"),
                "gun_status": payload.get("gunStatus"),
                "gun_lock": payload.get("gunLock"),
                "pile_status": payload.get("pileStatus"),
                "error_codes": payload.get("errCode", []),
                "block_errors": payload.get("blockError"),
                "card_list": payload.get("cardList", []),
                "network_way": payload.get("networkWay"),
                "net_source": payload.get("netSource"),
                "wifi_ssid": payload.get("wifiSsid"),
                "nfc_enable": payload.get("nfcEnable"),
                "time_zone": payload.get("timeZone"),
                "work_charge": payload.get("workCharg"),
                "work_this": payload.get("workThis"),
                "work_total": payload.get("workTotal"),
                "board_info": payload.get("board", []),
            }

            # Store device info in a separate key
            self._device_data["device_info"] = device_info
            _LOGGER.info("Charger device info parsed: %s", device_info)

        # Update device registry with new firmware version
        if self._device_type == "energy_storage":
            # For storage devices, create device info from payload
            registry_info = {
                "protocol_version": payload.get("netProtocolVer"),
                "app_firmware_version": payload.get("netFirmVer"),
            }
            self._update_device_registry(registry_info)
        else:
            # For charger devices, use the parsed device_info
            self._update_device_registry(device_info)

        # Notify all entities that device info has been updated
        self.async_set_updated_data(self._device_data.copy())

    def _handle_charging_control_response(self, message: dict[str, Any]) -> None:
        """Handle charging control response message."""
        payload = message.get("payload", [])
        topic = message.get("topic", "")

        _LOGGER.info("Received charging control response from topic: %s", topic)

        if isinstance(payload, list) and payload:
            control_data = payload[0]
            command_id = control_data.get("id")
            value = control_data.get("value")
            remark = control_data.get("remark", "")

            if command_id == "charg-switch":
                if value == "0":
                    _LOGGER.info("Charging started successfully: %s", remark)
                    self._device_data["charging_status"] = "charging"
                elif value == "1":
                    _LOGGER.info("Charging stopped successfully: %s", remark)
                    self._device_data["charging_status"] = "stopped"
            elif command_id == "network-way":
                _LOGGER.info("Charging mode changed successfully: %s", remark)
                self._device_data["charging_mode"] = (
                    "network_control" if value == "1" else "plug_and_play"
                )
            elif command_id == "charg-current":
                _LOGGER.info("Max current set successfully: %s", remark)
                self._device_data["max_current"] = int(value)
            elif command_id == "reset-pwd":
                _LOGGER.info(
                    "Screen password reset successfully: %s, new password: %s",
                    remark,
                    value,
                )

                # Store password reset response

                self._device_data["password_reset_response"] = {
                    "id": command_id,
                    "value": value,
                    "remark": remark,
                    "user_id": control_data.get("userId", ""),
                    "timestamp": time.time(),
                }

                # Keep backward compatibility
                self._device_data["screen_password_reset"] = {
                    "success": True,
                    "timestamp": asyncio.get_event_loop().time(),
                }
            elif command_id == "nfc-enable":
                _LOGGER.info("NFC enable/disable successfully: %s", remark)
                self._device_data["nfc_enabled"] = value == "0"  # 0=enabled, 1=disabled
                self._device_data["nfc_control_response"] = {
                    "success": True,
                    "enabled": value == "0",
                    "timestamp": asyncio.get_event_loop().time(),
                }
            elif command_id == "card-add":
                _LOGGER.info(
                    "NFC card added successfully: %s, card ID: %s", remark, value
                )

                # Store NFC card add response

                self._device_data["nfc_card_add_response"] = {
                    "id": command_id,
                    "value": value,
                    "remark": remark,
                    "user_id": control_data.get("userId", ""),
                    "timestamp": time.time(),
                    "success": True,
                    "card_id": value,
                }

                _LOGGER.info("NFC card add response stored: %s", value)
            elif command_id == "card-del":
                _LOGGER.info(
                    "NFC card deleted successfully: %s, card ID: %s", remark, value
                )

                # Store NFC card delete response

                self._device_data["nfc_card_delete_response"] = {
                    "id": command_id,
                    "value": value,
                    "remark": remark,
                    "user_id": control_data.get("userId", ""),
                    "timestamp": time.time(),
                    "success": True,
                    "card_id": value,
                }

                _LOGGER.info("NFC card delete response stored: %s", value)

            # Store charging control response
            self._device_data["charging_control_response"] = {
                "id": command_id,
                "value": value,
                "remark": remark,
                "timestamp": asyncio.get_event_loop().time(),
            }

    def _handle_charging_event(self, message: dict[str, Any]) -> None:
        """Handle charging session end event and error events."""
        payload = message.get("payload", {})
        topic = message.get("topic", "")

        _LOGGER.info("Received charging event from topic: %s", topic)

        # Check if payload is a list (error code response)
        if isinstance(payload, list) and payload:
            error_data = payload[0]
            command_id = error_data.get("id")

            if command_id == "charg-error":
                value = error_data.get("value", "[]")
                remark = error_data.get("remark", "")
                user_id = error_data.get("userId", "")

                _LOGGER.info("Device error codes received: %s", value)

                # Parse error codes from string array format

                try:
                    error_codes = json.loads(value) if value else []
                except (json.JSONDecodeError, TypeError):
                    error_codes = []
                    _LOGGER.warning("Failed to parse error codes: %s", value)

                # Store error response
                self._device_data["device_error_response"] = {
                    "id": command_id,
                    "value": value,
                    "error_codes": error_codes,
                    "remark": remark,
                    "user_id": user_id,
                    "timestamp": time.time(),
                }

                _LOGGER.info("Device error codes stored: %s", error_codes)
                return

        # Handle regular charging session end event (when payload is a dict)
        if isinstance(payload, dict):
            # Extract charging session data
            charging_session = {
                "degrees": payload.get("degrees", 0.0),  # Charging energy (kWh)
                "duration": payload.get("duration", 0),  # Charging duration
                "end_time": payload.get("endTime"),  # Charging end time
                "start_time": payload.get("startTime"),  # Charging start time
                "stop_reason": payload.get("stopReason", ""),  # Stop reason
                "error_codes": payload.get("errCode", []),  # Error codes
                "user_id": payload.get("userId", ""),
            }

            # Store charging session data
            self._device_data["last_charging_session"] = charging_session
            self._device_data["charging_status"] = "completed"

            _LOGGER.info("Charging session completed: %s", charging_session)

    def _handle_device_status_message(self, message: dict[str, Any]) -> None:
        """Handle device basic status message."""
        payload = message.get("payload", {})
        topic = message.get("topic", "")

        _LOGGER.info("Received device status from topic: %s", topic)

        # Check if payload is a list
        if isinstance(payload, list) and payload:
            # Check if this is a status change array (gun-status, charge-status, pile-status)
            if len(payload) == 3 and all(
                item.get("id") in ["gun-status", "charge-status", "pile-status"]
                for item in payload
            ):
                # Handle device status changes array

                timestamp = time.time()

                device_status = {}
                status_responses = []

                for status_item in payload:
                    status_id = status_item.get("id")
                    value = status_item.get("value")
                    remark = status_item.get("remark", "")
                    user_id = status_item.get("userId", "")

                    # Map status IDs to device status fields
                    if status_id == "gun-status":
                        device_status["gun_status"] = int(value) if value else 0
                        _LOGGER.info(
                            "Gun status changed: %s (value: %s)", remark, value
                        )
                    elif status_id == "charge-status":
                        device_status["charging_status"] = int(value) if value else 0
                        _LOGGER.info(
                            "Charging status changed: %s (value: %s)", remark, value
                        )
                    elif status_id == "pile-status":
                        device_status["pile_status"] = int(value) if value else 0
                        _LOGGER.info(
                            "Pile status changed: %s (value: %s)", remark, value
                        )

                    # Store individual status response
                    status_responses.append(
                        {
                            "id": status_id,
                            "value": value,
                            "remark": remark,
                            "user_id": user_id,
                            "timestamp": timestamp,
                        }
                    )

                # Update device status
                if "device_status" not in self._device_data:
                    self._device_data["device_status"] = {}
                self._device_data["device_status"].update(device_status)

                # Store status change responses
                self._device_data["device_status_responses"] = status_responses

                _LOGGER.info("Device status updated from array: %s", device_status)
                return

            # Handle single control response (existing logic)
            control_data = payload[0]
            command_id = control_data.get("id")

            if command_id == "network-way":
                value = control_data.get("value")
                remark = control_data.get("remark", "")

                _LOGGER.info("Charging mode changed successfully: %s", remark)

                # Update charging mode based on value
                if value == "1":
                    self._device_data["charging_mode"] = "network_control"
                    self._device_data["charging_mode_display"] = "network_control"
                elif value == "2":
                    self._device_data["charging_mode"] = "plug_and_play"
                    self._device_data["charging_mode_display"] = "plug_and_play"

                # Store mode change response

                self._device_data["charging_mode_response"] = {
                    "id": command_id,
                    "value": value,
                    "remark": remark,
                    "user_id": control_data.get("userId", ""),
                    "timestamp": time.time(),
                }

                _LOGGER.info(
                    "Charging mode updated to: %s",
                    self._device_data.get("charging_mode"),
                )
                return

            if command_id == "charg-current":
                value = control_data.get("value")
                remark = control_data.get("remark", "")

                _LOGGER.info(
                    "Charging current changed successfully: %s, new value: %s A",
                    remark,
                    value,
                )

                # Store current change response

                self._device_data["charging_current_response"] = {
                    "id": command_id,
                    "value": value,
                    "remark": remark,
                    "user_id": control_data.get("userId", ""),
                    "timestamp": time.time(),
                }

                _LOGGER.info("Charging current response stored: %s A", value)
                return

            if command_id == "nfc-enable":
                value = control_data.get("value")
                remark = control_data.get("remark", "")

                _LOGGER.info("NFC status changed: %s, value: %s", remark, value)

                # Update NFC status based on value
                nfc_enabled = value == "0"  # 0=enabled, 1=disabled
                self._device_data["nfc_enabled"] = nfc_enabled

                # Store NFC status response

                self._device_data["nfc_status_response"] = {
                    "id": command_id,
                    "value": value,
                    "remark": remark,
                    "user_id": control_data.get("userId", ""),
                    "timestamp": time.time(),
                    "enabled": nfc_enabled,
                }

                _LOGGER.info(
                    "NFC status updated: %s (value: %s)",
                    "enabled" if nfc_enabled else "disabled",
                    value,
                )
                return

        # Handle regular device status data (when payload is a dict)
        if isinstance(payload, dict):
            device_status = {
                "charging_status": payload.get(
                    "chargingStatus"
                ),  # Charging status 0: not charging 1: charging 2: charge complete
                "gun_status": payload.get(
                    "gunStatus"
                ),  # Gun status 0: not inserted 1: inserted
                "pile_status": self._map_pile_status(
                    payload.get("pileStatus")
                ),  # Pile status 0: idle 1: charging 2: fault
            }

            # Store device status data
            self._device_data["device_status"] = device_status

            _LOGGER.info("Device status parsed: %s", device_status)

    def _handle_charging_realtime_data(self, message: dict[str, Any]) -> None:
        """Handle charging real-time data message."""
        payload = message.get("payload", {})
        topic = message.get("topic", "")

        _LOGGER.info("Received charging real-time data from topic: %s", topic)

        # Extract charging real-time data
        realtime_data = {
            "amount": payload.get("amount", 0.0),  # Charging energy (kWh)
            "current": payload.get("current", 0.0),  # Average charging current (A)
            "current_l1": payload.get("currentL1", 0.0),  # Three-phase current L1 (A)
            "current_l2": payload.get("currentL2", 0.0),  # Three-phase current L2 (A)
            "current_l3": payload.get("currentL3", 0.0),  # Three-phase current L3 (A)
            "duration": payload.get("duration", 0),  # Duration (seconds)
            "duty_cycle": payload.get("dutyCycle", 0),  # CP duty cycle (%)
            "imt4g_rssi": self._map_signal_strength(
                payload.get("imt4gRssi", -1)
            ),  # 4G signal strength (0-4, -1 means unavailable)
            "moisture": payload.get("moisture", 0.0),  # Humidity (%)
            "power": payload.get("power", 0.0),  # Charging power (W)
            "temperature": payload.get("temperature", 0.0),  # Temperature (°C)
            "voltage": payload.get("voltage", 0.0),  # Voltage (V)
            "wifi_rssi": payload.get("wifiRssi", 0),  # WiFi signal strength
        }

        # Store charging real-time data
        self._device_data["charging_realtime"] = realtime_data

        _LOGGER.info("Charging real-time data parsed: %s", realtime_data)

    def _convert_timestamp(self, timestamp_ms: int) -> str:
        """Convert millisecond timestamp to readable format."""
        if timestamp_ms <= 0:
            return ""

        try:
            # Convert milliseconds to seconds
            timestamp_s = timestamp_ms / 1000
            # Convert to datetime object
            dt = datetime.datetime.fromtimestamp(timestamp_s, tz=datetime.UTC)
            # Format as ISO string
            return dt.isoformat()
        except (ValueError, OSError) as exc:
            _LOGGER.warning("Failed to convert timestamp %s: %s", timestamp_ms, exc)
            return str(timestamp_ms)

    async def async_send_command(self, command: dict[str, Any]) -> None:
        """Send a command to the device."""
        async with self._connection_lock:
            if not self._client.connected:
                raise ConnectionError("Not connected to device")

            try:
                await self._client.send_message(command)
            except (ConnectionError, OSError, TimeoutError) as exc:
                _LOGGER.error("Failed to send command: %s", exc)
                raise

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        _LOGGER.debug("Shutting down coordinator")

        # Discovery functionality has been removed

        # Disconnect client
        if self._client:
            await self._client.disconnect()

    async def async_start_charging(self) -> None:
        """Start charging."""
        if not self._device_id or not self._device_sn:
            raise ValueError("Device ID and SN are required for charging control")

        command = {
            "topic": f"/{self._device_id}/{self._device_sn}/function/get",
            "payload": {
                "id": "charg-switch",
                "value": "0",
                "remark": "app_charging",
                "userId": "",
            },
        }
        _LOGGER.info("Sending start charging command: %s", command)
        await self.async_send_command(command)

    async def async_get_device_info(self) -> None:
        """Get device information."""
        async with self._connection_lock:
            if not self._client or not self._client.connected:
                raise ConnectionError("Not connected to device")

            try:
                await self._client.get_device_info()
                _LOGGER.info("Device info request sent")
            except (ConnectionError, ValueError, OSError, TimeoutError) as exc:
                _LOGGER.error("Failed to get device info: %s", exc)
                raise

    async def async_get_device_status(self) -> None:
        """Get device status."""
        async with self._connection_lock:
            if not self._client or not self._client.connected:
                raise ConnectionError("Not connected to device")

            try:
                await self._client.get_device_status()
                _LOGGER.info("Device status request sent")
            except (ConnectionError, ValueError, OSError, TimeoutError) as exc:
                _LOGGER.error("Failed to get device status: %s", exc)
                raise

    async def _on_device_discovered(
        self, action: str, name: str, device_info: EwayDeviceInfo | None
    ) -> None:
        """Handle discovered device."""
        if action == "added" and device_info:
            _LOGGER.info(
                "Discovered Eway device: %s at %s:%d",
                name,
                device_info.host,
                device_info.port,
            )
            self._discovered_devices[name] = device_info

            # If we don't have a client yet, try to connect to this device
            if not self._client:
                await self._try_connect_to_discovered_device()

        elif action == "removed":
            if name in self._discovered_devices:
                _LOGGER.info("Eway device removed: %s", name)
                del self._discovered_devices[name]

    async def _try_connect_to_discovered_device(self) -> None:
        """Try to connect to the first discovered device."""
        if not self._discovered_devices:
            return

        # Get the first discovered device
        device_name, device_info = next(iter(self._discovered_devices.items()))

        _LOGGER.info(
            "Attempting to connect to discovered device: %s at %s:%d",
            device_name,
            device_info.host,
            device_info.port,
        )

        # Use parsed device ID and SN from device info
        device_id = self._device_id or device_info.device_id
        device_sn = self._device_sn or device_info.device_sn

        _LOGGER.info(
            "Device ID: %s, Device SN: %s",
            device_id,
            device_sn,
        )

        # Create a new client for this device
        self._client = EwayWebSocketClient(
            host=device_info.host,
            port=device_info.port,
            device_id=device_id,
            device_sn=device_sn,
            message_callback=self._handle_message,
        )

        # Update coordinator properties
        self._host = device_info.host
        self._port = device_info.port
        self._device_id = device_id
        self._device_sn = device_sn

        try:
            await self._client.connect()
            _LOGGER.info("Successfully connected to discovered device: %s", device_name)
        except (ConnectionError, OSError, TimeoutError) as exc:
            _LOGGER.error(
                "Failed to connect to discovered device %s: %s", device_name, exc
            )
            self._client = None

    async def async_discover_devices(self) -> list[EwayDeviceInfo]:
        """Manually trigger device discovery and return found devices."""
        # Device discovery functionality has been removed
        _LOGGER.warning("Device discovery functionality is no longer available")
        return list(self._discovered_devices.values())

    async def async_connect_to_device(
        self, device_info: EwayDeviceInfo, device_id: str | None = None
    ) -> None:
        """Manually connect to a specific device."""
        # Disconnect current client if any
        if self._client:
            await self._client.disconnect()

        # Use provided device_id or extract from device name
        target_device_id = device_id or self._device_id or device_info.name

        # Create new client
        self._client = EwayWebSocketClient(
            host=device_info.host,
            port=device_info.port,
            device_id=target_device_id,
            device_sn=self._device_sn,
            message_callback=self._handle_message,
        )

        # Update coordinator properties
        self._host = device_info.host
        self._port = device_info.port
        self._device_id = target_device_id

        await self._client.connect()
        _LOGGER.info(
            "Connected to device: %s at %s:%d",
            device_info.name,
            device_info.host,
            device_info.port,
        )

    async def async_stop_charging(self) -> None:
        """Stop charging."""
        if not self._device_id or not self._device_sn:
            raise ValueError("Device ID and SN are required for charging control")

        command = {
            "topic": f"/{self._device_id}/{self._device_sn}/function/get",
            "payload": {
                "id": "charg-switch",
                "value": "1",
                "remark": "stop_charging",
                "userId": "",
            },
        }
        _LOGGER.info("Sending stop charging command: %s", command)
        await self.async_send_command(command)

    def _map_pile_status(self, status: int | None) -> int | None:
        """Map pile status value."""
        if status is None:
            return None
        # Return the raw status value (0: idle, 1: charging, 2: fault)
        # The mapping to text is handled in the sensor classes
        return int(status) if isinstance(status, (int, float, str)) else None

    def _map_signal_strength(self, rssi: int | None) -> int | None:
        """Map signal strength value."""
        if rssi is None or rssi == -1:
            return -1  # -1 means signal unavailable
        # Return the raw RSSI value
        return int(rssi) if isinstance(rssi, (int, float, str)) else -1

    def _update_device_registry(self, device_info: dict[str, Any]) -> None:
        """Update device registry with new firmware version."""
        try:
            # Get device registry
            device_registry = dr.async_get(self.hass)
            device_identifier = self._device_id

            # Find the device in registry
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, device_identifier)}
            )

            if device:
                # Determine firmware version based on device type
                sw_version = device_info.get("app_firmware_version")

                # Only update if we have a valid firmware version
                if sw_version:
                    # Update device with new firmware version
                    device_registry.async_update_device(
                        device.id, sw_version=str(sw_version)
                    )
                    _LOGGER.warning(
                        "Updated device registry firmware version to: %s for device %s",
                        sw_version,
                        device_identifier,
                    )
                else:
                    _LOGGER.warning(
                        "No firmware version available to update device registry for device %s",
                        device_identifier,
                    )
            else:
                _LOGGER.warning(
                    "Device not found in registry for update with identifier: %s",
                    device_identifier,
                )

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.error("Failed to update device registry: %s", exc)


class EwayStorageCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Eway Energy Storage device."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        device_sn: str | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self._host = host
        self._device_sn = device_sn
        self._device_type = "energy_storage"
        self._client: EwayWebSocketClient | None = None
        self._device_data: dict[str, Any] = {}
        self._connection_lock = asyncio.Lock()
        self._pending_info_request = None
        self._storage_info_response = None

        # Initialize client for storage device (port 80)
        if host:
            self._client = EwayWebSocketClient(
                host=host,
                port=80,  # Storage devices use port 80
                device_id="",  # Storage devices don't use device_id
                device_sn=device_sn or "",
                message_callback=self._handle_message,
            )

    @property
    def host(self) -> str:
        """Return host."""
        return self._host

    @property
    def device_sn(self) -> str:
        """Return device serial number."""
        return self._device_sn

    @property
    def device_type(self) -> str:
        """Return device type."""
        return self._device_type

    @property
    def connected(self) -> bool:
        """Return True if connected to device."""
        return self._client.connected if self._client else False

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from storage device."""
        if not self._client:
            raise UpdateFailed("WebSocket client not initialized")

        async with self._connection_lock:
            try:
                if not self._client.connected:
                    await self._client.connect()
                    if self._client.connected:
                        _LOGGER.info("Connected to storage device at %s", self._host)
                        # Request device info after connection
                        await self.async_get_storage_info()
                    else:
                        raise UpdateFailed("Failed to connect to storage device")

                # Ping to keep connection alive
                if not await self._client.ping():
                    _LOGGER.warning("Ping failed, attempting to reconnect")
                    await self._client.connect()
                    if not self._client.connected:
                        raise UpdateFailed("Failed to reconnect to storage device")

            except Exception as exc:
                _LOGGER.error("Error communicating with storage device: %s", exc)
                raise UpdateFailed(f"Error communicating with storage device: {exc}")

        return self._device_data.copy()

    def _handle_message(self, message: dict[str, Any] | list[Any]) -> None:
        """Handle incoming WebSocket message."""
        _LOGGER.debug("Received message from storage device: %s", message)

        # Handle list format messages
        if isinstance(message, list):
            _LOGGER.debug("Received list format message, processing each item")
            for item in message:
                if isinstance(item, dict):
                    self._handle_message(item)
                else:
                    _LOGGER.warning("Unexpected list item format: %s", type(item))
            return

        # Handle dict format messages
        if not isinstance(message, dict):
            _LOGGER.warning(
                "Unexpected message format: %s, expected dict or list", type(message)
            )
            return

        topic = message.get("topic", "")

        # Check if this is a device info response
        if topic.endswith("/info/post"):
            self._handle_device_info_response(message)
        # Check if this is a storage device mini data message
        elif topic.endswith("/event/storage/mini/post"):
            self._handle_storage_mini_data(message)

        # Store the raw message
        self._device_data.update(message)

        # Trigger update for all entities
        self.async_set_updated_data(self._device_data.copy())

    def _handle_device_info_response(self, message: dict[str, Any]) -> None:
        """Handle device info response message."""
        payload = message.get("payload", {})

        _LOGGER.warning("🔋 Received storage device info response: %s", payload)

        # Extract device information
        device_info = {
            "protocol_version": payload.get("protocolVer", ""),
            "device_sn": payload.get("deviceNum", ""),
            "product_code": payload.get("productCode", ""),
        }

        # Store device info
        self._device_data["device_info"] = device_info

        # Update device registry
        self._update_device_registry(device_info)

        # Store response for async_get_storage_info
        self._storage_info_response = device_info

        _LOGGER.warning("🔋 Storage device info parsed: %s", device_info)

    def _handle_storage_mini_data(self, message: dict[str, Any]) -> None:
        """Handle storage device mini data message."""
        payload = message.get("payload", {})
        topic = message.get("topic", "")

        _LOGGER.warning("🔋 Received storage mini data from topic: %s", topic)
        _LOGGER.warning("🔋 Storage payload: %s", payload)

        # Extract storage mini data
        timestamp_formatted = self._convert_timestamp(payload.get("timestamp", 0))

        # Convert power values from 0.1W to W (divide by 10)
        output_power_raw = payload.get("outputPower", 0)
        output_power = round(output_power_raw, 2) if output_power_raw else 0.0

        storage_data = {
            "timestamp": payload.get("timestamp", 0),  # Original timestamp
            "timestamp_formatted": timestamp_formatted,  # Convert timestamp to readable format
            "protocol_version": payload.get("protocolVer", ""),  # Protocol version
            "output_power": output_power,  # Output power (W)
            "pv_power": 0.0,  # PV input total power (W)
            "pv_daily_generation": 0.0,  # PV daily generation (kWh)
            "pv_total_generation": 0.0,  # PV total generation (kWh)
            "battery_power": 0.0,  # Battery power (W)
            "battery_soc": 0.0,  # Battery total SOC (%)
            "battery_daily_charge": 0.0,  # Battery daily charge (kWh)
            "battery_total_charge": 0.0,  # Battery total charge (kWh)
            "battery_daily_discharge": 0.0,  # Battery daily discharge (kWh)
            "battery_total_discharge": 0.0,  # Battery total discharge (kWh)
        }

        # Extract PV data
        pv_data = payload.get("pv", {})
        if pv_data:
            # Convert power from 0.1W to W, energy from 0.01kWh to kWh
            pv_power_raw = pv_data.get("power", 0.0)
            pv_power = round(pv_power_raw, 2) if pv_power_raw else 0.0

            daily_gen_raw = pv_data.get("dailyGen", 0.0)
            daily_gen = round(daily_gen_raw, 2) if daily_gen_raw else 0.0

            total_gen_raw = pv_data.get("totalGen", 0.0)
            total_gen = round(total_gen_raw, 2) if total_gen_raw else 0.0

            storage_data.update(
                {
                    "pv_power": pv_power,  # PV input total power (W)
                    "pv_daily_generation": daily_gen,  # PV daily generation (kWh)
                    "pv_total_generation": total_gen,  # PV total generation (kWh)
                }
            )

        # Extract battery data
        battery_data = payload.get("battery", {})
        if battery_data:
            # Convert power from 0.1W to W, energy from 0.01kWh to kWh, SOC is already in %
            battery_power_raw = battery_data.get("batteryPower", 0.0)
            battery_power = round(battery_power_raw, 2) if battery_power_raw else 0.0

            battery_soc = round(battery_data.get("batteryTotalSOC", 0.0), 2)

            daily_charge_raw = battery_data.get("batteryDailyCharge", 0.0)
            daily_charge = round(daily_charge_raw, 2) if daily_charge_raw else 0.0

            total_charge_raw = battery_data.get("batteryTotalCharge", 0.0)
            total_charge = round(total_charge_raw, 2) if total_charge_raw else 0.0

            daily_discharge_raw = battery_data.get("batteryDailyDischarge", 0.0)
            daily_discharge = (
                round(daily_discharge_raw, 2) if daily_discharge_raw else 0.0
            )

            total_discharge_raw = battery_data.get("batteryTotalDischarge", 0.0)
            total_discharge = (
                round(total_discharge_raw, 2) if total_discharge_raw else 0.0
            )

            storage_data.update(
                {
                    "battery_power": battery_power,  # Battery power (W)
                    "battery_soc": battery_soc,  # Battery total SOC (%)
                    "battery_daily_charge": daily_charge,  # Battery daily charge (kWh)
                    "battery_total_charge": total_charge,  # Battery total charge (kWh)
                    "battery_daily_discharge": daily_discharge,  # Battery daily discharge (kWh)
                    "battery_total_discharge": total_discharge,  # Battery total discharge (kWh)
                }
            )

        # Store storage mini data
        self._device_data["storage_mini"] = storage_data

        # Also store protocol version in device_info for firmware version display
        if "device_info" not in self._device_data:
            self._device_data["device_info"] = {}
        self._device_data["device_info"]["protocol_version"] = payload.get(
            "protocolVer", ""
        )

        _LOGGER.warning("🔋 Storage mini data parsed: %s", storage_data)
        _LOGGER.warning(
            "🔋 Current device data keys: %s", list(self._device_data.keys())
        )

        # Update device registry with new firmware version
        self._update_device_registry(self._device_data["device_info"])

        # Notify all entities that data has been updated
        self.async_set_updated_data(self._device_data)
        _LOGGER.warning("🔋 Storage data update notification sent to all entities")

    def _convert_timestamp(self, timestamp_ms: int) -> str:
        """Convert timestamp from milliseconds to readable format."""
        try:
            if timestamp_ms == 0:
                return "N/A"
            # Convert milliseconds to seconds
            timestamp_s = timestamp_ms / 1000
            # Convert to datetime
            dt = datetime.datetime.fromtimestamp(timestamp_s)
            # Format as readable string
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError) as exc:
            _LOGGER.warning("Failed to convert timestamp %s: %s", timestamp_ms, exc)
            return "Invalid"

    async def async_send_command(self, command: dict[str, Any]) -> None:
        """Send command to storage device."""
        if not self._client:
            raise ValueError("WebSocket client not initialized")

        if not self._client.connected:
            await self._client.connect()

        await self._client.send_message(command)

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        if self._client:
            await self._client.disconnect()
            self._client = None
        _LOGGER.info("Storage coordinator shutdown complete")

    async def async_set_storage_power(self, power: int) -> None:
        """Set energy storage device power."""
        if not self._device_sn:
            raise ValueError("Device SN is required for storage power control")

        # Generate UUID and remove dashes
        message_id = str(uuid.uuid4()).replace("-", "")

        # Get current timestamp in milliseconds
        timestamp = int(time.time() * 1000)

        command = {
            "topic": f"/{self._device_sn}/property/get",
            "payload": {
                "timestamp": timestamp,
                "messageId": message_id,
                "productCode": "EwayES",
                "deviceNum": self._device_sn,
                "source": "ws",
                "property": [
                    {
                        "id": "workMode",
                        "value": "0",
                        "extend": {
                            "constantPower": power
                        }
                    }
                ]
            }
        }
        _LOGGER.info("Sending storage power control command: %s", command)
        await self.async_send_command(command)

    async def async_get_storage_info(self) -> dict[str, Any] | None:
        """Get storage device info."""
        if not self._device_sn:
            _LOGGER.error("Device SN is required for storage info request")
            return None

        # Generate UUID and remove dashes
        message_id = str(uuid.uuid4()).replace("-", "")

        # Get current timestamp in milliseconds
        timestamp = int(time.time() * 1000)

        command = {
            "topic": f"/{self._device_sn}/info/get",
            "payload": {
                "timestamp": timestamp,
                "messageId": message_id,
                "source": "ws"
            }
        }

        self._pending_info_request = message_id

        try:
            await self.async_send_command(command)
            _LOGGER.info("Storage info request sent")

            # Wait for response (with timeout)
            for _ in range(50):  # Wait up to 5 seconds (50 * 0.1s)
                await asyncio.sleep(0.1)
                if hasattr(self, '_storage_info_response') and self._storage_info_response:
                    response = self._storage_info_response
                    self._storage_info_response = None  # Clear the response
                    return response

            _LOGGER.warning("Timeout waiting for storage info response")
            return None

        except Exception as exc:
            _LOGGER.error("Failed to get storage info: %s", exc)
            raise

    def _update_device_registry(self, device_info: dict[str, Any]) -> None:
        """Update device registry with new firmware version."""
        try:
            # Get device registry
            device_registry = dr.async_get(self.hass)

            # Use device serial number as identifier for storage devices
            device_identifier = self._device_sn or ""

            # Find the device in registry
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, device_identifier)}
            )

            if device:
                # For storage devices, use protocol version
                sw_version = device_info.get("protocol_version")

                # Only update if we have a valid firmware version
                if sw_version:
                    # Update device with new firmware version
                    device_registry.async_update_device(
                        device.id, sw_version=str(sw_version)
                    )
                    _LOGGER.warning(
                        "Updated storage device registry firmware version to: %s for device %s",
                        sw_version,
                        device_identifier,
                    )
                else:
                    _LOGGER.warning(
                        "No firmware version available to update storage device registry for device %s",
                        device_identifier,
                    )
            else:
                _LOGGER.warning(
                    "Storage device not found in registry for update with identifier: %s",
                    device_identifier,
                )

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.error("Failed to update storage device registry: %s", exc)


class EwayCTCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the CT Device."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        device_sn: str | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_ct",
            update_interval=timedelta(seconds=10),  # 每10秒更新一次
        )
        self._host = host
        self._device_sn = device_sn or ""
        self._device_data: dict[str, Any] = {}
        self._connected = False
        self._session: aiohttp.ClientSession | None = None
        self._connection_retries = 0
        self._initial_connection_attempts = 0
        self.device_type = "ct"  # CT设备类型
        self._last_status_update = 0  # 上次状态数据更新时间
        self._config_fetch_scheduled = False  # 配置数据获取是否已调度

    @property
    def host(self) -> str:
        """Return host."""
        return self._host

    @property
    def device_sn(self) -> str:
        """Return device serial number."""
        return self._device_sn

    @property
    def connected(self) -> bool:
        """Return True if connected to device."""
        return self._connected

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from CT device via HTTP."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)  # 5秒超时
            )

        url = f"http://{self._host}/rpc/EM1.GetStatus?id=0"
        _LOGGER.warning("🔌 CT HTTP Request: %s", url)  # Use warning level to ensure visibility

        try:
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.warning("✅ CT HTTP Success: received data from %s", self._host)
                    _LOGGER.warning("📊 Raw CT API Response: %s", data)

                    # Reset connection retries on successful response
                    self._connection_retries = 0
                    if not self._connected:
                        self._connected = True
                        _LOGGER.warning("🔗 CT device connected successfully")

                    # Map API response fields to internal field names
                    # Check for different possible field names from the API
                    mapped_data = self._map_api_response(data)
                    _LOGGER.warning("🔄 Mapped CT data: %s", mapped_data)

                    # Process and store the data
                    # Preserve existing anti_backflow status if not present in current response
                    current_anti_backflow = mapped_data.get("anti_backflow")
                    if current_anti_backflow is None and hasattr(self, 'data') and self.data:
                        current_anti_backflow = self.data.get("anti_backflow")

                    self._device_data = {
                        "ct_voltage": mapped_data.get("voltage", 0.0),
                        "ct_current": mapped_data.get("current", 0.0),
                        "ct_act_power": mapped_data.get("act_power", 0.0),
                        "ct_aprt_power": mapped_data.get("aprt_power", 0.0),
                        "ct_pf": mapped_data.get("pf", 0.0),
                        "ct_freq": mapped_data.get("freq", 0.0),
                        "ct_calibration": mapped_data.get("calibration", ""),
                        "ct_errors": mapped_data.get("errors", []),
                        "ct_flags": mapped_data.get("flags", []),
                        "anti_backflow": current_anti_backflow,  # Preserve anti-backflow status
                        "last_update": self.hass.loop.time(),
                    }

                    _LOGGER.warning("💾 Final CT device data: %s", self._device_data)

                    # Update device registry
                    self._update_device_registry()

                    # Record the time of successful status data fetch
                    self._last_status_update = self.hass.loop.time()

                    # Schedule config data fetch 5 seconds later to avoid performance issues
                    if not self._config_fetch_scheduled:
                        self._config_fetch_scheduled = True
                        self.hass.loop.call_later(5.0, self._schedule_config_fetch)

                    return self._device_data.copy()
                else:
                    self._connection_retries += 1
                    if self._connected:
                        self._connected = False
                        _LOGGER.warning("❌ CT device connection lost")

                    response_text = await response.text()
                    _LOGGER.warning(
                        "❌ CT HTTP Failed: %s returned HTTP %s (retry %d) - Response: %s",
                        self._host,
                        response.status,
                        self._connection_retries,
                        response_text[:200] + "..." if len(response_text) > 200 else response_text
                    )

                    if self._connection_retries >= 3:
                        raise UpdateFailed(
                            f"CT device HTTP error {response.status} after {self._connection_retries} retries"
                        )

                    return self._device_data or {}

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            _LOGGER.warning("🌐 CT Network Error: %s - %s", self._host, exc)

            # 如果还没有建立连接，进行初始连接尝试
            if not self._connected:
                self._initial_connection_attempts += 1
                _LOGGER.warning(
                    "Initial connection attempt %d/3 failed: %s",
                    self._initial_connection_attempts,
                    exc,
                )

                if self._initial_connection_attempts >= 3:
                    raise UpdateFailed("CT device connection failed after 3 attempts")

                # 等待10秒后重试
                await asyncio.sleep(10)
                raise UpdateFailed(f"CT device connection error: {exc}") from exc
            else:
                # 已连接状态下的错误处理
                self._connection_retries += 1
                _LOGGER.warning(
                    "Error fetching CT data (attempt %d): %s",
                    self._connection_retries,
                    exc,
                )

                if self._connection_retries >= 3:
                    self._connected = False
                    _LOGGER.error("CT device disconnected after 3 failed attempts")

                raise UpdateFailed(f"CT device connection error: {exc}") from exc

        except Exception as exc:
            _LOGGER.error("💥 CT Unexpected Error: %s", exc)
            raise UpdateFailed(f"Unexpected error: {exc}") from exc

    def _map_api_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Map API response fields to standardized field names."""
        mapped = {}

        # Voltage mapping
        for key in ["voltage", "volt", "v", "ct_voltage"]:
            if key in data:
                mapped["voltage"] = data[key]
                break

        # Current mapping
        for key in ["current", "curr", "amp", "a", "ct_current"]:
            if key in data:
                mapped["current"] = data[key]
                break

        # Active power mapping
        for key in ["act_power", "active_power", "power", "watt", "w", "ct_act_power"]:
            if key in data:
                mapped["act_power"] = data[key]
                break

        # Apparent power mapping
        for key in ["aprt_power", "apparent_power", "va", "ct_aprt_power"]:
            if key in data:
                mapped["aprt_power"] = data[key]
                break

        # Power factor mapping
        for key in ["pf", "power_factor", "factor", "ct_pf"]:
            if key in data:
                mapped["pf"] = data[key]
                break

        # Frequency mapping
        for key in ["freq", "frequency", "hz", "ct_freq"]:
            if key in data:
                mapped["freq"] = data[key]
                break

        # Error and status mapping
        for key in ["errors", "error", "ct_errors"]:
            if key in data:
                mapped["errors"] = data[key]
                break

        for key in ["flags", "status", "ct_flags"]:
            if key in data:
                mapped["flags"] = data[key]
                break

        for key in ["calibration", "cal", "ct_calibration"]:
            if key in data:
                mapped["calibration"] = data[key]
                break

        # If no mappings found, try to extract numeric values from any field
        if not any(mapped.values()):
            _LOGGER.warning("🔍 No standard fields found, attempting to extract values from available fields")
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    _LOGGER.warning("📈 Found numeric field: %s = %s", key, value)
                    # Try to guess field type based on value range
                    if 200 <= value <= 250:  # Likely voltage
                        mapped["voltage"] = value
                    elif 0 <= value <= 100:  # Could be current or power factor
                        if value <= 1.0:
                            mapped["pf"] = value
                        else:
                            mapped["current"] = value
                    elif 45 <= value <= 65:  # Likely frequency
                        mapped["freq"] = value
                    elif value > 100:  # Likely power
                        if "power" not in mapped:
                            mapped["act_power"] = value

        return mapped

    def _update_device_registry(self) -> None:
        """Update device registry with CT device information."""
        device_registry = dr.async_get(self.hass)

        # Use consistent device identifier with sensor.py
        device_identifier = self._device_sn or self._host

        device_registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, device_identifier)},
            manufacturer=MANUFACTURER,
            model=MODEL_CT,
            name=f"CT Device {device_identifier}",
            sw_version=self._device_data.get("calibration", "unknown"),
        )

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False
        _LOGGER.debug("CT coordinator shutdown complete")

    async def test_connection(self) -> bool:
        """Test connection to CT device with 3 retry attempts."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            )

        url = f"http://{self._host}/rpc/EM1.GetStatus?id=0"

        for attempt in range(3):
            try:
                async with self._session.get(url) as response:
                    if response.status == 200:
                        _LOGGER.info("CT device connection test successful")
                        return True
                    else:
                        _LOGGER.warning(
                            "CT device test failed with status %s (attempt %d/3)",
                            response.status,
                            attempt + 1,
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                _LOGGER.warning(
                    "CT device test failed (attempt %d/3): %s",
                    attempt + 1,
                    exc,
                )

            if attempt < 2:
                await asyncio.sleep(10)

        _LOGGER.error("CT device connection test failed after 3 attempts")
        return False

    async def async_set_anti_backflow(self, enable: bool) -> bool:
        """Set anti-backflow configuration for CT device."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )

        config_value = "true" if enable else "false"
        url = f"http://{self._host}/rpc/EM1.SetConfig?id=0&config={{\"anti_backflow\":{config_value}}}"

        _LOGGER.warning(
            "🔧 CT Anti-backflow Setting: %s - URL: %s",
            "ENABLE" if enable else "DISABLE",
            url
        )

        try:
            async with self._session.get(url) as response:
                if response.status == 200:
                    response_data = await response.json()
                    _LOGGER.warning(
                        "✅ CT Anti-backflow Set Successfully: %s - Response: %s",
                        "ENABLED" if enable else "DISABLED",
                        response_data
                    )

                    # Update local data with new anti-backflow status
                    # Note: Response only contains {'restart_required': False}, not anti_backflow value
                    # So we directly set the status based on the enable parameter
                    if not hasattr(self, 'data') or self.data is None:
                        self.data = {}
                    self.data["anti_backflow"] = enable

                    return True
                else:
                    _LOGGER.warning(
                        "❌ CT Anti-backflow Set Failed: HTTP %s - %s",
                        response.status,
                        await response.text()
                    )
                    return False
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            _LOGGER.warning(
                "🌐 CT Anti-backflow Network Error: %s",
                exc
            )
            return False
        except Exception as exc:
            _LOGGER.error(
                "💥 CT Anti-backflow Unexpected Error: %s",
                exc
            )
            return False

    async def async_fetch_config_data(self) -> bool:
        """Fetch CT configuration data and update anti-backflow status."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            )

        url = f"http://{self._host}/rpc/EM1.GetConfig?id=0"
        _LOGGER.warning("🔧 CT Config Request: %s", url)

        try:
            async with self._session.get(url) as response:
                if response.status == 200:
                    config_data = await response.json()
                    _LOGGER.warning("✅ CT Config Success: received config from %s", self._host)
                    _LOGGER.warning("⚙️ Raw CT Config Response: %s", config_data)

                    # Extract anti_backflow status from config
                    anti_backflow_status = config_data.get("anti_backflow")
                    if anti_backflow_status is not None:
                        # Update the anti_backflow status in coordinator data
                        if not hasattr(self, 'data') or self.data is None:
                            self.data = {}

                        old_status = self.data.get("anti_backflow")
                        self.data["anti_backflow"] = anti_backflow_status

                        _LOGGER.warning(
                            "🔄 CT Anti-backflow Status Updated: %s -> %s",
                            old_status,
                            anti_backflow_status
                        )

                        # Trigger state update for switch entity
                        self.async_update_listeners()

                        return True
                    else:
                        _LOGGER.warning("⚠️ CT Config: anti_backflow field not found in response")
                        return False
                else:
                    response_text = await response.text()
                    _LOGGER.warning(
                        "❌ CT Config Failed: %s returned HTTP %s - Response: %s",
                        self._host,
                        response.status,
                        response_text[:200] + "..." if len(response_text) > 200 else response_text
                    )
                    return False

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            _LOGGER.warning("🌐 CT Config Network Error: %s - %s", self._host, exc)
            return False
        except Exception as exc:
            _LOGGER.error("💥 CT Config Unexpected Error: %s", exc)
            return False

    def _schedule_config_fetch(self) -> None:
        """Schedule config data fetch as an async task."""
        self.hass.async_create_task(self._async_config_fetch_task())

    async def _async_config_fetch_task(self) -> None:
        """Async task to fetch config data and reset scheduling flag."""
        try:
            await self.async_fetch_config_data()
        except Exception as exc:
            _LOGGER.error("Error in config fetch task: %s", exc)
        finally:
            # Reset the scheduling flag to allow next scheduling
            self._config_fetch_scheduled = False

    def get_anti_backflow_status(self) -> bool | None:
        """Get current anti-backflow status from coordinator data."""
        if not self.data:
            return None
        return self.data.get("anti_backflow")


class EwaySmartPlugCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Smart Plug Device."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        device_sn: str | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_smart_plug",
            update_interval=timedelta(seconds=5),  # 每5秒更新一次
        )
        self._host = host
        self._device_sn = device_sn or ""
        self._device_data: dict[str, Any] = {}
        self._connected = False
        self._session: aiohttp.ClientSession | None = None
        self._connection_retries = 0
        self._initial_connection_attempts = 0
        self.device_type = "smart_plug"  # 智能插座设备类型
        self.device_id = host  # 使用host作为device_id

    @property
    def host(self) -> str:
        """Return host."""
        return self._host

    @property
    def device_sn(self) -> str:
        """Return device serial number."""
        return self._device_sn

    @property
    def connected(self) -> bool:
        """Return True if connected to device."""
        return self._connected

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Smart Plug device via HTTP."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)  # 5秒超时
            )

        url = f"http://{self._host}/rpc/Switch.GetStatus?id=0"
        _LOGGER.warning("🔌 Smart Plug HTTP Request: %s", url)  # Use warning level to ensure visibility

        try:
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.warning("✅ Smart Plug HTTP Success: received data from %s", self._host)
                    _LOGGER.warning("📊 Raw Smart Plug API Response: %s", data)

                    # Reset connection retries on successful response
                    self._connection_retries = 0
                    if not self._connected:
                        self._connected = True
                        _LOGGER.warning("🔗 Smart Plug device connected successfully")

                    # Map API response fields to internal field names
                    mapped_data = self._map_api_response(data)
                    _LOGGER.warning("🔄 Mapped Smart Plug data: %s", mapped_data)

                    # Update device registry
                    self._update_device_registry()

                    return mapped_data
                else:
                    _LOGGER.warning("❌ Smart Plug HTTP Error: %s - %s", response.status, await response.text())
                    raise UpdateFailed(f"HTTP {response.status}: {await response.text()}")
        except asyncio.TimeoutError:
            self._connection_retries += 1
            _LOGGER.warning("⏰ Smart Plug HTTP Timeout (attempt %d)", self._connection_retries)
            if self._connection_retries >= 3:
                self._connected = False
                _LOGGER.error("❌ Smart Plug device disconnected after 3 failed attempts")
            raise UpdateFailed("Timeout connecting to smart plug device")
        except Exception as exc:
            self._connection_retries += 1
            _LOGGER.warning("❌ Smart Plug HTTP Exception (attempt %d): %s", self._connection_retries, exc)
            if self._connection_retries >= 3:
                self._connected = False
                _LOGGER.error("❌ Smart Plug device disconnected after 3 failed attempts")
            raise UpdateFailed(f"Error fetching smart plug data: {exc}") from exc

    def _map_api_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Map API response to internal data structure."""
        mapped_data = {
            "switch_state": data.get("output", False),  # 开关状态
            "power": data.get("apower", 0.0),  # 功率 (W)
            "voltage": data.get("voltage", 0.0),  # 电压 (V)
            "current": data.get("current", 0.0),  # 电流 (A)
            "frequency": data.get("freq", 0.0),  # 频率 (Hz)
            "temperature": data.get("temperature", {}).get("tC", 0.0),  # 温度 (摄氏度)
            "energy_total": data.get("aenergy", {}).get("total", 0.0),  # 总能耗
            "ret_energy_total": data.get("ret_aenergy", {}).get("total", 0.0),  # 返回能耗
        }

        return mapped_data

    def _update_device_registry(self) -> None:
        """Update device registry with smart plug device information."""
        device_registry = dr.async_get(self.hass)
        device_registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id if hasattr(self, 'config_entry') else None,
            identifiers={(DOMAIN, self._device_sn)},
            manufacturer=MANUFACTURER,
            model=MODEL_SMART_PLUG,
            name="Smart Plug",
            sw_version="1.0.0",
        )

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False

    async def test_connection(self) -> bool:
        """Test connection to smart plug device."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            )

        url = f"http://{self._host}/rpc/Switch.GetStatus?id=0"

        # Try 3 times with 10 second intervals
        for attempt in range(3):
            try:
                _LOGGER.warning("🔌 Testing Smart Plug connection (attempt %d/3): %s", attempt + 1, url)
                async with self._session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        _LOGGER.warning("✅ Smart Plug connection test successful")
                        return True
                    else:
                        _LOGGER.warning("❌ Smart Plug connection test failed: HTTP %s", response.status)
            except Exception as exc:
                _LOGGER.warning("❌ Smart Plug connection test exception (attempt %d/3): %s", attempt + 1, exc)

            # Wait 10 seconds before next attempt (except for the last attempt)
            if attempt < 2:
                await asyncio.sleep(10)

        _LOGGER.error("❌ Smart Plug connection test failed after 3 attempts")
        return False

    async def async_set_switch_state(self, state: bool) -> bool:
        """Set smart plug switch state."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            )

        url = f"http://{self._host}/rpc/Switch.Set?id=0&on={str(state).lower()}"
        _LOGGER.warning("🔌 Setting Smart Plug switch state: %s", url)

        try:
            async with self._session.get(url) as response:
                if response.status == 200:
                    _LOGGER.warning("✅ Smart Plug switch state set successfully to %s", state)
                    # Trigger immediate data update
                    await self.async_request_refresh()
                    return True
                else:
                    _LOGGER.error("❌ Failed to set Smart Plug switch state: HTTP %s", response.status)
                    return False
        except Exception as exc:
            _LOGGER.error("❌ Exception setting Smart Plug switch state: %s", exc)
            return False
