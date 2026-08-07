"""API client for Solar of Things (solar.siseli.com).

Authentication strategy
─────────────────────────────────────────────────────────────────────────────
The Siseli portal uses a dual-token system.  Login requires the IOT Open
Platform signing scheme discovered via JS bundle analysis (umi.js):

  Endpoint : POST https://test.solar.siseli.com/apis/login/account
  Signed   : yes — IOT-Open-AppID, IOT-Open-Nonce, IOT-Open-Body-Hash,
                    IOT-Open-Sign headers

Signing algorithm (reverse-engineered from portal umi.js):
  1. Build a dict of signing headers:
       {"IOT-Open-AppID": appId,
        "IOT-Open-Body-Hash": sha256(body_bytes).lower(),
        "IOT-Open-Nonce": random_32_char_hex}
  2. Sort keys alphabetically, join as k1=v1&k2=v2 (no URL-encoding).
  3. base64-encode the resulting string.
  4. HMAC-SHA256(b64_str, decrypted_app_secret)  [bytes result]
  5. MD5(hmac_bytes).hexdigest()  → IOT-Open-Sign value

App secret decryption (qe() in umi.js):
  key = MD5(appId).lower()[:16]  treated as ASCII bytes  (16 bytes = AES-128)
  iv  = MD5(appId).lower()[16:]  treated as ASCII bytes  (16 bytes)
  AES-128-CBC-ZeroPadding decrypt of base64(encrypted_secret)

After successful login the server returns an accessToken (used as
IOT-Token header for data requests) and a refreshToken.

This class supports three auth modes, tried in priority order:

  1. User-ID + password  (recommended)
     • Call login() at startup → stores both tokens in memory.
     • _ensure_token_valid() checks expiry before every API call and
       proactively refreshes (TOKEN_REFRESH_LEAD_SECONDS = 5 min before
       expiry, mirroring the portal JS behaviour).
     • If refresh fails, raises TokenExpiredError so the HA integration
       can trigger a re-auth flow.

  2. Token-pair (accessToken + refreshToken) without password
     • User pastes both tokens from DevTools.
     • Same proactive-refresh logic; re-auth needed when refreshToken
       expires.

  3. Legacy IOT-token only (backwards compatibility)
     • No refresh possible; raises TokenExpiredError on 401 so HA can
       prompt the user to re-enter a fresh token.

Usage in Home Assistant
─────────────────────────────────────────────────────────────────────────────
  api = SolarOfThingsAPI(
      user_id="myaccount",
      password="secret",          # or omit and pass iot_token=
      time_zone="Asia/Manila",
      on_token_refreshed=_save_tokens_callback,
  )
  await hass.async_add_executor_job(api.login)
  data = await hass.async_add_executor_job(api.fetch_latest_data, device_id)
"""
from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Callable

import requests

try:
    from Crypto.Cipher import AES as _AES
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

from .const import (
    API_BASE_URL,
    API_AUTH_BASE_URL,
    API_LOGIN,
    API_REFRESH_TOKEN as API_REFRESH_TOKEN_ENDPOINT,
    API_TIME_SERIES,
    API_MONTHLY_SUMMARY,
    API_DEVICE_LIST,
    API_SETTINGS_GET,
    API_SETTINGS_READ,
    API_SETTINGS_READ_DETAILS,
    API_SETTINGS_SET,
    BOOLEAN_CONTROLS,
    CHARGER_PRIORITY_BY_VALUE,
    IOT_APP_ID,
    IOT_APP_SECRET_ENC,
    NUMBER_CONTROLS,
    OUTPUT_PRIORITY_BY_VALUE,
    SETTING_KEY_CANDIDATES,
    TELEMETRY_STATE_FALLBACKS,
    TOKEN_REFRESH_LEAD_SECONDS,
)
from .const import STATE_KEY_CANDIDATES
from .helpers import (
    entry_display,
    entry_value,
    find_entry,
    normalise_text,
    state_fields,
    state_number,
    to_float,
)

_LOGGER = logging.getLogger(__name__)

_DEFAULT_TZ = "Asia/Manila"


# ──────────────────────────────────────────────────────────────────────────────
# Custom exceptions
# ──────────────────────────────────────────────────────────────────────────────

class TokenExpiredError(Exception):
    """Raised when the access token has expired and cannot be refreshed.

    The HA integration should catch this and call
    config_entry.async_start_reauth() so the user can re-enter credentials.
    """


class AuthenticationError(Exception):
    """Raised when login credentials are rejected by the server."""


