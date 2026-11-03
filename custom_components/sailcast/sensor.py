"""Sensors: each sailor's rating, score and next window, and spot conditions.

The rating and score use the sailor's skill and usual boat. Ratings for every
boat size are in the get_forecast action and the panel instead, because a
rating depends on the sailor's skill. The spot's own condition sensors are
off by default, since most people have a weather integration already.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import DEGREE, UnitOfLength, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import tides
from .coordinator import ResultsCoordinator, SailCastConfigEntry
from .entity import SailorEntity, SpotEntity, async_remove_stale
from .limits import Level
from .outlook import SpotConditions
from .profiles import Sailor, Spot
from .scoring import Window
from .timeline import Hour


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SailCastConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors for each spot and sailor."""
    data = entry.runtime_data
    results = data.results
    profiles = data.profiles
    added: list[str] = []
    for spot in profiles.spots.values():
        entities = [
            SpotSensor(results, spot, description)
            for description in SPOT_SENSORS
            if description.applies(spot)
        ]
        async_add_entities(entities, config_subentry_id=spot.id)
        added += [entity.unique_id for entity in entities if entity.unique_id]
    for sailor in profiles.sailors.values():
        sailor_entities: list[SailorEntity] = [NextWindowSensor(results, sailor)]
        for spot in profiles.spots.values():
            sailor_entities += [
                RatingSensor(results, sailor, spot),
                ScoreSensor(results, sailor, spot),
            ]
        async_add_entities(sailor_entities, config_subentry_id=sailor.id)
        added += [entity.unique_id for entity in sailor_entities if entity.unique_id]
    async_remove_stale(hass, entry, "sensor", added)


class RatingSensor(SailorEntity, SensorEntity):
    """The safety rating now, for a sailor in their usual boat at a spot."""

    _attr_device_class = SensorDeviceClass.ENUM
    _unrecorded_attributes = frozenset({"reasons", "next_change", "next_rating"})

    def __init__(
        self, coordinator: ResultsCoordinator, sailor: Sailor, spot: Spot
    ) -> None:
        """Set up the rating."""
        super().__init__(coordinator, sailor, "rating", spot)
        self._attr_options = [level.key for level in Level]

    @property
    def native_value(self) -> str | None:
        """Return this hour's rating."""
        if (now := self.now()) is None:
            return None
        boat, index = now
        return boat.hours[index].rating.level.key

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the boat, the reasons and when the rating next changes."""
        if (now := self.now()) is None:
            return None
        boat, index = now
        rating = boat.hours[index].rating
        attributes: dict[str, Any] = {
            "boat": boat.boat.name,
            "reasons": [reason.key for reason in rating.reasons],
        }
        for later in boat.hours[index + 1 :]:
            if later.rating.level != rating.level:
                attributes["next_change"] = later.hour.start.isoformat()
                attributes["next_rating"] = later.rating.level.key
                break
        return attributes


class ScoreSensor(SailorEntity, SensorEntity):
    """The sailing score now, for a sailor in their usual boat at a spot.

    It has no value at night.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: ResultsCoordinator, sailor: Sailor, spot: Spot
    ) -> None:
        """Set up the score."""
        super().__init__(coordinator, sailor, "score", spot)

    @property
    def native_value(self) -> int | None:
        """Return this hour's score."""
        if (now := self.now()) is None:
            return None
        boat, index = now
        return boat.hours[index].score


class NextWindowSensor(SailorEntity, SensorEntity):
    """When the sailor's next sailing window starts, at any spot.

    A window that's under way counts until it ends.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: ResultsCoordinator, sailor: Sailor) -> None:
        """Set up the next window."""
        super().__init__(coordinator, sailor, "next_window")

    def _next(self) -> tuple[Spot, str, Window] | None:
        now = dt_util.utcnow()
        found: tuple[Spot, str, Window] | None = None
        for outlook in self.coordinator.data.outlooks.values():
            if outlook.sailor.id != self.sailor.id or (boat := outlook.default) is None:
                continue
            for day in boat.days:
                for window in day.windows:
                    if window.end > now and (
                        found is None or window.start < found[2].start
                    ):
                        found = (outlook.spot, boat.boat.name, window)
        return found

    @property
    def native_value(self) -> datetime | None:
        """Return when the next window starts."""
        found = self._next()
        return found[2].start if found else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the window's spot, boat, end and score."""
        if (found := self._next()) is None:
            return None
        spot, boat, window = found
        return {
            "spot": spot.name,
            "boat": boat,
            "end": window.end.isoformat(),
            "score": window.score,
        }


