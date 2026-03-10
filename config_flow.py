"""Config flow for Bosch SmartLife integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant

from .api import BoschSmartLifeAPI
from .const import DOMAIN, CONF_ACCOUNT, CONF_PASSWORD, CONF_PANEL_ID

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _validate_login(hass: HomeAssistant, account: str, password: str) -> BoschSmartLifeAPI:
    """Validate credentials and return authenticated API client."""
    api = BoschSmartLifeAPI(account=account, password=password, panel_id="")
    success = await hass.async_add_executor_job(api.login)
    if not success:
        raise InvalidAuth
    return api


class BoschSmartLifeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bosch SmartLife."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._api: BoschSmartLifeAPI | None = None
        self._account: str = ""
        self._password: str = ""
        self._panels: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial login step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._account = user_input[CONF_ACCOUNT]
            self._password = user_input[CONF_PASSWORD]

            try:
                self._api = await _validate_login(
                    self.hass, self._account, self._password
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "cannot_connect"
            else:
                # Login succeeded, fetch panels
                try:
                    self._panels = await self.hass.async_add_executor_job(
                        self._api.get_panels
                    )
                except Exception:
                    _LOGGER.exception("Failed to fetch panels")
                    errors["base"] = "cannot_connect"
                else:
                    if not self._panels:
                        errors["base"] = "no_panels"
                    elif len(self._panels) == 1:
                        # Only one panel, skip selection
                        panel = self._panels[0]
                        panel_id = panel.get("physicalDeviceId", "")
                        return await self._create_entry(panel_id)
                    else:
                        return await self.async_step_panel()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_panel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle panel selection step."""
        if user_input is not None:
            return await self._create_entry(user_input[CONF_PANEL_ID])

        panel_options = {}
        for panel in self._panels:
            pid = panel.get("physicalDeviceId", "")
            name = panel.get("name", pid)
            family = panel.get("familyName", "")
            label = f"{name} - {family} ({pid})" if family else f"{name} ({pid})"
            panel_options[pid] = label

        return self.async_show_form(
            step_id="panel",
            data_schema=vol.Schema(
                {vol.Required(CONF_PANEL_ID): vol.In(panel_options)}
            ),
        )

    async def _create_entry(self, panel_id: str) -> ConfigFlowResult:
        """Create the config entry."""
        await self.async_set_unique_id(f"{self._account}_{panel_id}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"Bosch SmartLife ({panel_id})",
            data={
                CONF_ACCOUNT: self._account,
                CONF_PASSWORD: self._password,
                CONF_PANEL_ID: panel_id,
            },
        )


class InvalidAuth(Exception):
    """Error to indicate invalid authentication."""
