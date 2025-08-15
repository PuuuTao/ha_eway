"""Data update coordinator for CT Device."""

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
    MODEL_CT,
)

_LOGGER = logging.getLogger(__name__)


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