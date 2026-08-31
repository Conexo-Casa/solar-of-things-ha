"""Config flow for Solar of Things integration.

Supports two setup modes:
  1. User-ID + Password  (recommended) – integration logs in automatically and
     refreshes the token without any user intervention.
  2. IOT Token (legacy / advanced) – user pastes the token from DevTools.
     A re-auth flow is triggered when the token expires.

Re-auth flow:  HA calls async_step_reauth when a TokenExpiredError is caught by
the coordinator.  The user is asked only for the field(s) that need updating
(usually just a fresh token, or new credentials).
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .api import SolarOfThingsAPI, AuthenticationError, TokenExpiredError
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
from .util import normalise_config_fields

_LOGGER = logging.getLogger(__name__)

# ─── Validation helpers ────────────────────────────────────────────────────────

async def _validate_password_auth(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate user-ID/password auth, return title."""
    api = SolarOfThingsAPI(
        user_id=data[CONF_USER_ID],
        password=data[CONF_PASSWORD],
        time_zone=data.get(CONF_TIME_ZONE),
    )
    try:
        await hass.async_add_executor_job(api.login)
    except AuthenticationError as err:
        raise InvalidAuth(str(err)) from err
    except Exception as err:
        raise CannotConnect(str(err)) from err

    # After login, validate station
    ok = await hass.async_add_executor_job(api.test_connection, data[CONF_STATION_ID])
    if not ok:
        raise CannotConnect("Station/device unreachable after login.")

    return {
        "title": f"Solar Station {data[CONF_STATION_ID]}",
        CONF_IOT_TOKEN: api.access_token,
        CONF_REFRESH_TOKEN: api.refresh_token,
        CONF_ACCESS_TOKEN_EXPIRES: api.access_token_expires_iso,
        CONF_REFRESH_TOKEN_EXPIRES: api.refresh_token_expires_iso,
    }


