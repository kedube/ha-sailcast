"""The hourly conditions timeline, one per spot.

Every source is turned into one list of hours. Values are in SI units, except
wind and current, which are in knots because every threshold is set in knots.
Local corrections come after: readings nudge the next few hours, then waves
are worked out for the spot's shelter.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, time, timedelta, tzinfo
import math
import statistics
from typing import TYPE_CHECKING, Any

from astral import Observer
from astral.sun import elevation, sun

from .geo import mean_direction
from .nowcast import Adjustment, Observation, latest, nudge
from .waves import shelter

if TYPE_CHECKING:
    from .providers import Tides
    from .providers.noaa_coops import Currents
    from .providers.open_meteo import Forecast, Marine, Spread

HOUR = timedelta(hours=1)


@dataclass(frozen=True, slots=True, kw_only=True)
class Alert:
    """An official warning for a zone or pin, in effect from start to end.

    `issued` and `issuer` say when and by whom, and `details` the warning's
    own description and advice, where the provider asks for them to be shown.
    """

    event: str
    zone: str
    start: datetime
    end: datetime
    headline: str | None = None
    issued: datetime | None = None
    issuer: str | None = None
    details: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Hour:
    """The conditions at a spot for the hour that begins at `start`.

    Wind is the middle value of the forecast models, and `wind_models` keeps
    each model's value in a fixed order; `wind_spread` is the ECMWF ensemble's
    spread (one standard deviation). Current is positive on the flood and
    negative on the ebb, and its direction is where the water flows to. Tide
    heights are above the station's chart datum. `wave_source` says where the
    waves come from, `adjusted` lists the fields readings have nudged, and
    `visibility_measured` says the visibility was read, not forecast.
    """

    start: datetime
    daylight: bool
    wind: float
    gust: float
    wind_direction: float
    wind_models: tuple[float | None, ...] = ()
    temperature: float | None = None
    rain_chance: float | None = None
    weather_code: int | None = None
    visibility: float | None = None
    cape: float | None = None
    wave_height: float | None = None
    wave_period: float | None = None
    wave_direction: float | None = None
    water_temperature: float | None = None
    tide_height: float | None = None
    tide_rising: bool | None = None
    current: float | None = None
    current_direction: float | None = None
    alerts: tuple[Alert, ...] = ()
    wind_spread: float | None = None
    wave_source: str | None = None
    adjusted: tuple[str, ...] = ()
    visibility_measured: bool = False


@dataclass(frozen=True, slots=True)
class Daylight:
    """Sunrise and sunset on a date in a time zone, in UTC to the minute.

    Where the sun doesn't set, they're the day's two midnights; where it
    doesn't rise, they're both noon.
    """

    date: date
    sunrise: datetime
    sunset: datetime
    zone: tzinfo

    def covers(self, hour: datetime) -> bool:
        """Return whether most of the hour that begins then is in daylight."""
        return self.sunrise <= hour + HOUR / 2 < self.sunset


def daylight(latitude: float, longitude: float, day: date, zone: tzinfo) -> Daylight:
    """Return sunrise and sunset at a place on a local date."""
    observer = Observer(latitude, longitude)
    try:
        times = sun(observer, date=day, tzinfo=zone)
    except ValueError:
        midnight = datetime.combine(day, time(), zone)
        noon = midnight + timedelta(hours=12)
        if elevation(observer, noon) > 0:
            return Daylight(
                day, _utc(midnight), _utc(midnight + timedelta(days=1)), zone
            )
        return Daylight(day, _utc(noon), _utc(noon), zone)
    return Daylight(day, _utc(times["sunrise"]), _utc(times["sunset"]), zone)


def _utc(when: datetime) -> datetime:
    """Return a time in UTC, rounded to the minute."""
    rounded = when + timedelta(seconds=30)
    return rounded.replace(second=0, microsecond=0).astimezone(UTC)


def build(
    *,
    forecast: Forecast,
    days: Sequence[Daylight],
    marine: Marine | None = None,
    tides: Tides | None = None,
    currents: Currents | None = None,
    alerts: Sequence[Alert] = (),
    spread: Spread | None = None,
) -> list[Hour]:
    """Return the hours of the given local days, from every source.

    Hours with no wind from any model are left out.
    """
    if not days:
        return []
    zone = days[0].zone
    start = datetime.combine(days[0].date, time(), zone)
    end = datetime.combine(days[-1].date + timedelta(days=1), time(), zone)
    by_date = {day.date: day for day in days}
    marine_index = {when: i for i, when in enumerate(marine.times)} if marine else {}
    spreads = dict(zip(spread.times, spread.values, strict=True)) if spread else {}
    tide_heights = dict(tides.hourly) if tides else {}
    hours = []
    for index, when in enumerate(forecast.times):
        if not start <= when < end:
            continue
        winds = forecast.at("wind_speed_10m", index)
        if not (known_winds := [wind for wind in winds if wind is not None]):
            continue
        wind = statistics.median(known_winds)
        local = when.astimezone(zone)
        sun_day = by_date.get(local.date())
        hour: dict[str, Any] = {
            "start": when,
            "daylight": bool(sun_day and sun_day.covers(when)),
            "wind": wind,
            "gust": _middle(forecast.at("wind_gusts_10m", index)) or wind,
            "wind_direction": mean_direction(forecast.at("wind_direction_10m", index)),
            "wind_models": winds,
            "temperature": _middle(forecast.at("temperature_2m", index)),
            "rain_chance": _most(forecast.at("precipitation_probability", index)),
            "visibility": _least(forecast.at("visibility", index)),
            "cape": _most(forecast.at("cape", index)),
            "alerts": tuple(
                alert
                for alert in alerts
                if alert.start < when + HOUR and alert.end > when
            ),
        }
        if (code := _most(forecast.at("weather_code", index))) is not None:
            hour["weather_code"] = int(code)
        if (sigma := spreads.get(when)) is not None:
            hour["wind_spread"] = sigma
        if marine and (marine_hour := marine_index.get(when)) is not None:
            hour.update(
                wave_height=marine.values["wave_height"][marine_hour],
                wave_period=marine.values["wave_period"][marine_hour],
                wave_direction=marine.values["wave_direction"][marine_hour],
                water_temperature=marine.values["sea_surface_temperature"][marine_hour],
            )
        if tides:
            hour.update(_tide(tides, tide_heights, when))
        if currents:
            hour.update(_current(currents, when))
        hours.append(Hour(**hour))
    return hours


def localize(
    hours: Sequence[Hour],
    *,
    now: datetime,
    forecast: Forecast | None = None,
    marine: Marine | None = None,
    observations: Sequence[Observation] = (),
    open_water: bool = True,
    exposed: Collection[str] | None = None,
    fetch: Callable[[float], float] | None = None,
) -> tuple[list[Hour], tuple[Adjustment, ...]]:
    """Apply a spot's local corrections, and say how readings moved it.

    Readings nudge the next hours first, so the waves follow the nudged
    wind. `forecast` and `marine` are the spot's own, for its sensors.
    """
    rows = [
        {item.name: getattr(hour, item.name) for item in fields(Hour)} for hour in hours
    ]
    adjustments = nudge(
        rows, latest(observations, now), forecast=forecast, marine=marine, now=now
    )
    shelter(rows, open_water=open_water, exposed=exposed, fetch=fetch)
    return [Hour(**row) for row in rows], adjustments


def _tide(
    tides: Tides, heights: dict[datetime, float], when: datetime
) -> dict[str, float | bool | None]:
    """Return the tide's height and whether it's rising at a time."""
    pair = _around(tides.events, when, lambda event: event.time)
    if pair is None:
        return {"tide_height": heights.get(when)}
    before, after = pair
    height = heights.get(when)
    if height is None:
        height = _cosine(before.time, before.height, after.time, after.height, when)
    return {"tide_height": height, "tide_rising": after.high}


def _current(currents: Currents, when: datetime) -> dict[str, float | None]:
    """Return the current's speed and direction at a time, between its events."""
    pair = _around(currents.events, when, lambda event: event.time)
    if pair is None:
        return {}
    before, after = pair
    speed = _cosine(before.time, before.speed, after.time, after.speed, when)
    direction = currents.flood_direction if speed >= 0 else currents.ebb_direction
    return {"current": speed, "current_direction": direction}


def _around[T](
    events: Sequence[T], when: datetime, key: Callable[[T], datetime]
) -> tuple[T, T] | None:
    """Return the events just before (or at) and just after a time."""
    times = [key(event) for event in events]
    index = bisect_right(times, when)
    if index == 0 or index == len(events):
        return None
    return events[index - 1], events[index]


def _cosine(
    start: datetime, start_value: float, end: datetime, end_value: float, when: datetime
) -> float:
    """Interpolate between two turning points along half a cosine wave."""
    fraction = (when - start) / (end - start)
    return (
        start_value + (end_value - start_value) * (1 - math.cos(math.pi * fraction)) / 2
    )


def _middle(values: Sequence[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return statistics.median(known) if known else None


def _most(values: Sequence[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return max(known) if known else None


def _least(values: Sequence[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return min(known) if known else None
