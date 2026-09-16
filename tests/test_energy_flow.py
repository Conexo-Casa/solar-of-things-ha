"""Tests for the energy-flow fallback mapping.

Covers the fallback added for inverter / WiFi-dongle firmware families that
never populate the historical time-series endpoint, leaving every realtime
entity "unknown" while the portal shows live data (issue #7).

The field names and the sample values in ``ISSUE_7_NIGHT_PAYLOAD`` are taken
verbatim from that report, which was captured at night — hence the zeros.
The daylight payloads (``ISSUE_7_AC_PV_CHARGING`` / ``ISSUE_7_NOAC_PV_DISCHARGING``)
are trimmed from hidemichixt-creator's four-state capture set posted
2026-09-15, which settled the unit and sign questions the night capture
could not.
"""
from __future__ import annotations

import pytest

from custom_components.solar_of_things.api import (
    EnergyFlowRuleNotConfiguredError,
    SolarOfThingsAPI,
    TokenExpiredError,
    has_realtime_values,
    map_energy_flow_fields,
)
from custom_components.solar_of_things.const import ENERGY_FLOW_UNVERIFIED

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

# Trimmed from UPS_AC_PV_BatteryCharging.txt (issue #7, 2026-09-15): AC
# connected, PV producing, battery charging.
ISSUE_7_AC_PV_CHARGING = {
    "pv1Power": 234,
    "pv2Power": 0,
    "load_power": 0.614,  # kW, per the payload's own "unit" field
    "aPhaseMainsPower": -1100,  # W, per the payload's own "unit" field
    "bPhaseMainsPower": 0,
    "cPhaseMainsPower": 0,
    "positiveTerminalBatteryCurrent": -27,
    "negativeTerminalBatteryCurrent": 0,
    "batteryPower": -720,
    "bmsSOC": 54,
}

# Trimmed from UPS_NoAC_PV_BatteryDischarging.txt (issue #7, 2026-09-15): AC
# disconnected, PV producing, battery discharging.
ISSUE_7_NOAC_PV_DISCHARGING = {
    "pv1Power": 262,
    "pv2Power": 0,
    "load_power": 0.635,
    "aPhaseMainsPower": 0,
    "bPhaseMainsPower": 0,
    "cPhaseMainsPower": 0,
    "positiveTerminalBatteryCurrent": 17.6,
    "negativeTerminalBatteryCurrent": 0,
    "batteryPower": 462,
    "bmsSOC": 54,
}

# Trimmed from UPS_AC_PV_GridFeeding.txt (issue #7, 2026-09-16): the capture
# hidemichixt-creator took specifically to settle the positive/exporting case
# left unconfirmed in v2.6.1 — PV surplus after a full battery is being fed
# back to the grid.
ISSUE_7_GRID_FEEDING = {
    "pv1Power": 897,
    "pv2Power": 0,
    "load_power": 0.351,
    "aPhaseMainsPower": 495,
    "bPhaseMainsPower": 0,
    "cPhaseMainsPower": 0,
    "positiveTerminalBatteryCurrent": 0,
    "negativeTerminalBatteryCurrent": 0,
    "batteryPower": 0,  # battery full (96% SOC), neither charging nor discharging
    "bmsSOC": 96,
}


# ─── Pure mapping ──────────────────────────────────────────────────────────────

def test_issue_7_payload_maps_to_canonical_keys() -> None:
    """The reported payload must populate the previously-unknown sensors."""
    mapped = map_energy_flow_fields(ISSUE_7_NIGHT_PAYLOAD)

    # Units confirmed by a non-zero observed value in the report — publishable.
    assert mapped["pvInputPower"] == 0.0
    assert mapped["batteryVoltage"] == 26.6
    assert mapped["batterySOC"] == 100.0
    assert mapped["batteryPower"] == 9.0
    # Confirmed by the 2026-09-15 daylight captures (see below) — 0 at night
    # is a real reading now, not an unconfirmed guess.
    assert mapped["acOutputActivePower"] == 0.0
    assert mapped["batteryChargingCurrent"] == 0.0
    assert mapped["batteryDischargeCurrent"] == 0.4  # idle trickle, per the report

    # loadPower (camelCase) has no confirmed source — must stay ABSENT rather
    # than publish a possibly-wrong value. See ENERGY_FLOW_UNVERIFIED in const.py.
    assert "loadPower" not in mapped


