"""The Lifeblood blood supply levels integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from .const import ALL_BLOOD_TYPES, CONF_BLOOD_TYPES, CONF_REGION, DOMAIN
from .coordinator import LifebloodConfigEntry, LifebloodDataUpdateCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


def selected_blood_types(config_entry: LifebloodConfigEntry) -> list[str]:
    """The blood types this entry tracks - options win over initial setup."""
    return config_entry.options.get(
        CONF_BLOOD_TYPES,
        config_entry.data.get(CONF_BLOOD_TYPES, ALL_BLOOD_TYPES),
    )


def _async_remove_deselected_entities(
    hass: HomeAssistant, config_entry: LifebloodConfigEntry
) -> None:
    """Drop registry entries for blood types no longer selected.

    Without this, unticking a type in the options leaves its entity behind
    as permanently "unavailable" rather than removing it.
    """
    region = config_entry.data[CONF_REGION]
    keep = set(selected_blood_types(config_entry))
    registry = er.async_get(hass)
    for entry in er.async_entries_for_config_entry(registry, config_entry.entry_id):
        prefix = f"{region}_"
        if not entry.unique_id.startswith(prefix):
            continue
        blood_type = entry.unique_id.removeprefix(prefix)
        # Plasma supply % rides along with the plasma level sensor.
        blood_type = blood_type.removesuffix("_supply")
        if blood_type in ALL_BLOOD_TYPES and blood_type not in keep:
            _LOGGER.debug("Removing deselected Lifeblood entity %s", entry.entity_id)
            registry.async_remove(entry.entity_id)


async def async_setup_entry(hass: HomeAssistant, config_entry: LifebloodConfigEntry) -> bool:
    """Set up Lifeblood from a config entry."""
    integration = await async_get_integration(hass, DOMAIN)
    version = str(integration.version) if integration.version else "unknown"

    coordinator = LifebloodDataUpdateCoordinator(hass, config_entry, version)
    await coordinator.async_config_entry_first_refresh()
    config_entry.runtime_data = coordinator

    _async_remove_deselected_entities(hass, config_entry)

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    config_entry.async_on_unload(config_entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, config_entry: LifebloodConfigEntry) -> None:
    """Reload when the selected blood types change."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: LifebloodConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
