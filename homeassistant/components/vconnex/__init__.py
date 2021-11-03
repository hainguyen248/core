"""The Vconnex integration."""
from __future__ import annotations
from typing import NamedTuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send, dispatcher_send

from .py_vconnex.api import VconnexAPI
from .py_vconnex.device import (
    VconnexDevice,
    VconnexDeviceListener,
    VconnexDeviceManager,
)

from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_ENDPOINT,
    DOMAIN,
    PLATFORMS,
    DispatcherSignal,
)

import logging

logger = logging.getLogger(__name__)


class HomeAssistantVconnexData(NamedTuple):
    """Home Assistant data for Vconnex domain."""

    client_id: str
    device_manager: VconnexDeviceManager


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup Vconnex from a config entry."""

    if DOMAIN not in hass.data:
        hass.data.setdefault(DOMAIN, {})

    vconnex_data = await init_sdk(hass, entry)
    if vconnex_data is None:
        return False

    hass.data[DOMAIN][entry.entry_id] = vconnex_data

    device_manager = vconnex_data.device_manager
    device_manager.add_device_listener(DeviceListener(hass, device_manager))
    update_device_registry(hass, entry, device_manager)

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        vconnex_data = hass.data[DOMAIN][entry.entry_id]
        vconnex_data.device_manager.release()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def init_sdk(hass: HomeAssistant, entry: ConfigEntry) -> HomeAssistantVconnexData:
    """Init vconnex sdk."""
    api = VconnexAPI(
        endpoint=entry.data[CONF_ENDPOINT],
        client_id=entry.data[CONF_CLIENT_ID],
        client_secret=entry.data[CONF_CLIENT_SECRET],
        project_code="HASS",
    )

    if not await hass.async_add_executor_job(api.is_valid):
        logger.error("Cannot connect!")
        return None

    device_manager = VconnexDeviceManager(api)
    await hass.async_add_executor_job(device_manager.initialize)
    if not device_manager.is_initialized:
        return None

    return HomeAssistantVconnexData(
        client_id=api.client_id, device_manager=device_manager
    )


def update_device_registry(
    hass: HomeAssistant, entry: ConfigEntry, device_manager: VconnexDeviceManager
):
    """Update device registry for all device include unsupported platform"""

    # device_reg = device_registry.async_get(hass)

    # # Remove device
    # for device_id, device_entry in list(device_reg.devices.items()):
    #     for item in device_entry.identifiers:
    #         if DOMAIN == item[0] and item[1] not in device_manager.device_map:
    #             device_reg.async_remove_device(device_id)
    #             break

    # # Add new device
    # for device in device_manager.device_map.values():
    #     device_reg.async_get_or_create(
    #         config_entry_id=entry.entry_id,
    #         identifiers={(DOMAIN, device.deviceId)},
    #         manufacturer="Vconnex",
    #         name=device.name,
    #         model=f"[{device.deviceTypeCode}] {device.deviceTypeName}",
    #     )


class DeviceListener(VconnexDeviceListener):
    """DeviceListener for HomeAssistan"""

    def __init__(self, hass: HomeAssistant, device_manager: VconnexDeviceManager):
        self.hass = hass
        self.device_manager = device_manager

    def on_device_added(self, device: VconnexDevice):
        dispatcher_send(
            self.hass, f"{DispatcherSignal.DEVICE_ADDED}", [device.deviceId]
        )

    def on_device_removed(self, device: VconnexDevice):
        return super().on_device_removed(device)

    def on_device_update(
        self, new_device: VconnexDevice, old_device: VconnexDevice = None
    ):
        dispatcher_send(
            self.hass, f"{DispatcherSignal.DEVICE_UPDATED}.{new_device.deviceId}"
        )
