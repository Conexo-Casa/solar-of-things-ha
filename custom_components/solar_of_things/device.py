"""Device-registry helpers shared by every entity platform.

HA 2026.8 deprecated the ``via_device`` (domain, identifier) tuple in
``DeviceInfo`` in favour of ``via_device_id`` (the registry id of the parent
device); the old key stops working in HA 2027.8 (issues #34, #37).  The parent
here is the station hub device, which ``async_setup_entry`` registers before
any platform is forwarded, so its registry id can be resolved at the moment HA
reads an entity's ``device_info``.  The same release deprecated the
entry-agnostic ``async_get_device`` lookup, so the hub is resolved with
``async_get_device_by_identifier`` scoped to the config entry.
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

# HA releases before 2026.8 don't know via_device_id; keep the old key there
# (hacs.json still allows them) rather than silently dropping the hub link.
_SUPPORTS_VIA_DEVICE_ID = "via_device_id" in getattr(dr.DeviceInfo, "__annotations__", {})


# ── Per-device DeviceInfo ────────────────────────────────────────────────────
def inverter_device_info(
    hass: HomeAssistant | None,
    config_entry_id: str | None,
    station_id: str,
    device_id: str,
    device_name: str,
    model: str | None,
) -> dict[str, Any]:
    """Return the DeviceInfo for one inverter, linked to its station hub."""
    info: dict[str, Any] = {
        "identifiers": {(DOMAIN, device_id)},
        "name":        device_name,
        "manufacturer": "Siseli",
        "model":       model,
    }

    if not _SUPPORTS_VIA_DEVICE_ID:
        info["via_device"] = (DOMAIN, station_id)
        return info

    if hass is not None and config_entry_id:
        hub = dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, station_id), config_entry_id
        )
        if hub is not None:
            info["via_device_id"] = hub.id
    return info
