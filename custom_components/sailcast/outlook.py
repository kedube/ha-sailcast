"""Ratings, scores and sailing windows for each sailor at each spot.

Everything here is computed from the spots' timelines, with no I/O, so it can
run in a worker thread. Entities, the calendar, the get_forecast action and
the panel read the results.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from types import MappingProxyType

from .nowcast import Adjustment, Observation
from .profiles import Boat, Hours, Profiles, Sailor, SizeClass, Spot
from .providers import TideEvent, Tides
from .providers.noaa_coops import CurrentEvent
from .rating import Rating, rate
from .scoring import (
    Confidence,
    Slot,
    Window,
    best_window,
    confidence,
    day_score,
    find_windows,
    is_available,
    score,
)
from .shoreline import Shoreline
from .timeline import HOUR, Alert, Daylight, Hour


@dataclass(frozen=True, slots=True)
class SpotConditions:
    """A spot's hourly timeline, its days and the extra details shown with it.

    `tides` are the predictions its tide comes from, `observations` the
    readings it was built with, `adjustments` how they moved the forecast,
    and `shoreline` what its waves were worked out from.
    """

    spot: Spot
    hours: tuple[Hour, ...]
    days: tuple[Daylight, ...]
    tides: Tides | None = None
    tide_events: tuple[TideEvent, ...] = ()
    current_events: tuple[CurrentEvent, ...] = ()
    alerts: tuple[Alert, ...] = ()
    observations: tuple[Observation, ...] = ()
    adjustments: tuple[Adjustment, ...] = ()
    shoreline: Shoreline | None = None

    def index_at(self, when: datetime) -> int | None:
        """Return the index of the hour that contains a time."""
        for index, hour in enumerate(self.hours):
            if hour.start <= when < hour.start + HOUR:
                return index
        return None


@dataclass(frozen=True, slots=True)
class HourOutlook:
    """One hour for a sailor in a boat.

    Only the hours the boat can sail in have a score: its daylight hours, or
    every hour with navigation lights.
    """

    hour: Hour
    rating: Rating
    score: int | None
    available: bool


@dataclass(frozen=True, slots=True)
class DayOutlook:
    """One day for a sailor in a boat: its windows, score and confidence."""

    daylight: Daylight
    windows: tuple[Window, ...]
    best: Window | None
    score: int | None
    confidence: Confidence | None
    spread: float | None


@dataclass(frozen=True, slots=True)
class BoatOutlook:
    """A sailor's week in one boat at one spot."""

    boat: Boat
    hours: tuple[HourOutlook, ...]
    days: tuple[DayOutlook, ...]


@dataclass(frozen=True, slots=True)
class Outlook:
    """A sailor's week at one spot, in each of their boats.

    `sizes` rates every boat size at the sailor's skill, hour by hour, in the
    same order as the spot's hours. `changes` are the hours the sailor set for
    single dates, None for not sailing, which come before their weekdays'.
    """

    sailor: Sailor
    spot: Spot
    boats: tuple[BoatOutlook, ...]
    sizes: Mapping[SizeClass, tuple[Rating, ...]]
    changes: Mapping[date, Hours | None] = field(default_factory=dict)

    @property
    def default(self) -> BoatOutlook | None:
        """Return the sailor's usual boat's outlook."""
        return self.boats[0] if self.boats else None

    def hours_on(self, day: date) -> Hours | None:
        """Return the sailor's hours on a date, or None if they don't sail."""
        return self.sailor.hours_on(day, self.changes)


@dataclass(frozen=True, slots=True)
class Results:
    """Every spot's conditions and every sailor's outlook, by ID."""

    conditions: Mapping[str, SpotConditions] = field(default_factory=dict)
    outlooks: Mapping[tuple[str, str], Outlook] = field(default_factory=dict)

    def outlook(self, sailor: str, spot: str) -> Outlook | None:
        """Return a sailor's outlook at a spot."""
        return self.outlooks.get((sailor, spot))


def sails(boat: Boat, hour: Hour) -> bool:
    """Return whether a boat can sail in an hour: in daylight, or with lights."""
    return hour.daylight or boat.lights


def day_windows(boat: Boat, slots: Sequence[Slot], day: Daylight) -> list[Window]:
    """Return a day's windows, kept to daylight unless the boat has lights."""
    if boat.lights:
        return find_windows(slots, None, None)
    return find_windows(slots, day.sunrise, day.sunset)


def compute(
    profiles: Profiles,
    conditions: Mapping[str, SpotConditions],
    changes: Mapping[str, Mapping[date, Hours | None]] = MappingProxyType({}),
) -> Results:
    """Return the outlook for every sailor at every spot with conditions.

    `changes` are each sailor's hours for single dates, by sailor ID.
    """
    outlooks = {
        (sailor.id, spot_id): outlook(
            sailor, spot_conditions, profiles.boats, changes.get(sailor.id, {})
        )
        for sailor in profiles.sailors.values()
        for spot_id, spot_conditions in conditions.items()
    }
    return Results(conditions=dict(conditions), outlooks=outlooks)


def outlook(
    sailor: Sailor,
    conditions: SpotConditions,
    boats: Mapping[str, Boat],
    changes: Mapping[date, Hours | None] = MappingProxyType({}),
) -> Outlook:
    """Return a sailor's week at a spot, for every boat size and their boats.

    The sailor's free hours follow the hours set for a date, if any, and
    otherwise their hours on that day of the week.
    """
    spot = conditions.spot
    sizes = {
        size: tuple(
            rate(hour, size, sailor.skill, spot.offshore) for hour in conditions.hours
        )
        for size in SizeClass
    }
    zone = conditions.days[0].zone if conditions.days else None
    free = tuple(
        is_available(sailor.hours_on(local.date(), changes), local)
        for local in (hour.start.astimezone(zone) for hour in conditions.hours)
    )
    return Outlook(
        sailor=sailor,
        spot=spot,
        boats=tuple(
            _boat_outlook(boats[boat_id], sailor, conditions, sizes, free)
            for boat_id in sailor.boats
            if boat_id in boats
        ),
        sizes=sizes,
        changes=dict(changes),
    )


def _boat_outlook(
    boat: Boat,
    sailor: Sailor,
    conditions: SpotConditions,
    sizes: Mapping[SizeClass, tuple[Rating, ...]],
    free: tuple[bool, ...],
) -> BoatOutlook:
    """Return a boat's week. `free` says when the sailor's days and times allow."""
    ratings = sizes[boat.size_class]
    hours = tuple(
        HourOutlook(
            hour=hour,
            rating=rating,
            score=score(hour, boat.size_class, sailor.skill, rating, sailor.comfort)
            if sails(boat, hour)
            else None,
            available=allowed and sails(boat, hour),
        )
        for hour, rating, allowed in zip(conditions.hours, ratings, free, strict=True)
    )
    zone = conditions.days[0].zone if conditions.days else None
    days = []
    for day in conditions.days:
        sailable = [
            item
            for item in hours
            if item.score is not None
            and item.hour.start.astimezone(zone).date() == day.date
        ]
        slots = [
            Slot(item.hour.start, item.score, item.available)
            for item in sailable
            if item.score is not None
        ]
        windows = day_windows(boat, slots, day)
        agreement = confidence([item.hour for item in sailable])
        days.append(
            DayOutlook(
                daylight=day,
                windows=tuple(windows),
                best=best_window(windows),
                score=day_score(slots, windows),
                confidence=agreement[0] if agreement else None,
                spread=agreement[1] if agreement else None,
            )
        )
    return BoatOutlook(boat=boat, hours=hours, days=tuple(days))
