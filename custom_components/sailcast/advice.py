"""Rule-based advice for a sailor's day at a spot.

Each piece of advice is a translation key with values, which the panel turns
into a sentence in the user's language and units. Times are in UTC, wind and
current in knots, heights and visibility in meters, and temperatures in °C.
Advice never changes a rating; it explains the conditions behind one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from .geo import angle_between, compass_point
from .limits import BOAT_LIMITS, SKILL_WIND_LIMITS, WARNING_FLOORS, Level, warning_group
from .profiles import SizeClass, Skill, Spot
from .providers import TideEvent
from .summary import Summary, summarize
from .timeline import HOUR, Daylight, Hour

LIGHT_AIR: Final = 5.0
GUSTY_SPREAD: Final = 8.0
NEAR_LIMIT: Final = 2.0
REEF_MARGIN: Final = 3.0
# Wind against current that's worth a mention, below the rating's threshold.
AGAINST_CURRENT: Final = 0.8
AGAINST_CURRENT_WIND: Final = 10.0
AGAINST_CURRENT_ANGLE: Final = 120.0
RAIN_LIKELY: Final = 40.0
POOR_VISIBILITY: Final = 3704.0  # 2 nautical miles, in meters

_WARNING_KEYS: Final = {
    Level.DANGEROUS: "warning_dangerous",
    Level.NOT_RECOMMENDED: "warning_not_recommended",
    Level.CAUTION: "warning_caution",
}


@dataclass(frozen=True, slots=True)
class Advice:
    """One piece of advice.

    `icon` names the panel's icon for it, and `hot` marks advice that needs
    attention.
    """

    key: str
    icon: str
    values: Mapping[str, Any] = field(default_factory=dict)
    hot: bool = False


def advise(
    spot: Spot,
    size: SizeClass,
    skill: Skill,
    day: Daylight,
    hours: Sequence[Hour],
    *,
    tides: Sequence[TideEvent] = (),
    lights: bool = False,
) -> list[Advice]:
    """Return the advice for a day, from the hours still to come.

    `hours` are the ones the boat can sail in: its daylight hours, or every
    hour if it has navigation lights.
    """
    summary = summarize(hours)
    if summary is None:
        return [Advice("day_over", "sunset")]
    return [
        *_warnings(size, hours),
        *_wind(size, skill, summary, hours),
        *_water(spot, size, summary, hours),
        *_weather(summary),
        *_tides_and_sunset(day, hours, tides, lights=lights),
    ]


def _warnings(size: SizeClass, hours: Sequence[Hour]) -> list[Advice]:
    """Name each official warning in effect, and what it means for the boat."""
    advice = []
    for event in dict.fromkeys(alert.event for hour in hours for alert in hour.alerts):
        group = warning_group(event)
        key = _WARNING_KEYS[WARNING_FLOORS[group][size]] if group else "warning"
        advice.append(Advice(key, "flag", {"event": event, "size": size.value}, True))
    return advice


def _wind(
    size: SizeClass, skill: Skill, summary: Summary, hours: Sequence[Hour]
) -> list[Advice]:
    """Describe the day's wind, and what it means for the sailor and the boat."""
    limits = BOAT_LIMITS[size]
    advice = [
        Advice(
            "wind",
            "wind",
            {
                "direction": round(summary.direction),
                "low": summary.wind_low,
                "high": summary.wind_high,
                "gust": summary.gust,
                "trend": summary.trend,
            },
        )
    ]
    if summary.wind_high < LIGHT_AIR:
        advice.append(Advice("light_air", "windy"))
    elif limits.small and summary.gust - summary.wind_high >= GUSTY_SPREAD:
        key = "gusty_dinghy" if size is SizeClass.DINGHY else "gusty"
        advice.append(Advice(key, "windy"))
    if (limit := SKILL_WIND_LIMITS[skill]) is not None:
        over = [hour for hour in hours if hour.wind > limit]
        if len(over) == 1:
            values = {"limit": limit, "time": over[0].start.isoformat()}
            advice.append(Advice("over_limit_hour", "alert", values, True))
        elif over:
            values = {"limit": limit, **_span(over)}
            advice.append(Advice("over_limit", "alert", values, True))
        elif summary.wind_high >= limit - NEAR_LIMIT:
            advice.append(Advice("near_limit", "alert", {"limit": limit}))
    if summary.wind_high >= limits.wind[0] - REEF_MARGIN:
        advice.append(Advice("depower" if limits.small else "reef", "sail"))
    return advice


def _water(
    spot: Spot, size: SizeClass, summary: Summary, hours: Sequence[Hour]
) -> list[Advice]:
    """Cover waves, wind against the current, offshore wind and the water."""
    advice = []
    if summary.waves is not None:
        waves = {"low": summary.waves[0], "high": summary.waves[1]}
        advice.append(Advice("waves", "waves", waves))
    if against := [hour for hour in hours if _against_current(hour)]:
        flow = "flood" if (against[0].current or 0) > 0 else "ebb"
        advice.append(
            Advice("against_current", "current", {"flow": flow, **_span(against)}, True)
        )
    if size is SizeClass.DINGHY and compass_point(summary.direction) in spot.offshore:
        advice.append(Advice("offshore", "beach", hot=True))
    if summary.water_temperature is not None:
        water = {"temperature": summary.water_temperature}
        advice.append(Advice("water", "water", water))
    return advice


def _weather(summary: Summary) -> list[Advice]:
    """Warn of rain, and the poor visibility that can come with it."""
    if summary.rain_chance is None or summary.rain_chance < RAIN_LIKELY:
        return []
    if summary.visibility is not None and summary.visibility < POOR_VISIBILITY:
        values = {"chance": summary.rain_chance, "visibility": summary.visibility}
        return [Advice("rain_visibility", "rain", values)]
    return [Advice("rain", "rain", {"chance": summary.rain_chance})]


def _tides_and_sunset(
    day: Daylight, hours: Sequence[Hour], tides: Sequence[TideEvent], *, lights: bool
) -> list[Advice]:
    """Give the highs and lows still to come while the boat can sail, and sunset.

    Without navigation lights, that's in daylight.
    """
    advice = []
    if lights:
        first, last = hours[0].start, hours[-1].start + HOUR
    else:
        first, last = max(hours[0].start, day.sunrise), day.sunset
    if coming := [event for event in tides if first <= event.time <= last]:
        events = [
            {"time": event.time.isoformat(), "height": event.height, "high": event.high}
            for event in coming
        ]
        advice.append(Advice("tides", "tide", {"events": events}))
    advice.append(Advice("sunset", "sunset", {"time": day.sunset.isoformat()}))
    return advice


def _span(hours: Sequence[Hour]) -> dict[str, str]:
    """Return when a run of hours starts and ends."""
    return {
        "start": hours[0].start.isoformat(),
        "end": (hours[-1].start + HOUR).isoformat(),
    }


def _against_current(hour: Hour) -> bool:
    """Return whether the wind blows hard against a strong current."""
    if hour.current is None or hour.current_direction is None:
        return False
    downwind = (hour.wind_direction + 180) % 360
    return (
        abs(hour.current) >= AGAINST_CURRENT
        and hour.wind >= AGAINST_CURRENT_WIND
        and angle_between(downwind, hour.current_direction) > AGAINST_CURRENT_ANGLE
    )
