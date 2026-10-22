"""v2.9.0: energy-flow extra sensors (#41) and station daily/yearly/lifetime PV (#45).

Payloads are trimmed from real captures:
- #41 (Gospower via RWB1, 2026-10-13): energy-flow fields with unit tags,
  including the mixed-case "kWH" on loadConsumedEnergyOfDay/Month.
- #45 / owner's Sumry stations (live, 2026-10-22): the station summary
  family — category/monthly (one point per day) and category/total (one
  point per year) — same shape as the yearly summary the monthly sensors read.
"""
from __future__ import annotations

from datetime import datetime, timezone

from custom_components.solar_of_things.api import (
    SolarOfThingsAPI,
    map_energy_flow_extras,
    sum_real_points,
)


def _tag(value, unit):
    return {"unit": unit, "value": value}


GOSPOWER_41 = {
    "generationPower": _tag(1.114, "kW"),
    "loadPercentage": _tag(13, "%"),
    "pvVoltage": _tag(235.2, "V"),
    "pvGeneratedEnergyOfDay": _tag(1.846, "kWh"),
    "loadConsumedEnergyOfDay": _tag(1.52, "kWH"),
    "loadConsumedEnergyOfMonth": _tag(52.919, "kWH"),
    "loadConsumedEnergyOfYear": _tag(1259.317, "kWh"),
    "totalLoadConsumedEnergy": _tag(3073.992, "kWh"),
    "batteryChargingOfThisDay": _tag(0, "kWh"),
    "acOutputActivePower": _tag(0.715, "kW"),
}


def test_41_gospower_extras_use_unit_tags() -> None:
    extras = map_energy_flow_extras(GOSPOWER_41)
    assert extras["generationPower"] == 1114.0          # kW -> W
    assert extras["loadPercentage"] == 13
    assert extras["pvVoltage"] == 235.2
    assert extras["pvGeneratedEnergyOfDay"] == 1.846
    assert extras["loadConsumedEnergyOfDay"] == 1.52    # "kWH" accepted
    assert extras["loadConsumedEnergyOfMonth"] == 52.919
    assert extras["batteryChargingOfThisDay"] == 0      # a real 0 stays 0
    assert "acOutputActivePower" not in extras          # not an extra


def test_untagged_or_wrong_unit_is_skipped() -> None:
    extras = map_energy_flow_extras({
        "generationPower": 1.1,                         # bare, no tag
        "pvVoltage": _tag(235, "kV"),                   # unexpected unit
        "loadPercentage": {"value": 13},                # no unit key
        "pvGeneratedEnergyOfDay": _tag(5, "Wh"),        # not kWh
    })
    assert extras == {}


def _api(history, flow_fields):
    api = SolarOfThingsAPI(iot_token="t")
    api._ensure_token_valid = lambda: None
    calls = {"flow": 0}
    api._post = lambda *a, **k: {"code": 0, "data": {"payload": {"fields": history}}}

    def _get(*a, **k):
        calls["flow"] += 1
        return {"code": 0, "data": {"deviceAttributeState": {"fields": flow_fields}}}

    api._get = _get
    return api, calls


COMPLETE_HISTORY = {
    "pvInputPower": [100], "acOutputActivePower": [1.2], "batteryVoltage": [52.0],
    "batteryDischargeCurrent": [2.0], "batteryChargingCurrent": [0.0],
    "feedInPower": [0], "batterySOC": [90],
}


def test_extras_share_one_energy_flow_call_per_poll() -> None:
    api, calls = _api(COMPLETE_HISTORY, GOSPOWER_41)
    result = api.fetch_latest_data("gos")
    assert result["extras"]["generationPower"] == 1114.0
    assert calls["flow"] == 1        # unit lookup + extras reuse one fetch
    api.fetch_latest_data("gos")
    assert calls["flow"] == 2        # one per poll afterwards


def test_device_without_extras_stops_fetching_them() -> None:
    api, calls = _api(COMPLETE_HISTORY, {"acOutputActivePower": _tag(1.2, "kW")})
    assert api.fetch_latest_data("plain")["extras"] == {}
    first = calls["flow"]
    api.fetch_latest_data("plain")
    api.fetch_latest_data("plain")
    assert calls["flow"] == first    # no extra call on later polls


# ── #45: station daily / yearly / lifetime PV ────────────────────────────────
def _prop(key, points):
    return {
        "property": {"key": key, "unit": "kWh"},
        "timePoints": [{"time": t, "value": v, "isRealValue": r} for t, v, r in points],
    }


YEARLY = {"code": 0, "data": {"properties": [
    _prop("pvGeneratedEnergy", [("2026-09", 300.0, True), ("2026-10", 107.819, True),
                                ("2026-11", 0, False)]),
    _prop("buyElectricityQuantity", [("2026-10", 0, False)]),
]}}
MONTH = {"code": 0, "data": {"properties": [
    _prop("pvGeneratedEnergy", [("2026-10-21", 3.1, True), ("2026-10-22", 2.646, True),
                                ("2026-10-23", 0, False)]),
]}}
TOTAL = {"code": 0, "data": {"properties": [
    _prop("pvGeneratedEnergy", [("2025", 14.8, True), ("2026", 2808.009, True)]),
    _prop("buyElectricityQuantity", [("2026", None, True)]),
]}}


class _Resp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _station_api(total=TOTAL, month=MONTH):
    api = SolarOfThingsAPI(iot_token="t")
    api._ensure_token_valid = lambda: None
    api._now = lambda: datetime(2026, 10, 22, 16, tzinfo=timezone.utc)

    def _post(url, **k):
        if "category/yearly" in url:
            return _Resp(YEARLY)
        if "category/monthly" in url:
            assert k["json"] == {"time": "2026-10"}
            return _Resp(month)
        if "category/total" in url:
            return _Resp(total)
        raise AssertionError(url)

    api.session.post = _post
    return api


def test_45_station_periods_from_summaries() -> None:
    data = _station_api().fetch_monthly_summary("423564924235513857")
    assert data["monthly_pv_generated"] == 107.819          # unchanged
    assert data["daily_pv_generated"] == 2.646
    assert data["yearly_pv_generated"] == 407.819            # real months only
    assert round(data["lifetime_pv_generated"], 3) == 2822.809


def test_period_failure_leaves_only_that_sensor_unknown() -> None:
    def boom(*a, **k):
        raise RuntimeError("portal down")

    api = _station_api()
    real = api.session.post
    api.session.post = lambda url, **k: boom() if "category/total" in url else real(url, **k)
    data = api.fetch_monthly_summary("s")
    assert data["lifetime_pv_generated"] is None
    assert data["daily_pv_generated"] == 2.646
    assert data["monthly_pv_generated"] == 107.819


def test_padded_or_missing_points_read_unknown() -> None:
    assert sum_real_points(YEARLY, "buyElectricityQuantity") is None
    assert sum_real_points(TOTAL, "buyElectricityQuantity") is None   # value None
    assert sum_real_points({"code": 0, "data": None}, "pvGeneratedEnergy") is None
