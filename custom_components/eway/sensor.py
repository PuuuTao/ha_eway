"""Sensor platform for Eway Charger."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

_LOGGER = logging.getLogger(__name__)

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, get_device_model, get_device_name
from .coordinator import EwayChargerCoordinator

# Storage sensor configurations
STORAGE_SENSOR_CONFIGS = {
    "storage_timestamp": {
        "name": "Data Update Time",
        "translation_key": "storage_timestamp",
        "icon": "mdi:clock",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    "storage_protocol_version": {
        "name": "Energy Storage Protocol Version",
        "translation_key": "storage_protocol_version",
        "icon": "mdi:information",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    "storage_output_power": {
        "name": "Energy Storage Output Power",
        "translation_key": "storage_output_power",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "enabled_by_default": True,
    },
    "storage_pv_power": {
        "name": "Energy Storage PV Power",
        "translation_key": "storage_pv_power",
        "icon": "mdi:solar-power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "enabled_by_default": True,
    },
    "storage_pv_daily_generation": {
        "name": "Energy Storage PV Daily Generation",
        "translation_key": "storage_pv_daily_generation",
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled_by_default": True,
    },
    "storage_pv_total_generation": {
        "name": "Energy Storage PV Total Generation",
        "translation_key": "storage_pv_total_generation",
        "icon": "mdi:solar-power-variant-outline",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled_by_default": True,
    },
    "storage_battery_power": {
        "name": "Energy Storage Battery Power",
        "translation_key": "storage_battery_power",
        "icon": "mdi:battery-charging",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "enabled_by_default": True,
    },
    "storage_battery_soc": {
        "name": "Energy Storage Battery SOC",
        "translation_key": "storage_battery_soc",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "enabled_by_default": True,
    },
    "storage_battery_daily_charge": {
        "name": "Energy Storage Battery Daily Charge",
        "translation_key": "storage_battery_daily_charge",
        "icon": "mdi:battery-plus",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled_by_default": True,
    },
    "storage_battery_total_charge": {
        "name": "Energy Storage Battery Total Charge",
        "translation_key": "storage_battery_total_charge",
        "icon": "mdi:battery-plus-outline",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled_by_default": True,
    },
    "storage_battery_daily_discharge": {
        "name": "Energy Storage Battery Daily Discharge",
        "translation_key": "storage_battery_daily_discharge",
        "icon": "mdi:battery-minus",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled_by_default": True,
    },
    "storage_battery_total_discharge": {
        "name": "Energy Storage Battery Total Discharge",
        "translation_key": "storage_battery_total_discharge",
        "icon": "mdi:battery-minus-outline",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled_by_default": True,
    },
}

# Configurable sensor definitions
SENSOR_CONFIGS = {
    "app_firmware_version": {
        "class": "EwayAppFirmwareVersionSensor",
        "name": "App Firmware Version",
        "translation_key": "app_firmware_version",
        "icon": "mdi:chip",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    "charge_current": {
        "class": "EwayChargeCurrentSensor",
        "name": "Charge Current",
        "translation_key": "charge_current",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "enabled_by_default": True,
    },
    "charge_status": {
        "class": "EwayChargeStatusSensor",
        "name": "Charge Status",
        "translation_key": "charge_status",
        "icon": "mdi:battery-charging",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    "gun_status": {
        "class": "EwayGunStatusSensor",
        "name": "Gun Status",
        "translation_key": "gun_status",
        "icon": "mdi:power-plug",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    "pile_status": {
        "class": "EwayPileStatusSensor",
        "name": "Pile Status",
        "translation_key": "pile_status",
        "icon": "mdi:ev-station",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    "mcb_firmware_version": {
        "class": "EwayMcbFirmwareVersionSensor",
        "name": "MCB Firmware Version",
        "translation_key": "mcb_firmware_version",
        "icon": "mdi:chip",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": False,
    },
    "net_firmware_version": {
        "class": "EwayNetFirmwareVersionSensor",
        "name": "Network Firmware Version",
        "translation_key": "net_firmware_version",
        "icon": "mdi:router-wireless",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": False,
    },
    "net_source": {
        "class": "EwayNetSourceSensor",
        "name": "Network Source",
        "translation_key": "net_source",
        "icon": "mdi:network",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": False,
    },
    "wifi_ssid": {
        "class": "EwayWifiSsidSensor",
        "name": "WiFi SSID",
        "translation_key": "wifi_ssid",
        "icon": "mdi:wifi",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": False,
    },
    "work_charge_time": {
        "class": "EwayWorkChargeTimeSensor",
        "name": "Total Charge Time",
        "translation_key": "work_charge_time",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfTime.MINUTES,
        "enabled_by_default": False,
    },
    "work_this_time": {
        "class": "EwayWorkThisTimeSensor",
        "name": "Current Session Time",
        "translation_key": "work_this_time",
        "icon": "mdi:timer-outline",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.MINUTES,
        "enabled_by_default": False,
    },
    "work_total_time": {
        "class": "EwayWorkTotalTimeSensor",
        "name": "Total Work Time",
        "translation_key": "work_total_time",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfTime.MINUTES,
        "enabled_by_default": False,
    },
    "gun_lock": {
        "class": "EwayGunLockSensor",
        "name": "Gun Lock Status",
        "translation_key": "gun_lock",
        "icon": "mdi:lock",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": False,
    },
    "time_zone": {
        "class": "EwayTimeZoneSensor",
        "name": "Time Zone",
        "translation_key": "time_zone",
        "icon": "mdi:clock-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": False,
    },
    # Charging settlement data sensors
    "last_charging_degrees": {
        "class": "EwayChargingSessionSensor",
        "name": "Last Charging Energy",
        "translation_key": "last_charging_degrees",
        "icon": "mdi:lightning-bolt",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled_by_default": True,
    },
    "last_charging_duration": {
        "class": "EwayChargingSessionSensor",
        "name": "Last Charging Duration",
        "translation_key": "last_charging_duration",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.TOTAL,
        "unit": UnitOfTime.MINUTES,
        "enabled_by_default": True,
    },
    "last_charging_start_time": {
        "class": "EwayChargingSessionSensor",
        "name": "Last Charging Start Time",
        "translation_key": "last_charging_start_time",
        "icon": "mdi:clock-start",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    "last_charging_end_time": {
        "class": "EwayChargingSessionSensor",
        "name": "Last Charging End Time",
        "translation_key": "last_charging_end_time",
        "icon": "mdi:clock-end",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    "last_charging_stop_reason": {
        "class": "EwayChargingSessionSensor",
        "name": "Last Charging Stop Reason",
        "translation_key": "last_charging_stop_reason",
        "icon": "mdi:information",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    "last_charging_error_codes": {
        "class": "EwayChargingSessionSensor",
        "name": "Last Charging Error Codes",
        "translation_key": "last_charging_error_codes",
        "icon": "mdi:alert-circle",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    # Device error response sensor
    "device_error_response": {
        "class": "EwayDeviceErrorResponseSensor",
        "name": "Device Error Response",
        "translation_key": "device_error_response",
        "icon": "mdi:alert-circle-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": False,
    },
    # Device status response sensor
    "device_status_responses": {
        "class": "EwayDeviceStatusResponsesSensor",
        "name": "Device Status Responses",
        "translation_key": "device_status_responses",
        "icon": "mdi:message-reply",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    # Device basic status sensors
    "device_charging_status": {
        "class": "EwayDeviceStatusSensor",
        "name": "Device Charging Status",
        "translation_key": "device_charging_status",
        "icon": "mdi:battery-charging",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    "device_gun_status": {
        "class": "EwayDeviceStatusSensor",
        "name": "Device Gun Status",
        "translation_key": "device_gun_status",
        "icon": "mdi:power-plug",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    "device_pile_status": {
        "class": "EwayDeviceStatusSensor",
        "name": "Device Pile Status",
        "translation_key": "device_pile_status",
        "icon": "mdi:ev-station",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "enabled_by_default": True,
    },
    # Charging real-time data sensors
    "realtime_amount": {
        "class": "EwayRealtimeDataSensor",
        "name": "Charging Energy",
        "translation_key": "realtime_amount",
        "icon": "mdi:lightning-bolt",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "enabled_by_default": True,
    },
    "realtime_current": {
        "class": "EwayRealtimeDataSensor",
        "name": "Charging Current",
        "translation_key": "realtime_current",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "enabled_by_default": True,
    },
    "realtime_current_l1": {
        "class": "EwayRealtimeDataSensor",
        "name": "Current L1",
        "translation_key": "realtime_current_l1",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "enabled_by_default": False,
    },
    "realtime_current_l2": {
        "class": "EwayRealtimeDataSensor",
        "name": "Current L2",
        "translation_key": "realtime_current_l2",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "enabled_by_default": False,
    },
    "realtime_current_l3": {
        "class": "EwayRealtimeDataSensor",
        "name": "Current L3",
        "translation_key": "realtime_current_l3",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "enabled_by_default": False,
    },
    "realtime_duration": {
        "class": "EwayRealtimeDataSensor",
        "name": "Charging Duration",
        "translation_key": "realtime_duration",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.SECONDS,
        "enabled_by_default": True,
    },
    "realtime_duty_cycle": {
        "class": "EwayRealtimeDataSensor",
        "name": "CP Duty Cycle",
        "translation_key": "realtime_duty_cycle",
        "icon": "mdi:sine-wave",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "enabled_by_default": False,
    },
    "realtime_imt4g_rssi": {
        "class": "EwayRealtimeDataSensor",
        "name": "4G Signal Strength",
        "translation_key": "realtime_imt4g_rssi",
        "icon": "mdi:signal-cellular-3",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": None,
        "enabled_by_default": False,
    },
    "realtime_moisture": {
        "class": "EwayRealtimeDataSensor",
        "name": "Humidity",
        "translation_key": "realtime_moisture",
        "icon": "mdi:water-percent",
        "device_class": SensorDeviceClass.HUMIDITY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "enabled_by_default": False,
    },
    "realtime_power": {
        "class": "EwayRealtimeDataSensor",
        "name": "Charging Power",
        "translation_key": "realtime_power",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "enabled_by_default": True,
    },
    "realtime_temperature": {
        "class": "EwayRealtimeDataSensor",
        "name": "Temperature",
        "translation_key": "realtime_temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "enabled_by_default": False,
    },
    "realtime_voltage": {
        "class": "EwayRealtimeDataSensor",
        "name": "Voltage",
        "translation_key": "realtime_voltage",
        "icon": "mdi:flash-triangle",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "enabled_by_default": True,
    },
    "realtime_wifi_rssi": {
        "class": "EwayRealtimeDataSensor",
        "name": "WiFi Signal Strength",
        "translation_key": "realtime_wifi_rssi",
        "icon": "mdi:wifi",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": None,
        "enabled_by_default": False,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    # Set up charger sensors for charger devices
    if coordinator.device_type == "charger":
        _LOGGER.debug("Setting up charger sensors for device type: %s", coordinator.device_type)

        # Get user-configured sensor options, use default enabled sensors if not configured
        enabled_sensors = config_entry.options.get("enabled_sensors", [])
        if not enabled_sensors:
            # If not configured, use default enabled sensors
            enabled_sensors = [
                key
                for key, config in SENSOR_CONFIGS.items()
                if config["enabled_by_default"]
            ]

        for sensor_key in enabled_sensors:
            if sensor_key in SENSOR_CONFIGS:
                config = SENSOR_CONFIGS[sensor_key]
                sensor_class = globals()[config["class"]]
                entities.append(sensor_class(coordinator, sensor_key, config))

    # Set up storage sensors for energy storage devices
    elif coordinator.device_type == "energy_storage":
        _LOGGER.debug("Setting up storage sensors for device type: %s", coordinator.device_type)

        # Get enabled storage sensors from config entry options
        enabled_storage_sensors = config_entry.options.get("enabled_storage_sensors", [])
        if not enabled_storage_sensors:
            # If not configured, use all storage sensors as default
            enabled_storage_sensors = list(STORAGE_SENSOR_CONFIGS.keys())

        # Storage sensor class mapping
        storage_sensor_classes = {
            "storage_timestamp": EwayStorageTimestampSensor,
            "storage_protocol_version": EwayStorageProtocolVersionSensor,
            "storage_output_power": EwayStorageOutputPowerSensor,
            "storage_pv_power": EwayStoragePvPowerSensor,
            "storage_pv_daily_generation": EwayStoragePvDailyGenerationSensor,
            "storage_pv_total_generation": EwayStoragePvTotalGenerationSensor,
            "storage_battery_power": EwayStorageBatteryPowerSensor,
            "storage_battery_soc": EwayStorageBatterySocSensor,
            "storage_battery_daily_charge": EwayStorageBatteryDailyChargeSensor,
            "storage_battery_total_charge": EwayStorageBatteryTotalChargeSensor,
            "storage_battery_daily_discharge": EwayStorageBatteryDailyDischargeSensor,
            "storage_battery_total_discharge": EwayStorageBatteryTotalDischargeSensor,
        }

        for sensor_key in enabled_storage_sensors:
            if sensor_key in STORAGE_SENSOR_CONFIGS and sensor_key in storage_sensor_classes:
                config = STORAGE_SENSOR_CONFIGS[sensor_key]
                sensor_class = storage_sensor_classes[sensor_key]
                entities.append(sensor_class(coordinator, sensor_key, config))

    else:
        _LOGGER.debug("Unknown device type: %s, skipping sensor setup", coordinator.device_type)

    async_add_entities(entities)


class EwayChargerSensorEntity(CoordinatorEntity, SensorEntity):
    """Base class for Eway Charger sensor entities."""

    def __init__(
        self,
        coordinator: EwayChargerCoordinator,
        sensor_key: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._config = config
        self._attr_unique_id = f"{coordinator.device_id}_{sensor_key}"
        # self._attr_name = config["name"]  # Only show sensor name, not including DOMAIN and device ID
        self._attr_has_entity_name = True
        self._attr_translation_key = config.get("translation_key")
        self._attr_icon = config["icon"]
        if config["device_class"]:
            self._attr_device_class = config["device_class"]
        if config["state_class"]:
            self._attr_state_class = config["state_class"]
        if config["unit"]:
            self._attr_native_unit_of_measurement = config["unit"]

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

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.connected and super().available

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


# Status mapping dictionary
CHARGE_STATUS_MAP = {0: "not_charging", 1: "charging", 2: "charge_complete"}

GUN_STATUS_MAP = {0: "not_inserted", 1: "inserted"}

PILE_STATUS_MAP = {0: "idle", 1: "charging", 2: "fault"}

NET_SOURCE_MAP = {
    1: "wifi",
    2: "4g",
    3: "ethernet",
    4: "wifi_4g",
    5: "wifi_ethernet",
    6: "4g_ethernet",
    7: "wifi_4g_ethernet",
}

GUN_LOCK_MAP = {0: "unlocked", 1: "locked"}

# Device status mapping dictionary
DEVICE_CHARGING_STATUS_MAP = {0: "not_charging", 1: "charging", 2: "charge_complete"}

DEVICE_GUN_STATUS_MAP = {0: "not_inserted", 1: "inserted"}

DEVICE_PILE_STATUS_MAP = {0: "idle", 1: "charging", 2: "fault"}


class EwayAppFirmwareVersionSensor(EwayChargerSensorEntity):
    """App firmware version sensor."""

    @property
    def native_value(self) -> str | None:
        """Return the app firmware version."""
        version = self._get_device_info_value("appFirmVer")
        return str(version) if version is not None else None


class EwayChargeCurrentSensor(EwayChargerSensorEntity):
    """Charge current sensor."""

    @property
    def native_value(self) -> float | None:
        """Return the charge current."""
        return self._get_device_info_value("chargCurrent")


class EwayChargeStatusSensor(EwayChargerSensorEntity):
    """Charge status sensor."""

    @property
    def native_value(self) -> str | None:
        """Return the charge status."""
        status = self._get_device_info_value("chargeStatus")
        return CHARGE_STATUS_MAP.get(status, "unknown") if status is not None else None


class EwayGunStatusSensor(EwayChargerSensorEntity):
    """Gun status sensor."""

    @property
    def native_value(self) -> str | None:
        """Return the gun status."""
        status = self._get_device_info_value("gunStatus")
        return GUN_STATUS_MAP.get(status, "unknown") if status is not None else None


class EwayPileStatusSensor(EwayChargerSensorEntity):
    """Pile status sensor."""

    @property
    def native_value(self) -> str | None:
        """Return the pile status."""
        status = self._get_device_info_value("pileStatus")
        return PILE_STATUS_MAP.get(status, "unknown") if status is not None else None


class EwayMcbFirmwareVersionSensor(EwayChargerSensorEntity):
    """MCB firmware version sensor."""

    @property
    def native_value(self) -> str | None:
        """Return the MCB firmware version."""
        version = self._get_device_info_value("mcbFirmVer")
        return str(version) if version is not None else None


class EwayNetFirmwareVersionSensor(EwayChargerSensorEntity):
    """Network firmware version sensor."""

    @property
    def native_value(self) -> str | None:
        """Return the network firmware version."""
        return self._get_device_info_value("netFirmVer")


class EwayNetSourceSensor(EwayChargerSensorEntity):
    """Network source sensor."""

    @property
    def native_value(self) -> str | None:
        """Return the network source."""
        source = self._get_device_info_value("netSource")
        return NET_SOURCE_MAP.get(source, "unknown") if source is not None else None


class EwayWifiSsidSensor(EwayChargerSensorEntity):
    """WiFi SSID sensor."""

    @property
    def native_value(self) -> str | None:
        """Return the WiFi SSID."""
        return self._get_device_info_value("wifiSsid")


class EwayWorkChargeTimeSensor(EwayChargerSensorEntity):
    """Work charge time sensor."""

    @property
    def native_value(self) -> int | None:
        """Return the total charge time in minutes."""
        return self._get_device_info_value("workCharg")


class EwayWorkThisTimeSensor(EwayChargerSensorEntity):
    """Work this time sensor."""

    @property
    def native_value(self) -> int | None:
        """Return the current session time in minutes."""
        return self._get_device_info_value("workThis")


class EwayWorkTotalTimeSensor(EwayChargerSensorEntity):
    """Work total time sensor."""

    @property
    def native_value(self) -> int | None:
        """Return the total work time in minutes."""
        return self._get_device_info_value("workTotal")


class EwayGunLockSensor(EwayChargerSensorEntity):
    """Gun lock sensor."""

    @property
    def native_value(self) -> str | None:
        """Return the gun lock status."""
        status = self._get_device_info_value("gunLock")
        return GUN_LOCK_MAP.get(status, "unknown") if status is not None else None


class EwayNetworkWaySensor(EwayChargerSensorEntity):
    """Network way sensor."""

    @property
    def native_value(self) -> str | None:
        """Return the network mode."""
        way = self._get_device_info_value("networkWay")
        return "unknown" if way is None else str(way)


class EwayDeviceStatusSensor(EwayChargerSensorEntity):
    """Device status sensor for real-time status updates."""

    def _get_device_status_value(self, key: str) -> Any:
        """Get value from device status data."""
        if not self.coordinator.data or "device_status" not in self.coordinator.data:
            return None
        return self.coordinator.data["device_status"].get(key)

    @property
    def native_value(self) -> str | None:
        """Return the device status value."""
        if self._sensor_key == "device_charging_status":
            status = self._get_device_status_value("charging_status")
            return (
                DEVICE_CHARGING_STATUS_MAP.get(status, "unknown")
                if status is not None
                else None
            )
        if self._sensor_key == "device_gun_status":
            status = self._get_device_status_value("gun_status")
            return (
                DEVICE_GUN_STATUS_MAP.get(status, "unknown")
                if status is not None
                else None
            )
        if self._sensor_key == "device_pile_status":
            status = self._get_device_status_value("pile_status")
            return (
                DEVICE_PILE_STATUS_MAP.get(status, "unknown")
                if status is not None
                else None
            )
        return None


class EwayRealtimeDataSensor(EwayChargerSensorEntity):
    """Real-time charging data sensor."""

    def _get_realtime_data_value(self, key: str) -> Any:
        """Get value from charging real-time data."""
        if (
            not self.coordinator.data
            or "charging_realtime" not in self.coordinator.data
        ):
            return None
        return self.coordinator.data["charging_realtime"].get(key)

    @property
    def native_value(self) -> float | int | None:
        """Return the real-time data value."""
        key_mapping = {
            "realtime_amount": "amount",
            "realtime_current": "current",
            "realtime_current_l1": "current_l1",
            "realtime_current_l2": "current_l2",
            "realtime_current_l3": "current_l3",
            "realtime_duration": "duration",
            "realtime_duty_cycle": "duty_cycle",
            "realtime_imt4g_rssi": "imt4g_rssi",
            "realtime_moisture": "moisture",
            "realtime_power": "power",
            "realtime_temperature": "temperature",
            "realtime_voltage": "voltage",
            "realtime_wifi_rssi": "wifi_rssi",
        }

        data_key = key_mapping.get(self._sensor_key)
        if data_key:
            value = self._get_realtime_data_value(data_key)
            # Handle special values: signal strength -1 means unavailable
            if self._sensor_key in ["realtime_imt4g_rssi", "realtime_wifi_rssi"] and value == -1:
                return None
            return value
        return None


class EwayTimeZoneSensor(EwayChargerSensorEntity):
    """Time zone sensor."""

    @property
    def native_value(self) -> int | None:
        """Return the time zone."""
        return self._get_device_info_value("timeZone")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        timezone = self._get_device_info_value("timeZone")
        if timezone is not None:
            # Convert to standard timezone format (timezone - 100)
            offset = timezone - 100
            return {
                "timezone_offset": offset,
                "timezone_description": f"UTC{'+' if offset >= 0 else ''}{offset}",
            }
        return None


class EwayChargingSessionSensor(EwayChargerSensorEntity):
    """Sensor for charging session data."""

    StateType = str | int | float | None | datetime | Decimal

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        # Get charging session data
        if (
            not self.coordinator.data
            or "last_charging_session" not in self.coordinator.data
        ):
            return None

        charging_session = self.coordinator.data["last_charging_session"]

        if self._sensor_key == "last_charging_degrees":
            return charging_session.get("degrees")
        if self._sensor_key == "last_charging_duration":
            return charging_session.get("duration")
        if self._sensor_key == "last_charging_start_time":
            timestamp = charging_session.get("start_time")
            if timestamp:
                return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            return None
        if self._sensor_key == "last_charging_end_time":
            timestamp = charging_session.get("end_time")
            if timestamp:
                return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            return None
        if self._sensor_key == "last_charging_stop_reason":
            stop_reason = charging_session.get("stop_reason") or "Normal"
            # Map original stop reason to standardized status values to support translation system
            reason_mapping = {
                "Normal": "normal",
                "User Stop": "user_stop",
                "User": "user_stop",
                "Emergency Stop": "emergency_stop",
                "Emergency": "emergency_stop",
                "Fault": "fault",
                "Fault Stop": "fault",
                "Timeout": "timeout",
                "Timeout Stop": "timeout",
                "Overheat": "overheat",
                "Overheat Stop": "overheat",
                "Overcurrent": "overcurrent",
                "Overcurrent Stop": "overcurrent",
                "Undervoltage": "undervoltage",
                "Undervoltage Stop": "undervoltage",
                "Overvoltage": "overvoltage",
                "Overvoltage Stop": "overvoltage",
            }
            return reason_mapping.get(stop_reason, "unknown")
        if self._sensor_key == "last_charging_error_codes":
            error_codes = charging_session.get("error_codes", [])
            if error_codes:
                return ", ".join(map(str, error_codes))
            return "None"

        return None


class EwayDeviceErrorResponseSensor(EwayChargerSensorEntity):
    """Sensor for device error response data."""

    @property
    def native_value(self) -> str | None:
        """Return the device error response status."""
        if (
            not self.coordinator.data
            or "device_error_response" not in self.coordinator.data
        ):
            return None

        response_data = self.coordinator.data["device_error_response"]
        error_codes = response_data.get("error_codes", [])

        # Return error code count
        if error_codes:
            return f"{len(error_codes)}_errors"
        else:
            return "no_errors"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if (
            not self.coordinator.data
            or "device_error_response" not in self.coordinator.data
        ):
            return None

        response_data = self.coordinator.data["device_error_response"]
        error_codes = response_data.get("error_codes", [])

        attributes = {
            "command_id": response_data.get("id"),
            "raw_value": response_data.get("value"),
            "error_codes": error_codes,
            "error_count": len(error_codes),
            "user_id": response_data.get("user_id"),
            "response_timestamp": response_data.get("timestamp"),
        }

        # Add separate attributes for each error code for easy use in automation
        for i, code in enumerate(error_codes):
            attributes[f"error_code_{i + 1}"] = code

        return attributes

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and "last_charging_session" in self.coordinator.data
        )


class EwayDeviceStatusResponsesSensor(EwayChargerSensorEntity):
    """Device status response sensor class."""

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if (
            not self.coordinator.data
            or "device_status_responses" not in self.coordinator.data
        ):
            return None

        responses = self.coordinator.data["device_status_responses"]
        if not responses:
            return None

        # Return latest status change summary
        status_count = len(responses)
        return f"{status_count}_status_changes"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if (
            not self.coordinator.data
            or "device_status_responses" not in self.coordinator.data
        ):
            return None

        responses = self.coordinator.data["device_status_responses"]
        if not responses:
            return None

        # Build status change details
        status_details = {}
        status_mapping = {
            "gun-status": {"name": "gun_status", "values": {"0": "disconnected", "1": "connected"}},
            "charge-status": {
                "name": "charge_status",
                "values": {"0": "not_charging", "1": "charging", "2": "charge_complete"},
            },
            "pile-status": {
                "name": "pile_status",
                "values": {"0": "idle", "1": "charging", "2": "fault"},
            },
        }

        for response in responses:
            status_id = response.get("id")
            value = response.get("value")
            remark = response.get("remark")

            if status_id in status_mapping:
                mapping = status_mapping[status_id]
                status_text = mapping["values"].get(value, f"unknown_{value}")

                status_details[f"{mapping['name']}_value"] = value
                status_details[f"{mapping['name']}_text"] = status_text
                status_details[f"{mapping['name']}_remark"] = remark

        # Add general information
        if responses:
            first_response = responses[0]
            status_details.update(
                {
                    "response_count": len(responses),
                    "user_id": first_response.get("user_id", ""),
                    "response_timestamp": first_response.get("timestamp"),
                }
            )

        return status_details


# Storage sensor base class and specific sensor classes
class EwayStorageSensorEntity(EwayChargerSensorEntity):
    """Base class for Eway storage sensors."""

    def __init__(
        self,
        coordinator: EwayChargerCoordinator,
        sensor_key: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize the storage sensor."""
        super().__init__(coordinator, sensor_key, config)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_available = (
            self.coordinator.last_update_success
            and self.coordinator.device_type == "energy_storage"
            and self.coordinator.data is not None
            and "storage_mini" in self.coordinator.data
        )
        _LOGGER.debug(
            "Storage sensor %s availability check: last_update_success=%s, device_type=%s, storage_mini_exists=%s",
            self._sensor_key,
            self.coordinator.last_update_success,
            self.coordinator.device_type,
            "storage_mini" in (self.coordinator.data or {}),
        )
        return is_available

    def _get_storage_data_value(self, key: str) -> Any:
        """Get value from storage data."""
        if not self.coordinator.data or "storage_mini" not in self.coordinator.data:
            _LOGGER.debug("Getting storage data for key %s: No storage data available", key)
            return None

        storage_data = self.coordinator.data["storage_mini"]
        value = storage_data.get(key)
        _LOGGER.debug("Getting storage data for key %s: %s", key, value)
        return value


