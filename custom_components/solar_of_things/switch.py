"""Switch platform for Solar of Things integration."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import resolve_setting_key
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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


def _setting_value(coordinator_data: dict | None, canonical_key: str) -> int | None:
    """Extract the integer value for a canonical setting from coordinator data.

    Resolves through resolve_setting_key() so a firmware that exposes this
    control under a different key name (#18) still reads its real state
    instead of showing unknown.
    """
    settings = ((coordinator_data or {}).get("settings") or {})
    key = resolve_setting_key(settings, canonical_key)
    entry = settings.get(key) if key else None
    if entry is None:
        return None
    raw = entry.get("value") if isinstance(entry, dict) else entry
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class _BaseSwitch(CoordinatorEntity, SwitchEntity):
    # Canonical setting key this entity controls (set by subclasses). See
    # resolve_setting_key() in api.py: lets a firmware that exposes this
    # control under a different key name still work, and a firmware that
    # doesn't expose it under any known name report unavailable instead of
    # offering a control guaranteed to fail.
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


class SolarOfThingsGridChargingSwitch(_BaseSwitch):
    """Switch for AC Input Range setting (acInputRangeSetting).

    0 = Appliance mode – wide input voltage range, grid charging allowed.
    1 = UPS mode – narrow voltage range, stricter bypass behaviour.
    The switch reports ON when the inverter is in Appliance (grid-charging) mode.
    """

    _canonical_key = "acInputRangeSetting"

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Grid Charging (AC Input Range)"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_grid_charging"
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_icon = "mdi:transmission-tower"

    @property
    def is_on(self) -> bool | None:
        val = _setting_value(self.coordinator.data, self._canonical_key)
        if val is None:
            return None
        return val == 0  # 0=Appliance (charging OK), 1=UPS (bypass)

    async def async_turn_on(self, **kwargs):
        settings = (self.coordinator.data or {}).get("settings")
        await self.hass.async_add_executor_job(self._api.set_grid_charging, self._device_id, True, settings)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        settings = (self.coordinator.data or {}).get("settings")
        await self.hass.async_add_executor_job(self._api.set_grid_charging, self._device_id, False, settings)
        await self.coordinator.async_request_refresh()


class SolarOfThingsGridFeedInSwitch(_BaseSwitch):
    """Switch for GRID grid switch (batteryPowerLimitingSetting).

    0 = OFF (grid switch disabled / feed-in off).
    1 = ON  (grid switch enabled / feed-in on).
    """

    _canonical_key = "batteryPowerLimitingSetting"

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Grid Feed-In"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_grid_feed_in"
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_icon = "mdi:transmission-tower-export"

    @property
    def is_on(self) -> bool | None:
        val = _setting_value(self.coordinator.data, self._canonical_key)
        if val is None:
            return None
        return val == 1  # 1=ON

    async def async_turn_on(self, **kwargs):
        settings = (self.coordinator.data or {}).get("settings")
        await self.hass.async_add_executor_job(self._api.set_grid_feed_in, self._device_id, True, settings)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        settings = (self.coordinator.data or {}).get("settings")
        await self.hass.async_add_executor_job(self._api.set_grid_feed_in, self._device_id, False, settings)
        await self.coordinator.async_request_refresh()


class SolarOfThingsBackupModeSwitch(_BaseSwitch):
    """Switch that maps to Output Source Priority SBU (backup/off-grid biased).

    ON  → outputSourcePrioritySetting = 2 (SBU: Solar+Battery first, grid last).
    OFF → outputSourcePrioritySetting = 1 (SUB: Solar first, grid as supplement).

    Note: turning this switch ON will also change the Operating Mode select entity
    to 'Solar+Battery First (SBU)', which is the expected behaviour.
    """

    _canonical_key = "outputSourcePrioritySetting"

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Backup Mode (SBU Priority)"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_backup_mode"
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_icon = "mdi:battery-lock"

    @property
    def is_on(self) -> bool | None:
        val = _setting_value(self.coordinator.data, self._canonical_key)
        if val is None:
            return None
        return val == 2  # SBU

    async def async_turn_on(self, **kwargs):
        settings = (self.coordinator.data or {}).get("settings")
        await self.hass.async_add_executor_job(self._api.set_backup_mode, self._device_id, True, settings)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        settings = (self.coordinator.data or {}).get("settings")
        await self.hass.async_add_executor_job(self._api.set_backup_mode, self._device_id, False, settings)
        await self.coordinator.async_request_refresh()
