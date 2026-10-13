"""Tests for the Lifeblood config and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lifeblood.const import (
    ALL_BLOOD_TYPES,
    CONF_BLOOD_TYPES,
    CONF_REGION,
    DOMAIN,
    SOURCE_URL,
)


async def test_user_flow(hass: HomeAssistant, mock_lifeblood) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_REGION: "vic", CONF_BLOOD_TYPES: ["o_negative", "plasma"]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Lifeblood Victoria"
    assert result["data"] == {
        CONF_REGION: "vic",
        CONF_BLOOD_TYPES: ["o_negative", "plasma"],
    }
    assert result["result"].unique_id == "vic"
    await hass.async_block_till_done()

    assert hass.states.get("sensor.lifeblood_victoria_o_negative").state == "critical"
    assert hass.states.get("sensor.lifeblood_victoria_plasma").state == "ok"
    assert hass.states.get("sensor.lifeblood_victoria_o_positive") is None


async def test_user_flow_no_blood_types(hass: HomeAssistant, mock_lifeblood) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "vic", CONF_BLOOD_TYPES: []}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_BLOOD_TYPES: "no_blood_types"}


async def test_user_flow_cannot_connect(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(SOURCE_URL, status=500)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "national", CONF_BLOOD_TYPES: ALL_BLOOD_TYPES}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_cannot_parse(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(SOURCE_URL, text="<html></html>")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "national", CONF_BLOOD_TYPES: ALL_BLOOD_TYPES}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_parse"}


async def test_user_flow_already_configured(hass: HomeAssistant, mock_lifeblood) -> None:
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="vic",
        data={CONF_REGION: "vic", CONF_BLOOD_TYPES: ALL_BLOOD_TYPES},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION: "vic", CONF_BLOOD_TYPES: ALL_BLOOD_TYPES}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_removes_deselected(hass: HomeAssistant, mock_lifeblood) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="national",
        data={CONF_REGION: "national", CONF_BLOOD_TYPES: ALL_BLOOD_TYPES},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert registry.async_get("sensor.lifeblood_all_australia_plasma_shortfall")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_BLOOD_TYPES: ["a_positive"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert hass.states.get("sensor.lifeblood_all_australia_a_positive").state == "critical"
    # Gone from the registry, not just left behind as unavailable.
    assert registry.async_get("sensor.lifeblood_all_australia_o_positive") is None
    assert registry.async_get("sensor.lifeblood_all_australia_plasma") is None
    assert registry.async_get("sensor.lifeblood_all_australia_plasma_shortfall") is None
    state = hass.states.get("sensor.lifeblood_all_australia_o_positive")
    assert state is None or state.state == STATE_UNAVAILABLE
    # Not a blood type, so it stays.
    assert registry.async_get("sensor.lifeblood_all_australia_last_updated")
