"""Climate platform for Bosch SmartLife."""
import asyncio
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

# Aliases for fan modes sent by external bridges (e.g. Xiaomi/hasslife sends
# "mid" instead of "medium"). Normalize before validation/lookup so a "调中档"
# command from MiHome does not get rejected by HA core validation.
FAN_ALIASES = {
    "mid": FAN_MEDIUM,
    "middle": FAN_MEDIUM,
    "med": FAN_MEDIUM,
    "中": FAN_MEDIUM,
    "中档": FAN_MEDIUM,
    "low": FAN_LOW,
    "高": FAN_HIGH,
    "高档": FAN_HIGH,
    "低": FAN_LOW,
    "低档": FAN_LOW,
    "auto": FAN_MEDIUM,
}

# Bosch cloud only dispatches a command when the panel state CHANGES.
# Seconds to hold the "on" pulse before sending "off" when forcing an edge.
OFF_EDGE_PULSE_SECONDS = 1.5


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
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
    _attr_assumed_state = True  # cloud cache unreliable; always dispatch commands
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

    def _valid_mode_or_raise(self, mode_type, mode, modes) -> None:
        """Override core validation to accept external fan-mode aliases.

        HA core validates fan_mode against self.fan_modes BEFORE calling
        async_set_fan_mode. MiHome/hasslife sends "mid" which is not in
        [low, medium, high], so it was rejected with ServiceValidationError
        and "风速调中档" silently failed. Normalize known aliases here so the
        call proceeds; async_set_fan_mode then maps it to the real value.
        """
        if mode_type == "fan" and isinstance(mode, str):
            if str(mode).lower() in FAN_ALIASES:
                return
        return super()._valid_mode_or_raise(mode_type, mode, modes)

    def _find_device(self) -> dict | None:
        for dev in self.coordinator.data or []:
            if dev.get("acDeviceId") == self._device_id:
                return dev
        return None

    def _desired_mode_str(self) -> str:
        """The mode string to send when only temp/fan is being changed.

        Use the entity's OWN known hvac_mode (which set_hvac_mode updates
        optimistically before awaiting I/O), NOT the coordinator cache. This is
        the race fix: MiHome splits "cool 22C" into two concurrent service
        calls (set_hvac_mode + set_temperature). If set_temperature read the
        stale coordinator cache it would resend the OLD mode (e.g. "hot") and
        clobber the cooling that set_hvac_mode just applied.
        """
        if self._attr_hvac_mode and self._attr_hvac_mode != HVACMode.OFF:
            return MODE_REVERSE.get(self._attr_hvac_mode, "cold")
        # Entity thinks it's off: fall back to device cache, then a safe default.
        dev = self._find_device()
        if dev and dev.get("mode"):
            return dev["mode"]
        return "cold"

    def _desired_fan_int(self) -> int:
        return FAN_REVERSE.get(self._attr_fan_mode, 1)

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
            # AC off must send all fields (Mode/SetTemp/Wind).
            temp = self._attr_target_temperature or 24
            # Follow the entity's current mode for the brief "on" pulse; never
            # fall back to "cold" (would blip cooling in winter). Default to fan.
            mode = self._desired_mode_str() if self._attr_hvac_mode != HVACMode.OFF else "fan"
            fan = self._desired_fan_int()

            # The Bosch cloud only pushes a command to the hard-wired unit when
            # the panel state CHANGES. HA's cached power/state is unreliable, so
            # a plain "off" is often a no-op and the AC keeps running. Always
            # force an on->off edge so the "off" reliably dispatches. The brief
            # "on" pulse follows the current mode (never "cold" -> avoids a
            # winter cooling blip).
            _LOGGER.info(
                "AC %s: forcing on->off edge to guarantee shutdown "
                "(pulse mode=%s, %ss)", self._device_id, mode, OFF_EDGE_PULSE_SECONDS
            )
            # Optimistic update so concurrent setters see OFF.
            self._attr_hvac_mode = HVACMode.OFF
            self.async_write_ha_state()
            await self.hass.async_add_executor_job(
                self._api.ac_set, self._device_id, "on", temp, mode, fan
            )
            await asyncio.sleep(OFF_EDGE_PULSE_SECONDS)
            await self.hass.async_add_executor_job(
                self._api.ac_set, self._device_id, "off", temp, mode, fan
            )
        else:
            mode_str = MODE_REVERSE.get(hvac_mode, "auto")
            # Optimistic update FIRST (before awaiting I/O) so a concurrent
            # set_temperature/set_fan_mode reads the new mode, not the old one.
            self._attr_hvac_mode = hvac_mode
            self.async_write_ha_state()
            temp = self._attr_target_temperature or 24
            fan = self._desired_fan_int()
            await self.hass.async_add_executor_job(
                self._api.ac_set, self._device_id, "on", temp, mode_str, fan
            )
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            # Optimistic update first, then read a consistent snapshot from the
            # entity's own attrs (NOT the stale coordinator cache).
            self._attr_target_temperature = int(temp)
            self.async_write_ha_state()
            mode = self._desired_mode_str()
            fan = self._desired_fan_int()
            await self.hass.async_add_executor_job(
                self._api.ac_set, self._device_id, "on", int(temp), mode, fan
            )
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        # Normalize external aliases (e.g. MiHome "mid" -> "medium").
        normalized = FAN_ALIASES.get(str(fan_mode).lower(), fan_mode)
        fan_int = FAN_REVERSE.get(normalized, 0)
        if fan_int == 0:
            _LOGGER.warning("AC %s: unknown fan_mode=%r, ignoring", self._device_id, fan_mode)
            return
        # Optimistic update first, then consistent snapshot from own attrs.
        self._attr_fan_mode = normalized
        self.async_write_ha_state()
        mode = self._desired_mode_str()
        temp = self._attr_target_temperature or 24
        await self.hass.async_add_executor_job(
            self._api.ac_set, self._device_id, "on", temp, mode, fan_int
        )
        await self.coordinator.async_request_refresh()
