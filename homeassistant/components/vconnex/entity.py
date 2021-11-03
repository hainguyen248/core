"""Vconnex integration"""

from typing import Any

from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity, EntityDescription

from .py_vconnex.device import VconnexDevice, VconnexDeviceManager
from .const import DOMAIN, DispatcherSignal

import logging

logger = logging.getLogger(__name__)


class VconnexEntity(Entity):
    """Vconnex Entity"""

    def __init__(
        self,
        device: VconnexDevice,
        device_manager: VconnexDeviceManager,
        description: EntityDescription,
    ) -> None:
        """Init base entity class."""

        self.device = device
        self.device_manager = device_manager
        self.entity_description = description

        self._attr_unique_id = f"vconnex.{device.deviceId}"

    @property
    def name(self) -> str:
        return (
            f"[{self.device.name}] {self.entity_description.name}"
            if (
                self.entity_description is not None
                and self.entity_description.name is not None
            )
            else self.device.name
        )

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.device.deviceId)},
            manufacturer="Vconnex",
            name=self.device.name,
            model=f"[{self.device.deviceTypeCode}] {self.device.deviceTypeName}",
            sw_version=(
                self.device.version if hasattr(self.device, "version") else None
            ),
        )

    @property
    def available(self) -> bool:
        return True
        # return self.device.online

    async def async_added_to_hass(self) -> None:
        """Call when entity is added."""
        async_dispatcher_connect(
            self.hass,
            f"{DispatcherSignal.DEVICE_UPDATED}.{self.device.deviceId}",
            self.async_write_ha_state,
        )

    def _send_command(self, command: str, values: dict[str, Any]) -> None:
        logger.debug("Sending commands for device %s: %s", self.device.deviceId, values)
        self.device_manager.send_commands(self.device.deviceId, command, values)
