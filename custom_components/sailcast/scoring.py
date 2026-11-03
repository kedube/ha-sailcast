"""Scores, sailing windows and confidence.

The score (0-100) says how good an hour is for a sailor in a boat. It starts
from how well the wind fits the sailor's ideal range, takes off points for
gusts, waves, rain, cold and poor visibility, and is capped by the safety
rating. A sailing window is two or more hours in a row, in daylight and in the
sailor's time, scoring 60 or more.
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

from homeassistant.const import WEEKDAYS

from .limits import BOAT_LIMITS, FOOT, SKILL_WIND_LIMITS, Level
from .profiles import SizeClass, Skill
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


def band(score: int) -> Band:
    """Return the band a score falls in."""
    if score >= 80:
        return Band.GREAT
    if score >= 60:
        return Band.GOOD
    if score >= 40:
        return Band.FAIR
    return Band.POOR


def ideal_wind(size: SizeClass, skill: Skill) -> tuple[float, float]:
    """Return a sailor's ideal wind range (kt) for a boat size.

    The range tops out at the boat's ideal top or the skill's wind limit,
    whichever is lower, so a higher skill level never lowers a score.
    """
    low, top = BOAT_LIMITS[size].ideal_wind
    limit = SKILL_WIND_LIMITS[skill]
    return low, top if limit is None else min(top, limit)


def score(hour: Hour, size: SizeClass, skill: Skill, rating: Rating) -> int:
    """Score an hour for a boat size and skill level, given its rating."""
    limits = BOAT_LIMITS[size]
    limit = SKILL_WIND_LIMITS[skill]
    low, high = ideal_wind(size, skill)
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
        value -= hour.rain_chance * 0.35
    if hour.temperature is not None and hour.temperature < 10:
        # 1.2 points for each °F below 50 °F.
        value -= (10 - hour.temperature) * 9 / 5 * 1.2
    if hour.visibility is not None:
        if hour.visibility < 2000:
            value -= 30
        elif hour.visibility < 5000:
            value -= 15
    value = min(value, SCORE_CAPS[rating.level])
    return max(0, round_half_up(value))


def is_available(
    days: Sequence[str], start: str | None, end: str | None, hour: datetime
) -> bool:
    """Return whether a sailor can sail in the hour that begins at `hour`.

    `hour` is in local time. `days` are keys such as "sat", and `start` and
    `end` are times of day such as "09:00:00", or None for sunrise or sunset.
    """
    if WEEKDAYS[hour.weekday()] not in days:
        return False
    if start is not None and hour.time() < time.fromisoformat(start):
        return False
    if end is not None:
        limit = datetime.combine(hour.date(), time.fromisoformat(end), hour.tzinfo)
        return hour + HOUR <= limit
    return True


@dataclass(frozen=True, slots=True)
class Slot:
    """One daylight hour of a day: its score and whether the sailor is free."""

    start: datetime
    score: int
    available: bool


@dataclass(frozen=True, slots=True)
class Window:
    """A sailing window. It starts no earlier than sunrise and ends by sunset."""

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

    `slots` are a day's daylight hours, in order.
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
    model's wind in an hour.
    """
    spreads = sorted(
        max(winds) - min(winds)
        for hour in hours
        if len(winds := [wind for wind in hour.wind_models if wind is not None]) >= 2
    )
    if not spreads:
        return None
    spread = spreads[len(spreads) // 2]
    if spread <= CONFIDENCE_SPREADS[0]:
        return Confidence.HIGH, spread
    if spread <= CONFIDENCE_SPREADS[1]:
        return Confidence.MEDIUM, spread
    return Confidence.LOW, spread


def steady_level(levels: Sequence[Level]) -> Level:
    """Return the best rating that holds for at least two hours in a row."""
    if len(levels) == 1:
        return levels[0]
    return min(max(first, second) for first, second in pairwise(levels))


def round_half_up(value: float) -> int:
    """Round to the nearest whole number, halves up, as the panel does."""
    return math.floor(value + 0.5)
