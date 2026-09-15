"""Select platform for Solar of Things integration."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import resolve_setting_key
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Real API key: outputSourcePrioritySetting  (integer value)
# 0 = USO  Utility first
# 1 = SUB  Solar first (grid supplement)
# 2 = SBU  Solar + Battery first (grid only last resort)
OUTPUT_MODE_BY_VALUE: dict[int, str] = {
    0: "Utility First (USO)",
    1: "Solar First (SUB)",
    2: "Solar+Battery First (SBU)",
}
OUTPUT_MODES = list(OUTPUT_MODE_BY_VALUE.values())

# Real API key: chargerSourcePrioritySetting  (integer value)
# 0 = CSO  Solar + Utility charging (utility has priority)
# 1 = SNU  Solar First for charging, utility as fallback
# 2 = OSO  Solar Only charging
CHARGER_PRIORITY_BY_VALUE: dict[int, str] = {
    0: "Solar + Utility (CSO)",
    1: "Solar First (SNU)",
    2: "Solar Only (OSO)",
}
CHARGER_PRIORITIES = list(CHARGER_PRIORITY_BY_VALUE.values())


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


class _BaseSelect(CoordinatorEntity, SelectEntity):
    # Canonical setting key this entity controls (set by subclasses). Used
    # with resolve_setting_key() so a firmware that exposes the same control
    # under a different key name (#18) still reads and writes correctly, and
    # a firmware that doesn't expose it under any known name reports
    # unavailable instead of offering a control guaranteed to fail.
    _canonical_key: str = ""

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

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        settings = (self.coordinator.data or {}).get("settings")
        return resolve_setting_key(settings, self._canonical_key) is not None


class SolarOfThingsOperatingModeSelect(_BaseSelect):
    """Select entity for Output Source Priority (outputSourcePrioritySetting).

    Reflects the real device API key.  Values 0/1/2 map to USO/SUB/SBU.
    """

    _canonical_key = "outputSourcePrioritySetting"

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Output Source Priority"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_operating_mode"
        self._attr_options = OUTPUT_MODES
        self._attr_icon = "mdi:cog"

    @property
    def current_option(self) -> str | None:
        settings = ((self.coordinator.data or {}).get("settings") or {})
        key = resolve_setting_key(settings, self._canonical_key)
        entry = settings.get(key) if key else None
        if entry is None:
            return None
        raw = entry.get("value") if isinstance(entry, dict) else entry
        try:
            return OUTPUT_MODE_BY_VALUE.get(int(raw))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        settings = (self.coordinator.data or {}).get("settings")
        await self.hass.async_add_executor_job(
            self._api.set_operating_mode, self._device_id, option, settings
        )
        await self.coordinator.async_request_refresh()


class SolarOfThingsBatteryPrioritySelect(_BaseSelect):
    """Select entity for Charger Source Priority (chargerSourcePrioritySetting).

    Reflects the real device API key.  Values 0/1/2 map to CSO/SNU/OSO.
    """

    _canonical_key = "chargerSourcePrioritySetting"

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Charger Source Priority"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_battery_priority"
        self._attr_options = CHARGER_PRIORITIES
        self._attr_icon = "mdi:battery-sync"

    @property
    def current_option(self) -> str | None:
        settings = ((self.coordinator.data or {}).get("settings") or {})
        key = resolve_setting_key(settings, self._canonical_key)
        entry = settings.get(key) if key else None
        if entry is None:
            return None
        raw = entry.get("value") if isinstance(entry, dict) else entry
        try:
            return CHARGER_PRIORITY_BY_VALUE.get(int(raw))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        settings = (self.coordinator.data or {}).get("settings")
        await self.hass.async_add_executor_job(
            self._api.set_battery_priority, self._device_id, option, settings
        )
        await self.coordinator.async_request_refresh()
