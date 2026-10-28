"""Select platform for Solar of Things integration."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import resolve_setting_key
from .device import inverter_device_info
from .const import CHARGE_CONTROL_SELECTS, DOMAIN

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

        # #9: charge-current / comeback-voltage dropdowns, only for keys the
        # device's settings cache actually lists.
        settings = (coordinator.data or {}).get("settings")
        for key in CHARGE_CONTROL_SELECTS:
            if setting_entry(settings, key) is not None:
                entities.append(
                    SolarOfThingsChargeControlSelect(
                        api, coordinator, station_id, device_id, device_name, key
                    )
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
        return inverter_device_info(
            self.hass,
            self.platform.config_entry.entry_id if self.platform and self.platform.config_entry else None,
            self._station_id,
            self._device_id,
            self._device_name,
            (self.coordinator.data.get("device_meta") or {}).get("model") if self.coordinator.data else None,
        )

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


# ─── Charge-current / comeback-voltage dropdowns (#9) ──────────────────────────

def setting_entry(settings, key: str):
    """Return the current value for `key` from the settings cache, or None.

    The cache has been seen in two shapes: a flat {key: {"value": ...}} map,
    and the portal's full form payload with a {"configs": {key: value}} block
    (the #9 Victor 19.2 capture).  Both are accepted.
    """
    if not isinstance(settings, dict):
        return None
    if key in settings:
        entry = settings[key]
        return entry.get("value") if isinstance(entry, dict) else entry
    configs = settings.get("configs")
    if isinstance(configs, dict) and key in configs:
        return configs[key]
    return None


def match_option(raw, options: tuple[str, ...]) -> str | None:
    """Map a raw cached value onto one of the allowed option strings.

    Numeric compare, so "53.0" / 53 / "53" all select "53.0", and 2 selects
    "2".  A value outside the list reads unknown rather than a near guess.
    """
    try:
        num = float(raw)
    except (TypeError, ValueError):
        return None
    for opt in options:
        if float(opt) == num:
            return opt
    return None


class SolarOfThingsChargeControlSelect(_BaseSelect):
    """One enumerated charge setting from CHARGE_CONTROL_SELECTS (#9)."""

    def __init__(self, api, coordinator, station_id, device_id, device_name, key: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        name, unit, options, icon = CHARGE_CONTROL_SELECTS[key]
        self._key = key
        self._unit = unit
        self._values = options
        self._attr_name = f"{device_name} {name}"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_{key}"
        self._attr_options = [f"{v} {unit}" for v in options]
        self._attr_icon = icon

    @property
    def available(self) -> bool:
        if not CoordinatorEntity.available.fget(self):
            return False
        return setting_entry((self.coordinator.data or {}).get("settings"), self._key) is not None

    @property
    def current_option(self) -> str | None:
        raw = setting_entry((self.coordinator.data or {}).get("settings"), self._key)
        value = match_option(raw, self._values)
        return f"{value} {self._unit}" if value is not None else None

    async def async_select_option(self, option: str) -> None:
        value = option.removesuffix(f" {self._unit}")
        if value not in self._values:
            raise ValueError(f"{option!r} is not an allowed value for {self._key}")
        await self.hass.async_add_executor_job(
            self._api.set_setting_value, self._device_id, self._key, value
        )
        await self.coordinator.async_request_refresh()
