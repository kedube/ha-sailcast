"""Summaries of conditions over a stretch of hours.

The panel shows them under each day and for each window, the advice is built
from them, and calendar events describe a window with them. Values are in the
timeline's units: knots for wind, meters and °C for the rest.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import statistics
from typing import Final

from .timeline import HOUR, Hour, mean_direction

# The wind is building or easing when the last third of the hours averages
# this much (kt) more or less than the first third.
TREND_CHANGE: Final = 2.0


class Trend(StrEnum):
    """Which way the wind goes over the hours."""

    BUILDING = "building"
    EASING = "easing"


@dataclass(frozen=True, slots=True, kw_only=True)
class Summary:
    """Conditions over some hours: ranges, the most rain and the worst weather.

    Ranges are (lowest, highest). Waves and temperatures are None when no
    hour has them.
    """

    hours: int
    wind_low: float
    wind_high: float
    gust: float
    direction: float
    trend: Trend | None
    waves: tuple[float, float] | None
    temperature: tuple[float, float] | None
    rain_chance: float | None
    weather_code: int | None
    visibility: float | None
    water_temperature: float | None


def summarize(hours: Sequence[Hour]) -> Summary | None:
    """Return a summary of the hours, or None if there are none."""
    if not hours:
        return None
    winds = [hour.wind for hour in hours]
    third = max(1, len(hours) // 3)
    early = statistics.fmean(winds[:third])
    late = statistics.fmean(winds[-third:])
    trend = None
    if late - early >= TREND_CHANGE:
        trend = Trend.BUILDING
    elif early - late >= TREND_CHANGE:
        trend = Trend.EASING
    return Summary(
        hours=len(hours),
        wind_low=min(winds),
        wind_high=max(winds),
        gust=max(hour.gust for hour in hours),
        direction=mean_direction([hour.wind_direction for hour in hours]),
        trend=trend,
        waves=_range([hour.wave_height for hour in hours]),
        temperature=_range([hour.temperature for hour in hours]),
        rain_chance=_most([hour.rain_chance for hour in hours]),
        weather_code=_most_code([hour.weather_code for hour in hours]),
        visibility=_least([hour.visibility for hour in hours]),
        water_temperature=next(
            (
                hour.water_temperature
                for hour in hours
                if hour.water_temperature is not None
            ),
            None,
        ),
    )


def hours_between(hours: Sequence[Hour], start: datetime, end: datetime) -> list[Hour]:
    """Return the hours that overlap a stretch of time."""
    return [hour for hour in hours if hour.start < end and hour.start + HOUR > start]


def _range(values: Sequence[float | None]) -> tuple[float, float] | None:
    known = [value for value in values if value is not None]
    return (min(known), max(known)) if known else None


def _most(values: Sequence[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return max(known) if known else None


def _most_code(values: Sequence[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    return max(known) if known else None


def _least(values: Sequence[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return min(known) if known else None
