"""Sensor platform for Solar of Things integration."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_DEFINITIONS, STATE_KEY_CANDIDATES
from .helpers import (
    entry_display,
    entry_unit,
    entry_value,
    find_entry,
    scale_value,
    state_fields,
    to_float,
)

_LOGGER = logging.getLogger(__name__)

# Map sensor key → translation_key (snake_case)
_TRANSLATION_KEYS: dict[str, str] = {
    "pvInputPower": "pv_input_power",
    "acOutputActivePower": "ac_output_active_power",
    "batteryDischargeCurrent": "battery_discharge_current",
    "batteryChargingCurrent": "battery_charging_current",
    "batteryVoltage": "battery_voltage",
    "batteryPower": "battery_power",
    "batterySOC": "battery_soc",
    "feedInPower": "feed_in_power",
    "gridPower": "grid_power",
    "loadPower": "load_power",
    "monthly_pv_generated": "monthly_pv_generated",
    "monthly_grid_import": "monthly_grid_import",
    "monthly_total_consumption": "monthly_total_consumption",
    "monthly_solar_percentage": "monthly_solar_percentage",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solar of Things sensors."""

    data = hass.data[DOMAIN][entry.entry_id]
    station_id: str = data["station_id"]
    device_coordinators = data["device_coordinators"]
    station_coordinator = data["station_coordinator"]

    entities: list[SensorEntity] = []

    # Per-device sensors
    for device_id, coordinator in device_coordinators.items():
        device_name = (coordinator.device_meta or {}).get("name") or device_id

        for key, definition in SENSOR_DEFINITIONS.items():
            if key.startswith("monthly_"):
                continue

            entities.append(
                SolarOfThingsDeviceSensor(
                    coordinator=coordinator,
                    station_id=station_id,
                    device_id=device_id,
                    device_name=device_name,
                    sensor_key=key,
                    sensor_definition=definition,
                )
            )

        # State-endpoint sensors (temperature, voltages, freq, daily energy, mode)
        for definition in STATE_SENSORS:
            entities.append(
                SolarOfThingsStateSensor(
                    coordinator, station_id, device_id, device_name, definition
                )
            )

        # Active-alarms sensor
        entities.append(
            SolarOfThingsAlarmSensor(coordinator, station_id, device_id, device_name)
        )

    # Station-level monthly sensors
    if station_coordinator:
        for key, definition in SENSOR_DEFINITIONS.items():
            if not key.startswith("monthly_"):
                continue

            entities.append(
                SolarOfThingsStationMonthlySensor(
                    coordinator=station_coordinator,
                    station_id=station_id,
                    sensor_key=key,
                    sensor_definition=definition,
                )
            )

    async_add_entities(entities)


class SolarOfThingsDeviceSensor(CoordinatorEntity, SensorEntity):
    """Per-device telemetry sensor."""

    def __init__(
        self,
        coordinator,
        station_id: str,
        device_id: str,
        device_name: str,
        sensor_key: str,
        sensor_definition: dict,
    ) -> None:
        super().__init__(coordinator)

        self._station_id = station_id
        self._device_id = device_id
        self._device_name = device_name
        self._sensor_key = sensor_key
        self._sensor_definition = sensor_definition

        self._attr_has_entity_name = True
        self._attr_translation_key = _TRANSLATION_KEYS.get(sensor_key)
        # Fallback name if no translation key
        if not self._attr_translation_key:
            self._attr_name = f"{device_name} {sensor_definition['name']}"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_{sensor_key}"
        self._attr_icon = sensor_definition.get("icon")

        unit = sensor_definition.get("unit")
        if unit == "W":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif unit == "kWh":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif unit == "A":
            self._attr_device_class = SensorDeviceClass.CURRENT
            self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif unit == "V":
            self._attr_device_class = SensorDeviceClass.VOLTAGE
            self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif unit == "%":
            if "battery" in sensor_key.lower():
                self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT

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
        ts = (self.coordinator.data or {}).get("time_series") or {}
        val = ts.get(self._sensor_key)
        if val is None:
            return None
        try:
            return round(float(val), 2)
        except Exception:
            return None


