"""Shared fixtures for Lifeblood tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest

from custom_components.lifeblood.api import AJAX_URL
from custom_components.lifeblood.const import SOURCE_URL

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def load_json_fixture(name: str):
    return json.loads(load_fixture(name))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/lifeblood."""
    return


@pytest.fixture
def entity_registry_enabled_by_default():
    """Create every entity enabled, including ones disabled by default.

    The same fixture Home Assistant's own test suite has; the custom
    component test plugin doesn't ship it.
    """
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
        new_callable=PropertyMock,
    ):
        yield


@pytest.fixture
def mock_lifeblood(aioclient_mock):
    """Serve the captured 14 Oct 2026 page, with VIC as the AJAX region."""
    aioclient_mock.get(SOURCE_URL, text=load_fixture("page_national.html"))
    aioclient_mock.post(AJAX_URL, json=load_json_fixture("ajax_vic.json"))
    return aioclient_mock
