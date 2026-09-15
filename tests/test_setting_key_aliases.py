"""Tests for the write-path device-setting key aliases (issue #18 / #20).

Several inverter firmwares expose the same logical control under a different
writable-config key name than the one this integration was written against —
the same class of bug #13 fixed for sensor reads, here for control writes.
Confirmed by lukaszkwapien's full writable-config dump for a FCHAO inverter
(#18): Output Source Priority is `setOutputSourcePriority` on that firmware,
not the documented `outputSourcePrioritySetting`, and several other controls
(battery charge/discharge limit, grid charge limit) aren't exposed under any
key name at all on that device.
"""
from __future__ import annotations

import pytest

from custom_components.solar_of_things.api import (
    SolarOfThingsAPI,
    resolve_setting_key,
)
from custom_components.solar_of_things.const import SETTING_KEY_ALIASES

# Trimmed from lukaszkwapien's writable-config dump for a FCHAO inverter
# (#18) — a real device that exposes Output Source Priority under the
# alternate key and does not expose the three limit settings at all.
FCHAO_SETTINGS = {
    "setOutputSourcePriority": {"key": "setOutputSourcePriority", "value": 0, "valueDisplay": "Utilty"},
    "chargeSourcePrioirty": {"key": "chargeSourcePrioirty", "value": 0, "valueDisplay": "Solar And Utility"},
    "flotingChargingVoltageSetting": {"value": 54.0},
}

# A device that uses every documented key name as-is.
DOCUMENTED_SETTINGS = {
    "outputSourcePrioritySetting": {"key": "outputSourcePrioritySetting", "value": 1},
    "chargerSourcePrioritySetting": {"key": "chargerSourcePrioritySetting", "value": 0},
    "acInputRangeSetting": {"key": "acInputRangeSetting", "value": 0},
    "batteryPowerLimitingSetting": {"key": "batteryPowerLimitingSetting", "value": 1},
    "batteryChargeLimit": {"key": "batteryChargeLimit", "value": 80},
    "batteryDischargeLimit": {"key": "batteryDischargeLimit", "value": 20},
    "gridChargeLimit": {"key": "gridChargeLimit", "value": 3000},
}


# ─── resolve_setting_key ────────────────────────────────────────────────────

def test_resolves_the_documented_key_when_present():
    assert resolve_setting_key(DOCUMENTED_SETTINGS, "outputSourcePrioritySetting") == "outputSourcePrioritySetting"


def test_resolves_the_fchao_alternate_key_for_output_source_priority():
    assert resolve_setting_key(FCHAO_SETTINGS, "outputSourcePrioritySetting") == "setOutputSourcePriority"


def test_documented_key_wins_when_a_device_has_both():
    """The canonical name is tried first in SETTING_KEY_ALIASES — if a device
    somehow exposed both, prefer the documented one rather than the alias."""
    both = {**DOCUMENTED_SETTINGS, "setOutputSourcePriority": {"value": 9}}
    assert resolve_setting_key(both, "outputSourcePrioritySetting") == "outputSourcePrioritySetting"


@pytest.mark.parametrize(
    "canonical",
    ["batteryChargeLimit", "batteryDischargeLimit", "gridChargeLimit"],
)
def test_returns_none_when_a_device_exposes_neither_name(canonical):
    """FCHAO's dump does not contain these keys under any known spelling —
    must resolve to None so the entity can report unavailable, rather than
    fall back to a guess that would send a write guaranteed to fail with
    code=70134 "Config attribute not exists"."""
    assert resolve_setting_key(FCHAO_SETTINGS, canonical) is None


@pytest.mark.parametrize("settings", [None, {}, [], "text", 0])
def test_hostile_input_resolves_to_none(settings):
    assert resolve_setting_key(settings, "outputSourcePrioritySetting") is None


def test_every_alias_group_lists_the_canonical_name_first():
    """SETTING_KEY_ALIASES documents preference order; the canonical
    (documented) key must always be tried before any alternate."""
    for canonical, aliases in SETTING_KEY_ALIASES.items():
        assert aliases[0] == canonical, canonical


# ─── API write methods pick up the resolved key ────────────────────────────

@pytest.fixture
def api_stub():
    """An API instance with _write_setting stubbed to record what it was
    called with, instead of making a network request."""
    api = SolarOfThingsAPI(iot_token="test-token")
    calls = []
    api._write_setting = lambda device_id, key, value: calls.append((device_id, key, value))
    return api, calls


def test_set_operating_mode_uses_the_fchao_alternate_key(api_stub):
    api, calls = api_stub
    api.set_operating_mode("device-1", "Utility First (USO)", settings=FCHAO_SETTINGS)
    assert calls == [("device-1", "setOutputSourcePriority", 0)]


def test_set_operating_mode_uses_the_documented_key_by_default(api_stub):
    api, calls = api_stub
    api.set_operating_mode("device-2", "Utility First (USO)", settings=DOCUMENTED_SETTINGS)
    assert calls == [("device-2", "outputSourcePrioritySetting", 0)]


def test_set_operating_mode_falls_back_to_the_documented_key_when_settings_is_none(api_stub):
    """No settings passed (e.g. an older caller) -> unchanged pre-#18 behavior."""
    api, calls = api_stub
    api.set_operating_mode("device-3", "Solar First (SUB)", settings=None)
    assert calls == [("device-3", "outputSourcePrioritySetting", 1)]


def test_set_backup_mode_uses_the_fchao_alternate_key_too(api_stub):
    """set_backup_mode controls the same underlying setting as
    set_operating_mode and must resolve through the same alias."""
    api, calls = api_stub
    api.set_backup_mode("device-4", True, settings=FCHAO_SETTINGS)
    assert calls == [("device-4", "setOutputSourcePriority", 2)]


def test_set_battery_charge_limit_falls_back_when_key_is_confirmed_absent(api_stub):
    """No known alternate exists for this key on FCHAO — _resolve_write_key
    falls back to the documented name rather than raising, since preventing
    the doomed call is the entity's `available=False` job, not this one's."""
    api, calls = api_stub
    api.set_battery_charge_limit("device-5", 80, settings=FCHAO_SETTINGS)
    assert calls == [("device-5", "batteryChargeLimit", 80)]