def test_ac_output_power_mapped_from_load_power_kw() -> None:
    """load_power is confirmed kW by the payload's own "unit" tag → x1000."""
    mapped = map_energy_flow_fields(ISSUE_7_AC_PV_CHARGING)
    assert mapped["acOutputActivePower"] == 614.0


def test_grid_import_and_feed_in_split_from_signed_mains_power() -> None:
    """aPhaseMainsPower is confirmed W; negative means importing from mains.

    Sign confirmed by conservation of power: load (614 W) + battery charging
    (720 W) - PV (234 W) = 1100 W, matching |aPhaseMainsPower| exactly.
    """
    mapped = map_energy_flow_fields(ISSUE_7_AC_PV_CHARGING)
    assert mapped["gridPower"] == 1100.0
    assert mapped["feedInPower"] == 0.0  # not exporting while importing

    # No AC connection at all -> the field reads 0, which is a real
    # "no grid" measurement, not a missing one.
    mapped_no_ac = map_energy_flow_fields(ISSUE_7_NOAC_PV_DISCHARGING)
    assert mapped_no_ac["gridPower"] == 0.0
    assert mapped_no_ac["feedInPower"] == 0.0


def test_feed_in_power_positive_case_confirmed_by_direct_export_capture() -> None:
    """v2.6.1 shipped Grid Feed-in Power's positive/exporting case inferred
    only by symmetry — no capture had shown a device actually exporting.
    hidemichixt-creator's follow-up capture (issue #7, 2026-09-16) settles it:
    PV surplus (897 W) after a full battery (0 W charge/discharge) with a
    351 W load leaves ~546 W to go somewhere, and aPhaseMainsPower reads
    +495 W (the ~50 W gap is ordinary inverter conversion loss) — positive
    really does mean exporting, matching the prediction exactly.
    """
    mapped = map_energy_flow_fields(ISSUE_7_GRID_FEEDING)
    assert mapped["feedInPower"] == 495.0
    assert mapped["gridPower"] == 0.0  # not importing while exporting


def test_battery_charging_and_discharge_current_split_by_sign() -> None:
    """positiveTerminalBatteryCurrent flips sign with charge direction.

    Confirmed across all four states captured for issue #7: negative while
    charging, positive while discharging.
    """
    charging = map_energy_flow_fields(ISSUE_7_AC_PV_CHARGING)
    assert charging["batteryChargingCurrent"] == 27.0
    assert charging["batteryDischargeCurrent"] == 0.0

    discharging = map_energy_flow_fields(ISSUE_7_NOAC_PV_DISCHARGING)
    assert discharging["batteryChargingCurrent"] == 0.0
    assert discharging["batteryDischargeCurrent"] == 17.6


def test_unverified_fields_are_never_mapped() -> None:
    """No field in ENERGY_FLOW_UNVERIFIED may produce a sensor value.

    A 1000x-wrong power value feeds the HA Energy dashboard and long-term
    statistics, which a later fix cannot un-poison; an inverted charge/discharge
    current is actively misleading. Both are worse than an unknown sensor.

    This is the guard that stops a well-meaning change from re-enabling one of
    these before a confirming capture exists.
    """
    for field in ENERGY_FLOW_UNVERIFIED:
        assert map_energy_flow_fields({field: 500}) == {}, field

    # And as a group, mirroring the shape of a real payload.
    assert map_energy_flow_fields({f: 500 for f in ENERGY_FLOW_UNVERIFIED}) == {}


def test_multi_string_pv_is_summed_at_face_value() -> None:
    """Per-string PV inputs are reported in W and summed without scaling."""
    mapped = map_energy_flow_fields(
        {"pv1Power": 1200, "pv2Power": 800, "load_power": 1.5}
    )
    assert mapped["pvInputPower"] == 2000.0
    # load_power would need an unconfirmed kW→W conversion, so it stays out.
    assert "loadPower" not in mapped


def test_generation_power_is_not_used_as_a_pv_fallback() -> None:
    """generationPower is an aggregate in kW and its x1000 is unconfirmed.

    Excluding it means a device reporting ONLY generationPower gets an unknown
    PV sensor rather than one that may be 1000x wrong.
    """
    assert map_energy_flow_fields({"generationPower": 2.4}) == {}
    # A per-string reading is still mapped when one is present.
    assert (
        map_energy_flow_fields({"pv1Power": 500, "generationPower": 2.4})[
            "pvInputPower"
        ]
        == 500.0
    )


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