class EwayStorageTimestampSensor(EwayStorageSensorEntity):
    """Storage timestamp sensor."""

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp value."""
        timestamp = self._get_storage_data_value("timestamp")
        if timestamp:
            try:
                # Convert timestamp to datetime
                dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                _LOGGER.debug("Storage timestamp sensor value: %s (from %s)", dt, timestamp)
                return dt
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to convert timestamp %s: %s", timestamp, e)
                return None
        return None


class EwayStorageProtocolVersionSensor(EwayStorageSensorEntity):
    """Storage protocol version sensor."""

    @property
    def native_value(self) -> str | None:
        """Return the protocol version."""
        version = self._get_storage_data_value("protocol_version")
        _LOGGER.debug("Storage protocol version sensor value: %s", version)
        return str(version) if version is not None else None


class EwayStorageOutputPowerSensor(EwayStorageSensorEntity):
    """Storage output power sensor."""

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return 1

    @property
    def native_value(self) -> float | None:
        """Return the output power value."""
        power = self._get_storage_data_value("output_power")
        if power is not None:
            try:
                power_value = float(power)
                _LOGGER.debug("Storage output power sensor value: %s W (from %s)", power_value, power)
                return power_value
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to convert output power %s to float: %s", power, e)
                return None
        return None


class EwayStoragePvPowerSensor(EwayStorageSensorEntity):
    """Storage PV power sensor."""

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return 1

    @property
    def native_value(self) -> float | None:
        """Return the PV power value."""
        pv_power = self._get_storage_data_value("pv_power")
        if pv_power is not None:
            try:
                pv_power_value = float(pv_power)
                _LOGGER.debug("Storage PV power sensor value: %s W (from %s)", pv_power_value, pv_power)
                return pv_power_value
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to convert PV power %s to float: %s", pv_power, e)
                return None
        return None


class EwayStorageBatteryPowerSensor(EwayStorageSensorEntity):
    """Storage battery power sensor."""

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return 1

    @property
    def native_value(self) -> float | None:
        """Return the battery power value."""
        battery_power = self._get_storage_data_value("battery_power")
        if battery_power is not None:
            try:
                battery_power_value = float(battery_power)
                _LOGGER.debug("Storage battery power sensor value: %s W (from %s)", battery_power_value, battery_power)
                return battery_power_value
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to convert battery power %s to float: %s", battery_power, e)
                return None
        return None


class EwayStorageBatterySocSensor(EwayStorageSensorEntity):
    """Storage battery SOC sensor."""

    @property
    def native_value(self) -> float | None:
        """Return the battery SOC value."""
        soc = self._get_storage_data_value("battery_soc")
        if soc is not None:
            try:
                soc_value = float(soc)
                _LOGGER.debug("Storage battery SOC sensor value: %s%% (from %s)", soc_value, soc)
                return soc_value
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to convert battery SOC %s to float: %s", soc, e)
                return None
        return None


class EwayStoragePvDailyGenerationSensor(EwayStorageSensorEntity):
    """Storage PV daily generation sensor."""

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return 2

    @property
    def native_value(self) -> float | None:
        """Return the PV daily generation value."""
        daily_gen = self._get_storage_data_value("pv_daily_generation")
        if daily_gen is not None:
            try:
                daily_gen_value = float(daily_gen)
                _LOGGER.debug("Storage PV daily generation sensor value: %s kWh (from %s)", daily_gen_value, daily_gen)
                return daily_gen_value
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to convert PV daily generation %s to float: %s", daily_gen, e)
                return None
        return None


class EwayStoragePvTotalGenerationSensor(EwayStorageSensorEntity):
    """Storage PV total generation sensor."""

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return 2

    @property
    def native_value(self) -> float | None:
        """Return the PV total generation value."""
        total_gen = self._get_storage_data_value("pv_total_generation")
        if total_gen is not None:
            try:
                total_gen_value = float(total_gen)
                _LOGGER.debug("Storage PV total generation sensor value: %s kWh (from %s)", total_gen_value, total_gen)
                return total_gen_value
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to convert PV total generation %s to float: %s", total_gen, e)
                return None
        return None


class EwayStorageBatteryDailyChargeSensor(EwayStorageSensorEntity):
    """Storage battery daily charge sensor."""

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return 2

    @property
    def native_value(self) -> float | None:
        """Return the battery daily charge value."""
        daily_charge = self._get_storage_data_value("battery_daily_charge")
        if daily_charge is not None:
            try:
                daily_charge_value = float(daily_charge)
                _LOGGER.debug("Storage battery daily charge sensor value: %s kWh (from %s)", daily_charge_value, daily_charge)
                return daily_charge_value
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to convert battery daily charge %s to float: %s", daily_charge, e)
                return None
        return None


class EwayStorageBatteryTotalChargeSensor(EwayStorageSensorEntity):
    """Storage battery total charge sensor."""

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return 2

    @property
    def native_value(self) -> float | None:
        """Return the battery total charge value."""
        total_charge = self._get_storage_data_value("battery_total_charge")
        if total_charge is not None:
            try:
                total_charge_value = float(total_charge)
                _LOGGER.debug("Storage battery total charge sensor value: %s kWh (from %s)", total_charge_value, total_charge)
                return total_charge_value
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to convert battery total charge %s to float: %s", total_charge, e)
                return None
        return None


class EwayStorageBatteryDailyDischargeSensor(EwayStorageSensorEntity):
    """Storage battery daily discharge sensor."""

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return 2

    @property
    def native_value(self) -> float | None:
        """Return the battery daily discharge value."""
        daily_discharge = self._get_storage_data_value("battery_daily_discharge")
        if daily_discharge is not None:
            try:
                daily_discharge_value = float(daily_discharge)
                _LOGGER.debug("Storage battery daily discharge sensor value: %s kWh (from %s)", daily_discharge_value, daily_discharge)
                return daily_discharge_value
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to convert battery daily discharge %s to float: %s", daily_discharge, e)
                return None
        return None


class EwayStorageBatteryTotalDischargeSensor(EwayStorageSensorEntity):
    """Storage battery total discharge sensor."""

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return 2

    @property
    def native_value(self) -> float | None:
        """Return the battery total discharge value."""
        total_discharge = self._get_storage_data_value("battery_total_discharge")
        if total_discharge is not None:
            try:
                total_discharge_value = float(total_discharge)
                _LOGGER.debug("Storage battery total discharge sensor value: %s kWh (from %s)", total_discharge_value, total_discharge)
                return total_discharge_value
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to convert battery total discharge %s to float: %s", total_discharge, e)
                return None
        return None
