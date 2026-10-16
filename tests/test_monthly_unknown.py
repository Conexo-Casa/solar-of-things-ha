"""Monthly summary sensors (#14, #45, owner's Sumry stations).

Every Monthly sensor read 0.0 on every station checked: the parser looked for
flat {key, value} items, but the real response nests a per-month time series
under each property.  Payload trimmed from the owner's Sumry station
423564214316007425, captured live 2026-10-15.
"""
from __future__ import annotations

from datetime import datetime, timezone

from custom_components.solar_of_things.api import (
    SolarOfThingsAPI,
    parse_monthly_summary,
)


def _prop(key, points):
    return {
        "property": {"key": key, "unit": "kWh", "name": key},
        "timePoints": [
            {"time": t, "value": v, "isRealValue": real} for t, v, real in points
        ],
        "hasRealTimePoints": any(real for _, _, real in points),
    }


SUMRY_2026_10 = {
    "code": 0,
    "message": "Success",
    "data": {
        "category": {"key": "pvInverterElectricityQuantityClass"},
        "properties": [
            _prop("pvGeneratedEnergy", [("2026-09", 153.544, True),
                                        ("2026-10", 49.839, True),
                                        ("2026-11", 0, False)]),
            _prop("buyElectricityQuantity", [("2026-10", 0, False)]),
            _prop("sellElectricityQuantity", [("2026-10", 0, False)]),
            _prop("chargeElectricityQuantity", [("2026-10", 0, False)]),
            _prop("dischargeElectricityQuantity", [("2026-10", 0, False)]),
            _prop("consumeElectricityQuantity", [("2026-10", 0, False)]),
        ],
    },
}


class _Resp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _api(body):
    api = SolarOfThingsAPI(iot_token="t")
    api._ensure_token_valid = lambda: None
    api._now = lambda: datetime(2026, 10, 15, tzinfo=timezone.utc)
    api.session.post = lambda *a, **k: _Resp(body)
    return api


def test_parse_takes_this_month_and_skips_padding() -> None:
    assert parse_monthly_summary(SUMRY_2026_10, "2026-10") == {
        "pvGeneratedEnergy": 49.839,
    }
    assert parse_monthly_summary(SUMRY_2026_10, "2026-11") == {}


def test_sumry_station_reports_pv_and_unknown_for_padded() -> None:
    monthly = _api(SUMRY_2026_10).fetch_monthly_summary("423564214316007425")
    assert monthly["monthly_pv_generated"] == 49.839       # was 0.0
    assert monthly["monthly_grid_import"] is None          # padded, not 0
    assert monthly["monthly_total_consumption"] is None
    assert monthly["monthly_solar_percentage"] is None


def test_real_values_on_other_metrics_are_published() -> None:
    body = {"code": 0, "data": {"properties": [
        _prop("pvGeneratedEnergy", [("2026-10", 120.0, True)]),
        _prop("buyElectricityQuantity", [("2026-10", 0, True)]),
        _prop("consumeElectricityQuantity", [("2026-10", 240.0, True)]),
    ]}}
    monthly = _api(body).fetch_monthly_summary("s")
    assert monthly["monthly_grid_import"] == 0.0           # a real 0 stays 0
    assert monthly["monthly_total_consumption"] == 240.0
    assert monthly["monthly_solar_percentage"] == 50.0


def test_empty_or_odd_response_is_unknown() -> None:
    for body in ({"code": 0, "data": None},
                 {"code": 0, "data": {"properties": [{"key": "x", "value": 5}]}}):
        assert all(v is None for v in _api(body).fetch_monthly_summary("s").values())