# ──────────────────────────────────────────────────────────────────────────────
# Signing helpers  (reverse-engineered from portal umi.js)
# ──────────────────────────────────────────────────────────────────────────────

def _decrypt_app_secret(app_id: str, encrypted_b64: str) -> str:
    """AES-128-CBC decrypt the embedded app secret.

    Key derivation mirrors the portal qe() function:
      key = MD5(app_id).lower()[:16]  as ASCII bytes
      iv  = MD5(app_id).lower()[16:]  as ASCII bytes
    The ciphertext is the base64-decoded encrypted_b64 value.
    """
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError(
            "pycryptodome is not installed. "
            "Add 'pycryptodome' to the integration requirements."
        )
    md5_hex = hashlib.md5(app_id.encode("utf-8")).hexdigest()
    key = md5_hex[:16].encode("ascii")   # 16 bytes — AES-128
    iv  = md5_hex[16:].encode("ascii")   # 16 bytes — CBC IV
    ciphertext = base64.b64decode(encrypted_b64)
    cipher = _AES.new(key, _AES.MODE_CBC, iv)
    plaintext = cipher.decrypt(ciphertext).rstrip(b"\x00")
    return plaintext.decode("utf-8")


def _compute_iot_sign(app_id: str, nonce: str, body_hash: str, secret: str) -> str:
    """Compute the IOT-Open-Sign header value.

    Algorithm (Ye() in portal umi.js):
      1. Sort signing headers alphabetically by key.
      2. qs.stringify → "IOT-Open-AppID=X&IOT-Open-Body-Hash=Y&IOT-Open-Nonce=Z"
      3. Base64-encode the qs string.
      4. HMAC-SHA256(b64_qs, secret) → raw bytes.
      5. MD5(hmac_bytes).hexdigest() → sign value.
    """
    sign_headers = {
        "IOT-Open-AppID": app_id,
        "IOT-Open-Body-Hash": body_hash,
        "IOT-Open-Nonce": nonce,
    }
    qs_str = "&".join(f"{k}={sign_headers[k]}" for k in sorted(sign_headers.keys()))
    b64_qs = base64.b64encode(qs_str.encode("utf-8")).decode("ascii")
    hmac_bytes = _hmac.new(secret.encode("utf-8"), b64_qs.encode("utf-8"), hashlib.sha256).digest()
    return hashlib.md5(hmac_bytes).hexdigest()


