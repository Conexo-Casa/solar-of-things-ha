"""Charge-current / comeback-voltage dropdowns (#9, also requested in #52).

Allowed values and current values are trimmed from Xcpro1's Victor 19.2
settings capture on #9 (battery_setting group, enumValues):
  setMaxChargingCurrent              10..160 A step 10, current "60"
  setUtilityMaxChargingCurrent       2, 10..140 A,       current "2"
  comebackBatteryModeVolSBUPriority  "48.0".."58.0" V,   current "53.0"
  comebackUtilityModeVolSBUPriority  "42".."51" V,       current "51"
The write body shape follows the portal's own deviceRemoteWrite call:
{"id": <deviceId>, "key": ..., "value": ...}.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.solar_of_things.api import SolarOfThingsAPI
from custom_components.solar_of_things.const import CHARGE_CONTROL_SELECTS
from custom_components.solar_of_things.select import (
    SolarOfThingsChargeControlSelect,
    match_option,
    setting_entry,
)

# The portal-form shape from the #9 capture (configs block).
VICTOR_SETTINGS = {
    "ruleCode": "",
    "configs": {
        "chargerSourcePrioritySetting": "2",
        "setMaxChargingCurrent": "60",
        "setUtilityMaxChargingCurrent": "2",
        "comebackBatteryModeVolSBUPriority": "53.0",
        "comebackUtilityModeVolSBUPriority": "51",
        "outputSourcePrioritySetting": "2",
    },
}

# The flat shape the existing controls read.
FLAT_SETTINGS = {
    "setMaxChargingCurrent": {"key": "setMaxChargingCurrent", "value": "60"},
}


def test_allowed_values_match_the_victor_capture():
    assert CHARGE_CONTROL_SELECTS["setMaxChargingCurrent"][2] == tuple(
        str(a) for a in range(10, 170, 10)
    )
    assert CHARGE_CONTROL_SELECTS["setUtilityMaxChargingCurrent"][2][:3] == ("2", "10", "20")
    assert CHARGE_CONTROL_SELECTS["setUtilityMaxChargingCurrent"][2][-1] == "140"
    assert CHARGE_CONTROL_SELECTS["comebackBatteryModeVolSBUPriority"][2] == tuple(
        f"{v}.0" for v in range(48, 59)
    )
    assert CHARGE_CONTROL_SELECTS["comebackUtilityModeVolSBUPriority"][2] == tuple(
        str(v) for v in range(42, 52)
    )


@pytest.mark.parametrize("settings", [VICTOR_SETTINGS, FLAT_SETTINGS])
def test_setting_entry_reads_both_cache_shapes(settings):
    assert setting_entry(settings, "setMaxChargingCurrent") == "60"


@pytest.mark.parametrize("settings", [None, {}, [], {"configs": None}])
def test_setting_entry_missing_is_none(settings):
    assert setting_entry(settings, "setMaxChargingCurrent") is None


def test_match_option_numeric_and_out_of_range():
    volts = CHARGE_CONTROL_SELECTS["comebackBatteryModeVolSBUPriority"][2]
    assert match_option("53.0", volts) == "53.0"
    assert match_option(53, volts) == "53.0"
    assert match_option("47.5", volts) is None
    assert match_option(None, volts) is None


def _entity(key, settings):
    coordinator = MagicMock()
    coordinator.data = {"settings": settings}
    coordinator.last_update_success = True
    api = MagicMock()
    ent = SolarOfThingsChargeControlSelect(api, coordinator, "st", "dev1", "Victor", key)
    return ent, api


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("setMaxChargingCurrent", "60 A"),
        ("setUtilityMaxChargingCurrent", "2 A"),
        ("comebackBatteryModeVolSBUPriority", "53.0 V"),
        ("comebackUtilityModeVolSBUPriority", "51 V"),
    ],
)
def test_current_option_from_victor_capture(key, expected):
    ent, _ = _entity(key, VICTOR_SETTINGS)
    assert ent.available is True
    assert ent.current_option == expected
    assert expected in ent.options


def test_unavailable_when_device_lacks_the_key():
    ent, _ = _entity("setMaxChargingCurrent", {"configs": {"outputSourcePrioritySetting": "2"}})
    assert ent.available is False
    assert ent.current_option is None


async def test_select_sends_the_portal_value_string():
    ent, api = _entity("comebackBatteryModeVolSBUPriority", VICTOR_SETTINGS)
    ent.hass = MagicMock()

    async def run(fn, *args):
        return fn(*args)

    ent.hass.async_add_executor_job = run
    ent.coordinator.async_request_refresh = MagicMock(return_value=_done())
    await ent.async_select_option("54.0 V")
    api.set_setting_value.assert_called_once_with("dev1", "comebackBatteryModeVolSBUPriority", "54.0")


async def test_select_rejects_a_value_not_in_the_list():
    ent, api = _entity("setMaxChargingCurrent", VICTOR_SETTINGS)
    ent.hass = MagicMock()
    with pytest.raises(ValueError):
        await ent.async_select_option("65 A")
    api.set_setting_value.assert_not_called()


async def _noop():
    return None


def _done():
    return _noop()


def test_write_body_carries_id_like_the_portal():
    api = SolarOfThingsAPI(iot_token="t")
    api._ensure_token_valid = lambda: None
    sent = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"code": 0}

    def post(url, json=None, timeout=None):
        sent["url"], sent["json"] = url, json
        return Resp()

    api.session.post = post
    api.set_setting_value("dev1", "setMaxChargingCurrent", "60")
    assert sent["json"]["id"] == "dev1"
    assert sent["json"]["deviceId"] == "dev1"
    assert sent["json"]["key"] == "setMaxChargingCurrent"
    assert sent["json"]["value"] == "60"
    assert sent["url"].endswith("/apis/remote/device/config/write?deviceId=dev1")
