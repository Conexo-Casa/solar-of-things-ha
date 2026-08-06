"""Diagnostics support for Solar of Things.

Settings → Devices & Services → Solar of Things → ⋮ → *Download diagnostics*
produces a JSON file containing the raw payloads the integration received from
the portal, with credentials and tokens removed.

That file is the fastest way to work out why an entity reads ``unknown``: it
lists every attribute name the device actually publishes, alongside the names
the integration looked for.  Attach it to a GitHub issue and the missing name
can be added to the candidate lists in ``const.py``.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CHARGER_PRIORITY_ALIASES,
    CHARGER_PRIORITY_BY_VALUE,
    DOMAIN,
    OUTPUT_PRIORITY_ALIASES,
    OUTPUT_PRIORITY_BY_VALUE,
    SETTING_KEY_CANDIDATES,
    STATE_KEY_CANDIDATES,
    TELEMETRY_STATE_FALLBACKS,
)
from .helpers import (
    entry_display,
    entry_value,
    find_entry,
    resolve_option,
    state_fields,
)

TO_REDACT = {
    "password",
    "iot_token",
    "refresh_token",
    "user_id",
    "account",
    "access_token",
    "accessToken",
    "refreshToken",
}


def _priority_report(
    settings: dict[str, Any],
    fields: dict[str, Any],
    control: str,
    by_value: dict[int, str],
    aliases: dict[str, str],
) -> dict[str, Any]:
    """Show what each source returned for a priority control and how it resolved."""
    report: dict[str, Any] = {
        "searched_state_keys": STATE_KEY_CANDIDATES[control],
        "searched_setting_keys": SETTING_KEY_CANDIDATES[control],
    }

    for source, haystack, candidates in (
        ("state", fields, STATE_KEY_CANDIDATES[control]),
        ("settings", settings, SETTING_KEY_CANDIDATES[control]),
    ):
        key, entry = find_entry(haystack, candidates)
        raw, display = entry_value(entry), entry_display(entry)
        report[source] = {
            "matched_key": key,
            "raw_value": raw,
            "raw_display": display,
            "resolved_option": (
                resolve_option(raw, display, by_value, aliases) if key else None
            ),
        }

    return report


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    stored = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    station_coordinator = stored.get("station_coordinator")
    device_coordinators: dict[str, Any] = stored.get("device_coordinators", {})

    devices: list[dict[str, Any]] = []
    for device_id, coordinator in device_coordinators.items():
        data = coordinator.data or {}
        settings = data.get("settings") or {}
        state = data.get("state") or {}
        fields = state_fields(state)
        time_series = data.get("time_series") or {}

        devices.append(
            {
                "device_id": device_id,
                "device_meta": data.get("device_meta"),
                # Key lists first: this is usually all that is needed to spot a
                # measurement published under an unexpected name.
                "time_series_keys": sorted(time_series),
                "settings_keys": sorted(settings),
                "state_field_keys": sorted(fields),
                "time_series_values": time_series,
                "settings": settings,
                "state_fields": fields,
                "firing_alarms": state.get("firingAlarms"),
                "resolution": {
                    "output_source_priority": _priority_report(
                        settings, fields, "outputSourcePriority",
                        OUTPUT_PRIORITY_BY_VALUE, OUTPUT_PRIORITY_ALIASES,
                    ),
                    "charger_source_priority": _priority_report(
                        settings, fields, "chargerSourcePriority",
                        CHARGER_PRIORITY_BY_VALUE, CHARGER_PRIORITY_ALIASES,
                    ),
                    "telemetry_fallbacks": {
                        key: {
                            "value": time_series.get(key),
                            "searched_state_keys": candidates,
                            "matched_state_key": find_entry(fields, candidates)[0],
                        }
                        for key, (candidates, _kind) in TELEMETRY_STATE_FALLBACKS.items()
                    },
                },
            }
        )

    return async_redact_data(
        {
            "entry": {
                "version": entry.version,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "station": {
                "station_id": stored.get("station_id"),
                "monthly": (station_coordinator.data or {}).get("monthly")
                if station_coordinator
                else None,
                "device_count": len(device_coordinators),
            },
            "devices": devices,
        },
        TO_REDACT,
    )
