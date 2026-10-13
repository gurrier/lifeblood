"""Coordinator for the Lifeblood integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LifebloodClient, LifebloodError, SupplyData
from .const import CONF_REGION, DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

USER_AGENT_TEMPLATE = "ha-lifeblood/{version} (+https://github.com/gurrier/lifeblood)"

type LifebloodConfigEntry = ConfigEntry[LifebloodDataUpdateCoordinator]


class LifebloodDataUpdateCoordinator(DataUpdateCoordinator[SupplyData]):
    """Polls one region's supply levels."""

    config_entry: LifebloodConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: LifebloodConfigEntry, version: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.region: str = config_entry.data[CONF_REGION]
        self.client = LifebloodClient(
            async_get_clientsession(hass),
            USER_AGENT_TEMPLATE.format(version=version),
        )

    async def _async_update_data(self) -> SupplyData:
        try:
            return await self.client.async_get_levels(self.region)
        except LifebloodError as err:
            raise UpdateFailed(f"Error fetching Lifeblood supply levels: {err}") from err
