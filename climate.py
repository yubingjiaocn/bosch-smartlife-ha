"""Climate platform for Bosch SmartLife."""
import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
    FAN_AUTO,
)
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

MODE_MAP = {
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "dry": HVACMode.DRY,
    "fan": HVACMode.FAN_ONLY,
    "auto": HVACMode.AUTO,
}
MODE_REVERSE = {v: k for k, v in MODE_MAP.items()}

FAN_MAP = {0: FAN_AUTO, 1: FAN_LOW, 2: FAN_MEDIUM, 3: FAN_HIGH}
FAN_REVERSE = {v: k for k, v in FAN_MAP.items()}


def _create_entities(coordinator, api) -> list:
    """Create climate entities from coordinator data."""
    entities = []
    for dev in coordinator.data or []:
        if dev.get("subDeviceType") == 1:  # AC
            entities.append(BoschClimate(coordinator, api, dev))
    return entities


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict,
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict | None = None,
) -> None:
    """Set up Bosch SmartLife climate devices from yaml."""
    data = hass.data[DOMAIN]["yaml"]
    async_add_entities(_create_entities(data["coordinator"], data["api"]), True)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bosch SmartLife climate devices from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(_create_entities(data["coordinator"], data["api"]), True)


class BoschClimate(CoordinatorEntity, ClimateEntity):
    """A Bosch SmartLife AC."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.AUTO]
    _attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_AUTO]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_target_temperature_step = 1

    def __init__(self, coordinator, api, device_data):
        super().__init__(coordinator)
        self._api = api
        self._device_id = device_data["acDeviceId"]
        self._attr_name = device_data["name"]
        self._attr_unique_id = f"bosch_ac_{self._device_id}"

    def _get_device_data(self) -> dict | None:
        for dev in self.coordinator.data or []:
            if dev.get("acDeviceId") == self._device_id:
                return dev
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def hvac_mode(self) -> HVACMode:
        dev = self._get_device_data()
        if not dev or dev.get("power") == "off":
            return HVACMode.OFF
        return MODE_MAP.get(dev.get("mode"), HVACMode.AUTO)

    @property
    def current_temperature(self) -> float | None:
        return None  # Panel doesn't report room temp

    @property
    def target_temperature(self) -> float | None:
        dev = self._get_device_data()
        return dev.get("setTemp") if dev else None

    @property
    def fan_mode(self) -> str | None:
        dev = self._get_device_data()
        return FAN_MAP.get(dev.get("fan"), FAN_AUTO) if dev else None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.hass.async_add_executor_job(
                self._api.ac_set, self._device_id, "off"
            )
        else:
            mode_str = MODE_REVERSE.get(hvac_mode, "auto")
            await self.hass.async_add_executor_job(
                self._api.ac_set, self._device_id, "on", None, mode_str
            )
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self.hass.async_add_executor_job(
                self._api.ac_set, self._device_id, None, int(temp)
            )
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        fan_int = FAN_REVERSE.get(fan_mode, 0)
        await self.hass.async_add_executor_job(
            self._api.ac_set, self._device_id, None, None, None, fan_int
        )
        await self.coordinator.async_request_refresh()