@dataclass(frozen=True, kw_only=True)
class SpotSensorDescription(SensorEntityDescription):
    """A spot condition, read from the hour now or the tide events."""

    value: Callable[[SpotConditions, Hour], Any]
    applies: Callable[[Spot], bool] = lambda spot: True
    attributes: Callable[[SpotConditions], dict[str, Any] | None] = lambda _: None


def _has_tide_times(spot: Spot) -> bool:
    """Return whether a spot's tides have times, which the ocean model's don't."""
    return spot.tide_station not in (None, tides.MODEL)


def _next_tide(conditions: SpotConditions, high: bool) -> Any:
    now = dt_util.utcnow()
    return next(
        (
            event
            for event in conditions.tide_events
            if event.time > now and event.high is high
        ),
        None,
    )


def _tide_time(high: bool) -> Callable[[SpotConditions, Hour], datetime | None]:
    def value(conditions: SpotConditions, hour: Hour) -> datetime | None:
        event = _next_tide(conditions, high)
        return event.time if event else None

    return value


def _tide_height(high: bool) -> Callable[[SpotConditions], dict[str, Any] | None]:
    def attributes(conditions: SpotConditions) -> dict[str, Any] | None:
        event = _next_tide(conditions, high)
        # Meters above the station's chart datum (MLLW in the US).
        return {"height": round(event.height, 2)} if event else None

    return attributes


SPOT_SENSORS: tuple[SpotSensorDescription, ...] = (
    SpotSensorDescription(
        key="wind_speed",
        translation_key="wind_speed",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.KNOTS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value=lambda _, hour: hour.wind,
    ),
    SpotSensorDescription(
        key="wind_gust",
        translation_key="wind_gust",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.KNOTS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value=lambda _, hour: hour.gust,
    ),
    SpotSensorDescription(
        key="wind_direction",
        translation_key="wind_direction",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value=lambda _, hour: hour.wind_direction,
    ),
    SpotSensorDescription(
        key="wave_height",
        translation_key="wave_height",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        # Sheltered water and lakes have waves worked out from the fetch.
        value=lambda _, hour: hour.wave_height,
    ),
    SpotSensorDescription(
        key="water_temperature",
        translation_key="water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value=lambda _, hour: hour.water_temperature,
        applies=lambda spot: spot.open_water,
    ),
    SpotSensorDescription(
        key="next_high_tide",
        translation_key="next_high_tide",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        value=_tide_time(high=True),
        applies=_has_tide_times,
        attributes=_tide_height(high=True),
    ),
    SpotSensorDescription(
        key="next_low_tide",
        translation_key="next_low_tide",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        value=_tide_time(high=False),
        applies=_has_tide_times,
        attributes=_tide_height(high=False),
    ),
)


class SpotSensor(SpotEntity, SensorEntity):
    """A condition at a spot, from this hour's forecast."""

    entity_description: SpotSensorDescription

    def __init__(
        self,
        coordinator: ResultsCoordinator,
        spot: Spot,
        description: SpotSensorDescription,
    ) -> None:
        """Set up the condition."""
        super().__init__(coordinator, spot, description.key)
        self.entity_description = description

    def _now(self) -> tuple[SpotConditions, Hour] | None:
        if (conditions := self.conditions) is None:
            return None
        index = conditions.index_at(dt_util.utcnow())
        return None if index is None else (conditions, conditions.hours[index])

    @property
    def native_value(self) -> Any:
        """Return the condition now."""
        if (now := self._now()) is None:
            return None
        return self.entity_description.value(*now)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the condition's details."""
        if (conditions := self.conditions) is None:
            return None
        return self.entity_description.attributes(conditions)
