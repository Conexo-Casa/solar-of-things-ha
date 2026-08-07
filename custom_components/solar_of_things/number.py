"""Number platform for Solar of Things integration.

The entities here are driven by ``NUMBER_CONTROLS`` — the numeric settings the
portal's control panel can actually write.  The battery charge limit, battery
discharge limit and grid charge limit shipped before 2.6.0 are gone: PI30/VMIII
publishes no such attributes and the write endpoint has no keys for them, so
those sliders read as unavailable and their writes went nowhere.
"""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NUMBER_CONTROLS, SETTING_KEY_CANDIDATES, STATE_KEY_CANDIDATES
from .helpers import entry_value, find_entry, state_fields, to_float

_LOGGER = logging.getLogger(__name__)

_DEVICE_CLASSES = {
    "voltage": NumberDeviceClass.VOLTAGE,
    "current": NumberDeviceClass.CURRENT,
    "power": NumberDeviceClass.POWER,
}


def _control_value(coordinator_data: dict | None, control: str) -> float | None:
    """Return the numeric value of a control, snapshot before config cache.

    The settings cache stores each key as ``{"key": …, "value": …}``; returning
    the entry itself (as this platform used to) hands Home Assistant a dict and
    the number shows as unavailable.
    """
    data = coordinator_data or {}

    for haystack, candidates in (
        (state_fields(data.get("state")), STATE_KEY_CANDIDATES.get(control, [control])),
        (data.get("settings") or {}, SETTING_KEY_CANDIDATES.get(control, [control])),
    ):
        _key, entry = find_entry(haystack, candidates)
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

    entities: list[NumberEntity] = [
        SolarOfThingsControlNumber(
            api, coordinator, station_id, device_id,
            (coordinator.device_meta or {}).get("name") or device_id,
            control, spec,
        )
        for device_id, coordinator in device_coordinators.items()
        for control, spec in NUMBER_CONTROLS.items()
    ]

    async_add_entities(entities)


class SolarOfThingsControlNumber(CoordinatorEntity, NumberEntity):
    """Writable numeric device setting."""

    def __init__(
        self, api, coordinator, station_id: str, device_id: str, device_name: str,
        control: str, spec: dict,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._station_id = station_id
        self._device_id = device_id
        self._device_name = device_name
        self._control = control

        self._attr_has_entity_name = True
        self._attr_name = spec["name"]
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_{control}"
        self._attr_icon = spec.get("icon")
        self._attr_native_min_value = spec["min"]
        self._attr_native_max_value = spec["max"]
        self._attr_native_step = spec["step"]
        self._attr_native_unit_of_measurement = spec.get("unit")
        self._attr_device_class = _DEVICE_CLASSES.get(spec.get("device_class"))
        self._attr_mode = NumberMode.BOX

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "Siseli",
            "model": (self.coordinator.data.get("device_meta") or {}).get("model") if self.coordinator.data else None,
            "via_device": (DOMAIN, self._station_id),
        }

    @property
    def native_value(self):
        return _control_value(self.coordinator.data, self._control)

    async def async_set_native_value(self, value: float) -> None:
        await self.hass.async_add_executor_job(
            self._api.set_number_control, self._device_id, self._control, value
        )
        await self.coordinator.async_request_refresh()
