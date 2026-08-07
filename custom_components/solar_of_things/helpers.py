"""Value-resolution helpers for the Siseli API payloads.

The portal exposes device data through three differently-shaped payloads, and
the attribute names inside them vary between inverter models (PI30, VMIII,
Voltronic clones, …).  Everything in this module therefore looks a value up by
a *list of candidate keys*, matched case-insensitively, instead of hard-coding
one name.

  settings   ``POST /apis/remote/device/configs/cache/get``
             ``{"outputSourcePrioritySetting": {"key": …, "value": 2,
                                                "valueDisplay": "SBU"}, …}``
             This is a *write cache*: it holds the values that were pushed to
             the device through the portal, so on an account that has never
             changed a setting remotely it comes back empty.  That is why the
             priority selects showed ``unknown`` — there was nothing to read.

  state      ``GET /apis/deviceState/simple/state/latest/v1``
             ``{"fields": {"outputSourcePriority": {"value": 2,
                                                    "valueDisplay": "SBU",
                                                    "unit": "W"}, …},
                "firingAlarms": [...]}``
             The live snapshot the portal's overview page renders.  This is the
             authoritative source for *current* values and is what we read
             first everywhere.

  timeseries ``POST /apis/deviceState/simple/attribute/keys/history/v1``
             ``{"payload": {"fields": {"pvInputPower": [...], …}}}``
             Only returns keys that were explicitly requested *and* that the
             model actually records, so a key missing here does not mean the
             device lacks the measurement — the state snapshot may still have
             it under a different name.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable

_LOGGER = logging.getLogger(__name__)

# Where a field entry keeps its unit, depending on model/firmware.
_UNIT_KEYS = ("unit", "unitSymbol", "valueUnit", "units")

# Scale factors onto the canonical unit used by the integration.
_POWER_SCALE = {"w": 1.0, "kw": 1000.0, "mw": 1_000_000.0, "va": 1.0, "kva": 1000.0}
_ENERGY_SCALE = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0}

# kind → (canonical unit, scale table).  Kinds without a table are passed
# through unscaled.
_SCALES: dict[str, dict[str, float]] = {
    "power": _POWER_SCALE,
    "energy": _ENERGY_SCALE,
}


# ──────────────────────────────────────────────────────────────────────────────
# Generic extraction
# ──────────────────────────────────────────────────────────────────────────────

def state_fields(state: dict[str, Any] | None) -> dict[str, Any]:
    """Return the ``fields`` mapping of a state/latest payload.

    Accepts the payload either already unwrapped (``{"fields": {...}}``) or
    wrapped one level deeper (``{"data": {"fields": {...}}}``), and tolerates
    a payload that *is* the fields mapping itself.
    """
    if not isinstance(state, dict):
        return {}
    for candidate in (state, state.get("data")):
        if isinstance(candidate, dict):
            fields = candidate.get("fields")
            if isinstance(fields, dict):
                return fields
    # Some firmwares return the attributes flat; treat dict-of-dicts as fields.
    if state and all(isinstance(v, dict) for v in state.values()):
        return state
    return {}


def find_entry(
    fields: dict[str, Any] | None, candidates: Iterable[str]
) -> tuple[str | None, Any]:
    """Return ``(matched_key, entry)`` for the first candidate present.

    Matching is case-insensitive because the API is inconsistent about the
    leading character (``PV1InputVoltage`` vs ``pv1InputCurrent``).
    """
    if not isinstance(fields, dict) or not fields:
        return None, None
    lowered = {str(k).lower(): k for k in fields}
    for candidate in candidates:
        actual = lowered.get(str(candidate).lower())
        if actual is not None:
            return actual, fields[actual]
    return None, None


def entry_value(entry: Any) -> Any:
    """Return the raw value of a field/setting entry (or the entry itself)."""
    if isinstance(entry, dict):
        for key in ("value", "val", "rawValue"):
            if key in entry:
                return entry[key]
        return None
    return entry


def entry_display(entry: Any) -> Any:
    """Return the human-readable rendering of a field/setting entry, if any."""
    if isinstance(entry, dict):
        for key in ("valueDisplay", "displayValue", "display", "text"):
            value = entry.get(key)
            if value not in (None, ""):
                return value
    return None


def entry_unit(entry: Any) -> str | None:
    """Return the unit string attached to a field entry, if any."""
    if isinstance(entry, dict):
        for key in _UNIT_KEYS:
            unit = entry.get(key)
            if isinstance(unit, str) and unit.strip():
                return unit.strip()
    return None


def to_float(value: Any) -> float | None:
    """Best-effort float conversion; returns None for blanks and non-numerics."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        # Values sometimes arrive with the unit appended, e.g. "1234.5 W".
        match = re.match(r"^[-+]?\d*\.?\d+", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None


def scale_value(value: float, unit: str | None, kind: str | None) -> float:
    """Convert *value* to the integration's canonical unit for *kind*.

    Unknown units and unknown kinds are passed through untouched — better a
    plausible number in the wrong unit than no reading at all.
    """
    table = _SCALES.get(kind or "")
    if not table or not unit:
        return value
    factor = table.get(unit.strip().lower())
    if factor is None:
        return value
    return value * factor


def state_number(
    fields: dict[str, Any] | None,
    candidates: Iterable[str],
    kind: str | None = None,
) -> float | None:
    """Read a numeric measurement out of the state snapshot.

    Returns None when no candidate key exists or the value is not numeric.
    """
    key, entry = find_entry(fields, candidates)
    if key is None:
        return None
    number = to_float(entry_value(entry))
    if number is None:
        return None
    return scale_value(number, entry_unit(entry), kind)


def setting_number(
    settings: dict[str, Any] | None, candidates: Iterable[str]
) -> float | None:
    """Read a numeric value out of the remote-config settings cache."""
    _key, entry = find_entry(settings, candidates)
    if entry is None:
        return None
    return to_float(entry_value(entry))


# ──────────────────────────────────────────────────────────────────────────────
# Enum / option resolution
# ──────────────────────────────────────────────────────────────────────────────

def normalise_text(value: Any) -> str:
    """Lowercase *value* and collapse every non-alphanumeric run to one space."""
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _option_from_number(raw: Any, by_value: dict[int, str]) -> str | None:
    number = to_float(raw)
    if number is None or number != int(number):
        return None
    return by_value.get(int(number))


def _option_from_text(raw: Any, aliases: dict[str, str]) -> str | None:
    text = normalise_text(raw)
    if not text:
        return None
    if text in aliases:
        return aliases[text]
    # Fall back to scanning for a mode abbreviation (SBU, SNU, …) anywhere in
    # the string, so localised labels like "Solar first (SBU)" still resolve.
    for token in text.split():
        if len(token) == 3 and token in aliases:
            return aliases[token]
    return None


def resolve_option(
    raw: Any,
    display: Any,
    by_value: dict[int, str],
    aliases: dict[str, str],
) -> str | None:
    """Map an API value/display pair onto one of the select's option strings.

    Handles all the shapes seen in the wild: an integer code (``2``), a numeric
    string (``"2"``), an abbreviation (``"SBU"``) and a full label
    (``"Solar+Battery first (SBU)"``).  Returns None when nothing matches so the
    caller can log the raw payload instead of crashing the select entity.
    """
    for candidate in (raw, display):
        option = _option_from_number(candidate, by_value)
        if option is not None:
            return option
    for candidate in (display, raw):
        option = _option_from_text(candidate, aliases)
        if option is not None:
            return option
    return None
