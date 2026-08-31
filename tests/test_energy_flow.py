"""Tests for the energy-flow fallback mapping.

Covers the fallback added for inverter / WiFi-dongle firmware families that
never populate the historical time-series endpoint, leaving every realtime
entity "unknown" while the portal shows live data (issue #7).

The field names and the sample values in ``ISSUE_7_NIGHT_PAYLOAD`` are taken
verbatim from that report, which was captured at night — hence the zeros.
"""
from __future__ import annotations

import pytest

from custom_components.solar_of_things.api import (
    SolarOfThingsAPI,
    TokenExpiredError,
    has_realtime_values,
    map_energy_flow_fields,
)

# Exactly the fields reported in issue #7 (UWB1 inverter, night-time reading).
ISSUE_7_NIGHT_PAYLOAD = {
    "pv1Power": 0,
    "pv2Power": 0,
    "generationPower": 0,
    "batteryPower": 9,
    "positiveTerminalBatteryCurrent": 0.4,
    "negativeTerminalBatteryCurrent": 0,
    "positiveTerminalBatteryVoltage": 26.6,
    "bmsBatteryVoltage": 26.6,
    "batteryPercentage": 100,
    "bmsSOC": 100,
    "load_power": 0,
    "aPhaseOutputVoltage": 222.8,
    "aPhaseOutputFrequency": 50,
}


# ─── Pure mapping ──────────────────────────────────────────────────────────────

def test_issue_7_payload_maps_to_canonical_keys() -> None:
    """The reported payload must populate the previously-unknown sensors."""
    mapped = map_energy_flow_fields(ISSUE_7_NIGHT_PAYLOAD)

    assert mapped["pvInputPower"] == 0.0
    assert mapped["batteryVoltage"] == 26.6
    assert mapped["batterySOC"] == 100.0
    assert mapped["batteryPower"] == 9.0
    assert mapped["batteryDischargeCurrent"] == 0.4
    assert mapped["batteryChargingCurrent"] == 0.0
    assert mapped["loadPower"] == 0.0
    assert mapped["acOutputActivePower"] == 0.0


def test_mains_power_fields_are_not_mapped() -> None:
    """Unit for the per-phase mains fields is unconfirmed, so stay out.

    Publishing a possibly-1000x-wrong value into the Energy dashboard is worse
    than leaving the sensor unknown. See ENERGY_FLOW_UNVERIFIED in const.py.
    """
    mapped = map_energy_flow_fields(
        {"aPhaseMainsPower": 500, "bPhaseMainsPower": 0, "cPhaseMainsPower": 0}
    )
    assert mapped == {}


def test_multi_string_pv_is_summed_and_kw_is_scaled() -> None:
    mapped = map_energy_flow_fields(
        {"pv1Power": 1200, "pv2Power": 800, "load_power": 1.5}
    )
    assert mapped["pvInputPower"] == 2000.0
    assert mapped["loadPower"] == 1500.0  # kW → W


def test_generation_power_is_only_a_pv_fallback() -> None:
    """generationPower (kW) is used only when no per-string field exists."""
    assert map_energy_flow_fields({"generationPower": 2.4})["pvInputPower"] == 2400.0
    # A per-string reading always wins over the aggregate.
    both = {"pv1Power": 500, "generationPower": 2.4}
    assert map_energy_flow_fields(both)["pvInputPower"] == 500.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (77, 77.0),
        ("77", 77.0),
        ({"value": 63}, 63.0),
        ([10, 20, 44], 44.0),  # latest-wins, as the time-series endpoint returns
    ],
)
def test_accepts_the_value_shapes_this_portal_uses(raw, expected) -> None:
    assert map_energy_flow_fields({"bmsSOC": raw})["batterySOC"] == expected


@pytest.mark.parametrize("raw", [None, True, False, "n/a", "", {}, []])
def test_rejects_unusable_values_rather_than_publishing_garbage(raw) -> None:
    assert "batterySOC" not in map_energy_flow_fields({"bmsSOC": raw})


@pytest.mark.parametrize("payload", [None, {}, [1, 2], "text", 0])
def test_hostile_input_returns_empty_mapping(payload) -> None:
    assert map_energy_flow_fields(payload) == {}


def test_unknown_firmware_fields_are_ignored() -> None:
    assert map_energy_flow_fields({"someBrandNewKey": 5}) == {}


# ─── Realtime probe ────────────────────────────────────────────────────────────

