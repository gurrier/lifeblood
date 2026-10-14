"""Sensors for the Lifeblood integration."""

from __future__ import annotations

import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from . import selected_blood_types
from .api import SupplyLevel
from .const import (
    DOMAIN,
    PLASMA,
    PLASMA_LEVELS,
    RED_CELL_LEVELS,
    REGION_NAMES,
    SOURCE_URL,
)
from .coordinator import LifebloodConfigEntry, LifebloodDataUpdateCoordinator

# Entities only read the coordinator's already-fetched data.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LifebloodConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Lifeblood sensors from a config entry."""
    coordinator = config_entry.runtime_data
    blood_types = selected_blood_types(config_entry)

    entities: list[SensorEntity] = [
        LifebloodLevelSensor(coordinator, blood_type) for blood_type in blood_types
    ]
    if PLASMA in blood_types:
        entities.append(LifebloodPlasmaShortfallSensor(coordinator))
    entities.append(LifebloodLastUpdatedSensor(coordinator))
    async_add_entities(entities)


class LifebloodEntity(CoordinatorEntity[LifebloodDataUpdateCoordinator]):
    """Common device and naming for every Lifeblood entity."""

    _attr_has_entity_name = True
    _attr_attribution = "Data provided by Australian Red Cross Lifeblood"

    def __init__(self, coordinator: LifebloodDataUpdateCoordinator, key: str) -> None:
        super().__init__(coordinator)
        region = coordinator.region
        self._attr_translation_key = key
        self._attr_unique_id = f"{region}_{key}"
        # The device is named for the region alone, since its name prefixes
        # every entity's friendly name - "Lifeblood NSW A positive" pushed
        # the level itself off the edge of dashboard buttons. The entity_id
        # keeps "lifeblood_" so new installs don't get a bare, clash-prone
        # sensor.nsw_a_positive; it only applies when the entity is first
        # registered, so existing entity_ids are untouched.
        self.entity_id = f"sensor.{slugify(f'lifeblood {REGION_NAMES[region]}')}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, region)},
            name=REGION_NAMES[region],
            manufacturer="Australian Red Cross Lifeblood",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=SOURCE_URL,
        )


class LifebloodLevelSensor(LifebloodEntity, SensorEntity):
    """Supply level of one red cell blood type, or of plasma."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: LifebloodDataUpdateCoordinator, blood_type: str) -> None:
        super().__init__(coordinator, blood_type)
        self._blood_type = blood_type
        self._attr_options = PLASMA_LEVELS if blood_type == PLASMA else RED_CELL_LEVELS

    @property
    def _level(self) -> SupplyLevel | None:
        return self.coordinator.data.levels.get(self._blood_type)

    @property
    def available(self) -> bool:
        return super().available and self._level is not None

    @property
    def native_value(self) -> str | None:
        level = self._level
        if level is None or level.level not in self.options:
            return None
        return level.level

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        level = self._level
        if level is None:
            return None
        attrs: dict[str, Any] = {"label": level.label}
        if self._blood_type != PLASMA:
            attrs["appeal"] = level.appeal
        return attrs


class LifebloodPlasmaShortfallSensor(LifebloodEntity, SensorEntity):
    """How far plasma supply is below target, in percentage points.

    Derived from the percentage Lifeblood attaches to the plasma drop, which
    behaves like supply against target (100% = on target). A raw 96% reads
    as "nearly full" next to a "Need more" level, so this shows the gap
    instead. Above target is floored at 0 rather than going negative; the
    raw figure stays available as an attribute.
    """

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: LifebloodDataUpdateCoordinator) -> None:
        super().__init__(coordinator, f"{PLASMA}_shortfall")

    @property
    def _percent(self) -> float | None:
        level = self.coordinator.data.levels.get(PLASMA)
        return level.percent if level else None

    @property
    def native_value(self) -> float | None:
        percent = self._percent
        if percent is None:
            return None
        return max(0.0, round(100 - percent, 2))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        percent = self._percent
        return None if percent is None else {"percent_of_target": percent}


class LifebloodLastUpdatedSensor(LifebloodEntity, SensorEntity):
    """When Lifeblood last published the figures (not when we polled)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: LifebloodDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "last_updated")

    @property
    def native_value(self) -> datetime.datetime | None:
        return self.coordinator.data.updated
