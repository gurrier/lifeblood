"""Tests for the Lifeblood sensors."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lifeblood.const import (
    ALL_BLOOD_TYPES,
    CONF_BLOOD_TYPES,
    CONF_REGION,
    DOMAIN,
    SOURCE_URL,
)


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

    assert hass.states.get("sensor.lifeblood_all_australia_plasma_supply").state == "98.32"
    assert (
        hass.states.get("sensor.lifeblood_all_australia_last_updated").state
        == "2026-10-13T19:00:00+00:00"
    )


async def test_regional_sensors(hass: HomeAssistant, mock_lifeblood) -> None:
    await _setup(hass, "vic")
    assert hass.states.get("sensor.lifeblood_victoria_ab_positive").state == "low"
    assert hass.states.get("sensor.lifeblood_victoria_plasma_supply").state == "100.11"


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
