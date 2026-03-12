"""Cover platform for Bosch SmartLife (curtains)."""
import logging
from typing import Any

from homeassistant.components.cover import (
    CoverEntity,
    CoverDeviceClass,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _create_entities(coordinator, api) -> list:
    """Create cover entities from coordinator data."""
    entities = []
    for dev in coordinator.data or []:
        if dev.get("subDeviceType") == 5:  # Curtain
            device_id = dev["curtainDeviceId"]
            name = dev["name"]
            entities.append(BoschCover(coordinator, api, device_id, f"{name} Curtain", "curtain", name))
            entities.append(BoschCover(coordinator, api, device_id, f"{name} Sheer", "sheer", name))
    return entities


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict,
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict | None = None,
) -> None:
    """Set up Bosch SmartLife covers from yaml."""
    data = hass.data[DOMAIN]["yaml"]
    async_add_entities(_create_entities(data["coordinator"], data["api"]), True)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bosch SmartLife covers from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(_create_entities(data["coordinator"], data["api"]), True)


class BoschCover(CoordinatorEntity, CoverEntity):
    """A Bosch SmartLife curtain/sheer."""

    _attr_device_class = CoverDeviceClass.CURTAIN
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP

    def __init__(self, coordinator, api, device_id, name, cover_type, device_name):
        super().__init__(coordinator)
        self._api = api
        self._device_id = device_id
        self._panel_id = api.panel_id
        self._cover_type = cover_type  # "curtain" or "sheer"
        self._attr_name = name
        self._attr_unique_id = f"bosch_cover_{device_id}_{cover_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Bosch",
            via_device=(DOMAIN, self._panel_id),
        )

    def _get_device_data(self) -> dict | None:
        for dev in self.coordinator.data or []:
            if dev.get("curtainDeviceId") == self._device_id:
                return dev
        return None

    @property
    def is_closed(self) -> bool | None:
        dev = self._get_device_data()
        if not dev:
            return None
        status_key = "status1" if self._cover_type == "sheer" else "status"
        return dev.get(status_key) == "closed"

    async def async_open_cover(self, **kwargs: Any) -> None:
        if self._cover_type == "sheer":
            await self.hass.async_add_executor_job(
                self._api.sheer_set, self._device_id, "opened", self._attr_name
            )
        else:
            await self.hass.async_add_executor_job(
                self._api.curtain_set, self._device_id, "opened", self._attr_name
            )
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        if self._cover_type == "sheer":
            await self.hass.async_add_executor_job(
                self._api.sheer_set, self._device_id, "closed", self._attr_name
            )
        else:
            await self.hass.async_add_executor_job(
                self._api.curtain_set, self._device_id, "closed", self._attr_name
            )
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        if self._cover_type == "sheer":
            await self.hass.async_add_executor_job(
                self._api.sheer_set, self._device_id, "stopped", self._attr_name
            )
        else:
            await self.hass.async_add_executor_job(
                self._api.curtain_set, self._device_id, "stopped", self._attr_name
            )
        await self.coordinator.async_request_refresh()
