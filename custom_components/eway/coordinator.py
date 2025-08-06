"""Data update coordinator for Eway Charger."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, MANUFACTURER
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
            _LOGGER.warning("Auto-discovery is no longer supported. Please configure device manually.")

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
                    except Exception as exc:
                        raise UpdateFailed(
                            f"Error connecting to device: {exc}"
                        ) from exc

                # Test connection with ping
                if not await self._client.ping():
                    try:
                        await self._client.disconnect()
                        await self._client.connect()
                    except Exception as exc:
                        raise UpdateFailed(
                            f"Error reconnecting to device: {exc}"
                        ) from exc

            # Request current status from device
            if self._client and self._client.connected:
                try:
                    # Actively request device info and status to ensure data is up-to-date
                    await self._client.get_device_info()
                    await self._client.get_device_status()
                    _LOGGER.debug("Requested device info and status during update cycle")
                except Exception as exc:
                    _LOGGER.warning("Failed to request device data during update: %s", exc)

            # Return the current data (may be updated by the requests above)
            return self._device_data.copy()

    def _handle_message(self, message: dict[str, Any] | list[Any]) -> None:
        """Handle incoming WebSocket message."""
        _LOGGER.debug("Received message from device: %s", message)

        # Add debug logging for storage devices
        if self._device_type == "energy_storage":
            _LOGGER.warning("🔋 Storage device received message: %s", message)

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
            _LOGGER.warning("Unexpected message format: %s, expected dict or list", type(message))
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
        topic = message.get("topic", "")

        _LOGGER.info("Received device info response from topic: %s", topic)

        # Extract useful device information
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

        _LOGGER.info("Device info parsed: %s", device_info)

        # Update device registry with new firmware version
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
                "gun_status": payload.get("gunStatus"),  # Gun status 0: not inserted 1: inserted
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

    def _handle_storage_mini_data(self, message: dict[str, Any]) -> None:
        """Handle storage device mini data message."""
        payload = message.get("payload", {})
        topic = message.get("topic", "")

        _LOGGER.warning("🔋 Received storage mini data from topic: %s", topic)
        _LOGGER.warning("🔋 Storage payload: %s", payload)

        # Extract storage mini data
        timestamp_formatted = self._convert_timestamp(payload.get("timestamp", 0))
        storage_data = {
            "timestamp": payload.get("timestamp", 0),  # Original timestamp
            "timestamp_formatted": timestamp_formatted,  # Convert timestamp to readable format
            "protocol_version": payload.get("protocolVer", ""),  # Protocol version
            "output_power": payload.get("outputPower", 0),  # Output power (W)
        }

        # Extract PV data
        pv_data = payload.get("pv", {})
        storage_data["pv_power"] = pv_data.get("power", 0.0)  # PV input total power (W)

        # Extract battery data
        battery_data = payload.get("battery", {})
        storage_data["battery_power"] = battery_data.get("batteryPower", 0.0)  # Battery power (W)
        storage_data["battery_soc"] = battery_data.get("batteryTotalSOC", 0.0)  # Battery total SOC (%)

        # Store storage mini data
        self._device_data["storage_mini"] = storage_data

        # Also store protocol version in device_info for firmware version display
        if "device_info" not in self._device_data:
            self._device_data["device_info"] = {}
        self._device_data["device_info"]["protocol_version"] = payload.get("protocolVer", "")

        _LOGGER.warning("🔋 Storage mini data parsed: %s", storage_data)
        _LOGGER.warning("🔋 Current device data keys: %s", list(self._device_data.keys()))

        # Update device registry with new firmware version
        self._update_device_registry(self._device_data["device_info"])

        # Notify all entities that data has been updated
        self.async_set_updated_data(self._device_data)
        _LOGGER.warning("🔋 Storage data update notification sent to all entities")

    def _convert_timestamp(self, timestamp_ms: int) -> str:
        """Convert millisecond timestamp to readable format."""
        if timestamp_ms <= 0:
            return ""

        try:
            import datetime
            # Convert milliseconds to seconds
            timestamp_s = timestamp_ms / 1000
            # Convert to datetime object
            dt = datetime.datetime.fromtimestamp(timestamp_s, tz=datetime.timezone.utc)
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
            except Exception as exc:
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
            except Exception as exc:
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
            except Exception as exc:
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
        except Exception as exc:  # noqa: BLE001
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

    def _update_device_registry(self, device_info: dict[str, Any]) -> None:
        """Update device registry with new firmware version."""
        try:
            # Get device registry
            device_registry = dr.async_get(self.hass)

            # For energy storage devices, use device serial number as identifier if device_id is empty
            # For charger devices, use device_id as usual
            if self._device_type == "energy_storage" and not self._device_id:
                # Use device serial number as identifier for energy storage devices
                device_identifier = self._device_sn or ""
            else:
                # Use device_id for charger devices or when device_id is available
                device_identifier = self._device_id

            # Find the device in registry
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, device_identifier)}
            )

            if device:
                # Determine firmware version based on device type
                sw_version = None
                if self._device_type == "charger":
                    # For charger devices, use app firmware version
                    sw_version = device_info.get("app_firmware_version")
                elif self._device_type == "energy_storage":
                    # For energy storage devices, use protocol version if available
                    # Otherwise use app firmware version
                    sw_version = device_info.get("protocol_version") or device_info.get("app_firmware_version")

                # Only update if we have a valid firmware version
                if sw_version:
                    # Update device with new firmware version
                    device_registry.async_update_device(
                        device.id,
                        sw_version=str(sw_version)
                    )
                    _LOGGER.warning("Updated device registry firmware version to: %s for device %s", sw_version, device_identifier)
                else:
                    _LOGGER.warning("No firmware version available to update device registry for device %s", device_identifier)
            else:
                _LOGGER.warning("Device not found in registry for update with identifier: %s", device_identifier)

        except Exception as exc:
            _LOGGER.error("Failed to update device registry: %s", exc)
