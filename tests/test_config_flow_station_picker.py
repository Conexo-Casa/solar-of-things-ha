"""#14: password flow with optional Station ID + station picker, run against
real Home Assistant (pytest-homeassistant-custom-component)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.solar_of_things.const import DOMAIN

API = "custom_components.solar_of_things.api.SolarOfThingsAPI"
LOGIN = {"user_id": "bob", "password": "pw", "time_zone": "Europe/Budapest"}
TWO = [{"id": "111", "name": "House"}, {"id": "222", "name": "Barn"}]


@pytest.fixture(autouse=True)
def _custom(enable_custom_integrations):
    yield


async def _to_password(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"auth_mode": "password"}
    )


async def test_blank_station_single_station_autoselects(hass: HomeAssistant) -> None:
    with patch(f"{API}.login"), patch(
        f"{API}.list_stations", return_value=[TWO[0]]
    ), patch(f"{API}.test_connection", return_value=True):
        form = await _to_password(hass)
        result = await hass.config_entries.flow.async_configure(form["flow_id"], LOGIN)
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"]["station_id"] == "111"
    assert result["title"] == "House"


async def test_blank_station_many_shows_picker(hass: HomeAssistant) -> None:
    with patch(f"{API}.login"), patch(f"{API}.list_stations", return_value=TWO):
        form = await _to_password(hass)
        picker = await hass.config_entries.flow.async_configure(form["flow_id"], LOGIN)
        assert picker["type"] == data_entry_flow.FlowResultType.FORM
        assert picker["step_id"] == "station"
        assert picker["errors"] == {}
        result = await hass.config_entries.flow.async_configure(
            picker["flow_id"], {"station_id": "222"}
        )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"]["station_id"] == "222"
    assert result["data"]["user_id"] == "bob"


async def test_wrong_typed_id_falls_through_to_picker(hass: HomeAssistant) -> None:
    """The #14 / #42 case: a DTU-ID typed as Station ID."""
    with patch(f"{API}.login"), patch(
        f"{API}.test_connection", return_value=False
    ), patch(f"{API}.list_stations", return_value=TWO):
        form = await _to_password(hass)
        picker = await hass.config_entries.flow.async_configure(
            form["flow_id"], {**LOGIN, "station_id": "E50000123456"}
        )
    assert picker["step_id"] == "station"
    assert picker["errors"] == {"base": "station_not_found"}


async def test_valid_typed_id_still_works(hass: HomeAssistant) -> None:
    with patch(f"{API}.login"), patch(
        f"{API}.test_connection", return_value=True
    ), patch(f"{API}.list_stations") as ls:
        form = await _to_password(hass)
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], {**LOGIN, "station_id": "333"}
        )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"]["station_id"] == "333"
    assert result["title"] == "Solar Station 333"
    ls.assert_not_called()


async def test_no_stations_and_blank_id_asks_for_manual(hass: HomeAssistant) -> None:
    with patch(f"{API}.login"), patch(f"{API}.list_stations", side_effect=RuntimeError("x")):
        form = await _to_password(hass)
        result = await hass.config_entries.flow.async_configure(form["flow_id"], LOGIN)
    assert result["step_id"] == "password"
    assert result["errors"] == {"base": "no_stations"}


async def test_bad_time_zone_rejected(hass: HomeAssistant) -> None:
    form = await _to_password(hass)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {**LOGIN, "time_zone": "Europe"}
    )
    assert result["errors"] == {"base": "invalid_time_zone"}
