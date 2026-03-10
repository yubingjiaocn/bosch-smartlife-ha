"""Light platform for Bosch SmartLife."""
import logging
from typing import Any

from homeassistant.components.light import (
    LightEntity,
    ColorMode,
    ATTR_BRIGHTNESS,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _create_entities(coordinator, api) -> list:
    """Create light entities from coordinator data."""
    entities = []
    for dev in coordinator.data or []:
        if dev.get("subDeviceType") == 4:  # Light
            entities.append(BoschLight(coordinator, api, dev))
    return entities


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict,
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict | None = None,
) -> None:
    """Set up Bosch SmartLife lights from yaml."""
    data = hass.data[DOMAIN]["yaml"]
    async_add_entities(_create_entities(data["coordinator"], data["api"]), True)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bosch SmartLife lights from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(_create_entities(data["coordinator"], data["api"]), True)


class BoschLight(CoordinatorEntity, LightEntity):
    """A Bosch SmartLife light."""

    def __init__(self, coordinator, api, device_data):
        super().__init__(coordinator)
        self._api = api
        self._device_id = device_data["lightDeviceId"]
        self._attr_name = device_data["name"]
        self._attr_unique_id = f"bosch_light_{self._device_id}"
        self._attr_color_mode = ColorMode.ONOFF
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        if device_data.get("brightness", -1) >= 0:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    @callback
    def _handle_coordinator_update(self) -> None:
        for dev in self.coordinator.data or []:
            if dev.get("lightDeviceId") == self._device_id:
                self._attr_is_on = dev.get("power") == "on"
                if dev.get("brightness", -1) >= 0:
                    self._attr_brightness = int(dev["brightness"] * 255 / 100)
                break
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        for dev in self.coordinator.data or []:
            if dev.get("lightDeviceId") == self._device_id:
                return dev.get("power") == "on"
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is not None:
            pct = int(brightness * 100 / 255)
            await self.hass.async_add_executor_job(
                self._api.light_set, self._device_id, "on", self._attr_name, pct
            )
        else:
            await self.hass.async_add_executor_job(
                self._api.light_set, self._device_id, "on", self._attr_name
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(
            self._api.light_set, self._device_id, "off", self._attr_name
        )
        await self.coordinator.async_request_refresh()