def _make_signed_headers(body_bytes: bytes, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build the complete set of IOT Open Platform signed request headers.

    Returns headers suitable for POST to API_AUTH_BASE_URL endpoints.
    """
    secret = _decrypt_app_secret(IOT_APP_ID, IOT_APP_SECRET_ENC)
    nonce = os.urandom(16).hex()          # 32-char hex nonce
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    sign = _compute_iot_sign(IOT_APP_ID, nonce, body_hash, secret)

    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Origin": "https://solar.siseli.com",
        "Referer": "https://solar.siseli.com/",
        "IOT-Open-AppID": IOT_APP_ID,
        "IOT-Open-Nonce": nonce,
        "IOT-Open-Body-Hash": body_hash,
        "IOT-Open-Sign": sign,
    }
    if extra:
        headers.update(extra)
    return headers


# ──────────────────────────────────────────────────────────────────────────────
# Helper: parse Siseli ISO expiry strings safely
# ──────────────────────────────────────────────────────────────────────────────

def _parse_expiry(value: str | None) -> datetime | None:
    """Return an aware UTC datetime from an ISO-8601 string, or None."""
    if not value:
        return None
    try:
        # Python 3.7+ fromisoformat doesn't handle trailing 'Z'
        cleaned = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Telemetry assembly
# ──────────────────────────────────────────────────────────────────────────────

def compute_derived_values(values: dict[str, Any]) -> dict[str, Any]:
    """Fill in batteryPower / gridPower / loadPower from the raw measurements.

    Idempotent, so it can be re-run after the state-snapshot fallbacks have
    supplied keys that the time-series endpoint did not return.
    """
    def _num(key: str) -> float:
        try:
            return float(values.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    voltage = _num("batteryVoltage")
    discharge = _num("batteryDischargeCurrent")
    charge = _num("batteryChargingCurrent")
    values["batteryPower"] = (discharge - charge) * voltage

    pv_power = _num("pvInputPower")
    ac_output = _num("acOutputActivePower")
    feed_in = _num("feedInPower")
    battery_power = _num("batteryPower")

    values["gridPower"] = max(0.0, ac_output - pv_power + battery_power + feed_in)
    values["loadPower"] = ac_output
    return values


def merge_state_fallbacks(
    latest: dict[str, Any], state: dict[str, Any] | None
) -> dict[str, Any]:
    """Fill telemetry keys the time-series endpoint omitted from the snapshot.

    The history endpoint only returns keys the model actually records under the
    exact name we asked for, so measurements such as ``feedInPower`` come back
    empty on inverters that publish them under a different attribute name.  The
    state/latest snapshot carries every attribute the device reports, so we use
    it as the fallback source and then recompute the derived values.
    """
    fields = state_fields(state)
    if not fields:
        return latest

    for key, (candidates, kind) in TELEMETRY_STATE_FALLBACKS.items():
        if latest.get(key) not in (None, ""):
            continue
        value = state_number(fields, candidates, kind)
        if value is not None:
            latest[key] = value
            _LOGGER.debug(
                "SolarOfThings: %s not in time-series; using state snapshot (%s)",
                key, value,
            )

    # Off-grid models (PI30/VMIII) have no feed-in measurement at all — they
    # report only whether feeding the grid is permitted.  When it is switched
    # off, feed-in is definitively zero, which is both true and what the
    # derived grid-power figure needs; guessing "unknown" would be worse.
    if latest.get("feedInPower") in (None, ""):
        _key, entry = find_entry(fields, STATE_KEY_CANDIDATES["gridFeedIn"])
        if entry is not None and not _feed_in_enabled(entry):
            latest["feedInPower"] = 0.0

    return compute_derived_values(latest)


def _feed_in_enabled(entry: Any) -> bool:
    """Return True unless the solar-feed-to-grid setting reads as disabled."""
    number = to_float(entry_value(entry))
    if number is not None:
        return number != 0
    return normalise_text(entry_display(entry) or entry_value(entry)) not in {
        "disable",
        "disabled",
        "off",
        "no",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main API client
# ──────────────────────────────────────────────────────────────────────────────

class SolarOfThingsAPI:
    """Solar of Things API wrapper with automatic token refresh.

    Parameters
    ----------
    user_id:            Siseli portal login account / user-ID (preferred auth method).
    password:           Siseli portal password.
    iot_token:          Legacy/manual IOT-Token (used when user_id/password absent).
    refresh_token:      Stored refresh token (persisted between HA restarts).
    access_token_expires: ISO-8601 string of current access-token expiry.
    refresh_token_expires: ISO-8601 string of current refresh-token expiry.
    time_zone:          IOT-Time-Zone header value.
    on_token_refreshed: Optional callback(access_token, refresh_token,
                        access_expires_iso, refresh_expires_iso) called after
                        every successful token refresh so the HA entry can
                        persist the new tokens without restarting.
    """

    def __init__(
        self,
        *,
        user_id: str | None = None,
        password: str | None = None,
        iot_token: str | None = None,
        refresh_token: str | None = None,
        access_token_expires: str | None = None,
        refresh_token_expires: str | None = None,
        time_zone: str | None = None,
        on_token_refreshed: Callable[[str, str, str, str], None] | None = None,
    ) -> None:
        self._user_id = user_id
        self._password = password
        self._time_zone = time_zone or _DEFAULT_TZ
        self._on_token_refreshed = on_token_refreshed

        # Token state
        self._access_token: str = iot_token or ""
        self._refresh_token: str = refresh_token or ""
        self._access_expires: datetime | None = _parse_expiry(access_token_expires)
        self._refresh_expires: datetime | None = _parse_expiry(refresh_token_expires)

        # Thread-safety for concurrent refresh calls
        self._refresh_lock = threading.Lock()

        # Determine auth mode
        if user_id and password:
            self._auth_mode = "password"
        elif iot_token and refresh_token:
            self._auth_mode = "token_pair"
        elif iot_token:
            self._auth_mode = "legacy"
        else:
            raise ValueError("Provide either (user_id + password) or iot_token.")

        # HTTP session (headers updated after every token refresh)
        self.session = requests.Session()
        self._apply_token_headers()

    # ─── Session headers ───────────────────────────────────────────────────────

    def _apply_token_headers(self) -> None:
        """Write the current access token into the session headers."""
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "IOT-Token": self._access_token,
                "IOT-Time-Zone": self._time_zone,
                "Origin": "https://solar.siseli.com",
                "Referer": "https://solar.siseli.com/",
                "User-Agent": (
                    "HomeAssistant-SolarOfThings/2.3.0 "
                    "(+https://github.com/conexocasa/solar-of-things-ha)"
                ),
            }
        )

    # ─── Public auth helpers ───────────────────────────────────────────────────

    def login(self) -> None:
        """Authenticate with user-ID + password and store the resulting tokens.

        Uses the IOT Open Platform signed request format discovered from the
        portal JS bundle.  The login endpoint is:
          POST https://solar.siseli.com/apis/login/account

        The password is sent as MD5(plaintext_password) lowercase hex — this
        is how the portal processes it before transmitting.

        Raises AuthenticationError on bad credentials, or requests.RequestException
        on network failure.  Safe to call from a background thread.
        """
        if self._auth_mode not in ("password",):
            raise RuntimeError("login() requires user_id + password auth mode.")

        _LOGGER.debug("SolarOfThings: logging in as %s", self._user_id)

        import json as _json
        # The Siseli portal transmits the password as MD5(plaintext) lowercase hex —
        # the server rejects plaintext with error code 7.  This is a protocol
        # requirement of the upstream API, not a choice we can change.  The hash
        # is sent over HTTPS, so the transport layer provides confidentiality.
        # CodeQL alert suppressed: MD5 use here is non-cryptographic (protocol-mandated
        # pre-hashing by the upstream service), not used for storage or key derivation.
        password_md5 = hashlib.md5(self._password.encode("utf-8")).hexdigest()  # noqa: S324
        payload = {
            "account": self._user_id,
            "password": password_md5,
        }
        body_bytes = _json.dumps(payload, separators=(",", ":")).encode("utf-8")

        headers = _make_signed_headers(body_bytes)

        resp = requests.post(
            f"{API_AUTH_BASE_URL}{API_LOGIN}",
            data=body_bytes,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") not in (0, None, "0"):
            msg = data.get("message") or data.get("msg") or str(data)
            raise AuthenticationError(f"Login failed: {msg}")

        self._store_tokens(data.get("data") or data)

    def refresh_access_token(self) -> None:
        """Use the stored refresh token to obtain a new access token.

        Raises TokenExpiredError if the refresh token is also expired or invalid.
        """
        if not self._refresh_token:
            raise TokenExpiredError("No refresh token available.")

        _LOGGER.debug("SolarOfThings: refreshing access token")

        resp = requests.post(
            f"{API_AUTH_BASE_URL}{API_REFRESH_TOKEN_ENDPOINT}",
            json={"refreshToken": self._refresh_token},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "Origin": "https://solar.siseli.com",
                "Referer": "https://solar.siseli.com/",
            },
            timeout=30,
        )

        if resp.status_code in (401, 403):
            raise TokenExpiredError("Refresh token rejected by server (expired or invalid).")

        resp.raise_for_status()
        data = resp.json()

        if data.get("code") not in (0, None, "0"):
            raise TokenExpiredError(
                f"Refresh failed: code={data.get('code')} message={data.get('message')}"
            )

        self._store_tokens(data.get("data") or data)

    # ─── Internal token management ─────────────────────────────────────────────

    def _store_tokens(self, payload: dict[str, Any]) -> None:
        """Extract tokens from a login/refresh response payload and persist them."""
        access = (
            payload.get("accessToken")
            or payload.get("iotToken")
            or payload.get("token")
            or ""
        )
        refresh = payload.get("refreshToken") or ""
        access_exp = (
            payload.get("accessTokenWillExpiredAt")
            or payload.get("accessTokenExpiredAt")
            or ""
        )
        refresh_exp = (
            payload.get("refreshTokenWillExpiredAt")
            or payload.get("refreshTokenExpiredAt")
            or ""
        )

        if not access:
            raise AuthenticationError(
                f"Login/refresh response did not contain an access token. "
                f"Keys received: {list(payload.keys())}"
            )

        self._access_token = access
        self._refresh_token = refresh
        self._access_expires = _parse_expiry(access_exp)
        self._refresh_expires = _parse_expiry(refresh_exp)

        # Update session header immediately
        self._apply_token_headers()

        _LOGGER.debug(
            "SolarOfThings: token updated, expires=%s",
            self._access_expires.isoformat() if self._access_expires else "unknown",
        )

        # Notify the HA integration so it can persist the new token state
        if self._on_token_refreshed:
            try:
                self._on_token_refreshed(
                    self._access_token,
                    self._refresh_token,
                    self._access_expires.isoformat() if self._access_expires else "",
                    self._refresh_expires.isoformat() if self._refresh_expires else "",
                )
            except Exception as cb_err:  # pragma: no cover
                _LOGGER.warning("Token-refresh callback raised: %s", cb_err)

    def _token_needs_refresh(self) -> bool:
        """Return True if the access token is absent or about to expire."""
        if not self._access_token:
            return True
        if self._access_expires is None:
            # Unknown expiry: only refresh if we already have a refresh token
            return bool(self._refresh_token)
        lead = timedelta(seconds=TOKEN_REFRESH_LEAD_SECONDS)
        return datetime.now(timezone.utc) >= (self._access_expires - lead)

    def _ensure_token_valid(self) -> None:
        """Proactively refresh the access token if needed.

        Thread-safe: uses a lock so parallel coordinator updates don't
        trigger multiple simultaneous refresh calls.

        Raises TokenExpiredError when all refresh strategies are exhausted.
        """
        if not self._token_needs_refresh():
            return

        with self._refresh_lock:
            # Double-check inside the lock (another thread may have refreshed)
            if not self._token_needs_refresh():
                return

            _LOGGER.info("SolarOfThings: access token expiring; attempting refresh")

            # Strategy 1: use refresh token
            if self._refresh_token:
                try:
                    self.refresh_access_token()
                    return
                except TokenExpiredError:
                    _LOGGER.warning(
                        "SolarOfThings: refresh token expired/invalid; "
                        "attempting re-login"
                    )
                except Exception as err:
                    _LOGGER.error("SolarOfThings: token refresh request failed: %s", err)

            # Strategy 2: re-login with stored credentials
            if self._auth_mode == "password" and self._user_id and self._password:
                try:
                    self.login()
                    return
                except AuthenticationError as err:
                    raise TokenExpiredError(
                        f"Re-login failed (credentials rejected): {err}"
                    ) from err
                except Exception as err:
                    raise TokenExpiredError(
                        f"Re-login failed (network error): {err}"
                    ) from err

            # Strategy 3: nothing left — tell HA to trigger re-auth
            raise TokenExpiredError(
                "Access token expired and no refresh strategy succeeded. "
                "Please re-authenticate in Home Assistant."
            )

    # ─── Internal HTTP helper ──────────────────────────────────────────────────

    def _post(self, path: str, payload: dict[str, Any], *, timeout: int = 30) -> dict[str, Any]:
        """Perform a POST to a data endpoint, automatically refreshing the token on 401.

        On second 401 (after refresh) raises TokenExpiredError.
        Uses API_BASE_URL (solar.siseli.com) — not the auth base URL.
        """
        self._ensure_token_valid()

        resp = self.session.post(f"{API_BASE_URL}{path}", json=payload, timeout=timeout)

        if resp.status_code == 401:
            _LOGGER.warning("SolarOfThings: received 401; forcing token refresh")
            # Force an immediate refresh even if _token_needs_refresh() is False
            self._access_expires = None
            self._ensure_token_valid()
            resp = self.session.post(f"{API_BASE_URL}{path}", json=payload, timeout=timeout)

        resp.raise_for_status()
        return resp.json()

    # ─── Public properties (for persistence in HA config entry) ───────────────

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    @property
    def access_token_expires_iso(self) -> str:
        return self._access_expires.isoformat() if self._access_expires else ""

    @property
    def refresh_token_expires_iso(self) -> str:
        return self._refresh_expires.isoformat() if self._refresh_expires else ""

    # ─── Time helpers ──────────────────────────────────────────────────────────

    def _now(self) -> datetime:
        if ZoneInfo:
            try:
                return datetime.now(tz=ZoneInfo(self._time_zone))
            except Exception:
                return datetime.now()
        return datetime.now()

    def _format_time(self, dt: datetime) -> str:
        if ZoneInfo:
            try:
                dt = dt.astimezone(ZoneInfo(self._time_zone))
            except Exception:
                pass
        return dt.replace(microsecond=0).isoformat()

    # ─── Station → device listing ──────────────────────────────────────────────

    def list_devices(self, station_id: str, page_size: int = 50) -> list[dict[str, Any]]:
        """Return all devices under a station (paginated)."""
        devices: list[dict[str, Any]] = []
        page = 1
        total: int | None = None

        while True:
            data = self._post(
                API_DEVICE_LIST,
                {"page": page, "count": page_size, "stationId": station_id},
            )

            if data.get("code") not in (0, None):
                raise RuntimeError(
                    f"Device list error code={data.get('code')} "
                    f"message={data.get('message')}"
                )

            d = data.get("data") or {}
            total = d.get("total", total)
            batch = d.get("list") or []
            if not isinstance(batch, list):
                batch = []

            devices.extend(batch)

            if total is None:
                if len(batch) < page_size:
                    break
            else:
                if len(devices) >= int(total):
                    break
            if not batch:
                break
            page += 1

        return devices

    # ─── Time-series (per device) ──────────────────────────────────────────────

    def fetch_latest_data(self, device_id: str) -> dict[str, Any]:
        """Fetch the latest readings for a device (last 1 hour)."""
        end_time = self._now()
        start_time = end_time - timedelta(hours=1)

        # Original keys + alternate attribute keys used by PI30 / VMIII
        # (Voltronic-style) inverters. Whichever the model exposes is used.
        # Superset of the names seen across models — the endpoint simply omits
        # the ones this device does not record.  Anything missing here is filled
        # from the state snapshot afterwards (see merge_state_fallbacks).
        keys = [
            "pvInputPower", "generationPower", "PV1ChargingPower", "PV2ChargingPower",
            "acOutputActivePower",
            "batteryDischargeCurrent", "batteryChargingCurrent", "batteryVoltage",
            "batterySOC", "batteryCapacity", "batteryPercentage",
            "feedInPower", "gridFeedInPower", "feedInActivePower", "onGridPower",
        ]

        data = self._post(
            API_TIME_SERIES,
            {
                "deviceId": device_id,
                "count": 2000,
                "page": 1,
                "fromTime": self._format_time(start_time),
                "toTime": self._format_time(end_time),
                "orderByTimeAsc": True,
                "keys": keys,
            },
        )

        if data.get("code") not in (0, None):
            raise RuntimeError(
                f"Timeseries error code={data.get('code')} "
                f"message={data.get('message')}"
            )

        payload_data = (data.get("data") or {}).get("payload") or {}
        fields = payload_data.get("fields") or {}

        latest_values: dict[str, Any] = {}
        for key, arr in fields.items():
            if isinstance(arr, list) and arr:
                latest_values[key] = arr[-1]

        # ── Model-dependent key resolution ──────────────────────────────────
        # PV input power: pvInputPower, else generationPower (kW→W),
        # else PV1+PV2 charging power (already W).
        if latest_values.get("pvInputPower") in (None, ""):
            if latest_values.get("generationPower") not in (None, ""):
                try:
                    latest_values["pvInputPower"] = float(latest_values["generationPower"]) * 1000.0
                except Exception:
                    pass
            else:
                try:
                    pv1 = float(latest_values.get("PV1ChargingPower") or 0)
                    pv2 = float(latest_values.get("PV2ChargingPower") or 0)
                    if pv1 or pv2:
                        latest_values["pvInputPower"] = pv1 + pv2
                except Exception:
                    pass

        # Battery SOC: batterySOC, else batteryCapacity, else batteryPercentage.
        if latest_values.get("batterySOC") in (None, ""):
            soc = latest_values.get("batteryCapacity")
            if soc in (None, ""):
                soc = latest_values.get("batteryPercentage")
            if soc not in (None, ""):
                latest_values["batterySOC"] = soc

        # Remaining aliases: the history endpoint returns whichever attribute
        # name the model records, so normalise the known alternates onto our
        # canonical keys.  Values from this endpoint share the canonical key's
        # unit, so no scaling is applied here (the kW cases above are explicit).
        for canonical, (candidates, _kind) in TELEMETRY_STATE_FALLBACKS.items():
            if latest_values.get(canonical) not in (None, ""):
                continue
            for alias in candidates:
                if alias == canonical:
                    continue
                value = latest_values.get(alias)
                if value not in (None, ""):
                    latest_values[canonical] = value
                    break

        # Unit normalisation: acOutputActivePower is kW in API → W
        if "acOutputActivePower" in latest_values:
            try:
                latest_values["acOutputActivePower"] = (
                    float(latest_values["acOutputActivePower"]) * 1000.0
                )
            except Exception:
                pass

        compute_derived_values(latest_values)

        return latest_values

    # ─── Monthly summary (station) ─────────────────────────────────────────────

    def fetch_monthly_summary(self, station_id: str) -> dict[str, Any]:
        """Fetch monthly PV summary for the current month."""
        now = self._now()
        year = now.year
        month_key = f"{year}-{str(now.month).zfill(2)}"

        self._ensure_token_valid()
        resp = self.session.post(
            f"{API_BASE_URL}{API_MONTHLY_SUMMARY}"
            f"?stationId={station_id}&summaryCategoryKey=pvInverterElectricityQuantityClass",
            json={"time": str(year)},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") not in (0, None):
            raise RuntimeError(
                f"Monthly summary error code={data.get('code')} "
                f"message={data.get('message')}"
            )

        props = (((data.get("data") or {}).get("properties")) or
                 (data.get("data") or {}).get("list") or
                 [])

        result: dict[str, Any] = {}
        for item in props if isinstance(props, list) else []:
            k = item.get("key") or item.get("name")
            v = item.get("value")
            if k and v is not None:
                result[k] = v

        # Extract monthly totals (fallback: look for known keys)
        monthly: dict[str, Any] = {}
        pv_total = result.get(month_key) or result.get("pvTotal") or result.get("pv") or 0
        monthly["monthly_pv_generated"] = float(pv_total or 0)

        grid_import = result.get("gridImport") or result.get("buy") or 0
        monthly["monthly_grid_import"] = float(grid_import or 0)

        total_consumption = result.get("totalConsumption") or result.get("load") or 0
        monthly["monthly_total_consumption"] = float(total_consumption or 0)

        if monthly["monthly_total_consumption"] > 0:
            monthly["monthly_solar_percentage"] = round(
                100.0 * monthly["monthly_pv_generated"] / monthly["monthly_total_consumption"], 1
            )
        else:
            monthly["monthly_solar_percentage"] = 0.0

        return monthly

    # ─── Device settings ───────────────────────────────────────────────────────
    # The remote config endpoints require only a plain IOT-Token header (which the
    # session already carries) and pass deviceId as a URL query parameter rather
    # than in the JSON body.

    def _write_setting(self, device_id: str, key: str, value: Any) -> None:
        """Write a single device setting key=value via the remote config write API.

        The body field is ``id``, not ``deviceId`` — captured from the portal's
        own control panel.  Releases before 2.6.0 sent ``deviceId`` here, which
        the endpoint accepts with a success code while changing nothing.
        """
        self._ensure_token_valid()
        url = f"{API_BASE_URL}{API_SETTINGS_SET}?deviceId={device_id}"
        payload = {"id": device_id, "key": key, "value": value}
        _LOGGER.debug("SolarOfThings: writing %s=%r to %s", key, value, device_id)
        resp = self.session.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") not in (0, None):
            raise RuntimeError(
                f"Settings write error code={data.get('code')} "
                f"message={data.get('message')} (key={key})"
            )

    def get_device_settings(self, device_id: str) -> dict[str, Any]:
        """Fetch the cached device settings from the remote config API.

        Returns a flat dict of {settingKey: settingObject} where each value
        contains at least 'key', 'value', and 'valueDisplay' fields.
        The endpoint accepts a plain IOT-Token header (no IOT-Open-Sign).
        """
        self._ensure_token_valid()
        url = f"{API_BASE_URL}{API_SETTINGS_GET}?deviceId={device_id}"
        resp = self.session.post(url, json={}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") not in (0, None):
            raise RuntimeError(
                f"Settings fetch error code={data.get('code')} "
                f"message={data.get('message')}"
            )
        return data.get("data") or {}

    # Alias used by the coordinator in __init__.py
    fetch_settings = get_device_settings

    def update_device_settings(self, device_id: str, settings: dict[str, Any]) -> None:
        """Write multiple settings (one API call per key)."""
        for key, value in settings.items():
            self._write_setting(device_id, key, value)

    # ─── Control helpers (called by select.py / switch.py / number.py) ────────
    # Writes go to POST /apis/remote/device/config/write with the *setting* key
    # names (settingDevice…), which differ from the state-snapshot names the
    # entities read back from.  Enum values are sent as strings, matching what
    # the portal's own control panel sends.

    # Option-string → integer maps, inverted from the single definition in
    # const.py so the write path and the select read-back cannot drift apart.
    _OUTPUT_MODE_REVERSE: dict[int, str] = OUTPUT_PRIORITY_BY_VALUE
    _OUTPUT_MODE_MAP: dict[str, int] = {v: k for k, v in OUTPUT_PRIORITY_BY_VALUE.items()}

    _CHARGER_PRIORITY_REVERSE: dict[int, str] = CHARGER_PRIORITY_BY_VALUE
    _CHARGER_PRIORITY_MAP: dict[str, int] = {v: k for k, v in CHARGER_PRIORITY_BY_VALUE.items()}

    def _write_control(self, device_id: str, control: str, value: Any) -> None:
        """Write a logical control by its name in ``SETTING_KEY_CANDIDATES``.

        The first candidate is the name this firmware family uses; the rest are
        older names kept for models that still answer to them.
        """
        candidates = SETTING_KEY_CANDIDATES.get(control)
        if not candidates:
            raise ValueError(f"Unknown control {control!r}")
        self._write_setting(device_id, candidates[0], value)

    def set_operating_mode(self, device_id: str, mode: str) -> None:
        """Set Output Source Priority.  mode is one of _OUTPUT_MODE_MAP keys."""
        value = self._OUTPUT_MODE_MAP.get(mode)
        if value is None:
            raise ValueError(f"Unknown operating mode: {mode!r}. "
                             f"Valid options: {list(self._OUTPUT_MODE_MAP)!r}")
        self._write_control(device_id, "outputSourcePriority", str(value))

    def set_battery_priority(self, device_id: str, mode: str) -> None:
        """Set Charger Source Priority.  mode is one of _CHARGER_PRIORITY_MAP keys."""
        value = self._CHARGER_PRIORITY_MAP.get(mode)
        if value is None:
            raise ValueError(f"Unknown battery priority: {mode!r}. "
                             f"Valid options: {list(self._CHARGER_PRIORITY_MAP)!r}")
        self._write_control(device_id, "chargerSourcePriority", str(value))

    def set_boolean_control(self, device_id: str, control: str, enabled: bool) -> None:
        """Toggle one of the BOOLEAN_CONTROLS entries."""
        spec = BOOLEAN_CONTROLS.get(control)
        if spec is None:
            raise ValueError(f"Unknown boolean control {control!r}")
        self._write_control(device_id, control, spec["on_value"] if enabled else spec["off_value"])

    def set_number_control(self, device_id: str, control: str, value: float) -> None:
        """Write one of the NUMBER_CONTROLS entries.

        Numeric settings are sent as numbers (the portal sends 120, 29.2 …);
        anything else goes out as a string.
        """
        spec = NUMBER_CONTROLS.get(control)
        if spec is None:
            raise ValueError(f"Unknown number control {control!r}")
        if spec.get("numeric", True):
            payload_value: Any = int(value) if float(value).is_integer() else float(value)
        else:
            payload_value = str(value)
        self._write_control(device_id, control, payload_value)

    def set_grid_feed_in(self, device_id: str, enabled: bool) -> None:
        """Enable or disable feeding solar back to the grid."""
        self.set_boolean_control(device_id, "gridFeedIn", enabled)

    def set_backup_mode(self, device_id: str, enabled: bool) -> None:
        """Set Output Source Priority to SBU (backup/off-grid priority) when True,
        or SUB (solar-first, grid-supplemented) when False."""
        self.set_operating_mode(
            device_id,
            OUTPUT_PRIORITY_BY_VALUE[2] if enabled else OUTPUT_PRIORITY_BY_VALUE[1],
        )

    def request_config_read(self, device_id: str) -> str | None:
        """Ask the device to report its remote-config values (portal "Batch Read").

        Returns the batch id, which ``fetch_config_read_details`` can poll.  The
        round-trip goes out to the inverter, so results appear seconds later —
        the integration does not depend on it, since the live state snapshot
        already carries every current value.
        """
        self._ensure_token_valid()
        url = f"{API_BASE_URL}{API_SETTINGS_READ}?deviceId={device_id}"
        resp = self.session.post(url, json={}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") not in (0, None):
            raise RuntimeError(
                f"Config read request failed code={data.get('code')} "
                f"message={data.get('message')}"
            )
        return (data.get("data") or {}).get("id")

    def fetch_config_read_details(self, batch_read_id: str) -> dict[str, Any]:
        """Return the result of a ``request_config_read`` batch."""
        self._ensure_token_valid()
        url = f"{API_BASE_URL}{API_SETTINGS_READ_DETAILS}?batchReadId={batch_read_id}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") not in (0, None):
            raise RuntimeError(
                f"Config read details failed code={data.get('code')} "
                f"message={data.get('message')}"
            )
        return data.get("data") or {}

    def test_connection(self, station_id: str) -> bool:
        """Return True if we can reach the device-list endpoint successfully."""
        try:
            devices = self.list_devices(station_id, page_size=1)
            return True
        except Exception as err:
            _LOGGER.error("SolarOfThings: connection test failed: %s", err)
            return False

    def fetch_state(self, device_id: str) -> dict[str, Any]:
            """Fetch the full latest device state (all attribute fields + alarms)."""
            from .const import API_STATE_LATEST
            self._ensure_token_valid()
            url = f"{API_BASE_URL}{API_STATE_LATEST}?deviceId={device_id}&dataSource=1"
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 401:
                self._access_expires = None
                self._ensure_token_valid()
                resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") not in (0, None):
                raise RuntimeError(
                    f"State fetch error code={data.get('code')} message={data.get('message')}"
                )
            return data.get("data") or {}