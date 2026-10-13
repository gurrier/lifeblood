"""Diagnostics support for the Lifeblood integration."""

from __future__ import annotations

import dataclasses
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import LifebloodConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: LifebloodConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Nothing here is private - it's all from a public web page - so there's
    nothing to redact. The raw labels and percent are what matter when the
    page layout changes and a level stops being recognised.
    """
    coordinator = config_entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "data": dict(config_entry.data),
            "options": dict(config_entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": repr(coordinator.last_exception),
        },
        "data": {
            "region": data.region,
            "region_code": data.region_code,
            "updated": data.updated.isoformat() if data.updated else None,
            "levels": {k: dataclasses.asdict(v) for k, v in data.levels.items()},
        }
        if data
        else None,
    }
