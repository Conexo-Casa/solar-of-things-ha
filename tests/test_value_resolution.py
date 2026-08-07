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
        # Straight from a live PI30/VMIII snapshot: code 3 with this label.
        ("3", "Only Solar Permitted", "Solar Only"),
        ("1", "for solar first", "Solar First"),
        (0, None, "Utility First"),
        (2, None, "Solar + Utility"),
        (None, "Solar only", "Solar Only"),
        (7, None, None),
    ],
)
def test_resolve_charger_priority(raw, display, expected):
    assert helpers.resolve_option(
        raw, display, const.CHARGER_PRIORITY_BY_VALUE, const.CHARGER_PRIORITY_ALIASES
    ) == expected


def test_charger_priority_covers_all_four_pi30_codes():
    """PCP is 0-3; treating it as 0-2 is what broke read-back before 2.6.0."""
    assert sorted(const.CHARGER_PRIORITY_BY_VALUE) == [0, 1, 2, 3]


@pytest.mark.parametrize(
    ("raw", "display", "expected"),
    [
        ("1", "Photovoltaic ->mains power ->battery", "Solar First (SUB)"),
        (None, "SolarUtilityBat", "Solar First (SUB)"),
        (None, "SolarBatUtility", "Solar+Battery First (SBU)"),
        (None, "UtilitySolarBat", "Utility First (USO)"),
    ],
)
def test_resolve_output_priority_from_live_labels(raw, display, expected):
    assert helpers.resolve_option(
        raw, display, const.OUTPUT_PRIORITY_BY_VALUE, const.OUTPUT_PRIORITY_ALIASES
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

# Trimmed from a live PI30 / VMIII snapshot (state/latest, dataSource=1).
LIVE_STATE = {
    "fields": {
        "generationPower": {"unit": "kW", "value": 1.162, "valueDisplay": "1.162"},
        "acOutputActivePower": {"unit": "kW", "value": 1.354, "valueDisplay": "1.354"},
        "PV1ChargingPower": {"unit": "W", "value": 1162, "valueDisplay": "1162"},
        "PV2ChargingPower": {"unit": "W", "value": 0, "valueDisplay": "0"},
        "batteryVoltage": {"unit": "V", "value": 28.2, "valueDisplay": "28.2"},
        "batteryCapacity": {"unit": "%", "value": 100, "valueDisplay": "100"},
        "batteryChargingCurrent": {"unit": "A", "value": 0, "valueDisplay": "0"},
        "batteryDischargeCurrent": {"unit": "A", "value": 0, "valueDisplay": "0"},
        "chargerSourcePriority": {"unit": "A", "value": "3", "valueDisplay": "Only Solar Permitted"},
        "outputSourcePriority": {"unit": "", "value": "1", "valueDisplay": "Photovoltaic ->mains power ->battery"},
        "solarFeedToGrid": {"unit": "", "value": "0", "valueDisplay": "disable"},
        "inputVoltageRange": {"unit": "", "value": "0", "valueDisplay": "Appliance"},
    },
    "firingAlarms": [{"key": "lineFail", "name": "Line Fail"}],
}


def test_live_snapshot_populates_every_core_measurement():
    """The device publishes none of these under the names the history API uses."""
    merged = api.merge_state_fallbacks({}, LIVE_STATE)

    assert merged["pvInputPower"] == 1162.0        # generationPower, kW → W
    assert merged["acOutputActivePower"] == 1354.0
    assert merged["batterySOC"] == 100.0           # batteryCapacity
    assert merged["batteryVoltage"] == 28.2


def test_feed_in_is_zero_when_the_device_cannot_feed_the_grid():
    """PI30 has no feed-in measurement, only a permit flag; disabled means 0."""
    merged = api.merge_state_fallbacks({}, LIVE_STATE)

    assert merged["feedInPower"] == 0.0
    # ac_output - pv + battery + feed_in = 1354 - 1162 + 0 + 0
    assert merged["gridPower"] == 192.0


def test_feed_in_stays_unknown_when_the_flag_says_enabled():
    state = {"fields": {"solarFeedToGrid": {"value": "1", "valueDisplay": "enable"}}}
    assert api.merge_state_fallbacks({}, state).get("feedInPower") is None


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

def test_every_writable_control_can_be_read_back():
    """Anything we can write must have a state field to read it back from."""
    assert set(const.SETTING_KEY_CANDIDATES) <= set(const.STATE_KEY_CANDIDATES)


def test_boolean_and_number_controls_have_write_keys():
    for control in (*const.BOOLEAN_CONTROLS, *const.NUMBER_CONTROLS):
        assert control in const.SETTING_KEY_CANDIDATES, control


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"code": 0, "message": "Success"}


class _RecordingSession:
    """Captures what the client would POST, without touching the network."""

    def __init__(self):
        self.headers = {}
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return _FakeResponse()


def _client_with_recording_session():
    client = api.SolarOfThingsAPI.__new__(api.SolarOfThingsAPI)
    client.session = _RecordingSession()
    client._ensure_token_valid = lambda: None
    return client


def test_write_payload_uses_id_not_device_id():
    """The endpoint reports success for a deviceId body but changes nothing."""
    client = _client_with_recording_session()

    client.set_operating_mode("dev-1", const.OUTPUT_PRIORITY_BY_VALUE[2])

    url, body = client.session.calls[0]
    assert "deviceId=dev-1" in url
    assert body == {
        "id": "dev-1",
        "key": "settingDeviceOutputSourcePriority",
        "value": "2",
    }


def test_charger_priority_write_sends_the_pcp_code_as_a_string():
    client = _client_with_recording_session()

    client.set_battery_priority("dev-1", const.CHARGER_PRIORITY_BY_VALUE[3])

    assert client.session.calls[0][1] == {
        "id": "dev-1",
        "key": "settingDeviceChargerPriority",
        "value": "3",
    }


def test_number_control_writes_a_bare_number():
    client = _client_with_recording_session()

    client.set_number_control("dev-1", "equalizationVoltage", 29.2)
    client.set_number_control("dev-1", "equalizationPeriod", 30.0)

    assert client.session.calls[0][1]["value"] == 29.2
    assert client.session.calls[1][1]["value"] == 30


def test_boolean_control_writes_quoted_flags():
    client = _client_with_recording_session()

    client.set_grid_feed_in("dev-1", True)

    assert client.session.calls[0][1] == {
        "id": "dev-1",
        "key": "setGridConnectionStatus",
        "value": "1",
    }


def test_priority_write_keys_are_the_setting_names():
    """Writes use settingDevice… keys, not the state-snapshot names."""
    assert const.SETTING_KEY_CANDIDATES["outputSourcePriority"][0] == "settingDeviceOutputSourcePriority"
    assert const.SETTING_KEY_CANDIDATES["chargerSourcePriority"][0] == "settingDeviceChargerPriority"


def test_api_write_maps_match_the_select_options():
    """The labels the selects offer must be exactly the ones the API can write."""
    assert set(api.SolarOfThingsAPI._OUTPUT_MODE_MAP) == set(const.OUTPUT_PRIORITY_OPTIONS)
    assert set(api.SolarOfThingsAPI._CHARGER_PRIORITY_MAP) == set(const.CHARGER_PRIORITY_OPTIONS)
