"""Regression tests for #32, #35 and #37 (energy-flow fallback gaps).

Every payload here is trimmed from a raw capture posted on the issue it
names; none of the values are invented.

* #37 — DatouBoss 4863U (SRNE, protocol JI4649841): time-series returns the
  battery keys but no power keys, so the old all-or-nothing probe skipped the
  fallback and derived Grid Import from the battery discharge instead.  Field
  units confirmed against the inverter's RS485 registers by the reporter.
* #35 — EASUN ISolar-SMH-II / RWB1-04: PV power only on the pvPanelFlow card,
  and the time-series returned pvInputPower=None, which setdefault() kept.
* #9 / #24 — unit-tagged keys whose unit differs by model (Victor 19.2 vs
  Powmr MEGA-ECO) — mapped from the payload's own "unit" tag only.
"""
from __future__ import annotations

import logging

import pytest

from custom_components.solar_of_things.api import (
    SolarOfThingsAPI,
    map_energy_flow_fields,
    missing_realtime_keys,
)


def _tag(value, unit):
    return {"unit": unit, "value": value}


# ─── #37 DatouBoss 4863U ───────────────────────────────────────────────────────
ISSUE_37_TIME_SERIES = {
    "pvInputPower": [None],
    "acOutputActivePower": [None],
    "batteryDischargeCurrent": [0.8],
    "batteryChargingCurrent": [0.0],
    "batteryVoltage": [53.0],
    "feedInPower": [None],
    "batterySOC": [86.0],
}
ISSUE_37_FLOW = {
    "pv1RealTimePower": 0.493,          # kW (portal column "PV1 Real Time Power (kW)")
    "pv2RealTimePower": 0.416,          # kW
    "generationPower": 0.909,           # kW, untagged here — must not be needed
    "loadPower": 387,                   # W  ("Load Power (W)")
    "mainsInputRealTimePower": 0,       # W, unsigned
    "batteryVoltage": 53.0,
    "batteryCapacity": 86,
    "DCFlagPosition": 0,
}

# ─── #35 EASUN RWB1-04 (pvPanelFlow card only) ────────────────────────────────
ISSUE_35_RESPONSE = {
    "code": 0,
    "data": {
        "deviceAttributeState": {"fields": {"bmsSOC": 80}},
        "pvPanelFlow": {
            "key": "generationPower",
            "localeTitle": "PV Panel",
            "value": {
                "key": "generationPower",
                "unit": "kW",
                "value": 0.356,
                "valueDisplay": "0.356",
                "nameDisplay": "PV Charging Power",
            },
        },
        "gridFlow": None,
    },
}

# ─── #9 Victor 19.2 / #24 Powmr MEGA-ECO (unit-tagged) ────────────────────────
ISSUE_9_VICTOR = {
    "pvInputPower": _tag(538, "W"),
    "pv2InputPower": _tag(2021, "W"),
    "generationPower": _tag(2.559, "kW"),
    "acOutputActivePower": _tag(0.091, "kW"),
    "batteryCapacity": _tag(56, "%"),
    "batteryVoltage": _tag(53.8, "V"),
}
ISSUE_24_MEGA_ECO = {
    "acOutputActivePower": _tag(2279, "W"),
    "pvInputPower": _tag(1.513, "kW"),
    "pv2InputPower": _tag(1.448, "kW"),
    "generationPower": _tag(2.961, "kW"),
    "GridPower": _tag(-414, "W"),
    "batteryCapacity": _tag(0, "%"),
}


@pytest.fixture
def api_factory():
    def _factory(history_fields, flow_response):
        api = SolarOfThingsAPI(iot_token="test-token")
        api._ensure_token_valid = lambda: None
        calls = {"energy_flow": 0}
        api._post = lambda path, payload, **kw: {
            "code": 0, "data": {"payload": {"fields": history_fields}},
        }

        def fake_get(path, params, **kw):
            calls["energy_flow"] += 1
            return flow_response

        api._get = fake_get
        return api, calls

    return _factory


def _flow(fields):
    return {"code": 0, "data": {"deviceAttributeState": {"fields": fields}}}