class SolarOfThingsStationMonthlySensor(CoordinatorEntity, SensorEntity):
    """Station-level monthly summary sensor."""

    def __init__(
        self,
        coordinator,
        station_id: str,
        sensor_key: str,
        sensor_definition: dict,
    ) -> None:
        super().__init__(coordinator)

        self._station_id = station_id
        self._sensor_key = sensor_key
        self._sensor_definition = sensor_definition

        self._attr_has_entity_name = True
        self._attr_translation_key = _TRANSLATION_KEYS.get(sensor_key)
        if not self._attr_translation_key:
            self._attr_name = f"Station {station_id} {sensor_definition['name']}"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{sensor_key}"
        self._attr_icon = sensor_definition.get("icon")

        unit = sensor_definition.get("unit")
        if unit == "kWh":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL
        elif unit == "%":
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._station_id)},
            "name": f"Solar Station {self._station_id}",
            "manufacturer": "Siseli",
            "model": "Station",
        }

    @property
    def native_value(self):
        monthly = (self.coordinator.data or {}).get("monthly") or {}
        val = monthly.get(self._sensor_key)
        if val is None:
            return None
        try:
            return round(float(val), 2)
        except Exception:
            return None


# State-endpoint sensors (read from coordinator.data["state"]["fields"]).
_SC, _DC = SensorStateClass, SensorDeviceClass
STATE_SENSORS: list[dict] = [
    {"key": "inverterHeatSinkTemperature", "name": "Inverter Temperature", "unit": UnitOfTemperature.CELSIUS, "device_class": _DC.TEMPERATURE, "state_class": _SC.MEASUREMENT, "icon": "mdi:thermometer"},
    {"key": "busVoltage", "name": "Bus Voltage", "unit": UnitOfElectricPotential.VOLT, "device_class": _DC.VOLTAGE, "state_class": _SC.MEASUREMENT, "icon": "mdi:flash"},
    {"key": "acOutputVoltage", "name": "AC Output Voltage", "unit": UnitOfElectricPotential.VOLT, "device_class": _DC.VOLTAGE, "state_class": _SC.MEASUREMENT, "icon": "mdi:sine-wave"},
    {"key": "acOutputFrequency", "name": "AC Output Frequency", "unit": UnitOfFrequency.HERTZ, "device_class": _DC.FREQUENCY, "state_class": _SC.MEASUREMENT, "icon": "mdi:sine-wave"},
    {"key": "acOutputApparentPower", "name": "AC Output Apparent Power", "unit": UnitOfApparentPower.VOLT_AMPERE, "device_class": _DC.APPARENT_POWER, "state_class": _SC.MEASUREMENT, "icon": "mdi:power-plug"},
    {"key": "outputLoadPercent", "name": "Output Load", "unit": PERCENTAGE, "device_class": None, "state_class": _SC.MEASUREMENT, "icon": "mdi:gauge"},
    {"key": "gridVoltage", "name": "Grid Voltage", "unit": UnitOfElectricPotential.VOLT, "device_class": _DC.VOLTAGE, "state_class": _SC.MEASUREMENT, "icon": "mdi:transmission-tower"},
    {"key": "gridFrequency", "name": "Grid Frequency", "unit": UnitOfFrequency.HERTZ, "device_class": _DC.FREQUENCY, "state_class": _SC.MEASUREMENT, "icon": "mdi:transmission-tower"},
    {"key": "PV1InputVoltage", "name": "PV1 Voltage", "unit": UnitOfElectricPotential.VOLT, "device_class": _DC.VOLTAGE, "state_class": _SC.MEASUREMENT, "icon": "mdi:solar-panel"},
    {"key": "pv1InputCurrent", "name": "PV1 Current", "unit": UnitOfElectricCurrent.AMPERE, "device_class": _DC.CURRENT, "state_class": _SC.MEASUREMENT, "icon": "mdi:solar-panel"},
    {"key": "PV1ChargingPower", "name": "PV1 Power", "unit": UnitOfPower.WATT, "device_class": _DC.POWER, "state_class": _SC.MEASUREMENT, "icon": "mdi:solar-power"},
    {"key": "pvGeneratedEnergyOfDay", "name": "PV Generated", "unit": UnitOfEnergy.KILO_WATT_HOUR, "device_class": _DC.ENERGY, "state_class": _SC.TOTAL_INCREASING, "icon": "mdi:solar-power"},
    # Diagnostic text sensors reporting the mode the device is actually in.
    # These read the same snapshot fields as the select entities, so they are a
    # quick way to see the raw label the API returned for a mode.
    {"key": "workingMode", "name": "Working Mode", "text": True, "diagnostic": True, "icon": "mdi:state-machine"},
    {"key": "chargerSourcePriority", "name": "Charger Priority (current)", "text": True, "diagnostic": True, "icon": "mdi:battery-sync", "candidates": STATE_KEY_CANDIDATES["chargerSourcePriority"]},
    {"key": "outputSourcePriority", "name": "Output Priority (current)", "text": True, "diagnostic": True, "icon": "mdi:cog", "candidates": STATE_KEY_CANDIDATES["outputSourcePriority"]},
    {"key": "chargingStatus", "name": "Charging Status", "text": True, "diagnostic": True, "icon": "mdi:battery-charging"},
]

