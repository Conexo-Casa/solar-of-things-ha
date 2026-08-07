#!/usr/bin/env python3
"""Dump the raw Solar of Things API payloads for one station.

Run this when an entity reads ``unknown``: it prints (and saves) every attribute
name your inverter actually publishes, so a measurement that the integration
looks for under the wrong name can be identified and mapped.

    pip install requests pycryptodome
    python3 tools/dump_solar_api.py --user-id YOURID --station-id 12345

The password is prompted for and never written to the dump.  Tokens are stripped
from the output, so the resulting JSON is safe to attach to a GitHub issue —
give it a skim first anyway, since it contains your device names and readings.
"""
from __future__ import annotations

import argparse
import getpass
import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT_DIR = REPO_ROOT / "custom_components" / "solar_of_things"


def _load_component_modules() -> tuple[Any, Any, Any]:
    """Import api/const/helpers without pulling in Home Assistant.

    ``custom_components/solar_of_things/__init__.py`` imports Home Assistant, so
    the package is registered under a private name with only its ``__path__``
    set.  The submodules then resolve their relative imports normally while the
    real package ``__init__`` is never executed.
    """
    if not COMPONENT_DIR.is_dir():
        sys.exit(f"Cannot find {COMPONENT_DIR} — run this from the repository.")

    package = types.ModuleType("_sot")
    package.__path__ = [str(COMPONENT_DIR)]
    sys.modules["_sot"] = package

    return (
        importlib.import_module("_sot.api"),
        importlib.import_module("_sot.const"),
        importlib.import_module("_sot.helpers"),
    )


def _summarise(label: str, payload: dict[str, Any]) -> None:
    keys = sorted(payload)
    print(f"    {label}: {len(keys)} keys")
    for key in keys:
        print(f"      • {key}")


def _lookup_report(helpers, const, fields: dict, settings: dict) -> None:
    """Print how the integration resolves the commonly-broken values."""
    print("\n  Resolution of the values that commonly read 'unknown':")

    for control, by_value, aliases in (
        ("outputSourcePriority", const.OUTPUT_PRIORITY_BY_VALUE, const.OUTPUT_PRIORITY_ALIASES),
        ("chargerSourcePriority", const.CHARGER_PRIORITY_BY_VALUE, const.CHARGER_PRIORITY_ALIASES),
    ):
        for source, haystack, candidates in (
            ("state", fields, const.STATE_KEY_CANDIDATES[control]),
            ("settings", settings, const.SETTING_KEY_CANDIDATES[control]),
        ):
            key, entry = helpers.find_entry(haystack, candidates)
            raw = helpers.entry_value(entry)
            display = helpers.entry_display(entry)
            option = helpers.resolve_option(raw, display, by_value, aliases) if key else None
            print(
                f"    {control} [{source}]: key={key!r} value={raw!r} "
                f"display={display!r} → {option!r}"
            )

    for key, (candidates, kind) in const.TELEMETRY_STATE_FALLBACKS.items():
        matched, _entry = helpers.find_entry(fields, candidates)
        value = helpers.state_number(fields, candidates, kind)
        print(f"    {key} [state]: key={matched!r} → {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="Siseli portal account / user-ID")
    parser.add_argument("--station-id", required=True, help="Station ID from the portal URL")
    parser.add_argument("--device-id", help="Limit the dump to a single device ID")
    parser.add_argument("--time-zone", default="Asia/Manila", help="IOT-Time-Zone header value")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("solar_of_things_dump.json"),
        help="Where to write the JSON dump (default: ./solar_of_things_dump.json)",
    )
    args = parser.parse_args()

    api_mod, const, helpers = _load_component_modules()

    password = getpass.getpass("Siseli password: ")

    client = api_mod.SolarOfThingsAPI(
        user_id=args.user_id,
        password=password,
        time_zone=args.time_zone,
    )
    print("Logging in …")
    client.login()
    print("  ok")

    devices = client.list_devices(args.station_id)
    if args.device_id:
        devices = [d for d in devices if str(d.get("id")) == args.device_id]
    print(f"Found {len(devices)} device(s)")

    dump: dict[str, Any] = {"station_id": args.station_id, "devices": []}

    for device in devices:
        device_id = str(device.get("id") or "")
        if not device_id:
            continue
        name = device.get("name") or device_id
        print(f"\n▸ {name} ({device_id})")

        time_series = client.fetch_latest_data(device_id)

        try:
            settings = client.get_device_settings(device_id)
        except Exception as err:  # noqa: BLE001 — a dump should survive any failure
            print(f"    settings fetch failed: {err}")
            settings = {}

        try:
            state = client.fetch_state(device_id)
        except Exception as err:  # noqa: BLE001
            print(f"    state fetch failed: {err}")
            state = {}

        fields = helpers.state_fields(state)

        _summarise("time-series", time_series)
        _summarise("settings cache", settings)
        _summarise("state snapshot", fields)
        _lookup_report(helpers, const, fields, settings)

        dump["devices"].append(
            {
                "device_id": device_id,
                "device_meta": device,
                "time_series": time_series,
                "settings": settings,
                "state_fields": fields,
                "firing_alarms": state.get("firingAlarms"),
            }
        )

    args.output.write_text(json.dumps(dump, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
