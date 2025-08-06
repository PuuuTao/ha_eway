"""Device discovery module for Eway Charger integration."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class EwayDeviceInfo:
    """Information about discovered Eway device."""

    def __init__(
        self, name: str, host: str, port: int, properties: dict[str, Any] | None = None
    ) -> None:
        """Initialize device info."""
        self.name = name
        self.host = host
        self.port = port
        self.properties = properties or {}

        # Extract device_id and device_sn from name, and determine device type
        self.device_id, self.device_sn, self.device_type = self._parse_device_info_from_name(name)

    def _parse_device_info_from_name(self, name: str) -> tuple[str, str, str]:
        """Parse device ID, SN and device type from mDNS service name.

        Expected formats:
        - Charger: EwayCS-TFT-{device_id}/{device_sn}._http._tcp.local.
          Example: EwayCS-TFT-ZAU207T-CS-01-GEQ/252401530._http._tcp.local.
        - Energy Storage: EwayEnergyStorage-{sn}._http._tcp.local.
          Example: EwayEnergyStorage-12345._http._tcp.local.

        Returns:
            tuple: (device_id, device_sn, device_type)

        """
        try:
            # Remove the service type suffix
            if "._http._tcp.local." in name:
                name_part = name.replace("._http._tcp.local.", "")
            else:
                name_part = name

            # Check if it's a charger device
            if name_part.startswith("EwayCS-TFT-"):
                # Remove the prefix
                remaining = name_part[len("EwayCS-TFT-") :]

                # Split by '_' to get device_id and device_sn
                if "_" in remaining:
                    device_id, device_sn = remaining.split("_", 1)
                    return device_id.strip(), device_sn.strip(), "charger"

                # Fallback: if no '_', try to extract from properties or use name
                _LOGGER.warning("Unable to parse device ID and SN from charger name %s, format mismatch", name)
                return "unknown", "unknown", "charger"

            # Check if it's an energy storage device
            elif name_part.startswith("EwayEnergyStorage-"):
                # Remove the prefix
                remaining = name_part[len("EwayEnergyStorage-") :]

                # For energy storage, the remaining part is the SN
                device_sn = remaining.strip()
                # Energy storage devices don't have device_id, only SN
                return "", device_sn, "energy_storage"

            _LOGGER.warning("Device name %s does not start with expected prefix", name)
            return "unknown", "unknown", "unknown"  # noqa: TRY300

        except Exception as exc:  # noqa: BLE001  # check which device error
            _LOGGER.error("Error parsing device name %s: %s", name, exc)
            return "unknown", "unknown", "unknown"

    @property
    def device_id_property(self) -> str:
        """Get device ID from properties or parsed name."""
        return self.properties.get("device_id", self.device_id)

    @property
    def device_sn_property(self) -> str:
        """Get device SN from properties or parsed name."""
        return self.properties.get("device_sn", self.device_sn)

    @property
    def device_type_property(self) -> str:
        """Get device type from parsed name."""
        return self.device_type

    def __repr__(self) -> str:
        """Return string representation."""
        return f"EwayDeviceInfo(name={self.name}, host={self.host}, port={self.port}, device_id={self.device_id}, device_sn={self.device_sn}, device_type={self.device_type})"
