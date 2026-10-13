"""Tests for the Lifeblood sensors."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lifeblood.api import AJAX_URL
from custom_components.lifeblood.const import (
    ALL_BLOOD_TYPES,
    CONF_BLOOD_TYPES,
    CONF_REGION,
    DOMAIN,
    SOURCE_URL,
)

from .conftest import load_fixture, load_json_fixture


async def _setup(hass: HomeAssistant, region: str = "national") -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=region,
        data={CONF_REGION: region, CONF_BLOOD_TYPES: ALL_BLOOD_TYPES},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_national_sensors(hass: HomeAssistant, mock_lifeblood) -> None:
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    state = hass.states.get("sensor.lifeblood_all_australia_o_positive")
    assert state.state == "critical"
    assert state.attributes["device_class"] == "enum"
    assert state.attributes["options"][0] == "critical"
    assert state.attributes["label"] == "Critical"
    assert state.attributes["appeal"] is True

    assert hass.states.get("sensor.lifeblood_all_australia_ab_positive").state == "need_more"
    assert hass.states.get("sensor.lifeblood_all_australia_ab_negative").state == "good"

    plasma = hass.states.get("sensor.lifeblood_all_australia_plasma")
    assert plasma.state == "ok"
    assert plasma.attributes["options"] == ["need_more", "ok", "good"]
    assert "appeal" not in plasma.attributes

    shortfall = hass.states.get("sensor.lifeblood_all_australia_plasma_shortfall")
    assert shortfall.state == "1.68"
    assert shortfall.attributes["percent_of_target"] == 98.32
    assert (
        hass.states.get("sensor.lifeblood_all_australia_last_updated").state
        == "2026-10-13T19:00:00+00:00"
    )


async def test_regional_sensors(hass: HomeAssistant, mock_lifeblood) -> None:
    await _setup(hass, "vic")
    assert hass.states.get("sensor.lifeblood_victoria_ab_positive").state == "low"
    # Above target floors at 0 rather than going negative.
    shortfall = hass.states.get("sensor.lifeblood_victoria_plasma_shortfall")
    assert shortfall.state == "0.0"
    assert shortfall.attributes["percent_of_target"] == 100.11


async def test_setup_retries_when_site_down(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(SOURCE_URL, status=503)
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_sensors_unavailable_after_failed_update(
    hass: HomeAssistant, mock_lifeblood
) -> None:
    entry = await _setup(hass)
    mock_lifeblood.clear_requests()
    mock_lifeblood.get(SOURCE_URL, status=503)

    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.lifeblood_all_australia_o_positive").state
        == STATE_UNAVAILABLE
    )


async def test_unload(hass: HomeAssistant, mock_lifeblood) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_migrates_plasma_supply_to_plasma_shortfall(
    hass: HomeAssistant, mock_lifeblood
) -> None:
    """A 0.1.0 "Plasma supply" entity is renamed in place, not duplicated."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="nsw",
        data={CONF_REGION: "nsw", CONF_BLOOD_TYPES: ["plasma"]},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "nsw_plasma_supply",
        config_entry=entry,
        suggested_object_id="lifeblood_nsw_plasma_supply",
    )
    assert old.entity_id == "sensor.lifeblood_nsw_plasma_supply"
    # NSW comes back from the AJAX call, which the fixture serves as VIC.
    mock_lifeblood.clear_requests()
    mock_lifeblood.get(SOURCE_URL, text=load_fixture("page_national.html"))
    mock_lifeblood.post(AJAX_URL, json=load_json_fixture("ajax_nsw.json"))

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    migrated = registry.async_get("sensor.lifeblood_nsw_plasma_shortfall")
    assert migrated is not None
    assert migrated.id == old.id
    assert migrated.unique_id == "nsw_plasma_shortfall"
    assert registry.async_get("sensor.lifeblood_nsw_plasma_supply") is None
    assert hass.states.get("sensor.lifeblood_nsw_plasma_shortfall").state == "3.72"


async def test_migration_keeps_custom_entity_id(hass: HomeAssistant, mock_lifeblood) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="national",
        data={CONF_REGION: "national", CONF_BLOOD_TYPES: ["plasma"]},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "national_plasma_supply",
        config_entry=entry,
        suggested_object_id="my_plasma",
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get("sensor.my_plasma").unique_id == "national_plasma_shortfall"
    assert hass.states.get("sensor.my_plasma").state == "1.68"
