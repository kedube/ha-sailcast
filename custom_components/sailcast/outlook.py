"""Ratings, scores and sailing windows for each sailor at each spot.

Everything here is computed from the spots' timelines, with no I/O, so it can
run in a worker thread. Entities, the calendar, the get_forecast action and
the panel read the results.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from .profiles import Boat, Profiles, Sailor, SizeClass, Spot
from .providers.noaa_coops import CurrentEvent, TideEvent
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
from .timeline import HOUR, Alert, Daylight, Hour


@dataclass(frozen=True, slots=True)
class SpotConditions:
    """A spot's hourly timeline, its days and the extra details shown with it."""

    spot: Spot
    hours: tuple[Hour, ...]
    days: tuple[Daylight, ...]
    tide_events: tuple[TideEvent, ...] = ()
    current_events: tuple[CurrentEvent, ...] = ()
    alerts: tuple[Alert, ...] = ()

    def index_at(self, when: datetime) -> int | None:
        """Return the index of the hour that contains a time."""
        for index, hour in enumerate(self.hours):
            if hour.start <= when < hour.start + HOUR:
                return index
        return None


@dataclass(frozen=True, slots=True)
class HourOutlook:
    """One hour for a sailor in a boat. Only daylight hours have a score."""

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
    same order as the spot's hours.
    """

    sailor: Sailor
    spot: Spot
    boats: tuple[BoatOutlook, ...]
    sizes: Mapping[SizeClass, tuple[Rating, ...]]

    @property
    def default(self) -> BoatOutlook | None:
        """Return the sailor's usual boat's outlook."""
        return self.boats[0] if self.boats else None


@dataclass(frozen=True, slots=True)
class Results:
    """Every spot's conditions and every sailor's outlook, by ID."""

    conditions: Mapping[str, SpotConditions] = field(default_factory=dict)
    outlooks: Mapping[tuple[str, str], Outlook] = field(default_factory=dict)

    def outlook(self, sailor: str, spot: str) -> Outlook | None:
        """Return a sailor's outlook at a spot."""
        return self.outlooks.get((sailor, spot))


def compute(profiles: Profiles, conditions: Mapping[str, SpotConditions]) -> Results:
    """Return the outlook for every sailor at every spot with conditions."""
    outlooks = {
        (sailor.id, spot_id): outlook(sailor, spot_conditions, profiles.boats)
        for sailor in profiles.sailors.values()
        for spot_id, spot_conditions in conditions.items()
    }
    return Results(conditions=dict(conditions), outlooks=outlooks)


def outlook(
    sailor: Sailor, conditions: SpotConditions, boats: Mapping[str, Boat]
) -> Outlook:
    """Return a sailor's week at a spot, for every boat size and their boats."""
    spot = conditions.spot
    sizes = {
        size: tuple(
            rate(hour, size, sailor.skill, spot.offshore) for hour in conditions.hours
        )
        for size in SizeClass
    }
    zone = conditions.days[0].zone if conditions.days else None
    available = tuple(
        hour.daylight
        and is_available(
            sailor.days, sailor.start, sailor.end, hour.start.astimezone(zone)
        )
        for hour in conditions.hours
    )
    return Outlook(
        sailor=sailor,
        spot=spot,
        boats=tuple(
            _boat_outlook(boats[boat_id], sailor, conditions, sizes, available)
            for boat_id in sailor.boats
            if boat_id in boats
        ),
        sizes=sizes,
    )


def _boat_outlook(
    boat: Boat,
    sailor: Sailor,
    conditions: SpotConditions,
    sizes: Mapping[SizeClass, tuple[Rating, ...]],
    available: tuple[bool, ...],
) -> BoatOutlook:
    ratings = sizes[boat.size_class]
    hours = tuple(
        HourOutlook(
            hour=hour,
            rating=rating,
            score=score(hour, boat.size_class, sailor.skill, rating, sailor.comfort)
            if hour.daylight
            else None,
            available=free,
        )
        for hour, rating, free in zip(conditions.hours, ratings, available, strict=True)
    )
    zone = conditions.days[0].zone if conditions.days else None
    days = []
    for day in conditions.days:
        daytime = [
            item
            for item in hours
            if item.score is not None
            and item.hour.start.astimezone(zone).date() == day.date
        ]
        slots = [
            Slot(item.hour.start, item.score, item.available)
            for item in daytime
            if item.score is not None
        ]
        windows = find_windows(slots, day.sunrise, day.sunset)
        agreement = confidence([item.hour for item in daytime])
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