def test_hpvinv02_alternate_key_names_are_mapped_to_canonical(api_factory) -> None:
    """Siseli HPVINV02 ("Inverter Top One" gather protocol) reports PV/AC/SOC
    under pvPower / outputActivePower / batteryCapacity instead of the
    documented pvInputPower / acOutputActivePower / batterySOC — these stayed
    "unknown" forever until the alias mapping was added.
    """
    history = {
        "pvPower": [1.5],
        "outputActivePower": [1.1],
        "batteryCapacity": [77],
        "batteryVoltage": [52.0],
        "batteryDischargeCurrent": [2.0],
        "batteryChargingCurrent": [0.0],
        "feedInPower": [0],
    }
    api, calls = api_factory(history, flow_fields={"bmsSOC": 1})
    result = api.fetch_latest_data("device-hpvinv02")

    assert result["pvInputPower"] == 1500.0        # kW → W, via the alias
    assert result["acOutputActivePower"] == 1100.0  # kW → W, via the alias
    assert result["batterySOC"] == 77
    # The alternate keys must not leak into the published values.
    assert "pvPower" not in result
    assert "outputActivePower" not in result
    assert "batteryCapacity" not in result
    # Derived values still come from the shared _apply_derived_values path.
    assert result["batteryPower"] == 104.0          # (2.0 - 0.0) * 52.0
    assert result["loadPower"] == 1100.0
    assert calls["energy_flow"] == 0


def test_documented_keys_win_when_a_device_reports_both(api_factory) -> None:
    """A device that already uses the documented key names must be unaffected
    by the alias — the canonical value always wins, the alias is discarded,
    and (critically) pvInputPower is NOT kW->W converted on this path: it's
    already W for every device this integration supported before HPVINV02,
    and converting it unconditionally regressed test_working_device_is_unaffected.
    """
    history = {
        "pvInputPower": [2.0],
        "pvPower": [999],
        "acOutputActivePower": [1.0],
        "batterySOC": [55],
        "batteryCapacity": [10],
    }
    api, _ = api_factory(history, flow_fields={})
    result = api.fetch_latest_data("device-both-keys")

    assert result["pvInputPower"] == 2.0
    assert result["batterySOC"] == 55


def test_fallback_populates_sensors_when_time_series_is_empty(api_factory) -> None:
    api, calls = api_factory({}, flow_fields=ISSUE_7_NIGHT_PAYLOAD)
    result = api.fetch_latest_data("device-2")

    assert calls["energy_flow"] == 1
    assert result["batteryVoltage"] == 26.6
    assert result["batterySOC"] == 100.0
    assert result["batteryPower"] == 9.0


def test_measured_battery_power_is_not_overwritten_by_the_estimate(api_factory) -> None:
    """The flow endpoint reports batteryPower directly; keep it.

    The terminal currents are no longer mapped from flow data (direction
    unconfirmed), so no voltage x current estimate can be derived from this
    payload at all — but the no-clobber precedence must still hold for devices
    that get their currents from the time-series path.
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


def test_energy_flow_rule_not_configured_logs_a_warning(api_factory, caplog) -> None:
    """Issue #21: this failure mode looked identical to "no data" — no
    sensors AND no warning — because it fell into the same silent DEBUG-level
    except clause as an unsupported/404 endpoint. It must be loud by default,
    since the fix (configuring an energy-flow rule on the portal) is on the
    user/installer's side, not something a future field mapping can resolve.
    """
    api, _ = api_factory(
        {}, flow_error=EnergyFlowRuleNotConfiguredError("code=70132 message=Energy flow rule not exists")
    )
    with caplog.at_level("WARNING"):
        result = api.fetch_latest_data("device-8")

    assert isinstance(result, dict)  # still degrades quietly, not a raised error
    assert any(record.levelname == "WARNING" for record in caplog.records)
    assert "energy-flow rule" in caplog.text.lower()


def test_unknown_firmware_logs_field_names_for_reporting(api_factory, caplog) -> None:
    api, _ = api_factory({}, flow_fields={"someBrandNewKey": 5, "another": 7})
    api.fetch_latest_data("device-7")

    assert "another" in caplog.text and "someBrandNewKey" in caplog.text
