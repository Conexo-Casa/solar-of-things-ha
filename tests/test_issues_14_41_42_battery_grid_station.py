"""v2.8.3: honest battery/grid estimates (#42), measured grid import (#41),
non-blocking time-zone check + station picker (#14).

Payloads are trimmed from the reporters' own captures:
- #42 (Datouboss JC-5052, 2026-10-14): Battery Power 0.0 W while SOC rose
  85 -> 89 % in 15 min; Battery Charging Current never reported.
- #41 (Gospower via RWB1, 2026-10-13): energy-flow ``acInputPower`` tagged
  kW, value 0, no grid connected — integration showed 90 W Grid Import.
- #14 / #42: ``POST /apis/station/list`` -> data.list[].id/name, found by
  the #42 reporter in the portal's JS bundle.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.solar_of_things.api import (
    SolarOfThingsAPI,
    map_energy_flow_fields,
)
from custom_components.solar_of_things.util import is_valid_time_zone


def _api(history, flow_fields=None):
    api = SolarOfThingsAPI(iot_token="t")
    api._ensure_token_valid = lambda: None
    api._post = lambda *a, **k: {"code": 0, "data": {"payload": {"fields": history}}}
    api._get = lambda *a, **k: {
        "code": 0,
        "data": {"deviceAttributeState": {"fields": flow_fields or {}}},
    }
    return api


def _tag(value, unit):
    return {"unit": unit, "value": value}


# ── #42: battery power is not invented from a missing current ────────────────
def test_42_missing_charging_current_leaves_battery_power_unknown() -> None:
    api = _api(
        {
            "acOutputActivePower": [0.98],
            "pvInputPower": [1560],
            "batteryVoltage": [53.8],
            "batteryDischargeCurrent": [0.0],
            "batterySOC": [85],
            # batteryChargingCurrent: never reported on this model
        }
    )
    result = api.fetch_latest_data("jc5052")
    assert result["batteryPower"] is None          # was a fabricated 0.0 W
    # Grid import balances against battery power, so it is unknown too
    # rather than a number built on the same hole.
    assert result["gridPower"] is None
    assert result["loadPower"] == 980.0            # unaffected


def test_complete_currents_still_estimate_battery_power() -> None:
    """Owner-device regression guard: all three inputs present -> unchanged."""
    api = _api(
        {
            "pvInputPower": [100],
            "acOutputActivePower": [1.2],
            "batteryVoltage": [52.0],
            "batteryDischargeCurrent": [2.0],
            "batteryChargingCurrent": [0.0],
            "feedInPower": [0],
            "batterySOC": [90],
        }
    )
    result = api.fetch_latest_data("owned")
    assert result["batteryPower"] == 104.0
    assert result["gridPower"] == 1204.0


def test_measured_battery_power_still_feeds_grid_estimate() -> None:
    """A real batteryPower (energy-flow) still drives the grid estimate."""
    api = _api({}, {"batteryPower": _tag(0.127, "kW"),
                    "acOutputActivePower": _tag(0.715, "kW"),
                    "generationPower": _tag(1.114, "kW")})
    result = api.fetch_latest_data("x")
    assert result["batteryPower"] == pytest.approx(127.0)
    assert result["gridPower"] is not None


# ── #41: measured AC input power beats the estimate ──────────────────────────
GOSPOWER_41 = {
    "acInputPower": _tag(0, "kW"),
    "acInputVoltage": _tag(0, "V"),
    "acOutputActivePower": _tag(0.715, "kW"),
    "generationPower": _tag(1.114, "kW"),
    "batteryPower": _tag(0.127, "kW"),
    "batterySOC": _tag(73, "%"),
    "batteryVoltage": _tag(53.3, "V"),
}


def test_41_ac_input_power_maps_to_grid_import() -> None:
    assert map_energy_flow_fields(GOSPOWER_41)["gridPower"] == 0.0


def test_41_grid_import_reads_zero_with_no_grid() -> None:
    api = _api({}, GOSPOWER_41)
    result = api.fetch_latest_data("gospower")
    assert result["gridPower"] == 0.0              # was a derived 90 W


def test_41_untagged_ac_input_power_is_not_guessed() -> None:
    assert "gridPower" not in map_energy_flow_fields({"acInputPower": 0.4})


def test_41_tagged_ac_input_power_is_converted() -> None:
    assert map_energy_flow_fields({"acInputPower": _tag(0.4, "kW")})[
        "gridPower"
    ] == pytest.approx(400.0)


# ── #14: station list + cached time-zone check ───────────────────────────────
def test_list_stations_parses_portal_shape() -> None:
    api = SolarOfThingsAPI(iot_token="t")
    api._ensure_token_valid = lambda: None
    seen = {}

    def fake_post(path, payload, **kw):
        seen["path"], seen["payload"] = path, payload
        return {"code": 0, "data": {"list": [
            {"id": 434267123856932864, "name": "Home"},
            {"id": "", "name": "broken"},
            {"id": "99", "name": None},
        ]}}

    api._post = fake_post
    assert api.list_stations() == [
        {"id": "434267123856932864", "name": "Home"},
        {"id": "99", "name": "99"},
    ]
    assert seen["path"] == "/apis/station/list"
    assert seen["payload"] == {"page": 1, "count": 50}


def test_list_stations_error_code_raises() -> None:
    api = SolarOfThingsAPI(iot_token="t")
    api._ensure_token_valid = lambda: None
    api._post = lambda *a, **k: {"code": 20101, "message": "Illegal argument"}
    with pytest.raises(RuntimeError):
        api.list_stations()


def test_time_zone_set_is_read_once() -> None:
    from custom_components.solar_of_things import util

    util._cached_timezones.cache_clear()
    with patch.object(util, "available_timezones", return_value={"Europe/Budapest"}) as tz:
        assert is_valid_time_zone("Europe/Budapest")
        assert not is_valid_time_zone("Europe")
        assert tz.call_count == 1
    util._cached_timezones.cache_clear()
