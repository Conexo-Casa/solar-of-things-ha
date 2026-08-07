"""Switch platform for Solar of Things integration.

Each switch maps to one entry in ``BOOLEAN_CONTROLS``: it reads the live state
snapshot (falling back to the remote-config cache) and writes through the
remote-config endpoint under that control's *setting* key.

The pre-2.6.0 "Grid Charging (AC Input Range)" switch is gone.  Input voltage
range is reported by the device (``inputVoltageRange``) but the portal exposes
no write key for it, so the switch could never actually change anything; it is
now a read-only diagnostic sensor instead.
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
    BOOLEAN_CONTROLS,
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
_TRUE_WORDS = {"on", "enable", "enabled", "true", "yes"}
_FALSE_WORDS = {"off", "disable", "disabled", "false", "no"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    api = data["api"]
    station_id: str = data["station_id"]
    device_coordinators = data["device_coordinators"]

    entities: list[SwitchEntity] = []

    for device_id, coordinator in device_coordinators.items():
        device_name = (coordinator.device_meta or {}).get("name") or device_id
        entities.append(
            SolarOfThingsBackupModeSwitch(api, coordinator, station_id, device_id, device_name)
        )
        for control, spec in BOOLEAN_CONTROLS.items():
            entities.append(
                SolarOfThingsControlSwitch(
                    api, coordinator, station_id, device_id, device_name, control, spec
                )
            )

    async_add_entities(entities)


def _control_entries(
    coordinator_data: dict | None, control: str
) -> Iterator[tuple[str, str, Any]]:
    """Yield ``(source, matched_key, entry)`` for a control, snapshot first.

    The remote-config cache only holds values previously written through the
    portal, so it is a fallback rather than the primary source.
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
    coordinator_data: dict | None, control: str, on_codes: set[int]
) -> bool | None:
    """Resolve a control to on/off, accepting both codes and word renderings."""
    for _source, _key, entry in _control_entries(coordinator_data, control):
        number = to_float(entry_value(entry))
        if number is not None and number == int(number):
            return int(number) in on_codes
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
        self._attr_has_entity_name = True
        self._attr_device_class = SwitchDeviceClass.SWITCH

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "Siseli",
            "model": (self.coordinator.data.get("device_meta") or {}).get("model") if self.coordinator.data else None,
            "via_device": (DOMAIN, self._station_id),
        }


class SolarOfThingsControlSwitch(_BaseSwitch):
    """Switch for one of the device's enable/disable settings."""

    def __init__(
        self, api, coordinator, station_id: str, device_id: str, device_name: str,
        control: str, spec: dict,
    ) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._control = control
        self._on_codes: set[int] = spec["on_codes"]
        self._attr_name = spec["name"]
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_{control}"
        self._attr_icon = spec.get("icon")

    @property
    def is_on(self) -> bool | None:
        return _setting_bool(self.coordinator.data, self._control, self._on_codes)

    async def async_turn_on(self, **kwargs):
        await self._async_write(True)

    async def async_turn_off(self, **kwargs):
        await self._async_write(False)

    async def _async_write(self, enabled: bool) -> None:
        await self.hass.async_add_executor_job(
            self._api.set_boolean_control, self._device_id, self._control, enabled
        )
        await self.coordinator.async_request_refresh()


class SolarOfThingsBackupModeSwitch(_BaseSwitch):
    """Shortcut that maps to Output Source Priority SBU (backup/off-grid biased).

    ON  → Solar+Battery First (SBU): grid is the last resort.
    OFF → Solar First (SUB): solar first, grid supplements before the battery.

    Turning this on also moves the Output Source Priority select, which is the
    expected behaviour — they are the same device setting.
    """

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = "Backup Mode (SBU Priority)"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_backup_mode"
        self._attr_icon = "mdi:battery-lock"

    @property
    def is_on(self) -> bool | None:
        # Resolved through the same option table as the select, so a mode
        # reported as a label rather than a code still counts.
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
