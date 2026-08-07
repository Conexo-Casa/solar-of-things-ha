"""Select platform for Solar of Things integration.

Read-back strategy
──────────────────
Both priority selects used to read only the remote-config *settings cache*
(``/apis/remote/device/configs/cache/get``).  That cache only contains keys
that have previously been written through the portal, so on most accounts it
comes back empty and the selects showed ``unknown``.

They now resolve their current option from the live state snapshot
(``/apis/deviceState/simple/state/latest/v1``) first and fall back to the
settings cache, and they accept every value shape the API uses: an integer
code, a numeric string, an abbreviation (``"SBU"``) or a full label.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CHARGER_PRIORITY_ALIASES,
    CHARGER_PRIORITY_BY_VALUE,
    CHARGER_PRIORITY_OPTIONS,
    DOMAIN,
    OUTPUT_PRIORITY_ALIASES,
    OUTPUT_PRIORITY_BY_VALUE,
    OUTPUT_PRIORITY_OPTIONS,
    SETTING_KEY_CANDIDATES,
    STATE_KEY_CANDIDATES,
)
from .helpers import (
    entry_display,
    entry_value,
    find_entry,
    resolve_option,
    state_fields,
)

_LOGGER = logging.getLogger(__name__)

# Re-exported under their previous names for backwards compatibility.
OUTPUT_MODE_BY_VALUE = OUTPUT_PRIORITY_BY_VALUE
OUTPUT_MODES = OUTPUT_PRIORITY_OPTIONS
CHARGER_PRIORITIES = CHARGER_PRIORITY_OPTIONS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    api = data["api"]
    station_id: str = data["station_id"]
    device_coordinators = data["device_coordinators"]

    entities: list[SelectEntity] = []

    for device_id, coordinator in device_coordinators.items():
        device_name = (coordinator.device_meta or {}).get("name") or device_id
        entities.extend(
            [
                SolarOfThingsOperatingModeSelect(api, coordinator, station_id, device_id, device_name),
                SolarOfThingsBatteryPrioritySelect(api, coordinator, station_id, device_id, device_name),
            ]
        )

    async_add_entities(entities)


class _BasePrioritySelect(CoordinatorEntity, SelectEntity):
    """Select backed by a device priority setting.

    Subclasses provide the candidate key names and the value/alias tables; the
    resolution order (state snapshot → settings cache) is shared.
    """

    _state_candidates: list[str] = []
    _setting_candidates: list[str] = []
    _by_value: dict[int, str] = {}
    _aliases: dict[str, str] = {}

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(coordinator)
        self._api = api
        self._station_id = station_id
        self._device_id = device_id
        self._device_name = device_name
        self._unresolved_logged: str | None = None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "Siseli",
            "model": (self.coordinator.data.get("device_meta") or {}).get("model") if self.coordinator.data else None,
            "via_device": (DOMAIN, self._station_id),
        }

    def _read_source(self) -> tuple[str | None, str | None, Any, Any]:
        """Return ``(source, matched_key, raw_value, display_value)``.

        Prefers the live state snapshot, because the settings cache only holds
        values previously written through the portal and is empty on accounts
        that have never used remote control.
        """
        data = self.coordinator.data or {}

        key, entry = find_entry(state_fields(data.get("state")), self._state_candidates)
        if key is not None:
            raw, display = entry_value(entry), entry_display(entry)
            if raw not in (None, "") or display not in (None, ""):
                return "state", key, raw, display

        key, entry = find_entry(data.get("settings") or {}, self._setting_candidates)
        if key is not None:
            return "settings", key, entry_value(entry), entry_display(entry)

        return None, None, None, None

    @property
    def current_option(self) -> str | None:
        source, key, raw, display = self._read_source()
        if source is None:
            return None

        option = resolve_option(raw, display, self._by_value, self._aliases)
        if option is None:
            # Log once per distinct unrecognised value rather than on every
            # poll, so an unknown model shows up in the log without spamming it.
            signature = f"{key}={raw!r}/{display!r}"
            if self._unresolved_logged != signature:
                self._unresolved_logged = signature
                _LOGGER.warning(
                    "SolarOfThings %s: could not map %s value %r (display %r) from the "
                    "%s payload onto a known option %s. Please report this via a GitHub "
                    "issue so the mapping can be added.",
                    self._device_id, key, raw, display, source, self.options,
                )
        return option

    @property
    def extra_state_attributes(self):
        """Expose the raw API payload behind this select.

        Useful when the option cannot be resolved: the attributes show which
        endpoint and attribute name the value came from, and what it contained.
        """
        source, key, raw, display = self._read_source()
        return {
            "source": source,
            "api_key": key,
            "raw_value": raw,
            "raw_display": display,
        }


class SolarOfThingsOperatingModeSelect(_BasePrioritySelect):
    """Select entity for Output Source Priority.

    Written as ``outputSourcePrioritySetting``; values 0/1/2 map to USO/SUB/SBU.
    """

    _state_candidates = STATE_KEY_CANDIDATES["outputSourcePriority"]
    _setting_candidates = SETTING_KEY_CANDIDATES["outputSourcePriority"]
    _by_value = OUTPUT_PRIORITY_BY_VALUE
    _aliases = OUTPUT_PRIORITY_ALIASES

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Output Source Priority"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_operating_mode"
        self._attr_options = OUTPUT_PRIORITY_OPTIONS
        self._attr_icon = "mdi:cog"

    async def async_select_option(self, option: str) -> None:
        await self.hass.async_add_executor_job(self._api.set_operating_mode, self._device_id, option)
        await self.coordinator.async_request_refresh()


class SolarOfThingsBatteryPrioritySelect(_BasePrioritySelect):
    """Select entity for Charger Source Priority.

    Written as ``chargerSourcePrioritySetting``; values 0/1/2 map to CSO/SNU/OSO.
    """

    _state_candidates = STATE_KEY_CANDIDATES["chargerSourcePriority"]
    _setting_candidates = SETTING_KEY_CANDIDATES["chargerSourcePriority"]
    _by_value = CHARGER_PRIORITY_BY_VALUE
    _aliases = CHARGER_PRIORITY_ALIASES

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Charger Source Priority"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_battery_priority"
        self._attr_options = CHARGER_PRIORITY_OPTIONS
        self._attr_icon = "mdi:battery-sync"

    async def async_select_option(self, option: str) -> None:
        await self.hass.async_add_executor_job(self._api.set_battery_priority, self._device_id, option)
        await self.coordinator.async_request_refresh()
