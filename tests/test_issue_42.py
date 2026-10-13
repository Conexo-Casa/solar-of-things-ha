"""#42: acOutputActivePower unit taken from the device's own energy-flow tag.

Datouboss JC-5052 / JC-50521 dongle reports acOutputActivePower already in W
(integration showed 956000 W vs 976 W on the reporter's meter).  Gospower via
RWB1 (#41) tags the same key "kW" (value 0.715).  The time-series endpoint is
untagged, so the factor comes from the energy-flow payload.
"""
from __future__ import annotations

from custom_components.solar_of_things.api import (
    EnergyFlowRuleNotConfiguredError,
    SolarOfThingsAPI,
)

HISTORY = {
    "pvInputPower": [300],
    "batteryVoltage": [53.0],
    "batteryDischargeCurrent": [0.0],
    "batteryChargingCurrent": [0.0],
    "feedInPower": [0],
    "batterySOC": [49],
}


def _api(ac_value, flow_fields=None, flow_error=None):
    api = SolarOfThingsAPI(iot_token="t")
    api._ensure_token_valid = lambda: None
    calls = {"flow": 0}
    history = {**HISTORY, "acOutputActivePower": [ac_value]}
    api._post = lambda *a, **k: {"code": 0, "data": {"payload": {"fields": history}}}

    def fake_get(*a, **k):
        calls["flow"] += 1
        if flow_error is not None:
            raise flow_error
        return {"code": 0, "data": {"deviceAttributeState": {"fields": flow_fields or {}}}}

    api._get = fake_get
    return api, calls


def test_42_w_tagged_device_is_not_multiplied() -> None:
    api, calls = _api(976, {"acOutputActivePower": {"unit": "W", "value": 976}})
    result = api.fetch_latest_data("jc5052")
    assert result["acOutputActivePower"] == 976.0
    assert result["loadPower"] == 976.0
    assert result["gridPower"] == 676.0          # 976 - 300 + 0 + 0
    api.fetch_latest_data("jc5052")
    assert calls["flow"] == 1                    # unit looked up once


def test_41_kw_tagged_device_still_converted() -> None:
    api, _ = _api(0.715, {"acOutputActivePower": {"unit": "kW", "value": 0.715}})
    assert api.fetch_latest_data("gospower")["acOutputActivePower"] == 715.0


def test_untagged_keeps_historic_kw_assumption() -> None:
    api, _ = _api(1.2, {"bmsSOC": 1})
    assert api.fetch_latest_data("d")["acOutputActivePower"] == 1200.0


def test_no_energy_flow_rule_keeps_kw() -> None:
    api, _ = _api(1.2, flow_error=EnergyFlowRuleNotConfiguredError("70132"))
    assert api.fetch_latest_data("d")["acOutputActivePower"] == 1200.0


def test_transport_error_falls_back_and_retries() -> None:
    api, calls = _api(1.2, flow_error=RuntimeError("boom"))
    assert api.fetch_latest_data("d")["acOutputActivePower"] == 1200.0
    api.fetch_latest_data("d")
    assert calls["flow"] >= 2                    # not cached; retried
