"""Tests for the "blood type in demand" automation blueprint."""

from __future__ import annotations

from pathlib import Path

import pytest
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.core import Event, HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml

from custom_components.lifeblood.const import PLASMA_LEVELS, RED_CELL_LEVELS

BLUEPRINT = (
    Path(__file__).parent.parent
    / "blueprints/automation/lifeblood/blood_type_in_demand.yaml"
)
SENSOR = "sensor.lifeblood_nsw_a_positive"
PLASMA_SENSOR = "sensor.lifeblood_nsw_plasma"
TEST_EVENT = "lifeblood_blueprint_test"


def test_blueprint_is_valid() -> None:
    blueprint = Blueprint(
        load_yaml(BLUEPRINT),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    assert set(blueprint.inputs) == {"blood_type", "levels", "notify_device"}


def test_level_choices_match_integration() -> None:
    """Every level offered is one the sensors can actually report."""
    raw = load_yaml(BLUEPRINT)
    offered = [o["value"] for o in raw["blueprint"]["input"]["levels"]["selector"]["select"]["options"]]
    assert set(offered) <= set(RED_CELL_LEVELS) | set(PLASMA_LEVELS)
    assert set(raw["blueprint"]["input"]["levels"]["default"]) <= set(offered)


def test_notify_action_uses_mobile_app_fields() -> None:
    """The phone step only uses fields the mobile app's notify action accepts.

    Mirrors ACTION_SCHEMA in homeassistant/components/mobile_app/device_action.py
    (type "notify", required message, optional title and data - all rendered
    as templates). Importing that module here would drag in cloud, alexa and
    camera dependencies the test environment doesn't have.
    """
    action = load_yaml(BLUEPRINT)["actions"][-1]
    assert action["domain"] == "mobile_app"
    assert action["type"] == "notify"
    assert "message" in action
    assert set(action) <= {"device_id", "domain", "type", "message", "title", "data"}


@pytest.fixture
async def events(hass: HomeAssistant, tmp_path) -> list[Event]:
    """Install a copy of the blueprint whose phone step fires an event instead."""
    text = BLUEPRINT.read_text()
    start = text.index("  - device_id: !input notify_device")
    text = text[:start] + (
        f"  - event: {TEST_EVENT}\n"
        "    event_data:\n"
        '      title: "{{ trigger.to_state.name }} is {{ label }}"\n'
    )
    dest = Path(hass.config.path("blueprints/automation/lifeblood"))
    dest.mkdir(parents=True, exist_ok=True)
    (dest / BLUEPRINT.name).write_text(text)

    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "use_blueprint": {
                        "path": f"lifeblood/{BLUEPRINT.name}",
                        "input": {"blood_type": SENSOR, "notify_device": "abc123"},
                    }
                },
                {
                    "use_blueprint": {
                        "path": f"lifeblood/{BLUEPRINT.name}",
                        "input": {
                            "blood_type": PLASMA_SENSOR,
                            "notify_device": "abc123",
                            "levels": ["urgent", "need_more"],
                        },
                    }
                },
            ]
        },
    )
    fired: list[Event] = []
    hass.bus.async_listen(TEST_EVENT, fired.append)
    return fired


async def _set(hass: HomeAssistant, entity_id: str, state: str, label: str | None = None) -> None:
    options = PLASMA_LEVELS if entity_id == PLASMA_SENSOR else RED_CELL_LEVELS
    attrs = {"options": options, "friendly_name": "NSW A positive" if entity_id == SENSOR else "NSW Plasma"}
    if label:
        attrs["label"] = label
    hass.states.async_set(entity_id, state, attrs)
    await hass.async_block_till_done()


async def test_notifies_only_when_worse(hass: HomeAssistant, events: list[Event]) -> None:
    await _set(hass, SENSOR, "good", "Good")
    assert events == []

    await _set(hass, SENSOR, "very_low", "Very low")
    assert [e.data["title"] for e in events] == ["NSW A positive is Very low"]

    # Worse again: notify.
    await _set(hass, SENSOR, "critical", "Critical")
    assert len(events) == 2
    assert events[-1].data["title"] == "NSW A positive is Critical"

    # Improving into a watched level: quiet.
    await _set(hass, SENSOR, "very_low", "Very low")
    assert len(events) == 2

    # Worse, but to a level not ticked (Low isn't in the defaults): quiet.
    await _set(hass, SENSOR, "ok", "Ok")
    await _set(hass, SENSOR, "low", "Low")
    assert len(events) == 2


async def test_ignores_restarts_and_outages(hass: HomeAssistant, events: list[Event]) -> None:
    # The sensor appearing for the first time (integration just added) at
    # Critical is not a change, so it mustn't notify.
    await _set(hass, SENSOR, "critical", "Critical")
    assert events == []

    await _set(hass, SENSOR, "unavailable")
    await _set(hass, SENSOR, "critical", "Critical")
    assert events == []


async def test_plasma_urgent_and_custom_levels(hass: HomeAssistant, events: list[Event]) -> None:
    await _set(hass, PLASMA_SENSOR, "good", "Good")
    await _set(hass, PLASMA_SENSOR, "need_more", "Need more")
    await _set(hass, PLASMA_SENSOR, "urgent", "Urgent")
    assert [e.data["title"] for e in events] == [
        "NSW Plasma is Need more",
        "NSW Plasma is Urgent",
    ]


async def test_label_falls_back_to_state(hass: HomeAssistant, events: list[Event]) -> None:
    await _set(hass, SENSOR, "good")
    await _set(hass, SENSOR, "very_low")
    assert events[-1].data["title"] == "NSW A positive is Very low"
