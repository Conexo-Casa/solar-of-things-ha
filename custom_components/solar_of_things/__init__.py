"""The Solar of Things integration.

Authentication notes
────────────────────
The integration supports two modes:

  Email + Password (MODE_PASSWORD):
    • api.login() is called at setup → obtains accessToken + refreshToken.
    • _ensure_token_valid() is called before every API request; it proactively
      refreshes the token 5 minutes before expiry using the refresh-token
      endpoint, and falls back to re-login with stored credentials if the
      refresh token is also expired.
    • on_token_refreshed callback updates the config entry with fresh tokens so
      the state survives HA restarts without having to re-login every time.

  Legacy IOT-Token (MODE_TOKEN):
    • The stored token is used as-is.
    • On 401 / TokenExpiredError, the coordinator raises UpdateFailed and also
      calls entry.async_start_reauth() so the user is prompted for a fresh token.

Version history
────────────────
  v2.3.0 – user-id/password auth (replacing email), working IOT-Open signing
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SolarOfThingsAPI, TokenExpiredError, merge_state_fallbacks
from .const import (
    DOMAIN,
    CONF_USER_ID,
    CONF_PASSWORD,
    CONF_IOT_TOKEN,
    CONF_STATION_ID,
    CONF_DEVICE_ID,
    CONF_TIME_ZONE,
    CONF_REFRESH_TOKEN,
    CONF_ACCESS_TOKEN_EXPIRES,
    CONF_REFRESH_TOKEN_EXPIRES,
)
from .helpers import state_fields

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT, Platform.SWITCH]

DEVICE_UPDATE_INTERVAL = timedelta(minutes=5)
STATION_UPDATE_INTERVAL = timedelta(minutes=30)


# ──────────────────────────────────────────────────────────────────────────────
# Entry setup / teardown
# ──────────────────────────────────────────────────────────────────────────────

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar of Things from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    time_zone = entry.data.get(CONF_TIME_ZONE) or entry.options.get(CONF_TIME_ZONE)
    user_id = entry.data.get(CONF_USER_ID)
    password = entry.data.get(CONF_PASSWORD)

    # Build the token-refreshed callback *before* constructing the API so the
    # callback reference is captured.
    # NOTE: this callback is invoked from a background executor thread (inside
    # api.login / api.refresh_access_token).  async_update_entry must only be
    # called from the event loop, so we schedule it with call_soon_threadsafe.
    def _on_token_refreshed(
        access_token: str,
        refresh_token: str,
        access_expires: str,
        refresh_expires: str,
    ) -> None:
        """Persist refreshed token back to the config entry (thread-safe)."""

        @callback
        def _update() -> None:
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_IOT_TOKEN: access_token,
                    CONF_REFRESH_TOKEN: refresh_token,
                    CONF_ACCESS_TOKEN_EXPIRES: access_expires,
                    CONF_REFRESH_TOKEN_EXPIRES: refresh_expires,
                },
            )
            _LOGGER.debug(
                "SolarOfThings [%s]: access token refreshed; entry data updated",
                entry.entry_id,
            )

        hass.loop.call_soon_threadsafe(_update)

    # Instantiate API in the appropriate auth mode
    if user_id and password:
        api = SolarOfThingsAPI(
            user_id=user_id,
            password=password,
            iot_token=entry.data.get(CONF_IOT_TOKEN),          # cached token (avoids login on every restart)
            refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
            access_token_expires=entry.data.get(CONF_ACCESS_TOKEN_EXPIRES),
            refresh_token_expires=entry.data.get(CONF_REFRESH_TOKEN_EXPIRES),
            time_zone=time_zone,
            on_token_refreshed=_on_token_refreshed,
        )
        # If the cached token is already expired (or absent), login immediately.
        if not api.access_token:
            await hass.async_add_executor_job(api.login)
    else:
        # Legacy IOT-token mode
        api = SolarOfThingsAPI(
            iot_token=entry.data[CONF_IOT_TOKEN],
            time_zone=time_zone,
            on_token_refreshed=_on_token_refreshed,
        )

    station_id = entry.data[CONF_STATION_ID]
    configured_device_id = (entry.data.get(CONF_DEVICE_ID) or "").strip()

    # ── Station coordinator (device list + monthly) ────────────────────────────
    station_coordinator = SolarOfThingsStationCoordinator(
        hass=hass,
        api=api,
        station_id=station_id,
        entry=entry,
    )
    await station_coordinator.async_config_entry_first_refresh()

    # ── Per-device coordinators ────────────────────────────────────────────────
    devices: list[dict[str, Any]] = (
        station_coordinator.data.get("devices", []) if station_coordinator.data else []
    )

    if configured_device_id:
        filtered = [d for d in devices if str(d.get("id")) == configured_device_id]
        devices = filtered if filtered else [
            {"id": configured_device_id, "name": configured_device_id}
        ]

    device_coordinators: dict[str, SolarOfThingsDeviceCoordinator] = {}

    for dev in devices:
        device_id = str(dev.get("id") or "")
        if not device_id:
            continue
        c = SolarOfThingsDeviceCoordinator(
            hass=hass,
            api=api,
            station_id=station_id,
            device=device_id,
            device_meta=dev,
            entry=entry,
        )
        await c.async_config_entry_first_refresh()
        device_coordinators[device_id] = c

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "station_id": station_id,
        "station_coordinator": station_coordinator,
        "device_coordinators": device_coordinators,
        "devices": devices,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Explicitly register the station hub device so that per-device entities
    # can reference it via via_device without triggering the
    # "non existing via_device" warning introduced in HA 2025.12.
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, station_id)},
        name=f"Solar Station {station_id}",
        manufacturer="Siseli",
        model="Station",
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


# ──────────────────────────────────────────────────────────────────────────────
# Coordinators
# ──────────────────────────────────────────────────────────────────────────────

class SolarOfThingsStationCoordinator(DataUpdateCoordinator):
    """Fetch station-level data (device list + monthly stats)."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SolarOfThingsAPI,
        station_id: str,
        entry: ConfigEntry,
    ) -> None:
        self.api = api
        self.station_id = station_id
        self._entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_station_{station_id}",
            update_interval=STATION_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            devices = await self.hass.async_add_executor_job(
                self.api.list_devices, self.station_id
            )
            monthly = await self.hass.async_add_executor_job(
                self.api.fetch_monthly_summary, self.station_id
            )
            return {"devices": devices, "monthly": monthly}
        except TokenExpiredError as err:
            _LOGGER.error(
                "SolarOfThings station %s: token expired — triggering re-auth: %s",
                self.station_id, err,
            )
            self._entry.async_start_reauth(self.hass)
            raise UpdateFailed(f"Token expired: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Station update failed: {err}") from err


