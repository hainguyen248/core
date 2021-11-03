"""Config flow for Vconnex integration."""
from __future__ import annotations

import logging
from typing import Any
from .py_vconnex.api import VconnexAPI

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_COUNTRY,
    CONF_ENDPOINT,
    DEFAULT_ENDPOINT,
    DOMAIN,
)

logger = logging.getLogger(__name__)

# TODO adjust the data schema to the data that you need
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
        vol.Required(CONF_ENDPOINT): str,
    }
)


class PlaceholderHub:
    def __init__(self, host: str) -> None:
        self.host = host

    def authenticate(self, client_id: str, client_secret: str) -> bool:
        """Athenticate"""
        api1 = VconnexAPI(self.host, client_id, client_secret)
        return api1.is_valid()


def validate_input(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # TODO validate the data can be used to set up a connection.

    # If your PyPI package is not built with async, pass your methods
    # to the executor:
    # await hass.async_add_executor_job(
    #     your_validate_func, data["username"], data["password"]
    # )

    user_input[CONF_ENDPOINT] = DEFAULT_ENDPOINT
    endpoint = user_input.get(CONF_ENDPOINT, None)
    client_id = user_input.get(CONF_CLIENT_ID, None)
    client_secret = user_input.get(CONF_CLIENT_SECRET, None)

    if any(val is None for val in (endpoint, client_id, client_secret)):
        return None

    if (
        DOMAIN in hass.data
        and len(datas := hass.data[DOMAIN].values())
        and client_id in map(lambda data: data.client_id, datas)
    ):
        raise CredentialUsed

    hub = PlaceholderHub(endpoint)

    try:
        if not hub.authenticate(client_id, client_secret):
            raise InvalidAuth
    except Exception:
        raise CannotConnect from Exception

    # If you cannot connect:
    # throw CannotConnect
    # If the authentication is wrong:
    # InvalidAuth

    # Return info that you want to store in the config entry.
    return {"title": f"Vconnex {client_id}"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vconnex."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:

        errors = {}
        if user_input is not None:
            try:
                info = await self.hass.async_add_executor_job(
                    validate_input, self.hass, user_input
                )
                if info is not None:
                    return self.async_create_entry(title=info["title"], data=user_input)

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CredentialUsed:
                errors["base"] = "credential_used"
            except Exception:  # pylint: disable=broad-except
                logger.exception("Unexpected exception")
                errors["base"] = "unknown"

        else:
            user_input = {}

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CLIENT_ID, default=user_input.get(CONF_CLIENT_ID, "1")
                    ): str,
                    vol.Required(
                        CONF_CLIENT_SECRET,
                        default=user_input.get(CONF_CLIENT_SECRET, "1"),
                    ): str,
                }
            ),
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class CredentialUsed(HomeAssistantError):
    """Error to indicate there is credential is used"""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
