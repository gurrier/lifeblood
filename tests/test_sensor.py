"""Tests for the Lifeblood sensors."""

from __future__ import annotations

import pytest
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


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_national_sensors(hass: HomeAssistant, mock_lifeblood) -> None:
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    state = hass.states.get("sensor.lifeblood_australia_o_positive")
    assert state.state == "critical"
    # No "Lifeblood" prefix eating the space on dashboard buttons.
    assert state.attributes["friendly_name"] == "Australia O positive"
    assert state.attributes["device_class"] == "enum"
    assert state.attributes["options"][0] == "critical"
    assert state.attributes["label"] == "Critical"
    assert "appeal" not in state.attributes

    assert hass.states.get("sensor.lifeblood_australia_ab_positive").state == "need_more"
    assert hass.states.get("sensor.lifeblood_australia_ab_negative").state == "good"

    plasma = hass.states.get("sensor.lifeblood_australia_plasma")
    assert plasma.state == "ok"
    assert plasma.attributes["options"] == [
        "critical", "urgent", "very_low", "low", "need_more", "ok", "good"
    ]

    shortfall = hass.states.get("sensor.lifeblood_australia_plasma_shortfall")
    assert shortfall.state == "1.68"
    assert shortfall.attributes["percent_of_target"] == 98.32
    assert (
        hass.states.get("sensor.lifeblood_australia_last_updated").state
        == "2026-10-13T19:00:00+00:00"
    )


async def test_plasma_urgent_appeal(hass: HomeAssistant, aioclient_mock) -> None:
    """The 23 Oct 2026 "Urgent" plasma appeal shows as urgent, not unknown."""
    aioclient_mock.get(SOURCE_URL, text=load_fixture("page_national_plasma_urgent.html"))
    await _setup(hass)
    plasma = hass.states.get("sensor.lifeblood_australia_plasma")
    assert plasma.state == "urgent"
    assert plasma.attributes["label"] == "Urgent"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_regional_sensors(hass: HomeAssistant, mock_lifeblood) -> None:
    await _setup(hass, "vic")
    state = hass.states.get("sensor.lifeblood_vic_ab_positive")
    assert state.state == "low"
    assert state.attributes["friendly_name"] == "VIC AB positive"
    # Above target floors at 0 rather than going negative.
    shortfall = hass.states.get("sensor.lifeblood_vic_plasma_shortfall")
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
        hass.states.get("sensor.lifeblood_australia_o_positive").state
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


async def test_existing_entity_ids_kept_after_device_rename(
    hass: HomeAssistant, mock_lifeblood
) -> None:
    """Entities registered under the old "Lifeblood NSW" device keep their ids."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="national",
        data={CONF_REGION: "national", CONF_BLOOD_TYPES: ["a_positive"]},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "national_a_positive",
        config_entry=entry,
        suggested_object_id="lifeblood_national_a_positive",
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.lifeblood_national_a_positive")
    assert state.state == "critical"
    assert state.attributes["friendly_name"] == "Australia A positive"
    assert hass.states.get("sensor.lifeblood_australia_a_positive") is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_shortfall_and_last_updated_unavailable_without_values(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """No percent class and no Updated line -> unavailable, not 'unknown'."""
    page = load_fixture("page_national.html")
    page = page.replace("plasma-block National 98.32%", "plasma-block National")
    start = page.index('<div class="last-updated">')
    page = page[:start] + page[page.index("</div>", start) + len("</div>"):]
    aioclient_mock.get(SOURCE_URL, text=page)

    await _setup(hass)
    assert hass.states.get("sensor.lifeblood_australia_plasma").state == "ok"
    assert hass.states.get("sensor.lifeblood_australia_plasma_shortfall").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.lifeblood_australia_last_updated").state == STATE_UNAVAILABLE


async def test_migration_removes_stale_entity_when_new_exists(
    hass: HomeAssistant, mock_lifeblood
) -> None:
    """Both plasma_supply and plasma_shortfall registered -> old one dropped, setup still loads."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="national",
        data={CONF_REGION: "national", CONF_BLOOD_TYPES: ["plasma"]},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create("sensor", DOMAIN, "national_plasma_supply", config_entry=entry)
    new = registry.async_get_or_create("sensor", DOMAIN, "national_plasma_shortfall", config_entry=entry)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert registry.async_get_entity_id("sensor", DOMAIN, "national_plasma_supply") is None
    assert registry.async_get(new.entity_id).unique_id == "national_plasma_shortfall"
    assert hass.states.get(new.entity_id).state == "1.68"


async def test_plasma_shortfall_disabled_by_default(hass: HomeAssistant, mock_lifeblood) -> None:
    """New installs get the shortfall sensor registered but disabled."""
    await _setup(hass)
    entry = er.async_get(hass).async_get("sensor.lifeblood_australia_plasma_shortfall")
    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get("sensor.lifeblood_australia_plasma_shortfall") is None
    # The level sensor is unaffected.
    assert hass.states.get("sensor.lifeblood_australia_plasma").state == "ok"
