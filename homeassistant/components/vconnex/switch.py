from typing import Any


from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.components.switch import (
    DEVICE_CLASS_SWITCH,
    SwitchEntity,
    SwitchEntityDescription,
    DEVICE_CLASS_OUTLET,
)

from .py_vconnex.device import VconnexDevice, VconnexDeviceManager
from .const import DOMAIN, DeviceParam, DispatcherSignal, ParamType
from . import HomeAssistantVconnexData
from .entity import VconnexEntity


import logging

logger = logging.getLogger(__name__)


SUPPORTED_DEVICE_TYPE_LIST = [3017, 3018]


def get_entity_description_list(
    device: VconnexDevice, param_type: int, device_class: str
) -> list:
    """Get entity description base on device params."""
    description_list = []
    if device is not None and len(param_list := device.params) > 0:
        for param in param_list:
            if param.get("type", 0) == param_type:
                description_list.append(
                    SwitchEntityDescription(
                        key=param.get("paramKey"),
                        name=param.get("name"),
                        unit_of_measurement=param.get("unit", ""),
                        device_class=device_class,
                    )
                )
    return description_list


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup Vconnex device."""
    vconnex_data: HomeAssistantVconnexData = hass.data[DOMAIN][entry.entry_id]
    device_manager = vconnex_data.device_manager

    @callback
    def on_device_added(device_ids: list[str]) -> None:
        """Device added callback"""

        entities: list[Entity] = []
        for device_id in device_ids:
            device = device_manager.device_map[device_id]
            if (
                device.deviceTypeCode in SUPPORTED_DEVICE_TYPE_LIST
                and len(
                    description_list := get_entity_description_list(
                        device, ParamType.ON_OFF, DEVICE_CLASS_SWITCH
                    )
                )
                > 0
            ):
                for description in description_list:
                    if True or description.key in device.params:
                        entities.append(
                            VconnexSwitchEntity(device, device_manager, description)
                        )
        async_add_entities(entities)

    async_dispatcher_connect(hass, DispatcherSignal.DEVICE_ADDED, on_device_added)
    on_device_added(device_ids=device_manager.device_map.keys())


class VconnexSwitchEntity(VconnexEntity, SwitchEntity):
    """Vconnex Switch Device."""

    def __init__(
        self,
        device: VconnexDevice,
        device_manager: VconnexDeviceManager,
        description: SwitchEntityDescription,
    ) -> None:
        """Init."""
        super().__init__(
            device=device, device_manager=device_manager, description=description
        )
        self._attr_unique_id = f"{super().unique_id}.{description.key}"
        self.entity_id = self._attr_unique_id

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        try:
            param = self.entity_description.key
            device_data = self.device.data
            if "CmdGetData" in device_data:
                msg_dict = self.device.data.get("CmdGetData")
                if "devV" in msg_dict:
                    values = msg_dict.get("devV")
                    for value in values:
                        if value.get("param") == param:
                            return True if value.get("value", 0) != 0 else False
        except Exception:
            logger.exception("Something went wrong!!!")

        return False

    def turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._send_command("CmdSetData", {self.entity_description.key: 1})

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._send_command("CmdSetData", {self.entity_description.key: 0})
