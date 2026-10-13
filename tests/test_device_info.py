"""Device-registry linkage (issues #34, #37).

HA 2026.8 deprecated the ``via_device`` tuple in DeviceInfo; from 2026.10 it
logs "calls device_registry.async_get_or_create with a deprecated via_device
parameter" and the key stops working in 2027.8.  The inverter device must be
linked to the station hub through ``via_device_id`` instead.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_of_things import device as device_helpers
from custom_components.solar_of_things.const import DOMAIN, SENSOR_DEFINITIONS
from custom_components.solar_of_things.sensor import SolarOfThingsDeviceSensor

pytestmark = pytest.mark.skipif(
    not device_helpers._SUPPORTS_VIA_DEVICE_ID,
    reason="this HA release predates via_device_id",
)


@pytest.mark.asyncio
async def test_inverter_links_to_hub_via_device_id(hass, caplog) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    hub = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "ST1")},
        name="Solar Station ST1",
    )

    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), config_entry=entry, name="test"
    )
    coordinator.data = {"device_meta": {"model": "X"}, "time_series": {}}
    sensor = SolarOfThingsDeviceSensor(
        coordinator, "ST1", "DEV1", "Inverter", "pvInputPower",
        SENSOR_DEFINITIONS["pvInputPower"],
    )
    platform = EntityPlatform(
        hass=hass, logger=logging.getLogger(__name__), domain="sensor",
        platform_name=DOMAIN, platform=None, scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    platform.config_entry = entry

    with caplog.at_level(logging.WARNING):
        await platform.async_add_entities([sensor])

    inverter = dev_reg.async_get_device_by_identifier((DOMAIN, "DEV1"), entry.entry_id)
    assert inverter is not None
    assert inverter.via_device_id == hub.id
    assert "deprecated `via_device`" not in caplog.text
