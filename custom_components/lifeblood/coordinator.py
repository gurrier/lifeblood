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
from .const import (
    CHECK_TIMES,
    CONF_REGION,
    DOMAIN,
    RETRY_INTERVAL,
    SCHEDULE_MARGIN,
    USER_AGENT_TEMPLATE,
    VALIDATION_CACHE_TTL,
)

_LOGGER = logging.getLogger(__name__)

type LifebloodConfigEntry = ConfigEntry[LifebloodDataUpdateCoordinator]


def next_check(now: datetime.datetime) -> datetime.datetime:
    """The next CHECK_TIMES slot after `now`, in Sydney time.

    A slot within SCHEDULE_MARGIN of `now` counts as already reached: Home
    Assistant can fire a scheduled refresh a little under a second early,
    and without the margin that refresh would be followed by a second one
    a moment later, when the slot itself arrived.
    """
    local_now = now.astimezone(LIFEBLOOD_TZ)
    threshold = local_now + SCHEDULE_MARGIN
    for days in (0, 1):
        day = local_now.date() + datetime.timedelta(days=days)
        for check_time in CHECK_TIMES:
            slot = datetime.datetime.combine(day, check_time, tzinfo=LIFEBLOOD_TZ)
            if slot > threshold:
                return slot
    raise AssertionError("CHECK_TIMES is empty")


def time_until_next_check(now: datetime.datetime) -> datetime.timedelta:
    """How long from `now` until the next check.

    Both ends are converted to UTC before subtracting: Python subtracts two
    datetimes sharing a tzinfo by wall clock, which is an hour out across a
    daylight saving change.
    """
    return next_check(now).astimezone(datetime.UTC) - now.astimezone(datetime.UTC)


def cache_validation_result(hass: HomeAssistant, data: SupplyData) -> None:
    """Keep a fetch the config flow made, so setup needn't repeat it."""
    hass.data.setdefault(DOMAIN, {})[data.region] = (data, dt_util.utcnow())


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
        self.consecutive_failures = 0

    def _pop_validation_result(self) -> SupplyData | None:
        """A fresh fetch the config flow made for this region, if any."""
        cached = self.hass.data.get(DOMAIN, {}).pop(self.region, None)
        if cached is None:
            return None
        data, fetched_at = cached
        if dt_util.utcnow() - fetched_at > VALIDATION_CACHE_TTL:
            return None
        return data

    async def _async_update_data(self) -> SupplyData:
        now = dt_util.utcnow()
        data = self._pop_validation_result()
        if data is None:
            try:
                data = await self.client.async_get_levels(self.region)
            except LifebloodError as err:
                # Retry sooner than the next slot, backing off on repeated
                # failures so a redesigned page doesn't mean polling a public
                # site every 30 minutes until a fix ships - and never later
                # than the next scheduled check anyway.
                self.consecutive_failures += 1
                retry = RETRY_INTERVAL * 2 ** (self.consecutive_failures - 1)
                self.update_interval = min(retry, time_until_next_check(now))
                raise UpdateFailed(
                    f"Error fetching Lifeblood supply levels: {err}"
                ) from err
        self.consecutive_failures = 0
        # The coordinator schedules the next refresh from update_interval
        # once this returns, so pointing it at the next check time here is
        # what keeps the schedule pinned to Sydney clock times.
        self.update_interval = time_until_next_check(now)
        return data
