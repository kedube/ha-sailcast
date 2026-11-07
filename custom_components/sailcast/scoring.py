"""Scores, sailing windows and confidence.

The score (0-100) says how good an hour is for a sailor in a boat. It starts
from how well the wind fits the sailor's ideal range, takes off points for
gusts, waves, rain, cold and poor visibility, and is capped by the safety
rating. A sailor's comfort settings change the ideal range, the rain penalty
and where cold starts to count, but never the rating. A sailing window is two
or more hours in a row, in daylight and in the sailor's hours that day,
scoring 60 or more. In a boat with navigation lights, hours after dark count
too.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from itertools import pairwise
import math
from types import MappingProxyType
from typing import Final

from .limits import BOAT_LIMITS, FOOT, SKILL_WIND_LIMITS, Level
from .profiles import Comfort, Hours, RainTolerance, SizeClass, Skill
from .rating import Rating
from .timeline import Hour

HOUR: Final = timedelta(hours=1)

# The highest score each rating allows, so a caution hour can't join a window.
SCORE_CAPS: Final = MappingProxyType(
    {
        Level.GOOD: 100,
        Level.CAUTION: 55,
        Level.NOT_RECOMMENDED: 25,
        Level.DANGEROUS: 0,
    }
)
WINDOW_SCORE: Final = 60
WINDOW_HOURS: Final = 2
# A day without a window can't read better than fair.
NO_WINDOW_CAP: Final = 59


class Band(StrEnum):
    """How a score reads."""

    GREAT = "great"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class Confidence(StrEnum):
    """How closely the forecast models agree over a day."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Typical spread between the models' wind (kt) for high and medium.
CONFIDENCE_SPREADS: Final = (3.0, 6.0)
# Typical spread of the ECMWF ensemble's wind (kt, one standard deviation)
# for high and medium. Three models typically span about 1.7 of these, so the
# two scales match.
ENSEMBLE_SPREADS: Final = (1.75, 3.5)

# Points off for each percent chance of rain, by the sailor's tolerance.
RAIN_PENALTIES: Final = MappingProxyType(
    {RainTolerance.AVOID: 0.5, RainTolerance.SOME: 0.35, RainTolerance.ANY: 0.15}
)
# Cold costs 1.2 points for each °F below this (°C), unless a sailor sets
# their own coldest comfortable air.
COLD_START: Final = 10.0


def band(score: int) -> Band:
    """Return the band a score falls in."""
    if score >= 80:
        return Band.GREAT
    if score >= 60:
        return Band.GOOD
    if score >= 40:
        return Band.FAIR
    return Band.POOR


def ideal_wind(
    size: SizeClass, skill: Skill, comfort: Comfort | None = None
) -> tuple[float, float]:
    """Return a sailor's ideal wind range (kt) for a boat size.

    The range tops out at the boat's ideal top or the skill's wind limit,
    whichever is lower, so a higher skill level never lowers a score. A
    sailor's own ideal range can narrow it; one that doesn't overlap it is
    ignored.
    """
    low, top = BOAT_LIMITS[size].ideal_wind
    limit = SKILL_WIND_LIMITS[skill]
    high = top if limit is None else min(top, limit)
    if comfort is None:
        return low, high
    narrowed = (
        low if comfort.ideal_low is None else max(low, comfort.ideal_low),
        high if comfort.ideal_high is None else min(high, comfort.ideal_high),
    )
    return narrowed if narrowed[0] < narrowed[1] else (low, high)


def score(
    hour: Hour,
    size: SizeClass,
    skill: Skill,
    rating: Rating,
    comfort: Comfort | None = None,
) -> int:
    """Score an hour for a boat size and skill level, given its rating."""
    comfort = comfort or Comfort()
    limits = BOAT_LIMITS[size]
    limit = SKILL_WIND_LIMITS[skill]
    low, high = ideal_wind(size, skill, comfort)
    if hour.wind < low:
        value = 100 - (low - hour.wind) * 16
    elif hour.wind <= high:
        value = 100.0
    else:
        top = limits.wind[1] if limit is None else limit
        value = 100 - (hour.wind - high) / max(1, top - high) * 60
    if (spread := hour.gust - hour.wind) > 7:
        value -= (spread - 7) * 3
    if hour.wave_height is not None and hour.wave_height > limits.wave[0]:
        value -= (hour.wave_height - limits.wave[0]) / FOOT * 15
    if hour.rain_chance is not None:
        value -= hour.rain_chance * RAIN_PENALTIES[comfort.rain]
    cold = COLD_START if comfort.coldest is None else comfort.coldest
    if hour.temperature is not None and hour.temperature < cold:
        # 1.2 points for each °F below.
        value -= (cold - hour.temperature) * 9 / 5 * 1.2
    if hour.visibility is not None:
        if hour.visibility < 2000:
            value -= 30
        elif hour.visibility < 5000:
            value -= 15
    value = min(value, SCORE_CAPS[rating.level])
    return max(0, round_half_up(value))


