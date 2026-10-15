"""Monthly summary: unmatched keys must read unknown, not 0 (#14, #45, owner's
Sumry stations — all four Monthly sensors showed 0.0 on every station)."""
from __future__ import annotations

from datetime import datetime, timezone

from custom_components.solar_of_things.api import SolarOfThingsAPI


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


def test_unmatched_keys_are_unknown_not_zero() -> None:
    body = {"code": 0, "data": {"properties": [{"key": "somethingElse", "value": 5}]}}
    monthly = _api(body).fetch_monthly_summary("s")
    assert monthly == {
        "monthly_pv_generated": None,
        "monthly_grid_import": None,
        "monthly_total_consumption": None,
        "monthly_solar_percentage": None,
    }


def test_empty_response_is_unknown() -> None:
    monthly = _api({"code": 0, "data": None}).fetch_monthly_summary("s")
    assert all(v is None for v in monthly.values())


def test_matched_keys_still_reported() -> None:
    body = {"code": 0, "data": {"properties": [
        {"key": "2026-10", "value": 120.5},
        {"key": "load", "value": 241},
        {"key": "buy", "value": 0},
    ]}}
    monthly = _api(body).fetch_monthly_summary("s")
    assert monthly["monthly_pv_generated"] == 120.5
    assert monthly["monthly_total_consumption"] == 241.0
    assert monthly["monthly_grid_import"] == 0.0        # a real 0 stays 0
    assert monthly["monthly_solar_percentage"] == 50.0
