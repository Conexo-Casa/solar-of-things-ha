"""Switch platform for Solar of Things integration.

Like the selects, these switches read their state from the live snapshot
(``/apis/deviceState/simple/state/latest/v1``) first and only fall back to the
remote-config cache, which is empty until something has been written through
the portal.  Both integer codes and word renderings ("ON", "Appliance") are
accepted, because the snapshot reports some controls as text.
"""
from __future__ import annotations

import logging
from typing import Any, Iterator

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    OUTPUT_PRIORITY_ALIASES,
    OUTPUT_PRIORITY_BY_VALUE,
    SETTING_KEY_CANDIDATES,
    STATE_KEY_CANDIDATES,
)
from .helpers import (
    entry_display,
    entry_value,
    find_entry,
    normalise_text,
    resolve_option,
    state_fields,
    to_float,
)

_LOGGER = logging.getLogger(__name__)

# Word renderings the state snapshot uses instead of a numeric code.
_TRUE_WORDS = {"on", "enable", "enabled", "true", "yes", "appliance"}
_FALSE_WORDS = {"off", "disable", "disabled", "false", "no", "ups"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    api = data["api"]
    station_id: str = data["station_id"]
    device_coordinators = data["device_coordinators"]

    entities: list[SwitchEntity] = []

    for device_id, coordinator in device_coordinators.items():
        device_name = (coordinator.device_meta or {}).get("name") or device_id
        entities.extend(
            [
                SolarOfThingsGridChargingSwitch(api, coordinator, station_id, device_id, device_name),
                SolarOfThingsGridFeedInSwitch(api, coordinator, station_id, device_id, device_name),
                SolarOfThingsBackupModeSwitch(api, coordinator, station_id, device_id, device_name),
            ]
        )

    async_add_entities(entities)


def _control_entries(
    coordinator_data: dict | None, control: str
) -> Iterator[tuple[str, str, Any]]:
    """Yield ``(source, matched_key, entry)`` for a control, snapshot first.

    *control* is a key of ``STATE_KEY_CANDIDATES`` / ``SETTING_KEY_CANDIDATES``;
    each maps to the list of attribute names different models use.
    """
    data = coordinator_data or {}

    key, entry = find_entry(
        state_fields(data.get("state")), STATE_KEY_CANDIDATES.get(control, [control])
    )
    if entry is not None:
        yield "state", key, entry

    key, entry = find_entry(
        data.get("settings") or {}, SETTING_KEY_CANDIDATES.get(control, [control])
    )
    if entry is not None:
        yield "settings", key, entry


def _setting_bool(
    coordinator_data: dict | None, control: str, on_values: set[int]
) -> bool | None:
    """Resolve a control to on/off, accepting both codes and word renderings."""
    for _source, _key, entry in _control_entries(coordinator_data, control):
        number = to_float(entry_value(entry))
        if number is not None and number == int(number):
            return int(number) in on_values
        for text in (entry_display(entry), entry_value(entry)):
            word = normalise_text(text)
            if word in _TRUE_WORDS:
                return True
            if word in _FALSE_WORDS:
                return False
    return None


class _BaseSwitch(CoordinatorEntity, SwitchEntity):
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


class SolarOfThingsGridChargingSwitch(_BaseSwitch):
    """Switch for AC Input Range setting (acInputRangeSetting).

    0 = Appliance mode – wide input voltage range, grid charging allowed.
    1 = UPS mode – narrow voltage range, stricter bypass behaviour.
    The switch reports ON when the inverter is in Appliance (grid-charging) mode.
    """

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Grid Charging (AC Input Range)"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_grid_charging"
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_icon = "mdi:transmission-tower"

    @property
    def is_on(self) -> bool | None:
        # 0 = Appliance (charging OK), 1 = UPS (bypass).
        return _setting_bool(self.coordinator.data, "acInputRange", {0})

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(self._api.set_grid_charging, self._device_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self._api.set_grid_charging, self._device_id, False)
        await self.coordinator.async_request_refresh()


class SolarOfThingsGridFeedInSwitch(_BaseSwitch):
    """Switch for GRID grid switch (batteryPowerLimitingSetting).

    0 = OFF (grid switch disabled / feed-in off).
    1 = ON  (grid switch enabled / feed-in on).
    """

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Grid Feed-In"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_grid_feed_in"
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_icon = "mdi:transmission-tower-export"

    @property
    def is_on(self) -> bool | None:
        return _setting_bool(self.coordinator.data, "gridFeedIn", {1})

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(self._api.set_grid_feed_in, self._device_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self._api.set_grid_feed_in, self._device_id, False)
        await self.coordinator.async_request_refresh()


class SolarOfThingsBackupModeSwitch(_BaseSwitch):
    """Switch that maps to Output Source Priority SBU (backup/off-grid biased).

    ON  → outputSourcePrioritySetting = 2 (SBU: Solar+Battery first, grid last).
    OFF → outputSourcePrioritySetting = 1 (SUB: Solar first, grid as supplement).

    Note: turning this switch ON will also change the Output Source Priority
    select to 'Solar+Battery First (SBU)', which is the expected behaviour.
    """

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Backup Mode (SBU Priority)"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_backup_mode"
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_icon = "mdi:battery-lock"

    @property
    def is_on(self) -> bool | None:
        # Resolved through the same option table as the select, so an SBU
        # reported as the string "SBU" counts as on just like the code 2 does.
        for _source, _key, entry in _control_entries(
            self.coordinator.data, "outputSourcePriority"
        ):
            option = resolve_option(
                entry_value(entry),
                entry_display(entry),
                OUTPUT_PRIORITY_BY_VALUE,
                OUTPUT_PRIORITY_ALIASES,
            )
            if option is not None:
                return option == OUTPUT_PRIORITY_BY_VALUE[2]
        return None

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(self._api.set_backup_mode, self._device_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self._api.set_backup_mode, self._device_id, False)
        await self.coordinator.async_request_refresh()
