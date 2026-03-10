"""Bosch SmartLife integration for Home Assistant."""
import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BoschSmartLifeAPI
from .const import DOMAIN, CONF_ACCOUNT, CONF_PASSWORD, CONF_PANEL_ID

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.LIGHT, Platform.CLIMATE, Platform.COVER]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ACCOUNT): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Required(CONF_PANEL_ID): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def _create_coordinator(hass: HomeAssistant, api: BoschSmartLifeAPI) -> DataUpdateCoordinator:
    """Create a data update coordinator for the API."""

    async def _async_update():
        try:
            return await hass.async_add_executor_job(api.get_sub_devices)
        except Exception as err:
            raise UpdateFailed(f"Error fetching Bosch data: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="bosch_smartlife",
        update_method=_async_update,
        update_interval=timedelta(seconds=30),
    )

    await coordinator.async_refresh()
    return coordinator


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Bosch SmartLife from configuration.yaml (legacy)."""
    hass.data.setdefault(DOMAIN, {})

    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    api = BoschSmartLifeAPI(
        account=conf[CONF_ACCOUNT],
        password=conf[CONF_PASSWORD],
        panel_id=conf[CONF_PANEL_ID],
    )

    await hass.async_add_executor_job(api.login)

    coordinator = await _create_coordinator(hass, api)

    hass.data[DOMAIN]["yaml"] = {
        "api": api,
        "coordinator": coordinator,
    }

    for platform in PLATFORMS:
        hass.async_create_task(
            async_load_platform(hass, platform, DOMAIN, {}, config)
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bosch SmartLife from a config entry."""
    api = BoschSmartLifeAPI(
        account=entry.data[CONF_ACCOUNT],
        password=entry.data[CONF_PASSWORD],
        panel_id=entry.data[CONF_PANEL_ID],
    )

    success = await hass.async_add_executor_job(api.login)
    if not success:
        return False

    coordinator = await _create_coordinator(hass, api)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
