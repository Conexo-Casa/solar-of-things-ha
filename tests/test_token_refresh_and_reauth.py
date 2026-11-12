"""Tests for signed token refresh, code=8 retry, and transient error handling."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import requests

from custom_components.solar_of_things.api import (
    AuthenticationError,
    SolarOfThingsAPI,
    TokenExpiredError,
)


class _DummyResp:
    def __init__(self, body: dict, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._body


def test_refresh_access_token_sends_signed_headers_and_both_tokens() -> None:
    """/apis/login/refresh/access/token requires IOT-Open-* signing and both
    accessToken + refreshToken in the JSON body (otherwise fails with code=36
    or code=20101)."""
    api = SolarOfThingsAPI(
        user_id="test_user",
        password="test_password",
        iot_token="OLD_ACCESS",
        refresh_token="OLD_REFRESH",
    )

    captured: dict = {}

    def fake_post(url, *, data=None, headers=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        return _DummyResp(
            {
                "code": 0,
                "data": {
                    "accessToken": "NEW_ACCESS",
                    "refreshToken": "NEW_REFRESH",
                    "accessTokenWillExpiredAt": "2099-01-01T00:00:00Z",
                    "refreshTokenWillExpiredAt": "2099-02-01T00:00:00Z",
                },
            }
        )

    with patch("custom_components.solar_of_things.api.requests.post", side_effect=fake_post):
        api.refresh_access_token()

    assert api.access_token == "NEW_ACCESS"
    assert api.refresh_token == "NEW_REFRESH"
    assert json.loads(captured["data"].decode("utf-8")) == {
        "accessToken": "OLD_ACCESS",
        "refreshToken": "OLD_REFRESH",
    }
    for required_header in (
        "IOT-Open-AppID",
        "IOT-Open-Nonce",
        "IOT-Open-Body-Hash",
        "IOT-Open-Sign",
    ):
        assert required_header in captured["headers"]


def test_ensure_token_valid_does_not_raise_token_expired_on_network_error() -> None:
    """A transient DNS/timeout error during re-login must propagate as a
    network exception so the coordinator raises UpdateFailed and retries on
    the next poll instead of starting a persistent HA re-auth flow."""
    api = SolarOfThingsAPI(
        user_id="test_user",
        password="test_password",
    )
    api.login = lambda: (_ for _ in ()).throw(
        requests.ConnectionError("Failed to resolve 'solar.siseli.com'")
    )

    with pytest.raises(requests.ConnectionError):
        api._ensure_token_valid()


def test_ensure_token_valid_raises_token_expired_on_bad_credentials() -> None:
    """Actual credential rejection (AuthenticationError) must still raise
    TokenExpiredError so HA triggers the re-auth flow."""
    api = SolarOfThingsAPI(
        user_id="test_user",
        password="bad_password",
    )
    api.login = lambda: (_ for _ in ()).throw(AuthenticationError("bad password"))

    with pytest.raises(TokenExpiredError):
        api._ensure_token_valid()


def test_post_retries_on_code_8_token_error() -> None:
    """Siseli returns HTTP 200 with code=8 ('token error') when an IOT-Token
    is invalidated server-side; _post must refresh and retry transparently."""
    api = SolarOfThingsAPI(
        user_id="test_user",
        password="test_password",
        iot_token="STALE_TOKEN",
        refresh_token="VALID_REFRESH",
        access_token_expires="2099-01-01T00:00:00Z",
    )

    refreshed = {"count": 0}

    def fake_refresh():
        refreshed["count"] += 1
        api._access_token = "FRESH_TOKEN"

    api.refresh_access_token = fake_refresh

    responses = iter(
        [
            _DummyResp({"code": 8, "message": "token error", "data": None}),
            _DummyResp({"code": 0, "data": {"total": 0, "list": []}}),
        ]
    )
    api.session.post = lambda *a, **k: next(responses)

    result = api._post("/apis/device/list", {"page": 1, "count": 10})
    assert result["code"] == 0
    assert refreshed["count"] == 1
