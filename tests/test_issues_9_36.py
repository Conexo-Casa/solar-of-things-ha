"""Regression tests for #9 (PV2 missing from PV total) and #36 (grid voltage).

Payloads are trimmed from real captures:

* #9 — Victor 19.2 energy-flow capture: pvInputPower 538 W ("PV1 Input
  Power"), pv2InputPower 2021 W, generationPower 2.559 kW. PV1 + PV2 equals
  the portal's own generation total, which proves pvInputPower is PV1 only.
* PR #29 — time-series capture (no unit metadata): pvInputPower 6.0,
  pv2InputPower 0.0, generationPower 0.006 — the same PV1 + PV2 = total
  relationship in W, plus acInputVoltage 232.6.
"""
from __future__ import annotations

import pytest

from custom_components.solar_of_things.api import (
    SolarOfThingsAPI,
    map_energy_flow_fields,
)


@pytest.fixture
def api_factory():
    def _factory(history_fields, flow_fields=None):
        api = SolarOfThingsAPI(iot_token="test-token")
        api._ensure_token_valid = lambda: None
        api._post = lambda path, payload, **kw: {
            "code": 0, "data": {"payload": {"fields": history_fields}},
        }
        api._get = lambda path, params, **kw: {
            "code": 0, "data": {"deviceAttributeState": {"fields": flow_fields or {}}},
        }
        return api

    return _factory


def _full(**overrides):
    base = {
        "acOutputActivePower": [0.091],
        "batteryVoltage": [53.8],
        "batteryChargingCurrent": [40.0],
        "batteryDischargeCurrent": [0.0],
        "feedInPower": [0.0],
        "batteryCapacity": [56.0],
    }
    base.update(overrides)
    return base


def test_9_pv_total_includes_pv2_on_time_series(api_factory) -> None:
    api = api_factory(_full(
        pvInputPower=[538.0], pv2InputPower=[2021.0],
        pvInputVoltage=[151.8], pv2InputVoltage=[244.1],
    ))
    result = api.fetch_latest_data("victor")

    assert result["pvInputPower"] == 2559.0      # = portal 2.559 kW
    assert result["pv1InputPower"] == 538.0
    assert result["pv2InputPower"] == 2021.0
    assert result["pvInputVoltage"] == 151.8
    assert result["pv2InputVoltage"] == 244.1


def test_pr29_capture_pv_sum_matches_generation_power(api_factory) -> None:
    api = api_factory(_full(
        pvInputPower=[6.0], pv2InputPower=[0.0], acInputVoltage=[232.6],
    ))
    result = api.fetch_latest_data("pr29")

    assert result["pvInputPower"] == 6.0         # generationPower 0.006 kW
    assert result["acInputVoltage"] == 232.6


def test_single_string_device_is_unchanged(api_factory) -> None:
    api = api_factory(_full(pvInputPower=[100.0]))
    result = api.fetch_latest_data("single")

    assert result["pvInputPower"] == 100.0
    assert result["pv1InputPower"] == 100.0
    assert "pv2InputPower" not in result


def test_hpvinv02_alias_total_is_not_double_counted(api_factory) -> None:
    """pvPower (HPVINV02 alias) is already a device total, in kW."""
    api = api_factory(_full(pvPower=[1.5], pv2InputPower=[300.0]))
    result = api.fetch_latest_data("hpvinv02")

    assert result["pvInputPower"] == 1500.0
    assert "pv1InputPower" not in result


def test_9_energy_flow_per_string_and_grid_voltage() -> None:
    mapped = map_energy_flow_fields({
        "pvInputPower": {"unit": "W", "value": 538},
        "pv2InputPower": {"unit": "W", "value": 2021},
        "pvInputVoltage": {"unit": "V", "value": 151.8},
        "pv2InputVoltage": {"unit": "V", "value": 244.1},
        "acInputVoltage": {"unit": "V", "value": 226.3},
    })
    assert mapped["pvInputPower"] == 2559.0
    assert mapped["pv1InputPower"] == 538.0
    assert mapped["pv2InputPower"] == 2021.0
    assert mapped["pvInputVoltage"] == 151.8
    assert mapped["pv2InputVoltage"] == 244.1
    assert mapped["acInputVoltage"] == 226.3


def test_srne_per_string_kw_converted() -> None:
    mapped = map_energy_flow_fields({"pv1RealTimePower": 0.493, "pv2RealTimePower": 0.416})
    assert mapped["pv1InputPower"] == pytest.approx(493.0)
    assert mapped["pv2InputPower"] == pytest.approx(416.0)


def test_36_grid_voltage_zero_means_grid_down() -> None:
    """#36: 0 V must publish as 0, not unknown — it's the 'no grid' signal."""
    assert map_energy_flow_fields({"acInputVoltage": 0})["acInputVoltage"] == 0.0