class SolarOfThingsDeviceCoordinator(DataUpdateCoordinator):
    """Fetch device-level telemetry + settings."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SolarOfThingsAPI,
        station_id: str,
        device: str,
        device_meta: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        self.api = api
        self.station_id = station_id
        self.device_id = device
        self.device_meta = device_meta
        self._entry = entry
        self._keys_logged = False
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_device_{device}",
            update_interval=DEVICE_UPDATE_INTERVAL,
        )

    def _log_available_keys(
        self,
        time_series: dict[str, Any],
        settings: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        """Log every attribute name this device exposes, once per HA run.

        An entity that reads "unknown" almost always means the model publishes
        the measurement under a name the integration does not know yet.  With
        debug logging enabled these three lists show exactly which names are
        available, so a missing one can be added to the candidate lists in
        const.py (see API_CAPTURE.md).
        """
        if self._keys_logged or not _LOGGER.isEnabledFor(logging.DEBUG):
            return
        self._keys_logged = True
        fields = state_fields(state)
        _LOGGER.debug(
            "SolarOfThings device %s attribute names — "
            "time-series: %s | settings-cache: %s | state-snapshot: %s",
            self.device_id,
            sorted(time_series),
            sorted(settings or {}),
            sorted(fields),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            time_series = await self.hass.async_add_executor_job(
                self.api.fetch_latest_data, self.device_id
            )
            settings = await self.hass.async_add_executor_job(
                self.api.fetch_settings, self.device_id
            )
            try:
                state = await self.hass.async_add_executor_job(
                    self.api.fetch_state, self.device_id
                )
            except TokenExpiredError:
                raise
            except Exception as err:
                _LOGGER.warning(
                    "SolarOfThings device %s: state fetch failed: %s", self.device_id, err
                )
                state = {}

            # Logged before merging so each list shows what its own endpoint
            # actually returned.
            self._log_available_keys(time_series, settings, state)

            # The time-series endpoint only returns the attribute names it
            # knows; anything it omitted is filled from the live snapshot.
            time_series = merge_state_fallbacks(time_series, state)

            return {
                "time_series": time_series,
                "settings": settings,
                "state": state,
                "device": self.device_id,
                "station_id": self.station_id,
                "device_meta": self.device_meta,
            }
        except TokenExpiredError as err:
            _LOGGER.error(
                "SolarOfThings device %s: token expired — triggering re-auth: %s",
                self.device_id, err,
            )
            self._entry.async_start_reauth(self.hass)
            raise UpdateFailed(f"Token expired: {err}") from err
        except Exception as err:
            raise UpdateFailed(
                f"Device update failed for {self.device_id}: {err}"
            ) from err
