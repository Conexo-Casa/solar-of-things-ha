"""2.9.1: Manyi UD10048AM extra sensors (#49).

Fields and unit tags are copied from Rinpon71's energy/flow/v1 capture
(2026-10-23, night: PV 0 V, grid absent, inverting from battery).
"""
from __future__ import annotations

from custom_components.solar_of_things.api import map_energy_flow_extras
from custom_components.solar_of_things.const import ENERGY_FLOW_EXTRA_SENSORS
from custom_components.solar_of_things.sensor import SolarOfThingsExtraSensor


def _tag(value, unit):
    return {"key": "x", "unit": unit, "value": value, "valueDisplay": str(value)}


MANYI_49 = {
    "controllerTemp": _tag(23, "°C"),
    "deviceTemp": _tag(28, "℃"),          # U+2103, same payload as °C above
    "loadPercentage": _tag(7, "%"),
    "inputVoltage": _tag(0, "V"),
    "inputFrequency": _tag(0, "Hz"),
    "controllerChargingCurrent": _tag(0, "A"),
    "inverterChargingCurrent": _tag(0, "A"),
    "pvVoltage": _tag(0, "V"),
    "outputVoltage": _tag(230.2, "V"),
    "outputFrequency": _tag(50, "Hz"),
    "batteryVoltage": _tag(53.2, "V"),
    "batteryCapacity": _tag(100, "%"),
    "systemRunTime": _tag("132D 5.1H", ""),
    "systemOperationStatus": _tag("6", ""),
}


def test_49_manyi_extras_mapped_from_capture() -> None:
    extras = map_energy_flow_extras(MANYI_49)
    assert extras == {
        "controllerTemp": 23,
        "deviceTemp": 28,
        "loadPercentage": 7,
        "inputVoltage": 0,
        "inputFrequency": 0,
        "controllerChargingCurrent": 0,
        "inverterChargingCurrent": 0,
        "pvVoltage": 0,
        "outputVoltage": 230.2,
        "outputFrequency": 50,
    }


def test_49_both_celsius_tags_accepted_wrong_units_skipped() -> None:
    extras = map_energy_flow_extras({
        "deviceTemp": _tag(28, "℃"),
        "controllerTemp": _tag(23, "°C"),
        "outputVoltage": _tag(230, "kV"),             # unexpected unit
        "outputFrequency": {"value": 50},             # untagged
        "controllerChargingCurrent": _tag(5, "mA"),   # not A
        "inverterChargingCurrent": 4,                 # bare number
    })
    assert extras == {"deviceTemp": 28, "controllerTemp": 23}


def test_49_entities_get_proper_device_class() -> None:
    def make(key):
        return SolarOfThingsExtraSensor(
            coordinator=None, station_id="s", device_id="d",
            device_name="Manyi", sensor_key=key,
        )

    temp = make("deviceTemp")
    assert temp.device_class == "temperature"
    assert temp.native_unit_of_measurement == "°C"
    assert temp.name == "Inverter Temperature"

    freq = make("outputFrequency")
    assert freq.device_class == "frequency"
    assert freq.native_unit_of_measurement == "Hz"

    solar = make("controllerChargingCurrent")
    assert solar.device_class == "current"
    assert solar.name == "Solar Charging Current"

    volts = make("outputVoltage")
    assert volts.device_class == "voltage"
    assert volts.unique_id == "solar_of_things_s_d_outputVoltage"


def test_49_names_unique() -> None:
    names = [v[0] for v in ENERGY_FLOW_EXTRA_SENSORS.values()]
    assert len(names) == len(set(names))
