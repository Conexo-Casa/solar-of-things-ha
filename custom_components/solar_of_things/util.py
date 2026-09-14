"""Small helpers shared between the config flow and entry setup.

Deliberately free of Home Assistant imports so the logic can be unit-tested on
its own.
"""
from __future__ import annotations

from typing import Any

try:
    from zoneinfo import available_timezones
except ImportError:  # pragma: no cover - Python < 3.9, not a supported HA target
    available_timezones = None  # type: ignore[assignment]

from .const import WHITESPACE_SENSITIVE_FIELDS


def normalise_config_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *data* with whitespace trimmed from identifier fields.

    The Station ID, Device ID, account name, IOT token and time zone are all
    pasted or typed by hand.  A trailing space picked up while copying an ID out
    of the browser's Network tab makes the upstream API reject the value, and the
    user only sees "cannot connect" with no hint as to why.

    Which fields are trimmed is defined once in WHITESPACE_SENSITIVE_FIELDS so
    the config-flow path and the entry-setup path cannot drift apart.  The
    password is never trimmed — whitespace there may be intentional.

    Non-string values are passed through untouched, so this is safe to call on
    a mapping that also carries token-expiry timestamps and similar.
    """
    cleaned = dict(data)
    for key in WHITESPACE_SENSITIVE_FIELDS:
        value = cleaned.get(key)
        if isinstance(value, str):
            cleaned[key] = value.strip()
    return cleaned


def is_valid_time_zone(value: str) -> bool:
    """Return whether *value* is a real IANA time zone id (e.g. "Europe/Warsaw").

    The time-zone field is free text (issue #21): a continent name like
    "Europe" or a bare offset reads as plausible to a user copying from a
    dropdown elsewhere, but is not a zoneinfo key. Sent as-is in the
    IOT-Time-Zone header, the Siseli portal's timeseries endpoint rejects it
    outright with "Timeseries error code=20101 message=Illegal argument" —
    on the very first API call, with nothing in the error pointing at time
    zone as the cause. Catching this locally turns that into a same-form
    validation error instead of a cryptic upstream failure during setup.
    """
    if not value:
        return False
    if available_timezones is None:  # pragma: no cover
        return True
    return value in available_timezones()
