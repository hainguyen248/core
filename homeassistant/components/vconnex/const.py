"""Constants for the Vconnex integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


DOMAIN = "vconnex"

PLATFORMS = [
    "switch",
]

DEFAULT_ENDPOINT = "https://hass-api.vconnex.vn"
DEFAULT_ENDPOINT = "https://hass-api-stg.vconnex.vn/hass-api"


CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_USER_NAME = "user_name"
CONF_PASSWORD = "password"
CONF_ENDPOINT = "endpoint"
CONF_COUNTRY = "country"


@dataclass
class Country:
    name: str
    country_code: str
    endpoint: str = DEFAULT_ENDPOINT


COUNTRY_LIST = [
    Country("Vietnam", "84"),
]


class DispatcherSignal:
    """DispatcherSignal."""

    DEVICE_ADDED = "vconnex.device_added"
    DEVICE_UPDATED = "vconnex.device_updated"


class ParamType:
    """ParamType"""

    ON_OFF = 1
    OPEN_CLOSE = 2
    YES_NO = 3
    ALERT = 4
    RAW_VALUE = 6


class DeviceParam:
    """Device param code"""

    SWITCH_1 = "switch_1"
    SWITCH_2 = "switch_2"
    SWITCH_3 = "switch_3"
    SWITCH_4 = "switch_4"
