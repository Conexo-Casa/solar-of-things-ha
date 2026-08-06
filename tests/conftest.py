"""Test configuration for Solar of Things integration.

Home Assistant is an optional test dependency: the pure-logic tests
(``test_value_resolution.py``) run without it, so the HA imports are guarded
and the fixtures that need it skip instead of breaking collection for the
whole directory.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _component import load  # noqa: E402 — needs the path insertion above

try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    HA_AVAILABLE = True
except ImportError:  # pragma: no cover — depends on the environment
    MockConfigEntry = None
    HA_AVAILABLE = False

# Loaded without importing the package __init__, which pulls in Home Assistant.
DOMAIN = load("const").DOMAIN


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry."""
    if not HA_AVAILABLE:
        pytest.skip("Home Assistant test harness is not installed")
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "iot_token": "test_token_123",
            "station_id": "123456789012345678",
            "device_id": "876543210987654321",
        },
        entry_id="test_entry_id",
    )


@pytest.fixture
def mock_api_response():
    """Return mock API response data."""
    return {
        "data": {
            "pvInputPower": [{"ts": 1234567890, "value": 2500}],
            "acOutputActivePower": [{"ts": 1234567890, "value": 1800}],
            "batteryDischargeCurrent": [{"ts": 1234567890, "value": 0}],
            "batteryChargingCurrent": [{"ts": 1234567890, "value": 10}],
            "batteryVoltage": [{"ts": 1234567890, "value": 48}],
            "feedInPower": [{"ts": 1234567890, "value": 500}],
            "batterySOC": [{"ts": 1234567890, "value": 75}],
        }
    }
