"""Tests for the payload-shape handling that drives the entity read-back.

These cover the failure modes reported against 2.4.x: priority selects stuck on
``unknown`` because the settings cache was empty, and Grid Feed-in Power stuck
on ``unknown`` because the model publishes it under another name.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _component import load  # noqa: E402  — needs the path insertion above

api = load("api")
const = load("const")
helpers = load("helpers")


# ── state_fields ──────────────────────────────────────────────────────────────

def test_state_fields_accepts_unwrapped_payload():
    assert helpers.state_fields({"fields": {"a": {"value": 1}}}) == {"a": {"value": 1}}


def test_state_fields_accepts_data_wrapped_payload():
    payload = {"data": {"fields": {"a": {"value": 1}}}}
    assert helpers.state_fields(payload) == {"a": {"value": 1}}


def test_state_fields_of_empty_payload_is_empty():
    assert helpers.state_fields(None) == {}
    assert helpers.state_fields({}) == {}


# ── find_entry ────────────────────────────────────────────────────────────────

def test_find_entry_is_case_insensitive():
    fields = {"PV1InputVoltage": {"value": 230}}
    key, entry = helpers.find_entry(fields, ["pv1inputvoltage"])
    assert key == "PV1InputVoltage"
    assert entry == {"value": 230}


def test_find_entry_returns_first_matching_candidate():
    fields = {"gridFeedInPower": {"value": 5}, "feedbackPower": {"value": 9}}
    key, _entry = helpers.find_entry(fields, ["feedInPower", "gridFeedInPower", "feedbackPower"])
    assert key == "gridFeedInPower"


def test_find_entry_without_match():
    assert helpers.find_entry({"a": {}}, ["b", "c"]) == (None, None)


# ── numbers and units ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("raw", "expected"),
    [(1, 1.0), ("2.5", 2.5), ("1234.5 W", 1234.5), ("", None), (None, None), ("abc", None), (True, None)],
)
def test_to_float(raw, expected):
    assert helpers.to_float(raw) == expected


def test_state_number_scales_kilowatts_to_watts():
    fields = {"feedInPower": {"value": 1.5, "unit": "kW"}}
    assert helpers.state_number(fields, ["feedInPower"], "power") == 1500.0


def test_state_number_leaves_watts_alone():
    fields = {"feedInPower": {"value": 1500, "unit": "W"}}
    assert helpers.state_number(fields, ["feedInPower"], "power") == 1500.0


def test_state_number_passes_through_unknown_unit():
    fields = {"feedInPower": {"value": 1500, "unit": "??"}}
    assert helpers.state_number(fields, ["feedInPower"], "power") == 1500.0


# ── option resolution ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("raw", "display", "expected"),
    [
        (2, None, "Solar+Battery First (SBU)"),
        ("2", None, "Solar+Battery First (SBU)"),
        (None, "SBU", "Solar+Battery First (SBU)"),
        (None, "Solar+Battery first (SBU)", "Solar+Battery First (SBU)"),
        (None, "Utility first", "Utility First (USO)"),
        (0, "Utility First (USO)", "Utility First (USO)"),
        (None, "something else entirely", None),
        (None, None, None),
    ],
)
def test_resolve_output_priority(raw, display, expected):
    assert helpers.resolve_option(
        raw, display, const.OUTPUT_PRIORITY_BY_VALUE, const.OUTPUT_PRIORITY_ALIASES
    ) == expected


@pytest.mark.parametrize(
    ("raw", "display", "expected"),
    [
        (0, None, "Solar + Utility (CSO)"),
        (None, "SNU", "Solar First (SNU)"),
        (None, "Solar only", "Solar Only (OSO)"),
        (7, None, None),
    ],
)
def test_resolve_charger_priority(raw, display, expected):
    assert helpers.resolve_option(
        raw, display, const.CHARGER_PRIORITY_BY_VALUE, const.CHARGER_PRIORITY_ALIASES
    ) == expected


def test_every_option_label_resolves_to_itself():
    """The labels we send back to the API must survive a round trip."""
    for by_value, aliases in (
        (const.OUTPUT_PRIORITY_BY_VALUE, const.OUTPUT_PRIORITY_ALIASES),
        (const.CHARGER_PRIORITY_BY_VALUE, const.CHARGER_PRIORITY_ALIASES),
    ):
        for label in by_value.values():
            assert helpers.resolve_option(None, label, by_value, aliases) == label


# ── telemetry fallbacks ───────────────────────────────────────────────────────

def test_merge_state_fallbacks_fills_feed_in_power_from_alias():
    latest = {"acOutputActivePower": 2000.0, "pvInputPower": 1000.0}
    state = {"fields": {"gridFeedInPower": {"value": 0.4, "unit": "kW"}}}

    merged = api.merge_state_fallbacks(latest, state)

    assert merged["feedInPower"] == 400.0


def test_merge_state_fallbacks_does_not_override_existing_values():
    latest = {"feedInPower": 123.0}
    state = {"fields": {"feedInPower": {"value": 999}}}

    assert api.merge_state_fallbacks(latest, state)["feedInPower"] == 123.0


def test_merge_state_fallbacks_recomputes_derived_values():
    latest = {"acOutputActivePower": 2000.0, "pvInputPower": 500.0}
    state = {
        "fields": {
            "batteryVoltage": {"value": 48},
            "batteryDischargeCurrent": {"value": 10},
            "batteryChargingCurrent": {"value": 0},
            "feedInPower": {"value": 0},
        }
    }

    merged = api.merge_state_fallbacks(latest, state)

    assert merged["batteryPower"] == 480.0
    assert merged["loadPower"] == 2000.0
    # ac_output - pv + battery + feed_in = 2000 - 500 + 480 + 0
    assert merged["gridPower"] == 1980.0


def test_merge_state_fallbacks_without_state_is_a_noop():
    latest = {"acOutputActivePower": 100.0}
    assert api.merge_state_fallbacks(dict(latest), {}) == latest


def test_grid_power_never_goes_negative():
    values = api.compute_derived_values({"acOutputActivePower": 100.0, "pvInputPower": 5000.0})
    assert values["gridPower"] == 0.0


# ── key tables ────────────────────────────────────────────────────────────────

def test_state_and_setting_candidate_tables_cover_the_same_controls():
    assert set(const.STATE_KEY_CANDIDATES) == set(const.SETTING_KEY_CANDIDATES)


def test_api_write_maps_match_the_select_options():
    """The labels the selects offer must be exactly the ones the API can write."""
    assert set(api.SolarOfThingsAPI._OUTPUT_MODE_MAP) == set(const.OUTPUT_PRIORITY_OPTIONS)
    assert set(api.SolarOfThingsAPI._CHARGER_PRIORITY_MAP) == set(const.CHARGER_PRIORITY_OPTIONS)
