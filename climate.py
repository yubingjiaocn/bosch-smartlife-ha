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
)
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

MODE_MAP = {
    "cold": HVACMode.COOL,
    "hot": HVACMode.HEAT,
    "dry": HVACMode.DRY,
    "fan": HVACMode.FAN_ONLY,
    "auto": HVACMode.AUTO,
}
MODE_REVERSE = {v: k for k, v in MODE_MAP.items()}

FAN_MAP = {1: FAN_LOW, 2: FAN_MEDIUM, 3: FAN_HIGH}
FAN_REVERSE = {FAN_LOW: 1, FAN_MEDIUM: 2, FAN_HIGH: 3}


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
    _attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_target_temperature_step = 1

    def __init__(self, coordinator, api, device_data):
        super().__init__(coordinator)
        self._api = api
        self._device_id = device_data["acDeviceId"]
        self._panel_id = api.panel_id
        self._attr_name = device_data["name"]
        self._attr_unique_id = f"bosch_ac_{self._device_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_data["name"],
            manufacturer="Bosch",
            via_device=(DOMAIN, self._panel_id),
        )
        # Set initial state from device_data to avoid "unknown"
        if device_data.get("power") == "off":
            self._attr_hvac_mode = HVACMode.OFF
        else:
            self._attr_hvac_mode = MODE_MAP.get(device_data.get("mode"), HVACMode.OFF)
        self._attr_target_temperature = device_data.get("setTemp", 24)
        self._attr_fan_mode = FAN_MAP.get(device_data.get("fan"), FAN_LOW)
        self._attr_current_temperature = None  # Panel doesn't report room temp

    def _find_device(self) -> dict | None:
        for dev in self.coordinator.data or []:
            if dev.get("acDeviceId") == self._device_id:
                return dev
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        dev = self._find_device()
        if dev:
            if dev.get("power") == "off":
                self._attr_hvac_mode = HVACMode.OFF
            else:
                self._attr_hvac_mode = MODE_MAP.get(dev.get("mode"), HVACMode.AUTO)
            self._attr_target_temperature = dev.get("setTemp", self._attr_target_temperature)
            self._attr_fan_mode = FAN_MAP.get(dev.get("fan"), self._attr_fan_mode)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            # AC off must send all fields (Mode/SetTemp/Wind)
            dev = self._find_device()
            temp = dev.get("setTemp", 24) if dev else 24
            mode = dev.get("mode", "cold") if dev else "cold"
            fan = dev.get("fan", 1) if dev else 1
            await self.hass.async_add_executor_job(
                self._api.ac_set, self._device_id, "off", temp, mode, fan
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
