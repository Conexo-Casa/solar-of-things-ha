"""Tests for config-field normalisation.

Station and device IDs are copy-pasted out of the browser's Network tab, so they
routinely arrive with a stray leading or trailing space.  The upstream API
treats " 4235…" as a different, invalid value and the user only sees a generic
"cannot connect".
"""
from __future__ import annotations

import pytest

from custom_components.solar_of_things.const import WHITESPACE_SENSITIVE_FIELDS
from custom_components.solar_of_things.util import normalise_config_fields


def test_trims_pasted_station_and_device_ids() -> None:
    cleaned = normalise_config_fields(
        {"station_id": "486217907720650752 ", "device_id": " 486217907745816576"}
    )
    assert cleaned["station_id"] == "486217907720650752"
    assert cleaned["device_id"] == "486217907745816576"


def test_password_is_never_trimmed() -> None:
    """Whitespace in a password may be intentional, so it must survive."""
    cleaned = normalise_config_fields({"password": "  hunter2  ", "user_id": "  bob  "})
    assert cleaned["password"] == "  hunter2  "
    assert cleaned["user_id"] == "bob"


def test_password_is_excluded_from_the_field_list() -> None:
    assert "password" not in WHITESPACE_SENSITIVE_FIELDS


def test_trims_a_pasted_iot_token() -> None:
    """Tokens are copied out of DevTools and often carry a newline or tab."""
    cleaned = normalise_config_fields({"iot_token": "\n eyJhbGciOi.token.value \t"})
    assert cleaned["iot_token"] == "eyJhbGciOi.token.value"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("access_token_expires", "2026-01-01T00:00:00+00:00"),
        ("refresh_token", None),
        ("some_number", 5),
    ],
)
def test_unlisted_and_non_string_values_pass_through(key, value) -> None:
    assert normalise_config_fields({key: value})[key] == value


def test_returns_a_copy_without_mutating_the_input() -> None:
    """entry.data is a read-only mapping in HA; never write through it."""
    source = {"station_id": " 123 "}
    cleaned = normalise_config_fields(source)

    assert source["station_id"] == " 123 "
    assert cleaned["station_id"] == "123"
    assert cleaned is not source


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({}, {}),
        ({"unrelated": "x"}, {"unrelated": "x"}),
        ({"station_id": "   "}, {"station_id": ""}),
    ],
)
def test_edge_cases(payload, expected) -> None:
    assert normalise_config_fields(payload) == expected
