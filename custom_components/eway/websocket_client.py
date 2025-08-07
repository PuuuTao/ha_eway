"""WebSocket client for Eway Charger."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import json
import logging
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .const import (
    WS_CLOSE_TIMEOUT,
    WS_CONNECT_TIMEOUT,
    WS_PING_INTERVAL,
    WS_PING_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class EwayWebSocketClient:
    """WebSocket client for Eway Charger communication."""

    def __init__(
        self,
        host: str,
        port: int,
        device_id: str,
        device_sn: str | None = None,
        message_callback: Callable[[dict[str, Any] | list[Any]], None] | None = None,
    ) -> None:
        """Initialize the WebSocket client."""
        self._host = host
        self._port = port
        self._device_id = device_id
        self._device_sn = device_sn
        self._message_callback = message_callback
        self._websocket = None
        self._listen_task = None
        self._connected = False
        self._reconnect_interval = 5
        self._max_reconnect_attempts = 10
        self._reconnect_attempts = 0

    @property
    def connected(self) -> bool:
        """Return True if connected to WebSocket."""
        return self._connected

    @property
    def uri(self) -> str:
        """Return WebSocket URI."""
        return f"ws://{self._host}:{self._port}"

    async def connect(self) -> None:
        """Connect to the WebSocket server."""
        try:
            _LOGGER.debug("Connecting to %s", self.uri)
            # Use asyncio.wait_for to implement connection timeout <mcreference link="https://github.com/aaugustin/websockets/issues/428" index="2">2</mcreference>
            self._websocket = await asyncio.wait_for(
                websockets.connect(
                    self.uri,
                    ping_interval=WS_PING_INTERVAL,
                    ping_timeout=WS_PING_TIMEOUT,
                    close_timeout=WS_CLOSE_TIMEOUT,
                ),
                timeout=WS_CONNECT_TIMEOUT,
            )
            self._connected = True
            self._reconnect_attempts = 0
            _LOGGER.info("Connected to Eway Charger at %s", self.uri)

            # Start listening for messages
            if self._message_callback:
                self._listen_task = asyncio.create_task(self._listen_for_messages())

            # Automatically request device info and status after successful connection
            try:
                if self._device_id and self._device_sn:
                    _LOGGER.info("Automatically requesting device info and status after connection")
                    await self.get_device_info()
                    await self.get_device_status()
                else:
                    _LOGGER.warning("Cannot request device info: device_id=%s, device_sn=%s",
                                  self._device_id, self._device_sn)
            except Exception as exc:
                _LOGGER.warning("Failed to request initial device data: %s", exc)

        except Exception as exc:
            _LOGGER.error("Failed to connect to %s, %s", self.uri, exc)
            self._connected = False
            raise

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        self._connected = False

        if self._listen_task:
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listen_task
            self._listen_task = None

        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as exc:  # noqa: BLE001  # (Blind-except justified)
                _LOGGER.debug("Error closing WebSocket: %s", exc)
            self._websocket = None

        _LOGGER.info("Disconnected from Eway Charger")

    async def send_message(self, message: dict[str, Any]) -> None:
        """Send a message to the WebSocket server."""
        if not self._connected or not self._websocket:
            raise ConnectionError("Not connected to WebSocket server")

        try:
            message_str = json.dumps(message)
            await self._websocket.send(message_str)
            _LOGGER.debug("Sent message: %s", message_str)
        except Exception as exc:
            _LOGGER.error("Failed to send message: %s", exc)
            raise

    async def _listen_for_messages(self) -> None:
        """Listen for incoming WebSocket messages."""
        try:
            async for message in self._websocket:
                try:
                    data = json.loads(message)
                    _LOGGER.debug("Received message: %s", data)
                    if self._message_callback:
                        self._message_callback(data)
                except json.JSONDecodeError as exc:
                    _LOGGER.error("Failed to decode message: %s", exc)
                except Exception as exc:  # noqa: BLE001  # (Blind-except justified)
                    _LOGGER.error("Error processing message: %s", exc)
        except ConnectionClosed:
            _LOGGER.warning("WebSocket connection closed")
            self._connected = False
            await self._handle_reconnect()
        except WebSocketException as exc:
            _LOGGER.error("WebSocket error: %s", exc)
            self._connected = False
            await self._handle_reconnect()
        except Exception as exc:  # noqa: BLE001  # (Blind-except justified)
            _LOGGER.error("Unexpected error in message listener: %s", exc)
            self._connected = False

    async def _handle_reconnect(self) -> None:
        """Handle WebSocket reconnection."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            _LOGGER.error("Max reconnection attempts reached, giving up")
            return

        self._reconnect_attempts += 1
        _LOGGER.info(
            "Attempting to reconnect (%d/%d) in %d seconds",
            self._reconnect_attempts,
            self._max_reconnect_attempts,
            self._reconnect_interval,
        )

        await asyncio.sleep(self._reconnect_interval)

        try:
            await self.connect()
        except Exception as exc:  # noqa: BLE001  # (Blind-except justified)
            _LOGGER.error("Reconnection attempt failed: %s", exc)
            await self._handle_reconnect()

    async def get_device_info(self) -> None:
        """Request device information."""
        if not self._device_id:
            raise ValueError("Device ID is required to get device info")

        if not self._device_sn:
            raise ValueError("Device SN is required to get device info")

        message = {
            "topic": f"/{self._device_id}/{self._device_sn}/info/get",
            "payload": {},
        }

        _LOGGER.info("Requesting device info with topic: %s", message["topic"])
        await self.send_message(message)

    async def get_device_status(self) -> None:
        """Request device status information."""
        if not self._device_id:
            raise ValueError("Device ID is required to get device status")

        if not self._device_sn:
            raise ValueError("Device SN is required to get device status")

        message = {
            "topic": f"/{self._device_id}/{self._device_sn}/property/get",
            "payload": {},
        }

        _LOGGER.info("Requesting device status with topic: %s", message["topic"])
        await self.send_message(message)

    async def ping(self) -> bool:
        """Send a ping to test connection."""
        if not self._connected or not self._websocket:
            return False

        try:
            pong_waiter = await self._websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=WS_PING_TIMEOUT)
        except Exception as exc:  # noqa: BLE001  # (Blind-except justified)
            _LOGGER.debug("Ping failed: %s", exc)
            return False
        else:
            return True