def test_probe_treats_zero_as_a_real_reading() -> None:
    """A device reporting 0 W at night is working — must not trigger fallback."""
    assert has_realtime_values({"pvInputPower": 0}) is True


@pytest.mark.parametrize(
    "values", [{}, {"pvInputPower": None}, {"loadPower": 5}, None, "text"]
)
def test_probe_false_when_no_realtime_key_has_a_value(values) -> None:
    assert has_realtime_values(values) is False


# ─── fetch_latest_data integration ─────────────────────────────────────────────

@pytest.fixture
def api_factory():
    """Build an API instance with stubbed transport, tracking endpoint calls."""

    def _factory(history_fields, flow_fields=None, flow_error=None):
        api = SolarOfThingsAPI(iot_token="test-token")
        api._ensure_token_valid = lambda: None  # no network
        calls = {"time_series": 0, "energy_flow": 0}

        def fake_post(path, payload, **kwargs):
            calls["time_series"] += 1
            return {"code": 0, "data": {"payload": {"fields": history_fields}}}

        def fake_get(path, params, **kwargs):
            calls["energy_flow"] += 1
            if flow_error is not None:
                raise flow_error
            return {
                "code": 0,
                "data": {"deviceAttributeState": {"fields": flow_fields or {}}},
            }

        api._post = fake_post
        api._get = fake_get
        return api, calls

    return _factory


def test_working_device_is_unaffected(api_factory) -> None:
    """Regression guard: values and call pattern must match pre-fallback code."""
    history = {
        "pvInputPower": [100],
        "acOutputActivePower": [1.2],
        "batteryVoltage": [52.0],
        "batteryDischargeCurrent": [2.0],
        "batteryChargingCurrent": [0.0],
        "feedInPower": [0],
        "batterySOC": [90],
    }
    api, calls = api_factory(history, flow_fields={"bmsSOC": 1})
    result = api.fetch_latest_data("device-1")

    assert result["acOutputActivePower"] == 1200.0     # kW → W
    assert result["batteryPower"] == 104.0             # (2.0 - 0.0) * 52.0
    assert result["gridPower"] == 1204.0               # max(0, 1200-100+104+0)
    assert result["loadPower"] == 1200.0
    # The fallback must cost a working install nothing.
    assert calls["energy_flow"] == 0


def test_fallback_populates_sensors_when_time_series_is_empty(api_factory) -> None:
    api, calls = api_factory({}, flow_fields=ISSUE_7_NIGHT_PAYLOAD)
    result = api.fetch_latest_data("device-2")

    assert calls["energy_flow"] == 1
    assert result["batteryVoltage"] == 26.6
    assert result["batterySOC"] == 100.0
    assert result["batteryDischargeCurrent"] == 0.4


def test_measured_battery_power_is_not_overwritten_by_the_estimate(api_factory) -> None:
    """The flow endpoint reports batteryPower directly; keep it.

    The derived estimate would give (0.4 - 0) * 26.6 = 10.64 W here.
    """
    api, _ = api_factory({}, flow_fields=ISSUE_7_NIGHT_PAYLOAD)
    assert api.fetch_latest_data("device-3")["batteryPower"] == 9.0


def test_time_series_values_win_over_the_fallback(api_factory) -> None:
    api, calls = api_factory({"batterySOC": [42]}, flow_fields={"bmsSOC": 99})
    result = api.fetch_latest_data("device-4")

    assert result["batterySOC"] == 42
    assert calls["energy_flow"] == 0


def test_flow_endpoint_failure_degrades_quietly(api_factory) -> None:
    """An unsupported endpoint must not fail the whole coordinator update."""
    api, _ = api_factory({}, flow_error=RuntimeError("404 not supported"))
    result = api.fetch_latest_data("device-5")

    assert isinstance(result, dict)
    assert result["loadPower"] == 0.0


def test_token_expiry_propagates_for_reauth(api_factory) -> None:
    """TokenExpiredError must reach the coordinator so re-auth can start."""
    api, _ = api_factory({}, flow_error=TokenExpiredError("expired"))
    with pytest.raises(TokenExpiredError):
        api.fetch_latest_data("device-6")


def test_unknown_firmware_logs_field_names_for_reporting(api_factory, caplog) -> None:
    api, _ = api_factory({}, flow_fields={"someBrandNewKey": 5, "another": 7})
    api.fetch_latest_data("device-7")

    assert "another" in caplog.text and "someBrandNewKey" in caplog.text
