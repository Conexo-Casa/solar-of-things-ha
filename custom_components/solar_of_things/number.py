"""Number platform for Solar of Things integration."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import resolve_setting_key
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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
    # Canonical setting key this entity controls (set by subclasses via
    # _setting_key). See resolve_setting_key() in api.py: lets a firmware
    # that exposes this control under a different key name still work, and a
    # firmware that doesn't expose it under any known name report
    # unavailable instead of offering a control guaranteed to fail.
    _setting_key: str = ""

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
        return resolve_setting_key(settings, self._setting_key) is not None

    @property
    def native_value(self):
        """Return the setting's numeric value.

        get_device_settings() returns {key: {"key", "value", "valueDisplay",
        ...}} per key, not a bare number — this was previously returning that
        whole object, which HA's number platform cannot render as a value.
        """
        settings = ((self.coordinator.data or {}).get("settings") or {})
        key = resolve_setting_key(settings, self._setting_key)
        entry = settings.get(key) if key else None
        if entry is None:
            return None
        raw = entry.get("value") if isinstance(entry, dict) else entry
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None


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

    async def async_set_native_value(self, value: float) -> None:
        settings = (self.coordinator.data or {}).get("settings")
        await self.hass.async_add_executor_job(
            self._api.set_battery_charge_limit, self._device_id, int(value), settings
        )
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

    async def async_set_native_value(self, value: float) -> None:
        settings = (self.coordinator.data or {}).get("settings")
        await self.hass.async_add_executor_job(
            self._api.set_battery_discharge_limit, self._device_id, int(value), settings
        )
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

    async def async_set_native_value(self, value: float) -> None:
        settings = (self.coordinator.data or {}).get("settings")
        await self.hass.async_add_executor_job(
            self._api.set_grid_charge_limit, self._device_id, int(value), settings
        )
        await self.coordinator.async_request_refresh()