def is_available(hours: Hours | None, hour: datetime) -> bool:
    """Return whether a sailor can sail in the hour that begins at `hour`.

    `hour` is in local time, and `hours` are the sailor's hours that day, or
    None if they don't sail then. A missing start or end is no limit here:
    without navigation lights, the boat's daylight keeps it to sunrise and
    sunset.
    """
    if hours is None:
        return False
    if hours.start is not None and hour.time() < time.fromisoformat(hours.start):
        return False
    if hours.end is not None:
        end = time.fromisoformat(hours.end)
        return hour + HOUR <= datetime.combine(hour.date(), end, hour.tzinfo)
    return True


@dataclass(frozen=True, slots=True)
class Slot:
    """One hour the boat can sail in: its score and whether the sailor is free."""

    start: datetime
    score: int
    available: bool


@dataclass(frozen=True, slots=True)
class Window:
    """A sailing window.

    Without navigation lights, it starts no earlier than sunrise and ends by
    sunset.
    """

    start: datetime
    end: datetime
    average: float
    hours: int

    @property
    def score(self) -> int:
        """Return the window's average score, rounded."""
        return round_half_up(self.average)


def find_windows(
    slots: Sequence[Slot], sunrise: datetime | None, sunset: datetime | None
) -> list[Window]:
    """Return every run of two or more available hours scoring 60 or more.

    `slots` are the day's hours the boat can sail in, in order. Windows are
    kept between sunrise and sunset, unless those are None, as they are for
    a boat with navigation lights.
    """
    windows: list[Window] = []
    run: list[Slot] = []

    def close() -> None:
        if len(run) >= WINDOW_HOURS:
            start, end = run[0].start, run[-1].start + HOUR
            windows.append(
                Window(
                    start=max(start, sunrise) if sunrise else start,
                    end=min(end, sunset) if sunset else end,
                    average=sum(slot.score for slot in run) / len(run),
                    hours=len(run),
                )
            )
        run.clear()

    for slot in slots:
        if not slot.available or slot.score < WINDOW_SCORE:
            close()
            continue
        if run and slot.start - run[-1].start != HOUR:
            close()
        run.append(slot)
    close()
    return windows


def best_window(windows: Sequence[Window]) -> Window | None:
    """Return the window with the highest average, the longer one if close."""
    best: Window | None = None
    for window in windows:
        if (
            best is None
            or window.average > best.average + 0.5
            or (abs(window.average - best.average) <= 0.5 and window.hours > best.hours)
        ):
            best = window
    return best


def day_score(slots: Sequence[Slot], windows: Sequence[Window]) -> int | None:
    """Return a day's score: its best window's, or at most 59 without one.

    Without a window, the score is the best pair of available hours in a row,
    or the best single hour, so one good hour can't make a day look great.
    The day has no score if the sailor isn't free at all.
    """
    if best := best_window(windows):
        return best.score
    available = [slot for slot in slots if slot.available]
    if not available:
        return None
    pairs = [
        (first.score + second.score) / 2
        for first, second in pairwise(available)
        if second.start - first.start == HOUR
    ]
    value = max(pairs) if pairs else max(slot.score for slot in available)
    return min(NO_WINDOW_CAP, round_half_up(value))


def confidence(hours: Sequence[Hour]) -> tuple[Confidence, float] | None:
    """Return how closely the models agree on wind over some hours.

    The spread is the typical (median) gap between the highest and lowest
    model's wind in an hour. A wide spread in the ECMWF ensemble can lower
    the confidence, but never raise it.
    """
    spreads = sorted(
        max(winds) - min(winds)
        for hour in hours
        if len(winds := [wind for wind in hour.wind_models if wind is not None]) >= 2
    )
    if not spreads:
        return None
    spread = spreads[len(spreads) // 2]
    level = _level(spread, CONFIDENCE_SPREADS)
    ensemble = sorted(
        hour.wind_spread for hour in hours if hour.wind_spread is not None
    )
    if ensemble:
        level = max(
            level,
            _level(ensemble[len(ensemble) // 2], ENSEMBLE_SPREADS),
            key=_CONFIDENCE_ORDER.index,
        )
    return level, spread


_CONFIDENCE_ORDER: Final = (Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW)


def _level(spread: float, starts: tuple[float, float]) -> Confidence:
    if spread <= starts[0]:
        return Confidence.HIGH
    if spread <= starts[1]:
        return Confidence.MEDIUM
    return Confidence.LOW


def steady_level(levels: Sequence[Level]) -> Level:
    """Return the best rating that holds for at least two hours in a row."""
    if len(levels) == 1:
        return levels[0]
    return min(max(first, second) for first, second in pairwise(levels))


def round_half_up(value: float) -> int:
    """Round to the nearest whole number, halves up, as the panel does."""
    return math.floor(value + 0.5)