async def _validate_token_auth(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate legacy IOT-token auth, return title."""
    api = SolarOfThingsAPI(
        iot_token=data[CONF_IOT_TOKEN],
        time_zone=data.get(CONF_TIME_ZONE),
    )
    station_id = data[CONF_STATION_ID]
    device_id = (data.get(CONF_DEVICE_ID) or "").strip()

    try:
        if device_id:
            res = await hass.async_add_executor_job(api.fetch_latest_data, device_id)
            ok = bool(res)
        else:
            ok = await hass.async_add_executor_job(api.test_connection, station_id)
    except Exception as err:
        _LOGGER.error("Token validation failed: %s", err)
        ok = False

    if not ok:
        raise CannotConnect("Cannot connect with provided token.")

    return {"title": f"Solar Station {station_id}"}


# ─── Config Flow ───────────────────────────────────────────────────────────────

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar of Things."""

    VERSION = 3  # bumped for new auth fields

    def __init__(self) -> None:
        self._auth_mode: str = "password"  # "password" | "token"

    # ── Step 1: choose auth mode ───────────────────────────────────────────────

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Offer choice of auth mode."""
        if user_input is not None:
            self._auth_mode = user_input.get("auth_mode", "password")
            if self._auth_mode == "token":
                return await self.async_step_token()
            return await self.async_step_password()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("auth_mode", default="password"): vol.In(
                        {"password": "User ID + Password (recommended)", "token": "IOT Token (advanced)"}
                    )
                }
            ),
            description_placeholders={
                "docs_url": "https://github.com/Conexo-Casa/solar-of-things-ha"
            },
        )

    # ── Step 2a: user-id + password ────────────────────────────────────────────

    async def async_step_password(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """User-ID + password setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Trim before validating *and* before storing, so the value that is
            # checked is the same one that gets persisted.
            user_input = normalise_config_fields(user_input)
            try:
                info = await _validate_password_auth(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception in password step")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(f"station_{user_input[CONF_STATION_ID]}")
                self._abort_if_unique_id_configured()
                entry_data = {
                    CONF_USER_ID: user_input[CONF_USER_ID],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_STATION_ID: user_input[CONF_STATION_ID],
                    CONF_DEVICE_ID: user_input.get(CONF_DEVICE_ID, ""),
                    CONF_TIME_ZONE: user_input.get(CONF_TIME_ZONE, "Asia/Manila"),
                    CONF_IOT_TOKEN: info[CONF_IOT_TOKEN],
                    CONF_REFRESH_TOKEN: info[CONF_REFRESH_TOKEN],
                    CONF_ACCESS_TOKEN_EXPIRES: info[CONF_ACCESS_TOKEN_EXPIRES],
                    CONF_REFRESH_TOKEN_EXPIRES: info[CONF_REFRESH_TOKEN_EXPIRES],
                }
                return self.async_create_entry(title=info["title"], data=entry_data)

        return self.async_show_form(
            step_id="password",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USER_ID): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                    vol.Required(CONF_STATION_ID): cv.string,
                    vol.Optional(CONF_DEVICE_ID): cv.string,
                    vol.Optional(CONF_TIME_ZONE, default="Asia/Manila"): cv.string,
                }
            ),
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/Conexo-Casa/solar-of-things-ha"
            },
        )

    # ── Step 2b: legacy IOT token ─────────────────────────────────────────────

    async def async_step_token(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Legacy IOT-token setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # The entry is created from this same dict, so trim it up front.
            user_input = normalise_config_fields(user_input)
            try:
                info = await _validate_token_auth(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception in token step")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(f"station_{user_input[CONF_STATION_ID]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="token",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IOT_TOKEN): cv.string,
                    vol.Required(CONF_STATION_ID): cv.string,
                    vol.Optional(CONF_DEVICE_ID): cv.string,
                    vol.Optional(CONF_TIME_ZONE, default="Asia/Manila"): cv.string,
                }
            ),
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/Conexo-Casa/solar-of-things-ha"
            },
        )

    # ── Re-auth flow ───────────────────────────────────────────────────────────

    async def async_step_reauth(self, entry_data: dict[str, Any] | None = None) -> FlowResult:
        """Triggered by the coordinator when TokenExpiredError is raised."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask the user to re-enter credentials or a fresh token."""
        errors: dict[str, str] = {}
        existing_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        has_password = bool(
            existing_entry
            and (
                existing_entry.data.get(CONF_PASSWORD)
                or existing_entry.data.get(CONF_USER_ID)
            )
        )

        if user_input is not None:
            # Matters most for the token path: a freshly pasted IOT token is the
            # single most whitespace-prone value in this integration.
            user_input = normalise_config_fields(user_input)
            if has_password:
                # Re-authenticate with potentially updated email/password
                # Normalise the merge, not just user_input: the station/device
                # IDs come from the stored entry, which may pre-date trimming.
                merged = normalise_config_fields(
                    {**(existing_entry.data if existing_entry else {}), **user_input}
                )
                try:
                    info = await _validate_password_auth(self.hass, merged)
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected exception during re-auth")
                    errors["base"] = "unknown"
                else:
                    self.hass.config_entries.async_update_entry(
                        existing_entry,
                        data={
                            **existing_entry.data,
                            CONF_PASSWORD: user_input.get(CONF_PASSWORD, existing_entry.data.get(CONF_PASSWORD)),
                            CONF_IOT_TOKEN: info[CONF_IOT_TOKEN],
                            CONF_REFRESH_TOKEN: info[CONF_REFRESH_TOKEN],
                            CONF_ACCESS_TOKEN_EXPIRES: info[CONF_ACCESS_TOKEN_EXPIRES],
                            CONF_REFRESH_TOKEN_EXPIRES: info[CONF_REFRESH_TOKEN_EXPIRES],
                        },
                    )
                    await self.hass.config_entries.async_reload(existing_entry.entry_id)
                    return self.async_abort(reason="reauth_successful")
            else:
                # Legacy token mode: user provides a fresh token
                # Normalise the merge, not just user_input: the station/device
                # IDs come from the stored entry, which may pre-date trimming.
                merged = normalise_config_fields(
                    {**(existing_entry.data if existing_entry else {}), **user_input}
                )
                try:
                    await _validate_token_auth(self.hass, merged)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected exception during re-auth (token)")
                    errors["base"] = "unknown"
                else:
                    self.hass.config_entries.async_update_entry(
                        existing_entry,
                        data={**existing_entry.data, CONF_IOT_TOKEN: user_input[CONF_IOT_TOKEN]},
                    )
                    await self.hass.config_entries.async_reload(existing_entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

        # Build schema based on whether the entry has stored credentials
        if has_password:
            schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_PASSWORD,
                        description={"suggested_value": ""},
                    ): cv.string,
                }
            )
        else:
            schema = vol.Schema({vol.Required(CONF_IOT_TOKEN): cv.string})

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )


# ─── Custom exceptions ─────────────────────────────────────────────────────────

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate invalid authentication credentials."""