# device_class → the unit family used to normalise a snapshot reading.
_SCALE_KIND_BY_DEVICE_CLASS = {
    _DC.POWER: "power",
    _DC.ENERGY: "energy",
}


class SolarOfThingsStateSensor(CoordinatorEntity, SensorEntity):
    """Sensor reading a single field from the state/latest endpoint."""

    def __init__(self, coordinator, station_id, device_id, device_name, definition):
        super().__init__(coordinator)
        self._station_id = station_id
        self._device_id = device_id
        self._device_name = device_name
        self._key = definition["key"]
        self._candidates = definition.get("candidates") or [self._key]
        self._is_text = definition.get("text", False)
        self._scale_kind = _SCALE_KIND_BY_DEVICE_CLASS.get(definition.get("device_class"))
        self._attr_has_entity_name = True
        self._attr_name = definition["name"]
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_state_{self._key}"
        self._attr_icon = definition.get("icon")
        if definition.get("diagnostic"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if not self._is_text:
            self._attr_native_unit_of_measurement = definition.get("unit")
            self._attr_device_class = definition.get("device_class")
            self._attr_state_class = definition.get("state_class")

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "Siseli",
            "via_device": (DOMAIN, self._station_id),
        }

    @property
    def native_value(self):
        # Candidate lookup is case-insensitive: the snapshot is inconsistent
        # about capitalisation (PV1InputVoltage vs pv1InputCurrent) and some
        # models publish a measurement under an alternative name entirely.
        _key, entry = find_entry(
            state_fields((self.coordinator.data or {}).get("state")), self._candidates
        )
        if entry is None:
            return None

        if self._is_text:
            display = entry_display(entry)
            value = display if display not in (None, "") else entry_value(entry)
            return value if value not in (None, "") else None

        number = to_float(entry_value(entry))
        if number is None:
            return None
        return round(scale_value(number, entry_unit(entry), self._scale_kind), 2)


class SolarOfThingsAlarmSensor(CoordinatorEntity, SensorEntity):
    """Reports active (firing) device alarms; 'OK' when none."""

    def __init__(self, coordinator, station_id, device_id, device_name):
        super().__init__(coordinator)
        self._station_id = station_id
        self._device_id = device_id
        self._device_name = device_name
        self._attr_has_entity_name = True
        self._attr_name = "Active Alarms"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_active_alarms"
        self._attr_icon = "mdi:alert"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "Siseli",
            "via_device": (DOMAIN, self._station_id),
        }

    @property
    def native_value(self):
        alarms = ((self.coordinator.data or {}).get("state") or {}).get("firingAlarms") or []
        names = [a.get("name") for a in alarms if isinstance(a, dict) and a.get("name")]
        return ", ".join(names) if names else "OK"

    @property
    def extra_state_attributes(self):
        alarms = ((self.coordinator.data or {}).get("state") or {}).get("firingAlarms") or []
        return {
            "count": len(alarms),
            "alarms": [a.get("name") for a in alarms if isinstance(a, dict)],
        }