"""Datouboss HPVINV04 per-string PV (#51).

Fields, unit tags and values are copied from montemarzano75's energy/flow/v1
capture (2026-11-03T13:23:20Z, both strings producing).  Portal at that moment:
PV 136.8 V / 0.085 kW, PV2 406.6 V / 0.45 kW, Generation Power 0.535 kW.

The HPVINV04 names MPPT1 ``pv*`` (no "1") and MPPT2 ``pv2*``, and its
time-series ``pvPower`` is MPPT1 only.  Before this fix PV1/PV2 Input Voltage
were unknown, PV1 Input Power was unknown and PV Input Power showed MPPT1 only.
"""
from __future__ import annotations

import pytest

from custom_components.solar_of_things.api import SolarOfThingsAPI, split_pv_strings


def _tag(value, unit):
    return {"key": "x", "unit": unit, "value": value, "valueDisplay": str(value)}


HPVINV04_51 = {
    "pvVoltage": _tag(136.8, "V"),
    "pv2Voltage": _tag(406.6, "V"),
    "pvCurrent": _tag(0.6, "A"),
    "pv2Current": _tag(1.1, "A"),
    "pvPower": _tag(0.085, "kW"),
    "pv2Power": _tag(0.45, "kW"),
    "generationPower": _tag(0.535, "kW"),
    "batteryVoltage": _tag(53.3, "V"),
    "outputVoltage": _tag(238, "V"),
}


def test_51_split_from_capture() -> None:
    out = split_pv_strings(HPVINV04_51)
    assert out["pvInputVoltage"] == 136.8
    assert out["pv2InputVoltage"] == 406.6
    assert out["pv1InputPower"] == pytest.approx(85.0)
    assert out["pv2InputPower"] == pytest.approx(450.0)
    assert out["pvInputPower"] == pytest.approx(535.0)   # = generationPower


def test_51_single_string_models_unchanged() -> None:
    """Manyi (#49) / Gospower (#41) report pvVoltage only: no per-string map."""
    assert split_pv_strings({"pvVoltage": _tag(235.2, "V"),
                             "generationPower": _tag(1.114, "kW")}) == {}


def test_51_pvpower_as_total_is_not_double_counted() -> None:
    """If pvPower already equals generationPower (a device-total pvPower, as on
    the HPVINV02 in #13), the sum check fails and powers are left alone."""
    out = split_pv_strings({
        "pvPower": _tag(1.35, "kW"),
        "pv2Power": _tag(0.6, "kW"),
        "generationPower": _tag(1.35, "kW"),
    })
    assert "pvInputPower" not in out and "pv1InputPower" not in out


def test_51_untagged_values_are_not_guessed() -> None:
    out = split_pv_strings({
        "pvVoltage": 136.8, "pv2Voltage": 406.6,           # bare numbers
        "pvPower": 0.085, "pv2Power": 0.45, "generationPower": 0.535,
    })
    assert out == {}


def test_51_end_to_end_time_series_alias_path() -> None:
    """Time-series returns pvPower (MPPT1, kW) and pv2InputPower; energy-flow
    supplies the strings.  PV Input Power must become MPPT1 + MPPT2."""
    api = SolarOfThingsAPI(iot_token="t")
    api._ensure_token_valid = lambda: None
    history = {
        "pvPower": [0.085],
        "batteryVoltage": [53.3],
        "batterySOC": [91],
        "batteryDischargeCurrent": [0.0],
        "batteryChargingCurrent": [5.0],
        "outputActivePower": [0.4],
        "feedInPower": [0],
    }
    api._post = lambda path, payload, **kw: {
        "code": 0, "data": {"payload": {"fields": history}}}
    api._get = lambda path, params, **kw: {
        "code": 0, "data": {"deviceAttributeState": {"fields": HPVINV04_51}}}

    result = api.fetch_latest_data("hpvinv04")

    assert result["pvInputVoltage"] == 136.8
    assert result["pv2InputVoltage"] == 406.6
    assert result["pv1InputPower"] == pytest.approx(85.0)
    assert result["pv2InputPower"] == pytest.approx(450.0)
    assert result["pvInputPower"] == pytest.approx(535.0)
