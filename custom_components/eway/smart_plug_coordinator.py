"""Data update coordinator for Smart Plug Device."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL_SMART_PLUG,
)

_LOGGER = logging.getLogger(__name__)


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