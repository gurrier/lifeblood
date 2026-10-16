"""Tests for the Lifeblood coordinator's fetch schedule."""

from __future__ import annotations

import datetime

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.lifeblood.api import LIFEBLOOD_TZ
from custom_components.lifeblood.const import (
    ALL_BLOOD_TYPES,
    CONF_BLOOD_TYPES,
    CONF_REGION,
    DOMAIN,
    RETRY_INTERVAL,
    SOURCE_URL,
)
from custom_components.lifeblood.coordinator import time_until_next_check

from .conftest import load_fixture


def _sydney(*args: int) -> datetime.datetime:
    return datetime.datetime(*args, tzinfo=LIFEBLOOD_TZ)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Just before publication: wait for the 6:30 check.
        (_sydney(2026, 10, 14, 5, 59), datetime.timedelta(minutes=31)),
        # After the morning check: next is the evening one.
        (_sydney(2026, 10, 14, 6, 30), datetime.timedelta(hours=12)),
        # HA can fire a refresh a little early: that still counts as the
        # 6:30 check, so the next one is 18:30 - not 6:30 again in 0.5s.
        (_sydney(2026, 10, 14, 6, 29, 59, 500000), datetime.timedelta(hours=12, seconds=0.5)),
        (_sydney(2026, 10, 14, 12, 0), datetime.timedelta(hours=6, minutes=30)),
        # After the evening check: tomorrow morning.
        (_sydney(2026, 10, 14, 20, 0), datetime.timedelta(hours=10, minutes=30)),
        # Daylight saving starts 2am 4 Oct 2026: 7pm AEST to 6:30am AEDT is
        # 11.5 hours on the clock but 10.5 hours of real time.
        (_sydney(2026, 10, 3, 19, 0), datetime.timedelta(hours=10, minutes=30)),
        # And ends 3am 4 Apr 2027: 12.5 hours of real time.
        (_sydney(2027, 4, 3, 19, 0), datetime.timedelta(hours=12, minutes=30)),
    ],
)
def test_time_until_next_check(now: datetime.datetime, expected: datetime.timedelta) -> None:
    assert time_until_next_check(now) == expected


async def test_early_refresh_does_not_double_fetch(
    hass: HomeAssistant, mock_lifeblood, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(_sydney(2026, 10, 14, 12, 0))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="national",
        data={CONF_REGION: "national", CONF_BLOOD_TYPES: ALL_BLOOD_TYPES},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert mock_lifeblood.call_count == 1

    # The 18:30 refresh lands half a second early.
    freezer.move_to(_sydney(2026, 10, 14, 18, 29, 59, 500000))
    await entry.runtime_data.async_refresh()
    assert mock_lifeblood.call_count == 2

    freezer.move_to(_sydney(2026, 10, 14, 18, 30, 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_lifeblood.call_count == 2


def test_time_until_next_check_from_other_timezone() -> None:
    """A Perth (or UTC) clock still gets Sydney check times."""
    perth = datetime.datetime(2026, 10, 14, 3, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
    # 3:00am AWST = 6:00am AEDT.
    assert time_until_next_check(perth) == datetime.timedelta(minutes=30)


async def test_schedule_after_success_and_failure(
    hass: HomeAssistant, mock_lifeblood, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(_sydney(2026, 10, 14, 12, 0))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="national",
        data={CONF_REGION: "national", CONF_BLOOD_TYPES: ALL_BLOOD_TYPES},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data

    # Fetched once at startup, then waits for the 6:30pm check.
    assert mock_lifeblood.call_count == 1
    assert coordinator.update_interval == datetime.timedelta(hours=6, minutes=30)

    # A failure retries in 30 minutes rather than waiting 12 hours, backing
    # off on each further failure but never past the next scheduled check...
    mock_lifeblood.clear_requests()
    mock_lifeblood.get(SOURCE_URL, status=503)
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.update_interval == RETRY_INTERVAL
    await coordinator.async_refresh()
    assert coordinator.update_interval == RETRY_INTERVAL * 2
    await coordinator.async_refresh()
    assert coordinator.update_interval == RETRY_INTERVAL * 4
    freezer.move_to(_sydney(2026, 10, 14, 17, 0))
    await coordinator.async_refresh()
    assert coordinator.update_interval == datetime.timedelta(hours=1, minutes=30)
    assert coordinator.consecutive_failures == 4

    # ...and the next success goes back on the schedule.
    mock_lifeblood.clear_requests()
    mock_lifeblood.get(SOURCE_URL, text=load_fixture("page_national.html"))
    freezer.move_to(_sydney(2026, 10, 14, 18, 30))
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert coordinator.consecutive_failures == 0
    assert coordinator.update_interval == datetime.timedelta(hours=12)


async def test_fetches_at_check_times(
    hass: HomeAssistant, mock_lifeblood, freezer: FrozenDateTimeFactory
) -> None:
    """The fetch really happens at 6:30pm and 6:30am, and not in between."""
    freezer.move_to(_sydney(2026, 10, 14, 12, 0))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="national",
        data={CONF_REGION: "national", CONF_BLOOD_TYPES: ALL_BLOOD_TYPES},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert mock_lifeblood.call_count == 1

    freezer.move_to(_sydney(2026, 10, 14, 18, 29))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_lifeblood.call_count == 1

    freezer.move_to(_sydney(2026, 10, 14, 18, 30, 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_lifeblood.call_count == 2

    freezer.move_to(_sydney(2026, 10, 15, 6, 29))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_lifeblood.call_count == 2

    freezer.move_to(_sydney(2026, 10, 15, 6, 30, 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_lifeblood.call_count == 3
