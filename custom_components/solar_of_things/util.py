"""Small helpers shared between the config flow and entry setup.

Deliberately free of Home Assistant imports so the logic can be unit-tested on
its own.
"""
from __future__ import annotations

from typing import Any

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
