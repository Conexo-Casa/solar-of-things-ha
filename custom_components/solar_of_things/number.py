"""Number platform for Solar of Things integration."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SETTING_KEY_CANDIDATES, STATE_KEY_CANDIDATES
from .helpers import entry_value, find_entry, state_fields, to_float

_LOGGER = logging.getLogger(__name__)


def _limit_value(coordinator_data: dict | None, control: str) -> float | None:
    """Return the numeric value of a limit setting, snapshot before cache.

    The settings cache stores each key as ``{"key": …, "value": …}``; reading
    the entry itself (as this platform used to) hands Home Assistant a dict and
    the number shows as unavailable.
    """
    data = coordinator_data or {}

    for fields, candidates in (
        (state_fields(data.get("state")), STATE_KEY_CANDIDATES.get(control, [control])),
        (data.get("settings") or {}, SETTING_KEY_CANDIDATES.get(control, [control])),
    ):
        _key, entry = find_entry(fields, candidates)
        if entry is None:
            continue
        number = to_float(entry_value(entry))
        if number is not None:
            return number
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities (controls) for each device."""

    data = hass.data[DOMAIN][entry.entry_id]
    api = data["api"]
    station_id: str = data["station_id"]
    device_coordinators = data["device_coordinators"]

    entities: list[NumberEntity] = []

    for device_id, coordinator in device_coordinators.items():
        device_name = (coordinator.device_meta or {}).get("name") or device_id
        entities.extend(
            [
                SolarOfThingsBatteryChargeLimitNumber(api, coordinator, station_id, device_id, device_name),
                SolarOfThingsBatteryDischargeLimitNumber(api, coordinator, station_id, device_id, device_name),
                SolarOfThingsGridChargeLimitNumber(api, coordinator, station_id, device_id, device_name),
            ]
        )

    async_add_entities(entities)


class _BaseNumber(CoordinatorEntity, NumberEntity):
    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(coordinator)
        self._api = api
        self._station_id = station_id
        self._device_id = device_id
        self._device_name = device_name

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "Siseli",
            "model": (self.coordinator.data.get("device_meta") or {}).get("model") if self.coordinator.data else None,
            "via_device": (DOMAIN, self._station_id),
        }


class SolarOfThingsBatteryChargeLimitNumber(_BaseNumber):
    _setting_key = "batteryChargeLimit"

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Battery Charge Limit"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_battery_charge_limit"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_mode = NumberMode.SLIDER
        self._attr_icon = "mdi:battery-arrow-up"

    @property
    def native_value(self):
        return _limit_value(self.coordinator.data, self._setting_key)

    async def async_set_native_value(self, value: float) -> None:
        await self.hass.async_add_executor_job(self._api.set_battery_charge_limit, self._device_id, int(value))
        await self.coordinator.async_request_refresh()


class SolarOfThingsBatteryDischargeLimitNumber(_BaseNumber):
    _setting_key = "batteryDischargeLimit"

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Battery Discharge Limit"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_battery_discharge_limit"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_mode = NumberMode.SLIDER
        self._attr_icon = "mdi:battery-arrow-down"

    @property
    def native_value(self):
        return _limit_value(self.coordinator.data, self._setting_key)

    async def async_set_native_value(self, value: float) -> None:
        await self.hass.async_add_executor_job(self._api.set_battery_discharge_limit, self._device_id, int(value))
        await self.coordinator.async_request_refresh()


class SolarOfThingsGridChargeLimitNumber(_BaseNumber):
    _setting_key = "gridChargeLimit"

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Grid Charge Limit"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_grid_charge_limit"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 5000
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = "W"
        self._attr_mode = NumberMode.SLIDER
        self._attr_device_class = NumberDeviceClass.POWER
        self._attr_icon = "mdi:transmission-tower-import"

    @property
    def native_value(self):
        return _limit_value(self.coordinator.data, self._setting_key)

    async def async_set_native_value(self, value: float) -> None:
        await self.hass.async_add_executor_job(self._api.set_grid_charge_limit, self._device_id, int(value))
        await self.coordinator.async_request_refresh()