# ── #37 ───────────────────────────────────────────────────────────────────────
def test_37_srne_fields_map_with_confirmed_units() -> None:
    mapped = map_energy_flow_fields(ISSUE_37_FLOW)
    assert mapped["pvInputPower"] == pytest.approx(909.0)  # = portal 0.909 kW
    assert mapped["acOutputActivePower"] == 387.0
    assert mapped["gridPower"] == 0.0
    assert mapped["batterySOC"] == 86.0
    assert mapped["batteryVoltage"] == 53.0
    # Unsigned mains reading: feed-in is not derivable, so it stays unknown.
    assert "feedInPower" not in mapped


def test_37_partial_time_series_still_runs_the_fallback(api_factory) -> None:
    api, calls = api_factory(ISSUE_37_TIME_SERIES, _flow(ISSUE_37_FLOW))
    result = api.fetch_latest_data("dev-37")

    assert calls["energy_flow"] == 1
    assert result["pvInputPower"] == pytest.approx(909.0)
    assert result["acOutputActivePower"] == 387.0
    assert result["loadPower"] == 387.0          # was 0 W before the fix
    assert result["gridPower"] == 0.0            # was 42.4 W (battery, mislabeled)
    # Time-series readings it did have are kept, not replaced.
    assert result["batterySOC"] == 86.0
    assert result["batteryDischargeCurrent"] == 0.8


def test_partial_device_gets_no_warning_spam(api_factory, caplog) -> None:
    """A device with real data that lacks one key must not WARN every poll."""
    api, _ = api_factory(ISSUE_37_TIME_SERIES, _flow({"someUnknownKey": 1}))
    with caplog.at_level(logging.DEBUG):
        api.fetch_latest_data("dev-partial")
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_complete_time_series_makes_no_extra_call(api_factory) -> None:
    full = {k: [1.0] for k in missing_realtime_keys({})}
    api, calls = api_factory(full, _flow(ISSUE_37_FLOW))
    api.fetch_latest_data("dev-full")
    assert calls["energy_flow"] == 0


# ── #35 ───────────────────────────────────────────────────────────────────────
def test_35_pv_from_pv_panel_flow_card_replaces_a_null(api_factory) -> None:
    history = dict(ISSUE_37_TIME_SERIES, pvInputPower=[None])
    api, calls = api_factory(history, ISSUE_35_RESPONSE)
    result = api.fetch_latest_data("dev-35")

    assert calls["energy_flow"] == 1
    assert result["pvInputPower"] == pytest.approx(356.0)   # 0.356 kW


def test_flow_cards_never_override_flat_fields() -> None:
    api = SolarOfThingsAPI(iot_token="t")
    api._ensure_token_valid = lambda: None
    response = {
        "code": 0,
        "data": {
            "deviceAttributeState": {"fields": {"generationPower": _tag(1.0, "kW")}},
            "pvPanelFlow": {"key": "generationPower", "value": _tag(9.0, "kW")},
        },
    }
    api._get = lambda path, params, **kw: response
    assert api.fetch_energy_flow("d")["generationPower"]["value"] == 1.0


# ── #9 / #24 unit tags ────────────────────────────────────────────────────────
def test_9_victor_unit_tags() -> None:
    mapped = map_energy_flow_fields(ISSUE_9_VICTOR)
    assert mapped["pvInputPower"] == 2559.0      # 538 W + 2021 W = 2.559 kW
    assert mapped["acOutputActivePower"] == pytest.approx(91.0)   # 0.091 kW
    assert mapped["batterySOC"] == 56.0
    assert mapped["batteryVoltage"] == 53.8


def test_24_mega_eco_same_keys_opposite_units() -> None:
    mapped = map_energy_flow_fields(ISSUE_24_MEGA_ECO)
    assert mapped["pvInputPower"] == pytest.approx(2961.0)   # kW-tagged here
    assert mapped["acOutputActivePower"] == 2279.0           # W-tagged here
    assert mapped["feedInPower"] == 414.0                    # GridPower -414
    assert mapped["gridPower"] == 0.0


def test_untagged_ambiguous_keys_are_never_guessed() -> None:
    """scale=None rules: no unit tag → no value, never a 1000x guess."""
    assert map_energy_flow_fields(
        {"acOutputActivePower": 2279, "pvInputPower": 1.5, "generationPower": 2.4}
    ) == {}


def test_unit_tag_beats_the_table_scale() -> None:
    # load_power is kW per the table; a W tag on it must win.
    assert map_energy_flow_fields({"load_power": _tag(350, "W")})[
        "acOutputActivePower"
    ] == 350.0
