"""Diagnostics support for the Lifeblood integration."""

from __future__ import annotations

import dataclasses
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .coordinator import LifebloodConfigEntry, next_check


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: LifebloodConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Nothing here is private - it's all from a public web page - so there's
    nothing to redact. Aimed at the two questions that come up: why hasn't
    it updated (the schedule), and why is a level unknown (the raw text).
    """
    coordinator = config_entry.runtime_data
    data = coordinator.data
    update_interval = coordinator.update_interval
    return {
        "entry": {
            "data": dict(config_entry.data),
            "options": dict(config_entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": repr(coordinator.last_exception),
            "consecutive_failures": coordinator.consecutive_failures,
            # Short means it's in failure retry; long means it's idling
            # until the next scheduled check.
            "update_interval_seconds": (
                update_interval.total_seconds() if update_interval else None
            ),
            "next_scheduled_check": next_check(dt_util.utcnow()).isoformat(),
        },
        "data": {
            "region": data.region,
            "region_code": data.region_code,
            "updated": data.updated.isoformat() if data.updated else None,
            "updated_text": data.updated_text,
            "levels": {k: dataclasses.asdict(v) for k, v in data.levels.items()},
        }
        if data
        else None,
    }
