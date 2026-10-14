"""Coordinator for the Lifeblood integration."""

from __future__ import annotations

import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import LIFEBLOOD_TZ, LifebloodClient, LifebloodError, SupplyData
from .const import CHECK_TIMES, CONF_REGION, DOMAIN, RETRY_INTERVAL

_LOGGER = logging.getLogger(__name__)

USER_AGENT_TEMPLATE = "ha-lifeblood/{version} (+https://github.com/gurrier/lifeblood)"

type LifebloodConfigEntry = ConfigEntry[LifebloodDataUpdateCoordinator]


def time_until_next_check(now: datetime.datetime) -> datetime.timedelta:
    """How long from `now` until the next CHECK_TIMES slot, in Sydney time.

    Both ends are converted to UTC before subtracting: Python subtracts two
    datetimes sharing a tzinfo by wall clock, which is an hour out across a
    daylight saving change.
    """
    local_now = now.astimezone(LIFEBLOOD_TZ)
    for days in (0, 1):
        day = local_now.date() + datetime.timedelta(days=days)
        for check_time in CHECK_TIMES:
            slot = datetime.datetime.combine(day, check_time, tzinfo=LIFEBLOOD_TZ)
            if slot > local_now:
                return slot.astimezone(datetime.UTC) - now.astimezone(datetime.UTC)
    raise AssertionError("CHECK_TIMES is empty")


class LifebloodDataUpdateCoordinator(DataUpdateCoordinator[SupplyData]):
    """Fetches one region's supply levels at fixed times each day."""

    config_entry: LifebloodConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: LifebloodConfigEntry, version: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            # Recalculated after every fetch - see _async_update_data.
            update_interval=time_until_next_check(dt_util.utcnow()),
        )
        self.region: str = config_entry.data[CONF_REGION]
        self.client = LifebloodClient(
            async_get_clientsession(hass),
            USER_AGENT_TEMPLATE.format(version=version),
        )

    async def _async_update_data(self) -> SupplyData:
        try:
            data = await self.client.async_get_levels(self.region)
        except LifebloodError as err:
            self.update_interval = RETRY_INTERVAL
            raise UpdateFailed(f"Error fetching Lifeblood supply levels: {err}") from err
        # The coordinator schedules the next refresh from update_interval
        # once this returns, so pointing it at the next check time here is
        # what keeps the schedule pinned to Sydney clock times.
        self.update_interval = time_until_next_check(dt_util.utcnow())
        return data
